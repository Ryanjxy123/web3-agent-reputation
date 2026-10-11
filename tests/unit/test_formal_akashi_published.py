"""Recheck actual task8 responses offline; this is neither a live call nor a score."""

import base64
import hashlib
import importlib.util
from pathlib import Path

from reputation_core.akashi import normalize_proof
from reputation_core.evidence import strict_json
from reputation_core.models import EvidenceRecord
from reputation_platform.infrastructure.evidence_store import EvidenceStore
from reputation_platform.infrastructure.network.safe_http import (
    HttpObservation,
    _public_addresses,
    _readonly_request_allowed,
    decode_public_json,
)

ROOT = Path(__file__).resolve().parents[2] / "docs/testing/evidence/akashi-formal-2026-10-11"


def test_real_formal_adapter_records_are_immutable_readonly_and_replayable():
    saved = strict_json((ROOT / "acceptance.json").read_bytes())
    assert saved["scope"] == "task8-formal-adapter-only"
    assert saved["identity_verified"] is False and saved["business_verified"] is False
    results = saved["results"]
    assert [r["observation"]["http_status"] for r in results] == [200, 200, 200, 400, 200]
    assert results[0]["normalized"] == results[1]["normalized"] == results[4]["normalized"]
    store, responses = EvidenceStore(ROOT), []
    for result in results:
        assert result["capability"] == "verify_record"
        assert result["observation"]["candidate_tx_hash"] is None
        assert result["observation"]["evidence_refs"] == [r["evidence_id"] for r in result["evidence"]]
        for record in result["evidence"]:
            value = strict_json(store.read(EvidenceRecord.model_validate(record)))
            assert value["capability_id"] == "verify_record"
            assert _readonly_request_allowed(
                value["method"], value["origin"], value["path"], value["request_json"]
            )
            if "response" not in value:
                continue
            response = value["response"]
            responses.append(response)
            assert not response["audit"]["payment_required"]
            _public_addresses(response["audit"]["resolved_ips"])
            if not response["raw_body_retained"]:
                assert response["status"] == 202 and response["body_bytes"] == 0
                continue
            raw = response["raw_body_utf8"].encode()
            assert len(raw) == response["body_bytes"]
            assert hashlib.sha256(raw).hexdigest() == response["body_sha256"]
            parsed = decode_public_json(HttpObservation(response["status"], raw, response["content_type"]))
            if value["path"].startswith("/proof?tx="):
                assert normalize_proof(parsed) == result["normalized"]
            elif value["request_json"] and value["request_json"]["method"] == "tools/call":
                assert normalize_proof(parsed["result"], mcp=True) == result["normalized"]
    assert len(responses) == 8
    assert [r["audit"]["sequence"] for r in responses] == list(range(1, 9))


def test_operator_dns_evidence_preserves_tls_and_answer_bytes():
    spec = importlib.util.spec_from_file_location("operator_dns", ROOT / "operator_dns.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    records = list((ROOT / "dns").glob("*.json"))
    assert len(records) == 8
    for file in records:
        dns = strict_json(file.read_bytes())
        assert dns["resolver_ip"] == "8.8.8.8" and dns["tls_server_name"] == "dns.google"
        assert dns["tls_verified"] is True and dns["dnssec_verified"] is False
        assert [query["query_type"] for query in dns["queries"]] == [1, 28]
        assert all(query["response_wire_base64"] for query in dns["queries"])
        decoded = []
        for query in dns["queries"]:
            request = base64.b64decode(query["query_wire_base64"], validate=True)
            response = base64.b64decode(query["response_wire_base64"], validate=True)
            addresses, records = module.decode_answer(
                response, int.from_bytes(request[:2], "big"), query["query_type"]
            )
            assert records == query["records"]
            decoded.extend(addresses)
        assert sorted(set(decoded)) == dns["resolved_ips"]
        _public_addresses(dns["resolved_ips"])
