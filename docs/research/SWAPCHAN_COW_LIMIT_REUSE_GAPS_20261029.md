> 历史调查记录：2026-10-29用户已取消十对象目标。本轮四对象完成后停止新增实验，下文候选不再继续请求、付款或适配；当前状态以README和STATUS为准。

# SwapChan CoW limit：既有原件与最小通用适配缺项

2026-10-29，离线审核。Ophis 当前已 pin 的 operator、signer、protocol 与三份不可执行 snapshot SHA 均相等；本次不修改它们。Ophis 首轮可按既有 DRAFT-v2 审核后另存真实 FROZEN plan 起步，仍须 fresh quote、资金、TTL、nonce 和实际履约核验。根先完成 Hydrex 发布，再决定本节适配顺序。

本次没有新候选搜索、HTTP/RPC、wallet/key 读取、签名、提交或资金操作；没有生成正式 source/评分报告。只读取已经保存的公共原件，并调用现有纯 CoW 协议函数核对 unsigned Order。

## 已证事实

- 官方公开服务引用：`mcp-registry:io.github.TSavo/swapchan@0.3.0`；remote 为 `https://mcp.swapchan.com/mcp`。既有 proof：`runtime/next-reusable-trading-services-20261029/identities/swapchan/registration-proof.json`。这是独立 MCP 公开服务登记，不据此声称 ERC8004 链注册或独立组织归属。
- 真实免费构建原件：`runtime/next-reusable-trading-services-20261029/phase2/swapchan-limit.observation.json` 与 `.response.bin`。HTTP200、完整 body，原 response SHA 在本次离线读取中一致。
- 原 MCP 请求为 `build_limit_order`，Base8453；owner 为现有 EOA `0x176501c795dbc31259bb86a49eb8a88ff2298b85`，卖 `0.1` USDC、最低收 `0.00003` WETH，`expiresInHours=0.1`。请求单位是 human decimal，响应 typed Order 单位是 raw；已知 USDC6/WETH18 对应 gross100000、minimum30000000000000。
- 响应包含完整标准12字段 EIP-712 Order，domain 为 Gnosis Protocol/v2/Base8453，Settlement=`0x9008d19f58aabd9ed0d60971565aa8510560ab41`，approvalSpender=`0xc92e8bdf79f0507f65a392b0ab4667716bfe0110`。receiver 与 owner 同址、sell/FOK/ERC20、signed feeAmount=0、无 hooks。
- 精确 appData 为 appCode=`SwapChan`、orderClass=`limit`、version=`1.4.0`；partnerFee 是对象，volumeBps=10、recipient=`0xeb0eC7a28E4B6B175806E21D9D3afE45792C5c7B`。这些是该响应数据；没有套用 Ophis 的来源字段、数组形状、1bp/99bp 费率或收款地址，也未把10bp称为全部成本。
- 用该服务自身 appData 策略和原请求独立金额，现 `inspect_cow_order` 纯函数可核 domain/type、全部 Order 字段、精确 UTF-8 appData hash、gross/minimum/receiver/expiry，并得到 unsigned UID：`0x2bb47f426fb0d1ae1512aa6ff0e20926e60b8b2060bdfce8938b549aebb9b090176501c795dbc31259bb86a49eb8a88ff2298b856ae2945c`。该 UID 没有签、提交或成交。

该构建只有360秒有效期，不能作为后来执行的可签旧单；将来若执行必须先冻结独立意图并 fresh build。响应 `marketBuyAmountFormatted=null`，没有可用于判断市场改善或 quote-derived slippage 的市场基准。最低值来自本次显式 limit 请求，不能补造市场报价。

## 不能仅换映射就运行当前 Ophis pipeline

1. **通用 MCP envelope。** 此 body 是 SSE：一个匹配 JSON-RPC id 的 message，content 为一份 JSON text、image、两个 resource_link。当前 CoW collector/report 只接受直接 JSON 及单 text，不能处理该原件。未来可增加明确的通用 JSON/SSE envelope 规则，选唯一业务 JSON text、保留整份原 bytes/SHA；附属图片/展示指令不改变计划，不下载或执行资源。该规则不能按对象名分支。
2. **显式 limit 闭集 flow。** 此服务直接构建 limit Order，未返回 `quote → build → validate` 三阶段。当前 operator 的 `order_material`、signer 的三阶段原件核验及 report 的 minimum 推导依赖这三段。未来若根选择实现，应由冻结 flow/minimum_rule 区分 quote-derived 与 explicit-limit，独立绑定 human→raw、owner、gross/minimum、TTL 和各字段来源；不得伪造 quote、validate 原件或把未声明的工具算 PASS。
3. **提交 transport。** 既有 `phase1/swapchan-tools` 声明没有 `submit_order`；构建结果指向 `POST https://api.swapchan.com/limit/submit`，body 为 chainId/owner/order/signature。当前 operator 只允许声明的原生 MCP write tool，不能把该 REST 入口假装为别的 MCP 工具。后续需经根审核的固定 REST submit/UID-response 数据配置，仍只提交原 Order/签名/UID 一次，私有 signed request 不进入公开 source。`cancel_limit_order` 也只是生成 OrderCancellations typed data，不代表实际取消已发生。

可直接复用的是现标准 CoW Order/UID 密码规则、已有 EOA 签名原语、精确 VaultRelayer approve、可信 Base deployment/getters、独立 order/trades、canonical Settlement Trade/净资产、64块与 allowance0规则。public orders/trades 使用既有官方 Base CoW binding；本次归一化使用该独立已审 API host，没有冒称它由 build 返回。

appData 的费率、收款、来源和 orderClass 继续放冻结数据；不同合法服务不能因 appCode 或 partnerFee 形状不同而被普遍拒绝。尚未独立核验 SwapChan REST 接收、solver 可成交性、费用结算、撤单或真实资产结果，不能计 B。公开 remote 的角色目前是交易构建工具服务，不宣传为已经自主执行的钱包 Agent。

## Ophis 当前最短续跑清单

冻结时复制 `plan-draft-v2.json` 到新 plan，设置真实 FROZEN/时间并重新计算 SHA，保留旧草案。设置 `REPUTATION_COW_PLAN`、`REPUTATION_COW_PLAN_SHA`、`REPUTATION_COW_TASK_ID`、public Base 与既有 DoH 配置；签名器使用新的 `REPUTATION_COW_SECRET_FILE`，不是旧 pilot 的 `REPUTATION_OPHIS_SECRET_FILE`。C01只导入原 pilot，不重采。

C09–C30只 collect；实际 C02→C08逐项 `collect/prepare → prepare-approve/签/发/proof → order-readiness/签 Order → submit → 原UID proof`，到64块及 allowance0再下一项。缺资金、open order、旧 allowance、TTL 或未知写状态都先对账，不能换 UID 重签/重发。余额/surplus 独立准确性与 native submit 的公开绑定仍 UNKNOWN。当前 CoW report 的旧任务 freeze-clock 继承尚未像 unsigned 实现 append-only lineage，后续补 case 不可直接重设旧任务冻结时间。

本次没有修改已 pin 源码、冻结数据或运行旧 suite；纯 unsigned 解析检查 exit0，不构成新业务样本或实际履约。
