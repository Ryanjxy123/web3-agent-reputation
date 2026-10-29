# Cleave unsigned 方案：外层可核，executor 仍待绑定

本次单独授权的定向审核只做 4 GET，均 HTTP200：BaseScan 指定地址页、Cleave 官网、官网链接的 `/docs`、文档链接的 `/docs/safety`。没有 RPC、钱包、密钥、付款、签名、提交、链写或新业务请求。原件、派生 ABI/源码文本与投影在 `runtime/cleave-protocol-review-20261029/`。此前发现阶段的12请求单独结算，没有继续广搜。

BaseScan 页面明确标记 Source Code Verified / Exact Match，源码名为 `CleaveSwapShell`。独立按 ABI 计算：

`swapWithBlob((address,address,uint256,uint256,uint256,address,address,uint16,bool),bytes)` → `0xab33b1ec`。

这是自定义 Shell/executor 协议，不能当成已有 0x AllowanceHolder、Kyber 或标准通用 router。可复用已有 ERC20 资产净变化、精确授权、canonical receipt、确认窗口等公共核验；route blob 需要独立协议支持，不写单 Agent 给分分支。[对应 BaseScan 代码页](https://basescan.org/address/0xb08F28a3575805ee1E3729fc19Ab7E869CBAF563)

真实方案 ABI 解码结果：

| 字段 | 真实值 |
| --- | --- |
| tokenIn / tokenOut | Base USDC / WETH |
| amountIn / minAmountOut | 100000 / 42591278921154 raw |
| recipient | 自有 SMA `0x73d642847cb9a3acef116ea207a74b9956c34a09` |
| referrer / referralFeeBps | zero / 0 |
| wethAsErc20 | true，保留 WETH ERC20，不走原生 ETH payout |
| calldata deadline / response validUntil | 1793214976 / 1793213836，采用较早的已知约束；方案已过期，未执行 |
| blob | version7，1633 bytes；其内部 schema 与 executor 仍未知 |
| approve | USDC approve100000，spender 为第二CALL同一 Shell `0xb08F28a3575805ee1E3729fc19Ab7E869CBAF563`，所有CALL from 自有 SMA、chain8453、value0 |

Shell 通过 `executorFor(blob[0])` 找 executor，直接 `safeTransferFrom(msg.sender, executor, amountIn)`，并要求 executor 输入资产余额增量恰为 amountIn。它围绕 executor 执行测量 Shell 输出余额增量，扣当前协议费和 referral fee 后再检查净 minAmountOut，最后转给 recipient。输出转账本身没有测接收者余额，因此真实 WETH 净增仍应独立核；事件也不能替代收款资产证明。

`FeeController` 源码上限为10bps，当前 `protocolFeeBps()` 可变且本次未读链。response `fees:[]` 不能证明当前协议费为0。constructor 页给出 controller=`0x5635c8e24d9cdb2892599267da74d971b8776688`、WETH 为 Base 标准地址、Permit2 为规范地址；本方案是普通 transferFrom 入口，不需要为此新增 Permit2 签名或授权。

精确 approve100000 在标准 USDC 成功完整 transferFrom 后应被消费，但本轮没有实际调用，剩余额度仍未知。Root 后续若审核通过，应把 post allowance=0 和必要清理纳入自己的完整测量批次，不把 approve 或清理当额外 Agent 履约。Shell 源码未对整笔方案承诺所有内部 allowance 清理，executor 还未审，不能提前给这个结论。

当前停止点是：未取得官方发布的具体部署表、固定块 Shell/runtime、当前 `executorFor(7)` 地址及代码、version7 blob 的 pool/factory/recipient/refund 规则、当前 fee state、完整模拟和实际 receipt。官方 safety 页说部署表在 `/docs/api` 的 Contract addresses，本轮4 GET已用完，未再读取。BaseScan已核外层源码并不代替这些部署/内层前置。[Cleave 官方安全说明](https://cleave.fi/docs/safety)

Quietwork 离线参数复查同时保存于 `PROTOCOL_REVIEW.json`：真实 `cow_build_order` schema 的链字段是 `chain`，枚举包含 `base`；本次请求精确填了 `chain:"base"`、官方 USDC/WETH 地址、human units `amount:"0.1"`、同址 sender/recipient、50bps，required 字段齐全。没有默认 Ethereum 或遗漏链字段。其原生 token metadata 错误来源未定，保留未取得有效订单的缺项；未重发 quote/build，不把声明可用写成业务已通过。

## 后续定向读取：部署声明已补，内部执行仍未知

Root 后续单独授权的3 GET均200：官网 `/docs/api`、`/docs/agents/discovery` 和 API 文档明确列出的公共 `/v1/meta`。此外只对 Quietwork 的另一种明确 unsigned 工具 `swap_build_tx` 做了一次免费请求。原件是 `phase4/`、`phase5/`，摘要为 `FOLLOWUP_REVIEW.json`。没有继续广搜、调用 RPC、读取私密配置或执行任何钱包动作。

官方 API 部署表明确把本真实方案目标 `0xb08F28a3575805ee1E3729fc19Ab7E869CBAF563` 标作 **Base Swap Shell (classic)**。公共 metadata 在精确 `chainId=8453` 行给出 executor=`0xd28baFa0865a0d74E8AE478AEc8F1bAa61767052`、blobVersion7、shareBlobVersion8，并声明相同的函数签名、selector 和 approvalSpender。MeasuredShellV2 是另一目标 `0x003d4C95756608Ed4C11C5d0Ad9ca4c4076cAF20`，不能混用。曾在即时简报中按数组位置误报的 `0x5741A1dD…` 属于 Optimism；正确投影按 chainId 选择，原 raw 与两条链实例均保留。此处是发布方部署声明，尚未以可信固定块 RPC 核当前 runtime/executor 映射。[官方 API 与部署表](https://cleave.fi/docs/api)

官方 Discovery 页声明 ERC8004 registry=`0x8004A169FB4a3325136EB29fA0ceB6D2e539a432`，Base agentId=1135050，列出同一 MCP remote 和公开 `https://api.cleave.fi/.well-known/agent-registration.json`。本轮没有再取该 JSON、owner/tokenURI 或链证明，因此只增加官方声明证据，不把既有 MCP 登记自动升级成链注册已核。[官方身份声明](https://cleave.fi/docs/agents/discovery)

metadata 给出了 executor 线索，没有给出可独立解释 version7 blob 的完整编码。executor 代码/route schema、pool/factory/refund 与中间余额约束仍未知；本轮到此停止，不据外层通过实现单对象评分器或发送旧方案。

Quietwork 这一次严格按已保存真实 `swap_build_tx` schema 发出：chain=`base`，USDC/WETH 两个官方地址，amount=`0.1` token units，sender=recipient=自有 EOA `0x176501c795dbc31259bb86a49eb8a88ff2298b85`，slippageBps=50，无额外 aggregator 参数。HTTP200，原生仍为 `isError=true`、相同的 token metadata 错误，未返回 target/selector/recipient 可核 payload。它是同一注册服务的不同功能，不计新 Agent，也没有重发该功能。
