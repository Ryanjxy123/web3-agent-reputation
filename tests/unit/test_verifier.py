from copy import deepcopy
from pathlib import Path
from uuid import UUID, uuid4
from zipfile import ZipFile

import pytest
from reputation_core.case_templates import mutated_payload
from reputation_core.evidence import canonical_bytes, hash_bytes, hash_json, strict_json
from reputation_core.models import (
    AnchorReceipt,
    DispatchState,
    EvidenceManifest,
    EvidenceRecord,
    ManifestDocument,
    Observation,
    PublicationContext,
    RecordVerificationInput,
    RunPlan,
)
from reputation_core.record_verifier import verify_record
from reputation_core.reporting import build_report
from reputation_verifier import VerificationError, verify_bundle

from tests.factories import ADDRESS, NOW, ZERO
from tests.unit.test_capability_rules import read_input
from tests.unit.test_task_outcomes import (
    claim_result,
    excluded_input,
    reverted_anchor_input,
)
from tests.unit.test_task_outcomes import (
    task_input as v2_task_input,
)


def test_verifier_rejects_path_traversal(tmp_path):
    path = tmp_path / "unsafe.zip"
    with ZipFile(path, "w") as archive:
        archive.writestr("../report_core.json", b"{}")
    with pytest.raises(VerificationError) as failure:
        verify_bundle(str(path))
    assert failure.value.code == "UNSAFE_ARCHIVE"


def test_formal_report_replays_scores_and_distinct_task_success_rate(tmp_path):
    path, _, _, _ = make_bundle(tmp_path, formal=True)
    result = verify_bundle(str(path))
    assert result["offline"] == "PASS"
    assert result["task_counts"]["PASS"] == 1
    with ZipFile(path) as archive:
        core = strict_json(archive.read("report_core.json"))
    assert core["schema_version"] == "1.4.0"
    assert core["task_success_rate_bp"] == 10000
    assert core["scores"]["overall_score_bp"] is None


@pytest.mark.parametrize("field", ["task_success_rate_bp", "raw_statistics", "scores"])
def test_formal_scoring_tampering_is_rejected_after_rehash(tmp_path, field):
    path, _, _, _ = make_bundle(tmp_path, formal=True)
    changed = tmp_path / "changed-formal.zip"

    def change(core):
        if field == "task_success_rate_bp":
            core[field] = 0
        elif field == "raw_statistics":
            core[field]["capabilities"][0]["mapping"] = 0
        else:
            core[field]["dimensions"]["consistency"]["observed_score_bp"] = 0

    rewrite_bundle(path, changed, core_change=change)
    with pytest.raises(VerificationError) as failure:
        verify_bundle(str(changed))
    assert failure.value.code == "REPLAY_MISMATCH"


def test_formal_initial_http_evidence_tamper_is_rejected(tmp_path):
    path, _, _, _ = make_bundle(tmp_path, formal=True)
    with ZipFile(path) as archive:
        index = strict_json(archive.read("verification.json"))
    initial_id = UUID(index["tasks"][0]["initial_http_evidence_id"])
    changed = tmp_path / "changed-initial.zip"
    rewrite_bundle(path, changed, evidence_change={
        initial_id: lambda value: value.update(latency_ms=99999),
    })
    with pytest.raises(VerificationError) as failure:
        verify_bundle(str(changed))
    assert failure.value.code == "EVIDENCE_INCONSISTENT"


def test_formal_initial_http_cannot_be_reclassified_as_retry(tmp_path):
    path, _, _, _ = make_bundle(tmp_path, formal=True)
    changed = tmp_path / "retry-is-initial.zip"

    def mark_retry(observations):
        observations[0].update(attempt_no=2, diagnostic_only=True)

    rewrite_bundle(path, changed, document_change={"observations.json": mark_retry})
    with pytest.raises(VerificationError) as failure:
        verify_bundle(str(changed))
    assert failure.value.code == "EVIDENCE_INCONSISTENT"


def test_formal_negative_replays_correct_rejection_and_actual_payload_hash(tmp_path):
    path, input_id, freeze_id, _ = make_bundle(tmp_path, formal=True, case="rejection")
    assert verify_bundle(str(path))["task_counts"]["PASS"] == 1
    changed = tmp_path / "baseline-payload.zip"

    def baseline_hash(value):
        value["dispatch_payload_hash"] = hash_json(value["slot"]["task"])

    rewrite_bundle(path, changed, evidence_change={
        input_id: baseline_hash, freeze_id: baseline_hash,
    })
    with pytest.raises(VerificationError) as failure:
        verify_bundle(str(changed))
    assert failure.value.code == "REPLAY_MISMATCH"


def test_formal_v12_report_remains_recognized_without_assessment_upgrade(tmp_path):
    path, _, _, _ = make_bundle(tmp_path, formal=True, report_schema_version="1.2.0")
    with ZipFile(path) as archive:
        core = strict_json(archive.read("report_core.json"))
    assert core["schema_version"] == "1.2.0"
    assert "assessment_rule_version" not in core
    assert "evidence_sufficiency" not in core and "risk_assessment" not in core
    result = verify_bundle(str(path))
    assert result["offline"] == "PASS" and result["task_count_comparison"] == "MATCH"
    assert result["assessment_comparison"] == "NOT_AVAILABLE_LEGACY_REPORT"
    assert "evidence_sufficiency" not in result and "risk_assessment" not in result


@pytest.mark.parametrize("field", [
    "sufficiency", "sufficiency_gate", "risk_conclusion", "risk_evidence", "rule_version",
])
@pytest.mark.parametrize("report_schema_version", [None, "1.5.0"])
def test_verifier_rejects_assessment_tampering_even_after_rehash(
    tmp_path, field, report_schema_version,
):
    path, _, _, _ = make_bundle(
        tmp_path, formal=True, case="critical", report_schema_version=report_schema_version,
    )
    original = verify_bundle(str(path))
    assert original["assessment_comparison"] == "MATCH"
    assert original["risk_assessment"]["critical_findings"]
    changed = tmp_path / f"assessment-{field}.zip"

    def alter(core):
        if field == "sufficiency":
            core["evidence_sufficiency"]["task_unknown_bp"] = 10000
        elif field == "sufficiency_gate":
            core["evidence_sufficiency"]["overall_allowed"] = True
            core["evidence_sufficiency"]["gate_status"] = "PASS"
        elif field == "risk_conclusion":
            core["risk_assessment"]["critical_findings"] = []
            core["risk_assessment"]["conclusion"] = "NO_CONFIRMED_CRITICAL_CONFLICT"
        elif field == "risk_evidence":
            core["risk_assessment"]["critical_findings"][0]["evidence_refs"] = [str(uuid4())]
        else:
            core["assessment_rule_version"] = "evidence-assessment-v2"

    rewrite_bundle(path, changed, core_change=alter)
    with pytest.raises(VerificationError) as failure:
        verify_bundle(str(changed))
    assert failure.value.code == "REPLAY_MISMATCH"


def test_formal_cannot_be_relabeled_as_legacy_with_assessment_fields(tmp_path):
    path, _, _, _ = make_bundle(tmp_path, formal=True)
    changed = tmp_path / "relabeled-assessment.zip"
    rewrite_bundle(path, changed, core_change=lambda core: core.update(schema_version="1.2.0"))
    with pytest.raises(VerificationError) as failure:
        verify_bundle(str(changed))
    assert failure.value.code == "RULE_VERSION_MISMATCH"


def test_formal_v13_remains_recognized_without_upgrade(tmp_path):
    path, _, _, _ = make_bundle(tmp_path, formal=True, report_schema_version="1.3.0")
    with ZipFile(path) as archive:
        core = strict_json(archive.read("report_core.json"))
    result = verify_bundle(str(path))
    assert core["schema_version"] == "1.3.0"
    assert all(item["rule_version"] == "4" for item in core["task_results"])
    assert result["offline"] == "PASS" and result["assessment_comparison"] == "MATCH"
    assert result["evidence_sufficiency"] == core["evidence_sufficiency"]
    assert result["risk_assessment"] == core["risk_assessment"]


def test_formal_rpc_log_gap_stays_unknown_when_freeze_read_recovers(tmp_path):
    path, input_id, freeze_id, _ = make_bundle(tmp_path, formal=True, case="rpc_logs_unknown")
    result = verify_bundle(str(path))
    assert result["offline"] == "PASS" and result["assessment_comparison"] == "MATCH"
    assert result["task_counts"] == {"PASS": 0, "FAIL": 0, "UNKNOWN": 1, "NOT_APPLICABLE": 0}
    assert result["risk_assessment"]["critical_findings"] == []
    with ZipFile(path) as archive:
        manifest = strict_json(archive.read("evidence_manifest.json"))
        by_id = {UUID(item["evidence_id"]): item for item in manifest["evidence"]}
        original = RecordVerificationInput.model_validate_json(archive.read(by_id[input_id]["path"]))
        frozen = RecordVerificationInput.model_validate_json(archive.read(by_id[freeze_id]["path"]))
    assert verify_record(original, (input_id,)).outcome == "UNKNOWN"
    assert verify_record(frozen, (input_id,)).outcome == "PASS"


@pytest.mark.parametrize(("case", "outcome", "reason"), [
    ("pass", "PASS", None),
    ("critical", "FAIL", "TX_REVERTED"),
    ("rpc_receipt_unknown", "UNKNOWN", "PLATFORM_RPC_ERROR"),
])
def test_formal_v15_replays_outcomes_and_partial_risk(tmp_path, case, outcome, reason):
    path, input_id, freeze_id, _ = make_bundle(
        tmp_path, formal=True, case=case, report_schema_version="1.5.0",
    )
    result = verify_bundle(str(path))
    assert result["offline"] == "PASS"
    assert result["task_count_comparison"] == result["assessment_comparison"] == "MATCH"
    task, = result["task_results"]
    assert (task["outcome"], task["reason_code"], task["rule_version"]) == (outcome, reason, "6")
    assert result["task_counts"][outcome] == 1 and sum(result["task_counts"].values()) == 1
    assert not result["evidence_sufficiency"]["overall_allowed"]
    with ZipFile(path) as archive:
        core = strict_json(archive.read("report_core.json"))
        manifest = strict_json(archive.read("evidence_manifest.json"))
        by_id = {UUID(item["evidence_id"]): item for item in manifest["evidence"]}
        original = RecordVerificationInput.model_validate_json(archive.read(by_id[input_id]["path"]))
        frozen = RecordVerificationInput.model_validate_json(archive.read(by_id[freeze_id]["path"]))
    assert core["schema_version"] == "1.5.0"
    assert core["scores"]["evaluation_state"] == "PARTIAL"
    assert core["scores"]["overall_score_bp"] is None
    if case == "critical":
        assert core["scores"]["advice"] == "NOT_RECOMMENDED"
        assert result["risk_assessment"]["conclusion"] == "CONFIRMED_CRITICAL_CONFLICT"
        assert any(
            finding["rule_id"] == "tx.target" and finding["reason_code"] == "TX_WRONG_TARGET"
            for finding in result["risk_assessment"]["critical_findings"]
        )
    else:
        assert result["risk_assessment"]["critical_findings"] == []
    if case == "rpc_receipt_unknown":
        assert verify_record(original, (input_id,)).outcome == "UNKNOWN"
        assert verify_record(frozen, (input_id,)).outcome == "PASS"


def test_formal_v15_rpc_assertion_tampering_is_rejected_after_rehash(tmp_path):
    path, _, _, _ = make_bundle(
        tmp_path, formal=True, case="rpc_receipt_unknown", report_schema_version="1.5.0",
    )
    assert verify_bundle(str(path))["task_results"][0]["outcome"] == "UNKNOWN"
    changed = tmp_path / "changed-rpc-assertion.zip"

    def erase_rpc_gap(assertions):
        assertion = next(item for item in assertions if item["rule_id"] == "receipt.evidence")
        assert assertion["outcome"] == "UNKNOWN"
        assertion.update(outcome="PASS", reason_code=None)

    rewrite_bundle(
        path, changed,
        core_change=lambda core: erase_rpc_gap(core["assertions"]),
        document_change={"assertions.json": erase_rpc_gap},
    )
    with pytest.raises(VerificationError) as failure:
        verify_bundle(str(changed))
    assert failure.value.code == "REPLAY_MISMATCH"


@pytest.mark.parametrize("target", ["plan", "inputs"])
def test_formal_v15_rejects_frozen_rule_downgrade_after_rehash(tmp_path, target):
    path, input_id, freeze_id, _ = make_bundle(
        tmp_path, formal=True, report_schema_version="1.5.0",
    )
    changed = tmp_path / "downgraded-rule.zip"
    rewrite_bundle(
        path, changed,
        document_change={
            "run_plan.json": lambda plan: plan.update(template_version="capabilities@5"),
        } if target == "plan" else None,
        evidence_change={
            input_id: lambda data: data.update(rule_version="5"),
            freeze_id: lambda data: data.update(rule_version="5"),
        } if target == "inputs" else None,
    )
    with pytest.raises(VerificationError) as failure:
        verify_bundle(str(changed))
    assert failure.value.code == "RULE_VERSION_MISMATCH"


@pytest.mark.parametrize(("source", "target"), [
    ("1.2.0", "1.3.0"), ("1.2.0", "1.4.0"), ("1.3.0", "1.2.0"),
    ("1.3.0", "1.4.0"), ("1.4.0", "1.2.0"), ("1.4.0", "1.3.0"),
    ("1.4.0", "1.5.0"), ("1.5.0", "1.4.0"),
])
def test_formal_report_version_cannot_upgrade_or_downgrade_its_frozen_rules(tmp_path, source, target):
    path, _, _, _ = make_bundle(tmp_path, formal=True, report_schema_version=source)
    changed = tmp_path / "relabeled-report.zip"
    rewrite_bundle(path, changed, core_change=lambda core: core.update(schema_version=target))
    with pytest.raises(VerificationError) as failure:
        verify_bundle(str(changed))
    assert failure.value.code == "RULE_VERSION_MISMATCH"


def make_bundle(
    tmp_path, *, rule_version="2", legacy_index=False, case="pass", identical_freeze=False,
    formal=False, report_schema_version=None,
):
    if formal:
        rule_version = (
            "3" if report_schema_version == "1.2.0"
            else "4" if report_schema_version == "1.3.0"
            else "6" if report_schema_version == "1.5.0" else "5"
        )
    raw_input = (
        reverted_anchor_input().model_dump(mode="json")
        if case == "critical"
        else
        excluded_input()
        if case == "not_applicable"
        else v2_task_input(status="NOT_FOUND")
        if case == "unknown"
        else v2_task_input()
        if rule_version in {"2", "3", "4", "5", "6"}
        else read_input(status="SUCCESS").model_dump(mode="json")
    )
    if case in {"rpc_logs_unknown", "rpc_receipt_unknown"}:
        from tests.unit.test_evidence_assessment import high_score_critical_arguments
        raw_input = high_score_critical_arguments()["inputs"][30].model_dump(mode="json")
        raw_input["binding"]["verification_evidence"] = []
        raw_input["evm"]["observed_at"] = NOW
        for field in ("agent_http", "initial_agent_http"):
            raw_input[field].update(started_at=NOW, ended_at=NOW, latency_ms=0)
    if formal:
        raw_input["rule_version"] = rule_version
        if case != "not_applicable":
            raw_input["slot"]["required_class"] = (
                "normal" if raw_input["slot"]["capability_id"] == "anchor_record" else "success"
            )
        if raw_input.get("agent_http") is not None:
            raw_input["initial_agent_http"] = {
                **deepcopy(raw_input["agent_http"]), "method": "POST", "path": "/tasks",
                "latency_ms": 0,
            }
    if case == "rejection":
        raw_input["slot"].update(case_kind="negative", required_class="invalid_format")
        response = {"accepted": False, "error": {"code": "SCHEMA_ERROR"}}
        raw_input.update(agent_response=response, agent_result=None, agent_task_status=None)
        for field in ("agent_http", "initial_agent_http"):
            raw_input[field].update(
                method="POST", path="/tasks", http_status=422, response=response,
            )
        raw_input["agent_http"] = deepcopy(raw_input["initial_agent_http"])
        from reputation_core.models import CaseSlot
        raw_input["dispatch_payload_hash"] = hash_json(
            mutated_payload(CaseSlot.model_validate(raw_input["slot"]))
        )
        raw_input["evm"]["candidate_tx_hash"] = None
    if case == "fail":
        claim_result(raw_input, tx_status="REVERTED")
    if case == "critical":
        raw_input["evm"]["results"]["transaction"]["to"] = "0x" + "22" * 20
        raw_input["binding"]["verification_evidence"] = []
    if case == "not_applicable":
        raw_input["execution_reason"] = raw_input["slot"]["applicability_reason"]
    if case in {"service_error", "schema_error", "failed_query"}:
        response = (
            {
                **raw_input["agent_response"],
                "task_status": "failed",
                "result": None,
                "reason_code": "INTERNAL_ERROR",
            }
            if case == "failed_query"
            else {"error": "service unavailable"}
        )
        raw_input["agent_http"].update(
            http_status=503 if case == "service_error" else 200, response=response
        )
        raw_input.update(
            agent_response=deepcopy(response),
            agent_result=None,
            agent_task_status="failed" if case == "failed_query" else None,
        )
    recovered_evm = deepcopy(raw_input["evm"])
    if case == "rpc_logs_unknown":
        raw_input["evm"]["results"]["receipt"]["logs"][0]["transactionHash"] = "0x" + "ee" * 32
    if case == "rpc_receipt_unknown":
        raw_input["evm"]["results"]["receipt"]["status"] = "0x2"
    if case in {"rpc_unknown", "rpc_unknown_without_candidate"}:
        raw_input["evm"].update(results={}, error_reason="PLATFORM_RPC_ERROR")
        if case == "rpc_unknown_without_candidate":
            raw_input["evm"]["candidate_tx_hash"] = None
    inputs = RecordVerificationInput.model_validate(raw_input)
    input_id = uuid4()
    freeze_id = input_id if identical_freeze else uuid4()
    http_id = uuid4() if inputs.agent_http is not None else None
    frozen = (
        inputs
        if identical_freeze
        else inputs.model_copy(
            update={
                "evm": inputs.evm.model_copy(update={"observed_at": NOW.replace(".000Z", ".001Z")})
            }
        )
    )
    if case in {"rpc_unknown", "rpc_unknown_without_candidate", "rpc_logs_unknown", "rpc_receipt_unknown"}:
        frozen = frozen.model_copy(
            update={
                "evm": frozen.evm.model_copy(
                    update={
                        "candidate_tx_hash": recovered_evm["candidate_tx_hash"],
                        "results": recovered_evm["results"],
                        "error_reason": None,
                    }
                )
            }
        )
    policy = strict_json(
        (Path(__file__).resolve().parents[2] / "configs/policies/policy-v1.json").read_bytes()
    )
    plan = RunPlan(
        run_id=uuid4(),
        snapshot_hash=inputs.snapshot.snapshot_hash,
        review_version=inputs.review_version,
        policy_version="policy-v1",
        policy_hash=hash_json(policy),
        profile="record-write-v1" if inputs.slot.capability_id == "anchor_record" else "record-read-v1",
        confirmed_capabilities=inputs.review.confirmed_claims,
        suite_id="formal-evaluation-v1" if formal else "capabilities-v1",
        template_version=f"capabilities@{rule_version}",
        planning_time=NOW,
        slots=(inputs.slot,),
    )
    replay = verify_record(inputs, (input_id,))
    observation = Observation(
        observation_id=uuid4(),
        slot_id=inputs.slot.slot_id,
        attempt_no=1,
        dispatch_state="SETTLED",
        started_at=NOW,
        ended_at=NOW,
        latency_ms=None,
        error_origin="platform" if inputs.evm.error_reason else None,
        reason_code=inputs.execution_reason,
        accepted=inputs.slot.applicability_reason is None,
        candidate_tx_hash=inputs.evm.candidate_tx_hash
        if inputs.slot.capability_id == "anchor_record"
        else None,
        evidence_refs=(http_id,) if http_id else (),
        diagnostic_only=False,
    )
    initial_id = (
        http_id if inputs.initial_agent_http == inputs.agent_http else uuid4()
    ) if formal and inputs.initial_agent_http is not None else None
    observed = [observation]
    if initial_id is not None:
        observed.insert(0, observation.model_copy(update={
            "observation_id": uuid4(), "dispatch_state": DispatchState.ACKNOWLEDGED,
            "latency_ms": 0, "http_status": inputs.initial_agent_http["http_status"],
            "evidence_refs": (initial_id,),
        }))
    verification = (
        {
            "schema_version": "task-replay-v1",
            "tasks": [
                {
                    "slot_id": str(inputs.slot.slot_id),
                    "input_evidence_id": str(input_id),
                    "freeze_evidence_id": str(freeze_id),
                    **({"agent_http_evidence_id": str(http_id)} if http_id else {}),
                    **({"initial_http_evidence_id": str(initial_id)} if initial_id else {}),
                }
            ],
        }
        if not legacy_index
        else {"input_evidence_id": str(input_id), "freeze_evidence_id": str(freeze_id)}
    )
    documents = {
        "access_grants.json": [inputs.grant.model_dump(mode="json")] if inputs.grant else [],
        "assertions.json": [
            item.model_dump(mode="json")
            for item in sorted(replay.assertions, key=lambda item: str(item.assertion_id))
        ],
        "bindings.json": [inputs.binding.model_dump(mode="json")] if inputs.binding else [],
        "claims_review.json": inputs.review.model_dump(mode="json"),
        "observations.json": [item.model_dump(mode="json") for item in observed],
        "policy.json": policy,
        "run_plan.json": plan.model_dump(mode="json"),
        "snapshot_core.json": inputs.snapshot.core.model_dump(mode="json"),
        "verification.json": verification,
    }
    files = {}
    evidence = []
    evidence_by_content = {}

    def add_record(data, source, evidence_id=None):
        digest = hash_bytes(data)
        if digest in evidence_by_content:
            return evidence_by_content[digest]
        record = EvidenceRecord(
            evidence_id=evidence_id or uuid4(),
            path=f"blobs/{digest[2:]}.bin",
            blob_hash=digest,
            byte_count=len(data),
            media_type="application/json",
            source=source,
            observed_at=NOW,
            collector_version="verifier-test-v1",
            redaction_profile="credentials-v1",
            trust_group="platform-and-local-rpc",
        )
        evidence_by_content[digest] = record
        evidence.append(record)
        files[record.path] = data
        return record

    input_record = add_record(
        canonical_bytes(inputs.model_dump(mode="json")), "record-verification-input", input_id
    )
    freeze_record = add_record(
        canonical_bytes(frozen.model_dump(mode="json")),
        "report-freeze-verification-input",
        freeze_id,
    )
    assert input_record.evidence_id == input_id
    assert freeze_record.evidence_id == freeze_id
    if inputs.agent_http is not None:
        http_record = add_record(canonical_bytes(inputs.agent_http), "agent-task-response", http_id)
        assert http_record.evidence_id == http_id
    if initial_id is not None:
        add_record(canonical_bytes(inputs.initial_agent_http), "agent-task-response", initial_id)
    aliases = []
    for name, body in documents.items():
        record = add_record(canonical_bytes(body), f"report-document:{name}")
        aliases.append(ManifestDocument(path=name, evidence_id=record.evidence_id))
        files[name] = files[record.path]
    chain = inputs.slot.expected.execution_chain
    manifest = EvidenceManifest(
        publication=PublicationContext(
            chain=chain,
            contract=ADDRESS,
            publisher=ADDRESS,
            confirmation_depth=1,
            previous_report_hash=ZERO,
            head_sequence=0,
            head_block_number="1",
            head_block_hash=inputs.slot.expected.pre_dispatch_block_hash,
            platform_instance_id=inputs.platform_instance_id,
        ),
        documents=tuple(sorted(aliases, key=lambda item: item.path)),
        evidence=tuple(sorted(evidence, key=lambda item: str(item.evidence_id))),
    )
    manifest_hash = hash_json(manifest.model_dump(mode="json"))
    report = build_report(
        plan,
        (inputs,) if formal else inputs,
        (input_id,) if formal else input_id,
        tuple(observed),
        policy,
        evaluated_at="2026-10-02T12:00:01.000Z",
        code_version="0" * 40,
        manifest_hash=manifest_hash,
        previous_report_hash=ZERO,
        report_schema_version=report_schema_version,
    )
    if legacy_index and rule_version == "2":
        report = report.model_copy(
            update={"schema_version": "1.0.0", "task_results": (), "task_counts": None}
        )
    report_data = report.model_dump(mode="json")
    report_hash = hash_json(report_data)
    receipt = AnchorReceipt(
        report_hash=report_hash,
        status="NOT_REQUESTED",
        trusted_chain_key="local-demo",
        chain_instance_id=chain.instance_hash,
        contract=ADDRESS,
        publisher=ADDRESS,
        tx_hash=None,
        sequence=None,
        block_number=None,
        block_hash=None,
        confirmations=0,
    )
    files.update(
        {
            "report_core.json": canonical_bytes(report_data),
            "evidence_manifest.json": canonical_bytes(manifest.model_dump(mode="json")),
            "anchor_receipt.json": canonical_bytes(receipt.model_dump(mode="json")),
        }
    )
    path = tmp_path / f"bundle-{rule_version}-{legacy_index}.zip"
    with ZipFile(path, "w") as archive:
        for name, data in sorted(files.items()):
            archive.writestr(name, data)
    return path, input_id, freeze_id, http_id


def rewrite_bundle(
    path,
    destination,
    *,
    core_change=None,
    document_change=None,
    evidence_change=None,
    manifest_change=None,
    receipt_change=None,
):
    with ZipFile(path) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    manifest = strict_json(files["evidence_manifest.json"])
    core = strict_json(files["report_core.json"])
    records = {item["evidence_id"]: item for item in manifest["evidence"]}

    def replace_record(record, body):
        old_path = record["path"]
        digest = hash_bytes(body)
        new_path = f"blobs/{digest[2:]}.bin"
        record.update(path=new_path, blob_hash=digest, byte_count=len(body))
        files[new_path] = body
        if old_path != new_path and old_path not in {
            item["path"] for item in manifest["evidence"] if item is not record
        }:
            files.pop(old_path, None)
        for doc in manifest["documents"]:
            if doc["evidence_id"] == record["evidence_id"]:
                files[doc["path"]] = body

    if document_change:
        docs = {item["path"]: item for item in manifest["documents"]}
        for name, change in document_change.items():
            value = strict_json(files[name])
            change(value)
            body = canonical_bytes(value)
            replace_record(records[docs[name]["evidence_id"]], body)
            files[name] = body
    if evidence_change:
        for evidence_id, change in evidence_change.items():
            record = records[str(evidence_id)]
            value = strict_json(files[record["path"]])
            change(value)
            replace_record(record, canonical_bytes(value))
    if core_change:
        core_change(core)
    if manifest_change:
        manifest_change(manifest)
    manifest["evidence"] = sorted(manifest["evidence"], key=lambda item: item["evidence_id"])
    manifest_bytes = canonical_bytes(manifest)
    core["evidence_manifest_hash"] = hash_json(manifest)
    core_bytes = canonical_bytes(core)
    receipt = strict_json(files["anchor_receipt.json"])
    receipt["report_hash"] = hash_json(core)
    if receipt_change:
        receipt_change(receipt)
    files.update(
        {
            "evidence_manifest.json": manifest_bytes,
            "report_core.json": core_bytes,
            "anchor_receipt.json": canonical_bytes(receipt),
        }
    )
    with ZipFile(destination, "w") as archive:
        for name, data in sorted(files.items()):
            archive.writestr(name, data)


@pytest.mark.parametrize("report_schema_version", ["1.0.0", "1.5.0"])
@pytest.mark.parametrize("status", ["NOT_REQUESTED", "CONFIRMING", "FAILED"])
@pytest.mark.parametrize(("field", "replacement"), [
    ("publisher", "0x" + "aa" * 20),
    ("contract", "0x" + "aa" * 20),
    ("chain_instance_id", "0x" + "aa" * 32),
    ("trusted_chain_key", "unrelated-chain"),
])
def test_verifier_rejects_receipt_identity_mismatch(
    tmp_path, report_schema_version, status, field, replacement,
):
    path, _, _, _ = make_bundle(
        tmp_path, rule_version="1", legacy_index=report_schema_version == "1.0.0",
        formal=report_schema_version == "1.5.0",
        report_schema_version="1.5.0" if report_schema_version == "1.5.0" else None,
    )
    assert verify_bundle(str(path))["offline"] == "PASS"
    changed = tmp_path / "changed-receipt.zip"
    rewrite_bundle(
        path, changed, receipt_change=lambda receipt: receipt.update(
            status=status, **{field: replacement},
        ),
    )
    with pytest.raises(VerificationError) as failure:
        verify_bundle(str(changed))
    assert failure.value.code == "EVIDENCE_INCONSISTENT"


@pytest.mark.parametrize("report_schema_version", ["1.0.0", "1.5.0"])
@pytest.mark.parametrize("field", ["platform_instance_id", "previous_report_hash"])
def test_verifier_rejects_publication_context_mismatch_after_rehash(
    tmp_path, report_schema_version, field,
):
    path, _, _, _ = make_bundle(
        tmp_path, rule_version="1", legacy_index=report_schema_version == "1.0.0",
        formal=report_schema_version == "1.5.0",
        report_schema_version="1.5.0" if report_schema_version == "1.5.0" else None,
    )
    changed = tmp_path / "changed-publication.zip"
    rewrite_bundle(path, changed, manifest_change=lambda manifest: manifest["publication"].update(
        **{field: "0x" + "aa" * 32},
    ))
    with pytest.raises(VerificationError) as failure:
        verify_bundle(str(changed))
    assert failure.value.code == "EVIDENCE_INCONSISTENT"


@pytest.mark.parametrize("field", ["executor", "agent_id", "owner"])
def test_verifier_rejects_frozen_task_identity_change_after_rehash(tmp_path, field):
    path, _, freeze_id, _ = make_bundle(tmp_path, formal=True, report_schema_version="1.5.0")
    changed = tmp_path / "changed-task-identity.zip"

    def change_identity(value):
        if field == "owner":
            value["snapshot"]["core"]["owner"] = "0x" + "aa" * 20
        elif field == "agent_id":
            value["slot"]["expected"]["agent_ref"]["agent_id"] = "7"
        else:
            value["slot"]["expected"]["executor"] = "0x" + "aa" * 20

    rewrite_bundle(path, changed, evidence_change={freeze_id: change_identity})
    with pytest.raises(VerificationError) as failure:
        verify_bundle(str(changed))
    assert failure.value.code == "EVIDENCE_INCONSISTENT"


@pytest.mark.parametrize("target", ["cas", "manifest", "report"])
def test_verifier_rejects_changed_committed_bytes(tmp_path, target):
    path, _, _, _ = make_bundle(tmp_path, formal=True, report_schema_version="1.5.0")
    with ZipFile(path) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    manifest = strict_json(files["evidence_manifest.json"])
    if target == "cas":
        files[manifest["evidence"][0]["path"]] = b"{}"
    elif target == "manifest":
        manifest["publication"]["publisher"] = "0x" + "aa" * 20
        files["evidence_manifest.json"] = canonical_bytes(manifest)
    else:
        core = strict_json(files["report_core.json"])
        core["agent_key_hash"] = "0x" + "aa" * 32
        files["report_core.json"] = canonical_bytes(core)
    changed = tmp_path / "changed-commitment.zip"
    with ZipFile(changed, "w") as archive:
        for name, data in sorted(files.items()):
            archive.writestr(name, data)
    with pytest.raises(VerificationError) as failure:
        verify_bundle(str(changed))
    assert failure.value.code == "CONTENT_HASH_MISMATCH"


def test_verifier_replays_new_task_result_and_returns_recomputed_counts(tmp_path):
    path, _, _, _ = make_bundle(tmp_path)

    result = verify_bundle(str(path))

    assert result["offline"] == "PASS"
    assert isinstance(result["limitations"], list)
    assert any("Offline PASS" in item and "not original authenticity" in item
               for item in result["limitations"])
    assert any("does not authenticate historical Registry" in item and "endpoints" in item
               for item in result["limitations"])
    assert result["task_counts"] == {"PASS": 1, "FAIL": 0, "UNKNOWN": 0, "NOT_APPLICABLE": 0}
    assert result["task_count_comparison"] == "MATCH"
    assert result["task_results"][0]["outcome"] == "PASS"
    assert result["task_results"][0]["live_chain"]["status"] == "NOT_CHECKED"
    assert (
        result["task_results"][0]["live_chain"]["reason"] == "trusted task RPC was not configured"
    )


@pytest.mark.parametrize(
    ("rule_version", "legacy_index", "case"),
    [("2", False, "pass"), ("2", False, "not_applicable"), ("1", True, "pass")],
)
def test_verifier_accepts_deduplicated_input_and_freeze_record(
    tmp_path, rule_version, legacy_index, case
):
    path, input_id, freeze_id, _ = make_bundle(
        tmp_path,
        rule_version=rule_version,
        legacy_index=legacy_index,
        case=case,
        identical_freeze=True,
    )

    assert input_id == freeze_id
    result = verify_bundle(str(path))
    assert result["offline"] == "PASS"
    outcome = "NOT_APPLICABLE" if case == "not_applicable" else "PASS"
    assert result["task_counts"][outcome] == 1


def test_verifier_rejects_distinct_freeze_record_with_input_source(tmp_path):
    path, input_id, freeze_id, _ = make_bundle(tmp_path)
    assert input_id != freeze_id
    changed = tmp_path / "wrong-freeze-source.zip"

    def change_source(manifest):
        next(item for item in manifest["evidence"] if item["evidence_id"] == str(freeze_id))[
            "source"
        ] = "record-verification-input"

    rewrite_bundle(path, changed, manifest_change=change_source)
    with pytest.raises(VerificationError) as failure:
        verify_bundle(str(changed))
    assert failure.value.code == "EVIDENCE_INCONSISTENT"


@pytest.mark.parametrize("case", ["pass", "unknown"])
def test_verifier_rejects_freeze_receipt_change_after_hashes_are_recomputed(tmp_path, case):
    path, _, freeze_id, _ = make_bundle(tmp_path, case=case)
    changed = tmp_path / "changed-freeze-receipt.zip"

    def change_receipt(data):
        if case == "pass":
            data["evm"]["results"]["receipt"]["status"] = "0x0"
        else:
            data["evm"]["results"]["receipt"] = {}

    rewrite_bundle(path, changed, evidence_change={freeze_id: change_receipt})
    with pytest.raises(VerificationError) as failure:
        verify_bundle(str(changed))
    assert failure.value.code == "EVIDENCE_INCONSISTENT"


@pytest.mark.parametrize("observed_at", ["2026-10-02T11:59:59.999Z", "2026-10-02T12:00:02.000Z"])
def test_verifier_rejects_freeze_time_outside_report_interval(tmp_path, observed_at):
    path, _, freeze_id, _ = make_bundle(tmp_path)
    changed = tmp_path / "changed-freeze-time.zip"

    def change_time(data):
        data["evm"]["observed_at"] = observed_at

    rewrite_bundle(path, changed, evidence_change={freeze_id: change_time})
    with pytest.raises(VerificationError) as failure:
        verify_bundle(str(changed))
    assert failure.value.code == "EVIDENCE_INCONSISTENT"


@pytest.mark.parametrize("case", ["pass", "rpc_unknown"])
@pytest.mark.parametrize("reason", ["PLATFORM_RPC_ERROR", "CHAIN_INSTANCE_CHANGED"])
def test_verifier_rejects_unresolved_freeze_error(tmp_path, case, reason):
    path, _, freeze_id, _ = make_bundle(tmp_path, case=case)
    changed = tmp_path / "changed-freeze-error.zip"

    def change_reason(data):
        data["evm"]["error_reason"] = reason

    rewrite_bundle(path, changed, evidence_change={freeze_id: change_reason})
    with pytest.raises(VerificationError) as failure:
        verify_bundle(str(changed))
    assert failure.value.code == "EVIDENCE_INCONSISTENT"


@pytest.mark.parametrize("case", ["rpc_unknown", "rpc_unknown_without_candidate"])
def test_verifier_keeps_historical_rpc_unknown_after_freeze_recovers(tmp_path, case):
    path, _, _, _ = make_bundle(tmp_path, case=case)

    result = verify_bundle(str(path))

    assert result["offline"] == "PASS"
    assert result["task_results"][0]["outcome"] == "UNKNOWN"
    assert result["task_results"][0]["reason_code"] == "PLATFORM_RPC_ERROR"
    assert result["task_counts"] == {"PASS": 0, "FAIL": 0, "UNKNOWN": 1, "NOT_APPLICABLE": 0}


def test_verifier_rejects_rpc_recovery_with_wrong_query_candidate(tmp_path):
    path, _, freeze_id, _ = make_bundle(tmp_path, case="rpc_unknown_without_candidate")
    changed = tmp_path / "wrong-query-candidate.zip"

    def change_candidate(data):
        data["evm"]["candidate_tx_hash"] = ZERO

    rewrite_bundle(path, changed, evidence_change={freeze_id: change_candidate})
    with pytest.raises(VerificationError) as failure:
        verify_bundle(str(changed))
    assert failure.value.code == "EVIDENCE_INCONSISTENT"


def test_verifier_does_not_extend_rpc_recovery_exception_to_legacy_rules(tmp_path):
    path, _, _, _ = make_bundle(tmp_path, rule_version="1", legacy_index=True, case="rpc_unknown")

    with pytest.raises(VerificationError) as failure:
        verify_bundle(str(path))
    assert failure.value.code == "EVIDENCE_INCONSISTENT"


@pytest.mark.parametrize(
    ("case", "outcome"),
    [
        ("pass", "PASS"),
        ("fail", "FAIL"),
        ("unknown", "UNKNOWN"),
        ("not_applicable", "NOT_APPLICABLE"),
    ],
)
def test_verifier_recounts_each_four_state_outcome(tmp_path, case, outcome):
    path, _, _, _ = make_bundle(tmp_path, case=case)

    result = verify_bundle(str(path))

    assert result["task_results"][0]["outcome"] == outcome
    assert result["task_counts"][outcome] == 1
    assert sum(result["task_counts"].values()) == 1
    assert result["task_count_comparison"] == "MATCH"


def test_legacy_replay_reports_recomputed_unknown_count_without_claiming_comparison(tmp_path):
    path, _, _, _ = make_bundle(tmp_path, case="unknown", legacy_index=True)

    result = verify_bundle(str(path))

    assert result["task_results"][0]["outcome"] == "UNKNOWN"
    assert result["task_counts"] == {"PASS": 0, "FAIL": 0, "UNKNOWN": 1, "NOT_APPLICABLE": 0}
    assert result["task_count_comparison"] == "NOT_AVAILABLE_LEGACY_REPORT"


@pytest.mark.parametrize(("rule_version", "legacy_index"), [("1", True), ("2", True)])
def test_verifier_keeps_legacy_report_and_singleton_index_compatibility(
    tmp_path, rule_version, legacy_index
):
    path, _, _, _ = make_bundle(tmp_path, rule_version=rule_version, legacy_index=legacy_index)

    result = verify_bundle(str(path))

    assert result["offline"] == "PASS"
    assert result["task_counts"]["PASS"] == 1
    assert result["task_count_comparison"] == "NOT_AVAILABLE_LEGACY_REPORT"


def test_verifier_rejects_new_index_with_legacy_report_schema(tmp_path):
    path, _, _, _ = make_bundle(tmp_path)
    changed = tmp_path / "stripped-summary.zip"

    def strip_summary(core):
        core["schema_version"] = "1.0.0"
        core.pop("task_results")
        core.pop("task_counts")

    rewrite_bundle(path, changed, core_change=strip_summary)
    with pytest.raises(VerificationError) as failure:
        verify_bundle(str(changed))
    assert failure.value.code == "RULE_VERSION_MISMATCH"


def test_verifier_rejects_version_mismatched_index_formats(tmp_path):
    rule_v1_with_new_index, _, _, _ = make_bundle(tmp_path, rule_version="1")
    with pytest.raises(VerificationError) as failure:
        verify_bundle(str(rule_v1_with_new_index))
    assert failure.value.code == "RULE_VERSION_MISMATCH"

    rule_v2_with_legacy_index, _, _, _ = make_bundle(tmp_path)
    changed = tmp_path / "legacy-index-new-report.zip"

    def replace_index(index):
        task = index["tasks"][0]
        index.clear()
        index.update(
            input_evidence_id=task["input_evidence_id"],
            freeze_evidence_id=task["freeze_evidence_id"],
        )

    rewrite_bundle(
        rule_v2_with_legacy_index,
        changed,
        document_change={"verification.json": replace_index},
    )
    with pytest.raises(VerificationError) as failure:
        verify_bundle(str(changed))
    assert failure.value.code == "RULE_VERSION_MISMATCH"


def test_verifier_rejects_multi_slot_report_without_full_report_replay(tmp_path):
    path, _, _, _ = make_bundle(tmp_path)
    changed = tmp_path / "multi-slot.zip"

    def add_slot(plan):
        extra = deepcopy(plan["slots"][0])
        extra["slot_id"] = str(uuid4())
        extra["slot_key"] += "-second"
        request_id = "0x" + "11" * 32
        extra["task"]["request_id"] = request_id
        extra["expected"]["request_id"] = request_id
        plan["slots"].append(extra)

    rewrite_bundle(path, changed, document_change={"run_plan.json": add_slot})
    with pytest.raises(VerificationError) as failure:
        verify_bundle(str(changed))
    assert failure.value.code == "REPLAY_MISMATCH"


def test_verifier_reports_missing_new_summary_as_rule_mismatch(tmp_path):
    path, _, _, _ = make_bundle(tmp_path)
    changed = tmp_path / "missing-summary.zip"

    def remove_summary(core):
        core.pop("task_results")
        core.pop("task_counts")

    rewrite_bundle(path, changed, core_change=remove_summary)
    with pytest.raises(VerificationError) as failure:
        verify_bundle(str(changed))
    assert failure.value.code == "RULE_VERSION_MISMATCH"


def test_verifier_rejects_task_result_tampering_after_hashes_are_recomputed(tmp_path):
    path, _, _, _ = make_bundle(tmp_path)
    changed = tmp_path / "changed-task-result.zip"

    def change_task_result(core):
        core["task_results"][0].update(outcome="FAIL", reason_code="SEMANTIC_MISMATCH")
        core["task_counts"] = {"PASS": 0, "FAIL": 1, "UNKNOWN": 0, "NOT_APPLICABLE": 0}

    rewrite_bundle(path, changed, core_change=change_task_result)
    with pytest.raises(VerificationError) as failure:
        verify_bundle(str(changed))
    assert failure.value.code == "REPLAY_MISMATCH"


def test_verifier_rejects_tampered_task_counts_after_hashes_are_recomputed(tmp_path):
    path, _, _, _ = make_bundle(tmp_path)
    changed = tmp_path / "changed-task-counts.zip"

    def change_counts(core):
        core["task_counts"] = {"PASS": 0, "FAIL": 1, "UNKNOWN": 0, "NOT_APPLICABLE": 0}

    rewrite_bundle(path, changed, core_change=change_counts)
    with pytest.raises(VerificationError) as failure:
        verify_bundle(str(changed))
    assert failure.value.code == "REPLAY_MISMATCH"


def test_verifier_rejects_rule_template_mismatch_explicitly(tmp_path):
    path, _, _, _ = make_bundle(tmp_path)
    changed = tmp_path / "wrong-rule.zip"

    def change_template(plan):
        plan["template_version"] = "capabilities@1"

    rewrite_bundle(path, changed, document_change={"run_plan.json": change_template})
    with pytest.raises(VerificationError) as failure:
        verify_bundle(str(changed))
    assert failure.value.code == "RULE_VERSION_MISMATCH"


def test_verifier_rejects_freeze_context_and_http_evidence_mismatch(tmp_path):
    path, _, freeze_id, http_id = make_bundle(tmp_path)
    changed_freeze = tmp_path / "changed-freeze.zip"

    def change_freeze(value):
        value["intent_persisted_at"] = NOW.replace(".000Z", ".001Z")

    rewrite_bundle(path, changed_freeze, evidence_change={freeze_id: change_freeze})
    with pytest.raises(VerificationError) as failure:
        verify_bundle(str(changed_freeze))
    assert failure.value.code == "EVIDENCE_INCONSISTENT"

    assert http_id is not None
    changed_http = tmp_path / "changed-http.zip"

    def change_http(value):
        value["response"]["result"]["tx_status"] = "REVERTED"

    rewrite_bundle(path, changed_http, evidence_change={http_id: change_http})
    with pytest.raises(VerificationError) as failure:
        verify_bundle(str(changed_http))
    assert failure.value.code == "EVIDENCE_INCONSISTENT"


def test_verifier_rejects_missing_input_reference_after_hashes_are_recomputed(tmp_path):
    path, _, _, _ = make_bundle(tmp_path)
    changed = tmp_path / "missing-input.zip"

    def remove_input(index):
        index["tasks"][0]["input_evidence_id"] = str(uuid4())

    rewrite_bundle(path, changed, document_change={"verification.json": remove_input})
    with pytest.raises(VerificationError) as failure:
        verify_bundle(str(changed))
    assert failure.value.code == "MISSING_EVIDENCE"


def test_task_live_recheck_is_separate_from_offline_replay(tmp_path, monkeypatch):
    path, _, _, _ = make_bundle(tmp_path)
    from reputation_verifier import bundle

    monkeypatch.setattr(bundle, "_live_rpc_results", lambda _web3, data: data.evm.results)
    confirmed = verify_bundle(str(path), task_rpc_url="http://127.0.0.1:1")
    assert confirmed["offline"] == "PASS"
    assert confirmed["task_results"][0]["live_chain"]["status"] == "CONFIRMED"

    def unavailable(*_args):
        raise OSError("RPC unavailable")

    monkeypatch.setattr(bundle, "_live_rpc_results", unavailable)
    unavailable_result = verify_bundle(str(path), task_rpc_url="http://127.0.0.1:1")
    assert unavailable_result["offline"] == "PASS"
    assert unavailable_result["task_results"][0]["live_chain"]["status"] == "UNKNOWN"


def test_not_applicable_task_does_not_query_live_chain(tmp_path, monkeypatch):
    path, _, _, _ = make_bundle(tmp_path, case="not_applicable")
    from reputation_verifier import bundle

    def unexpected_rpc(*_args):
        pytest.fail("NOT_APPLICABLE task must not query chain RPC")

    monkeypatch.setattr(bundle, "_live_rpc_results", unexpected_rpc)
    result = verify_bundle(str(path), task_rpc_url="http://127.0.0.1:1")

    live = result["task_results"][0]["live_chain"]
    assert result["offline"] == "PASS"
    assert live["status"] == "NOT_REQUIRED"
    assert live["reason_code"] == "CAPABILITY_NOT_DECLARED"


@pytest.mark.parametrize(
    ("case", "reason"),
    [
        ("service_error", "AGENT_SERVICE_ERROR"),
        ("schema_error", "SCHEMA_ERROR"),
        ("failed_query", "AGENT_TASK_FAILED"),
    ],
)
def test_agent_failure_without_chain_assertions_does_not_claim_live_confirmation(
    tmp_path, monkeypatch, case, reason
):
    path, _, _, _ = make_bundle(tmp_path, case=case)
    from reputation_verifier import bundle

    def unexpected_rpc(*_args):
        pytest.fail("HTTP-only Agent failure must not query chain RPC")

    monkeypatch.setattr(bundle, "_live_rpc_results", unexpected_rpc)
    result = verify_bundle(str(path), task_rpc_url="http://127.0.0.1:1")

    assert result["offline"] == "PASS"
    assert result["task_results"][0]["outcome"] == "FAIL"
    assert result["task_results"][0]["reason_code"] == reason
    assert result["task_results"][0]["live_chain"] == {
        "status": "NOT_REQUIRED",
        "reason_code": reason,
    }


def test_failed_anchor_does_not_confirm_live_results_from_another_chain(monkeypatch):
    from reputation_verifier import bundle

    data = reverted_anchor_input()
    evidence_id = uuid4()
    original = verify_record(data, (evidence_id,))
    other_chain = {**data.evm.results, "chain_id": "0x1"}
    monkeypatch.setattr(bundle, "_live_rpc_results", lambda *_args: other_chain)

    live = bundle._live_task_check(
        "http://127.0.0.1:1", data, original.outcome, original.reason_code, evidence_id
    )

    assert live["status"] == "UNKNOWN"
    assert live["reason_code"] == "CHAIN_INSTANCE_CHANGED"


def test_historical_rpc_unknown_can_be_resolved_by_live_chain_reads(tmp_path, monkeypatch):
    path, _, freeze_id, _ = make_bundle(tmp_path, case="rpc_unknown")
    from reputation_verifier import bundle

    with ZipFile(path) as archive:
        manifest = strict_json(archive.read("evidence_manifest.json"))
        record = next(
            item for item in manifest["evidence"] if item["evidence_id"] == str(freeze_id)
        )
        frozen = RecordVerificationInput.model_validate_json(archive.read(record["path"]))
    monkeypatch.setattr(bundle, "_live_rpc_results", lambda *_args: frozen.evm.results)

    result = verify_bundle(str(path), task_rpc_url="http://127.0.0.1:1")

    assert result["task_results"][0]["outcome"] == "UNKNOWN"
    live = result["task_results"][0]["live_chain"]
    assert live["status"] == "RESOLVED"
    assert live["outcome"] == "PASS"
