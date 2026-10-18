"""Bounded, retained evidence collection for the frozen Gnosis prediction protocol."""

from dataclasses import asdict, dataclass
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import secrets
import threading
from urllib.parse import urlsplit

from reputation_core.admission import ProbeObservation
from reputation_core.ipfs import verify_car_file
from reputation_core.scoring import PREDICTION_POLICY_VERSIONS
from reputation_core.prediction_chain import (
    BRIDGER, CT, MARKETPLACE, PROXY, REALITY, REGISTRY, SERVICE_REGISTRY,
    calldata, verify_omen_settlement, verify_prediction_chain, extract_task_anchors,
)
from reputation_platform.safe_http import PublicTarget, SafeHttpClient
from reputation_platform.settings import PROJECT_ROOT

RPC = "https://rpc.gnosischain.com"
MECH_INDEX = "https://api.subgraph.autonolas.tech/api/proxy/marketplace-gnosis"
OMEN_INDEX = "https://omen.subgraph.autonolas.tech"
GATEWAY = "https://gateway.autonolas.tech/ipfs/"
POLICY = "docs/adr/0008-prediction-history-policy.md"
EXCLUDED_MARKETS = {"0xf4004bb9ff8ded28d9f75443a0c95de00f8a1bc1", "0x00f6727ebdd4b473419d950e9e017ee454ea464b"}
READ_METHODS = {"eth_chainId", "eth_blockNumber", "eth_getBlockByNumber", "eth_getTransactionByHash",
                "eth_getTransactionReceipt", "eth_call", "eth_getLogs", "eth_getCode"}


def file_reference(path: Path, root: Path = PROJECT_ROOT) -> dict:
    return {"path": path.resolve().relative_to(root.resolve()).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def runtime_directory(path: str | Path, root: Path = PROJECT_ROOT) -> Path:
    directory, runtime = (root / path).resolve(), (root / "runtime").resolve()
    if (directory == runtime or not directory.is_relative_to(runtime) or not directory.is_dir()
        or any(part.lower() in {"secrets", "platform-config"} for part in directory.relative_to(runtime).parts)):
        raise ValueError("Evidence sources must be existing public runtime directories")
    return directory


@dataclass(frozen=True)
class PredictionProfile:
    candidate_key: str
    mech: str
    service_id: int
    agent_id: int
    registration_source: str
    registration_sha256: str
    snapshot_block: int
    snapshot_hash: str
    confirmation_head: int
    cutoff_timestamp: int = 1790812800
    history_page_size: int = 32
    history_max_deliveries: int = 128
    chain_id: int = 100
    policy_version: str = "prediction-history-v1"
    registry: str = REGISTRY

    def __post_init__(self):
        if (not self.candidate_key or self.chain_id != 100 or self.registry != REGISTRY
            or self.policy_version not in PREDICTION_POLICY_VERSIONS or not re.fullmatch(r"0x[0-9a-f]{40}", self.mech)
            or type(self.service_id) is not int or self.service_id < 0 or type(self.agent_id) is not int or self.agent_id < 0
            or not re.fullmatch(r"[0-9a-f]{64}", self.registration_sha256)
            or not re.fullmatch(r"0x[0-9a-f]{64}", self.snapshot_hash)
            or self.snapshot_block < 0 or self.confirmation_head - self.snapshot_block < 64
            or self.cutoff_timestamp != 1790812800 or not 1 <= self.history_page_size <= 64
            or not self.history_page_size <= self.history_max_deliveries <= 512):
            raise ValueError("Operator profile does not match the supported frozen Gnosis policy")

    @property
    def registration_reference(self) -> str:
        return f"eip155:100:{REGISTRY}:{self.agent_id}"

    @classmethod
    def load(cls, path: Path) -> "PredictionProfile":
        return cls(**json.loads(path.read_bytes()))


class EvidenceUnavailable(RuntimeError):
    pass


class EvidenceStore:
    def __init__(self, run: Path, reuse_runs: list[Path], *, enabled: bool = False,
                 proxy: str | None = None, max_requests: int = 1200, parallel_reads: int = 2, root: Path = PROJECT_ROOT):
        if enabled and not proxy:
            raise ValueError("Public reads require an explicit operator proxy")
        if type(parallel_reads) is not int or not 1 <= parallel_reads <= 4:
            raise ValueError("Independent public reads must use one to four workers")
        self.root, self.run = root.resolve(), run.resolve()
        self.enabled, self.proxy, self.limit, self.sent = enabled, proxy, max_requests, 0
        self.client = None
        self.lock = threading.Lock()
        self.parallel_reads = parallel_reads
        self.cache, self.inputs, self.issues, self.stopped_hosts = {}, {}, [], set()
        for supplied in reuse_runs:
            directory = runtime_directory(supplied, self.root)
            for observation_path in sorted(directory.glob("*.observation.json")):
                try:
                    observation = ProbeObservation.model_validate_json(observation_path.read_bytes())
                    if (observation.http_status != 200 or observation.error_kind or not observation.body_complete
                        or not observation.response_file):
                        continue
                    response_path = (directory / observation.response_file).resolve()
                    if not response_path.is_relative_to(directory) or not response_path.is_file():
                        raise ValueError("response_path_outside_run")
                    raw = response_path.read_bytes()
                    if hashlib.sha256(raw).hexdigest() != observation.response_sha256:
                        raise ValueError("response_digest_mismatch")
                    request = json.loads(observation.request_json) if observation.request_json else None
                    self._scope(observation.url, observation.method, request)
                    references = [file_reference(observation_path, self.root), file_reference(response_path, self.root)]
                    self.cache[self._key(observation.url, observation.method, request)] = {
                        "raw": raw, "response_file": response_path.relative_to(self.root).as_posix(),
                        "evidence": references, "purpose": observation.purpose.value,
                        "request": request, "observed_at": observation.observed_at.isoformat()}
                except (OSError, ValueError, TypeError, KeyError) as error:
                    self.issues.append({"source": observation_path.relative_to(self.root).as_posix(), "reason": str(error)})

    @staticmethod
    def _key(url: str, method: str, body: dict | None) -> str:
        canonical = dict(body) if body is not None else None
        if url == RPC and canonical is not None:
            canonical.pop("id", None)
        return json.dumps([url, method, canonical], sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _scope(url: str, method: str, body: dict | None):
        if url == RPC and method == "POST" and body and body.get("method") in READ_METHODS and body.get("jsonrpc") == "2.0":
            return
        if url in {MECH_INDEX, OMEN_INDEX} and method == "POST" and body and isinstance(body.get("query"), str):
            if "mutation" not in body["query"].lower():
                return
        if method == "GET" and (re.fullmatch(r"https://gateway\.autonolas\.tech/ipfs/f01701220[0-9a-f]{64}/(?:metadata\.json|[0-9]+)(?:\?format=car&dag-scope=entity)?", url)
            or re.fullmatch(r"https://gateway\.autonolas\.tech/ipfs/f01701220[0-9a-f]{64}\?format=car&dag-scope=entity", url)
            or re.fullmatch(r"https://marketplace\.olas\.network/(?:api/)?erc8004/gnosis/ai-agents/[0-9]+", url)):
            return
        raise ValueError("Request is outside the operator-supported read-only protocol")

    def _remember(self, references: list[dict]):
        for item in references:
            self.inputs[item["path"]] = item

    def _stop_host(self, host: str, reason: str):
        self.stopped_hosts.add(host)
        directory = self.root / "runtime/prediction-network-stops"
        directory.mkdir(exist_ok=True)
        try:
            with (directory / (host + ".json")).open("x", encoding="utf-8") as stream:
                json.dump({"host": host, "reason": reason, "source_run": self.run.relative_to(self.root).as_posix()}, stream)
        except FileExistsError:
            pass

    def request(self, key: str, url: str, method: str = "GET", body: dict | None = None) -> dict:
        self._scope(url, method, body)
        cache_key = self._key(url, method, body)
        if cache_key in self.cache:
            retained = self.cache[cache_key]
            self._remember(retained["evidence"])
            return retained
        host = urlsplit(url).hostname
        with self.lock:
            if not self.enabled:
                raise EvidenceUnavailable("Required immutable evidence is not retained; public reads are disabled")
            if (self.sent >= self.limit or host in self.stopped_hosts
                or (self.root / "runtime/prediction-network-stops" / (host + ".json")).is_file()):
                raise EvidenceUnavailable("Request bound reached or this host stopped after access/payment/rate-limit response")
            self.sent += 1
            key = re.sub(r"[^a-z0-9-]", "-", key.lower())[:90] + f"-{self.sent:04d}"
        target = PublicTarget(key, url, method, json_body=body)
        planned = self.run / f"{key}.request-plan.json"
        planned.write_text(json.dumps({"key": key, "url": url, "method": method, "json": body,
                                      "measurement_purpose": "background", "retries": 0}, indent=2), encoding="utf-8")
        with self.lock:
            if self.client is None:
                self.client = SafeHttpClient((target,), enabled=True, proxy=self.proxy, max_requests=self.limit)
            else:
                # Every target passes the fixed protocol scope above before it enters the client list.
                self.client.targets[key] = target
        observation = self.client.fetch(key, self.run)
        references = [file_reference(planned, self.root), file_reference(self.run / f"{key}.observation.json", self.root)]
        if observation.http_status in (401, 402, 403, 429):
            self._stop_host(host, f"HTTP {observation.http_status}")
        if observation.response_file:
            references.append(file_reference(self.run / observation.response_file, self.root))
        self._remember(references)
        if observation.http_status != 200 or observation.error_kind or not observation.body_complete or not observation.response_file:
            raise EvidenceUnavailable(observation.error_kind or "Incomplete or unsuccessful public read")
        retained = {"raw": (self.run / observation.response_file).read_bytes(),
                    "response_file": (self.run / observation.response_file).relative_to(self.root).as_posix(),
                    "evidence": references, "purpose": "background", "request": body,
                    "observed_at": observation.observed_at.isoformat()}
        self.cache[cache_key] = retained
        return retained

    def rpc(self, name: str, method: str, params: list) -> dict:
        request = {"jsonrpc": "2.0", "id": self.sent + 1, "method": method, "params": params}
        retained = self.request(name, RPC, "POST", request)
        payload = json.loads(retained["raw"])
        original = retained["request"]
        if (not isinstance(payload, dict) or payload.get("jsonrpc") != "2.0" or payload.get("id") != original["id"]
            or "error" in payload or payload.get("result") is None):
            error = payload.get("error", {}) if isinstance(payload, dict) else {}
            if isinstance(error, dict) and (error.get("code") in (-32005, -32016, 429)
                or any(term in str(error.get("message", "")).lower() for term in ("rate limit", "quota", "too many requests"))):
                self._stop_host(urlsplit(RPC).hostname, "RPC access or rate limit")
            raise EvidenceUnavailable("RPC error or missing result; retained without retry or endpoint switching")
        return {"method": method, "params": params, "value": payload["result"], "evidence": retained["evidence"]}

    def call(self, name: str, contract: str, data: str, block: int) -> dict:
        return self.rpc(name, "eth_call", [{"to": contract, "data": data}, hex(block)])

    def graphql(self, name: str, url: str, query: str) -> dict:
        retained = self.request(name, url, "POST", {"query": query})
        payload = json.loads(retained["raw"])
        if payload.get("errors") or not isinstance(payload.get("data"), dict):
            raise EvidenceUnavailable("The official index did not return the supported query shape")
        return {"data": payload["data"], "evidence": retained["evidence"]}

    def ipfs(self, name: str, digest: str, filename: str, *, root_layout: bool = False) -> dict:
        if not re.fullmatch(r"0x[0-9a-f]{64}", digest) or not re.fullmatch(r"metadata\.json|[0-9]+", filename):
            raise ValueError("Unsupported fixed CID or filename")
        if root_layout:
            from reputation_platform.prediction_content import collect_root_or_path_content

            return collect_root_or_path_content(self, name, digest, filename)
        url = GATEWAY + "f01701220" + digest[2:] + "/" + filename
        content = self.request(name, url)
        car = self.request(name + "-car", url + "?format=car&dag-scope=entity")
        verification = verify_car_file(car["raw"], digest, filename, content["raw"])
        format_error = None
        try:
            payload = json.loads(content["raw"])
            if not isinstance(payload, dict):
                payload, format_error = None, "CID-authenticated content is not the declared JSON object"
        except (ValueError, UnicodeError):
            payload, format_error = None, "CID-authenticated bytes are not valid JSON"
        return {"payload": payload, "url": url, "response_file": content["response_file"],
                "sha256": hashlib.sha256(content["raw"]).hexdigest(), "car_file": car["response_file"],
                "car_verification": verification, "format_error": format_error,
                "evidence": content["evidence"] + car["evidence"]}

    def save(self, name: str, value: dict | list):
        path = self.run / name
        with path.open("x", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
        return file_reference(path, self.root)

    def close(self):
        if self.client is not None:
            self.client.__exit__()


def create_run(profile: PredictionProfile, profile_path: Path, *, root: Path = PROJECT_ROOT) -> Path:
    now = datetime.now(timezone.utc)
    run = root / "runtime" / f"prediction-history-{now:%Y%m%dT%H%M%SZ}-{secrets.token_hex(4)}"
    run.mkdir()
    manifest = {"started_at": now.isoformat(), "policy_version": profile.policy_version, "measurement_purpose": "background",
                "profile": asdict(profile), "inputs": [file_reference(profile_path, root), file_reference(root / POLICY, root)],
                "stages": ["identity", "qualification_without_outputs", "persist_fourteen_slot_plan", "selected_outputs", "independent_chain_checks"],
                "mainnet_writes": False, "paid_calls": False, "retries": 0}
    (run / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return run


def _single_word(proof: dict) -> int:
    value = proof["value"]
    if not isinstance(value, str) or not re.fullmatch(r"0x[0-9a-fA-F]{64}", value):
        raise EvidenceUnavailable("A fixed ABI getter did not return one word")
    return int(value, 16)


def _parallel_reads(store: EvidenceStore, specifications: list[tuple[str, str, list]]) -> dict:
    """At most four independent reads; stop submitting further chunks after a failure."""
    output = {}
    width = store.parallel_reads
    with ThreadPoolExecutor(max_workers=width) as executor:
        for offset in range(0, len(specifications), width):
            chunk = specifications[offset:offset + width]
            pending = [(name, executor.submit(store.rpc, name, method, params)) for name, method, params in chunk]
            for name, future in pending:
                output[name] = future.result()
    return output


def _abi_text(proof: dict) -> str:
    encoded = bytes.fromhex(proof["value"][2:])
    if len(encoded) < 64 or int.from_bytes(encoded[:32]) != 32:
        raise EvidenceUnavailable("Unsupported ABI text")
    length = int.from_bytes(encoded[32:64])
    if len(encoded) != 64 + (length + 31) // 32 * 32 or any(encoded[64 + length:]):
        raise EvidenceUnavailable("Truncated ABI text")
    return encoded[64:64 + length].decode("utf-8")


def collect_identity(store: EvidenceStore, profile: PredictionProfile) -> dict:
    """Current ERC-8004 mapping is distinct from historical service control."""
    n, calls = profile.snapshot_block, {}
    chain = store.rpc("chain-id", "eth_chainId", [])
    if int(chain["value"], 16) != profile.chain_id:
        raise EvidenceUnavailable("Trusted RPC returned another chain; collection stopped")
    head = store.rpc("head", "eth_blockNumber", [])
    if int(head["value"], 16) < profile.confirmation_head:
        raise EvidenceUnavailable("Retained head does not establish the declared confirmation distance")
    header = store.rpc("snapshot-header", "eth_getBlockByNumber", [hex(n), False])
    if header["value"]["hash"].lower() != profile.snapshot_hash or int(header["value"]["number"], 16) != n:
        raise EvidenceUnavailable("Frozen snapshot hash differs; collection stopped")
    specifications = []
    for name, target, signature, args in (
        ("registration-owner", REGISTRY, "ownerOf(uint256)", (profile.agent_id,)),
        ("registration-uri", REGISTRY, "tokenURI(uint256)", (profile.agent_id,)),
        ("bridger-agent-id", BRIDGER, "mapServiceIdAgentIds(uint256)", (profile.service_id,)),
        ("mech-service-id", profile.mech, "serviceId()", ()),
        ("mech-service-registry", profile.mech, "serviceRegistry()", ()),
        ("mech-operator", profile.mech, "getOperator()", ()),
    ):
        specifications.append((name, "eth_call", [{"to": target, "data": calldata(signature, *args)}, hex(n)]))
    calls.update(_parallel_reads(store, specifications))
    expected_uri = f"https://marketplace.olas.network/erc8004/gnosis/ai-agents/{profile.service_id}"
    if (_single_word(calls["registration-owner"]) != int(BRIDGER, 16)
        or _single_word(calls["bridger-agent-id"]) != profile.agent_id
        or _single_word(calls["mech-service-id"]) != profile.service_id
        or _single_word(calls["mech-service-registry"]) != int(SERVICE_REGISTRY, 16)
        or _abi_text(calls["registration-uri"]) != expected_uri):
        raise EvidenceUnavailable("Current registry, bridge and Mech service identities do not agree")
    source = (store.root / profile.registration_source).resolve()
    runtime_directory(source.parent, store.root)
    if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != profile.registration_sha256:
        raise EvidenceUnavailable("Operator-frozen registration source hash differs")
    registration = store.request("chain-registration-document", expected_uri)
    if hashlib.sha256(registration["raw"]).hexdigest() != profile.registration_sha256:
        raise EvidenceUnavailable("The fixed on-chain URI and retained registration document differ")
    document = json.loads(registration["raw"])
    operator_endpoint = f"https://{profile.mech[2:]}-100.mech.valory.xyz"
    registrations = document.get("registrations", [])
    if (not any(item.get("agentId") == profile.agent_id
                and str(item.get("agentRegistry", "")).lower() == f"eip155:100:{REGISTRY}" for item in registrations)
        or not any(item.get("name") == "operator" and item.get("endpoint") == operator_endpoint
                   for item in document.get("services", []))):
        raise EvidenceUnavailable("Official registration does not bind this actual Mech and ERC-8004 identity")
    store._remember([file_reference(source, store.root)])
    return {"verdict": "PASS", "reason": "固定块注册持有人为官方桥；桥映射、原注册JSON和Mech同服务绑定已核实，holder与执行Safe分开。",
            "chain": chain, "head": head, "header": header, "calls": calls, "registration": {
                "payload": document, "response_file": registration["response_file"], "evidence": registration["evidence"]},
            "historical_note": "当前ERC-8004注册不被前推为历史注册；每项任务另核任务区块的同服务与执行控制。"}


def collect_market(store: EvidenceStore, market: str, profile: PredictionProfile, header: dict) -> dict:
    if not re.fullmatch(r"0x[0-9a-f]{40}", market):
        raise EvidenceUnavailable("Original input does not specify one valid Omen market")
    query = ('{fixedProductMarketMaker(id:"' + market + '"){id outcomes '
             'conditions{id oracle questionId outcomeSlotCount} question{id title outcomes templateId data '
             'openingTimestamp currentAnswer answerFinalizedTimestamp isPendingArbitration}}}')
    index = store.graphql("omen-market-index", OMEN_INDEX, query)
    indexed = index["data"].get("fixedProductMarketMaker")
    if not isinstance(indexed, dict) or not isinstance(indexed.get("question"), dict):
        raise EvidenceUnavailable("Official Omen index has no supported original market question")
    question, n = indexed["question"], profile.snapshot_block
    question_id = question.get("id", "")
    if not re.fullmatch(r"0x[0-9a-f]{64}", question_id):
        raise EvidenceUnavailable("Official Omen index lacks an exact question identifier")
    calls = {}
    def read(name, target, signature, *args):
        calls[name] = store.call(name, target, calldata(signature, *args), n)
        return _single_word(calls[name])
    read("market-ct", market, "conditionalTokens()")
    condition = read("market-condition", market, "conditionIds(uint256)", 0)
    condition_id = "0x" + f"{condition:064x}"
    specifications = []
    for name, target, signature, args in (
        ("proxy-reality", PROXY, "realitio()", ()),
        ("proxy-ct", PROXY, "conditionalTokens()", ()),
        ("outcome-count", CT, "getOutcomeSlotCount(bytes32)", (condition_id,)),
        ("payout-denominator", CT, "payoutDenominator(bytes32)", (condition_id,)),
        ("payout-0", CT, "payoutNumerators(bytes32,uint256)", (condition_id, 0)),
        ("payout-1", CT, "payoutNumerators(bytes32,uint256)", (condition_id, 1)),
        ("reality-finalized", REALITY, "isFinalized(bytes32)", (question_id,)),
        ("reality-answer", REALITY, "resultFor(bytes32)", (question_id,)),
        ("reality-content-hash", REALITY, "getContentHash(bytes32)", (question_id,)),
        ("reality-opening", REALITY, "getOpeningTS(bytes32)", (question_id,)),
        ("reality-finalize-ts", REALITY, "getFinalizeTS(bytes32)", (question_id,)),
        ("reality-template-hash", REALITY, "template_hashes(uint256)", (int(question["templateId"]),)),
    ):
        specifications.append((name, "eth_call", [{"to": target, "data": calldata(signature, *args)}, hex(n)]))
    calls.update(_parallel_reads(store, specifications))
    return {"market": market, "question": question, "index": index, "header": header, "calls": calls}


def collect_task(store: EvidenceStore, hint: dict, profile: PredictionProfile, *, include_calls: bool = True) -> dict:
    parts = {"calls": {}}
    specifications = []
    for side, indexed in (("request", hint["request"]), ("delivery", hint)):
        transaction_hash = indexed["transactionHash"]
        if not re.fullmatch(r"0x[0-9a-f]{64}", transaction_hash):
            raise EvidenceUnavailable("Unsupported index transaction hash")
        block = int(indexed["blockNumber"])
        specifications.extend([(side + "-transaction", "eth_getTransactionByHash", [transaction_hash]),
                               (side + "-receipt", "eth_getTransactionReceipt", [transaction_hash]),
                               (side + "-header", "eth_getBlockByNumber", [hex(block), False])])
    proofs = _parallel_reads(store, specifications)
    for side in ("request", "delivery"):
        tx, receipt, header = [proofs[side + "-" + kind] for kind in ("transaction", "receipt", "header")]
        parts[side] = {"transaction": tx["value"], "receipt": receipt["value"], "header": header["value"],
                       "proofs": {"transaction": tx, "receipt": receipt, "header": header}}
    if not include_calls:
        return parts
    rb, db, rid = int(hint["request"]["blockNumber"]), int(hint["blockNumber"]), hint["requestId"]
    specifications = []
    for name, target, signature, arguments, block in (
        ("request-info-before", MARKETPLACE, "mapRequestIdInfos(bytes32)", (rid,), db - 1),
        ("request-info-after", MARKETPLACE, "mapRequestIdInfos(bytes32)", (rid,), db),
        ("delivery-operator", profile.mech, "getOperator()", (), db),
        ("request-service-id", profile.mech, "serviceId()", (), rb),
        ("request-service-registry", profile.mech, "serviceRegistry()", (), rb),
        ("delivery-service-id", profile.mech, "serviceId()", (), db),
        ("delivery-service-registry", profile.mech, "serviceRegistry()", (), db),
        ("delivery-authorized", MARKETPLACE, "checkMech(address)", (profile.mech,), db),
        ("delivery-payment-type", profile.mech, "paymentType()", (), db),
    ):
        specifications.append((name, "eth_call", [{"to": target, "data": calldata(signature, *arguments)}, hex(block)]))
    parts["calls"] = _parallel_reads(store, specifications)
    return parts


def _history_query(profile: PredictionProfile, skip: int) -> str:
    return ('{delivers(first:' + str(profile.history_page_size) + ',skip:' + str(skip)
            + ',orderBy:blockTimestamp,orderDirection:desc,where:{mech:"' + profile.mech
            + '",blockTimestamp_lt:"' + str(profile.cutoff_timestamp) + '",blockNumber_lte:"'
            + str(profile.snapshot_block) + '"}){id requestId mech blockNumber blockTimestamp transactionHash '
              'marketplaceDelivery{ipfsHashBytes mechServiceMultisig} '
              'request{id blockNumber blockTimestamp transactionHash marketplaceRequest{ipfsHashBytes}}}}')


def _history_anchors(store: EvidenceStore, hint: dict, profile: PredictionProfile) -> dict:
    anchors = extract_task_anchors(collect_task(store, hint, profile, include_calls=False), mech=profile.mech,
                                   request_id=hint['requestId'], confirmation_head=profile.confirmation_head)
    indexed_input = hint['request']['marketplaceRequest']['ipfsHashBytes']
    indexed_output = hint['marketplaceDelivery']['ipfsHashBytes']
    if ((indexed_input is not None and indexed_input != anchors['input_digest'])
        or (indexed_output is not None and indexed_output != anchors['output_digest'])
        or anchors['delivery_timestamp'] != int(hint['blockTimestamp'])):
        raise EvidenceUnavailable('Index CID/time hints differ from the actual retained on-chain task')
    return anchors


def collect_history(store: EvidenceStore, profile: PredictionProfile, *, pilot_hint: dict | None = None,
                    identity: dict | None = None, supported_operations: set[str] | None = None,
                    profile_reference: dict | None = None) -> dict:
    supplied_identity = identity is not None
    if supported_operations is not None and (not isinstance(supported_operations, set)
        or any(not isinstance(operation, str) or not operation.strip() for operation in supported_operations)):
        raise ValueError("Supported prediction operations must be a set of nonempty catalog names")
    operations = frozenset(supported_operations) if supported_operations is not None else None
    if supplied_identity or profile_reference is not None:
        # Local imports avoid a cycle: the retained reader also imports PredictionProfile.
        from reputation_platform.mech_task_identity import verify_mech_identity
        from reputation_platform.prediction_report import RetainedEvidence

        retained = RetainedEvidence(store.root)
        try:
            if supplied_identity:
                verify_mech_identity(retained, {"profile": asdict(profile), "identity": identity},
                                     profile.registration_reference)
            if profile_reference is not None:
                path = retained.remember(profile_reference["path"], profile_reference["sha256"])
                if json.loads(path.read_bytes()) != asdict(profile):
                    raise ValueError("Runtime prediction profile differs from its retained original")
        finally:
            store._remember([{"path": name, "sha256": digest} for name, digest in retained.inputs.items()])
    if identity is None:
        identity = collect_identity(store, profile)
    header = identity["header"]["value"]
    hints, qualifications, selected, tasks, seen_markets = [], [], [], [], set()
    expanded = profile.policy_version == 'prediction-history-v2'
    seen_questions = set()
    if pilot_hint is not None:
        hints = [pilot_hint]
        store._remember(pilot_hint.get("index_evidence", []))
    else:
        for skip in range(0, profile.history_max_deliveries, profile.history_page_size):
            index = store.graphql("delivery-index", MECH_INDEX, _history_query(profile, skip))
            page = index["data"].get("delivers")
            if not isinstance(page, list):
                raise EvidenceUnavailable("Official delivery index has an unsupported shape")
            hints.extend(page)
            if len(page) < profile.history_page_size:
                break
        hints.sort(key=lambda item: (int(item["blockTimestamp"]), int(item["blockNumber"]), item["id"]), reverse=True)
    for hint in hints:
        record = {"request_id": hint.get("requestId"), "hint": hint, "verdict": "UNKNOWN"}
        qualifications.append(record)
        try:
            rid = hint["requestId"]
            if (not re.fullmatch(r"0x[0-9a-f]{64}", rid) or hint.get("mech", profile.mech) != profile.mech
                or int(hint["blockNumber"]) > profile.snapshot_block
                or (pilot_hint is None and int(hint["blockTimestamp"]) >= profile.cutoff_timestamp)):
                raise EvidenceUnavailable("Index record is outside the frozen instance/time range")
            indexed_input = hint['request']['marketplaceRequest']['ipfsHashBytes']
            indexed_output = hint['marketplaceDelivery']['ipfsHashBytes']
            anchors = _history_anchors(store, hint, profile) if indexed_input is None or indexed_output is None else None
            input_digest = anchors['input_digest'] if anchors is not None else indexed_input
            input_content = store.ipfs("request-content", input_digest, "metadata.json", root_layout=expanded)
            if input_content["payload"] is None:
                raise EvidenceUnavailable(input_content["format_error"])
            if operations is not None:
                record["input"] = input_content
                operation = input_content["payload"].get("tool")
                if not isinstance(operation, str) or not operation:
                    raise EvidenceUnavailable("Original task does not identify a declared prediction operation")
                record["operation"] = operation
                if operation not in operations:
                    record.update(verdict="NOT_APPLICABLE", reason="实际请求工具不属于本次已核验的预测操作集合；保留背景，不读取交付结果或计入预测样本。")
                    continue
            context = input_content["payload"].get("request_context", {})
            if expanded and context == {}:
                from reputation_platform.prediction_question_resolution import resolve_exact_question

                resolution = resolve_exact_question(store, input_content['payload'])
                record['question_resolution'] = resolution
                if resolution['method'] == 'omen-exact-direct-question-v1':
                    store._remember([file_reference(store.root/'docs/adr/0017-prediction-question-and-output-contract.md', store.root)])
                market = resolution['market']
            else:
                if not isinstance(context, dict) or not isinstance(context.get("market_id"), str):
                    raise EvidenceUnavailable("Original task lacks an explicit supported market identifier")
                market = context["market_id"].lower()
            record["market"], record["input"] = market, input_content
            if not re.fullmatch(r"0x[0-9a-f]{40}", market) or ('question_resolution' not in record and context.get("type") != "omen"):
                raise EvidenceUnavailable("Original CID-authenticated request is not a supported Omen market task")
            if market in seen_markets or (pilot_hint is None and market in EXCLUDED_MARKETS):
                record.update(verdict="NOT_APPLICABLE", reason="同市场较早任务或已查看pilot市场；保留背景，不进入正式分母。")
                continue
            seen_markets.add(market)
            if anchors is None:
                anchors = _history_anchors(store, hint, profile)
            record["anchors"] = anchors
            market_evidence = collect_market(store, market, profile, header)
            settlement = verify_omen_settlement(market_evidence, snapshot_block=profile.snapshot_block, snapshot_hash=profile.snapshot_hash)
            record["market_evidence"], record["settlement_verification"] = market_evidence, settlement.model_dump(mode="json")
            if settlement.verdict.value != "PASS":
                record.update(verdict=settlement.verdict.value, reason=settlement.reason)
                continue
            if expanded:
                if 'question_resolution' in record:
                    resolution = record['question_resolution']
                    if settlement.question_id != resolution['question_id'] or settlement.title != resolution['title']:
                        raise EvidenceUnavailable('Exact-title discovery differs from the actual on-chain question')
                if settlement.question_id in seen_questions:
                    record.update(verdict='NOT_APPLICABLE', reason='同一独立问题的较早或其它市场交付不重复计入V2样本。')
                    continue
                seen_questions.add(settlement.question_id)
                record['question_id'] = settlement.question_id
            prompt = input_content["payload"].get("prompt")
            title_bound = isinstance(prompt, str) and (f'"{settlement.title}"' in prompt or expanded
                and record.get('question_resolution', {}).get('method') == 'omen-exact-direct-question-v1'
                and prompt == settlement.title)
            if (not title_bound
                or not isinstance(input_content["payload"].get("tool"), str)
                or not int(hint["blockTimestamp"]) < settlement.opening_timestamp
                or not int(hint["blockTimestamp"]) < settlement.finalized_timestamp):
                raise EvidenceUnavailable("Original task does not exactly bind this title/tool or precede market close/finalization")
            record.update(verdict="PASS", reason="资格仅依据输入原件、时间、不同市场和链上有效二元结算；未读取交付输出。")
            selected.append(record)
            if len(selected) == (1 if pilot_hint is not None else 14):
                break
        except (EvidenceUnavailable, ValueError, KeyError, TypeError) as error:
            record.update(verdict="UNKNOWN", reason=str(error))
    slots = []
    for index in range(1 if pilot_hint is not None else 14):
        chosen = selected[index] if index < len(selected) else None
        slots.append({"slot": index + 1, "purpose": "background" if pilot_hint is not None else ("functional" if index < 7 else "behavioral"),
                      "request_id": chosen["request_id"] if chosen else None, "market": chosen["market"] if chosen else None,
                      "task_key": f"{profile.chain_id}:{profile.mech}:{chosen['request_id']}" if chosen else None,
                      "qualification_index": qualifications.index(chosen) if chosen else None})
        if expanded:
            slots[-1]['question_id'] = chosen['question_id'] if chosen else None
    plan = {"policy_version": profile.policy_version, "pilot_only": pilot_hint is not None, "slots": slots,
            "eligibility_uses_outputs": False, "cutoff_timestamp": profile.cutoff_timestamp,
            "excluded_pilot_markets": sorted(EXCLUDED_MARKETS), "history_bound": profile.history_max_deliveries,
            "qualified_market_count": len(selected), "status": "READY" if len(selected) == len(slots) else "PARTIAL"}
    if operations is not None:
        plan["supported_operations"] = sorted(operations)
    # Append-only files are durable before the first selected-output read below.
    store.save("qualifications.json", qualifications)
    plan_reference = store.save("plan.json", plan)
    for slot in slots:
        if slot["request_id"] is None:
            tasks.append({**slot, "verdict": "UNKNOWN", "reason": "固定筛选范围内缺少合资格的独立市场，不替换或省略槽位。"})
            continue
        chosen = qualifications[slot["qualification_index"]]
        task = {**slot, "input": chosen["input"], "output": None, "hint": chosen["hint"],
                "market_evidence": chosen["market_evidence"], "settlement_verification": chosen["settlement_verification"]}
        if chosen.get('question_resolution'):
            task['question_resolution'] = chosen['question_resolution']
        try:
            task["chain_evidence"] = collect_task(store, chosen["hint"], profile)
            verification = verify_prediction_chain(task["chain_evidence"], mech=profile.mech, service_id=profile.service_id,
                request_id=slot["request_id"], confirmation_head=profile.confirmation_head,
                marketplace_event_revision=2 if profile.policy_version == 'prediction-history-v2' else 1)
            task["chain_verification"] = verification.model_dump(mode="json")
            task["output"] = store.ipfs("delivery-content", chosen['anchors']['output_digest'], str(int(slot["request_id"], 16)), root_layout=expanded)
            task["source_refs"] = task["input"]["evidence"] + task["output"]["evidence"]
        except (EvidenceUnavailable, ValueError, KeyError, TypeError) as error:
            task.update(verdict="UNKNOWN", reason=str(error))
        tasks.append(task)
        store.save(f"task-{slot['slot']:02d}.json", task)
    bundle = {"schema_version": "prediction-evidence-bundle-v1", "profile": asdict(profile), "identity": identity,
              "plan": plan, "plan_reference": plan_reference, "qualifications": qualifications, "tasks": tasks,
              "inputs": list(store.inputs.values()), "issues": store.issues, "new_request_count": store.sent}
    if supplied_identity:
        bundle["identity_protocol"] = "mech-registered-v1"
    if profile_reference is not None:
        bundle["profile_reference"] = dict(profile_reference)
    store.save("bundle.json", bundle)
    return bundle
