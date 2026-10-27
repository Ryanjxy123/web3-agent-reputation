<script setup lang="ts">
import { computed } from 'vue'
import type { EvaluationReport } from '../contracts'
import { businessCapabilities, capabilityKey } from '../capability'
import { score, scoreRange, when } from '../format'

const props = defineProps<{
  reports: Array<{ id: string; report: EvaluationReport }>
  expected: number
  selectedId: string
  loading: boolean
  incomplete: boolean
}>()
defineEmits<{ select: [id: string] }>()
const tested = computed(() => new Set(props.reports.flatMap(({ report }) => businessCapabilities(report).map(capabilityKey))).size)
const legacy = computed(() => props.reports.filter(({ report }) => !(report.capabilities ?? []).length
  && report.samples.some(item => ['functional', 'behavioral'].includes(item.sample.purpose))).length)
const publishable = (report: EvaluationReport) => report.shared_assessment
  ? report.shared_assessment.result.score_status === 'AVAILABLE' : report.scores.status === 'COMPLETE'
const complete = computed(() => props.reports.filter(({ report }) => publishable(report)).length)
const partial = computed(() => props.reports.filter(({ report }) => !publishable(report) && report.scores.status === 'PARTIAL').length)
const declared = computed(() => [...new Map(props.reports.flatMap(({ report }) =>
  (report.capabilities ?? []).filter(item => item.operation !== '未提供可识别操作').map(item => [capabilityKey(item), item] as const))).values()])
const title = (report: EvaluationReport) => report.shared_assessment
  ? report.shared_assessment.capabilities.filter(item => item.selected).map(item => item.title).join('、')
  : businessCapabilities(report).map(item => item.operation).join('、')
  || ((report.capabilities ?? []).length ? '协议与可用性资料（尚无能力业务样本）' : report.scope)
const dimensionValue = (report: EvaluationReport, purpose: 'availability' | 'functional' | 'behavioral') => {
  const dimension = report.shared_assessment?.result[purpose]
  return dimension ? scoreRange(dimension.interval?.lower, dimension.interval?.upper) : score(report.scores[purpose].value)
}
const overallValue = (report: EvaluationReport) => report.shared_assessment
  ? scoreRange(report.shared_assessment.result.overall?.lower, report.shared_assessment.result.overall?.upper)
  : score(report.scores.overall)
</script>

<template>
  <details class="panel agent-coverage report-secondary" aria-label="Agent 能力覆盖">
    <summary class="section-heading"><h2>其他能力与历史报告</h2><span class="muted small">已读取 {{ reports.length }} / {{ expected }} 份</span></summary>
    <p class="section-description"><template v-if="tested">已明确关联业务样本的能力类 {{ tested }} 项 · </template><template v-else-if="!legacy">尚无明确关联能力的业务样本 · </template>可发布范围综合结果 {{ complete }} 份 · 证据不足的范围报告 {{ partial }} 份。</p>
    <p v-if="legacy" class="muted small">{{ legacy }} 份旧报告未记录逐能力映射，不能据此认定已测能力为 0。其真实核验范围与样本保留在对应报告中。</p>
    <p class="muted small">每个分数仅属于同一行的报告范围；尚未计算跨能力的 Agent 全局综合分。</p>
    <p v-if="loading" class="muted small" role="status">正在读取其他能力报告…</p>
    <p v-if="incomplete" class="coverage-warning" role="status">部分历史报告未能读取，覆盖统计仅包含已加载报告；可通过报告历史重试读取。</p>
    <div v-if="reports.length" class="coverage-table-wrap"><table class="coverage-table"><thead><tr><th scope="col">能力与报告范围</th><th scope="col">A 可用性</th><th scope="col">F 功能</th><th scope="col">B 履约</th><th scope="col">范围综合分 S</th><th scope="col">报告</th></tr></thead><tbody><tr v-for="{ id, report } in reports" :key="id" :class="{ selected: id === selectedId }"><th scope="row"><strong>{{ title(report) }}</strong><p class="muted small">{{ when(report.generated_at) }}</p><p class="muted small">{{ report.scores.policy_version }}</p></th><td>{{ dimensionValue(report, 'availability') }}</td><td>{{ dimensionValue(report, 'functional') }}</td><td>{{ dimensionValue(report, 'behavioral') }}</td><td>{{ overallValue(report) }}</td><td><button class="text-button" :aria-current="id === selectedId ? 'true' : undefined" @click="$emit('select', id)">{{ id === selectedId ? '当前报告' : '查看范围与证据' }}</button></td></tr></tbody></table></div>
    <details v-if="declared.length" class="method-details"><summary>已记录的 {{ declared.length }} 项能力条目与工具声明</summary><p>以下是资料中的声明或协议发现，可能包含同一业务的不同表述；有声明不等于已验证能力。实际业务覆盖与缺项以对应报告为准。</p><ul class="capability-declarations"><li v-for="item in declared" :key="capabilityKey(item)">{{ item.operation }}<span class="muted small"> · {{ item.capability_type || item.protocol }}<template v-if="item.checker_id"> · {{ item.checker_id }}/{{ item.checker_version }}</template></span></li></ul></details>
  </details>
</template>
