<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue';
import type { components } from './api/generated/schema';
import { downloadBundle, optionalJson, pollEvaluation, requestAllPages, requestJson, terminalStatuses, updateIfCurrent, type AgentPage, type SnapshotPage, type ReportPage, type AgentView, type AgentSnapshot, type EvaluationRun, type ReportView, type Observation, type RunPlan, type RecordVerificationResult, type ExecutorBinding, type ReadonlyIdentityAssociation, type AcceptedEvaluation, type AcceptedJob } from './api/client';
import { dimensionLabels, evaluationRequest, readVerifierCliFile, reportComparison, reportSampleSections, scoreLabel, taskEvidenceSections, verifierHashMatch, type VerifierCliResult } from './model';
import { checkConnection, type Connection } from './status';

type Tab = 'agent' | 'evaluation' | 'evidence' | 'history';
const connection = ref<Connection>('checking');
const activeTab = ref<Tab>('agent');
const operatorToken = ref('');
const chainId = ref('31337');
const agentNumber = ref('1');
const registryAddress = ref('');
const lookupAgentId = ref('');
const lookupRunId = ref('');
const startSnapshotId = ref('');
const reviewVersion = ref(1);
const grants = ref('');
const publicReadonly = ref(false);
const suiteId = ref<'m1-smoke-v1' | 'capabilities-v1'>('m1-smoke-v1');
const capabilityId = ref<components['schemas']['EvaluationCreate']['capability_id']>('anchor_record');
const queryTxHash = ref('');
const targetContract = ref('');
const recordExecutor = ref('');
const recordRequestId = ref('');
const recordHash = ref('');
const idempotencyKey = ref(crypto.randomUUID());
const agent = ref<AgentView | null>(null);
const agents = ref<AgentView[]>([]);
const snapshots = ref<AgentSnapshot[]>([]);
const snapshot = ref<AgentSnapshot | null>(null);
const bindings = ref<ExecutorBinding[]>([]);
const associations = ref<ReadonlyIdentityAssociation[]>([]);
const evaluation = ref<EvaluationRun | null>(null);
const report = ref<ReportView | null>(null);
const reportJob = ref<components['schemas']['JobView'] | null>(null);
let acceptedReportJob: AcceptedJob | null = null;
let missingReportAttempts = 0;
const history = ref<ReportView[]>([]);
const comparisonId = ref('');
const anchor = ref<components['schemas']['AnchorReceipt'] | null>(null);
const observations = ref<Observation[]>([]);
const verification = ref<RecordVerificationResult[]>([]);
const plan = ref<RunPlan | null>(null);
const busy = ref(false);
const message = ref('');
const error = ref('');
const taskEvidence = ref<components['schemas']['EvidencePacket'] | null>(null);
const evidenceSections = ref<ReturnType<typeof taskEvidenceSections> | null>(null);
const verifierImport = ref<VerifierCliResult | null>(null);
const verifierFileName = ref('');
const verifierImportError = ref('');
let pollTimer: ReturnType<typeof setTimeout> | undefined;
let pollAbort: AbortController | undefined;
let runGeneration = 0;
let agentGeneration = 0;
let evidenceGeneration = 0;
let awaitingReport = false;
let verifierImportGeneration = 0;
const labels: Record<Connection, string> = { checking: '正在连接平台', connected: '平台进程已连接', unavailable: '平台尚未连接' };
const sampleSections = computed(() => report.value ? reportSampleSections(report.value) : null);
const comparison = computed(() => history.value.find(item => item.report_id === comparisonId.value));
const comparisonReason = computed(() => report.value && comparison.value ? reportComparison(report.value, comparison.value) : null);
const verifierHashState = computed(() => verifierHashMatch(verifierImport.value, report.value?.report_hash ?? null));
const verifierHashLabel = computed(() => ({ MATCH: 'MATCH：与当前平台报告摘要一致', MISMATCH: 'MISMATCH：与当前平台报告摘要不一致，不能归因到当前报告', NO_HASH: '未提供 report_hash，无法确认对应当前报告', NO_REPORT: '尚未选择平台报告，无法比对 report_hash' }[verifierHashState.value]));
const declaredCapabilities = computed(() => {
  const value = snapshot.value?.core.normalized_metadata.capabilities;
  return Array.isArray(value) ? value.filter(item => typeof item === 'string').join('、') : '未提供结构化能力声明';
});
const executorState = computed(() => snapshot.value?.core.source_type === 'public_registry' ? 'UNKNOWN（公共只读关联不证明执行者）' : bindings.value.some(item => item.status === 'VERIFIED') ? 'VERIFIED（历史签名已核验，非当前授权）' : 'UNKNOWN');
const isTerminal = computed(() => evaluation.value ? terminalStatuses.has(evaluation.value.status) : false);
function short(value: string | null | undefined): string { return value ? value.length > 22 ? `${value.slice(0, 12)}…${value.slice(-6)}` : value : '—'; }
function newEvaluationKey() { idempotencyKey.value = crypto.randomUUID(); }
function notice(cause: unknown) { error.value = cause instanceof Error ? cause.message : '请求失败。'; }
function clearNotice() { error.value = ''; message.value = ''; }
function resetVerifierImport() { verifierImportGeneration += 1; verifierImport.value = null; verifierFileName.value = ''; verifierImportError.value = ''; }
async function action(work: () => Promise<void>): Promise<boolean> { clearNotice(); busy.value = true; try { await work(); return true; } catch (cause) { notice(cause); return false; } finally { busy.value = false; } }
function requireOperator() { if (!operatorToken.value.trim()) throw new Error('此操作需要本次会话的本地 Operator token。'); }
async function refreshConnection() { connection.value = 'checking'; connection.value = await checkConnection(); }
async function listAgents() { agents.value = await requestAllPages<AgentPage>('/api/v1/agents'); }
async function registerAgent() { await action(async () => {
  requireOperator();
  const created = await requestJson<AgentView>('/api/v1/agents', { method: 'POST', token: operatorToken.value,
    body: { agent_ref: { namespace: 'eip155', chain_id: chainId.value.trim(), registry_address: registryAddress.value.trim(), agent_id: agentNumber.value.trim() } } satisfies components['schemas']['AgentCreate'] });
  await listAgents(); if (await loadAgent(created.id)) message.value = 'Agent 已登记，可刷新身份快照。';
}); }
async function refreshAgent() { await action(async () => {
  requireOperator(); if (!agent.value) return;
  const queued = await requestJson<AcceptedJob>(`/api/v1/agents/${agent.value.id}/refresh`, { method: 'POST', token: operatorToken.value, body: {} });
  message.value = `身份刷新任务 ${queued.job_id} 已排队，完成后重新查询 Agent。`;
}); }
async function loadAgent(id = lookupAgentId.value) { return action(async () => {
  if (!id.trim()) throw new Error('请输入 Agent UUID。');
  const generation = ++agentGeneration;
  clearRunContext();
  agent.value = null; snapshot.value = null; snapshots.value = []; bindings.value = []; associations.value = []; history.value = []; startSnapshotId.value = '';
  const value = await requestJson<AgentView>(`/api/v1/agents/${encodeURIComponent(id.trim())}`);
  if (generation !== agentGeneration) return;
  agent.value = value; lookupAgentId.value = value.id; publicReadonly.value = value.source_type === 'public_registry';
  const [versions, reports] = await Promise.all([
    requestAllPages<SnapshotPage>(`/api/v1/agents/${value.id}/snapshots`),
    requestAllPages<ReportPage>(`/api/v1/agents/${value.id}/reports`),
  ]);
  if (generation !== agentGeneration) return;
  snapshots.value = versions; history.value = reports;
  if (value.current_snapshot_id) await loadSnapshot(value.current_snapshot_id);
  message.value = 'Agent 和历史记录已从平台加载。';
}); }
async function loadSnapshot(id: string) {
  snapshot.value = null; bindings.value = []; associations.value = []; startSnapshotId.value = '';
  const generation = ++agentGeneration;
  const value = await requestJson<AgentSnapshot>(`/api/v1/snapshots/${encodeURIComponent(id)}`);
  if (generation !== agentGeneration) return;
  snapshot.value = value; startSnapshotId.value = value.snapshot_id;
  if (value.core.source_type === 'public_registry') {
    const reads = await Promise.all(value.core.endpoints.filter(endpoint => endpoint.protocol !== 'controlled-http-v1').map(endpoint => optionalJson<ReadonlyIdentityAssociation>(`/api/v1/snapshots/${value.snapshot_id}/readonly-association?protocol=${endpoint.protocol}`)));
    if (generation === agentGeneration) associations.value = reads.filter((item): item is ReadonlyIdentityAssociation => item !== null);
  } else {
    const proofs = await requestJson<ExecutorBinding[]>(`/api/v1/snapshots/${value.snapshot_id}/bindings`);
    if (generation === agentGeneration) bindings.value = proofs;
  }
}
function stopPolling() { if (pollTimer) clearTimeout(pollTimer); pollTimer = undefined; pollAbort?.abort(); pollAbort = undefined; }
function clearRunContext() {
  stopPolling(); const generation = ++runGeneration;
  evaluation.value = null; report.value = null; anchor.value = null; observations.value = []; verification.value = []; plan.value = null;
  taskEvidence.value = null; evidenceSections.value = null; resetVerifierImport(); lookupRunId.value = '';
  awaitingReport = false; acceptedReportJob = null; reportJob.value = null; missingReportAttempts = 0;
  return generation;
}
async function refreshRun(id: string, generation: number, current?: EvaluationRun) {
  const base = `/api/v1/evaluations/${encodeURIComponent(id)}`;
  const run = current ?? await requestJson<EvaluationRun>(base);
  const [obs, runPlan, results, runReport] = await Promise.all([
    optionalJson<Observation[]>(`${base}/observations`), optionalJson<RunPlan>(`${base}/plan`),
    optionalJson<RecordVerificationResult | RecordVerificationResult[]>(`${base}/verification`), optionalJson<ReportView>(`${base}/report`),
  ]);
  if (generation !== runGeneration) return null;
  evaluation.value = run; observations.value = obs ?? []; plan.value = runPlan;
  if (report.value?.report_id !== runReport?.report_id) resetVerifierImport();
  verification.value = results ? Array.isArray(results) ? results : [results] : []; report.value = runReport;
  if (awaitingReport && acceptedReportJob && !runReport) {
    const job = await requestJson<components['schemas']['JobView']>(acceptedReportJob.status_url, { token: operatorToken.value });
    if (generation !== runGeneration) return null;
    reportJob.value = job;
    if (job.state === 'FAILED' || job.state === 'CANCELLED') {
      awaitingReport = false;
      throw new Error(`报告任务 ${job.state}：${job.reason_code ?? '后端未返回原因'}`);
    }
    if (job.state === 'SUCCEEDED' && ++missingReportAttempts > 5) {
      awaitingReport = false;
      throw new Error('报告任务已完成但报告仍不可读取，请重新查询并检查平台日志。');
    }
  }
  if (runReport) {
    await updateIfCurrent(optionalJson<components['schemas']['AnchorReceipt']>(`/api/v1/reports/${runReport.report_id}/anchor`),
      () => generation === runGeneration && report.value?.report_id === runReport.report_id,
      value => { anchor.value = value; awaitingReport = false; });
  }
  if (generation !== runGeneration) return null;
  if (awaitingReport) {
    pollTimer = setTimeout(() => { refreshRun(id, generation).catch(cause => {
      if (generation === runGeneration) { notice(cause); stopPolling(); }
    }); }, 2000);
  }
  return run;
}
async function loadEvaluation(id = lookupRunId.value) { return action(async () => {
  if (!id.trim()) throw new Error('请输入 Run UUID。');
  const generation = clearRunContext(); lookupRunId.value = id.trim();
  await updateIfCurrent(refreshRun(id.trim(), generation), () => generation === runGeneration, loaded => {
    activeTab.value = 'evaluation';
    if (loaded && !terminalStatuses.has(loaded.status)) {
      pollAbort = new AbortController();
      const signal = pollAbort.signal;
      pollTimer = setTimeout(() => {
        pollEvaluation(id.trim(), { signal, onUpdate: async run => { await refreshRun(id.trim(), generation, run); } }).catch(cause => {
          if (!signal.aborted) { notice(cause); stopPolling(); }
        });
      }, 2000);
    }
  });
}); }
async function startEvaluation() { await action(async () => {
  requireOperator();
  const request = evaluationRequest({ snapshotId: startSnapshotId.value, reviewVersion: reviewVersion.value, grantIds: grants.value.split(/[\s,]+/).filter(Boolean), publicReadonly: publicReadonly.value,
    suiteId: suiteId.value, capabilityId: capabilityId.value, queryTxHash: queryTxHash.value, targetContract: targetContract.value,
    recordExecutor: recordExecutor.value, recordRequestId: recordRequestId.value, recordHash: recordHash.value });
  const accepted = await requestJson<AcceptedEvaluation>(request.path, { method: 'POST', token: operatorToken.value, body: request.body, idempotencyKey: idempotencyKey.value });
  if (await loadEvaluation(accepted.run_id)) message.value = `评价已排队：${accepted.run_id}。后端仍核对授权、快照和配额。`;
}); }
async function cancelEvaluation() { await action(async () => {
  requireOperator(); if (!evaluation.value) return;
  const id = evaluation.value.run_id; const generation = runGeneration;
  const isCurrent = () => generation === runGeneration && evaluation.value?.run_id === id;
  await updateIfCurrent(requestJson<EvaluationRun>(`/api/v1/evaluations/${id}/cancel`, { method: 'POST', token: operatorToken.value, body: { reason: 'Cancelled from local operator dashboard' } }), isCurrent, () => {});
  if (!isCurrent()) return;
  const reloadGeneration = runGeneration + 1;
  if (await loadEvaluation(id) && runGeneration === reloadGeneration && evaluation.value?.run_id === id) message.value = '取消请求已提交；已发生的任务和证据保留。';
}); }
async function requestReport() { await action(async () => {
  requireOperator(); if (!evaluation.value) return;
  const id = evaluation.value.run_id; const generation = runGeneration;
  const isCurrent = () => generation === runGeneration && evaluation.value?.run_id === id;
  await updateIfCurrent(requestJson<AcceptedJob>(`/api/v1/evaluations/${id}/report`, { method: 'POST', token: operatorToken.value }), isCurrent,
    accepted => { acceptedReportJob = accepted; reportJob.value = null; missingReportAttempts = 0; awaitingReport = true; stopPolling(); });
  if (!isCurrent()) return;
  await updateIfCurrent(refreshRun(id, generation), isCurrent, () => { message.value = '报告生成任务已排队。'; });
}); }
async function selectReport(item: ReportView) {
  const generation = clearRunContext(); report.value = item;
  activeTab.value = 'evidence';
  try {
    await updateIfCurrent(optionalJson<components['schemas']['AnchorReceipt']>(`/api/v1/reports/${item.report_id}/anchor`),
      () => generation === runGeneration && report.value?.report_id === item.report_id, value => { anchor.value = value; });
  } catch (cause) { notice(cause); }
}
async function importVerifierFile(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = '';
  const generation = ++verifierImportGeneration;
  verifierImport.value = null; verifierImportError.value = ''; verifierFileName.value = file?.name ?? '';
  if (!file) return;
  try {
    const result = await readVerifierCliFile(file);
    if (generation === verifierImportGeneration) verifierImport.value = result;
  } catch (cause) {
    if (generation === verifierImportGeneration) verifierImportError.value = cause instanceof Error ? cause.message : 'Verifier 文件读取失败。';
  }
}
async function loadTaskEvidence(evidenceId: string) { await action(async () => {
  if (!report.value) return;
  const reportId = report.value.report_id; const generation = runGeneration; const selectedEvidence = ++evidenceGeneration;
  taskEvidence.value = null; evidenceSections.value = null;
  await updateIfCurrent(requestJson<components['schemas']['EvidencePacket']>(`/api/v1/reports/${reportId}/evidence/${evidenceId}`),
    () => generation === runGeneration && selectedEvidence === evidenceGeneration && report.value?.report_id === reportId,
    value => { evidenceSections.value = taskEvidenceSections(value); taskEvidence.value = value; });
}); }
async function downloadEvidence() { await action(async () => {
  if (!report.value) return;
  const reportId = report.value.report_id; const url = URL.createObjectURL(await downloadBundle(reportId));
  const link = document.createElement('a'); link.href = url; link.download = `report-${reportId}.zip`; link.click(); URL.revokeObjectURL(url);
  message.value = '证据包已开始下载。';
}); }
onMounted(() => { refreshConnection(); listAgents().catch(notice); });
onUnmounted(() => { stopPolling(); ++runGeneration; ++agentGeneration; });
</script>

<template>
  <main class="shell">
    <header class="hero">
      <div><p class="eyebrow">WEB3 AGENT REPUTATION · LOCAL DEMO</p><h1>Agent 声誉评价工作台</h1><p>身份、真实履约、独立链上核验与冻结证据，使用平台真实 API。</p></div>
      <div class="connection" :class="connection"><span class="dot"></span>{{ labels[connection] }}<button class="link-button" @click="refreshConnection">重试</button></div>
    </header>
    <section class="operator card"><label>本地 Operator token（仅当前页面内存）<input v-model="operatorToken" type="password" autocomplete="off" placeholder="写操作需要 Operator 认证" /></label><small>后端继续执行身份、授权、配额和免费只读策略校验。</small></section>
    <nav class="tabs" aria-label="评价模块"><button :class="{ selected: activeTab === 'agent' }" @click="activeTab = 'agent'">Agent 与身份</button><button :class="{ selected: activeTab === 'evaluation' }" @click="activeTab = 'evaluation'">任务评价</button><button :class="{ selected: activeTab === 'evidence' }" @click="activeTab = 'evidence'">声誉与证据</button><button :class="{ selected: activeTab === 'history' }" @click="activeTab = 'history'">历史对比</button></nav>
    <p v-if="message" class="notice success" role="status">{{ message }}</p><p v-if="error" class="notice error" role="alert">{{ error }}</p><p v-if="busy" role="status">正在请求平台…</p>

    <section v-if="activeTab === 'agent'" class="stack">
      <article class="card">
        <div class="section-heading"><div><p class="eyebrow">ERC-8004</p><h2>Agent 管理</h2></div><button :disabled="busy" @click="action(listAgents)">刷新列表</button></div>
        <div v-if="agents.length" class="agent-list"><button v-for="item in agents" :key="item.id" class="agent-choice" :disabled="busy" @click="loadAgent(item.id)"><strong>Agent #{{ item.agent_ref.agent_id }} · {{ short(item.id) }}</strong><span>{{ item.source_type === 'controlled' ? '受控 Agent' : item.source_type === 'public_registry' ? '真实第三方 Agent' : '证据重放' }} · {{ item.status }}</span></button></div><p v-else class="empty">尚无已登记 Agent。</p>
        <div class="form-grid"><label>Agent UUID<input v-model="lookupAgentId" /></label><button :disabled="busy" @click="loadAgent()">查询</button></div>
        <details><summary>登记 Agent</summary><div class="form-grid three"><label>Chain ID<input v-model="chainId" /></label><label>Registry address<input v-model="registryAddress" /></label><label>链上 Agent ID<input v-model="agentNumber" /></label></div><button :disabled="busy || !operatorToken" @click="registerAgent">登记</button></details>
      </article>
      <article class="card">
        <div class="section-heading"><h2>身份、版本与能力声明</h2><button v-if="agent" :disabled="busy || !operatorToken" @click="refreshAgent">刷新链上身份</button></div>
        <p v-if="!agent" class="empty">选择 Agent 后显示实际身份状态。</p>
        <template v-else>
          <div class="facts"><div><span>ERC-8004 身份</span><strong>{{ agent.agent_ref.chain_id }} / #{{ agent.agent_ref.agent_id }}</strong><small>{{ agent.agent_ref.registry_address }}</small></div><div><span>平台身份状态</span><strong>{{ agent.status }}</strong></div><div><span>当前快照 UUID</span><strong>{{ agent.current_snapshot_id ?? '尚未采集' }}</strong></div></div>
          <label v-if="snapshots.length" class="history-select">查看快照版本<select :value="snapshot?.snapshot_id" @change="action(() => loadSnapshot(($event.target as HTMLSelectElement).value))"><option v-for="item in snapshots" :key="item.snapshot_id" :value="item.snapshot_id">{{ item.core.captured_at }} · revision {{ item.core.registry_revision }} · {{ short(item.snapshot_hash) }}</option></select></label>
          <template v-if="snapshot">
            <div class="facts"><div><span>Owner</span><strong>{{ snapshot.core.owner }}</strong></div><div><span>链上读取</span><strong>Block {{ snapshot.core.read_block_number }}</strong><small>{{ short(snapshot.core.read_block_hash) }}</small></div><div><span>执行者绑定</span><strong>{{ executorState }}</strong><small>声明执行者：{{ snapshot.core.declared_executor ?? 'UNKNOWN' }}</small></div></div>
            <p>能力声明：{{ declaredCapabilities }}</p><p class="hint">能力声明与支持端点是待评价输入，业务履约由任务证据核验。</p>
            <div class="capabilities"><span v-for="endpoint in snapshot.core.endpoints" :key="endpoint.endpoint_id" class="pill">{{ endpoint.endpoint_id }} · {{ endpoint.protocol }} · {{ endpoint.scheme }}://{{ endpoint.host }}:{{ endpoint.port }}{{ endpoint.path }}</span></div>
            <div v-for="item in bindings" :key="item.binding_id" class="observation"><strong>{{ item.status }}</strong><span>Executor {{ item.message.executor }}</span><span>{{ item.reason_code ?? '历史签名已核验' }}</span><small>绑定期限（Unix 秒）{{ item.message.deadline }} · 当前执行仍由后端检查时效与授权</small></div>
            <div v-for="item in associations" :key="item.protocol" class="observation"><strong>{{ item.protocol }}</strong><span>注册 {{ item.registration_outcome }} · 端点 {{ item.endpoint_outcome }}</span><span>Executor {{ item.executor_outcome }}</span><small>{{ item.registration_reason ?? item.endpoint_reason ?? item.executor_reason }}</small></div>
          </template>
        </template>
      </article>
    </section>

    <section v-else-if="activeTab === 'evaluation'" class="stack">
      <article class="card"><h2>启动授权评价</h2><div class="form-grid three"><label>快照 UUID<input v-model="startSnapshotId" /></label><label>已确认 review version<input v-model.number="reviewVersion" type="number" min="1" /></label><label>已有授权 grant UUID（逗号分隔）<input v-model="grants" /></label></div><label class="inline"><input v-model="publicReadonly" type="checkbox" />公共第三方免费只读（HTTP 与 MCP 两个授权）</label><div v-if="!publicReadonly" class="form-grid three"><label>本地评价套件<select v-model="suiteId" @change="suiteId === 'm1-smoke-v1' && (capabilityId = 'anchor_record')"><option value="m1-smoke-v1">M1 本地写入演示</option><option value="capabilities-v1">三类能力模板</option></select></label><label>评价能力<select aria-label="评价能力" v-model="capabilityId" :disabled="suiteId === 'm1-smoke-v1'"><option value="anchor_record">anchor_record</option><option value="get_tx_status">get_tx_status</option><option value="verify_record">verify_record</option></select></label><label v-if="capabilityId !== 'get_tx_status'">目标合约（可空，使用后端本地配置）<input v-model="targetContract" /></label></div><label v-if="!publicReadonly && capabilityId === 'get_tx_status'">Query tx_hash<input v-model="queryTxHash" placeholder="0x + 64位hex，本地测试链交易" /></label><div v-if="!publicReadonly && capabilityId === 'verify_record'" class="form-grid three"><label>Record executor<input v-model="recordExecutor" /></label><label>Record request_id<input v-model="recordRequestId" /></label><label>Record hash<input v-model="recordHash" /></label></div><p class="hint">本地三类任务只使用测试链；公共 Agent 使用固定免费只读套件。能力、输入或授权不匹配由后端拒绝。</p><div class="form-grid"><label>Idempotency key<input v-model="idempotencyKey" /></label><button :disabled="busy || !operatorToken" @click="startEvaluation">启动评价</button></div><button class="link-button" @click="newEvaluationKey">开始一项新评价时生成新 key</button></article>
      <article class="card"><h2>任务进度</h2><div class="form-grid"><label>Run UUID<input v-model="lookupRunId" /></label><button :disabled="busy" @click="loadEvaluation()">加载 / 刷新</button></div><p v-if="!evaluation" class="empty">尚未加载任务。</p><template v-else><div class="facts"><div><span>运行状态</span><strong>{{ evaluation.status }}</strong></div><div><span>阶段</span><strong>{{ evaluation.stage }}</strong></div><div><span>进度 / UNKNOWN</span><strong>{{ evaluation.settled }} / {{ evaluation.planned }} · {{ evaluation.unknown }}</strong></div></div><p class="hint">非终态每 2 秒更新。任务被接受、返回成功交易、业务 PASS 是三个独立事实。</p><div class="buttons"><button :disabled="busy || isTerminal || !operatorToken" @click="cancelEvaluation">取消评价</button><button :disabled="busy || !isTerminal || !!report || !operatorToken" @click="requestReport">生成冻结报告</button><button :disabled="!report" @click="activeTab = 'evidence'">查看声誉与证据</button></div><p v-if="plan">已确认能力：{{ plan.confirmed_capabilities.join('、') }} · 套件 {{ plan.suite_id }}</p><div class="table-wrap"><table><thead><tr><th>任务 / 尝试</th><th>Agent 执行观测</th><th>HTTP</th><th>接受</th><th>失败原因</th><th>耗时</th></tr></thead><tbody><tr v-for="item in observations" :key="item.observation_id"><td>{{ short(item.slot_id) }} / {{ item.attempt_no }}</td><td>{{ item.dispatch_state }}</td><td>{{ item.http_status ?? '—' }}</td><td>{{ item.accepted ? '已接受' : '未接受' }}</td><td>{{ item.reason_code ?? '—' }}</td><td>{{ item.latency_ms == null ? '未测得' : `${item.latency_ms} ms` }}</td></tr></tbody></table></div><p v-if="!observations.length" class="empty">尚无任务执行观测。</p><p v-if="reportJob" class="hint">报告任务 {{ reportJob.state }} · {{ reportJob.reason_code ?? '无失败原因' }}</p><h3>平台独立链上核验</h3><div v-for="(item, index) in verification" :key="index" class="observation"><strong>{{ item.outcome }}</strong><span>{{ item.reason_code ?? '断言通过' }}</span><span>任务匹配 {{ item.task_link.match_status }}</span><small>执行者 {{ item.task_link.executor ?? 'UNKNOWN' }} · 链上区块 {{ item.task_link.block_number ?? '—' }} · 核验交易 {{ item.task_link.verified_tx_hash ?? '无核验交易' }}</small></div><p v-if="!verification.length" class="empty">核验尚未完成。</p></template></article>
    </section>

    <section v-else-if="activeTab === 'evidence'" class="stack">
      <article class="card"><div class="section-heading"><h2>声誉、充分度与关键风险</h2><button :disabled="!report || busy" @click="downloadEvidence">下载 Evidence Bundle</button></div><p v-if="!report" class="empty">尚未选择冻结报告。</p><template v-else><div class="score-head"><strong>{{ report.core.scores.evaluation_state }}</strong><span>综合分：{{ scoreLabel(report.core.scores.overall_score_bp) }}</span></div><div class="dimensions"><div v-for="dimension in dimensionLabels" :key="dimension.key"><span>{{ dimension.label }}</span><strong>{{ report.core.scores.dimensions[dimension.key]?.state ?? 'UNKNOWN' }}</strong><small>{{ scoreLabel(report.core.scores.dimensions[dimension.key]?.score_bp) }}</small><small>观测分 {{ scoreLabel(report.core.scores.dimensions[dimension.key]?.observed_score_bp) }}</small><small>覆盖 {{ report.core.scores.dimensions[dimension.key]?.coverage_bp ?? '—' }} bp · 样本比例 {{ report.core.scores.dimensions[dimension.key]?.sample_bp ?? '—' }} bp</small></div></div><p>证据充分度 {{ report.core.scores.sufficiency_bp }} bp · 建议 {{ report.core.scores.advice }}</p><p>任务分布：{{ report.core.task_counts ? JSON.stringify(report.core.task_counts) : '历史格式无四态摘要' }}</p><p>风险：{{ report.core.risk_assessment?.conclusion ?? (report.core.scores.critical_conflict ? '关键冲突' : '历史格式无独立风险评估') }}</p><div v-for="risk in report.core.risk_assessment?.critical_findings ?? []" :key="risk.assertion_id" class="notice error"><strong>{{ risk.reason_code }}</strong> · 任务 {{ risk.slot_id }}<p>规则 {{ risk.rule_id }} · 证据 {{ risk.evidence_refs.join('、') }}</p></div><p v-if="report.core.evidence_sufficiency">充分度门槛 {{ report.core.evidence_sufficiency.gate_status }} · 未覆盖声明 {{ report.core.evidence_sufficiency.uncovered_claims?.join('、') || '无' }} · 缺失证据 {{ report.core.evidence_sufficiency.missing_evidence?.join('、') || '无' }}</p><p class="hint">{{ [...report.core.scores.limitations, ...report.core.limitations].join('；') }}</p></template></article>
      <article v-if="report && sampleSections" class="card"><details><summary>实际样本数与能力覆盖（后端统计）</summary><p class="hint">planned 为计划数，decided 为可判定数，responded 为响应数，accepted 为接受数，passed / correct 为通过数；这些是实际数量，bp 为比例。covered_classes / required_classes 为已覆盖 / 要求用例类别，tested_claim_count / claim_count 为已测试 / 声明能力数量。</p><h3>执行观测与能力样本</h3><pre v-if="Object.keys(sampleSections.statistics).length">{{ JSON.stringify(sampleSections.statistics, null, 2) }}</pre><p v-else class="empty">历史报告未提供实际样本统计。</p><h3>三维充分度与能力覆盖数量</h3><pre v-if="sampleSections.dimensions">{{ JSON.stringify(sampleSections.dimensions, null, 2) }}</pre><p v-else class="empty">历史报告未提供维度样本与覆盖明细。</p><h3>每项能力的样本与用例覆盖</h3><pre v-if="sampleSections.capabilities?.length">{{ JSON.stringify(sampleSections.capabilities, null, 2) }}</pre><p v-else class="empty">报告未提供能力样本与用例覆盖明细。</p></details></article>
      <article v-if="report" class="card"><h2>冻结报告与任务证据</h2><div class="facts"><div><span>Report / version</span><strong>{{ short(report.report_id) }} / {{ report.core.schema_version }}</strong></div><div><span>报告摘要</span><strong>{{ report.report_hash }}</strong></div><div><span>链上锚定</span><strong>{{ anchor?.status === 'NOT_REQUESTED' ? 'UNANCHORED / NOT_REQUESTED' : anchor?.status ?? '锚定状态未查询' }}</strong><small>{{ anchor?.tx_hash ?? '无已确认锚定交易' }}</small></div></div><p>规则 {{ report.core.scoring_rule_version ?? '历史规则' }} · policy {{ report.core.policy_version }} · {{ short(report.core.policy_hash) }}</p><p class="hint">锚定发生在本地测试链；只有 CONFIRMED 才表示该链已确认。</p><details v-for="task in report.core.task_results ?? []" :key="task.slot_id"><summary>{{ task.capability_id }} · {{ task.outcome }} · {{ task.reason_code ?? 'PASS' }}</summary><p>任务 {{ task.slot_id }} · 输入证据 {{ task.input_evidence_id }} · rule {{ task.rule_version }}</p><button :disabled="busy" @click="loadTaskEvidence(task.input_evidence_id)">读取冻结任务输入、响应与链上证据</button><template v-for="assertion in report.core.assertions.filter(item => item.slot_id === task.slot_id)" :key="assertion.assertion_id"><p>{{ assertion.rule_id }}：{{ assertion.outcome }} / {{ assertion.reason_code ?? 'PASS' }} · 关键 {{ assertion.critical ? '是' : '否' }}</p><pre>{{ JSON.stringify({ expected: assertion.expected, observed: assertion.observed }, null, 2) }}</pre><small>证据引用 {{ assertion.evidence_refs.join('、') }}</small></template></details><p v-if="!report.core.task_results?.length" class="hint">历史报告没有逐任务摘要，下载原 Evidence Bundle 使用兼容 Verifier 复核。</p></article>
      <article v-if="taskEvidence && evidenceSections" class="card"><h2>冻结任务输入与原始证据</h2><p>内容来自当前报告 manifest 内的已脱敏证据，并经后端重新校验摘要。证据摘要 {{ taskEvidence.record.blob_hash }}</p><h3>任务输入</h3><pre>{{ JSON.stringify(evidenceSections.input, null, 2) }}</pre><h3>Agent 响应</h3><pre>{{ JSON.stringify(evidenceSections.response, null, 2) }}</pre><h3>链上证据</h3><pre>{{ JSON.stringify(evidenceSections.chain, null, 2) }}</pre></article>
      <article class="card"><h2>独立 Verifier 结果（本地导入）</h2><p>用户导入的独立 CLI 结果：文件只在本地读取，不上传平台，也不代表后端或可信 RPC 已确认。</p><label>Verifier CLI JSON（最大 1 MiB）<input type="file" accept="application/json,.json" @change="importVerifierFile" /></label><p v-if="verifierFileName" class="hint">已选择 {{ verifierFileName }}</p><p v-if="verifierImportError" class="notice error" role="alert">{{ verifierImportError }}</p><template v-if="verifierImport"><div class="facts"><div><span>CLI 顶层状态</span><strong>{{ verifierImport.status }}</strong><small v-if="verifierImport.code">{{ verifierImport.code }}</small></div><div><span>离线证据状态</span><strong>{{ verifierImport.offline ?? '未提供' }}</strong></div><div><span>当前报告摘要比对</span><strong>{{ verifierHashLabel }}</strong><small v-if="verifierImport.reportHash">CLI {{ verifierImport.reportHash }}</small></div></div><p v-if="verifierImport.message" class="notice error">Verifier 失败原因：{{ verifierImport.message }}</p><div v-if="verifierImport.taskResults.length" class="table-wrap"><table><thead><tr><th>任务</th><th>离线结果</th><th>原因</th><th>可信链状态</th></tr></thead><tbody><tr v-for="task in verifierImport.taskResults" :key="task.slotId"><td>{{ task.capabilityId }} · {{ task.slotId }}</td><td>{{ task.outcome }}</td><td>{{ task.reasonCode ?? '—' }}</td><td>{{ task.liveChain?.status ?? '未提供' }}<span v-if="task.liveChain?.outcome"> · 当前 {{ task.liveChain.outcome }}</span><small v-if="task.liveChain?.historicalOutcome">历史 {{ task.liveChain.historicalOutcome }} / {{ task.liveChain.historicalReasonCode ?? '—' }}</small><small>{{ task.liveChain?.reasonCode ?? task.liveChain?.reason ?? '—' }}</small></td></tr></tbody></table></div><p>任务计数比对：{{ verifierImport.taskCountComparison ?? '未提供' }} · 评价断言比对：{{ verifierImport.assessmentComparison ?? '未提供' }}</p><p v-if="verifierImport.taskCounts">Verifier 任务计数：{{ JSON.stringify(verifierImport.taskCounts) }}</p><p v-if="verifierImport.anchor">锚定核验：{{ verifierImport.anchor.status }}<span v-if="verifierImport.anchor.reason"> · {{ verifierImport.anchor.reason }}</span><span v-if="verifierImport.anchor.confirmations != null"> · confirmations {{ verifierImport.anchor.confirmations }}</span></p></template></article>
      <article v-if="report" class="card"><h2>独立 Verifier 复核</h2><p>页面显示平台独立任务断言。下载 ZIP 后，可在独立进程重判任务并复算分数；离线通过只证明冻结证据内部一致性。</p><pre>uv run --all-packages reputation-verify report-{{ report.report_id }}.zip</pre><p>受控本地链：使用操作者信任的 RPC 核查当前链状态和锚定。</p><pre>uv run --all-packages reputation-verify report-{{ report.report_id }}.zip --rpc-url http://127.0.0.1:8545</pre><p class="hint">公共第三方报告的业务链为 Base，应使用可信 Base RPC 作为 --task-rpc-url；报告锚定链与任务链可不同。此页面没有将未运行的 CLI 复核显示为 PASS。</p></article>
    </section>

    <section v-else class="stack"><article class="card"><h2>同一 Agent 的历史评价</h2><p v-if="!agent" class="empty">先选择 Agent。</p><p v-else-if="!history.length" class="empty">该 Agent 尚无冻结评价报告。</p><template v-else><div class="table-wrap"><table><thead><tr><th>时间 / 快照</th><th>范围 / 规则</th><th>状态 / 综合分</th><th>风险 / 充分度</th><th></th></tr></thead><tbody><tr v-for="item in history" :key="item.report_id"><td>{{ item.core.evaluated_at }}<br />{{ short(item.core.snapshot_hash) }}</td><td>{{ item.core.profile }} / {{ item.core.schema_version }}</td><td>{{ item.core.scores.evaluation_state }}<br />{{ scoreLabel(item.core.scores.overall_score_bp) }}</td><td>{{ item.core.scores.critical_conflict ? '关键风险' : '无已确认关键风险' }} / {{ item.core.scores.sufficiency_bp }} bp</td><td><button @click="selectReport(item)">查看</button></td></tr></tbody></table></div><label v-if="report" class="history-select">与当前报告比较<select v-model="comparisonId"><option value="">选择报告</option><option v-for="item in history.filter(item => item.report_id !== report?.report_id)" :key="item.report_id" :value="item.report_id">{{ item.core.evaluated_at }} · {{ short(item.report_id) }}</option></select></label><template v-if="report && comparison"><p v-if="comparisonReason" class="notice error">{{ comparisonReason }}</p><p v-else class="notice success">当前报告与所选报告规则和评价范围一致，可比较已形成的正式评分。</p><div v-if="!comparisonReason" class="dimensions"><div v-for="dimension in dimensionLabels" :key="dimension.key"><span>{{ dimension.label }}</span><strong>{{ scoreLabel(comparison.core.scores.dimensions[dimension.key]?.score_bp) }} → {{ scoreLabel(report.core.scores.dimensions[dimension.key]?.score_bp) }}</strong></div></div><p v-if="!comparisonReason">充分度 {{ comparison.core.scores.sufficiency_bp }} → {{ report.core.scores.sufficiency_bp }} bp；关键风险 {{ comparison.core.scores.critical_conflict ? '有' : '无' }} → {{ report.core.scores.critical_conflict ? '有' : '无' }}</p><p v-else>所选报告：{{ comparison.core.scores.evaluation_state }}，充分度 {{ comparison.core.scores.sufficiency_bp }} bp，关键风险{{ comparison.core.scores.critical_conflict ? '有' : '无' }}。当前报告：{{ report.core.scores.evaluation_state }}，充分度 {{ report.core.scores.sufficiency_bp }} bp，关键风险{{ report.core.scores.critical_conflict ? '有' : '无' }}。</p></template></template></article></section>
  </main>
</template>

<style>
.card, .facts > div, .dimensions > div { min-width: 0; }
:root { font-family: Inter, ui-sans-serif, system-ui, sans-serif; color: #172b35; background: #eef4f3; } * { box-sizing: border-box; } body { margin: 0; } button, input, select { font: inherit; } button { border: 0; border-radius: 8px; padding: 10px 16px; background: #176b68; color: white; cursor: pointer; } button:disabled { cursor: default; opacity: .5; } input, select { width: 100%; border: 1px solid #bdcfcc; border-radius: 7px; padding: 10px; color: #172b35; background: #fbfdfc; } .inline { display: flex; align-items: center; gap: 8px; }.inline input { width: auto; } label { display: grid; gap: 7px; color: #48626a; font-size: 13px; } small { overflow-wrap: anywhere; color: #668087; display: block; margin-top: 5px; }
.shell { max-width: 1180px; margin: 0 auto; padding: 40px 24px 72px; } .hero { display: flex; gap: 24px; justify-content: space-between; align-items: flex-start; margin-bottom: 28px; } .hero h1 { font-size: clamp(30px, 5vw, 48px); letter-spacing: -.03em; margin: 6px 0 10px; } .hero p, .hint { color: #577078; line-height: 1.7; } .eyebrow { margin: 0; color: #4c7d7a; font-size: 12px; font-weight: 700; letter-spacing: .12em; }.hint { font-size: 13px; }
.connection { white-space: nowrap; display: flex; align-items: center; gap: 8px; background: #fff; border: 1px solid #d3e0df; border-radius: 999px; padding: 9px 12px; font-size: 13px; } .dot { width: 9px; height: 9px; border-radius: 50%; background: #d49a3a; }.connected .dot { background: #2b9b75; }.unavailable .dot { background: #c24d53; }.link-button { background: none; color: #176b68; padding: 0; text-decoration: underline; }
.card { background: #fff; border: 1px solid #d4e1df; border-radius: 14px; padding: 22px; box-shadow: 0 8px 28px #173d3a0b; }.operator { margin-bottom: 20px; }.tabs { display: flex; flex-wrap: wrap; gap: 6px; border-bottom: 1px solid #cadbd8; margin-bottom: 22px; }.tabs button { background: transparent; color: #557078; border-radius: 8px 8px 0 0; }.tabs button.selected { color: #176b68; background: #dcecea; font-weight: 700; }.stack { display: grid; gap: 18px; }.section-heading { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }.section-heading h2 { margin: 5px 0 18px; }.form-grid { display: grid; grid-template-columns: 1fr auto; gap: 12px; align-items: end; margin: 16px 0; }.form-grid.three { grid-template-columns: repeat(3, 1fr); }.history-select { margin: 20px 0; }.buttons { display: flex; flex-wrap: wrap; gap: 8px; }
.notice { padding: 12px 14px; border-radius: 8px; }.success { background: #e4f5ec; color: #1c6548; }.error { background: #fbe8e8; color: #8c3038; }.pill { display: inline-block; padding: 5px 8px; border-radius: 7px; color: #176b68; background: #e2f0ed; font-size: 12px; overflow-wrap: anywhere; }.facts { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }.facts div, .dimensions div { background: #f4f8f7; border-radius: 9px; padding: 12px; }.facts span, .dimensions span { display: block; color: #668087; font-size: 12px; margin-bottom: 5px; }.facts strong { overflow-wrap: anywhere; font-size: 14px; }.capabilities { display: flex; flex-wrap: wrap; gap: 7px; margin-top: 18px; }.empty { color: #788f94; }.observation { display: grid; grid-template-columns: 1fr 2fr 1fr; gap: 10px; padding: 12px 0; border-top: 1px solid #e7efed; font-size: 13px; overflow-wrap: anywhere; }.observation small { grid-column: 1 / -1; }.agent-list { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 9px; margin-bottom: 14px; }.agent-choice { display: grid; gap: 4px; text-align: left; background: #f4f8f7; color: #172b35; }.agent-choice span { color: #60787f; font-size: 12px; }
.score-head { display: flex; gap: 18px; align-items: baseline; margin-bottom: 16px; }.score-head strong { font-size: 22px; }.dimensions { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }.dimensions strong { display: block; font-size: 15px; } details { margin-top: 18px; border-top: 1px solid #e2ecea; padding-top: 15px; } summary { color: #176b68; cursor: pointer; font-weight: 650; } pre { background: #172b35; color: #d9efea; padding: 16px; border-radius: 8px; overflow: auto; max-height: 300px; font-size: 12px; }.table-wrap { overflow-x: auto; } table { width: 100%; border-collapse: collapse; text-align: left; margin-top: 16px; font-size: 13px; } th, td { border-bottom: 1px solid #e2ecea; padding: 10px; } th { color: #668087; font-weight: 600; }
@media (max-width: 760px) { .hero { display: block; }.connection { display: inline-flex; }.form-grid, .form-grid.three, .facts, .dimensions { grid-template-columns: 1fr; }.observation { grid-template-columns: 1fr; gap: 4px; }.shell { padding: 28px 15px 48px; } }
</style>
