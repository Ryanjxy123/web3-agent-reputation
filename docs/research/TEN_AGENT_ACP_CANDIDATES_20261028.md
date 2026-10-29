> 历史调查记录：2026-10-29用户已取消十对象目标。本轮四对象完成后停止新增实验，下文候选不再继续请求、付款或适配；当前状态以README和STATUS为准。

# 十对象真实交易覆盖：ACP候选核查

调查日期：2026-10-28。目标是MangoSwap、Hydrex以外继续补至少8个真实交易服务，每个至少30个真实业务任务。本调查不出分、不操作钱包。排名表示接入调查的优先顺序，不是服务质量分，也不表示八家已经完成实际接单或独立提供方认证。

## 已取得的事实

复用`runtime/candidate-review-20261028-acp/`、`TRANSACTION_COHORT_20261028.md`及结果文档后，新增3次官方ACP公开搜索、10份候选详情、2份ERC-8004正文读取。两次搜索完整返回70个去重目录记录；第三次大型响应HTTP200但25秒总超时、正文不完整，不使用该结果、不重试。12次定向详情/正文均HTTP200并完整保存。没有读取认证配置、私钥、秘密RPC或任何`.private`文件；没有业务POST、签名、建单、付款、资产操作或工程测试。

原件目录为`runtime/candidate-expansion-goal-20261028-acp/`；每个外部请求有`*.observation.json`与原始`*.response.bin`，`candidate-details.json`保留10家完整声明/输入/输出Schema。官方详情端点均为`GET https://api.acp.virtuals.io/agents/{provider_uuid}`。本次取证走SafeHttpClient、显式`http://127.0.0.1:7897`代理和`pin_public_dns=True`，不降低HTTPS/SSRF边界。目录`lastActiveAt=2999-12-31`不是在线证明，详情200也不是业务A样本。

## 优先队列：八个不同服务记录

前两家已有真实方案与独立历史效果，可复用已有0x/Kyber解码；后六家是本轮新定向核查的执行服务。后六家不能都按unsigned方案接入：其声明是自己完成兑换并交付交易hash。不同UUID、钱包、builderCode及consoleAgentId只支持区分平台记录，不能独立证明最终经营者不同；目前未发现六家共用后台的确证，Clawpump与ArmaBase自报owner也不同，最终去重还需可信身份和实际业务材料。

| 顺序 | 服务、业务入口 | 挂牌USDC / SLA / 本金标记 | 模式与当前证据 | 关键剩余事项 |
| --- | --- | --- | --- | --- |
| 1 | TheSafeRouteBot / `safe_quote` | 0.05 / 5分钟 / false | **买方签名方案**；真实ACP交付，Kyber calldata已独立解码、固定块效果通过 | 取新鲜方案及真实兑换；ERC8004尚缺，保留真实ACP身份 |
| 2 | SafeRoute / `safe_token_swap_quote` | 0.01另10bps / 5分钟 / false | **买方签名方案**；真实直连x402交付，0x固定块效果通过 | 30秒左右有效窗口需准备充分；默认约1%最低到账不冒称接受50bps；ERC8004尚缺 |
| 3 | PinchyMeow / `safe_base_swap` | 0.05 / 10分钟 / true | **提供方执行**；只支持现有USDC/WETH，严格Schema及交付tx/amountOut；当前无已知拒单历史 | 确认`amountIn/minAmountOut`单位、隐含收款人、精确fund请求及实际执行者；不能擅加recipient字段 |
| 4 | Clawpump / `On-chain Swap` | 0.01 / 30分钟 / false | **提供方执行**；Base登记#60748线索；要求5项输入、交付hash；当前无已知拒单历史 | 规范为文字模板，无收款/滑点/本金协议；先取得明确原任务条款，不把false当作无需本金 |
| 5 | SimonAgent / `swap_token` | 0.01 / 120分钟 / false | **提供方执行**；结构化资产地址/金额，交付`data.txn`；资源含swap-records | USDC计价金额与输入token数量不同；没有收款/滑点字段，Axelrod授权/资金流未核 |
| 6 | Opet / `Token Swap on Base` | 0.10 / 15分钟 / false | **提供方执行**；结构化token对/amount/slippage，承诺hash、实际数量、route、gas、确认 | 无recipient及完整资金契约，必须确认输出归属；禁止选择其token launch产品 |
| 7 | ArmaBase / `Instant Token Swap` | 0.12 / 5分钟 / false | **提供方执行**；Base登记#60504线索，LiFi、hash与confirmed receipt声明 | 输入文字模板、无recipient/minOut；只选普通swap，不买ARBA/ARRB、不走holder门槛 |
| 8 | OUWIBO AGENT / `token_swap` | 0.05 / 5分钟 / false | **提供方执行**；声明1inch/Jupiter、文字输入与tx_hash；无已知拒单历史 | `token, amount, chain`没指定输入/输出两腿、收款或滑点，先补确切契约；禁选deploy/NFT mint |

上述0.01等是ACP挂牌服务费；本金、额外服务级资金请求、gas和实际总费用需从真实条款核实。不得由`requiredFunds=true`推断允许把任意本金转给provider，也不得由false推断提供方会免费垫资。

## 精确身份及调用字段

### TheSafeRouteBot：已有可复用unsigned样本

- provider UUID `019eb95d-2e16-7ea6-80fd-384434761336`；平台钱包`0xe4bce29bc099e2a04369f6a2df98dc7d5eac2ac7`；ERC8004尚缺。
- `safe_quote`必需`sellToken,buyToken,amountIn,buyer`；可选`slippageBps,aggregator,chain`；交付`target,calldata,valueToSend,minOut,quotedOut,aggregator,gasUsd,verdict,reasons,validUntil`。
- [官方详情](https://api.acp.virtuals.io/agents/019eb95d-2e16-7ea6-80fd-384434761336)。直接桥为`POST https://api.acp-metabot.dev/v1/bridge/forward`，但桥价0.08且EOA兼容性有旧缺项；优先复用已实际成功的ACP服务路线，不重复桥探测。
- 已有job82343：需求、链上认证交付、Kyber解析及固定块效果原件见`runtime/acp-quote-cohort-20261028/`和`runtime/protocol-verified-20261028-kyber/`。尚无该任务真实swap，不把付款/ACP结算填B。

### SafeRoute：已有可复用unsigned样本

- provider UUID `019fe1a3-ac02-7451-8253-50b4af6356cb`；平台钱包`0x08a6a2ddecdebdbfcb29d725042a6f3d74849e08`，与真实x402 payTo一致；ERC8004尚缺。
- 直连`POST https://api.usesaferoute.com/v1/quote`，输入`from,to,amount,wallet,executionMode`；`standard`返回买方签名unsigned交易。[官方开发文档](https://usesaferoute.com/developers)、[官方ACP详情](https://api.acp.virtuals.io/agents/019fe1a3-ac02-7451-8253-50b4af6356cb)。
- 既有任务`6e25927a-fa0d-46fd-bffc-00283082efb2`真实交付和历史固定块效果通过，最早期限很短；原件`runtime/transaction-cohort-pilot-20261028/runs/6e25927a-fa0d-46fd-bffc-00283082efb2/`。0x内层费用和正滑点分配已发现，不能只按宣传10bps认定成本全部核齐。

### PinchyMeow：优先核精确本金执行

- provider UUID `019f59b9-393a-7bc7-9641-ce4405672b07`；钱包`0x72d22730ad0d37c3bfee32690fb748df366f2ac5`；Base/Robinhood目录登记ID都为null。[官方详情](https://api.acp.virtuals.io/agents/019f59b9-393a-7bc7-9641-ce4405672b07)。
- offering UUID `019f5a49-5791-75ae-9890-0274fe7400bd`。必需`fromToken,toToken,amountIn,minAmountOut,slippagePct`，`additionalProperties=false`。两个token仅允许Base原生USDC `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`及WETH `0x4200000000000000000000000000000000000006`。金额字段为十进制字符串、最多18小数；Schema没有明示人类单位，需由条款确认。`slippagePct`为number且`0 < x <= 5`。
- 声明每单最多1USDC或0.001WETH、dual-size fresh quote、2% impact cap、minimum output、24小时滚动限额、事前确定失败退本金、evaluator拒绝退服务费。拒绝边界是有价值场景，不能据此把全部任务设计成容易成功请求。
- 输出必需`status,transactionHash,tokenOut,amountOut`，皆string。Schema没有recipient，不能传额外字段或默认“就是新EOA”；先核ACP客户端地址和提供方确认的输出地址。
- 原件`details/pinchymeow.response.bin`，SHA256 `cab342ab6a8e4a604ab2bbca1404a9b067d85b8fc63ca4e7ab87d20dbb5f4a57`。没有找到本项目既有拒单/付款记录，本轮没有建单。

### Clawpump：便宜、已有链身份线索，语义仍需补

- provider UUID `019fd6be-5e09-75a0-84d2-7b7694c5481f`；钱包`0x3ce8dc26e2f1c26848563b94e4d980c69ad80ac5`；Base目录#60748。[官方详情](https://api.acp.virtuals.io/agents/019fd6be-5e09-75a0-84d2-7b7694c5481f)、[注册正文入口](https://api.acp.virtuals.io/agents/019fd6be-5e09-75a0-84d2-7b7694c5481f/erc8004)。
- offering UUID `019fd773-6353-7d61-bb85-cabcbcffd578`。原始requirements是文字`token-in, chain-in, amount, token-out, chain-out.`，deliverable是`Transaction hash.`。没有JSON Schema，没有recipient/slippage/minOut保证。`On-chain Swap`声明ACP trade真实签名和链上结算；不能由此推断支持我方钱包代签。
- ERC正文自报owner`0x76d3131d70b0ab2562ed33679ab45bded712e7bb`，web endpoint精确绑定该UUID，但`agentRegistry`错误填了provider钱包。可信RPC应读操作者已配置标准Registry的`ownerOf(60748)/tokenURI(60748)`，不得调用正文给出的错误地址当注册合约。
- 正文SHA256 `a0d073813ba2de121a512a47f32be3f7781030fbb2ba48f7fbd8357812f00e38`；detail SHA256 `47e224f98d97fc7b5fc43f19266cbde2adf284fa02ba7089425476f0afad3f8a`。现无本项目旧拒单历史。

### SimonAgent：字段完整度高，资金/收款绑定不足

- UUID `019d7c06-3764-7ce8-9db6-72066565c5a7`；钱包`0x9a0629a8dcae5f65c4211064ebbc48664b0258bf`；Base ERC8004字段null。[官方详情](https://api.acp.virtuals.io/agents/019d7c06-3764-7ce8-9db6-72066565c5a7)。
- `swap_token` offering UUID `019d7c06-3b42-72e2-a29f-3a71d54629d4`。Schema仅必需`amount:number`；可选`fromSymbol,toSymbol,fromContractAddress,toContractAddress`。描述要求每腿至少有symbol/address之一，地址优先；`amount`描述为通常按USDC计价，不能擅当任意input-token数量。输出为`data.txn:string`。
- 资源公开了`https://api-test.aixvc.io/sapi/v2/axr/seller/swap-records?address={{clientAddress}}`，名称不是生产可用性证明，本轮未调用。这是潜在任务历史入口，不能把任意钱包记录归给SimonAgent。现无本项目旧拒单历史。
- detail SHA256 `e7c192e8ad73cf94df41877879b0ce32e331095cda947a057662f2f1ab2e2e6f`。

### Opet：交付说明具体，优先补资金契约

- UUID `019fc0ea-8cc2-7e6c-b6f8-af02ca2ca85b`；钱包`0x95d5261c4f54202d6aabbf81eb915de05c1c6903`；Base/Robinhood ERC8004字段null。[官方详情](https://api.acp.virtuals.io/agents/019fc0ea-8cc2-7e6c-b6f8-af02ca2ca85b)。
- `Token Swap on Base` offering UUID `019fc11d-4939-75d6-926a-7a5da6305cb2`；必需`token_in:string,token_out:string,amount_in:number`，可选`slippage:number`（百分比、缺省1.0）及`chain_out`（缺省base）。本轮只选Base既有资产，不调用其跨链、杠杆或token launch服务。
- 声明使用BondingV5/LiFi，资金在agent wallet或client提供；输出文字承诺hash、输入/实收、route、实际滑点、gas、目标链确认和浏览器链接。仍缺明确receiver和fund-request语义，不能据单个返回hash认定本次已履约。
- detail SHA256 `6d298bcd923441c8086b396db89f96f616b4e8b51b3c9cd3f5b85807c0b87aa2`。没有本项目旧拒单历史。

### ArmaBase：Base #60504线索与普通swap

- UUID `019fbb50-31de-7e2f-be3b-2225023960b3`；钱包`0x12b5d81cdbe234de287cf45061f5e56f3ceb37dc`；[详情](https://api.acp.virtuals.io/agents/019fbb50-31de-7e2f-be3b-2225023960b3)、[注册正文](https://api.acp.virtuals.io/agents/019fbb50-31de-7e2f-be3b-2225023960b3/erc8004)。
- `Instant Token Swap` offering UUID `019fc942-c56c-70e9-a6ba-cd38f48ab31e`；文字要求from ticker/address、to ticker/address、amount；交付hash及confirmed swap receipt。普通服务0.12，不需要ARBA/ARRB；holder跨链服务另列，不作为本轮入口。
- Base #60504正文自报owner`0xfaf7e67d3c5093e520c9c8e81096d0f0356d09c4`，与Clawpump不同；同样把agentWallet错误填入agentRegistry。可信身份待root通过标准Registry核，不把错误字段静默修成已证明。
- 正文SHA256 `57a652995ab8b581a7c5d346a3f0dfc4705f1e646d6001c5015af6836c7e3c13`；detail SHA256 `db1710f3fe3eef469d4fc12ec2a0b7726df5cdc4ffe1d0f0b228b43b2172bb69`。没有本项目旧拒单历史。

### OUWIBO AGENT：保留低成本线索，先补两腿语义

- UUID `019ecd07-1c8a-7825-a3eb-a034bdec1d36`；钱包`0xd541377317bc23e09603aebbddffc0ec9c15f1e4`；Base ERC8004字段null。[官方详情](https://api.acp.virtuals.io/agents/019ecd07-1c8a-7825-a3eb-a034bdec1d36)。
- `token_swap` offering UUID `019ecd28-b698-7083-a709-2299abd5827d`；requirements原文`token, amount, chain`、deliverable`tx_hash`，声明1inch/Jupiter DEX swaps。当前不能确定是否支持精确USDC→WETH、收款者或滑点。只允许调查该swap，不选择其contract_deploy、nft_mint或钱包管理等其它产品。
- detail SHA256 `5bee03afb210a0c9622274f75b0eedac9dae280973dda65188abb13ba10583b2`。没有本项目旧拒单历史。

## 备选与明确不重复路线

| 对象 | 新读事实 | 当前动作 |
| --- | --- | --- |
| Woodie `019f41fb-dd54-7b77-94d4-92327c0ea375`，钱包`0x5e8f2599169a9f1d088165076aa323b6ce6623ce` | `sherwood_swap`为Robinhood4663，必需action=`swap_execute`,token_out,recipient；金额ETH缺省0.0005/最大0.002，费用实时USD+5%，挂牌1USDC；交付tx；ERC8004缺 | 比Base方案增加链/RPC及资产准备，待主线阻塞时再评估；不能当BaseUSDC/WETH现成复用 |
| SolProbe `019ddf5c-62c0-706d-a3c2-99c6e08a5388`，钱包`0xb5e3251a6ae029cd237dc64ee3e9544f46796164` | `sol_trade`0.15/5分钟，非托管Jupiter Ultra unsigned；输入input_mint,output_mint,taker_wallet,amount_lamports，可选slippage_bps/max_price_impact_pct；交付request_id/unsigned_transaction_b64和后续tx_signature/slot；官方pairs/currencies资源齐 | 是真实不同链路线，但需确认既有Solana资产/权限和独立核验器，不能拿EVM付款钱包冒充Solana执行钱包；本轮不碰钱包 |
| DevOps Butler `019d75e5-4df2-7449-8f9c-3e6fed031c05` | `swap_execute_guard`0.35/20分钟/true，有from_token,to_token,amount及可选recipient/max_slippage；免费quote仍HTTP裸IP；`swap_preflight_check`文案free而挂牌0.02 | 旧缺项未变，不重复裸IP请求，不为免费文案直接付款；ACP执行可作为次级候选，但交付仅json-string及成本无优势 |
| b402 `019d97f2-5a75-7c92-b55d-bc258a7d0d5a` | private_swap0.5/5分钟/true，requirements和deliverable都为空；声明Railgun隐私与输入输出不可直接关联 | 缺确切任务/输出契约和可独立绑定执行证据，当前不启动实验 |
| Eiko `019f0d04-72a4-7273-8609-6c2d585ec872` | ETH/BTC期权RFQ，BUY/SELL、position/optionAddress/settleTx/transferTx声明具体 | 可能涉及新期权合约/头寸发行，未证明满足禁止部署/发币边界；当前不调用，不以低0.01挂牌绕过业务红线 |
| VEGETA/iCLONE | swap_base输入、退款文案和cloneframe来源高度重合，已有未回复/过期任务 | 不以两身份凑新提供方，不重试旧失败路径 |
| Nox、Ethy、ZeroAgent、GSB、BridgeKitty、N9T2 | 既有无回复/拒单及缺项已记载 | 不进行新的相同探测 |
| Spraay Batch Agent v2 | 同Mango/Spraay现有品牌和执行来源 | 不计新增独立提供方 |
| Tator | 普通EOA费用已发生后HTTP500 `API keys not configured` | 维持暂停，不再付款猜provider参数 |

Topaz、Silverback等direct路线由另一只读任务调查，本任务不重复读取。

## 可复用能力与进入实验的边界

unsigned组（SafeRoute、TheSafeRouteBot、已发布Hydrex）可复用现有`decode_unsigned_swap`及独立固定块效果、真实receipt/asset/allowance核验。每次必须绑定原输入、实际交付hash、递归最早期限及同一买方；报价费用不计B。返回不同协议时先按协议适配，不按Agent名称打分。

provider执行组暂只有Pinchy明确包含minimum-output输入，DevOps提供slippage和recipient；Clawpump/Simon/Opet/Arma/OUWIBO还没有两家同时证明精确本金、指定收款、最低到账和已同意任务的完整契约。可以由root在冻结共同任务后采用现有ACP询条款/建单路径补证；本次没有将这些缺项当作永远不能评分。原始需求按服务真实Schema发送，文字模板不应伪造为提供方承诺的严格JSON Schema。

共用ACP协议证据可以是：冻结task_id/provider UUID/wallet/chain/offering/原始requirement → `GET /jobs/8453/{jobId}`与`GET /chats/8453/{jobId}/history` → 可信ACP合约的JobCreated/Funded/Submitted及原交付keccak → 原交付明确指向的资产执行交易 → 相同任务窗口内的真实sender、receiver、router/token事件、精确输入/最低输出/实际到账/确认数。provider钱包是任务对手方，不自动等于实际执行钱包；若其使用其它EOA、智能账户或内部钱包，必须用该任务材料和链上效果证明关系。不能拿资金转入、ACP手续费或无关成功交易填B。

30任务扩量应在至少两个同模式对象补齐必要契约后冻结共同场景：双向、金额档、最小到账/滑点、缺省值及可验证拒绝边界。只有服务声明支持的场景进入分母，不把本地decoder负控算实际业务任务；不通过重复同一路线或只看目录200刷样本。此文只是候选资格调查，没有冻结或执行新的30任务计划。

## 实际命令与退出码

- `.venv/Scripts/python.exe runtime/candidate-expansion-goal-20261028-acp/discover.py`：exit1。网络采集3次均落盘，前2完整、第三total_timeout；随后控制台GBK打印emoji失败。完整原件与`directory-agents.json`已在打印前保存；仅改打印为ASCII转义，没有重新联网。
- `.venv/Scripts/python.exe runtime/candidate-expansion-goal-20261028-acp/details.py`：exit0；12次定向读取均完整200，保留全部原文和SHA。
- 本地JSON/完整性检查结果见同目录`review.json`。工程测试NOT_RUN（只读研究）；业务实验、钱包调用、签名、付款、真实兑换均0。本任务不修改PLAN/STATUS、生产代码或评分，由root汇总当前目标和交付状态。
