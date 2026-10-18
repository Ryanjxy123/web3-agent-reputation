# 真实公共 Agent 候选与扩展记录

更新日期：2026-10-18。首批 5 个候选已实查，既有 3 个提供方线索及新的 Custos 调查记录继续保留。Brain DeFi 的历史增仓窄范围已完成 10+7+7 个真实槽位的三维分和综合分，当前为 1 / 至少 10 个对象，不代表整个 Agent 的能力。第二个独立提供方的同类复用尚未完成，Custos 不计为已就绪。

## 已实际检查的候选

| 候选 | 本轮已取得的事实 | 当前缺口与后续动作 |
| --- | --- | --- |
| [DegenAI](https://degenai.dev/erc8004)，Ethereum #23121 | 能力发现列出操作与价格；免费 BTC 资产查询返回成功及 2 条资产资料。ERC-8183 发现结果明确 `contractDeployed=false`，执行者、任务合约、核验者为空 | 身份尚未直接查链；用 HyperLiquid 官方资料核对资产字段及缓存口径，另找可归属执行记录。未部署的这条任务线不能提供履约证据，不推断其所有功能都未部署 |
| [Agent Arena](https://agentarena.site/)，Base #18500 | 实际查询返回 HTTP 200，但 name/description 为空、services=[]，与保留目录存在差异 | 固定同一身份读取链上 agentURI 与文件，查清来源/缓存差异；尚不能直接判业务失败。被查询对象的交易不归给 Arena |
| [DARKSOL / Synthesis](https://github.com/darks0l/synthesis-agent)，Base #31929 | 目录与作者仓库指向同一身份；作者仓库有执行钱包和交易线索，但仪表盘为 localhost | 当前 API 的免费与证明条件未闭合；公开文档读取曾遇到 402，已停止该主机，不调用付费路径。随机数 demo 不等于实际链上执行证明；身份换名不另算一个 Agent |
| [Brain On BNB](https://brainonbnb.com/services)，BSC #49467 | 固定区块直接核实注册存在；保留官方服务说明与 434 条公开 burn 日志；抽查一笔真实历史销毁交易 | 抽查交易使用旧执行地址和不同代币，不能直接归给当前身份。需要迁移/绑定证明；不把同项目 DeFi 历史移给它。免费业务正确性尚未评价 |
| [Brain DeFi](https://brainonbnb.com/defi)，BSC #363709 | 历史增仓窄范围 COMPLETE：可用性 88.89、功能一致性 100、交易可靠性 100，综合 96.67；24 个真实槽位，13 条 N_A 另列。注册事件内 Operating wallet 与 record 接口、真实执行者、固定块仓位所有权及三步交易均已核对 | 仅覆盖记录入口、7 条披露和另 7 条三步行为；实时 `lp/look` 未固定 block，收益与完整策略不在结论内。与 #49467 同一提供方，不能用两身份冒充独立提供方复用 |

## 保留的资料线索，尚未调用业务或 RPC

| 提供方 | 官方来源与拟评业务 | 决定性缺项与下一步 |
| --- | --- | --- |
| b1e55ed，Base #28362 | [介绍](https://docs.b1e55ed.permanentupperclass.com/introduction)、[作者仓库](https://github.com/P-U-C/b1e55ed)、[官网](https://b1e55ed.permanentupperclass.com/)公开匿名 provenance 查询 | 官方明确仓位是模拟盘，不能计入真实交易。若评价链上 karma 写入，需实际签名者、信号与具体交易关联；捐赠钱包不能代替执行钱包 |
| Clawlinker / Molttail，Ethereum #22945 | [身份 manifest](https://github.com/clawlinker/synthesis-hackathon/blob/main/agent.json)、[公开接口声明](https://github.com/clawlinker/synthesis-hackathon/blob/main/public/.well-known/agent.json)、[receipt 路由](https://github.com/clawlinker/synthesis-hackathon/blob/main/app/api/receipts/route.ts)声明匿名 receipt 查询与执行钱包 | 尚未直接核实注册绑定。receipt 错误/超时路径会返回 sample；[ENS 路由](https://github.com/clawlinker/synthesis-hackathon/blob/main/app/api/ens-resolver/route.ts)对合法名称返回固定记录，contenthash 是 placeholder，不能据源码声称已通过实时解析。执行日志的支付日期与缓存交易日期不对应，尚无完整任务归属链。需检查实际响应并排除演示数据 |
| ACK / Etch | [ACK 注册说明](https://gist.github.com/tyler-james-bridges/cc80c2eee531a02a29370f931de90c5d)、[Etch 作者仓库](https://github.com/tyler-james-bridges/etch)公开免费存证 verify 与合约 | ACK 的多个注册身份不能自动转给 Etch。需要注册 metadata 到 Etch 服务的绑定、真实 minter 与历史存证任务；当前不计为已确定身份候选 |
| Custos，作者 0xMaxyz | [本轮调研](CANDIDATE_RESEARCH_20261018.md)记录作者部署资料、拟核实的 Mantle #128 身份、匿名 `/snapshot` 与 `/decisions` 路由及决策事件设计 | 尚未独立核验注册、实际匿名服务、ALLOCATOR 执行关联或真实任务证据；deployer 不能当执行者。优先核实资料，不计为可评分或第二提供方复用已通过 |

这些线索按提供方记录，不将多个链上的同一服务重复计数。源码和文档描述不冒充已部署服务的实际表现。

## 已完成的首个限定范围评分

最新[中文详细报告](../runtime/evaluation-report-20261018T053613Z-fe5237bc/report.html)与 JSON、manifest、background 位于 `runtime/evaluation-report-20261018T053613Z-fe5237bc/`。首次版本 `runtime/evaluation-report-20261018T053426Z-ba06f389/` 保留；两次离线生成均退出 0，新版复用原件并改善普通用户读法，分数相同。

24 个评分槽位固定为 10 次新可用性访问、7 条功能披露、7 条不同运行的行为任务；13 条无动作记录为背景 NOT_APPLICABLE，不进入七任务分母。可用性的非满分来自实际访问耗时，未对真实全通过的功能或行为人为扣分。`MODEL_PILOT`、`FIRST_EVIDENCE_LOOP` 已完成；接下来验证独立提供方复用并建设 `LOCAL_PLATFORM`，完整网站、API、worker 和 PostgreSQL 尚未实现。

Git 为 `codex/model-evidence-loop`，实现已本地提交 `2b71d65`；本轮状态文档随后提交，以 `git log` 为准。`REMOTE_NOT_CONFIGURED`，未 push 或创建 PR。

## 首批证据定位

所有目录均在本项目 `runtime/` 中，未复制旧项目证据，也未进入 Git：

- `candidate-check-20261017T175652Z-f876ebbc`：9 次请求，发现资料、资产查询、Arena 查询和 4 条目录记录。
- `candidate-check-20261017T180114Z-bc374bd3`：4 次请求，DeFi 官方页、执行记录、burn 日志和 #363709 目录。
- `candidate-check-20261017T180531Z-40968620`：1 次免费仓位查询。
- `bsc-check-20261017T180807Z-79c769b9`：10 次固定可信 BSC 读取，含链号、固定区块、注册、两笔历史交易及回执。
- `defi-step-20261017T181209Z-f4925047`：2 次必要补充读取。首笔 DeFi 交易只是包装 BNB，另查公开记录中实际增仓的最后一步。
- `admission-report-20261017T182038Z-f504c54e`：汇总 26 条原始观测的新报告，输入摘要全部匹配，0 个输入问题；中间报告保留，不覆盖。

固定区块为 BSC **128215589**，哈希 `0x410de9f8a26b1273815e92e102e8eea4a66a74d7817c49e04ff5e536658e1ec8`。DeFi 增仓交易为 `0xceda861374ea49e79034c23812c90d6d98b2ce0a7d17ea2f1abfb5aa2881f644`，实际区块 128169298；目标为[官方列出的仓位管理合约](https://developer.pancakeswap.finance/contracts/v3/addresses)。先核实参数、执行者、目标、回执、事件、确认距离与历史时间关联，再表述为“一条可归属步骤”。

Brain DeFi 的[公开路由](https://github.com/mmxrealQQ/bobai-buyburn/blob/main/worker-agent/index.js)只接受仓位/钱包；[读取实现](https://github.com/mmxrealQQ/bobai-buyburn/blob/main/shared/lp-agent.js)未固定 block。不能额外传一个未支持的 `block` 参数就声称解决对照。不可变字段可另设有限子判据，但不能替代费用、流动性、区间与估值等动态功能的充分核验。

首批请求均为资料、免费只读业务或链上读取；HTTP 200 只表示采集取得响应。首批可行性样本没有据此计算分数；后续已按 ADR-0004 冻结正式范围和分组，不因结果高低换对象，缺资料、缺授权或未适配不统一扣分。新采集位置、失败与定向补齐见 [本轮运行记录](../docs/runbooks/MODEL_EVIDENCE_LOOP.md)。

## 同提供方专业 Agent 的后续核实

官方 [own-agents.mjs](https://github.com/mmxrealQQ/bobai-buyburn/blob/8945284edb68562f75fce328977cec1fcb4cce69/scripts/lib/own-agents.mjs) 列出 Health #302257、Grid #302258、Yield #304493、Rebalancer #304494、LP Placement #310460 的独立身份和接口。共享收款/服务提供方不代表每笔任务都能直接归给某一身份，不计为不同提供方复用证明。

已通过固定 GET 保留 Health 56657、Grid 56670、Yield 56850 三份实际结果，均 HTTP 200。它们缺原始任务文本和固定链上输入，尚未独立核验：Health 是运营者自测；Grid 的输出对象可能与原始请求不同，须取得原始 description 后判断；Yield 缺原始逐市场利率和统一固定块。结果文件不自带已核实的链上交付摘要，不能把作者日志的一致哈希当独立链证明。

三份原件在 `runtime/candidate-check-20261018T050732Z-5acb2765/`，没有调用新付费任务。无法评分的缺项继续保留，尚未计入完整评分目标。
