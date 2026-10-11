import type { components } from './generated/schema';

export type AgentView = components['schemas']['AgentView'];
export type AgentSnapshot = components['schemas']['AgentSnapshot'];
export type EvaluationCreate = components['schemas']['EvaluationCreate'];
export type PublicReadonlyEvaluationCreate = components['schemas']['PublicReadonlyEvaluationCreate'];
export type EvaluationRun = components['schemas']['EvaluationRun'];
export type ReportView = components['schemas']['ReportView'];
export type Observation = components['schemas']['Observation'];
export type RunPlan = components['schemas']['RunPlan'] | components['schemas']['PublicReadonlyRunPlan'];
export type RecordVerificationResult = components['schemas']['RecordVerificationResult'];
export type ExecutorBinding = components['schemas']['ExecutorBinding'];
export type ReadonlyIdentityAssociation = components['schemas']['ReadonlyIdentityAssociation'];
export type AcceptedEvaluation = components['schemas']['AcceptedEvaluation'];
export type AcceptedJob = components['schemas']['AcceptedJob'];
export type AgentPage = components['schemas']['AgentPage'];
export type SnapshotPage = components['schemas']['SnapshotPage'];
export type ReportPage = components['schemas']['ReportPage'];

export class ApiError extends Error {
  constructor(message: string, readonly status: number, readonly details?: unknown) {
    super(message);
    this.name = 'ApiError';
  }
}

function errorMessage(body: unknown, status: number): string {
  if (typeof body === 'object' && body !== null && 'error' in body) {
    const error = (body as { error?: unknown }).error;
    if (typeof error === 'object' && error !== null && 'message' in error) {
      const message = (error as { message?: unknown }).message;
      if (typeof message === 'string') return message;
    }
  }
  return `请求失败（HTTP ${status}）`;
}

export async function requestJson<T>(
  path: string,
  options: { method?: string; body?: unknown; token?: string; signal?: AbortSignal; idempotencyKey?: string } = {},
): Promise<T> {
  const headers = new Headers({ Accept: 'application/json' });
  if (options.body !== undefined) headers.set('Content-Type', 'application/json');
  if (options.token) headers.set('Authorization', `Bearer ${options.token}`);
  if (options.idempotencyKey) headers.set('Idempotency-Key', options.idempotencyKey);
  const response = await fetch(path, {
    method: options.method ?? 'GET', headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
    signal: options.signal ? AbortSignal.any([options.signal, AbortSignal.timeout(15000)]) : AbortSignal.timeout(15000),
  });
  const text = await response.text();
  let body: unknown;
  if (text) {
    try { body = JSON.parse(text) as unknown; } catch { body = text; }
  }
  if (!response.ok) throw new ApiError(errorMessage(body, response.status), response.status, body);
  return body as T;
}

export async function optionalJson<T>(path: string): Promise<T | null> {
  try { return await requestJson<T>(path); }
  catch (error) { if (error instanceof ApiError && error.status === 404) return null; throw error; }
}

export async function requestAllPages<P extends AgentPage | SnapshotPage | ReportPage>(path: string): Promise<P['items']> {
  const items: P['items'][number][] = [];
  const cursors = new Set<string>();
  let cursor: string | null = null;
  do {
    const page: P = await requestJson<P>(`${path}${path.includes('?') ? '&' : '?'}limit=100${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ''}`);
    items.push(...page.items);
    cursor = page.next_cursor;
    if (cursor && cursors.has(cursor)) throw new Error('平台列表游标重复，请重新查询。');
    if (cursor) cursors.add(cursor);
  } while (cursor);
  return items as P['items'];
}

export async function updateIfCurrent<T>(request: Promise<T>, isCurrent: () => boolean, apply: (value: T) => void): Promise<void> {
  try {
    const value = await request;
    if (isCurrent()) apply(value);
  } catch (error) {
    if (isCurrent()) throw error;
  }
}

export const terminalStatuses = new Set<components['schemas']['RunStatus']>(['PARTIAL', 'COMPLETED', 'FAILED', 'CANCELLED']);

export async function pollEvaluation(
  runId: string,
  options: { intervalMs?: number; maxAttempts?: number; signal?: AbortSignal; wait?: (ms: number) => Promise<void>; onUpdate?: (run: EvaluationRun) => Promise<void> } = {},
): Promise<EvaluationRun> {
  const wait = options.wait ?? ((ms: number) => new Promise<void>(resolve => setTimeout(resolve, ms)));
  const maxAttempts = options.maxAttempts ?? Infinity;
  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    const run = await requestJson<EvaluationRun>(`/api/v1/evaluations/${encodeURIComponent(runId)}`, { signal: options.signal });
    await options.onUpdate?.(run);
    if (terminalStatuses.has(run.status) || attempt === maxAttempts - 1) return run;
    await wait(options.intervalMs ?? 2000);
  }
  throw new Error('评价轮询未返回最终状态。');
}

export async function downloadBundle(reportId: string): Promise<Blob> {
  const response = await fetch(`/api/v1/reports/${encodeURIComponent(reportId)}/bundle`, { headers: { Accept: 'application/zip' }, signal: AbortSignal.timeout(30000) });
  if (!response.ok) throw new ApiError(`证据包下载失败（HTTP ${response.status}）`, response.status);
  return response.blob();
}
