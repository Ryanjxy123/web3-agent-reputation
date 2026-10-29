"""Business descriptions from authenticated report inputs, not measurement scope."""

import hashlib
import json
from pathlib import Path

from reputation_core.application import AgentProfile, normalize_reference
from reputation_core.scoring import SHARED_POLICY_VERSIONS, MULTICAP_POLICY_VERSION, POINT_POLICY_VERSION


def profile_from_report(root: Path, row: dict) -> AgentProfile:
    report = row["validated_json"]
    policy = report["scores"]["policy_version"]
    canonical = normalize_reference(row.get("registration_reference", ""))
    chain = int(canonical.split(":")[1]) if canonical and canonical.startswith('eip155:') else None
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

    cow_origins = [item for item in inputs if Path(item['path']).name == 'cow-swap-report-origin.json']
    if cow_origins:
        if len(cow_origins) != 1:
            raise ValueError('No unique authenticated CoW swap origin')
        origin = source_json(cow_origins[0])
        if origin.get('schema_version') != 'cow-swap-report-origin-v1' or origin.get('adapter') != 'retained-cow-swap-campaign-v1':
            raise ValueError('Unsupported CoW profile origin')
        configs = [item for item in inputs if item['path'] == origin['source']]
        if len(configs) != 1:
            raise ValueError('No authenticated CoW swap source')
        source = source_json(configs[0])
        plans = [item for item in inputs if item['path'] == source['campaign_plan']]
        proofs = [item for item in inputs if item['path'] == source['registration_proof']]
        if len(plans) != 1 or len(proofs) != 1:
            raise ValueError('No authenticated CoW campaign or identity profile')
        plan = source_json(plans[0])
        source_json(proofs[0])
        if not canonical or source['registration_reference'] != canonical or plan['registration_reference'] != canonical:
            raise ValueError('CoW profile identity differs from the report')
        from reputation_platform.public_service_identity import verify_service_identity
        identity = verify_service_identity(root, root / source['registration_proof'], canonical)
        identity_boundary = ('ERC8004链注册已核。' if identity['chain_registration_verified'] else
                             '官方公共服务目录已核；ERC8004链注册仍为UNKNOWN。')
        declared = [group['title'] for group in plan['capability']['declaration_groups']]
        return AgentProfile(
            business_summary=('根据资产、金额和滑点生成CoW兑换报价与待签名订单，并检查订单参数。'
                              '买方签名后由solver撮合并在链上结算；本次核验链ID '
                              + str(plan['chain_id']) + ' 上的冻结ERC20订单任务。'),
            ecosystem='CoW Protocol · ERC20订单', role='asset-execution',
            registration_chain_id=identity['registration_chain_id'], execution_chain_ids=[plan['chain_id']],
            capabilities=declared, execution_accounts=[plan['owner']], evidence_status='verified',
            sources=[source['registration_proof'], source['campaign_plan']],
            boundary=identity_boundary + '登记服务与买方钱包是不同角色；报价、构建和验证不代表成交，实际成交须独立核验UID、Trade及净资产证据。',
        )

    atomic_origins = [item for item in inputs if Path(item['path']).name == 'atomic-swap-report-origin.json']
    if atomic_origins:
        if len(atomic_origins) != 1:
            raise ValueError('No unique authenticated atomic swap origin')
        origin = source_json(atomic_origins[0])
        configs = [item for item in inputs if item['path'] == origin['source']]
        if len(configs) != 1:
            raise ValueError('No authenticated atomic swap source')
        source = source_json(configs[0])
        plans = [item for item in inputs if item['path'] == source['campaign_plan']]
        if len(plans) != 1:
            raise ValueError('No authenticated atomic campaign profile')
        plan = source_json(plans[0])
        return AgentProfile(
            business_summary='根据指定ERC20资产、数量和滑点生成报价及原子交易方案，由买方钱包授权执行；本报告范围为' + plan['scope'],
            ecosystem='ERC20 · 原子兑换方案', role='asset-execution', registration_chain_id=chain,
            execution_chain_ids=[plan['chain_id']], capabilities=[plan['capability']['title']],
            execution_accounts=[plan['executor']], evidence_status='verified',
            sources=[source['registration_proof'], source['campaign_plan']],
            boundary='登记服务身份与买方执行钱包是不同角色；方案、模拟和真实成交分别核验，未采任务及未测声明不代表通过。',
        )

    unsigned_origins = [item for item in inputs if Path(item['path']).name == 'unsigned-swap-report-origin.json']
    if unsigned_origins:
        if len(unsigned_origins) != 1:
            raise ValueError('No unique authenticated unsigned swap origin')
        origin = source_json(unsigned_origins[0])
        config_refs = [item for item in inputs if item['path'] == origin['source']]
        if len(config_refs) != 1:
            raise ValueError('No authenticated unsigned swap source profile')
        return AgentProfile.model_validate_json(json.dumps(source_json(config_refs[0])['profile']))

    if policy in ("evm-swap-builder-v1", "evm-swap-builder-v2", *SHARED_POLICY_VERSIONS):
        origins = [item for item in inputs if Path(item["path"]).name == "swap-report-origin.json"]
        if len(origins) != 1:
            raise ValueError("No unique authenticated swap report origin")
        origin = source_json(origins[0])
        campaigns = [item for item in inputs if item["path"] == origin["campaign"]]
        if len(campaigns) != 1:
            raise ValueError("No unique authenticated swap campaign profile")
        campaign = source_json(campaigns[0])
        declared = (report.get('shared_assessment') or {}).get('capabilities', [])
        capability_names = [item['title'] for item in declared] if declared else ['ERC20兑换报价', '精确授权与兑换方案']
        summary = ('公开声明' + '、'.join(capability_names) + '；本次范围只验证网关ERC20兑换方案及用户授权执行。'
                   if declared else '根据指定代币、金额和滑点生成Base链兑换报价与待签名方案；经用户授权后，由用户钱包执行，平台核验实际成交、资产到账与授权余额。')
        if policy in (MULTICAP_POLICY_VERSION, POINT_POLICY_VERSION):
            summary = '提供即时资产兑换、定时与限价订单管理；本次核验兑换，以及订单创建、合约查询、撤销退款。由用户钱包签名执行，自动触发成交仍未验证。'
        return AgentProfile(
            business_summary=summary,
            ecosystem="Uniswap V3 · x402", role="asset-execution", registration_chain_id=chain,
            execution_chain_ids=[campaign["execution_chain_id"]], capabilities=capability_names,
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
