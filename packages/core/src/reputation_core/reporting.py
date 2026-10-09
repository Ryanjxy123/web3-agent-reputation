"""M1 statistics from replayed task evidence; no clock, database or platform imports."""

from datetime import datetime
from typing import Any
from uuid import UUID

from .binding import agent_key_hash
from .evidence import hash_json
from .models import Observation, RecordVerificationInput, ReportCore, RunPlan, ScoreResult
from .record_verifier import verify_record
from .scoring_reference import evaluate_from_stats

LIMITATIONS = (
    "Local Anvil demonstration with one anchor_record functional slot; not a production trust rating.",
    "No independent availability or behavioral samples; this functional slot is not reused in their denominators.",
    "Manual claim review alone does not establish declaration mapping correctness; mapping remains unknown.",
    "Policy-v1 sample gates remain 20/10/10; this report is PARTIAL with no overall score.",
    "Offline replay proves consistency of saved evidence, not collector honesty or historical HTTP truth.",
)


def build_report(
    plan: RunPlan,
    inputs: RecordVerificationInput,
    evidence_id: UUID,
    observations: tuple[Observation, ...],
    policy: dict[str, Any],
    *,
    evaluated_at: str,
    code_version: str,
    manifest_hash: str,
    previous_report_hash: str,
) -> ReportCore:
    if (
        len(plan.slots) != 1
        or plan.slots[0] != inputs.slot
        or (plan.profile == "record-read-v1" and inputs.slot.capability_id == "anchor_record")
        or inputs.slot.purpose != "functional"
        or inputs.slot.case_kind != "positive"
        or inputs.slot.required_class != "normal"
        or inputs.slot.expected_outcome not in {"PASS", "NOT_APPLICABLE"}
        or (
            inputs.slot.applicability_reason is None
            and inputs.slot.capability_id not in plan.confirmed_capabilities
        )
        or not set(plan.confirmed_capabilities).issubset(inputs.review.confirmed_claims)
        or (
            plan.suite_id == "m1-smoke-v1"
            and (
                plan.profile != "record-write-v1"
                or plan.confirmed_capabilities != ("anchor_record",)
                or plan.template_version not in {"anchor_record@1", "anchor_record@2"}
            )
        )
        or plan.review_version != inputs.review_version
        or plan.review_version != inputs.review.review_version
        or plan.snapshot_hash != inputs.snapshot.snapshot_hash
        or plan.policy_hash != hash_json(policy)
    ):
        raise ValueError("REPORT_CONTEXT_MISMATCH")
    if len({item.observation_id for item in observations}) != len(observations) or any(
        item.slot_id != inputs.slot.slot_id for item in observations
    ):
        raise ValueError("REPORT_OBSERVATIONS_MISMATCH")
    settled = [item for item in observations if item.dispatch_state == "SETTLED"]
    expected_candidate = (
        inputs.evm.candidate_tx_hash if inputs.slot.capability_id == "anchor_record" else None
    )
    query_candidate_missing = (
        inputs.slot.capability_id == "get_tx_status"
        and inputs.rule_version == "2"
        and inputs.evm.candidate_tx_hash is None
        and inputs.evm.error_reason is not None
    )
    if (
        len(settled) != 1
        or settled[0].candidate_tx_hash != expected_candidate
        or (
            inputs.slot.capability_id == "get_tx_status"
            and inputs.slot.applicability_reason is not None
            and inputs.evm.candidate_tx_hash is not None
        )
        or (
            inputs.slot.capability_id == "get_tx_status"
            and inputs.slot.applicability_reason is None
            and not query_candidate_missing
            and inputs.evm.candidate_tx_hash != inputs.slot.task.query_tx_hash
        )
    ):
        raise ValueError("REPORT_SETTLEMENT_MISMATCH")
    times = [
        plan.planning_time,
        inputs.snapshot.core.captured_at,
        inputs.evm.observed_at,
        *[item.started_at for item in observations],
        *[item.ended_at for item in observations if item.ended_at],
    ]
    if max(times) > evaluated_at:
        raise ValueError("REPORT_TIME_PRECEDES_EVIDENCE")
    result = verify_record(inputs, (evidence_id,))
    decided = int(result.outcome in {"PASS", "FAIL"})
    age = datetime.fromisoformat(evaluated_at) - datetime.fromisoformat(min(times))
    age_seconds = age.days * 86400 + age.seconds
    stats: dict[str, Any] = {
        "profile": plan.profile,
        "availability": {
            "planned": 0,
            "decided": 0,
            "responded": 0,
            "within_latency": 0,
            "oldest_age_seconds": None,
        },
        "capabilities": [
            {
                "capability_id": inputs.slot.capability_id,
                "planned": 1,
                "decided": decided,
                "passed": int(result.outcome == "PASS"),
                "mapping": None,
                "required_classes_decided": False,
                "oldest_age_seconds": age_seconds if decided else None,
            }
        ],
        "behavior": None
        if plan.profile == "record-read-v1"
        else {
            "planned": 0,
            "accepted": 0,
            "decided": 0,
            "correct": 0,
            "oldest_age_seconds": None,
        },
        "uncovered_claim_count": len(inputs.review.unsupported_claims),
        "attribution_verified": all(
            item.outcome == "PASS"
            for item in result.assertions
            if item.rule_id.startswith(("context.", "binding.", "task.", "chain."))
        ),
        "critical_conflict": result.critical_conflict,
    }
    scores = ScoreResult.model_validate(evaluate_from_stats(stats, policy))
    return ReportCore(
        agent_ref=inputs.slot.expected.agent_ref,
        agent_key_hash=agent_key_hash(inputs.slot.expected.agent_ref),
        snapshot_hash=plan.snapshot_hash,
        run_id=plan.run_id,
        profile=plan.profile,
        observation_start=min(times),
        observation_end=max(times),
        evaluated_at=evaluated_at,
        policy_version=plan.policy_version,
        policy_hash=plan.policy_hash,
        code_version=code_version,
        raw_statistics=stats,
        scores=scores,
        assertions=tuple(sorted(result.assertions, key=lambda item: str(item.assertion_id))),
        evidence_manifest_hash=manifest_hash,
        previous_report_hash=previous_report_hash,
        limitations=LIMITATIONS
        if plan.suite_id == "m1-smoke-v1"
        else (
            "Local Anvil demonstration with one functional capability slot; not a production trust rating.",
            *LIMITATIONS[1:],
        ),
    )
