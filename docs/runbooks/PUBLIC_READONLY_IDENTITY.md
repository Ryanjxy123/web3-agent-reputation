# Akashi ERC-8004 只读身份接入

任务9实现设计见 ADR0020。此流程验证固定块的注册和服务端点关联；执行者控制权与业务可靠性仍 UNKNOWN。任务10才接正式业务评价、Bundle 与独立 Verifier。

## 默认与配置

公网默认关闭。只有操作者启动 API/worker 进程时显式设 `PUBLIC_READONLY_ENABLED=1`，现有 authenticated refresh 才允许静态 Akashi 对象。该开关不允许任意身份、RPC、URI、付费或写入操作；其他公共 ref 返回 UNSUPPORTED_PUBLIC_REGISTRY。

固定 AgentRef：chainId `8453`、Registry `0x8004a169fb4a3325136eb29fa0ceb6d2e539a432`、agentId `98097`。官方 ABI/commit 复用 configs/upstream-lock.json；RPC 来源固定操作者可信 Base HTTPS。不要从注册文件传入 RPC、服务凭据或执行代码。

## 运行

无数据库的真实只读组件验收：

```powershell
. ./scripts/tools.ps1
uv run --all-packages python scripts/akashi_identity_smoke.py --allow-public-readonly --output runtime/akashi-identity-new-run
```

每轮正常路径10次请求，串行且每次完成后至少1秒，无自动重试。输出目录必须不存在；失败保留全部已保存 CAS 和 UNKNOWN 结果，不覆盖旧材料。系统 DNS 返回 fake-IP/私网会被阻断，应由操作者修正可信 DNS 配置；不禁用 DNS/IP/TLS 校验。Windows 本轮使用与任务8相同的固定 TLS DNS resolver 注入，来源 DNS wire 原件及 TLS 证书 hash 一并保存，不宣称 DNSSEC。

正式平台接入复用已有 API/Worker：authenticated `POST /api/v1/agents`（上述 agent_ref）→ `POST /api/v1/agents/{id}/refresh`（`{}`）→ Worker ingest → authenticated `GET /api/v1/jobs/{id}`。JobView.public_identity 分别列出注册和元数据状态；只有成功读取才有 snapshot_id。`GET /api/v1/snapshots/{id}/readonly-association?protocol=akashi-mcp-readonly-v1` 或 `akashi-http-readonly-v1` 返回四个独立状态。HTTP 关联同时检查声明的 OpenAPI 原件。

人工 claims confirm 可以确认静态 verify_record 候选映射，但不能产生 ExecutorBinding。绑定、授权和正式写任务仍受原 EIP-712 安全门槛约束，public current_identity 显式拒绝。agentWallet/Owner 不被推断为 executor。

## 证据与恢复

发送前保存 fenced 公共读取发起记录和每请求 CAS 意图；成功/错误响应均审计。崩溃发生在请求之后、结果落库之前，重领任务输出 UNKNOWN/DISPATCH_UNCERTAIN，不自动重发公共读取。操作者可以明确发起新的 refresh。未完成/失败的新读使旧快照的当前关联降为 UNKNOWN，原快照和历史证据仍可读取；成功新快照关联上个 hash，不继承任何 binding。

ownerOf/tokenURI/code 在相同数字块读取，元数据前后复查 canonical block。未知 URI 从不被跟随。ABI 编码 URI 只在规范编码且等于固定公开 URI 时保留原文；其他 URI、RPC 错误或额外字段省略不透明数据，防止编码凭据进入证据。

本轮公开原件位于 docs/testing/evidence/akashi-identity-2026-10-11，逐字节保留真实 CAS/DNS。定向自动化测试使用历史原件及固定 RPC replay，真实 PostgreSQL/Anvil 测试单列；它们不冒充新的真实公网调用。旧 A/D Bundle 保持原规则版本和哈希输入，任务9没有升级评分或报告。

## 历史敏感材料隔离（SEC-1）

2026-10-12 修复阻止新增 URL 凭据进入公共证据和快照，并在公开 JSON 返回、只读关联原件和 Bundle 导出前拒绝未脱敏内容（HTTP 403 / `HISTORICAL_EVIDENCE_RESTRICTED`）。这是读取隔离，不清理已经落盘或分发的材料；拒绝时不返回凭据，也不在原 hash 下返回改过的字节。具体边界见 ADR0024。

如负责人在授权历史材料中确认含密，按以下顺序处置，并仅记录受影响对象 ID、原 hash、处置时间和状态，不记录凭据原文：

1. 部署并重启修复后的 API/Worker，确认受影响快照、历史列表、证据和 Bundle API 均拒绝返回；历史列表包含受污染对象时整页拒绝，不静默隐藏版本。独立静态文件/既有发布包及外部缓存不经过 API，需要暂停其分发并撤下副本。
2. 追踪同一原件派生的快照 body、ingest job、任务核验输入、冻结报告文档、CAS 和 ZIP 副本；原字节与原清单只留在受限私有隔离存储中。不原位改写 CAS、不修改只追加记录、不在原 hash 路径覆盖脱敏字节。
3. 由凭据所有者撤销或轮换已经暴露的凭据；撤下副本不能保证已下载内容被收回。本轮不自动通知第三方或执行凭据操作。
4. 使用修复后的采集流程创建安全新快照，并按原授权规则重新评价/冻结新报告；新版本产生自己的 hash。保留旧 hash 与隔离审计，安全历史材料继续按原规则复核，不将旧受污染证据升级为安全证据。

本次已实施读取隔离并只读盘点可访问的本机历史，没有改写、删除、迁移原件或轮换凭据。其他环境和已下载副本未盘点，不能断言没有泄漏；若发现真实凭据，记录对象 ID/原 hash/新安全版本关联，人工申请轮换或吊销授权。
