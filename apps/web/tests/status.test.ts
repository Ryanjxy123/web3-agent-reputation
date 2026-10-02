import { describe, expect, it, vi } from 'vitest';
import { checkConnection } from '../src/status';

describe('platform connection', () => {
  it('requires a real health payload, not merely HTTP 200', async () => {
    for (const body of [{}, { status: 'failed' }, null]) {
      expect(await checkConnection(vi.fn().mockResolvedValue(new Response(JSON.stringify(body))))).toBe('unavailable');
    }
    expect(await checkConnection(vi.fn().mockResolvedValue(new Response('{"status":"ok"}')))).toBe('connected');
  });
  it('handles errors without claiming an agent failure', async () => {
    expect(await checkConnection(vi.fn().mockRejectedValue(new Error('network')))).toBe('unavailable');
    expect(await checkConnection(vi.fn().mockResolvedValue(new Response('', { status: 503 })))).toBe('unavailable');
  });
});
