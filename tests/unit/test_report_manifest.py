import json
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError
from reputation_core.evidence import hash_json
from reputation_core.models import ManifestDocument, Observation, RecordVerificationInput, RunPlan
from reputation_core.reporting import build_report

from tests.factories import HASH, NOW, ZERO
from tests.unit.test_task_outcomes import excluded_input, task_input


@pytest.mark.parametrize(
    "path",
    [
        "report_core.json",
        "evidence_manifest.json",
        "anchor_receipt.json",
        "../policy.json",
        "/policy.json",
        "schemas/../policy.json",
        "C:/policy.json",
        "schemas\\policy.json",
    ],
)
def test_manifest_rejects_commitment_cycles_and_nonportable_paths(path):
    with pytest.raises(ValidationError):
        ManifestDocument(path=path, evidence_id=uuid4())


def report_arguments(reason, *, legacy=False):
    body = excluded_input() if reason == "CAPABILITY_NOT_DECLARED" else task_input()
    body["execution_reason"] = reason
    if reason == "PLATFORM_RPC_ERROR":
        body["evm"].update(results={}, error_reason=reason)
    elif reason == "AGENT_SERVICE_ERROR":
        response = {"error": {"code": "INTERNAL"}}
        body["agent_http"].update(http_status=503, response=response)
        body.update(agent_response=response, agent_result=None, agent_task_status=None)
    if legacy:
        body.update(rule_version="1", agent_http=None)
    inputs = RecordVerificationInput.model_validate(body)
    policy = json.loads(
        (Path(__file__).resolve().parents[2] / "configs/policies/policy-v1.json").read_text()
    )
    return {
        "plan": RunPlan(
            run_id=uuid4(),
            snapshot_hash=inputs.snapshot.snapshot_hash,
            review_version=inputs.review_version,
            policy_version="policy-v1",
            policy_hash=hash_json(policy),
            profile="record-read-v1",
            confirmed_capabilities=inputs.review.confirmed_claims,
            suite_id="capabilities-v1",
            template_version="capabilities@1" if legacy else "capabilities@2",
            planning_time=NOW,
            slots=(inputs.slot,),
        ),
        "inputs": inputs,
        "evidence_id": uuid4(),
        "observations": (
            Observation(
                observation_id=uuid4(),
                slot_id=inputs.slot.slot_id,
                attempt_no=1,
                dispatch_state="SETTLED",
                started_at=NOW,
                ended_at=NOW,
                latency_ms=None,
                error_origin=None,
                reason_code=reason,
                accepted=reason != "CAPABILITY_NOT_DECLARED",
                candidate_tx_hash=None,
                evidence_refs=(),
                diagnostic_only=False,
            ),
        ),
        "policy": policy,
        "evaluated_at": "2026-10-02T12:00:01.000Z",
        "code_version": "0" * 40,
        "manifest_hash": HASH,
        "previous_report_hash": ZERO,
    }


@pytest.mark.parametrize(
    "reason,outcome",
    [
        (None, "PASS"),
        ("CAPABILITY_NOT_DECLARED", "NOT_APPLICABLE"),
        ("PLATFORM_RPC_ERROR", "UNKNOWN"),
        ("AGENT_SERVICE_ERROR", "FAIL"),
    ],
)
def test_report_binds_final_reason_for_all_outcomes(reason, outcome):
    arguments = report_arguments(reason)
    report = build_report(**arguments)
    assert report.task_results[0].outcome == outcome
    changed = arguments["observations"][0].model_copy(update={"reason_code": "AGENT_TASK_FAILED"})
    arguments["observations"] = (changed,)
    with pytest.raises(ValueError, match="REPORT_SETTLEMENT_MISMATCH"):
        build_report(**arguments)


def test_diagnostic_failure_does_not_change_the_final_settlement_reason():
    arguments = report_arguments(None)
    settled = arguments["observations"][0]
    diagnostic = settled.model_copy(
        update={
            "observation_id": uuid4(),
            "dispatch_state": "DISPATCH_UNCERTAIN",
            "reason_code": "PLATFORM_NETWORK_ERROR",
            "diagnostic_only": True,
        }
    )
    arguments["observations"] = (diagnostic, settled)
    assert build_report(**arguments).task_results[0].outcome == "PASS"


def test_legacy_report_retains_existing_reason_compatibility():
    arguments = report_arguments(None, legacy=True)
    arguments["observations"] = (
        arguments["observations"][0].model_copy(update={"reason_code": "AGENT_TASK_FAILED"}),
    )
    assert build_report(**arguments).schema_version == "1.0.0"
