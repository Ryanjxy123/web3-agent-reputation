"""Static free proof queries; service responses remain unverified business evidence."""

import asyncio
import hashlib
import re
import time
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID, uuid4

import httpx
from reputation_core.akashi import normalize_proof
from reputation_core.evidence import canonical_bytes, strict_json
from reputation_core.models import DispatchState, EvidenceRecord, Observation, Reason
from sqlalchemy import Connection

from reputation_platform.adapters.registries.demo import timestamp
from reputation_platform.infrastructure.evidence_store import SECRET_FIELDS, EvidenceStore, redact
from reputation_platform.infrastructure.network.safe_http import (
    HttpObservation,
    NetworkPolicyError,
    SafeHttpClient,
    decode_public_json,
    payment_requested,
)

ORIGIN = "https://anchor.akashi-notari.com"
PROTOCOLS = ("akashi-http-readonly-v1", "akashi-mcp-readonly-v1")
MCP_VERSION = "2025-11-25"


class EvidencePersistenceError(RuntimeError):
    pass


def _evidence_json(value: Any) -> Any:
    """Redact credentials inside MCP text JSON as well as structured JSON."""
    value = redact(value)
    if isinstance(value, dict):
        secret_names = {key.replace("_", "").replace("-", "") for key in SECRET_FIELDS} | {
            "refreshtoken", "clientsecret", "mcpsessionid", "sessionid",
        }
        result = {
            key: "[REDACTED]" if key.lower().replace("_", "").replace("-", "") in secret_names
            else _evidence_json(child) for key, child in value.items()
        }
        if result.get("type") == "text" and isinstance(result.get("text"), str):
            try:
                embedded = strict_json(result["text"].encode())
                scrubbed = _evidence_json(embedded)
                if scrubbed != embedded:
                    result["text"] = canonical_bytes(scrubbed).decode()
            except (ValueError, RecursionError):
                result["text"] = "[OPAQUE TEXT OMITTED]"
        return result
    if isinstance(value, list):
        return [_evidence_json(child) for child in value]
    if isinstance(value, str) and re.search(
        r'(?i)bearer\s|(?:authorization|cookie|api[_-]?key|access[_-]?token|token|password|'
        r'secret|private[_-]?key)["\x27]?\s*[:=]|-----BEGIN .*PRIVATE KEY', value
    ):
        return "[REDACTED]"
    return value


@dataclass(frozen=True)
class ReadonlyResult:
    observation: Observation
    normalized: dict[str, Any] | None
    evidence: tuple[EvidenceRecord, ...]

    def registered(self, connection: Connection, store: EvidenceStore) -> "ReadonlyResult":
        records = tuple(store.register(connection, record) for record in self.evidence)
        observation = self.observation.model_copy(update={
            "evidence_refs": tuple(dict.fromkeys(record.evidence_id for record in records)),
        })
        return ReadonlyResult(observation, self.normalized, records)


class AkashiReadonlyAdapter:
    capability_id = "verify_record"

    def __init__(self, protocol: str, client: SafeHttpClient, evidence: EvidenceStore):
        if protocol not in PROTOCOLS or not client.is_public_readonly:
            raise NetworkPolicyError("UNSUPPORTED_PUBLIC_PROTOCOL")
        self.protocol, self.client, self.evidence = protocol, client, evidence
        self._identifier = 0
        self._session: str | None = None
        self._initialized = False
        self._negotiated = False
        self._stopped = False
        self._lock = asyncio.Lock()
        self._response: HttpObservation | None = None

    async def _save(self, value, source, observed_at):
        try:
            return await asyncio.to_thread(
                self.evidence.prepare_json, value, source, observed_at, "public-http"
            )
        except (OSError, ValueError, RecursionError):
            self._stopped = True
            raise EvidencePersistenceError("PUBLIC_EVIDENCE_SAVE_FAILED") from None

    async def _request(self, method, path, payload, records):
        started = timestamp()
        intent = {"protocol": self.protocol, "capability_id": self.capability_id,
                  "method": method, "origin": ORIGIN,
                  "path": path, "request_json": payload, "started_at": started}
        # A durable intent is required before every network attempt, including discovery.
        records.append(await self._save(intent, "public-readonly-intent", started))
        headers = None
        if path == "/mcp" and self._negotiated:
            headers = {"mcp-protocol-version": MCP_VERSION}
            if self._session:
                headers["mcp-session-id"] = self._session
        try:
            response = await self.client.request(method, ORIGIN, path, json=payload, headers=headers)
        except (NetworkPolicyError, httpx.HTTPError, TimeoutError) as exc:
            error = str(exc) if isinstance(exc, NetworkPolicyError) else type(exc).__name__
            records.append(await self._save(
                {**intent, "error": error}, "public-readonly-response", timestamp()
            ))
            raise
        self._response = response
        parsed = None
        try:
            parsed = decode_public_json(response)
        except NetworkPolicyError:
            pass
        redacted = _evidence_json(parsed)
        retain_raw = parsed is not None and redacted == parsed and response.status != 402
        response_evidence = {
            **intent,
            "response": {
                "status": response.status, "content_type": response.content_type,
                "json": redacted,
                "raw_body_utf8": response.body.decode() if retain_raw else None,
                "raw_body_retained": retain_raw,
                "body_sha256": hashlib.sha256(response.body).hexdigest()
                if not response.audit.get("body_not_read") else None,
                "body_bytes": len(response.body), "audit": response.audit,
            },
        }
        records.append(await self._save(
            response_evidence, "public-readonly-response", timestamp()
        ))
        if response.audit.get("payment_required") or response.status == 402:
            self._stopped = True
            raise NetworkPolicyError("PAYMENT_REQUIRED")
        return response

    async def _mcp(self, method, params, records):
        self._identifier += 1
        identifier = self._identifier
        response = await self._request("POST", "/mcp", {
            "jsonrpc": "2.0", "id": identifier, "method": method, "params": params,
        }, records)
        if response.status != 200:
            return response, None
        value = decode_public_json(response)
        if (set(value) != {"jsonrpc", "id", "result"} or value["jsonrpc"] != "2.0"
                or type(value["id"]) is not int or value["id"] != identifier
                or not isinstance(value["result"], dict)):
            raise NetworkPolicyError("INVALID_MCP_ENVELOPE")
        return response, value["result"]

    async def query(
        self, query: dict[str, str], slot_id: UUID, *, attempt_no: int = 1
    ) -> ReadonlyResult:
        if (not isinstance(query, dict) or set(query) not in ({"tx"}, {"hash"})
                or not all(isinstance(value, str) for value in query.values())
                or ("tx" in query and re.fullmatch(r"0x[0-9a-fA-F]{64}", query["tx"]) is None)
                or ("hash" in query and re.fullmatch(r"(?:0x)?[0-9a-fA-F]{64}", query["hash"]) is None
                    and not (self.protocol == PROTOCOLS[0] and query["hash"] == "not-a-sha256"))
                or type(attempt_no) is not int or attempt_no < 1):
            raise NetworkPolicyError("INVALID_PROOF_QUERY")
        async with self._lock:
            if self._stopped:
                raise NetworkPolicyError("PUBLIC_ADAPTER_STOPPED")
            started = timestamp()
            timer = time.monotonic()
            records: list[EvidenceRecord] = []
            self._response = None
            response: HttpObservation | None = None
            normalized = None
            reason = None
            origin: Literal["platform", "agent", "unknown"] | None = None
            try:
                if self.protocol == PROTOCOLS[1]:
                    if not self._initialized:
                        response, init = await self._mcp("initialize", {
                            "protocolVersion": MCP_VERSION, "capabilities": {},
                            "clientInfo": {"name": "web3-agent-reputation", "version": "1.0"},
                        }, records)
                        if init is None or init.get("protocolVersion") != MCP_VERSION:
                            raise NetworkPolicyError("MCP_INITIALIZATION_FAILED")
                        self._session = response.headers.get("mcp-session-id")
                        self._negotiated = True
                        notification = await self._request("POST", "/mcp", {
                            "jsonrpc": "2.0", "method": "notifications/initialized", "params": {},
                        }, records)
                        if notification.status not in {200, 202, 204}:
                            raise NetworkPolicyError("MCP_INITIALIZATION_FAILED")
                        response, discovery = await self._mcp("tools/list", {}, records)
                        tools = discovery.get("tools") if discovery else None
                        matches = [tool for tool in tools if isinstance(tool, dict)
                                   and tool.get("name") == "find_proof"] if isinstance(tools, list) else []
                        annotations = matches[0].get("annotations") if len(matches) == 1 else None
                        if len(matches) == 1 and payment_requested(matches[0]):
                            self._stopped = True
                            raise NetworkPolicyError("PAYMENT_REQUIRED")
                        if (not isinstance(annotations, dict)
                                or annotations.get("readOnlyHint") is not True
                                or annotations.get("destructiveHint", False) is not False):
                            self._stopped = True
                            raise NetworkPolicyError("MCP_TOOL_NOT_READONLY")
                        self._initialized = True
                    response, value = await self._mcp("tools/call", {
                        "name": "find_proof", "arguments": query,
                    }, records)
                    if value is not None:
                        content = value.get("content", [])
                        if (not isinstance(content, list) or any(
                            not isinstance(item, dict) or item.get("type") != "text"
                            for item in content
                        )):
                            raise NetworkPolicyError("UNKNOWN_MCP_CONTENT")
                        normalized = normalize_proof(value, mcp=True)
                else:
                    name, value = next(iter(query.items()))
                    response = await self._request("GET", f"/proof?{name}={value}", None, records)
                    if response.status == 200:
                        normalized = normalize_proof(decode_public_json(response))
                if response.status != 200:
                    reason = Reason.RATE_LIMIT_UNATTRIBUTED if response.status == 429 else (
                        Reason.AGENT_SERVICE_ERROR if response.status >= 500 else Reason.SCHEMA_ERROR
                    )
                    origin = "unknown" if response.status == 429 else "agent"
                if normalized is not None and _evidence_json(normalized) != normalized:
                    normalized = None
                    raise ValueError("SENSITIVE_PROOF_FIELDS")
            except (TimeoutError, httpx.TimeoutException):
                if self.protocol == PROTOCOLS[1]:
                    self._stopped = True
                reason, origin = Reason.SERVICE_TIMEOUT, "unknown"
            except httpx.HTTPError:
                if self.protocol == PROTOCOLS[1]:
                    self._stopped = True
                reason, origin = Reason.PLATFORM_NETWORK_ERROR, "platform"
            except NetworkPolicyError:
                if self.protocol == PROTOCOLS[1]:
                    self._stopped = True
                reason, origin = Reason.UNSUPPORTED_PROTOCOL, "unknown"
            except (ValueError, TypeError, KeyError, RecursionError):
                if self.protocol == PROTOCOLS[1]:
                    self._stopped = True
                reason, origin = Reason.SCHEMA_ERROR, "agent"
            except OSError:
                self._stopped = True
                raise
            return ReadonlyResult(Observation(
                observation_id=uuid4(), slot_id=slot_id, attempt_no=attempt_no,
                dispatch_state=DispatchState.SETTLED, started_at=started,
                ended_at=timestamp(),
                http_status=self._response.status if self._response else None,
                latency_ms=round((time.monotonic() - timer) * 1000), error_origin=origin,
                reason_code=reason, accepted=normalized is not None and reason is None,
                candidate_tx_hash=None, evidence_refs=tuple(record.evidence_id for record in records),
                diagnostic_only=attempt_no > 1,
            ), normalized, tuple(records))
