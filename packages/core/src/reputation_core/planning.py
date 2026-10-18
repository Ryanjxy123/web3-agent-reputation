"""Select frozen evaluation plans from source-backed business descriptors."""

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict

from reputation_core.admission import CandidateRecord, Verdict
from reputation_core.claims import DeclarationAnalysis


class LiquidityHistoryDescriptor(BaseModel):
    """Backend-parsed source locations and claimed identifiers, not verified chain facts."""

    model_config = ConfigDict(extra="forbid")

    candidate_key: str
    claim_ids: list[str]
    chain_id: int | None = None
    protocol: str | None = None
    history_shape: str | None = None
    history_source_file: str | None = None
    history_json_path: str | None = None
    published_execution_wallet: str | None = None
    trusted_manager: str | None = None


class PlanSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_key: str
    status: Literal["SELECTED", "NEEDS_INFO", "UNSUPPORTED"]
    policy_id: Literal["liquidity-history-v1", "prediction-history-v1"] | None
    claim_ids: list[str]
    reasons: list[str]
    pending_evidence: list[str]


def select_plan(
    analysis: DeclarationAnalysis, candidate: CandidateRecord,
    descriptor: LiquidityHistoryDescriptor,
) -> PlanSelection:
    """Select a verifier; the caller must first source-validate the declaration analysis."""
    pending = [f"{check.code.value}: {check.status.value}"
               for check in candidate.checks if check.status != Verdict.PASS]
    pending.append("Selection does not authorize execution or establish publication/sample sufficiency")

    def result(status: str, reasons: list[str]) -> PlanSelection:
        return PlanSelection(
            candidate_key=candidate.key, status=status,
            policy_id="liquidity-history-v1" if status == "SELECTED" else None,
            claim_ids=descriptor.claim_ids if status == "SELECTED" else [],
            reasons=reasons, pending_evidence=pending,
        )

    if descriptor.candidate_key != candidate.key:
        return result("NEEDS_INFO", ["Source descriptor belongs to a different candidate"])
    ids = [claim.claim_id for claim in analysis.claims]
    if len(ids) != len(set(ids)):
        return result("NEEDS_INFO", ["Declaration analysis contains duplicate claim_id values"])
    if not descriptor.claim_ids or len(descriptor.claim_ids) != len(set(descriptor.claim_ids)):
        return result("NEEDS_INFO", ["Source descriptor requires nonempty, unique claim_ids"])
    claims = {claim.claim_id: claim for claim in analysis.claims}
    if any(claim_id not in claims for claim_id in descriptor.claim_ids):
        return result("NEEDS_INFO", ["Referenced claim_id is absent from the source-validated analysis"])
    if any(not claims[claim_id].citations or any(not citation.source_id.strip() or not citation.quote.strip()
           for citation in claims[claim_id].citations) for claim_id in descriptor.claim_ids):
        return result("NEEDS_INFO", ["Each selected claim requires a nonempty source citation"])
    missing = []
    if not candidate.registration_reference.strip():
        missing.append("A public registration reference is required")
    for name in ("chain_id", "protocol", "history_shape", "history_source_file", "history_json_path",
                 "published_execution_wallet", "trusted_manager"):
        value = getattr(descriptor, name)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(f"Missing source descriptor field: {name}")
    for name, supported in (("chain_id", 56), ("protocol", "pancakeswap-v3-npm"),
                            ("history_shape", "run-history-increase-v1")):
        value = getattr(descriptor, name)
        if value is not None and (not isinstance(value, str) or value.strip()) and value != supported:
            return result("UNSUPPORTED", [f"No implemented historical-liquidity plan for {name}={value}"])
    if descriptor.history_source_file and "://" in descriptor.history_source_file:
        missing.append("History source must identify a retained local file, not a remote endpoint")
    if descriptor.history_json_path and not descriptor.history_json_path.startswith("$"):
        missing.append("History source requires an explicit JSONPath location")
    for name in ("published_execution_wallet", "trusted_manager"):
        value = getattr(descriptor, name)
        if value and not re.fullmatch(r"0x[0-9a-fA-F]{40}", value):
            missing.append(f"Invalid address in source descriptor: {name}")
    if missing:
        return result("NEEDS_INFO", missing)
    return result("SELECTED", [
        "Source-backed historical increase records match the implemented BSC PancakeSwap V3 NPM plan",
        "Only public history reads and existing-transaction verification are selected; no new asset operations",
    ])


class PredictionToolDescriptor(BaseModel):
    """Concrete tool declarations parsed from the retained provider metadata."""

    model_config = ConfigDict(extra="forbid")

    operation: str
    description: str
    input_type: str | None = None
    output_type: str | None = None
    result_type: str | None = None
    required_output_fields: list[str]
    probability_fields: list[str]


class PredictionHistoryDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_key: str
    claim_ids: list[str]
    tools: list[PredictionToolDescriptor]
    chain_id: int | None = None
    protocol: str | None = None
    metadata_source_id: str | None = None
    metadata_source_file: str | None = None
    input_format: str | None = None
    output_format: str | None = None
    published_mech: str | None = None
    service_id: str | None = None
    history_shape: str | None = None
    history_source_file: str | None = None
    history_tool: str | None = None
    history_context_type: str | None = None
    history_market: str | None = None
    history_prompt: str | None = None


def _prediction_meaning(tool: PredictionToolDescriptor) -> bool:
    text = tool.description.casefold()
    return bool(re.search(r"\b(?:predict(?:ion|ions)?|forecast(?:ing|s)?)\b", text)
                and re.search(r"\b(?:binary|markets?|omen)\b", text))


def prediction_tool_supported(tool: PredictionToolDescriptor) -> bool:
    """Require prediction meaning and its concrete I/O shape, never tool names."""
    return (_prediction_meaning(tool) and tool.input_type == "text" and tool.output_type == "object"
            and tool.result_type == "string"
            and {"requestId", "prompt", "result"}.issubset(tool.required_output_fields)
            and {"p_yes", "p_no"}.issubset(tool.probability_fields))


def select_prediction_plan(
    analysis: DeclarationAnalysis, candidate: CandidateRecord, descriptor: PredictionHistoryDescriptor,
) -> PlanSelection:
    """Match cited tools and actual Omen request structure; sources are validated by the caller."""
    pending = [f"{check.code.value}: {check.status.value}"
               for check in candidate.checks if check.status != Verdict.PASS]
    pending.extend(["方案选择不代替历史归属、结算、CID或样本充分性的独立核验。",
                    "仅选择公开历史读取；不授权新预测、签名、付款或资产操作。"])

    def result(status: str, reasons: list[str]) -> PlanSelection:
        return PlanSelection(candidate_key=candidate.key, status=status,
            policy_id="prediction-history-v1" if status == "SELECTED" else None,
            claim_ids=descriptor.claim_ids if status == "SELECTED" else [],
            reasons=reasons, pending_evidence=pending)

    if descriptor.candidate_key != candidate.key:
        return result("NEEDS_INFO", ["来源描述符不属于当前候选。"])
    for field, supported in (("chain_id", 100), ("protocol", "olas-mech-marketplace"),
                             ("input_format", "ipfs-v0.1"), ("output_format", "ipfs-v0.1"),
                             ("history_shape", "omen-binary-request-v1")):
        value = getattr(descriptor, field)
        if value is not None and value != supported:
            return result("UNSUPPORTED", [f"当前预测历史方案不支持 {field}={value}。"])
    if descriptor.tools and all(tool.description.strip() for tool in descriptor.tools) and not any(
            _prediction_meaning(tool) for tool in descriptor.tools):
        return result("UNSUPPORTED", ["实际工具描述没有二元预测或预测市场含义；概率输出示例不能代替业务声明。"])
    missing = []
    for field in ("chain_id", "protocol", "metadata_source_id", "metadata_source_file", "input_format",
                  "output_format", "published_mech", "service_id", "history_shape", "history_source_file",
                  "history_tool", "history_context_type", "history_market", "history_prompt"):
        value = getattr(descriptor, field)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(f"缺少来源字段：{field}。")
    if not re.fullmatch(r"eip155:100:0x[0-9a-fA-F]{40}:[0-9]+", candidate.registration_reference):
        missing.append("需要完整的Gnosis公共注册标识。")
    for field in ("metadata_source_file", "history_source_file"):
        value = getattr(descriptor, field)
        if value and (not value.startswith("runtime/") or "://" in value or ".." in value.split("/")):
            missing.append(f"{field}必须定位保留的本地公开原件。")
    for field in ("published_mech", "history_market"):
        value = getattr(descriptor, field)
        if value and (not re.fullmatch(r"0x[0-9a-fA-F]{40}", value) or int(value[2:], 16) == 0):
            missing.append(f"{field}不是有效的非零合约地址。")
    if descriptor.service_id and not re.fullmatch(r"[1-9][0-9]*", descriptor.service_id):
        missing.append("service_id需要明确的正整数十进制标识。")
    if descriptor.history_context_type not in (None, "omen"):
        return result("UNSUPPORTED", ["实际历史请求不属于当前支持的Omen市场上下文。"])
    if descriptor.history_prompt and not all(token in descriptor.history_prompt for token in ("p_yes", "p_no")):
        missing.append("历史原始输入尚未明确Yes/No概率问题。")
    operations = [tool.operation for tool in descriptor.tools]
    if not operations or len(set(operations)) != len(operations) or any(not name.strip() for name in operations):
        missing.append("需要真实metadata中非空且唯一的工具catalog。")
    claims = {claim.claim_id: claim for claim in analysis.claims}
    if len(claims) != len(analysis.claims):
        missing.append("声明分析含重复claim_id。")
    if not descriptor.claim_ids or len(set(descriptor.claim_ids)) != len(descriptor.claim_ids):
        missing.append("需要非空且唯一的来源声明引用。")
    if any(claim_id not in claims for claim_id in descriptor.claim_ids):
        missing.append("指定声明不在已经验证来源的分析中。")
    supported_tools = {tool.operation: tool for tool in descriptor.tools if prediction_tool_supported(tool)}
    if not supported_tools:
        missing.append("缺少同时符合预测语义、文本输入和概率JSON输出的工具声明。")
    if missing:
        return result("NEEDS_INFO", missing)
    selected_operations = set()
    for claim_id in descriptor.claim_ids:
        claim = claims[claim_id]
        if claim.operation not in operations:
            return result("NEEDS_INFO", ["模型operation不是来源tool catalog中的实际条目。"])
        if claim.operation not in supported_tools:
            return result("UNSUPPORTED", ["被引用工具的实际含义或输入输出结构不属于当前二元预测方案。"])
        tool = supported_tools[claim.operation]
        citations = [citation for citation in claim.citations
                     if citation.source_id == descriptor.metadata_source_id and citation.quote.strip()]
        business_quotes = [citation.quote if citation.quote in tool.description else tool.description
                           for citation in citations if citation.quote in tool.description or tool.description in citation.quote]
        if not any(_prediction_meaning(tool.model_copy(update={'description': quote})) for quote in business_quotes):
            return result("NEEDS_INFO", ["每项被选声明必须引用对应工具的实际业务描述，不能只引用概率示例。"])
        selected_operations.add(claim.operation)
    if descriptor.history_tool not in selected_operations:
        return result("NEEDS_INFO", ["已定位历史请求的tool尚无对应的来源预测声明。"])
    return result("SELECTED", ["有来源的预测工具声明、输入输出结构和实际Omen历史请求匹配已冻结方案。",
                                "不按候选名称、注册号或准入布尔值选方案；当前缺项继续独立保留。"])
