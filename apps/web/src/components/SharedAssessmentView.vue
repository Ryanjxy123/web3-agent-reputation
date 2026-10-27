<script setup lang="ts">
import { computed } from 'vue'
import type { EvaluationReport, MeasurementPurpose, ReportChainEvidence, SharedAssessment, SharedObservation, SharedTask } from '../contracts'
import { scoreRange, when } from '../format'
import ChainEvidencePanel from './ChainEvidencePanel.vue'
import EvidenceList from './EvidenceList.vue'
import StatusBadge from './StatusBadge.vue'
import '../shared-assessment.css'

const props = defineProps<{
  assessment: SharedAssessment
  report: EvaluationReport
  reportId: string
  chainEvidence: ReportChainEvidence | null
  chainEvidenceError: boolean
  sampleLinks: Record<string, number>
}>()
const result = computed(() => props.assessment.result)
const dimensions = computed(() => [
  { purpose: 'availability' as const, title: 'A · 服务可用性', weight: '30%', result: result.value.availability,
    caption: '有效业务调用能否按时取得完整响应。' },
  { purpose: 'functional' as const, title: 'F · 功能声明一致性', weight: '40%', result: result.value.functional,
    caption: '实际输入输出是否兑现本次核验的功能声明。' },
  { purpose: 'behavioral' as const, title: 'B · 交易行为可靠性', weight: '30%', result: result.value.behavioral,
    caption: '真实交易的资产、权限与终态是否符合任务约定。' },
])
const selected = computed(() => props.assessment.capabilities.filter(item => item.selected))
const unselected = computed(() => props.assessment.capabilities.filter(item => !item.selected))
const coverageLabel = computed(() => ({ FULL: '已记录声明均有评价', PARTIAL: '仍有声明未覆盖', NONE: '声明覆盖待评价' })[result.value.declaration_coverage])
const scopeLabel = computed(() => result.value.risk_status === 'MAJOR_VIOLATION' ? '存在重大约束违背'
  : result.value.score_status === 'AVAILABLE' ? '已测范围综合评价' : '范围证据待补')
const hasInterval = computed(() => result.value.overall !== null && result.value.overall.lower !== result.value.overall.upper)
const selectedGroups = computed(() => props.assessment.capabilities.flatMap(item => item.declaration_groups).filter(item => item.selected).length)
const allGroups = computed(() => props.assessment.capabilities.reduce((sum, item) => sum + item.declaration_groups.length, 0))
const riskReasons = computed(() => [...new Set(props.assessment.observations.filter(item => item.critical && item.verdict === 'FAIL').map(item => item.reason))])
const actualExecutions = computed(() => {
  const keys = new Set(props.assessment.cases.filter(item => item.dimension === 'behavioral' && item.normal_execution)
    .flatMap(item => item.task_keys))
  return props.assessment.tasks.filter(task => keys.has(task.task_key))
})
const conclusion = computed(() => {
  if (result.value.risk_status === 'MAJOR_VIOLATION') return '已发现重大约束违背，请先查看具体交易与证据。'
  if (result.value.score_status !== 'AVAILABLE') return '已有部分核验结果，仍有维度缺少充分证据。'
  const completed = actualExecutions.value.filter(item => item.outcome === 'completed').length
  const inconsistent = result.value.functional.counts.failed
  if (completed && inconsistent) return `已核 ${completed} 个真实履约任务，${inconsistent} 个任务含声明不一致项。`
  if (completed) return `已核 ${completed} 个真实履约任务，三维结论对应下方已测范围。`
  return '本次已测范围的三维结果已形成，未测功能另外列明。'
})
const outcomeLabel: Record<SharedTask['outcome'], string> = {
  completed: '已完成', failed: '真实执行失败', rejected: '已拒绝', protected_exit: '保护退出', not_executed: '未执行', unknown: '结局待核',
}
const attributionLabel: Record<SharedTask['attribution'], string> = {
  provider: '提供方', operator: '操作者', network: '网络路径', chain_or_market: '链或市场条件', unknown: '归因未明',
}
const capabilityName = (id: string) => props.assessment.capabilities.find(item => item.capability_id === id)?.title ?? id
const observationsFor = (key: string, dimension?: MeasurementPurpose) => props.assessment.observations.filter(item =>
  item.task_key === key && (!dimension || item.dimension === dimension))
const criterionLabels: Record<string, string> = {
  'complete-response': '业务响应按时完整',
  'onchain-fulfillment': '真实交易与资产履约',
}
const caseTitle = (caseId: string, criterionId?: string) => {
  const test = props.assessment.cases.find(item => item.case_id === caseId)
  if (!test) return '本项核验'
  const capability = props.assessment.capabilities.find(item => item.capability_id === test.capability_id)
  const group = capability?.declaration_groups.find(item => item.group_id === test.declaration_group_id)
  const label = group?.title ?? criterionLabels[criterionId ?? test.criterion_ids[0]]
    ?? (/[\u3400-\u9fff]/.test(test.title) ? test.title : '本项核验')
  const firstPart = test.title.split(' · ')[0] ?? ''
  return firstPart.includes('→') ? `${firstPart} · ${label}` : label
}
const observationTitle = (item: SharedObservation) => caseTitle(item.case_id, item.criterion_id)
const observationState = (item: SharedObservation) => item.measurement_validity === 'valid' ? item.verdict : item.measurement_validity
const taskDimensionSummary = (key: string, dimension: MeasurementPurpose) => {
  const items = observationsFor(key, dimension)
  if (!items.length) return '未涉及'
  const values = [['PASS', '通过'], ['FAIL', '不符'], ['UNKNOWN', '未决'], ['unknown', '有效性待核'], ['invalid', '测量无效'], ['NOT_APPLICABLE', '不适用']] as const
  return values.map(([verdict, title]) => {
    const count = items.filter(item => observationState(item) === verdict).length
    return count ? `${count}项${title}` : ''
  }).filter(Boolean).join('、')
}
const groupCases = (capabilityId: string, groupId: string) => result.value.cases.filter(item =>
  item.capability_id === capabilityId && item.declaration_group_id === groupId)
const legacyAnchor = (key: string) => {
  const index = props.report.samples.findIndex(item => item.sample.task_key === key)
  return index < 0 ? undefined : `sample-${index + 1}`
}
const representative = computed(() => {
  const keys = new Set<string>()
  const failure = props.assessment.observations.find(item => item.verdict === 'FAIL')
  const unknown = props.assessment.observations.find(item => item.verdict === 'UNKNOWN')
  const execution = props.assessment.tasks.find(item => item.outcome === 'completed')
  for (const item of [failure?.task_key, unknown?.task_key, execution?.task_key]) if (item) keys.add(item)
  if (!keys.size && props.assessment.tasks[0]) keys.add(props.assessment.tasks[0].task_key)
  return keys
})
</script>

<template>
  <div class="shared-report">
    <section class="panel shared-lead">
      <div class="row-between wrap"><span class="eyebrow">本次评价结论</span><span class="report-status" :class="{ complete: result.score_status === 'AVAILABLE' && result.risk_status === 'NORMAL' }">{{ scopeLabel }}</span></div>
      <div>
        <h2>{{ conclusion }}</h2>
        <p class="lead-scope">{{ report.scope }}</p>
        <p class="shared-scope-line"><strong>{{ coverageLabel }}</strong><span>本次纳入 {{ selected.length }} 项功能 · {{ selectedGroups }} / {{ allGroups }} 组声明</span></p>
      </div>
      <div class="shared-overall"><strong :class="{ 'shared-score-pending': result.overall === null }">{{ scoreRange(result.overall?.lower, result.overall?.upper) }}</strong><span>已测范围综合分 / 100</span><span v-if="hasInterval">区间保留未决结果，不取中点当精确分</span></div>
      <p class="scope-note">未测完全部声明也可以评价已有范围；范围分不代表全部功能已验证。<template v-if="hasInterval">上下界是当前未决结果的可能范围，不是长期成功率的置信区间。</template></p>
    </section>

    <section v-if="result.risk_status === 'MAJOR_VIOLATION'" class="shared-risk" role="alert"><h3>已发现重大资金或权限约束违背</h3><ul><li v-for="reason in riskReasons" :key="reason">{{ reason }}</li></ul><p>该状态优先于综合分，不作为正常高分推荐。</p></section>

    <section class="score-grid" aria-label="共享任务的三维评分">
      <article v-for="dimension in dimensions" :key="dimension.purpose" class="score-card shared-score-card">
        <div class="row-between"><h3>{{ dimension.title }}</h3><span class="muted small">{{ dimension.weight }}</span></div>
        <p class="shared-score-value" :class="{ pending: dimension.result.interval === null }">{{ scoreRange(dimension.result.interval?.lower, dimension.result.interval?.upper) }}</p>
        <p class="shared-score-caption">{{ dimension.caption }}</p>
        <div class="score-counts"><span>{{ dimension.purpose === 'functional' ? '完全符合' : '通过' }} <b>{{ dimension.result.counts.passed }}</b></span><span>{{ dimension.purpose === 'functional' ? '含不符' : '不符' }} <b>{{ dimension.result.counts.failed }}</b></span><span>未决 <b>{{ dimension.result.counts.unknown }}</b></span><span>未采 <b>{{ dimension.result.counts.not_run }}</b></span></div>
        <p class="muted small">保留 {{ dimension.result.counts.observed }} 个任务观察<template v-if="dimension.result.counts.measurement_invalid"> · 测量无效 {{ dimension.result.counts.measurement_invalid }} 项</template><template v-if="dimension.result.counts.not_applicable"> · 不适用 {{ dimension.result.counts.not_applicable }} 项</template><template v-if="dimension.result.counts.protected_exit"> · 保护退出 {{ dimension.result.counts.protected_exit }} 项</template></p>
        <p v-if="dimension.purpose === 'functional'" class="muted small">同一任务的部分条款可以通过、其它条款不符；分数按声明组汇总，不是任务全项通过率。</p>
        <p v-if="dimension.purpose === 'availability' && dimension.result.p95_ms != null" class="muted small">响应 p50 {{ dimension.result.p50_ms == null ? '未记录' : (dimension.result.p50_ms / 1000).toFixed(2) + ' 秒' }} · p95 {{ (dimension.result.p95_ms / 1000).toFixed(2) }} 秒</p>
        <p v-for="reason in dimension.result.blocked_reasons" :key="reason" class="shared-range-note">{{ reason }}</p>
      </article>
    </section>

    <section class="panel">
      <div class="section-heading"><h2>本次测了什么，还没测什么</h2><span>{{ coverageLabel }}</span></div>
      <div class="shared-coverage-layout">
        <section><h3>纳入本次评价</h3><ul class="shared-feature-list"><li v-for="capability in selected" :key="capability.capability_id"><strong>{{ capability.title }}</strong><p>{{ capability.description }}</p><p>已纳入 {{ capability.declaration_groups.filter(item => item.selected).length }} / {{ capability.declaration_groups.length }} 组声明</p></li></ul><p v-if="!selected.length" class="shared-empty">尚未选定有证据的评价范围。</p></section>
        <section><h3>尚未纳入本次分数</h3><ul class="shared-feature-list uncovered"><li v-for="capability in unselected" :key="capability.capability_id"><strong>{{ capability.title }}</strong><p>{{ capability.description }}</p></li><template v-for="capability in selected" :key="capability.capability_id"><li v-for="group in capability.declaration_groups.filter(item => !item.selected)" :key="group.group_id"><strong>{{ capability.title }} · {{ group.title }}</strong><p>{{ group.selection_reason || group.description }}</p></li></template></ul><p v-if="!unselected.length && selected.every(item => item.declaration_groups.every(group => group.selected))" class="shared-empty">本次清单没有另列未纳入项；实际结论仍以每条核验及案例条件为准。</p></section>
      </div>
      <p class="muted small" style="margin-top:18px">同一功能多做几次不会增加功能覆盖；已知失败也可以形成明确评价。</p>
    </section>

    <ChainEvidencePanel v-if="chainEvidence" :actions="chainEvidence.actions" :summary="chainEvidence.summary" :limitations="chainEvidence.limitations" :report-id="reportId" :sample-links="sampleLinks" />
    <p v-else-if="chainEvidenceError" class="muted small" role="status">链上操作摘要暂时无法读取，任务内的实际结局与原始证据仍保留。</p>

    <section v-if="actualExecutions.length" class="panel">
      <h2>实际交易结局</h2>
      <p class="section-description">{{ actualExecutions.length }} 个预定正常履约任务：{{ actualExecutions.filter(item => item.outcome === 'completed').length }} 个完成，{{ actualExecutions.filter(item => item.outcome === 'failed').length }} 个真实执行失败，{{ actualExecutions.filter(item => item.outcome === 'protected_exit').length }} 个保护退出，{{ actualExecutions.filter(item => item.outcome === 'not_executed').length }} 个未执行，{{ actualExecutions.filter(item => item.outcome === 'unknown').length }} 个结局待核。<template v-if="actualExecutions.some(item => item.outcome === 'rejected')">另有 {{ actualExecutions.filter(item => item.outcome === 'rejected').length }} 个拒绝。</template></p>
      <p class="muted small">保护退出保留未成交事实，既不冒充成交成功，也不直接等于 Agent 违约；具体约束与归因见任务。</p>
    </section>

    <details class="panel report-secondary">
      <summary class="section-heading"><h2>功能声明与核验范围</h2><span>{{ allGroups }} 组已记录声明</span></summary>
      <section v-for="capability in assessment.capabilities" :key="capability.capability_id" class="shared-feature">
        <div class="row-between wrap"><h3>{{ capability.title }}</h3><span class="report-status">{{ capability.selected ? '本次纳入' : '未纳入本次分数' }}</span></div><p>{{ capability.description }}</p>
        <ul class="shared-claim-list"><li v-for="group in capability.declaration_groups" :key="group.group_id"><div class="row-between wrap"><strong>{{ group.title }}</strong><span class="muted small">{{ group.selected ? '纳入本次判分' : '待扩展范围' }}</span></div><p>{{ group.description }}</p><p v-if="group.selection_reason">{{ group.selection_reason }}</p><p v-for="test in groupCases(capability.capability_id, group.group_id)" :key="test.case_id">{{ caseTitle(test.case_id) }}：{{ scoreRange(test.interval?.lower, test.interval?.upper) }}<template v-if="test.counts.unknown"> · {{ test.counts.unknown }} 项未决</template></p><details class="technical"><summary>声明来源</summary><EvidenceList :sources="group.source_references" :report-id="reportId" /></details></li></ul>
      </section>
    </details>

    <section class="panel">
      <div class="section-heading"><h2>同一任务怎样支持三维评价</h2><span>{{ result.task_count }} 个任务 · {{ result.observation_count }} 项判据观察</span></div>
      <p class="section-description">每个任务只保留一份业务过程；响应、声明核验与交易结果分别判断。下列观察不能相加成更多独立任务。</p>
      <div class="shared-task-list"><details v-for="(task, index) in assessment.tasks" :id="`task-${index + 1}`" :key="task.task_key" class="shared-task" :open="representative.has(task.task_key)">
        <summary><strong>{{ String(index + 1).padStart(2, '0') }} · {{ capabilityName(task.capability_id) }} · {{ outcomeLabel[task.outcome] }}</strong><span class="shared-task-dimensions"><span>A {{ taskDimensionSummary(task.task_key, 'availability') }}</span><span>F {{ taskDimensionSummary(task.task_key, 'functional') }}</span><span>B {{ taskDimensionSummary(task.task_key, 'behavioral') }}</span></span></summary>
        <div class="shared-task-body"><span :id="legacyAnchor(task.task_key)"></span>
          <div class="shared-task-facts"><section><h4>这次请求</h4><p>{{ task.input_summary }}</p></section><section><h4>观察到的结局</h4><p>{{ outcomeLabel[task.outcome] }} · {{ attributionLabel[task.attribution] }}</p><p v-if="task.outcome === 'not_executed' && !observationsFor(task.task_key, 'behavioral').length">本任务未纳入实际交易履约核验；未执行不等于履约失败。</p><p>{{ when(task.observed_at) }}</p></section></div>
          <div class="shared-task-observations"><section v-for="dimension in dimensions" :key="dimension.purpose" class="shared-task-observation"><h4>{{ dimension.title }}</h4><ul v-if="observationsFor(task.task_key, dimension.purpose).length"><li v-for="observation in observationsFor(task.task_key, dimension.purpose)" :key="`${observation.case_id}:${observation.criterion_id}`"><strong>{{ observationTitle(observation) }}</strong><StatusBadge v-if="observation.measurement_validity === 'valid'" :verdict="observation.verdict" /><span v-else class="report-status">{{ observation.measurement_validity === 'invalid' ? '测量无效' : '有效性待核' }}</span><p>{{ observation.reason }}</p><p v-if="observation.elapsed_ms !== null">本次观测用时 {{ (observation.elapsed_ms / 1000).toFixed(3) }} 秒</p><p v-if="observation.measurement_validity === 'invalid'">本次测量无效，不作为 Agent 的成功或失败。</p><p v-else-if="observation.measurement_validity === 'unknown'">测量有效性尚待确认。</p><details v-if="observation.evidence.length" class="technical"><summary>这项判断的证据</summary><EvidenceList :sources="observation.evidence" :report-id="reportId" /></details></li></ul><p v-else>该任务没有本维度的核验记录。</p></section></div>
          <details class="technical"><summary>任务标识与完整证据</summary><p><code>{{ task.task_key }}</code></p><EvidenceList :sources="task.evidence" :report-id="reportId" /></details>
        </div>
      </details></div>
    </section>

    <details class="panel report-secondary"><summary><h2>分数、权重与未知结果怎样处理</h2></summary><ol class="shared-method-list"><li>A 评价有效业务请求的按时完整交付；响应时限按本次方案固定，响应速度另列。F 对照纳入范围的声明和案例，B 核真实交易与资产状态。</li><li>同一案例内，已通过 P、明确失败 V、未决 U 的结果范围为 [100P/(P+V+U)，100(P+U)/(P+V+U)]。未决不是失败，区间下界不是处罚分，也不取中点冒充精确分。</li><li>按功能、声明和案例分层汇总；重复容易的请求不能增加该功能权重。未纳入的功能明确列出，不冒充已经验证。</li><li>综合分使用 A 30%、F 40%、B 30%。权重体现项目对功能兑现的重视，属于公开的产品选择。</li><li>安全拒绝、保护退出、测量无效和真正缺证据分别保留；缺少某维度的必要证据时不重新分配权重。</li></ol><dl class="report-meta"><div><dt>观察窗口</dt><dd>{{ report.evaluation_window }}</dd></div><div><dt>报告生成</dt><dd>{{ when(report.generated_at) }}</dd></div><div class="full"><dt>评价方式</dt><dd>{{ report.approach }}</dd></div><div class="full"><dt>政策版本</dt><dd><code>{{ report.policy_version }}</code></dd></div></dl></details>

    <details class="panel report-secondary"><summary><h2>范围限制与资料来源</h2></summary><div class="boundary-grid"><section><h3>本次未覆盖</h3><ul><li v-for="item in report.scope_exclusions" :key="item">{{ item }}</li></ul></section><section><h3>当前限制</h3><ul><li v-for="item in report.limitations" :key="item">{{ item }}</li></ul></section></div><EvidenceList :sources="report.source_references" :report-id="reportId" /></details>
  </div>
</template>
