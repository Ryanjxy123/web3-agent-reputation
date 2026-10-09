# ADR 0013：Evidence Bundle 逐任务独立复核

日期：2026-10-09。范围：本轮第 3 项；复用 M1 verifier 和纯规则。

新 v2 报告使用 ReportCore 1.1，冻结每个任务槽位的状态、原因、规则版本及 PASS/FAIL/UNKNOWN/NOT_APPLICABLE 计数。Bundle 的 `task-replay-v1` 索引将槽位绑定到原始核验输入、报告冻结输入及原始 Agent HTTP CAS；Verifier 先验证这些引用和内容，再从计划、冻结事实、RPC 原始证据及已版本化规则调用现有 `verify_record` 逐任务重判。

Verifier 将重新计算的断言、任务结果、四态计数和当前单槽位报告统计与 Bundle 内容比较。报告结果或计数不符、证据引用/冻结上下文不一致、规则与 schema/index 不匹配时拒绝 Bundle。旧单任务 ReportCore 1.0 与旧索引继续兼容，包括任务模板已升级到 @2 但报告尚未带 task summary 的历史 Bundle；此路径仍重算并输出结果，但明确标记原报告没有可比较的 task counts。新的 v1.1 摘要不得降级成旧索引格式。

原始核验输入与报告冻结时的链观测均重新判定，复用报告冻结的稳定性规则：断言结果、原因或任务关联变化须拒绝，历史平台 RPC UNKNOWN 的后续观测恢复可单独保留且不改写原任务结果。冻结观测时间须位于原观测与报告冻结时间之间；v2 结算原因须与核验输入一致。内容寻址存储可能将完全相同的原始输入与冻结输入去重为同一证据 ID，Verifier 接受该明确的角色复用；不同 ID 的冻结证据仍须具有冻结输入来源。

Report builder 当前仍限定每 run 一个任务槽位，Verifier 同样拒绝多槽位报告；只有完整重建所有报告统计和评分后才可扩展此边界。可选任务 RPC 必须由操作者通过 CLI 提供，Bundle 不指定 RPC；在线复查与离线证据重放分开返回，RPC 不可用不改写冻结结果，NOT_APPLICABLE 不触发任务 RPC。Verifier 不调用 Agent、不访问平台 DB/API。

限制：离线复核证明 Bundle 内冻结证据、报告字段与现行版本化规则一致，不能单独证明采集者诚实或当前链状态。历史 v1.0 报告没有原始 task counts，无法比较一个不存在的计数字段。完整三维评分不在此 ADR 范围内。具体测试、代码 Review 和稳定 CI 结果以 STATUS 为准。
