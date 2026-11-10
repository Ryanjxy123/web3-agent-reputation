# Ophis MCP → Base CoW 订单：执行资格与独立取证

2026-10-29（北京时间）。结论：**Ophis 本身的免费 quote → build → validate 已真实可用；现有专用普通 EOA 可按其原生 `submit_order` 路线继续验证。尚未签单、提交订单、授权、付款或实际成交，不能计入 B。** 本文只定义协议绑定和操作者下一步，不是新增评分 adapter，也没有冻结 30 任务计划。

原发现包保留于 `runtime/candidate-expansion-goal-20261028-direct/ophis-handoff.json`，Ophis 官方 MCP Registry 身份为 `fi.ophis/mcp`、remote 为 `https://mcp.ophis.fi/mcp`。没有找到的 ERC-8004 身份仍为 NOT_FOUND，不补造注册。未核定第二个不同运营方的同协议公开 Agent，不把 SDK、CoW API 与 Ophis 多入口重复算成多个对象。

## 已执行的资格读取

新增原件统一位于 `runtime/protocol-cow-review-20261029/`；每个外部请求均经既有 SafeHttpClient、固定 HTTPS target 和受限响应大小保存 observation/body。仅 GET 官方资料和公开订单路由，以及明确免费、只读的 MCP quote/build/validate POST；没有 submit、approve、链写、签名、密钥或 keychain 操作。

| 原件 | 实际结果及意义 |
| --- | --- |
| `phase3/ophis-eoa-quote-small.response.bin` | 普通 EOA `0x176501c795dbc31259bb86a49eb8a88ff2298b85`，Base USDC→WETH，100000 raw USDC 总预算。报价 sell=98026、fee=1974、buy=41974592128008；`verified=false`。 |
| `phase4/ophis-eoa-build-small.response.bin` | 相同 EOA=receiver，signed sell=100000、fee=0、signed minBuy=41764719167368、FOK、ERC20 余额，validTo=1793205992。该 minBuy 由外部报价的 `ceil(buy×9950/10000)` 事先确定，构建请求未让 Agent 自行降低它。 |
| `phase5/ophis-eoa-validate-small.response.bin` | `valid=true`，errors/warnings 均空；核得 Base 的 domain、host、appCode 和两条 partnerFee。它是离线格式检查，不检查真实授权或 solver 成交。 |
| `phase6/cow-eoa-v2-trades.response.bin`、`cow-eoa-orders.response.bin` | 对公开 EOA 的 CoW v2 trades 和 v1 account orders 路由实 GET 均 HTTP 200；可用作后续独立观察入口，当前读取不证明任何新履约。 |

本轮只有上述 EOA 三阶段资格链；另保留一次 SMA 报价读取。早期尝试抓 Ophis 整仓 recursive tree 超过 2 MiB 上限，原失败 observation 保留，随后改读官方目录和必要源文件，没有绕过大小限制。

## 官方部署、资金与签名

Base chain ID=8453；GPv2Settlement=`0x9008D19f58AAbD9eD0D60971565AA8510560ab41`；VaultRelayer=`0xC92E8bdf79f0507f65a392b0ab4667716BFE0110`。ERC20 额度授予 **VaultRelayer**。Root 执行前仍需在操作者可信 Base RPC 的固定块独立读 chainId、二者 code、settlement.vaultRelayer() 和 domainSeparator()，不可只依赖 Agent 返回的地址。[CoW 官方部署](https://docs.cow.fi/cow-protocol/reference/contracts/core)

EIP-712 domain：name=`Gnosis Protocol`，version=`v2`，chainId=8453，verifyingContract 为上述 Settlement。当前公开 EOA 可签 `eip712`，也可选 Ophis 暴露的 `ethsign`；优先使用前者。签名恢复地址必须等于冻结 owner，提交 `from` 也必须等于该地址。`Order` 的 12 个字段、类型和顺序见保存的 build，不增删字段。EOA 的 signer 从签名恢复，不是一个可随便改写的 order 字段。[CoW signing schemes](https://docs.cow.fi/cow-protocol/reference/core/signing-schemes)

Ophis MCP 的 `submit_order` 实际 schema 仅允许 `eip712`/`ethsign`，不暴露 ERC-1271、presign 或 cancel；`from` 与 receiver 必须同址。其实现将完整 appData JSON 放入 API 的 `appData`，将签入订单的 bytes32 放入 `appDataHash`，再发往 `https://api.cow.fi/base/api/v1/orders`。这条 EOA 路线能测试 Ophis 自己的提交工具，不必绕过它。[Ophis MCP 源码](https://github.com/ophis-fi/ophis/blob/main/apps/mcp-server/src/ophis.ts)

SMA `0x73d642847cb9a3acef116ea207a74b9956c34a09` 仍可另走 CoW presign：本地先算 UID，同一 owner 调 settlement.setPreSignature(UID,true)，API 使用 `signingScheme=presign`、`signature=0x`、`from=owner`。合约检查 msg.sender 必须为 UID owner；API 空签名与 solver 合约内部编码的 owner bytes 是不同层，不混用。此路径不能标作 Ophis submit 工具已验证，当前优先 EOA，不继续猜 SMA 的 ERC-1271 编码。[GPv2Signing 官方源码](https://github.com/cowprotocol/contracts/blob/main/src/contracts/mixins/GPv2Signing.sol)

## 费用、最小输出与小额可成交性

**97885+2115=100000、signed fee=0 没有矛盾。** CoW quote 的 `sellAmountBeforeFee` 是可用于整单的总卖出预算，quote.sellAmount 是扣网络成本后的定价量；现代签署形式把 quote.sellAmount+quote.feeAmount 合为 signed sellAmount，并将 signed feeAmount 置 0。官方 SDK 示例明确如此转换。0 不代表交易免费，也不能把 quote.feeAmount 再加到 100000 的授权上。[CoW SDK 示例](https://docs.cow.fi/cow-protocol/reference/sdks/cow-sdk)

Ophis 对 USDC/WETH 使用两条 appData 费用：1 bp volume，以及 80% 的正向参考报价改善、最高 99 bp volume。后者不是固定再收 99 bp，也不是抽取 80% 本金；CoW 上游费用和 solver 网络成本另外影响最终报价，所以 **1+99 bp 不是本次全部成本上限**。本轮 0.10 USDC 报价的网络成本估计约 0.001974 USDC，不能因为 signed fee=0 隐去。[Ophis 费用](https://docs.ophis.fi/fees/)

实际 MCP build 会独立获取相同账户、金额和订单绝对 validTo 的新报价，再检查限价。已审源码的 backstop 为 `slippageBips + 所有 partnerFee 的最大 bps`；这里参数 50 加 1+99，内部拒绝阈值实为 150 bps。它不会改写调用方明确传入的 minBuy；评分仍应逐字段匹配冻结的最终 signed minBuy，并核实际净到账，不能把该 backstop 宣称为无费用的端到端 0.5% 保证。[Ophis build/限价源码](https://github.com/ophis-fi/ophis/blob/main/packages/sdk/src/order-build.ts)

当前 quote/build 成功说明 0.10 USDC 能取得正的有效方案；没有证据证明全网存在统一最低成交额，也不能据此保证 solver 会接该小额单。quote `verified=false`，余额、精确 relayer allowance、真实订单接收、限价及 solver 执行仍待采。若订单因成本、余额、授权或流动性被拒绝，保留具体错误；不要套用另一个 TWAP 产品的 $5 门槛，不降低 minBuy 或隐藏未成交。必要调整金额由 root 在冻结的新任务中明确执行。

## appData、UID 与不可重复采样

必须保留返回的 fullAppData **精确 UTF-8 字节**，不把 JSON 解析后重新排版再签；keccak256 必须同时等于 order.appData 和 appDataHash。当前 appCode=`ophis`，metadata.ophisSource.app=`mcp`，partnerFee 接收方=`0x858f0F5eE954846D47155F5203c04aF1819eCeF8`，无 hooks。fee、source、orderClass、slippage 元数据均受该 hash 承诺。后续 signer/fee/hook 的改变须重新审查、形成新订单，不能事后替换。[Ophis appData 构建](https://github.com/ophis-fi/ophis/blob/main/packages/sdk/src/order-build.ts)

`digest=keccak256(0x1901 || domainSeparator || hashStruct(Order))`；`UID=digest(32 bytes)||owner(20 bytes)||validTo(4 bytes, big-endian)`，共 56 bytes。task→请求→返回原件→经济字段→digest/UID 的绑定须在签名/提交前落盘；MCP 返回 UID 必须与本地 UID 一致。重复相同订单得到相同 UID，不能靠多次请求/多判据把一单计为多个真实执行样本。CoW 一个合法 settlement tx 可有多个不同 UID，不能把所有同 tx 的独立 UID 误拒为重复。[官方 UID 实现](https://github.com/cowprotocol/contracts/blob/main/src/ts/order.ts)

本地纯 helper：`runtime/protocol-cow-review-20261029/cow_order_facts.py`，只读输入、算 hash 和绑定，不联网、不取时、不签名。`offline-facts.json` 保存本轮实际 unsigned build 的 domainSeparator/digest/UID；六项受控负控分别改 owner、amount、appData 字节、domain、signed fee、deadline，均拒绝，命令 exit 0。该 UID **未签、未提交、未成交**。助手没有为本轮生成任何 txHash。

## 独立履约链与撤单

当前官方 OpenAPI 使用分页 `GET /base/api/v2/trades?orderUid=<UID>&offset=0&limit=...`，owner/orderUid 必须二选一；按页取完整结果。订单为 `GET /base/api/v1/orders/<UID>`。不能直接沿用老示例里的 v1 trades。核 owner、tokens、signed amounts、receiver、appData/fullAppData、validTo、kind/FOK、settlementContract、实际状态；trades 的 txHash/blockNumber/logIndex 是继续查链的定位，不是链上证明。[官方 OpenAPI](https://github.com/cowprotocol/services/blob/main/crates/orderbook/openapi.yml)

Root 后续原始链证据至少包括：

1. canonical tx/receipt/block、链实例和既定确认距离；receipt 成功及事件 emitter 必须为官方 Settlement。
2. 精确匹配 `Trade(address indexed owner,address sellToken,address buyToken,uint256 sellAmount,uint256 buyAmount,uint256 feeAmount,bytes orderUid)` 的 UID、owner、token pair 和事件位置。同批 tx 的其它用户或其它 UID 不归本任务。
3. 本范围 FOK sell、signed fee=0 时，单 UID 的事件总卖出须为 100000、buy 不低于冻结 minBuy；ERC20 Transfer 与 owner 的净 debit/credit 独立对账。固定块前后余额是整个窗口，额外资金移动须解释，不能替代逐交易归属。API 的 executedFee/executedProtocolFees 可解释动态收费，不能只用 event.feeAmount=0 宣称没有成本。
4. 收款人=owner、成交区块时间≤validTo、filledAmount 及真实订单状态一致；读成交后 allowance 并清理到 0。approve/清理 gas 属操作者费用，不属于被评 Agent 的兑换笔数。

上述事件及费用含义由 Settlement 原码和 API schema 相互核对；Trade.sellAmount 包括 signed fee，buyAmount 是交易交付量，现代 signed fee 为 0 时动态费用仍存在。[GPv2Settlement](https://github.com/cowprotocol/contracts/blob/main/src/contracts/GPv2Settlement.sol)

标准 ERC20 路径未预存本金，未成交资金留在 owner 钱包，**没有一笔需要虚构的“退款交易”**。CoW 的离线签署 DELETE cancellation 是 best effort，可能输给正在上链的 settlement；需要强失效时可由 root 对 UID 调 invalidateOrder，并核 OrderInvalidated/filledAmount。presign=false 仅撤销 presign 资格；仅将 allowance 清零也不永久作废 EIP-712 订单，后续重新授权前须处理有效旧订单。不能把撤单状态等同兑换完成或本金退款。[官方取消及订单接口](https://github.com/cowprotocol/services/blob/main/crates/orderbook/openapi.yml)

## Root 可以继续的步骤

先冻结 Ophis 的真实任务范围及判据，再用其声明的功能设计有区别的 quote/build/validate、sell/buy、方向、金额、有效期、滑点和拒绝案例；只安排必要真实成交验证，不用同参数重放凑 30。取消是 CoW 管理路径，不列为一个 Ophis 未声明的 MCP 工具。

普通 EOA 路线：确认钱包无未决 tx/订单并读可信部署及余额 → 精确批准本次 gross sell 给 VaultRelayer → 取得新鲜 quote/build，独立核 minBuy/appData/domain/owner/TTL → 本地持久化 task/digest/UID 后 EIP-712 签名 → Ophis submit_order 一次 → 未知提交先 GET 原 UID 对账 → 用 UID、v2 trades、原始 Trade/资产变化核齐成交或如实保留失败/未知 → allowance 清理。Root 负责所有实际操作；本研究没有执行其中任何授权、签名或发送动作。
