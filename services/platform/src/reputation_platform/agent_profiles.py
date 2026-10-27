"""Business descriptions from authenticated report inputs, not measurement scope."""

import hashlib
import json
from pathlib import Path

from reputation_core.application import AgentProfile, normalize_reference


def profile_from_report(root: Path, row: dict) -> AgentProfile:
    report = row["validated_json"]
    policy = report["scores"]["policy_version"]
    canonical = normalize_reference(row.get("registration_reference", ""))
    chain = int(canonical.split(":")[1]) if canonical else None
    sources = report.get("source_references", [])
    if policy in ("prediction-history-v1", "prediction-history-v2"):
        return AgentProfile(
            business_summary="接收预测问题，提供概率与研究结果；通过Gnosis链上的Mech市场接单并交付结果，供交易Agent决策使用。",
            ecosystem="Olas · Mech", role="research-delivery", registration_chain_id=chain or 100,
            execution_chain_ids=[100], capabilities=["预测研究", "链上接单与结果交付"], execution_accounts=[],
            evidence_status="verified", sources=sources[:2],
            boundary="已核验的是研究交付；这份报告不证明该对象替用户买入或管理资产。",
        )

    directory = (root / row["source_directory"]).resolve()
    if not directory.is_relative_to(root / "runtime"):
        raise ValueError("Profile source is outside retained runtime")
    raw_manifest = (directory / "manifest.json").read_bytes()
    if hashlib.sha256(raw_manifest).hexdigest() != row["manifest_sha256"]:
        raise ValueError("Profile source manifest changed")
    inputs = json.loads(raw_manifest)["inputs"]

    def source_json(reference: dict):
        path = (root / reference["path"]).resolve()
        if not (path.is_relative_to(root / "runtime") or path.is_relative_to(root / "configs")):
            raise ValueError("Invalid profile source")
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != reference["sha256"]:
            raise ValueError("Profile source changed")
        return json.loads(raw)

    if policy in ("evm-swap-builder-v1", "evm-swap-builder-v2"):
        origins = [item for item in inputs if Path(item["path"]).name == "swap-report-origin.json"]
        if len(origins) != 1:
            raise ValueError("No unique authenticated swap report origin")
        origin = source_json(origins[0])
        campaigns = [item for item in inputs if item["path"] == origin["campaign"]]
        if len(campaigns) != 1:
            raise ValueError("No unique authenticated swap campaign profile")
        campaign = source_json(campaigns[0])
        return AgentProfile(
            business_summary="根据指定代币、金额和滑点生成Base链兑换报价与待签名方案；经用户授权后，由用户钱包执行，平台核验实际成交、资产到账与授权余额。",
            ecosystem="Uniswap V3 · x402", role="asset-execution", registration_chain_id=chain,
            execution_chain_ids=[campaign["execution_chain_id"]], capabilities=["ERC20兑换报价", "精确授权与兑换方案"],
            execution_accounts=[campaign["buyer"]], evidence_status="verified", sources=[campaigns[0]["path"]],
            boundary="方案由服务生成、用户钱包签名执行。入口归属依据官方卡声明；本轮未取得IPFS注册正文及owner签名认证。",
        )

    if policy == "liquidity-history-v1":
        pilots = [item for item in inputs if item["path"].startswith("configs/pilots/")]
        config = next((value for value in map(source_json, pilots) if value.get("policy_version") == policy), None)
        if config is None:
            raise ValueError("No authenticated execution profile configuration")
        return AgentProfile(
            business_summary="在BNB Chain管理PancakeSwap V3流动性仓位，包装BNB、兑换缺少的一侧资产，再向指定NFT仓位增加流动性。",
            ecosystem="Brain · PancakeSwap", role="asset-execution", registration_chain_id=config["chain_id"],
            execution_chain_ids=[config["chain_id"]], capabilities=["原生币包装", "代币兑换", "V3仓位增仓"],
            execution_accounts=[config["execution_wallet"]], evidence_status="verified",
            sources=[item["path"] for item in pilots] + [config["history_source_url"]],
            boundary="已有真实历史执行证据；不以收益、策略优劣或当前资产安全作结论。",
        )

    proofs = [item for item in inputs if Path(item["path"]).name == "registration-proof.json"]
    proof = source_json(proofs[0]) if len(proofs) == 1 else {}
    document = (proof.get("document") or {}).get("payload") or {}
    description = document.get("description")
    capabilities = report.get("capabilities", [])
    checkers = {item.get('checker_id') for item in capabilities}
    position_query = 'query.pancakeswap-v3-position' in checkers
    transfer_query = 'query.erc20-transfer-record' in checkers
    checked_query = position_query or transfer_query
    operations = list(dict.fromkeys(item["operation"] for item in capabilities
                                    if item.get("operation") and item["operation"] != "未提供可识别操作"))
    if position_query:
        summary = "提供链上事实查询；本次已核验PancakeSwap V3 NFT仓位资料，返回资产对、费率和价格区间等字段，供用户或其它Agent决策。"
    elif transfer_query:
        summary = '查询ERC20交易记录，并从真实交易回执独立核对代币、转入地址与到账数量。'
    else:
        summary = description.strip()[:500] if isinstance(description, str) and description.strip() else "已登记公开服务，具体业务功能仍需补齐有来源的说明。"
    intent_refs = [item for item in inputs if Path(item['path']).name in
                   ('position-fulfillment-intent.json', 'position-checker-intent.json', 'query-checker-intent.json')]
    business_chains = sorted({value['chain'] for value in map(source_json, intent_refs)
                              if type(value.get('chain')) is int})
    return AgentProfile(
        business_summary=summary, ecosystem="公开注册服务", role="chain-query" if checked_query else "unverified",
        registration_chain_id=chain, execution_chain_ids=business_chains,
        capabilities=operations[:8], execution_accounts=[],
        evidence_status="verified" if checked_query else "declared" if description else "unverified",
        sources=[item["path"] for item in proofs],
        boundary="查询响应或目录声明不等于资产执行授权；本对象的交易执行账户尚未核实。",
    )
