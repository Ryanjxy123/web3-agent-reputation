# 真实链上执行 Agent 群体：Omenstrat 只读取证

日期：2026-10-23（北京时间）。本轮调研、真实采集已完成；确定性核验、入库和页面交付以主任务记录为准。

## 1. 选取结论

优先采用 **Olas 注册的 Omenstrat 交易 Agent 实例**验证可复用性。这些实例会用自己的 Safe 智能账户在 Gnosis 的 Omen 市场购买结果份额，与旧目录中“出售研究预测结果的 Mech”分工不同。旧 Mech 可以是交易者购买的上游服务；两者不能混称为同一种交易能力。

本轮先从官方交易者索引取得 30 个不同 Safe/服务关联，再冻结原始返回顺序的前 10 个作为取证群体。选择规则在读取这些对象的链上核验结果之前固定：按保留索引的历史累计买入次数降序，不按本平台分数、成功率或某个漂亮案例选取；有缺项不换对象。此选择偏向历史交易量大、上线时间较长的实例，**不是当前活跃 Agent 的随机代表样本**。

资产买卖、授权和签名应纳入能力范围。本轮直接分析真实历史资产交易和公开签名，未创建新签名、使用用户资金或发送链上写交易。后续主动测试可以考虑本地链、分叉、测试网及明确授权的真实调用，分别记录环境与证据，不能将模拟成功当成真实公共实例执行成功。

官方来源：

- [Trader 官方仓库](https://github.com/valory-xyz/trader)：Omenstrat 和 Polystrat 的服务分工、执行链和 Safe 账户模型。
- [官方 Predict 前端常量](https://github.com/valory-xyz/olas-predict/blob/main/constants/index.ts)：公开 Omen、交易者与 Conditional Tokens 索引。
- [官方查询](https://github.com/valory-xyz/olas-predict/blob/main/graphql/queries.ts)：交易者、服务 ID、买入和市场字段。
- [官方注册合约配置](https://github.com/valory-xyz/olas-predict/blob/main/constants/leaderboard.ts)：Gnosis ServiceRegistry 为 `0x9338b5153ae39bb89f50468e608ed9d764b755fd`。

## 2. 真正取得了什么

采集脚本：`scripts/collect_olas_execution_cohort.py`。外网均走现有 `SafeHttpClient`；链 RPC 来自操作者静态配置 `configs/generic-rpc.json`，未接受 metadata 中的 RPC。所有业务采集都是只读。

原始研究目录：`runtime/execution-cohort-20261023/`。

固定 10 对象目录：`runtime/olas-execution-cohort-20261022T173937Z-8ad2b5c5/`。

入口文件：

- `summary.json`：固定顺序、对象、链上下文、各类原件路径和哈希、采集缺项。
- `singleton-supplement.json`：追加的每对象历史 Safe 单例及代码核验，不改写原 summary/checkpoint。
- `allowance-supplement.json`：三笔直接 buy 的历史已有授权额度。
- `position-supplement.json`：每对象从市场条件、方向和抵押资产绑定 Conditional Tokens 份额 ID 的追加证据。
- 原始研究目录内 `configuration-metadata-supplement.json`：两个不同历史配置哈希对应的 CAR/DAG 认证声明。

每个对象都取得一笔真实买入的 transaction、receipt、block；交易前一块的 ServiceRegistry → Safe 映射、Agent 实例、Safe owners；以及买入市场的抵押代币、Conditional Tokens 合约和条件 ID。每个对象另扫固定“买入区块前 256 块”内该 Safe 发出的全部 `ExecutionSuccess` / `ExecutionFailure` 事件。缺项如实保留，未做业务重试或替换。

| 顺序 | Olas 服务 ID | Safe 执行账户 | 选中买入时间 | 前 256 块 Safe 成功/失败事件 | 采集缺项 |
| --- | --- | --- | --- | --- | --- |
| 1 | 1953 | `0xee031c0b86c3a4345b363bf088415d8c874baa26` | 2026-06-27 05:06 UTC | 13/0 | 无本轮采集缺项 |
| 2 | 219 | `0x8dd0f0f64e575a356545d9ed096122a1887e64bf` | 2026-10-22 02:18 UTC | 4/0 | 无本轮采集缺项 |
| 3 | 1949 | `0x984a845e62825ec376c063aa7c230f9a4ce735a7` | 2026-06-27 05:05 UTC | 14/0 | 历史 threshold 单次读取未成功 |
| 4 | 415 | `0x8cd3e072c8341cfe1a03dbe1d6c32b5177b06164` | 2026-10-22 02:13 UTC | 3/0 | 无本轮采集缺项 |
| 5 | 1968 | `0x18f7eb70cee093671b7fb9d48cf141cffeb0703f` | 2026-06-26 14:23 UTC | 1/0 | 无本轮采集缺项 |
| 6 | 1781 | `0x718b95f721ea02f5d08f60702bf4bfc6caca30a8` | 2026-06-27 05:15 UTC | 12/0 | 无本轮采集缺项 |
| 7 | 1788 | `0xc64bd69e2f990e066cc6cae23d6cedb0a359a867` | 2026-06-26 14:56 UTC | 1/0 | 无本轮采集缺项 |
| 8 | 1969 | `0xa0cf77873c8e5ce763533e14b7dd81cb1f53a2fb` | 2026-06-27 00:49 UTC | 19/0 | 历史 Safe proxy code 单次读取未成功 |
| 9 | 1784 | `0xfa92b4788f8f68e872b565d1d851c90cce7fb595` | 2026-06-26 16:27 UTC | 1/0 | 无本轮采集缺项 |
| 10 | 1684 | `0xfc778ea7ac81ad086e84c2326f86d29c5715e355` | 2026-06-27 02:27 UTC | 2/0 | 无本轮采集缺项 |

上述时间说明样本新旧；较早样本不能证明实例目前在线。Olas service ID、ERC-8004 token ID、Safe 地址也不是可互换的标识。此处独立核验的是 Olas 服务身份，不凭编号相同就声称已完成 ERC-8004 桥接核验。

## 3. 身份、声明、签名和执行怎样连起来

应展示下面这条证据链，而不是只展示交易哈希：

1. 交易前块的 `ServiceRegistry.mapServices(serviceId)` 指向目标 Safe；`getAgentInstances(serviceId)` 给出该服务的实例账户。
2. 同一历史块 Safe 的 owners/threshold 说明谁能授权。`masterCopy()` 指向真实 Safe 实现；读取该历史块单例代码并计算 Keccak，与官方部署清单的地址及 codeHash 比较。
3. 注册配置哈希认证自然语言声明。该群体出现两个配置，均为 `service/valory/trader_pearl/0.1.0`，描述为 Omen 预测市场交易者，代码内容地址不同。9 个实例共享配置内容，按配置哈希认证一次后复用，仍保留每实例自己的链上映射。
4. 解开 Safe 的 `execTransaction`。本轮有两种正常形态：delegatecall 到官方 MultiSend，内部依次进行精确额度 approve 和目标市场 buy；或直接 buy 并复用已有授权。1953、1781、1684 的历史前块 allowance 恰等于各笔 investmentAmount，不能因没有同笔 approve 就判失败。必须核准每条内部操作，不能因为外层 receipt 成功就跳过内部。
5. 对实际签名和 `ExecutionSuccess` 的 Safe 交易哈希做关联；校验交易属于预期链、Safe、注册实例和市场，并核对真实 buy 参数、结果份额事件和抵押资产流转。

10 个对象的历史 `masterCopy()` 均为 `0xd9db270c1b5e3bd161e8c8503c55ceabee709552`；每对象历史块代码哈希均精确匹配官方 Safe v1.3.0 清单。这是来源核验结果，不意味着所有业务检查均已通过。1949/1969 的原始缺项仍然存在。

重要的内容认证细节：配置 CID 是 dag-pb / UnixFS，不能将 HTTP 返回 JSON 的 SHA256 直接与 CID digest 相比。本轮读取 CAR 并复用现有 `read_car_file` 逐块认证；根文件重建后再与保留 JSON 精确比较。

官方原件：

- [Safe v1.3.0 单例部署清单](https://github.com/safe-global/safe-deployments/blob/main/src/assets/v1.3.0/gnosis_safe.json)
- [Safe v1.3.0 MultiSend 清单](https://github.com/safe-global/safe-deployments/blob/main/src/assets/v1.3.0/multi_send.json)
- [Safe execTransaction 语义](https://docs.safe.global/reference-smart-account/transactions/execTransaction)
- [FPMM 官方合约](https://github.com/gnosis/conditional-tokens-market-makers/blob/master/contracts/FixedProductMarketMaker.sol)

## 4. 用 #219 举例，报告应讲清哪些事

真实买入：[Gnosis 交易](https://gnosis.blockscout.com/tx/0x2a0f5e06a32cdc801ee7aa045f35e367dcc556d2e16de304566b6d4cfc2e734f)。

该笔历史交易由注册实例 `0xca714d1486626b1f9a7af900d651e15621d50fde` 发给服务 Safe；交易前块的注册实例与 Safe owner 均指向该实例，threshold 为 1。不能把 Safe 收款地址当成 EOA，也不能只比较交易 `from` 就结束授权判断。

已签调用表达的执行意图：批准目标 Omen 市场使用 `290180360721442944` 个 wxDAI 最小单位，以同一数量买入 Yes（outcomeIndex=0），最低取得 `394160767706284416` 个结果份额最小单位。真实 FPMMBuy 事件记录取得 `398142189602307528`，满足该笔调用的最少份额约束；签名账户、抵押代币、市场、方向和金额需分别核验。

这里的“符合执行意图”是指链上执行与签名参数相符。它不代表“印度进口问题预测正确”，也不代表长期盈利、低风险或适合某位投资者。原问题、市场方向、执行参数、实际结果和未评价范围应分开写。

## 5. 三维仍然不变，避免新的偷换

| 维度 | 该类能力真正应评价什么 | 本轮不足 |
| --- | --- | --- |
| 服务可用性 | 在明确的服务/运行周期和窗口内能否提供声明的功能；若有公开接口，应实测该接口 | Safe、RPC 和索引可读不等于 Agent 在线；本轮不据此给可用性分 |
| 功能声明一致性 | 声明买入能力是否有真实执行支持；执行是否遵循签名中的市场、资产、方向、金额和最少份额等参数 | 一笔 buy 只覆盖一个能力子项；不证明选市、研究、持仓、盈利、卖出或赎回全部正确 |
| 交易行为可靠性 | 授权、身份、链、目标合约、内层执行、真实资产/份额变化和完成状态是否相符；有明确任务分母时统计完成/失败 | 成功买入索引遗漏失败尝试；Safe 窗口也含研究付费、授权等其他动作，不能直接作为 7 个买入任务的分母 |

因此，此批数据可支持真实链上执行的可复用证据展示及独立检查，不应自动产生 10 个新的完整综合分。完整分仍需满足冻结政策的各维证据和样本要求；UNKNOWN、FAIL 与未覆盖分开显示。原预测、查询、流动性报告保持既有含义和原件，不能改标签后冒充这批交易执行结果。

本轮所有 Safe 窗口均未见 ExecutionFailure，只能表述为“此固定窗口内未观察到该类失败事件”。不能解释成无失败历史或 Agent 永远可靠。被 RPC 拒绝、未广播、未打包、链下放弃的尝试，不会因为扫描事件就自动可见。

## 6. 下一步扩展顺序

先完成本批证据的确定性核验、清晰页面和三维缺项提示。以后扩同类，优先按事先声明的最近活跃时间/固定时间窗选样，保留停止运行和不可核验对象；增加每对象不同任务及失败路径，仍不按成绩更换样本。

业务扩展可考虑 Polystrat 的预测份额交易与赎回、Optimus 的 DeFi 换币/仓位调整，再扩到其他框架中的真实运行实例。相同的 EVM 交易、Safe 授权、签名和事件层可复用；市场/资产操作的语义需单独适配。框架仓库和钱包 SDK 不算公共运行 Agent；不能因为支持一个工具包就宣称覆盖该生态的所有 Agent。

新路线启动前，仍须先找多个实例的声明、执行钱包授权、真实任务与交易关联和可访问原件。本轮不因为找到了漂亮的 #219 示例就继续堆单对象规则，也不为多样性优先接入证据尚不可得的品牌。对付费、激活、资产转移或主动签名所需的实际权限和资金，由具体测试计划单独明确。

官方生态状态资料：[研究 Mech 与交易者的分工及 Optimus/历史 Modius](https://olas.network/blog/economy-bby-dgn-mech)、[官方 Pearl Agent 类型配置](https://github.com/valory-xyz/olas-operate-app/blob/main/frontend/config/agents.ts)。这些资料用于候选方向，不替代逐实例核验。
