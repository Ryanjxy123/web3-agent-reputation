import pytest
from reputation_core.evidence import hash_bytes, strict_json
from reputation_platform.infrastructure.evidence_store import EvidenceStore


def test_redacted_saved_bytes_are_the_hash_input_and_tampering_is_detected(tmp_path):
    store = EvidenceStore(tmp_path)
    document = {
        "Authorization": "Bearer never-persist-this",
        "nested": [{"private_key": "not-a-real-key", "public": 1}],
    }
    record = store.prepare_json(document, "test", "2026-10-02T12:00:00.000Z", "test")
    stored = store.read(record)
    assert b"never-persist-this" not in stored and b"not-a-real-key" not in stored
    assert strict_json(stored)["nested"][0] == {"private_key": "[REDACTED]", "public": 1}
    assert record.blob_hash == hash_bytes(stored)
    again = store.prepare_json(document, "test", "2026-10-02T12:00:00.000Z", "test")
    assert again.blob_hash == record.blob_hash
    (tmp_path / record.path).write_bytes(b"modified")
    with pytest.raises(ValueError, match="EVIDENCE_CONTENT_CONFLICT"):
        store.read(record)
    with pytest.raises(ValueError, match="EVIDENCE_CONTENT_CONFLICT"):
        store.prepare_json(document, "test", "2026-10-02T12:00:00.000Z", "test")
    assert (tmp_path / record.path).read_bytes() == b"modified"
    assert not list(tmp_path.rglob("*.tmp"))
