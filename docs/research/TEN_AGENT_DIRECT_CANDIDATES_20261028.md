> 历史调查记录：2026-10-29用户已取消十对象目标。本轮四对象完成后停止新增实验，下文候选不再继续请求、付款或适配；当前状态以README和STATUS为准。

# 十个交易Agent目标：直接服务候选核查

日期：2026-10-28。原件仅新增于 `runtime/candidate-expansion-goal-20261028-direct/`。本调查没有钱包读取、签名、授权、付费、RPC或链上发送；不修改评分、Schema、生产代码和旧报告。负责人负责可信链证明及串行资金操作。

本轮新增三个独立、公开登记的交易服务线索：Topaz Agent、SwapTitan、Ophis。**Topaz已取得正常免费报价和完整7调用原子方案；Ophis已取得正常免费CoW报价和未签订单；SwapTitan出现与正确请求不符的收款地址，禁止执行。** 后两者登记来源为官方MCP Registry，不冒称ERC-8004。以下六个主候选及已有对象仍不等于六个已评分，更不等于达到十个、每个30任务。

## 候选与当前资格

| 对象、独立登记 | 交易功能与真实服务接口 | 当前原件与费用 | 可复用证据路径及下一步 |
| --- | --- | --- | --- |
| **Topaz Agent**；主页声明BNB链56、ERC-8004 Registry `0x8004A169FB4a3325136EB29fA0ceB6D2e539a432`、ID113284；owner声明 `0x9e9a1513Ed6b0f0d3305A87a6Aca5C815Ad949D6` | 5链swap报价/构建、LP/CL查询与策略、费用/投票/奖励等；`POST https://agents.topazdex.com/api/swap/quote`、`/api/swap/build` | 官方agent/openapi/status/card、Base池列表及2正常业务请求均200；无API付款。Base有3池，其中WETH/USDC约3564USD，其余微小/零流动性，不能当全部可成交 | 新协议是Universal Router+Permit2原子batch；复用通用任务意图/链证明/独立模拟/交易事件与余额。负责人补BNB注册owner/tokenURI及Base部署证明后，冻结正式矩阵。只选既有资产兑换与查询，不调用CL mint、身份/报告mint、部署、代币发行或xTOPAZ铸造。 |
| **Ophis MCP**；官方MCP Registry `fi.ophis/mcp@0.2.0`、active，发布2026-10-19，remote=`https://mcp.ophis.fi/mcp`；未证ERC-8004 | 13工具，包括报价、CoW签单构建/校验/提交、链/代币发现、余额/费用/预期盈余；公开免key | 官方登记、manifest、实时tools/list/list_chains/USDC解析及0.10/1.00USDC→WETH报价、0.10未签build均200且无MCP isError；Base配置指向 `https://api.cow.fi/base`。自有receiver正确 | 新通用协议为CoW EIP-712订单+appData，不是任意交易。负责人核订单哈希/UID、domain、fee与receiver、EIP1271/EOA兼容、限额授权、实际settlement事件/余额。报价与未签build不算B成交。 |
| **SwapTitan**；官方MCP Registry `net.swaptitan/swaptitan@1.0.0`、active，remote=`https://swaptitan.net/mcp`；DMV编号仅为自报，未证ERC-8004 | 21实时MCP工具；Base单链 `GET /v1/evm/base/quote`、`POST /v1/evm/base/swap`，另Solana/跨链/价格/HL工具。只测试Base已有USDC/WETH | 正确amountRaw报价、REST build、一次MCP build对照均200；两次build实际直接0x Settler，feeBps15，文档称Kyber/30bps。两次均给另一个收款地址，**禁止签名或批准** | 先将正确请求与输出冲突作为可归责候选事实交给共用F判据；B没有实兑，不能用保护退出补正常B。不得修改calldata后称Agent正常交付，也不继续换参数盲试。 |
| **DegenAI**；Ethereum ERC-8004 #23121；官网另列Base/OpenAgent #19162，系同一服务，不计两个Agent | `POST https://degenai.dev/x402/hyperliquid_order`，市场/限价/止损/批量/修改/取消/减仓；免费positions/orders/account/history/assets | 本轮官网HTML/Markdown/OpenAPI均200；交易声明费用为0.10USD+名义金额0.01%，支付与交易钱包可分开。只读声明与旧免费成功原件可复用 | 需要真实Hyperliquid交易账户及明确API-agent/builder授权、可用保证金，再以cloid/oid→fills→账户变化取证。未开授权、未入金、未付费，不能把任意钱包fills当DegenAI履约。 |
| **Silverback**；Base ERC-8004 #1156、Ethereum #13026，同服务 | 登记swap:permit2/swap:quote等；`POST /api/v1/swap`声称返回待签0x Permit2方案，另报价/池/分析工具 | 复用已有可信Base登记原件。旧主机 `x402.silverbackdefi.app`此前连接失败；OpenSea市集公布的 `silverback-x402.onrender.com` 本轮health/pricing/endpoints均503。未付费 | 恢复正常公开服务后再取方案。503是服务发现观测，不作为已冻结业务A槽成功或直接扣分。0.05USD swap价来自市集/公开说明，付款前仍须取实时challenge。 |
| **AgentSwap**；官方 `/.well-known/agent-registration.json` 声明服务，registrations为空；本轮MCP Registry按agentswap名称检索0项，仅说明该次检索 | MAS多聚合比较、执行calldata、流式路由比较、token/chain/pool发现；官方MAS主机 `meta-api.agentswap.co` 与Smart Router主机 `api.agentswap.co` 分开 | 复用本日负责人已取得的免费0.10USDC→WETH真实OKX方案及完整输入。未把OKX计成独立Agent | 尚缺能与该官方服务稳定绑定的公开登记；MCP名字检索0项不证明所有登记均不存在。保留方案格式证据，不直接计入已登记交易评分数量。 |

Topaz身份、能力和接口来自其[官方主页](https://agents.topazdex.com/)、[agent.json](https://agents.topazdex.com/agent.json)、[OpenAPI](https://agents.topazdex.com/openapi.json)。Ophis与SwapTitan登记分别来自[官方MCP Registry：Ophis](https://registry.modelcontextprotocol.io/v0.1/servers/fi.ophis%2Fmcp/versions/0.2.0)、[官方MCP Registry：SwapTitan](https://registry.modelcontextprotocol.io/v0.1/servers/net.swaptitan%2Fswaptitan/versions/1.0.0)；登记证明公开服务身份与端点，不能代替链交易履约。[DegenAI官方集成说明](https://degenai.dev/erc8004)、[Silverback市集接口](https://opensea.io/tools/x402-bazaar/base/1618834331880192107)、[AgentSwap官方API](https://agentswap.co/docs/api)支持各自声明，不使用其评分作为本平台分数。

## Topaz：可直接交给共用协议实现的完整材料

`runtime/candidate-expansion-goal-20261028-direct/topaz-handoff.json` 包含原始完整request、两个OpenAPI operation、原quote/build原文、7调用及离线解析、文件SHA256。全部数据由原件投影，脚本 `build_handoffs.py` 离线运行exit0；不是新的外部观测或工程集成通过。

真实build输入：Base8453，sellToken=原生发行USDC `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`，buyToken=WETH `0x4200000000000000000000000000000000000006`，`sellAmount="0.1"`（human units）、`slippageBps=50`、`deadlineSeconds=600`、`taker=0x73d642847cb9a3acef116ea207a74b9956c34a09`。该地址来自本项目已有公开自有买方资料，本调查不读取其钥匙或本地账户配置。

build返回固定块53206262、exactIn100000、expectedOut42916120680455、minOut42702607642243，route=100% CL，池 `0x9DD30d200B5C7e6874aB5a23c7BD7e2AD6d9C135`、tickSpacing50。Router=`0xe4b23F13b24232C1E68AD0575191216152AA9480`；**这是提供方返回值，部署认证由负责人独立执行**。官方schema明确ERC20交易必须由taker在同一原子batch提交完整序列，不得由EOA拆开顺序发送。[官方OpenAPI](https://agents.topazdex.com/openapi.json)

| 顺序 | 目标/selector | 解出的业务意义 |
| --- | --- | --- |
| 1 | USDC / `0x095ea7b3` | 清零旧direct-router allowance |
| 2 | USDC / `0x095ea7b3` | 清零token→Permit2 allowance |
| 3 | USDC / `0x095ea7b3` | 精确授权100000给canonical Permit2 |
| 4 | Permit2 / `0x87517c45` | token=USDC、spender=Topaz Router、amount100000、带expiration |
| 5 | Router / `0x3593564c` | UniversalRouter execute，commands=`0x0004`。V3 exact-in把输出暂留Router；最终SWEEP约束WETH、自有taker与min42702607642243 |
| 6 | Permit2 / `0x87517c45` | 清零Topaz Router额度 |
| 7 | USDC / `0x095ea7b3` | 清零token→Permit2 allowance |

内层V3 swap minimum是0，但最终SWEEP执行整体minOut；不能只看一条内部指令就判“没有最小到账保护”。所有7call value=0，`atomicRequired=true`、`permit2SignatureRequired=false`。本调查未运行模拟，未判断此batch已可执行，未把原件过期后换单称原任务成功。

注册tx为主页原值 `0x5ee64019e3d4ddf90b6df270553e28f1b3fc04d3960c6f55264c87b3b37cbc43`，不是本平台新部署或交易。chain56 tokenURI/owner、Base Router/Permit2/CL池、源代码与固定块状态均由负责人追加可信证据；不从Agent元数据接收任意RPC。

## SwapTitan：正确字段对照及停止点

官方README、公开客户端 `index.js` 的 `evmSwap(chain,{tokenIn,tokenOut,amount,amountRaw,account,slippageBps})` 和实时MCP `evm_swap` schema都将用户地址字段定义为`account`。本轮正确REST请求与唯一MCP对照均按此输入 `account=0x73d6…4a09`、`amountRaw="100000"`、slippage50，排除了由本客户端误用`taker`字段造成的不符。[官方代码](https://github.com/polsolbridge/solana-swap-api/blob/main/index.js)、[官方README](https://github.com/polsolbridge/solana-swap-api)

两次返回都以`0x1fff991f`调用 `0x7d6839415693801e94cdc4a7d732c9a3fdbbd1d7`，Settler结构首字段recipient为 `0x2daeb9502c35cd75cd6085e4d37a6958c368a2ea`，与请求自有买方不符；不是大小写差异。既有通用Settler ABI可解释该字段，但当前decoder只支持AllowanceHolder外层，不能靠补一个router白名单自动接受此直接调用。完整对照保存在 `swaptitan-handoff.json`。

第一次human amount=0.1的两请求返回400、要求amountRaw；这两原件完整保留。实时MCP文档明确human units只支持native，因此它们可作为接入前置错误，不能直接作为Agent业务FAIL凑数。之后已知终态400才以正确base units开展新请求，没有未知付款或重复签名。

文档称Kyber/30bps，实际label为“RiftBeam Base via 0x v2”、feeBps15；披露漂移可进入后续声明一致性审查，实际费用仍须按calldata/合约独立核实。没有实际损失或恶意动机结论。不得签名、批准spender、替换recipient后声称正常交付，亦不把拦截当成交B。

## Ophis：有效报价及未签订单

原件 `ophis-handoff.json` 留存官方MCP登记、2份正常报价及完整未签订单。Base配置采用CoW canonical settlement `0x9008D19f58AAbD9eD0D60971565AA8510560ab41`，签名domain name=`Gnosis Protocol`、version=`v2`、chainId8453。服务声明receiver固定owner，实际build两字段均为自有买方。[官方manifest](https://ophis.fi/.well-known/mcp.json)、[集成说明](https://docs.ophis.fi/ai-agents/)

0.10USDC报价为sell97885+fee2115=100000，buy41914334070273；1.00USDC报价为sell997788+fee2212=1000000，buy427678544656831。build按schema明确sellAmount100000、buyAmount41704762399921、feeAmount0、sell/nonpartial、slippageBips50、600sec、referrerCode空串。它独立再取当前quote后接受此限制，返回appData hash `0x2c30cf0e04af8ace86f34533fd156d63e39dc1efead7da85cff5155b9804ebf4`，fullAppData原字节保留。

伙伴费声明为1bp基础费，volatile对参考价改进的80%且cap99bps；这不排除上游CoW费用，不能把1bp当全部成本。0.10报价中的2115原子单位是上游quote的feeAmount，不是本调查实际付款。[官方费率与集成说明](https://docs.ophis.fi/ai-agents/)

USDC符号解析找到正确Base地址，WETH在其当前trusted token list未找到；依然保留为代币发现覆盖缺项。本轮报价使用本项目操作者已有、已核的WETH地址；没有依赖注册资料引入新资产。后续签单还需核EIP1271或EOA方案，不能让智能账户地址未经证明地充当EOA签名者。

## 每个30真实任务的覆盖设计建议（尚未执行/冻结）

这些是待负责人冻结的场景家族，不是49次调查请求自动转成正式任务样本。quote、build、模拟、签单、settlement若属于同一经济意图，按一个任务保留多个阶段，不能各自算一个样本。错误输入必须预设与正常目标区分，保留有效失败、UNKNOWN和平台无效测量。

| 对象 | 30任务矩阵可覆盖的不同目标 | 独立核验重点 |
| --- | --- | --- |
| Topaz | 8个双向正常兑换目标；8个不同金额/滑点/缺省/最短与最长deadline报价目标；4个symbol/address或hex/human单位等价目标；4个Base池发现/费率/流动性/路由目标；6个预设安全边界（slippage0/501、deadline29/1801、同token、未支持链） | 完整原子batch、精确授权与清理、最终SWEEP、固定块route/池费、实际收款/minimum。所有原生/包裹资产必须按实际声明和实现选择。 |
| Ophis | 8个正常双向订单履约目标；6个sell/buy/金额/期限报价；4个slippage/部分成交/fee校验目标；4个代币解析/链发现目标；4个有明确错误的外部订单校验；4个真实订单状态/取消目标（须官方可用接口及自己的已建订单） | owner=receiver、domain/appData哈希、sell精确或buy精确语义、fee/surplus、UID对应Trade事件、累计fill/有效期与取消状态。不能从模拟代替真实订单。 |
| SwapTitan | 当前停止正常资金实验。若提供方恢复正确account绑定，可用8正常双向执行+8不同金额/滑点/包裹与原生目标+4路由/费用目标+4已声明余额/资产发现+6预设输入边界 | 先修复当前正确输入却错recipient；新版本重新冻结，不覆盖负例。跨链/Solana/HL不因接口存在自动纳入当前Base范围。 |
| DegenAI | 获得合法交易账户后，可覆盖创建/修改/取消/批量/reduceOnly/止损、6种免费查询、方向/size/tif/cloid/重复id/错误边界；按不同任务目标冻结30项 | Hyperliquid实际授权、oid/cloid、成交与仓位/余额，不借任意钱包fills；需要新资金或权限的动作交负责人判断。 |
| Silverback | 恢复后以swap/swap_quote/池/费用/资产发现及声明边界组合30；当前不继续请求30次不可达接口刷样本 | 先取得真实方案，再确认Permit2/0x协议、recipient、精确授权、实际成交；分析/回测不能补交易B。 |
| AgentSwap | 登记绑定补齐后，可覆盖多聚合器源、流式与单次比较、双向/金额/滑点/fee、token/chain/pool发现与拒绝边界，冻结30真实目标 | 同时间/同固定块参数、多路输出与实际方案归属、聚合器协议、user recipient与资产效果；不能按聚合器数算Agent数。 |

这里各功能家族存在重叠，冻结时仍须落实为30个互不重复task_id和具体参数；受控查询与真实执行的数量、充分性、权重沿用v3，不为凑30降低门槛。Topaz/Ophis/SwapTitan的未签来源可共用“公开服务身份→任务意图→unsigned plan/order→独立执行效果”的来源结构，但UniversalRouter、0x Settler、CoW是三个协议适配，不是三个对象专属评分器。

## 排除及复用

- Tator Trader沿用本日已付费500/API keys not configured的停止决定，不重付费。SafeRoute、TheSafeRouteBot、Hydrex和Mango已有对象不由直接入口数重复计数。
- Captain Dackie/Capminal有既有登记1380(Base)/9382(Ethereum)，但当前官方Cap Wallet skill要求CAP_API_KEY；匿名x402服务为token部署，触及红线，未调用。其公开card本轮404。有swaps能力不意味着必须测试部署。[官方Capminal skill源码](https://github.com/Capminal/agent-skills/blob/main/capminal/SKILL.md)
- Elsa官网有多能力API，但仍未找到与该服务可靠绑定的登记；MCP Registry的elsa名称检索第一页包含自行车教练等无关对象，不能借同名填身份。其已有健康200/业务402只复用，不新付费。[Elsa官方文档](https://x402.heyelsa.ai/docs)
- FrostyLabs所举Base #54630是Gas Oracle示例，不是已找到公开交易Agent；没有把平台能力、自己的新部署或token launch当本轮交易对象。[官方说明](https://frostylabs.ai/)
- AgenticFi本轮官方card/OpenAPI可读，声明LI.FI quote；无可确认登记、公开输出Schema没有完整交易计划保证，不优先新增付费调用。[官方接口](https://defi-api.agenticfi.wtf/)

## 实际命令、状态与限制

每批先写 `phaseN-plan.json` 再运行 `.venv/Scripts/python.exe -X utf8 runtime/candidate-expansion-goal-20261028-direct/read_sources.py <plan>`，均走现有SafeHttpClient、显式`http://127.0.0.1:7897`、pin_public_dns、20秒/2MiB、无自动重试/重定向。批次1–9、10b、11退出0；最初phase10计划JSON语法错误在任何网络调用前退出1，原件保留，修正为独立phase10b计划后执行。目录API一次timeout、一次TransportError也保留，没有绕过限流或以搜索网页404推空仓库。

本轮合计49个实际网络请求，完整逐项记录以 `research-summary-final.json` 为准；其中36个GET、13个POST，39个HTTP200、2个400、2个404、3个503、1个422及2个无HTTP状态。400/422分别保留其接入参数背景，HTTP200包括背景查询和MCP transport成功，均不能直接当A/F/B通过。0付款、0签名、0授权、0广播、0RPC、0模型调用、0正式评分。工程测试NOT_RUN，链上模拟/实际履约NOT_RUN_BY_THIS_SUBAGENT。

Git：本子任务不提交、不push、不改全局PLAN/STATUS；仅新增本研究文档及受忽略runtime原件，交负责人并入本轮状态/交付。下一步先用Topaz与Ophis的共用协议材料完成独立安全验证；SwapTitan保留负例，不能为完成覆盖指标绕过收款约束。
