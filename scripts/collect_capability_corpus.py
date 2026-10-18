"""Collect declared public registration data, never Agent business or reputation scores."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import secrets
import sys
import time
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "packages/core/src"), str(ROOT / "services/platform/src")]

from reputation_platform.safe_http import PublicTarget, SafeHttpClient

BASE = "https://api.8004scan.io"
ALLOWED_QUERY = {"limit", "offset", "chain_id", "is_testnet", "sort_by", "sort_order",
                 "is_active", "is_registered", "has_mcp", "has_a2a", "created_after", "created_before"}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)


def project_path(value: str, prefix: str) -> Path:
    path = (ROOT / value).resolve()
    if not path.is_relative_to((ROOT / prefix).resolve()) or not path.is_file():
        raise ValueError(f"Expected an existing project {prefix} file")
    return path


def load_config(path: Path) -> tuple[dict, tuple[PublicTarget, ...]]:
    config = json.loads(path.read_bytes())
    if config.get("schema_version") != "capability-corpus-config-v1":
        raise ValueError("Unsupported corpus configuration")
    if config.get("phase") not in {"documentation", "directory", "details"}:
        raise ValueError("Only documentation and registration data phases are supported")
    interval = config.get("request_interval_seconds", 2.2)
    if not isinstance(interval, (int, float)) or not 2.2 <= interval <= 10:
        raise ValueError("Anonymous directory request interval must be 2.2–10 seconds")
    targets = []
    for item in config["targets"]:
        query = item.get("query", {})
        if not isinstance(query, dict) or set(query) - ALLOWED_QUERY:
            raise ValueError("Directory query contains unreviewed fields")
        if item["resource"] == "openapi" and config["phase"] == "documentation" and not query:
            url = BASE + "/openapi.json"
        elif item["resource"] == "agents" and config["phase"] == "directory":
            if not 1 <= int(query.get("limit", 10)) <= 100 or int(query.get("offset", 0)) < 0:
                raise ValueError("Directory pagination outside reviewed bounds")
            if query.get("sort_by", "created_at") not in {"created_at", "token_id", "name"}:
                raise ValueError("Reputation, popularity and ranking must not select corpus records")
            url = BASE + "/api/v1/agents?" + urlencode(query)
        elif item["resource"] == "agent-detail" and config["phase"] == "details" and not query:
            chain, token = str(item["chain_id"]), str(item["token_id"])
            if not re.fullmatch(r"[1-9][0-9]*", chain) or not re.fullmatch(r"[0-9]+", token):
                raise ValueError("Agent detail requires a numeric EVM registration identity")
            url = BASE + f"/api/v1/agents/{chain}/{token}"
        else:
            raise ValueError("Only fixed official OpenAPI and Agent list GETs are allowed")
        targets.append(PublicTarget(item["key"], url))
    if not 1 <= len(targets) <= 150 or len({x.url for x in targets}) != len(targets):
        raise ValueError("Expected 1–150 unique bounded registration GETs")
    return config, tuple(targets)


def api_surface(payload: dict) -> dict:
    operation = payload.get("paths", {}).get("/api/v1/agents", {}).get("get", {})
    schemas = payload.get("components", {}).get("schemas", {})
    refs = set()

    def collect(value):
        if isinstance(value, dict):
            if "$ref" in value:
                refs.add(value["$ref"].rsplit("/", 1)[-1])
            for child in value.values():
                collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)

    collect(operation)
    selected = {}
    while refs - selected.keys():
        for name in list(refs - selected.keys()):
            selected[name] = schemas.get(name, {})
            collect(selected[name])
    return {"version": payload.get("info", {}).get("version"),
            "list_operation": operation, "referenced_schemas": selected}


def read_retained(run_values: list[str]) -> tuple[dict, list[dict]]:
    cache, inputs = {}, []
    for value in run_values:
        run = (ROOT / value).resolve()
        if not run.is_relative_to((ROOT / "runtime").resolve()) or not run.is_dir():
            raise ValueError("Reuse directory must be inside project runtime")
        for path in sorted(run.glob("*.observation.json")):
            observation = json.loads(path.read_bytes())
            url = observation.get("url", "")
            if not url.startswith(BASE + "/api/v1/agents") or observation.get("method") != "GET":
                continue
            if observation.get("http_status") != 200 or observation.get("error_kind") or not observation.get("body_complete"):
                continue
            raw = (run / observation["response_file"]).resolve()
            if raw.parent != run or digest(raw) != observation["response_sha256"]:
                raise ValueError("Retained directory response digest mismatch")
            cache[url] = (path, raw, observation)
            inputs.extend([{"path": str(p.relative_to(ROOT)), "sha256": digest(p)} for p in (path, raw)])
    return cache, list({item["path"]: item for item in inputs}.values())


def description_quality(text: object, name: object) -> dict:
    if not isinstance(text, str) or not text.strip():
        return {"description_present": False, "specific_function": "NO", "reason": "缺少功能描述；名字或标签不算声明。"}
    cleaned = " ".join(text.split())
    generic = {"test", "simple tools", "default olas service configuration", "an ai agent", "ai agent"}
    if cleaned.casefold() in generic or cleaned.casefold() == str(name).strip().casefold():
        return {"description_present": True, "specific_function": "NO", "reason": "测试、默认模板或仅名称，缺少具体业务。"}
    return {"description_present": True, "specific_function": "REVIEW_REQUIRED",
            "reason": "保留原文；是否为具体可归类功能须语义复核，非长度或关键词即可证明。"}


def normalize(row: dict, pointer: str, observation_path: Path, raw: Path, obs: dict, reviews: dict) -> dict:
    chain, token, registry = row.get("chain_id"), str(row.get("token_id", "")), row.get("contract_address", "")
    if (isinstance(chain, bool) or not isinstance(chain, int) or chain <= 0
        or not re.fullmatch(r"[0-9]+", token) or not re.fullmatch(r"0x[0-9a-fA-F]{40}", registry)):
        raise ValueError("Directory row lacks a complete EVM canonical registration identity")
    canonical = f"eip155:{chain}:{registry.lower()}:{int(token)}"
    expected = f"{chain}:{registry.lower()}:{int(token)}"
    if str(row.get("agent_id", expected)).lower() not in {expected, canonical}:
        raise ValueError("Directory composite agent_id disagrees with registration fields")
    raw_path, obs_path = str(raw.relative_to(ROOT)), str(observation_path.relative_to(ROOT))

    def citation(locator: str, quote: object) -> dict:
        return {"source_id": obs["request_key"], "url": obs["url"], "json_pointer": locator,
            "quote": quote, "raw_sha256": obs["response_sha256"], "raw_path": raw_path,
            "observation_path": obs_path, "projection_sha256": None}

    declarations = []
    if isinstance(row.get("description"), str) and row["description"].strip():
        declarations.append({"kind": "description", "original_text": row["description"],
            "source_citations": [citation(pointer + "/description", row["description"])]})
    metadata = row.get("raw_metadata") or {}
    content = metadata.get("offchain_content") if isinstance(metadata, dict) else None
    content = content if isinstance(content, dict) else {}
    for field in ("description", "skills", "capabilities", "tools"):
        value = content.get(field)
        if value:
            declarations.append({"kind": field, "original_value": value,
                "source_citations": [citation(pointer + "/raw_metadata/offchain_content/" + field, value)]})
    services = {key: row[key] for key in ("services", "mcp_server", "mcp_version", "a2a_endpoint", "a2a_version", "agent_url") if row.get(key)}
    published_interfaces = {key: content[key] for key in ("services", "endpoints", "url", "homepage") if content.get(key)}
    operator = content.get("operator")
    declared_name = operator.get("name") if isinstance(operator, dict) else None
    provider = {"status": "DECLARED" if isinstance(declared_name, str) and declared_name.strip() else "UNKNOWN",
        "name": declared_name if isinstance(declared_name, str) and declared_name.strip() else None,
        "evidence": [citation(pointer + "/raw_metadata/offchain_content/operator/name", declared_name)] if declared_name else [],
        "hints": {key: row[key] for key in ("owner_address", "owner_username", "owner_certified_name") if row.get(key)}}
    missing = ["目录身份尚未由本轮链上读取核实", "未核实声明是否兑现", "未调用接口核实业务可用性",
               "未核实独立判据、历史任务和执行关联"]
    if not services and not published_interfaces:
        missing.append("列表未提供服务详情，或登记详情中没有接口声明")
    if provider["status"] == "UNKNOWN":
        missing.append("提供方未核实；登记owner和共享网关不能直接视为独立提供方")
    quality = description_quality(row.get("description"), row.get("name"))
    text = row.get("description")
    review = reviews.get(hashlib.sha256(text.encode()).hexdigest()) if isinstance(text, str) else None
    if review:
        quality.update(specific_function=review["status"], reason=review["reason"], reviewer="codex-agent-editor",
                       reviewed_description_sha256=review["description_sha256"])
    quality["coverage_status"] = "DIRECTORY_SPECIFIC" if quality["specific_function"] == "YES" else "UNKNOWN"
    quality["supplemental_note"] = "目录文字不足不代表没有功能；旧manifest的具体声明由独立库存按完整身份合并。"
    return {"candidate_key": None, "registration_reference": canonical, "name": row.get("name"),
        "identity_status": "INDEXED_NOT_CHAIN_VERIFIED", "chain_id": chain, "provider": provider,
        "source_documents": [{"source_id": obs["request_key"], "url": obs["url"], "raw_path": raw_path,
            "raw_sha256": obs["response_sha256"], "observation_path": obs_path,
            "json_pointer": pointer, "declared_metadata_uri": metadata.get("offchain_uri") if isinstance(metadata, dict) else None}],
        "claims": [], "declarations": declarations, "quality": quality,
        "services": services, "published_interfaces": published_interfaces,
        "interface_source_citations": [citation(pointer + "/" + key, value) for key, value in services.items()]
            + [citation(pointer + "/raw_metadata/offchain_content/" + key, value)
               for key, value in published_interfaces.items()],
        "supported_protocols": row.get("supported_protocols", []),
        "feasibility": {key: {"status": "UNKNOWN", "value": None, "evidence": [], "gaps": [gap]}
            for key, gap in (("input_output", "仅保留工具声明，尚未逐工具确认输入输出规范的完整性"), ("authorization", "协议标签不等于免费或已授权"),
                             ("independent_oracle", "未核实独立正确性判据"), ("transaction_history", "未核实任务到交易的完整归属"))},
        "missing": missing, "source_runs": [str(raw.parent.relative_to(ROOT))]}


def build_corpus(cache: dict, reviews: dict) -> tuple[list[dict], list[dict]]:
    records, gaps = {}, []
    for _, (obs_path, raw, obs) in cache.items():
        payload = json.loads(raw.read_bytes())
        if isinstance(payload, dict) and isinstance(payload.get("items"), list):
            rows = [(row, f"/items/{index}") for index, row in enumerate(payload["items"])]
        elif isinstance(payload, dict) and "chain_id" in payload and "token_id" in payload:
            rows = [(payload, "")]
        else:
            gaps.append({"raw_path": str(raw.relative_to(ROOT)), "reason": "Unrecognized indexed registration shape"})
            continue
        for row, pointer in rows:
            try:
                record = normalize(row, pointer, obs_path, raw, obs, reviews)
                key = record["registration_reference"]
                if key in records:
                    existing = records[key]
                    if len(json.dumps(record["declarations"])) > len(json.dumps(existing["declarations"])):
                        record["source_documents"] += existing["source_documents"]
                        record["source_runs"] = list(dict.fromkeys(record["source_runs"] + existing["source_runs"]))
                        records[key] = record
                    else:
                        existing["source_documents"] += record["source_documents"]
                        existing["source_runs"] = list(dict.fromkeys(existing["source_runs"] + record["source_runs"]))
                else:
                    records[key] = record
            except (ValueError, TypeError) as error:
                gaps.append({"raw_path": str(raw.relative_to(ROOT)), "json_pointer": pointer, "reason": str(error)})
    return list(records.values()), gaps


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--execute-public-readonly", action="store_true")
    parser.add_argument("--offline-build", action="store_true", help="Only aggregate already retained responses")
    parser.add_argument("--proxy")
    parser.add_argument("--reuse-runs", nargs="*", default=[])
    args = parser.parse_args()
    if args.execute_public_readonly and not args.proxy:
        parser.error("Execution requires an explicit --proxy")
    if args.execute_public_readonly and args.offline_build:
        parser.error("Offline aggregation and public execution are mutually exclusive")
    config_path = project_path(args.config, "configs")
    config, targets = load_config(config_path)
    cache, inputs = read_retained(args.reuse_runs)
    if config.get("review_source_corpus"):
        source = config["review_source_corpus"]
        source_path = project_path(source["path"], "runtime")
        if digest(source_path) != source["sha256"]:
            raise ValueError("Frozen editorial source corpus digest mismatch")
        inputs.append({"path": source["path"], "sha256": source["sha256"]})
    reviews = {}
    for item in config.get("description_reviews", []):
        if (item["status"] not in {"YES", "NO", "UNKNOWN"} or not item["reason"]
            or not re.fullmatch(r"[0-9a-f]{64}", item["description_sha256"])):
            raise ValueError("Malformed frozen directory-description review")
        if item["description_sha256"] in reviews:
            raise ValueError("Duplicate directory-description review")
        reviews[item["description_sha256"]] = item
    manifest = {"schema_version": "capability-corpus-manifest-v1", "phase": config["phase"],
        "config": {"path": str(config_path.relative_to(ROOT)), "sha256": digest(config_path)},
        "script_sha256": digest(Path(__file__)), "source_documentation": config["source_documentation"],
        "execution_enabled": args.execute_public_readonly,
        "inputs": inputs, "reuse_runs": args.reuse_runs,
        "requests": [{"key": x.key, "method": "GET", "url": x.url,
            "purpose": "background"} for x in targets], "request_limit": len(targets),
        "request_interval_seconds": config["request_interval_seconds"], "retries": 0,
        "stop_host_http_statuses": [401, 402, 403, 429], "redirects": False,
        "rpc_calls": 0, "agent_business_calls": 0, "model_calls": 0, "scores_computed": False,
        "scope": "Published indexed registration declarations only; not verified capabilities or providers."}
    if not args.execute_public_readonly and not args.offline_build:
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return 0
    now = datetime.now(timezone.utc)
    run = ROOT / "runtime" / f"capability-corpus-{now:%Y%m%dT%H%M%SZ}-{secrets.token_hex(4)}"
    run.mkdir()
    write_json(run / "manifest.json", {"created_at": now.isoformat(), **manifest})
    print(json.dumps({"evidence_directory": str(run.relative_to(ROOT))}), flush=True)
    results, stop = [], None
    stop_path = ROOT / "runtime/capability-corpus-network-stops/api.8004scan.io.json"
    if stop_path.exists():
        stop = "An earlier authorization or quota response stopped this host"
    with SafeHttpClient(targets, enabled=args.execute_public_readonly, proxy=args.proxy, max_requests=len(targets),
                        max_body_bytes=8_388_608, timeout_seconds=45) as client:
        for index, target in enumerate(targets):
            if stop:
                break
            if target.url in cache:
                continue
            if args.offline_build:
                stop = "Offline aggregation does not contain every configured request"
                break
            if index:
                time.sleep(config["request_interval_seconds"])
            observation = client.fetch(target.key, run)
            result = {"request_key": target.key, "http_status": observation.http_status,
                "error_kind": observation.error_kind, "raw_sha256": observation.response_sha256}
            results.append(result)
            if len(results) % 10 == 0:
                print(json.dumps({"requests_retained": len(results), "last_http_status": observation.http_status}), flush=True)
            if observation.http_status in (401, 402, 403, 429):
                stop_path.parent.mkdir(exist_ok=True)
                if not stop_path.exists():
                    write_json(stop_path, {"run": str(run.relative_to(ROOT)), "request_key": target.key,
                        "http_status": observation.http_status, "observed_at": observation.observed_at.isoformat()})
            if observation.http_status != 200 or observation.error_kind or not observation.body_complete:
                stop = "Directory read not available; no retry or endpoint change"
                break
            try:
                payload = json.loads((run / observation.response_file).read_bytes())
                if config["phase"] == "documentation":
                    write_json(run / "api-surface.json", api_surface(payload))
                else:
                    item = config["targets"][index]
                    if item["resource"] == "agent-detail":
                        actual = f"eip155:{payload.get('chain_id')}:{str(payload.get('contract_address', '')).lower()}:{payload.get('token_id')}"
                        if actual != item["registration_reference"]:
                            raise ValueError("Detail response differs from the selected complete registration identity")
                    cache[target.url] = (run / f"{target.key}.observation.json", run / observation.response_file,
                                         observation.model_dump(mode="json"))
                    write_json(run / f"{target.key}.structure.json", {
                        "root_type": type(payload).__name__,
                        "root_keys": list(payload) if isinstance(payload, dict) else [],
                        "data_type": type(payload.get("data")).__name__ if isinstance(payload, dict) else None})
            except (ValueError, TypeError, KeyError) as error:
                stop = "JSON registration data unavailable: " + type(error).__name__
                break
    records, gaps = build_corpus(cache, reviews)
    if config["phase"] != "documentation":
        write_json(run / "corpus.json", {"schema_version": "capability-corpus-v1", "records": records,
            "data_gaps": gaps, "model_calls": 0, "scores_computed": False})
    write_json(run / "result.json", {"status": "RETAINED" if stop is None else "STOPPED",
        "requests_observed": len(results), "results": results, "stop_reason": stop,
        "distinct_indexed_identities": len(records), "chains": dict(Counter(str(r["chain_id"]) for r in records)),
        "description_quality": dict(Counter(r["quality"]["specific_function"] for r in records)),
        "unique_owner_hints": len({r["provider"]["hints"].get("owner_address") for r in records}),
        "scores_computed": False})
    if config["phase"] != "documentation":
        source_inputs = {item["path"]: item for item in inputs}
        for obs_path, raw, _ in cache.values():
            for path in (obs_path, raw):
                source_inputs[str(path.relative_to(ROOT))] = {"path": str(path.relative_to(ROOT)), "sha256": digest(path)}
        write_json(run / "corpus-manifest.json", {"schema_version": "capability-corpus-artifacts-v1",
            "request_manifest": {"path": str((run / 'manifest.json').relative_to(ROOT)), "sha256": digest(run / "manifest.json")},
            "inputs": list(source_inputs.values()),
            "outputs": [{"path": str((run / name).relative_to(ROOT)), "sha256": digest(run / name)}
                        for name in ("corpus.json", "result.json")],
            "new_network_requests": len(results), "scores_computed": False, "model_calls": 0})
    print(json.dumps({"evidence_directory": str(run.relative_to(ROOT)),
        "requests_observed": len(results), "stop_reason": stop}, ensure_ascii=False))
    return 0 if stop is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
