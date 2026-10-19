# 真实公共 Agent 候选与扩展记录

更新日期：2026-10-18。当前完整评分、报告数及进行中的任务统一见[STATUS](../STATUS.md)。下表保留各次调查时的声明、实查和后续线索，不能用旧缺项代替新报告，也不把线索计为就绪；跨提供方业务复用仍未证明。

## 已实际检查的候选

| 候选 | 本轮已取得的事实 | 当前缺口与后续动作 |
| --- | --- | --- |
| [DegenAI](https://degenai.dev/erc8004)，Ethereum #23121 | 能力发现列出操作与价格；免费 BTC 资产查询返回成功及 2 条资产资料。ERC-8183 发现结果明确 `contractDeployed=false`，执行者、任务合约、核验者为空 | 身份尚未直接查链；用 HyperLiquid 官方资料核对资产字段及缓存口径，另找可归属执行记录。未部署的这条任务线不能提供履约证据，不推断其所有功能都未部署 |
| [Agent Arena](https://agentarena.site/)，Base #18500 | 实际查询返回 HTTP 200，但 name/description 为空、services=[]，与保留目录存在差异 | 固定同一身份读取链上 agentURI 与文件，查清来源/缓存差异；尚不能直接判业务失败。被查询对象的交易不归给 Arena |
| [DARKSOL / Synthesis](https://github.com/darks0l/synthesis-agent)，Base #31929 | 目录与作者仓库指向同一身份；作者仓库有执行钱包和交易线索，但仪表盘为 localhost | 当前 API 的免费与证明条件未闭合；公开文档读取曾遇到 402，已停止该主机，不调用付费路径。随机数 demo 不等于实际链上执行证明；身份换名不另算一个 Agent |
| [Brain On BNB](https://brainonbnb.com/services)，BSC #49467 | 固定区块直接核实注册存在；保留官方服务说明与 434 条公开 burn 日志；抽查一笔真实历史销毁交易 | 抽查交易使用旧执行地址和不同代币，不能直接归给当前身份。需要迁移/绑定证明；不把同项目 DeFi 历史移给它。免费业务正确性尚未评价 |
| [Brain DeFi](https://brainonbnb.com/defi)，BSC #363709 | 历史增仓窄范围 COMPLETE：首次 88.89 / 100 / 100、综合 96.67；正式接入复评 93.09 / 100 / 100、综合 97.93。每份 24 个真实槽位，13 条 N_A 另列。注册事件内 Operating wallet 与 record 接口、真实执行者、固定块仓位所有权及三步交易均已核对 | 第二报告重新采集可用性、复用未变历史，不算新对象。仅覆盖记录入口、7 条披露和另 7 条三步行为；实时 `lp/look` 未固定 block，收益与完整策略不在结论内。与 #49467 同一提供方，不能冒充独立提供方复用 |

## 后续扩展线索与实际核实状态

| 提供方 | 官方来源与拟评业务 | 决定性缺项与下一步 |
| --- | --- | --- |
| b1e55ed，Base #28362 | [介绍](https://docs.b1e55ed.permanentupperclass.com/introduction)、[作者仓库](https://github.com/P-U-C/b1e55ed)、[官网](https://b1e55ed.permanentupperclass.com/)公开匿名 provenance 查询 | 官方明确仓位是模拟盘，不能计入真实交易。若评价链上 karma 写入，需实际签名者、信号与具体交易关联；捐赠钱包不能代替执行钱包 |
| Clawlinker / Molttail，Ethereum #22945 | [身份 manifest](https://github.com/clawlinker/synthesis-hackathon/blob/main/agent.json)、[公开接口声明](https://github.com/clawlinker/synthesis-hackathon/blob/main/public/.well-known/agent.json)、[receipt 路由](https://github.com/clawlinker/synthesis-hackathon/blob/main/app/api/receipts/route.ts)声明匿名 receipt 查询与执行钱包 | 尚未直接核实注册绑定。receipt 错误/超时路径会返回 sample；[ENS 路由](https://github.com/clawlinker/synthesis-hackathon/blob/main/app/api/ens-resolver/route.ts)对合法名称返回固定记录，contenthash 是 placeholder，不能据源码声称已通过实时解析。执行日志的支付日期与缓存交易日期不对应，尚无完整任务归属链。需检查实际响应并排除演示数据 |
| ACK / Etch | [ACK 注册说明](https://gist.github.com/tyler-james-bridges/cc80c2eee531a02a29370f931de90c5d)、[Etch 作者仓库](https://github.com/tyler-james-bridges/etch)公开免费存证 verify 与合约 | ACK 的多个注册身份不能自动转给 Etch。需要注册 metadata 到 Etch 服务的绑定、真实 minter 与历史存证任务；当前不计为已确定身份候选 |
| Custos，作者 0xMaxyz | [本轮调研](CANDIDATE_RESEARCH_20261018.md)记录作者部署资料、拟核实的 Mantle #128 身份、匿名 `/snapshot` 与 `/decisions` 路由及决策事件设计；两个官方只读入口各尝试一次，均 ReadTimeout、未取得 HTTP 状态 | 网络失败 UNKNOWN，不判 Agent 失败、不重试凑样本。尚缺注册、ALLOCATOR 关联和真实决策原件；deployer 不能当执行者。原件 `runtime/candidate-check-20261018T053927Z-27b8ade9/` |
| Olas Valory Mech Predict，Gnosis #2182 线索 | 固定块注册、bridger 的服务号→注册号映射、实际 operator 与一条旧请求/交付原件已取得；owner 是 bridger，不能当执行钱包。真实预测目标日尚未到，不能判准确；见[本轮调研](CANDIDATE_RESEARCH_20261018.md) | 继续核较早已结算任务、CID/DAG、历史 operator 与接手规则。原优先 Mech 和实际交付者分开，不复用 analytics accuracy，多个 tool 不算多个 Agent，不发付费新任务 |
| delu，Base #30004 | 目录和固定块注册已读取；链上 dataURI 的服务列表为空。作者仓库提供一条带输入/输出和 txHash 的 MOLT 兑换记录，见[扩展调查](CANDIDATE_EXPANSION_20261018.md) | 作者项目到注册服务及实际执行钱包的关联未闭合，且不足量任务；dashboard 源码有 mock fallback，不能以页面 200 或新时间戳判实时服务正常 |
| Clicks Protocol，Base #45074 | 固定块注册→实际注册 JSON→MCP 文档和远程四工具列表已核；一次匿名分账预览 HTTP200 但业务 `isError=true`，上游 RPC 额度不足，无结果 | 停止该入口后续请求；没有固定块查询支持或可归属的足量结算任务。bootstrap attestation 对象是 Agent #1，不是本 Agent。保留缺项与原件，未计分 |

这些线索按提供方记录，不将多个链上的同一服务重复计数。源码和文档描述不冒充已部署服务的实际表现。

## 已完成的首个限定范围评分

最新[中文详细报告](../runtime/evaluation-report-20261018T060340Z-4c27cea3/report.html)与 JSON、manifest、background 位于 `runtime/evaluation-report-20261018T060340Z-4c27cea3/`，由正式 API 任务及 worker 自动发布，综合 97.93。首轮 `runtime/evaluation-report-20261018T053613Z-fe5237bc/` 与更早排版版保留；同一对象多份报告不增加对象数。

该增仓报告24槽为10次新访问、7条披露、另7条行为；13条无动作记录为背景NOT_APPLICABLE。可用性差异来自实际耗时，功能/行为未人为扣分。后续已完成两对象预测复用及通用接入/履约；下一任务 `GENERIC_FUNCTIONAL_EVIDENCE` 路线待对齐，至少10个和跨提供方业务复用仍未完成。

Git为 `codex/local-platform`，提交记录以 `git log` 及STATUS为准；`REMOTE_NOT_CONFIGURED`，未push或创建PR。

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
