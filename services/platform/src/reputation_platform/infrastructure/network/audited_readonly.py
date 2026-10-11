"""Persist public read-only intent before egress and redact the immutable response."""

import asyncio
import hashlib
import re
from collections.abc import Callable
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

import httpx
from reputation_core.evidence import canonical_bytes, strict_json
from reputation_core.models import EvidenceRecord

from reputation_platform.infrastructure.evidence_store import SECRET_FIELDS, EvidenceStore, redact
from reputation_platform.infrastructure.network.safe_http import (
    HttpObservation,
    NetworkPolicyError,
    SafeHttpClient,
    decode_public_json,
)


class EvidencePersistenceError(RuntimeError):
    pass


def evidence_json(value: Any) -> Any:
    """Redact credentials inside MCP text JSON as well as structured JSON."""
    value = redact(value)
    if isinstance(value, dict):
        secret_names = {key.replace("_", "").replace("-", "") for key in SECRET_FIELDS} | {
            "refreshtoken", "clientsecret", "mcpsessionid", "sessionid",
        }
        result = {
            key: "[REDACTED]" if key.lower().replace("_", "").replace("-", "") in secret_names
            else evidence_json(child) for key, child in value.items()
        }
        if result.get("type") == "text" and isinstance(result.get("text"), str):
            try:
                embedded = strict_json(result["text"].encode())
                scrubbed = evidence_json(embedded)
                if scrubbed != embedded:
                    result["text"] = canonical_bytes(scrubbed).decode()
            except (ValueError, RecursionError):
                result["text"] = "[OPAQUE TEXT OMITTED]"
        return result
    if isinstance(value, list):
        return [evidence_json(child) for child in value]
    if isinstance(value, str) and re.search(
        r'(?i)bearer\s|(?:authorization|cookie|api[_-]?key|access[_-]?token|token|password|'
        r'secret|private[_-]?key)["\x27]?\s*[:=]|-----BEGIN .*PRIVATE KEY', value,
    ):
        return "[REDACTED]"
    return value


def _timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


async def audited_readonly_request(
    client: SafeHttpClient, store: EvidenceStore, *, protocol: str, capability_id: str,
    method: str, origin: str, path: str, payload: dict | None,
    records: list[EvidenceRecord], headers: dict[str, str] | None = None,
    response_redactor: Callable[[dict], dict] | None = None,
) -> HttpObservation:
    if not client.is_public_readonly:
        raise NetworkPolicyError("PUBLIC_READONLY_REQUIRED")

    async def save(value, source, observed_at):
        try:
            return await asyncio.to_thread(
                store.prepare_json, value, source, observed_at, "public-http",
            )
        except (OSError, ValueError, RecursionError):
            client.stop_public_readonly("PUBLIC_EVIDENCE_SAVE_FAILED")
            raise EvidencePersistenceError("PUBLIC_EVIDENCE_SAVE_FAILED") from None

    started = _timestamp()
    intent = {"protocol": protocol, "capability_id": capability_id,
              "method": method, "origin": origin,
              "path": path, "request_json": payload, "started_at": started}
    # A durable intent is required before every network attempt, including discovery.
    records.append(await save(intent, "public-readonly-intent", started))
    try:
        response = await client.request(method, origin, path, json=payload, headers=headers)
    except (NetworkPolicyError, httpx.HTTPError, TimeoutError) as exc:
        error = str(exc) if isinstance(exc, NetworkPolicyError) else type(exc).__name__
        records.append(await save(
            {**intent, "error": error}, "public-readonly-response", _timestamp(),
        ))
        raise
    parsed = None
    try:
        parsed = decode_public_json(response)
    except NetworkPolicyError:
        pass
    redacted = evidence_json(
        response_redactor(deepcopy(parsed))
        if response_redactor is not None and parsed is not None else parsed,
    )
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
    records.append(await save(
        response_evidence, "public-readonly-response", _timestamp(),
    ))
    if response.audit.get("payment_required") or response.status == 402:
        client.stop_public_readonly("PAYMENT_REQUIRED")
    return response
