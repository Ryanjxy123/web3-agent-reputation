# 官方公开服务身份接入

2026-10-29。目标仍是10个交易Agent、每个至少30真实任务；本项完成身份来源支持，不把目录核验或计划文件计为业务任务。

新增严格canonical reference `mcp-registry:<namespace/name>@<具体version>`与`acp:virtuals:<官方UUID>`。报告、候选和资料页沿现有字符串/nullable登记链字段兼容，无数据库表迁移。ERC8004原ownerOf/tokenURI核验保持。新公共目录proof的public_registry_verified=true与chain_registration_verified=false明确分开；链注册缺项为BACKGROUND UNKNOWN，不扣A/F/B。参考[ADR0034](../adr/0034-official-public-service-identity.md)。

MCP具体版本原件通过一次SafeHttpClient GET取得，显式proxy7897、pinDNS、操作者DoH IPv4 1.0.0.1，无API key、付款或钱包操作。[官方fi.ophis/mcp@0.2.0记录](https://registry.modelcontextprotocol.io/v0.1/servers/fi.ophis%2Fmcp/versions/0.2.0)返回200/完整，绑定remote `https://mcp.ophis.fi/mcp`。proof为 `runtime/public-service-identities-20261029/mcp-ophis-v020/registration-proof.json`，SHA256 `af8f278790320077775e25750a0a5fcb2b66f4c089a48f6e09822f60aca4b831`。未据此评价CoW协议、订单签名或真实成交。具体version服务记录用于证据固定；同一name的多个version/remote不能算多个独立Agent凑数量。

[TheSafeRouteBot官方ACP目录](https://api.acp.virtuals.io/agents/019eb95d-2e16-7ea6-80fd-384434761336)绑定UUID、provider钱包 `0xe4bce29bc099e2a04369f6a2df98dc7d5eac2ac7` 与safe_quote。已有job82343官方job/history原件、真实receipt和canonical block，将提交事件与原deliverable hash核齐。proof为 `runtime/public-service-identities-20261029/acp-saferoutebot/registration-proof.json`，SHA256 `bfdbc96d0c957e234d7df970f74fb1d11a6746521d814065fe4048cab90a4c18`；provider_chain_event_verified=true，仍不声称ERC8004注册。该基线只是身份背景，不算新业务样本。

[SafeRoute官方ACP目录](https://api.acp.virtuals.io/agents/019fe1a3-ac02-7451-8253-50b4af6356cb)与x402支付钱包已有原件，但当前未找到它自己的真实ACP job/provider提交事件。目录和payTo相同不替代该事件，完整评分身份proof仍待root补齐。不是将其判为Agent FAIL，也不是认定以后不能评分。

dispatcher已接unsigned v1、campaign v2及atomic离线报告身份流程；ACP每个任务仍独立核provider、需求、链交付，MCP仅绑定登记remote，不自动扩展到其它REST origin。原worker不扩为任意联网发现；新引用不能进入ERC8004专用链解析。资料页明确公开登记与链注册未证，数据库防重绑覆盖新canonical。

首发前review追加chainId存在性要求后，同一必要离线单项补missing/wrong-chain反例复跑，最终1test/0.363s/exit0（原0.252s结果保留）；前端类型检查与构建exit0。原ERC8004 verifier委派、remote/version/offering/provider事件与source hash边界已覆盖。未重跑旧suite、未连接PostgreSQL、未浏览器验收；无新业务、RPC、签名、资金或权限操作。

## 两服务共用任务草案

`runtime/public-service-identities-20261029/trading-campaigns-draft.json` 为 **DRAFT**、frozen_at=null，SHA256 `1b5dd9fac74a50e83a1a7883d7a4eea504639ccd448288a14a50e6b1c74be7d6`。各30个独立未来UUID，20个正常双向兑换目标、4个输入校验目标、6个交易相关只读目标；正常兑换前8项是实兑目标，方向各4，不是已成交数。

最新只追加身份review：TheSafeRouteBot应使用 `acp-saferoutebot/registration-proof-v2.json`（完整前缀同本页身份目录），SHA `acbf0c71628277e1692553ce34a6a70ac03f2175bb1577d9dc4dc538699829a8`；它追加同endpoint既有真实chainId=8453原件，无新RPC。旧proof未覆盖，缺该存在性证据的初版不再作完整核验输入。新 `trading-campaigns-draft-v2.json` SHA `1149fac833e2dbd061193d8fed9d87a2d2ecb6cbef55d796f5488c1252ff7158` 仅更新该proof引用，仍DRAFT，30任务字典与原草案保持。

TheSafeRouteBot覆盖safe_quote与batch_screen两项声明。safe_quote_pro的签名尽调/EAS证明路径涉及当前报告/存证红线，未纳入或调用。SafeRoute覆盖safe_token_swap_quote、wallet risk facts、token risk facts及transaction preflight四项声明；preflight只分析无签名ERC20 calldata，不发送交易。风险GO/CAUTION等意见不当作独立真值，oracle、honeypot及链事实需要root固定块来源；辅助功能未有独立checker前保持UNKNOWN。

草案按各自真实schema传raw或human数量，未强行给SafeRoute添加其没声明的50bps参数；B执行仍需独立最低到账、完整原payload、净资产和授权清零。目录挂牌服务费估计分别2.40/0.42USDC，仅是旧快照名义估算，不是费用上限或已发生开销，root须在真实条款/当前准备中核实。SafeRoute短TTL、身份缺事件、客户端schema阻断等真实限制如实保留，不靠重发、费用或模拟补B。

两者是不同官方服务UUID/钱包，草案不推断组织或后台独立性；总体候选去重仍由root审查。root确认身份、同意任务分母、只读判据和资金顺序后另冻正式版本；本草案不授权dispatch，也不产生60个已采样任务或总分。

另按root冻结的A38真实原件补齐atomic已知非法输入的typed 5xx校验负例：一次定向1test/0.002s/exit0，未改冻结请求、阈值或A33/A34 UNKNOWN，见ADR0032。atomic exporter已补收observe-rpc中的历史固定块模拟，不把它当真实执行。
