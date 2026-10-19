"""Plan four fixed BSC historical reads; execute only with explicit flags."""

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

from reputation_platform.safe_http import PublicTarget, SafeHttpClient
from reputation_platform.settings import load_zan_key_file

RPC_PROVIDERS = {
    "bnb-official": ("trusted-rpc.json", "https://bsc-dataseed.bnbchain.org"),
    "publicnode": ("trusted-bsc-publicnode.json", "https://bsc-rpc.publicnode.com"),
    "zan": ("trusted-bsc-zan.json", "https://api.zan.top/node/v1/bsc/mainnet"),
}
NPM = "0x46a15b0b27311cedf172ab29e4f4766fbe7f4364"
NPM_SOURCE = "https://developer.pancakeswap.finance/contracts/v3/addresses"
POSITIONS_SELECTOR = "0x99fbab88"
SELECTOR_COMMAND = "D:/web3-runtime/tools/foundry-v1.8.4/cast.exe sig positions(uint256)"
HEX_HASH = re.compile(r"0x[0-9a-fA-F]{64}")


def retained(directory: Path, key: str) -> tuple[object, list[dict], dict[str, bytes]]:
    observation_path = directory / f"{key}.observation.json"
    observation_bytes = observation_path.read_bytes()
    observation = json.loads(observation_bytes)
    response_path = (directory / observation["response_file"]).resolve()
    if not response_path.is_relative_to(directory.resolve()):
        raise ValueError("Retained response must stay inside its source run")
    body = response_path.read_bytes()
    digest = hashlib.sha256(body).hexdigest()
    if digest != observation["response_sha256"] or not observation["body_complete"]:
        raise ValueError("Retained response is incomplete or its digest changed")
    files = {observation_path.name: observation_bytes, response_path.name: body}
    inputs = [{"path": path.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(raw).hexdigest()}
              for path, raw in ((observation_path, observation_bytes), (response_path, body))]
    return json.loads(body), inputs, files


def runtime_directory(value: Path) -> Path:
    directory = (ROOT / value).resolve()
    runtime = (ROOT / "runtime").resolve()
    if not directory.is_dir() or directory == runtime or not directory.is_relative_to(runtime):
        raise ValueError("Input runs must be existing directories inside this project's runtime")
    return directory


def make_plan(transaction_run: Path, history_run: Path, history_index: int,
              rpc_provider: str) -> tuple[dict, tuple[PublicTarget, ...], dict[str, bytes]]:
    config_name, rpc_url = RPC_PROVIDERS[rpc_provider]
    trusted_path = ROOT / "configs" / config_name
    trusted_bytes = trusted_path.read_bytes()
    trusted = json.loads(trusted_bytes)
    if (trusted["chain_id"], trusted["rpc_url"]) != (56, rpc_url):
        raise ValueError("Trusted configuration must match the reviewed fixed BSC endpoint")
    transaction_run, history_run = runtime_directory(transaction_run), runtime_directory(history_run)
    transaction_body, tx_inputs, tx_files = retained(transaction_run, "increase-transaction")
    receipt_body, receipt_inputs, receipt_files = retained(transaction_run, "increase-receipt")
    history, history_inputs, history_files = retained(history_run, "brain-agent")
    tx, receipt = transaction_body["result"], receipt_body["result"]
    if not 0 <= history_index < len(history["history"]):
        raise ValueError("--history-index must identify a retained history entry")
    entry = history["history"][history_index]
    step = entry["steps"]["increase"]
    transaction_hash = str(tx["hash"]).lower()
    token_id = int(step["position"])
    block = int(receipt["blockNumber"], 16)
    if (not HEX_HASH.fullmatch(transaction_hash) or receipt["transactionHash"].lower() != transaction_hash
            or tx["blockHash"] != receipt["blockHash"] or tx["blockNumber"] != receipt["blockNumber"]
            or not HEX_HASH.fullmatch(receipt["blockHash"]) or receipt["status"] != "0x1"
            or tx["to"].lower() != NPM or receipt["to"].lower() != NPM
            or tx["from"].lower() != entry["wallet"].lower() or int(tx["chainId"], 16) != 56
            or int(tx["input"][10:74], 16) != token_id or block <= 0
            or not any(str(item.get("hash", "")).lower() == transaction_hash for item in step["txs"])):
        raise ValueError("Retained transaction, receipt and history task do not match")
    call_data = POSITIONS_SELECTOR + f"{token_id:064x}"
    calls = (
        ("chain-id", "eth_chainId", []),
        ("increase-block", "eth_getBlockByNumber", [hex(block), False]),
        ("positions-before", "eth_call", [{"to": NPM, "data": call_data}, hex(block - 1)]),
        ("positions-after", "eth_call", [{"to": NPM, "data": call_data}, hex(block)]),
    )
    targets = tuple(PublicTarget(key, rpc_url, "POST", json_body={"jsonrpc": "2.0", "id": index,
                    "method": method, "params": params})
                    for index, (key, method, params) in enumerate(calls, 1))
    plan = {
        "measurement": "historical-state-feasibility-only", "chain_id": 56, "rpc_url": rpc_url,
        "rpc_provider": rpc_provider, "rpc_source": trusted["source"],
        "position_manager": NPM, "position_manager_source": NPM_SOURCE,
        "token_id": token_id, "history_index_zero_based": history_index,
        "transaction_run": transaction_run.relative_to(ROOT).as_posix(),
        "history_run": history_run.relative_to(ROOT).as_posix(),
        "transaction_hash": transaction_hash, "block_number": block, "block_hash": receipt["blockHash"],
        "selector_validation": {"signature": "positions(uint256)", "selector": POSITIONS_SELECTOR,
                                "command": SELECTOR_COMMAND, "exit_code": 0,
                                "note": "Independently checked once with local cast before implementing this probe."},
        "inputs": [{"path": trusted_path.relative_to(ROOT).as_posix(),
                    "sha256": hashlib.sha256(trusted_bytes).hexdigest()}, *tx_inputs, *receipt_inputs, *history_inputs],
        "request_limit": 4, "retries": 0, "node_failover": False, "scores_computed": False,
        "planned_requests": [{"key": target.key, "json": target.json_body} for target in targets],
        "limits": ["This probe only checks whether fixed historical state can be read.",
                   "Block-end changes may include other transactions; same-block events are not collected here.",
                   "Any provider or historical-state error stops the probe and does not reduce the Agent's score."],
    }
    source_files = {**tx_files, **receipt_files, **history_files, trusted_path.name: trusted_bytes}
    return plan, targets, source_files


def decode_position(value: object) -> dict:
    if not isinstance(value, str) or not re.fullmatch(r"0x[0-9a-fA-F]{768}", value):
        raise ValueError("positions() did not return twelve ABI words")
    words = [int(value[2 + offset:66 + offset], 16) for offset in range(0, 768, 64)]
    signed = lambda word: word - (1 << 256) if word >= 1 << 255 else word
    return {"token0": "0x" + f"{words[2]:064x}"[-40:], "token1": "0x" + f"{words[3]:064x}"[-40:],
            "fee": words[4], "tick_lower": signed(words[5]), "tick_upper": signed(words[6]),
            "liquidity": str(words[7]), "tokens_owed0": str(words[10]), "tokens_owed1": str(words[11])}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transaction-run", type=Path, required=True,
                        help="Retained increase transaction/receipt run inside this project's runtime")
    parser.add_argument("--history-run", type=Path, required=True,
                        help="Retained brain-agent response run inside this project's runtime")
    parser.add_argument("--history-index", type=int, required=True, help="Explicit zero-based task index")
    parser.add_argument("--rpc-provider", choices=tuple(RPC_PROVIDERS), default="bnb-official")
    parser.add_argument("--execute-public-readonly", action="store_true")
    parser.add_argument("--proxy", help="Required explicit operator proxy when execution is enabled")
    parser.add_argument("--zan-key-url-file", type=Path)
    args = parser.parse_args()
    if args.execute_public_readonly and not args.proxy:
        parser.error("Execution requires --proxy; the default command performs no network calls")
    plan, targets, source_files = make_plan(args.transaction_run, args.history_run,
                                          args.history_index, args.rpc_provider)
    plan["execution_enabled"] = args.execute_public_readonly
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    if not args.execute_public_readonly:
        return 0
    now = datetime.now(timezone.utc)
    run = ROOT / "runtime" / f"liquidity-state-{now:%Y%m%dT%H%M%SZ}-{secrets.token_hex(4)}"
    run.mkdir()
    with (run / "manifest.json").open("x", encoding="utf-8") as stream:
        json.dump({"started_at": now.isoformat(), **plan}, stream, ensure_ascii=False, indent=2)
    for name, body in source_files.items():
        with (run / ("input-" + name)).open("xb") as stream:
            stream.write(body)
    results, stop = {}, None
    with SafeHttpClient(targets, enabled=True, proxy=args.proxy, max_requests=4,
                        zan_key_url_file=load_zan_key_file(args.zan_key_url_file) if args.rpc_provider == "zan" else None) as client:
        for target in targets:
            observation = client.fetch(target.key, run)
            if (observation.error_kind or not observation.body_complete
                    or observation.http_status != 200 or not observation.response_file):
                stop = {"request": target.key, "reason": observation.error_kind or "incomplete_or_unsuccessful_http"}
                break
            try:
                response = json.loads((run / observation.response_file).read_bytes())
                if (not isinstance(response, dict) or response.get("jsonrpc") != "2.0"
                        or response.get("id") != target.json_body["id"] or "error" in response
                        or response.get("result") is None):
                    stop = {"request": target.key, "reason": "rpc_error_or_missing_result", "rpc_error": response.get("error") if isinstance(response, dict) else None}
                    break
                value = response["result"]
                if target.key == "chain-id" and int(value, 16) != 56:
                    raise ValueError("unexpected_chain_id")
                if target.key == "increase-block" and (not isinstance(value, dict)
                        or value.get("number") != hex(plan["block_number"]) or value.get("hash") != plan["block_hash"]):
                    raise ValueError("historical_block_does_not_match_retained_receipt")
                results[target.key] = decode_position(value) if target.key.startswith("positions-") else value
                print(f"{target.key}: retained HTTP 200 and valid read result")
            except (ValueError, TypeError) as exc:
                stop = {"request": target.key, "reason": str(exc)[:500]}
                break
    result = {"probe_status": "BLOCKED" if stop else "HISTORICAL_STATE_READABLE",
              "stopped_reason": stop, "requests_observed": 4 - client.remaining,
              "scores_computed": False, "same_block_events_collected": False, "results": results}
    with (run / "result.json").open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(f"evidence_directory={run}; probe_status={result['probe_status']}; no Agent scores computed")
    return 1 if stop else 0


if __name__ == "__main__":
    raise SystemExit(main())
