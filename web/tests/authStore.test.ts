import { beforeEach, describe, expect, it, vi } from 'vitest';
import { isAuthed } from '../src/lib/authGuard';
import { setOnUnauthorized, setTokenProvider } from '../src/api/http';
import { useAuthStore } from '../src/store/auth';

const loginResponse = {
  access_token: 'jwt.1',
  token_type: 'bearer',
  user: { id: 'u1', username: 'alice', email: 'a@x.com', role: 'admin', is_active: true },
};

describe('authGuard', () => {
  it('treats only non-empty tokens as authenticated', () => {
    expect(isAuthed('abc.def')).toBe(true);
    expect(isAuthed('')).toBe(false);
    expect(isAuthed(null)).toBe(false);
  });
});

describe('auth store', () => {
  beforeEach(() => {
    localStorage.clear();
    setTokenProvider(() => useAuthStore.getState().token);
    setOnUnauthorized(() => useAuthStore.getState().logout());
  });

  it('login stores token + user and persists to localStorage', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(loginResponse), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      )
    );
    await useAuthStore.getState().login('alice', 'pw');
    expect(useAuthStore.getState().token).toBe('jwt.1');
    expect(useAuthStore.getState().user?.username).toBe('alice');
    expect(localStorage.getItem('fuel.auth')).toContain('jwt.1');
    vi.unstubAllGlobals();
  });

  it('logout clears the session', () => {
    useAuthStore.getState().login = async () => {};
    useAuthStore.setState({ token: 'jwt.1', user: loginResponse.user as never });
    useAuthStore.getState().logout();
    expect(useAuthStore.getState().token).toBeNull();
    expect(useAuthStore.getState().user).toBeNull();
  });

  it('boot calls /me with the token; a 401 clears the session', async () => {
    useAuthStore.setState({ token: 'stale.jwt' });
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: 'expired' }), { status: 401 }))
    );
    await useAuthStore.getState().boot();
    expect(useAuthStore.getState().token).toBeNull();
    vi.unstubAllGlobals();
  });
});