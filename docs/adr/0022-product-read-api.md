# ADR 0022：真实操作台所需的最小查询接口

状态：已采纳；2026-10-12。任务12阶段验收结果另见STATUS。

已有API支持单Agent、快照、任务、报告和ZIP，前端无法列出已注册对象、
查看同Agent的快照/报告历史、读取真实anchor receipt或逐任务原件。
添加相应GET接口，复用IdentityService/ReportService及现有生成DTO。

AgentPage、SnapshotPage、ReportPage提供items/next_cursor；limit默认20、
最大100，按(created_at,id)稳定keyset分页。cursor只接受UUID，快照/报告
cursor必须属于该Agent。每页复用既有完整性检查，报告读取成本受页大小约束。
小型本地操作台可以按页读取，扩大部署规模时再优化每页查询次数。

报告内证据只能以manifest成员UUID读取，经过原有CAS摘要/大小校验和JSON解析；
不接收文件路径、RPC或URL。公开范围与既有报告/Bundle GET一致；凭证仍由
采集时脱敏。anchor查询与ZIP导出复用同一真实receipt/fallback，不改哈希承诺。
写操作的token、grant、deadline、幂等和网络出口限制保持既有约束。

不改变评分、充分度、风险、ReportCore/规则版本或历史Bundle字节。
生成JSON Schema/OpenAPI/TS来自共享模型，前端只读取和呈现后台结论。
