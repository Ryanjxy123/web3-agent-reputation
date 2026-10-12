"""Rule 7 replay using committed public originals, never a bundle-supplied RPC."""

from typing import Any
from uuid import UUID

from reputation_core.evidence import canonical_bytes, hash_json
from reputation_core.models import (
    AnchorReceipt,
    AssertionResult,
    EvidenceManifest,
    EvidenceRecord,
    Observation,
    ReportCore,
)
from reputation_core.models.public_evaluation import (
    PublicReadonlyRunPlan,
    PublicReadonlyVerificationInput,
)
from reputation_core.public_reporting import build_public_readonly_report
from reputation_core.public_verifier import public_observation, verify_public_readonly

from .bundle import (
    VERIFICATION_LIMITATIONS,
    VerificationError,
    _fail,
    _json,
    _verify_anchor,
    _verify_publication_context,
)


def _packets(
    data: PublicReadonlyVerificationInput,
    records: dict[UUID, EvidenceRecord],
    files: dict[str, bytes],
) -> None:
    role_refs = (*data.identity_evidence_refs, *data.agent_evidence_refs, *data.business_evidence_refs)
    if (
        len(set(role_refs)) != len(role_refs)
        or set(role_refs) != {packet.record.evidence_id for packet in data.packets}
        or set(data.identity_evidence_refs) != set(data.snapshot.evidence_refs)
    ):
        _fail("EVIDENCE_INCONSISTENT", "Public evidence roles do not resolve their exact originals.")
    for packet in data.packets:
        if records.get(packet.record.evidence_id) != packet.record:
            _fail("EVIDENCE_INCONSISTENT", "Public packet record differs from the manifest.")
        if files.get(packet.record.path) != canonical_bytes(packet.body):
            _fail("CONTENT_HASH_MISMATCH", "Public packet differs from committed CAS bytes.")
        if packet.record.observed_at > data.observed_at:
            _fail("EVIDENCE_INCONSISTENT", "Public original was captured after its replay input.")


def verify_public_bundle(
    core_data: dict[str, Any],
    manifest: EvidenceManifest,
    receipt: AnchorReceipt,
    aliases: dict[str, bytes],
    files: dict[str, bytes],
    *,
    report_hash: str,
    manifest_hash: str,
    rpc_url: str | None,
) -> dict[str, Any]:
    try:
        if core_data.get("schema_version") != "1.6.0":
            _fail("RULE_VERSION_MISMATCH", "Public evidence requires report schema 1.6.0.")
        plan = PublicReadonlyRunPlan.model_validate(_json(aliases, "run_plan.json"))
        core = ReportCore.model_validate(core_data)
        if hash_json(core.model_dump(mode="json")) != report_hash:
            _fail("CONTENT_HASH_MISMATCH", "Public report is not in canonical wire form.")
        if manifest.publication.chain.chain_id != "31337":
            _fail("EVIDENCE_INCONSISTENT", "Public business evidence and local publication disagree.")
        index = _json(aliases, "verification.json")
        if not isinstance(index, dict) or set(index) != {"schema_version", "tasks"} or (
            index.get("schema_version") != "public-readonly-replay-v1"
        ):
            _fail("RULE_VERSION_MISMATCH", "Public evidence requires its own replay index.")
        rows = index.get("tasks")
        if not isinstance(rows, list) or len(rows) != len(plan.slots):
            _fail("REPLAY_MISMATCH", "Public replay index does not cover the plan.")
        records = {item.evidence_id: item for item in manifest.evidence}
        by_slot = {}
        used_ids: set[UUID] = set()
        for row in rows:
            if not isinstance(row, dict) or set(row) != {
                "slot_id", "input_evidence_id", "freeze_evidence_id"
            }:
                _fail("REPLAY_MISMATCH", "Public task reference contains unexpected fields.")
            slot_id, input_id, freeze_id = (UUID(row[key]) for key in (
                "slot_id", "input_evidence_id", "freeze_evidence_id"
            ))
            if slot_id in by_slot or input_id == freeze_id or used_ids & {input_id, freeze_id}:
                _fail("REPLAY_MISMATCH", "Public replay index reuses a task or input.")
            if input_id not in records or freeze_id not in records:
                _fail("MISSING_EVIDENCE", "Public task input is absent from the manifest.")
            original_record, frozen_record = records[input_id], records[freeze_id]
            if (original_record.source != "public-readonly-verification-input"
                    or frozen_record.source != "report-freeze-public-readonly-input"):
                _fail("EVIDENCE_INCONSISTENT", "Public task references have unexpected sources.")
            original = PublicReadonlyVerificationInput.model_validate_json(files[original_record.path])
            frozen = PublicReadonlyVerificationInput.model_validate_json(files[frozen_record.path])
            _packets(original, records, files)
            _packets(frozen, records, files)
            if not original.observed_at <= frozen.observed_at <= core.evaluated_at:
                _fail("EVIDENCE_INCONSISTENT", "Public freeze time is outside the report interval.")
            mutable = {"observed_at", "packets", "business_evidence_refs"}
            if original.model_dump(exclude=mutable) != frozen.model_dump(exclude=mutable):
                _fail("EVIDENCE_INCONSISTENT", "Public freeze changed facts outside business reads.")
            unchanged = set((*original.identity_evidence_refs, *original.agent_evidence_refs))
            original_packets = {packet.record.evidence_id: packet for packet in original.packets}
            frozen_packets = {packet.record.evidence_id: packet for packet in frozen.packets}
            if any(original_packets[identifier] != frozen_packets.get(identifier)
                   for identifier in unchanged):
                _fail("EVIDENCE_INCONSISTENT", "Public freeze changed identity or Agent originals.")
            result = verify_public_readonly(original, (input_id,))
            rechecked = verify_public_readonly(frozen, (input_id,))
            if (
                [(item.rule_id, item.outcome, item.reason_code, item.critical)
                 for item in result.assertions]
                != [(item.rule_id, item.outcome, item.reason_code, item.critical)
                    for item in rechecked.assertions]
                or result.task_link != rechecked.task_link
            ):
                _fail("EVIDENCE_INCONSISTENT", "Public freeze changes the original judgement.")
            by_slot[slot_id] = (original, input_id, result)
            used_ids.update((input_id, freeze_id))
        if set(by_slot) != {slot.slot_id for slot in plan.slots}:
            _fail("REPLAY_MISMATCH", "Public index contains missing or unplanned tasks.")
        entries = [by_slot[slot.slot_id] for slot in plan.slots]
        inputs = tuple(entry[0] for entry in entries)
        input_ids = tuple(entry[1] for entry in entries)
        _verify_publication_context(
            manifest, receipt, core, (data.platform_instance_id for data in inputs)
        )
        results = tuple(entry[2] for entry in entries)
        for slot, data in zip(plan.slots, inputs, strict=True):
            if data.slot != slot:
                _fail("EVIDENCE_INCONSISTENT", "Public input differs from its planned slot.")
            if (data.snapshot.core.model_dump(mode="json") != _json(aliases, "snapshot_core.json")
                    or data.snapshot.model_dump(mode="json") != _json(aliases, "public_snapshot.json")
                    or data.review.model_dump(mode="json") != _json(aliases, "claims_review.json")):
                _fail("EVIDENCE_INCONSISTENT", "Public identity or review document differs from input.")
        grants: dict[str, Any] = {}
        associations: dict[str, Any] = {}
        for data in inputs:
            if data.grant is not None:
                identifier, body = str(data.grant.grant_id), data.grant.model_dump(mode="json")
                if identifier in grants and grants[identifier] != body:
                    _fail("EVIDENCE_INCONSISTENT", "Shared public grant has inconsistent content.")
                grants[identifier] = body
            identifier, body = data.association.protocol, data.association.model_dump(mode="json")
            if identifier in associations and associations[identifier] != body:
                _fail("EVIDENCE_INCONSISTENT", "Shared endpoint association has inconsistent content.")
            associations[identifier] = body
        if (
            _json(aliases, "bindings.json") != []
            or _json(aliases, "access_grants.json") != list(grants.values())
            or _json(aliases, "readonly_associations.json") != list(associations.values())
        ):
            _fail("EVIDENCE_INCONSISTENT", "Public authorization or association documents differ.")
        observations = tuple(Observation.model_validate(item)
                             for item in _json(aliases, "observations.json"))
        if len(observations) != len(inputs) or len({item.slot_id for item in observations}) != len(inputs):
            _fail("EVIDENCE_INCONSISTENT", "Public observations do not cover each slot once.")
        observations_by_slot = {item.slot_id: item for item in observations}
        for data in inputs:
            if public_observation(data) != observations_by_slot.get(data.slot.slot_id):
                _fail("EVIDENCE_INCONSISTENT", "Public observation differs from its committed original.")
        referenced = {*plan.planning_evidence_refs}
        for data in inputs:
            referenced.update(data.review.mapping_evidence_ids)
        for observation in observations:
            referenced.update(observation.evidence_refs)
        if not referenced.issubset(records):
            _fail("MISSING_EVIDENCE", "Public context references evidence absent from the manifest.")
        assertions = tuple(sorted((item for result in results for item in result.assertions),
                                  key=lambda item: str(item.assertion_id)))
        frozen_assertions = tuple(AssertionResult.model_validate(item)
                                  for item in _json(aliases, "assertions.json"))
        if assertions != frozen_assertions or assertions != core.assertions:
            _fail("REPLAY_MISMATCH", "Public assertions differ from original evidence replay.")
        rebuilt = build_public_readonly_report(
            plan, inputs, input_ids, observations, _json(aliases, "policy.json"),
            evaluated_at=core.evaluated_at, code_version=core.code_version,
            manifest_hash=manifest_hash, previous_report_hash=core.previous_report_hash,
        )
        if rebuilt != core:
            _fail("REPLAY_MISMATCH", "Public statistics, risk or scores differ from replay.")
    except VerificationError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise VerificationError("REPLAY_MISMATCH", "Public bundle cannot replay its originals.") from exc
    anchor = _verify_anchor(rpc_url or "", manifest, receipt, report_hash, core)
    return {
        "status": "PASS", "offline": "PASS", "report_hash": report_hash,
        "limitations": list(VERIFICATION_LIMITATIONS),
        "task_results": [{
            "slot_id": str(data.slot.slot_id), "capability_id": "verify_record",
            "outcome": result.outcome, "reason_code": result.reason_code, "rule_version": "7",
            "live_chain": {"status": "NOT_CHECKED", "reason": "public chain replay is offline"},
        } for data, result in zip(inputs, results, strict=True)],
        "task_counts": core.task_counts.model_dump(mode="json") if core.task_counts else {},
        "task_count_comparison": "MATCH", "assessment_comparison": "MATCH",
        "evidence_sufficiency": core.evidence_sufficiency.model_dump(mode="json")
        if core.evidence_sufficiency else None,
        "risk_assessment": core.risk_assessment.model_dump(mode="json")
        if core.risk_assessment else None,
        "publication": "LOCAL_ANVIL",
        "publication_status": "UNANCHORED" if receipt.status == "NOT_REQUESTED" else receipt.status,
        "anchor": anchor,
    }
