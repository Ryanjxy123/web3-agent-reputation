# 真实公共 Agent 候选与扩展记录

更新日期：2026-10-18。5 个候选已进行有范围的真实只读检查，另有 3 个提供方的文档线索。完整三维准入数 0，完整评分数 0；至少 10 个完整评分对象的目标不变。以下缺项是当前核实状态，不是对生态整体可行性的结论。

## 已实际检查的候选

| 候选 | 本轮已取得的事实 | 当前缺口与后续动作 |
| --- | --- | --- |
| [DegenAI](https://degenai.dev/erc8004)，Ethereum #23121 | 能力发现列出操作与价格；免费 BTC 资产查询返回成功及 2 条资产资料。ERC-8183 发现结果明确 `contractDeployed=false`，执行者、任务合约、核验者为空 | 身份尚未直接查链；用 HyperLiquid 官方资料核对资产字段及缓存口径，另找可归属执行记录。未部署的这条任务线不能提供履约证据，不推断其所有功能都未部署 |
| [Agent Arena](https://agentarena.site/)，Base #18500 | 实际查询返回 HTTP 200，但 name/description 为空、services=[]，与保留目录存在差异 | 固定同一身份读取链上 agentURI 与文件，查清来源/缓存差异；尚不能直接判业务失败。被查询对象的交易不归给 Arena |
| [DARKSOL / Synthesis](https://github.com/darks0l/synthesis-agent)，Base #31929 | 目录与作者仓库指向同一身份；作者仓库有执行钱包和交易线索，但仪表盘为 localhost | 当前 API 的免费与证明条件未闭合；公开文档读取曾遇到 402，已停止该主机，不调用付费路径。随机数 demo 不等于实际链上执行证明；身份换名不另算一个 Agent |
| [Brain On BNB](https://brainonbnb.com/services)，BSC #49467 | 固定区块直接核实注册存在；保留官方服务说明与 434 条公开 burn 日志；抽查一笔真实历史销毁交易 | 抽查交易使用旧执行地址和不同代币，不能直接归给当前身份。需要迁移/绑定证明；不把同项目 DeFi 历史移给它。免费业务正确性尚未评价 |
| [Brain DeFi](https://brainonbnb.com/defi)，BSC #363709 | 免费 `lp/look?position=7637521` 返回仓位数据；注册持有人、公开执行记录、查询 owner 与历史交易 sender 一致。真实核验一条增仓调用及同目标、同仓位事件 | 查询不支持固定区块，尚无动态结果的独立对照；还需预先固定抽样规则并扩大可归属历史样本。一条增仓步骤不等于整次任务完成或整体可靠性。与 #49467 同一提供方 |

## 保留的资料线索，尚未调用业务或 RPC

| 提供方 | 官方来源与拟评业务 | 决定性缺项与下一步 |
| --- | --- | --- |
| b1e55ed，Base #28362 | [介绍](https://docs.b1e55ed.permanentupperclass.com/introduction)、[作者仓库](https://github.com/P-U-C/b1e55ed)、[官网](https://b1e55ed.permanentupperclass.com/)公开匿名 provenance 查询 | 官方明确仓位是模拟盘，不能计入真实交易。若评价链上 karma 写入，需实际签名者、信号与具体交易关联；捐赠钱包不能代替执行钱包 |
| Clawlinker / Molttail，Ethereum #22945 | [身份 manifest](https://github.com/clawlinker/synthesis-hackathon/blob/main/agent.json)、[公开接口声明](https://github.com/clawlinker/synthesis-hackathon/blob/main/public/.well-known/agent.json)、[receipt 路由](https://github.com/clawlinker/synthesis-hackathon/blob/main/app/api/receipts/route.ts)声明匿名 receipt 查询与执行钱包 | 尚未直接核实注册绑定。receipt 错误/超时路径会返回 sample；[ENS 路由](https://github.com/clawlinker/synthesis-hackathon/blob/main/app/api/ens-resolver/route.ts)对合法名称返回固定记录，contenthash 是 placeholder，不能据源码声称已通过实时解析。执行日志的支付日期与缓存交易日期不对应，尚无完整任务归属链。需检查实际响应并排除演示数据 |
| ACK / Etch | [ACK 注册说明](https://gist.github.com/tyler-james-bridges/cc80c2eee531a02a29370f931de90c5d)、[Etch 作者仓库](https://github.com/tyler-james-bridges/etch)公开免费存证 verify 与合约 | ACK 的多个注册身份不能自动转给 Etch。需要注册 metadata 到 Etch 服务的绑定、真实 minter 与历史存证任务；当前不计为已确定身份候选 |

这些线索按提供方记录，不将多个链上的同一服务重复计数。源码和文档描述不冒充已部署服务的实际表现。

## 本轮证据定位

所有目录均在本项目 `runtime/` 中，未复制旧项目证据，也未进入 Git：

- `candidate-check-20261017T175652Z-f876ebbc`：9 次请求，发现资料、资产查询、Arena 查询和 4 条目录记录。
- `candidate-check-20261017T180114Z-bc374bd3`：4 次请求，DeFi 官方页、执行记录、burn 日志和 #363709 目录。
- `candidate-check-20261017T180531Z-40968620`：1 次免费仓位查询。
- `bsc-check-20261017T180807Z-79c769b9`：10 次固定可信 BSC 读取，含链号、固定区块、注册、两笔历史交易及回执。
- `defi-step-20261017T181209Z-f4925047`：2 次必要补充读取。首笔 DeFi 交易只是包装 BNB，另查公开记录中实际增仓的最后一步。
- `admission-report-20261017T182038Z-f504c54e`：汇总 26 条原始观测的新报告，输入摘要全部匹配，0 个输入问题；中间报告保留，不覆盖。

固定区块为 BSC **128215589**，哈希 `0x410de9f8a26b1273815e92e102e8eea4a66a74d7817c49e04ff5e536658e1ec8`。DeFi 增仓交易为 `0xceda861374ea49e79034c23812c90d6d98b2ce0a7d17ea2f1abfb5aa2881f644`，实际区块 128169298；目标为[官方列出的仓位管理合约](https://developer.pancakeswap.finance/contracts/v3/addresses)。先核实参数、执行者、目标、回执、事件、确认距离与历史时间关联，再表述为“一条可归属步骤”。

Brain DeFi 的[公开路由](https://github.com/mmxrealQQ/bobai-buyburn/blob/main/worker-agent/index.js)只接受仓位/钱包；[读取实现](https://github.com/mmxrealQQ/bobai-buyburn/blob/main/shared/lp-agent.js)未固定 block。不能额外传一个未支持的 `block` 参数就声称解决对照。不可变字段可另设有限子判据，但不能替代费用、流动性、区间与估值等动态功能的充分核验。

本轮请求均为资料、免费只读业务或链上读取；HTTP 200 只表示采集取得响应。历史样本为可行性调查选择，未固定正式评分样本，不计算成功率或分数。后续评分须在正式采样前固定标准，不因结果高低换对象，也不将缺资料、缺授权或未适配统一扣分。
