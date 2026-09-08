import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, request, setOnUnauthorized, setTokenProvider } from '../src/api/http';
import { api } from '../src/api/client';

const json = (data: unknown, init: ResponseInit = {}) =>
  new Response(JSON.stringify(data), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });

describe('request', () => {
  beforeEach(() => {
    setTokenProvider(() => 'tok123');
    setOnUnauthorized(() => {});
    vi.stubGlobal('fetch', vi.fn());
  });
  afterEach(() => vi.unstubAllGlobals());

  it('adds the Bearer token from the provider', async () => {
    vi.mocked(fetch).mockResolvedValue(json({ ok: true }));
    await request('/api/v1/health');
    const [, init] = vi.mocked(fetch).mock.calls[0];
    const authHeader = (init.headers as any).get?.('Authorization') ?? init.headers?.Authorization;
    expect(authHeader).toBe('Bearer tok123');
  });

  it('throws ApiError on 4xx', async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify({ detail: 'nope' }), { status: 400 }),
    );
    await expect(request('/api/v1/tanks')).rejects.toBeInstanceOf(ApiError);
  });

  it('fires onUnauthorized on a 401 response', async () => {
    const on401 = vi.fn();
    setOnUnauthorized(on401);
    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify({ detail: 'bad token' }), { status: 401 }),
    );
    await expect(request('/api/v1/tanks')).rejects.toBeInstanceOf(ApiError);
    expect(on401).toHaveBeenCalledOnce();
  });
});

describe('api client', () => {
  beforeEach(() => {
    setTokenProvider(() => null);
    vi.stubGlobal('fetch', vi.fn());
  });
  afterEach(() => vi.unstubAllGlobals());

  it('login posts credentials and returns the parsed login payload', async () => {
    const payload = { access_token: 'abc', token_type: 'bearer', user: { id: 'u1' } };
    vi.mocked(fetch).mockResolvedValue(json(payload));
    const out = await api.login('alice', 's3cret');
    expect(out.access_token).toBe('abc');
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe('/api/v1/auth/login');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body as string)).toEqual({ username: 'alice', password: 's3cret' });
  });

  it('listTanks GETs /api/v1/tanks', async () => {
    vi.mocked(fetch).mockResolvedValue(json([]));
    const tanks = await api.listTanks();
    expect(vi.mocked(fetch).mock.calls[0][0]).toBe('/api/v1/tanks');
    expect(Array.isArray(tanks)).toBe(true);
  });

  it('rangeReadings encodes query params', async () => {
    vi.mocked(fetch).mockResolvedValue(json([]));
    await api.rangeReadings('t1', '2026-01-01T00:00:00Z', '2026-01-01T01:00:00Z');
    const url = vi.mocked(fetch).mock.calls[0][0] as string;
    expect(url).toContain('start=2026-01-01T00');
    expect(url).toContain('end=2026-01-01T01');
    expect(url).toContain('bucket=5');
  });
});
