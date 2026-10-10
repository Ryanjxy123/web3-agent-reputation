"""Fixed controlled-scenario expectations, specified before running the scorer."""

from copy import deepcopy

import pytest
from reputation_core.models import RecordVerificationInput
from reputation_core.reporting import build_report

from tests.unit.test_formal_scoring import formal_arguments
from tests.unit.test_task_outcomes import excluded_input


@pytest.mark.parametrize(
    "mode,purpose,outcome,reason,decided,observed,mapping",
    [
        ("normal", "availability", "PASS", None, 1, 10000, 1),
        ("late", "availability", "PASS", None, 1, 8000, 1),
        ("service_error", "availability", "FAIL", "AGENT_SERVICE_ERROR", 1, 0, None),
        ("timeout", "availability", "UNKNOWN", "SERVICE_TIMEOUT", 0, None, None),
        ("network", "availability", "UNKNOWN", "PLATFORM_NETWORK_ERROR", 0, None, None),
        ("unsupported", "availability", "FAIL", "CAPABILITY_EXPLICITLY_UNSUPPORTED", 1, 10000, 0),
        ("unsupported", "functional", "FAIL", "CAPABILITY_EXPLICITLY_UNSUPPORTED", 1, 0, 0),
    ],
)
def test_fixed_http_scenarios_separate_service_function_and_platform_evidence(
    mode, purpose, outcome, reason, decided, observed, mapping
):
    arguments = formal_arguments(
        availability=int(purpose == "availability"),
        functional=int(purpose == "functional"),
        mode="unsupported" if mode == "unsupported" else "normal",
    )
    body = arguments["inputs"][0].model_dump(mode="json")
    observations = list(arguments["observations"])
    if mode == "late":
        body["initial_agent_http"].update(latency_ms=3500, ended_at="2026-10-02T12:00:03.500Z")
        observations[0] = observations[0].model_copy(
            update={
                "latency_ms": 3500,
                "ended_at": "2026-10-02T12:00:03.500Z",
            }
        )
        arguments["evaluated_at"] = "2026-10-02T12:00:04.000Z"
    if mode == "unsupported" and purpose == "availability":
        body["agent_response"].update(
            task_status="failed", result=None, reason_code="CAPABILITY_EXPLICITLY_UNSUPPORTED"
        )
        body.update(agent_result=None, agent_task_status="failed")
        body["agent_http"]["response"] = deepcopy(body["agent_response"])
    if mode in {"service_error", "timeout", "network"}:
        status = 503 if mode == "service_error" else None
        response = {"accepted": False, "error": {"code": "SERVICE_UNAVAILABLE"}} if status else None
        initial = {
            **body["initial_agent_http"],
            "http_status": status,
            "response": response,
            "reason_code": reason,
        }
        body.update(
            agent_http=deepcopy(initial),
            initial_agent_http=initial,
            agent_response=response,
            agent_result=None,
            agent_task_status=None,
        )
        observations[0] = observations[0].model_copy(
            update={
                "http_status": status,
                "accepted": False,
                "reason_code": reason,
                "dispatch_state": "DISPATCH_UNCERTAIN",
                "error_origin": "agent" if status else "platform",
            }
        )
    if reason is not None:
        body["execution_reason"] = reason
        observations[1] = observations[1].model_copy(
            update={
                "reason_code": reason,
                "accepted": mode == "unsupported",
            }
        )
    arguments["inputs"] = (RecordVerificationInput.model_validate(body),)
    arguments["observations"] = tuple(observations)
    report = build_report(**arguments)
    assert report.task_counts is not None
    assert report.evidence_sufficiency is not None and report.risk_assessment is not None
    assert (report.task_results[0].outcome, report.task_results[0].reason_code) == (outcome, reason)
    assert report.task_counts.not_applicable_count == 0
    stats = report.model_dump(mode="json")["raw_statistics"]
    expected_denominators = (1, decided, 0, 0) if purpose == "availability" else (0, 0, 1, decided)
    assert (
        stats["availability"]["planned"],
        stats["availability"]["decided"],
        stats["capabilities"][0]["planned"],
        stats["capabilities"][0]["decided"],
    ) == expected_denominators
    assert stats["capabilities"][0]["mapping"] == mapping
    dimension = (
        report.scores.dimensions["availability"]
        if purpose == "availability"
        else report.scores.dimensions["consistency"]
    )
    assert dimension.observed_score_bp == observed
    assert dimension.score_bp is None
    assert report.scores.dimensions["behavior"].state == "NOT_APPLICABLE"
    assert report.scores.evaluation_state == "PARTIAL" and report.scores.overall_score_bp is None
    assert report.evidence_sufficiency.gate_status == "PARTIAL"
    assert not report.evidence_sufficiency.overall_allowed
    assert report.evidence_sufficiency.task_unknown_bp == (10000 if outcome == "UNKNOWN" else 0)
    assert not report.risk_assessment.critical_findings
    assert bool(report.risk_assessment.ordinary_failure_slots) == (outcome == "FAIL")
    # A confirmed service failure can coexist with unobserved downstream chain facts.
    assert bool(report.risk_assessment.evidence_gap_slots) == (mode not in {"normal", "late"})


def test_prior_undeclared_capability_is_excluded_without_hiding_current_claim_samples():
    arguments = formal_arguments(availability=0, functional=1)
    body = excluded_input()
    body["rule_version"] = "5"
    item = RecordVerificationInput.model_validate(body)
    arguments["inputs"] = (item,)
    arguments["plan"] = arguments["plan"].model_copy(
        update={
            "snapshot_hash": item.snapshot.snapshot_hash,
            "confirmed_capabilities": ("verify_record",),
            "slots": (item.slot,),
        }
    )
    arguments["observations"] = (
        arguments["observations"][-1].model_copy(
            update={
                "slot_id": item.slot.slot_id,
                "accepted": False,
                "reason_code": "CAPABILITY_NOT_DECLARED",
            }
        ),
    )
    report = build_report(**arguments)
    assert report.task_counts is not None
    assert report.evidence_sufficiency is not None and report.risk_assessment is not None
    assert report.task_counts.not_applicable_count == 1
    assert report.task_results[0].reason_code == "CAPABILITY_NOT_DECLARED"
    assert report.task_success_rate_bp is None and report.evidence_sufficiency.task_unknown_bp == 0
    stats = report.model_dump(mode="json")["raw_statistics"]
    assert (stats["availability"]["planned"], stats["availability"]["decided"]) == (0, 0)
    capability = stats["capabilities"][0]
    assert (capability["capability_id"], capability["planned"], capability["decided"]) == (
        "verify_record",
        0,
        0,
    )
    assert (
        report.evidence_sufficiency.model_dump(mode="json")["dimensions"]["consistency"][
            "not_applicable"
        ]
        == 1
    )
    assert "verify_record:samples" in report.evidence_sufficiency.missing_evidence
    assert report.scores.evaluation_state == "PARTIAL" and report.scores.overall_score_bp is None
    assert not report.risk_assessment.critical_findings
    assert not report.risk_assessment.ordinary_failure_slots
    assert not report.risk_assessment.evidence_gap_slots
