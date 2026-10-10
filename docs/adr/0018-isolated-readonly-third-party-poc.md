# ADR 0018：隔离的免费第三方只读 PoC 出口

日期：2026-10-10；范围：后续任务 7。正式平台默认仍仅接受受控回环 HTTP，不开启注册地址抓取或任意公网目标。

单次调查脚本显式使用 `SafeHttpClient.readonly_poc()`。目标固定为官方 GitHub raw/API、Akashi Notari、Base 公共 RPC；资料路径、已核实源码 SHA、GET proof 参数、MCP 方法和 RPC 方法均使用精确白名单。MCP 仅发现及 `find_proof`；RPC 仅链、交易、回执、块及最多 2000 块的定址日志查询。登记身份查询只允许指定 registry 的 `ownerOf/tokenURI(98097)`，不作为正式身份适配器。

禁止付费 anchor、支付工具、任意 `eth_call`、发送或签名交易、任意 RPC、跳转和认证/支付 headers。MCP session/protocol headers 严格限定；响应仅保留 content-type/session-id，不重放服务端 Cookie。TLS 保持验证，不继承代理，无自动重试；单次总超时 20 秒、body 上限 1 MiB。PoC 保留受限原始 JSON、文本或 SSE，由独立调查脚本解析及归因；默认平台严格 JSON 和 15 秒行为不变。合约 code 读取也仅限已从官方源码核对的两个存证合约及该身份 registry。

遇到 HTTP 402，立即关闭该客户端的后续请求并保留状态，付款响应 body 不读取；调查记录明确 `body_not_read`，不能把未读取误称远端空响应。现有 Observation 新字段有默认值，原调用兼容。只读 PoC 的实测结果、身份验证状态及外部限制分别记录，不转成正式评价分数。
