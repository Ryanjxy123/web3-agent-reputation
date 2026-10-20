<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import type { AgentDetail, AgentSummary, EvaluationJob, EvaluationReport } from './contracts'
import { ApiError, asApiError, getAgent, getAgents, getJob, getReport, getRuntimeStatus, submitEvaluation } from './api'
import type { RuntimeStatus } from './api'
import { checkLabel, jobLabel, score, stageLabel, when } from './format'
import ErrorNotice from './components/ErrorNotice.vue'
import AgentCoverage from './components/AgentCoverage.vue'
import EvidenceList from './components/EvidenceList.vue'
import ReportView from './components/ReportView.vue'
import StatusBadge from './components/StatusBadge.vue'

const view = ref<'browse' | 'detail' | 'submit'>('browse')
const runtime = ref<RuntimeStatus | null>(null)
const runtimeError = ref(false)
const runtimeLoading = ref(false)
const workerLabels = { 'public-off': '在线 · 公开取证关闭', scoped: '在线 · 限定身份', online: '在线 · 公开只读已启用', stopped: '已停止', unavailable: '没有有效在线心跳' }
const agents = ref<AgentSummary[]>([])
const search = ref('')
const statusFilter = ref<'all' | 'COMPLETE' | 'PARTIAL' | 'NOT_EVALUATED'>('all')
const scopeFilter = ref('all')
const directorySort = ref<'updated' | 'name'>('updated')
const scopeLabels = {
  prediction: '历史预测', liquidity: '历史增仓', generic: '通用服务',
  unknown: '范围待确认', unreported: '尚无报告范围',
}
const nameOrder = new Intl.Collator('zh-CN', { numeric: true, sensitivity: 'base' })
const directoryLoading = ref(true)
const directoryError = ref<ApiError | null>(null)
const pageLoading = ref(false)
const pageError = ref<ApiError | null>(null)
const detail = ref<AgentDetail | null>(null)
const report = ref<EvaluationReport | null>(null)
const reportId = ref('')
const coverageReports = ref<Array<{ id: string; report: EvaluationReport }>>([])
const coverageLoading = ref(false)
const coverageIncomplete = ref(false)
const reference = ref('')
const submitting = ref(false)
const submissionError = ref<ApiError | null>(null)
const job = ref<EvaluationJob | null>(null)
const jobError = ref<ApiError | null>(null)
const completedCount = computed(() => agents.value.filter(agent => agent.latest_report?.scores.status === 'COMPLETE').length)
const exampleAgent = computed(() => agents.value.find(agent => agent.latest_report && agent.registration_reference.startsWith('eip155:'))
  ?? agents.value.find(agent => agent.registration_reference.startsWith('eip155:')))
const scopeOptions = computed(() => {
  const present = new Set(agents.value.map(evaluationScope))
  return (Object.keys(scopeLabels) as Array<keyof typeof scopeLabels>)
    .filter(value => present.has(value)).map(value => ({ value, label: scopeLabels[value] }))
})
const hasDirectoryConditions = computed(() => search.value !== '' || statusFilter.value !== 'all'
  || scopeFilter.value !== 'all' || directorySort.value !== 'updated')
const matches = computed(() => {
  const needle = search.value.trim().toLocaleLowerCase()
  return agents.value.filter(agent => [agent.name, agent.description, agent.registration_reference, agent.key]
    .some(value => value.toLocaleLowerCase().includes(needle))
    && (statusFilter.value === 'all' || evaluationStatus(agent) === statusFilter.value)
    && (scopeFilter.value === 'all' || evaluationScope(agent) === scopeFilter.value))
    .sort(compareAgents)
})
const jobActive = computed(() => job.value?.status === 'QUEUED' || job.value?.status === 'RUNNING')
const stages = ['QUEUED', 'COLLECTING', 'VERIFYING', 'REPORTING'] as const
let routeVersion = 0
let routeAbort: AbortController | undefined
let pollingGeneration = 0
let pollTimer: ReturnType<typeof setTimeout> | undefined
let runtimeTimer: ReturnType<typeof setTimeout> | undefined
let runtimeDisposed = false

async function loadRuntime() {
  if (runtimeLoading.value) return
  if (runtimeTimer !== undefined) clearTimeout(runtimeTimer)
  runtimeLoading.value = true
  try {
    runtime.value = await getRuntimeStatus()
    runtimeError.value = false
  } catch { runtimeError.value = true }
  finally {
    runtimeLoading.value = false
    if (!runtimeDisposed) runtimeTimer = setTimeout(() => { void loadRuntime() }, 15000)
  }
}

function evaluationStatus(agent: AgentSummary) {
  return agent.latest_report?.scores.status ?? 'NOT_EVALUATED'
}

function evaluationScope(agent: AgentSummary): keyof typeof scopeLabels {
  if (!agent.latest_report) return 'unreported'
  switch (String(agent.latest_report.scores.policy_version)) {
    case 'prediction-history-v1':
    case 'prediction-history-v2': return 'prediction'
    case 'liquidity-history-v1': return 'liquidity'
    case 'service-contract-v1':
    case 'service-fulfillment-v1': return 'generic'
    default: return 'unknown'
  }
}

function compareAgents(left: AgentSummary, right: AgentSummary): number {
  const byName = () => nameOrder.compare(left.name, right.name) || nameOrder.compare(left.key, right.key)
  if (directorySort.value === 'name') return byName()
  const a = left.latest_report ? Date.parse(left.latest_report.generated_at) : NaN
  const b = right.latest_report ? Date.parse(right.latest_report.generated_at) : NaN
  if (Number.isNaN(a) && !Number.isNaN(b)) return 1
  if (!Number.isNaN(a) && Number.isNaN(b)) return -1
  return (!Number.isNaN(a) && !Number.isNaN(b) && a !== b) ? b - a : byName()
}

function clearDirectoryConditions() {
  search.value = ''
  statusFilter.value = 'all'
  scopeFilter.value = 'all'
  directorySort.value = 'updated'
}

function stopPolling() {
  pollingGeneration += 1
  if (pollTimer !== undefined) clearTimeout(pollTimer)
  pollTimer = undefined
}

function navigate(parameters: Record<string, string> = {}) {
  const query = new URLSearchParams(parameters).toString()
  history.pushState(null, '', location.pathname + (query ? '?' + query : ''))
  void loadRoute()
  window.scrollTo({ top: 0, behavior: 'instant' })
}

function openAgent(key: string, id?: string) {
  navigate(id ? { agent: key, report: id } : { agent: key })
}

function openSubmission(value?: string) {
  if (value !== undefined) reference.value = value.startsWith('eip155:') ? value : ''
  submissionError.value = null
  navigate({ view: 'submit' })
}

async function loadAgents() {
  directoryLoading.value = true
  directoryError.value = null
  try { agents.value = await getAgents() }
  catch (error) { directoryError.value = asApiError(error) }
  finally { directoryLoading.value = false }
}

function applyJob(updated: EvaluationJob) {
  job.value = updated
  jobError.value = null
  stopPolling()
  if (updated.status === 'COMPLETE' && updated.candidate_key && updated.report_id) {
    void loadAgents()
    openAgent(updated.candidate_key, updated.report_id)
  } else if (updated.status === 'QUEUED' || updated.status === 'RUNNING') {
    const generation = pollingGeneration
    pollTimer = setTimeout(() => { void pollJob(updated.id, generation) }, 2000)
  }
}

async function pollJob(id: string, generation: number) {
  if (generation !== pollingGeneration) return
  try {
    const updated = await getJob(id)
    if (generation === pollingGeneration) applyJob(updated)
  } catch (error) {
    if (generation === pollingGeneration) {
      jobError.value = asApiError(error)
      stopPolling()
    }
  }
}

async function resumeJob() {
  if (!job.value || !jobActive.value) return
  jobError.value = null
  await pollJob(job.value.id, pollingGeneration)
}

async function loadCoverage(found: AgentDetail, selected: EvaluationReport, version: number, signal: AbortSignal) {
  coverageReports.value = [{ id: reportId.value, report: selected }]
  coverageLoading.value = found.reports.length > 1
  const results = await Promise.allSettled(found.reports.filter(item => item.id !== reportId.value)
    .map(async item => ({ id: item.id, report: await getReport(item.id, signal) })))
  if (version !== routeVersion) return
  coverageReports.value.push(...results.flatMap(result => result.status === 'fulfilled' ? [result.value] : []))
  coverageReports.value.sort((a, b) => Date.parse(b.report.generated_at) - Date.parse(a.report.generated_at))
  coverageIncomplete.value = results.some(result => result.status === 'rejected')
  coverageLoading.value = false
}

async function loadRoute() {
  const version = ++routeVersion
  stopPolling()
  routeAbort?.abort()
  routeAbort = new AbortController()
  const signal = routeAbort.signal
  const parameters = new URLSearchParams(location.search)
  pageError.value = null
  pageLoading.value = false
  if (parameters.has('agent')) {
    view.value = 'detail'
    detail.value = null
    report.value = null
    coverageReports.value = []
    coverageLoading.value = false
    coverageIncomplete.value = false
    pageLoading.value = true
    try {
      const found = await getAgent(parameters.get('agent')!, signal)
      if (version !== routeVersion) return
      detail.value = found
      reportId.value = parameters.get('report') || found.agent.latest_report?.id || found.reports[0]?.id || ''
      if (reportId.value) {
        if (!found.reports.some(item => item.id === reportId.value)) {
          throw new ApiError('这份报告不属于当前 Agent，请选择下面已有的报告。', 'Report identifier is not in this agent’s report history')
        }
        const selected = await getReport(reportId.value, signal)
        if (version === routeVersion) {
          report.value = selected
          void loadCoverage(found, selected, version, signal)
        }
      }
    } catch (error) {
      if (version === routeVersion && !signal.aborted) pageError.value = asApiError(error)
    } finally { if (version === routeVersion) pageLoading.value = false }
  } else if (parameters.get('view') === 'submit' || parameters.has('job')) {
    view.value = 'submit'
    job.value = null
    jobError.value = null
    if (parameters.has('job')) {
      pageLoading.value = true
      try {
        const updated = await getJob(parameters.get('job')!, signal)
        if (version === routeVersion) applyJob(updated)
      } catch (error) {
        if (version === routeVersion && !signal.aborted) pageError.value = asApiError(error)
      } finally { if (version === routeVersion) pageLoading.value = false }
    }
  } else view.value = 'browse'
}

async function submit() {
  if (!reference.value.trim() || submitting.value) return
  submitting.value = true
  submissionError.value = null
  const version = routeVersion
  try {
    const created = await submitEvaluation({ reference: reference.value.trim() })
    if (version === routeVersion) navigate({ view: 'submit', job: created.id })
  } catch (error) {
    if (version === routeVersion) submissionError.value = asApiError(error)
  } finally { submitting.value = false }
}

onMounted(() => {
  void loadRuntime()
  void loadAgents()
  void loadRoute()
  window.addEventListener('popstate', loadRoute)
})
onBeforeUnmount(() => {
  runtimeDisposed = true
  if (runtimeTimer !== undefined) clearTimeout(runtimeTimer)
  stopPolling()
  routeAbort?.abort()
  window.removeEventListener('popstate', loadRoute)
})
</script>

<template>
  <div class="app-shell">
    <a class="skip-link" href="#main">跳到主要内容</a>
    <header class="site-header"><div class="header-inner">
      <a href="?" class="brand" @click.prevent="navigate()"><span class="brand-mark" aria-hidden="true"><svg viewBox="0 0 32 32" fill="none"><path d="m16 3 11 6.5v13L16 29 5 22.5v-13L16 3Z" stroke="currentColor" stroke-width="1.6"/><path d="m10.5 16 3.7 3.7 7.3-7.4" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg></span><span>Agent 声誉<span class="brand-subtitle">WEB3 · 多源证据评价</span></span></a>
      <nav aria-label="主导航"><button :aria-current="view !== 'submit' ? 'page' : undefined" @click="navigate()">浏览 Agent</button><button :aria-current="view === 'submit' ? 'page' : undefined" @click="openSubmission()">接入并评价</button></nav>
      <span class="local-indicator"><i aria-hidden="true"></i>本机运行</span>
    </div></header>

    <main id="main" class="main-container">
      <section class="runtime-strip" aria-label="平台实时运行状态"><div class="runtime-line"><span>API：{{ runtimeError ? '状态读取失败' : runtime ? '在线' : '正在读取' }}</span><span>数据库：{{ runtimeError || !runtime ? '待确认' : runtime.database === 'ready' ? '就绪' : '不可用' }}</span><span>Worker：{{ runtimeError || !runtime ? '待确认' : workerLabels[runtime.worker.state] }}</span><span>作业：排队 {{ runtimeError ? '—' : runtime?.queued ?? '—' }} · 处理中 {{ runtimeError ? '—' : runtime?.running ?? '—' }}</span><button class="text-button" :disabled="runtimeLoading" @click="loadRuntime">刷新状态</button></div><p v-if="runtimeError" class="muted small">无法读取当前运行状态，请刷新；已有报告可继续查看。</p><template v-else-if="runtime"><p v-if="runtime.worker.state === 'unavailable' || runtime.worker.state === 'stopped'" class="muted small">当前没有已确认在线的 Worker，新的请求可能等待队列处理。</p><p v-else-if="runtime.worker.state === 'public-off'" class="muted small">Worker 可处理请求并说明缺项；当前公开取证关闭，不会自动调用外部 Agent。</p><p v-else-if="runtime.worker.state === 'scoped'" class="muted small multiline">公开取证仅限身份：{{ runtime.worker.scope_reference }}</p><p class="muted small">状态读取于 {{ when(runtime.observed_at) }}<template v-if="runtime.worker.last_seen_at"> · 最近心跳 {{ when(runtime.worker.last_seen_at) }}</template></p></template></section>
      <template v-if="view === 'browse'">
        <section class="directory-heading"><div><p class="eyebrow">公开 Agent · 可追溯的评价</p><h1>看清服务表现，读懂评分依据。</h1><p class="page-description">从实际业务与链上记录出发，了解每个 Agent 做了什么、结果如何，以及哪些能力还没有被核验。</p></div><button class="primary-button" @click="openSubmission()">接入 Agent <span aria-hidden="true">↗</span></button></section>
        <section v-if="!directoryLoading && !directoryError" class="directory-stats" aria-label="目录概况"><div><strong>{{ agents.length }}</strong><span>已记录的公共 Agent</span></div><div><strong>{{ completedCount }}</strong><span>已有完整范围分</span></div><p>每个分数都对应一份具体范围的报告。<br>暂不能评价的对象，也保留缺项与后续线索。</p></section>
        <div class="directory-toolbar">
          <label class="search-field"><svg aria-hidden="true" viewBox="0 0 20 20" fill="none"><circle cx="8.5" cy="8.5" r="5.5" stroke="currentColor" stroke-width="1.5"/><path d="m13 13 4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg><span class="sr-only">搜索 Agent</span><input v-model="search" type="search" placeholder="搜索名称、能力或注册标识" /></label>
          <div class="directory-filters">
            <label class="directory-filter"><span>评价状态</span><select v-model="statusFilter"><option value="all">全部状态</option><option value="COMPLETE">完整评价</option><option value="PARTIAL">部分评价</option><option value="NOT_EVALUATED">待评价</option></select></label>
            <label class="directory-filter"><span>评价范围</span><select v-model="scopeFilter"><option value="all">全部范围</option><option v-for="option in scopeOptions" :key="option.value" :value="option.value">{{ option.label }}</option></select></label>
            <label class="directory-filter sort-filter"><span>排序方式</span><select v-model="directorySort"><option value="updated">最近更新</option><option value="name">名称顺序</option></select></label>
          </div>
          <div v-if="!directoryLoading && !directoryError" class="directory-results"><p role="status" aria-live="polite" aria-atomic="true">显示 <strong>{{ matches.length }}</strong> / {{ agents.length }} 个 Agent</p><button v-if="hasDirectoryConditions" class="text-button" @click="clearDirectoryConditions">清空条件</button></div>
          <p class="directory-comparison-note">分数仅适用于报告列明的能力、政策与样本。目录按最新报告时间或名称排列。</p>
        </div>
        <p v-if="directoryLoading" class="loading-state" role="status"><span class="spinner" aria-hidden="true"></span>正在读取 Agent 目录…</p>
        <ErrorNotice v-else-if="directoryError" :error="directoryError"><button class="text-button" @click="loadAgents">重新读取目录</button></ErrorNotice>
        <section v-else-if="!matches.length" class="empty-state panel"><h2>{{ agents.length ? '没有符合条件的 Agent' : '目录中还没有 Agent' }}</h2><p>{{ agents.length ? '可以调整搜索词、评价状态或范围，也可以清空条件查看全部对象。' : '提交公开注册信息后，平台会检查资料并推进评价。' }}</p><button v-if="agents.length && hasDirectoryConditions" class="secondary-button" @click="clearDirectoryConditions">清空条件</button><button v-else class="primary-button" @click="openSubmission()">接入 Agent</button></section>
        <section v-else class="agent-grid" aria-label="Agent 目录"><article v-for="agent in matches" :key="agent.key" class="agent-card">
          <header>
            <div class="agent-card-top"><span class="agent-avatar" aria-hidden="true">{{ agent.name.slice(0, 2).toUpperCase() }}</span><span class="report-status" :class="{ complete: evaluationStatus(agent) === 'COMPLETE' }">{{ evaluationStatus(agent) === 'COMPLETE' ? '本范围已评分' : evaluationStatus(agent) === 'PARTIAL' ? '部分评价' : '待评价' }}</span></div>
            <h2><a :href="'?agent=' + encodeURIComponent(agent.key)" @click.prevent="openAgent(agent.key)">{{ agent.name }}</a></h2>
            <p v-if="agent.latest_report" class="card-scope">{{ scopeLabels[evaluationScope(agent)] }}</p>
          </header>
          <div class="agent-card-body">
            <template v-if="agent.latest_report">
              <div class="card-score"><strong>{{ score(agent.latest_report.scores.overall) }}</strong><span>本范围综合分</span></div>
              <p class="card-description">{{ agent.latest_report.scope }}</p>
              <p class="muted small card-updated">更新于 {{ when(agent.latest_report.generated_at) }}</p>
            </template>
            <template v-else>
              <p class="card-description">{{ agent.description }}</p>
              <p class="unscored-note">尚无足够证据形成完整评分。详情中保留了已核实事实、缺项和下一步。</p>
            </template>
          </div>
          <a class="card-link" :href="'?agent=' + encodeURIComponent(agent.key)" @click.prevent="openAgent(agent.key)">{{ agent.latest_report ? '阅读评价报告' : '查看资料与缺项' }}<span aria-hidden="true">→</span></a>
        </article></section>
      </template>

      <template v-else-if="view === 'detail'">
        <button class="back-link" @click="navigate()"><span aria-hidden="true">←</span> 返回 Agent 目录</button>
        <p v-if="pageLoading && !detail" class="loading-state" role="status"><span class="spinner" aria-hidden="true"></span>正在读取 Agent 与报告…</p>
        <template v-if="detail"><section class="detail-heading"><div><p class="eyebrow">Agent 详情</p><h1>{{ detail.agent.name }}</h1><p class="page-description">{{ detail.agent.description }}</p></div><button class="secondary-button" @click="openSubmission(detail.agent.registration_reference)">{{ detail.reports.length ? '发起重新评价' : '提交资料发起评价' }}</button></section>
          <details class="identity-details"><summary>身份与资料来源</summary><p class="multiline">{{ detail.agent.registration_reference.startsWith('eip155:') ? '完整注册标识' : '注册资料线索' }}：{{ detail.agent.registration_reference }}</p><EvidenceList v-if="detail.candidate" :sources="detail.candidate.source_urls" /></details>
          <AgentCoverage v-if="coverageReports.length" :reports="coverageReports" :expected="detail.reports.length" :selected-id="reportId" :loading="coverageLoading" :incomplete="coverageIncomplete" @select="openAgent(detail.agent.key, $event)" />
          <div v-if="detail.reports.length" class="report-toolbar"><label for="report-history">报告历史 <span class="muted">{{ detail.reports.length }} 份</span></label><select id="report-history" :value="reportId" @change="openAgent(detail.agent.key, ($event.target as HTMLSelectElement).value)"><option v-for="item in detail.reports" :key="item.id" :value="item.id">{{ when(item.generated_at) }} · {{ item.scores.status === 'COMPLETE' ? '本范围完整评分' : '部分评价' }} · {{ item.scope }}</option></select></div>
          <p v-if="pageLoading" class="loading-state" role="status"><span class="spinner" aria-hidden="true"></span>正在读取所选报告…</p>
          <ReportView v-if="report" :key="reportId" :report="report" :report-id="reportId" />
          <section v-else-if="!pageLoading && !detail.reports.length" class="panel candidate-panel"><span class="report-status">尚未形成完整评价</span><h2>先看已经核实什么，还缺什么。</h2><p class="section-description">目前没有足够证据发布完整三维分。以下内容帮助了解资料状态，不会换算成零分。</p><template v-if="detail.candidate"><div class="candidate-checks"><section v-for="check in detail.candidate.checks" :key="check.code"><div class="row-between"><h3>{{ checkLabel[check.code] }}</h3><StatusBadge :verdict="check.status" /></div><p>{{ check.explanation }}</p><details class="technical"><summary>这项判断的证据</summary><EvidenceList :sources="check.evidence" /></details></section></div><section class="next-actions"><h3>接下来需要什么</h3><ul><li v-for="(action, index) in detail.candidate.next_actions" :key="index">{{ action }}</li></ul></section></template><p v-else class="empty-inline">暂未保存详细资料检查记录。可通过接入入口提交完整注册信息。</p></section>
        </template>
        <ErrorNotice v-if="pageError" :error="pageError" />
      </template>

      <template v-else>
        <section class="submission-heading"><p class="eyebrow">接入 Agent · 提交评价请求</p><h1>提交公开注册信息，<br>让评价回到真实证据。</h1><p class="page-description">平台按身份、能力与可用证据选择适用的评价方式。公开取证是否执行取决于后台当前配置；尚未开启、资料不足或暂不支持时，任务会说明实际原因。</p></section>
        <div class="submission-layout"><section class="panel submission-form-panel"><h2>提交 Agent 评价请求</h2><form @submit.prevent="submit"><label for="agent-reference">完整注册标识或注册页面链接</label><textarea id="agent-reference" v-model="reference" rows="3" required spellcheck="false" placeholder="粘贴完整注册标识，或公开注册页面的 HTTPS 链接" :disabled="submitting" aria-describedby="reference-hint"></textarea><p id="reference-hint" class="muted small">需要能够明确定位到链、注册合约与 Agent ID 的信息。公开取证关闭时，仅保留请求并说明原因。</p><button v-if="exampleAgent && !reference" type="button" class="example-button" @click="reference = exampleAgent.registration_reference">使用目录中的真实示例：{{ exampleAgent.name }}</button><button class="primary-button submit-button" type="submit" :disabled="submitting || !reference.trim()"><span v-if="submitting" class="spinner" aria-hidden="true"></span>{{ submitting ? '正在提交…' : '提交评价请求' }}<span v-if="!submitting" aria-hidden="true">→</span></button></form><ErrorNotice v-if="submissionError" :error="submissionError" /></section>
          <aside class="submission-guide"><p class="eyebrow">提交之后</p><ol><li><span>01</span><div><h3>收集公开资料</h3><p>定位注册身份、功能声明、服务接口与执行线索。</p></div></li><li><span>02</span><div><h3>独立核验结果</h3><p>按适用方案核对实际服务和可归属的链上记录。</p></div></li><li><span>03</span><div><h3>阅读具体结论</h3><p>报告解释得分、样本与边界；缺少证据的部分明确列出。</p></div></li></ol></aside></div>
        <p v-if="pageLoading" class="loading-state" role="status"><span class="spinner" aria-hidden="true"></span>正在读取评价进度…</p><ErrorNotice v-if="pageError" :error="pageError" />
        <section v-if="job" class="panel job-panel" aria-live="polite"><div class="row-between wrap"><div><p class="eyebrow">本次评价进度</p><h2>{{ jobLabel[job.status] }}</h2></div><span class="report-status" :class="{ complete: job.status === 'COMPLETE' }">{{ stageLabel[job.stage] }}</span></div><p class="job-message">{{ job.message }}</p><p class="muted small">状态更新于 {{ when(job.updated_at) }}</p>
          <ol v-if="jobActive" class="job-stages" aria-label="评价阶段"><li v-for="(stage, index) in stages" :key="stage" :class="{ current: job.stage === stage, done: stages.indexOf(job.stage as typeof stages[number]) > index }"><span>{{ String(index + 1).padStart(2, '0') }}</span>{{ stageLabel[stage] }}</li></ol>
          <p v-if="jobActive && !jobError" class="muted small"><span class="spinner small-spinner" aria-hidden="true"></span>正在自动读取进度，完成后会打开报告。</p><ErrorNotice v-if="jobError" :error="jobError"><button v-if="jobActive" class="text-button" @click="resumeJob">重新读取进度</button></ErrorNotice>
          <button v-if="job.status === 'COMPLETE' && job.candidate_key && job.report_id" class="primary-button" @click="openAgent(job.candidate_key, job.report_id)">打开评价报告 →</button>
          <details class="technical"><summary>本次提交记录</summary><p class="multiline">提交信息：{{ job.reference }}</p><p>创建于 {{ when(job.created_at) }}<br>更新于 {{ when(job.updated_at) }}</p><p>任务标识：<code>{{ job.id }}</code></p></details>
        </section>
      </template>
    </main>
    <footer class="site-footer"><div><span>Web3 Agent 声誉评价</span><p>公开资料 · 实际核验 · 可追溯证据</p></div><p>分数适用于各份报告列明的业务范围与样本时间。</p></footer>
  </div>
</template>
