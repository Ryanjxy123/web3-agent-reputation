"""Replay the retained real online bytes; this test makes no external requests."""

import hashlib
from pathlib import Path

from reputation_core.evidence import strict_json

from scripts.akashi_assertions import normalize_proof, verify_proof

EVIDENCE = Path(__file__).resolve().parents[2] / "docs/testing/evidence/akashi-2026-10-11"


def test_published_raw_hashes_and_independent_business_replay():
    observations = strict_json((EVIDENCE / "observations.json").read_bytes())
    publication = strict_json((EVIDENCE / "publication-manifest.json").read_bytes())
    omitted = {item["file"]: item for item in publication["omitted"]}
    by_label = {item["label"]: item for item in observations}
    included = 0
    for item in observations:
        assert item["status"] in (200, 400)
        name = item["body_file"]
        if name in omitted:
            assert item["body_sha256"] == omitted[name]["sha256"]
            continue
        raw = (EVIDENCE / name).read_bytes()
        assert len(raw) == item["body_bytes"]
        assert hashlib.sha256(raw).hexdigest() == item["body_sha256"]
        included += 1
    assert included == publication["raw_bodies_included"]

    def read(label):
        return strict_json((EVIDENCE / by_label[label]["body_file"]).read_bytes())

    evidence = {
        "chain_id": read("chain-id")["result"], "head": read("chain-head")["result"],
        "tx": read("positive-tx")["result"], "receipt": read("positive-receipt")["result"],
        "receipt_block": read("receipt-block")["result"],
        "canonical_block": read("canonical-block")["result"],
    }
    tx_hash = evidence["tx"]["hash"]
    normalized = [normalize_proof(read(f"positive-http-{index}")) for index in (1, 2, 3)]
    assert normalized[0] == normalized[1] == normalized[2]
    assert normalize_proof(read("positive-mcp")["result"], mcp=True) == normalized[0]
    for proof in normalized:
        result = verify_proof(proof, {"tx": tx_hash}, evidence)
        assert result["status"] == "PASS"
        assert result["confirmed_proofs"][0]["hash"] == "be44340d151cbfa7a5dc59b579dd6632fb0891b573f8fdc927264309a3b168f0"
        assert result["confirmed_proofs"][0]["contract"] == "0xeed9d0f7265892e84e43d05da464c75add199260"
    random = normalize_proof(read("random-hash"))
    assert random["anchored"] is False and random["unsearched"]
    assert verify_proof(random, {"hash": random["hash"]}, evidence)["status"] == "UNKNOWN"
    assert by_label["invalid-hash"]["status"] == 400
    assert "error" in read("invalid-hash")
