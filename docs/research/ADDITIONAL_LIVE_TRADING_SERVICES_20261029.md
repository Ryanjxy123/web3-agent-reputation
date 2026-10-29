> 历史调查记录：2026-10-29用户已取消十对象目标。本轮四对象完成后停止新增实验，下文候选不再继续请求、付款或适配；当前状态以README和STATUS为准。

# 额外公开交易服务：有限资格扩展

2026-10-29。限定核查 LI.FI、Enso、AVNU、Squid、KyberSwap 五个不同提供方，复用既有 Topaz/Ophis/SwapTitan/AgentSwap 等调查结论，不复查其超时服务、不把既有对象换入口再计数。**本轮取得 1 条真实有效的匿名交易 payload 线索（LI.FI），没有取得 2–4 个同时满足公开登记与可测性条件的新 Agent。新增完整评分对象为 0，10×30 目标仍未达成。**

全部原件在 `runtime/additional-live-trading-services-20261029/`。仅公开官方 GET、MCP tools/list 和一次明确只读 get-quote；没有 RPC、登录、API key、钱包/密钥、授权、签名、submit、付款或链写，没有本地部署远程开源工具冒充新服务。

## 五个提供方的实际资格

| 提供方及身份类型 | 已核接口/接入边界 | 实际业务与结论 |
| --- | --- | --- |
| **LI.FI**：官方发布的 hosted MCP **工具服务**，不是已证自主 Agent；当前未核得其 ERC-8004、A2A Card 或匹配的官方 MCP Registry record | 官方明确 remote=`https://mcp.li.quest/mcp`，匿名 200 请求/2 小时；API key 仅提高限流额度。实时 tools/list HTTP 200，25 个只读工具 | 一次 Base USDC→WETH 真实 get-quote HTTP 200，返回完整 unsigned transactionRequest；自有 SMA、代币、金额、最小到账与外层 calldata 收款绑定一致。技术线索成立，登记身份和完整执行证明仍欠缺。 |
| **Enso**：官方交易 API/SDK 基础设施 | 官方认证文档要求 Enso Developer Portal 创建 API key，再用 Bearer 或 apikey 参数。未核得官方 hosted 交易 MCP remote；不采纳第三方把 API 推导 manifest 称为既有 MCP 的说法 | 未绕过认证，不发匿名交易探测、不注册账号，quote/build 为 NOT_RUN。不是本轮新增可测公开 Agent。 |
| **AVNU**：Starknet 交易 API/SDK 基础设施 | 官方 AI 集成页提供 avnu skill、Context7 和文档，不给 hosted 交易 MCP。官方 MCP Registry 的 avnu 名称检索为 0；不能由此证明所有登记均不存在 | 没有自有已核 Starknet 执行账户或可绑定的公开交易 remote，不拿 EVM 地址假冒已可执行 Starknet 钱包；未改变链方向、未安装本地钱包 MCP，业务 NOT_RUN。 |
| **Squid**：官方本地 MCP 应用 | 官方文档要求本地 clone/build、审核签发 Squid Integrator ID；MCP 还生成/管理 OS keychain 钱包。不是已公布的匿名 hosted remote | 没有调用 setup_wallet、keychain、执行工具或借用他人 Integrator ID，quote/build 为 NOT_RUN。不把其官网的 MCP 宣传当远程 Agent 实证。 |
| **KyberSwap**：官方开源交易 MCP | 官方 README 的用法是本地 Node stdio，13 个 read/build/limit-order 工具，无已公布 hosted 交易 remote。GitBook 的 `~gitbook/mcp` 是查文档入口，不是 swap-build 服务 | 复用原有 Kyber 协议知识，不自建实例凑新对象，未调用自己的适配器冒充上游 Agent；新 remote 业务 NOT_RUN。 |

来源分别为 [LI.FI MCP 官方说明](https://docs.li.fi/mcp-server/overview)、[Enso 认证](https://docs.enso.build/pages/build/get-started/authentication)、[AVNU 官方 AI 集成](https://docs.avnu.fi/resources/ai-integration)、[Squid 官方 MCP 文档](https://docs.squidrouter.com/squid-ai/mcp)、[KyberSwap 官方 README](https://github.com/KyberNetwork/kyberswap-mcp)。这些事实只说明当前接入边界，不据此推断它们永远不能评价。

## LI.FI：真实请求、结果及 calldata 外层绑定

原始请求见 `phase3-plan.json`，原始 MCP observation/body 为 `phase3/lifi-base-quote.*`。这是一个查询/方案任务，交易未发送：

| 参数 | 实际请求/返回 |
| --- | --- |
| source/destination chain | 8453 / 8453 |
| fromAddress/toAddress | 均为自有 SMA `0x73d642847cb9a3acef116ea207a74b9956c34a09` |
| fromToken | USDC `0x833589fcd6edb6e08f4c7c32d4f71b54bda02913` |
| toToken | WETH `0x4200000000000000000000000000000000000006` |
| fromAmount/slippage | 100000 raw USDC / 0.005 |
| estimate toAmount/toAmountMin | 42834679427837 / 42620506030697 raw WETH |
| tx from/value/chainId | 自有 SMA / 0 / 8453 |
| tx to/approvalAddress | `0x1231DEB6f5749EF6cE6943a275A1D3E7486F4EaE`，**尚未独立证明当前部署** |

按保存的官方 `GenericSwapFacetV3.sol` 和 `LibSwap.sol` 定义独立计算 selector、解析外层 ABI，命令 exit 0，投影保存在 `lifi-outer-binding.json`。selector=`0x5fd9ae2e`，函数为 `swapTokensMultipleV3ERC20ToERC20(bytes32,string,string,address,uint256,(address,address,address,address,uint256,bytes,bool)[])`。外层 receiver 确为本次自有 SMA，minAmountOut=42620506030697，最终 receivingAssetId=WETH；所有 requiresDeposit 项均为 USDC，总额恰为 100000。

两条内层调用分别为 feeCollection 和 SushiSwap：先存入 100000 raw USDC，后续 Sushi 使用 99750。返回的 feeCosts 明确披露 `LIFI Fixed Fee=250` raw USDC、0.25%、included=true，integratorFee=0；不是本轮 API 已付款，也不能把这 25 bps 从交易成本中隐去。源文件只用于数据解释，没有运行远程代码。[官方 Facet 源码](https://github.com/lifinance/contracts/blob/main/src/Facets/GenericSwapFacetV3.sol)、[官方 SwapData 定义](https://github.com/lifinance/contracts/blob/main/src/Libraries/LibSwap.sol)

**尚欠** Diamond 当前 facet/代码及可变白名单、fee collector 实际语义、Sushi 内层路由和固定块完整效果、实际事件/资产变化及清理授权。外层意图绑定不等于完整模拟或真实成交；本轮没有新 production decoder/adapter。若后续选择该服务，先完成身份接入决定与这些协议前置，不修改返回 calldata 后称 Agent 原方案已通过。

## 登记与同名误识别

官方 MCP Registry 的 lifi、enso、squid 搜索会返回字符串碰巧相含的无关记录；avnu 搜索返回 0。本轮另外针对 lifinance 与 quest.li 精确缩小名称检索，均 0。分页/命名限制意味着这不是全网不存在证明，但当前没有可用来交付的官方匹配 record。`phase1/*registry.*`、`phase3/lifi-registry-publisher.*`、`phase4/lifi-registry-domain.*` 保留完整原件。

检索里出现的 somosvelora 电商 MCP、Velora UI 组件库与 Velora DEX 不是同一对象；没有把它们的登记移给交易聚合器。Squid Router 也不等于 Subsquid/SQD 数据查询服务器。LI.FI 内层 Sushi 路由不是另一个本轮已接入 Agent。

## 当前可交接内容与停止点

可交接的是 LI.FI 的完整正确请求、真实返回和外层 ABI 绑定，足以继续做身份与协议资格调查；**不能据此新增一个完整注册评分对象，更不能称已完成 30 任务或 B。** 其它提供方已定位到认证、本地实例或链账户/remote 缺项，没有在同一缺口反复重试。

本调查不要求用户立刻提供新 key、登录或钱包，不擅自放宽“不同公开登记服务”的筛选条件。Root 如决定下一轮扩大提供方池，可基于这些明确缺项选择路线；本轮不以多写文档、API 数量或模拟成功充当新增 Agent。
