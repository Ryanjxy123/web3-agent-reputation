<script setup lang="ts">
import { computed, ref } from 'vue'
import type { ChainAction } from '../contracts'
import { chainName } from '../agentProfile'
import EvidenceList from './EvidenceList.vue'
import StatusBadge from './StatusBadge.vue'

const props = defineProps<{
  actions: ChainAction[]
  summary: string
  limitations: string[]
  reportId?: string
  agentKey?: string
  sampleLinks?: Record<string, number>
}>()

const copied = ref('')
const copyError = ref(false)
const expanded = ref(false)
const shownActions = computed(() => expanded.value || props.actions.length <= 3 ? props.actions
  : props.actions.filter(action => action.sample_id === props.actions[0]?.sample_id))
const explorers: Record<number, string> = { 56: 'https://bscscan.com', 100: 'https://gnosisscan.io', 8453: 'https://basescan.org' }
const shorten = (value: string) => value.length > 22 ? `${value.slice(0, 12)}…${value.slice(-8)}` : value
const transactionLink = (chain: number, hash: string | null) => explorers[chain] && hash && /^0x[0-9a-fA-F]{64}$/.test(hash)
  ? `${explorers[chain]}/tx/${hash}` : undefined
const blockLink = (chain: number, block: number) => explorers[chain] ? `${explorers[chain]}/block/${block}` : undefined

async function copy(value: string) {
  copyError.value = false
  try {
    await navigator.clipboard.writeText(value)
    copied.value = value
  } catch { copyError.value = true }
}
</script>

<template>
  <section class="panel chain-evidence-panel" aria-label="链上操作与核验证据">
    <div class="section-heading"><div><p class="eyebrow">从任务到真实交易</p><h2>链上实际发生了什么</h2></div><span class="muted small">{{ actions.length }} 项操作</span></div>
    <p class="section-description">{{ summary }}</p>
    <p v-if="shownActions.length < actions.length" class="muted small">先展示一个实际任务的完整操作，其余 {{ actions.length - shownActions.length }} 项可展开查看。</p>
    <ol v-if="actions.length" class="chain-actions">
      <li v-for="(action, index) in shownActions" :key="`${action.sample_id}:${action.transaction_hash}:${index}`" class="chain-action">
        <div class="chain-action-heading"><span class="chain-step">{{ String(index + 1).padStart(2, '0') }}</span><h3>{{ action.title }}</h3><StatusBadge :verdict="action.verdict" /></div>
        <p class="chain-business-result">{{ action.summary }}</p>
        <dl class="chain-action-facts">
          <div><dt>链与区块</dt><dd>{{ chainName(action.chain_id) }}<template v-if="action.block_number !== null"> · <a v-if="blockLink(action.chain_id, action.block_number)" :href="blockLink(action.chain_id, action.block_number)" target="_blank" rel="noopener noreferrer">#{{ action.block_number.toLocaleString('en-US') }}</a><span v-else>#{{ action.block_number }}</span></template></dd></div>
          <div><dt>实际调用</dt><dd>{{ action.method }}</dd></div>
          <div class="full"><dt>交易哈希</dt><dd class="chain-transaction"><template v-if="action.transaction_hash"><a v-if="transactionLink(action.chain_id, action.transaction_hash)" :href="transactionLink(action.chain_id, action.transaction_hash)" :title="action.transaction_hash" target="_blank" rel="noopener noreferrer"><code>{{ shorten(action.transaction_hash) }}</code> ↗</a><code v-else :title="action.transaction_hash">{{ shorten(action.transaction_hash) }}</code><button class="text-button" @click="copy(action.transaction_hash)">{{ copied === action.transaction_hash ? '已复制' : '复制完整哈希' }}</button></template><span v-else>尚无可核实的执行交易</span></dd></div>
        </dl>
        <a v-if="sampleLinks?.[action.sample_id]" class="text-button" :href="`#sample-${sampleLinks[action.sample_id]}`">阅读对应样本 {{ sampleLinks[action.sample_id] }} →</a>
        <details class="technical"><summary>执行账户、合约与原始证据</summary><dl class="chain-action-facts"><div class="full"><dt>执行账户</dt><dd><code>{{ action.executor || '尚未核实' }}</code></dd></div><div class="full"><dt>调用目标</dt><dd><code>{{ action.target || '尚未核实' }}</code></dd></div></dl><EvidenceList :sources="action.evidence" :report-id="reportId" :agent-key="agentKey" /></details>
      </li>
    </ol>
    <button v-if="actions.length > shownActions.length" class="text-button" @click="expanded = true">展开其余 {{ actions.length - shownActions.length }} 项链上操作 ↓</button>
    <button v-else-if="expanded" class="text-button" @click="expanded = false">收起其他任务 ↑</button>
    <p v-if="copyError" class="muted small" role="status">当前浏览器无法复制，请展开交易链接查看完整哈希。</p>
    <details v-if="limitations.length" class="method-details"><summary>本次链上核验的范围与缺项</summary><ul><li v-for="limitation in limitations" :key="limitation">{{ limitation }}</li></ul></details>
  </section>
</template>
