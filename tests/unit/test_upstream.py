import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_upstream_bytes_match_provenance_and_external_access_stays_disabled():
    lock = json.loads((ROOT / "configs/upstream-lock.json").read_text(encoding="utf-8"))
    assert not lock["usable"] and not lock["external_enabled"]
    assert len(lock["erc8004"]["commit"]) == 40
    for item in lock["files"]:
        if item["status"] == "PINNED":
            data = (ROOT / item["path"]).read_bytes()
            assert len(data) == item["bytes"]
            assert hashlib.sha256(data).hexdigest() == item["sha256"]
        else:
            assert item["status"] == "BLOCKED_DOWNLOAD"
            assert "sha256" not in item
    abi = json.loads((ROOT / "third_party/erc8004/IdentityRegistry.json").read_bytes())
    functions = {entry.get("name") for entry in abi if entry["type"] == "function"}
    assert {"ownerOf", "tokenURI", "getAgentWallet"} <= functions
