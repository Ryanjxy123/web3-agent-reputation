import type { AgentChainEvidence, AgentDetail, AgentSummary, EvaluationJob, EvaluationReport, EvaluationSubmission, ReportChainEvidence } from './contracts'

export class ApiError extends Error {
  constructor(message: string, public detail: string) { super(message) }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  let response: Response
  try {
    response = await fetch('/api' + path, { ...options, headers: { Accept: 'application/json', ...options.headers } })
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') throw error
    throw new ApiError('暂时无法连接评价服务，请稍后再试。', String(error))
  }
  if (!response.ok) {
    const detail = await response.text()
    const message = response.status === 404 ? '没有找到这条记录，可能需要返回目录重新选择。'
      : response.status === 422 ? '提交内容暂时无法识别，请检查完整注册标识或链接。'
      : response.status >= 500 ? '评价服务暂时无法完成请求，请稍后再试。' : '这次请求暂时无法处理，请检查输入后重试。'
    throw new ApiError(message, `HTTP ${response.status}\n${detail}`)
  }
  try { return await response.json() as T }
  catch (error) { throw new ApiError('服务返回的内容暂时无法读取，请稍后再试。', String(error)) }
}

export const getAgents = () => request<AgentSummary[]>('/agents')
export type RuntimeStatus = {
  api: 'ok'; database: 'ready' | 'unavailable'; queued: number | null; running: number | null
  worker: { state: 'public-off' | 'scoped' | 'online' | 'stopped' | 'unavailable'; last_seen_at: string | null; scope_reference: string | null }
  observed_at: string
}
export const getRuntimeStatus = () => request<RuntimeStatus>('/runtime')
export const getAgent = (key: string, signal?: AbortSignal) => request<AgentDetail>('/agents/' + encodeURIComponent(key), { signal })
export const getReport = (id: string, signal?: AbortSignal) => request<EvaluationReport>('/reports/' + encodeURIComponent(id), { signal })
export const getReportChainEvidence = (id: string, signal?: AbortSignal, taskKey?: string) => request<ReportChainEvidence>('/reports/' + encodeURIComponent(id) + '/chain-evidence' + (taskKey ? '?task_key=' + encodeURIComponent(taskKey) : ''), { signal })
export const getAgentChainEvidence = (key: string, signal?: AbortSignal) => request<AgentChainEvidence | null>('/agents/' + encodeURIComponent(key) + '/chain-evidence', { signal })
export const getJob = (id: string, signal?: AbortSignal) => request<EvaluationJob>('/jobs/' + encodeURIComponent(id), { signal })
export const submitEvaluation = (submission: EvaluationSubmission) => request<EvaluationJob>('/evaluations', {
  method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(submission),
})

export function asApiError(error: unknown): ApiError {
  return error instanceof ApiError ? error : new ApiError('暂时无法完成操作，请稍后再试。', String(error))
}
