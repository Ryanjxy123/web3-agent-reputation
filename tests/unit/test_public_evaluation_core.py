"""Constructed task-10 envelopes over published originals; these are not live runs."""

import hashlib
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError
from reputation_core.evidence import canonical_bytes, hash_bytes, hash_json, strict_json
from reputation_core.models import (
    AgentSnapshot,
    EvidenceRecord,
    Observation,
    Outcome,
    Purpose,
    Reason,
    TaskLink,
)
from reputation_core.models.public_evaluation import (
    KNOWN_TX,
    EvidencePacket,
    PublicReadonlyCaseSlot,
    PublicReadonlyExpectedFacts,
    PublicReadonlyGrant,
    PublicReadonlyRunPlan,
    PublicReadonlyTask,
    PublicReadonlyVerificationInput,
    public_task_payload,
)
from reputation_core.public_identity import (
    AKASHI_HTTP_URL,
    AKASHI_MCP_URL,
    associate_readonly_identity,
)
from reputation_core.public_reporting import build_public_readonly_report
from reputation_core.public_verifier import (
    ORIGIN,
    PublicPaymentRequired,
    _raw,
    public_observation,
    replay_public_identity,
    verify_public_readonly,
)
from reputation_core.reporting import POLICY_V1_HASH

ROOT = Path(__file__).resolve().parents[2]
SAVED = ROOT / "docs/testing/evidence/akashi-identity-2026-10-11"
POC = ROOT / "docs/testing/evidence/akashi-2026-10-11"
TIME = "2026-10-11T05:00:00.000Z"
DEADLINE = "2026-10-11T05:10:00.000Z"


def packet(body, source, observed_at):
    raw = canonical_bytes(body)
    digest = hash_bytes(raw)
    return EvidencePacket(record=EvidenceRecord(
        evidence_id=uuid4(), path=f"blobs/{digest[2:]}.bin", blob_hash=digest,
        byte_count=len(raw), media_type="application/json", source=source, observed_at=observed_at,
        collector_version="platform-v1", redaction_profile="credentials-v1", trust_group="public-http",
    ), body=body)


def exchange(protocol, capability, method, origin, path, request, result, index=0, status=200, notification=False):
    start = f"2026-10-11T05:00:{index + 1:02d}.000Z"
    end = f"2026-10-11T05:00:{index + 1:02d}.500Z"
    intent = {"protocol": protocol, "capability_id": capability, "method": method,
              "origin": origin, "path": path, "request_json": request, "started_at": start}
    raw = canonical_bytes(result) if result is not None else b""
    response = {**intent, "response": {
        "status": status, "content_type": "application/json", "json": result,
        "raw_body_utf8": raw.decode() if not notification else None,
        "raw_body_retained": not notification, "body_sha256": hashlib.sha256(raw).hexdigest(),
        "body_bytes": len(raw), "audit": {"payment_required": False, "body_not_read": False},
    }}
    return (packet(intent, "public-readonly-intent", start), packet(response, "public-readonly-response", end))


def rpc_packet(method, params, result, index):
    identifier = index + 1
    return exchange("akashi-business-readonly-v1", "verify_record", "POST", "https://mainnet.base.org", "/",
                    {"jsonrpc": "2.0", "id": identifier, "method": method, "params": params},
                    {"jsonrpc": "2.0", "id": identifier, "result": result}, index + 12)


def make_input(protocol="akashi-http-readonly-v1", query=None, kind="positive", purpose=Purpose.FUNCTIONAL):
    acceptance = strict_json((SAVED / "acceptance.json").read_bytes())
    snapshot = AgentSnapshot.model_validate(acceptance["snapshot"])
    identity = tuple(EvidencePacket(record=EvidenceRecord.model_validate(record), body=strict_json((SAVED / record["path"]).read_bytes()))
                     for record in acceptance["evidence"])
    query = query or {"tx": KNOWN_TX}
    http = protocol == "akashi-http-readonly-v1"
    endpoint = "akashi-http" if http else "akashi-mcp"
    slot_id, grant_id = uuid4(), uuid4()
    task = PublicReadonlyTask(protocol=protocol, request_id="0x" + uuid4().hex * 2,
        snapshot_hash=snapshot.snapshot_hash, chain_instance_id=snapshot.core.registry_chain.instance_hash,
        endpoint_id=endpoint, query=query, read_block_number=snapshot.core.read_block_number,
        read_block_hash=snapshot.core.read_block_hash, deadline=DEADLINE)
    facts = PublicReadonlyExpectedFacts(agent_ref=snapshot.core.agent_ref, snapshot_hash=snapshot.snapshot_hash,
        execution_chain=snapshot.core.registry_chain, request_id=task.request_id, window_start=TIME,
        deadline=DEADLINE, pre_dispatch_block=task.read_block_number, pre_dispatch_block_hash=task.read_block_hash,
        protocol=protocol, endpoint_id=endpoint, query=query)
    slot = PublicReadonlyCaseSlot(slot_id=slot_id, slot_key="public-query", purpose=purpose, case_kind=kind,
        required_class="invalid_format" if kind == "negative" else "match" if "tx" in query else "not_found",
        expected_outcome=Outcome.PASS if "tx" in query or kind == "negative" else Outcome.UNKNOWN,
        task=task, expected=facts, grant_id=grant_id)
    metadata_raw = (SAVED / "metadata.body").read_bytes()
    openapi_raw = (SAVED / "openapi.body").read_bytes()
    association = associate_readonly_identity(snapshot, AKASHI_HTTP_URL if http else AKASHI_MCP_URL, protocol,
                                             metadata_raw=metadata_raw, openapi_raw=openapi_raw)
    grant = PublicReadonlyGrant(protocol=protocol, grant_id=grant_id, snapshot_hash=snapshot.snapshot_hash,
        endpoint_ids=(endpoint,), methods=("GET",) if http else ("POST",), paths=("/proof",) if http else ("/mcp",),
        chain_instances=(snapshot.core.registry_chain.instance_hash,), max_tasks=5, expires_at=DEADLINE,
        operator="test-operator", consent_ref="free-public-readonly")
    review = {"snapshot_hash": snapshot.snapshot_hash, "review_version": 1, "confirmed_claims": ["verify_record"],
              "mapping_evidence_ids": [str(identity[14].record.evidence_id)], "actor": "operator", "reason": "static protocol review"}
    proof = strict_json((POC / "025-positive-http-1.body").read_bytes())
    agent = []
    if http:
        name, value = next(iter(query.items()))
        response = proof if "tx" in query else {"hash": value, "anchored": False, "proofs": [], "unsearched": ["0xeed9d0f7265892e84e43d05da464c75add199260"]}
        status = 400 if kind == "negative" else 200
        if kind == "negative":
            response = {"error": "invalid hash"}
        agent.extend(exchange(protocol, "verify_record", "GET", "https://anchor.akashi-notari.com", f"/proof?{name}={value}", None, response, status=status))
    else:
        init = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "web3-agent-reputation", "version": "1.0"}}}
        agent.extend(exchange(protocol, "verify_record", "POST", "https://anchor.akashi-notari.com", "/mcp", init,
                              {"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2025-11-25"}}))
        agent.extend(exchange(protocol, "verify_record", "POST", "https://anchor.akashi-notari.com", "/mcp",
                              {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}, None, 1, 202, True))
        agent.extend(exchange(protocol, "verify_record", "POST", "https://anchor.akashi-notari.com", "/mcp",
                              {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
                              {"jsonrpc": "2.0", "id": 2, "result": {"tools": [{"name": "find_proof", "annotations": {"readOnlyHint": True}}]}}, 2))
        agent.extend(exchange(protocol, "verify_record", "POST", "https://anchor.akashi-notari.com", "/mcp",
                              {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "find_proof", "arguments": query}},
                              {"jsonrpc": "2.0", "id": 3, "result": {"structuredContent": proof}}, 3))
        status = 200
    observation = Observation(observation_id=uuid4(), slot_id=slot_id, attempt_no=1, dispatch_state="SETTLED",
        started_at="2026-10-11T05:00:01.000Z", ended_at="2026-10-11T05:00:10.000Z", http_status=status,
        latency_ms=500 if http else 3500, error_origin="agent" if kind == "negative" else None,
        reason_code=Reason.SCHEMA_ERROR if kind == "negative" else None, accepted=kind != "negative",
        candidate_tx_hash=None, evidence_refs=tuple(value.record.evidence_id for value in agent), diagnostic_only=False)
    agent.append(packet(observation.model_dump(mode="json"), "public-readonly-observation", observation.ended_at))
    business = []
    if "tx" in query:
        original_rpc = [value.body for value in identity if isinstance(value.body, dict) and "response" in value.body and value.body["origin"] == "https://mainnet.base.org"]
        genesis = original_rpc[1]["response"]["json"]["result"]
        head = original_rpc[2]["response"]["json"]["result"]
        tx = strict_json((POC / "021-positive-tx.body").read_bytes())["result"]
        receipt = strict_json((POC / "022-positive-receipt.body").read_bytes())["result"]
        block = strict_json((POC / "023-receipt-block.body").read_bytes())["result"]
        canonical = strict_json((POC / "024-canonical-block.body").read_bytes())["result"]
        tag = hex(int(task.read_block_number))
        calls = [("eth_chainId", [], "0x2105"), ("eth_getBlockByNumber", ["0x0", False], genesis),
                 ("eth_getBlockByNumber", [tag, False], head), ("eth_getTransactionByHash", [KNOWN_TX], tx),
                 ("eth_getTransactionReceipt", [KNOWN_TX], receipt),
                 ("eth_getBlockByHash", [receipt["blockHash"], False], block),
                 ("eth_getBlockByNumber", [receipt["blockNumber"], False], canonical),
                 ("eth_getBlockByNumber", [tag, False], head)]
        for index, (method, params, result) in enumerate(calls):
            business.extend(rpc_packet(method, params, result, index))
    return PublicReadonlyVerificationInput(slot=slot, snapshot=snapshot, review=review, review_version=1,
        platform_instance_id="0x" + "ab" * 32, grant=grant, intent_persisted_at=TIME,
        dispatch_started_at="2026-10-11T05:00:01.000Z", dispatch_payload_hash=hash_json(public_task_payload(slot)),
        execution_reason=observation.reason_code, observed_at="2026-10-11T05:03:00.000Z", association=association,
        packets=(*identity, *agent, *business), identity_evidence_refs=tuple(value.record.evidence_id for value in identity),
        agent_evidence_refs=tuple(value.record.evidence_id for value in agent), business_evidence_refs=tuple(value.record.evidence_id for value in business))


def replace_packet(data, index, body):
    packets = list(data.packets)
    old = packets[index]
    new = packet(body, old.record.source, old.record.observed_at)
    new = new.model_copy(update={"record": new.record.model_copy(update={"evidence_id": old.record.evidence_id})})
    packets[index] = new
    return data.model_copy(update={"packets": tuple(packets)})


@pytest.mark.parametrize("protocol", ["akashi-http-readonly-v1", "akashi-mcp-readonly-v1"])
def test_public_historical_business_pass_is_not_executor_binding(protocol):
    data = make_input(protocol)
    result = verify_public_readonly(data, (uuid4(),))
    assert result.outcome == Outcome.PASS, result
    assert result.task_link.executor is None and result.task_link.verified_tx_hash is None
    assert result.task_link.completion_kind == "readonly-query"
    assert data.association.executor_outcome == data.association.business_outcome == Outcome.UNKNOWN


def test_random_digest_is_unknown_and_invalid_input_is_correct_rejection():
    unknown = make_input(query={"hash": "aa" * 32})
    result = verify_public_readonly(unknown, (uuid4(),))
    assert result.outcome == Outcome.UNKNOWN and result.reason_code == Reason.MISSING_EVIDENCE
    assert "SEARCH_INCOMPLETE" in str(result.model_dump())
    invalid = make_input(query={"hash": "not-a-sha256"}, kind="negative")
    assert verify_public_readonly(invalid, (uuid4(),)).outcome == Outcome.PASS


@pytest.mark.parametrize("index", [1, 3, 5, 7, 9, 11, 13, 15, 17, 19])
def test_every_registration_source_raw_mismatch_stays_unknown(index):
    data = make_input()
    body = deepcopy(data.packets[index].body)
    body["response"]["raw_body_utf8"] += " "
    altered = replace_packet(data, index, body)
    assert verify_public_readonly(altered, (uuid4(),)).outcome == Outcome.UNKNOWN


def test_false_proof_with_recomputed_source_hash_is_critical_failure():
    data = make_input()
    body = deepcopy(data.packets[21].body)
    value = deepcopy(body["response"]["json"])
    value["proofs"][0]["filename"] = "incorrect.txt"
    raw = canonical_bytes(value)
    body["response"].update(json=value, raw_body_utf8=raw.decode(), body_sha256=hashlib.sha256(raw).hexdigest(), body_bytes=len(raw))
    result = verify_public_readonly(replace_packet(data, 21, body), (uuid4(),))
    assert result.outcome == Outcome.FAIL and result.critical_conflict
    assert any(item.rule_id == "public.proof.events" and item.outcome == Outcome.FAIL for item in result.assertions)


def test_missing_or_changed_business_rpc_never_becomes_agent_failure():
    data = make_input()
    body = deepcopy(data.packets[-1].body)
    body["request_json"]["params"][0] = "latest"
    result = verify_public_readonly(replace_packet(data, len(data.packets) - 1, body), (uuid4(),))
    assert result.outcome == Outcome.UNKNOWN and result.reason_code == Reason.PLATFORM_RPC_ERROR
    assert not result.critical_conflict


def test_nullable_executor_cannot_enter_old_execution_or_rejection():
    data = make_input()
    link = verify_public_readonly(data, (uuid4(),)).task_link.model_dump(mode="json")
    for kind in ("execution", "rejection"):
        with pytest.raises(ValidationError):
            TaskLink.model_validate({**link, "completion_kind": kind})
    with pytest.raises(ValidationError):
        TaskLink.model_validate({**link, "executor": "0x" + "ab" * 20})


def make_report(data=None):
    data = data or make_input(purpose=Purpose.AVAILABILITY)
    plan = PublicReadonlyRunPlan(run_id=uuid4(), snapshot_hash=data.snapshot.snapshot_hash,
        review_version=1, policy_hash=POLICY_V1_HASH, planning_time=TIME, slots=(data.slot,))
    policy = strict_json((ROOT / "configs/policies/policy-v1.json").read_bytes())
    report = build_public_readonly_report(plan, (data,), (uuid4(),), (public_observation(data),), policy,
        evaluated_at="2026-10-11T05:04:00.000Z", code_version="a" * 40,
        manifest_hash="0x" + "cd" * 32, previous_report_hash="0x" + "00" * 32)
    return report, plan, data, policy


def test_small_real_read_plan_reuses_exact_partial_gates():
    report, _, _, _ = make_report()
    assert report.schema_version == "1.6.0"
    assert report.scores.overall_score_bp is None and report.scores.evaluation_state == "PARTIAL"
    assert report.raw_statistics["availability"]["decided"] == 1
    assert report.raw_statistics["availability"]["responded"] == 1
    assert report.evidence_sufficiency.thresholds["availability_min_samples"] == 20
    assert set(report.evidence_sufficiency.capabilities[0]["missing_classes"]) == set(("match", "not_found", "hash_mismatch", "invalid_format", "forbidden_contract"))


def test_report_rejects_observation_mutation_even_with_same_raw_http():
    _, plan, data, policy = make_report()
    altered = public_observation(data).model_copy(update={"latency_ms": 0})
    with pytest.raises(ValueError, match="REPORT_CONTEXT_MISMATCH"):
        build_public_readonly_report(plan, (data,), (uuid4(),), (altered,), policy,
            evaluated_at="2026-10-11T05:04:00.000Z", code_version="a" * 40,
            manifest_hash="0x" + "cd" * 32, previous_report_hash="0x" + "00" * 32)


@pytest.mark.parametrize("change", [{"grant": None}, {"dispatch_started_at": None},
    {"dispatch_payload_hash": "0x" + "00" * 32}, {"review_version": 2}])
def test_public_query_requires_mapping_authorization_and_durable_intent(change):
    data = make_input().model_copy(update=change)
    result = verify_public_readonly(data, (uuid4(),))
    assert result.outcome == Outcome.UNKNOWN and not result.critical_conflict


@pytest.mark.parametrize("field,value", [("raw_body_retained", False), ("body_bytes", 0), ("body_sha256", "0" * 64)])
def test_business_raw_original_is_required_even_if_cached_json_looks_valid(field, value):
    data = make_input()
    body = deepcopy(data.packets[-1].body)
    body["response"][field] = value
    result = verify_public_readonly(replace_packet(data, len(data.packets) - 1, body), (uuid4(),))
    assert result.outcome == Outcome.UNKNOWN and result.reason_code == Reason.PLATFORM_RPC_ERROR


def test_exact_query_wire_cannot_be_replaced_with_an_unrelated_success():
    data = make_input()
    packets = list(data.packets)
    for index in (20, 21):
        body = deepcopy(packets[index].body)
        body["path"] = "/proof?hash=" + "aa" * 32
        data = replace_packet(data, index, body)
    assert verify_public_readonly(data, (uuid4(),)).outcome == Outcome.UNKNOWN


def test_report_retains_confirmed_critical_conflict_with_partial_score():
    data = make_input()
    body = deepcopy(data.packets[21].body)
    value = deepcopy(body["response"]["json"])
    value["anchored"] = False
    raw = canonical_bytes(value)
    body["response"].update(json=value, raw_body_utf8=raw.decode(), body_sha256=hashlib.sha256(raw).hexdigest(), body_bytes=len(raw))
    report, _, _, _ = make_report(replace_packet(data, 21, body))
    assert report.scores.overall_score_bp is None
    assert report.risk_assessment.conclusion == "CONFIRMED_CRITICAL_CONFLICT"
    assert report.risk_assessment.critical_findings and report.scores.critical_conflict
    assert report.raw_statistics["public_identity"]["business_outcome"] == "FAIL"


@pytest.mark.parametrize("kind", ["correct_rejection", "service_failure"])
def test_report_does_not_confuse_rejection_or_service_with_business_evidence(kind):
    if kind == "correct_rejection":
        data = make_input(query={"hash": "not-a-sha256"}, kind="negative")
    else:
        data = make_input()
        body = deepcopy(data.packets[21].body)
        value = {"error": "temporarily unavailable"}
        raw = canonical_bytes(value)
        body["response"].update(status=500, json=value, raw_body_utf8=raw.decode(),
            body_sha256=hashlib.sha256(raw).hexdigest(), body_bytes=len(raw))
        data = replace_packet(data, 21, body)
        body = deepcopy(data.packets[22].body)
        body.update(http_status=500, accepted=False, reason_code="AGENT_SERVICE_ERROR", error_origin="agent")
        data = replace_packet(data, 22, body).model_copy(update={"execution_reason": Reason.AGENT_SERVICE_ERROR})
    report, _, _, _ = make_report(data)
    assert report.task_counts.pass_count == int(kind == "correct_rejection")
    assert report.task_counts.fail_count == int(kind == "service_failure")
    assert report.raw_statistics["public_identity"]["business_outcome"] == "UNKNOWN"
    assert not any(assertion.rule_id == "public.business" for assertion in report.assertions)


def test_recovered_unknown_observation_retains_original_sources_without_latency_claim():
    data = make_input()
    body = deepcopy(data.packets[22].body)
    recovery_at = "2026-10-11T05:04:00.000Z"
    body.update(
        started_at="2026-10-11T05:00:01.000Z", ended_at=recovery_at,
        latency_ms=None, error_origin="platform", reason_code="DISPATCH_UNCERTAIN",
        accepted=False, http_status=200,
    )
    replaced = replace_packet(data, 22, body)
    packet_value = replaced.packets[22]
    packet_value = packet_value.model_copy(update={
        "record": packet_value.record.model_copy(update={"observed_at": recovery_at})
    })
    packets = list(replaced.packets)
    packets[22] = packet_value
    recovered = replaced.model_copy(update={
        "packets": tuple(packets), "observed_at": recovery_at,
        "execution_reason": Reason.DISPATCH_UNCERTAIN,
    })
    observation = public_observation(recovered)
    assert observation.latency_ms is None and observation.accepted is False
    result = verify_public_readonly(recovered, (uuid4(),))
    assert result.outcome == Outcome.UNKNOWN


def test_one_response_cannot_be_counted_in_two_public_slots():
    data = make_input()
    second = make_input(purpose=Purpose.AVAILABILITY)
    second = second.model_copy(update={"slot": second.slot.model_copy(update={"slot_key": "separate-availability"})})
    plan = PublicReadonlyRunPlan(run_id=uuid4(), snapshot_hash=data.snapshot.snapshot_hash,
        review_version=1, policy_hash=POLICY_V1_HASH, planning_time=TIME, slots=(data.slot, second.slot))
    policy = strict_json((ROOT / "configs/policies/policy-v1.json").read_bytes())
    with pytest.raises(ValueError, match="REPORT_AGENT_SAMPLE_REUSED"):
        build_public_readonly_report(plan, (data, second), (uuid4(), uuid4()),
            (public_observation(data), public_observation(second)), policy,
            evaluated_at="2026-10-11T05:04:00.000Z", code_version="a" * 40,
            manifest_hash="0x" + "cd" * 32, previous_report_hash="0x" + "00" * 32)


def test_public_report_cannot_be_relabelled_as_a_legacy_schema():
    report, _, _, _ = make_report()
    with pytest.raises(ValidationError):
        type(report).model_validate({**report.model_dump(mode="json"), "schema_version": "1.5.0"})


def test_failed_refresh_association_is_not_presented_as_identity_pass_in_report():
    data = make_input()
    bad_association = data.association.model_copy(update={"snapshot_hash": "0x" + "cc" * 32})
    report, _, _, _ = make_report(data.model_copy(update={"association": bad_association}))
    assert report.task_counts.unknown_count == 1
    assert report.raw_statistics["public_identity"]["registration_outcome"] == "UNKNOWN"
    assert report.raw_statistics["public_identity"]["executor_outcome"] == "UNKNOWN"


def test_formal_ingest_durable_start_packet_is_replayed_with_twenty_network_originals():
    data = make_input()
    started = "2026-10-11T04:30:00.000Z"
    ledger = packet({"job_id": str(uuid4()), "agent_ref": data.snapshot.core.agent_ref.model_dump(mode="json"),
                     "scope": "public-identity-read-start", "started_at": started}, "public-identity-read-start", started)
    ledger = ledger.model_copy(update={"record": ledger.record.model_copy(update={"trust_group": "platform"})})
    refs = (ledger.record.evidence_id, *data.identity_evidence_refs)
    snapshot = data.snapshot.model_copy(update={"evidence_refs": refs})
    data = data.model_copy(update={"snapshot": snapshot, "identity_evidence_refs": refs, "packets": (ledger, *data.packets)})
    assert verify_public_readonly(data, (uuid4(),)).outcome == Outcome.PASS
    body = deepcopy(ledger.body)
    body["agent_ref"]["agent_id"] = "98098"
    assert verify_public_readonly(replace_packet(data, 0, body), (uuid4(),)).outcome == Outcome.UNKNOWN


@pytest.mark.parametrize("source", ["initialize", "tool_nested", "notification", "call_text"])
def test_nested_mcp_payment_is_rejected_after_raw_and_cas_recommit(source):
    data = make_input("akashi-mcp-readonly-v1")
    index = {"initialize": 21, "notification": 23, "tool_nested": 25, "call_text": 27}[source]
    body = deepcopy(data.packets[index].body)
    value = deepcopy(body["response"]["json"])
    if source == "tool_nested":
        value["result"]["tools"][0]["annotations"]["paymentRequired"] = True
    elif source == "initialize":
        value["result"]["paymentRequirements"] = {"amount": "1"}
    elif source == "notification":
        value = {"paymentRequired": True}
    else:
        value["result"]["content"] = [{"type": "text", "text": '{"requiresPayment":true}'}]
    raw = canonical_bytes(value)
    body["response"].update(json=value, raw_body_utf8=raw.decode(), raw_body_retained=True,
        body_sha256=hashlib.sha256(raw).hexdigest(), body_bytes=len(raw))
    result = verify_public_readonly(replace_packet(data, index, body), (uuid4(),))
    assert result.outcome == Outcome.UNKNOWN and result.reason_code == Reason.NOT_DECLARED_READ_ONLY


def test_unrelated_paid_mcp_tool_does_not_reclassify_free_find_proof():
    data = make_input("akashi-mcp-readonly-v1")
    body = deepcopy(data.packets[25].body)
    value = deepcopy(body["response"]["json"])
    value["result"]["tools"].append({"name": "anchor_hash", "paymentRequired": True})
    raw = canonical_bytes(value)
    body["response"].update(json=value, raw_body_utf8=raw.decode(), body_sha256=hashlib.sha256(raw).hexdigest(), body_bytes=len(raw))
    assert verify_public_readonly(replace_packet(data, 25, body), (uuid4(),)).outcome == Outcome.PASS


@pytest.mark.parametrize("field,value", [
    ("x-payment-info", False), ("x402", {}), ("x402Support", False), ("price", 0),
])
@pytest.mark.parametrize("scope", ["global", "path", "get"])
def test_openapi_payment_marker_is_rejected_even_when_false(field, value, scope):
    document = {"openapi": "3.1.0", "paths": {"/proof": {"get": {"operationId": "proof"}}}}
    node = document if scope == "global" else document["paths"]["/proof"]
    if scope == "get":
        node = node["get"]
    node[field] = value
    source = exchange("erc8004-public-readonly-v1", "identity-read", "GET", ORIGIN,
                      "/openapi.json", None, document)[1].body
    with pytest.raises(PublicPaymentRequired):
        _raw(source)


def test_identity_start_without_network_sources_is_rejected_without_index_error():
    data = make_input()
    started = "2026-10-11T04:30:00.000Z"
    ledger = packet({"job_id": str(uuid4()), "agent_ref": data.snapshot.core.agent_ref.model_dump(mode="json"),
                     "scope": "public-identity-read-start", "started_at": started},
                    "public-identity-read-start", started)
    ledger = ledger.model_copy(update={"record": ledger.record.model_copy(update={"trust_group": "platform"})})
    snapshot = data.snapshot.model_copy(update={"evidence_refs": (ledger.record.evidence_id,)})
    malformed = data.model_copy(update={"snapshot": snapshot,
                                        "identity_evidence_refs": (ledger.record.evidence_id,),
                                        "packets": (ledger, *data.packets)})
    with pytest.raises(ValueError):
        replay_public_identity(malformed)
    assert verify_public_readonly(malformed, (uuid4(),)).outcome == Outcome.UNKNOWN
