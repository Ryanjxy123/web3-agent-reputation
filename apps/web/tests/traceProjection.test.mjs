import assert from 'node:assert/strict'
import test from 'node:test'
import { checkTone, isAssetLabelNotice, loadTraceSources, projectTaskTrace, projectTaskTraces, traceExplorerUrl, verificationTone } from '../src/traceProjection.ts'

// Test fixtures only; the product loads published reports through the API.
const task = (key, outcome = 'completed') => ({ task_key: key, capability_id: 'swap', input_summary: '输入要求',
  outcome, attribution: 'provider', observed_at: '2026-10-27T00:00:00Z', evidence: [`runtime/${key}/task.json`] })
const sample = (key) => ({ sample: { task_key: key, sample_id: `sample:${key}`, purpose: 'behavioral', verdict: 'PASS',
  evidence: [`runtime/${key}/transaction.response.bin`] }, title: '相同名称', claimed_output: '交易方案', independent_result: '已核结果' })
const observation = (key) => ({ task_key: key, case_id: 'case', criterion_id: 'execution-effect', dimension: 'functional',
  verdict: 'PASS', measurement_validity: 'valid', evidence: [], reason: '独立效果', elapsed_ms: null })
const report = (...tasks) => ({ generated_at: '2026-10-28T00:00:00Z', samples: tasks.map(item => sample(item.task_key)),
  scores: { overall: 96.67 }, shared_assessment: { tasks, observations: tasks.map(item => observation(item.task_key)),
    capabilities: [{ capability_id: 'swap', title: '即时兑换' }], cases: [] } })
const action = (key, hash = '1', method = 'swap()') => ({ sample_id: `sample:${key}`, chain_id: 8453,
  transaction_hash: '0x' + hash.repeat(64), executor: '0x' + 'a'.repeat(40), target: '0x' + 'b'.repeat(40),
  method, action: 'contract_call', title: '实际调用', summary: '已保留调用', verdict: 'PASS',
  block_number: 10, evidence: [`runtime/${key}/transaction.response.bin`] })

test('joins by task/sample IDs, rejects foreign evidence and foreign source records, and preserves report', () => {
  const input = report(task('a'), task('b'))
  const before = JSON.stringify(input)
  const chain = { actions: [action('b'), action('a'), { ...action('a'), evidence: ['runtime/foreign/receipt.response.bin'] }] }
  const traces = projectTaskTraces('report-a', input, chain)
  assert.equal(traces[0].nodes.filter(node => node.action).length, 1)
  assert.equal(traces[0].nodes.find(node => node.action).action.sample_id, 'sample:a')
  assert.equal(traces[1].observations[0].task_key, 'b')
  assert.equal(projectTaskTrace('report-a', input, 'missing'), null)
  const raw = { reportId: 'foreign-report', taskKey: 'a', path: 'runtime/a/task.json', value: { request_id: 'a' } }
  assert.deepEqual(projectTaskTrace('report-a', input, 'a', chain, [raw]).nodes, traces[0].nodes)
  assert.equal(JSON.stringify(input), before)
})

test('preserves multiple transactions and multiple operations within one transaction', () => {
  const input = report(task('a'))
  const trace = projectTaskTrace('r', input, 'a', { actions: [action('a'), { ...action('a', '1', 'getOrder()'), action: 'contract_read' }, action('a', '2')] })
  const calls = trace.nodes.filter(node => node.action)
  assert.equal(calls.length, 3)
  assert.equal(new Set(calls.map(node => node.id)).size, 3)
  assert.equal(trace.nodes.find(node => node.id === 'wallet').output[0].value, '2')
  assert.ok(calls.every(node => node.timestamp === null))
  assert.match(calls[1].output.find(field => field.label === '查询返回值').value, /没有记录内部调用返回值/)
  assert.ok(trace.edges.filter(edge => edge.to === 'result').every(edge => edge.kind === 'evidence'))
})

test('quote-only and missing fields do not fabricate wallet execution or occurrence times', () => {
  const input = report(task('quote', 'not_executed'))
  input.shared_assessment.observations = []
  const trace = projectTaskTrace('r', input, 'quote')
  assert.equal(trace.outcomeLabel, '未取得方案')
  assert.equal(trace.nodes.some(node => node.id === 'wallet'), false)
  assert.equal(trace.nodes.find(node => node.id === 'service').status, 'unrecorded')
  assert.equal(trace.nodes.some(node => node.timestamp !== null), false)
  assert.equal(trace.observedAt, input.shared_assessment.tasks[0].observed_at)
  assert.equal(trace.nodes.find(node => node.id === 'result').lane, 'execution')
  assert.equal(traceExplorerUrl(8453, 'tx', '0x' + '1'.repeat(64)), 'https://basescan.org/tx/0x' + '1'.repeat(64))
  assert.equal(traceExplorerUrl(999999, 'tx', '0x' + '1'.repeat(64)), undefined)
})

test('HTTP payload fields are read from the nested body; an unknown response is not promoted to success', () => {
  const item = task('a', 'not_executed')
  item.evidence.push('runtime/a/business-request.json', 'runtime/a/business-response.json', 'runtime/a/business-observation.json')
  const input = report(item)
  input.shared_assessment.observations = [{ ...observation('a'), dimension: 'availability', verdict: 'UNKNOWN', response_complete: null }]
  const sources = [
    ['business-request.json', { method: 'POST', url: 'https://example.test/swap', body: { amountIn: '0.02', recipient: '0xabc' } }],
    ['business-response.json', { status: 'error' }],
    ['business-observation.json', { status: 503, started_at: '2026-10-27T01:00:00Z', received_at: '2026-10-27T01:00:02Z' }],
  ].map(([name, value]) => ({ reportId: 'r', taskKey: 'a', path: `runtime/a/${name}`, value }))
  const trace = projectTaskTrace('r', input, 'a', undefined, sources)
  const service = trace.nodes.find(node => node.id === 'service')
  assert.equal(service.input.find(field => field.label === '输入数量').value, '0.02')
  assert.equal(service.status, 'UNKNOWN')
  assert.equal(trace.nodes.find(node => node.id === 'response').status, 'UNKNOWN')
  assert.equal(trace.nodes.find(node => node.id === 'response').title, '服务返回记录')
  assert.equal(trace.nodes.find(node => node.id === 'task').timestamp, null)
  assert.equal(trace.nodes.find(node => node.id === 'wallet'), undefined)
})

test('source loader uses only report-scoped GETs and stops on task identity mismatch', async () => {
  const previous = globalThis.fetch
  const requests = []
  globalThis.fetch = async (url) => { requests.push(url); return { ok: true, text: async () => JSON.stringify({ request_id: 'other-task' }) } }
  try {
    const item = task('a')
    item.evidence.push('runtime/a/business-request.json', 'runtime/a/business-response.json')
    const records = await loadTraceSources('current-report', item)
    assert.equal(requests.length, 1)
    assert.ok(requests[0].startsWith('/api/reports/current-report/evidence?path='))
    assert.match(records[0].error, /任务标识不匹配/)
  } finally { globalThis.fetch = previous }
})

test('business results use actual delivery, preserve quote/finding separation and flag uncollected plans', () => {
  const item = task('native')
  item.input_summary = '0.00003ETH换USDC，最低0.06USDC。'
  const input = report(item)
  input.samples[0].title = '原生资产即时兑换'
  input.samples[0].claimed_output = '报价0.071USDC'
  input.samples[0].independent_result = '使用0.00003ETH，实际收到0.067123USDC，最低0.06USDC。'
  input.shared_assessment.observations = [{ ...observation('native'), criterion_id: 'native-input' }]
  input.shared_assessment.cases = [{ case_id: 'uncaptured-http', dimension: 'availability', task_keys: ['native'] }]
  const before = JSON.stringify(input)
  const view = projectTaskTrace('r', input, 'native')
  assert.equal(view.title, 'ETH → USDC 即时兑换')
  assert.match(view.requestSummary, /0.00003 ETH/)
  assert.match(view.resultSummary, /0.067123 USDC/)
  assert.doesNotMatch(view.resultSummary, /0.071/)
  assert.equal(view.outcomeLabel, '已成交')
  assert.equal(view.verificationStatus, 'UNKNOWN')
  assert.match(view.verificationSummary, /服务响应未采集/)
  assert.equal(view.nodes.find(n => n.id === 'criteria').status, 'UNKNOWN')
  assert.equal(view.nodes.find(n => n.id === 'criteria').checks.length, 1)
  assert.equal(JSON.stringify(input), before)

  item.outcome = 'not_executed'
  input.shared_assessment.observations = [{ ...observation('native'), criterion_id: 'asset-display', verdict: 'FAIL',
    reason: 'tokenOut显示ETH，实际地址对应WETH', response_complete: true }]
  const quote = projectTaskTrace('r', input, 'native')
  assert.equal(quote.outcomeLabel, '已返回方案')
  assert.match(quote.resultSummary, /报价 0.071 USDC/)
  assert.doesNotMatch(quote.resultSummary, /实际到账/)
  assert.equal(quote.verificationStatus, 'FAIL')
  assert.match(quote.verificationSummary, /服务将 WETH 标注为 ETH；合约地址按 WETH 记录/)
})

test('order cancellation stays a refund and transaction receipt status must match the actual hash', () => {
  const item = task('order')
  item.input_summary = '使用0.04USDC创建限价订单，随后撤销退款。'
  const input = report(item)
  input.samples[0].title = '限价订单创建并撤销'
  input.samples[0].independent_result = '同笔创建并撤销订单9，0.04USDC全退，结束授权0；没有触发兑换。'
  input.shared_assessment.observations = [{ ...observation('order'), criterion_id: 'exact-principal-refund' }]
  const operation = action('order', '1', 'cancelLimitOrder(uint256)')
  const path = operation.evidence[0]
  const sources = [{ reportId: 'r', taskKey: 'order', path, value: { result: {
    transactionHash: '0x' + '2'.repeat(64), status: '0x1',
  } } }]
  let view = projectTaskTrace('r', input, 'order', { actions: [operation] }, sources)
  assert.equal(view.outcomeLabel, '已撤销退款')
  assert.match(view.resultSummary, /0.04 USDC本金全额退回/)
  assert.match(view.resultSummary, /未触发兑换/)
  let node = view.nodes.find(n => n.action)
  assert.doesNotMatch(node.summary, /cancelLimitOrder|uint256|0x/)
  assert.equal(node.receiptStatus, 'unknown')
  assert.equal(node.status, 'UNKNOWN')
  sources[0].value.result.transactionHash = operation.transaction_hash
  sources[0].value.result.status = '0x0'
  view = projectTaskTrace('r', input, 'order', { actions: [operation] }, sources)
  node = view.nodes.find(n => n.action)
  assert.equal(node.receiptStatus, 'failed')
  assert.equal(node.status, 'FAIL')
  assert.equal(node.tone, 'danger')
  assert.equal(node.action.verdict, 'PASS')
})

test('no observations do not imply a successful independent check', () => {
  const input = report(task('unknown', 'unknown'))
  input.shared_assessment.observations = []
  const view = projectTaskTrace('r', input, 'unknown')
  assert.equal(view.verificationStatus, 'unrecorded')
  assert.match(view.verificationSummary, /尚无可判核验记录/)
  assert.doesNotMatch(view.verificationSummary, /证据相符/)
})

test('partial criterion gaps remain unknown in the matching lane and retain already observed service facts', () => {
  const item = task('partial', 'not_executed')
  item.evidence.push('runtime/partial/business-request.json', 'runtime/partial/business-response.json')
  const input = report(item)
  input.shared_assessment.cases = [
    { case_id: 'case', dimension: 'functional', task_keys: ['partial'], criterion_ids: ['intent-binding', 'execution-effect'] },
    { case_id: 'service', dimension: 'availability', task_keys: ['partial'], criterion_ids: ['complete-response', 'service-uptime'] },
  ]
  input.shared_assessment.observations = [
    { ...observation('partial'), criterion_id: 'intent-binding' },
    { ...observation('partial'), case_id: 'service', criterion_id: 'complete-response', dimension: 'availability', response_complete: true },
  ]
  let view = projectTaskTrace('r', input, 'partial')
  let independent = view.nodes.find(n => n.id === 'verification')
  assert.equal(view.verificationStatus, 'UNKNOWN')
  assert.equal(independent.status, 'UNKNOWN')
  assert.match(independent.summary, /尚有未采项目/)
  assert.match(independent.business.find(field => field.label === '证据缺项').value, /独立执行效果/)
  assert.match(view.verificationSummary, /部分服务核验项目未采集/)
  assert.doesNotMatch(view.verificationSummary, /服务响应未采集/)
  assert.doesNotMatch(independent.summary, /模拟已核对|证据相符/)
  assert.equal(view.observations.length, 2)

  input.shared_assessment.cases[0].criterion_ids = ['intent-binding']
  view = projectTaskTrace('r', input, 'partial')
  assert.equal(view.verificationStatus, 'UNKNOWN')
  assert.equal(view.nodes.find(n => n.id === 'verification').status, 'PASS')
  assert.doesNotMatch(view.nodes.find(n => n.id === 'verification').summary, /模拟已核对|实际到账/)
  assert.match(view.verificationLabel, /服务核验有缺项/)

  input.shared_assessment.observations.push({ ...observation('partial'), case_id: 'behavior',
    criterion_id: 'accepted-goal', dimension: 'behavioral', verdict: 'FAIL', reason: '实际业务结果未达到任务约定目标。' })
  view = projectTaskTrace('r', input, 'partial')
  independent = view.nodes.find(n => n.id === 'verification')
  assert.equal(view.verificationStatus, 'FAIL')
  assert.equal(independent.status, 'FAIL')
  assert.doesNotMatch(view.verificationLabel, /功能声明/)
  assert.doesNotMatch(independent.statusLabel, /功能声明/)
})

test('asset labels use a notice without changing verdicts, and execution risks retain priority', () => {
  const item = task('label', 'not_executed')
  item.evidence.push('runtime/label/business-request.json')
  const input = report(item)
  const labelCheck = { ...observation('label'), criterion_id: 'asset-display', verdict: 'FAIL',
    reason: 'tokenOut显示ETH，实际地址对应WETH', response_complete: true }
  input.shared_assessment.observations = [labelCheck,
    { ...observation('label'), criterion_id: 'execution-effect' }]
  const before = JSON.stringify(input)
  let view = projectTaskTrace('r', input, 'label')
  assert.equal(isAssetLabelNotice(labelCheck), true)
  assert.equal(checkTone(labelCheck), 'notice')
  assert.equal(checkTone({ ...labelCheck, critical: true }), 'danger')
  assert.equal(view.verificationStatus, 'FAIL')
  assert.equal(view.verificationTone, 'notice')
  assert.equal(view.verificationLabel, '资产标注有差异')
  assert.match(view.verificationSummary, /服务将 WETH 标注为 ETH/)
  for (const id of ['verification', 'criteria']) {
    const node = view.nodes.find(n => n.id === id)
    assert.equal(node.status, 'FAIL')
    assert.equal(node.tone, 'notice')
    assert.equal(node.statusLabel, '资产标注有差异')
    assert.equal(node.checks.find(o => o.criterion_id === 'asset-display').verdict, 'FAIL')
  }
  assert.equal(view.outcomeLabel, '方案已验证')
  assert.equal(JSON.stringify(input), before)

  input.shared_assessment.observations[1].verdict = 'UNKNOWN'
  view = projectTaskTrace('r', input, 'label')
  assert.equal(view.verificationStatus, 'FAIL')
  assert.equal(view.verificationTone, 'warning')
  assert.match(view.verificationLabel, /有待核项/)
  assert.notEqual(view.outcomeLabel, '方案已验证')

  input.shared_assessment.observations.push({ ...observation('label'), criterion_id: 'intent-binding', verdict: 'FAIL', reason: '接收账户与请求不一致。' })
  view = projectTaskTrace('r', input, 'label')
  assert.equal(view.verificationTone, 'danger')
  assert.equal(view.nodes.find(n => n.id === 'verification').tone, 'danger')
  assert.match(view.verificationSummary, /接收账户与请求不一致/)
  assert.equal(verificationTone([labelCheck], 'invalid'), 'warning')
  assert.equal(verificationTone([], 'unrecorded'), 'neutral')
  assert.equal(checkTone({ ...labelCheck, measurement_validity: 'unknown' }), 'warning')

  item.outcome = 'failed'
  view = projectTaskTrace('r', input, 'label')
  assert.equal(view.nodes.find(n => n.id === 'result').tone, 'danger')
})
