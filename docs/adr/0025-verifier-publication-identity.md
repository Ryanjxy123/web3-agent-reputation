# ADR 0025：独立 Verifier 发布身份一致性（SEC-3）

状态：已采纳；2026-10-12。范围：evaluation-findings 的 AUD-EVAL-001，复用 ADR0006/0008/0009/0010/0013。

## 根因与决定

AnchorReceipt 按设计不进入 ReportCore 摘要，避免循环承诺。受控报告 1.0–1.5 原本仅核对 receipt.report_hash；在线 Anchor 使用 manifest 中的发布身份，未拒绝与回执不同的身份。因此修改 receipt.publisher、contract、chain_instance_id 或 trusted_chain_key 后，原材料仍可返回 PASS，甚至 Anchor CONFIRMED。另可重新计算公开摘要，使 publication.platform_instance_id 或 previous_report_hash 与任务/报告矛盾却离线通过。公共 1.6 已有这些检查。

两条复核路径复用同一一致性检查：回执四个字段必须等于已承诺的 publication；ReportCore.previous_report_hash 必须等于 publication.previous_report_hash；每个原始任务输入的平台实例必须等于 publication.platform_instance_id。检查在任何任务/Anchor RPC 和未配置 RPC、未确认回执的早退之前完成，矛盾统一拒绝为 EVIDENCE_INCONSISTENT。公共报告仍要求本地 31337 发布链。既有 report_hash、CAS、别名字节、重算与可信 RPC 检查保持生效；不把回执身份作为覆盖已承诺身份的来源。

AgentRef 的 agentId/链/Registry、Snapshot/hash、计划槽位、Owner/executor EIP-712 双签名、平台 domain、任务 request/hash、交易/事件执行者及报告重算已有规则约束，本次不重复设计身份系统。不将正确重放的负面任务 FAIL/UNKNOWN 当作 Bundle 篡改；篡改证据关联与真实任务失败分别报告。

## 可信边界与兼容

所有版本的 Verifier 结果增加 limitations，明确离线 PASS 仅证明冻结材料、摘要和原版本规则一致，不证明原件真实性或采集者诚实。任务 live_chain CONFIRMED 只复查执行链事实；当前 RPC 复查不重新认证历史 Registry Owner、端点或 HTTP 原件。Anchor CONFIRMED 证明可信配置链上的报告摘要发布，不认证其原件。缺 RPC 保持 NOT_CHECKED；RPC 不可用、错误链、缺证据不得升级身份等级；不输出新的 VERIFIED。

RPC 仅来自操作者 --rpc-url/--task-rpc-url，不采用 Bundle 中的 URL；公共 1.6 的业务证据仍离线重放，独立本地 Anchor 查询与业务链证明分开。

不改变 ReportCore/Bundle/Schema 版本、签名输入、数据库或不可变历史字节，不新增依赖。1.0–1.6 按其原规则重放，旧格式缺任务/评价摘要继续标记 NOT_AVAILABLE_LEGACY_REPORT。原件保持兼容；历史格式中的已确认身份矛盾不因版本旧而接受。CLI 的附加 limitations 字段不改变已有状态/结果键；现有 Web 导入容忍附加字段，仍标明本地文件不构成后端或可信 RPC 认证。

## 验证

先运行合成回归复现离线错误接受，以及真实 PostgreSQL/Anvil/HTTP A/D 已确认 Anchor 的离线、在线错误接受，再修复。测试覆盖四个回执字段和非确认状态、重新承诺 publication 平台/previous、冻结 Owner/AgentId/executor 错配、既有 CAS/报告/任务篡改和 RPC 故障/换链边界。历史 A/D/public Bundle 按原版本重放且 SHA-256 不变；实际命令、统计、独立 Review 和交付门禁见 STATUS。
