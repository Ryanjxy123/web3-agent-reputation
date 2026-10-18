"""Prepare a prediction runtime from authenticated registration and public sources."""

from dataclasses import asdict
import json
import re

from eth_hash.auto import keccak

from reputation_core.admission import ProbeObservation
from reputation_core.application import normalize_reference
from reputation_core.prediction_chain import BRIDGER, REGISTRY, calldata
from reputation_platform.mech_task_collection import _mech_hint, _tool_manifests
from reputation_platform.mech_task_evidence import _catalog
from reputation_platform.mech_task_identity import verify_mech_identity
from reputation_platform.prediction_evidence import EvidenceUnavailable, MECH_INDEX, PredictionProfile, file_reference
from reputation_platform.prediction_report import RetainedEvidence, _registration_timing
from reputation_platform.registration_discovery import verify_registration_proof

FIXED_NATIVE_FACTORY = "0x8b299c20f87e3fcbff0e1b86dc0acc06ab6993ef"
FACTORY_QUERY = """query MechsOrderedByServiceDeliveries {
  meches(first: 40, orderBy: totalDeliveriesTransactions, orderDirection: desc) {
    id address mechFactory totalDeliveriesTransactions
    service { id totalDeliveries metadata { metadata } }
  }
}"""


def _factory_row(data: dict, mech: str | None, service_id: int, references: list[dict]) -> dict | None:
    rows = data.get("meches")
    if not isinstance(rows, list) or len(rows) > 40:
        return None
    matches = [row for row in rows if isinstance(row, dict)
               and isinstance(row.get("service"), dict) and str(row["service"].get("id")) == str(service_id)
               and (mech is None or str(row.get("address", "")).lower() == mech)]
    if len(matches) > 1:
        raise EvidenceUnavailable("官方目录中同一服务的Mech线索不唯一；未按名称、交付量或版本猜选地址。")
    if not matches:
        return None
    address = str(matches[0].get("address", ""))
    if (not re.fullmatch(r"0x[0-9a-fA-F]{40}", address) or int(address, 16) == 0
        or not re.fullmatch(r"0x[0-9a-fA-F]{40}", str(matches[0].get("mechFactory", "")))):
        return None
    return {"mech": address.lower(), "service_id": service_id, "factory": matches[0]["mechFactory"].lower(),
            "evidence": references, "source": "official-index-protocol-hint",
            "note": "factory仅用于当前实现的协议适用性门禁；每个任务的支付、执行与交付仍须独立核验。"}


def _factory_source(reader: RetainedEvidence, store, mech: str | None, service_id: int) -> dict:
    retained = []
    for key, item in store.cache.items():
        if json.loads(key)[0] == MECH_INDEX:
            retained.append(item["evidence"])
    for path in sorted(reader.root.glob("runtime/olas-*/*mech-directory*.observation.json")):
        try:
            observed = ProbeObservation.model_validate_json(path.read_bytes())
            response = (path.parent / observed.response_file).resolve() if observed.response_file else None
            if response is not None and response.parent == path.parent:
                retained.append([file_reference(path, reader.root), file_reference(response, reader.root)])
        except (ValueError, TypeError, OSError):
            continue
    for references in retained:
        try:
            observed, raw = reader.observation(references, url=MECH_INDEX, method="POST")
            request, payload = json.loads(observed.request_json), json.loads(raw)
            query = request.get("query")
            if not isinstance(query, str) or "mutation" in query.lower() or payload.get("errors"):
                continue
            found = _factory_row(payload.get("data", {}), mech, service_id, references)
            if found:
                return found
        except (ValueError, KeyError, TypeError, OSError):
            continue
    # Exact known query_mechs fields and bounds; no guessed filter or factory getter.
    indexed = store.graphql("prediction-mech-directory", MECH_INDEX, FACTORY_QUERY)
    found = _factory_row(indexed["data"], mech, service_id, indexed["evidence"])
    if found is None:
        raise EvidenceUnavailable("官方目录这一限定页未提供本Mech与服务的唯一factory线索；保留通用接入，不推测预测协议兼容性。")
    return found


def _registration_date(reader: RetainedEvidence, store, profile: PredictionProfile,
                       identity: dict, directory: dict | None) -> None:
    try:
        payload = directory["payload"] if directory else {}
        if directory:
            reader.observation(directory["evidence"],
                url=f"https://api.8004scan.io/api/v1/agents/100/{profile.agent_id}", method="GET")
        hint = payload.get("created_tx_hash")
        block_hint = payload.get("created_block_number")
        block_hint = int(block_hint) if block_hint is not None else None
        identity["registration_lookup"] = {"transaction_hint": hint, "block_hint": block_hint,
                                            "source": "authenticated-directory-hint-not-registration-time"}
        if not isinstance(hint, str) or not re.fullmatch(r"0x[0-9a-fA-F]{64}", hint):
            if block_hint is None or not 0 < block_hint <= profile.snapshot_block:
                raise EvidenceUnavailable("未取得登记交易或登记区块线索；未从创世区块扫描，登记时间仍缺证据。")
            topic = "0x" + keccak(b"Transfer(address,address,uint256)").hex()
            query = {"address": REGISTRY, "fromBlock": hex(block_hint), "toBlock": hex(block_hint),
                     "topics": [topic, "0x" + "0" * 64, "0x" + BRIDGER[2:].zfill(64),
                                "0x" + f"{profile.agent_id:064x}"]}
            identity["registration_lookup"]["bounded_log_query"] = query
            logs = store.rpc("prediction-registration-mint-index", "eth_getLogs", [query])["value"]
            if (not isinstance(logs, list) or len(logs) != 1 or logs[0].get("removed") is not False
                or logs[0].get("address", "").lower() != REGISTRY or logs[0].get("topics") != query["topics"]):
                raise EvidenceUnavailable("单个提示区块未返回唯一登记铸造线索；未翻页或扩大扫描。")
            hint = logs[0].get("transactionHash")
            if not isinstance(hint, str) or not re.fullmatch(r"0x[0-9a-fA-F]{64}", hint):
                raise EvidenceUnavailable("登记铸造日志没有完整交易哈希。")
        hint = hint.lower()
        receipt = store.rpc("prediction-registration-receipt", "eth_getTransactionReceipt", [hint])
        block = int(receipt["value"]["blockNumber"], 16)
        if not 0 < block <= profile.snapshot_block or block_hint is not None and block_hint != block:
            raise EvidenceUnavailable("登记回执未落在固定快照或提示的准确区块内。")
        proofs = {"receipt": receipt,
            "transaction": store.rpc("prediction-registration-transaction", "eth_getTransactionByHash", [hint]),
            "header": store.rpc("prediction-registration-header", "eth_getBlockByNumber", [hex(block), False])}
        timing = _registration_timing({"registration_evidence": reader.tree(proofs)}, profile, derive_time=True)
        identity.update(timing)
    except (EvidenceUnavailable, ValueError, KeyError, TypeError, OSError) as error:
        identity["registration_gap"] = str(error)


def prepare_prediction_source(registration, evidence, store) -> dict | None:
    canonical = normalize_reference(registration.get("canonical", ""))
    if canonical is None or canonical.split(":")[1:3] != ["100", REGISTRY]:
        return None
    reader = RetainedEvidence(evidence.root)

    def dependencies() -> dict[str, str]:
        store._remember([{"path": path, "sha256": digest} for path, digest in reader.inputs.items()])
        evidence.inputs.update(reader.inputs)
        evidence.inputs.update({item["path"]: item["sha256"] for item in store.inputs.values()})
        return dict(evidence.inputs)

    try:
        verified = verify_registration_proof(evidence.root, registration["proof_path"], canonical)
        proof = reader.json(registration["proof_path"])
        rpc = proof["rpc"]
        if (not verified["registration_verified"] or not proof.get("document")
            or int(rpc["owner"]["value"], 16) != int(BRIDGER, 16)):
            return None
        uri = verified["token_uri"]
        matched = re.fullmatch(r"https://marketplace\.olas\.network/(?:api/)?erc8004/gnosis/ai-agents/(0|[1-9][0-9]*)", uri)
        if matched is None:
            return None
        service_id = int(matched[1])
        mech = _mech_hint(verified["services"])
        factory = None
        if mech is None:
            factory = _factory_source(reader, store, None, service_id)
            mech = factory["mech"]
        document = proof["document"]
        observed, _ = reader.observation(document["evidence"], url=uri, method="GET")
        observed_name = next(item["path"] for item in document["evidence"] if item["path"].endswith(".observation.json"))
        source = (evidence.root / observed_name).parent / observed.response_file
        header = rpc["header"]["value"]
        profile = PredictionProfile(candidate_key=registration["candidate_key"], mech=mech,
            service_id=service_id, agent_id=int(canonical.split(":")[-1]),
            registration_source=source.relative_to(evidence.root).as_posix(), registration_sha256=document["sha256"],
            snapshot_block=int(header["number"], 16), snapshot_hash=header["hash"].lower(),
            confirmation_head=int(rpc["head"]["value"], 16), cutoff_timestamp=1790812800)
        identity = {"chain": rpc["chain"], "head": rpc["head"], "header": rpc["header"],
            "calls": {"registration-owner": rpc["owner"], "registration-uri": rpc["uri"]},
            "registration": {"payload": document["payload"], "response_file": profile.registration_source,
                             "evidence": document["evidence"]},
            "historical_note": "当前登记不会前推为历史登记；任务时的同服务、执行控制及支付仍须逐项核对。"}
        for name, target, signature, arguments in (
            ("bridger-agent-id", BRIDGER, "mapServiceIdAgentIds(uint256)", (profile.service_id,)),
            ("mech-service-id", mech, "serviceId()", ()),
            ("mech-service-registry", mech, "serviceRegistry()", ()),
            ("mech-operator", mech, "getOperator()", ()),
        ):
            identity["calls"][name] = store.call("prediction-identity-" + name, target,
                                                 calldata(signature, *arguments), profile.snapshot_block)
        binding = verify_mech_identity(reader, {"profile": asdict(profile), "identity": identity}, canonical)
        factory = factory or _factory_source(reader, store, mech, profile.service_id)
        if factory["factory"] != FIXED_NATIVE_FACTORY:
            raise EvidenceUnavailable("当前自动预测只适配已知Fixed Price Native协议；此factory未适配，不假设订阅或其它支付兼容。")
        identity["factory_protocol_hint"] = factory
        try:
            catalog, catalog_proof = _catalog(reader, binding, {**evidence.inputs, **reader.inputs})
        except ValueError:
            declarations = _tool_manifests(verified["services"], evidence, reader)
            for declaration in declarations:
                try:
                    catalog, catalog_proof = _catalog(reader, binding, {},
                        {"url": declaration["url"], "evidence": declaration["evidence"]})
                    break
                except (ValueError, KeyError, TypeError, OSError):
                    continue
            else:
                raise EvidenceUnavailable("登记manifest尚无可认证的工具目录原件；未按名称猜测预测能力。")
        _registration_date(reader, store, profile, identity, proof.get("directory"))
        return {"profile": profile, "identity": identity, "catalog": catalog,
                "catalog_proof": catalog_proof, "retained_inputs": dependencies()}
    finally:
        dependencies()
