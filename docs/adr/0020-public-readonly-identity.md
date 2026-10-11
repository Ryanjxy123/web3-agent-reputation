# ADR 0020：固定块 ERC-8004 注册与受限只读端点关联

日期：2026-10-11；范围：FOLLOWUP-09。延续 ADR0006/0019；不修改 EIP-712 executor binding、评分规则、充分度或历史报告语义。

## 决定

复用 AgentRef、SnapshotCore、AgentSnapshot、现有 ingest Worker、PostgreSQL 快照/证据/审计和 CAS。首个静态对象仅 Base 8453 / Identity Registry `0x8004a169fb4a3325136eb29fa0ceb6d2e539a432` / agentId 98097。开启需要操作者显式 `PUBLIC_READONLY_ENABLED=1`，默认关闭，不改变原 external-enabled 配置或受控流程。

复用已锁官方 commit `b9e466c250744a7e06b13dff9d3c2844ed64f825` 的 IdentityRegistry ABI，并检查实际文件 SHA256。可信 RPC 固定 `https://mainnet.base.org`，只允许 identity 的 chainId、block、固定注册合约 code、固定 token 的 ownerOf/tokenURI。先选择块，所有注册读取使用相同数字块，元数据前后复查块号和 canonical hash；缺失、畸形、重组或读取失败输出 UNKNOWN。RPC 来源由操作者配置，注册文件不能提供 RPC 或扩大 URL 白名单。

元数据 URI 仅支持已验证的 Akashi 注册路径；Owner/URI 改变保存为新观察，未知 URI 不被跟随。严格重复 key、大小、深度、类型、服务 URL、凭据和 registrations 复合身份检查；没有任意远程代码导入或描述文本能力推断。注册 x402Support 和其他付费服务属于声明数据，不能授权付款；OpenAPI 检查仅免费 `/proof.get`，HTTP 402、付款 headers 或所选操作付款要求仍立即停止。

PublicIdentityRead 附加记录 ABI、代码、可信 RPC 标识、源 CAS hash、注册/OpenAPI 原字节 hash 和解析声明。SnapshotCore 保存固定块/Owner/URI/规范化声明和候选端点；`verify_record` 是静态适配候选，仍需现有人工 claim review。标准没有受控 revisionOf/executor/deploymentInstanceId：公共快照 revision=0 明确表示没有链上 revision，declared_executor=null；chain deployment_instance_id 是 `erc8004-public-v1` + chainId/genesis/registry 的确定性域标识，不能解释为合约提供的部署标识。registry_code_hash 只承诺所读 bytecode，不宣称代理实现已锁定或行为可靠。

公共 snapshot_hash 承诺 `{core, public_identity}`；历史/受控快照仍仅承诺 core，public_identity=null 不序列化。原始元数据 byte hash 与规范化 metadata_hash 分开。现有只追加 snapshots.agent_fk 建立版本历史，刷新保存 previous_snapshot_hash 审计，不继承 binding。注册读取失败保存意图、响应、UNKNOWN 结果至 ingest job，Agent 保留 UNVERIFIED（没有成功快照时），不猜 Owner/URI/块或构造成功快照。完成标记前恢复复用已保存结果，不重新发送公共读取。

ReadonlyIdentityAssociation 将注册、端点、执行者和业务四个状态分别输出。MCP 精确核对注册 `/mcp`；HTTP `/proof` 还需注册声明的 OpenAPI 原件、服务器、GET 路径、安全/付款/覆盖字段和 hash。关联仅证明某固定块的注册声明指向所读服务，executor 永远 UNKNOWN/BINDING_UNVERIFIED，业务永远 UNKNOWN；它不产生 ExecutorBinding，不允许写入评价。原 controlled current_identity 对 public 快照显式拒绝。

## 兼容与验证

Endpoint 增加两个静态只读协议，原 controlled-http-v1 仍必须 POST；新增共享 DTO 生成 Schema/OpenAPI/TS，无 DB 迁移。公共请求沿用任务8的 DNS 全量校验、数字 IP pin、原 Host/TLS/SNI、串行/配额、超时/大小限制和零自动重试。抽取共用请求审计避免重复实现，任务8协议回归必须通过。

定向测试覆盖真实历史原件重放、恶意元数据/端点/凭据、RPC/ABI 畸形、固定块/reorg、Owner/URI/端点与版本变化、CAS/哈希篡改、UNKNOWN、只追加/租约恢复和写入门槛。真实只读验收与独立 Review、实际测试数字见 STATUS。正式任务执行、评分、Bundle 和独立 Verifier 接入属于任务10，本 ADR 不宣称完整评价闭环。
