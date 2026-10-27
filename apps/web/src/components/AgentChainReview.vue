<script setup lang="ts">
import type { AgentChainEvidence } from '../contracts'
import { when } from '../format'
import ChainEvidencePanel from './ChainEvidencePanel.vue'
import EvidenceList from './EvidenceList.vue'
import StatusBadge from './StatusBadge.vue'

defineProps<{ review: AgentChainEvidence; agentKey: string; hasAssessment?: boolean }>()
const labels = { availability: 'A · 服务可用性', functional: 'F · 功能声明一致性', behavioral: 'B · 交易行为可靠性' }
</script>

<template>
  <component :is="hasAssessment ? 'details' : 'div'" class="chain-review" :class="{ panel: hasAssessment }">
    <summary v-if="hasAssessment" class="section-heading"><h2>新增链上补测</h2><span class="muted small">{{ review.actions.length }} 项操作 · 查看结果与原件</span></summary>
    <section class="panel chain-review-heading"><div class="row-between wrap"><p class="eyebrow">真实公共 Agent · 链上证据核验</p><span class="report-status">{{ hasAssessment ? '补测证据 · 不计当前范围分' : '证据快照 · 尚未完整评分' }}</span></div><h2>{{ review.title }}</h2><p class="section-description">{{ review.window_summary }}</p><p class="muted small">{{ hasAssessment ? '以下为新增功能的实际核验，与原报告的已测范围分分别展示。' : '已核实的操作与完整声誉评分分别展示。' }}下列通过结论属于具体样本，不换算成 100 分。</p></section>
    <section class="score-grid" aria-label="链上业务三维证据与评分状态">
      <article v-for="dimension in review.dimensions" :key="dimension.purpose" class="score-card chain-review-dimension"><h3>{{ labels[dimension.purpose] }}</h3><p class="dimension-value pending">尚未出分</p><p>{{ dimension.summary }}</p><p class="muted small">已核样本 {{ dimension.observed }} 条</p><div class="row-between"><span class="muted small">当前证据结论</span><StatusBadge :verdict="dimension.verdict" /></div><details v-if="dimension.missing_evidence.length" class="method-details"><summary>评分还缺什么</summary><ul><li v-for="missing in dimension.missing_evidence" :key="missing">{{ missing }}</li></ul></details></article>
    </section>
    <ChainEvidencePanel :actions="review.actions" :summary="review.selection" :limitations="review.limitations" :agent-key="agentKey" />
    <details class="panel report-secondary"><summary><h2>身份、历史授权与核验依据</h2></summary><ul class="finding-list"><li v-for="(check, index) in review.checks" :key="index"><div class="row-between"><strong>{{ check.label }}</strong><StatusBadge :verdict="check.verdict" /></div><p>{{ check.explanation }}</p></li></ul><p class="muted small">证据快照生成于 {{ when(review.generated_at) }} · {{ review.schema_version }}</p><details class="technical"><summary>公开资料与原始证据下载</summary><EvidenceList :sources="review.sources" :agent-key="agentKey" /></details></details>
  </component>
</template>
