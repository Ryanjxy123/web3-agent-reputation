import type { ChainAction, EvaluationReport, ReportChainEvidence, SampleExplanation, SharedObservation, SharedTask, Verdict } from './contracts'
import { chainName } from './agentProfile.ts'

/** Display-only projection. Scores, verdicts and source records remain authoritative. */
export type TraceField = { label: string; value: string }
export type TraceStatus = Verdict | 'unrecorded' | 'invalid'
export type TraceTone = 'neutral' | 'success' | 'notice' | 'warning' | 'danger'
export type TraceNode = {
  id: string; title: string; role: string; summary: string
  business: TraceField[]; checks: SharedObservation[]; statusLabel: string; tone: TraceTone
  input: TraceField[]; output: TraceField[]; evidence: string[]; status: TraceStatus
  source: '原始记录' | '证据重建'; timestamp: string | null; timeLabel: string | null
  lane: 'execution' | 'verification'; action?: ChainAction; receiptStatus?: 'success' | 'failed' | 'unknown'
}
export type TraceEdge = { id: string; from: string; to: string; kind: 'execution' | 'evidence'; label: string }
export type TraceStep = { id: string; nodeId: string; label: string; detail: string }
export type TraceSourceRecord = { reportId: string; taskKey: string; path: string; value?: unknown; error?: string }
export type TaskTraceViewModel = {
  reportId: string; taskKey: string; title: string; capabilityId: string; capabilityTitle: string
  requestSummary: string; resultSummary: string; verificationLabel: string; verificationSummary: string; verificationStatus: TraceStatus; verificationTone: TraceTone
  outcome: SharedTask['outcome']; outcomeLabel: string; status: TraceStatus; hasIssues: boolean
  observations: SharedObservation[]; samples: SampleExplanation[]; evidence: string[]
  observedAt: string | null; generatedAt: string; nodes: TraceNode[]; edges: TraceEdge[]; steps: TraceStep[]
}

const unique = (values: string[]) => [...new Set(values)]
const object = (value: unknown): Record<string, unknown> => value !== null && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {}
const text = (value: unknown) => typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean' ? String(value) : ''
const fields = (value: Record<string, unknown>, labels: Record<string, string>) => Object.entries(labels)
  .filter(([key]) => text(value[key]) !== '').map(([key, label]) => ({ label, value: text(value[key]) }))
const validTime = (value: unknown): string | null => typeof value === 'string' && !Number.isNaN(Date.parse(value)) ? value : null

/** Wording only: full observation text stays in the original report and technical fields. */
export function businessText(value: string): string {
  return value.replace(/(?:tokenIn|tokenOut|输入资产|输出资产)显示\s*([A-Z][A-Z0-9]*)[，,；;]\s*实际地址对应\s*([A-Z][A-Z0-9]*)/g, '服务将 $2 标注为 $1；合约地址按 $2 记录。')
    .replace(/tokenIn/g, '输入资产').replace(/tokenOut/g, '输出资产')
    .replace(/calldata/g, '交易调用参数').replace(/Cancelled/g, '已撤销').replace(/Executed/g, '已执行')
    .replace(/0x[\da-f]{40,}/gi, address => `${address.slice(0, 8)}…${address.slice(-4)}`)
    .replace(/(\d)(USDC|WETH|ETH)\b/g, '$1 $2')
}

const amountIn = (value: string) => value.match(/(?:使用|本金)?\s*(\d+(?:\.\d+)?)\s*([A-Z][A-Z0-9]{1,9})\b/)
const amountFormat = new Intl.NumberFormat('en-US', { maximumSignificantDigits: 6, useGrouping: false })
const amountText = (match: RegExpMatchArray | null) => {
  if (!match) return ''
  const value = Number(match[1]), formatted = amountFormat.format(value)
  return `${Number(formatted) !== value ? '约 ' : ''}${formatted} ${match[2]}`
}

/** Visual importance is separate from the report's authoritative verdict. */
export function isAssetLabelNotice(check: SharedObservation): boolean {
  return check.measurement_validity === 'valid' && check.dimension === 'functional'
    && check.criterion_id === 'asset-display' && check.verdict === 'FAIL' && !check.critical
}

export function checkTone(check: SharedObservation): TraceTone {
  if (isAssetLabelNotice(check)) return 'notice'
  if (check.measurement_validity !== 'valid' || check.verdict === 'UNKNOWN') return 'warning'
  return check.verdict === 'FAIL' ? 'danger' : check.verdict === 'PASS' ? 'success' : 'neutral'
}

export function verificationTone(checks: SharedObservation[], status: TraceStatus): TraceTone {
  if (checks.some(check => checkTone(check) === 'danger')) return 'danger'
  const labelNotice = checks.some(isAssetLabelNotice)
  if (status === 'FAIL' && !labelNotice) return 'danger'
  if (status === 'invalid' || status === 'UNKNOWN' || checks.some(check => checkTone(check) === 'warning')) return 'warning'
  if (labelNotice) return 'notice'
  return status === 'PASS' ? 'success' : 'neutral'
}

function verificationLabel(status: TraceStatus, checks: SharedObservation[] = [], hasMissing = false): string {
  if (status === 'FAIL' && checks.some(isAssetLabelNotice) && !checks.some(check => checkTone(check) === 'danger')) {
    return hasMissing || checks.some(check => checkTone(check) === 'warning') ? '资产标注有差异 · 有待核项' : '资产标注有差异'
  }
  return { PASS: '已核项目通过', FAIL: checks.some(item => item.dimension === 'functional' && item.measurement_validity === 'valid' && item.verdict === 'FAIL') ? '功能声明不一致' : '核验存在失败项', UNKNOWN: '存在待核项目', invalid: '测量无效',
    unrecorded: '尚无核验记录', NOT_APPLICABLE: '无适用核验项' }[status]
}
const callTitles: Record<string, string> = {
  approve: '资产授权', scheduleSwap: '创建定时订单', cancelSwap: '撤销定时订单', getSwap: '查询定时订单',
  createLimitOrder: '创建限价订单', cancelLimitOrder: '撤销限价订单', getLimitOrder: '查询限价订单',
  instantSwap: '即时资产兑换', balanceOf: '查询资产余额', allowance: '查询剩余授权', exactInputSingle: '执行资产兑换',
}

export const criterionTitles: Record<string, string> = {
  'complete-response': '业务响应按时完整', 'intent-binding': '任务参数与授权',
  'asset-display': '资产标识一致性', 'execution-effect': '独立执行效果', 'onchain-fulfillment': '真实交易与资产履约',
  'native-input': '原生资产输入', 'order-created': '订单创建', 'order-query': '订单查询',
  'order-cancelled': '订单撤销', 'exact-principal-refund': '本金完整退回',
  'allowance-zero': '结束授权归零', 'actual-network-fees': '实际网络费用',
  'contract-state': '合约状态', 'receipt-status': '交易回执',
  'order-binding': '订单归属与参数绑定', 'stored-management-state': '订单最终持久状态',
  'ending-allowance': '任务结束授权状态', 'management-fee-conservation': '订单管理费用与资产核对',
  'accepted-goal': '任务约定目标', 'asset-permission-boundary': '资产与权限边界',
  'minimum-output': '最低到账约束', 'native-fee-conservation': '原生资产与费用核对',
}

export function traceOutcomeLabel(task: SharedTask, observations: SharedObservation[], report: EvaluationReport): string {
  const passed = (ids: string[]) => observations.some(item => ids.includes(item.criterion_id) && item.verdict === 'PASS' && item.measurement_validity === 'valid')
  if (task.outcome === 'completed') {
    if (passed(['exact-principal-refund'])) return '已撤销退款'
    return passed(['execution-effect', 'native-input']) ? '已成交' : '已完成'
  }
  const executionPlanned = report.shared_assessment?.cases.some(item => item.dimension === 'behavioral' && item.normal_execution && item.task_keys.includes(task.task_key))
  if (task.outcome === 'not_executed' && !executionPlanned) {
    if (passed(['execution-effect'])) return '方案已验证'
    return observations.some(item => item.response_complete === true && item.measurement_validity === 'valid') ? '已返回方案' : '未取得方案'
  }
  return { failed: '真实执行失败', rejected: '已拒绝', protected_exit: '保护退出', not_executed: '尚未执行', unknown: '结局待核' }[task.outcome]
}

function observationStatus(observations: SharedObservation[]): TraceStatus {
  if (observations.some(item => item.measurement_validity === 'valid' && item.verdict === 'FAIL')) return 'FAIL'
  if (observations.some(item => item.measurement_validity === 'invalid')) return 'invalid'
  if (observations.some(item => item.measurement_validity === 'unknown' || item.verdict === 'UNKNOWN')) return 'UNKNOWN'
  if (observations.some(item => item.verdict === 'PASS')) return 'PASS'
  return observations.length ? 'NOT_APPLICABLE' : 'unrecorded'
}

function outcomeStatus(task: SharedTask): TraceStatus {
  return task.outcome === 'completed' ? 'PASS' : task.outcome === 'failed' ? 'FAIL' : 'UNKNOWN'
}

/** A chain response is accepted only when sample ID and all source refs belong to this report's task. */
function taskActions(report: EvaluationReport, task: SharedTask, chain?: ReportChainEvidence | null): ChainAction[] {
  const samples = report.samples.filter(item => item.sample.task_key === task.task_key)
  const permitted = new Set([...task.evidence, ...samples.flatMap(item => item.sample.evidence)])
  const ids = new Set(samples.map(item => item.sample.sample_id))
  return (chain?.actions ?? []).filter(action => ids.has(action.sample_id) && action.evidence.length > 0
    && action.evidence.every(path => permitted.has(path)))
}

/** No array-position joins, no Agent snapshot merge, and no cross-report source cache. */
export function projectTaskTrace(reportId: string, report: EvaluationReport, taskKey: string,
  chainEvidence?: ReportChainEvidence | null, sources: TraceSourceRecord[] = []): TaskTraceViewModel | null {
  const assessment = report.shared_assessment
  const task = assessment?.tasks.find(item => item.task_key === taskKey)
  if (!assessment || !task) return null
  const observations = assessment.observations.filter(item => item.task_key === taskKey)
  const samples = report.samples.filter(item => item.sample.task_key === taskKey)
  const evidence = unique([...task.evidence, ...observations.flatMap(item => item.evidence), ...samples.flatMap(item => item.sample.evidence)])
  const permitted = new Set(evidence)
  const records = sources.filter(item => item.reportId === reportId && item.taskKey === taskKey && permitted.has(item.path) && !item.error)
  const source = (suffix: string) => records.find(item => item.path.endsWith('/' + suffix))
  const requestSource = source('business-request.json')
  const responseSource = source('business-response.json')
  const observationSource = source('business-observation.json')
  const request = object(requestSource?.value)
  const response = object(responseSource?.value)
  const transport = object(observationSource?.value)
  const quote = object(response.quote)
  const actions = taskActions(report, task, chainEvidence)
  const hasServiceRecord = evidence.some(path => path.endsWith('/business-request.json'))
  const hasResponseRecord = observations.some(item => item.response_complete === true) || Object.keys(response).length > 0
  const availability = observations.filter(item => item.dimension === 'availability')
  const sample = samples[0]
  const label = traceOutcomeLabel(task, observations, report)
  const resultStatus = ['已返回方案', '方案已验证'].includes(label) ? 'PASS' : outcomeStatus(task)
  const capabilityTitle = assessment.capabilities.find(item => item.capability_id === task.capability_id)?.title || task.capability_id
  const missingCases = assessment.cases.filter(item => item.task_keys.includes(taskKey)
    && (!observations.some(observation => observation.case_id === item.case_id)
      || item.criterion_ids?.some(id => !observations.some(observation => observation.case_id === item.case_id && observation.criterion_id === id))))
  const missingService = missingCases.some(item => item.dimension === 'availability')
  const serviceResponseUnrecorded = !hasResponseRecord && !evidence.some(path => path.endsWith('/business-response.json'))
  const missingServiceSummary = serviceResponseUnrecorded ? '服务响应未采集，无法判断可用性。'
    : availability.length ? '部分服务核验项目未采集，可用性结论仍有缺项。' : '服务响应已有记录，可用性尚无核验观测。'
  const nonAvailability = observations.filter(item => item.dimension !== 'availability')
  const missingIndependent = missingCases.filter(item => item.dimension !== 'availability')
  const independentCheckedStatus = observationStatus(nonAvailability)
  const independentStatus = missingIndependent.length && !['FAIL', 'invalid'].includes(independentCheckedStatus) ? 'UNKNOWN' : independentCheckedStatus
  const missingTitles = (cases: typeof missingCases) => unique(cases.flatMap(item => item.criterion_ids?.length
    ? item.criterion_ids.filter(id => !observations.some(observation => observation.case_id === item.case_id && observation.criterion_id === id))
      .map(id => criterionTitles[id] || id)
    : [item.title || '计划核验']))
  const checkedStatus = observationStatus(observations)
  const verificationStatus = missingCases.length && !['FAIL', 'invalid'].includes(checkedStatus) ? 'UNKNOWN' : checkedStatus
  const verificationTitle = checkedStatus === 'PASS' && independentStatus === 'PASS' && missingService
    ? serviceResponseUnrecorded ? '链上结果已核 · 服务未采' : '已核项目通过 · 服务核验有缺项'
    : verificationLabel(verificationStatus, observations, missingCases.length > 0)
  const issues = observations.filter(item => item.verdict === 'FAIL' || item.verdict === 'UNKNOWN' || item.measurement_validity !== 'valid')
  const failure = issues.find(item => checkTone(item) === 'danger') ?? issues.find(isAssetLabelNotice)
  const verificationSummary = unique([
    ...(failure ? [businessText(failure.reason)] : []),
    ...(missingService ? [missingServiceSummary] : []),
    ...(!failure && issues.length ? [businessText(issues[0]!.reason)] : []),
    ...(missingIndependent.length ? [`独立业务核验尚有未采项目：${missingTitles(missingIndependent).join('、')}。`] : []),
  ]).join(' ') || (verificationStatus === 'PASS' ? '已记录的任务参数、业务结果与独立证据相符。'
    : verificationStatus === 'NOT_APPLICABLE' ? '本任务没有适用的核验项目。' : '尚无可判核验记录，无法确认业务结果符合要求。')
  const pair = sample?.title.match(/([A-Z][A-Z0-9]+)\s*→\s*([A-Z][A-Z0-9]+)/)
    ?? task.input_summary.match(/\d\s*([A-Z][A-Z0-9]+)\s*换\s*([A-Z][A-Z0-9]+)/)
  const inputAmount = amountText(amountIn(task.input_summary))
  const received = sample?.independent_result.match(/(?:实际收到|真实到账)\s*(\d+(?:\.\d+)?)\s*([A-Z][A-Z0-9]+)/) ?? null
  const refunded = sample?.independent_result.match(/(\d+(?:\.\d+)?)\s*([A-Z][A-Z0-9]+)\s*全退/) ?? null
  const quoteAmount = sample?.claimed_output.match(/(?:服务报价|报价)\s*(\d+(?:\.\d+)?)\s*([A-Z][A-Z0-9]+)/) ?? null
  const simulation = sample?.independent_result.match(/独立模拟输出\s*(\d+(?:\.\d+)?)\s*([A-Z][A-Z0-9]+)/) ?? null
  const minimum = (sample?.independent_result || task.input_summary).match(/最低\s*(\d+(?:\.\d+)?)\s*([A-Z][A-Z0-9]+)/)
  const title = pair ? `${pair[1]} → ${pair[2]} 即时兑换` : (sample?.title || capabilityTitle).replace(/^[A-Z]\d+\s*·\s*/, '')
  const requestSummary = pair && inputAmount
    ? `使用 ${inputAmount}，${task.outcome === 'not_executed' ? '请求兑换为' : '兑换为'} ${pair[2]}${minimum && task.outcome === 'completed' ? `，最低接收 ${amountText(minimum)}` : ''}。`
    : businessText(task.input_summary)
  const resultSummary = label === '已撤销退款' ? `创建、查询并撤销订单，${amountText(refunded) || inputAmount || '原'}本金全额退回；未触发兑换。`
    : task.outcome === 'completed' && received ? `实际到账 ${amountText(received)}${inputAmount ? `，投入 ${inputAmount}` : ''}。`
    : label === '方案已验证' ? `已返回兑换方案${simulation ? `，独立模拟输出 ${amountText(simulation)}` : ''}；尚无成交交易。`
    : label === '已返回方案' ? `已返回兑换方案${quoteAmount ? `，报价 ${amountText(quoteAmount)}` : ''}；实际兑换效果未核。`
    : label === '未取得方案' ? '未取得完整业务响应，无法确认方案或兑换效果。'
    : businessText(sample?.independent_result || label)
  const resultChecks = nonAvailability.filter(item => ['execution-effect', 'native-input', 'minimum-output', 'exact-principal-refund', 'accepted-goal'].includes(item.criterion_id))
  const nodes: TraceNode[] = []
  const edges: TraceEdge[] = []
  const add = (id: string, title: string, role: string, summary: string, input: TraceField[], output: TraceField[], refs: string[],
    status: TraceStatus, lane: TraceNode['lane'] = 'execution', timestamp: string | null = null, timeLabel: string | null = null,
    action?: ChainAction) => {
    nodes.push({ id, title, role, summary, business: [], checks: [], statusLabel: verificationLabel(status), tone: verificationTone([], status), input, output, evidence: unique(refs), status,
      source: id.startsWith('call:') || [requestSource?.path, responseSource?.path].some(path => path && refs.includes(path)) ? '原始记录' : '证据重建',
      timestamp, timeLabel, lane, action })
  }
  const connect = (from: string, to: string, kind: TraceEdge['kind'], edgeLabel: string) => edges.push({ id: `${from}:${to}`, from, to, kind, label: edgeLabel })
  const taskSources = evidence.filter(path => /\/(?:task|input|execution-intent)\.json$/.test(path))
  add('task', '测试任务', '用户 / 测试任务', task.input_summary,
    [{ label: '任务标识', value: taskKey }, { label: '输入要求', value: task.input_summary }], [], taskSources.length ? taskSources : task.evidence, resultStatus)
  add('service', hasServiceRecord ? 'Agent 服务请求' : '服务调用未记录', 'HTTP 服务', hasServiceRecord
    ? [text(request.method), text(request.url)].filter(Boolean).join(' ') || '报告已引用业务请求原件。'
    : '本任务没有 Agent 业务 HTTP 请求/响应记录；链上操作不能代替服务可用性观测。',
    fields(object(request.body), { tokenIn: '输入资产地址', tokenOut: '输出资产地址', amountIn: '输入数量', recipient: '接收账户', slippageBps: '滑点 bps' }),
    fields(transport, { status: 'HTTP 状态', elapsed_ms: 'HTTP 观测耗时 ms' }),
    evidence.filter(path => /\/business-(?:request|observation)\.json$/.test(path)),
    hasServiceRecord ? observationStatus(availability) : 'unrecorded', 'execution', validTime(transport.started_at), 'HTTP 请求开始')
  if (hasServiceRecord) connect('task', 'service', 'execution', '业务请求')
  if (hasResponseRecord) {
    add('response', response.status && response.status !== 'ready' ? '服务返回记录' : '返回结果 / 交易方案', 'Agent 服务响应', sample?.claimed_output || '原件记录已取得业务响应。',
      [], [{ label: '报告中的返回说明', value: sample?.claimed_output || '未记录' },
        ...fields(response, { status: '服务状态' }),
        ...fields(object(quote.tokenIn), { symbol: '返回的输入资产标签', address: '输入资产地址', amount: '输入数量' }),
        ...fields(object(quote.tokenOut), { symbol: '返回的输出资产标签', address: '输出资产地址', estimatedAmount: '估算输出', minimumAmount: '最低输出' })],
      evidence.filter(path => path.endsWith('/business-response.json')), observationStatus(availability), 'execution', validTime(transport.received_at), 'HTTP 完整响应接收')
    connect('service', 'response', 'execution', '返回方案')
  }
  if (actions.length) {
    const executors = unique(actions.map(item => item.executor).filter(Boolean))
    add('wallet', '用户执行账户', '用户账户执行', '实际执行账户来自交易 from。由用户账户执行与 Agent 返回方案分别记录；签名交互过程没有内部日志。',
      executors.map(value => ({ label: '执行账户', value })), [{ label: '独立交易数', value: String(new Set(actions.map(item => item.transaction_hash)).size) }],
      unique(actions.flatMap(item => item.evidence.filter(path => /transaction.*(?:bin|json)$/.test(path)))), outcomeStatus(task))
    connect(hasResponseRecord ? 'response' : 'task', 'wallet', hasResponseRecord ? 'execution' : 'evidence', hasResponseRecord ? '账户执行方案' : '任务执行证据')
    const grouped = new Map<string, ChainAction[]>()
    for (const action of actions) grouped.set(action.transaction_hash, [...(grouped.get(action.transaction_hash) ?? []), action])
    let previousTransaction: string | null = null
    for (const [hash, transactionActions] of grouped) {
      let previousCall = 'wallet'
      transactionActions.forEach((action, index) => {
        const id = `call:${action.sample_id}:${hash}:${index}`
        const blockSource = records.find(item => action.evidence.includes(item.path) && object(object(item.value).result).number !== undefined)
        const block = object(object(blockSource?.value).result)
        const seconds = typeof block.timestamp === 'string' && /^0x[\da-f]+$/i.test(block.timestamp) ? Number.parseInt(block.timestamp, 16) : NaN
        const timestamp = Number.isFinite(seconds) && Number.parseInt(text(block.number), 16) === action.block_number ? new Date(seconds * 1000).toISOString() : null
        const methodName = action.method.split('(')[0]
        const callTitle = callTitles[methodName] || action.title
        add(id, callTitle + (transactionActions.length > 1 ? ` · ${String(index + 1).padStart(2, '0')}` : ''),
          action.action === 'contract_read' ? '合约查询 · 同笔调用' : '链上合约调用', action.summary,
          [{ label: '执行账户', value: action.executor }, { label: '调用目标', value: action.target }, { label: '合约方法', value: action.method }],
          [{ label: '交易哈希', value: hash }, { label: 'chain_id', value: String(action.chain_id) }, { label: '区块', value: String(action.block_number) },
            { label: '同笔操作', value: `${index + 1} / ${transactionActions.length}` }, { label: '判定来源', value: '沿用报告的任务整体结论，本视图不新增单次调用判定' },
            ...(action.action === 'contract_read' ? [{ label: '查询返回值', value: '交易回执没有记录内部调用返回值；固定块状态核验见独立核验节点。' }] : [])],
          action.evidence, action.verdict, 'execution', timestamp, timestamp ? '链上区块时间（同笔共享）' : null, action)
        connect(previousCall, id, 'execution', index ? '同笔后续调用' : previousTransaction ? '另一笔账户交易' : '账户调用')
        previousCall = id
      })
      previousTransaction = previousCall
      connect(previousCall, 'result', 'evidence', '回执 / 状态')
    }
  }
  add('result', label, '业务结果', sample?.independent_result || '报告未记录独立结果摘要。',
    [], [{ label: '实际结局', value: label }, { label: '独立结果', value: sample?.independent_result || '本任务没有独立结果摘要。' }],
    unique(samples.flatMap(item => item.sample.evidence)), resultStatus, 'execution')
  if (!actions.length && hasResponseRecord) connect('response', 'result', 'evidence', '已记录结果')
  add('verification', '独立核验', '独立核验', '平台引用请求响应、交易回执、事件和资产 / 订单状态核验事实。核验关系不参与交易广播。',
    [{ label: '核验输入', value: `${evidence.length} 份引用；以报告允许读取的原件为准。` }],
    observations.filter(item => item.dimension !== 'availability').map(item => ({ label: criterionTitles[item.criterion_id] || item.criterion_id, value: item.reason })),
    unique(observations.flatMap(item => item.evidence)), observationStatus(observations.filter(item => item.dimension !== 'availability')), 'verification')
  connect('result', 'verification', 'evidence', '独立观察')
  if (hasServiceRecord) connect('service', 'verification', 'evidence', '请求 / 响应证据')
  add('criteria', '报告判据', '报告判据', `${observations.length} 项判据观测关联本任务；分数直接来自当前报告。`,
    observations.map(item => ({ label: `${item.dimension} · ${criterionTitles[item.criterion_id] || item.criterion_id}`, value: item.measurement_validity === 'valid' ? item.verdict : item.measurement_validity })),
    [{ label: '报告 ID', value: reportId }, { label: '政策版本', value: String(report.policy_version ?? '未记录') }],
    unique(observations.flatMap(item => item.evidence)), observationStatus(observations), 'verification')
  connect('verification', 'criteria', 'evidence', '对应判据')
  // Business presentation sits beside, rather than replacing, the complete technical fields above.
  for (const node of nodes) {
    if (node.id === 'task') {
      node.title = '用户任务'; node.role = '用户请求'; node.statusLabel = '任务已记录'
      node.summary = pair && inputAmount ? task.outcome === 'not_executed' ? `请求 ${inputAmount} → ${pair[2]} 兑换方案。`
        : `兑换 ${inputAmount} 为 ${pair[2]}。` : /订单/.test(capabilityTitle + requestSummary)
          ? `${inputAmount ? `使用 ${inputAmount} ` : ''}创建并管理订单。` : requestSummary
      node.business = [{ label: '实际请求', value: requestSummary }]
    } else if (node.id === 'service') {
      node.title = hasServiceRecord ? '请求 Agent 服务' : 'Agent 服务未采集'
      node.summary = hasServiceRecord ? '通过 HTTP 向 Agent 请求业务方案。' : '未记录本任务的 HTTP 服务响应。'
      if (missingService && !['FAIL', 'invalid'].includes(node.status)) node.status = 'UNKNOWN'
      node.statusLabel = hasServiceRecord ? (node.status === 'PASS' ? '响应完整' : missingService && availability.length ? '服务核验有缺项' : '响应待核') : '未采集'
      node.business = [{ label: '请求内容', value: requestSummary }, { label: '服务记录', value: hasServiceRecord
        ? observations.some(item => item.response_complete === true) ? '已取得完整业务响应。' : '未取得完整业务响应，不能判断为服务成功。'
        : '本次证据从用户账户的链上操作开始；服务可用性未知。' }]
      node.checks = availability
    } else if (node.id === 'response') {
      node.summary = failure?.criterion_id === 'asset-display' ? `已返回方案；${businessText(failure.reason)}`
        : availability.some(item => item.response_complete === true) ? 'Agent 已返回兑换方案，交由用户账户执行。' : '服务响应已记录，完整性仍待核。'
      node.statusLabel = availability.some(item => item.response_complete === true) ? '方案已返回' : '响应待核'
      node.business = [{ label: '服务交付', value: availability.some(item => item.response_complete === true) ? '兑换报价与交易方案' : '尚未确认完整方案' },
        ...(quoteAmount ? [{ label: '估算获得', value: `${amountText(quoteAmount)}（报价）` }] : []),
        ...(minimum ? [{ label: '最低接收', value: amountText(minimum) }] : [])]
      node.checks = observations.filter(item => item.dimension === 'availability' || ['asset-display', 'intent-binding'].includes(item.criterion_id))
    } else if (node.id === 'wallet') {
      const count = new Set(actions.map(item => item.transaction_hash)).size
      node.summary = `用户账户提交 ${count} 笔链上交易。`; node.statusLabel = '账户执行已记录'
      node.business = [{ label: '执行主体', value: '用户账户' }, { label: '链上执行', value: `${count} 笔交易，${actions.length} 项合约操作` }]
    } else if (node.action) {
      const action = node.action
      const method = action.method.split('(')[0]
      const details: Record<string, { summary: string; criteria: string[] }> = {
        approve: { summary: `为本次资产操作授权${inputAmount ? ` ${inputAmount}` : '额度'}。`, criteria: ['intent-binding', 'asset-permission-boundary'] },
        instantSwap: { summary: '合约执行即时兑换。', criteria: ['native-input', 'minimum-output', 'native-fee-conservation'] },
        exactInputSingle: { summary: '合约按用户方案执行资产兑换。', criteria: ['execution-effect', 'onchain-fulfillment'] },
        scheduleSwap: { summary: '创建定时订单，等待后续管理。', criteria: ['order-binding'] },
        createLimitOrder: { summary: '创建带价格条件的限价订单。', criteria: ['order-binding'] },
        cancelSwap: { summary: '撤销定时订单，退回托管本金。', criteria: ['exact-principal-refund', 'stored-management-state'] },
        cancelLimitOrder: { summary: '撤销限价订单，退回托管本金。', criteria: ['exact-principal-refund', 'stored-management-state'] },
        getSwap: { summary: '读取定时订单记录。', criteria: ['stored-management-state'] },
        getLimitOrder: { summary: '读取限价订单记录。', criteria: ['stored-management-state'] },
        balanceOf: { summary: '读取资产余额，供本金核对。', criteria: ['exact-principal-refund', 'native-fee-conservation'] },
        allowance: { summary: '读取剩余授权额度。', criteria: ['ending-allowance'] },
      }
      const detail = details[method]
      node.summary = detail?.summary || '链上交易记录包含此项合约操作。'
      node.statusLabel = action.action === 'contract_read' ? '查询已记录' : '调用已记录'
      node.business = [{ label: '业务动作', value: callTitles[method] || businessText(action.title) },
        { label: '执行网络', value: chainName(action.chain_id) },
        ...(action.action === 'contract_read' ? [{ label: '查询结果', value: '调用返回值未单列；最终资产或订单状态由平台另行核验。' }] : [])]
      node.checks = nonAvailability.filter(item => detail?.criteria.includes(item.criterion_id))
      const receipt = records.map(item => object(object(item.value).result)).find(item =>
        text(item.transactionHash).toLowerCase() === action.transaction_hash.toLowerCase() && ['0x0', '0x1'].includes(text(item.status)))
      node.receiptStatus = receipt?.status === '0x1' ? 'success' : receipt?.status === '0x0' ? 'failed' : 'unknown'
      // ChainAction.verdict is a task verdict, not a receipt or an individual-call verdict.
      node.status = node.receiptStatus === 'success' ? 'PASS' : node.receiptStatus === 'failed' ? 'FAIL' : 'UNKNOWN'
    } else if (node.id === 'result') {
      node.title = '业务结果'; node.summary = task.outcome === 'completed' && received ? `实际到账 ${amountText(received)}。`
        : label === '已撤销退款' ? `${amountText(refunded) || inputAmount || '原'}本金已退回；未兑换。` : resultSummary
      node.statusLabel = label
      node.business = [ ...(received ? [{ label: '实际到账', value: amountText(received) }] : []),
        ...(refunded ? [{ label: '退回本金', value: amountText(refunded) }] : []),
        ...(minimum && task.outcome === 'completed' ? [{ label: '最低接收', value: amountText(minimum) }] : []),
        ...(label === '已撤销退款' ? [{ label: '订单结局', value: '已撤销；本任务未发生兑换' }] : [])]
      node.checks = resultChecks
    } else if (node.id === 'verification') {
      const independentFailure = nonAvailability.find(item => checkTone(item) === 'danger') ?? nonAvailability.find(isAssetLabelNotice)
      node.status = independentStatus
      node.summary = independentFailure ? businessText(independentFailure.reason) : missingIndependent.length ? '独立业务核验尚有未采项目，结果仍待核。' : independentStatus === 'PASS'
        ? label === '已撤销退款' ? '订单已撤销，本金退款与记录的证据相符。'
          : task.outcome === 'completed' && resultChecks.some(item => item.measurement_validity === 'valid' && item.verdict === 'PASS') ? '实际到账、任务要求与链上证据相符。'
            : simulation && resultChecks.some(item => item.criterion_id === 'execution-effect' && item.measurement_validity === 'valid' && item.verdict === 'PASS') ? '方案参数与独立模拟已核对。'
              : '已记录的业务核验项目通过。'
        : '部分业务效果缺少独立证据，结论待核。'
      node.checks = nonAvailability
      node.business = [{ label: '核验范围', value: label === '已撤销退款' ? '订单归属、撤销终态、本金退款、授权与费用' : task.outcome === 'completed' ? '交易、输入输出资产、实际到账与费用' : '请求参数、资产标识与可观察的方案效果' },
        ...(missingIndependent.length ? [{ label: '证据缺项', value: `尚未采集：${missingTitles(missingIndependent).join('、')}；不按通过处理。` }] : [])]
      node.statusLabel = verificationLabel(node.status, nonAvailability, missingIndependent.length > 0)
    } else if (node.id === 'criteria') {
      node.title = '平台核验结论'; node.role = '平台评价'; node.summary = verificationSummary
      node.status = verificationStatus; node.statusLabel = verificationTitle; node.checks = observations
      node.business = [{ label: '评价范围', value: '服务响应、功能声明与链上业务分别核验' },
        ...(missingCases.length ? [{ label: '证据缺项', value: `尚未采集：${missingTitles(missingCases).join('、')}；不按通过处理。` }] : [])]
    }
    const executionFailed = node.action ? node.receiptStatus === 'failed'
      : ['task', 'wallet', 'result'].includes(node.id) && task.outcome === 'failed'
    node.tone = executionFailed ? 'danger' : verificationTone(node.checks, node.status)
    if (node.tone === 'notice' && (node.id === 'criteria' && missingCases.length || node.id === 'verification' && missingIndependent.length)) node.tone = 'warning'
  }
  return { reportId, taskKey, title, capabilityId: task.capability_id, capabilityTitle,
    requestSummary, resultSummary, verificationLabel: verificationTitle, verificationSummary, verificationStatus,
    verificationTone: missingCases.length && verificationTone(observations, verificationStatus) === 'notice' ? 'warning' : verificationTone(observations, verificationStatus),
    outcome: task.outcome, outcomeLabel: label, status: resultStatus, hasIssues: issues.length > 0 || missingCases.length > 0,
    observations, samples, evidence, observedAt: task.observed_at, generatedAt: report.generated_at, nodes, edges,
    steps: nodes.map(node => ({ id: `step:${node.id}`, nodeId: node.id, label: node.title, detail: node.summary })) }
}

export function projectTaskTraces(reportId: string, report: EvaluationReport, chainEvidence?: ReportChainEvidence | null): TaskTraceViewModel[] {
  return (report.shared_assessment?.tasks ?? []).map(task => projectTaskTrace(reportId, report, task.task_key, chainEvidence)!)
}

/** Fetch only task-scoped identity, HTTP records and up to three cited blocks/receipts. All GETs are local evidence reads. */
export async function loadTraceSources(reportId: string, task: SharedTask, signal?: AbortSignal): Promise<TraceSourceRecord[]> {
  const paths = task.evidence.filter(path => path.startsWith('runtime/'))
  const read = async (path: string): Promise<TraceSourceRecord> => {
    const identity = { reportId, taskKey: task.task_key, path }
    try {
      const response = await fetch(`/api/reports/${encodeURIComponent(reportId)}/evidence?path=${encodeURIComponent(path)}`, { signal })
      if (!response.ok) return { ...identity, error: `原件读取失败 HTTP ${response.status}` }
      if (Number(response.headers?.get('Content-Length')) > 262144) {
        await response.body?.cancel()
        return { ...identity, error: '原件较大，请使用证据下载入口。' }
      }
      const raw = await response.text()
      if (raw.length > 262144) return { ...identity, error: '原件较大，请使用证据下载入口。' }
      return { ...identity, value: JSON.parse(raw) as unknown }
    } catch (error) {
      if (signal?.aborted) throw error
      return { ...identity, error: error instanceof Error ? error.message : '原件不可读' }
    }
  }
  const identityPath = paths.find(path => path.endsWith('/task.json'))
  const identity = identityPath ? await read(identityPath) : null
  const identityValue = object(identity?.value)
  if (identity && identity.value && text(identityValue.request_id) !== task.task_key) return [{ ...identity, value: undefined, error: '原件任务标识不匹配，未用于链路展示。' }]
  const directory = identityPath?.slice(0, identityPath.lastIndexOf('/') + 1)
  const http = directory ? ['business-request.json', 'business-response.json', 'business-observation.json']
    .map(name => directory + name).filter(path => paths.includes(path)) : []
  const blocks = paths.filter(path => /\/(?:canonical-)?block\.response\.bin$/.test(path) && /independent-proof/.test(path)).slice(0, 3)
  const receipts = paths.filter(path => /\/receipt\.response\.bin$/.test(path)).slice(0, 3)
  return [...(identity ? [identity] : []), ...await Promise.all([...http, ...blocks, ...receipts].map(read))]
}

const explorers: Record<number, string> = { 1: 'https://etherscan.io', 56: 'https://bscscan.com', 100: 'https://gnosisscan.io', 8453: 'https://basescan.org' }
export function traceExplorerUrl(chainId: number, kind: 'tx' | 'address' | 'block', value: string): string | undefined {
  const valid = kind === 'tx' ? /^0x[\da-f]{64}$/i.test(value) : kind === 'address' ? /^0x[\da-f]{40}$/i.test(value) : /^\d+$/.test(value)
  return valid && explorers[chainId] ? `${explorers[chainId]}/${kind}/${value}` : undefined
}
