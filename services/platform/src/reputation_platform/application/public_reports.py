"""Public freeze guards; shared report assembly stays in ReportService."""

import asyncio
from collections.abc import Callable
from typing import TYPE_CHECKING
from uuid import UUID

from reputation_core.evidence import canonical_bytes
from reputation_core.models import EvidenceRecord, Outcome, RecordVerificationResult
from reputation_core.models.public_evaluation import PublicReadonlyVerificationInput
from reputation_core.public_verifier import public_observation, verify_public_readonly

from reputation_platform.adapters.registries.demo import timestamp
from reputation_platform.infrastructure.db.jobs import JobQueue, Lease

from .errors import ApplicationError

if TYPE_CHECKING:
    from .reports import ReportService


def check_public_packets(
    data: PublicReadonlyVerificationInput,
    records: dict[UUID, EvidenceRecord],
    read: Callable[[EvidenceRecord], bytes],
) -> None:
    refs = set((*data.identity_evidence_refs, *data.agent_evidence_refs, *data.business_evidence_refs))
    if len(refs) != sum(len(item) for item in (
        data.identity_evidence_refs, data.agent_evidence_refs, data.business_evidence_refs
    )) or refs != {packet.record.evidence_id for packet in data.packets} or set(
        data.identity_evidence_refs
    ) != set(data.snapshot.evidence_refs):
        raise ApplicationError(409, "MISSING_EVIDENCE", "Public originals are incomplete.")
    for packet in data.packets:
        if records.get(packet.record.evidence_id) != packet.record or read(
            packet.record
        ) != canonical_bytes(packet.body):
            raise ApplicationError(409, "CONTENT_HASH_MISMATCH", "Public packet differs from CAS.")


async def refresh_public_inputs(
    service: "ReportService",
    inputs: tuple[PublicReadonlyVerificationInput, ...],
    results: tuple[RecordVerificationResult, ...],
    evidence_ids: tuple[UUID, ...],
    lease: Lease | None,
    queue: JobQueue | None,
) -> tuple[PublicReadonlyVerificationInput, ...]:
    from .public_verification import PublicReadonlyVerificationService

    if lease is None or queue is None:
        raise ApplicationError(409, "LEASE_REQUIRED", "Public report freezing requires a worker lease.")
    verifier = PublicReadonlyVerificationService(
        service.db, service.identity, client_factory=service.client_factory
    )
    refreshed = []
    for original, stored, evidence_id in zip(inputs, results, evidence_ids, strict=True):
        check_public_packets(
            original, {packet.record.evidence_id: packet.record for packet in original.packets},
            service.read_evidence,
        )
        if verify_public_readonly(original, (evidence_id,)) != stored:
            raise ApplicationError(409, "ASSERTION_REPLAY_MISMATCH", "Stored public assertions differ.")
        if stored.outcome == Outcome.UNKNOWN:
            frozen_at = timestamp()
            if frozen_at < original.observed_at:
                raise ApplicationError(409, "EVIDENCE_INCONSISTENT", "Public input has a future timestamp.")
            if frozen_at == original.observed_at:
                # CAS dedup must retain a distinct freeze document without upgrading missing evidence.
                await asyncio.sleep(0.001)
                frozen_at = timestamp()
            fresh = original.model_copy(update={"observed_at": frozen_at})
        else:
            fresh = await verifier.fresh_input(original, lease=lease, queue=queue)
        if (
            original.model_dump(exclude={"observed_at", "packets", "business_evidence_refs"})
            != fresh.model_dump(exclude={"observed_at", "packets", "business_evidence_refs"})
            or public_observation(original) != public_observation(fresh)
        ):
            raise ApplicationError(409, "EVIDENCE_INCONSISTENT", "Public freeze changed immutable facts.")
        rechecked = verify_public_readonly(fresh, (evidence_id,))
        if (
            [(item.rule_id, item.outcome, item.reason_code, item.critical) for item in stored.assertions]
            != [(item.rule_id, item.outcome, item.reason_code, item.critical)
                for item in rechecked.assertions]
            or stored.task_link != rechecked.task_link
        ):
            raise ApplicationError(409, "STALE_EVIDENCE", "Public chain judgement changed before freeze.")
        refreshed.append(fresh)
    return tuple(refreshed)
