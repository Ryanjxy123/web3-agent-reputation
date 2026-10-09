# ADR 0015：充分度解释与已确认关键风险

日期：2026-10-10。范围：后续任务 5；沿用 policy-v1 和 three-dimensional-v1。

## 决策

ReportCore 1.3 新增 `evidence-assessment-v1`、`evidence_sufficiency` 和 `risk_assessment`。
使用 `capabilities@4` / 断言规则 4，旧 ReportCore1.2 / @3 / 规则3保留原重判。
平台与独立 Verifier 均从冻结逐任务输入执行同一纯规则，不接收外部充分度统计或风险标签。
评分公式、权重、样本要求和阈值保持 ADR 0014 / policy-v1 原值。

充分度逐维度、逐能力记录适用 planned、有效 decided、unresolved=planned-decided、N/A 排除数、
必要样本、声明映射/测试覆盖、必要类别缺口、最旧证据年龄、coverage/sample/freshness/Q 和精确 gate。
有效样本是对应维度独立可判定证据，FAIL 也是有效样本；UNKNOWN 不作零分。
行为 unresolved 还包括未形成明确接受的计划任务，因此不能称为逐任务 UNKNOWN 计数。
全任务 UNKNOWN/(PASS+FAIL+UNKNOWN) 单列诊断；N/A 不进入该分母。
可用性使用首次 HTTP 判定，后续 RPC 故障不会把已经证明的响应改为未知或失败。

最低样本仍为 A20、每能力 B10、T10；覆盖至少 80%，Q 至少 60%。
最大 unresolved 占比 20% 仅为 `1-min_coverage` 的等价表达，不是新增业务阈值。
新鲜度仍为 `max(0,1-age/86400)`，沿用原规则按完整秒计龄；允许正式总分要求每个适用维度完成且精确 Q>=0.6。
不使用四舍五入后的 bp 放行；Q 看似 6000bp 但精确值不足时仍 PARTIAL/overall=null。
未确认、范围外或未测试声明保留在声明分母；必要类别缺失继续阻止正式总分。

## 风险与优先级

先核验冻结材料及上下文，再重判任务与断言。只有已确认 `critical=true && outcome=FAIL` 的断言形成关键风险，
包含 slot、assertion、rule、reason_code 与证据引用。沿用已接受写任务的交易/合约/参数/事件/任务关联关键断言；
查询答案错误属于普通功能失败，正确报告记录摘要不匹配属于查询 PASS。
规则4在可信 HTTP、链身份、canonical和finality均确认后比较写任务返回 chain_id/executor/record_hash 与任务约束。
明确返回错误链/执行者/摘要形成关键失败；返回 tx_hash 与采集候选不一致说明材料选取不一致，保持UNKNOWN。
没有返回result的合法链上恢复路径仍可依据完整链证据判定；RPC不足不能将这些返回字段认定为关键风险。
普通履约失败与存在 UNKNOWN 断言的证据缺口分别列出；缺口不能自动推断风险或恶意。

已确认关键风险独立于证据充分度及数值分数输出：高分仍保留关键风险、PARTIAL 仍保留关键风险；
policy-v1 的 critical_conflict_veto 继续使 advice=NOT_RECOMMENDED。
风险结论只说明本次已证实的不一致，不推断 Agent 动机或长期行为。
处理优先级为证据有效性 → 已确认风险保留 → 充分度决定是否有总分 → 常规分数及接入建议。
材料篡改是报告复核失败，不归为 Agent 风险。

## 兼容及复核

1.0/1.1/1.2 序列化省略所有 assessment 字段，保留历史哈希和原重算路径。
Verifier 按原报告版本显式重建；1.2 不会被自动提升到 1.3。
1.3 必须携带匹配 assessment 版本、规则4、充分度与风险对象；旧版本不得伪装携带新结论。
Verifier 比较完整重建报告，并输出 assessment_comparison=MATCH；旧版标明 NOT_AVAILABLE_LEGACY_REPORT。
即使攻击者重算 ZIP、manifest、报告与 receipt hash，修改统计、gate、风险结论或证据引用仍会被重判发现。
无需新依赖、数据库迁移或前端功能；报告仍只追加，离线一致性仍不证明采集者诚实。
