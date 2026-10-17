"""Plan or explicitly execute up to ten fixed BSC public read-only requests."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import secrets
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "packages/core/src"), str(ROOT / "services/platform/src")]

from reputation_platform.safe_http import PublicTarget, SafeHttpClient

REGISTRY = "0x8004a169fb4a3325136eb29fa0ceb6d2e539a432"
RPC = "https://bsc-dataseed.bnbchain.org"
WALLET = "0xbFAA69233741924eD5b9d5DAA9B4Bf7B84567F0A"
TX_HASH = re.compile(r"0x[0-9a-fA-F]{64}")


def hashes(value: object, path: str):
    if isinstance(value, dict):
        for key, child in value.items():
            yield from hashes(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from hashes(child, f"{path}[{index}]")
    elif isinstance(value, str) and TX_HASH.fullmatch(value):
        yield path, value


def select_transactions(source: Path) -> tuple[list[dict], list[str]]:
    selected, gaps = [], []
    agent = json.loads((source / "brain-agent.response.bin").read_bytes())
    eligible = [(i, row) for i, row in enumerate(agent["history"])
                if row.get("dry") is False and row.get("ok") is True
                and row.get("wallet", "").lower() == WALLET.lower()]
    for index, row in sorted(eligible, key=lambda pair: pair[1]["at"], reverse=True):
        found = list(hashes(row.get("steps"), f"$.history[{index}].steps"))
        if found:
            path, tx_hash = found[0]
            selected.append({"key": "defi", "tx_hash": tx_hash, "field_path": path,
                             "source_file": "brain-agent.response.bin", "at": row["at"],
                             "expected_execution_wallet": WALLET})
            break
    else:
        gaps.append("No transaction hash in successful non-dry DeFi steps for the expected wallet")
    burns = json.loads((source / "brain-burns.response.bin").read_bytes())
    eligible_burns = [(i, row) for i, row in enumerate(burns) if isinstance(row, dict)
                      and str(row.get("block", "")).isdigit()
                      and isinstance(row.get("burnTx"), str) and TX_HASH.fullmatch(row["burnTx"])]
    if eligible_burns:
        index, row = max(eligible_burns, key=lambda pair: int(pair[1]["block"]))
        selected.append({"key": "burn", "tx_hash": row["burnTx"], "field_path": f"$[{index}].burnTx",
                         "source_file": "brain-burns.response.bin", "reported_block": int(row["block"]),
                         "eligible_records": len(eligible_burns), "total_records": len(burns)})
    else:
        gaps.append("No burn record with a numeric block and valid burnTx hash")
    return selected, gaps


def make_targets(selected: list[dict]) -> tuple[PublicTarget, ...]:
    calls = [("chain-id", "eth_chainId", []), ("head", "eth_blockNumber", []),
             ("snapshot-block", "eth_getBlockByNumber", ["SNAPSHOT", False])]
    for key, selector, token_id in (("owner-defi", "6352211e", 363709),
                                    ("owner-brain", "6352211e", 49467),
                                    ("tokenuri-defi", "c87b56dd", 363709)):
        calls.append((key, "eth_call", [{"to": REGISTRY, "data": "0x" + selector + f"{token_id:064x}"}, "SNAPSHOT"]))
    for transaction in selected:
        calls.extend([(transaction["key"] + "-transaction", "eth_getTransactionByHash", [transaction["tx_hash"]]),
                      (transaction["key"] + "-receipt", "eth_getTransactionReceipt", [transaction["tx_hash"]])])
    return tuple(PublicTarget(key, RPC, "POST", json_body={"jsonrpc": "2.0", "id": i,
                 "method": method, "params": params}) for i, (key, method, params) in enumerate(calls, 1))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-run", required=True, help="Existing run directory inside this repository's runtime")
    parser.add_argument("--execute-public-readonly", action="store_true")
    parser.add_argument("--proxy", help="Required operator-configured proxy for execution")
    args = parser.parse_args()
    if args.execute_public_readonly and not args.proxy:
        parser.error("Execution requires an explicit --proxy")
    source = (ROOT / args.source_run).resolve()
    runtime = (ROOT / "runtime").resolve()
    if not source.is_dir() or source == runtime or not source.is_relative_to(runtime):
        parser.error("--source-run must be an existing directory inside this repository's runtime")
    trusted = json.loads((ROOT / "configs/trusted-rpc.json").read_text(encoding="utf-8"))
    if (trusted["chain_id"], trusted["rpc_url"], trusted["registry"]) != (56, RPC, REGISTRY):
        raise ValueError("Trusted RPC configuration must match the reviewed fixed BSC target")
    selected, gaps = select_transactions(source)
    targets = make_targets(selected)
    plan = {"execution_enabled": args.execute_public_readonly, "chain_id": 56,
            "rpc_url": RPC, "source_directory": str(source.relative_to(ROOT)),
            "request_limit": 10, "planned_count": len(targets), "retries": 0,
            "snapshot_rule": "head - 64", "selected_transactions": selected, "gaps": gaps,
            "planned_requests": [{"key": target.key, "json": target.json_body} for target in targets]}
    print(json.dumps(plan, indent=2))
    if not args.execute_public_readonly:
        return 0
    now = datetime.now(timezone.utc)
    run = ROOT / "runtime" / f"bsc-check-{now:%Y%m%dT%H%M%SZ}-{secrets.token_hex(4)}"
    run.mkdir()
    with (run / "manifest.json").open("x", encoding="utf-8") as stream:
        json.dump({"started_at": now.isoformat(), "measurement": "chain-evidence-only", **plan}, stream, indent=2)
    results, snapshot, stop = [], None, None
    with SafeHttpClient(targets, enabled=True, proxy=args.proxy, max_requests=10) as client:
        for target in targets:
            observation = client.fetch(target.key, run)
            item = {"key": target.key, "http_status": observation.http_status}
            results.append(item)
            if observation.error_kind or not observation.body_complete or not observation.http_status or not 200 <= observation.http_status < 300:
                stop = observation.error_kind or "incomplete_or_unsuccessful_http_response"
                break
            try:
                response = json.loads((run / observation.response_file).read_bytes())
                if (not isinstance(response, dict) or response.get("jsonrpc") != "2.0"
                    or response.get("id") != target.json_body["id"] or "result" not in response or "error" in response):
                    stop = "rpc_error_or_invalid_envelope"
                    break
                value = response["result"]
                if target.key == "chain-id" and int(value, 16) != 56:
                    stop = "unexpected_chain_id"
                    break
                if target.key == "head":
                    head = int(value, 16)
                    if head < 64:
                        stop = "head_below_confirmation_offset"
                        break
                    snapshot = hex(head - 64)
                    for pending in targets:
                        if pending.key == "snapshot-block":
                            pending.json_body["params"][0] = snapshot
                        elif pending.json_body["method"] == "eth_call":
                            pending.json_body["params"][1] = snapshot
                if target.key == "snapshot-block" and (not isinstance(value, dict)
                    or value.get("number") != snapshot or not TX_HASH.fullmatch(value.get("hash", ""))):
                    stop = "invalid_snapshot_block"
                    break
                item["rpc_result_present"] = value is not None
                print(f"{target.key}: HTTP={observation.http_status} rpc=ok result_present={value is not None}")
            except (ValueError, TypeError):
                stop = "invalid_rpc_response"
                break
    with (run / "result.json").open("x", encoding="utf-8") as stream:
        json.dump({"snapshot_block": snapshot, "requests_observed": len(results),
                   "stopped_reason": stop, "results": results, "scores_computed": False}, stream, indent=2)
    print(f"evidence_directory={run}; stopped_reason={stop}")
    return 1 if stop else 0


if __name__ == "__main__":
    raise SystemExit(main())
