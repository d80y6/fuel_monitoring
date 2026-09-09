import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';
import type { UserRead } from '../lib/apiTypes';
import { api } from '../api/client';
import { ApiError, setOnUnauthorized, setTokenProvider } from '../api/http';

export interface AuthState {
  token: string | null;
  user: UserRead | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  boot: () => Promise<void>;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      token: null,
      user: null,
      login: async (username, password) => {
        const res = await api.login(username, password);
        set({ token: res.access_token, user: res.user });
      },
      logout: () => set({ token: null, user: null }),
      boot: async () => {
        if (!get().token) return;
        try {
          const me = await api.me();
          set({ user: me });
        } catch (err) {
          if (err instanceof ApiError && err.status === 401) get().logout();
        }
      },
    }),
    { name: 'fuel.auth', storage: createJSONStorage(() => localStorage) }
  )
);

setTokenProvider(() => useAuthStore.getState().token);
setOnUnauthorized(() => useAuthStore.getState().logout());