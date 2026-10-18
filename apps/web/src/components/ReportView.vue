<script setup lang="ts">
import { computed } from 'vue'
import type { EvaluationReport, MeasurementPurpose } from '../contracts'
import { score, when } from '../format'
import EvidenceList from './EvidenceList.vue'
import ScoreCard from './ScoreCard.vue'
import StatusBadge from './StatusBadge.vue'

const props = defineProps<{ report: EvaluationReport; reportId: string }>()
const dimensions = computed(() => [
  { purpose: 'availability' as const, title: '服务可用性', weight: '30%', dimension: props.report.scores.availability },
  { purpose: 'functional' as const, title: '功能声明一致性', weight: '40%', dimension: props.report.scores.functional },
  { purpose: 'behavioral' as const, title: '交易行为可靠性', weight: '30%', dimension: props.report.scores.behavioral },
])
const representatives = computed(() => {
  const indices = new Set<number>()
  for (const purpose of ['availability', 'functional', 'behavioral']) {
    for (const predicate of [
      (verdict: string) => verdict === 'PASS',
      (verdict: string) => verdict === 'FAIL' || verdict === 'UNKNOWN',
    ]) {
      const index = props.report.samples.findIndex(item => item.sample.purpose === purpose && predicate(item.sample.verdict))
      if (index >= 0) indices.add(index)
    }
  }
  return indices
})
const samplesFor = (purpose: MeasurementPurpose) => props.report.samples
  .map((item, index) => ({ item, index })).filter(({ item }) => item.sample.purpose === purpose)
const conclusion = computed(() => {
  const scores = props.report.scores
  if (scores.status === 'COMPLETE') {
    const findings = []
    if (scores.functional.failed === 0 && scores.behavioral.failed === 0) {
      findings.push('本次样本中的历史披露，以及包装、兑换、增仓三笔公开操作均已核实。')
    } else {
      findings.push(`本次历史披露核验有 ${scores.functional.failed} 条未通过，三笔公开操作核验有 ${scores.behavioral.failed} 条未通过。`)
    }
    if (scores.availability.failed > 0) findings.push(`公开记录查询有 ${scores.availability.failed} 次未通过。`)
    if (scores.availability.passed > 0 && scores.availability.p95_ms !== null && scores.availability.p95_ms > 1000) {
      findings.push(`成功查询的 p95 为 ${(scores.availability.p95_ms / 1000).toFixed(2)} 秒，本次线路的查询耗时影响了可用性得分。`)
    }
    return findings.join('') + `本次范围综合分为 ${score(scores.overall)} 分。`
  }
  if (scores.status === 'PARTIAL') return '已完成部分样本核验；尚有维度未达到完整评分要求，因此暂不计算综合分。'
  return '目前尚无足够的实际评价样本，三项维度与综合分均待评价。'
})
</script>

<template>
  <div class="report-content">
    <section class="report-lead panel">
      <div class="row-between wrap"><span class="eyebrow">本次评价结论</span><span class="report-status" :class="{ complete: report.scores.status === 'COMPLETE' }">{{ report.scores.status === 'COMPLETE' ? '本范围完整评分' : report.scores.status === 'PARTIAL' ? '部分评价' : '待评价' }}</span></div>
      <div class="report-conclusion"><div><h2>{{ conclusion }}</h2><p class="lead-scope">{{ report.scope }}</p></div><div class="overall-block"><strong>{{ score(report.scores.overall) }}</strong><span>本范围综合分<span v-if="report.scores.overall !== null"> / 100</span></span></div></div>
      <dl class="report-meta"><div><dt>样本时间范围</dt><dd>{{ report.evaluation_window }}</dd></div><div><dt>报告生成时间</dt><dd>{{ when(report.generated_at) }}</dd></div><div class="full"><dt>评价方式</dt><dd>{{ report.approach }}</dd></div></dl>
    </section>

    <section class="score-grid" aria-label="三维评价分数">
      <ScoreCard v-for="item in dimensions" :key="item.purpose" :title="item.title" :weight="item.weight" :dimension="item.dimension" />
    </section>

    <section class="panel method-panel">
      <h2 class="section-title">这几个分数怎样理解</h2>
      <div class="method-grid">
        <div><h3>接口是否能用</h3><p>可用性检查公开记录入口是否按约定响应。得分由 80% 成功率和 20% 延迟表现组成。</p><p class="latency-note">成功响应 p95：{{ report.scores.availability.p95_ms === null ? '尚无数据' : report.scores.availability.p95_ms.toFixed(2) + ' 毫秒' }}</p><p>p95 表示至少 95% 的成功请求在这个耗时内完成。这是本机经指定代理线路的访问体验，包含网络和代理耗时。</p></div>
        <div><h3>公布的结果是否准确</h3><p>功能维度核对历史增仓公布的资产用量和执行后流动性。用固定区块状态与事件顺序独立复算，精确比较实际结果。</p><p>这次评价的是这些具体披露，不涵盖全部策略能力。</p></div>
        <div><h3>公开操作是否可靠完成</h3><p>行为维度使用另一组互不重复的运行记录，逐笔核验包装原生币、兑换和最终增仓的完整公开步骤。</p><p>每笔都要核对身份、目标、资产流向、调用限制与链上结果。</p></div>
      </div>
      <details class="method-details"><summary>查看计分门槛与无法判断的处理方式</summary><p>可用性须保留全部 10 个槽位且至少有 8 个确定结论；功能与行为分别保留 7 个任务且各有 7 个确定结论。功能、行为得分 = 通过数 ÷ 确定结论数 × 100。UNKNOWN（无法判断）与不适用单独展示，不记失败、不进入分母。三维齐全后按 30% / 40% / 30% 加权。</p><p>成功响应 p95 不超过 1000 毫秒时，延迟项满分；达到 10000 毫秒为零，中间线性计算。样本按耗时排序取最近秩。缺少维度不会补零，也不重新分配权重。</p></details>
    </section>

    <section class="panel samples-panel">
      <div class="section-heading"><div><p class="eyebrow">从结论回到事实</p><h2>每条样本实际发生了什么</h2></div><span class="muted small">共 {{ report.samples.length }} 条评分样本</span></div>
      <p class="section-description">查看真实输入、服务公布的结果，以及独立核验的发现。每个维度的首个通过样本，以及已记录的首个未通过或无法判断样本默认展开。</p>
      <section v-for="group in dimensions" :key="group.purpose" class="sample-group">
        <div class="sample-group-heading"><h3>{{ group.title }}</h3><span>{{ samplesFor(group.purpose).length }} 条实际样本</span></div>
        <p v-if="!samplesFor(group.purpose).length" class="empty-inline">本维度尚无实际评价样本。</p>
        <details v-for="{ item, index } in samplesFor(group.purpose)" :key="item.sample.sample_id" class="sample" :open="representatives.has(index)">
          <summary><span class="sample-marker">{{ String(index + 1).padStart(2, '0') }}</span><span class="sample-title">{{ item.title }}</span><StatusBadge :verdict="item.sample.verdict" /></summary>
          <div class="sample-body">
            <p class="muted small">{{ when(item.observed_at) }}<template v-if="item.sample.elapsed_ms !== null"> · 请求耗时 {{ item.sample.elapsed_ms.toFixed(2) }} 毫秒</template></p>
            <div class="sample-facts"><section><h4>实际检查输入</h4><p>{{ item.input_summary }}</p></section><section><h4>声明或公布的结果</h4><p>{{ item.claimed_output }}</p></section><section class="independent"><h4>独立核验发现了什么</h4><p>{{ item.independent_result }}</p></section></div>
            <h4>怎样得出这条结论</h4>
            <ul v-if="item.checks.length" class="finding-list"><li v-for="(check, checkIndex) in item.checks" :key="checkIndex"><div class="row-between"><strong>{{ check.label }}</strong><StatusBadge :verdict="check.verdict" /></div><p>{{ check.explanation }}</p></li></ul>
            <p v-else class="muted">本项尚无分项检查记录。</p>
            <details class="technical"><summary>原始证据与技术详情</summary><dl><dt>样本标识</dt><dd><code>{{ item.sample.sample_id }}</code></dd><dt>任务标识</dt><dd><code>{{ item.sample.task_key }}</code></dd><dt>规则原始结论</dt><dd class="multiline">{{ item.sample.reason }}</dd></dl><EvidenceList :sources="item.sample.evidence" :report-id="reportId" /></details>
          </div>
        </details>
      </section>
    </section>

    <section class="panel boundaries-panel"><h2 class="section-title">哪些内容还不在这份结论里</h2><div class="boundary-grid"><section><h3>本次未覆盖</h3><ul v-if="report.scope_exclusions.length"><li v-for="(item, index) in report.scope_exclusions" :key="index">{{ item }}</li></ul><p v-else class="muted">报告未另列范围之外的项目。</p></section><section><h3>本轮限制与待补项</h3><ul v-if="report.limitations.length"><li v-for="(item, index) in report.limitations" :key="index">{{ item }}</li></ul><p v-else class="muted">报告未另列限制。</p></section></div><details class="technical"><summary>资料来源与背景证据</summary><EvidenceList :sources="report.source_references" :report-id="reportId" /><p class="muted small">政策：{{ report.scores.policy_version }} · 格式：{{ report.schema_version }}</p></details></section>
  </div>
</template>
