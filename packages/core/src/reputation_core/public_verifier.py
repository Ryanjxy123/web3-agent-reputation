"""Replay public identity, exact query wire and historical Base proof from CAS packets."""

import hashlib
import re
from typing import Any
from uuid import UUID

from eth_abi import decode, encode
from eth_abi.exceptions import DecodingError
from pydantic import TypeAdapter

from .akashi import normalize_proof, verify_proof
from .evidence import hash_bytes, hash_json, strict_json
from .models import (
    AssertionResult,
    Observation,
    Outcome,
    Reason,
    RecordVerificationResult,
    TaskLink,
)
from .models.base import Timestamp
from .models.public_evaluation import (
    KNOWN_TX,
    EvidencePacket,
    PublicReadonlyVerificationInput,
)
from .models.public_evaluation import (
    public_task_payload as public_task_payload,
)
from .public_identity import (
    AKASHI_HTTP_URL,
    AKASHI_MCP_URL,
    associate_readonly_identity,
    normalized_public_metadata,
    parse_registration_metadata,
    readonly_endpoints,
)
from .record_verifier import hex_data, quantity

REGISTRY = "0x8004a169fb4a3325136eb29fa0ceb6d2e539a432"
ORIGIN = "https://anchor.akashi-notari.com"
RPC_ORIGIN = "https://mainnet.base.org"
URI = ORIGIN + "/.well-known/agent-registration.json"
ABI_SHA256 = "cdb8e30f41a56ed53421126dab87551ff2a178b8463646f69f75bc5dc9620564"
INTENT_FIELDS = ("protocol", "capability_id", "method", "origin", "path", "request_json", "started_at")


class PublicResponseSchemaError(ValueError):
    """A retained, well-formed source carries a malformed business result."""


class PublicPaymentRequired(ValueError):
    """A response or selected tool requests a payment outside readonly scope."""


def payment_requested(value: Any) -> bool:
    """Pure payment declaration rule, shared by collection and offline replay."""
    if isinstance(value, dict):
        if any(value.get(key) for key in (
            "payment_required", "paymentRequired", "requires_payment", "requiresPayment",
            "paymentRequirements", "x402Version",
        )):
            return True
        for key, child in value.items():
            if key == "tools":
                if isinstance(child, list) and any(
                    isinstance(tool, dict) and tool.get("name") == "find_proof"
                    and payment_requested(tool) for tool in child
                ):
                    return True
            elif payment_requested(child):
                return True
        return False
    if isinstance(value, list):
        return any(payment_requested(child) for child in value)
    return isinstance(value, str) and re.search(
        r"\b(?:payment[ _]required|requires? payment)\b", value, re.IGNORECASE,
    ) is not None


def _raw(exchange: dict[str, Any], *, status: int = 200) -> tuple[Any, bytes]:
    response = exchange["response"]
    if (not isinstance(response, dict) or type(response.get("status")) is not int
            or response["status"] != status or not isinstance(response.get("audit"), dict)
            or response["audit"].get("payment_required") is not False
            or response.get("raw_body_retained") is not True
            or not isinstance(response.get("raw_body_utf8"), str)):
        raise ValueError("raw source unavailable")
    raw = response["raw_body_utf8"].encode("utf-8")
    if (len(raw) > 1024 * 1024 or type(response.get("body_bytes")) is not int
            or len(raw) != response["body_bytes"]
            or hashlib.sha256(raw).hexdigest() != response.get("body_sha256")):
        raise ValueError("raw source hash or length mismatch")
    value = strict_json(raw)
    if value != response.get("json"):
        raise ValueError("raw source and parsed cache differ")
    scopes = [value]
    if exchange.get("origin") == ORIGIN and exchange.get("path") == "/openapi.json" and isinstance(value, dict):
        paths = value.get("paths")
        path = paths.get("/proof") if isinstance(paths, dict) else None
        selected = path.get("get") if isinstance(path, dict) else None
        scopes = [
            {key: child for key, child in value.items() if key != "paths"},
            {key: child for key, child in path.items() if key not in {
                "get", "put", "post", "delete", "options", "head", "patch", "trace",
            }} if isinstance(path, dict) else {}, selected,
        ]
        # The egress policy forbids these OpenAPI markers even when false or zero.
        if any(isinstance(scope, dict) and any(
            key in scope for key in {"x-payment-info", "x402", "x402Support", "price"}
        ) for scope in scopes):
            raise PublicPaymentRequired("OpenAPI declares payment")
    if any(payment_requested(scope) for scope in scopes):
        raise PublicPaymentRequired("source requests payment")
    if isinstance(value, dict) and isinstance(value.get("result"), dict):
        content = value["result"].get("content")
        if isinstance(content, list):
            for item in content:
                if (isinstance(item, dict) and item.get("type") == "text"
                        and isinstance(item.get("text"), str) and item["text"].lstrip().startswith(("{", "["))
                        and payment_requested(strict_json(item["text"].encode()))):
                    raise PublicPaymentRequired("MCP text requests payment")
    return value, raw


def _exchanges(
    data: PublicReadonlyVerificationInput, refs: tuple[UUID, ...], protocol: str, capability: str
) -> list[dict[str, Any]]:
    packets = {packet.record.evidence_id: packet for packet in data.packets}
    if protocol in {"akashi-http-readonly-v1", "akashi-mcp-readonly-v1"}:
        refs = tuple(ref for ref in refs if packets[ref].record.source != "public-readonly-observation")
    if not refs or len(refs) % 2:
        raise ValueError("missing or incomplete paired source packets")
    result = []
    for index in range(0, len(refs), 2):
        intent = packets[refs[index]]
        response = packets[refs[index + 1]]
        for packet in (intent, response):
            EvidencePacket.model_validate(packet.model_dump(mode="json"))
            if packet.record.observed_at > data.observed_at or packet.record.trust_group != "public-http":
                raise ValueError("source time or trust group differs")
        first, second = intent.body, response.body
        if (not isinstance(first, dict) or not isinstance(second, dict)
                or intent.record.source != "public-readonly-intent"
                or response.record.source != "public-readonly-response"
                or set(first) != set(INTENT_FIELDS)
                or any(first[name] != second.get(name) for name in INTENT_FIELDS)
                or first["protocol"] != protocol or first["capability_id"] != capability
                or first["started_at"] != intent.record.observed_at
                or response.record.observed_at < intent.record.observed_at
                or "error" in second or "response" not in second):
            raise ValueError("request and response provenance differs")
        result.append(second)
    return result


def public_observation(data: PublicReadonlyVerificationInput) -> Observation:
    """Bind saved platform measurements to the original request/response sequence."""
    packets = {packet.record.evidence_id: packet for packet in data.packets}
    measured = [packets[ref] for ref in data.agent_evidence_refs
                if packets[ref].record.source == "public-readonly-observation"]
    if len(measured) != 1 or data.agent_evidence_refs[-1] != measured[0].record.evidence_id:
        raise ValueError("one final observation packet required")
    packet = measured[0]
    EvidencePacket.model_validate(packet.model_dump(mode="json"))
    observation = Observation.model_validate(packet.body)
    network_refs = data.agent_evidence_refs[:-1]
    recovered_unknown = (
        observation.latency_ms is None
        and observation.reason_code == Reason.DISPATCH_UNCERTAIN
        and not observation.accepted
        and observation.error_origin == "platform"
    )
    if (observation.slot_id != data.slot.slot_id or observation.attempt_no != 1
            or observation.dispatch_state != "SETTLED" or observation.diagnostic_only
            or observation.candidate_tx_hash is not None or observation.ended_at is None
            or (observation.latency_ms is None and not recovered_unknown)
            or observation.ended_at < observation.started_at
            or observation.evidence_refs != network_refs or observation.reason_code != data.execution_reason
            or packet.record.trust_group != "public-http"
            or not observation.ended_at <= packet.record.observed_at <= data.observed_at):
        raise ValueError("saved public observation differs from frozen task")
    for ref in network_refs:
        source = packets[ref].record
        if not observation.started_at <= source.observed_at <= observation.ended_at:
            raise ValueError("observation does not cover the original network sources")
    if network_refs:
        final = packets[network_refs[-1]].body
        response = final.get("response") if isinstance(final, dict) else None
        status = response.get("status") if isinstance(response, dict) else None
        if observation.http_status != status:
            raise ValueError("observation status differs from original response")
    elif observation.http_status is not None or observation.accepted:
        raise ValueError("unsent observation cannot claim a response")
    return observation


def _rpc(exchange: dict[str, Any], method: str, params: list[Any]) -> Any:
    request = exchange["request_json"]
    if (exchange["method"] != "POST" or exchange["origin"] != RPC_ORIGIN
            or exchange["path"] != "/" or not isinstance(request, dict)
            or set(request) != {"jsonrpc", "id", "method", "params"}
            or request["jsonrpc"] != "2.0" or type(request["id"]) is not int
            or request["id"] < 1 or request["method"] != method or request["params"] != params):
        raise ValueError("unexpected RPC request")
    value, _ = _raw(exchange)
    if (not isinstance(value, dict) or set(value) != {"jsonrpc", "id", "result"}
            or value["jsonrpc"] != "2.0" or type(value["id"]) is not int
            or value["id"] != request["id"]):
        raise ValueError("invalid RPC envelope")
    return value["result"]


def _block(value: Any, number: str, digest: str) -> None:
    if (not isinstance(value, dict) or str(quantity(value["number"])) != number
            or hex_data(value["hash"], 32) != digest or int(digest[2:], 16) == 0):
        raise ValueError("frozen block differs")


def _abi(value: Any, type_name: str) -> Any:
    raw = bytes.fromhex(hex_data(value)[2:])
    decoded = decode([type_name], raw)[0]
    if encode([type_name], [decoded]) != raw:
        raise ValueError("noncanonical ABI result")
    return decoded


def replay_public_identity(data: PublicReadonlyVerificationInput) -> None:
    """Reconstruct the fixed registration read; a supplied association is only a cache."""
    snapshot, read = data.snapshot, data.snapshot.public_identity
    core = snapshot.core
    packets = {packet.record.evidence_id: packet for packet in data.packets}
    starts = [packets[ref] for ref in data.identity_evidence_refs
              if packets[ref].record.source == "public-identity-read-start"]
    network_refs = tuple(ref for ref in data.identity_evidence_refs
                         if packets[ref].record.source != "public-identity-read-start")
    if len(network_refs) != 20:
        raise ValueError("twenty original identity network sources required")
    if starts:
        if len(starts) != 1 or data.identity_evidence_refs[0] != starts[0].record.evidence_id:
            raise ValueError("one first durable identity start is required")
        start = EvidencePacket.model_validate(starts[0].model_dump(mode="json"))
        body = start.body
        if (not isinstance(body, dict) or set(body) != {"job_id", "agent_ref", "scope", "started_at"}
                or body["scope"] != "public-identity-read-start" or body["agent_ref"] != core.agent_ref.model_dump(mode="json")
                or start.record.trust_group != "platform" or UUID(str(body["job_id"])).version != 4
                or not TypeAdapter(Timestamp).validate_python(body["started_at"])
                <= start.record.observed_at <= packets[network_refs[0]].record.observed_at):
            raise ValueError("durable identity start provenance differs")
    if (read is None or data.identity_evidence_refs != snapshot.evidence_refs
            or read.abi_sha256 != ABI_SHA256
            or core.agent_ref.key_text != f"eip155:8453:{REGISTRY}:98097"
            or core.source_type != "public_registry" or core.declared_executor is not None
            or read.registration_outcome != Outcome.PASS or read.metadata_outcome != Outcome.PASS
            or read.rpc_source != "operator-base-mainnet-v1"
            or read.source_hashes != tuple(dict.fromkeys(
                packets[ref].record.blob_hash for ref in network_refs))
            or snapshot.snapshot_hash != hash_json({
                "core": core.model_dump(mode="json"), "public_identity": read.model_dump(mode="json")})):
        raise ValueError("public snapshot or identity commitment differs")
    if any(packets[ref].record.observed_at > core.captured_at for ref in data.identity_evidence_refs):
        raise ValueError("identity source follows its immutable snapshot")
    exchanges = _exchanges(data, network_refs, "erc8004-public-readonly-v1", "identity-read")
    tag = hex(int(core.read_block_number))
    if quantity(_rpc(exchanges[0], "eth_chainId", [])) != 8453:
        raise ValueError("wrong registry chain")
    genesis = _rpc(exchanges[1], "eth_getBlockByNumber", ["0x0", False])
    _block(genesis, "0", core.registry_chain.genesis_hash)
    _block(_rpc(exchanges[2], "eth_getBlockByNumber", ["latest", False]),
           core.read_block_number, core.read_block_hash)
    code = hex_data(_rpc(exchanges[3], "eth_getCode", [REGISTRY, tag]))
    code_hash = hash_bytes(bytes.fromhex(code[2:]))
    if code == "0x" or code_hash != read.registry_code_hash or code_hash != core.registry_chain.registry_code_hash:
        raise ValueError("registry code commitment differs")
    owner = _abi(_rpc(exchanges[4], "eth_call", [{
        "to": REGISTRY, "data": "0x6352211e" + f"{98097:064x}"}, tag]), "address")
    uri = _abi(_rpc(exchanges[5], "eth_call", [{
        "to": REGISTRY, "data": "0xc87b56dd" + f"{98097:064x}"}, tag]), "string")
    if owner.lower() != core.owner or uri != URI or uri != core.agent_uri or core.registry_revision != 0:
        raise ValueError("owner or registration URI differs")
    for index in (6, 9):
        _block(_rpc(exchanges[index], "eth_getBlockByNumber", [tag, False]),
               core.read_block_number, core.read_block_hash)
    raw_documents = []
    for exchange, path in zip(exchanges[7:9], ("/.well-known/agent-registration.json", "/openapi.json"), strict=True):
        if (exchange["method"] != "GET" or exchange["origin"] != ORIGIN
                or exchange["path"] != path or exchange["request_json"] is not None):
            raise ValueError("unexpected registration document request")
        raw_documents.append(_raw(exchange)[1])
    metadata_raw, openapi_raw = raw_documents
    metadata = parse_registration_metadata(metadata_raw, core.agent_ref)
    normalized = normalized_public_metadata(metadata)
    domain = hash_json({"kind": "erc8004-public-v1", "chain_id": "8453",
                        "genesis_hash": core.registry_chain.genesis_hash, "registry_address": REGISTRY})
    chain = {"chain_id": "8453", "genesis_hash": core.registry_chain.genesis_hash,
             "deployment_instance_id": domain, "registry_code_hash": code_hash}
    if (read.metadata != metadata or read.metadata_bytes_hash != hash_bytes(metadata_raw)
            or read.openapi_bytes_hash != hash_bytes(openapi_raw)
            or core.metadata_hash != hash_json(normalized) or core.normalized_metadata != normalized
            or core.endpoints != readonly_endpoints(metadata)
            or core.registry_chain.model_dump(mode="json") != {**chain, "instance_hash": hash_json(chain)}):
        raise ValueError("registration metadata or chain commitment differs")
    target = AKASHI_HTTP_URL if data.slot.task.protocol == "akashi-http-readonly-v1" else AKASHI_MCP_URL
    association = associate_readonly_identity(snapshot, target, data.slot.task.protocol,
                                             metadata_raw=metadata_raw, openapi_raw=openapi_raw)
    if association != data.association or association.endpoint_outcome != Outcome.PASS:
        raise ValueError("public endpoint association differs")


def replay_public_business(data: PublicReadonlyVerificationInput) -> dict[str, Any]:
    exchanges = _exchanges(data, data.business_evidence_refs, "akashi-business-readonly-v1", "verify_record")
    if len(exchanges) != 8 or data.slot.task.query != {"tx": KNOWN_TX}:
        raise ValueError("missing fixed transaction business witness")
    task, chain = data.slot.task, data.slot.expected.execution_chain
    tag = hex(int(task.read_block_number))
    chain_id = _rpc(exchanges[0], "eth_chainId", [])
    if quantity(chain_id) != 8453:
        raise ValueError("wrong business chain")
    _block(_rpc(exchanges[1], "eth_getBlockByNumber", ["0x0", False]), "0", chain.genesis_hash)
    head = _rpc(exchanges[2], "eth_getBlockByNumber", [tag, False])
    _block(head, task.read_block_number, task.read_block_hash)
    tx = _rpc(exchanges[3], "eth_getTransactionByHash", [KNOWN_TX])
    receipt = _rpc(exchanges[4], "eth_getTransactionReceipt", [KNOWN_TX])
    if not isinstance(receipt, dict):
        raise ValueError("receipt unavailable")
    block_hash = hex_data(receipt["blockHash"], 32)
    block_tag = hex(quantity(receipt["blockNumber"]))
    block = _rpc(exchanges[5], "eth_getBlockByHash", [block_hash, False])
    canonical = _rpc(exchanges[6], "eth_getBlockByNumber", [block_tag, False])
    _block(_rpc(exchanges[7], "eth_getBlockByNumber", [tag, False]), task.read_block_number, task.read_block_hash)
    return {"chain_id": chain_id, "tx": tx, "receipt": receipt,
            "receipt_block": block, "canonical_block": canonical, "head": head}


def replay_public_response(data: PublicReadonlyVerificationInput) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return original business response and normalized proof; no collector cache is trusted."""
    task = data.slot.task
    exchanges = _exchanges(data, data.agent_evidence_refs, task.protocol, "verify_record")
    if any(item["origin"] != ORIGIN for item in exchanges):
        raise ValueError("unexpected public origin")
    if task.protocol == "akashi-http-readonly-v1":
        if len(exchanges) != 1:
            raise ValueError("one HTTP business attempt required")
        exchange = exchanges[0]
        name, value = next(iter(task.query.items()))
        if exchange["method"] != "GET" or exchange["path"] != f"/proof?{name}={value}" or exchange["request_json"] is not None:
            raise ValueError("HTTP query differs from frozen task")
        status = exchange["response"]["status"]
        if type(status) is not int:
            raise ValueError("invalid HTTP status")
        value, _ = _raw(exchange, status=status)
        try:
            normalized = normalize_proof(value) if status == 200 else {}
        except (ValueError, TypeError, KeyError, RecursionError) as exc:
            raise PublicResponseSchemaError("invalid public proof schema") from exc
        return exchange, normalized
    if len(exchanges) != 4:
        raise ValueError("MCP requires complete initialization and discovery originals")
    for exchange in exchanges:
        if exchange["method"] != "POST" or exchange["path"] != "/mcp":
            raise ValueError("unexpected MCP wire")
    initial, notification, discovery, call = exchanges
    request = initial["request_json"]
    if (not isinstance(request, dict) or request.get("method") != "initialize"
            or request.get("params") != {"protocolVersion": "2025-11-25", "capabilities": {},
                                        "clientInfo": {"name": "web3-agent-reputation", "version": "1.0"}}):
        raise ValueError("MCP initialization differs")
    initialized, _ = _raw(initial)
    listed, _ = _raw(discovery)
    value, _ = _raw(call)
    for exchange, response in ((initial, initialized), (discovery, listed), (call, value)):
        request = exchange["request_json"]
        if (not isinstance(request, dict) or set(request) != {"jsonrpc", "id", "method", "params"}
                or request["jsonrpc"] != "2.0" or type(request["id"]) is not int
                or not isinstance(response, dict) or set(response) != {"jsonrpc", "id", "result"}
                or response["jsonrpc"] != "2.0" or type(response["id"]) is not int
                or response["id"] != request["id"] or not isinstance(response["result"], dict)):
            raise ValueError("MCP request/response envelope differs")
    if (initialized["result"].get("protocolVersion") != "2025-11-25"
            or notification["request_json"] != {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}
            or notification["response"].get("status") not in {200, 202, 204}
            or notification["response"].get("audit", {}).get("payment_required") is not False
            or discovery["request_json"]["method"] != "tools/list" or discovery["request_json"]["params"] != {}
            or call["request_json"]["method"] != "tools/call"
            or call["request_json"]["params"] != {"name": "find_proof", "arguments": task.query}):
        raise ValueError("MCP sequence differs")
    notice = notification["response"]
    if notice.get("body_bytes") == 0:
        if (type(notice["body_bytes"]) is not int or notice.get("json") is not None
                or notice.get("raw_body_utf8") not in (None, "")
                or notice.get("body_sha256") != hashlib.sha256(b"").hexdigest()):
            raise ValueError("empty MCP notification original differs")
    else:
        _raw(notification, status=notice["status"])
    tools = listed["result"].get("tools")
    matches = [item for item in tools if isinstance(item, dict) and item.get("name") == "find_proof"] if isinstance(tools, list) else []
    if (len(matches) != 1 or not isinstance(matches[0].get("annotations"), dict)
            or matches[0]["annotations"].get("readOnlyHint") is not True
            or matches[0]["annotations"].get("destructiveHint", False) is not False):
        raise ValueError("MCP tool is not explicitly readonly")
    if any(name in matches[0] for name in (
        "paymentRequired", "payment_required", "requiresPayment", "requires_payment",
        "paymentRequirements", "x402Version", "x402Support", "x-payment-info", "x402", "price",
    )):
        raise ValueError("MCP tool declares payment")
    content = value["result"].get("content", [])
    if not isinstance(content, list) or any(not isinstance(item, dict) or item.get("type") != "text" for item in content):
        raise PublicResponseSchemaError("unsupported MCP business content")
    try:
        normalized = normalize_proof(value["result"], mcp=True)
    except (ValueError, TypeError, KeyError, RecursionError) as exc:
        raise PublicResponseSchemaError("invalid MCP proof schema") from exc
    return call, normalized


def verify_public_readonly(
    data: PublicReadonlyVerificationInput, evidence_refs: tuple[UUID, ...]
) -> RecordVerificationResult:
    slot, task, facts = data.slot, data.slot.task, data.slot.expected
    assertions: list[AssertionResult] = []

    def emit(rule: str, outcome: Outcome, reason: Reason | None, expected: Any = None,
             observed: Any = None, *, critical: bool = False) -> None:
        assertions.append(AssertionResult(
            assertion_id=UUID(bytes=bytes.fromhex(hash_json([str(slot.slot_id), rule, "7"])[2:34]), version=4),
            slot_id=slot.slot_id, rule_id=rule, rule_version="7", outcome=outcome,
            reason_code=reason, expected=expected, observed=observed,
            evidence_refs=evidence_refs, critical=critical,
        ))

    def finish() -> RecordVerificationResult:
        failed = [item for item in assertions if item.outcome == Outcome.FAIL]
        unresolved = [item for item in assertions if item.outcome == Outcome.UNKNOWN]
        outcome = Outcome.FAIL if failed else Outcome.UNKNOWN if unresolved else Outcome.PASS
        reason = failed[0].reason_code if failed else unresolved[0].reason_code if unresolved else None
        return RecordVerificationResult(
            assertions=tuple(assertions), outcome=outcome, reason_code=reason,
            critical_conflict=any(item.critical for item in failed),
            task_link=TaskLink(capability_id="verify_record", completion_kind="readonly-query",
                request_id=task.request_id, executor=None, candidate_tx_hash=None, verified_tx_hash=None,
                block_number=task.read_block_number if outcome == Outcome.PASS else None,
                block_hash=task.read_block_hash if outcome == Outcome.PASS else None,
                log_index=None, match_status=outcome),
        )

    if not evidence_refs:
        emit("evidence.available", Outcome.UNKNOWN, Reason.MISSING_EVIDENCE)
        return finish()
    try:
        PublicReadonlyVerificationInput.model_validate(data.model_dump(mode="json"))
        replay_public_identity(data)
        core = data.snapshot.core
        if (facts.snapshot_hash != data.snapshot.snapshot_hash or facts.agent_ref != core.agent_ref
                or facts.execution_chain != core.registry_chain
                or task.read_block_number != core.read_block_number or task.read_block_hash != core.read_block_hash):
            raise ValueError("frozen evaluation identity differs")
    except (ValueError, TypeError, KeyError, IndexError, AttributeError, DecodingError, RecursionError):
        emit("context.snapshot", Outcome.UNKNOWN, Reason.EVIDENCE_INCONSISTENT)
        return finish()
    emit("context.snapshot", Outcome.PASS, None, data.snapshot.snapshot_hash, facts.snapshot_hash)
    mapping = (data.review.snapshot_hash == data.snapshot.snapshot_hash
               and data.review.review_version == data.review_version
               and data.review.confirmed_claims == ("verify_record",)
               and bool(data.review.mapping_evidence_ids)
               and set(data.review.mapping_evidence_ids).issubset(data.identity_evidence_refs))
    emit("context.mapping", Outcome.PASS if mapping else Outcome.UNKNOWN,
         None if mapping else Reason.MAPPING_UNCONFIRMED)
    dispatched = data.dispatch_started_at
    intent = (dispatched is not None and core.captured_at <= facts.window_start
              <= data.intent_persisted_at <= dispatched <= task.deadline
              and dispatched <= data.observed_at
              and data.dispatch_payload_hash == hash_json(public_task_payload(slot)))
    emit("task.intent", Outcome.PASS if intent else Outcome.UNKNOWN,
         None if intent else data.execution_reason or Reason.DISPATCH_UNCERTAIN)
    grant = data.grant
    authorized = (grant is not None and grant.grant_id == slot.grant_id
                  and grant.snapshot_hash == data.snapshot.snapshot_hash and grant.protocol == task.protocol
                  and task.endpoint_id in grant.endpoint_ids and task.chain_instance_id in grant.chain_instances
                  and task.deadline <= grant.expires_at and dispatched is not None)
    emit("task.authorization", Outcome.PASS if authorized else Outcome.UNKNOWN,
         None if authorized else Reason.ACCESS_NOT_GRANTED)
    emit("identity.readonly", Outcome.PASS, None, "registration and endpoint only", data.association.model_dump(mode="json"))
    if not mapping or not intent or not authorized:
        return finish()
    assert dispatched is not None
    try:
        observation = public_observation(data)
        first_packet = next(packet for packet in data.packets if packet.record.evidence_id == data.agent_evidence_refs[0])
        if first_packet.record.observed_at < dispatched or first_packet.record.observed_at > task.deadline:
            raise ValueError("agent dispatch source precedes authorization or misses deadline")
        exchange, proof = replay_public_response(data)
    except PublicResponseSchemaError:
        if observation.accepted or observation.reason_code != Reason.SCHEMA_ERROR:
            emit("agent.measurement", Outcome.UNKNOWN, Reason.EVIDENCE_INCONSISTENT)
        else:
            emit("agent.evidence", Outcome.PASS, None)
            emit("agent.service", Outcome.FAIL, Reason.SCHEMA_ERROR)
        return finish()
    except PublicPaymentRequired:
        emit("agent.evidence", Outcome.UNKNOWN, Reason.NOT_DECLARED_READ_ONLY)
        return finish()
    except (ValueError, TypeError, KeyError, IndexError, AttributeError, StopIteration, RecursionError):
        emit("agent.evidence", Outcome.UNKNOWN, data.execution_reason or Reason.EVIDENCE_INCONSISTENT)
        return finish()
    emit("agent.evidence", Outcome.PASS, None)
    status = exchange["response"]["status"]
    expected_reason = (None if status == 200 else Reason.RATE_LIMIT_UNATTRIBUTED if status == 429
                       else Reason.AGENT_SERVICE_ERROR if status >= 500 else Reason.SCHEMA_ERROR)
    expected_origin = None if status == 200 else "unknown" if status == 429 else "agent"
    if (observation.accepted != (status == 200) or observation.reason_code != expected_reason
            or observation.error_origin != expected_origin):
        emit("agent.measurement", Outcome.UNKNOWN, Reason.EVIDENCE_INCONSISTENT)
        return finish()
    if slot.case_kind == "negative":
        emit("functional.request_validity", Outcome.PASS, None, "invalid_format", task.query)
        correct = status == 400
        emit("functional.rejection", Outcome.PASS if correct else Outcome.FAIL,
             None if correct else Reason.SEMANTIC_MISMATCH, 400, status, critical=not correct)
        return finish()
    if status != 200:
        unknown = status == 429
        emit("agent.service", Outcome.UNKNOWN if unknown else Outcome.FAIL,
             Reason.RATE_LIMIT_UNATTRIBUTED if unknown else Reason.AGENT_SERVICE_ERROR if status >= 500 else Reason.SCHEMA_ERROR,
             200, status)
        return finish()
    emit("agent.service", Outcome.PASS, None, 200, status)
    if "tx" not in task.query:
        business = verify_proof(proof, task.query, {})
    else:
        try:
            witness = replay_public_business(data)
        except (ValueError, TypeError, KeyError, IndexError, AttributeError, RecursionError):
            emit("business.evidence", Outcome.UNKNOWN, Reason.PLATFORM_RPC_ERROR)
            return finish()
        emit("business.evidence", Outcome.PASS, None)
        business = verify_proof(proof, task.query, witness)
    status = Outcome(business["status"])
    detail = business["reason"]
    reason = None if status == Outcome.PASS else Reason.SEMANTIC_MISMATCH if status == Outcome.FAIL else (
        Reason.PENDING_FINALITY if detail in {"PENDING_FINALITY", "RECEIPT_NOT_CONFIRMED"}
        else Reason.PLATFORM_RPC_ERROR if detail in {"PLATFORM_RPC_ERROR", "RPC_WRONG_CHAIN"}
        else Reason.EVIDENCE_INCONSISTENT if detail == "EVIDENCE_INCONSISTENT"
        else Reason.MISSING_EVIDENCE)
    for item in business["assertions"]:
        item_outcome = Outcome(item["status"])
        emit("public." + item["rule"], item_outcome,
             None if item_outcome == Outcome.PASS else Reason.SEMANTIC_MISMATCH if item_outcome == Outcome.FAIL else reason or Reason.MISSING_EVIDENCE,
             item.get("expected"), item.get("observed"), critical=item_outcome == Outcome.FAIL)
    emit("public.business", status, reason, {"required_class": slot.required_class},
         {"detail": detail, "confirmed_proofs": business["confirmed_proofs"], "confirmations": business["confirmations"]},
         critical=status == Outcome.FAIL)
    return finish()
