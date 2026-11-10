# ADR-0034：官方公开服务身份与链注册分开核验

状态：本轮新增来源范围。评分、30/40/30、共享任务Schema、旧ERC8004证明及已发布结果保持。

## 边界与兼容

公开登记Agent不必拥有已证ERC8004身份。EvaluationReport、候选和数据库reference原本就是字符串，AgentProfile.registration_chain_id已允许null；因此只扩core的严格reference解析，不增加共享字段或迁移表。新canonical为`mcp-registry:<namespace/name>@<具体semver>`与`acp:virtuals:<官方UUID>`。不接受latest、任意官网URL或以钱包冒充注册ID。旧eip155/8004scan归一化不变，原registration_discovery只处理eip155，原verify_registration_proof继续验证ownerOf/tokenURI。

新public_service_identity是离线证据核验及dispatcher，不联网、不读密钥、不签名。返回public_registry_verified、chain_registration_verified、provider_chain_event_verified独立事实。公开proof的registration_verified保持false，防旧调用者误称链上注册；链注册缺项以BACKGROUND UNKNOWN说明，不加入A/F/B分母。登记服务身份、ACP provider和买方执行钱包是不同角色。

## 官方来源

MCP要求官方registry精确GET `/v0.1/servers/<URL编码name>/versions/<version>`原观测与正文、具体name/version、官方active发布元数据及原record列出的HTTPS remote一致。搜索latest或普通官网自声明不能代替该记录；当前支持streamable-http/sse remote。Ophis真实原件为`runtime/public-service-identities-20261029/mcp-ophis-v020/official-version.*`，精确fi.ophis/mcp@0.2.0；没有据此声明CoW订单或链上身份已核。

ACP要求官方GET `/agents/<UUID>`绑定UUID、非零provider钱包及唯一offering；同时核官方job/history与可信Base ACP合约的真实canonical JobSubmitted、provider主题、job ID及原deliverable keccak。操作者配置固定可信RPC，proof不提供任意RPC。基线事件只是身份背景，不算新的业务任务，也不替代每个评分任务自己的需求、交付与资产证据。当前已核TheSafeRouteBot job82343；SafeRoute仅目录/x402钱包一致而缺ACP事件时，不制造该事件或给完整评分身份proof。

ACP事件原件必须包含至少一个成功eth_chainId=8453，所有成功chainId原件都须一致；仅目录标注Base或只有header/receipt不够。首发前review补齐该存在性守卫，复用同一ZAN Base endpoint的既有真实chainId读，初版proof保留，正式使用registration-proof-v2。

proof的source_refs必须覆盖原HTTP/RPC观测及正文，正文hash、GET URL/方法、响应完整性及链块绑定逐项重放。只保留本地配置/自写目录而无官方观测不可通过。与现有证据系统相同，这依赖操作者保留的官方HTTPS/RPC观测；不是服务器签名的TLS证明，不把目录描述当代码指令。

## 接入与不变性

unsigned v1、campaign v2和atomic报表共用dispatcher；ERC8004仍委派原函数，原owner约束和服务绑定保持。ACP另核公开provider钱包与实际任务provider一致；MCP只绑定其remote，不自动推导其它REST origin、支付钱包或执行钱包。资料页公开身份的登记链为null并明确“链注册未证”。数据库防重绑覆盖新canonical，公开包沿既有normalizer校验；不扩大自动联网worker或任意合约能力。

atomic exporter补收observe-rpc与prepare-rpc中的真实simulation source-item，按原观测时间选择，execution仍只从proof取；quote-only不会由此成为真实成交。

## 验收与限制

单项离线验收使用官方MCP具体版本、真实ACP目录/job/history/receipt/header原字节，覆盖remote、版本、offering、provider事件和hash边界；原ERC8004 verifier委派及严格reference也核对。链注册false不会成为A/F/B FAIL。数据库实际写入、浏览器及新的Agent业务采样不在本项验收中；公开登记proof不能替代交易协议适配和真实履约证据。
