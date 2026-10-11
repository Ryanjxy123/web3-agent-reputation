# ADR 0019：正式免费只读 HTTPS/MCP 出口与协议适配

日期：2026-10-11；范围：FOLLOWUP-08。延续 ADR0018，不修改评分规则、历史报告语义、受控 Agent 契约或默认公网关闭状态。

## 决策

复用 SafeHttpClient，增加显式 `public_readonly(enabled=True)`，仅允许固定 Akashi HTTPS origin、443、GET `/proof` 的 tx/hash 参数，以及 MCP initialize/initialized/tools/list/find_proof。禁写入、签名、支付、代理、跳转、任意 metadata 地址和认证 headers。旧 controlled 构造和隔离 PoC 保留原行为。

每次请求在同一串行锁内重新读取全部 DNS IPv4/IPv6 答案，拒绝任一非公网、转译/隧道/带 scope 的地址；连接仅使用本次已验证的数字 IP，保留原始 Host、TLS SNI 和证书验证。HTTPcore 禁连接复用及自动重试，阻断 DNS 校验与实际连接之间的重新解析。依赖现有 HTTPX/HTTPcore 锁定版本，不增加依赖；HTTPX 不暴露 backend 参数，使用其已有 transport 的 pool 接入点，升级时必须重跑真实 socket/SNI 测试。

20 秒包含 DNS、连接、读取，响应至多 1 MiB，严格 JSON/SSE 单响应、重复 key/嵌入 MCP 文本深度至多 32。每客户端最多 64 次尝试，失败也计数；请求完成后至少 1 秒才开始下一次，等待期限重新检查以适应 Windows 提前唤醒。自动重试次数固定为零，不在 429/超时/平台故障时放大流量。

402 或付款 headers 时不读取 body；JSON、MCP text 或所选 find_proof 的付款要求关闭后续调用。发现中的其他付费工具只当数据，不能调用。选中工具必须唯一且声明只读、无 destructiveHint；MCP 握手/协议异常/超时后停止该适配器，不能跳过检查继续 tools/call。Cookie 不重放，session 只在受限 MCP 会话内使用，不写证据。

平台静态 AkashiReadonlyAdapter 支持 `akashi-http-readonly-v1` / `akashi-mcp-readonly-v1`，归一到 verify_record 类只读查询。原 PoC 纯业务断言移入 core，脚本保留兼容导出，算法不变。返回现有 Observation 与 EvidenceRecord；服务响应规范化成功只代表接受响应，不代表业务 PASS、身份验证或 executor 控制权。

## 证据与兼容

每次发现/业务请求先保存持久 CAS 意图，再发送；请求、状态、时间、DNS/IP、配额序号和响应审计均保存。写盘/内容冲突失败停止适配器。有效无凭据响应保留原 UTF-8 字节及 SHA256；JSON 凭据（含 camelCase）和 MCP 嵌入文本先脱敏，发现敏感字段时不保留原 body；畸形/不透明响应只保留长度、hash 和错误，不持久化无法安全脱敏的文本。含敏感业务字段的规范化结果拒绝返回，防止后续导出泄漏。

复用现有 EvidenceStore.register 和 PostgreSQL 只追加约束。CAS 去重返回已有 ID 时，ReadonlyResult.registered 在调用者事务中重映射 Observation 引用；worker 的租约/fencing 事务仍由后续接入层持有。新增内部协议没有冒充现有 controlled TaskEnvelope/AccessGrant，也不改变 Schema、API、旧冻结报告或证据。任务 9 实施身份关联；任务 10 才将新协议纳入正式规划/Worker/报告/Verifier。

本机系统 DNS 使用 198.18.0.85 fake-IP，正式策略正确拒绝。真实验收使用操作者固定 `8.8.8.8:853`、TLS `dns.google` 的 DNS-over-TLS resolver 注入；DNS 原字节及 TLS 证书 hash 留存，所有返回 IP 仍经过同一公网校验和实际连接绑定。该运行时 resolver 不是 metadata 输入，不宣称 DNSSEC 已验证；默认生产 resolver 仍为系统 DNS，未放宽私网规则。

## 验证

SSRF/IP/DNS rebinding/实际 socket/TLS Host-SNI、redirect、Cookie、quota、并发、限频提前唤醒、响应大小/depth、MCP 畸形/付费/工具副作用、敏感字段和证据失败均有离线回归；真实 PostgreSQL 注册/去重/只追加/篡改拒绝单列。真实 Akashi 低频运行和完整回归结果见 STATUS 与 THIRD_PARTY_READONLY。
