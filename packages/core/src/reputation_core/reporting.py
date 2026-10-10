"""M1 statistics from replayed task evidence; no clock, database or platform imports."""

from datetime import datetime
from fractions import Fraction
from typing import Any, Literal, cast
from uuid import UUID

from .binding import agent_key_hash
from .case_templates import CASE_CLASSES
from .evidence import hash_json
from .models import (
    ControlledTaskView,
    CriticalRisk,
    EvidenceSufficiency,
    Observation,
    Outcome,
    Reason,
    RecordVerificationInput,
    RecordVerificationResult,
    ReportCore,
    ReportTaskResult,
    RiskAssessment,
    RunPlan,
    ScoreResult,
    TaskOutcomeCounts,
)
from .record_verifier import verify_record
from .scoring_reference import _bp, _quality, _ratio, evaluate_from_stats

LIMITATIONS = (
    "Local Anvil demonstration with one anchor_record functional slot; not a production trust rating.",
    "No independent availability or behavioral samples; this functional slot is not reused in their denominators.",
    "Manual claim review alone does not establish declaration mapping correctness; mapping remains unknown.",
    "Policy-v1 sample gates remain 20/10/10; this report is PARTIAL with no overall score.",
    "Offline replay proves consistency of saved evidence, not collector honesty or historical HTTP truth.",
)

# Policy content is versioned; changing thresholds under the same name is not a new rule.
POLICY_V1_HASH = "0xb77fe04e65be4f73e3d588c6db2b5902e752fd56c771e32c874d1e631c8f61fb"


def build_report(
    plan: RunPlan,
    inputs: RecordVerificationInput | tuple[RecordVerificationInput, ...],
    evidence_id: UUID | tuple[UUID, ...],
    observations: tuple[Observation, ...],
    policy: dict[str, Any],
    *,
    evaluated_at: str,
    code_version: str,
    manifest_hash: str,
    previous_report_hash: str,
    report_schema_version: Literal["1.2.0", "1.3.0", "1.4.0", "1.5.0"] | None = None,
) -> ReportCore:
    if plan.suite_id == "formal-evaluation-v1":
        return _build_formal_report(
            plan,
            inputs if isinstance(inputs, tuple) else (inputs,),
            evidence_id if isinstance(evidence_id, tuple) else (evidence_id,),
            observations,
            policy,
            evaluated_at=evaluated_at,
            code_version=code_version,
            manifest_hash=manifest_hash,
            previous_report_hash=previous_report_hash,
            report_schema_version=report_schema_version or ("1.5.0" if plan.template_version == "capabilities@6" else "1.4.0"),
        )
    if report_schema_version is not None:
        raise ValueError("legacy reports cannot be upgraded by schema selection")
    if isinstance(inputs, tuple) or isinstance(evidence_id, tuple):
        raise ValueError("REPORT_CONTEXT_MISMATCH")
    expected_rule_version = "2" if plan.template_version.endswith("@2") else "1"
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
        or inputs.rule_version != expected_rule_version
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
        or (inputs.rule_version == "2" and settled[0].reason_code != inputs.execution_reason)
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
    task_result = ReportTaskResult(
        slot_id=inputs.slot.slot_id,
        capability_id=inputs.slot.capability_id,
        outcome=result.outcome,
        reason_code=result.reason_code,
        rule_version=inputs.rule_version,
        input_evidence_id=evidence_id,
    )
    return ReportCore(
        schema_version="1.1.0" if expected_rule_version == "2" else "1.0.0",
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
        task_results=(task_result,) if expected_rule_version == "2" else (),
        task_counts=TaskOutcomeCounts.model_validate(
            {outcome.value: int(outcome == result.outcome) for outcome in Outcome}
        )
        if expected_rule_version == "2"
        else None,
        evidence_manifest_hash=manifest_hash,
        previous_report_hash=previous_report_hash,
        limitations=LIMITATIONS
        if plan.suite_id == "m1-smoke-v1"
        else (
            "Local Anvil demonstration with one functional capability slot; not a production trust rating.",
            *LIMITATIONS[1:],
        ),
    )


PRE_DISPATCH_RULES = {
    "context.snapshot", "context.mapping", "task.intent", "binding.identity", "task.authorization"
}


def _dispatch_attributed(result: RecordVerificationResult) -> bool:
    assertions = {item.rule_id: item.outcome for item in result.assertions}
    needed = PRE_DISPATCH_RULES | (
        {"binding.signatures"} if "binding.signatures" in assertions else set()
    )
    return all(assertions.get(rule) == Outcome.PASS for rule in needed)


def _response_view(
    inputs: RecordVerificationInput, http: dict[str, Any] | None
) -> ControlledTaskView | None:
    if http is None or type(http.get("http_status")) is not int:
        return None
    if not 200 <= http["http_status"] <= 299:
        return None
    try:
        view = ControlledTaskView.model_validate(http.get("response"))
    except (ValueError, TypeError):
        return None
    if (
        view.request_id != inputs.slot.task.request_id
        or view.status_path != "/tasks/" + view.request_id
        or view.result is not None and view.result.capability_id != inputs.slot.capability_id
        or view.task_status == "succeeded" and view.result is None
    ):
        return None
    return view


def _initial_availability(
    inputs: RecordVerificationInput,
    evidence_id: UUID,
    observations: tuple[Observation, ...],
    threshold_ms: int,
) -> tuple[int, int, int]:
    """Judge the original protocol response, independently of later polls or RPC reads."""
    initial = inputs.initial_agent_http
    first = [
        item for item in observations
        if item.attempt_no == 1 and not item.diagnostic_only and item.dispatch_state != "SETTLED"
    ]
    if initial is None or len(first) != 1 or initial.get("method") != "POST":
        return 0, 0, 0
    observation = first[0]
    latency = initial.get("latency_ms")
    if (
        type(latency) is not int
        or latency < 0
        or observation.latency_ms != latency
        or observation.started_at != initial.get("started_at")
        or observation.ended_at != initial.get("ended_at")
        or observation.http_status != initial.get("http_status")
    ):
        return 0, 0, 0
    view = _response_view(inputs, initial)
    initial_input = inputs.model_copy(update={
        "agent_http": initial,
        "agent_response": initial.get("response"),
        "agent_result": view.result if view else None,
        "agent_task_status": view.task_status if view else None,
        "execution_reason": observation.reason_code,
    })
    replay = verify_record(initial_input, (evidence_id,))
    if not _dispatch_attributed(replay) or any(
        item.rule_id == "agent.evidence" and item.outcome != Outcome.PASS
        for item in replay.assertions
    ):
        return 0, 0, 0
    if view is not None:
        return 1, 1, int(latency <= threshold_ms)
    definitive_failure = any(
        item.rule_id == "agent.service"
        and item.outcome == Outcome.FAIL
        and item.reason_code in {"AGENT_SERVICE_ERROR", "SCHEMA_ERROR"}
        for item in replay.assertions
    )
    return int(definitive_failure), 0, 0


def _verified_class(
    inputs: RecordVerificationInput, result: RecordVerificationResult
) -> str | None:
    """A frozen label is coverage only when independently read facts support that class."""
    if result.outcome not in {Outcome.PASS, Outcome.FAIL}:
        return None
    if inputs.slot.case_kind == "negative":
        valid_request = any(
            assertion.rule_id == "functional.request_validity" and assertion.outcome == Outcome.PASS
            for assertion in result.assertions
        )
        decided_rejection = any(
            assertion.rule_id in {"functional.rejection", "agent.service"}
            and assertion.outcome in {Outcome.PASS, Outcome.FAIL}
            for assertion in result.assertions
        )
        return inputs.slot.required_class if valid_request and decided_rejection else None
    if inputs.slot.capability_id == "anchor_record":
        return "normal" if inputs.slot.case_kind == "positive" else None
    for assertion in result.assertions:
        if not isinstance(assertion.expected, dict):
            continue
        if assertion.rule_id == "query.status":
            return {
                "SUCCESS": "success", "REVERTED": "revert", "PENDING": "pending", "NOT_FOUND": "not_found"
            }.get(
                str(assertion.expected.get("status"))
            )
        if assertion.rule_id == "query.record":
            if assertion.expected.get("exists") is False:
                return "not_found"
            return (
                "match" if assertion.expected.get("record_hash") == inputs.slot.task.record_hash
                else "hash_mismatch"
            )
    return None


def _assess_evidence(
    stats: dict[str, Any], scores: ScoreResult, inputs: tuple[RecordVerificationInput, ...],
    results: list[RecordVerificationResult], policy: dict[str, Any],
) -> tuple[EvidenceSufficiency, RiskAssessment]:
    """Explain existing exact policy gates and preserve only confirmed critical failures."""
    gates = policy["gates"]
    minimum_coverage = Fraction(gates["min_coverage_bp"], 10_000)
    minimum_quality = Fraction(gates["min_sufficiency_bp"], 10_000)
    maximum_unresolved = 1 - minimum_coverage
    ttl = gates["freshness_ttl_seconds"]
    dimensions: dict[str, Any] = {}
    capability_details: list[dict[str, Any]] = []
    missing: list[str] = []
    qualities: list[Fraction] = []
    unresolved_ratios: list[Fraction] = []

    def sample_detail(name: str, sample: dict[str, Any], required: int) -> dict[str, Any]:
        planned, decided = sample["planned"], sample["decided"]
        unresolved = planned - decided
        coverage, quantity, freshness = _quality(
            decided, planned, required, sample.get("oldest_age_seconds"), ttl
        )
        ratio = _ratio(unresolved, planned)
        checks = {
            "samples": decided >= required,
            "coverage": coverage >= minimum_coverage,
            "unresolved": bool(planned) and ratio <= maximum_unresolved,
            "freshness": freshness >= minimum_quality,
        }
        for check, passed in checks.items():
            if not passed:
                missing.append(f"{name}:{check}")
        return {
            "planned": planned, "decided": decided, "unresolved": unresolved,
            "required_samples": required, "oldest_age_seconds": sample.get("oldest_age_seconds"),
            "coverage_bp": _bp(coverage), "sample_bp": _bp(quantity),
            "freshness_bp": _bp(freshness), "sufficiency_bp": _bp(min(coverage, quantity, freshness)),
            "unknown_or_unresolved_bp": _bp(ratio), "exact_gates": checks,
        }

    availability = sample_detail("availability", stats["availability"], policy["availability"]["min_samples"])
    dimensions["availability"] = availability
    quantities = _quality(
        availability["decided"], availability["planned"], availability["required_samples"],
        availability["oldest_age_seconds"], ttl,
    )
    qualities.append(min(quantities))
    unresolved_ratios.append(_ratio(availability["unresolved"], availability["planned"]))

    capabilities = stats["capabilities"]
    uncovered = stats["uncovered_claim_count"]
    total_claims = len(capabilities) + uncovered
    known_mapping = sum(capability["mapping"] is not None for capability in capabilities)
    tested_claims = sum(bool(capability["decided"]) for capability in capabilities)
    total_planned = total_decided = 0
    capability_quantities = []
    for capability in capabilities:
        cid = capability["capability_id"]
        detail = sample_detail(cid, capability, policy["consistency"]["min_cases_per_capability"])
        detail.update({
            "capability_id": cid, "mapping": capability["mapping"],
            "required_classes": capability["required_classes"],
            "covered_classes": capability["covered_classes"],
            "missing_classes": capability["missing_classes"],
            "not_applicable": sum(
                result.outcome == Outcome.NOT_APPLICABLE
                and item.slot.purpose == "functional" and item.slot.capability_id == cid
                for item, result in zip(inputs, results, strict=True)
            ),
        })
        detail["exact_gates"].update({
            "mapping": capability["mapping"] is not None,
            "mandatory_classes": capability["required_classes_decided"],
        })
        if capability["mapping"] is None:
            missing.append(f"{cid}:mapping")
        missing.extend(f"{cid}:case:{case}" for case in capability["missing_classes"])
        capability_details.append(detail)
        total_planned += capability["planned"]
        total_decided += capability["decided"]
        quality = _quality(
            capability["decided"], capability["planned"], detail["required_samples"],
            capability.get("oldest_age_seconds"), ttl,
        )
        capability_quantities.append(quality)
        unresolved_ratios.append(_ratio(detail["unresolved"], detail["planned"]))
    consistency_coverage = min(
        _ratio(total_decided, total_planned), _ratio(known_mapping, total_claims)
    )
    consistency_sample = min((item[1] for item in capability_quantities), default=Fraction(0))
    if uncovered:
        consistency_sample = Fraction(0)
        missing.append("consistency:uncovered_claims")
    consistency_freshness = min((item[2] for item in capability_quantities), default=Fraction(0))
    consistency_quality = min(consistency_coverage, consistency_sample, consistency_freshness)
    qualities.append(consistency_quality)
    consistency_checks = {
        "samples": bool(capabilities) and not uncovered and all(
            detail["exact_gates"]["samples"] for detail in capability_details
        ),
        "coverage": consistency_coverage >= minimum_coverage and all(
            detail["exact_gates"]["coverage"] for detail in capability_details
        ),
        "unresolved": bool(total_planned) and all(
            detail["exact_gates"]["unresolved"] for detail in capability_details
        ),
        "mapping": bool(capabilities) and not uncovered and known_mapping == total_claims,
        "mandatory_classes": bool(capabilities) and all(
            detail["exact_gates"]["mandatory_classes"] for detail in capability_details
        ),
        "freshness": consistency_freshness >= minimum_quality,
    }
    dimensions["consistency"] = {
        "planned": total_planned, "decided": total_decided, "unresolved": total_planned - total_decided,
        "oldest_age_seconds": max(
            (capability["oldest_age_seconds"] for capability in capabilities
             if capability["oldest_age_seconds"] is not None), default=None,
        ),
        "claim_count": total_claims, "mapped_claim_count": known_mapping, "tested_claim_count": tested_claims,
        "claim_coverage_bp": _bp(_ratio(tested_claims, total_claims)),
        "mapping_coverage_bp": _bp(_ratio(known_mapping, total_claims)),
        "coverage_bp": _bp(consistency_coverage), "sample_bp": _bp(consistency_sample),
        "freshness_bp": _bp(consistency_freshness), "sufficiency_bp": _bp(consistency_quality),
        "unknown_or_unresolved_bp": _bp(_ratio(total_planned - total_decided, total_planned)),
        "exact_gates": consistency_checks,
    }
    for check, passed in consistency_checks.items():
        if not passed:
            missing.append(f"consistency:{check}")
    if stats["behavior"] is not None:
        behavior = sample_detail("behavior", stats["behavior"], policy["behavior"]["min_accepted_decided_tasks"])
        behavior["accepted"] = stats["behavior"]["accepted"]
        behavior["exact_gates"]["binding"] = stats["attribution_verified"]
        dimensions["behavior"] = behavior
        quality = _quality(
            behavior["decided"], behavior["planned"], behavior["required_samples"],
            behavior["oldest_age_seconds"], ttl,
        )
        qualities.append(min(quality) if stats["attribution_verified"] else Fraction(0))
        unresolved_ratios.append(_ratio(behavior["unresolved"], behavior["planned"]))
        if not stats["attribution_verified"]:
            missing.append("behavior:binding")
    else:
        dimensions["behavior"] = {"state": "NOT_APPLICABLE", "exact_gates": {}}
    for dimension, detail in dimensions.items():
        detail["state"] = scores.dimensions[cast(Literal["availability", "consistency", "behavior"], dimension)].state
        detail["not_applicable"] = sum(
            result.outcome == Outcome.NOT_APPLICABLE
            and item.slot.purpose == {"availability": "availability", "consistency": "functional", "behavior": "behavioral"}[dimension]
            for item, result in zip(inputs, results, strict=True)
        )
    exact_quality = min(qualities, default=Fraction(0))
    if exact_quality < minimum_quality:
        missing.append("overall:sufficiency")
    allowed = not missing and all(
        value.state in {"COMPLETE", "NOT_APPLICABLE"} for value in scores.dimensions.values()
    )
    if allowed != (scores.overall_score_bp is not None):
        raise ValueError("EVIDENCE_GATE_MISMATCH")
    applicable_results = [result for result in results if result.outcome != Outcome.NOT_APPLICABLE]
    sufficiency = EvidenceSufficiency(
        thresholds={
            "min_coverage_bp": gates["min_coverage_bp"], "min_sufficiency_bp": gates["min_sufficiency_bp"],
            "max_unknown_or_unresolved_bp": 10_000 - gates["min_coverage_bp"],
            "freshness_ttl_seconds": ttl,
            "availability_min_samples": policy["availability"]["min_samples"],
            "consistency_min_samples_per_capability": policy["consistency"]["min_cases_per_capability"],
            "behavior_min_accepted_decided_samples": policy["behavior"]["min_accepted_decided_tasks"],
            "unresolved_threshold_basis": "1 - policy min_coverage; includes unaccepted or undecided planned slots",
        },
        dimensions=dimensions, capabilities=tuple(capability_details),
        unknown_or_unresolved_bp=cast(int, _bp(max(unresolved_ratios, default=Fraction(0)))),
        task_unknown_bp=cast(int, _bp(_ratio(
            sum(result.outcome == Outcome.UNKNOWN for result in applicable_results), len(applicable_results)
        ))),
        sufficiency_bp=scores.sufficiency_bp,
        exact_gates={
            "dimensions_complete": all(
                value.state in {"COMPLETE", "NOT_APPLICABLE"} for value in scores.dimensions.values()
            ),
            "sufficiency": exact_quality >= minimum_quality,
            "unresolved": all(ratio <= maximum_unresolved for ratio in unresolved_ratios),
            "binding": stats["profile"] == "record-read-v1" or stats["attribution_verified"],
        },
        uncovered_claims=tuple(stats["uncovered_claims"]), missing_evidence=tuple(sorted(set(missing))),
        gate_status="PASS" if allowed else "PARTIAL", overall_allowed=allowed,
    )
    findings = tuple(
        CriticalRisk(
            slot_id=assertion.slot_id, assertion_id=assertion.assertion_id,
            rule_id=assertion.rule_id, reason_code=cast(Reason, assertion.reason_code),
            evidence_refs=assertion.evidence_refs,
        )
        for assertion in sorted(
            (assertion for result in results for assertion in result.assertions
             if assertion.critical and assertion.outcome == Outcome.FAIL),
            key=lambda assertion: str(assertion.assertion_id),
        )
    )
    risks = RiskAssessment(
        conclusion="CONFIRMED_CRITICAL_CONFLICT" if findings else "NO_CONFIRMED_CRITICAL_CONFLICT",
        critical_findings=findings,
        ordinary_failure_slots=tuple(
            item.slot.slot_id for item, result in zip(inputs, results, strict=True)
            if result.outcome == Outcome.FAIL and not result.critical_conflict
        ),
        evidence_gap_slots=tuple(
            item.slot.slot_id for item, result in zip(inputs, results, strict=True)
            if any(assertion.outcome == Outcome.UNKNOWN for assertion in result.assertions)
        ),
    )
    return sufficiency, risks


def _build_formal_report(
    plan: RunPlan,
    inputs: tuple[RecordVerificationInput, ...],
    evidence_ids: tuple[UUID, ...],
    observations: tuple[Observation, ...],
    policy: dict[str, Any],
    *,
    evaluated_at: str,
    code_version: str,
    manifest_hash: str,
    previous_report_hash: str,
    report_schema_version: Literal["1.2.0", "1.3.0", "1.4.0", "1.5.0"],
) -> ReportCore:
    expected_rule = {"1.2.0": "3", "1.3.0": "4", "1.4.0": "5", "1.5.0": "6"}[report_schema_version]
    if (
        plan.template_version != f"capabilities@{expected_rule}"
        or len(inputs) != len(plan.slots)
        or len(evidence_ids) != len(inputs)
        or len(set(evidence_ids)) != len(evidence_ids)
        or plan.policy_hash != hash_json(policy)
        or plan.policy_version != policy.get("policy_version")
        or plan.policy_hash != POLICY_V1_HASH
    ):
        raise ValueError("REPORT_CONTEXT_MISMATCH")
    first = inputs[0]
    if plan.confirmed_capabilities != first.review.confirmed_claims:
        raise ValueError("REPORT_CONTEXT_MISMATCH")
    planned_ids = {slot.slot_id for slot in plan.slots}
    if (
        len({item.observation_id for item in observations}) != len(observations)
        or {item.slot_id for item in observations} != planned_ids
    ):
        raise ValueError("REPORT_OBSERVATIONS_MISMATCH")
    times = [plan.planning_time, first.snapshot.core.captured_at]
    results: list[RecordVerificationResult] = []
    slot_observations: list[tuple[Observation, ...]] = []
    for slot, item, identifier in zip(plan.slots, inputs, evidence_ids, strict=True):
        if (
            item.slot != slot
            or item.snapshot != first.snapshot
            or item.review != first.review
            or item.platform_instance_id != first.platform_instance_id
            or item.review_version != plan.review_version
            or item.review.review_version != plan.review_version
            or item.snapshot.snapshot_hash != plan.snapshot_hash
            or item.rule_version != expected_rule
            or slot.expected.agent_ref != first.slot.expected.agent_ref
            or slot.expected.execution_chain != first.slot.expected.execution_chain
            or slot.purpose == "availability" and slot.capability_id == "anchor_record"
            or slot.purpose == "behavioral" and (
                slot.capability_id != "anchor_record" or slot.case_kind != "positive"
            )
        ):
            raise ValueError("REPORT_CONTEXT_MISMATCH")
        observed = tuple(value for value in observations if value.slot_id == slot.slot_id)
        settlements = [value for value in observed if value.dispatch_state == "SETTLED"]
        expected_candidate = item.evm.candidate_tx_hash if slot.capability_id == "anchor_record" else None
        if (
            len(settlements) != 1
            or settlements[0].candidate_tx_hash != expected_candidate
            or settlements[0].reason_code != item.execution_reason
            or slot.capability_id == "get_tx_status" and item.evm.candidate_tx_hash is not None
            and item.evm.candidate_tx_hash != slot.task.query_tx_hash
        ):
            raise ValueError("REPORT_SETTLEMENT_MISMATCH")
        for observation in observed:
            if observation.ended_at is not None and observation.ended_at < observation.started_at:
                raise ValueError("REPORT_TIME_PRECEDES_EVIDENCE")
            times.extend([
                observation.started_at, *([observation.ended_at] if observation.ended_at else [])
            ])
        times.extend([item.evm.observed_at, item.intent_persisted_at])
        if item.dispatch_started_at:
            times.append(item.dispatch_started_at)
        for http in (item.agent_http, item.initial_agent_http):
            if http is not None:
                times.extend(
                    timestamp for field in ("started_at", "ended_at")
                    if isinstance(timestamp := http.get(field), str)
                )
        results.append(verify_record(item, (identifier,)))
        slot_observations.append(observed)
    if max(times) > evaluated_at:
        raise ValueError("REPORT_TIME_PRECEDES_EVIDENCE")
    age = datetime.fromisoformat(evaluated_at) - datetime.fromisoformat(min(times))
    age_seconds = age.days * 86400 + age.seconds
    availability: dict[str, Any] = {
        "planned": 0, "decided": 0, "responded": 0, "within_latency": 0,
        "oldest_age_seconds": None,
    }
    behavior: dict[str, Any] | None = None if plan.profile == "record-read-v1" else {
        "planned": 0, "accepted": 0, "decided": 0, "correct": 0, "oldest_age_seconds": None,
    }
    capabilities: list[dict[str, Any]] = []
    basis: list[dict[str, Any]] = []
    binding_verified = True
    for item, identifier, result, observed in zip(
        inputs, evidence_ids, results, slot_observations, strict=True
    ):
        applicable = result.outcome != Outcome.NOT_APPLICABLE
        decided = int(result.outcome in {Outcome.PASS, Outcome.FAIL})
        contribution: dict[str, Any] = {
            "slot_id": str(item.slot.slot_id), "purpose": item.slot.purpose.value,
            "outcome": result.outcome.value, "input_evidence_id": str(identifier),
            "planned": int(applicable), "decided": 0,
        }
        if item.slot.purpose == "availability" and applicable:
            n, responded, timely = _initial_availability(
                item, identifier, observed, policy["availability"]["latency_threshold_ms"]
            )
            availability["planned"] += 1
            availability["decided"] += n
            availability["responded"] += responded
            availability["within_latency"] += timely
            contribution.update(decided=n, responded=responded, within_latency=timely)
        elif item.slot.purpose == "behavioral" and applicable:
            assert behavior is not None
            settlement = next(value for value in observed if value.dispatch_state == "SETTLED")
            accepted = settlement.accepted and any(
                _response_view(item, http) is not None
                for http in (item.agent_http, item.initial_agent_http)
            )
            n = decided if accepted else 0
            behavior["planned"] += 1
            behavior["accepted"] += int(accepted)
            behavior["decided"] += n
            correct = int(accepted and result.outcome == Outcome.PASS)
            behavior["correct"] += correct
            contribution.update(decided=n, accepted=int(accepted), correct=correct)
            binding_verified &= _dispatch_attributed(result)
        elif item.slot.purpose == "functional" and applicable:
            contribution["decided"] = decided
        basis.append(contribution)
    for capability in first.review.confirmed_claims:
        members = [
            (item, identifier, result) for item, identifier, result
            in zip(inputs, evidence_ids, results, strict=True)
            if item.slot.capability_id == capability
        ]
        functional = [(item, result) for item, _, result in members if item.slot.purpose == "functional"]
        decided_members = [
            (item, result) for item, result in functional
            if result.outcome in {Outcome.PASS, Outcome.FAIL}
        ]
        covered = {
            item.slot.required_class for item, result in decided_members
            if item.slot.required_class == _verified_class(item, result)
        }
        required = set(CASE_CLASSES[capability])
        mappings: list[tuple[int, UUID]] = []
        for item, identifier, result in members:
            if item.slot.case_kind != "positive" or item.slot.purpose == "background":
                continue
            if not _dispatch_attributed(result) or any(
                assertion.rule_id == "agent.evidence" and assertion.outcome != Outcome.PASS
                for assertion in result.assertions
            ):
                continue
            view = _response_view(item, item.agent_http)
            if view is None:
                continue
            if any(
                assertion.reason_code == "CAPABILITY_EXPLICITLY_UNSUPPORTED"
                and assertion.outcome == Outcome.FAIL for assertion in result.assertions
            ):
                mappings.append((0, identifier))
            elif view.result is not None:
                mappings.append((1, identifier))
        mapping = min((value for value, _ in mappings), default=None)
        capabilities.append({
            "capability_id": capability,
            "planned": sum(result.outcome != Outcome.NOT_APPLICABLE for _, result in functional),
            "decided": len(decided_members),
            "passed": sum(result.outcome == Outcome.PASS for _, result in decided_members),
            "mapping": mapping,
            "mapping_evidence_ids": [str(identifier) for _, identifier in mappings],
            "required_classes_decided": required.issubset(covered),
            "required_classes": sorted(required), "covered_classes": sorted(covered & required),
            "missing_classes": sorted(required - covered),
            "oldest_age_seconds": age_seconds if decided_members else None,
        })
    if availability["decided"]:
        availability["oldest_age_seconds"] = age_seconds
    if behavior is not None and behavior["decided"]:
        behavior["oldest_age_seconds"] = age_seconds
    declared = first.snapshot.core.normalized_metadata.get("capabilities", [])
    uncovered = set(first.review.unsupported_claims) | (
        {value for value in declared if isinstance(value, str)} - set(first.review.confirmed_claims)
        if isinstance(declared, list) else set()
    )
    stats: dict[str, Any] = {
        "profile": plan.profile, "availability": availability, "capabilities": capabilities,
        "behavior": behavior, "uncovered_claim_count": len(uncovered),
        "uncovered_claims": sorted(uncovered), "attribution_verified": binding_verified,
        "critical_conflict": any(result.critical_conflict for result in results),
        "basis": basis,
    }
    scores = ScoreResult.model_validate(evaluate_from_stats(stats, policy))
    counts = {outcome.value: sum(result.outcome == outcome for result in results) for outcome in Outcome}
    decided_count = counts["PASS"] + counts["FAIL"]
    sufficiency, risks = (
        _assess_evidence(stats, scores, inputs, results, policy)
        if report_schema_version in {"1.3.0", "1.4.0", "1.5.0"} else (None, None)
    )
    return ReportCore(
        schema_version=report_schema_version, scoring_rule_version="three-dimensional-v1",
        assessment_rule_version="evidence-assessment-v1" if sufficiency is not None else None,
        evidence_sufficiency=sufficiency, risk_assessment=risks,
        task_success_rate_bp=(2 * counts["PASS"] * 10_000 + decided_count) // (2 * decided_count)
        if decided_count else None,
        agent_ref=first.slot.expected.agent_ref, agent_key_hash=agent_key_hash(first.slot.expected.agent_ref),
        snapshot_hash=plan.snapshot_hash, run_id=plan.run_id, profile=plan.profile,
        observation_start=min(times), observation_end=max(times), evaluated_at=evaluated_at,
        policy_version=plan.policy_version, policy_hash=plan.policy_hash, code_version=code_version,
        raw_statistics=stats, scores=scores,
        assertions=tuple(sorted(
            (assertion for result in results for assertion in result.assertions),
            key=lambda item: str(item.assertion_id),
        )),
        task_results=tuple(
            ReportTaskResult(
                slot_id=item.slot.slot_id, capability_id=item.slot.capability_id,
                outcome=result.outcome, reason_code=result.reason_code, rule_version=item.rule_version,
                input_evidence_id=identifier,
            ) for item, identifier, result in zip(inputs, evidence_ids, results, strict=True)
        ),
        task_counts=TaskOutcomeCounts.model_validate(counts), evidence_manifest_hash=manifest_hash,
        previous_report_hash=previous_report_hash,
        limitations=(
            "Controlled local protocol evidence; not a calibrated trust probability.",
            "Purpose-separated slots contribute once; task success rate and dimension scores have distinct denominators.",
            "Missing mandatory case classes or policy gates keep the report PARTIAL with no overall score.",
            "Offline replay proves saved evidence consistency, not collector honesty or historical HTTP truth.",
        ),
    )
