"""Retain Omenstrat execution evidence for a fixed public discovery cohort.

Read-only discovery, not reputation scoring. A latest-buy index is a successful-
event index; the separate Safe window includes all matching Safe executions,
including non-buy actions, and does not establish a complete task denominator.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import secrets
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "packages/core/src"), str(ROOT / "services/platform/src")]

from eth_hash.auto import keccak

from reputation_core import ProbeObservation
from reputation_core.ipfs import read_car_file
from reputation_core.prediction_chain import calldata
from reputation_platform.registration_discovery import DiscoveryEvidence, _rpc

REGISTRY = "0x9338b5153ae39bb89f50468e608ed9d764b755fd"
OMEN_INDEX = "https://omen.subgraph.autonolas.tech"
SOURCE = "https://github.com/valory-xyz/olas-predict/blob/main/constants/leaderboard.ts"
DECLARATION = "https://github.com/valory-xyz/trader/blob/main/README.md"
SUCCESS = "0x" + keccak(b"ExecutionSuccess(bytes32,uint256)").hex()
FAILURE = "0x" + keccak(b"ExecutionFailure(bytes32,uint256)").hex()


def write(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8") as output:
        json.dump(value, output, ensure_ascii=False, indent=2)


def reference(path: Path) -> dict:
    return {"path": path.relative_to(ROOT).as_posix(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def retained(directory: Path, key: str, *, parse_json: bool = True) -> tuple[object, dict]:
    observation_path = directory / f"{key}.observation.json"
    observation = ProbeObservation.model_validate_json(observation_path.read_bytes())
    response_path = directory / f"{key}.response.bin"
    raw = response_path.read_bytes()
    if (observation.request_key != key or observation.http_status != 200
        or observation.error_kind or not observation.body_complete
        or observation.response_file != response_path.name
        or observation.response_sha256 != hashlib.sha256(raw).hexdigest()):
        raise ValueError(f"Retained read is unavailable or changed: {key}")
    refs = {"response_path": response_path.relative_to(ROOT).as_posix(),
            "observation_path": observation_path.relative_to(ROOT).as_posix(),
            "references": [reference(observation_path), reference(response_path)]}
    plan = directory / f"{key}.request-plan.json"
    if plan.is_file():
        refs["request_plan_path"] = plan.relative_to(ROOT).as_posix()
        refs["references"].append(reference(plan))
    return (json.loads(raw) if parse_json else raw), refs


def rpc_read(evidence: DiscoveryEvidence, key: str, method: str, params: list) -> tuple[object, dict]:
    value = _rpc(evidence, 100, key, method, params)["value"]
    _, refs = retained(evidence.run, key)
    return value, refs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retained-research", type=Path, required=True,
                        help="Existing runtime research with the frozen 30-row trader discovery")
    parser.add_argument("--execute-public-readonly", action="store_true")
    parser.add_argument("--retained-source-evidence", type=Path,
                        help="Optional existing runtime source reads, reused after interrupted collection")
    parser.add_argument("--proxy", default="http://127.0.0.1:7897")
    args = parser.parse_args()
    previous = (ROOT / args.retained_research).resolve()
    if not previous.is_relative_to(ROOT / "runtime") or not previous.is_dir():
        parser.error("Retained research must be an existing project runtime directory")
    discovery, discovery_ref = retained(previous, "omen-trader-cohort")
    if discovery.get("errors") or discovery["data"]["_meta"]["hasIndexingErrors"]:
        parser.error("Frozen discovery returned GraphQL or indexing errors")
    rows = discovery["data"]["traderAgents"][:10]
    if len(rows) != 10 or len({row["id"] for row in rows}) != 10:
        parser.error("Expected ten distinct Safe instances in the frozen index order")
    selection = {"source": discovery_ref, "count": 10,
        "order": "first ten rows in retained totalBets descending discovery; no score selection",
        "replacement_on_gap": False, "index_is_successful_buy_discovery": True}
    if not args.execute_public_readonly:
        print(json.dumps({"selection": selection, "candidate_service_ids": [r["serviceId"] for r in rows],
                          "execution_enabled": False, "scores_computed": False}, ensure_ascii=False))
        return 0
    now = datetime.now(timezone.utc)
    run = ROOT / "runtime" / f"olas-execution-cohort-{now:%Y%m%dT%H%M%SZ}-{secrets.token_hex(4)}"
    evidence = DiscoveryEvidence(ROOT, run, proxy=args.proxy, enabled=True,
                                 timeout_seconds=30, max_requests=64)
    manifest = {"created_at": now.isoformat(), "schema_version": "olas-execution-cohort-discovery-v1",
        "selection": selection, "service_registry": REGISTRY, "registry_source": SOURCE,
        "declaration_source": DECLARATION, "script": reference(Path(__file__)),
        "window": {"blocks": 256, "ends_before_selected_buy_block": True,
                   "topics": [SUCCESS, FAILURE]},
        "scores_computed": False, "signatures_created": 0, "transactions_sent": 0,
        "limits": ["Latest-buy index contains successful buys, not all trade attempts.",
                   "Safe window includes non-buy actions and is not a business-task denominator.",
                   "A historical signed call expresses execution intent; it does not prove prediction quality.",
                   "No availability score is derived from RPC/index availability.",
                   "No failed candidate is replaced and no task/sample threshold is lowered."]}
    write(run / "manifest.json", manifest)
    source_refs = {}
    sources = (ROOT / args.retained_source_evidence).resolve() if args.retained_source_evidence else previous
    if not sources.is_relative_to(ROOT / "runtime") or not sources.is_dir():
        parser.error("Retained source evidence must be an existing project runtime directory")
    for name, url in [
        ("trader-declaration", "https://raw.githubusercontent.com/valory-xyz/trader/main/README.md"),
        ("safe-multisend-deployment", "https://raw.githubusercontent.com/safe-global/safe-deployments/main/src/assets/v1.3.0/multi_send.json"),
        ("safe-singleton-deployment", "https://raw.githubusercontent.com/safe-global/safe-deployments/main/src/assets/v1.3.0/gnosis_safe.json"),
        ("safe-singleton-l2-deployment", "https://raw.githubusercontent.com/safe-global/safe-deployments/main/src/assets/v1.3.0/gnosis_safe_l2.json"),
    ]:
        if (sources / f"{name}.observation.json").is_file():
            _, source_refs[name] = retained(sources, name, parse_json=False)
        else:
            evidence.request(name, url)
            _, source_refs[name] = retained(run, name, parse_json=False)
    chain, chain_ref = retained(previous, "execution-chain-id")
    if int(chain["result"], 16) != 100:
        raise ValueError("Retained RPC chain is not Gnosis")
    head, head_ref = rpc_read(evidence, "cohort-confirmation-head", "eth_blockNumber", [])
    head_number = int(head, 16)
    _, confirmed_ref = rpc_read(evidence, "cohort-confirmed-header", "eth_getBlockByNumber", [hex(head_number - 64), False])
    existing_trades, existing_trade_ref = retained(previous, "omen-independent-trades")
    known = {service.removeprefix("s"): value[0] for service, value in existing_trades["data"].items()
             if service.startswith("s") and isinstance(value, list) and value}
    missing = [row for row in rows if row["serviceId"] not in known]
    query = "query { " + " ".join(
        "s" + row["serviceId"] + ": fpmmTrades(first: 1, orderBy: creationTimestamp, orderDirection: desc, "
        "where: {creator: \"" + row["id"] + "\", type: Buy}) "
        "{ id transactionHash creator { id } fpmm { id outcomes collateralToken question { id data } } "
        "outcomeIndex collateralAmount outcomeTokensTraded creationTimestamp feeAmount type }"
        for row in missing) + " _meta { block { number } hasIndexingErrors } }"
    response = evidence.request("cohort-latest-buy-index", OMEN_INDEX, "POST", {"query": query})
    if not response["raw"]:
        raise ValueError("Latest-buy index unavailable; original cohort retained without replacement")
    payload, trade_ref = retained(run, "cohort-latest-buy-index")
    if payload.get("errors") or payload["data"]["_meta"]["hasIndexingErrors"]:
        raise ValueError("Latest-buy index returned GraphQL/indexing errors")
    for service, value in payload["data"].items():
        if service.startswith("s") and isinstance(value, list) and value:
            known[service[1:]] = value[0]
    summary = {"schema_version": "olas-execution-cohort-discovery-v1",
        "created_at": now.isoformat(), "run_directory": run.relative_to(ROOT).as_posix(),
        "selection": selection, "service_registry": REGISTRY,
        "source_evidence": source_refs,
        "chain_context": {"chain_id": 100, "head": head_number, "confirmed_block": head_number - 64,
                          "chain_evidence": chain_ref, "head_evidence": head_ref,
                          "confirmed_header_evidence": confirmed_ref},
        "scores_computed": False, "candidates": []}
    configurations = {}
    prior_metadata = previous / "configuration-metadata-supplement.json"
    if prior_metadata.is_file():
        configurations = {item["config_hash"]: item for item in
                          json.loads(prior_metadata.read_bytes())["configurations"]}
    specifications = (("transaction", "tx", "eth_getTransactionByHash"),
                      ("receipt", "receipt", "eth_getTransactionReceipt"))
    for rank, row in enumerate(rows, 1):
        service, safe = row["serviceId"], row["id"].lower()
        item = {"rank": rank, "chain_id": 100, "olas_service_id": service,
            "execution_address": safe, "declared_function": "在Gnosis的Omen预测市场自主选择市场并通过Safe买入结果份额，随后结算/赎回；本轮只核验买入执行。",
            "declaration_source": DECLARATION, "indexed_total_buys": row["totalBets"],
            "latest_buy": known.get(service), "evidence": {}, "gaps": []}
        summary["candidates"].append(item)
        trade = item["latest_buy"]
        if not trade:
            item["gaps"].append("No indexed buy for this frozen candidate; no replacement")
            write(run / f"checkpoint-{rank:02}.json", summary)
            continue
        item["evidence"]["buy_index"] = existing_trade_ref if service in {"219", "415", "691"} else trade_ref
        tx_hash = trade["transactionHash"]
        try:
            for name, suffix, method in specifications:
                oldkey = "execution-" + service + "-" + suffix
                if (previous / f"{oldkey}.observation.json").is_file():
                    envelope, refs = retained(previous, oldkey)
                    value = envelope["result"]
                else:
                    value, refs = rpc_read(evidence, "cohort-" + service + "-" + suffix, method, [tx_hash])
                item["evidence"][name] = refs
                if name == "transaction":
                    tx = value
            block, before = tx["blockNumber"], hex(int(tx["blockNumber"], 16) - 1)
            if int(block, 16) > head_number - 64:
                item["gaps"].append("Selected latest buy lacks configured confirmation distance")
            calls = [
                ("block", "block", "eth_getBlockByNumber", [block, False]),
                ("service_before", "service-before", "eth_call", [{"to": REGISTRY, "data": calldata("mapServices(uint256)", int(service))}, before]),
                ("agent_instances_before", "agent-instances-before", "eth_call", [{"to": REGISTRY, "data": calldata("getAgentInstances(uint256)", int(service))}, before]),
                ("safe_owners_before", "safe-owners-before", "eth_call", [{"to": safe, "data": calldata("getOwners()")}, before]),
                ("safe_threshold_before", "safe-threshold-before", "eth_call", [{"to": safe, "data": calldata("getThreshold()")}, before]),
                ("safe_master_copy_before", "safe-master-copy-before", "eth_call", [{"to": safe, "data": calldata("masterCopy()")}, before]),
                ("safe_code", "safe-code", "eth_getCode", [safe, block]),
                ("market_collateral_before", "market-collateral-before", "eth_call", [{"to": trade["fpmm"]["id"], "data": calldata("collateralToken()")}, before]),
                ("market_conditional_tokens_before", "market-conditional-tokens-before", "eth_call", [{"to": trade["fpmm"]["id"], "data": calldata("conditionalTokens()")}, before]),
                ("market_condition_before", "market-condition-before", "eth_call", [{"to": trade["fpmm"]["id"], "data": calldata("conditionIds(uint256)", 0)}, before]),
                ("execution_window", "execution-window", "eth_getLogs", [{"address": safe,
                    "fromBlock": hex(max(0, int(block, 16) - 256)), "toBlock": before,
                    "topics": [[SUCCESS, FAILURE]]}]),
            ]
            # A separate explicit 16-read scope per instance; the global client covers only discovery.
            scoped = DiscoveryEvidence(ROOT, run, proxy=args.proxy, enabled=True,
                                       timeout_seconds=30, max_requests=16)
            values = {}
            for name, suffix, method, params in calls:
                oldkey = "execution-" + service + "-" + suffix
                try:
                    if (previous / f"{oldkey}.observation.json").is_file():
                        envelope, refs = retained(previous, oldkey)
                        value = envelope["result"]
                    else:
                        value, refs = rpc_read(scoped, "cohort-" + service + "-" + suffix, method, params)
                    item["evidence"][name] = refs
                    values[name] = value
                    if name == "execution_window":
                        item["safe_window"] = {"from_block": max(0, int(block, 16) - 256),
                            "to_block": int(before, 16), "all_matching_logs_retained": True,
                            "success_events": sum(log["topics"][0] == SUCCESS for log in value),
                            "failure_events": sum(log["topics"][0] == FAILURE for log in value),
                            "business_task_denominator": False}
                except (OSError, ValueError, KeyError) as error:
                    item["gaps"].append(name + ": " + str(error))
            encoded = bytes.fromhex(tx["input"][10:])
            offset = int.from_bytes(encoded[64:96])
            size = int.from_bytes(encoded[offset:offset + 32])
            inner = encoded[offset + 32:offset + 32 + size]
            if (inner[:4].hex() == calldata("buy(uint256,uint256,uint256)")[2:]
                and "market_collateral_before" in values):
                try:
                    collateral = "0x" + values["market_collateral_before"][-40:]
                    _, refs = rpc_read(scoped, "cohort-" + service + "-collateral-allowance-before",
                        "eth_call", [{"to": collateral, "data": calldata("allowance(address,address)",
                            safe, trade["fpmm"]["id"])}, before])
                    item["evidence"]["collateral_allowance_before"] = refs
                except (OSError, ValueError, KeyError) as error:
                    item["gaps"].append("collateral_allowance_before: " + str(error))
            if "safe_master_copy_before" in values:
                try:
                    singleton = "0x" + values["safe_master_copy_before"][-40:]
                    _, refs = rpc_read(scoped, "cohort-" + service + "-safe-singleton-code-before",
                                       "eth_getCode", [singleton, before])
                    item["evidence"]["safe_singleton_code_before"] = refs
                except (OSError, ValueError, KeyError) as error:
                    item["gaps"].append("safe_singleton_code_before: " + str(error))
            if "service_before" in values:
                digest = "0x" + values["service_before"][130:194]
                try:
                    if digest not in configurations:
                        key = "cohort-config-" + digest[2:] + "-car"
                        response = scoped.request(key,
                            "https://gateway.autonolas.tech/ipfs/f01701220" + digest[2:]
                            + "?format=car&dag-scope=entity")
                        raw, proof = read_car_file(response["raw"], digest)
                        file = run / (key + "-verified-metadata.json")
                        file.write_bytes(raw)
                        configurations[digest] = {"config_hash": digest,
                            "document": json.loads(raw), "file_ref": reference(file),
                            "car_verification": proof, "car_response_path": response["response_file"],
                            "references": response["evidence"]}
                    record = configurations[digest]
                    # Reauthenticate retained CAR bytes before sharing one metadata file across instances.
                    actual, _ = read_car_file((ROOT / record["car_response_path"]).read_bytes(), digest)
                    if actual != (ROOT / record["file_ref"]["path"]).read_bytes():
                        raise ValueError("Authenticated metadata differs from retained JSON")
                    item["configuration_metadata"] = record
                except (OSError, ValueError, KeyError) as error:
                    item["gaps"].append("configuration_metadata: " + str(error))
            if all(name in values for name in ("market_collateral_before",
                    "market_conditional_tokens_before", "market_condition_before")):
                try:
                    token = "0x" + values["market_collateral_before"][-40:]
                    conditional_tokens = "0x" + values["market_conditional_tokens_before"][-40:]
                    collection, refs = rpc_read(scoped, "cohort-" + service + "-collection-id-before",
                        "eth_call", [{"to": conditional_tokens, "data": calldata(
                            "getCollectionId(bytes32,bytes32,uint256)", 0,
                            values["market_condition_before"], 1 << int(trade["outcomeIndex"]))}, before])
                    item["evidence"]["collection_id_before"] = refs
                    position, refs = rpc_read(scoped, "cohort-" + service + "-position-id-before",
                        "eth_call", [{"to": conditional_tokens, "data": calldata(
                            "getPositionId(address,bytes32)", token, collection)}, before])
                    item["evidence"]["position_id_before"] = refs
                    item["collection_id"], item["position_id"] = collection, str(int(position, 16))
                except (OSError, ValueError, KeyError) as error:
                    item["gaps"].append("position_id_before: " + str(error))
        except (OSError, ValueError, KeyError) as error:
            item["gaps"].append(str(error))
        write(run / f"checkpoint-{rank:02}.json", summary)
        print(json.dumps({"rank": rank, "service_id": service, "evidence_items": len(item["evidence"]),
                          "gaps": item["gaps"], "safe_window": item.get("safe_window")}, ensure_ascii=False), flush=True)
    write(run / "summary.json", summary)
    print(json.dumps({"directory": str(run.relative_to(ROOT)), "candidates": len(rows),
                      "scores_computed": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
