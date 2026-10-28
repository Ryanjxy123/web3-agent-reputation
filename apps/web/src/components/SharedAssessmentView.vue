<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { EvaluationReport, MeasurementPurpose, ReportChainEvidence, SharedAssessment, SharedObservation, SharedTask } from '../contracts'
import { score, when } from '../format'
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
const emit = defineEmits<{ trace: [taskKey: string, dimension?: MeasurementPurpose] }>()
const result = computed(() => props.assessment.result)
const singleScorePolicy = computed(() => String(props.report.policy_version) === 'transaction-agent-evidence-v3')
const dimensions = computed(() => [
  { purpose: 'availability' as const, title: 'A · 服务可用性', weight: '30%', result: result.value.availability,
    caption: '有效业务调用能否按时取得完整响应。' },
  { purpose: 'functional' as const, title: 'F · 功能声明一致性', weight: '40%', result: result.value.functional,
    caption: '实际输入输出是否兑现本次核验的功能声明。' },
  { purpose: 'behavioral' as const, title: 'B · 交易行为可靠性', weight: '30%', result: result.value.behavioral,
    caption: '真实交易的资产、权限与终态是否符合任务约定。' },
])
const selected = computed(() => props.assessment.capabilities.filter(item => item.selected))
const scopeLabel = computed(() => result.value.risk_status === 'MAJOR_VIOLATION' ? '存在重大约束违背'
  : result.value.score_status === 'AVAILABLE' ? '已测范围综合评价' : '范围证据待补')
const historicalScore = computed(() => props.report.scores.overall == null && result.value.overall != null
  && result.value.overall.lower !== result.value.overall.upper)
const displayScore = (value: number | null | undefined) => value == null ? '未评价' : score(value)
const caseScore = (interval: { lower: number; upper: number } | null) => interval == null ? '未评价'
  : interval.lower === interval.upper ? score(interval.lower) : '历史版本'
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
  return '本次功能的三维结果与核验样本如下。'
})
const plannedExecution = (key: string) => props.assessment.cases.some(item =>
  item.dimension === 'behavioral' && item.normal_execution && item.task_keys.includes(key))
const outcomeLabel = (task: SharedTask) => {
  if (task.outcome === 'completed') {
    const refunded = observationsFor(task.task_key, 'functional').some(item =>
      item.criterion_id === 'exact-principal-refund' && item.measurement_validity === 'valid' && item.verdict === 'PASS')
    if (refunded) return '已撤销退款'
    const exchanged = observationsFor(task.task_key, 'functional').some(item =>
      ['execution-effect', 'native-input'].includes(item.criterion_id) && item.measurement_validity === 'valid' && item.verdict === 'PASS')
    return exchanged ? '已成交' : '已完成'
  }
  if (task.outcome === 'not_executed' && !plannedExecution(task.task_key)) {
    const verified = observationsFor(task.task_key, 'functional').some(item =>
      item.criterion_id === 'execution-effect' && item.measurement_validity === 'valid' && item.verdict === 'PASS')
    if (verified) return '方案已验证'
    return observationsFor(task.task_key).some(item => item.response_complete === true) ? '已返回方案' : '未取得方案'
  }
  return ({ failed: '真实执行失败', rejected: '已拒绝', protected_exit: '保护退出', not_executed: '尚未执行', unknown: '结局待核' } as const)[task.outcome]
}
const attributionLabel: Record<SharedTask['attribution'], string> = {
  provider: '提供方', operator: '操作者', network: '网络路径', chain_or_market: '链或市场条件', unknown: '归因未明',
}
const capabilityName = (id: string) => props.assessment.capabilities.find(item => item.capability_id === id)?.title ?? id
const observationsFor = (key: string, dimension?: MeasurementPurpose) => props.assessment.observations.filter(item =>
  item.task_key === key && (!dimension || item.dimension === dimension))
function openDimension(dimension: MeasurementPurpose) {
  const observations = props.assessment.observations.filter(item => item.dimension === dimension)
  const selected = observations.find(item => item.verdict === 'FAIL')
    ?? observations.find(item => item.verdict === 'UNKNOWN') ?? observations[0]
  if (selected) emit('trace', selected.task_key, dimension)
}
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
const isPlanned = (key: string, dimension: MeasurementPurpose) => props.assessment.cases.some(item =>
  item.dimension === dimension && item.task_keys.includes(key))
const taskDimensionSummary = (key: string, dimension: MeasurementPurpose) => {
  const items = observationsFor(key, dimension)
  if (!items.length) return isPlanned(key, dimension) ? '未验证' : '未涉及'
  const values = [['PASS', '通过'], ['FAIL', '不符'], ['UNKNOWN', '未验证'], ['unknown', '有效性待核'], ['invalid', '测量无效'], ['NOT_APPLICABLE', '不适用']] as const
  return values.map(([verdict, title]) => {
    const count = items.filter(item => observationState(item) === verdict).length
    return count ? `${count}项${title}` : ''
  }).filter(Boolean).join('、')
}
const groupCases = (capabilityId: string, groupId: string) => result.value.cases.filter(item =>
  item.capability_id === capabilityId && item.declaration_group_id === groupId)
const legacyAnchors = (key: string) => props.report.samples.flatMap((item, index) =>
  item.sample.task_key === key ? [`sample-${index + 1}`] : [])
const representative = computed(() => {
  const keys = new Set<string>()
  const failure = props.assessment.observations.find(item => item.verdict === 'FAIL')
  const unknown = props.assessment.observations.find(item => item.verdict === 'UNKNOWN')
  for (const item of [failure?.task_key, unknown?.task_key]) if (item) keys.add(item)
  for (const capability of selected.value) {
    const task = props.assessment.tasks.find(item => item.capability_id === capability.capability_id && item.outcome === 'completed')
    if (task) keys.add(task.task_key)
  }
  if (!keys.size && props.assessment.tasks[0]) keys.add(props.assessment.tasks[0].task_key)
  return keys
})
const showAllTasks = ref(/^#(?:task|sample)-\d+$/.test(window.location.hash))
const visibleTasks = computed(() => props.assessment.tasks.map((task, index) => ({ task, index }))
  .filter(({ task }) => showAllTasks.value || representative.value.has(task.task_key)))
async function revealHash() {
  const hash = window.location.hash
  if (!/^#(?:(?:task|sample)-\d+|dimension-(?:availability|functional|behavioral))$/.test(hash)) return
  if (/^#(?:task|sample)-/.test(hash)) showAllTasks.value = true
  await nextTick()
  if (hash !== window.location.hash) return
  const target = document.getElementById(hash.slice(1))
  for (let ancestor = target; ancestor; ancestor = ancestor.parentElement) {
    if (ancestor.tagName === 'DETAILS') ancestor.setAttribute('open', '')
  }
  target?.scrollIntoView({ block: 'start' })
}
const revealLinkedSample = (event: MouseEvent) => {
  const target = event.target as Element | null
  const href = target?.closest('a')?.getAttribute('href') ?? ''
  if (!/^#(?:task|sample)-\d+$/.test(href)) return
  event.preventDefault()
  if (window.location.hash === href) void revealHash()
  else window.location.hash = href
}
onMounted(() => {
  window.addEventListener('hashchange', revealHash)
  void revealHash()
})
onBeforeUnmount(() => window.removeEventListener('hashchange', revealHash))
watch(() => props.chainEvidence, () => { void revealHash() })
</script>

<template>
  <div class="shared-report" @click="revealLinkedSample">
    <section class="panel shared-lead">
      <div class="row-between wrap"><span class="eyebrow">本次评价结论</span><span class="report-status" :class="{ complete: result.score_status === 'AVAILABLE' && result.risk_status === 'NORMAL' }">{{ scopeLabel }}</span></div>
      <div>
        <h2>{{ conclusion }}</h2>
        <p class="lead-scope">{{ report.scope }}</p>
        <p class="shared-scope-line">评价功能：{{ selected.map(item => item.title).join('、') }}</p>
      </div>
      <div class="shared-overall"><strong :class="{ 'shared-score-pending': report.scores.overall === null }">{{ historicalScore ? '历史版本' : displayScore(report.scores.overall) }}</strong><span>本报告综合分 / 100</span><span v-if="historicalScore">旧版记录未生成单一分数</span></div>
    </section>

    <section v-if="result.risk_status === 'MAJOR_VIOLATION'" class="shared-risk" role="alert"><h3>已发现重大资金或权限约束违背</h3><ul><li v-for="reason in riskReasons" :key="reason">{{ reason }}</li></ul><p>该状态优先于综合分，不作为正常高分推荐。</p></section>

    <section class="score-grid" aria-label="共享任务的三维评分">
      <article v-for="dimension in dimensions" :id="`dimension-${dimension.purpose}`" :key="dimension.purpose" class="score-card shared-score-card">
        <div class="row-between"><h3>{{ dimension.title }}</h3><span class="muted small">{{ dimension.weight }}</span></div>
        <p class="shared-score-value" :class="{ pending: report.scores[dimension.purpose].value === null }">{{ historicalScore && report.scores[dimension.purpose].value === null ? '历史版本' : displayScore(report.scores[dimension.purpose].value) }}</p>
        <p class="shared-score-caption">{{ dimension.caption }}</p>
        <div class="score-counts"><span>{{ dimension.purpose === 'functional' ? '完全符合' : '通过' }} <b>{{ dimension.result.counts.passed }}</b></span><span>{{ dimension.purpose === 'functional' ? '含不符' : '不符' }} <b>{{ dimension.result.counts.failed }}</b></span><span>未验证 <b>{{ dimension.result.counts.unknown }}</b></span><span>未采样 <b>{{ dimension.result.counts.not_run }}</b></span></div>
        <p class="muted small">保留 {{ dimension.result.counts.observed }} 个任务观察<template v-if="dimension.result.counts.measurement_invalid"> · 测量无效 {{ dimension.result.counts.measurement_invalid }} 项</template><template v-if="dimension.result.counts.not_applicable"> · 不适用 {{ dimension.result.counts.not_applicable }} 项</template><template v-if="dimension.result.counts.protected_exit"> · 保护退出 {{ dimension.result.counts.protected_exit }} 项</template></p>
        <p v-if="dimension.purpose === 'functional'" class="muted small">同一任务的部分条款可以通过、其它条款不符；分数按声明组汇总，不是任务全项通过率。</p>
        <p v-if="dimension.purpose === 'availability' && dimension.result.p95_ms != null" class="muted small">响应 p50 {{ dimension.result.p50_ms == null ? '未记录' : (dimension.result.p50_ms / 1000).toFixed(2) + ' 秒' }} · p95 {{ (dimension.result.p95_ms / 1000).toFixed(2) }} 秒</p>
        <p v-for="reason in dimension.result.blocked_reasons" :key="reason" class="shared-range-note">{{ reason }}</p>
        <button v-if="assessment.observations.some(item => item.dimension === dimension.purpose)" class="text-button" @click="openDimension(dimension.purpose)">追踪对应任务与判据 →</button>
      </article>
    </section>

    <ChainEvidencePanel v-if="chainEvidence" :actions="chainEvidence.actions" :summary="chainEvidence.summary" :limitations="chainEvidence.limitations" :report-id="reportId" :sample-links="sampleLinks" />
    <p v-else-if="chainEvidenceError" class="muted small" role="status">链上操作摘要暂时无法读取，任务内的实际结局与原始证据仍保留。</p>

    <section v-if="actualExecutions.length" class="panel">
      <h2>链上任务履约结局</h2>
      <p class="section-description">{{ actualExecutions.length }} 个实际履约任务：{{ actualExecutions.filter(item => item.outcome === 'completed' && outcomeLabel(item) === '已成交').length }} 个已成交，{{ actualExecutions.filter(item => outcomeLabel(item) === '已撤销退款').length }} 个已撤销退款，{{ actualExecutions.filter(item => item.outcome === 'failed').length }} 个真实执行失败，{{ actualExecutions.filter(item => item.outcome === 'protected_exit').length }} 个保护退出。<template v-if="actualExecutions.some(item => ['not_executed', 'unknown', 'rejected'].includes(item.outcome))">另有 {{ actualExecutions.filter(item => item.outcome === 'not_executed').length }} 个尚未执行、{{ actualExecutions.filter(item => item.outcome === 'unknown').length }} 个结局待核、{{ actualExecutions.filter(item => item.outcome === 'rejected').length }} 个拒绝。</template></p>
    </section>

    <section class="panel">
      <div class="section-heading"><h2>代表性样本</h2><span>{{ result.task_count }} 个任务 · {{ result.observation_count }} 项判据观察</span></div>
      <p class="section-description">先看声明不符、未验证与真实履约样本；可展开全部任务核对每项证据。</p>
      <div class="shared-task-list"><details v-for="{ task, index } in visibleTasks" :id="`task-${index + 1}`" :key="task.task_key" class="shared-task" :open="representative.has(task.task_key)">
        <summary><strong>{{ String(index + 1).padStart(2, '0') }} · {{ capabilityName(task.capability_id) }} · {{ outcomeLabel(task) }}</strong><span class="shared-task-dimensions"><span>A {{ taskDimensionSummary(task.task_key, 'availability') }}</span><span>F {{ taskDimensionSummary(task.task_key, 'functional') }}</span><span>B {{ taskDimensionSummary(task.task_key, 'behavioral') }}</span></span></summary>
        <div class="shared-task-body"><span v-for="anchor in legacyAnchors(task.task_key)" :id="anchor" :key="anchor"></span>
          <div class="shared-task-actions"><button class="secondary-button" @click="emit('trace', task.task_key)">查看任务链路 →</button></div>
          <div class="shared-task-facts"><section><h4>这次请求</h4><p>{{ task.input_summary }}</p></section><section><h4>观察到的结局</h4><p>{{ outcomeLabel(task) }} · {{ attributionLabel[task.attribution] }}</p><p>采证记录时间：{{ when(task.observed_at) }}</p></section></div>
          <div class="shared-task-observations"><section v-for="dimension in dimensions" :key="dimension.purpose" class="shared-task-observation"><h4>{{ dimension.title }}</h4><ul v-if="observationsFor(task.task_key, dimension.purpose).length"><li v-for="observation in observationsFor(task.task_key, dimension.purpose)" :key="`${observation.case_id}:${observation.criterion_id}`"><strong>{{ observationTitle(observation) }}</strong><StatusBadge v-if="observation.measurement_validity === 'valid'" :verdict="observation.verdict" /><span v-else class="report-status">{{ observation.measurement_validity === 'invalid' ? '测量无效' : '有效性待核' }}</span><p>{{ observation.reason }}</p><button class="text-button" @click="emit('trace', task.task_key, dimension.purpose)">定位关联链路 →</button><p v-if="observation.elapsed_ms !== null">本次观测用时 {{ (observation.elapsed_ms / 1000).toFixed(3) }} 秒</p><p v-if="observation.measurement_validity === 'invalid'">本次测量无效，不作为 Agent 的成功或失败。</p><p v-else-if="observation.measurement_validity === 'unknown'">测量有效性尚待确认。</p><details v-if="observation.evidence.length" class="technical"><summary>这项判断的证据</summary><EvidenceList :sources="observation.evidence" :report-id="reportId" /></details></li></ul><p v-else>{{ isPlanned(task.task_key, dimension.purpose) ? '本维度已安排核验案例，尚未取得观察；未采不等于通过。' : '该任务未安排本维度的核验。' }}</p></section></div>
          <details class="technical"><summary>任务标识与完整证据</summary><p><code>{{ task.task_key }}</code></p><EvidenceList :sources="task.evidence" :report-id="reportId" /></details>
        </div>
      </details></div>
      <button v-if="assessment.tasks.length > representative.size" class="text-button" @click="showAllTasks = !showAllTasks">{{ showAllTasks ? '收起其他任务' : `展开全部 ${assessment.tasks.length} 个任务与证据` }}</button>
    </section>

    <details class="panel report-secondary"><summary><h2>评分方法与声明依据</h2></summary><ol class="shared-method-list"><li>A 核有效业务请求的按时完整交付；F 对照声明核实际输入输出，B 核真实交易与资产状态。</li><li v-if="singleScorePolicy">已知判据按 100P/(P+V) 计算，P 为通过、V 为明确不符。未验证、未采样及测量无效另列，不计为成功或失败；没有可判证据的维度不评分。</li><li v-else>这是历史政策记录；旧版没有单一分数的项目不补造数值。</li><li>按功能、声明组和案例分层汇总，重复容易的请求不能增加功能权重。综合分使用 A 30%、F 40%、B 30%。分数只对应报告说明的评价范围。</li><li>保护退出、测量无效和缺少证据分别保留；管理任务的撤销退款成功与兑换成交分开判断。</li></ol><section v-for="capability in selected" :key="capability.capability_id" class="shared-feature"><h3>{{ capability.title }}</h3><p>{{ capability.description }}</p><ul class="shared-claim-list"><li v-for="group in capability.declaration_groups.filter(item => item.selected)" :key="group.group_id"><strong>{{ group.title }}</strong><p v-for="test in groupCases(capability.capability_id, group.group_id)" :key="test.case_id">{{ caseTitle(test.case_id) }}：{{ caseScore(test.interval) }}<template v-if="test.counts.unknown"> · {{ test.counts.unknown }} 项未验证</template></p><details class="technical"><summary>声明来源</summary><EvidenceList :sources="group.source_references" :report-id="reportId" /></details></li></ul></section><dl class="report-meta"><div><dt>观察窗口</dt><dd>{{ report.evaluation_window }}</dd></div><div><dt>报告生成</dt><dd>{{ when(report.generated_at) }}</dd></div><div class="full"><dt>评价方式</dt><dd>{{ report.approach }}</dd></div><div class="full"><dt>政策版本</dt><dd><code>{{ report.policy_version }}</code></dd></div></dl></details>

    <details class="panel report-secondary"><summary><h2>评价边界与资料来源</h2></summary><ul><li v-for="item in [...report.scope_exclusions, ...report.limitations]" :key="item">{{ item }}</li></ul><EvidenceList :sources="report.source_references" :report-id="reportId" /></details>
  </div>
</template>
