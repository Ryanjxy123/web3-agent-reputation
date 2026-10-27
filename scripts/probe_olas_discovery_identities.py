"""Bind configured discovered services to actual ERC-8004 IDs; background reads only."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import secrets
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "packages/core/src"), str(ROOT / "services/platform/src")]

from reputation_core import ProbeObservation
from reputation_platform.safe_http import PublicTarget, SafeHttpClient
from discover_olas_candidates import ENDPOINT, QUERY
from probe_olas_history import (BRIDGER, CONFIG as RPC_CONFIG, REGISTRY, RPC,
                               SERVICE_REGISTRY, abi_string, address, digest,
                               retained_identity, word)

SERVICES = (2198, 3098, 2235, 2340, 2359, 2360, 3783, 3786, 3066)
SNAPSHOT = 48815687
CONFIGS = ("configs/olas-discovery-identities.json", "configs/olas-discovery-identities-v2.json",
           "configs/olas-discovery-identities-v3.json")


def write_json(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)


def runtime_directory(value: str) -> Path:
    path, runtime = (ROOT / value).resolve(), (ROOT / "runtime").resolve()
    if not path.is_dir() or path == runtime or not path.is_relative_to(runtime):
        raise ValueError("Evidence inputs must be existing project runtime directories")
    return path


def source(path: Path) -> dict:
    return {"path": path.relative_to(ROOT).as_posix(), "sha256": digest(path)}


def load_inputs(args) -> tuple[dict, dict, list[dict], list[dict]]:
    config_path = ROOT / args.config
    config = json.loads(config_path.read_bytes())
    trusted = json.loads(RPC_CONFIG.read_bytes())
    if (config["chain_id"] != 100 or trusted["chain_id"] != 100
        or config["rpc_url"] != RPC or trusted["rpc_url"] != RPC
        or config["registry"] != REGISTRY or trusted["registry"] != REGISTRY
        or config["bridger"] != BRIDGER or config["service_registry"] != SERVICE_REGISTRY
        or config["snapshot_block"] != SNAPSHOT):
        raise ValueError("Public config differs from the fixed reviewed scope")
    facts, inputs = retained_identity(runtime_directory(args.identity_run))
    if facts["snapshot_block"] != SNAPSHOT or facts["snapshot_hash"] != config["snapshot_hash"]:
        raise ValueError("Retained chain snapshot differs from the fixed scope")
    directory = runtime_directory(args.discovery_run)
    obs_path = directory / "olas-mech-directory.observation.json"
    body_path = directory / "olas-mech-directory.response.bin"
    observation = ProbeObservation.model_validate_json(obs_path.read_bytes())
    if (observation.url != ENDPOINT or observation.method != "POST" or observation.http_status != 200
        or observation.error_kind or not observation.body_complete
        or observation.response_file != body_path.name or observation.response_sha256 != digest(body_path)
        or json.loads(observation.request_json) != {"query": QUERY}):
        raise ValueError("Retained directory request or digest differs from the reviewed discovery")
    payload = json.loads(body_path.read_bytes())
    if payload.get("errors") or not isinstance(payload["data"]["meches"], list):
        raise ValueError("Directory did not retain a valid list")
    if args.config == CONFIGS[0]:
        expected_services = SERVICES
    elif args.config == CONFIGS[1]:
        excluded = {2182, *SERVICES}
        expected_services = tuple(int(row["service"]["id"]) for row in payload["data"]["meches"]
                                  if int(row["service"]["id"]) not in excluded)[:6]
        selection = config.get("selection", {})
        if set(selection.get("exclude_service_ids", [])) != excluded or selection.get("first") != 6:
            raise ValueError("Second batch does not preserve the frozen exclusions and bounded order")
    else:
        excluded = {2182, *SERVICES, 3118, 3264, 3254, 3440, 3446, 3443}
        expected_services = tuple(int(row["service"]["id"]) for row in payload["data"]["meches"]
                                  if int(row["service"]["id"]) not in excluded and row["service"].get("metadata"))[:9]
        selection = config.get("selection", {})
        if (set(selection.get("exclude_service_ids", [])) != excluded or selection.get("first") != 9
            or selection.get("require_metadata") is not True):
            raise ValueError("Third batch must preserve metadata availability and original directory order")
    if tuple(row["service_id"] for row in config["candidates"]) != expected_services:
        raise ValueError("Candidates do not match the frozen selection from retained directory order")
    selected = []
    for candidate in config["candidates"]:
        rows = [row for row in payload["data"]["meches"]
                if row["address"].lower() == candidate["mech"]
                and int(row["service"]["id"]) == candidate["service_id"]]
        if len(rows) != 1 or not re.fullmatch(r"0x[0-9a-f]{40}", candidate["mech"]):
            raise ValueError("Configured service/Mech is not unique in retained discovery")
        selected.append({**candidate, "metadata_hashes": [item["metadata"]
            for item in rows[0]["service"].get("metadata", [])],
            "erc8004_agent_id": None, "identity_status": "UNKNOWN", "facts": {}, "evidence": [],
            "reason": "Actual ERC-8004 bridge mapping has not been read"})
    inputs.extend(source(path) for path in (config_path, RPC_CONFIG, Path(__file__), obs_path,
                                            body_path, directory / "manifest.json"))
    return config, facts, inputs, selected


def rpc_target(service: int, kind: str, contract: str, data: str) -> PublicTarget:
    return PublicTarget(f"service-{service}-{kind}", RPC, "POST", json_body={
        "jsonrpc": "2.0", "id": f"{service}-{kind}", "method": "eth_call",
        "params": [{"to": contract, "data": data}, hex(SNAPSHOT)]})


def specification(target: PublicTarget) -> dict:
    return {"key": target.key, "url": target.url, "method": target.method,
            "measurement_purpose": target.purpose.value, "json": target.json_body}


def collect_phase(run: Path, phase: str, targets: list[PublicTarget], proxy: str | None,
                  retained: Path | None = None) -> tuple[dict, str | None]:
    # Every exact URL/body is persisted before its first transmission, including derived IDs/URIs.
    write_json(run / f"{phase}.manifest.json", {"created_at": datetime.now(timezone.utc).isoformat(),
        "execution_enabled": retained is None, "retained_evidence_run": retained.relative_to(ROOT).as_posix() if retained else None,
        "retries": 0, "request_limit": 0 if retained else len(targets), "planned_requests": [specification(t) for t in targets]})
    values, stop = {}, None
    if not targets:
        return values, stop
    failed_services = set()
    with SafeHttpClient(tuple(targets), enabled=retained is None, proxy=proxy, max_requests=len(targets),
                        max_body_bytes=1_048_576, timeout_seconds=30) as client:
        for target in targets:
            service = target.key.split("-")[1]
            if service in failed_services:
                continue
            evidence_run = retained or run
            if retained is None:
                obs = client.fetch(target.key, run)
            else:
                obs = ProbeObservation.model_validate_json((retained / f"{target.key}.observation.json").read_bytes())
                expected_json = target.json_body
                actual_json = json.loads(obs.request_json) if obs.request_json is not None else None
                if (obs.request_key != target.key or obs.url != target.url or obs.method != target.method
                    or actual_json != expected_json or obs.purpose != target.purpose
                    or (obs.response_file is not None and (obs.response_file != f"{target.key}.response.bin"
                        or obs.response_sha256 != digest(retained / obs.response_file)))):
                    raise ValueError("Retained request or response differs from the exact planned target")
            entry = {"evidence": [source(evidence_run / f"{target.key}.observation.json")], "value": None}
            values[target.key] = entry
            if obs.response_file:
                entry["evidence"].append(source(evidence_run / obs.response_file))
            print(f"{'retained' if retained else 'read'} {target.key}: HTTP={obs.http_status} error={obs.error_kind}", flush=True)
            if obs.error_kind or not obs.body_complete or obs.http_status != 200:
                entry["error"] = obs.error_kind or "incomplete_or_unsuccessful_http"
                stop = f"{target.key}: {entry['error']}"
                break  # No transport retries, fallback, or further reads after a host/network stop.
            try:
                payload = json.loads((evidence_run / obs.response_file).read_bytes())
                if target.method == "POST":
                    if (not isinstance(payload, dict) or payload.get("jsonrpc") != "2.0"
                        or payload.get("id") != target.json_body["id"] or "result" not in payload
                        or "error" in payload):
                        code = payload.get("error", {}).get("code") if isinstance(payload, dict) else None
                        raise ValueError(f"RPC result unavailable (code={code})")
                    payload = payload["result"]
                entry["value"] = payload
            except (ValueError, TypeError, KeyError, AttributeError) as error:
                entry["error"] = str(error)
                failed_services.add(service)  # Mapping/RPC errors remain UNKNOWN for this object.
    return values, stop


def bind_value(row: dict, values: dict, kind: str):
    key = f"service-{row['service_id']}-{kind}"
    entry = values.get(key)
    if entry is None:
        raise ValueError(f"{kind}: not observed after an earlier stop or object error")
    row["evidence"].extend(entry["evidence"])
    if "error" in entry:
        raise ValueError(f"{kind}: {entry['error']}")
    return entry["value"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--identity-run", required=True)
    parser.add_argument("--discovery-run", required=True)
    parser.add_argument("--config", choices=CONFIGS, required=True, help="Explicitly supply a retained cohort configuration")
    parser.add_argument("--execute-public-readonly", action="store_true")
    parser.add_argument("--proxy")
    parser.add_argument("--retained-run", help="Reuse exact identity observations without repeating their HTTP calls")
    parser.add_argument("--fetch-manifests", action="store_true",
                        help="GET verified registration manifest links; identity reads are reused when --retained-run is given")
    args = parser.parse_args()
    if args.execute_public_readonly and not args.proxy:
        parser.error("Execution requires explicit --proxy")
    if args.execute_public_readonly and args.retained_run and not args.fetch_manifests:
        parser.error("Offline retained analysis cannot enable public execution")
    retained = runtime_directory(args.retained_run) if args.retained_run else None
    config, snapshot, inputs, rows = load_inputs(args)
    mappings = [rpc_target(row["service_id"], "bridge", BRIDGER,
                           "0xe0e3e127" + f"{row['service_id']:064x}") for row in rows]
    plan = {"execution_enabled": args.execute_public_readonly, "measurement_purpose": "background",
        "chain_id": 100, "fixed_snapshot": snapshot, "sources": inputs,
        "official_sources": config["sources"],
        "request_limit": len(rows) if retained and args.fetch_manifests else len(rows) * (8 if args.fetch_manifests else 7),
        "retries": 0,
        "scores_computed": False, "paid_calls": False, "writes": False,
        "planned_mapping_requests": [specification(t) for t in mappings],
        "retained_input": source(retained / "manifest.json") if retained else None,
        "fetch_manifests": args.fetch_manifests,
        "network_scope": ("manifest-get-only" if retained and args.fetch_manifests else "identity-and-manifest" if args.fetch_manifests else "identity-only") if args.execute_public_readonly else "disabled",
        "conditional_followup": "Nonzero mappings only: ownerOf, tokenURI, serviceId, serviceRegistry, getOperator; then exact official tokenURI GET. Each phase has its own pre-request manifest.",
        "limitations": ["Snapshot chain/header are verified from retained 2182 originals, never requested again.",
            "Service IDs are not assumed to be ERC-8004 IDs.",
            "Identity admission is not service availability, functional correctness or reliability scoring.",
            "Current fixed-snapshot operator is not automatically the historical task executor."]}
    if not args.execute_public_readonly and (retained is None or args.fetch_manifests):
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0
    now = datetime.now(timezone.utc)
    run = ROOT / "runtime" / f"olas-discovery-identities-{now:%Y%m%dT%H%M%SZ}-{secrets.token_hex(4)}"
    run.mkdir()
    write_json(run / "manifest.json", {"created_at": now.isoformat(), **plan})
    values, stop = collect_phase(run, "mapping", mappings, args.proxy, retained)
    bindings = []
    for row in rows:
        try:
            agent_id = int.from_bytes(word(bind_value(row, values, "bridge")))
            row["erc8004_agent_id"] = agent_id or None
            if not agent_id:
                raise ValueError("No ERC-8004 bridge mapping at the fixed snapshot; no follow-up requested")
            row["registration_reference"] = f"eip155:100:{REGISTRY}:{agent_id}"
            for kind, contract, data in [("owner", REGISTRY, "0x6352211e" + f"{agent_id:064x}"),
                    ("uri", REGISTRY, "0xc87b56dd" + f"{agent_id:064x}"),
                    ("service-id", row["mech"], "0xda20ec6a"),
                    ("service-registry", row["mech"], "0xcbcf252a"),
                    ("operator", row["mech"], "0xe7f43c68")]:
                bindings.append(rpc_target(row["service_id"], kind, contract, data))
        except (ValueError, TypeError) as error:
            row["reason"] = str(error)
    values, follow_stop = collect_phase(run, "binding", bindings if not stop else [], args.proxy, retained)
    stop = stop or follow_stop
    documents = []
    for row in rows:
        if row["erc8004_agent_id"] is None:
            continue
        try:
            facts = row["facts"]
            facts["registration_owner"] = address(bind_value(row, values, "owner"))
            facts["token_uri"] = abi_string(bind_value(row, values, "uri"))
            facts["mech_service_id"] = int.from_bytes(word(bind_value(row, values, "service-id")))
            facts["service_registry"] = address(bind_value(row, values, "service-registry"))
            facts["operator"] = address(bind_value(row, values, "operator"))
            if (facts["registration_owner"] != BRIDGER or facts["mech_service_id"] != row["service_id"]
                or facts["service_registry"] != SERVICE_REGISTRY):
                raise ValueError("Fixed-state bridge/registration/Mech binding does not match")
            if not re.fullmatch(r"https://marketplace\.olas\.network/erc8004/gnosis/ai-agents/[0-9]+", facts["token_uri"]):
                raise ValueError("Actual tokenURI is outside the explicitly permitted official registration route")
            documents.append(PublicTarget(f"service-{row['service_id']}-document", facts["token_uri"]))
            row["reason"] = "Fixed-state bridge and execution identity verified; registration document pending"
        except (ValueError, TypeError, UnicodeError) as error:
            row["reason"] = str(error)
    values, doc_stop = collect_phase(run, "registration", documents if not stop else [], args.proxy, retained)
    stop = stop or doc_stop
    for row in rows:
        if not any(t.key == f"service-{row['service_id']}-document" for t in documents):
            continue
        try:
            doc = bind_value(row, values, "document")
            registrations = doc.get("registrations", [])
            expected = f"eip155:100:{REGISTRY}"
            if not any(str(item.get("agentId")) == str(row["erc8004_agent_id"])
                       and str(item.get("agentRegistry", "")).lower() == expected for item in registrations):
                raise ValueError("Official document does not confirm the actual mapped ERC-8004 identity")
            services = doc.get("services", [])
            service_link = f"https://marketplace.olas.network/gnosis/ai-agents/{row['service_id']}"
            if not any(item.get("name") == "web" and item.get("endpoint") == service_link for item in services):
                raise ValueError("Official document does not link the independently verified Olas service")
            analytics = f"https://mech-analytics-api.autonolas.tech/v1/metrics/mech/100/{row['mech']}"
            row["facts"]["document_names_mech_directly"] = any(item.get("endpoint") == analytics for item in services)
            # The verified Mech.serviceId -> Bridger mapping proves the binding independently.
            # An optional benchmark URL and the document's agentWallet are not execution proofs.
            row["facts"]["registration_service_link"] = service_link
            row.update(identity_status="PASS", reason="Actual bridge mapping, registration and service/Mech/operator association verified at the retained fixed state",
                       name=doc.get("name"), description=doc.get("description"), services=services,
                       gaps=["Specific task/tool claims and authenticated historical inputs/results still require verification",
                             "No three-dimensional score was produced by these background reads"])
        except (ValueError, TypeError, KeyError, AttributeError) as error:
            row["reason"] = str(error)
    if args.fetch_manifests and not stop:
        manifests = []
        for row in rows:
            if row["identity_status"] != "PASS":
                continue
            links = [service.get("endpoint") for service in row["services"] if service.get("name") == "manifest"]
            permitted = {"https://gateway.autonolas.tech/ipfs/f01701220" + value[2:].lower()
                         for value in row["metadata_hashes"] if re.fullmatch(r"0x[0-9a-fA-F]{64}", value)}
            if (len(links) != 1 or not isinstance(links[0], str)
                or not re.fullmatch(r"https://gateway\.autonolas\.tech/ipfs/f01701220[0-9a-f]{64}", links[0])
                or (permitted and links[0] not in permitted)):
                row["manifest_gap"] = "Missing canonical official manifest, or it differs from the retained directory CID"
                continue
            row["facts"]["manifest_cid_source"] = "registration_and_directory" if permitted else "registration_only_directory_metadata_empty"
            manifests.append(PublicTarget(f"service-{row['service_id']}-manifest", links[0]))
        manifest_values, manifest_stop = collect_phase(run, "manifests", manifests, args.proxy)
        stop = stop or manifest_stop
        for row in rows:
            if not any(t.key == f"service-{row['service_id']}-manifest" for t in manifests):
                continue
            try:
                document = bind_value(row, manifest_values, "manifest")
                if not isinstance(document, dict):
                    raise ValueError("Manifest is not a JSON object")
                row["manifest_document"] = document
                row["manifest_content_authentication"] = "NOT_VERIFIED: gateway bytes retained; CID/DAG authentication is separate"
            except (ValueError, TypeError) as error:
                row["manifest_gap"] = str(error)
    requests = len({item["path"] for row in rows for item in row["evidence"] if item["path"].endswith(".observation.json")})
    result = {"requests_observed": requests, "new_requests_observed": len(list(run.glob("*.observation.json"))),
        "stopped_reason": stop, "scores_computed": False,
        "fixed_snapshot": snapshot, "identity_pass_count": sum(row["identity_status"] == "PASS" for row in rows),
        "candidates": rows, "operator_count": len({row["facts"]["operator"] for row in rows if row["identity_status"] == "PASS"})}
    write_json(run / "result.json", result)
    print(json.dumps({"evidence_directory": run.relative_to(ROOT).as_posix(),
        **{k: v for k, v in result.items() if k != "candidates"}}, ensure_ascii=False, indent=2))
    return 0 if not stop and result["identity_pass_count"] == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
