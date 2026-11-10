> 历史调查记录：2026-10-29用户已取消十对象目标。本轮四对象完成后停止新增实验，下文候选不再继续请求、付款或适配；当前状态以README和STATUS为准。

# 下一批可复用交易 Agent：资格核查

2026-10-29。本轮只读核查，主线仍由 root 先完成 Hydrex。没有改生产代码、PLAN 或 STATUS，没有读取账户秘密、付款、授权、签名、提交订单或发交易；没有新增正式评分对象。原件集中在 `runtime/next-reusable-trading-services-20261029/`，逐请求路径、正文 SHA 与状态见 `REVIEW_RECEIPT.json`。

实际 42 个 HTTP 请求：33 个 200、4 个匿名 MCP 初始化确认 202、1 个 401、1 个初始协议 400、1 个 404、2 个 TransportError。HTTP 阶段数不算任务样本，更不算成交。全部经过 SafeHttpClient、显式 HTTP 代理7897、pinDNS 和 DoH1.0.0.1。匿名 MCP 协议会话不是钱包登录，不曾调用账户授权、凭据创建或钱包工具。工程测试 NOT_RUN：没有生产行为变更；只对真实原件做身份/ABI核验。

## 建议顺序

优先 **SwapChan 的 CoW 限价订单**，其次由 root 核 **Vurto 的 Kyber 授权后方案**。两者能直接复用现有 CoW/Kyber 取证思路。MemeSwap 已取得真正的零 value 双 ERC20 LI.FI 方案，提供下一个共用协议方向；HostDeFi 先由 root 决定是否按其真实 x402 要求取得一次方案。不能把四条线索称为四个已完成三维评价的 Agent。

| 对象、准确登记与服务 | 已取得的真实结果 | 根后续与边界 |
| --- | --- | --- |
| **SwapChan**：`io.github.TSavo/swapchan@0.3.0`；`https://mcp.swapchan.com/mcp` | 官方具体版本和66项工具声明均200；免费 `build_limit_order` 返回完整 Base CoW EIP712 Order、appData、relayer和提交方法；另一次普通 swap build 返回1inch unsigned交易 | 首选 CoW 共用规则；该对象完整订单没有提交过。正式采样先冻结它自己的声明、参数和费用。大小写身份解析缺口待 root 通用修正；不要将官方 `TSavo` 偷换小写。 |
| **Vurto**：`io.github.cryptoconspiracy/vurto-swap@1.0.0`；`https://swap.vurto.cc/mcp` | 具体版本/工具/报价/build均200。Base USDC100000→WETH报价有8个提供方；fresh build选Kyber，最低42252492711595 raw WETH，披露3bps费用 | 当前仅返回精确approve100000给Kyber，并明确 `simulation.status=approval_required`；还没有可执行swap calldata。root 如继续，先审核精确授权，再用该build的quote.id/refresh续取同路方案并独立模拟，不能把approve当成交。 |
| **MemeSwap**：`fun.memeswap/trading@0.2.1`；`https://mcp.memeswap.fun/mcp` | 准确版本200；按服务器明确要求完成匿名MCP初始化后43项工具可读。取得正常ETH→USDC Kyber unsigned build；又按官方OpenAPI取得 **Base USDC100000→WETH的零value LI.FI方案** | 双ERC20优先保留零value LI.FI线索，不为对象名字写native适配。LI.FI当前facet/代码、可变白名单和完整固定块效果仍需核；下单前重新冻结新任务、取得有效方案。原ETH→WETH wrap build503保留。 |
| **HostDeFi**：`io.github.verixiaapps/hostdefi-x402@1.3.1`；`https://hostdefi.com/api/v1/mcp` | 具体版本、15项工具和免费价格目录均200；明确 `swap_evm_quote` 生成自有钱包的Kyber交易方案。精确Base USDC100000→WETH/自有SMA请求返回HTTP200内的业务status402与付款要求 | 服务费0.01USDC/次，另声明交易内1% native平台费；尚未付费或得到swap payload。不能猜它一定value0，也不能将付费要求当实际功能兑现。 |

这些是不同准确注册记录与服务入口；没有把同一对象的主路、跨链路或背后的DEX各计一个Agent。官方服务目录核验不等于ERC8004链注册或独立运营信誉证明。本轮未核得四者的链上注册身份，保持背景 UNKNOWN，不扣A/F/B。Vurto、MemeSwap、HostDeFi 的数据型 proof 已通过现有公开身份核验；SwapChan proof保留原件，但当前机器核验因大小写限制未过。

## SwapChan：同一 CoW 判据可复用

原件 `phase2/swapchan-limit.*`：`chainId=8453`，owner/receiver均为现有自有EOA `0x176501c795dbc31259bb86a49eb8a88ff2298b85`；sellToken为Base USDC，sellAmount100000，buyToken为WETH，buyAmount30000000000000，kind=sell，partiallyFillable=false，feeAmount=0。Settlement为已独立审核过的 `0x9008d19f58aabd9ed0d60971565aa8510560ab41`，relayer为 `0xc92e8bdf79f0507f65a392b0ab4667716bfe0110`。

同一 `inspect_cow_order` 对这份真实返回的12项Order字段、EIP712域、接收者、原始UTF8 appData/hash及请求时间窗做离线核验通过，投影在 `swapchan-cow-projection.json`。这是回顾性资格核查，不是预先冻结的评分样本，不证明已签名或已结算。返回appData实际披露partnerFee10bps；未把它冒充事前已知的声明费率，后续必须先固定费用约定。签名提交入口由服务返回为 `https://api.swapchan.com/limit/submit`；提交后仍须到CoW原始订单/Trade事件独立核UID与净资产。

另一份 `phase2/swapchan-build.*` 返回1inch router `0x111111125421ca6dc452d289314280a0f8842a65`、selector `0x07ed2379`、精确USDC授权和自己的SMA收款；simulation明确skipped。现有评分器尚无该1inch模式，不必为了它另起对象专用分支，优先已取得的CoW路径。

## MemeSwap：双 ERC20 零 value 与费用原件

主 `quote/build` 声明只有 `side=buy/sell` 和单token；官方OpenAPI明确buy金额以native计，不能猜成任意ERC20输入。其 `xquote` 则明确支持source/destination token地址与链标识，返回LI.FI unsigned材料。来源为官方帮助所给的 `https://memeswap.fun/openapi.json`（`phase10-memeswap-api/openapi.*`）。

一次精确 `GET /api/xquote` 使用fromChain/toChain均8453、USDC→WETH、amount=0.1人类单位、slippage=0.005，from/to均为现有自有SMA。`phase11-memeswap-erc20/usdc-weth-xquote.*`返回：

- `transactionRequest.chainId=8453`，from为自有SMA，`value=0x0`，to为LI.FI Diamond `0x1231DEB6f5749EF6cE6943a275A1D3E7486F4EaE`，selector `0x5fd9ae2e`。
- 输入100000 raw USDC；预期41948508894233、最低41738766349761 raw WETH。
- `feeCosts.amount=1100` raw USDC、`included=true`，明确分为LI.FI250和MemeSwap850；余下98900进入兑换。这是输入内扣费，不是额外native充值或“无费用”。gas仍另外支付。
- 此selector对应已有官方源码资料中的 `swapTokensMultipleV3ERC20ToERC20`；可复用先前LI.FI外层ABI研究，但当前Diamond/facet/fee collector/内层路由及独立净效果未完成，不标成交或已具金融执行资格。

旧的ETH→WETH wrap路径quote200、build原生`isError=true`/503，说明85bps费用未进入该wrap路由，不能只看HTTP200。另一正常ETH0.00004→USDC路径完整build成功；`memeswap-native-kyber-projection.json`静态解码为自有收款、minimum92847、value=input40000000000000wei、fee85bps在currency_in内扣，flags0x280含现decoder未认可的0x200位。该路径不在当前zero-value/ERC20执行边界内，没有绕过门禁执行它。

## HostDeFi：付款要求已具体，不代付

`phase5/hostdefi-payment-requirements.*` 是对精确Base USDC100000→WETH/自有SMA的第一次请求。Base接受项为x402 v1 `exact`，资产USDC `0x833589fcd6edb6e08f4c7c32d4f71b54bda02913`，maxAmountRequired10000，payTo `0x60D631095fBe251e8158422a3EF678CD0dc596Fb`，resource `https://hostdefi.com/api/v1/x402/swap/evm/quote`，maxTimeoutSeconds60。没有支付、创建账户、购买API key或绕过付款。即使root取得方案，公开声明的1%native费也需在实际calldata/value中独立验证。

## 已关闭的低收益缺口

- SwapWizard准确登记/工具可读，真实quote401；官方setup guide明确需要钱包SIWE取得integrator API key。已停该host，不反复匿名请求、不替用户登录或读秘密。
- datasnag DeFi Router虽准确登记/工具200，实际只暴露行情/安全/桥接分析，未给swap-build入口；不因“autonomous router”简介就当可成交对象。
- Uniswap Junct与Tenzro两个准确登记200，但各tools/list为TransportError；未重试、未猜工具名。
- Tollbooth准确登记200，remote404 Application not found；停止。
- MemeSwap首次tools/list400明确要求先initialize；只作标准匿名协议协商，未创建钱包登录会话、社交账号或凭据。没有执行其工具列表中任何增长/推广/发帖/地址生成等动作。

后续先冻结可复用的任务与费用，再由root单序列取新有效方案、签发和对账。旧资格原件与失败不覆盖，私钥、签名和提交请求仍只在本地私密操作目录。
