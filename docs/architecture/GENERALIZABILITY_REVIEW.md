# 评价方案可复用性审查

日期：2026-10-18。本文区分已经实现的公共规则、单对象适配和真实复用验收，不改变冻结政策、原件或既有报告。

## 当前结论与推进顺序

Brain DeFi LP 是一个真实的窄范围特例试点，不能据此宣称 LP 端到端方案已经通过多对象复用验收。Olas 2198、2235 已使用同政策和实现完成三维评价，中文报告通过真实 API/worker/ PostgreSQL 发布，综合分分别为 89.72、98.71。当前按用户授权先收集跨提供方功能声明、按能力分析可测覆盖与价值，再决定后续类别；不自动扩大既有名单或启动第三类。尚未验证跨提供方复用。

两个预测实例各有 14 个不同市场的输入、输出及完整任务链证据，并完成各自 10 次全新可用性采样。报告独立重验后：2198 为可用性 98.20、功能 75.66、行为 100、综合 89.72；2235 为 98.61、97.81、100、98.71，均为 COMPLETE。该结论仅覆盖政策限定的历史预测任务，不能将其他未采样工具或新对象视作已通过。

## 第一类：哪些规则已经与 Agent 身份分离

- `packages/core/src/reputation_core/liquidity.py:51` 的 `verify_increase` 接收链、执行者、管理器、仓位、交易哈希和可信区块时间，核对直接 NPM 增仓调用、参数、唯一事件及数量边界。它不含 Brain 名称或注册号，也不声称验证整个策略。
- `packages/core/src/reputation_core/disclosure.py:63` 的 `verify_disclosure` 接收两种代币、精度、固定区块前后状态及完整同块增减仓事件，重建指定交易后的流动性并精确核对披露。该算法不依赖某个 Agent，但要求同一种 NPM ABI、可信状态读取及完整日志。
- `packages/core/src/reputation_core/behavior.py:94` 的身份、交易/区块/事件绑定、确认距离和任务窗口检查可复用；完整包装—兑换—增仓顺序的判定仍受下述具体协议路径限制。
- 四态区分、用途互斥、样本充分门槛、30/40/30 权重、只追加报告与数据库租约等平台规则不依赖某个 Agent。通用基础设施不能替代业务适配器的第二对象验收。

## 第一类：目前仍固定的边界

| 层次 | 真实文件位置 | 当前固定内容 |
| --- | --- | --- |
| 冻结试点 | `configs/pilots/brain-defi-liquidity-v1.json` | 注册号、注册交易、执行钱包、记录入口/摘要、14 个样本索引和 13 条无动作索引 |
| 采集计划 | `scripts/collect_liquidity_history.py:20`、`:59`、`:71`、`:87` | BSC/ZAN、NPM、Brain 配置、`brain-agent` 原件键、`history[].steps.increase`、`position`/`wallet` 和三个英文交易标签 |
| 独立上下文 | `scripts/collect_liquidity_context.py:13`、`:49`、`:59` | CAKE/WBNB、Pancake factory、500 费档及固定方向 |
| 行为规则 | `packages/core/src/reputation_core/behavior.py:12`、`:199`、`:246` | WBNB/CAKE、router/NPM、8 字段 `exactInputSingle`、WBNB→CAKE、500 费档、标准代币 Transfer 语义 |
| 自动选案 | `packages/core/src/reputation_core/planning.py:77` | 只支持 BSC、Pancake V3 NPM 和 `run-history-increase-v1`；现有描述符并未完整表达币对、费档和执行路径 |
| 来源与可用性 | `scripts/select_evaluation_plan.py:20`、`:105`；`scripts/sample_availability.py:22`、`:59` | Brain 配置、来源文件键和公开记录 JSON 结构 |
| 报告编排 | `scripts/build_liquidity_report.py:34`、`:264`、`:383`、`:418` | 注册事件 dataURI 内 `Operating wallet`/`record` 绑定；`other_used`/`wbnb_used` 字段、代币映射和展示文案 |

因此，现状不能只替换注册号或名称后就评价任意 LP Agent。`verify_increase` 的调用选择器检查位于 `liquidity.py:90`：推广时应先识别是否为已支持的直接调用；合法但未适配的 multicall、mint 或其他路径应保留 UNKNOWN，不能把“未适配”当作 Agent 失败。

## 第一类的最小复用边界

先寻找同链、同协议、同币对和同三步路径，且任务归属可区分的第二个真实对象。只新增该对象的冻结配置、来源字段映射和独立采样计划，将配置/来源键/样本索引作为输入，不复制一套核验代码，不建立通用插件框架。

若确有第二对象使用不同币对或费档，才将经操作者核实的 `chain / wrapped_native / token0 / token1 / router / factory / manager / fee` 移入协议配置，并以实际固定区块的 `positions`、`decimals`、`getPool` 证明映射。不能从 metadata 接受任意 RPC、合约或可执行代码；任意税币、重基币不能仅凭 Transfer 日志套用标准代币判据。新增受支持路径须记录 ADR 与兼容性，保留原政策和报告。

第二对象至少需要：

1. 独立公开注册身份，及可信的服务—执行钱包—公开历史入口绑定。钱包可以共用，但必须有额外服务/任务归属证据，不能将同一历史和同一批交易换名计作第二个对象。
2. 在该政策允许的登记时间范围内，至少 14 个实际增仓任务，按预先确定的机械顺序分为互斥 7 功能、7 行为槽；无动作、未知和不支持记录保留，不能按预期结果删选。
3. 功能披露包含仓位、实际资产用量和执行后流动性，能够与固定状态及完整同块日志精确对照；行为任务提供三笔真实交易及任务时间，并能核实执行者、目标、池、事件、数量限制、顺序和确认距离。
4. 本对象入口另做 10 个全新可用性槽位。只有规划说明、无动作记录、共享交易哈希或缺少历史披露的对象不能取得完整三维分。

## 预测方案已取得的复用证据

`prediction_evidence.py`、`prediction_chain.py` 和 `collect_prediction_history.py` 使用同一实现，差异来自冻结 operator profile 的注册号、实际 Mech、服务号与注册原件。评分不接受外部直接质量分；报告另重验 CID/DAG、任务和原问题绑定、最终结算与原始概率。

- 2198：`runtime/prediction-history-20261018T072135Z-26548298`，14 市场/14 任务，418 次新读取，完整输出 14，链核验 PASS 14；已发布[详细报告](../../runtime/evaluation-report-20261018T074802Z-2378ca3d/report.json)，综合 89.72。
- 2235：`runtime/prediction-history-20261018T072524Z-fc00242b`，14 市场/14 任务，432 次新读取，完整输出 14，链核验 PASS 14；已发布[详细报告](../../runtime/evaluation-report-20261018T074803Z-c4f9fbe0/report.json)，综合 98.71。
- 两次实际取证都使用连接复用和有界并发；未发生 401/402/403/429 或 host-stop。该结论仅覆盖这两次实际记录，不推定其他实例或提供方必然可评。

正式批次沿用采样前已实现的 `(blockTimestamp, blockNumber, id)` 降序确定性规则。后来提出的区块内交易/日志排序仅作离线实验，已移出生产代码。诊断确认：2198 的差异仅为同时间未适配 UNKNOWN 背景记录的位置，普通记录的相对顺序、14 个合资格市场及其顺序、7/7 分组均未变；2235 的资格全序也未变。实验和失败断言记录保留于 `runtime/prediction-order-verification-20261018T073451Z-132c8448`，没有事后换样本。

## 结论的语义边界

- LP 只能声称公开历史入口的访问体验、已披露增仓结果与独立状态的一致性、三笔公开操作的完整归属；没有评价实时仓位、收益、最佳区间或资金安全。
- 预测虽然可以由配置更换 Mech、服务号、实际注册号和来源，但 `prediction_evidence.py` 的身份适配仍精确要求 Valory operator 域名 `https://{mech无0x}-100.mech.valory.xyz`。选案/报告层接受更宽的域名不等于收集器已支持其他提供方。
- 两种政策的 availability 都是本机既定线路对公开历史入口的本次访问体验，不代表实时 Agent 推理在线，更不能把代理连接故障扣作 Agent 失败。
- 预测功能维度包含概率任务效果。Brier 衍生信用分不是 JSON 合规分或预测准确率；50/50 的信用为 75，给最终方向不足 50% 的 FAIL 不等于撒谎或未交付。
- Omen/Reality 的最终链上结算是本范围的独立判据，不等于已独立调查现实世界真相。登记前的历史只有在同服务和历史执行控制均有证据时才可讨论连续归属，不能前推当前注册。

旧串行 2182 在资格阶段按新优先级停止，`runtime/prediction-history-20261018T070812Z-bb2164f7/interrupted.json` 标为 INTERRUPTED：268 条观测保留，另有 269 号发送前计划但无观测；没有正式 14 槽计划、bundle 或分数，不计完成对象。原进程因人为停止返回 1，不记作验收通过。
