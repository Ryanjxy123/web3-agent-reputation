# 真实 Agent 与首个能力 Checker 候选调查

调查日期：2026-10-19。阶段为只读资料调查；本文件不新增评价政策，不把声明、协议发现或目录评分当作业务正确性证据。

## 本轮结论

已整理 **20 个完整注册身份**，覆盖 Ethereum、BNB、Gnosis、Base、Arbitrum、Celo 六条链的多个真实项目线索。项目名、owner、域名仅是提供方线索，没有据此认证独立提供方数量。适合优先研究的是确定性查询；仍未证明两个不同提供方同时满足可信注册绑定、免费无副作用调用、完整输入输出和独立 oracle，不能宣称已完成可复用 Query Checker 的真实验收。

最有希望的三个方向：

1. **Brain On BNB AI #49467**：真实 MCP 发现了任意 BSC token/pool/position 查询及自币元数据查询；免费范围有原文，链数据可独立 RPC 对照。缺口是可信链上 tokenURI 与当前服务绑定、源码审查、时间/区块一致的输出和实际业务样本。
2. **DegenAI #23121**：真实 x402 discovery 列出零价格 `get_available_assets`、历史成交、仓位等查询。资产符号/静态交易参数可能对照独立 Hyperliquid 官方 meta；动态价格不能直接与另一个时间的结果比较。缺口是可信 Ethereum 注册读取、匿名鉴权条件及返回字段核实。
3. **Agent Arena #18500**：真实 MCP 的 `get_agent_profile(chainId, agentId)` 明示免费。选取 profile 中注册名称、服务端点等可与可信 registry/tokenURI 原件对照；平台已有 reputation 数值不是独立正确性 oracle。缺口是源码审查、可信注册绑定、缓存/更新时间及实际返回字段。其业务是登记资料查询，不与 ERC20 查询混为同一语义判据；可共享受控工具执行和证据框架，能力适配仍应分开。

**Clawdia 的 Routing 尚不适合自动业务执行**：真实 `route_task` 只有任务描述和可选 credits budget，没有 dry-run、候选集合限制、禁止转委托或固定预期结果。不能因目录自报 Free 或预算填 0 就判断没有费用和外部副作用。

## 来源与本轮范围

优先阅读并复用：

- `AGENTS.md`、`PLAN.md`、`STATUS.md`。
- `docs/reviews/AGENT_EVALUATION_ARCHITECTURE_AUDIT.md`、`docs/runbooks/HISTORICAL_EVALUATION_AND_AGENT2290_20261019.md`。
- `reference/CAPABILITY_COVERAGE_DECISION_20261018.md`、`CAPABILITY_CORPUS_20261018.md`、`CAPABILITY_CORPUS_SEMANTICS_20261018.md`。
- `configs/corpus-semantic-review-20261018.json`、`configs/inventory-semantic-review-20261018.json`、`configs/candidate-reviews-20261018.json`。
- `scripts/collect_capability_corpus.py`、`scripts/check_candidates.py`、`services/platform/src/reputation_platform/public_targets.py`、`safe_http.py`、`protocol_evaluation.py`。

旧群体统计为 554 索引/109 详情/72 接口声明；**本机没有旧 `runtime/capability-corpus-*` 原件目录**，配置中的旧引文/SHA只用于选线索，不能当本轮重新核实的原件。公开评分包中的历史报告与 Clawdia 20261019 原件实际存在，可复用但必须按其范围解释。

本轮新原件全部保留在 `runtime/checker-candidate-research-20261019/`：

- 根目录 `registration-<chain>-<id>.response.bin` 和同名 observation：16 个登记详情请求，14 个完整 HTTP200；Base #1、Arbitrum #1 已收到 HTTP200，但响应体总超时，不能解析为完整资料。没有重试。
- `protocol-brain/`：skill.md、A2A Card、initialize、tools/list，4 个完整 HTTP200。
- `protocol-other/`：Loopuman MCP descriptor、Arena tools/list、Degen x402 discovery、Brain GitHub tree，4 个完整 HTTP200；DARKSOL OpenAPI 1 次 ConnectError；另 Degen 登记详情 1 个完整 HTTP200。
- 共 **26 份实际观测、23 个完整 HTTP200、2 个响应体超时、1 个连接失败**。初始目录计划 17 项，在第5项后改为最多3并发；保守排除可能正在途中的 Credora #31793，不重新发该请求，**整个采集请求上限27**。manifest 和 parallel-continuation.json 保留该调整。
- 全程使用现有 `SafeHttpClient(pin_public_dns=True)`、固定 HTTPS 目标、当前代理、每请求20秒/1 MiB、无重试/重定向；最大3并发。0 `tools/call`、0 A2A业务任务、0新建历史任务、0 RPC、0模型、0支付/签名/交易、0 Worker改变。网络/权限资料缺口不记 Agent FAIL。

Brain GitHub tree 是 `https://api.github.com/repos/mmxrealQQ/bobai-buyburn/git/trees/main?recursive=1` 的公开只读响应，commit `d90dc1a1fd899404a90c619447820551abd48655`，`truncated=false`。目录仅用于定位源码，不执行其中代码或指令。具体源码审查由另一调查线继续。

## 20 个候选身份与条件

下表注册合约统一为 `0x8004a169fb4a3325136eb29fa0ceb6d2e539a432`。`链/ID` 与该合约共同构成完整身份；“当前目录”指本轮官方 `https://api.8004scan.io/api/v1/agents/<chain>/<id>` 原件，仍不是独立链认证。免费/协议等是有出处的服务声明，不是已完成业务验证。

| 链/ID · 名称/提供方线索 | 具体能力、真实端点/协议 | 免费、鉴权和副作用条件 | 历史与独立判据可得性、当前判断 |
| --- | --- | --- | --- |
| **56/49467 Brain On BNB AI** · Brain On BNB AI（Card署名） | Query：`https://brainonbnb.com/mcp`；A2A `https://brainonbnb.com/.well-known/agent-card.json`；token/pool/钱包/position/登记资料查询；Routing另有 `/dispatch` | Card和skill明示查询免费无key；pool scan每日50次后需pass。`bsc_rug_watch`注册webhook有副作用；`watch`收费；均排除。只读属性不能单独作安全证明 | 链RPC可核token/position/烧毁tx；公开 burns/session history可查但尚未业务采集。优先候选；本轮目录+4协议资料完整，尚缺可信tokenURI/业务输出 |
| **1/23121 DegenAI** · DegenAI/ACP | Query与交易：`https://degenai.dev/x402`；登记A2A为`virtuals://degenai`，不是普通HTTP A2A | 实际discovery列零价资产/成交/余额；部分wallet从x402 auth context取得。交易、automation、收费图表排除；零价不自动等于无鉴权 | 官方Hyperliquid meta/fills可作独立对照，但需同条件和时间；旧候选记录曾取得免费BTC资产结果。本轮discovery和登记完整；未查可信Ethereum tokenURI |
| **8453/18500 Agent Arena** · Agent Arena | Query：MCP `https://agentarena.site/api/mcp`；A2A `/api/a2a`；`get_agent_profile` | 真实工具描述profile免费；`search_agents`现为$0.005 USDC，登记描述仍$0.001，保留差异；register为$0.05且链写入，均不调用 | profile注册字段可对独立RPC+tokenURI；已有reputation不能当oracle。当前目录+tools/list完整；需源码及缓存条件，未业务调用 |
| **8453/45074 Clicks Protocol** · clicks-protocol | Query：注册URI `https://clicksprotocol.xyz/.well-known/agent-registration.json`；descriptor `/mcp/server.json`，远程 `https://mcp.clicksprotocol.xyz/mcp`；分账/收益/推荐关系 | 旧资料匿名initialize/tools/list成功，但分账业务isError上游RPC用量限制。**本轮没有重试或换入口绕过限额** | 旧固定块注册已核；业务响应未锚定block，oracle不成立。本轮只重取目录；待服务/固定状态条件恢复 |
| **8453/2290 Clawdia** · ClawPlaza | Routing/Workflow/Chat；MCP `https://work.clawplaza.ai/mcp/clawdia`；A2A `/agents/clawdia/.well-known/agent-card.json` | 目录Free/x402=false仅自报；route_task budget是credits，无安全dry-run。Chat及路由均未执行 | 已有真实PARTIAL A90.87，F/B缺项；链注册读取通过但IPFS原件超时。原tools/list可复用。编排缺独立期望、执行归属及完成记录，不启动正式Routing评分 |
| **8453/1 ClawNews** · 项目名线索，未证提供方独立 | Query/社区：新闻、Agent目录、登记身份核验；具体端点本轮未取得完整响应 | 旧语义资料仅声明API-first，没有建立匿名免费业务许可；社区动作可能写入 | 本轮目录body timeout；旧语义条目007有出处。注册核验可考虑RPC oracle，先取得完整规范；不把同一项目多链登记当多提供方 |
| **42161/1 ClawSearch** · 项目名线索 | Query：Agent/工具语义检索、能力匹配、身份核验；旧文档GET仅SPA外壳 | 无已确认免费工具schema；检索主观匹配缺固定真值 | 本轮目录body timeout；旧语义条目026。与ClawNews可能相关，不能算已证两独立提供方；先取正式API规范 |
| **8453/31929 DARKSOL** · DARKSOL | Query/Commerce：`https://acp.darksol.net/openapi.json`；目录原文另列 `/mcp`、`/.well-known/agent-card.json`、oracle随机数/receipt/支出策略 | 随机oracle付费x402，10M持币者需签名免费；卡订单/交易/协商外部副作用排除 | oracle可核VRF但需任务绑定/公开历史。目录完整，OpenAPI ConnectError；未绕过、未业务调用 |
| **42220/17 Loopuman** · Loopuman | Routing/人工任务：`https://api.loopuman.com/.well-known/mcp.json`；A2A Card同域；translation/labeling/verification | 实际descriptor鉴权bearer或x402；post_task预算VAE、ask_human会委托真人；register_worker写入。均禁自动执行 | get_task_status需既有task_id；任务输入、雇佣/交付/质量历史尚缺；不适合第一种只读事实Query |
| **42220/7 MyDay Guardian** · 项目名线索 | Query/行为分析/质押：`https://myday-guardian-production.up.railway.app/api/v1/discipline-score/{telegram_id}`、`/api/v1/agent` | 普通score是否公开授权未知；premium 0.01cUSD、stake 0.10；humanity handshake及payment verify会改变状态，排除 | 原文含明确returns但telegram个人数据及行为输入不公开，缺独立oracle。目录tools完整；不访问他人ID |
| **1/31778 adaidaran（DataAnalyst Pro）** · 产品名线索 | Query/开放分析：`https://api.dataanalystpro.ai/mcp`；CSV/JSON/SQL统计、可视化、报告 | 注册描述pay-per-use/subscription；schema/匿名免费条件未核。上传数据和SQL操作范围未知 | 可以构造有明确算术答案的数据，但需安全上传/调用许可与完整schema。本轮目录完整，未发现真实工具 |
| **1/6817 Otto AI - Market Alpha Agent** · useOttoAI | Query/Open-ended：A2A `https://useotto.xyz/.well-known/a2a/market-alpha-agent.json`，x402 `https://x402.ottoai.services`，ACP | x402/ACP服务，无已证匿名免费调用；自然语言建议不是确定性真值 | 市场新闻/情绪/建议需出处、时间窗和业务oracle，不能用另一个LLM打可信F。本轮仅目录完整 |
| **1/31808 SmartFlow Signal API** · SmartFlow/Onchainintel（自述） | Query/警报：`https://api.smartflowproai.com `（原件尾空格保留，不自动改写调用）；OASF通用URL非业务API | 自述x402 $0.02–0.10/call；不得调用付费数据feed | 实时token score/鲸鱼alert须历史事件与窗口。当前只具目录描述，未取业务schema |
| **8453/38326 Atlas** · Syntrophic | Query：ERC8004元数据索引/关系图，`https://syntrophic.md/agents/syntrophic-agent-223-atlas` | 只有web资料，无已确认业务schema和免费条件 | 名称#233与URL223不一致，不擅自纠正身份；本轮目录完整。可核登记字段，关系图暂无独立真值 |
| **8453/38351 3Jane** · Applied Identities（注册声明） | Query/开放报告：`https://vi.appliedidentities.com/api/v1/verify/chain/3jane`；报告目录 `https://research.appliedidentities.com/x402/.well-known/x402` | 研究出版物x402收费；verification公开可达性/授权未核 | “治理链完整”需公开签名、根信任和原件，不能信任自报valid。本轮目录完整，未取verification结果 |
| **42161/16 Chain Oracle** · 未知 | Query/警报：on-chain feed/whale/sentiment；当前注册缓存没有services | 无端点、无schema、鉴权费用未知 | 链数据理论可oracle，但同一对象没有可用接口，不能与别家接口拼接M。目录完整；UNSUPPORTED/NEEDS_INFO候选 |
| **42161/22 Rug Pull Detector** · 未知 | Query/风险分析：liquidity lock/ownership renouncement；当前注册缓存没有services | 无端点、安全免费条件未知 | owner/lock可独立链核，但红旗综合分析未给定义；目录完整；不能因名字就匹配Brain工具 |
| **56/363709 Brain DeFi** · 与#49467同提供方 | DeFi/历史履约：`https://agent.brainonbnb.com/lp/agent`、`/defi-agent/a2a` | 新任务$0.10且资产/付费边界；只复用已公开历史，不新发交易 | 原完整增仓报告及独立链证据可复用，是已证特例；不能当第二独立提供方或泛化Query证明 |
| **100/2182 Olas Valory Mech Predict** · Olas/Mech生态 | Prediction/历史履约：`https://marketplace.olas.network/api/erc8004/gnosis/ai-agents/2182`、IPFS任务输入输出 | 新任务需签名付款；历史GET可读；不新建任务 | 现有prediction-history-v1成熟判据与正式历史评分可复用；不以预测工具里的检索阶段当独立Query能力 |
| **1/31793 Credora credit ratings** · Credora声明线索 | Query：DeFi vault rating/PSL/publish_date；旧语义条目003 | 本轮保守跳过可能在途的第6次目录请求，未重试；服务端点/鉴权未知 | 评级是提供方产生的业务数据，缺独立可重建判据；不能拿相同Credora评级接口自证。保留候选，不计本轮已取详情 |

> 上述共20个身份，真实可测性不按表格行数计。Brain DeFi与Brain Plaza是同提供方，ClawNews/ClawSearch也未证明独立。调查来源覆盖与正式业务完成覆盖分别统计。

## 真实工具输入及适配边界

工具Schema来自原始协议发现，而不是按名称猜测。所有结果先审查文档/源码/状态/费用，不能让任意外部Schema决定平台执行权限。

### Brain MCP（本轮完整tools/list）

```json
{"name":"bobai_token_info","inputSchema":{"type":"object","properties":{},"additionalProperties":false}}
{"name":"bobai_wallet_balance","inputSchema":{"type":"object","properties":{"address":{"type":"string","description":"BSC wallet address (0x + 40 hex chars)"}},"required":["address"],"additionalProperties":false}}
{"name":"bsc_token_preflight","inputSchema":{"type":"object","properties":{"address":{"type":"string","description":"A BSC token address, a pool/pair address, or a link containing one"},"usd":{"type":"number","description":"Trade size in dollars, optional - defaults to 250"}},"required":["address"],"additionalProperties":false}}
{"name":"pancakeswap_position_look","inputSchema":{"type":"object","properties":{"position":{"type":"string","description":"A PancakeSwap V3 position id (the NFT token id), digits only"},"address":{"type":"string","description":"Or a wallet address that holds the position"}},"additionalProperties":false}}
```

`bobai_token_info`不能指定其他token/chain。其他查询也没有指定固定区块的参数。若只核name/symbol/decimals等静态项，必须证明该项和实现确实可重复；供应量、价格、仓位、tax/LP状态不得用另一时刻/另一块的值直接判FAIL。`bsc_token_preflight`会聚合链查询、模拟和GoPlus部分缓存（最多6h），其stop/caution语义比ERC20元数据复杂，不适合首轮无依据扩成通用“安全币判据”。

### Degen x402 discovery（本轮完整响应）

```json
{"id":"get_available_assets","inputSchema":{"type":"object","properties":{"filter":{"type":"string","description":"Optional filter by asset symbol prefix","example":"BTC"}},"required":[]},"pricing":{"scheme":"exact","basePrice":0,"currency":"USDC"}}
{"id":"get_trade_history","inputSchema":{"type":"object","properties":{"wallet":{"type":"string"},"limit":{"type":"number"}},"required":["wallet"]},"pricing":{"scheme":"exact","basePrice":0,"currency":"USDC"}}
```

以上为原Schema的字段投影，完整description/pricing说明仍以response.bin为准。资产业务不是预测；零价格不消除鉴权要求。不能用一次返回BTC价格证明全体资产/全部交易能力。

### Arena MCP（本轮完整tools/list）

```json
{"name":"get_agent_profile","description":"Retrieve the full profile of a specific agent by their on-chain ID. Returns name, description, endpoints, reputation, reviews, and cross-chain presence. Free endpoint.","inputSchema":{"type":"object","properties":{"chainId":{"type":"number","description":"Chain ID where the agent is registered (e.g. 8453 for Base)"},"agentId":{"type":"string","description":"On-chain agent ID (token ID from the ERC-8004 registry)"}},"required":["chainId","agentId"]}}
```

平台不得直接采用该服务的reputation/reviews作为自己的F/B分数。只可选择预先定义且能由可信链资料重建的有限字段。必须核实该工具不会调用登记/付费路径，且不存在跨身份资料移用。

### Clawdia Routing（复用20261019真实原件）

原件：`runtime/generic-evaluation-20261019T093532Z-805ea72f/protocol-62d54211ebda-availability-001.response.bin`（其余十次availability同样含该列表）。

```json
{"name":"route_task","description":"Route a task to the best-matching agent in ClawPlaza.","inputSchema":{"type":"object","properties":{"task_description":{"type":"string","description":"Description of the task"},"budget":{"type":"number","description":"Budget in credits (optional)"}},"required":["task_description"]}}
{"name":"get_agent_info","description":"Get information about registered agents on ClawPlaza.","inputSchema":{"type":"object","properties":{"agent_id":{"type":"string","description":"Agent ID or name (optional, lists all if omitted)"}}}}
```

没有outputSchema，没有明确预算下限/最大执行/候选限制/不委托/dry-run。`get_agent_info`也是业务工具，未审源码和允许范围前不因名字像查询就调用。Routing F需预先规定约束、允许候选、预期选项及独立核验；B需责任归属和实际接收/执行/交付记录，不能把同一任务同时计入F和B。当前保持探索/缺项。

## 对实施阶段的建议

先基于Brain/Degen/Arena三条真实服务线决定最小可核验任务，不机械开发五种Checker。统一的安全执行/任务证据结构可以复用，但ERC20静态属性、资产目录和注册资料查询分别需要明确的参数/输出映射及独立数据源。匹配须同时检查来源认证、协议、完整Schema、只读许可与固定状态条件，不按Agent ID特判，也不由工具名模糊命中自动执行。

如果本轮无法取得两个提供方的合格证据，保留已实现的来源发现、能力覆盖及PARTIAL解释，并如实标注真实F验收阻断；Mock只用于工程失败路径，不计真实评价。不要为了凑7个F样本把一次业务输出拆成多字段或重复同一查询冒充不同任务。

尚未完成：可信注册与新端点逐项绑定、真实安全业务调用、独立oracle实际采集、来源Verifier重建、新能力F/B评分、跨提供方真实复用。上述均没有被本调查声称完成。

## 后续真实核验收据（调查之后，2026-10-19）

本节记录实施阶段后来取得的业务证据，不改写前述只读调查的 **26 份观测、23 个完整 HTTP200、0 tools/call、0 RPC** 等原始统计。Brain On BNB AI（BNB #49467）的链注册及内嵌 data JSON 已完成认证，并绑定登记的 MCP 服务；随后在明确限定的安全范围内实际调用一次 `bobai_activity({})`。能力类型为 `Query / Tool`，Checker 为 `query.erc20-transfer-record` / `v1`。

六次可信 RPC 读取取得成功交易 `0x41da02b6e7e36aae1b74e336b8975afd1a71813f3d8b8e6b85208940b043eb37` 的链、交易、回执、区块及固定交易区块下的 decimals 等原件。独立重建确认区块为 **128175989**、代币 decimals 为 **18**，指定代币转入预定 `0x000000000000000000000000000000000000dead` 地址的匹配 Transfer 合计为 **11768.639803124515570716**；按预定 half-up 整数舍入为 **11769**，与 Agent 披露一致，本项 F 事实核验为 **PASS**。该结论只覆盖此笔交易及金额，不证明永久销毁、记录最新性、历史完整性或 Agent 执行归属。

正式报告现含 **1 个不同的 F 任务、1 PASS**，仍未达到 F 的 7 个不同确定任务门槛；A、F、B 和综合分均为 `null`，报告状态为 **PARTIAL**。报告已通过来源 Verifier 重建验证，**截至本节记录时尚未入库**。独立审查仅重放已有原件，额外网络请求和业务调用均为 0。

原件与核验收据：

- [真实 Query 报告、计划及 manifest](../../runtime/checker-expansion-20261019/real-query-report/)。
- [独立核验结果](../../runtime/checker-expansion-20261019/query-oracle-supplement/independent-review.json)。

本次尚未证明两个不同提供方复用同一 Checker：DegenAI 与 Agent Arena 未同时满足已认证服务绑定及同语义独立 oracle，不能合并视为第二个合格对象。Routing / Workflow 仍未执行业务测试，也未产生正式 F/B 结论。

## 最终发布更新（同日，晚于上节）

上述真实Query报告现已通过正式来源复核和导入，报告ID `888f98ca-0bc7-4a58-9de2-1f0626bc40a5`，本地Agent key `agent-e9357377962d8c944359ca49`。数据库现为12个Agent、12份报告、5个作业；该新增报告仍为1个F PASS、各维度及综合分均null的PARTIAL。实际数据库API、证据SHA及私密配置下载拒绝均通过验收；未增加真实业务调用或为此启动公开Worker。完整测试范围、历史保护、浏览器截图及未达成项见 [实施验收报告](../runbooks/CHECKER_EXPANSION_20261019.md)。
