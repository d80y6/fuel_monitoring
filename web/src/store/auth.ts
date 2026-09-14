import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';
import type { UserRead } from '../lib/apiTypes';
import { api } from '../api/client';
import { ApiError, setOnUnauthorized, setRefreshSession, setTokenProvider } from '../api/http';

export interface AuthState {
  token: string | null;
  refreshToken: string | null;
  user: UserRead | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  boot: () => Promise<void>;
  refreshSession: () => Promise<boolean>;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      token: null,
      refreshToken: null,
      user: null,
      login: async (username, password) => {
        const res = await api.login(username, password);
        set({ token: res.access_token, refreshToken: res.refresh_token, user: res.user });
      },
      logout: () => {
        const { token, refreshToken } = get();
        set({ token: null, refreshToken: null, user: null });
        if (token) {
          void api.logout(token, refreshToken);
        }
      },
      boot: async () => {
        if (!get().token) return;
        try {
          const me = await api.me();
          set({ user: me });
        } catch (err) {
          if (err instanceof ApiError && err.status === 401) get().logout();
        }
      },
      refreshSession: () => {
        const refreshToken = get().refreshToken;
        if (!refreshToken) return Promise.resolve(false);
        if (!refreshFlight) {
          refreshFlight = (async () => {
            try {
              const res = await api.refresh(refreshToken);
              set({
                token: res.access_token,
                refreshToken: res.refresh_token,
                user: res.user,
              });
              return true;
            } catch {
              get().logout();
              return false;
            }
          })();
          void refreshFlight.finally(() => {
            refreshFlight = null;
          });
        }
        return refreshFlight;
      },
    }),
    { name: 'fuel.auth', storage: createJSONStorage(() => localStorage) }
  )
);

// Single-flight guard: rotation is single-use, so concurrent 401s must share
// one refresh instead of each trying (and failing) to rotate the same token.
let refreshFlight: Promise<boolean> | null = null;

setTokenProvider(() => useAuthStore.getState().token);
setRefreshSession(() => useAuthStore.getState().refreshSession());
setOnUnauthorized(() => useAuthStore.getState().logout());