"""Retain one bounded, operator-fixed Gnosis identity probe; no task submission."""

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

from reputation_core.admission import ProbeObservation
from reputation_platform.safe_http import PublicTarget, SafeHttpClient

RPC = "https://rpc.gnosischain.com"
REGISTRY = "0x8004a169fb4a3325136eb29fa0ceb6d2e539a432"
MECH = "0xc05e7412439bd7e91730a6880e18d5d5873f632c"
SERVICE_REGISTRY = "0x9338b5153ae39bb89f50468e608ed9d764b755fd"
BRIDGER = "0x6e8f740f23f07ce129daa59786926feca8c2d2f3"
REGISTRATION = "https://marketplace.olas.network/api/erc8004/gnosis/ai-agents/2182"
CHAIN_URI = "https://marketplace.olas.network/erc8004/gnosis/ai-agents/2182"
REQUEST = "0x1ebd17f97038d3a14148566de635eab9901371bf904262f5498331b0c62921ce"
DELIVER = "0xb0d013658abb05dd269ff3ab257175d5ae3fa4107d4e142abd96e947cd5cb06f"
HASH = re.compile(r"0x[0-9a-fA-F]{64}")
CONFIG = ROOT / "configs/trusted-gnosis.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def word(value: object) -> bytes:
    if not isinstance(value, str) or not HASH.fullmatch(value):
        raise ValueError("Expected one ABI word")
    return bytes.fromhex(value[2:])


def abi_string(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"0x(?:[0-9a-fA-F]{2})+", value):
        raise ValueError("Expected ABI string result")
    raw = bytes.fromhex(value[2:])
    if len(raw) < 64 or int.from_bytes(raw[:32]) != 32:
        raise ValueError("Invalid ABI string offset")
    length = int.from_bytes(raw[32:64])
    if len(raw) != 64 + ((length + 31) // 32) * 32 or any(raw[64 + length:]):
        raise ValueError("Invalid ABI string size or padding")
    return raw[64:64 + length].decode("utf-8")


def address(value: object) -> str:
    raw = word(value)
    if any(raw[:12]) or not any(raw[12:]):
        raise ValueError("Invalid address word")
    return "0x" + raw[12:].hex()


def retained_identity(directory: Path) -> tuple[dict, list[dict]]:
    runtime = (ROOT / "runtime").resolve()
    if directory == runtime or not directory.is_dir() or not directory.is_relative_to(runtime):
        raise ValueError("--identity-run must be an existing runtime directory")
    expected, values, files = targets(), {}, []
    for target in expected:
        observation_file = directory / f"{target.key}.observation.json"
        observation = ProbeObservation.model_validate_json(observation_file.read_bytes())
        response_file = directory / f"{target.key}.response.bin"
        if target.key not in ("chain-id", "head"):
            target.json_body["params"][0 if target.key == "snapshot-header" else 1] = hex(int(values["head"], 16) - 64)
        if (observation.url != RPC or observation.method != "POST" or observation.http_status != 200
            or observation.error_kind or not observation.body_complete or observation.response_file != response_file.name
            or observation.response_sha256 != digest(response_file)
            or json.loads(observation.request_json) != target.json_body):
            raise ValueError("Retained identity request or response failed verification")
        envelope = json.loads(response_file.read_bytes())
        if envelope.get("jsonrpc") != "2.0" or envelope.get("id") != target.json_body["id"] or "error" in envelope:
            raise ValueError("Retained identity RPC envelope is invalid")
        values[target.key] = envelope["result"]
        files.extend({"path": path.relative_to(ROOT).as_posix(), "sha256": digest(path)}
                     for path in (observation_file, response_file))
    snapshot = int(values["head"], 16) - 64
    header = values["snapshot-header"]
    if (int(values["chain-id"], 16) != 100 or header["number"] != hex(snapshot)
        or not HASH.fullmatch(header["hash"]) or address(values["registration-owner"]) != BRIDGER
        or abi_string(values["registration-uri"]) != CHAIN_URI or values["mech-code"] == "0x"):
        raise ValueError("Retained identity is outside the reviewed fixed scope")
    files.append({"path": (directory / "manifest.json").relative_to(ROOT).as_posix(),
                  "sha256": digest(directory / "manifest.json")})
    return {"snapshot_block": snapshot, "snapshot_hash": header["hash"], "registration_owner": BRIDGER}, files


def decode_event(log: dict, snapshot: int, operator: str, expected_mech: str = MECH) -> dict:
    topics = log["topics"]
    kind = {REQUEST: "Request", DELIVER: "Deliver"}[topics[0]]
    block = int(log["blockNumber"], 16)
    if (log["address"].lower() != expected_mech or log.get("removed") is not False
        or not snapshot - 199 <= block <= snapshot or not HASH.fullmatch(log["blockHash"])
        or not HASH.fullmatch(log["transactionHash"]) or address(topics[1]) != expected_mech
        or len(topics) != (2 if kind == "Request" else 3)):
        raise ValueError("Unexpected event emitter, indexing or fixed window")
    if kind == "Deliver" and address(topics[2]) != operator:
        raise ValueError("Delivery operator differs from the verified service operator")
    if not re.fullmatch(r"0x(?:[0-9a-fA-F]{2})+", log["data"]):
        raise ValueError("Invalid event data")
    data = bytes.fromhex(log["data"][2:])
    offset = 64 if kind == "Request" else 96
    if len(data) < offset + 32 or int.from_bytes(data[offset - 32:offset]) != offset:
        raise ValueError("Invalid event bytes offset")
    size = int.from_bytes(data[offset:offset + 32])
    if len(data) != offset + 32 + ((size + 31) // 32) * 32 or any(data[offset + 32 + size:]):
        raise ValueError("Invalid event bytes size or padding")
    return {"kind": kind, "mech": expected_mech, "request_id": "0x" + data[:32].hex(), "data_hex": "0x" + data[offset + 32:offset + 32 + size].hex(),
            "block": block, "block_hash": log["blockHash"], "tx_hash": log["transactionHash"],
            "transaction_index": int(log["transactionIndex"], 16), "log_index": int(log["logIndex"], 16),
            "operator": operator if kind == "Deliver" else None}


def followup(args, source: dict) -> int:
    facts, identity_sources = retained_identity((ROOT / args.identity_run).resolve())
    snapshot = facts["snapshot_block"]
    specifications = [("mech-service-id", MECH, "0xda20ec6a"),
                      ("mech-service-registry", MECH, "0xcbcf252a"),
                      ("mech-operator", MECH, "0xe7f43c68"),
                      ("bridger-agent-id", BRIDGER, "0xe0e3e127" + f"{2182:064x}")]
    planned = [PublicTarget("chain-registration-document", CHAIN_URI)]
    planned.extend(PublicTarget(key, RPC, "POST", json_body={"jsonrpc": "2.0", "id": index,
                   "method": "eth_call", "params": [{"to": contract, "data": data}, hex(snapshot)]})
                   for index, (key, contract, data) in enumerate(specifications, 1))
    planned.append(PublicTarget("history-events", RPC, "POST", json_body={"jsonrpc": "2.0", "id": 5,
                   "method": "eth_getLogs", "params": [{"address": MECH, "fromBlock": hex(snapshot - 199),
                   "toBlock": hex(snapshot), "topics": [[REQUEST, DELIVER]]}]}))
    plan = {"execution_enabled": args.execute_public_readonly, "measurement_purpose": "background",
            "request_limit": 8, "planned_count": len(planned), "retries": 0, "scores_computed": False,
            "fixed_snapshot": facts, "identity_sources": identity_sources, "registration_source": source,
            "config": {"path": CONFIG.relative_to(ROOT).as_posix(), "sha256": digest(CONFIG)},
            "contract_sources": ["https://github.com/valory-xyz/autonolas-marketplace/blob/main/abis/0.8.28/MechFixedPriceNative.json",
                                 "https://github.com/valory-xyz/autonolas-registries/blob/main/contracts/8004/IdentityRegistryBridger.sol"],
            "planned_requests": [{"key": target.key, "url": target.url, "json": target.json_body} for target in planned]}
    print(json.dumps(plan, indent=2))
    if not args.execute_public_readonly:
        return 0
    now = datetime.now(timezone.utc)
    run = ROOT / "runtime" / f"olas-binding-probe-{now:%Y%m%dT%H%M%SZ}-{secrets.token_hex(4)}"
    run.mkdir()
    (run / "manifest.json").write_text(json.dumps({"started_at": now.isoformat(), **plan}, indent=2), encoding="utf-8")
    results, stop, events = [], None, []
    with SafeHttpClient(tuple(planned), enabled=True, proxy=args.proxy, max_requests=8) as client:
        for target in planned:
            observation = client.fetch(target.key, run)
            results.append({"key": target.key, "http_status": observation.http_status, "error_kind": observation.error_kind})
            if observation.error_kind or not observation.body_complete or observation.http_status != 200:
                stop = observation.error_kind or "incomplete_or_unsuccessful_http"
                break
            try:
                payload = json.loads((run / observation.response_file).read_bytes())
                if target.method == "GET":
                    expected = "eip155:100:" + REGISTRY
                    if (not any(item.get("agentId") == 2182 and str(item.get("agentRegistry", "")).lower() == expected
                                for item in payload.get("registrations", []))
                        or not any(item.get("endpoint") == f"https://mech-analytics-api.autonolas.tech/v1/metrics/mech/100/{MECH}"
                                   for item in payload.get("services", []))):
                        raise ValueError("Actual chain URI document does not bind the reviewed identity and Mech")
                    facts["chain_uri_document_sha256"] = observation.response_sha256
                else:
                    if (not isinstance(payload, dict) or payload.get("jsonrpc") != "2.0" or "error" in payload
                        or payload.get("id") != target.json_body["id"] or "result" not in payload):
                        raise ValueError("Invalid RPC envelope")
                    value = payload["result"]
                    if target.key in ("mech-service-id", "bridger-agent-id"):
                        number = int.from_bytes(word(value))
                        if number != 2182:
                            raise ValueError("Service/agent identity differs from the explicit bridger mapping")
                        facts[target.key] = number
                    elif target.key == "mech-service-registry":
                        if address(value) != SERVICE_REGISTRY:
                            raise ValueError("Mech uses a different ServiceRegistry than the official Gnosis deployment")
                        facts["service_registry"] = SERVICE_REGISTRY
                    elif target.key == "mech-operator":
                        facts["service_operator"] = address(value)
                    elif target.key == "history-events":
                        if not isinstance(value, list):
                            raise ValueError("Logs result is not a list")
                        events = [decode_event(log, snapshot, facts["service_operator"]) for log in value]
                print(f"{target.key}: HTTP=200 valid=ok")
            except (ValueError, TypeError, KeyError, IndexError, AttributeError):
                stop = "invalid_rpc_result_or_identity_binding"
                break
    requests = {event["request_id"]: event for event in events if event["kind"] == "Request"}
    pairs = [{"request": requests[event["request_id"]], "delivery": event} for event in events
             if event["kind"] == "Deliver" and event["request_id"] in requests
             and (requests[event["request_id"]]["block"], requests[event["request_id"]]["transaction_index"], requests[event["request_id"]]["log_index"])
                 < (event["block"], event["transaction_index"], event["log_index"])]
    selected = max(pairs, key=lambda pair: (pair["delivery"]["block"], pair["delivery"]["log_index"])) if pairs else None
    result = {"requests_observed": len(results), "stopped_reason": stop, "results": results,
              "facts": facts, "events": events, "selected_pair": selected, "scores_computed": False,
              "probe_status": "UNKNOWN" if stop else "BINDING_AND_WINDOW_RETAINED",
              "limitations": ["No receipt/calldata verification or independent prediction correctness evaluation",
                              "The public chain-URI document can change; its exact fetched bytes are retained"]}
    (run / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"evidence_directory={run.relative_to(ROOT).as_posix()}; events={len(events)}; matched_pairs={len(pairs)}; stopped_reason={stop}")
    return 1 if stop else 0


def locate_history(args, source: dict) -> int:
    if not args.identity_run:
        raise ValueError("Historical indexing requires --identity-run; prior identity calls are not repeated")
    facts, inputs = retained_identity((ROOT / args.identity_run).resolve())
    query = """{ delivers(first:1, orderBy:blockNumber, orderDirection:desc,
      where:{service_:{id:"2182"}, mech:"MECH", blockNumber_lte:"BLOCK"}) {
      blockNumber transactionHash requestId
      marketplaceDelivery { ipfsHashBytes mechServiceMultisig }
      request { id blockNumber transactionHash marketplaceRequest { ipfsHashBytes } }
    } }""".replace("MECH", MECH).replace("BLOCK", str(facts["snapshot_block"]))
    limit = 3 if args.earlier_history else 1
    if args.earlier_history:
        query = """{ delivers(first:3, orderBy:blockTimestamp, orderDirection:desc,
          where:{service_:{id:"2182"}, mech:"MECH", blockTimestamp_lt:"1790812800"}) {
          id requestId mech blockNumber blockTimestamp transactionHash
          marketplaceDelivery { ipfsHashBytes mechServiceMultisig }
          request { id blockNumber blockTimestamp transactionHash marketplaceRequest { ipfsHashBytes } }
        } }""".replace("MECH", MECH)
    target = PublicTarget("latest-indexed-delivery", "https://api.subgraph.autonolas.tech/api/proxy/marketplace-gnosis",
                          "POST", json_body={"query": query})
    plan = {"execution_enabled": args.execute_public_readonly, "measurement_purpose": "background",
            "request_limit": 1, "retries": 0, "scores_computed": False, "identity_sources": inputs,
            "registration_source": source, "fixed_snapshot": facts,
            "query_source": "https://github.com/valory-xyz/autonolas-frontend-mono/blob/main/apps/marketplace/common-util/graphql/service-activity.ts",
            "schema_source": "https://github.com/valory-xyz/autonolas-subgraph/blob/main/subgraphs/marketplace/schema.graphql",
            "selection": {"limit": limit, "cutoff_before": "2026-10-01T00:00:00Z" if args.earlier_history else None,
                          "rule": "Chronological selection; never filtered by predicted correctness"},
            "planned_requests": [{"key": target.key, "url": target.url, "json": target.json_body}]}
    print(json.dumps(plan, indent=2))
    if not args.execute_public_readonly:
        return 0
    now = datetime.now(timezone.utc)
    run = ROOT / "runtime" / f"olas-history-index-{now:%Y%m%dT%H%M%SZ}-{secrets.token_hex(4)}"
    run.mkdir()
    (run / "manifest.json").write_text(json.dumps({"started_at": now.isoformat(), **plan}, indent=2), encoding="utf-8")
    with SafeHttpClient((target,), enabled=True, proxy=args.proxy, max_requests=1) as client:
        observation = client.fetch(target.key, run)
    stop, rows = observation.error_kind, []
    if not stop and observation.body_complete and observation.http_status == 200:
        try:
            payload = json.loads((run / observation.response_file).read_bytes())
            rows = payload["data"]["delivers"]
            if payload.get("errors") or not isinstance(rows, list) or len(rows) > limit:
                raise ValueError("Invalid bounded historical query result")
            for hint in rows:
                if not HASH.fullmatch(hint["transactionHash"]) or not 0 <= int(hint["blockNumber"]) <= facts["snapshot_block"]:
                    raise ValueError("Invalid indexed transaction hint")
                if args.earlier_history and (hint["mech"].lower() != MECH or int(hint["blockTimestamp"]) >= 1790812800):
                    raise ValueError("Indexed historical hint is outside the declared cutoff or Mech")
        except (ValueError, TypeError, KeyError):
            stop = "invalid_index_result"
    elif not stop:
        stop = "incomplete_or_unsuccessful_http"
    result = {"stopped_reason": stop, "hint": rows[0] if len(rows) == 1 else None, "hints": rows, "scores_computed": False,
              "scope": "Discovery hint only; index content is not an independently verified chain event"}
    (run / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"evidence_directory={run.relative_to(ROOT).as_posix()}; hints={len(rows)}; stopped_reason={stop}")
    return 1 if stop else 0


def collect_task(args, source: dict) -> int:
    if not args.identity_run or not args.binding_run:
        raise ValueError("Task collection requires --identity-run and --binding-run")
    facts, inputs = retained_identity((ROOT / args.identity_run).resolve())
    runtime = (ROOT / "runtime").resolve()

    def retained(directory_value: str, key: str, url: str, method: str, expected_request: dict | None = None):
        directory = (ROOT / directory_value).resolve()
        if directory == runtime or not directory.is_dir() or not directory.is_relative_to(runtime):
            raise ValueError("Task source directories must be inside runtime")
        observation_file, response_file = directory / f"{key}.observation.json", directory / f"{key}.response.bin"
        observation = ProbeObservation.model_validate_json(observation_file.read_bytes())
        manifest_file = directory / "manifest.json"
        manifest = json.loads(manifest_file.read_bytes())
        planned = next(item for item in manifest["planned_requests"] if item["key"] == key)
        body = json.loads(observation.request_json) if observation.request_json else None
        if (observation.url != url or observation.method != method or observation.http_status != 200
            or observation.error_kind or not observation.body_complete or observation.response_file != response_file.name
            or observation.response_sha256 != digest(response_file) or body != planned.get("json")
            or (expected_request is not None and body != expected_request)):
            raise ValueError("Retained task hint or operator request failed verification")
        inputs.extend({"path": path.relative_to(ROOT).as_posix(), "sha256": digest(path)}
                      for path in (manifest_file, observation_file, response_file))
        return json.loads(response_file.read_bytes()), body

    indexed, indexed_body = retained(args.task_index_run, "latest-indexed-delivery",
        "https://api.subgraph.autonolas.tech/api/proxy/marketplace-gnosis", "POST")
    query = indexed_body.get("query", "")
    if any(value not in query for value in ("first:1", MECH, 'id:"2182"', f'blockNumber_lte:"{facts["snapshot_block"]}"')):
        raise ValueError("The retained task index is outside the fixed one-result query")
    hints = indexed["data"]["delivers"]
    if indexed.get("errors") or len(hints) != 1:
        raise ValueError("Exactly one indexed historical task is required")
    hint = hints[0]
    operator_body = {"jsonrpc": "2.0", "id": 3, "method": "eth_call", "params": [
        {"to": MECH, "data": "0xe7f43c68"}, hex(facts["snapshot_block"])]}
    operator_response, _ = retained(args.binding_run, "mech-operator", RPC, "POST", operator_body)
    if operator_response.get("error") or operator_response.get("id") != 3:
        raise ValueError("Invalid retained operator response")
    operator = address(operator_response["result"])
    request_id = hint["requestId"]
    request_digest = hint["request"]["marketplaceRequest"]["ipfsHashBytes"]
    delivery_digest = hint["marketplaceDelivery"]["ipfsHashBytes"]
    for value in (request_id, request_digest, delivery_digest, hint["transactionHash"], hint["request"]["transactionHash"]):
        word(value)
    request_block, delivery_block = int(hint["request"]["blockNumber"]), int(hint["blockNumber"])
    if (hint["request"]["id"] != request_id or not 0 <= request_block <= delivery_block <= facts["snapshot_block"]
        or hint["marketplaceDelivery"]["mechServiceMultisig"].lower() != operator):
        raise ValueError("Historical discovery hint has inconsistent identities or order")
    calls = []
    for prefix, tx_hash, block in (("request", hint["request"]["transactionHash"], request_block),
                                    ("delivery", hint["transactionHash"], delivery_block)):
        calls.extend([(prefix + "-transaction", "eth_getTransactionByHash", [tx_hash]),
                      (prefix + "-receipt", "eth_getTransactionReceipt", [tx_hash]),
                      (prefix + "-header", "eth_getBlockByNumber", [hex(block), False])])
    planned = [PublicTarget(key, RPC, "POST", json_body={"jsonrpc": "2.0", "id": index,
               "method": method, "params": params}) for index, (key, method, params) in enumerate(calls, 1)]
    request_url = "https://gateway.autonolas.tech/ipfs/f01701220" + request_digest[2:]
    planned.extend([PublicTarget("request-content", request_url + ("/metadata.json" if args.request_metadata_file else "")),
                    PublicTarget("delivery-content", "https://gateway.autonolas.tech/ipfs/f01701220" + delivery_digest[2:] + "/" + str(int(request_id, 16)))])
    cached, cached_sources, cached_digests = {}, {}, {}
    if args.resume_task_run:
        for target in planned[:6]:
            cached[target.key], _ = retained(args.resume_task_run, target.key, RPC, "POST", target.json_body)
            cached_sources[target.key] = args.resume_task_run
    if args.request_metadata_file:
        if not args.content_run:
            raise ValueError("The metadata filename requires --content-run containing the actual directory listing")
        directory = (ROOT / args.content_run).resolve()
        if not directory.is_relative_to(runtime):
            raise ValueError("Content source must be inside runtime")
        observation_file = directory / "request-directory.observation.json"
        response_file = directory / "request-directory.response.bin"
        observation = ProbeObservation.model_validate_json(observation_file.read_bytes())
        expected_link = '/ipfs/f01701220' + request_digest[2:] + '/metadata.json'
        if (observation.url != request_url + "/" or observation.http_status != 200 or observation.error_kind
            or not observation.body_complete or observation.response_sha256 != digest(response_file)
            or f'href="{expected_link}"' not in response_file.read_text(encoding="utf-8")):
            raise ValueError("The retained directory does not explicitly list this metadata filename")
        inputs.extend({"path": path.relative_to(ROOT).as_posix(), "sha256": digest(path)}
                      for path in (observation_file, response_file))
    if args.content_run:
        target = planned[-1]
        cached[target.key], _ = retained(args.content_run, target.key, target.url, "GET")
        cached_sources[target.key] = args.content_run
        cached_digests[target.key] = digest((ROOT / args.content_run) / f"{target.key}.response.bin")
    plan = {"execution_enabled": args.execute_public_readonly, "measurement_purpose": "background",
            "request_limit": 8, "new_request_limit": len(planned) - len(cached), "retries": 0, "scores_computed": False, "inputs": inputs,
            "registration_source": source, "request_id": request_id,
            "planned_requests": [{"key": target.key, "url": target.url, "json": target.json_body} for target in planned]}
    print(json.dumps(plan, indent=2))
    if not args.execute_public_readonly:
        return 0
    now = datetime.now(timezone.utc)
    run = ROOT / "runtime" / f"olas-task-probe-{now:%Y%m%dT%H%M%SZ}-{secrets.token_hex(4)}"
    run.mkdir()
    (run / "manifest.json").write_text(json.dumps({"started_at": now.isoformat(), **plan}, indent=2), encoding="utf-8")
    values, checked, observations, stop = {}, {}, [], None
    with SafeHttpClient(tuple(planned), enabled=True, proxy=args.proxy, max_requests=8) as client:
        for target in planned:
            observation = None
            if target.key in cached:
                payload = cached[target.key]
                observations.append({"key": target.key, "reused_from": cached_sources[target.key]})
            else:
                observation = client.fetch(target.key, run)
                observations.append({"key": target.key, "http_status": observation.http_status, "error_kind": observation.error_kind})
                if observation.error_kind or not observation.body_complete or observation.http_status != 200:
                    stop = observation.error_kind or "incomplete_or_unsuccessful_http"
                    break
            try:
                if target.key not in cached:
                    payload = json.loads((run / observation.response_file).read_bytes())
                if target.method == "GET":
                    values[target.key] = {"json_type": type(payload).__name__, "response_sha256":
                                         cached_digests[target.key] if target.key in cached else observation.response_sha256}
                else:
                    if payload.get("jsonrpc") != "2.0" or payload.get("id") != target.json_body["id"] or "error" in payload or payload.get("result") is None:
                        raise ValueError("Invalid historical RPC result")
                    values[target.key] = payload["result"]
                if target.key == "delivery-header":
                    for prefix, block, expected_digest in (("request", request_block, request_digest),
                                                           ("delivery", delivery_block, delivery_digest)):
                        tx, receipt, header = (values[prefix + suffix] for suffix in ("-transaction", "-receipt", "-header"))
                        tx_hash = hint["request"]["transactionHash"] if prefix == "request" else hint["transactionHash"]
                        if (tx["hash"] != tx_hash or receipt["transactionHash"] != tx_hash or receipt["status"] != "0x1"
                            or int(tx["chainId"], 16) != 100 or header["number"] != hex(block)
                            or tx["blockNumber"] != hex(block) or receipt["blockNumber"] != hex(block)
                            or tx["blockHash"] != header["hash"] or receipt["blockHash"] != header["hash"]
                            or tx["transactionIndex"] != receipt["transactionIndex"]):
                            raise ValueError("Historical transaction, receipt and header do not bind")
                        matching = [decode_event(log, delivery_block, operator,
                                    expected_mech=log["address"].lower() if prefix == "request" else MECH)
                                    for log in receipt["logs"]
                                    if (prefix == "request" or log["address"].lower() == MECH)
                                    and log.get("topics", [None])[0] == (REQUEST if prefix == "request" else DELIVER)]
                        matching = [event for event in matching if event["request_id"] == request_id]
                        if (len(matching) != 1 or matching[0]["data_hex"] != expected_digest
                            or matching[0]["tx_hash"] != tx_hash or matching[0]["block_hash"] != header["hash"]
                            or matching[0]["transaction_index"] != int(tx["transactionIndex"], 16)):
                            raise ValueError("Actual Request/Deliver event differs from the indexed task or CID")
                        checked[prefix] = {"event": matching[0], "timestamp": int(header["timestamp"], 16),
                                           "transaction_from": tx["from"], "transaction_to": tx["to"]}
                    if checked["request"]["timestamp"] > checked["delivery"]["timestamp"]:
                        raise ValueError("Request timestamp follows delivery")
                print(f"{target.key}: {'reused' if target.key in cached else 'HTTP=200'} valid=ok")
            except (ValueError, TypeError, KeyError, IndexError):
                stop = "historical_evidence_binding_or_content_invalid"
                break
    result = {"stopped_reason": stop, "observations": observations, "checked_chain_events": checked,
              "contents": {key: value for key, value in values.items() if key.endswith("-content")},
              "scores_computed": False, "request_id": request_id,
              "limitations": ["Discovery and feasibility evidence only; no formal scoring samples",
                              "The original priority Mech and actual delivery Mech may differ; only actual delivery is attributed",
                              "Historical calldata, operator state and registered-at-task chronology are not fully verified",
                              "No independent prediction outcome or IPFS UnixFS/DAG content-address verification"]}
    (run / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"evidence_directory={run.relative_to(ROOT).as_posix()}; requests={len(observations)}; stopped_reason={stop}")
    return 1 if stop else 0


def load_source(directory: Path) -> dict:
    runtime = (ROOT / "runtime").resolve()
    if directory == runtime or not directory.is_dir() or not directory.is_relative_to(runtime):
        raise ValueError("--source-run must be an existing directory in this repository's runtime")
    observation_file = directory / "olas-registration-2182.observation.json"
    observation = ProbeObservation.model_validate_json(observation_file.read_bytes())
    response_file = directory / "olas-registration-2182.response.bin"
    manifest_file = directory / "manifest.json"
    manifest = json.loads(manifest_file.read_bytes())
    if (observation.url != REGISTRATION or observation.method != "GET" or observation.http_status != 200
        or observation.error_kind or not observation.body_complete
        or observation.response_file != response_file.name or observation.response_sha256 != digest(response_file)
        or not any(item.get("key") == observation.request_key and item.get("url") == REGISTRATION
                   and item.get("method") == "GET" for item in manifest["planned_requests"])):
        raise ValueError("Retained registration observation does not match its declared source and bytes")
    payload = json.loads(response_file.read_bytes())
    expected_registry = "eip155:100:" + REGISTRY
    if not any(item.get("agentId") == 2182 and str(item.get("agentRegistry", "")).lower() == expected_registry
               for item in payload.get("registrations", [])):
        raise ValueError("Retained registration does not declare the reviewed full identity")
    if not any(item.get("endpoint") == f"https://mech-analytics-api.autonolas.tech/v1/metrics/mech/100/{MECH}"
               for item in payload.get("services", [])):
        raise ValueError("Retained registration does not declare the reviewed Mech instance")
    return {"files": [{"path": path.relative_to(ROOT).as_posix(), "sha256": digest(path)}
                       for path in (manifest_file, observation_file, response_file)],
            "association_scope": "The official registration JSON declares the Mech; execution control remains unverified"}


def targets() -> tuple[PublicTarget, ...]:
    calls = [("chain-id", "eth_chainId", []), ("head", "eth_blockNumber", []),
             ("snapshot-header", "eth_getBlockByNumber", ["SNAPSHOT", False]),
             ("registration-owner", "eth_call", [{"to": REGISTRY, "data": "0x6352211e" + f"{2182:064x}"}, "SNAPSHOT"]),
             ("registration-uri", "eth_call", [{"to": REGISTRY, "data": "0xc87b56dd" + f"{2182:064x}"}, "SNAPSHOT"]),
             ("mech-code", "eth_getCode", [MECH, "SNAPSHOT"])]
    return tuple(PublicTarget(key, RPC, "POST", json_body={"jsonrpc": "2.0", "id": index,
                 "method": method, "params": params}) for index, (key, method, params) in enumerate(calls, 1))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-run", required=True, help="Retained official registration run inside runtime")
    parser.add_argument("--identity-run", help="Reuse a verified identity run for the fixed binding and 200-block event window")
    parser.add_argument("--locate-history", action="store_true", help="One official indexed delivery hint; no log scan")
    parser.add_argument("--earlier-history", action="store_true", help="At most three deliveries before 2026-10-01T00:00Z, selected by time")
    parser.add_argument("--task-index-run", help="Collect one indexed task's original transactions, receipts, headers and CID files")
    parser.add_argument("--binding-run", help="Retained binding run supplying the independently read service operator")
    parser.add_argument("--resume-task-run", help="Reuse six retained historical RPC responses; issue only the two missing CID reads")
    parser.add_argument("--content-run", help="Reuse the retained delivery file and request CID directory listing")
    parser.add_argument("--request-metadata-file", action="store_true", help="Read metadata.json only when explicitly listed by the retained request CID directory")
    parser.add_argument("--execute-public-readonly", action="store_true")
    parser.add_argument("--proxy", help="Explicit operator proxy; required to execute")
    args = parser.parse_args()
    if args.execute_public_readonly and not args.proxy:
        parser.error("Execution requires --proxy")
    trusted = json.loads(CONFIG.read_bytes())
    if (trusted["chain_id"], trusted["rpc_url"], trusted["registry"], trusted["agent_id"], trusted["mech"]) != (100, RPC, REGISTRY, 2182, MECH):
        raise ValueError("The trusted configuration must match the reviewed fixed scope")
    source = load_source((ROOT / args.source_run).resolve())
    if args.task_index_run:
        return collect_task(args, source)
    if args.locate_history or args.earlier_history:
        return locate_history(args, source)
    if args.identity_run:
        return followup(args, source)
    planned = targets()
    plan = {"execution_enabled": args.execute_public_readonly, "measurement_purpose": "background",
            "rpc_url": RPC, "chain_id": 100, "request_limit": 8, "planned_count": len(planned),
            "retries": 0, "snapshot_rule": "head - 64", "metadata_rpc_accepted": False,
            "paid_calls": False, "writes": False, "scores_computed": False,
            "config": {"path": CONFIG.relative_to(ROOT).as_posix(), "sha256": digest(CONFIG)},
            "registration_source": source,
            "planned_requests": [{"key": target.key, "json": target.json_body} for target in planned]}
    print(json.dumps(plan, indent=2, ensure_ascii=False))
    if not args.execute_public_readonly:
        return 0
    now = datetime.now(timezone.utc)
    run = ROOT / "runtime" / f"olas-history-probe-{now:%Y%m%dT%H%M%SZ}-{secrets.token_hex(4)}"
    run.mkdir()
    (run / "manifest.json").write_text(json.dumps({"started_at": now.isoformat(), **plan}, indent=2), encoding="utf-8")
    results, facts, stop, snapshot = [], {}, None, None
    with SafeHttpClient(planned, enabled=True, proxy=args.proxy, max_requests=8) as client:
        for target in planned:
            observation = client.fetch(target.key, run)
            item = {"key": target.key, "http_status": observation.http_status, "error_kind": observation.error_kind}
            results.append(item)
            if observation.error_kind or not observation.body_complete or observation.http_status != 200:
                stop = observation.error_kind or "incomplete_or_unsuccessful_http"
                break
            try:
                response = json.loads((run / observation.response_file).read_bytes())
                if (not isinstance(response, dict) or response.get("jsonrpc") != "2.0"
                    or response.get("id") != target.json_body["id"] or "result" not in response or "error" in response):
                    stop = "rpc_error_or_invalid_envelope"
                    break
                value = response["result"]
                if target.key == "chain-id":
                    if int(value, 16) != 100:
                        stop = "unexpected_chain_id"
                        break
                    facts["chain_id"] = 100
                elif target.key == "head":
                    head = int(value, 16)
                    if head < 64:
                        raise ValueError("Head below snapshot offset")
                    snapshot = hex(head - 64)
                    facts.update(head=head, snapshot_block=int(snapshot, 16))
                    for pending in planned[2:]:
                        params = pending.json_body["params"]
                        params[0 if pending.key == "snapshot-header" else 1] = snapshot
                elif target.key == "snapshot-header":
                    if not isinstance(value, dict) or value.get("number") != snapshot or not HASH.fullmatch(value.get("hash", "")):
                        raise ValueError("Invalid snapshot header")
                    facts.update(snapshot_hash=value["hash"], snapshot_timestamp=int(value["timestamp"], 16))
                elif target.key == "registration-owner":
                    owner = word(value)
                    if any(owner[:12]) or not any(owner[12:]):
                        raise ValueError("Invalid registration owner")
                    facts["registration_owner"] = "0x" + owner[12:].hex()
                elif target.key == "registration-uri":
                    uri = abi_string(value)
                    facts.update(token_uri=uri, token_uri_matches_retained_registration_url=uri == REGISTRATION)
                elif target.key == "mech-code":
                    if not isinstance(value, str) or not re.fullmatch(r"0x(?:[0-9a-fA-F]{2})+", value):
                        raise ValueError("No Mech contract code at the snapshot")
                    facts["mech_code_sha256"] = hashlib.sha256(bytes.fromhex(value[2:])).hexdigest()
                item["rpc_result_valid"] = True
                print(f"{target.key}: HTTP=200 rpc=ok")
            except (ValueError, TypeError, KeyError, UnicodeError):
                stop = "invalid_rpc_result"
                break
    result = {"requests_observed": len(results), "stopped_reason": stop, "results": results, "facts": facts,
              "probe_status": "UNKNOWN" if stop else "IDENTITY_READS_RETAINED", "scores_computed": False,
              "remaining_gaps": ["ERC-8004 identity to Mech execution control is not yet independently proven",
                                 "No raw Request/Deliver historical task has been selected or evaluated"]}
    (run / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"evidence_directory={run.relative_to(ROOT).as_posix()}; stopped_reason={stop}")
    return 1 if stop else 0


if __name__ == "__main__":
    raise SystemExit(main())
