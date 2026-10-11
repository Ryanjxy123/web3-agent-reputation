import { afterEach, describe, expect, it, vi } from 'vitest';
import { optionalJson, pollEvaluation, requestAllPages, requestJson, updateIfCurrent, type AgentPage, type EvaluationRun } from '../src/api/client';

afterEach(() => vi.unstubAllGlobals());

describe('API client', () => {
  it('sends JSON and keeps bearer credentials in the request only', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response('{"id":"run-1"}'));
    vi.stubGlobal('fetch', fetcher);
    await expect(requestJson<{ id: string }>('/api/v1/evaluations', {
      method: 'POST', token: 'secret', body: { enabled: true },
    })).resolves.toEqual({ id: 'run-1' });
    expect(fetcher.mock.calls[0][1]).toMatchObject({
      method: 'POST', body: '{"enabled":true}',
    });
    expect((fetcher.mock.calls[0][1] as RequestInit).headers).toBeInstanceOf(Headers);
    expect(((fetcher.mock.calls[0][1] as RequestInit).headers as Headers).get('Authorization')).toBe('Bearer secret');
    vi.unstubAllGlobals();
  });

  it('preserves structured backend error details', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
      '{"error":{"code":"AUTH_REQUIRED","message":"Operator authentication required."}}',
      { status: 401 },
    )));
    await expect(requestJson('/api/v1/agents')).rejects.toMatchObject({
      status: 401,
      message: 'Operator authentication required.',
    });
    vi.unstubAllGlobals();
  });

  it('only treats 404 as absent data, preserving network and server failures', async () => {
    const fetcher = vi.fn().mockResolvedValueOnce(new Response('{}', { status: 404 }))
      .mockResolvedValueOnce(new Response('{}', { status: 500 }))
      .mockRejectedValueOnce(new Error('network unavailable'));
    vi.stubGlobal('fetch', fetcher);
    await expect(optionalJson('/optional')).resolves.toBeNull();
    await expect(optionalJson('/optional')).rejects.toMatchObject({ status: 500 });
    await expect(optionalJson('/optional')).rejects.toThrow('network unavailable');
  });

  it('polls at the specified interval and stops on PARTIAL without converting UNKNOWN to failure', async () => {
    const run = (status: EvaluationRun['status']): EvaluationRun => ({ run_id: 'run', status, stage: 'DONE', planned: 5, settled: 5, unknown: 1, latest_report_id: null, cancel_requested: false });
    const fetcher = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify(run('RUNNING'))))
      .mockResolvedValueOnce(new Response(JSON.stringify(run('PARTIAL'))));
    const wait = vi.fn().mockResolvedValue(undefined);
    const updated = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal('fetch', fetcher);
    await expect(pollEvaluation('run', { wait, onUpdate: updated })).resolves.toMatchObject({ status: 'PARTIAL', unknown: 1 });
    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(wait).toHaveBeenCalledExactlyOnceWith(2000);
    expect(updated).toHaveBeenCalledTimes(2);
  });

  it('does not wait or fetch again for any terminal state', async () => {
    for (const status of ['COMPLETED', 'FAILED', 'CANCELLED'] as const) {
      const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ status })));
      const wait = vi.fn();
      vi.stubGlobal('fetch', fetcher);
      await pollEvaluation('run', { wait });
      expect(fetcher).toHaveBeenCalledTimes(1);
      expect(wait).not.toHaveBeenCalled();
    }
  });

  it('reuses the operator supplied idempotency key for retrying a start request', async () => {
    const fetcher = vi.fn().mockImplementation(async () => new Response('{}'));
    vi.stubGlobal('fetch', fetcher);
    await requestJson('/api/v1/evaluations', { method: 'POST', body: {}, idempotencyKey: 'same-operation' });
    await requestJson('/api/v1/evaluations', { method: 'POST', body: {}, idempotencyKey: 'same-operation' });
    for (const call of fetcher.mock.calls) {
      expect((call[1].headers as Headers).get('Idempotency-Key')).toBe('same-operation');
    }
  });

  it('keeps an old report anchor or evidence response from overwriting a newer selection', async () => {
    let resolveOld: (value: string) => void = () => undefined;
    const old = new Promise<string>(resolve => { resolveOld = resolve; });
    let selected = 'old-report';
    let displayed = '';
    const pending = updateIfCurrent(old, () => selected === 'old-report', value => { displayed = value; });
    selected = 'new-report';
    await updateIfCurrent(Promise.resolve('new-evidence'), () => selected === 'new-report', value => { displayed = value; });
    resolveOld('old-evidence');
    await pending;
    expect(displayed).toBe('new-evidence');
  });

  it('preserves errors for the current selection and ignores stale request failures', async () => {
    await expect(updateIfCurrent(Promise.reject(new Error('network')), () => true, () => undefined)).rejects.toThrow('network');
    await expect(updateIfCurrent(Promise.reject(new Error('old network')), () => false, () => undefined)).resolves.toBeUndefined();
  });

  it('uses generated paginated list contracts and sends the returned cursor', async () => {
    const fetcher = vi.fn().mockResolvedValueOnce(new Response('{"items":[],"next_cursor":"next page"}'))
      .mockResolvedValueOnce(new Response('{"items":[],"next_cursor":null}'));
    vi.stubGlobal('fetch', fetcher);
    await expect(requestAllPages<AgentPage>('/api/v1/agents')).resolves.toEqual([]);
    expect(fetcher.mock.calls.map(call => call[0])).toEqual(['/api/v1/agents?limit=100', '/api/v1/agents?limit=100&cursor=next%20page']);
  });

  it('rejects repeated pagination cursors instead of hanging the loading state', async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation(async () => new Response('{"items":[],"next_cursor":"same"}')));
    await expect(requestAllPages<AgentPage>('/api/v1/agents')).rejects.toThrow('游标重复');
  });
});
