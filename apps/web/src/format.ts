import type { CheckCode, EvaluationJob, Verdict } from './contracts'

export function score(value: number | null | undefined): string {
  return value == null ? '待评价' : value.toFixed(2)
}

export function scoreRange(lower: number | null | undefined, upper: number | null | undefined): string {
  if (lower == null || upper == null) return '证据不足'
  return lower === upper ? score(lower) : `${score(lower)}–${score(upper)}`
}

export function when(value: string | null | undefined): string {
  if (!value) return '具体时刻未记录'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
  }).format(date) + ' CST'
}

export const verdictLabel: Record<Verdict, string> = {
  PASS: '通过', FAIL: '未通过', UNKNOWN: '无法判断', NOT_APPLICABLE: '不适用',
}

export const checkLabel: Record<CheckCode, string> = {
  registration: '公开注册身份', functional_declaration: '具体功能声明', service_interface: '业务接口',
  independent_oracle: '独立核验依据', execution_binding: '执行身份关联', execution_history: '可归属交易历史',
}

export const jobLabel: Record<EvaluationJob['status'], string> = {
  QUEUED: '正在排队', RUNNING: '正在评价', COMPLETE: '评价完成', NEEDS_INFO: '需要补充资料',
  UNSUPPORTED: '暂未支持这类评价', FAILED: '本次评价未完成',
}

export const stageLabel: Record<EvaluationJob['stage'], string> = {
  QUEUED: '等待处理', COLLECTING: '收集资料', VERIFYING: '独立核验', REPORTING: '生成报告', DONE: '处理结束',
}

export function externalLink(value: string): string | undefined {
  if (/[\u0000-\u001f\u007f]/.test(value)) return undefined
  try {
    const url = new URL(value)
    return url.protocol === 'https:' && !url.username && !url.password ? url.href : undefined
  } catch { return undefined }
}
