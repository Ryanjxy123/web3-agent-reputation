"""Formal scores are reduced from purpose-separated frozen task evidence."""

from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError
from reputation_core.case_templates import CASE_CLASSES, mutated_payload
from reputation_core.evidence import hash_json, strict_json
from reputation_core.models import Observation, RecordVerificationInput, ReportCore, RunPlan
from reputation_core.reporting import build_report

from tests.factories import HASH, NOW, ZERO
from tests.unit.test_formal_case_rules import negative_input
from tests.unit.test_task_outcomes import (
    claim_result,
    excluded_input,
    reverted_anchor_input,
    task_input,
)


def formal_arguments(*, availability=20, functional=10, behavior=0, mode="normal"):
    base = reverted_anchor_input().model_dump(mode="json") if behavior else task_input()
    capability = base["slot"]["capability_id"]
    inputs = []
    observations = []
    for purpose, number in (("availability", availability), ("functional", functional), ("behavioral", behavior)):
        for _ in range(number):
            body = deepcopy(base)
            request_id = "0x" + (len(inputs) + 1).to_bytes(32, "big").hex()
            slot = body["slot"]
            slot.update(slot_id=str(uuid4()), slot_key=f"{purpose}-{len(inputs)}", purpose=purpose)
            slot["required_class"] = "normal" if behavior else "success"
            slot["task"]["request_id"] = request_id
            slot["expected"]["request_id"] = request_id
            if behavior:
                body["evm"]["results"]["transaction"]["input"] = (
                    body["evm"]["results"]["transaction"]["input"][:10]
                    + request_id[2:] + slot["task"]["record_hash"][2:]
                )
            body["rule_version"] = "3"
            body["dispatch_payload_hash"] = hash_json(slot["task"])
            body["agent_response"].update(request_id=request_id, status_path="/tasks/" + request_id)
            body["agent_http"].update(
                request_id=request_id,
                path="/tasks" if body["agent_http"]["method"] == "POST" else "/tasks/" + request_id,
                response=deepcopy(body["agent_response"]),
            )
            if mode == "business_failure" and purpose == "functional":
                claim_result(body, tx_status="REVERTED")
            if mode == "rpc_unknown":
                body["evm"].update(results={}, error_reason="PLATFORM_RPC_ERROR")
            if mode == "unsupported" and purpose == "functional":
                body["agent_response"].update(task_status="failed", result=None, reason_code="UNSUPPORTED_CAPABILITY")
                body.update(agent_result=None, agent_task_status="failed")
                body["agent_http"]["response"] = deepcopy(body["agent_response"])
            initial = {
                **deepcopy(body["agent_http"]), "method": "POST", "path": "/tasks", "latency_ms": 100,
                "response": {
                    "request_id": request_id, "task_status": "accepted", "status_path": "/tasks/" + request_id,
                    "result": None,
                },
            }
            if mode == "bad_initial" and purpose == "availability":
                initial["response"] = None
            body["initial_agent_http"] = initial
            if mode == "unattributed":
                body["grant"] = None
            value = RecordVerificationInput.model_validate(body)
            inputs.append(value)
            observations.extend((
                Observation(
                    observation_id=uuid4(), slot_id=value.slot.slot_id, attempt_no=1,
                    dispatch_state="ACKNOWLEDGED", started_at=NOW, ended_at=NOW,
                    http_status=200, latency_ms=100, error_origin=None, reason_code=None,
                    accepted=True, candidate_tx_hash=None, evidence_refs=(uuid4(),), diagnostic_only=False,
                ),
                Observation(
                    observation_id=uuid4(), slot_id=value.slot.slot_id, attempt_no=2,
                    dispatch_state="SETTLED", started_at=NOW, ended_at=NOW,
                    http_status=None, latency_ms=None, error_origin=None,
                    reason_code=value.execution_reason, accepted=True,
                    candidate_tx_hash=value.evm.candidate_tx_hash if behavior else None,
                    evidence_refs=(uuid4(),), diagnostic_only=True,
                ),
            ))
    policy = strict_json((Path(__file__).resolve().parents[2] / "configs/policies/policy-v1.json").read_bytes())
    return {
        "plan": RunPlan(
            run_id=uuid4(), snapshot_hash=inputs[0].snapshot.snapshot_hash,
            review_version=1, policy_version="policy-v1", policy_hash=hash_json(policy),
            profile="record-write-v1" if behavior else "record-read-v1",
            confirmed_capabilities=(capability,), suite_id="formal-evaluation-v1",
            template_version="capabilities@3", planning_time=NOW,
            slots=tuple(value.slot for value in inputs),
        ),
        "inputs": tuple(inputs), "evidence_id": tuple(uuid4() for _ in inputs),
        "observations": tuple(observations), "policy": policy,
        "evaluated_at": "2026-10-02T12:00:01.000Z", "code_version": "0" * 40,
        "manifest_hash": HASH, "previous_report_hash": ZERO,
    }


def test_independent_denominators_and_mapping_are_evidence_based():
    report = build_report(**formal_arguments(mode="business_failure"))
    assert report.schema_version == "1.3.0"
    assert report.task_success_rate_bp == 6667
    assert report.raw_statistics["availability"]["decided"] == 20
    assert report.raw_statistics["capabilities"][0]["decided"] == 10
    assert report.scores.dimensions["availability"].score_bp == 10000
    assert report.scores.dimensions["consistency"].observed_score_bp == 2000
    assert report.raw_statistics["capabilities"][0]["mapping"] == 1
    assert report.scores.overall_score_bp is None


def test_normal_only_cannot_bypass_mandatory_classes():
    report = build_report(**formal_arguments())
    capability = report.raw_statistics["capabilities"][0]
    assert capability["covered_classes"] == ["success"]
    assert "invalid_format" in capability["missing_classes"]
    assert report.scores.evaluation_state == "PARTIAL"
    assert report.scores.dimensions["consistency"].score_bp is None
    assert report.task_success_rate_bp == 10000


def test_rpc_fault_does_not_deduct_initial_http_availability():
    report = build_report(**formal_arguments(mode="rpc_unknown"))
    assert report.task_counts.unknown_count == 30
    assert report.task_success_rate_bp is None
    assert report.scores.dimensions["availability"].score_bp == 10000
    assert report.raw_statistics["capabilities"][0]["decided"] == 0
    assert report.scores.dimensions["consistency"].observed_score_bp is None


def test_final_good_response_does_not_replace_invalid_initial_response():
    report = build_report(**formal_arguments(mode="bad_initial"))
    assert report.task_counts.pass_count == 30
    assert report.scores.dimensions["availability"].score_bp == 0
    assert report.task_success_rate_bp == 10000


def test_initial_good_structure_is_not_business_success():
    report = build_report(**formal_arguments(mode="unsupported"))
    assert report.scores.dimensions["availability"].score_bp == 10000
    assert report.raw_statistics["capabilities"][0]["mapping"] == 0
    assert report.scores.dimensions["consistency"].observed_score_bp == 0


def test_invalid_dispatch_is_unknown_even_with_successful_http():
    report = build_report(**formal_arguments(mode="unattributed"))
    assert report.scores.dimensions["availability"].state == "UNKNOWN"
    assert report.task_counts.unknown_count == 30


def test_behavior_uses_only_accepted_independent_behavior_slots():
    report = build_report(**formal_arguments(availability=0, behavior=10))
    assert report.raw_statistics["behavior"]["decided"] == 10
    assert report.raw_statistics["behavior"]["accepted"] == 10
    assert report.raw_statistics["behavior"]["correct"] == 0
    assert report.raw_statistics["capabilities"][0]["decided"] == 10
    assert report.scores.dimensions["behavior"].score_bp == 0
    assert not report.scores.critical_conflict


@pytest.mark.parametrize("change", ["reordered_inputs", "duplicate_evidence", "extra_observation", "future", "wrong_class"])
def test_formal_context_and_observation_boundaries(change):
    arguments = formal_arguments()
    if change == "reordered_inputs":
        arguments["inputs"] = tuple(reversed(arguments["inputs"]))
    elif change == "duplicate_evidence":
        arguments["evidence_id"] = (arguments["evidence_id"][0],) * len(arguments["inputs"])
    elif change == "extra_observation":
        arguments["observations"] += (arguments["observations"][0].model_copy(update={"observation_id": uuid4(), "slot_id": uuid4()}),)
    elif change == "future":
        arguments["evaluated_at"] = "2026-10-02T11:59:59.000Z"
    else:
        slots = list(arguments["plan"].slots)
        slots[-1] = slots[-1].model_copy(update={"required_class": "invalid_format"})
        arguments["plan"] = arguments["plan"].model_copy(update={"slots": tuple(slots)})
        inputs = list(arguments["inputs"])
        inputs[-1] = inputs[-1].model_copy(update={"slot": slots[-1]})
        arguments["inputs"] = tuple(inputs)
        assert "invalid_format" in build_report(**arguments).raw_statistics["capabilities"][0]["missing_classes"]
        return
    with pytest.raises(ValueError):
        build_report(**arguments)


def test_missing_initial_evidence_keeps_availability_unknown():
    arguments = formal_arguments()
    arguments["inputs"] = tuple(item.model_copy(update={"initial_agent_http": None}) for item in arguments["inputs"])
    assert build_report(**arguments).scores.dimensions["availability"].state == "UNKNOWN"


def test_formal_wire_is_explicit_and_reproducible():
    arguments = formal_arguments()
    report = build_report(**arguments)
    assert ReportCore.model_validate_json(report.model_dump_json()) == report
    assert build_report(**arguments) == report
    wire = report.model_dump(mode="json")
    wire["schema_version"] = "1.1.0"
    with pytest.raises(ValidationError):
        ReportCore.model_validate(wire)


def test_formal_report_requires_task_rule_version_three():
    wire = build_report(**formal_arguments()).model_dump(mode="json")
    slot_id = wire["task_results"][0]["slot_id"]
    wire["task_results"][0]["rule_version"] = "2"
    for assertion in wire["assertions"]:
        if assertion["slot_id"] == slot_id:
            assertion["rule_version"] = "2"
    with pytest.raises(ValidationError, match="task rule version 3"):
        ReportCore.model_validate(wire)


@pytest.mark.parametrize("mode,success_rate", [("normal", None), ("normal", 9999), ("rpc_unknown", 0)])
def test_formal_task_success_rate_must_match_decided_results(mode, success_rate):
    wire = build_report(**formal_arguments(mode=mode)).model_dump(mode="json")
    wire["task_success_rate_bp"] = success_rate
    with pytest.raises(ValidationError, match="success rate disagrees"):
        ReportCore.model_validate(wire)


def test_formal_policy_cannot_change_thresholds_without_a_new_version():
    arguments = formal_arguments()
    arguments["policy"]["availability"]["min_samples"] = 1
    arguments["plan"] = arguments["plan"].model_copy(update={
        "policy_hash": hash_json(arguments["policy"]),
    })
    with pytest.raises(ValueError, match="REPORT_CONTEXT_MISMATCH"):
        build_report(**arguments)


@pytest.mark.parametrize("http_status,expected_outcome", [(422, "PASS"), (500, "FAIL")])
def test_negative_class_is_covered_by_verified_rejection_not_its_label(http_status, expected_outcome):
    arguments = formal_arguments(availability=0, functional=1)
    item = arguments["inputs"][0]
    slot = item.slot.model_copy(update={"case_kind": "negative", "required_class": "invalid_format"})
    response = {"accepted": False, "error": {"code": "SCHEMA_ERROR"}}
    initial = {**item.initial_agent_http, "http_status": http_status, "response": response}
    changed = item.model_copy(update={
        "slot": slot, "agent_http": initial, "initial_agent_http": initial,
        "agent_response": response, "agent_result": None, "agent_task_status": None,
        "dispatch_payload_hash": hash_json(mutated_payload(slot)),
        "evm": item.evm.model_copy(update={"candidate_tx_hash": None}),
    })
    arguments["inputs"] = (changed,)
    arguments["plan"] = arguments["plan"].model_copy(update={"slots": (slot,)})
    report = build_report(**arguments)
    assert report.task_results[0].outcome == expected_outcome
    capability = report.raw_statistics["capabilities"][0]
    assert capability["covered_classes"] == ["invalid_format"]
    assert capability["mapping"] is None
    assert capability["decided"] == 1


def test_unmeasured_confirmed_capability_remains_in_consistency_denominator():
    arguments = formal_arguments()
    changed = []
    for item in arguments["inputs"]:
        body = item.model_dump(mode="json")
        core = body["snapshot"]["core"]
        core["normalized_metadata"]["capabilities"] = ["get_tx_status", "verify_record"]
        core["metadata_hash"] = hash_json(core["normalized_metadata"])
        snapshot_hash = hash_json(core)
        body["snapshot"]["snapshot_hash"] = snapshot_hash
        body["review"].update(snapshot_hash=snapshot_hash, confirmed_claims=["get_tx_status", "verify_record"])
        body["slot"]["task"]["snapshot_hash"] = snapshot_hash
        body["slot"]["expected"]["snapshot_hash"] = snapshot_hash
        body["grant"]["snapshot_hash"] = snapshot_hash
        body["registry_witness"]["snapshot_core"] = deepcopy(core)
        body["dispatch_payload_hash"] = hash_json(body["slot"]["task"])
        changed.append(RecordVerificationInput.model_validate(body))
    arguments["inputs"] = tuple(changed)
    arguments["plan"] = arguments["plan"].model_copy(update={
        "slots": tuple(item.slot for item in changed), "snapshot_hash": changed[0].snapshot.snapshot_hash,
        "confirmed_capabilities": changed[0].review.confirmed_claims,
    })
    report = build_report(**arguments)
    unmeasured = report.raw_statistics["capabilities"][1]
    assert unmeasured["capability_id"] == "verify_record" and unmeasured["decided"] == 0
    assert report.scores.dimensions["consistency"].sample_bp == 0
    assert report.scores.overall_score_bp is None


def test_formal_availability_cannot_execute_writes():
    with pytest.raises(ValidationError, match="safe availability"):
        formal_arguments(behavior=1)


def test_prior_not_applicable_is_excluded_without_erasing_unmeasured_claim():
    arguments = formal_arguments(availability=0, functional=1)
    body = excluded_input()
    body["rule_version"] = "3"
    item = RecordVerificationInput.model_validate(body)
    arguments["inputs"] = (item,)
    arguments["plan"] = arguments["plan"].model_copy(update={
        "snapshot_hash": item.snapshot.snapshot_hash, "confirmed_capabilities": item.review.confirmed_claims,
        "slots": (item.slot,),
    })
    arguments["observations"] = (
        arguments["observations"][-1].model_copy(update={
            "slot_id": item.slot.slot_id, "accepted": False,
            "reason_code": "CAPABILITY_NOT_DECLARED",
        }),
    )
    report = build_report(**arguments)
    assert report.task_counts.not_applicable_count == 1
    assert report.task_success_rate_bp is None
    assert report.raw_statistics["capabilities"][0]["capability_id"] == "verify_record"
    assert report.raw_statistics["capabilities"][0]["planned"] == 0
    assert report.scores.overall_score_bp is None


def test_initial_latency_must_match_its_observation():
    arguments = formal_arguments()
    arguments["inputs"] = tuple(
        item.model_copy(update={"initial_agent_http": {**item.initial_agent_http, "latency_ms": 1}})
        for item in arguments["inputs"]
    )
    report = build_report(**arguments)
    assert report.scores.dimensions["availability"].state == "UNKNOWN"
    assert report.raw_statistics["availability"]["decided"] == 0


def complete_read_arguments():
    """Twenty independent HTTP probes and ten fixed-class record tasks, all raw evidence."""
    arguments = formal_arguments()
    snapshot = task_input("verify_record")["snapshot"]
    classes = ("normal",) * 20 + ("match",) * 4 + ("not_found",) * 2 + (
        "hash_mismatch", "hash_mismatch", "invalid_format", "forbidden_contract"
    )
    inputs = []
    observations = []
    for index, case in enumerate(classes):
        negative = case in {"invalid_format", "forbidden_contract"}
        body = (
            negative_input("verify_record", case)
            if negative else task_input("verify_record", exists=case != "not_found")
        )
        body["snapshot"] = deepcopy(snapshot)
        slot = body["slot"]
        request_id = "0x" + (index + 1).to_bytes(32, "big").hex()
        slot.update(
            slot_id=str(uuid4()), slot_key=f"record-{index}",
            purpose="availability" if index < 20 else "functional", required_class=case,
        )
        slot["task"]["request_id"] = slot["expected"]["request_id"] = request_id
        if case == "hash_mismatch":
            slot["task"]["record_hash"] = slot["expected"]["record_hash"] = "0x" + "22" * 32
            claim_result(body, record_matches=False)
        if not negative:
            body["agent_response"].update(request_id=request_id, status_path="/tasks/" + request_id)
        if case == "forbidden_contract":
            # A confirmed ordinary rejection failure: the raw error code is wrong.
            body["agent_response"] = {"accepted": False, "error": {"code": "OTHER_REJECTION"}}
        body["rule_version"] = "3"
        body["dispatch_payload_hash"] = hash_json(mutated_payload(
            RecordVerificationInput.model_validate(body).slot
        ))
        body["agent_http"].update(
            request_id=request_id, response=deepcopy(body["agent_response"]),
            path="/tasks" if negative else "/tasks/" + request_id,
        )
        latency = 4000 if index == 18 else 100
        initial = {
            **deepcopy(body["agent_http"]), "method": "POST", "path": "/tasks",
            "latency_ms": latency, "ended_at": "2026-10-02T12:00:04.000Z"
            if latency == 4000 else "2026-10-02T12:00:00.100Z",
        }
        if not negative:
            initial["response"] = {
                "request_id": request_id, "task_status": "accepted",
                "status_path": "/tasks/" + request_id, "result": None,
            }
        if index == 19:
            initial["response"] = None  # Captured malformed first response, not missing evidence.
        body["initial_agent_http"] = initial
        if negative:
            body["agent_http"] = deepcopy(initial)
        item = RecordVerificationInput.model_validate(body)
        inputs.append(item)
        observations.extend((
            Observation(
                observation_id=uuid4(), slot_id=item.slot.slot_id, attempt_no=1,
                dispatch_state="DISPATCH_UNCERTAIN" if negative or index == 19 else "ACKNOWLEDGED",
                started_at=NOW, ended_at=initial["ended_at"], http_status=initial["http_status"],
                latency_ms=latency, error_origin=None, reason_code=None,
                accepted=not negative, candidate_tx_hash=None, evidence_refs=(uuid4(),), diagnostic_only=False,
            ),
            Observation(
                observation_id=uuid4(), slot_id=item.slot.slot_id, attempt_no=2,
                dispatch_state="SETTLED", started_at="2026-10-02T12:00:05.000Z",
                ended_at="2026-10-02T12:00:05.000Z", http_status=None, latency_ms=None,
                error_origin=None, reason_code=item.execution_reason, accepted=not negative,
                candidate_tx_hash=None, evidence_refs=(uuid4(),), diagnostic_only=True,
            ),
        ))
    arguments.update(
        inputs=tuple(inputs), observations=tuple(observations),
        evidence_id=tuple(uuid4() for _ in inputs), evaluated_at="2026-10-02T14:24:00.000Z",
    )
    arguments["plan"] = arguments["plan"].model_copy(update={
        "snapshot_hash": snapshot["snapshot_hash"], "confirmed_capabilities": ("verify_record",),
        "slots": tuple(item.slot for item in inputs),
    })
    return arguments


def test_complete_golden_scores_are_derived_from_frozen_raw_evidence():
    arguments = complete_read_arguments()
    report = build_report(**arguments)
    assert report.scores.evaluation_state == "COMPLETE"
    availability = report.raw_statistics["availability"]
    assert (availability["planned"], availability["decided"], availability["responded"], availability["within_latency"]) == (20, 20, 19, 18)
    consistency = report.raw_statistics["capabilities"][0]
    assert (consistency["planned"], consistency["decided"], consistency["passed"], consistency["mapping"]) == (10, 10, 9, 1)
    assert consistency["covered_classes"] == sorted(CASE_CLASSES["verify_record"])
    assert consistency["missing_classes"] == []
    assert report.scores.dimensions["availability"].score_bp == 9400
    assert report.scores.dimensions["consistency"].score_bp == 9200
    assert report.scores.dimensions["behavior"].state == "NOT_APPLICABLE"
    assert report.scores.overall_score_bp == 9270
    assert report.scores.sufficiency_bp == 9000
    assert report.task_success_rate_bp == 9667
    assert report.task_counts.pass_count == 29 and report.task_counts.fail_count == 1
    assert not report.scores.critical_conflict
    assert build_report(**arguments) == report


def test_assessment_explains_exact_policy_gates_and_ordinary_failure():
    report = build_report(**complete_read_arguments())
    evidence = report.evidence_sufficiency
    risk = report.risk_assessment
    assert evidence is not None and risk is not None
    assert evidence.overall_allowed and evidence.gate_status == "PASS"
    assert evidence.missing_evidence == () and all(evidence.exact_gates.values())
    assert evidence.thresholds["max_unknown_or_unresolved_bp"] == 2000
    assert evidence.thresholds["availability_min_samples"] == 20
    assert evidence.thresholds["consistency_min_samples_per_capability"] == 10
    assert evidence.unknown_or_unresolved_bp == 0
    assert evidence.dimensions["consistency"]["claim_coverage_bp"] == 10000
    assert evidence.dimensions["consistency"]["oldest_age_seconds"] == 8640
    assert evidence.capabilities[0]["not_applicable"] == 0
    assert evidence.capabilities[0]["missing_classes"] == []
    assert risk.conclusion == "NO_CONFIRMED_CRITICAL_CONFLICT" and risk.critical_findings == ()
    assert len(risk.ordinary_failure_slots) == 1


def test_rpc_unknown_retains_initial_http_availability_and_never_becomes_risk():
    report = build_report(**formal_arguments(mode="rpc_unknown"))
    evidence = report.evidence_sufficiency
    risk = report.risk_assessment
    assert evidence is not None and risk is not None
    assert evidence.dimensions["availability"]["unresolved"] == 0
    assert evidence.dimensions["availability"]["unknown_or_unresolved_bp"] == 0
    assert evidence.dimensions["consistency"]["unknown_or_unresolved_bp"] == 10000
    assert evidence.task_unknown_bp == 10000
    assert not evidence.overall_allowed and report.scores.overall_score_bp is None
    assert risk.critical_findings == () and risk.ordinary_failure_slots == ()
    assert len(risk.evidence_gap_slots) == 30


@pytest.mark.parametrize("missing", ["samples", "coverage", "long_claim", "unbounded_claim", "blank_claim"])
def test_sufficiency_names_missing_samples_and_capability_coverage(missing):
    arguments = complete_read_arguments()
    if missing == "samples":
        arguments["plan"] = arguments["plan"].model_copy(update={"slots": arguments["plan"].slots[1:]})
        arguments["inputs"] = arguments["inputs"][1:]
        arguments["evidence_id"] = arguments["evidence_id"][1:]
        arguments["observations"] = arguments["observations"][2:]
    else:
        claim = {"coverage": "unadapted-public-claim", "long_claim": "x" * 2000,
                 "unbounded_claim": "x" * 2001, "blank_claim": ""}[missing]
        bodies = []
        for item in arguments["inputs"]:
            body = item.model_dump(mode="json")
            core = body["snapshot"]["core"]
            core["normalized_metadata"]["capabilities"].append(claim)
            core["metadata_hash"] = hash_json(core["normalized_metadata"])
            snapshot_hash = hash_json(core)
            body["snapshot"]["snapshot_hash"] = snapshot_hash
            body["review"]["snapshot_hash"] = snapshot_hash
            body["slot"]["task"]["snapshot_hash"] = snapshot_hash
            body["slot"]["expected"]["snapshot_hash"] = snapshot_hash
            body["grant"]["snapshot_hash"] = snapshot_hash
            body["registry_witness"]["snapshot_core"] = deepcopy(core)
            body["dispatch_payload_hash"] = hash_json(mutated_payload(RecordVerificationInput.model_validate(body).slot))
            bodies.append(RecordVerificationInput.model_validate(body))
        arguments["inputs"] = tuple(bodies)
        arguments["plan"] = arguments["plan"].model_copy(update={
            "snapshot_hash": bodies[0].snapshot.snapshot_hash, "slots": tuple(item.slot for item in bodies),
        })
    report = build_report(**arguments)
    evidence = report.evidence_sufficiency
    assert evidence is not None and not evidence.overall_allowed
    assert report.scores.overall_score_bp is None
    if missing == "samples":
        assert "availability:samples" in evidence.missing_evidence
    else:
        assert evidence.uncovered_claims == (claim,)
        assert evidence.dimensions["consistency"]["claim_count"] == 2
        assert evidence.dimensions["consistency"]["claim_coverage_bp"] == (0 if missing in {"blank_claim", "unbounded_claim"} else 5000)
        assert "consistency:uncovered_claims" in evidence.missing_evidence


@pytest.mark.parametrize("unknown_number,allowed", [(4, True), (5, True), (6, False)])
def test_unresolved_limit_is_exact_complement_of_coverage_and_applied_per_dimension(unknown_number, allowed):
    arguments = complete_read_arguments()
    original_inputs, original_observations = arguments["inputs"], arguments["observations"]
    additional = []
    additional_observations = []
    for index in range(unknown_number):
        body = original_inputs[0].model_dump(mode="json")
        slot_id = uuid4()
        request_id = "0x" + (100 + index).to_bytes(32, "big").hex()
        body["slot"].update(slot_id=str(slot_id), slot_key=f"extra-unknown-{index}")
        body["slot"]["task"]["request_id"] = body["slot"]["expected"]["request_id"] = request_id
        body["dispatch_payload_hash"] = hash_json(body["slot"]["task"])
        body.update(initial_agent_http=None, agent_http=None, agent_response=None,
                    agent_result=None, agent_task_status=None, execution_reason="PLATFORM_NETWORK_ERROR")
        additional.append(RecordVerificationInput.model_validate(body))
        additional_observations.append(original_observations[1].model_copy(update={
            "observation_id": uuid4(), "slot_id": slot_id, "accepted": False,
            "reason_code": "PLATFORM_NETWORK_ERROR",
        }))
    arguments["inputs"] = (*original_inputs, *additional)
    arguments["observations"] = (*original_observations, *additional_observations)
    arguments["evidence_id"] = tuple(uuid4() for _ in arguments["inputs"])
    arguments["plan"] = arguments["plan"].model_copy(update={"slots": tuple(item.slot for item in arguments["inputs"])})
    report = build_report(**arguments)
    evidence = report.evidence_sufficiency
    assert evidence is not None
    assert evidence.dimensions["availability"]["unresolved"] == unknown_number
    assert evidence.dimensions["availability"]["exact_gates"]["unresolved"] == allowed
    assert evidence.overall_allowed == allowed  # Exactly 20/25 satisfies coverage >=80%; 20/26 does not.
    assert (report.scores.overall_score_bp is not None) == allowed


@pytest.mark.parametrize("age,allowed", [(34560, True), (34561, False)])
def test_sufficiency_gate_uses_exact_freshness_not_displayed_basis_points(age, allowed):
    from datetime import datetime, timedelta

    arguments = complete_read_arguments()
    arguments["evaluated_at"] = (datetime.fromisoformat(NOW) + timedelta(seconds=age)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    report = build_report(**arguments)
    evidence = report.evidence_sufficiency
    assert evidence is not None
    assert evidence.sufficiency_bp == 6000 and evidence.overall_allowed == allowed
    assert evidence.exact_gates["sufficiency"] == allowed


def test_v12_replay_omits_assessments_and_retains_original_scoring_fields():
    arguments = complete_read_arguments()
    old = build_report(**arguments, report_schema_version="1.2.0")
    new = build_report(**arguments)
    old_wire, new_wire = old.model_dump(mode="json"), new.model_dump(mode="json")
    assert old.schema_version == "1.2.0" and old.evidence_sufficiency is None
    assert old.raw_statistics == new.raw_statistics and old.scores == new.scores
    for field in ("evidence_sufficiency", "risk_assessment", "assessment_rule_version"):
        assert field not in old_wire
        new_wire.pop(field)
    new_wire["schema_version"] = "1.2.0"
    assert new_wire == old_wire
    old_wire["risk_assessment"] = new.risk_assessment.model_dump(mode="json")
    with pytest.raises(ValidationError, match="assessment fields"):
        ReportCore.model_validate(old_wire)
