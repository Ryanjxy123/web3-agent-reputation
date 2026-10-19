"""Aggregate retained HTTP evidence into a new, append-only admission report."""

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import secrets
import sys

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = (ROOT / "runtime").resolve()
sys.path[:0] = [str(ROOT / "packages/core/src"), str(ROOT / "services/platform/src")]

from pydantic import ValidationError
from reputation_core import (
    AdmissionCheck, AdmissionReport, CandidateRecord, CheckCode,
    ProbeObservation, Verdict, assess_candidate,
)
from reputation_platform.admission_report import render_admission_report


@dataclass
class Evidence:
    observation: ProbeObservation
    references: list[str]
    payload: object = None
    text: str = ""
    problem: str | None = None

    @property
    def usable(self) -> bool:
        return (
            self.problem is None and self.observation.body_complete
            and self.observation.http_status is not None
            and 200 <= self.observation.http_status < 300
            and self.observation.error_kind is None
        )


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def load_runs(directories: list[Path]) -> tuple[list[ProbeObservation], dict[str, Evidence], dict]:
    observations, records = [], {}
    manifest = {"input_runs": [relative(path) for path in directories], "inputs": [], "issues": []}
    for directory in directories:
        for path in sorted(directory.glob("*.observation.json")):
            source = relative(path)
            try:
                raw = path.read_bytes()
                observation = ProbeObservation.model_validate_json(raw)
            except (OSError, ValueError, ValidationError) as exc:
                manifest["issues"].append({"source": source, "problem": f"观测文件无法解析：{type(exc).__name__}"})
                continue
            item = {"observation_file": source, "observation_sha256": hashlib.sha256(raw).hexdigest()}
            record = Evidence(observation=observation, references=[source])
            if observation.response_file:
                response_path = (directory / observation.response_file).resolve()
                if not response_path.is_relative_to(directory):
                    record.problem = "响应文件指向原证据目录之外，未读取。"
                    observation = observation.model_copy(update={"response_file": None})
                else:
                    response_reference = relative(response_path)
                    record.references.append(response_reference)
                    observation = observation.model_copy(update={"response_file": response_reference})
                    try:
                        body = response_path.read_bytes()
                        actual_hash = hashlib.sha256(body).hexdigest()
                        item.update(response_file=response_reference, response_sha256=actual_hash)
                        if actual_hash != observation.response_sha256:
                            record.problem = "响应文件与采集时的摘要不一致，暂不能作为通过依据。"
                        record.text = body.decode("utf-8")
                        if observation.request_key not in ("brain-docs", "brain-defi"):
                            record.payload = json.loads(record.text)
                    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                        record.problem = f"响应资料未能解析：{type(exc).__name__}，对应检查保留为待核实。"
            else:
                record.problem = "没有保留响应文件，暂不能核实业务内容。"
            record.observation = observation
            if record.problem:
                manifest["issues"].append({"source": source, "problem": record.problem})
            manifest["inputs"].append(item)
            observations.append(observation)
            previous = records.get(observation.request_key)
            if previous is None or observation.observed_at.isoformat() >= previous.observation.observed_at.isoformat():
                records[observation.request_key] = record
    return observations, records, manifest


def build_candidates(records: dict[str, Evidence]) -> list:
    def data(key: str) -> dict:
        record = records.get(key)
        return record.payload if record and record.usable and isinstance(record.payload, dict) else {}

    def refs(*keys: str) -> list[str]:
        return [reference for key in keys if key in records for reference in records[key].references]

    def problem(key: str) -> str:
        record = records.get(key)
        if record is None:
            return "本轮没有保留该接口的实际响应。"
        return record.problem or f"HTTP 状态为 {record.observation.http_status}；响应内容尚不足以确认业务接口通过。"

    def request_params(key: str) -> list:
        try:
            request = json.loads(records[key].observation.request_json or "null")
            return request.get("params", []) if isinstance(request, dict) else []
        except (KeyError, json.JSONDecodeError):
            return []

    def chain_result(key: str, method: str) -> object:
        record = records.get(key)
        if not record or not record.usable or record.observation.url != "https://bsc-dataseed.bnbchain.org":
            return None
        try:
            request = json.loads(record.observation.request_json or "null")
            response = data(key)
            if (isinstance(request, dict) and request.get("method") == method
                    and response.get("jsonrpc") == "2.0" and response.get("id") == request.get("id")
                    and "error" not in response):
                return response.get("result")
        except json.JSONDecodeError:
            pass
        return None

    def number(value: object) -> int:
        try:
            return int(str(value), 16)
        except (ValueError, TypeError):
            return -1

    registry = "0x8004a169fb4a3325136eb29fa0ceb6d2e539a432"
    defi_wallet = "0xbfaa69233741924ed5b9d5daa9b4bf7b84567f0a"
    brain_owner = "0x15ba17075ef5e0736292b030e3715d9100fe3d38"
    manager = "0x46a15b0b27311cedf172ab29e4f4766fbe7f4364"
    head = chain_result("head", "eth_blockNumber")
    snapshot = chain_result("snapshot-block", "eth_getBlockByNumber")
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    snapshot_tag = snapshot.get("number")
    snapshot_ok = (
        chain_result("chain-id", "eth_chainId") == "0x38"
        and request_params("snapshot-block") == [snapshot_tag, False]
        and 0 < number(snapshot_tag) <= number(head)
        and isinstance(snapshot.get("hash"), str) and len(snapshot["hash"]) == 66
    )

    def registered(key: str, token_id: int, expected_owner: str) -> bool:
        params = request_params(key)
        return bool(
            snapshot_ok and len(params) == 2 and isinstance(params[0], dict)
            and params[0].get("to", "").lower() == registry and params[1] == snapshot_tag
            and params[0].get("data", "").lower() == "0x6352211e" + f"{token_id:064x}"
            and chain_result(key, "eth_call") == "0x" + expected_owner[2:].rjust(64, "0")
        )

    defi_registered = registered("owner-defi", 363709, defi_wallet)
    brain_registered = registered("owner-brain", 49467, brain_owner)
    transaction = chain_result("increase-transaction", "eth_getTransactionByHash")
    receipt = chain_result("increase-receipt", "eth_getTransactionReceipt")
    transaction = transaction if isinstance(transaction, dict) else {}
    receipt = receipt if isinstance(receipt, dict) else {}
    transaction_hash = transaction.get("hash")
    transaction_params = request_params("increase-transaction")
    receipt_params = request_params("increase-receipt")
    encoded_call = str(transaction.get("input", ""))
    event_topic = "0x3067048beee31b25b2f1681f88dac838c8bba36af25bfb2b7cf7473a5847e35f"
    matching_event = next((event for event in receipt.get("logs", []) if isinstance(event, dict)
        and event.get("address", "").lower() == manager
        and event.get("topics") == [event_topic, "0x" + f"{7637521:064x}"]
        and event.get("transactionHash") == transaction_hash
        and event.get("blockHash") == transaction.get("blockHash")
        and event.get("blockNumber") == transaction.get("blockNumber")
        and event.get("removed") is False), None)
    profile = data("brain-agent")
    history = profile.get("history", [])
    matching_step = None
    if isinstance(history, list):
        for entry in history:
            if not isinstance(entry, dict) or not isinstance(entry.get("steps"), dict):
                continue
            step = entry["steps"].get("increase")
            if (isinstance(step, dict) and entry.get("dry") is False and entry.get("acted") is True
                    and entry.get("ok") is True and str(entry.get("wallet", "")).lower() == defi_wallet
                    and str(step.get("position")) == "7637521" and step.get("acted") is True
                    and any(isinstance(tx, dict) and tx.get("hash") == transaction_hash for tx in step.get("txs", []))):
                matching_step = entry
                break
    history_time_ok = False
    if matching_step and matching_event:
        try:
            recorded_at = datetime.fromisoformat(str(matching_step["at"]).replace("Z", "+00:00"))
            delay = recorded_at.timestamp() - number(matching_event.get("blockTimestamp"))
            history_time_ok = abs(delay) <= 300
        except (KeyError, ValueError, TypeError):
            pass
    history_step_ok = bool(
        defi_registered and matching_step and matching_event and history_time_ok and transaction_hash
        and transaction_params == [transaction_hash] and receipt_params == [transaction_hash]
        and number(transaction.get("chainId")) == 56
        and transaction.get("from", "").lower() == receipt.get("from", "").lower() == defi_wallet
        and transaction.get("to", "").lower() == receipt.get("to", "").lower() == manager
        and encoded_call[:10] == "0x219f5d17" and number(encoded_call[10:74]) == 7637521
        and receipt.get("status") == "0x1" and receipt.get("transactionHash") == transaction_hash
        and transaction.get("blockHash") == receipt.get("blockHash")
        and transaction.get("blockNumber") == receipt.get("blockNumber")
        and 0 <= number(snapshot_tag) - number(transaction.get("blockNumber"))
    )
    last = profile.get("last", {})
    look = data("brain-look-position")
    deposit = chain_result("defi-transaction", "eth_getTransactionByHash")
    deposit = deposit if isinstance(deposit, dict) else {}
    binding_ok = bool(defi_registered and isinstance(last, dict)
        and str(last.get("wallet", "")).lower() == str(look.get("owner", "")).lower() == defi_wallet
        and transaction.get("from", "").lower() == deposit.get("from", "").lower() == defi_wallet)

    definitions = (
        ("degenai", "DegenAI", "Ethereum / 23121", "https://degenai.dev/erc8004", "catalog-degen"),
        ("agent-arena", "Agent Arena", "Base / 18500", "https://agentarena.site/", "catalog-arena"),
        ("synthesis", "DARKSOL（Synthesis 关联身份）", "Base / 31929", "https://github.com/darks0l/synthesis-agent", "catalog-synthesis"),
        ("brain", "Brain On BNB", "BNB Chain / 49467", "https://brainonbnb.com/services", "catalog-brain"),
        ("brain-defi", "Brain on BNB — DeFi Agent", "BNB Chain / 363709", "https://brainonbnb.com/defi", "catalog-defi"),
    )
    candidates = []
    for key, name, registration, source, catalog_key in definitions:
        checks = {
            CheckCode.REGISTRATION: (Verdict.UNKNOWN, "已有公开目录的身份线索，尚未直接核对链上登记，暂不能确认。", refs(catalog_key)),
            CheckCode.FUNCTIONAL_DECLARATION: (Verdict.UNKNOWN, "本轮资料中尚未确认可定位的具体功能声明。", refs(catalog_key)),
            CheckCode.SERVICE_INTERFACE: (Verdict.UNKNOWN, "尚未取得足以确认可调用业务接口的响应。", []),
            CheckCode.INDEPENDENT_ORACLE: (Verdict.UNKNOWN, "尚未把同一输入的业务结果与独立事实比对；HTTP 成功不等于结果正确。", []),
            CheckCode.EXECUTION_BINDING: (Verdict.UNKNOWN, "尚未独立核实注册身份、实际执行者和业务合约的关联；收款地址不能直接代替执行者。", refs(catalog_key)),
            CheckCode.EXECUTION_HISTORY: (Verdict.UNKNOWN, "尚未独立核验可归属于该 Agent 的任务与交易历史。", []),
        }

        def set_check(code: CheckCode, status: Verdict, explanation: str, *keys: str) -> None:
            checks[code] = (status, explanation, refs(*keys))

        catalog = data(catalog_key)
        if key in ("brain", "brain-defi") and (brain_registered if key == "brain" else defi_registered):
            owner_key = "owner-brain" if key == "brain" else "owner-defi"
            owner = brain_owner if key == "brain" else defi_wallet
            set_check(CheckCode.REGISTRATION, Verdict.PASS, f"已直接核对链上登记，确认这个身份在 BNB Chain 上存在。核对基于固定区块 {number(snapshot_tag)}；登记持有人为 {owner}。身份存在不等于业务表现已评分。", "chain-id", "snapshot-block", owner_key)
        if isinstance(catalog.get("description"), str) and catalog["description"].strip():
            set_check(CheckCode.FUNCTIONAL_DECLARATION, Verdict.PASS, "已保留注册目录中的具体业务声明；这只证明承诺存在，不代表功能已经兑现。", catalog_key)

        if key == "degenai":
            discovery, assets, jobs = data("degen-discovery"), data("degen-assets"), data("degen-jobs")
            if isinstance(discovery.get("capabilities"), list) and discovery["capabilities"]:
                set_check(CheckCode.FUNCTIONAL_DECLARATION, Verdict.PASS, "能力发现资料列出业务操作、输入和价格，可据此安排窄范围评价。", "degen-discovery")
            assets_data = assets.get("data")
            if assets.get("success") is True and isinstance(assets_data, dict) and isinstance(assets_data.get("assets"), list) and assets_data["assets"]:
                set_check(CheckCode.SERVICE_INTERFACE, Verdict.PASS, f"真实调用资产查询，业务响应声明成功，返回 {len(assets_data['assets'])} 条资产资料。这里只确认接口能返回业务数据，未核验资产字段正确性，也未覆盖交易执行。", "degen-assets")
            else:
                set_check(CheckCode.SERVICE_INTERFACE, Verdict.UNKNOWN, problem("degen-assets"), "degen-assets")
            if jobs.get("contractDeployed") is False and all(not jobs.get(field) for field in ("providerAddress", "contractAddress", "evaluatorAddress")):
                set_check(CheckCode.EXECUTION_HISTORY, Verdict.UNKNOWN, "这条任务线尚未部署，暂时无法取得对应执行历史。具体依据：ERC-8183 发现资料标记 contractDeployed=false，执行者、任务合约和核验者地址均为空。", "degen-jobs")
            next_actions = ["用 HyperLiquid 官方资料逐项对照资产查询，记录查询参数、采集时间和缓存口径。", "寻找其他能够明确归属于该 Agent 的公开执行记录；这条任务线尚未部署。", "直接核对 Ethereum 上 #23121 的身份登记。"]
        elif key == "agent-arena":
            arena = data("arena-query")
            if arena and arena.get("name") is None and arena.get("description") is None and arena.get("services") == []:
                set_check(CheckCode.SERVICE_INTERFACE, Verdict.UNKNOWN, "真实查询返回 HTTP 200，但名称、描述为空且服务列表为空；保留目录另有名称和接口。存在资料差异，尚未独立核对链上注册文件，不能直接判为 Agent 业务失败。", "arena-query", catalog_key)
            else:
                set_check(CheckCode.SERVICE_INTERFACE, Verdict.UNKNOWN, problem("arena-query"), "arena-query")
            next_actions = ["固定同一注册标识，读取链上 agentURI 与对应文件，查清查询结果和目录之间的资料差异。", "确认免费注册资料查询的字段承诺和更新时间，再决定哪些字段可独立检验。", "寻找 Arena 自身业务执行记录，不把被查询 Agent 的交易算给 Arena。"]
        elif key == "synthesis":
            set_check(CheckCode.SERVICE_INTERFACE, Verdict.UNKNOWN, "作者项目记录的是 localhost 仪表盘；目录现名 DARKSOL，并提供公共 API 线索。免费调用、授权和链上证明条件尚未核实；同一 #31929 不另算对象。", catalog_key)
            next_actions = ["核实当前 DARKSOL 官方 API 文档与支付条件；随机数 demo 返回 2xx 不代表提供真实链上执行证明。", "核对作者 README 的注册交易、执行钱包和当前目录身份，保留名称变化的出处。", "取得有明确任务语义的历史交易后，通过可信 Base RPC 核验，暂不调用付费业务。"]
        elif key == "brain":
            docs = records.get("brain-docs")
            if docs and docs.usable and docs.text.strip():
                set_check(CheckCode.FUNCTIONAL_DECLARATION, Verdict.PASS, "已保留官方服务说明，可定位业务承诺；服务说明页可读不等于具体业务已经通过。", "brain-docs", catalog_key)
            burns = records.get("brain-burns")
            if burns and burns.usable and isinstance(burns.payload, list):
                set_check(CheckCode.EXECUTION_HISTORY, Verdict.UNKNOWN, f"已保留项目公开的 {len(burns.payload)} 条回购/销毁日志，但尚未核实交易回执、事件与该身份的关联；日志声明不能代替链上事实。", "brain-burns")
            burn = chain_result("burn-transaction", "eth_getTransactionByHash")
            if (isinstance(burn, dict) and brain_registered
                    and burn.get("from", "").lower() != brain_owner
                    and burn.get("to", "").lower() != "0x245c386dcfed896f5c346107596141e5edcbffff"):
                set_check(CheckCode.EXECUTION_HISTORY, Verdict.UNKNOWN, "抽查的历史销毁交易使用了不同执行地址和代币合约，目前不能归属于这个身份；需要迁移或地址绑定资料，不据此扣分。具体依据：历史执行者为 " + str(burn.get("from")) + "，目标为 " + str(burn.get("to")) + "；与当前登记持有人、当前项目代币不同。", "brain-burns", "burn-transaction", "burn-receipt", "owner-brain", catalog_key)
            next_actions = ["补充 #49467 与历史销毁执行地址、旧代币之间的迁移或绑定资料。", "分清主 Agent 与 DeFi 子 Agent 的任务归属，不能把同一项目的所有交易归给任意身份。", "选择一种免费业务取得实际结果并独立核验，不以服务说明页代替业务样本。"]
        else:
            look, profile = data("brain-look-position"), data("brain-agent")
            if look.get("service") == "lp_position_look" and str(look.get("position")) == "7637521" and str(look.get("owner", "")).lower() == "0xbfaa69233741924ed5b9d5daa9b4bf7b84567f0a":
                set_check(CheckCode.SERVICE_INTERFACE, Verdict.PASS, "真实免费查询返回 lp_position_look、仓位 #7637521 和执行钱包 0xbFAA…7F0A。这里只确认服务能返回对应业务数据；仓位、费用和区间等正确性仍待独立核验。", "brain-look-position")
            else:
                set_check(CheckCode.SERVICE_INTERFACE, Verdict.UNKNOWN, problem("brain-look-position"), "brain-look-position")
            history = profile.get("history")
            if isinstance(history, list):
                set_check(CheckCode.EXECUTION_HISTORY, Verdict.UNKNOWN, f"公开运行资料包含 {len(history)} 条历史记录，涵盖执行、等待和失败等状态；尚未独立核验链上回执与任务关联，不能把记录数当成功交易数。", "brain-agent")
            set_check(CheckCode.EXECUTION_BINDING, Verdict.UNKNOWN, "目录声明 #363709 由 Brain #49467 运营，并指向同一项目的执行钱包；尚未完成链上身份与实际任务的独立关联核验。这两个候选不代表两个独立提供方。", catalog_key, "brain-agent", "brain-look-position")
            if binding_ok:
                set_check(CheckCode.EXECUTION_BINDING, Verdict.PASS, "链上登记持有人、公开运行记录、仓位查询和两笔历史交易的执行地址一致，已形成执行身份关联。地址为 " + defi_wallet + "。与 Brain #49467 属于同一提供方，不能当作两个独立提供方。", "owner-defi", "brain-agent", "brain-look-position", "defi-transaction", "increase-transaction")
            if history_step_ok:
                set_check(CheckCode.EXECUTION_HISTORY, Verdict.PASS, "已独立核验一条历史增仓步骤：执行者、仓位、目标合约、成功状态和对应事件一致。这证明存在可归属的历史步骤，尚未形成整体交易可靠性评分；早先核对的包装 BNB 交易只是准备步骤，不能代表整次任务完成。技术定位：交易 " + str(transaction_hash) + "，仓位 #7637521，区块 " + str(number(transaction.get("blockNumber"))) + "；增仓调用及其事件均由仓位管理合约对应。", "brain-agent", "owner-defi", "increase-transaction", "increase-receipt", "defi-transaction", "defi-receipt", "snapshot-block")
                checks[CheckCode.EXECUTION_HISTORY][2].append("https://developer.pancakeswap.finance/contracts/v3/addresses")
            set_check(CheckCode.INDEPENDENT_ORACLE, Verdict.UNKNOWN, "本轮尚未完成同一份链上状态的对照，因此暂不能判断查询结果是否正确。已采集实时查询只记录测量时间，未记录固定区块；需要先对齐评价所依据的状态，再独立核对，不能直接用另一个时刻的数据判定它对错。", "brain-look-position", "snapshot-block")
            next_actions = ["预先固定历史抽样规则，保存原始任务、执行步骤和链上结果之间的对应关系。", "为仓位查询建立固定区块的独立核验；若服务不支持对齐，动态结果继续显示待核实。", "按固定标准扩大真实历史步骤样本，区分准备、完成、未执行和失败；一条增仓成功不等于完整声誉评分。"]
        candidates.append(assess_candidate(CandidateRecord(
            key=key, name=name, registration_reference=registration, source_urls=[source],
            checks=[AdmissionCheck(code=code, status=status, explanation=message, evidence=evidence)
                    for code, (status, message, evidence) in checks.items()],
            next_actions=next_actions,
        )))
    return candidates


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs", type=Path, nargs="+")
    args = parser.parse_args()
    directories = list(dict.fromkeys(path.resolve() for path in args.runs))
    for directory in directories:
        if not directory.is_relative_to(RUNTIME) or not directory.is_dir():
            parser.error("Each run must be an existing directory inside this project's runtime")
    observations, records, manifest = load_runs(directories)
    now = datetime.now(timezone.utc)
    report = AdmissionReport(assessed_at=now, candidates=build_candidates(records))
    output = RUNTIME / f"admission-report-{now:%Y%m%dT%H%M%SZ}-{secrets.token_hex(4)}"
    output.mkdir()
    manifest.update(schema_version="admission-input-manifest-v1", generated_at=now.isoformat(),
                    observation_count=len(observations), network_requests_performed=0)
    documents = {
        "admission-report.json": report.model_dump_json(indent=2),
        "observations.json": json.dumps([item.model_dump(mode="json") for item in observations], ensure_ascii=False, indent=2),
        "manifest.json": json.dumps(manifest, ensure_ascii=False, indent=2),
        "admission-report.html": render_admission_report(report, observations),
    }
    for filename, content in documents.items():
        with (output / filename).open("x", encoding="utf-8") as stream:
            stream.write(content)
    print(f"candidate_count={len(report.candidates)} ready_for_full_score={sum(candidate.ready_for_full_score for candidate in report.candidates)} retained_observations={len(observations)} input_issues={len(manifest['issues'])}")
    print(f"report={output / 'admission-report.html'}")


if __name__ == "__main__":
    main()
