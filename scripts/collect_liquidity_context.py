"""Read registration, token precision, position ownership and factory pool evidence."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import secrets

from collect_liquidity_history import (
    ROOT, Collector, NPM, prepare, request_spec, call_key,
)

CAKE = "0x0e09fabb73bd3ade0a17ecc321fd13a19e81ce82"
WBNB = "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c"
FACTORY = "0x0bfbcf9fa4f9c56b0f40a671ad40e0805a091865"
GET_POOL = "0x1698ee82"
DECIMALS = "0x313ce567"
OWNER_OF = "0x6352211e"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history-run", type=Path, required=True)
    parser.add_argument("--transaction-runs", nargs="+", type=Path, required=True)
    parser.add_argument("--execute-public-readonly", action="store_true")
    parser.add_argument("--proxy")
    parser.add_argument("--zan-key-url-file", type=Path,
                        default=Path("D:/xjtu_project/block_chain_new/runtime/secrets/base-mainnet-rpc-url.txt"))
    args = parser.parse_args()
    if args.execute_public_readonly and not args.proxy:
        parser.error("Execution requires explicit --proxy")
    baseline, cache = prepare(args.history_run, None, args.transaction_runs)
    config = json.loads((ROOT / "configs/pilots/brain-defi-liquidity-v1.json").read_bytes())
    specs = [request_spec("chain-id", "eth_chainId", []),
             request_spec("registration-transaction", "eth_getTransactionByHash", [config["registration_tx_hash"]]),
             request_spec("registration-receipt", "eth_getTransactionReceipt", [config["registration_tx_hash"]])]
    gaps = []
    for task in baseline["tasks"]:
        index = task["history_index"]
        try:
            final_hash = next(tx["hash"] for tx in task["transactions"] if tx["role"] == "increase")
            receipt = cache[call_key("eth_getTransactionReceipt", [final_hash])]["value"]
            block = receipt["blockNumber"]
            if receipt["transactionHash"].lower() != final_hash:
                raise ValueError("wrong retained transaction")
            owner_call = {"to": NPM, "data": OWNER_OF + f"{task['token_id']:064x}"}
            specs.append(request_spec(f"history-{index}-position-owner", "eth_call", [owner_call, block], task))
            if task["purpose"] == "functional":
                for name, token in (("cake", CAKE), ("wbnb", WBNB)):
                    specs.append(request_spec(f"history-{index}-{name}-decimals", "eth_call",
                                              [{"to": token, "data": DECIMALS}, block], task))
            else:
                swap_hash = task["transactions"][1]["hash"]
                swap = cache[call_key("eth_getTransactionByHash", [swap_hash])]["value"]
                swap_receipt = cache[call_key("eth_getTransactionReceipt", [swap_hash])]["value"]
                calldata = swap["input"].lower()
                words = [int(calldata[start:start + 64], 16) for start in range(10, len(calldata), 64)]
                if (len(calldata) != 522 or not calldata.startswith("0x414bf389") or len(words) != 8
                        or words[0] != int(WBNB, 16) or words[1] != int(CAKE, 16) or words[2] != 500
                        or swap["hash"].lower() != swap_hash or swap_receipt["transactionHash"].lower() != swap_hash):
                    raise ValueError("unadapted swap parameters")
                data = GET_POOL + f"{words[0]:064x}{words[1]:064x}{words[2]:064x}"
                specs.append(request_spec(f"history-{index}-factory-pool", "eth_call",
                                          [{"to": FACTORY, "data": data}, swap_receipt["blockNumber"]], task))
        except (KeyError, TypeError, ValueError, IndexError):
            gaps.append({"history_index": index, "reason": "retained_task_or_supported_protocol_context_missing"})
    plan = {
        "measurement": "liquidity-independent-context-only", "execution_enabled": args.execute_public_readonly,
        "policy": baseline["policy"], "pilot_config": baseline["pilot_config"],
        "trusted_rpc_config": baseline["trusted_rpc_config"], "rpc_url": baseline["rpc_url"],
        "inputs": baseline["inputs"], "tasks": baseline["tasks"], "requests": specs, "planning_gaps": gaps,
        "registration_block_request": "Derived from the retained registration receipt and persisted before sending",
        "maximum_new_requests": len(specs) + 1, "retries": 0, "scores_computed": False,
        "protocol_source": "https://developer.pancakeswap.finance/contracts/v3/addresses",
        "identity_source": "https://eips.ethereum.org/EIPS/eip-8004#registration",
        "selector_validation": {"getPool(address,address,uint24)": GET_POOL, "decimals()": DECIMALS,
                                "command": "cast sig <signature>", "exit_code": 0},
        "credential_note": "ZAN private key path segment omitted from all public request addresses",
    }
    print(json.dumps({"requests": len(specs), "planning_gaps": gaps,
                      "execution_enabled": args.execute_public_readonly}, indent=2))
    if not args.execute_public_readonly:
        return 0
    now = datetime.now(timezone.utc)
    run = ROOT / "runtime" / f"liquidity-context-{now:%Y%m%dT%H%M%SZ}-{secrets.token_hex(4)}"
    run.mkdir()
    (run / "manifest.json").write_text(json.dumps({"created_at": now.isoformat(), **plan}, indent=2), encoding="utf-8")
    collector = Collector(run, cache, args.proxy, args.zan_key_url_file, len(specs) + 1)
    results = collector.stage(specs)
    receipt = results.get("registration-receipt")
    if isinstance(receipt, dict) and not collector.stop:
        header_spec = request_spec("registration-block", "eth_getBlockByNumber", [receipt["blockNumber"], False])
        results.update(collector.stage([header_spec]))
    summary = {"new_requests": collector.new_requests, "stopped_reason": collector.stop,
               "planning_gaps": gaps, "requested": len(specs) + 1, "retained": len(results),
               "scores_computed": False}
    with (run / "result.json").open("x", encoding="utf-8") as stream:
        json.dump(summary, stream, indent=2)
    print(f"evidence_directory={run}; " + json.dumps(summary))
    return 0 if not gaps and not collector.stop and len(results) == len(specs) + 1 else 1


if __name__ == "__main__":
    raise SystemExit(main())
