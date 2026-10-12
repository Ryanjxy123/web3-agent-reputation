"""Redact JSON first, then durably save and register immutable content-addressed bytes."""

import os
from pathlib import Path
from uuid import uuid4

from reputation_core.evidence import canonical_bytes, hash_bytes
from reputation_core.models import EvidenceRecord
from reputation_core.public_identity import contains_sensitive_text
from sqlalchemy import Connection, select
from sqlalchemy.dialects.postgresql import insert

from .db.tables import evidence_blobs

SECRET_FIELDS = {
    "authorization",
    "cookie",
    "set-cookie",
    "x-api-key",
    "api_key",
    "apikey",
    "token",
    "access_token",
    "password",
    "secret",
    "private_key",
    "mnemonic",
    "signed_raw",
    "signed_transaction",
}


def redact(value):
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if key.lower() in SECRET_FIELDS else redact(child)
            for key, child in value.items()
            if not contains_sensitive_text(key)
        }
    if isinstance(value, list):
        return [redact(child) for child in value]
    if isinstance(value, str) and contains_sensitive_text(value):
        return "[REDACTED]"
    return value


class EvidenceStore:
    def __init__(self, root: Path):
        self.root = root

    def prepare_json(
        self, value: object, source: str, observed_at: str, trust_group: str
    ) -> EvidenceRecord:
        data = canonical_bytes(redact(value))
        digest = hash_bytes(data)
        record = EvidenceRecord(
            evidence_id=uuid4(),
            path=f"blobs/{digest[2:]}.bin",
            blob_hash=digest,
            byte_count=len(data),
            media_type="application/json",
            source=source,
            observed_at=observed_at,
            collector_version="platform-v1",
            redaction_profile="credentials-v1",
            trust_group=trust_group,
        )
        target = self.root / record.path
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{uuid4().hex}.tmp")
        try:
            with temporary.open("xb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                # Link is atomic and cannot overwrite an existing content-addressed file.
                os.link(temporary, target)
            except FileExistsError:
                if target.read_bytes() != data:
                    raise ValueError("EVIDENCE_CONTENT_CONFLICT") from None
        finally:
            temporary.unlink(missing_ok=True)
        return record

    def register(self, connection: Connection, record: EvidenceRecord) -> EvidenceRecord:
        saved = connection.execute(
            insert(evidence_blobs)
            .values(
                id=record.evidence_id,
                blob_hash=record.blob_hash,
                path=record.path,
                byte_count=record.byte_count,
                body=record.model_dump(mode="json"),
            )
            .on_conflict_do_nothing(index_elements=["blob_hash"])
            .returning(evidence_blobs.c.body)
        ).scalar_one_or_none()
        if saved is None:
            saved = connection.execute(
                select(evidence_blobs.c.body).where(evidence_blobs.c.blob_hash == record.blob_hash)
            ).scalar_one()
        return EvidenceRecord.model_validate(saved)

    def read(self, record: EvidenceRecord) -> bytes:
        data = (self.root / record.path).read_bytes()
        if len(data) != record.byte_count or hash_bytes(data) != record.blob_hash:
            raise ValueError("EVIDENCE_CONTENT_CONFLICT")
        return data
