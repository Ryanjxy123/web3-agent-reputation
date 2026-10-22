<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import type { EvaluationReport, MeasurementPurpose, ReportChainEvidence } from '../contracts'
import { getReportChainEvidence } from '../api'
import { capabilityDimension } from '../capability'
import { score, when } from '../format'
import EvidenceList from './EvidenceList.vue'
import ScoreCard from './ScoreCard.vue'
import StatusBadge from './StatusBadge.vue'
import ChainEvidencePanel from './ChainEvidencePanel.vue'

const props = defineProps<{ report: EvaluationReport; reportId: string }>()
const chainEvidence = ref<ReportChainEvidence | null>(null)
const chainEvidenceError = ref(false)
const chainAbort = new AbortController()
const sampleLinks = computed(() => Object.fromEntries(props.report.samples.map((item, index) => [item.sample.sample_id, index + 1])))
onMounted(async () => {
  try { chainEvidence.value = await getReportChainEvidence(props.reportId, chainAbort.signal) }
  catch { if (!chainAbort.signal.aborted) chainEvidenceError.value = true }
})
onBeforeUnmount(() => chainAbort.abort())
const isPrediction = computed(() => ['prediction-history-v1', 'prediction-history-v2'].includes(props.report.scores.policy_version ?? ''))
const isFulfillment = computed(() => String(props.report.scores.policy_version) === 'service-fulfillment-v1')
const isGeneric = computed(() => ['service-contract-v1', 'service-fulfillment-v1'].includes(props.report.scores.policy_version ?? ''))
const capabilities = computed(() => (props.report.capabilities ?? []).filter(item => item.operation !== '未提供可识别操作'))
const probability = (value: number) => new Intl.NumberFormat('zh-CN', { style: 'percent', maximumFractionDigits: 6 }).format(value)
const dimensions = computed(() => [
  { purpose: 'availability' as const, title: 'A · 服务可用性', weight: '30%', dimension: props.report.scores.availability },
  { purpose: 'functional' as const, title: 'F · 功能声明一致性', weight: '40%', dimension: props.report.scores.functional },
  { purpose: 'behavioral' as const, title: 'B · 交易行为可靠性', weight: '30%', dimension: props.report.scores.behavioral },
])
const representatives = computed(() => {
  const indices = new Set<number>()
  for (const purpose of ['availability', 'functional', 'behavioral']) {
    const index = ['FAIL', 'UNKNOWN', 'PASS'].map(verdict => props.report.samples.findIndex(item =>
      item.sample.purpose === purpose && item.sample.verdict === verdict)).find(index => index >= 0)
    if (index !== undefined) indices.add(index)
  }
  return indices
})
const samplesFor = (purpose: MeasurementPurpose) => props.report.samples
  .map((item, index) => ({ item, index })).filter(({ item }) => item.sample.purpose === purpose)
const capabilityCoverage = computed(() => capabilities.value.map(capability => {
  const samples = props.report.samples.map((item, index) => ({ item, index }))
    .filter(({ item }) => item.capability_id === capability.capability_id)
  const scores = dimensions.value.map(item => {
    const records = samples.filter(record => record.item.sample.purpose === item.purpose)
    return { ...item, bound: capabilityDimension(props.report, capability, item.purpose), count: records.length,
      counts: ['PASS', 'FAIL', 'UNKNOWN', 'NOT_APPLICABLE'].map(verdict => records.filter(record => record.item.sample.verdict === verdict).length) }
  })
  return {
    ...capability, samples, scores,
    overall: scores.every(item => item.bound?.value != null) ? props.report.scores.overall : null,
    functional: samples.filter(({ item }) => item.sample.purpose === 'functional').length,
    behavioral: samples.filter(({ item }) => item.sample.purpose === 'behavioral').length,
  }
}))
const capabilitiesWithBusinessSamples = computed(() => capabilityCoverage.value
  .filter(item => item.functional > 0 || item.behavioral > 0).length)
const capabilityNames = computed(() => capabilities.value.slice(0, 3).map(item => item.operation).join('、'))
const missingEvidence = computed(() => [...new Set([
  ...capabilities.value.flatMap(item => item.missing_evidence), ...props.report.limitations,
])])
const conclusion = computed(() => {
  const scores = props.report.scores
  if (isGeneric.value) {
    if (scores.status === 'COMPLETE') {
      return `本次范围内，${scores.functional.observed} 个不同任务的功能声明核验有 ${scores.functional.passed} 条通过、${scores.functional.failed} 条未通过；另外 ${scores.behavioral.observed} 个任务的${isFulfillment.value ? '可观察服务履约' : '真实交易履约'}核验有 ${scores.behavioral.passed} 条通过、${scores.behavioral.failed} 条未通过。三维样本充分，综合分为 ${score(scores.overall)} 分。`
    }
    const pending = dimensions.value.filter(item => item.dimension.value === null).map(item => item.title).join('、')
    if (scores.status === 'PARTIAL') {
      return `本次保留 ${props.report.samples.length} 条核验记录；${pending}仍缺足够的证据或确定结论，暂不计算综合分。`
    }
    return capabilities.value.length
      ? `本次已整理 ${capabilities.value.length} 项功能的资料与协议信息，尚无达到评分条件的实际采样，三维分数与综合分均待评价。`
      : '本次尚未识别出有充分资料可执行评价的功能，三维分数与综合分均待评价；已取得的资料和具体缺项保留在本报告中。'
  }
  if (scores.status === 'COMPLETE') {
    const findings = []
    if (isPrediction.value) {
      const invalid = props.report.samples.filter(item => item.sample.purpose === 'functional' && item.sample.verdict === 'FAIL' && !item.sample.prediction).length
      findings.push(`本次核验 ${scores.functional.observed} 个不同历史问题，平均概率信用分为 ${score(scores.functional.value)}，这不是预测准确率。`)
      if (invalid) findings.push(`其中 ${invalid} 份交付未返回符合约定的有效概率，按规则计零信用。`)
      findings.push(`另 ${scores.behavioral.observed} 个任务的履约核验包含链上归属与约定输出，${scores.behavioral.passed} 条通过、${scores.behavioral.failed} 条未通过；具体输出差异与链上发现见逐条结果。`)
    } else if (scores.functional.failed === 0 && scores.behavioral.failed === 0) {
      findings.push('本次样本中的历史披露，以及包装、兑换、增仓三笔公开操作均已核实。')
    } else {
      findings.push(`本次历史披露核验有 ${scores.functional.failed} 条未通过，三笔公开操作核验有 ${scores.behavioral.failed} 条未通过。`)
    }
    if (scores.availability.failed > 0) findings.push(`${isPrediction.value ? '历史交付文件读取' : '公开记录查询'}有 ${scores.availability.failed} 次未通过。`)
    if (scores.availability.passed > 0 && scores.availability.p95_ms !== null && scores.availability.p95_ms > 1000) {
      findings.push(`成功查询的 p95 为 ${(scores.availability.p95_ms / 1000).toFixed(2)} 秒，本次线路的查询耗时影响了可用性得分。`)
    }
    return findings.join('') + `本次范围综合分为 ${score(scores.overall)} 分。`
  }
  if (scores.status === 'PARTIAL') return `${isPrediction.value ? '已取得部分历史预测与交付核验结果' : '已完成部分样本核验'}；尚有维度未达到完整评分要求，因此暂不计算综合分。`
  if (isPrediction.value) return '目前尚无足量可独立核验的已结算二元预测，三项维度与综合分均待评价。'
  return '目前尚无足够的实际评价样本，三项维度与综合分均待评价。'
})
</script>

<template>
  <div class="report-content">
    <section class="report-lead panel">
      <div class="row-between wrap"><span class="eyebrow">本次评价结论</span><span class="report-status" :class="{ complete: report.scores.status === 'COMPLETE' }">{{ report.scores.status === 'COMPLETE' ? '本范围完整评分' : report.scores.status === 'PARTIAL' ? '部分评价' : '待评价' }} · {{ report.scores.status }}</span></div>
      <div class="report-conclusion"><div><h2>{{ conclusion }}</h2><p class="lead-scope">{{ report.scope }}</p></div><div class="overall-block"><strong>{{ score(report.scores.overall) }}</strong><span>本报告范围综合分 S<span v-if="report.scores.overall !== null"> / 100</span></span></div></div>
      <p v-if="isFulfillment" class="scope-note">这份历史查询报告的 B 分衡量查询交付，不证明 Agent 已完成资产交易。三维固定展示，实际测量口径按原政策保留。</p>
      <details class="method-details"><summary>评价时间、政策与完整范围说明</summary>
        <template v-if="isGeneric"><p v-if="capabilities.length" class="section-description">本次已识别：{{ capabilityNames }}<template v-if="capabilities.length > 3">等 {{ capabilities.length }} 项功能</template>。资料与协议发现用于确定可测范围，业务结论对应下方实际任务及独立核验。</p><p v-if="missingEvidence.length" class="section-description">当前缺项：{{ missingEvidence.slice(0, 2).join('；') }}<template v-if="missingEvidence.length > 2">。其余 {{ missingEvidence.length - 2 }} 项见各功能与报告限制。</template></p></template>
        <p v-if="isPrediction" class="section-description">本次评价公开历史交付入口、已结算问题的预测概率，以及另一组任务的链上归属与交付。历史文件可读不表示实时推理服务可用；不同业务范围的分数不能直接排名。</p>
        <p v-if="capabilities.length" class="section-description">本报告记录 {{ capabilities.length }} 项声明或发现的能力，其中 {{ capabilitiesWithBusinessSamples }} 项有关联功能或履约样本。结论限于已列明的任务与证据。</p>
        <p v-else class="section-description">旧报告未记录逐能力映射，已评分范围以报告说明和样本为准。</p>
      <dl class="report-meta"><div class="full"><dt>评分政策版本</dt><dd><code>{{ report.scores.policy_version }}</code></dd></div><div><dt>样本时间范围</dt><dd>{{ report.evaluation_window }}</dd></div><div><dt>报告生成时间</dt><dd>{{ when(report.generated_at) }}</dd></div><div class="full"><dt>评价方式</dt><dd>{{ report.approach }}</dd></div></dl>
      </details>
    </section>

    <section class="score-grid" aria-label="三维评价分数">
      <ScoreCard v-for="item in dimensions" :key="item.purpose" :title="item.title" :weight="item.weight" :dimension="item.dimension" />
    </section>

    <ChainEvidencePanel v-if="chainEvidence" :actions="chainEvidence.actions" :summary="chainEvidence.summary" :limitations="chainEvidence.limitations" :report-id="reportId" :sample-links="sampleLinks" />
    <p v-else-if="chainEvidenceError" class="muted small" role="status">链上操作视图暂时无法读取，逐条样本与原始证据仍在下方保留。</p>

    <details v-if="isGeneric || capabilities.length" class="panel report-secondary">
      <summary class="section-heading"><h2>已测功能与完整能力映射</h2><span>{{ capabilities.length }} 项已记录条目</span></summary>
      <p class="section-description">功能声明、协议发现和实际业务结果分别记录。F 需要适用的独立业务判据；B 依照本报告政策核验履约。下列能力只在该维度全部样本明确关联时展示对应分数；服务入口采样未关联具体能力时，A 仅在报告范围内展示。</p>
      <p v-if="!capabilities.length" class="empty-inline">本轮尚无可列明的功能范围；资料来源与缺项见报告限制。</p>
      <details v-for="capability in capabilityCoverage" :key="capability.capability_id" class="capability-item">
        <summary class="sample-group-heading wrap"><h3>{{ capability.operation }}</h3><span>{{ capability.samples.length }} 条关联样本</span><span class="report-status">{{ capability.functional || capability.behavioral ? '有关联业务样本' : '尚无业务样本' }}</span></summary>
        <div class="capability-body">
        <p class="section-description multiline">{{ capability.description }}</p>
        <dl class="capability-score-summary"><div v-for="item in capability.scores" :key="item.purpose"><dt>{{ item.title }}</dt><dd>{{ item.bound ? score(item.bound.value) : '未单独评分' }}</dd><p class="muted small">关联 {{ item.count }} 条<br>PASS {{ item.counts[0] }} · FAIL {{ item.counts[1] }}<br>UNKNOWN {{ item.counts[2] }} · N_A {{ item.counts[3] }}</p></div><div><dt>能力范围综合分 S</dt><dd>{{ capability.overall === null ? '未单独评分' : score(capability.overall) }}</dd></div></dl>
        <dl class="report-meta"><div><dt>能力类型</dt><dd>{{ capability.capability_type || '未记录' }}</dd></div><div><dt>Checker / 版本</dt><dd><code>{{ capability.checker_id || '未记录' }}</code> / {{ capability.checker_version || '未记录' }}</dd></div><div><dt>声明或发现的协议</dt><dd>{{ capability.protocol }}</dd></div><div><dt>本报告关联的业务样本</dt><dd>F 功能 {{ capability.functional }} 条 · B 履约 {{ capability.behavioral }} 条</dd></div><div class="full"><dt>本次实际业务判定范围</dt><dd>{{ capability.tested_scope || '尚未形成实际业务判定范围。' }}</dd></div></dl>
        <h4>资料与核验发现</h4>
        <ul v-if="capability.findings.length" class="finding-list"><li v-for="(finding, index) in capability.findings" :key="index"><div class="row-between"><strong>{{ finding.label }}</strong><StatusBadge :verdict="finding.verdict" /></div><p>{{ finding.explanation }}</p></li></ul>
        <p v-else class="empty-inline">本轮尚无分项发现。</p>
        <h4>对应的实际任务</h4>
        <ul v-if="capability.samples.length"><li v-for="{ item, index } in capability.samples" :key="item.sample.sample_id"><a :href="`#sample-${index + 1}`">样本 {{ String(index + 1).padStart(2, '0') }} · {{ item.title }}</a> <StatusBadge :verdict="item.sample.verdict" /></li></ul>
        <p v-else class="empty-inline">本轮没有该功能的实际业务评分样本，当前仅展示资料及缺项。</p>
        <h4>仍缺哪些证据</h4><ul v-if="capability.missing_evidence.length"><li v-for="(missing, index) in capability.missing_evidence" :key="index" class="multiline">{{ missing }}</li></ul><p v-else class="empty-inline">本项未另列证据缺口，结论限于上方已测范围。</p>
        </div>
      </details>
    </details>

    <details class="panel method-panel report-secondary">
      <summary><h2 class="section-title">评分算法、门槛与判据</h2></summary>
      <div class="method-grid">
        <div><h3>{{ isPrediction ? '历史交付入口是否能读' : '接口是否能用' }}</h3><p v-if="isPrediction">可用性检查已选历史交付文件是否按约定完整返回、任务号与摘要是否匹配，衡量本次线路的公开历史读取体验，不是实时预测或推理服务的可用率。</p><p v-else-if="isGeneric">可用性检查本次明确列明的声明服务入口及只读调用，核对协议结果、业务响应与延迟。仅发现接口或读取元数据，不代表已完成业务可用性采样。</p><p v-else>可用性检查公开记录入口是否按约定响应。</p><p>得分由 80% 成功率和 20% 延迟表现组成。</p><p class="latency-note">成功响应 p95：{{ report.scores.availability.p95_ms === null ? '尚无数据' : report.scores.availability.p95_ms.toFixed(2) + ' 毫秒' }}</p><p>p95 表示至少 95% 的成功请求在这个耗时内完成。这是本机经指定代理线路的访问体验，包含网络和代理耗时。</p></div>
        <div v-if="isPrediction"><h3>概率是否支持最终结算结果</h3><p>功能维度使用 7 个不同问题，将原始预测的“是/否”概率与最终二元结算对应。先核对原始题干、选项顺序、内容来源与时间，再评价概率。</p><p>每题按 Brier 概率信用计分，功能分取 7 题平均。确定且符合结算结果为 100，确定且相反为 0；50/50 的中性预测为 75。这个分数不是预测准确率，也不代表收益。</p></div>
        <div v-else-if="isGeneric"><h3>实际调用是否兑现了所测声明</h3><p>功能维度使用 7 个不同任务，核对声明的操作、实际输入输出绑定、约定格式和明确限制；需要业务正确性判据时，用独立证据核验结果。</p><p>只有格式符合约定，不能判定整个业务功能通过；缺少必要判据时保留无法判断。评价范围按各功能及任务列明。</p></div>
        <div v-else><h3>公布的结果是否准确</h3><p>功能维度核对历史增仓公布的资产用量和执行后流动性。用固定区块状态与事件顺序独立复算，精确比较实际结果。</p><p>这次评价的是这些具体披露，不涵盖全部策略能力。</p></div>
        <div v-if="isPrediction"><h3>交付能否归属于这个 Agent</h3><p>行为维度使用另外 7 个不同问题，核对真实请求和交付交易、链上事件、任务号、内容摘要，以及任务当时的执行控制权。</p><p>请求者、优先接单者、实际交付者与服务钱包分别核实；接手其他服务的请求时，还要满足交付窗口与授权。成功回执本身不能证明完整履约。</p></div>
        <div v-else-if="isFulfillment"><h3>另外一组查询任务是否按约履行</h3><p>行为维度使用与 F 互斥的另外 7 个真实任务，核对认证端点、请求标识与任务对象绑定、完整业务交付及调用前冻结的时限。</p><p>B 不重复检验业务事实真值，不以 HTTP 成功或 Agent 自报完成判 PASS。归责明确的违约记 FAIL；无法归责的网络或平台故障为 UNKNOWN。同步 Message 仅证明实际保留的请求与交付，不冒充 A2A Task 状态历史。</p></div>
        <div v-else-if="isGeneric"><h3>另外一组任务是否真实履约</h3><p>行为维度使用另外 7 个不同任务，核验任务与链实例、执行者、调用目标和参数、回执、事件及确认状态的完整对应。</p><p>执行归属需独立证据；注册持有人或收款地址不自动等于执行者。成功回执本身不足以证明任务完成，只读功能不虚构执行交易。</p></div>
        <div v-else><h3>公开操作是否可靠完成</h3><p>行为维度使用另一组互不重复的运行记录，逐笔核验包装原生币、兑换和最终增仓的完整公开步骤。</p><p>每笔都要核对身份、目标、资产流向、调用限制与链上结果。</p></div>
      </div>
      <details class="method-details"><summary>查看计分门槛与无法判断的处理方式</summary><p>可用性须保留全部 10 个槽位且至少有 8 个确定结论；功能与行为分别保留 7 个任务且各有 7 个确定结论。</p><template v-if="isPrediction"><p>每题概率信用 = 100 × [1 −（p_yes − y）²]，最终结算为 Yes 时 y=1、No 时 y=0；功能分是七题信用的平均值。PASS 表示分给最终结果的概率至少为 50%，包括中性预测；低于 50% 为方向未通过，但仍保留实际连续分。已证实违反输出格式的样本为 FAIL、信用 0；缺少可信内容或独立判据为 UNKNOWN，不补成 0。</p><p>行为分仍为通过数 ÷ 确定结论数 × 100。同一市场只取一份交付，功能与行为问题互不重复；结算指所绑定链上市场的最终结果，不冒充对全部现实事实的保证。</p></template><p v-else>功能、行为得分 = 通过数 ÷ 确定结论数 × 100。</p><p>UNKNOWN（无法判断）与不适用单独展示，不记失败、不进入分母；它们仍占原定槽位，不会被删掉以凑齐样本。三维齐全后按 30% / 40% / 30% 加权。</p><p>成功响应 p95 不超过 1000 毫秒时，延迟项满分；达到 10000 毫秒为零，中间线性计算。样本按耗时排序取最近秩。缺少维度不会补零，也不重新分配权重。</p></details>
    </details>

    <section class="panel samples-panel">
      <div class="section-heading"><div><p class="eyebrow">从结论回到事实</p><h2>每条样本实际发生了什么</h2></div><span class="muted small">共 {{ report.samples.length }} 条核验记录</span></div>
      <p class="section-description">每个维度默认展开一条代表样本，优先展示未通过或无法判断的发现。展开其他样本可查看全部输入、结果与独立证据。</p>
      <section v-for="group in dimensions" :key="group.purpose" class="sample-group">
        <div class="sample-group-heading"><h3>{{ group.title }}</h3><span>{{ samplesFor(group.purpose).length }} 条核验记录</span></div>
        <p v-if="!samplesFor(group.purpose).length" class="empty-inline">本维度尚无实际评价样本。</p>
        <details v-for="{ item, index } in samplesFor(group.purpose)" :id="`sample-${index + 1}`" :key="item.sample.sample_id" class="sample" :open="representatives.has(index)">
          <summary><span class="sample-marker">{{ String(index + 1).padStart(2, '0') }}</span><span class="sample-title">{{ item.title }}</span><StatusBadge :verdict="item.sample.verdict" /></summary>
          <div class="sample-body">
            <p class="muted small">{{ when(item.observed_at) }}<template v-if="item.sample.elapsed_ms !== null"> · 请求耗时 {{ item.sample.elapsed_ms.toFixed(2) }} 毫秒</template></p>
            <section v-if="isPrediction && item.sample.purpose === 'functional'" class="prediction-summary">
              <template v-if="item.sample.prediction"><h4>这份预测与最终结算</h4><dl class="report-meta"><div><dt>预测“是”（Yes）</dt><dd>{{ probability(item.sample.prediction.p_yes) }} <span class="muted small">（p_yes={{ item.sample.prediction.p_yes }}）</span></dd></div><div><dt>预测“否”（No）</dt><dd>{{ probability(item.sample.prediction.p_no) }} <span class="muted small">（p_no={{ item.sample.prediction.p_no }}）</span></dd></div><div><dt>最终独立结算</dt><dd>{{ item.sample.prediction.final_outcome === 'yes' ? '是（Yes）' : '否（No）' }}</dd></div></dl><p v-if="item.sample.verdict === 'FAIL'">预测给最终结算结果的概率低于 50%，方向未通过；信用分仍按原始概率计算，并非统一记 0。</p><p v-else>预测给最终结算结果的概率至少为 50%，达到中性方向门槛；PASS 不表示确定正确。</p><p class="muted small">这条预测的信用分与依据见下方独立核验说明。</p></template>
              <p v-else-if="item.sample.verdict === 'FAIL'">已确认输出格式违反声明，本题信用为 0；具体违反项见独立核验说明。</p>
              <p v-else-if="item.sample.verdict === 'UNKNOWN'">本题尚缺可信原始内容或独立结算判据，当前无法判断，不记为失败或 0 分；缺项见独立核验说明。</p>
              <p v-else-if="item.sample.verdict === 'NOT_APPLICABLE'">本题不在当前二元预测范围，不进入概率评分。</p>
            </section>
            <div class="sample-facts"><section><h4>实际检查输入</h4><p>{{ item.input_summary }}</p></section><section><h4>声明或公布的结果</h4><p>{{ item.claimed_output }}</p></section><section class="independent"><h4>独立核验发现了什么</h4><p>{{ item.independent_result }}</p></section></div>
            <h4>怎样得出这条结论</h4>
            <ul v-if="item.checks.length" class="finding-list"><li v-for="(check, checkIndex) in item.checks" :key="checkIndex"><div class="row-between"><strong>{{ check.label }}</strong><StatusBadge :verdict="check.verdict" /></div><p>{{ check.explanation }}</p></li></ul>
            <p v-else class="muted">本项尚无分项检查记录。</p>
            <details class="technical"><summary>原始证据与技术详情</summary><dl><dt>样本标识</dt><dd><code>{{ item.sample.sample_id }}</code></dd><dt>任务标识</dt><dd><code>{{ item.sample.task_key }}</code></dd><dt>规则原始结论</dt><dd class="multiline">{{ item.sample.reason }}</dd></dl><EvidenceList :sources="item.sample.evidence" :report-id="reportId" /></details>
          </div>
        </details>
      </section>
    </section>

    <details class="panel boundaries-panel report-secondary"><summary><h2 class="section-title">未覆盖内容、限制与资料来源</h2></summary><div class="boundary-grid"><section><h3>本次未覆盖</h3><ul v-if="report.scope_exclusions.length"><li v-for="(item, index) in report.scope_exclusions" :key="index">{{ item }}</li></ul><p v-else class="muted">报告未另列范围之外的项目。</p></section><section><h3>本轮限制与待补项</h3><ul v-if="report.limitations.length"><li v-for="(item, index) in report.limitations" :key="index">{{ item }}</li></ul><p v-else class="muted">报告未另列限制。</p></section></div><details class="technical"><summary>资料来源与背景证据</summary><EvidenceList :sources="report.source_references" :report-id="reportId" /><p class="muted small">政策：{{ report.scores.policy_version }} · 格式：{{ report.schema_version }}</p></details></details>
  </div>
</template>
