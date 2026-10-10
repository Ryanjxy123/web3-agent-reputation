# ADR 0016：RPC 日志证据有效性与断言版本隔离

日期：2026-10-10。范围：后续任务 4、5 的回归修复；沿用现有模块边界和评价参数。

## 问题

规则 4 校验 RPC 日志字段结构，但没有先完整核对日志与所属 receipt 的位置关系。
格式合法但 transactionHash、blockHash、blockNumber 或 transactionIndex 不一致的日志，
以及 removed、重复或乱序 logIndex，不能证明 Agent 返回了错误任务结果。
如果先用这样的日志生成关键断言，平台证据异常可能被误归为 Agent 的关键风险。

## 决策与判断顺序

新正式计划使用 `capabilities@5`、断言规则 `5` 和 ReportCore `1.4.0`。
在对写任务日志执行任务关联和关键风险断言之前，先确认 RPC 日志证据有效：

- 日志字段满足既有严格类型和格式约束；RecordAnchored 的 topics、摘要长度和 indexed address padding 必须满足固定 ABI。
- 每条日志的 transactionHash、blockHash、blockNumber、transactionIndex 与所属 receipt 一致。
- removed 必须为 false；receipt 内 logIndex 必须唯一并严格递增。

位置或集合关系不一致时，任务保持 `UNKNOWN / EVIDENCE_INCONSISTENT`，不以该材料扣减 Agent 分数或形成关键风险。
畸形日志产生带原始依据的 `receipt.logs / UNKNOWN / PLATFORM_RPC_ERROR`；字段合法不等于证据已足以支持业务结论。
只有通过证据有效性、可信链身份、canonical 和 finality 检查后，才允许对任务关联、摘要、目标等生成已确认关键失败。
因此同一次判定中，证据有效性检查先于依赖该证据的 critical 断言。

UNKNOWN 留在对应覆盖和充分度分母，仍可导致 PARTIAL / overall=null。
独立可用性槽位的首次 HTTP 证据不因链 RPC 的位置异常而变成 Agent 的响应失败。
已经由其他有效任务证据确认的关键风险继续保留；一次 RPC 异常不推断 Agent 恶意。

平台冻结与 Verifier 共用 `preserve_rpc_unknown`：明确的原 RPC 故障和规则5的实际日志证据缺口，
不会因冻结时 RPC 恢复而覆盖原 UNKNOWN。上下文或 HTTP 异常产生的日志占位断言没有原始依据，不能使用该例外。
原 PASS/FAIL 在冻结时读到矛盾材料仍拒绝冻结；原始和复读证据分别保留，在线恢复只单列结果。
新 @5 完整正式报告将运行状态设为 COMPLETED；证据不足仍 PARTIAL，关键风险不会改变已完成的评价流程状态。

## 版本兼容与复核

规则 4、`capabilities@4` 和 ReportCore `1.3.0` 的重放语义、断言及序列化结果保持原样。
规则 5 的日志有效性检查只作用于新版本，不静默修订已经冻结的历史报告。
已有在途 `@4` 计划明确冻结为 `1.3.0`，已有 `@3` 计划继续冻结为 `1.2.0`。
平台和独立 Verifier 必须按报告、模板和断言的对应版本显式构建并双向检查，禁止将旧报告自动升级。
历史报告是否一致仍按其原规则判断；新规则的回放需要新版本报告，不能覆盖旧事实或旧哈希。

评分公式、权重、充分度计算和阈值均未变化，因此保留 `policy-v1`、`three-dimensional-v1`
和 `evidence-assessment-v1`，不修改 policy 内容或 hash。
共享类型增加规则 5、模板 @5 和报告 1.4 的枚举后，JSON Schema、OpenAPI 和 TS 仍由现有脚本生成。
不增加依赖或数据库迁移，不开发后续 Agent、第三方接入或前端。

## 回归要求与限制

回归需覆盖正常 receipt、每个位置字段不一致、removed、重复及乱序 logIndex；
确认规则 5 输出 UNKNOWN 且无由坏 RPC 导致的 critical，同时规则 4 的历史输出不变。
还需验证在途 @4 的 1.3 冻结、1.3/1.4 独立重放、版本混用拒绝及既有 M1 历史报告兼容。
本 ADR 记录决策和验收要求；真实执行结果另记 STATUS，不以本文声称测试已经通过。
离线复核仍只证明保存证据的一致性，不能证明采集者诚实或历史 RPC 观测真实。
