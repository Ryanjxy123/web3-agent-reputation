"""One bounded Gnosis Mech directory read; discovery is not reputation scoring."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import secrets
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "packages/core/src"), str(ROOT / "services/platform/src")]

from reputation_core import MeasurementPurpose
from reputation_platform.safe_http import PublicTarget, SafeHttpClient

ENDPOINT = "https://api.subgraph.autonolas.tech/api/proxy/marketplace-gnosis"
FIRST = 40
# Field names and ordering match official mech-client query_mechs; add a server-side bound.
QUERY = """query MechsOrderedByServiceDeliveries {
  meches(first: 40, orderBy: totalDeliveriesTransactions, orderDirection: desc) {
    id
    address
    mechFactory
    totalDeliveriesTransactions
    service {
      id
      totalDeliveries
      metadata { metadata }
    }
  }
}"""
SOURCES = [
    {"url": "https://github.com/valory-xyz/mech-client/blob/main/mech_client/infrastructure/subgraph/client.py",
     "github_blob_sha": "5658cc5055e7e24a27fba6cb9e0952c967186c42"},
    {"url": "https://github.com/valory-xyz/mech-client/blob/main/mech_client/infrastructure/subgraph/queries.py",
     "github_blob_sha": "07373e1f81d2347b61f8ef343a5ca83bf7ce0a2e"},
    {"url": "https://github.com/valory-xyz/mech-client/blob/main/mech_client/configs/mechs.json",
     "github_blob_sha": "b08a07da0122f0100010c987f1b7c7aeda82c6e7"},
]
FACTORIES = {
    "0x8b299c20f87e3fcbff0e1b86dc0acc06ab6993ef": "Fixed Price Native",
    "0x31ffdc795fdf36696b8edf7583a3d115995a45fa": "Fixed Price Token",
    "0x65fd74c29463afe08c879a3020323dd7df02da57": "NvmSubscription Native",
}


def write_json(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)


def address(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"0x[0-9a-fA-F]{40}", value):
        raise ValueError("Missing or malformed public contract address")
    return value.lower()


def count(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, (str, int)) or not re.fullmatch(r"[0-9]+", str(value)):
        raise ValueError("Missing or malformed directory integer")
    return int(value)


def summarize(rows: list) -> dict:
    services, gaps, seen = {}, [], set()
    for index, row in enumerate(rows):
        try:
            contract = address(row["address"])
            if contract in seen:
                raise ValueError("Duplicate Mech address in directory response")
            service = row["service"]
            service_id = str(count(service["id"]))
            factory = address(row["mechFactory"])
            mech = {"address": contract, "directory_id": str(row["id"]), "factory": factory,
                    "factory_type_hint": FACTORIES.get(factory, "not_mapped_by_reviewed_client"),
                    "deliveries_transactions": str(count(row["totalDeliveriesTransactions"]))}
            metadata = service.get("metadata") or []
            hashes = [item["metadata"] for item in metadata
                      if isinstance(item, dict) and isinstance(item.get("metadata"), str)]
            group = services.setdefault(service_id, {"chain_id": 100, "olas_service_id": service_id,
                "indexed_service_total_deliveries": str(count(service["totalDeliveries"])),
                "metadata_hashes": [], "mechs": [], "erc8004_agent_id": None,
                "erc8004_mapping": "NOT_CHECKED", "onchain_registration_verified": False})
            group["mechs"].append(mech)
            group["metadata_hashes"] = list(dict.fromkeys(group["metadata_hashes"] + hashes))
            seen.add(contract)
        except (KeyError, TypeError, ValueError) as error:
            gaps.append({"row_index_zero_based": index, "reason": str(error)})
    grouped = list(services.values())
    active = [group for group in grouped if any(int(mech["deliveries_transactions"]) > 0 for mech in group["mechs"])]
    return {"raw_rows": len(rows), "distinct_mech_contracts": len(seen),
        "distinct_services": len(grouped), "services_with_indexed_deliveries": len(active),
        "nine_distinct_active_services_found": len(active) >= 9, "services": grouped, "data_gaps": gaps}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute-public-readonly", action="store_true")
    parser.add_argument("--proxy", help="Explicit operator HTTP proxy required for the single read")
    args = parser.parse_args()
    if args.execute_public_readonly and not args.proxy:
        parser.error("Execution requires an explicit --proxy")
    manifest = {"measurement": "olas-directory-discovery-only", "chain_id_hint": 100,
        "execution_enabled": args.execute_public_readonly, "endpoint": ENDPOINT,
        "method": "POST", "request_json": {"query": QUERY}, "first": FIRST,
        "request_limit": 1, "retries": 0, "node_failover": False, "scores_computed": False,
        "source_review": SOURCES, "query_sha256": hashlib.sha256(QUERY.encode()).hexdigest(),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "limits": ["Directory counters are discovery signals, not reliability scores.",
            "Different Mechs of one Olas service are grouped, not counted as independent agents.",
            "Olas service IDs are not ERC-8004 agent IDs; registry bridge and chain proofs are not queried.",
            "No new prediction request, IPFS download, model call, RPC, payment or signature."]}
    if not args.execute_public_readonly:
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return 0
    now = datetime.now(timezone.utc)
    directory = ROOT / "runtime" / f"olas-discovery-{now:%Y%m%dT%H%M%SZ}-{secrets.token_hex(4)}"
    directory.mkdir()
    write_json(directory / "manifest.json", {"created_at": now.isoformat(), **manifest})
    target = PublicTarget("olas-mech-directory", ENDPOINT, "POST", MeasurementPurpose.BACKGROUND, {"query": QUERY})
    with SafeHttpClient((target,), enabled=True, proxy=args.proxy, max_requests=1,
                        max_body_bytes=1_048_576, timeout_seconds=30) as client:
        observation = client.fetch(target.key, directory)
    result = {"status": "BLOCKED", "requests_observed": 1, "scores_computed": False}
    try:
        if observation.http_status != 200 or not observation.body_complete or observation.error_kind:
            raise ValueError(f"Directory read unavailable: HTTP={observation.http_status}, error={observation.error_kind}")
        payload = json.loads((directory / observation.response_file).read_bytes())
        if payload.get("errors"):
            raise ValueError("GraphQL returned errors; inspect retained response without retrying")
        rows = payload["data"]["meches"]
        if not isinstance(rows, list) or len(rows) > FIRST:
            raise ValueError("Directory rows do not match the fixed bounded query")
        result.update(status="DISCOVERY_RETAINED", **summarize(rows))
    except (KeyError, TypeError, ValueError) as error:
        result["reason"] = str(error)
    write_json(directory / "result.json", result)
    print(json.dumps({"evidence_directory": str(directory.relative_to(ROOT)),
                     **{key: value for key, value in result.items() if key != "services"}}, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "DISCOVERY_RETAINED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
