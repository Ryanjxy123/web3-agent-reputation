export type Connection = 'checking' | 'connected' | 'unavailable';

export async function checkConnection(request: typeof fetch = fetch): Promise<Connection> {
  try {
    const response = await request('/health/live', { signal: AbortSignal.timeout(5000) });
    if (!response.ok) return 'unavailable';
    const body: unknown = await response.json();
    return typeof body === 'object' && body !== null && 'status' in body && body.status === 'ok'
      ? 'connected' : 'unavailable';
  } catch {
    return 'unavailable';
  }
}
