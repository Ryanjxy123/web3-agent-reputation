"""Offline Akashi transport replay into real PostgreSQL and immutable CAS evidence."""

import hashlib
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from reputation_core.akashi import normalize_proof
from reputation_core.evidence import canonical_bytes, strict_json
from reputation_platform.adapters.akashi import PROTOCOLS, AkashiReadonlyAdapter
from reputation_platform.infrastructure.db.tables import audit_logs, evidence_blobs, metadata
from reputation_platform.infrastructure.evidence_store import EvidenceStore
from reputation_platform.infrastructure.network.safe_http import NetworkPolicyError, SafeHttpClient
from sqlalchemy import func, insert, inspect, select, update
from sqlalchemy.exc import DBAPIError

EVIDENCE = Path(__file__).resolve().parents[2] / "docs/testing/evidence/akashi-2026-10-11"
pytestmark = pytest.mark.postgres


@pytest.mark.parametrize("protocol", PROTOCOLS)
async def test_adapter_evidence_registers_in_existing_schema_and_rejects_tampering(
    db, tmp_path, monkeypatch, protocol
):
    observations = strict_json((EVIDENCE / "observations.json").read_bytes())
    captured = {item["label"]: item for item in observations}

    def raw(label):
        return (EVIDENCE / captured[label]["body_file"]).read_bytes()

    proof = strict_json(raw("positive-http-1"))
    requests = []
    returned_bodies = []

    def replay(request):
        requests.append(request)
        if request.method == "GET":
            body = raw("positive-http-1")
        else:
            payload = strict_json(request.content)
            if payload["method"] == "notifications/initialized":
                return httpx.Response(202)
            label = {
                "initialize": "mcp-initialize",
                "tools/list": "mcp-tools",
                "tools/call": "positive-mcp",
            }[payload["method"]]
            envelope = strict_json(raw(label))
            envelope["id"] = payload["id"]
            body = canonical_bytes(envelope)
        returned_bodies.append(body)
        return httpx.Response(200, content=body, headers={"content-type": "application/json"})

    # Only this deterministic transport runs at zero interval; production keeps the fixed quota.
    monkeypatch.setattr(
        "reputation_platform.infrastructure.network.safe_http.PUBLIC_REQUEST_INTERVAL", 0
    )
    client = SafeHttpClient.public_readonly(
        enabled=True, transport=httpx.MockTransport(replay), resolver=lambda host: ["8.8.8.8"]
    )
    store = EvidenceStore(tmp_path)
    adapter = AkashiReadonlyAdapter(protocol, client, store)
    try:
        result = await adapter.query({"tx": proof["tx"]}, uuid4())
    finally:
        await client.close()
    assert len(requests) == (1 if protocol == PROTOCOLS[0] else 4)
    assert result.observation.accepted and result.observation.reason_code is None
    assert result.normalized == normalize_proof(proof)
    assert result.observation.candidate_tx_hash is None

    with db.begin() as connection:
        saved = result.registered(connection, store)
        connection.execute(insert(audit_logs).values(
            actor="test-offline-replay", action="public-readonly-evidence",
            target=saved.observation.slot_id,
            body={"observation": saved.observation.model_dump(mode="json")},
        ))
        fresh_records = tuple(
            record.model_copy(update={"evidence_id": uuid4()}) for record in result.evidence
        )
        duplicate = replace(result, evidence=fresh_records).registered(connection, store)
    assert set(record.evidence_id for record in fresh_records).isdisjoint(
        saved.observation.evidence_refs
    )
    assert saved.observation.evidence_refs == duplicate.observation.evidence_refs
    assert saved.observation.evidence_refs == tuple(record.evidence_id for record in saved.evidence)
    with db.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(evidence_blobs)) == len(
            saved.evidence
        )
        audit = connection.execute(select(audit_logs.c.body)).scalar_one()
        assert audit["observation"]["evidence_refs"] == [
            str(record.evidence_id) for record in saved.evidence
        ]
    assert set(inspect(db).get_table_names()) == set(metadata.tables) | {"alembic_version"}

    last_response = strict_json(store.read(saved.evidence[-1]))["response"]
    assert last_response["raw_body_retained"] is True
    assert last_response["raw_body_utf8"].encode() == returned_bodies[-1]
    assert last_response["body_sha256"] == hashlib.sha256(returned_bodies[-1]).hexdigest()
    assert last_response["audit"]["resolved_ips"] == ["8.8.8.8"]

    for statement in (
        update(evidence_blobs).values(body={"changed": True}),
        evidence_blobs.delete(),
        update(audit_logs).values(body={"changed": True}),
        audit_logs.delete(),
    ):
        with pytest.raises(DBAPIError), db.begin() as connection:
            connection.execute(statement)
    (tmp_path / saved.evidence[-1].path).write_bytes(b"changed")
    with pytest.raises(ValueError, match="EVIDENCE_CONTENT_CONFLICT"):
        store.read(saved.evidence[-1])


async def test_payment_stop_evidence_is_preserved_without_payment_body(db, tmp_path):
    requests = []
    client = SafeHttpClient.public_readonly(
        enabled=True, resolver=lambda host: ["8.8.8.8"],
        transport=httpx.MockTransport(lambda request: requests.append(request) or httpx.Response(
            402, json={"authorization": "never-persist-this", "paymentRequired": True}
        )),
    )
    store = EvidenceStore(tmp_path)
    adapter = AkashiReadonlyAdapter(PROTOCOLS[0], client, store)
    try:
        result = await adapter.query({"tx": "0x" + "ab" * 32}, uuid4())
        assert not result.observation.accepted and result.normalized is None
        with pytest.raises(NetworkPolicyError, match="PUBLIC_ADAPTER_STOPPED"):
            await adapter.query({"tx": "0x" + "ab" * 32}, uuid4())
    finally:
        await client.close()
    with db.begin() as connection:
        saved = result.registered(connection, store)
    response = strict_json(store.read(saved.evidence[-1]))["response"]
    assert response["status"] == 402
    assert response["audit"]["body_not_read"] and response["audit"]["payment_required"]
    assert response["raw_body_utf8"] is None and response["body_sha256"] is None
    assert len(requests) == 1
    assert all(b"never-persist-this" not in store.read(record) for record in saved.evidence)
