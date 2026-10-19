"""Locate one indexed ERC-8004 mint, then independently verify its receipt and block."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import secrets
from urllib.parse import urlsplit

from probe_olas_history import (ROOT, RPC, REGISTRY, BRIDGER, HASH, digest,
                               address, word)
from reputation_core import ProbeObservation
from reputation_platform.prediction_evidence import EvidenceStore, EvidenceUnavailable, PredictionProfile
from reputation_platform.safe_http import PublicTarget, SafeHttpClient

INDEXES = {"blockscout": f"https://gnosis.blockscout.com/api/v2/tokens/{REGISTRY}/instances/{{agent_id}}/transfers",
           "8004scan": "https://api.8004scan.io/api/v1/agents/100/{agent_id}"}
TRANSFER = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
LINKED = "0xed3b0677b72f7c613d36efedb855a37500f282c148335826c86ee2525c151391"
ZERO_WORD = "0x" + "0" * 64
ZERO_ADDRESS = "0x" + "0" * 40


def write_json(path: Path, data: object) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)


def retained_directory(value: str) -> Path:
    path, runtime = (ROOT / value).resolve(), (ROOT / "runtime").resolve()
    if not path.is_dir() or path == runtime or not path.is_relative_to(runtime):
        raise ValueError("Input must be an existing project runtime directory")
    return path


def read(target: PublicTarget, run: Path, proxy: str, retained: Path | None = None):
    if retained is None:
        stop_file = ROOT / "runtime/prediction-network-stops" / (urlsplit(target.url).hostname + ".json")
        if stop_file.is_file():
            raise ValueError("This host previously stopped after access, payment or rate-limit response")
        write_json(run / f"{target.key}.manifest.json", {"created_at": datetime.now(timezone.utc).isoformat(),
            "measurement_purpose": "background", "request_limit": 1, "retries": 0,
            "url": target.url, "method": target.method, "json": target.json_body})
        with SafeHttpClient((target,), enabled=True, proxy=proxy, max_requests=1,
                            timeout_seconds=30) as client:
            obs = client.fetch(target.key, run)
        if obs.http_status in (401, 402, 403, 429):
            stop_file.parent.mkdir(exist_ok=True)
            if not stop_file.exists():
                write_json(stop_file, {"host": urlsplit(target.url).hostname, "reason": f"HTTP {obs.http_status}",
                    "source_run": run.relative_to(ROOT).as_posix()})
    else:
        obs = ProbeObservation.model_validate_json((retained / f"{target.key}.observation.json").read_bytes())
    base = retained or run
    if (obs.request_key != target.key or obs.url != target.url or obs.method != target.method
        or (json.loads(obs.request_json) if obs.request_json else None) != target.json_body
        or obs.http_status != 200 or obs.error_kind or not obs.body_complete
        or obs.response_file != f"{target.key}.response.bin"
        or obs.response_sha256 != digest(base / obs.response_file)):
        raise ValueError(f"{target.key}: unavailable, incomplete or mismatched retained read (HTTP={obs.http_status}, error={obs.error_kind})")
    payload = json.loads((base / obs.response_file).read_bytes())
    print(f"{'retained' if retained else 'read'} {target.key}: HTTP=200", flush=True)
    if target.method == "POST":
        if (payload.get("jsonrpc") != "2.0" or payload.get("id") != target.json_body["id"]
            or "error" in payload or "result" not in payload or payload["result"] is None):
            raise ValueError(f"{target.key}: RPC result unavailable; inspect retained response")
        payload = payload["result"]
    return payload


def proof(run: Path, key: str, method: str, params: list, value: object) -> dict:
    return {"method": method, "params": params, "value": value,
            "evidence": [{"path": path.relative_to(ROOT).as_posix(), "sha256": digest(path)}
                         for path in (run / f"{key}.observation.json", run / f"{key}.response.bin")]}


def retained_snapshot(directory: Path, profile: PredictionProfile) -> tuple[dict, list[dict]]:
    specifications = (("chain-id", 1, "eth_chainId", []), ("head", 2, "eth_blockNumber", []),
                      ("snapshot-header", 3, "eth_getBlockByNumber", [hex(profile.snapshot_block), False]))
    values, inputs = {}, []
    for key, request_id, method, params in specifications:
        target = PublicTarget(key, RPC, "POST", json_body={"jsonrpc": "2.0", "id": request_id,
                                                         "method": method, "params": params})
        values[key] = read(target, directory, "", directory)
        inputs.extend(proof(directory, key, method, params, values[key])["evidence"])
    if (int(values["chain-id"], 16) != 100 or int(values["head"], 16) != profile.confirmation_head
            or int(values["snapshot-header"]["number"], 16) != profile.snapshot_block
            or values["snapshot-header"]["hash"].lower() != profile.snapshot_hash):
        raise ValueError("Retained chain, confirmation head or snapshot differs from the operator profile")
    return {"snapshot_block": profile.snapshot_block, "snapshot_hash": profile.snapshot_hash,
            "confirmation_head": profile.confirmation_head}, inputs


def supplement(identity_run: Path, run: Path, result: dict) -> Path:
    head_obs_path = identity_run / "head.observation.json"
    head_obs = ProbeObservation.model_validate_json(head_obs_path.read_bytes())
    head_body = identity_run / "head.response.bin"
    envelope = json.loads(head_body.read_bytes())
    if (head_obs.url != RPC or head_obs.method != "POST" or head_obs.http_status != 200
        or head_obs.error_kind or not head_obs.body_complete or head_obs.response_sha256 != digest(head_body)
        or json.loads(head_obs.request_json) != {"jsonrpc": "2.0", "id": 2, "method": "eth_blockNumber", "params": []}
        or envelope.get("id") != 2 or envelope.get("jsonrpc") != "2.0" or "error" in envelope):
        raise ValueError("Retained head proof does not match its source observation")
    data = {"head": proof(identity_run, "head", "eth_blockNumber", [], envelope["result"])}
    if result["status"] == "REGISTRATION_PROVEN":
        data.update(registration_time=result["registered_at"], registration_evidence=result["proofs"])
    else:
        data["registration_gap"] = result.get("reason", "Actual registration receipt/header not proven")
    now = datetime.now(timezone.utc)
    output = ROOT / "runtime" / f"olas-identity-supplement-{now:%Y%m%dT%H%M%SZ}-{secrets.token_hex(4)}"
    output.mkdir()
    paths = {head_obs_path, head_body, run / "manifest.json", run / "result.json",
             *run.glob("*.observation.json"), *run.glob("*.response.bin")}
    references = json.loads((run / "manifest.json").read_bytes())["inputs"]
    for item in result.get("proofs", {}).values():
        references.extend(item["evidence"])
    for item in references:
        path = (ROOT / item["path"]).resolve()
        if (not any(path.is_relative_to(ROOT / base) for base in ("runtime", "configs/pilots"))
                or any(part.lower() in {"secrets", "platform-config"} or ".private" in part.lower() for part in path.parts)
                or digest(path) != item["sha256"]):
            raise ValueError("A supplementary source differs from its frozen digest")
        paths.add(path)
    write_json(output / "identity-supplement.json", data)
    write_json(output / "manifest.json", {"created_at": now.isoformat(), "network_requests_performed": 0,
        "scores_computed": False, "inputs": [{"path": path.relative_to(ROOT).as_posix(), "sha256": digest(path)}
                                               for path in sorted(paths)],
        "outputs": [{"path": (output / "identity-supplement.json").relative_to(ROOT).as_posix(),
                     "sha256": digest(output / "identity-supplement.json")}]})
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, default=Path("configs/pilots/olas-predict-2182-v1.json"))
    parser.add_argument("--identity-run", required=True)
    parser.add_argument("--index-run", help="Reuse one previously retained index response; no repeat GET")
    parser.add_argument("--index-provider", choices=tuple(INDEXES), default="8004scan")
    parser.add_argument("--reuse-run", action="append", default=[], help="Reuse exact retained RPC requests across mint batches")
    parser.add_argument("--execute-public-readonly", action="store_true")
    parser.add_argument("--proxy")
    args = parser.parse_args()
    if args.execute_public_readonly and not args.proxy:
        parser.error("Actual execution requires explicit --proxy")
    profile_path = (ROOT / args.profile).resolve()
    if not profile_path.is_relative_to(ROOT / "configs/pilots") or profile_path.suffix != ".json":
        parser.error("Profile must be an operator JSON under configs/pilots")
    profile = PredictionProfile.load(profile_path)
    identity_run = retained_directory(args.identity_run)
    snapshot, inputs = retained_snapshot(identity_run, profile)
    inputs.append({"path": profile_path.relative_to(ROOT).as_posix(), "sha256": digest(profile_path)})
    index_run = retained_directory(args.index_run) if args.index_run else None
    if index_run:
        inputs.extend({"path": path.relative_to(ROOT).as_posix(), "sha256": digest(path)}
                      for path in (index_run / "registration-index.observation.json", index_run / "registration-index.response.bin"))
    index_url = INDEXES[args.index_provider].format(agent_id=profile.agent_id)
    plan = {"execution_enabled": args.execute_public_readonly, "measurement_purpose": "background",
        "chain_id": 100, "candidate_key": profile.candidate_key, "agent_id": profile.agent_id,
        "olas_service_id": profile.service_id, "registry": REGISTRY,
        "bridger": BRIDGER, "rpc_url": RPC, "fixed_snapshot": snapshot, "inputs": inputs,
        "index_provider": args.index_provider, "index_url": index_url,
        "index_run_reused": args.index_run, "index_request_limit": 0 if index_run else 1,
        "request_limit": 3 if index_run else 4, "retries": 0, "scores_computed": False,
        "selection": "One exact official agent index lookup; locate mint hint, never scan logs or auto-page",
        "followup": "One receipt by indexed transaction hash, its exact transaction, then one exact receipt block header",
        "sources": ["https://docs.gnosischain.com/tools/Blockchain%20Explorers/blockscout",
            "https://github.com/blockscout/agent-skills/blob/main/blockscout-analysis/references/blockscout-api/tokens.md",
            "https://github.com/valory-xyz/autonolas-registries/blob/main/contracts/8004/IdentityRegistryBridger.sol"],
        "linked_event_signature": "ServiceAgentLinked(uint256,uint256)", "linked_event_topic": LINKED,
        "linked_event_verification": "Independent local Foundry cast keccak, exit 0; official source blob 835ca77ea72c2e329a7343e12137ae8727762dac",
        "script_sha256": digest(Path(__file__))}
    if not args.execute_public_readonly:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0
    now = datetime.now(timezone.utc)
    run = ROOT / "runtime" / f"olas-registration-probe-{now:%Y%m%dT%H%M%SZ}-{secrets.token_hex(4)}"
    run.mkdir()
    write_json(run / "manifest.json", {"created_at": now.isoformat(), **plan})
    result = {"status": "UNKNOWN", "scores_computed": False}
    store = EvidenceStore(run, [identity_run, *[retained_directory(value) for value in args.reuse_run]],
                          enabled=True, proxy=args.proxy, max_requests=3, parallel_reads=1)
    try:
        indexed = read(PublicTarget("registration-index", index_url), run, args.proxy, index_run)
        if args.index_provider == "8004scan":
            if (indexed.get("chain_id") != 100 or str(indexed.get("token_id")) != str(profile.agent_id)
                or str(indexed.get("contract_address", "")).lower() != REGISTRY):
                raise ValueError("Directory hint does not identify the fixed chain/registry/agent")
            hints = [{"transaction_hash": indexed.get("created_tx_hash"),
                      "block_number": indexed.get("created_block_number")}]
        else:
            rows = indexed["items"]
            if not isinstance(rows, list) or len(rows) > 50:
                raise ValueError("Index did not return one bounded NFT-transfer page")
            hints = [row for row in rows if str(row.get("from", {}).get("hash", "")).lower() == ZERO_ADDRESS
                     and str(row.get("to", {}).get("hash", "")).lower() == BRIDGER
                     and str(row.get("token", {}).get("address_hash", "")).lower() == REGISTRY]
        if len(hints) != 1 or not HASH.fullmatch(hints[0].get("transaction_hash", "")):
            raise ValueError("Index first page does not identify one exact registry-to-Bridger mint")
        hint = hints[0]
        tx_hash = hint["transaction_hash"].lower()
        receipt_proof = store.rpc("registration-receipt", "eth_getTransactionReceipt", [tx_hash])
        receipt = receipt_proof["value"]
        block = int(receipt["blockNumber"], 16)
        if (receipt["transactionHash"].lower() != tx_hash or receipt["status"] != "0x1"
            or not 0 < block <= snapshot["snapshot_block"] or not HASH.fullmatch(receipt["blockHash"])):
            raise ValueError("Registration receipt failed fixed-chain inclusion or success checks")
        for log in receipt["logs"]:
            if (log["transactionHash"].lower() != tx_hash or log["blockHash"].lower() != receipt["blockHash"].lower()
                or int(log["blockNumber"], 16) != block or log.get("removed") is not False):
                raise ValueError("Receipt logs do not share the exact transaction and block")
        mint = [log for log in receipt["logs"] if log["address"].lower() == REGISTRY
                and len(log["topics"]) == 4 and log["topics"][0].lower() == TRANSFER
                and log["topics"][1].lower() == ZERO_WORD and address(log["topics"][2]) == BRIDGER
                and int.from_bytes(word(log["topics"][3])) == profile.agent_id and log["data"] == "0x"]
        linked = [log for log in receipt["logs"] if log["address"].lower() == BRIDGER
                  and len(log["topics"]) == 3 and log["topics"][0].lower() == LINKED
                  and int.from_bytes(word(log["topics"][1])) == profile.service_id
                  and int.from_bytes(word(log["topics"][2])) == profile.agent_id and log["data"] == "0x"]
        if len(mint) != 1 or len(linked) != 1 or int(mint[0]["logIndex"], 16) >= int(linked[0]["logIndex"], 16):
            raise ValueError("Receipt does not contain one ordered exact NFT mint and service-agent link")
        transaction_proof = store.rpc("registration-transaction", "eth_getTransactionByHash", [tx_hash])
        transaction = transaction_proof["value"]
        if (transaction["hash"].lower() != tx_hash or int(transaction["blockNumber"], 16) != block
            or transaction["blockHash"].lower() != receipt["blockHash"].lower()
            or transaction["from"].lower() != receipt["from"].lower()
            or transaction["to"].lower() != receipt["to"].lower()):
            raise ValueError("Transaction differs from the exact mint receipt")
        header_proof = store.rpc("registration-header", "eth_getBlockByNumber", [hex(block), False])
        header = header_proof["value"]
        if (int(header["number"], 16) != block or header["hash"].lower() != receipt["blockHash"].lower()
            or (hint.get("block_number") is not None and int(hint["block_number"]) != block)):
            raise ValueError("Registration header differs from its exact receipt/index block")
        timestamp = int(header["timestamp"], 16)
        result.update(status="REGISTRATION_PROVEN", transaction_hash=tx_hash, block_number=block,
            block_hash=header["hash"], registered_at_unix=timestamp,
            registered_at=datetime.fromtimestamp(timestamp, timezone.utc).isoformat(),
            mint_log_index=int(mint[0]["logIndex"], 16), linked_log_index=int(linked[0]["logIndex"], 16),
            owner_at_mint=BRIDGER, olas_service_id=profile.service_id, erc8004_agent_id=profile.agent_id,
            proofs={"transaction": transaction_proof, "receipt": receipt_proof, "header": header_proof},
            limitation="Proves mint and bridge-link chronology only; historical task operator and task correctness remain separate")
    except (ValueError, KeyError, TypeError, AttributeError, OSError, EvidenceUnavailable) as error:
        result["reason"] = str(error)
    finally:
        store.close()
    result["new_requests_observed"] = len(list(run.glob("*.observation.json")))
    write_json(run / "result.json", result)
    supplement_run = supplement(identity_run, run, result)
    print(json.dumps({"evidence_directory": run.relative_to(ROOT).as_posix(),
        "identity_supplement": supplement_run.relative_to(ROOT).as_posix(),
        **{key: value for key, value in result.items() if key != "proofs"}}, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "REGISTRATION_PROVEN" else 1


if __name__ == "__main__":
    raise SystemExit(main())
