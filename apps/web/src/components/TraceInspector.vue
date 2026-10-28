<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import type { SharedObservation } from '../contracts'
import type { TraceNode } from '../traceProjection'
import { businessText, criterionTitles, traceExplorerUrl } from '../traceProjection'
import { chainName } from '../agentProfile'
import { when } from '../format'
import EvidenceList from './EvidenceList.vue'
import '../inspector.css'

const props = defineProps<{ node: TraceNode | null; reportId: string; taskKey: string }>()
defineEmits<{ close: [] }>()
const copyStatus = ref('')
const copyFailed = ref(false)
const selectedSource = ref('')
const rawText = ref('')
const rawError = ref('')
const rawLoading = ref(false)
const fullAddresses = ref(false)
const inputFields = computed(() => props.node?.input.filter(field => !props.node?.action
  || !['执行账户', '调用目标', '合约方法'].includes(field.label)) ?? [])
const outputFields = computed(() => props.node?.output.filter(field => !props.node?.action
  || !['交易哈希', 'chain_id', '区块'].includes(field.label)) ?? [])
const businessFields = computed(() => props.node?.business.filter(field => field.value !== props.node?.summary) ?? [])
const checks = computed(() => props.node?.checks ?? [])
const passedChecks = computed(() => checks.value.filter(check => check.measurement_validity === 'valid' && check.verdict === 'PASS'))
const attentionChecks = computed(() => checks.value.filter(check => check.measurement_validity !== 'valid' || check.verdict === 'FAIL' || check.verdict === 'UNKNOWN'))
const counts = computed(() => ({
  pass: passedChecks.value.length,
  fail: checks.value.filter(check => check.measurement_validity === 'valid' && check.verdict === 'FAIL').length,
  unknown: checks.value.filter(check => check.measurement_validity === 'unknown' || check.measurement_validity === 'valid' && check.verdict === 'UNKNOWN').length,
  invalid: checks.value.filter(check => check.measurement_validity === 'invalid').length,
  excluded: checks.value.filter(check => check.measurement_validity === 'valid' && check.verdict === 'NOT_APPLICABLE').length,
}))
const previewPaths = computed(() => props.node?.evidence.filter(path => path.startsWith('runtime/') && /\.(?:json|response\.bin)$/i.test(path)) ?? [])
const actionFields = computed(() => props.node?.action ? [
  { label: '交易哈希', value: props.node.action.transaction_hash, kind: 'tx' as const },
  { label: '用户执行账户', value: props.node.action.executor, kind: 'address' as const },
  { label: '调用目标合约', value: props.node.action.target, kind: 'address' as const },
] : [])
const shortAddress = (value: string) => /^0x[\da-f]{40,64}$/i.test(value) ? value.slice(0, 8) + '…' + value.slice(-6) : value
const checkLabel = (check: SharedObservation) => check.measurement_validity === 'invalid' ? '测量无效'
  : check.measurement_validity === 'unknown' || check.verdict === 'UNKNOWN' ? '无法判断'
  : check.verdict === 'FAIL' ? '未通过' : check.verdict === 'NOT_APPLICABLE' ? '不适用' : '通过'
const checkTone = (check: SharedObservation) => check.measurement_validity === 'valid' && check.verdict === 'FAIL' ? 'failure' : 'unknown'
let previewAbort: AbortController | undefined
let previewVersion = 0

function clearPreview() {
  previewVersion += 1
  previewAbort?.abort()
  previewAbort = undefined
  rawText.value = ''
  rawError.value = ''
  rawLoading.value = false
}

watch(() => [props.node?.id, props.reportId, props.taskKey, previewPaths.value.join('\n')], () => {
  clearPreview()
  selectedSource.value = previewPaths.value[0] ?? ''
  copyStatus.value = ''
  copyFailed.value = false
  fullAddresses.value = false
}, { immediate: true })
onBeforeUnmount(clearPreview)

async function copy(value: string, label: string) {
  const nodeId = props.node?.id
  const taskKey = props.taskKey
  const reportId = props.reportId
  copyFailed.value = false
  try {
    await navigator.clipboard.writeText(value)
    if (props.node?.id !== nodeId || props.reportId !== reportId || props.taskKey !== taskKey) return
    copyStatus.value = `${label}已完整复制`
  } catch {
    if (props.node?.id !== nodeId || props.reportId !== reportId || props.taskKey !== taskKey) return
    copyFailed.value = true
    fullAddresses.value = true
    copyStatus.value = '浏览器未允许复制，可选中下方完整内容手动复制。'
  }
}

async function preview() {
  clearPreview()
  const path = selectedSource.value
  if (!props.node?.evidence.includes(path) || !previewPaths.value.includes(path)) return
  const version = previewVersion
  const abort = new AbortController()
  previewAbort = abort
  rawLoading.value = true
  const maxBytes = 1024 * 1024
  try {
    const response = await fetch(`/api/reports/${encodeURIComponent(props.reportId)}/evidence?path=${encodeURIComponent(path)}`, { signal: abort.signal })
    if (!response.ok) throw new Error(`此报告引用的原件暂时不可读（HTTP ${response.status}）。`)
    if (Number(response.headers.get('Content-Length')) > maxBytes) {
      await response.body?.cancel()
      throw new Error('原件超过 1 MiB 预览上限，请使用证据下载入口。')
    }
    if (!response.body) throw new Error('此原件没有可读内容，请使用证据下载入口。')
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let bytes = 0
    let text = ''
    try {
      while (true) {
        const chunk = await reader.read()
        if (chunk.done) break
        bytes += chunk.value.byteLength
        if (bytes > maxBytes) {
          await reader.cancel()
          throw new Error('原件超过 1 MiB 预览上限，请使用证据下载入口。')
        }
        text += decoder.decode(chunk.value, { stream: true })
      }
      text += decoder.decode()
    } finally { reader.releaseLock() }
    let formatted: string
    try { formatted = JSON.stringify(JSON.parse(text), null, 2) }
    catch { throw new Error('原件无法解析为 JSON；可下载原文件核对。') }
    if (version === previewVersion) rawText.value = formatted
  } catch (error) {
    if (!abort.signal.aborted && version === previewVersion) rawError.value = error instanceof Error ? error.message : '原件读取失败。'
  } finally {
    if (version === previewVersion) rawLoading.value = false
  }
}
</script>

<template>
  <div class="trace-inspector">
    <header class="ti-header">
      <span class="ti-kicker">步骤检查 <small>EVIDENCE INSPECTOR</small></span>
      <button class="ti-close" type="button" aria-label="关闭步骤检查面板" @click="$emit('close')"><svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="m5 5 10 10M15 5 5 15" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg></button>
    </header>
    <div v-if="node" :key="`${reportId}:${taskKey}:${node.id}`" class="ti-content" :class="'ti-status-'+node.status">
      <section class="ti-selected" aria-label="当前步骤结论">
        <p class="ti-role">{{ node.role }}</p>
        <div class="ti-node-heading"><h2 id="trace-inspector-title">{{ node.title }}</h2></div>
        <span class="ti-business-status" :class="node.status">{{ node.statusLabel }}</span>
        <p class="ti-summary">{{ node.summary }}</p>
      </section>

      <section v-if="businessFields.length" class="ti-section ti-business-section">
        <h3>关键业务信息</h3>
        <dl class="ti-fields"><div v-for="(field, index) in businessFields" :key="`${field.label}:${index}`"><dt>{{ field.label }}</dt><dd>{{ field.value }}</dd></div></dl>
      </section>

      <details v-if="node.action" class="ti-section ti-chain-section ti-disclosure">
        <summary><span>关键链上操作</span><span class="ti-chain-tag">{{ chainName(node.action.chain_id) }}</span></summary>
        <dl class="ti-fields">
          <div><dt>执行动作</dt><dd>{{ node.title }}</dd></div>
          <div class="ti-chain-facts"><div><dt>网络 / Chain ID</dt><dd>{{ chainName(node.action.chain_id) }} · {{ node.action.chain_id }}</dd></div><div><dt>交易回执</dt><dd :class="{'ti-failed':node.receiptStatus === 'failed'}">{{ node.receiptStatus === 'success' ? '交易成功' : node.receiptStatus === 'failed' ? '交易失败' : '未读取或未记录' }}</dd></div></div>
          <div><dt>区块高度</dt><dd><a v-if="traceExplorerUrl(node.action.chain_id, 'block', String(node.action.block_number))" :href="traceExplorerUrl(node.action.chain_id, 'block', String(node.action.block_number))" target="_blank" rel="noopener noreferrer" class="ti-mono">#{{ node.action.block_number }} ↗</a><span v-else class="ti-mono">{{ node.action.block_number == null ? '未记录' : '#' + node.action.block_number }}</span></dd></div>
          <div v-for="field in actionFields" :key="field.label" class="ti-address-field">
            <dt>{{ field.label }}<button v-if="field.value" type="button" :aria-label="`复制完整${field.label}`" class="ti-copy" @click="copy(field.value, field.label)">复制</button></dt>
            <dd class="ti-mono"><a v-if="traceExplorerUrl(node.action.chain_id, field.kind, field.value)" :href="traceExplorerUrl(node.action.chain_id, field.kind, field.value)" :title="field.value" target="_blank" rel="noopener noreferrer">{{ fullAddresses ? field.value : shortAddress(field.value) }} <span class="sr-only">（区块浏览器，新窗口打开）</span><span aria-hidden="true">↗</span></a><span v-else>{{ field.value || '未记录' }}</span></dd>
          </div>
          <div><dt>原始合约方法</dt><dd class="ti-mono">{{ node.action.method || '未记录' }}</dd></div>
        </dl>
        <button type="button" class="ti-inline-button" :aria-expanded="fullAddresses" @click="fullAddresses=!fullAddresses">{{ fullAddresses ? '缩略地址与交易哈希' : '显示完整地址与交易哈希' }}</button>
        <p v-if="copyStatus" class="ti-copy-status" :class="{ error: copyFailed }" role="status">{{ copyStatus }}</p>
        <p class="ti-context-note">回执说明交易是否被链上执行；功能是否符合要求见下方核验。</p>
      </details>

      <section class="ti-section ti-verification-section">
        <h3>核验结果</h3>
        <div v-if="checks.length" class="ti-check-counts" aria-label="本步骤核验统计"><span class="pass">{{ counts.pass }} 通过</span><span :class="{failure:counts.fail}">{{ counts.fail }} 未通过</span><span :class="{unknown:counts.unknown}">{{ counts.unknown }} 未知</span><span v-if="counts.invalid" class="unknown">{{ counts.invalid }} 测量无效</span><span v-if="counts.excluded">{{ counts.excluded }} 不适用</span></div>
        <p v-if="!checks.length" class="ti-context-note">本步骤没有独立判据观测。已记录业务与平台核验分别展示。</p>
        <div v-if="attentionChecks.length" class="ti-attention-checks">
          <article v-for="check in attentionChecks" :key="check.case_id+':'+check.criterion_id" class="ti-check-issue" :class="checkTone(check)">
            <div><strong>{{ criterionTitles[check.criterion_id] || check.criterion_id }}</strong><span>{{ checkLabel(check) }}</span></div>
            <p>{{ businessText(check.reason) }}</p>
          </article>
        </div>
        <p v-else-if="passedChecks.length" class="ti-verification-note">本步骤已采集的 {{ passedChecks.length }} 项检查通过，结论依据见逐项结果。</p>
        <details v-if="passedChecks.length" class="ti-pass-checks"><summary>查看 {{ passedChecks.length }} 项通过依据</summary><article v-for="check in passedChecks" :key="check.case_id+':'+check.criterion_id"><strong>{{ criterionTitles[check.criterion_id] || check.criterion_id }}</strong><p>{{ businessText(check.reason) }}</p></article></details>
      </section>

      <details class="ti-section ti-technical ti-disclosure">
        <summary><span>技术详情 / 原始证据</span><small>按需追溯</small></summary>
        <section v-if="previewPaths.length" class="ti-technical-part ti-preview-section">
          <h4>原始 JSON</h4><p class="ti-preview-note">读取当前步骤已引用的报告原件。</p>
          <label class="sr-only" for="trace-json-source">选择已引用的 JSON 原件</label><select id="trace-json-source" v-model="selectedSource" @change="clearPreview"><option v-for="(path,index) in previewPaths" :key="path" :value="path">{{ index + 1 }} · {{ path.split('/').slice(-2).join('/') }}</option></select>
          <p class="ti-source-path">{{ selectedSource }}</p>
          <button type="button" class="ti-preview-button" :disabled="rawLoading || !selectedSource" @click="preview"><span v-if="rawLoading" class="spinner small-spinner" aria-hidden="true"></span>{{ rawLoading ? '读取中…' : rawText ? '重新读取原件' : '查看原始 JSON' }}</button>
          <p v-if="rawError" class="ti-preview-error" role="status">{{ rawError }}</p><pre v-if="rawText" class="ti-raw" tabindex="0" aria-label="当前步骤原始 JSON">{{ rawText }}</pre>
        </section>
        <dl class="ti-metadata">
          <div><dt>报告标识</dt><dd class="ti-mono">{{ reportId }}</dd></div><div><dt>任务标识</dt><dd class="ti-mono">{{ taskKey }}</dd></div><div><dt>步骤标识</dt><dd class="ti-mono">{{ node.id }}</dd></div><div><dt>记录来源</dt><dd>{{ node.source }}</dd></div>
          <div><dt>{{ node.timeLabel || '步骤发生时间' }}</dt><dd :class="node.timestamp ? 'ti-mono' : 'ti-missing'">{{ node.timestamp ? when(node.timestamp) : '未记录' }}</dd></div>
        </dl>
        <section v-if="inputFields.length" class="ti-technical-part"><h4>完整输入记录</h4><dl class="ti-fields"><div v-for="(field, index) in inputFields" :key="`${field.label}:${index}`"><dt>{{ field.label }}</dt><dd>{{ field.value }}</dd></div></dl></section>
        <section v-if="outputFields.length" class="ti-technical-part"><h4>完整输出与观测记录</h4><dl class="ti-fields"><div v-for="(field, index) in outputFields" :key="`${field.label}:${index}`"><dt>{{ field.label }}</dt><dd>{{ field.value }}</dd></div></dl></section>
        <section v-if="node.action" class="ti-technical-part"><h4>完整链上操作摘要</h4><pre class="ti-raw" tabindex="0" aria-label="完整链上操作摘要">{{ JSON.stringify(node.action, null, 2) }}</pre></section>
        <section v-if="checks.length" class="ti-technical-part"><h4>原始判据与观测记录</h4><pre class="ti-raw" tabindex="0" aria-label="原始核验观测">{{ JSON.stringify(checks, null, 2) }}</pre></section>
        <section class="ti-technical-part ti-evidence-section"><h4>证据引用与原件下载</h4><EvidenceList :sources="node.evidence" :report-id="reportId" /></section>
      </details>
    </div>
    <div v-else class="ti-empty"><h2 id="trace-inspector-title">选择一个步骤</h2><p>点击任务节点，查看业务说明、核验结果和原始证据。</p></div>
  </div>
</template>
