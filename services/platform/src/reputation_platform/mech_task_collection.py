"""Registration-led collection of seven ordinary, already delivered Mech tasks."""

from datetime import datetime, timezone
import json
from pathlib import Path
import re
from types import SimpleNamespace

from reputation_core.admission import ProbeObservation
from reputation_core.application import normalize_reference
from reputation_core.prediction_chain import BRIDGER, REGISTRY, calldata, extract_task_anchors
from reputation_platform.mech_task_identity import verify_mech_identity
from reputation_platform.prediction_evidence import (
    EvidenceStore, EvidenceUnavailable, MECH_INDEX, _history_query, collect_task, file_reference,
)
from reputation_platform.prediction_report import RetainedEvidence
from reputation_platform.registration_discovery import verify_registration_proof

POLICY = "docs/adr/0011-shared-task-delivery-evidence.md"
POLICY_VERSION = "service-contract-v1"
DISCOVERY_LIMIT = 32
SLOTS = 7
HEX32 = r"0x[0-9a-fA-F]{64}"


class _LeasedEvidenceStore(EvidenceStore):
    def __init__(self, *args, heartbeat=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.heartbeat = heartbeat

    def request(self, key, url, method="GET", body=None):
        if self.heartbeat:
            self.heartbeat()
        try:
            return super().request(key, url, method, body)
        finally:
            if self.heartbeat:
                self.heartbeat()


def _mech_hint(services: list[dict]) -> str | None:
    hints = set()
    for service in services:
        name, url = str(service.get("name", "")).casefold(), service.get("endpoint", "")
        if not isinstance(url, str):
            continue
        match = None
        if name == "benchmark":
            match = re.fullmatch(r"https://mech-analytics-api\.autonolas\.tech/v1/metrics/mech/100/(0x[0-9a-fA-F]{40})", url)
        elif name == "operator":
            match = re.fullmatch(r"https://([0-9a-fA-F]{40})-100\.mech\.valory\.xyz", url)
        if match:
            value = match[1].lower()
            hints.add(value if value.startswith("0x") else "0x" + value)
    if len(hints) != 1:
        return None
    mech = hints.pop()
    return mech if int(mech, 16) else None


def _select(page: list, profile) -> tuple[list[dict], list[dict]]:
    selected, excluded, seen = [], [], set()
    for index, hint in enumerate(page):
        try:
            if not isinstance(hint, dict):
                raise ValueError("目录行不是任务对象。")
            rid = hint.get("requestId")
            if not isinstance(rid, str) or not re.fullmatch(HEX32, rid):
                raise ValueError("任务标识不是完整32字节十六进制值。")
            if rid.lower() in seen:
                raise ValueError("同一requestId重复交付，不重复计为任务。")
            if str(hint.get("mech", "")).lower() != profile.mech:
                raise ValueError("目录行不是本次已核对的Mech实例。")
            request, delivery = hint.get("request"), hint.get("marketplaceDelivery")
            if (not isinstance(request, dict) or not isinstance(request.get("marketplaceRequest"), dict)
                or not request["marketplaceRequest"] or not isinstance(delivery, dict) or not delivery):
                raise ValueError("缺少普通marketplace请求/交付结构；未适配signed或offchain路径。")
            for side in (request, hint):
                if (not re.fullmatch(HEX32, str(side.get("transactionHash", "")))
                    or not 0 <= int(side["blockNumber"]) <= profile.snapshot_block
                    or not 0 <= int(side["blockTimestamp"]) < profile.cutoff_timestamp):
                    raise ValueError("请求或交付线索不在固定链状态与截止时间内。")
            selected.append({"index": index, "hint": hint})
            seen.add(rid.lower())
            if len(selected) == SLOTS:
                break
        except (ValueError, KeyError, TypeError) as error:
            excluded.append({"index": index, "request_id": hint.get("requestId") if isinstance(hint, dict) else None,
                             "reason": str(error)})
    return selected, excluded


def _tool_manifests(services: list[dict], evidence, retained: RetainedEvidence) -> list[dict]:
    sources = []
    urls = dict.fromkeys(item["endpoint"] for item in services
                         if str(item.get("name", "")).casefold() == "manifest" and item.get("endpoint"))
    for index, url in enumerate(urls):
        source = {"url": url, "evidence": [], "response_file": None}
        try:
            for path in sorted(evidence.run.glob("*.observation.json")):
                observed = ProbeObservation.model_validate_json(path.read_bytes())
                if observed.url != url or observed.method != "GET" or observed.request_json is not None:
                    continue
                references = [file_reference(retained.remember(path.relative_to(evidence.root).as_posix()), evidence.root)]
                if observed.response_file:
                    response = (path.parent / observed.response_file).resolve()
                    if response.parent != path.parent:
                        raise ValueError("登记manifest原件路径越界。")
                    retained.remember(response.relative_to(evidence.root).as_posix(), observed.response_sha256)
                    references.append(file_reference(response, evidence.root))
                    source["response_file"] = response.relative_to(evidence.root).as_posix()
                plan = path.with_name(path.name.removesuffix(".observation.json") + ".request-plan.json")
                if plan.is_file():
                    references.append(file_reference(retained.remember(plan.relative_to(evidence.root).as_posix()), evidence.root))
                source.update(evidence=references, observation=observed.model_dump(mode="json"), reused=True)
                break
            else:
                key = "mech-tool-manifest" + (f"-{index + 1:02d}" if index else "")
                response = evidence.request(key, url)
                source.update({key: response[key] for key in ("evidence", "response_file", "observation")}, reused=False)
        except (ValueError, KeyError, TypeError, OSError) as error:
            source["reason"] = str(error)
        sources.append(source)
    return sources


def collect_mech_history(registration: dict, evidence) -> Path | None:
    try:
        return _collect_mech_history(registration, evidence)
    except (EvidenceUnavailable, ValueError, OSError) as error:
        path = evidence.run / "mech-collection-issue.json"
        with path.open("x", encoding="utf-8") as stream:
            json.dump({"status": "UNKNOWN", "reason": str(error), "retries": 0,
                       "registration_reference": registration.get("canonical")}, stream, ensure_ascii=False, indent=2)
        evidence._remember(path)
        return None


def _collect_mech_history(registration: dict, evidence) -> Path | None:
    """Collect background originals; task verdicts and scores are rebuilt by the adapter."""
    canonical = normalize_reference(registration.get("canonical", ""))
    if canonical is None or canonical.split(":")[1:3] != ["100", REGISTRY]:
        return None
    retained = RetainedEvidence(evidence.root)
    verified = verify_registration_proof(evidence.root, registration["proof_path"], canonical)
    proof = retained.json(registration["proof_path"])
    rpc = proof.get("rpc", {})
    if (not verified["registration_verified"] or not proof.get("document")
        or int(rpc["owner"]["value"], 16) != int(BRIDGER, 16)):
        return None
    uri = verified["token_uri"]
    matched = re.fullmatch(r"https://marketplace\.olas\.network/(?:api/)?erc8004/gnosis/ai-agents/(0|[1-9][0-9]*)", uri)
    mech = _mech_hint(verified["services"])
    if not matched or mech is None:
        return None
    service_id = int(matched[1])
    if service_id >= 2**256:
        return None
    document = proof["document"]
    observed, _ = retained.observation(document["evidence"], url=uri, method="GET")
    observation_path = next(item["path"] for item in document["evidence"] if item["path"].endswith(".observation.json"))
    source = (evidence.root / observation_path).parent / observed.response_file
    header = rpc["header"]["value"]
    if not isinstance(header.get("timestamp"), str) or not re.fullmatch(r"0x[0-9a-fA-F]+", header["timestamp"]):
        raise ValueError("固定区块头没有可核对的时间，未猜测历史截止时间。")
    profile = SimpleNamespace(
        candidate_key=registration["candidate_key"], chain_id=100, registry=REGISTRY,
        agent_id=int(canonical.split(":")[-1]), service_id=service_id, mech=mech,
        registration_source=source.relative_to(evidence.root).as_posix(), registration_sha256=document["sha256"],
        snapshot_block=int(header["number"], 16), snapshot_hash=header["hash"].lower(),
        confirmation_head=int(rpc["head"]["value"], 16), cutoff_timestamp=int(header["timestamp"], 16) + 1,
        history_page_size=DISCOVERY_LIMIT, history_max_deliveries=DISCOVERY_LIMIT, policy_version=POLICY_VERSION,
    )
    identity = {"chain": rpc["chain"], "head": rpc["head"], "header": rpc["header"],
        "calls": {"registration-owner": rpc["owner"], "registration-uri": rpc["uri"]},
        "registration": {"payload": document["payload"], "response_file": profile.registration_source,
                         "evidence": document["evidence"]},
        "historical_note": "当前登记只用于确认本次身份；任务执行时的服务、执行者和交付分别核验。"}
    store = _LeasedEvidenceStore(evidence.run, [evidence.run], enabled=evidence.enabled,
        proxy=evidence.proxy, max_requests=160, parallel_reads=2, root=evidence.root, heartbeat=evidence.heartbeat)
    counted = 0

    def sync_inputs():
        nonlocal counted
        evidence.inputs.update(retained.inputs)
        evidence.inputs.update({item["path"]: item["sha256"] for item in store.inputs.values()})
        evidence.request_count += store.sent - counted
        counted = store.sent

    def heartbeat():
        if evidence.heartbeat:
            evidence.heartbeat()

    try:
        retained.remember(POLICY)
        policy = {"path": POLICY, "sha256": retained.inputs[POLICY]}
        heartbeat()
        index, selected, excluded, discovery_error, tool_manifests = None, [], [], None, []
        try:
            for name, target, signature, args in (
                ("bridger-agent-id", BRIDGER, "mapServiceIdAgentIds(uint256)", (service_id,)),
                ("mech-service-id", mech, "serviceId()", ()),
                ("mech-service-registry", mech, "serviceRegistry()", ()),
                ("mech-operator", mech, "getOperator()", ()),
            ):
                identity["calls"][name] = store.call("mech-identity-" + name, target,
                                                    calldata(signature, *args), profile.snapshot_block)
            verify_mech_identity(retained, {"profile": vars(profile), "identity": identity}, canonical)
            identity["verdict"] = "PASS"
            tool_manifests = _tool_manifests(verified["services"], evidence, retained)
            index = store.graphql("mech-history-index", MECH_INDEX, _history_query(profile, 0))
            page = index["data"].get("delivers")
            if not isinstance(page, list) or len(page) > DISCOVERY_LIMIT:
                raise EvidenceUnavailable("目录没有返回限定的一页普通交付记录。")
            selected, excluded = _select(page, profile)
        except (EvidenceUnavailable, ValueError, KeyError, TypeError, OSError) as error:
            if identity.get("verdict") != "PASS":
                raise EvidenceUnavailable("当前Mech服务绑定尚未取得完整原件：" + str(error)) from None
            discovery_error = str(error)
        slots = []
        for number in range(SLOTS):
            chosen = selected[number] if number < len(selected) else None
            rid = chosen["hint"]["requestId"].lower() if chosen else None
            slots.append({"slot": number + 1, "purpose": "behavioral", "request_id": rid,
                "task_key": f"eip155:100:mech:{mech}:request:{rid}" if rid else None,
                "qualification_index": chosen["index"] if chosen else None})
        plan = {"schema_version": "mech-history-plan-v1", "policy_version": POLICY_VERSION,
            "policy": policy, "created_at": datetime.now(timezone.utc).isoformat(),
            "chain_id": 100, "registry": REGISTRY, "agent_id": profile.agent_id,
            "mech": mech, "service_id": service_id, "snapshot_block": profile.snapshot_block,
            "snapshot_hash": profile.snapshot_hash, "confirmation_head": profile.confirmation_head,
            "cutoff_timestamp": profile.cutoff_timestamp, "history_bound": DISCOVERY_LIMIT,
            "selection": "一页按交付时间降序的最多32条线索，保留首7个不同requestId的普通marketplace请求；不按输出或成绩筛选。",
            "eligibility_uses_outputs": False, "pilot_only": False, "slots": slots,
            "excluded": excluded, "discovery_error": discovery_error, "index": index,
            "selected_count": len(selected), "status": "PLANNED" if len(selected) == SLOTS else "PARTIAL",
            "measurement_purpose": "background", "mainnet_writes": False, "paid_calls": False, "retries": 0}
        plan_reference = store.save("mech-history-plan.json", plan)
        store._remember([plan_reference])
        tasks = []
        for position, slot in enumerate(slots):
            heartbeat()
            task = {**slot, "input": None, "output": None, "chain_evidence": None,
                    "source_refs": [], "verdict": "UNKNOWN"}
            try:
                if slot["request_id"] is None:
                    task["reason"] = discovery_error or "固定一页资料不足7个受支持的独立任务；保留空槽，未补选。"
                    continue
                hint = selected[position]["hint"]
                task["hint"] = hint
                task["chain_evidence"] = collect_task(store, hint, profile)
                anchors = extract_task_anchors(task["chain_evidence"], mech=mech,
                    request_id=slot["request_id"], confirmation_head=profile.confirmation_head)
                task["anchors"] = anchors
                if (anchors["input_digest"] != hint["request"]["marketplaceRequest"].get("ipfsHashBytes")
                    or anchors["output_digest"] != hint["marketplaceDelivery"].get("ipfsHashBytes")
                    or anchors["request_block"] != int(hint["request"]["blockNumber"])
                    or anchors["delivery_block"] != int(hint["blockNumber"])
                    or anchors["request_timestamp"] != int(hint["request"]["blockTimestamp"])
                    or anchors["delivery_timestamp"] != int(hint["blockTimestamp"])):
                    raise EvidenceUnavailable("目录提示与原始链上任务的CID、区块或时间不一致；未换槽。")
                task["input"] = store.ipfs(f"mech-slot-{slot['slot']:02d}-input", anchors["input_digest"], "metadata.json")
                task["source_refs"].extend(task["input"]["evidence"])
                task["output"] = store.ipfs(f"mech-slot-{slot['slot']:02d}-output", anchors["output_digest"],
                                            str(int(slot["request_id"], 16)))
                task["source_refs"].extend(task["output"]["evidence"])
                task["reason"] = "历史原件已采集；交易与交付结论由独立核验器重算，未评价业务内容正确性。"
            except (EvidenceUnavailable, ValueError, KeyError, TypeError, OSError) as error:
                task["reason"] = str(error)
            finally:
                tasks.append(task)
                sync_inputs()
                heartbeat()
        sync_inputs()
        inputs = [{"path": path, "sha256": digest} for path, digest in sorted(evidence.inputs.items())]
        bundle = {"schema_version": "mech-task-evidence-bundle-v1", "profile": vars(profile),
            "identity": identity, "plan": plan, "plan_reference": plan_reference, "tasks": tasks,
            "tool_manifests": tool_manifests, "inputs": inputs, "issues": store.issues,
            "new_request_count": store.sent}
        bundle_reference = store.save("mech-task-bundle.json", bundle)
        source_manifest = store.save("mech-source-manifest.json", {
            "schema_version": "mech-task-source-manifest-v1", "completed_at": datetime.now(timezone.utc).isoformat(),
            "inputs": inputs, "outputs": [bundle_reference]})
        evidence.inputs[bundle_reference["path"]] = bundle_reference["sha256"]
        evidence.inputs[source_manifest["path"]] = source_manifest["sha256"]
        return evidence.root / bundle_reference["path"]
    finally:
        sync_inputs()
        store.close()
