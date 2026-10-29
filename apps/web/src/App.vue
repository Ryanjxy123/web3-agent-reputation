<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import type { AgentChainEvidence, AgentDetail, AgentSummary, EvaluationReport } from './contracts'
import { ApiError, asApiError, getAgent, getAgentChainEvidence, getAgents, getReport, getRuntimeStatus } from './api'
import type { RuntimeStatus } from './api'
import { checkLabel, score, when } from './format'
import { businessRole, businessSummary, chainName, executionChains, isOlasService, profileStatus, registrationType, roleLabels } from './agentProfile'
import ErrorNotice from './components/ErrorNotice.vue'
import AgentCoverage from './components/AgentCoverage.vue'
import AgentChainReview from './components/AgentChainReview.vue'
import EvidenceList from './components/EvidenceList.vue'
import ReportView from './components/ReportView.vue'
import StatusBadge from './components/StatusBadge.vue'
import AgentOverview from './components/AgentOverview.vue'
import SpatialBackdrop from './components/SpatialBackdrop.vue'
import TaskTraceWorkbench from './components/TaskTraceWorkbench.vue'

const view = ref<'browse' | 'detail'>('browse')
const detailTab = ref<'overview' | 'trace' | 'report' | 'evidence'>('overview')
const traceTaskKey = ref('')
const traceDimension = ref('')
const featuredReport = ref<EvaluationReport | null>(null)
const featuredReportError = ref<ApiError | null>(null)
const runtime = ref<RuntimeStatus | null>(null)
const runtimeError = ref(false)
const runtimeLoading = ref(false)
const agents = ref<AgentSummary[]>([])
const search = ref('')
const statusFilter = ref<'all' | 'COMPLETE' | 'PARTIAL' | 'NOT_EVALUATED'>('all')
const scopeFilter = ref('all')
const roleFilter = ref('all')
const directorySort = ref<'score-desc' | 'updated' | 'name'>('score-desc')
const scopeLabels = {
  prediction: '历史预测', liquidity: '历史增仓', generic: '通用服务', transaction: '链上交易',
  unknown: '范围待确认', unreported: '尚无报告范围',
}
const nameOrder = new Intl.Collator('zh-CN', { numeric: true, sensitivity: 'base' })
const directoryLoading = ref(true)
const directoryError = ref<ApiError | null>(null)
const pageLoading = ref(false)
const pageError = ref<ApiError | null>(null)
const detail = ref<AgentDetail | null>(null)
const chainReview = ref<AgentChainEvidence | null>(null)
const chainReviewLoading = ref(false)
const chainReviewError = ref(false)
const report = ref<EvaluationReport | null>(null)
const chainReviewIncluded = computed(() => {
  const assessment = report.value?.shared_assessment
  const actions = chainReview.value?.actions
  if (!assessment?.tasks.length || !actions?.length) return false
  const functional = new Set(assessment.observations.filter(item => item.dimension === 'functional').map(item => item.task_key))
  const behavioral = new Set(assessment.observations.filter(item => item.dimension === 'behavioral').map(item => item.task_key))
  return actions.every(action => {
    const key = action.sample_id.startsWith('contract:') ? action.sample_id.slice('contract:'.length) : action.sample_id
    return functional.has(key) && behavioral.has(key)
  })
})
const reportId = ref('')
const coverageReports = ref<Array<{ id: string; report: EvaluationReport }>>([])
const coverageLoading = ref(false)
const coverageIncomplete = ref(false)
const reportServiceLabel = computed(() => {
  if (runtimeError.value || !runtime.value) return '报告服务状态待确认'
  return runtime.value.database === 'ready' ? '已发布报告可浏览' : '报告读取暂不可用'
})
const scopeOptions = computed(() => {
  const present = new Set(agents.value.map(evaluationScope))
  return (Object.keys(scopeLabels) as Array<keyof typeof scopeLabels>)
    .filter(value => present.has(value)).map(value => ({ value, label: scopeLabels[value] }))
})
const hasDirectoryConditions = computed(() => search.value !== '' || statusFilter.value !== 'all'
  || scopeFilter.value !== 'all' || roleFilter.value !== 'all' || directorySort.value !== 'score-desc')
const matches = computed(() => {
  const needle = search.value.trim().toLocaleLowerCase()
  return agents.value.filter(agent => [agent.name, businessSummary(agent), ...(agent.profile?.capabilities ?? []), agent.registration_reference, agent.key]
    .some(value => value.toLocaleLowerCase().includes(needle))
    && (statusFilter.value === 'all' || (statusFilter.value === 'COMPLETE'
      ? (agent.complete_report_count ?? 0) > 0 || agent.latest_report?.shared_result?.score_status === 'AVAILABLE'
      : evaluationStatus(agent) === statusFilter.value))
    && (scopeFilter.value === 'all' || evaluationScope(agent) === scopeFilter.value)
    && (roleFilter.value === 'all' || businessRole(agent) === roleFilter.value))
    .sort(compareAgents)
})
let routeVersion = 0
let routeAbort: AbortController | undefined
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
  if (agent.latest_report?.shared_result?.score_status === 'AVAILABLE') return 'COMPLETE'
  return agent.latest_report?.scores.status ?? 'NOT_EVALUATED'
}

function directoryStatus(agent: AgentSummary): string {
  const shared = agent.latest_report?.shared_result
  if (shared?.risk_status === 'MAJOR_VIOLATION') return '存在重大约束违背'
  if (shared?.score_status === 'AVAILABLE') return '已测范围有分'
  const status = evaluationStatus(agent)
  if (status === 'COMPLETE') return '本范围已评分'
  if (status === 'PARTIAL') return '部分评价'
  if (businessRole(agent) === 'asset-execution') return agent.profile?.evidence_status === 'verified'
    ? '链上样本已核' : '链上证据待补齐'
  return '待评价'
}

function evaluationScope(agent: AgentSummary): keyof typeof scopeLabels {
  if (!agent.latest_report) return 'unreported'
  switch (String(agent.latest_report.scores.policy_version)) {
    case 'prediction-history-v1':
    case 'prediction-history-v2': return 'prediction'
    case 'liquidity-history-v1': return 'liquidity'
    case 'service-contract-v1':
    case 'service-fulfillment-v1': return 'generic'
    case 'evm-swap-builder-v1':
    case 'evm-swap-builder-v2':
    case 'transaction-agent-evidence-v1':
    case 'transaction-agent-evidence-v2':
    case 'transaction-agent-evidence-v3': return 'transaction'
    default: return 'unknown'
  }
}

function directoryScore(agent: AgentSummary): string {
  const report = agent.latest_report
  if (report?.scores.overall != null) return score(report.scores.overall)
  return report?.shared_result?.overall ? '历史版本' : '未评价'
}

function directoryScope(agent: AgentSummary): string {
  const shared = agent.latest_report?.shared_result
  return shared ? shared.capabilities.filter(item => item.selected).map(item => item.title).join('、')
    : scopeLabels[evaluationScope(agent)]
}

function compareAgents(left: AgentSummary, right: AgentSummary): number {
  const byName = () => nameOrder.compare(left.name, right.name) || nameOrder.compare(left.key, right.key)
  if (directorySort.value === 'name') return byName()
  if (directorySort.value === 'score-desc') {
    const riskPriority = Number(left.latest_report?.shared_result?.risk_status === 'MAJOR_VIOLATION')
      - Number(right.latest_report?.shared_result?.risk_status === 'MAJOR_VIOLATION')
    if (riskPriority) return riskPriority
    const order = { 'asset-execution': 0, 'chain-query': 1, 'research-delivery': 2, unverified: 3 }
    const priority = order[businessRole(left)] - order[businessRole(right)]
    if (priority) return priority
    const a = left.latest_report?.scores.overall ?? -1
    const b = right.latest_report?.scores.overall ?? -1
    return b - a || byName()
  }
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
  roleFilter.value = 'all'
  directorySort.value = 'score-desc'
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

function openDetailTab(tab: typeof detailTab.value, taskKey = '', dimension = '') {
  detailTab.value = tab
  traceTaskKey.value = taskKey
  traceDimension.value = dimension
  const query = new URLSearchParams(location.search)
  query.set('tab', tab)
  if (taskKey) query.set('task', taskKey); else query.delete('task')
  if (dimension) query.set('dimension', dimension); else query.delete('dimension')
  query.delete('node')
  history.pushState(null, '', location.pathname + '?' + query)
}
function openTrace(taskKey?: string, dimension?: string) { openDetailTab('trace', taskKey, dimension) }
function openFeatured(tab: 'trace' | 'report', taskKey?: string, dimension?: string) {
  const agent = matches.value[0]
  if (agent) navigate({ agent: agent.key, tab, ...(taskKey ? { task: taskKey } : {}), ...(dimension ? { dimension } : {}) })
}
function reportCriterion(taskKey: string, dimension?: string) {
  openDetailTab('report')
  void nextTick(() => {
    const index = report.value?.shared_assessment?.tasks.findIndex(t => t.task_key === taskKey) ?? -1
    const hash = dimension ? 'dimension-' + dimension : index >= 0 ? 'task-' + (index + 1) : ''
    if (hash) { location.hash = hash; document.getElementById(hash)?.scrollIntoView({block:'start'}) }
  })
}

async function loadAgents() {
  directoryLoading.value = true
  directoryError.value = null
  featuredReportError.value = null
  try {
    agents.value = await getAgents()
    const featured = agents.value.length === 1 ? agents.value[0]?.latest_report?.id : undefined
    if (featured) { try { featuredReport.value = await getReport(featured) } catch (error) { featuredReport.value = null; featuredReportError.value = asApiError(error) } }
  }
  catch (error) { directoryError.value = asApiError(error) }
  finally { directoryLoading.value = false }
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

async function loadChainReview(key: string, version: number, signal: AbortSignal) {
  chainReviewLoading.value = true
  chainReviewError.value = false
  try {
    const snapshot = await getAgentChainEvidence(key, signal)
    if (version === routeVersion) chainReview.value = snapshot
  } catch {
    if (version === routeVersion && !signal.aborted) chainReviewError.value = true
  } finally { if (version === routeVersion) chainReviewLoading.value = false }
}

async function loadRoute() {
  const version = ++routeVersion
  routeAbort?.abort()
  routeAbort = new AbortController()
  const signal = routeAbort.signal
  const parameters = new URLSearchParams(location.search)
  pageError.value = null
  pageLoading.value = false
  if (parameters.has('agent')) {
    view.value = 'detail'
    const tab = parameters.get('tab')
    detailTab.value = ['overview', 'trace', 'report', 'evidence'].includes(tab ?? '') ? tab as typeof detailTab.value : parameters.has('report') || /^#(?:task|sample)-/.test(location.hash) ? 'report' : 'overview'
    traceTaskKey.value = parameters.get('task') ?? ''
    traceDimension.value = parameters.get('dimension') ?? ''
    detail.value = null
    chainReview.value = null
    chainReviewError.value = false
    chainReviewLoading.value = false
    report.value = null
    coverageReports.value = []
    coverageLoading.value = false
    coverageIncomplete.value = false
    pageLoading.value = true
    try {
      const found = await getAgent(parameters.get('agent')!, signal)
      if (version !== routeVersion) return
      detail.value = found
      void loadChainReview(found.agent.key, version, signal)
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
  } else view.value = 'browse'
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
  routeAbort?.abort()
  window.removeEventListener('popstate', loadRoute)
})
</script>

<template>
  <div class="app-shell">
    <SpatialBackdrop :quiet="view === 'detail' && detailTab !== 'overview'" />
    <a class="skip-link" href="#main">跳到主要内容</a>
    <header class="site-header"><div class="header-inner">
      <a href="?" class="brand" @click.prevent="navigate()"><span class="brand-mark" aria-hidden="true"><svg viewBox="0 0 32 32" fill="none"><path d="m16 3 11 6.5v13L16 29 5 22.5v-13L16 3Z" stroke="currentColor" stroke-width="1.6"/><path d="m10.5 16 3.7 3.7 7.3-7.4" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg></span><span>Agent 声誉<span class="brand-subtitle">WEB3 · 多源证据评价</span></span></a>
      <span class="local-indicator"><i aria-hidden="true"></i>本机运行</span>
    </div></header>

    <main id="main" class="main-container">
      <details v-if="view!=='detail'" class="runtime-strip" aria-label="平台实时运行状态">
        <summary class="runtime-compact"><strong>{{ runtimeError ? '平台状态待确认' : runtime ? '平台在线' : '正在连接平台' }}</strong><span>{{ reportServiceLabel }}</span><span class="runtime-disclosure">运行详情</span></summary>
        <div class="runtime-details"><div class="runtime-line"><span>API：{{ runtimeError ? '状态读取失败' : runtime ? '在线' : '正在读取' }}</span><span>数据库：{{ runtimeError || !runtime ? '待确认' : runtime.database === 'ready' ? '就绪' : '不可用' }}</span><button class="text-button" :disabled="runtimeLoading" @click="loadRuntime">刷新状态</button></div><p v-if="runtimeError" class="muted small">无法读取当前运行状态，请刷新；已加载的报告可继续查看。</p><p v-else-if="runtime" class="muted small">状态读取于 {{ when(runtime.observed_at) }}</p></div>
      </details>
      <template v-if="view === 'browse'">
        <section class="directory-heading" v-if="agents.length !== 1"><div><p class="eyebrow">WEB3 AGENT REPUTATION</p><h1>用真实任务，读懂 Agent 声誉。</h1><p class="page-description">从服务请求到链上结果，循着证据理解每一项评价。</p></div></section>
        <div class="directory-toolbar" :class="{'single-agent-toolbar':agents.length===1}">
          <label class="search-field"><svg aria-hidden="true" viewBox="0 0 20 20" fill="none"><circle cx="8.5" cy="8.5" r="5.5" stroke="currentColor" stroke-width="1.5"/><path d="m13 13 4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg><span class="sr-only">搜索 Agent</span><input v-model="search" type="search" placeholder="搜索名称、能力或注册标识" /></label>
          <details class="directory-filter-disclosure"><summary>筛选与排序</summary><div class="directory-filters">
            <label class="directory-filter"><span>业务类型</span><select v-model="roleFilter"><option value="all">全部业务</option><option v-for="(label, value) in roleLabels" :key="value" :value="value">{{ label }}</option></select></label>
            <label class="directory-filter"><span>评价状态</span><select v-model="statusFilter"><option value="all">全部状态</option><option value="COMPLETE">已有范围综合分</option><option value="PARTIAL">最新报告为部分评价</option><option value="NOT_EVALUATED">尚无评分报告</option></select></label>
            <label class="directory-filter"><span>评价范围</span><select v-model="scopeFilter"><option value="all">全部范围</option><option v-for="option in scopeOptions" :key="option.value" :value="option.value">{{ option.label }}</option></select></label>
            <label class="directory-filter sort-filter"><span>排序方式</span><select v-model="directorySort"><option value="score-desc">链上执行优先 · 分数降序</option><option value="updated">最近更新</option><option value="name">名称顺序</option></select></label>
          </div></details>
          <div v-if="!directoryLoading && !directoryError" class="directory-results"><p role="status" aria-live="polite" aria-atomic="true">显示 <strong>{{ matches.length }}</strong> / {{ agents.length }} 个 Agent</p><button v-if="hasDirectoryConditions" class="text-button" @click="clearDirectoryConditions">清空条件</button></div>
          <p v-if="agents.length!==1" class="directory-comparison-note">默认优先展示链上资产操作，同类按综合分降序。分数对应各自报告的功能与样本范围。</p>
        </div>
        <p v-if="directoryLoading" class="loading-state" role="status"><span class="spinner" aria-hidden="true"></span>正在读取 Agent 目录…</p>
        <ErrorNotice v-else-if="directoryError" :error="directoryError"><button class="text-button" @click="loadAgents">重新读取目录</button></ErrorNotice>
        <section v-else-if="!matches.length" class="empty-state panel"><h2>{{ agents.length ? '没有符合条件的 Agent' : '目录中还没有 Agent' }}</h2><p>{{ agents.length ? '可以调整搜索词、评价状态或范围，也可以清空条件查看全部对象。' : '已发布的 Agent 评价报告会显示在这里。' }}</p><button v-if="agents.length && hasDirectoryConditions" class="secondary-button" @click="clearDirectoryConditions">清空条件</button></section>
        <template v-else-if="agents.length === 1 && matches[0]"><ErrorNotice v-if="featuredReportError" :error="featuredReportError"><button class="text-button" @click="loadAgents">重新读取完整报告</button></ErrorNotice><AgentOverview :agent="matches[0]" :report="featuredReport" :report-id="matches[0].latest_report?.id" @open="openFeatured('trace', $event)" @report="openFeatured('report')" @dimension="openFeatured('trace', undefined, $event)" /></template>
        <section v-else class="agent-grid" aria-label="Agent 目录"><article v-for="agent in matches" :key="agent.key" class="agent-card">
          <header>
            <div class="agent-card-top"><span class="agent-avatar" aria-hidden="true">{{ agent.name.slice(0, 2).toUpperCase() }}</span><span class="report-status" :class="{ complete: evaluationStatus(agent) === 'COMPLETE' && agent.latest_report?.shared_result?.risk_status !== 'MAJOR_VIOLATION', risk: agent.latest_report?.shared_result?.risk_status === 'MAJOR_VIOLATION' }">{{ directoryStatus(agent) }}</span></div>
            <h2><a :href="'?agent=' + encodeURIComponent(agent.key)" @click.prevent="openAgent(agent.key)">{{ agent.name }}</a></h2>
            <div class="agent-tags"><span>{{ roleLabels[businessRole(agent)] }}</span><span>{{ executionChains(agent) }}</span></div>
          </header>
          <div class="agent-card-body">
            <p class="card-description agent-business-summary">{{ businessSummary(agent) }}</p>
            <template v-if="agent.latest_report">
              <div class="card-score"><strong>{{ directoryScore(agent) }}</strong><span>本范围综合分</span></div>
              <p class="muted small">已测范围：{{ directoryScope(agent) }}</p>
              <p v-if="(agent.complete_report_count ?? 0) > 0 && evaluationStatus(agent) !== 'COMPLETE'" class="muted small">另保留 {{ agent.complete_report_count }} 份三维齐备的历史报告</p>
              <p class="muted small card-updated">更新于 {{ when(agent.latest_report.generated_at) }}</p>
            </template>
            <template v-else>
              <p v-if="businessRole(agent) === 'asset-execution'" class="unscored-note">{{ agent.profile?.evidence_status === 'verified' ? '已有真实链上样本核验，三维评分仍待补齐采样。' : '正在补齐可归属的链上任务、授权与执行证据。' }}</p>
              <p v-else class="unscored-note">尚无足够证据形成完整评分。详情中保留了已核实事实、缺项和下一步。</p>
            </template>
          </div>
          <a class="card-link" :href="'?agent=' + encodeURIComponent(agent.key)" @click.prevent="openAgent(agent.key)">{{ agent.latest_report ? '阅读评价报告' : businessRole(agent) === 'asset-execution' ? '查看链上操作' : '查看资料与缺项' }}<span aria-hidden="true">→</span></a>
        </article></section>
      </template>

      <template v-else-if="view === 'detail'">

        <p v-if="pageLoading && !detail" class="loading-state" role="status"><span class="spinner" aria-hidden="true"></span>正在读取 Agent 与报告…</p>
        <template v-if="detail">
          <div class="detail-topline"><div><button class="text-button detail-directory-link" @click="navigate()">← 目录</button><span class="eyebrow">AGENT / {{ detail.agent.name }}</span><span class="agent-tags"><span>业务链 · {{ executionChains(detail.agent) }}</span><span>历史证据</span></span></div><div v-if="detail.reports.length" class="report-toolbar"><label for="report-history">报告版本</label><select id="report-history" :value="reportId" @change="navigate({agent:detail.agent.key, report:($event.target as HTMLSelectElement).value, tab:detailTab})"><option v-for="item in detail.reports" :key="item.id" :value="item.id">{{ when(item.generated_at) }} · {{ item.scores.policy_version }} · {{ item.id.slice(0,8) }}</option></select></div></div>
          <nav class="detail-tabs" aria-label="Agent 详情"><button v-for="tab in ([{id:'overview',title:'概览'},{id:'trace',title:'任务链路'},{id:'report',title:'评价报告'},{id:'evidence',title:'链上证据'}] as const)" :key="tab.id" :aria-current="detailTab === tab.id ? 'page' : undefined" @click="openDetailTab(tab.id)">{{ tab.title }}</button><span class="muted small">{{ report?.policy_version }}</span></nav>
          <AgentOverview v-if="detailTab === 'overview'" :agent="detail.agent" :report="report" :report-id="reportId" @open="openTrace" @report="openDetailTab('report')" @dimension="openTrace(undefined, $event)" />
          <TaskTraceWorkbench v-if="detailTab === 'trace' && report" :key="reportId" :agent="detail.agent" :report="report" :report-id="reportId" :initial-task-key="traceTaskKey" :initial-dimension="traceDimension" @report="reportCriterion" />
          <section v-if="detailTab === 'trace' && report && !report.shared_assessment" class="panel"><p>该历史版本没有共享任务映射，请在评价报告中查看原始样本。</p><button class="secondary-button" @click="openDetailTab('report')">阅读历史报告</button></section>
          <div v-if="detailTab === 'evidence'" class="detail-evidence">
          <section v-if="detail.agent.profile" class="profile-context">
            <p v-if="detail.agent.profile.capabilities.length" class="profile-capabilities"><strong>业务功能</strong><span v-for="capability in detail.agent.profile.capabilities" :key="capability">{{ capability }}</span></p>
            <p class="muted small">{{ detail.agent.profile.boundary }}</p>
            <details class="identity-details"><summary>功能资料、链与执行账户来源 · {{ profileStatus(detail.agent.profile) }}</summary><p>注册链：{{ detail.agent.profile.registration_chain_id === null ? '待核实' : chainName(detail.agent.profile.registration_chain_id) }}；业务链：{{ executionChains(detail.agent) }}。</p><p v-if="detail.agent.profile.execution_accounts.length" class="multiline">已记录的执行账户：<code v-for="account in detail.agent.profile.execution_accounts" :key="account">{{ account }}<br></code></p><p v-else>尚未核实可归属于本对象的实际执行账户。</p><EvidenceList :sources="detail.agent.profile.sources" /></details>
          </section>
          <details class="identity-details"><summary>身份与资料来源 · {{ registrationType(detail.agent) }}</summary><p class="multiline">{{ detail.agent.registration_reference.startsWith('eip155:') ? '完整注册标识' : '注册资料线索' }}：{{ detail.agent.registration_reference }}</p><p v-if="isOlasService(detail.agent)">该身份登记于 Olas Service Registry；执行账户与历史授权由实际链上证据另行核验。</p><EvidenceList v-if="detail.candidate" :sources="detail.candidate.source_urls" /></details>
          <p v-if="chainReviewLoading" class="loading-state" role="status"><span class="spinner" aria-hidden="true"></span>正在读取链上核验证据…</p>
          <p v-else-if="chainReviewError" class="muted small" role="status">链上核验证据暂时无法读取，刷新页面可重试；已有报告仍可阅读。</p>
          <details v-else-if="chainReview && chainReviewIncluded" class="panel report-secondary"><summary>链上补测已纳入当前正式报告 · 查看原件来源</summary><p class="muted small">同一批任务已在下方正式评价中展示，此处保留原证据快照来源。</p><EvidenceList :sources="chainReview.sources" :agent-key="detail.agent.key" /></details>
          <AgentChainReview v-else-if="chainReview" :review="chainReview" :agent-key="detail.agent.key" :has-assessment="detail.reports.length > 0" />
          <details class="panel" v-if="coverageReports.length"><summary>跨报告范围索引 · 按版本分别查看</summary><AgentCoverage :reports="coverageReports" :expected="detail.reports.length" :selected-id="reportId" :loading="coverageLoading" :incomplete="coverageIncomplete" @select="openAgent(detail.agent.key, $event)" /></details>
          <p v-if="!chainReview && !chainReviewLoading" class="muted">当前没有单独发布的 Agent 补测快照；当前报告内的交易与原件可在任务链路逐项查看。</p><button class="secondary-button" @click="openTrace()">打开当前报告的链上任务 →</button>
          </div>
          <p v-if="pageLoading" class="loading-state" role="status"><span class="spinner" aria-hidden="true"></span>正在读取所选报告…</p>
          <div v-if="report && detailTab === 'report'" class="report-actions"><span class="muted small">当前报告 · <code>{{ reportId }}</code></span><a :href="'/api/reports/'+encodeURIComponent(reportId)" :download="'report-'+reportId+'.json'">下载报告 JSON ↗</a></div>
          <ReportView v-if="report && detailTab === 'report'" :key="reportId" :report="report" :report-id="reportId" @trace="openTrace" />
          <section v-if="!pageLoading && !detail.reports.length && !chainReview && !chainReviewLoading" class="panel candidate-panel"><span class="report-status">尚未形成完整评价</span><h2>先看已经核实什么，还缺什么。</h2><p class="section-description">目前没有足够证据发布完整三维分。以下内容帮助了解资料状态，不会换算成零分。</p><template v-if="detail.candidate"><div class="candidate-checks"><section v-for="check in detail.candidate.checks" :key="check.code"><div class="row-between"><h3>{{ checkLabel[check.code] }}</h3><StatusBadge :verdict="check.status" /></div><p>{{ check.explanation }}</p><details class="technical"><summary>这项判断的证据</summary><EvidenceList :sources="check.evidence" /></details></section></div><section class="next-actions"><h3>接下来需要什么</h3><ul><li v-for="(action, index) in detail.candidate.next_actions" :key="index">{{ action }}</li></ul></section></template><p v-else class="empty-inline">暂未保存详细资料检查记录。现有结论以已发布报告和证据为准。</p></section>
        </template>
        <ErrorNotice v-if="pageError" :error="pageError" />
      </template>

    </main>
    <footer class="site-footer"><div><span>Web3 Agent 声誉评价</span><p>公开资料 · 实际核验 · 可追溯证据</p></div><p>分数适用于各份报告列明的业务范围与样本时间。</p></footer>
  </div>
</template>
