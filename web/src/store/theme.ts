import { create } from 'zustand';
import type { Scheme, ThemeMode } from '../lib/theme';
import { readStoredMode, writeStoredMode } from '../lib/theme';

export interface ThemeState {
  mode: ThemeMode;
  resolvedScheme: Scheme;
  setMode: (mode: ThemeMode) => void;
  applyResolvedScheme: (scheme: Scheme) => void;
}

export const useThemeStore = create<ThemeState>()((set) => ({
  mode: readStoredMode(),
  resolvedScheme: 'light',
  setMode: (mode) => {
    writeStoredMode(mode);
    set({ mode });
  },
  applyResolvedScheme: (resolvedScheme) => set({ resolvedScheme }),
}));

/** Test helper: reset to a known state. */
export function themeStoreReset() {
  useThemeStore.setState({ mode: 'system', resolvedScheme: 'light' });
}