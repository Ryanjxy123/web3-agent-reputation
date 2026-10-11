"""Purpose-separated public statistics using the unchanged policy-v1 exact gates."""

from datetime import datetime
from typing import Any
from uuid import UUID

from .binding import agent_key_hash
from .case_templates import CASE_CLASSES
from .evidence import hash_json
from .models import (
    Observation,
    Outcome,
    ReportCore,
    ReportTaskResult,
    ScoreResult,
    TaskOutcomeCounts,
)
from .models.public_evaluation import (
    PublicReadonlyGrant,
    PublicReadonlyRunPlan,
    PublicReadonlyVerificationInput,
)
from .public_verifier import public_observation, verify_public_readonly
from .reporting import POLICY_V1_HASH, _assess_evidence
from .scoring_reference import evaluate_from_stats


def build_public_readonly_report(
    plan: PublicReadonlyRunPlan,
    inputs: tuple[PublicReadonlyVerificationInput, ...],
    evidence_ids: tuple[UUID, ...],
    observations: tuple[Observation, ...],
    policy: dict[str, Any],
    *, evaluated_at: str, code_version: str, manifest_hash: str, previous_report_hash: str,
) -> ReportCore:
    if (not inputs or len(inputs) != len(plan.slots) or len(evidence_ids) != len(inputs)
            or len(set(evidence_ids)) != len(evidence_ids)
            or plan.policy_hash != POLICY_V1_HASH or hash_json(policy) != plan.policy_hash
            or policy.get("policy_version") != plan.policy_version
            or len(observations) != len(inputs)
            or len({value.observation_id for value in observations}) != len(observations)):
        raise ValueError("REPORT_CONTEXT_MISMATCH")
    first = inputs[0]
    if first.review.confirmed_claims != plan.confirmed_capabilities:
        raise ValueError("REPORT_CONTEXT_MISMATCH")
    results = []
    agent_ids: set[UUID] = set()
    agent_hashes: set[str] = set()
    grants: dict[UUID, PublicReadonlyGrant] = {}
    for item in inputs:
        packet_map = {packet.record.evidence_id: packet for packet in item.packets}
        hashes = {packet_map[ref].record.blob_hash for ref in item.agent_evidence_refs}
        if agent_ids.intersection(item.agent_evidence_refs) or agent_hashes.intersection(hashes):
            raise ValueError("REPORT_AGENT_SAMPLE_REUSED")
        agent_ids.update(item.agent_evidence_refs)
        agent_hashes.update(hashes)
        if item.grant is not None:
            previous = grants.setdefault(item.grant.grant_id, item.grant)
            if previous != item.grant or sum(slot.grant_id == item.grant.grant_id for slot in plan.slots) > item.grant.max_tasks:
                raise ValueError("REPORT_GRANT_SCOPE_MISMATCH")
    times = [plan.planning_time, first.snapshot.core.captured_at]
    for slot, item, identifier, observation in zip(plan.slots, inputs, evidence_ids, observations, strict=True):
        if (item.slot != slot or item.snapshot != first.snapshot or item.review != first.review
                or item.platform_instance_id != first.platform_instance_id
                or item.review_version != plan.review_version or item.review.review_version != plan.review_version
                or item.snapshot.snapshot_hash != plan.snapshot_hash
                or item.identity_evidence_refs != first.identity_evidence_refs
                or observation != public_observation(item)):
            raise ValueError("REPORT_CONTEXT_MISMATCH")
        times.extend([item.intent_persisted_at, item.observed_at, observation.started_at])
        if item.dispatch_started_at is not None:
            times.append(item.dispatch_started_at)
        if observation.ended_at is not None:
            times.append(observation.ended_at)
        times.extend(packet.record.observed_at for packet in item.packets)
        results.append(verify_public_readonly(item, (identifier,)))
    if max(times) > evaluated_at:
        raise ValueError("REPORT_TIME_PRECEDES_EVIDENCE")
    age = datetime.fromisoformat(evaluated_at) - datetime.fromisoformat(min(times))
    age_seconds = age.days * 86400 + age.seconds
    availability: dict[str, Any] = {
        "planned": 0, "decided": 0, "responded": 0, "within_latency": 0,
        "oldest_age_seconds": None,
    }
    basis = []
    functional = []
    covered = set()
    mappings = []
    for item, identifier, result, observation in zip(inputs, evidence_ids, results, observations, strict=True):
        by_rule = {assertion.rule_id: assertion for assertion in result.assertions}
        attributed = all(by_rule.get(rule) is not None and by_rule[rule].outcome == Outcome.PASS
                         for rule in ("context.snapshot", "context.mapping", "task.intent", "task.authorization", "identity.readonly", "agent.evidence"))
        service = by_rule.get("agent.service")
        valid_service = attributed and service is not None and service.outcome == Outcome.PASS
        decided = int(result.outcome in {Outcome.PASS, Outcome.FAIL})
        contribution: dict[str, Any] = {
            "slot_id": str(item.slot.slot_id), "purpose": item.slot.purpose.value,
            "outcome": result.outcome.value, "input_evidence_id": str(identifier),
            "planned": 1, "decided": 0,
        }
        if item.slot.purpose == "availability":
            service_failed = attributed and service is not None and service.outcome == Outcome.FAIL
            responded = int(valid_service)
            n = int(valid_service or service_failed)
            timely = int(valid_service and observation.latency_ms is not None
                         and observation.latency_ms <= policy["availability"]["latency_threshold_ms"])
            availability["planned"] += 1
            availability["decided"] += n
            availability["responded"] += responded
            availability["within_latency"] += timely
            contribution.update(decided=n, responded=responded, within_latency=timely)
        elif item.slot.purpose == "functional":
            functional.append(result)
            contribution["decided"] = decided
            if item.slot.case_kind == "negative":
                validity, rejection = by_rule.get("functional.request_validity"), by_rule.get("functional.rejection")
                if (validity is not None and validity.outcome == Outcome.PASS
                        and rejection is not None and rejection.outcome in {Outcome.PASS, Outcome.FAIL}):
                    covered.add("invalid_format")
            elif decided and item.slot.required_class == "match":
                events = by_rule.get("public.proof.events")
                if events is not None and isinstance(events.expected, list) and events.expected:
                    covered.add("match")
        if item.slot.case_kind == "positive" and item.slot.purpose != "background" and valid_service:
            mappings.append((1, identifier))
        basis.append(contribution)
    if availability["decided"]:
        availability["oldest_age_seconds"] = age_seconds
    required = set(CASE_CLASSES["verify_record"])
    functional_decided = [result for result in functional if result.outcome in {Outcome.PASS, Outcome.FAIL}]
    capability = {
        "capability_id": "verify_record", "planned": len(functional), "decided": len(functional_decided),
        "passed": sum(result.outcome == Outcome.PASS for result in functional_decided),
        "mapping": 1 if mappings else None,
        "mapping_evidence_ids": [str(identifier) for _, identifier in mappings],
        "required_classes_decided": required.issubset(covered), "required_classes": sorted(required),
        "covered_classes": sorted(covered & required), "missing_classes": sorted(required - covered),
        "oldest_age_seconds": age_seconds if functional_decided else None,
    }
    uncovered = sorted(set(first.review.unsupported_claims))
    business_outcomes = [
        next((assertion.outcome for assertion in result.assertions
              if assertion.rule_id == "public.business"), Outcome.UNKNOWN)
        for item, result in zip(inputs, results, strict=True) if item.slot.case_kind == "positive"
    ]
    business_outcome = (Outcome.FAIL if Outcome.FAIL in business_outcomes else Outcome.PASS
                        if business_outcomes and all(value == Outcome.PASS for value in business_outcomes)
                        else Outcome.UNKNOWN)
    stats: dict[str, Any] = {
        "profile": "record-read-v1", "availability": availability, "capabilities": [capability],
        "behavior": None, "uncovered_claim_count": len(uncovered), "uncovered_claims": uncovered,
        "attribution_verified": False, "critical_conflict": any(result.critical_conflict for result in results),
        "basis": basis,
        "public_identity": {
            "registration_outcome": "PASS" if all(any(a.rule_id == "context.snapshot" and a.outcome == Outcome.PASS for a in result.assertions) for result in results) else "UNKNOWN",
            "endpoint_outcome": "PASS" if all(any(a.rule_id == "context.snapshot" and a.outcome == Outcome.PASS for a in result.assertions) for result in results) else "UNKNOWN",
            "executor_outcome": "UNKNOWN", "executor_reason": "BINDING_UNVERIFIED",
            "business_outcome": business_outcome.value,
        },
    }
    scores = ScoreResult.model_validate(evaluate_from_stats(stats, policy))
    sufficiency, risks = _assess_evidence(stats, scores, inputs, results, policy)
    counts = {outcome.value: sum(result.outcome == outcome for result in results) for outcome in Outcome}
    decided = counts["PASS"] + counts["FAIL"]
    return ReportCore(
        schema_version="1.6.0", scoring_rule_version="three-dimensional-v1",
        assessment_rule_version="evidence-assessment-v1", evidence_sufficiency=sufficiency, risk_assessment=risks,
        task_success_rate_bp=(2 * counts["PASS"] * 10_000 + decided) // (2 * decided) if decided else None,
        agent_ref=first.slot.expected.agent_ref, agent_key_hash=agent_key_hash(first.slot.expected.agent_ref),
        snapshot_hash=plan.snapshot_hash, run_id=plan.run_id, profile="record-read-v1",
        observation_start=min(times), observation_end=max(times), evaluated_at=evaluated_at,
        policy_version=plan.policy_version, policy_hash=plan.policy_hash, code_version=code_version,
        raw_statistics=stats, scores=scores,
        assertions=tuple(sorted((assertion for result in results for assertion in result.assertions), key=lambda assertion: str(assertion.assertion_id))),
        task_results=tuple(ReportTaskResult(slot_id=item.slot.slot_id, capability_id="verify_record",
            outcome=result.outcome, reason_code=result.reason_code, rule_version="7", input_evidence_id=identifier)
            for item, identifier, result in zip(inputs, evidence_ids, results, strict=True)),
        task_counts=TaskOutcomeCounts.model_validate(counts), evidence_manifest_hash=manifest_hash,
        previous_report_hash=previous_report_hash,
        limitations=(
            "Public ERC-8004 registration and endpoint association do not prove executor control.",
            "This read-only evaluation verifies historical Base proofs; it does not execute new on-chain writes.",
            "Unknown hash searches do not establish global absence; unobserved mandatory classes remain missing.",
            "Policy-v1 thresholds remain unchanged; limited samples retain PARTIAL and no overall score.",
            "Saved HTTP originals and latency measurements depend on collector honesty; CAS replay proves consistency.",
        ),
    )
