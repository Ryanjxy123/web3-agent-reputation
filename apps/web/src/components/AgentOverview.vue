<script setup lang="ts">
import { computed } from 'vue'
import type { AgentSummary, EvaluationReport } from '../contracts'
import { businessSummary, chainName, executionChains, registrationType } from '../agentProfile'
import { score, when } from '../format'
import { actualExecutionTasks, projectTaskTraces } from '../traceProjection'
import type { TaskTraceViewModel, TraceStatus } from '../traceProjection'
import '../overview.css'
import TrustCore from './TrustCore.vue'

const props = defineProps<{ agent: AgentSummary; report?: EvaluationReport | null; reportId?: string }>()
const emit = defineEmits<{
  open: [taskKey?: string]
  report: []
  dimension: [dimension: 'availability' | 'functional' | 'behavioral']
}>()
const currentReport = computed(() => props.report?.candidate_key === props.agent.key ? props.report : null)
const assessment = computed(() => currentReport.value?.shared_assessment)
const scores = computed(() => currentReport.value?.scores ?? props.agent.latest_report?.scores)
const result = computed(() => assessment.value?.result ?? props.agent.latest_report?.shared_result)
const identity = computed(() => props.agent.registration_reference.split(':').at(-1))
const capabilities = computed(() => assessment.value?.capabilities.filter(item => item.selected).map(item => item.title)
  ?? props.agent.profile?.capabilities ?? [])
const dimensions = computed(() => [
  { id: 'availability' as const, letter: 'A', title: '服务可用性', value: scores.value?.availability.value, weight: '30%' },
  { id: 'functional' as const, letter: 'F', title: '功能声明一致性', value: scores.value?.functional.value, weight: '40%' },
  { id: 'behavioral' as const, letter: 'B', title: '交易行为可靠性', value: scores.value?.behavioral.value, weight: '30%' },
])
const executions = computed(() => {
  if (!assessment.value) return null
  return currentReport.value ? actualExecutionTasks(currentReport.value).length : null
})
const failure = computed(() => assessment.value?.observations.find(item => item.measurement_validity === 'valid' && item.verdict === 'FAIL'))
const unknown = computed(() => {
  const observations=assessment.value?.observations??[]
  return observations.find(item => (item.measurement_validity === 'unknown' || item.verdict === 'UNKNOWN') && !observations.some(other=>other.task_key===item.task_key&&other.measurement_validity==='valid'&&other.verdict==='FAIL'))
    ?? observations.find(item => item.measurement_validity === 'unknown' || item.verdict === 'UNKNOWN')
})
const traces = computed(() => currentReport.value ? projectTaskTraces(props.reportId ?? '', currentReport.value) : [])
const representative = computed(() => {
  const data = assessment.value
  if (!data) return []
  const keys = new Set<string>()
  const native = data.observations.find(item => item.criterion_id === 'native-input' && item.verdict === 'PASS')
  if (native) keys.add(native.task_key)
  for (const capability of data.capabilities.filter(item => item.selected)) {
    if ([...keys].some(key => data.tasks.some(item => item.task_key === key && item.capability_id === capability.capability_id))) continue
    const task = data.tasks.find(item => item.capability_id === capability.capability_id && item.outcome === 'completed')
    if (task) keys.add(task.task_key)
  }
  if (failure.value) keys.add(failure.value.task_key)
  if (unknown.value) keys.add(unknown.value.task_key)
  if (!keys.size && data.tasks[0]) keys.add(data.tasks[0].task_key)
  return [...keys].map(key => traces.value.find(item => item.taskKey === key)).filter((task): task is TaskTraceViewModel => !!task)
})
const statusTone = (status: TraceStatus) => status === 'PASS' ? 'success' : status === 'FAIL' ? 'failure' : 'warning'
const businessTone = (task: TaskTraceViewModel) => task.outcome === 'not_executed' && task.status === 'PASS' ? 'neutral' : statusTone(task.status)
const mainTask = computed(() => representative.value[0]?.taskKey)
</script>

<template>
  <div class="agent-overview">
    <section class="ov-intro">
      <div class="ov-heading-row"><p class="ov-kicker"><span></span> 基于多源证据的 Web3 Agent 声誉评价</p><span class="ov-history">历史报告 · 可追溯证据</span></div>
      <div class="ov-top-grid">
        <div class="ov-agent-panel">
          <div class="ov-agent-identity">
            <div class="ov-avatar" aria-hidden="true"><svg viewBox="0 0 48 48" fill="none"><path d="M8 35 15 13l9 18 9-18 7 22" stroke="currentColor" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/></svg></div>
            <div><h1>{{ agent.name }} <span>#{{ identity }}</span></h1><p class="ov-agent-type">{{ capabilities.join(' · ') || '公开注册 Agent' }}</p></div>
          </div>
          <p class="ov-description">{{ businessSummary(agent) }}</p>
          <div class="ov-chain-tags"><span><svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="m7 3-4 7 4 7m6-14 4 7-4 7M6 10h8" stroke="currentColor" stroke-width="1.4"/></svg>业务执行 · {{ executionChains(agent) }}</span><span>{{ registrationType(agent) }}<template v-if="agent.profile?.registration_chain_id"> · {{ chainName(agent.profile.registration_chain_id) }}</template></span><span class="ov-scope-tag">已测范围评价</span></div>
          <div class="ov-actions"><button class="primary-button" @click="emit('open', mainTask)">查看真实任务 <svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="M3 10h13m-5-5 5 5-5 5" stroke="currentColor" stroke-width="1.7"/></svg></button><button class="secondary-button" @click="emit('report')">阅读评价报告</button></div>
        </div>
        <TrustCore />
        <aside class="ov-score-panel" aria-label="当前报告评分">
          <div class="ov-score-heading"><span>已测范围综合分</span><span class="ov-score-scale">/ 100</span></div>
          <div class="ov-overall"><strong>{{ score(scores?.overall) }}</strong><span class="ov-score-caption">范围评分<span>EVIDENCE BASED</span></span></div>
          <div class="ov-dimensions"><button v-for="dimension in dimensions" :key="dimension.id" @click="emit('dimension', dimension.id)"><span class="ov-dimension-letter">{{ dimension.letter }}</span><span class="ov-dimension-content"><span class="ov-dimension-label">{{ dimension.title }}<small>{{ dimension.weight }}</small></span><span class="ov-dimension-track"><span :style="{ width: `${dimension.value ?? 0}%` }"></span></span></span><strong>{{ score(dimension.value) }}</strong><span class="ov-dimension-arrow" aria-hidden="true">↗</span></button></div>
          <p class="ov-score-note">分数来自当前报告，仅代表已测功能与样本。</p>
        </aside>
      </div>
      <div class="ov-stat-row"><div><strong>{{ result?.task_count ?? '—' }}</strong><span>真实任务</span></div><div><strong>{{ executions ?? '—' }}</strong><span>链上履约任务<small>任务数不等于交易数</small></span></div><div><strong>{{ result?.observation_count ?? '—' }}</strong><span>判据观测</span></div><div class="ov-report-date"><span>报告生成</span><time>{{ when(currentReport?.generated_at ?? agent.latest_report?.generated_at) }}</time></div></div>
    </section>

    <section v-if="assessment" class="ov-tasks-panel">
      <div class="ov-section-heading"><div><p class="ov-kicker">从任务走向证据</p><h2>代表性真实任务</h2></div><button class="text-button" @click="emit('open')">查看全部 {{ result?.task_count }} 个任务 <span aria-hidden="true">→</span></button></div>
      <div class="ov-task-table" role="group" aria-label="代表性真实任务">
        <div class="ov-task-columns" aria-hidden="true"><span>真实任务</span><span>关键业务动作与结果</span><span>业务状态</span><span>平台核验</span><span></span></div>
        <button v-for="(task, index) in representative" :key="task.taskKey" class="ov-task-row" @click="emit('open', task.taskKey)">
          <span class="ov-task-name"><strong>{{ task.title }}</strong></span>
          <span class="ov-task-summary">{{ task.resultSummary }}</span>
          <span class="ov-task-status" :class="businessTone(task)"><span class="sr-only">业务状态：</span>{{ task.outcomeLabel }}</span>
          <span class="ov-finding-pill" :class="task.verificationTone"><span class="sr-only">平台核验：</span>{{ task.verificationLabel }}</span>
          <span class="ov-task-open">查看链路 <span aria-hidden="true">↗</span></span>
          <span class="sr-only">样本 {{ index + 1 }}</span>
        </button>
      </div>
      <div class="ov-boundary-row"><svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><circle cx="10" cy="10" r="7" stroke="currentColor" stroke-width="1.4"/><path d="M10 9v5m0-8v.2" stroke="currentColor" stroke-width="1.6"/></svg><p>{{ currentReport?.scope_exclusions.join(' ') || agent.profile?.boundary || '完整评价范围与未覆盖内容见报告。' }}</p></div>
    </section>
  </div>
</template>
