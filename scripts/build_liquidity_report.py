"""Build the limited liquidity-history report from retained evidence, without network calls."""

import argparse
import base64
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
from math import isfinite
from pathlib import Path
import re
import secrets
import sys

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = (ROOT / "runtime").resolve()
sys.path[:0] = [str(ROOT / "packages/core/src"), str(ROOT / "services/platform/src")]

from collect_liquidity_history import (
    NPM, POSITIONS_SELECTOR, REUSE_RPC_URLS, call_key, prepare, rpc_value,
)
from collect_liquidity_context import CAKE, DECIMALS, FACTORY, GET_POOL, OWNER_OF, WBNB
from probe_liquidity_state import runtime_directory
from sample_availability import classify
from reputation_core import CandidateRecord, MeasurementPurpose, ProbeObservation, Verdict
from reputation_core.behavior import verify_behavior
from reputation_core.disclosure import DECREASE_TOPIC, verify_disclosure
from reputation_core.liquidity import INCREASE_TOPIC
from reputation_core.planning import LiquidityHistoryDescriptor, PlanSelection
from reputation_core.reporting import EvaluationReport, ReportFinding, SampleExplanation
from reputation_core.scoring import ScoredSample
from reputation_platform.evaluation_report import render_evaluation_report

CONFIG: Path | None = None
POLICY = ROOT / "docs/adr/0004-liquidity-history-policy.md"
IMPLEMENTATION = ROOT / "docs/adr/0005-evidence-binding-and-complete-slots.md"
REGISTERED = "0xca52e62c367d81bb2e328eb795f7c7ba24afb478408a26c0e201d155c449bc4a"
READ_METHODS = {"eth_chainId", "eth_blockNumber", "eth_getBlockByNumber", "eth_getTransactionByHash",
                "eth_getTransactionReceipt", "eth_call", "eth_getLogs", "eth_getCode", "eth_getBalance"}
LABEL = {Verdict.PASS: "通过", Verdict.FAIL: "未通过", Verdict.UNKNOWN: "无法判断"}


class Gap(ValueError):
    pass


class Mismatch(ValueError):
    pass


def load(path: Path, *, exact: bool = False):
    return json.loads(path.read_bytes(), parse_float=Decimal if exact else float)


def local(directory: Path, name: str) -> Path:
    path = (directory / name).resolve()
    if not path.is_relative_to(directory) or not path.is_file():
        raise Gap("缺少保留文件或文件路径超出指定目录：" + name)
    return path


def ref(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def uint(value: object) -> int:
    if not isinstance(value, str) or not re.fullmatch(r"0x[0-9a-fA-F]+", value):
        raise Gap("缺少规范十六进制数量")
    return int(value, 16)


def fixed_hex(value: object, digits: int) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"0x[0-9a-fA-F]{" + str(digits) + "}", value):
        raise Gap("固定长度十六进制证据不完整")
    return value.lower()


def address_word(value: object) -> str:
    number = uint(fixed_hex(value, 64))
    if not 0 < number < 2**160:
        raise Gap("地址返回值不是规范非零 ABI 地址")
    return "0x" + f"{number:040x}"


def same(actual: object, expected: object, label: str) -> None:
    if actual != expected:
        raise Mismatch(label + "与独立证据不一致")


def when(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise Gap("来源时间缺少时区")
    return result


def finding(label: str, verdict: Verdict, explanation: str) -> ReportFinding:
    return ReportFinding(label=label, verdict=verdict, explanation=explanation)


def token_amount(value: str | None, decimals: int = 18) -> str:
    if value is None:
        return "尚未核实"
    digits = value.zfill(decimals + 1)
    if not decimals:
        return digits
    return (digits[:-decimals] + "." + digits[-decimals:]).rstrip("0").rstrip(".")


def display_time(value: datetime | None) -> str:
    return value.astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S") if value else "未记录"


class Evidence:
    def __init__(self, cache: dict, directories: list[Path]) -> None:
        self.cache, self.inputs, self.issues, self.heads = cache, {}, [], []
        for directory in directories:
            for path in sorted(directory.glob("*.observation.json")):
                if path.name.startswith("input-"):
                    continue
                try:
                    request, value, references = self.rpc(path)
                    if request["method"] == "eth_blockNumber" and request["params"] == []:
                        self.heads.append((uint(value), references))
                except (OSError, KeyError, TypeError, ValueError) as error:
                    self.issues.append({"observation": ref(path), "reason": str(error)})

    def check_ref(self, item: dict) -> Path:
        path = (ROOT / item["path"]).resolve()
        allowed = path.is_relative_to(RUNTIME) or path in {CONFIG, POLICY.resolve(),
                    (ROOT / "configs/trusted-bsc-zan.json").resolve()}
        if not allowed or not path.is_file() or digest(path) != item["sha256"]:
            raise Gap("输入摘要不匹配或超出本次证据范围：" + str(item.get("path")))
        self.inputs[ref(path)] = item["sha256"]
        return path

    def rpc(self, path: Path, expected: tuple | None = None) -> tuple:
        observation = load(path)
        if (observation["method"] != "POST" or observation["url"] not in REUSE_RPC_URLS
            or observation["http_status"] != 200 or observation["error_kind"]
            or not observation["body_complete"] or not observation["response_file"]):
            raise Gap("RPC 观测不是完整成功的可信 BSC 只读响应")
        request = json.loads(observation["request_json"])
        if request.get("jsonrpc") != "2.0" or request.get("method") not in READ_METHODS or not isinstance(request.get("params"), list):
            raise Gap("RPC 请求方法或参数格式不在允许范围")
        if expected is not None and call_key(request["method"], request["params"]) != call_key(*expected):
            raise Gap("RPC 原始请求与所需固定参数不一致")
        response = local(path.parent, observation["response_file"])
        if digest(response) != observation["response_sha256"]:
            raise Gap("RPC 原件摘要不匹配")
        value = rpc_value(load(response), request)
        references = [ref(path), ref(response)]
        for source in (path, response):
            self.inputs[ref(source)] = digest(source)
        return request, value, references

    def get(self, method: str, params: list, evidence: set[str]):
        record = self.cache.get(call_key(method, params))
        if record is None:
            raise Gap("缺少真实 RPC 请求/响应：" + method + " " + json.dumps(params, ensure_ascii=False))
        paths = [self.check_ref(item) for item in record["evidence"]]
        observations = [path for path in paths if path.name.endswith(".observation.json")]
        if len(observations) != 1:
            raise Gap("RPC 观测出处不唯一")
        _, value, references = self.rpc(observations[0], (method, params))
        evidence.update(references)
        return value

    def head(self, evidence: set[str]) -> int:
        if not self.heads:
            raise Gap("缺少真实 eth_blockNumber 确认高度响应")
        value, references = max(self.heads, key=lambda item: item[0])
        evidence.update(references)
        return value


def bind(tx: dict, receipt: dict, block: dict, expected_hash: str, sender: str | None,
         target: str, head: int, distance: int) -> tuple[int, int]:
    expected_hash = fixed_hex(expected_hash, 64)
    same(uint(tx["chainId"]), 56, "交易链号")
    same(fixed_hex(tx["hash"], 64), expected_hash, "交易哈希")
    same(fixed_hex(receipt["transactionHash"], 64), expected_hash, "回执交易哈希")
    actual_sender = fixed_hex(tx["from"], 40)
    if sender is not None:
        same(actual_sender, sender.lower(), "执行者")
    same(fixed_hex(receipt["from"], 40), actual_sender, "回执执行者")
    for item in (tx, receipt):
        same(fixed_hex(item["to"], 40), target.lower(), "调用目标")
    number, index = uint(tx["blockNumber"]), uint(tx["transactionIndex"])
    block_hash = fixed_hex(tx["blockHash"], 64)
    same(fixed_hex(receipt["blockHash"], 64), block_hash, "回执区块哈希")
    same(fixed_hex(block["hash"], 64), block_hash, "独立区块头哈希")
    same(uint(receipt["blockNumber"]), number, "回执区块高度")
    same(uint(block["number"]), number, "区块头高度")
    same(uint(receipt["transactionIndex"]), index, "回执交易序号")
    if not isinstance(block["transactions"], list) or index >= len(block["transactions"]):
        raise Gap("区块中缺少该交易序号")
    same(fixed_hex(block["transactions"][index], 64), expected_hash, "区块交易列表")
    if head - number < distance:
        raise Gap("独立确认距离不足")
    if uint(receipt["status"]) == 0:
        raise Mismatch("该执行者对指定目标的交易已回滚")
    if uint(receipt["status"]) != 1 or not isinstance(receipt["logs"], list):
        raise Gap("回执状态或事件列表不完整")
    positions = []
    for log in receipt["logs"]:
        same(fixed_hex(log["transactionHash"], 64), expected_hash, "事件交易哈希")
        same(fixed_hex(log["blockHash"], 64), block_hash, "事件区块哈希")
        same(uint(log["blockNumber"]), number, "事件区块高度")
        same(uint(log["transactionIndex"]), index, "事件交易序号")
        if log["removed"] is not False:
            raise Gap("事件已被移除或缺少规范状态")
        positions.append(uint(log["logIndex"]))
    if len(set(positions)) != len(positions) or positions != sorted(positions):
        raise Gap("回执事件序号重复或无序")
    return number, uint(block["timestamp"])


def registration_uri(data: str) -> tuple[dict, bytes]:
    if not isinstance(data, str) or not re.fullmatch(r"0x(?:[0-9a-fA-F]{2})+", data):
        raise Gap("注册事件 URI ABI 数据格式不完整")
    raw = bytes.fromhex(data[2:])
    if len(raw) < 64 or int.from_bytes(raw[:32], "big") != 32:
        raise Gap("注册 URI 不是单 string ABI 编码")
    length = int.from_bytes(raw[32:64], "big")
    if len(raw) != 64 + ((length + 31) // 32) * 32 or any(raw[64 + length:]):
        raise Gap("注册 URI 长度或填充不规范")
    uri = raw[64:64 + length].decode("utf-8")
    prefix = "data:application/json;base64,"
    if not uri.startswith(prefix):
        raise Gap("注册事件未内嵌可离线核验的 JSON data URI")
    document = base64.b64decode(uri[len(prefix):], validate=True)
    return json.loads(document), document


def verify_registration(store: Evidence, config: dict, history: dict) -> tuple[Verdict, str, dict, set[str]]:
    evidence, facts = set(), {}
    try:
        same(uint(store.get("eth_chainId", [], evidence)), 56, "可信 RPC 链号")
        tx_hash = config["registration_tx_hash"].lower()
        tx = store.get("eth_getTransactionByHash", [tx_hash], evidence)
        receipt = store.get("eth_getTransactionReceipt", [tx_hash], evidence)
        block = store.get("eth_getBlockByNumber", [receipt["blockNumber"], False], evidence)
        number, timestamp = bind(tx, receipt, block, tx_hash, None, config["registry"],
                                 store.head(evidence), config["confirmation_distance"])
        events = [log for log in receipt["logs"] if fixed_hex(log["address"], 40) == config["registry"].lower()
                  and log["topics"] and log["topics"][0].lower() == REGISTERED]
        matching = [event for event in events if len(event["topics"]) == 3
                    and uint(fixed_hex(event["topics"][1], 64)) == config["agent_id"]]
        if len(matching) != 1:
            raise Gap("Registered 事件中缺少唯一匹配的 Agent ID")
        event = matching[0]
        owner = address_word(event["topics"][2])
        document, document_bytes = registration_uri(event["data"])
        wallets = [item["value"] for item in document["attributes"]
                   if item.get("trait_type") == "Operating wallet"]
        endpoints = [item["endpoint"] for item in document["services"] if item.get("name") == "record"]
        if len(wallets) != 1 or len(endpoints) != 1:
            raise Gap("注册文件缺少唯一 Operating wallet 或 record 服务")
        same(wallets[0].lower(), "eip155:56:" + config["execution_wallet"].lower(), "注册文件运营钱包")
        same(endpoints[0], config["history_source_url"], "注册文件公开记录接口")
        all_indices = sorted(config["functional_indices"] + config["behavioral_indices"] + config["not_applicable_indices"])
        for index in all_indices:
            row = history["history"][index]
            if timestamp > when(row["at"]).timestamp():
                raise Mismatch("实际注册时间晚于冻结运行记录")
            same(row["wallet"].lower(), config["execution_wallet"].lower(), "公开运行记录执行钱包")
        facts = {"agent_id": config["agent_id"], "registration_owner": owner,
                 "execution_wallet": config["execution_wallet"], "record_endpoint": endpoints[0],
                 "registration_block": number, "registration_timestamp": timestamp,
                 "registration_document_sha256": hashlib.sha256(document_bytes).hexdigest(),
                 "role_note": "注册 NFT 持有人与实际执行钱包分角色；关联来自注册事件内 Operating wallet，而非收款地址"}
        return Verdict.PASS, "链上注册事件、登记时的运营钱包/记录接口，以及登记后运行记录关联均已核实", facts, evidence
    except Mismatch as error:
        return Verdict.FAIL, str(error), facts, evidence
    except (OSError, KeyError, IndexError, TypeError, ValueError) as error:
        return Verdict.UNKNOWN, "注册与执行关联证据不足：" + str(error), facts, evidence


def validate_plan(run: Path, config: dict, history_file: Path, store: Evidence) -> tuple[CandidateRecord, set[str]]:
    manifest = load(local(run, "manifest.json"))
    paths = [store.check_ref(item) for item in manifest["inputs"]]
    selection = PlanSelection.model_validate(load(local(run, "selection.json")))
    descriptor = LiquidityHistoryDescriptor.model_validate(load(local(run, "descriptor.json")))
    if selection.status != "SELECTED" or selection.policy_id != config["policy_version"]:
        raise Gap("离线计划未选中本次冻结方案")
    same(descriptor.candidate_key, selection.candidate_key, "计划候选身份")
    same(descriptor.claim_ids, selection.claim_ids, "计划引用声明")
    same(descriptor.chain_id, 56, "计划链号")
    same(descriptor.protocol, "pancakeswap-v3-npm", "计划协议")
    same(descriptor.history_shape, "run-history-increase-v1", "计划记录类型")
    same((ROOT / descriptor.history_source_file).resolve(), history_file, "计划历史来源文件")
    same(digest(history_file), config["history_response_sha256"], "计划历史来源摘要")
    same(descriptor.published_execution_wallet.lower(), config["execution_wallet"].lower(), "计划执行钱包")
    same(descriptor.trusted_manager.lower(), NPM, "计划仓位管理器")
    reports = [path for path in paths if path.name == "admission-report.json"]
    if len(reports) != 1:
        raise Gap("计划缺少唯一背景候选报告")
    candidates = [item for item in load(reports[0])["candidates"] if item["key"] == selection.candidate_key]
    if len(candidates) != 1:
        raise Gap("背景候选身份不唯一")
    candidate = dict(candidates[0])
    candidate.pop("ready_for_full_score", None)
    references = {ref(path) for path in paths} | {ref(local(run, name)) for name in ("manifest.json", "selection.json", "descriptor.json", "selected-claims.json")}
    return CandidateRecord.model_validate(candidate), references


def availability(run: Path, config: dict, store: Evidence) -> list[SampleExplanation]:
    manifest_path = local(run, "manifest.json")
    manifest = load(manifest_path)
    same(store.check_ref(manifest["policy"]), POLICY.resolve(), "可用性政策文件")
    same(store.check_ref(manifest["config"]), CONFIG.resolve(), "可用性配置文件")
    for key, value in (("policy_version", config["policy_version"]), ("purpose", "availability"),
                       ("url", config["history_source_url"]), ("method", "GET"),
                       ("request_limit", 10), ("interval_seconds", 30), ("retries", 0)):
        same(manifest[key], value, "可用性计划 " + key)
    slots = manifest["slots"]
    if len(slots) != 10 or manifest["run_id"] != run.name:
        raise Gap("可用性计划不是该运行的固定十槽")
    result, stopped = [], False
    for ordinal, slot in enumerate(slots, 1):
        key = f"availability-{ordinal:03d}"
        same(slot["target_key"], key, "可用性槽名称")
        same(slot["scheduled_offset_seconds"], (ordinal - 1) * 30, "可用性固定起点")
        same(slot["sample_id"], f"{run.name}:{ordinal:03d}", "可用性样本标识")
        same(slot["task_key"], f"availability:{run.name}:{ordinal:03d}", "可用性任务标识")
        evidence, elapsed, observed, status = {ref(manifest_path)}, None, None, None
        try:
            if stopped:
                path = local(run, key + ".skip.json")
                skipped = load(path)
                same(skipped["request_key"], key, "跳过槽标识")
                same(skipped["purpose"], "availability", "跳过槽用途")
                same(skipped["request_sent"], False, "跳过槽未发送状态")
                observed = when(skipped["observed_at"])
                evidence.add(ref(path))
                verdict, reason = Verdict.UNKNOWN, "前一响应触发主机停止规则；本槽未发送请求"
            else:
                path = local(run, key + ".observation.json")
                observation = ProbeObservation.model_validate(load(path))
                same(observation.request_key, key, "真实观测槽标识")
                same(observation.purpose, MeasurementPurpose.AVAILABILITY, "真实观测用途")
                same((observation.url, observation.method, observation.request_json),
                     (config["history_source_url"], "GET", None), "真实可用性查询")
                evidence.add(ref(path))
                if observation.response_file:
                    body = local(run, observation.response_file)
                    same(digest(body), observation.response_sha256, "可用性原始响应摘要")
                    evidence.add(ref(body))
                elif observation.response_sha256 is not None:
                    raise Gap("响应原件与摘要记录不完整")
                observed, elapsed, status = observation.observed_at, observation.elapsed_ms, observation.http_status
                stopped = status in (401, 402, 403, 429)
                verdict, reason = classify(observation, run)
                if not isfinite(elapsed) or elapsed < 0:
                    verdict, reason = Verdict.UNKNOWN, "真实耗时记录无效"
        except (OSError, KeyError, TypeError, ValueError) as error:
            verdict, reason = Verdict.UNKNOWN, "可用性原件无法完整核对：" + str(error)
        sample = ScoredSample(sample_id=slot["sample_id"], task_key=slot["task_key"],
            purpose=MeasurementPurpose.AVAILABILITY, verdict=verdict, elapsed_ms=elapsed,
            reason=reason, evidence=sorted(evidence))
        result.append(SampleExplanation(sample=sample, observed_at=observed,
            title=f"公开运行记录访问 · 第 {ordinal} 次",
            input_summary=f"GET 公开运行记录入口；固定计划起点为第 {(ordinal - 1) * 30} 秒；本槽专用于可用性。",
            claimed_output="期望返回 JSON 对象，其中 history 为列表、last 为对象。",
            independent_result=f"重新核对原件后，本槽{LABEL[verdict]}。HTTP 状态：{status if status is not None else '未取得响应'}；"
                               + (f"实际观测耗时 {elapsed:.2f} 毫秒。" if elapsed is not None else "没有可计的请求耗时。"),
            checks=[finding("响应原件与预期结构", verdict, reason)]))
    return result


def task_explanation(task: dict, row: dict, store: Evidence, config: dict,
                     identity: tuple, history_refs: set[str]) -> tuple[SampleExplanation, dict]:
    index, purpose = task["history_index"], MeasurementPurpose(task["purpose"])
    evidence, checks = set(history_refs), [finding("注册身份与执行关联", identity[0], identity[1])]
    evidence.update(identity[3])
    step = row.get("steps", {}).get("increase", {})
    details, observed, core = {}, None, None
    claimed = f"公开记录的仓位为 {step.get('position', '缺失')}。"
    if purpose == MeasurementPurpose.FUNCTIONAL:
        claimed += f"使用 CAKE {step.get('other_used', '缺失')}、WBNB {step.get('wbnb_used', '缺失')}，执行后流动性份额为 {step.get('liquidity_after', '缺失')}（协议内部份额数，不是资产金额）。"
    else:
        claimed += "记录宣称依次包装 BNB、买入缺少的一侧代币，再增加仓位流动性。"
    try:
        same(row["wallet"].lower(), config["execution_wallet"].lower(), "运行记录执行者")
        if task["planning_gaps"]:
            raise Gap("冻结任务结构缺项：" + "; ".join(task["planning_gaps"]))
        token_id = int(step["position"])
        same(token_id, task["token_id"], "冻结仓位标识")
        transactions = {item["role"]: item["hash"] for item in task["transactions"]}
        final_hash = transactions["increase"]
        tx = store.get("eth_getTransactionByHash", [final_hash], evidence)
        receipt = store.get("eth_getTransactionReceipt", [final_hash], evidence)
        block = store.get("eth_getBlockByNumber", [receipt["blockNumber"], False], evidence)
        head = store.head(evidence)
        number, timestamp = bind(tx, receipt, block, final_hash, config["execution_wallet"], NPM,
                                 head, config["confirmation_distance"])
        observed = datetime.fromtimestamp(timestamp, timezone.utc)
        started = when(row["at"]).timestamp()
        if not started <= timestamp <= started + config["task_window_seconds"]:
            raise Mismatch("最终增仓交易超出该公开运行记录的任务窗口")
        checks.append(finding("真实交易、区块顺序与确认距离", Verdict.PASS,
                              f"最终增仓位于区块 {number}，交易序号 {uint(tx['transactionIndex'])}；独立确认高度为 {head}。"))
        owner = address_word(store.get("eth_call", [{"to": NPM, "data": OWNER_OF + f"{token_id:064x}"}, hex(number)], evidence))
        same(owner, config["execution_wallet"].lower(), "固定区块仓位持有人")
        checks.append(finding("固定区块仓位归属", Verdict.PASS, f"仓位 #{token_id} 在最终增仓区块属于实际执行钱包。"))
        if purpose == MeasurementPurpose.FUNCTIONAL:
            data = POSITIONS_SELECTOR + f"{token_id:064x}"
            before = store.get("eth_call", [{"to": NPM, "data": data}, hex(number - 1)], evidence)
            after = store.get("eth_call", [{"to": NPM, "data": data}, hex(number)], evidence)
            logs = store.get("eth_getLogs", [{"address": NPM, "fromBlock": hex(number), "toBlock": hex(number),
                "topics": [[INCREASE_TOPIC, DECREASE_TOPIC], "0x" + f"{token_id:064x}"]}], evidence)
            decimals = [uint(fixed_hex(store.get("eth_call", [{"to": token, "data": DECIMALS}, hex(number)], evidence), 64))
                        for token in (CAKE, WBNB)]
            core = verify_disclosure(tx, receipt, chain_id=56, expected_sender=config["execution_wallet"],
                manager=NPM, token_id=token_id, expected_tx_hash=final_hash, block_timestamp=timestamp,
                positions_before=before, positions_after=after, block_logs=logs,
                declared_liquidity_after=step.get("liquidity_after"), declared_amount0=step.get("other_used"),
                declared_amount1=step.get("wbnb_used"), decimals0=decimals[0], decimals1=decimals[1],
                expected_token0=CAKE, expected_token1=WBNB)
            summary = (f"按区块 {number - 1} 与 {number} 的固定状态和完整增减仓事件顺序，"
                       f"重建该交易后的流动性份额为 {core.actual_liquidity_after or '尚无法确定'}；"
                       f"链上实际使用 CAKE {token_amount(core.actual_amount0_base_units, decimals[0])}、"
                       f"WBNB {token_amount(core.actual_amount1_base_units, decimals[1])}。")
            checks.append(finding("精确金额与目标交易后流动性", core.verdict, summary))
        else:
            proofs = {}
            for role in ("wrap", "swap", "increase"):
                try:
                    role_hash = transactions[role]
                    role_tx = store.get("eth_getTransactionByHash", [role_hash], evidence)
                    role_receipt = store.get("eth_getTransactionReceipt", [role_hash], evidence)
                    role_block = store.get("eth_getBlockByNumber", [role_receipt["blockNumber"], False], evidence)
                    proofs[role] = {"transaction": role_tx, "receipt": role_receipt, "block": role_block}
                except (KeyError, TypeError, ValueError):
                    proofs[role] = {}
            pool, pool_block = None, None
            try:
                swap_tx, swap_receipt = proofs["swap"]["transaction"], proofs["swap"]["receipt"]
                calldata = swap_tx["input"]
                if not isinstance(calldata, str) or len(calldata) != 522 or calldata[:10].lower() != "0x414bf389":
                    raise Gap("兑换 calldata 尚未适配")
                words = [uint("0x" + calldata[start:start + 64]) for start in range(10, len(calldata), 64)]
                lookup = GET_POOL + f"{words[0]:064x}{words[1]:064x}{words[2]:064x}"
                pool = address_word(store.get("eth_call", [{"to": FACTORY, "data": lookup}, swap_receipt["blockNumber"]], evidence))
                pool_block = uint(swap_receipt["blockNumber"])
            except (KeyError, TypeError, ValueError):
                pass
            core = verify_behavior(proofs, expected_tx_hashes=transactions, expected_sender=config["execution_wallet"],
                token_id=token_id, trusted_pool=pool, trusted_pool_block=pool_block,
                confirmation_head=head, task_started_at=started, chain_id=56,
                task_window_seconds=config["task_window_seconds"], confirmation_distance=config["confirmation_distance"])
            for role, label in (("wrap", "包装原生币"), ("swap", "可信池兑换"), ("increase", "最终增仓")):
                checked = getattr(core, role)
                passed_explanation = {
                    "wrap": "实际支付的 BNB 与执行钱包收到的 WBNB 包装存款事件精确一致。",
                    "swap": "兑换池由独立的固定区块 factory 查询确定；实际支付与接收数量、接收者和最低接收限制均匹配。",
                    "increase": "指定仓位的增仓调用、两种资产转入及最终事件精确匹配，截止时间和调用目标也已核实。",
                }
                checks.append(finding(label, checked.verdict,
                    passed_explanation[role] if checked.verdict == Verdict.PASS else checked.reason))
            summary = "三笔独立核验结果：" + "；".join(
                f"{label}{LABEL[getattr(core, role).verdict]}" for role, label in
                (("wrap", "包装"), ("swap", "兑换"), ("increase", "增仓"))) + "。"
            if core.swap.amount_in is not None:
                summary += f"兑换支付 WBNB {token_amount(core.swap.amount_in)}、收到 CAKE {token_amount(core.swap.amount_out)}。"
        verdict, reason = core.verdict, core.reason
        details = core.model_dump(mode="json")
    except Mismatch as error:
        verdict, reason, summary = Verdict.FAIL, str(error), "真实链上证据与该运行记录的身份、仓位或执行约束存在明确矛盾。" + str(error)
        checks.append(finding("独立链上约束", verdict, reason))
    except (OSError, KeyError, IndexError, TypeError, ValueError) as error:
        verdict, reason, summary = Verdict.UNKNOWN, str(error), "必要证据尚不能完整对齐，本条不记为失败。缺项：" + str(error)
        checks.append(finding("独立证据完整性", verdict, reason))
    if identity[0] != Verdict.PASS:
        verdict = Verdict.UNKNOWN
        reason = "注册身份或运营钱包关联尚未闭合；底层核验保留但不能归为候选的完整结论。" + reason
        summary += " 注册身份与执行关联尚未闭合，因此本条最终为无法判断。"
    sample = ScoredSample(sample_id="liquidity-history-v1:" + task["task_key"], task_key=task["task_key"],
        purpose=purpose, verdict=verdict, elapsed_ms=None, reason=reason, evidence=sorted(evidence))
    explanation = SampleExplanation(sample=sample, observed_at=observed,
        title=("结果披露" if purpose == MeasurementPurpose.FUNCTIONAL else "三笔操作") + f" · 运行记录 {index}",
        input_summary=f"BNB Chain 上登记后的运行记录 {index}，记录起始时间 {row.get('at', '缺失')}；"
                      f"核对仓位 #{step.get('position', '缺失')} 和该记录预先公布的交易。",
        claimed_output=claimed, independent_result=f"本条{LABEL[verdict]}。" + summary, checks=checks)
    return explanation, {"history_index": index, "purpose": purpose.value, "verdict": verdict.value,
                         "verification": details, "task_key": task["task_key"]}


def main() -> int:
    global CONFIG
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, required=True, help="Explicit operator-owned profile under configs/pilots")
    for name in ("history-run", "context-run", "availability-run", "plan-run"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--rpc-runs", nargs="+", type=Path, required=True)
    args = parser.parse_args()
    CONFIG = (ROOT / args.profile).resolve()
    history_run, context_run, availability_run, plan_run = (
        runtime_directory(getattr(args, name + "_run")) for name in ("history", "context", "availability", "plan")
    )
    rpc_runs = list(dict.fromkeys([runtime_directory(path) for path in args.rpc_runs] + [context_run]))
    baseline, cache = prepare(history_run, None, rpc_runs, CONFIG)
    config = load(CONFIG)
    store = Evidence(cache, rpc_runs)
    for name in ("policy", "pilot_config", "trusted_rpc_config"):
        store.check_ref(baseline[name])
    for run in rpc_runs:
        manifest = load(local(run, "manifest.json"))
        for name in ("policy", "pilot_config", "trusted_rpc_config"):
            if name in manifest:
                store.check_ref(manifest[name])
    history_file = local(history_run, "brain-agent.response.bin")
    history = load(history_file, exact=True)
    candidate, plan_refs = validate_plan(plan_run, config, history_file, store)
    history_refs = {item["path"] for item in baseline["inputs"]
                    if str(item["path"]).startswith(ref(history_run) + "/")}
    for item in baseline["inputs"]:
        store.check_ref(item)
    identity = verify_registration(store, config, history)
    explanations = availability(availability_run, config, store)
    task_details = []
    for task in baseline["tasks"]:
        explanation, details = task_explanation(task, history["history"][task["history_index"]], store, config, identity, history_refs)
        explanations.append(explanation)
        task_details.append(details)
    now = datetime.now(timezone.utc)
    time_values = [when(history["history"][index]["at"]) for index in config["functional_indices"] + config["behavioral_indices"]]
    limits = ["这是一个 Agent 的历史增仓窄范围试点，不能外推为整个 Agent 的能力或资产安全评级。",
              "可用性耗时包含本机既定代理和网络线路；传输故障与限流不归因于 Agent。",
              "历史索引 123 曾用于可行性核实，本报告不将样本描述为随机盲测。"]
    if identity[0] != Verdict.PASS:
        limits.append("注册身份与执行钱包关联未闭合，功能和行为样本均保留为无法判断。")
    if store.issues:
        limits.append(f"保留了 {len(store.issues)} 条早期未成功的 RPC 观测，后续只补采缺项。旧失败不冒充成功；当前结论使用各样本列出的有效原件，仍无法补齐的样本会显示无法判断。")
    references = set(plan_refs) | history_refs | identity[3] | {ref(local(availability_run, "manifest.json")), ref(CONFIG), ref(POLICY)}
    references.update(path for item in explanations for path in item.sample.evidence)
    report = EvaluationReport(candidate_key=candidate.key, name=candidate.name,
        registration_reference=candidate.registration_reference, generated_at=now,
        scope="评价公开运行记录入口的十次真实访问、七条历史增仓结果披露，以及另外七条运行中包装/兑换/增仓的完整三笔操作。",
        scope_exclusions=["最佳区间、收益预测、策略优劣和资金安全", "实时仓位查询与付费规划", "新交易执行、整个日常策略或未抽到的其他功能"],
        evaluation_window=f"历史运行：{display_time(min(time_values))} 至 {display_time(max(time_values))}；"
                          f"记录入口采样：{display_time(explanations[0].observed_at)} 至 {display_time(explanations[9].observed_at)}（均为北京时间）。",
        approach="先按来源和固定规则自动选定方案，再从原始 RPC 请求、回执、固定区块状态与事件独立计算；模型提取的声明不作为事实证明。",
        samples=explanations, source_references=sorted(references), limitations=limits)
    run = RUNTIME / f"evaluation-report-{now:%Y%m%dT%H%M%SZ}-{secrets.token_hex(4)}"
    run.mkdir()
    background = {"registration": {"verdict": identity[0].value, "explanation": identity[1], "facts": identity[2], "evidence": sorted(identity[3])},
        "not_applicable": [{"history_index": index, "task_key": f"{config['history_response_sha256']}:{index}",
            "verdict": "NOT_APPLICABLE", "reason": "公开记录明确无动作，不属于本次已执行增仓范围，不进入七任务评分分母",
            "source_path": f"$.history[{index}]", "at": history["history"][index]["at"]} for index in config["not_applicable_indices"]],
        "task_verifications": task_details, "unusable_rpc_observations": store.issues}
    for path in references:
        actual = (ROOT / path).resolve()
        if actual.is_file() and actual.is_relative_to(RUNTIME):
            store.inputs[path] = digest(actual)
    manifest = {"created_at": now.isoformat(), "policy_version": config["policy_version"], "network_requests": 0,
        "history_source_sha256": config["history_response_sha256"], "plan_run": ref(plan_run),
        "availability_run": ref(availability_run), "context_run": ref(context_run), "rpc_runs": [ref(path) for path in rpc_runs],
        "implementation_note": {"path": ref(IMPLEMENTATION), "sha256": digest(IMPLEMENTATION)},
        "inputs": [{"path": path, "sha256": value} for path, value in sorted(store.inputs.items())],
        "samples": len(explanations), "not_applicable_background_records": len(background["not_applicable"])}
    for name, value in (("manifest.json", manifest), ("background.json", background)):
        with (run / name).open("x", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
    with (run / "report.json").open("x", encoding="utf-8") as stream:
        stream.write(report.model_dump_json(indent=2))
    with (run / "report.html").open("x", encoding="utf-8") as stream:
        stream.write(render_evaluation_report(report))
    print(json.dumps({"evidence_directory": str(run), "registration": identity[0].value,
                      "scores": report.scores.model_dump(mode="json")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
