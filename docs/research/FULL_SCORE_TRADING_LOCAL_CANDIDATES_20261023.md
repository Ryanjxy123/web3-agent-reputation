# 可完整评价的交易 Agent：本地候选复查

调查日期：2026-10-23。范围为新项目已保存的候选声明与原件，并定向复查 CeloFX、Agenthaus 的官方公开入口。本轮只做发现和证据可得性调查，不新增评分政策、适配器、正式评分或 Worker 任务。

## 结论

**尚未发现 Brain、Olas 以外，已有材料能证明多个对象可完整三维评分的交易 Agent 群体。** 本轮排除了两个容易误判的线索：CeloFX 的历史 API 可以读取，但返回的9条记录与源码预置历史一致，缺原始任务关联；Agenthaus 有可复用的公开接口，旧交易实例当前返回404，现有公开对象没有足够的交易业务历史。应先寻找证据更完整的群体，暂不为它们编写专用适配。

服务可用性、功能声明一致性、交易行为可靠性及30/40/30权重保持。下文的“可读”均为背景调查的一次真实读取，**没有完成正式A的10槽位采样**；目录声明、钱包标签和交易列表分别列明来源，不计作已验证履约。

### 样本数量的准确含义

如果 F、B 都取同一类执行历史，当前规则要求两组互不复用的7个不同任务，因此需要能划成7F与7B的执行任务。它不是“Agent天然必须有14笔交易”：一次业务可能包含多笔链交易；同笔交易中的多个事件也不能拆成多个独立任务。

如果同一 Agent 的另一项已声明只读业务能提供7个不同、可独立核验的F任务，B另用7个执行任务，也存在满足采样的可能。报告必须准确说明F检验的是哪项功能；查询F通过不代表兑换功能正确。本轮尚未证明以下对象满足这种组合条件。

## 主要对象与当前证据矩阵

除特别注明外，表内 ERC-8004 注册合约为 `0x8004a169fb4a3325136eb29fa0ceb6d2e539a432`；完整身份由链ID、合约、Agent ID共同构成。这里的注册线索并非全部经过本轮独立RPC认证。

| 对象与完整身份 | 功能、执行账户及绑定状态 | A：服务入口 | F：声明与原始业务输入输出 | B：授权与交易历史 | 当前决定 |
| --- | --- | --- | --- | --- | --- |
| **CeloFX** · `eip155:42220:0x8004a169fb4a3325136eb29fa0ceb6d2e539a432:10` | 声明在Mento/Uniswap V3兑换；官方policy列执行钱包 `0x6652acdc623b7ccd52e115161d84b949baf3a303`，源码签名实现为EOA。本轮未核tokenURI、历史权限或实际tx sender，钱包仍为声明关联。 | AgentCard、trades、policy、decisions均HTTP200；没有调用执行或付费服务。 | 9条自报兑换结果，全部有swapTxHash；没有对应用户原始委托/决策输入，当前decisions为0。可作后续结果披露调查，尚不能判断执行任务声明一致性。 | 本轮RPC核验0笔；未取得历史授权、固定区块receipt/事件与任务归属。不能将9条API记录记为9个已验证任务。 | 保留高价值单对象线索；未证明多对象，也未具完整三维条件。 |
| **TradingMento** · `eip155:42220:0x8004a169fb4a3325136eb29fa0ceb6d2e539a432:22` | 旧目录声明条件兑换、止损止盈。旧目录钱包字段 `0x53eaf4cd171842d8144e45211308e5d90b4b0088` 未认证为该身份的历史执行账户。 | 登记dashboard只返回钱包连接页面；当前public详情及registration.json均404。 | 当前无实例业务响应或原始任务。 | 当前无该身份可归属交易原件。不能移用现有其他身份的同地址记录。 | 当前入口缺源；不由页面HTTP200判断A通过。 |
| **ForexPro** · `eip155:42220:0x8004a169fb4a3325136eb29fa0ceb6d2e539a432:31` | 旧目录声明CELO/稳定币兑换。旧目录钱包字段 `0x98f7e3fc142ce7736956cd79d3f6b164c631a3d9` 尚无独立绑定。 | 登记dashboard为钱包连接页面；public详情及registration.json均404。 | 当前无实例业务响应或原始任务。 | 当前无可归属交易原件。 | 当前入口缺源，保留扩展记录。 |
| **Agenthaus同类旧声明 #24、#30** · 链42220及同注册合约 | #24与#22同一条件兑换描述；#30与#31同一外汇兑换描述。重复文案不证明相互独立的提供方。 | 本轮未另外调用这两个对象；旧资料仅作线索。 | 尚无同对象任务证据。 | 尚无同对象授权/执行证据。 | 不用模板数量代替可测覆盖。 |
| **Genesis** · `eip155:42220:0x8004a169fb4a3325136eb29fa0ceb6d2e539a432:2113` | 现公开模板为payment；公开标注Agent钱包 `0x5925d337af10b74ad0c4c83ccfe23cfea4f8386b`，账户类型及执行角色尚未独立认证。 | 脱敏public详情HTTP200，支持读取交易记录。 | 没有付款原始任务或交易业务结果。 | API两行记录均为register，而且是同一哈希；不是两个付款任务。 | 接口可读，当前不具交易评分样本。 |
| **Gnes #19、Haus Child #1826** · 链42220及同注册合约 | 现公开均为custom模板；均标注同一钱包 `0x53eaf4cd171842d8144e45211308e5d90b4b0088`。 | 当前public列表可读；未另作业务调用。 | 列表交易数均为0；无原始任务。 | 未取得可归属交易；共用钱包不能证明两套独立执行。 | 保留候选，尚无交易业务可评分证据。 |
| **Custos** · `eip155:5000:0x8004a169fb4a3325136eb29fa0ceb6d2e539a432:128` | 官方源码声明USDC金库、Aave/USDY配置与去风险；执行者是vault的ALLOCATOR角色。本项目尚未独立核实该身份、实际ALLOCATOR地址与具体vault的关联。 | 既有snapshot/decisions两次读取均超时，无完整业务响应；本轮复用旧观测，未重试。 | 缺实际历史决策、固定块输入与decisionURI原件，不能拿README的守卫说明当已执行结果。 | 缺具体执行任务、授权/角色状态、receipt/事件及资产变动原件。 | 是真实具体入口，当前缺可归属证据；仅一个提供方线索，未证明多实例群体。 |
| **DegenAI** · `eip155:1:0x8004a169fb4a3325136eb29fa0ceb6d2e539a432:23121` | 声明Hyperliquid订单执行；付款钱包、交易钱包及获准API Agent密钥分角色。目录agent_wallet或payment recipient不能替代交易授权。Ethereum身份也不代表业务在Ethereum执行。 | 既有x402发现和免费BTC资产查询成功；当前官方文档继续给出免费查询。实际交易需授权及收费。 | 免费任意钱包fills查询可以研究事实查询功能，但不能证明这些fills由DegenAI执行；缺原始订单约束→服务交付→订单/成交的可认证关联。 | 尚无本项目留存的获准Agent地址/历史授权与具体服务执行记录；旧erc8183发现中provider/contract/evaluator为空、contractDeployed=false，仅代表当时发现状态。 | 具真实服务入口；现有成功查询不足以形成交易B，也不能算已完成交易F。保留，未新授权或付款。 |

## CeloFX：公开入口齐全，业务历史仍需独立认证

本轮通过官方仓库 `edwardtay/celofx` 的固定commit `1b92b328aff9f98868f9a3433728297db94fbb9a` 审查了trades、policy、decisions、MCP和存储实现，再读取对应匿名GET。源码说明用户签名意图与Agent API鉴权是两种执行方式；本轮没有调用执行接口。[官方README](https://github.com/edwardtay/celofx/tree/1b92b328aff9f98868f9a3433728297db94fbb9a)

当前观察：

- `GET https://celofx.vercel.app/api/trades`：9条`confirmed`自报记录，时间落在2026-02-09T18:23:03Z至2026-02-10T21:02:46Z。不能由confirmed字段认定链上已确认。
- 9个不同`swapTxHash`与固定commit `seed-trades.ts`的9个哈希集合完全相同。`trade-store.ts`在没有持久化记录时使用该seed；预置记录的真实性仍需独立RPC核对。[存储源码](https://github.com/edwardtay/celofx/blob/1b92b328aff9f98868f9a3433728297db94fbb9a/frontend/src/lib/trade-store.ts)、[预置历史](https://github.com/edwardtay/celofx/blob/1b92b328aff9f98868f9a3433728297db94fbb9a/frontend/src/lib/seed-trades.ts)
- `GET /api/agent/decisions`返回`totalDecisions=0`，`onChain.totalOnChainDecisions=0`。源码在上游日志读取异常时也返回空数组，因此这个0不能证明链上没有承诺，更不证明服务从未决策。[决策读取源码](https://github.com/edwardtay/celofx/blob/1b92b328aff9f98868f9a3433728297db94fbb9a/frontend/src/lib/agent-policy.ts)
- 本轮没有对Celo RPC发请求，已核交易数为0。当前的短板包括原始意图/约束、历史委托、交易前绑定、实际成交与披露的精确比较；公开查询能读解决的是资料入口问题。

例如自报`trade-real-9`称花费0.15 cEUR收到0.178 cUSD，swap哈希为`0x3126ec624216415b594d71535e4d83a1b2c89412c6365ad73d7381b9bd07ed96`。这是一个可定向追踪的候选记录，尚不是本平台PASS样本；不能先围绕这条记录写专属评价，再寻找第二个对象。

如果以后重新评估此方向，优先取得该Agent可公开验证的原始意图、执行归属与完整不同任务；同时寻找另一独立实例的同语义条件。另一项只读F若要参与报告，还需证明输入/输出和独立oracle相匹配，不能用另一个时间点的动态报价直接判错。

## Agenthaus：平台可复用，当前没有可直接评分的交易实例群

官方仓库 `Olisehgenesis/agenthausv2` 固定commit `69251387ca31e10e2de8f9cec27c095cde8c9570` 提供了显式脱敏的匿名查询路由：

- `GET /api/public/agents?status=all&erc8004Only=true&limit=50`；
- `GET /api/public/agents/{uuid}?include=transactions`，最多50条历史；
- `GET /api/agents/{uuid}/registration.json`，显式选择公开登记字段。

这三个入口比钱包连接页面更有调查价值。public详情会返回业务模板、所报Agent钱包、登记ID和选定交易字段；公开交易字段包含hash、type、status、amount、currency、block和时间，不包含完整原始指令/条件。`amount`在其数据库中还是浮点数，需要与链上最小单位分开处理。[公开详情源码](https://github.com/Olisehgenesis/agenthausv2/blob/69251387ca31e10e2de8f9cec27c095cde8c9570/src/app/api/public/agents/%5Bid%5D/route.ts)、[数据模型](https://github.com/Olisehgenesis/agenthausv2/blob/69251387ca31e10e2de8f9cec27c095cde8c9570/prisma/schema.prisma)

当前匿名列表实际返回4个对象：

| 当前public对象 | 登记 | 自报模板/历史 | 对本次交易评价的意义 |
| --- | --- | --- | --- |
| Scott's Agent | Celo Sepolia #541，链11142220，注册合约`0x8004a818bfb912233c491871b3d84c89a494bd9e` | custom，计数2 | 测试网身份，不计本轮主网交易候选成果。 |
| Gnes | Celo #19 | custom，计数0 | 当前没有公开执行记录。 |
| Genesis | Celo #2113 | payment，计数2 | 详细读取显示两行同哈希登记记录，不能按2个业务任务计。 |
| Haus Child | Celo #1826 | custom，计数0 | 当前没有公开执行记录；与Gnes标注同一钱包。 |

这个4是该次公开查询的返回量，不是对整个生态总量的断言。旧登记线索#22、#31在本轮分别做了public详情和registration.json读取，均返回404；其dashboard主机规范化后的HTTP200只提供Connect Wallet外壳。404说明当前路由未提供该实例，不说明链上身份已经不存在。

Genesis两条记录共享哈希`0x5344946d755b89c655c40962ec56eaf1cc7d0069505048d03f957a33ddb3b4ec`且type均为register。这个例子也说明，平台聚合`transactionCount`不能当作交易业务样本数。

另外，官方MCP源码声明了`execute_transaction`工具，但实际POST分派没有对应执行分支；不能把工具列表当已可调用交易服务。为避免读取不必要的账号字段，本轮只请求public脱敏路由与显式公开的registration路由，没有调用内部详情、export、chat、execute、transfer或session接口。[MCP源码](https://github.com/Olisehgenesis/agenthausv2/blob/69251387ca31e10e2de8f9cec27c095cde8c9570/src/app/api/mcp/%5Bid%5D/route.ts)

## Custos与DegenAI没有进入交易主线的具体原因

### Custos：有具体能力、接口及合约设计，缺本项目可取证的任务闭环

既有新项目资料已定位Mantle #128、`https://trycustos.xyz/api/snapshot`和`/api/decisions`，以及作者的`YieldVault`、`Guardrails`、`AgentBenchmark`设计。官方描述的`rebalance`/`deRisk`会改变金库配置，并用DecisionRecorded和decisionURI留下决策证据，是值得保留的链执行方向。[官方仓库](https://github.com/0xMaxyz/Custos)

但本项目2026-10-18两次匿名GET分别在16.172秒、15.640秒后ReadTimeout，HTTP状态和完整业务响应均未取得；这记录的是读证据未完成，不是Agent FAIL。本轮没有重试这两个缺源入口。当前缺口逐项为：

1. 链上#128的登记文件与具体公开接口、vault、ALLOCATOR账户之间的认证关联；
2. 同一历史任务的原始决策参数、decisionURI内容和执行前固定状态；
3. `rebalance`/`deRisk`的交易、receipt、目标事件、角色权限及资产变化；
4. 足够不同任务以及另一个同语义、同时具备上述条件的真实对象。

旧收据：`runtime/candidate-check-20261018T053927Z-27b8ade9/custos-snapshot.observation.json`、`custos-decisions.observation.json`；六项准入记录见`configs/candidate-reviews-20261018.json`的`custos`。没有原件时，部署者、README中的地址或ALLOCATOR角色名都不能被直接升级为已绑定的执行钱包。

### DegenAI：免费查询确实可用，任意钱包成交记录缺服务执行归属

已有真实发现响应列Agent #23121及免费资产、仓位、历史查询；一次`get_available_assets(filter=BTC)`返回BTC/BTCD两个符号。这是实际查询响应，不是交易执行证明。当前官方文档的交易通路需要交易钱包的Agent授权和按次支付；付款钱包与Hyperliquid交易钱包还可分开。[官方集成文档](https://degenai.dev/erc8004)

缺口是把“用户原始订单→获准的DegenAI执行身份→服务交付→Hyperliquid订单/成交”连为同一条可认证记录。官方原生fills可独立核事实，但查询任意钱包的fills并不说明成交由DegenAI完成；注册在Ethereum、费用用Base USDC，也不构成成交授权证明。应取得服务公开的既有任务/回执和历史授权，而不是拿`recipientAddress`当交易钱包。

旧`GET https://degenai.dev/erc8183`在2026-10-17返回`contractDeployed=false`及空provider/contract/evaluator地址，尚不能从它取得已部署任务合约的历史闭环。这是当时原件，不外推为今天仍然未部署。本轮没有重新调用该服务、申请授权、付款或创建任务。

旧原件位于`runtime/candidate-check-20261017T175652Z-f876ebbc/`：`degen-discovery.*`、`degen-assets.*`、`degen-jobs.*`；进一步费用/鉴权语义见`docs/research/AGENT_CHECKER_CANDIDATES_20261019.md`。完整交易评分前，可信登记绑定、原始订单、执行授权与足量不同任务都还要在同一对象上成立。

## 其他已存材料的去留

- **delu，Base #30004**：已有链上登记原件，但注册描述是基础设施开发、services为空；作者交易journal只有一条可追踪兑换线索，身份到交易服务及实际执行者尚未认证。状态服务源码可能返回mock，不能据网页时间和HTTP200判A。保留`candidate-reviews-20261018.json`的逐项缺口，不新抓同一条缺源记录。
- **Clicks Protocol，Base #45074**：登记与MCP发现存在；旧分账读取返回上游RPC额度限制，已有观察不能作业务通过。交易执行归属、原始结算任务与receipt未取得。本轮不重试或绕开限额。
- **Arbitrum #14/#19、Avalanche #1613/#1614等声明**：旧目录有复投、闪电贷、再平衡文案，但当时services为空或没有具体业务规范。同名模板、激进收益宣传和有余额的钱包都不是“可完整评分对象”。在出现同对象实际接口与任务证据前，优先级低于有真实公开历史入口的候选。
- **Hallmark等已有仓位查询对象**：只读查询报告保留其已测含义，本次没有找到足以把它改列资产执行者的证据。

以上原件索引来自`configs/corpus-semantic-review-20261018.json`、`configs/corpus-detail-declarations-20261018.json`与现存runtime，仅按候选字段读取；没有扫描父级失败项目。

## 本轮只读操作与复用条件

新证据目录：`runtime/full-score-trading-local-20261023/`。每阶段都有预先列明URL的`phaseN-plan.json`和同名运行子目录；原始响应、`ProbeObservation`及`read-summary.json`保留。读取均经`SafeHttpClient(pin_public_dns=True)`、`http://127.0.0.1:7897`代理、每请求20秒上限及2 MiB响应界限，无自动重试/重定向。最初agenthaus非www地址的307也保留；改读已公开的www官方主机有独立新观察。

合计36次公开只读：30个完整HTTP200、2个307、4个404。0 RPC、0模型、0签名、0资产写入、0付费服务、0 Worker任务、0正式评分。命令为`.venv/Scripts/python.exe -X utf8 runtime/full-score-trading-local-20261023/read_sources.py runtime/full-score-trading-local-20261023/phaseN-plan.json`，六阶段均exit0；其中exit0代表调查脚本正常保存观察，404/307未被改写成业务成功。工程测试NOT_RUN，本轮没有生产实现变更。

建议下一轮继续发现已有完整取证条件的群体。开始适配前，至少在多个明确身份上同时看到：可读且有明确业务含义的接口、原始任务及约束、真实执行账户的历史授权、可独立核验的结果、足量互斥评分任务。某一项没有满足就保留具体缺项，不能将不同对象的接口、钱包、历史或oracle拼成一个可测对象。
