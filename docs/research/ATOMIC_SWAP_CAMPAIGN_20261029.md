# 原子ERC20兑换采样草稿

2026-10-29最新root记录：正式plan-v4共38槽位，SHA `08563d2fdf9cfa706b8979d6c66a7e65514507c13366a1d81ae9d790589defe5`。A37/A38是不同amount表示的覆盖扩展，真实500依冻结错误契约为F负例，不是解锁总分；A/F required_decisive仅为覆盖目标，正常B才有硬数量门禁。root已报告8次实兑与16个非实兑历史固定块完整16CALL通过，正在统一64块确认和正式导出，最终结果以原件重放/PG导入为准。子代理没有执行本轮资金或确认网络操作。

2026-10-29后续现状：以下34项矩阵为原DRAFT历史；正式计划已由root冻结为plan.json，并依平台传输中断追加不可变plan-v2/v3。当前v3共36槽位，SHA256 `73ce3e96ef9b726d63e126795e20adea4ff3bfea21792a1164d10c18839c4d66`；A35/A36分别复制A02/A03经济意图，使用新UUID，旧UNKNOWN和case成员保留，B方向required_decisive仍各4。调度目标8次正常实兑，目标数不等于已成交数。

A09–A34已完成26真实HTTP任务/42请求（32个200、10个400），原件及失败语义保留；A01等实兑由root单序列执行，本文件不替代其回执核验。最新只读source草稿为 `runtime/atomic-swap-campaign-20261029/source-export-draft-f1aa63ce-885e-477f-9e05-154342578cd1`：该18:05:08 UTC快照有30个HTTP观测任务、28个取得HTTP响应、1个执行source-item，冻结36槽位；这不是评分报告或36个已完成任务。

通用导出命令：`.venv/Scripts/python.exe -X utf8 scripts/export_atomic_swap_sources.py --plan <frozen-plan> --plan-sha256 <actual-sha> --registration-proof <public-proof> --http-map <retained-map> --output <new-runtime-directory>`。它自动接入同计划链内后续公开执行source-item，拒绝私密签名/SEND/auth来源；root在取证追加后另存新草稿，不覆盖旧输入。正式build仍用 `scripts/build_atomic_swap_report.py`，其共享核验入口、profile、链视图已接入。离线导入前置核验和前端构建通过；真实PostgreSQL导入与公开发布由root后续执行。

原草稿记录（采样前）：日期2026-10-29，状态 **DRAFT**，当时尚未冻结或执行业务请求、模拟、签名及链交易。以下代码和计划本身不是实验成果；后续真实进展以上方最新记录和原件为准。本草稿为十个交易Agent、各至少30真实任务目标的一份协议可复用矩阵，不把一个对象当十个对象。

草稿：`runtime/atomic-swap-campaign-20261029/plan-draft.json`，当前字节SHA256 `25f47422c3c090aab90e1f86b47d357fd75f79fc67183e6756a7c10ed54324fe`。此哈希仅标识草稿，**不是已冻结执行授权**。负责人须在首个业务请求前确认登记绑定、资金/协议前置和最终参数，另存FROZEN版本、真实frozen_at及SHA；保留本草稿和全部原件。

## 范围与来源

对象配置为Topaz Agent，登记声明为BNB链56 ERC-8004 #113284，业务执行链为Base8453；负责人已取得并核验 `runtime/identity-goal-20261029/topaz-113284/registration-proof.json`，tokenURI服务绑定为 `https://agents.topazdex.com`；DRAFT的 `registered_service`已采用该确切webroot。此处登记结论由负责人提供，适配器仍须对实际输入proof重放校验。owner与执行钱包是不同角色，自有执行者为 `0x73d642847cb9a3acef116ea207a74b9956c34a09`。本草稿不读取任何钱包秘密、账户配置、余额或授权。

只选已有USDC/WETH精确输入兑换、参数/缺省一致性、完整原子call约束、独立效果与安全拒绝。API quote/build可作为同一任务的连续阶段；A/F/B共享原件，但**2个HTTP请求仍只计1个task_key**。34项计划含24个正常任务与10个拒绝任务，其中正常的前8项安排真实兑换，方向各4项。这里没有34个已完成任务。

冻结公共OpenAPI原件 `runtime/candidate-expansion-goal-20261028-direct/phase1/topaz-openapi.response.bin`，SHA256 `a97122624efe4f4d75d4f23a8395cc48667b63942cbc393d80c238d16296b863`；默认slippage100bps、deadline600s、slippage范围1–500、deadline范围30–1800。source_snapshot同时绑定该GET原observation；protocol_binding引用静态准备文件 `runtime/atomic-swap-campaign-20261029/protocol-binding-preparation.json`，SHA256 `d002abe16b599a847839a47cdb9abea288dbd8d9ea5f665ebe51b51d804d2960`。其中运行代码hash全部为null、状态为PREPARATION，**不能直接冻结**。负责人应另存已审查部署绑定，填入可信固定块五角色runtime_keccak，替换plan内path/SHA后再冻结；不覆盖本准备原件。quote明确支持symbol/address、human数量或0x base units；A23仅quote使用hex，build使用等价human值，A24仅quote使用USDC/WETH符号，build使用已核地址，避免臆定build也承诺相同表示形式。Agent元数据原件 `runtime/candidate-expansion-goal-20261028-direct/phase1/topaz-agent.response.bin`、SHA256 `8dbebd61efff78f8100caf72757a08de82c56bb376081d34c53aea06691177e7`用于保留未选声明。

不测全58项声明不是出范围综合分的强制门槛；未选的LP/CL建仓、投票、奖励、跨链及其他链保留范围外。禁止发币、tokenize、身份/报告mint、新部署、LP/CL铸造与原生资产wrap，不为了样本数量开启这些动作。

## 34个前瞻任务

输入资产：USDC `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`，WETH `0x4200000000000000000000000000000000000006`。正常任务两阶段均请求同一经济意图，negative仅调用明确业务quote路由，不发送build或资金。下表数量是人类单位；A23的quote以0x原子单位表达。

| task_id | 方向 | quote sellAmount | slippage bps | deadline s | 任务目标 |
| --- | --- | --- | --- | --- | --- |
| A01 | USDC→WETH | 0.02 | 50 | 600 | 真实兑换目标 |
| A02 | WETH→USDC | 0.00001 | 50 | 600 | 真实兑换目标 |
| A03 | USDC→WETH | 0.05 | 50 | 600 | 真实兑换目标 |
| A04 | WETH→USDC | 0.00002 | 50 | 600 | 真实兑换目标 |
| A05 | USDC→WETH | 0.10 | 25 | 600 | 真实兑换目标 |
| A06 | WETH→USDC | 0.00004 | 25 | 600 | 真实兑换目标 |
| A07 | USDC→WETH | 0.15 | 100 | 600 | 真实兑换目标 |
| A08 | WETH→USDC | 0.00006 | 100 | 600 | 真实兑换目标 |
| A09 | USDC→WETH | 1.00 | 50 | 600 | 报价/方案目标 |
| A10 | USDC→WETH | 10.00 | 50 | 600 | 报价/方案目标 |
| A11 | WETH→USDC | 0.00010 | 50 | 600 | 报价/方案目标 |
| A12 | WETH→USDC | 0.00100 | 50 | 600 | 报价/方案目标 |
| A13 | USDC→WETH | 0.10 | 1 | 600 | 报价/方案目标 |
| A14 | USDC→WETH | 0.10 | 500 | 600 | 报价/方案目标 |
| A15 | WETH→USDC | 0.00004 | 1 | 600 | 报价/方案目标 |
| A16 | WETH→USDC | 0.00004 | 500 | 600 | 报价/方案目标 |
| A17 | USDC→WETH | 0.10 | 缺省100 | 600 | 报价/方案目标 |
| A18 | WETH→USDC | 0.00004 | 缺省100 | 600 | 报价/方案目标 |
| A19 | USDC→WETH | 0.10 | 50 | 30 | 报价/方案目标 |
| A20 | WETH→USDC | 0.00004 | 50 | 1800 | 报价/方案目标 |
| A21 | USDC→WETH | 0.10 | 50 | 缺省600 | 报价/方案目标 |
| A22 | WETH→USDC | 0.00004 | 50 | 缺省600 | 报价/方案目标 |
| A23 | USDC→WETH | 0x186a0 | 50 | 600 | 报价/方案目标 |
| A24 | USDC→WETH | 0.03 | 50 | 600 | 报价/方案目标 |
| A25 | USDC→WETH | 0 | 50 | 600 | 安全拒绝：sellAmount |
| A26 | USDC→WETH | -1 | 50 | 600 | 安全拒绝：sellAmount |
| A27 | USDC→WETH | 0.1 | 0 | 600 | 安全拒绝：slippageBps |
| A28 | USDC→WETH | 0.1 | 501 | 600 | 安全拒绝：slippageBps |
| A29 | USDC→WETH | 0.1 | 50 | 29 | 安全拒绝：deadlineSeconds |
| A30 | USDC→WETH | 0.1 | 50 | 1801 | 安全拒绝：deadlineSeconds |
| A31 | USDC→WETH | 0.1 | 50 | 600 | 安全拒绝：sellToken |
| A32 | USDC→WETH | 0.1 | 50 | 600 | 安全拒绝：chainId |
| A33 | USDC→WETH | 0.1 | 50 | 600 | 安全拒绝：buyToken |
| A34 | USDC→WETH | 0.1 | 50 | 600 | 安全拒绝：sellToken |

A01–A08按双向交替排列；本金在自有资产之间往返，不由本草稿假定实时余额或授权可用。四个USDC真实目标名义输入合计0.32USDC，四个WETH真实目标输入合计0.00013WETH；这不是费用上限或余额承诺，也不把内部归集算Agent履约。A09–A24只报价/构建，不为较大报价目标投入本金。A19的30秒最短deadline只测试生成方案，不安排真实发送追逐短窗。

A25/A26零/负输入、A27/A28滑点越界、A29/A30期限越界、A31畸形资产地址、A32不支持链、A33/A34缺必填字段，均为预先保存的真实业务请求目标。安全拒绝须是该精确URL及请求得到完整400/422及明确输入错误；404路由错误、502/503、超时、RPC不足、未适配不能当安全通过，也不统一扣Agent分。未返回方案时不虚构call或最低到账。

## 预先固定的判据和分母

沿用SharedAssessment v3与30/40/30，不按本批预期分数选样。A仅24个正常任务，要求其已安排的quote/build均完整正常成功；没有公开SLA，latency逐阶段与合计展示，不能自行设毫秒门槛扣分。10个预期拒绝目标只进入F safe-rejection，避免把正常输入校验4xx叫可用性失败。

F按方向固定intent-binding、call-safety、execution-effect三组案例；另有4项default-contract与10项safe-rejection。相同task可提供多个不同criterion，但每task＋维度＋判据只出现一次。案例的required_decisive在计划中固定为该案例安排的任务数，不因失败/未知删分母；覆盖与可判分数分开。B仅前8项真实兑换，按方向各4项正常履约目标；费用、报价、模拟、保护退出均不能补正常成交B。

独立call检查采用通用Slipstream Universal Router七CALL协议，不按Topaz名字/域名/登记ID评分：清旧router授权、清Permit2、精确token授权、精确Permit2 approve、execute(commands0004)、清Permit2、清token授权。root须证明实际完整原子执行、执行者、部署及池/Factory绑定；仅可解析call不等于安全执行许可。

F固定块效果与B实际净到账都采用16调用约束：(用户输入余额、用户输出余额、Router输出余额)前读＋真实7CALL＋相同3项后读＋3类授权后读，禁state/block overrides。必须核自有输入/输出变化、三类授权最终0、完整目标调用及Router旧输出余额。SWEEP只检查Router当时总余额，旧余额不能补本次兑换最低值；不得只凭内部min0或最终SWEEP门槛推断净到账通过。B还需真实receipt/事件、期限窗口、执行钱包模型保持及至少64块确认距离。

缺省slippage明确为100bps；缺省deadline只核provider公开issued_at与calldata execute deadline内部600秒TTL一致，实际时效另由固定块timestamp≤有效deadline证明。缺issued_at、observed_at或无法复核时钟上下文均保持UNKNOWN，不用跨机网络延迟强扣分。

## 最小采集约定

plan内requests逐stage冻结method/url/json，source将原始observation和response按task_key绑定；不能以一个旧方案复制成多个task。response_mapping只映射最终build响应：`/transactions`、`/chainId`、`/timestamp`和`/data`下输入输出、amount、payer、minOut、expectedOut、slippageBips和blockNumber字段；quote阶段没有payer或transactions，不因这些build字段在quote不存在而判错。此配置仅映射事实，不接受提供方给分。登记proof、冻结声明、业务原件、完整固定块模拟、原子执行意图、真实tx/receipt和后读查询仍需负责人采集；计划本身不供这些缺失证据。

后续只读槽位pool列表与自有positions已列为future_unselected_slots，暂不进入本轮样本和评分分母。必须先冻结确切参数、公开声明及可信链判据，不能把API200、无仓位或未查询当功能通过，不创建NFT/仓位来补覆盖。

## 通用输入与冻结接口

新来源版本为 `atomic-swap-evidence-v1`，adapter为 `retained-atomic-swap-campaign-v1`。最小source形状如下；尖括号内容是字段说明，不是已存在证据。每个被引用的原件、observation、response、配置、proof及冻结plan都须列入sources并匹配实际字节SHA256；不能把live实现源码作为不可变manifest输入。

```json
{
  "schema_version": "atomic-swap-evidence-v1",
  "adapter": "retained-atomic-swap-campaign-v1",
  "candidate_key": "<same as frozen plan>",
  "name": "<same as frozen plan>",
  "registration_reference": "<canonical ERC8004 reference>",
  "registered_service": "<exact registered service URL>",
  "registration_proof": "<public retained proof path>",
  "campaign_plan": "<FROZEN plan path>",
  "tasks": [{
    "task_key": "<persisted UUIDv4 from plan>",
    "http_observations": ["<quote observation>", "<build observation>"],
    "simulation": {
      "plan": "<exact 16-call plan path>",
      "rpc_observations": ["<retained original fixed-block RPC observations>"],
      "call_label": "<simulation observation basename without .observation.json>"
    },
    "execution": {
      "plan": "<exact 16-call plan path>",
      "intent_path": "<persisted pre-send intent path>",
      "payer": "<buyer execution wallet>",
      "transaction_hash": "<actual sent tx hash>",
      "rpc_observations": ["<original canonical transaction/receipt/header/post-state observations>"]
    }
  }],
  "sources": [{"path": "<public relative artifact path>", "sha256": "<actual 64-hex SHA256>"}]
}
```

未采task可以完全不在source.tasks中，但仍保留在plan.tasks/cases分母；没有模拟或真实成交时省略相应对象，不填虚构hash。安全拒绝任务只保留单个已冻结quote observation。plan格式以实际DRAFT为完整模板，另存时改status为FROZEN、填真实frozen_at，使用不可变source_snapshot、response_mapping、scoring_contract、protocol_binding、capability、cases、tasks。frozen_at须先于所有本批业务观测；task_key、输入参数、方向、case成员、required_decisive不能事后重组。采样后追加任务另冻新版本。

`response_mapping.calls_pointer`指向call数组；`fields`映射token_in、token_out、amount_in、recipient、minimum_out、quoted_out、chain_id及可选slippage_bps/fixed_block/issued_at；`call_fields`可配置各call的to/data/value字段名，缺省采用同名字段；`quote_fields`可为quote阶段单独映射相应事实。这里只接受数据映射，不执行远端代码。最小16-call plan为 `{task_key,chain_id,payer,source_response_sha256,calls}`；calls使用 `{target,value,data}`，必须与 `atomic_evidence_calls({chain_id,calls:provider_calls})` 的精确结果一致。前置intent为 `{task_key,plan_sha256,simulation_plan_sha256,fixed_block,block_hash,transaction}`，transaction含真实from/to/chainId/value/data/nonce；未发送时不创建execution证据。

16调用下标为0用户输入余额、1用户输出余额、2Router输出余额、3–9提供方原7CALL、10–12相同余额后读、13 token allowance(owner,Permit2)、14 token allowance(owner,router)、15 Permit2 allowance(owner,token,router)。Permit2后读须完整96字节amount/expiration/nonce；许可金额必须为0。`atomic_post_calls()`返回10–15六项，供回执块独立后读。固定块RPC还需chainId、block header、五角色eth_getCode、factory.getPool、pool token0/token1/tickSpacing及池eth_getCode；实际执行需原tx、receipt、canonical block、最新块高度与executor代码后读。所有RPC由负责人可信配置选择；source不提供RPC地址。

静态Base部署：router `0xe4b23F13b24232C1E68AD0575191216152AA9480`，Permit2 `0x000000000022D473030F116dDEE9F6B43aC78BA3`，CL factory `0xaa5865dC3A60b25D305226d66fd573021f0D8fFB`，CL implementation `0x2DaA7cF731334b4Cd1c2E4E01E97Ca67F4B9C6AE`。来源path/SHA、getter ABI和clone完整格式见准备文件。WETH/USDC spacing50的公式预测池为 `0x9dd30d200b5c7e6874ab5a23c7bd7e2ad6d9c135`；此处无RPC，不称部署或池已verified。`predict_slipstream_pool()`可在不联网的情况下产生同公式地址，报告仍要求独立同块原件。

构建命令为 `.venv/Scripts/python.exe -X utf8 scripts/build_atomic_swap_report.py --source <public-source.json> --output <new-runtime-directory>`；输出全新report/manifest/origin/html，并将必要实现复制为artifact内 `.py.txt` 软件provenance快照。快照仅hash存证，不执行。来源与origin版本独立；既有报告分派由负责人后接，不改变旧报告。

本文件仅由离线参数/唯一标识与计划完整性检查生成；网络、钱包、RPC、模拟、签名、付款、实际兑换均0。未运行生产工程测试，仅新adapter的一项离线验收已通过，覆盖真实七CALL格式及受控正常/风险负控；不是公开链集成结果，旧suite未重跑。负责人单序列冻结并执行；接口/资金/部署/证据阻断只阻断相关任务，不修改红线或旧报告。
