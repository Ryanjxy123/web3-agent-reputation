"""Collect the frozen liquidity-history-v1 evidence; dry-run unless explicitly enabled."""

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

from probe_liquidity_state import decode_position, retained, runtime_directory
from reputation_core import MeasurementPurpose
from reputation_core.liquidity import INCREASE_TOPIC
from reputation_platform.safe_http import PublicTarget, SafeHttpClient
from reputation_platform.settings import load_zan_key_file

RPC_URL = "https://api.zan.top/node/v1/bsc/mainnet"
NPM = "0x46a15b0b27311cedf172ab29e4f4766fbe7f4364"
POSITIONS_SELECTOR = "0x99fbab88"
DECREASE_TOPIC = "0x26f6a048ee9138f2c0ce266f322cb99228e8d619ae2bff30c67f8dcf9d2377b4"
EVENT_INTERFACE_SOURCE = "https://raw.githubusercontent.com/pancakeswap/pancake-v3-contracts/main/projects/v3-periphery/contracts/interfaces/INonfungiblePositionManager.sol"
REUSE_RPC_URLS = {RPC_URL, "https://bsc-dataseed.bnbchain.org", "https://bsc-rpc.publicnode.com"}
FROZEN_FUNCTIONAL = [97, 99, 101, 104, 112, 116, 121]
FROZEN_BEHAVIORAL = [98, 100, 102, 106, 114, 119, 123]
LABELS = ["wrap", "buy the missing other side", "increase the position"]
HASH = re.compile(r"0x[0-9a-fA-F]{64}")
MAX_REQUESTS = 128  # 2 shared + 7 functional * 6 + 7 behavioral * 12, before reuse.


def file_reference(path: Path) -> dict:
    return {"path": path.relative_to(ROOT).as_posix(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def call_key(method: str, params: list) -> str:
    return json.dumps([method, params], sort_keys=True, separators=(",", ":"))


def rpc_value(body: object, request: dict) -> object:
    if (not isinstance(body, dict) or body.get("jsonrpc") != "2.0"
            or body.get("id") != request["id"] or "error" in body
            or body.get("result") is None):
        raise ValueError("rpc_error_or_missing_result")
    return body["result"]


def request_spec(key: str, method: str, params: list, task: dict | None = None) -> dict:
    return {"key": key, "method": method, "params": params,
            "purpose": task["purpose"] if task else MeasurementPurpose.BACKGROUND.value,
            "task_key": task["task_key"] if task else None,
            "history_index": task["history_index"] if task else None,
            "source_path": task["source_path"] if task else None}


def prepare(history_run: Path, indices: list[int] | None, reuse_runs: list[Path]) -> tuple[dict, dict]:
    config_path = ROOT / "configs/pilots/brain-defi-liquidity-v1.json"
    policy_path = ROOT / "docs/adr/0004-liquidity-history-policy.md"
    trusted_path = ROOT / "configs/trusted-bsc-zan.json"
    config = json.loads(config_path.read_bytes())
    trusted = json.loads(trusted_path.read_bytes())
    if (config["policy_version"] != "liquidity-history-v1" or config["chain_id"] != 56
            or config["position_manager"].lower() != NPM
            or config["functional_indices"] != FROZEN_FUNCTIONAL
            or config["behavioral_indices"] != FROZEN_BEHAVIORAL
            or (trusted["chain_id"], trusted["rpc_url"]) != (56, RPC_URL)):
        raise ValueError("Configuration does not match the frozen pilot and fixed ZAN BSC endpoint")
    history_run = runtime_directory(history_run)
    history, history_inputs, files = retained(history_run, "brain-agent")
    source_observation = json.loads(files["brain-agent.observation.json"])
    source_hash = hashlib.sha256(files["brain-agent.response.bin"]).hexdigest()
    if (source_hash != config["history_response_sha256"]
            or source_observation["url"] != config["history_source_url"]
            or source_observation["http_status"] != 200 or source_observation["error_kind"]):
        raise ValueError("History source does not match the frozen complete public snapshot")
    frozen = sorted(FROZEN_FUNCTIONAL + FROZEN_BEHAVIORAL)
    selected = frozen if indices is None else indices
    if not selected or len(set(selected)) != len(selected) or any(index not in frozen for index in selected):
        raise ValueError("--history-index must select distinct indices from the frozen fourteen tasks")
    tasks = []
    for index in sorted(selected):
        entry = history["history"][index]
        task = {"history_index": index, "task_key": f"{source_hash}:{index}",
                "purpose": "functional" if index in FROZEN_FUNCTIONAL else "behavioral",
                "source_path": f"$.history[{index}].steps.increase", "source_record": entry,
                "planning_gaps": []}
        step = entry.get("steps", {}).get("increase")
        txs = step.get("txs") if isinstance(step, dict) else None
        malformed = (not isinstance(txs, list) or not txs
                or any(not isinstance(tx, dict) for tx in txs)
                or any(not isinstance(tx.get("hash"), str) or not HASH.fullmatch(tx["hash"]) for tx in txs))
        if not malformed:
            labels = [tx.get("label") for tx in txs]
            malformed = (labels != LABELS if task["purpose"] == "behavioral"
                         else labels.count("increase the position") != 1)
        if malformed:
            task["planning_gaps"].append("unadapted_increase_transaction_structure_or_labels")
        else:
            roles = dict(zip(LABELS, ("wrap", "swap", "increase")))
            task["transactions"] = [{"role": roles.get(tx.get("label"), f"unmeasured-{ordinal}"),
                                     "hash": tx["hash"].lower(), "ordinal": ordinal,
                                     "source_path": f"{task['source_path']}.txs[{ordinal}].hash"}
                                    for ordinal, tx in enumerate(txs)]
        if not isinstance(step, dict) or not str(step.get("position", "")).isdigit():
            task["planning_gaps"].append("missing_position_identifier")
        else:
            task["token_id"] = int(step["position"])
        if entry.get("wallet", "").lower() != config["execution_wallet"].lower():
            task["planning_gaps"].append("source_execution_wallet_mismatch")
        tasks.append(task)
    cache, reuse_inputs, reuse_gaps = {}, [], []
    for supplied_run in reuse_runs:
        directory = runtime_directory(supplied_run)
        for observation_path in sorted(directory.glob("*.observation.json")):
            if observation_path.name.startswith("input-"):
                continue
            try:
                observation = json.loads(observation_path.read_bytes())
                if (observation.get("method") != "POST" or observation.get("url") not in REUSE_RPC_URLS
                        or observation.get("http_status") != 200 or observation.get("error_kind")
                        or not observation.get("body_complete") or not observation.get("response_file")):
                    continue
                response_path = (directory / observation["response_file"]).resolve()
                if not response_path.is_relative_to(directory):
                    raise ValueError("response_path_outside_source_run")
                raw = response_path.read_bytes()
                if hashlib.sha256(raw).hexdigest() != observation["response_sha256"]:
                    raise ValueError("retained_response_digest_mismatch")
                request = json.loads(observation["request_json"])
                if request["method"] == "eth_blockNumber":
                    continue  # Confirmation height is observed for this collection, not borrowed from an old run.
                value = rpc_value(json.loads(raw), request)
                references = [file_reference(observation_path), file_reference(response_path)]
                cache[call_key(request["method"], request["params"])] = {
                    "value": value, "evidence": references, "original_purpose": observation["purpose"],
                    "original_rpc_url": observation["url"]}
                reuse_inputs.extend(references)
            except (OSError, KeyError, TypeError, ValueError):
                reuse_gaps.append({"observation": observation_path.relative_to(ROOT).as_posix(),
                                   "reason": "unusable_retained_rpc_evidence"})
    manifest = {
        "measurement": "frozen-liquidity-history-evidence-only", "policy_version": config["policy_version"],
        "policy": file_reference(policy_path), "pilot_config": file_reference(config_path),
        "trusted_rpc_config": file_reference(trusted_path), "chain_id": 56, "rpc_url": RPC_URL,
        "rpc_source": trusted["source"], "history_source_sha256": source_hash,
        "inputs": history_inputs + reuse_inputs, "reuse_gaps": reuse_gaps, "tasks": tasks,
        "registration_tx_hash": config["registration_tx_hash"], "agent_id": config["agent_id"],
        "execution_wallet": config["execution_wallet"], "position_manager": NPM,
        "confirmation_distance": config["confirmation_distance"],
        "task_window_seconds": config["task_window_seconds"],
        "maximum_new_requests": min(MAX_REQUESTS, 2 + sum(6 if task["purpose"] == "functional" else 12
                                                         for task in tasks if not task["planning_gaps"])),
        "retries": 0, "node_failover": False, "scores_computed": False,
        "event_interface_source": EVENT_INTERFACE_SOURCE,
        "event_topic_validation": {"command": "cast keccak 'DecreaseLiquidity(uint256,uint128,uint256,uint256)'",
                                   "exit_code": 0, "topic": DECREASE_TOPIC,
                                   "note": "Derived once by the coordinating operator before this implementation."},
        "deferred_requests": [
            "For every task: final transaction, receipt, matching block header, positions at N-1 and N.",
            "At each final block N: NPM Increase/DecreaseLiquidity logs for this tokenId only.",
            "For behavioral tasks: both preceding transactions, receipts and matching block headers.",
        ],
        "limits": ["Collection does not score or establish task completion.",
                   "Token decimals, protocol-specific swap checks and same-block reconstruction remain verifier work.",
                   "A block-end position is not automatically the position immediately after this transaction.",
                   "Reused background evidence is referenced without changing its original measurement purpose."],
    }
    return manifest, cache


class Collector:
    def __init__(self, directory: Path, cache: dict, proxy: str, key_file: Path, request_limit: int) -> None:
        self.directory, self.cache, self.proxy, self.key_file = directory, cache, proxy, key_file
        self.request_limit = request_limit
        self.new_requests = 0
        self.stop = None

    def stage(self, specs: list[dict]) -> dict:
        values = {}
        targets = tuple(PublicTarget(spec["key"], RPC_URL, "POST", MeasurementPurpose(spec["purpose"]),
                                    {"jsonrpc": "2.0", "id": index, "method": spec["method"], "params": spec["params"]})
                        for index, spec in enumerate(specs, 1))
        with SafeHttpClient(targets, enabled=True, proxy=self.proxy,
                            max_requests=min(len(targets), self.request_limit - self.new_requests),
                            zan_key_url_file=self.key_file) as client:
            for spec, target in zip(specs, targets):
                if self.stop:
                    break
                record = {**spec, "request_json": target.json_body, "status": "UNKNOWN"}
                # Append the exact dependent request and its task/purpose before any send.
                with (self.directory / "request-plan.jsonl").open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(record) + "\n")
                cached = self.cache.get(call_key(spec["method"], spec["params"]))
                if cached:
                    record.update(status="REUSED", evidence=cached["evidence"],
                                  original_purpose=cached["original_purpose"],
                                  original_rpc_url=cached["original_rpc_url"])
                    values[spec["key"]] = cached["value"]
                elif self.new_requests >= self.request_limit:
                    self.stop = "request_budget_exhausted"
                    record["gap"] = self.stop
                else:
                    observation = client.fetch(target.key, self.directory)
                    self.new_requests += 1
                    record["evidence"] = [file_reference(self.directory / f"{target.key}.observation.json")]
                    if observation.response_file:
                        record["evidence"].append(file_reference(self.directory / observation.response_file))
                    if observation.http_status in (401, 402, 403, 429):
                        self.stop = f"host_stop_http_{observation.http_status}"
                    if (observation.error_kind or observation.http_status != 200
                            or not observation.body_complete or not observation.response_file):
                        record["gap"] = observation.error_kind or "incomplete_or_unsuccessful_http"
                    else:
                        try:
                            body = json.loads((self.directory / observation.response_file).read_bytes())
                            value = rpc_value(body, target.json_body)
                            values[spec["key"]] = value
                            record["status"] = "RPC_RESULT_RETAINED"
                            self.cache[call_key(spec["method"], spec["params"])] = {
                                "value": value, "evidence": record["evidence"],
                                "original_purpose": spec["purpose"], "original_rpc_url": RPC_URL}
                        except (TypeError, ValueError):
                            record["gap"] = "rpc_error_or_missing_result"
                if spec["method"] == "eth_chainId":
                    try:
                        if int(values[spec["key"]], 16) != 56:
                            raise ValueError("unexpected_chain_id")
                    except (KeyError, TypeError, ValueError):
                        self.stop = self.stop or "unexpected_or_unavailable_chain_id"
                        record.update(status="UNKNOWN", gap=self.stop)
                with (self.directory / "request-results.jsonl").open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(record) + "\n")
                print(f"{spec['key']}: {record['status']}" + (f" gap={record['gap']}" if record.get("gap") else ""))
        return values


def transaction_specs(task: dict) -> list[dict]:
    requests = []
    txs = [tx for tx in task["transactions"] if task["purpose"] == "behavioral" or tx["role"] == "increase"]
    for transaction in txs:
        stem = f"history-{task['history_index']}-{transaction['role']}"
        for suffix, method in (("transaction", "eth_getTransactionByHash"), ("receipt", "eth_getTransactionReceipt")):
            spec = request_spec(f"{stem}-{suffix}", method, [transaction["hash"]], task)
            spec["source_path"] = transaction["source_path"]
            requests.append(spec)
    return requests


def dependent_specs(task: dict, transactions: dict) -> tuple[list[dict], list[dict]]:
    requests, gaps = [], []
    txs = [tx for tx in task["transactions"] if task["purpose"] == "behavioral" or tx["role"] == "increase"]
    for transaction in txs:
        stem = f"history-{task['history_index']}-{transaction['role']}"
        tx, receipt = transactions.get(stem + "-transaction"), transactions.get(stem + "-receipt")
        if not isinstance(tx, dict) or not isinstance(receipt, dict):
            gaps.append({"role": transaction["role"], "reason": "transaction_or_receipt_unavailable"})
            continue
        try:
            block = int(receipt["blockNumber"], 16)
            block_hash = receipt["blockHash"]
            if (block <= 0 or not isinstance(block_hash, str) or not HASH.fullmatch(block_hash)
                    or tx["hash"].lower() != transaction["hash"]
                    or receipt["transactionHash"].lower() != transaction["hash"]
                    or tx["blockNumber"] != receipt["blockNumber"] or tx["blockHash"] != block_hash):
                raise ValueError("transaction_receipt_binding_mismatch")
            spec = request_spec(stem + "-block", "eth_getBlockByNumber", [hex(block), False], task)
            spec["expected_block_hash"] = block_hash
            requests.append(spec)
            if transaction["role"] == "increase":
                calldata = POSITIONS_SELECTOR + f"{task['token_id']:064x}"
                for name, number in (("before", block - 1), ("after", block)):
                    requests.append(request_spec(stem + "-positions-" + name, "eth_call",
                                                 [{"to": NPM, "data": calldata}, hex(number)], task))
                requests.append(request_spec(stem + "-same-block-events", "eth_getLogs", [{
                    "address": NPM, "fromBlock": hex(block), "toBlock": hex(block),
                    "topics": [[INCREASE_TOPIC, DECREASE_TOPIC], "0x" + f"{task['token_id']:064x}"],
                }], task))
        except (KeyError, TypeError, ValueError):
            gaps.append({"role": transaction["role"], "reason": "transaction_receipt_binding_or_block_gap"})
    return requests, gaps


def inspect_fixed_results(specs: list[dict], values: dict) -> list[dict]:
    gaps = []
    for spec in specs:
        value = values.get(spec["key"])
        try:
            if value is None:
                raise ValueError("fixed_read_unavailable")
            if spec["method"] == "eth_getBlockByNumber":
                if (not isinstance(value, dict) or value.get("number") != spec["params"][0]
                        or value.get("hash") != spec["expected_block_hash"]):
                    raise ValueError("fixed_block_header_mismatch")
            elif spec["method"] == "eth_call":
                decode_position(value)
            elif spec["method"] == "eth_getLogs" and not isinstance(value, list):
                raise ValueError("malformed_same_block_events")
        except (KeyError, TypeError, ValueError):
            gaps.append({"request": spec["key"], "reason": "fixed_read_unavailable_or_unadapted"})
    return gaps


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history-run", required=True, type=Path)
    parser.add_argument("--history-index", nargs="+", type=int, help="Optional subset of the frozen fourteen indices")
    parser.add_argument("--reuse-run", nargs="+", type=Path, default=[], help="Explicit retained RPC runs; digests are checked")
    parser.add_argument("--execute-public-readonly", action="store_true")
    parser.add_argument("--proxy")
    parser.add_argument("--zan-key-url-file", type=Path)
    args = parser.parse_args()
    if args.execute_public_readonly and not args.proxy:
        parser.error("Execution requires --proxy; the default performs no network calls")
    manifest, cache = prepare(args.history_run, args.history_index, args.reuse_run)
    manifest["execution_enabled"] = args.execute_public_readonly
    manifest["initial_requests"] = [request_spec("chain-id", "eth_chainId", []),
                                    request_spec("confirmation-head", "eth_blockNumber", [])]
    manifest["transaction_requests"] = [spec for task in manifest["tasks"]
                                        if not task["planning_gaps"] for spec in transaction_specs(task)]
    print(json.dumps(manifest if not args.execute_public_readonly else {
        "tasks": len(manifest["tasks"]), "maximum_new_requests": manifest["maximum_new_requests"],
        "execution_enabled": True, "purpose": "frozen historical evidence collection only",
    }, ensure_ascii=True, indent=2))
    if not args.execute_public_readonly:
        return 0
    now = datetime.now(timezone.utc)
    run = ROOT / "runtime" / f"liquidity-history-{now:%Y%m%dT%H%M%SZ}-{secrets.token_hex(4)}"
    run.mkdir()
    with (run / "manifest.json").open("x", encoding="utf-8") as stream:
        json.dump({"started_at": now.isoformat(), **manifest}, stream, indent=2)
    collector = Collector(run, cache, args.proxy, load_zan_key_file(args.zan_key_url_file), manifest["maximum_new_requests"])
    initial = collector.stage(manifest["initial_requests"])
    try:
        if int(initial["chain-id"], 16) != 56:
            collector.stop = "unexpected_chain_id"
        head = int(initial["confirmation-head"], 16)
    except (KeyError, TypeError, ValueError):
        collector.stop = collector.stop or "chain_or_confirmation_head_unavailable"
        head = None
    task_results = []
    for task in manifest["tasks"]:
        result = {"task_key": task["task_key"], "history_index": task["history_index"],
                  "purpose": task["purpose"], "collection_status": "UNKNOWN",
                  "gaps": [{"reason": reason} for reason in task["planning_gaps"]]}
        if collector.stop:
            result["gaps"].append({"reason": collector.stop})
        elif not task["planning_gaps"]:
            transactions = collector.stage(transaction_specs(task))
            specs, gaps = dependent_specs(task, transactions)
            fixed = collector.stage(specs) if specs and not collector.stop else {}
            result["gaps"].extend(gaps + inspect_fixed_results(specs, fixed))
            result["confirmation_head"] = head
            result["confirmation_distance_required"] = manifest["confirmation_distance"]
            if collector.stop:
                result["gaps"].append({"reason": collector.stop})
            if not result["gaps"]:
                result["collection_status"] = "REQUESTED_EVIDENCE_RETAINED"
        task_results.append(result)
        with (run / f"history-{task['history_index']}.collection.json").open("x", encoding="utf-8") as stream:
            json.dump(result, stream, indent=2)
    complete = all(result["collection_status"] == "REQUESTED_EVIDENCE_RETAINED" for result in task_results)
    summary = {"collection_status": "REQUESTED_EVIDENCE_RETAINED" if complete else "HAS_GAPS",
               "new_requests": collector.new_requests, "stopped_reason": collector.stop,
               "scores_computed": False, "tasks": task_results}
    with (run / "result.json").open("x", encoding="utf-8") as stream:
        json.dump(summary, stream, indent=2)
    print(f"evidence_directory={run}; collection_status={summary['collection_status']}; no scores computed")
    return 0 if complete else 1


if __name__ == "__main__":
    raise SystemExit(main())
