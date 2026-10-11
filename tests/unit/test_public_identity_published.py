"""Recompute published live identity commitments from saved, immutable RPC bytes."""

import hashlib
from pathlib import Path

from eth_abi import decode, encode
from reputation_core.evidence import hash_bytes, hash_json, strict_json
from reputation_core.models import AgentSnapshot, EvidenceRecord, Outcome
from reputation_core.public_identity import associate_readonly_identity

SAVED = Path(__file__).resolve().parents[2] / "docs/testing/evidence/akashi-identity-2026-10-11"


def test_real_public_identity_bytes_recompute_registration_and_both_endpoints():
    acceptance = strict_json((SAVED / "acceptance.json").read_bytes())
    snapshot = AgentSnapshot.model_validate(acceptance["snapshot"])
    records = tuple(EvidenceRecord.model_validate(value) for value in acceptance["evidence"])
    assert len(records) == 20
    read = snapshot.public_identity
    assert read is not None and read.source_hashes == tuple(record.blob_hash for record in records)
    assert snapshot.snapshot_hash == hash_json({"core": snapshot.core.model_dump(mode="json"),
                                               "public_identity": read.model_dump(mode="json")})
    calls = []
    metadata_raw = openapi_raw = None
    for record in records:
        raw = (SAVED / record.path).read_bytes()
        assert hash_bytes(raw) == record.blob_hash and len(raw) == record.byte_count
        value = strict_json(raw)
        if "response" not in value:
            continue
        response = value["response"]
        body = response["raw_body_utf8"].encode()
        assert hashlib.sha256(body).hexdigest() == response["body_sha256"]
        assert strict_json(body) == response["json"] and response["status"] == 200
        assert not response["audit"]["payment_required"]
        if value["origin"] == "https://mainnet.base.org":
            payload = value["request_json"]
            result = response["json"]["result"]
            assert response["json"]["id"] == payload["id"]
            if payload["method"] in {"eth_getCode", "eth_call"}:
                assert payload["params"][-1] == hex(int(snapshot.core.read_block_number))
            if payload["method"] == "eth_chainId":
                assert str(int(result, 16)) == snapshot.core.agent_ref.chain_id
            elif payload["method"] == "eth_getCode":
                assert hash_bytes(bytes.fromhex(result[2:])) == read.registry_code_hash
            elif payload["method"] == "eth_call":
                type_name = "address" if payload["params"][0]["data"].startswith("0x6352211e") else "string"
                decoded = decode([type_name], bytes.fromhex(result[2:]))[0]
                assert encode([type_name], [decoded]).hex() == result[2:]
                assert decoded.lower() == snapshot.core.owner if type_name == "address" else decoded == snapshot.core.agent_uri
                calls.append(type_name)
            elif payload["method"] == "eth_getBlockByNumber" and payload["params"][0] != "0x0":
                assert result["hash"] == snapshot.core.read_block_hash
                assert str(int(result["number"], 16)) == snapshot.core.read_block_number
        elif value["path"].endswith("agent-registration.json"):
            metadata_raw = body
        elif value["path"] == "/openapi.json":
            openapi_raw = body
    assert calls == ["address", "string"] and metadata_raw is not None and openapi_raw is not None
    for saved in acceptance["associations"]:
        result = associate_readonly_identity(snapshot, saved["target_url"], saved["protocol"],
                                             metadata_raw=metadata_raw, openapi_raw=openapi_raw)
        assert result.model_dump(mode="json") == saved
        assert result.registration_outcome == result.endpoint_outcome == Outcome.PASS
        assert result.executor_outcome == result.business_outcome == Outcome.UNKNOWN
