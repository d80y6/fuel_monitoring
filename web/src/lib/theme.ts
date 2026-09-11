export type ThemeMode = 'light' | 'dark' | 'system';
export type Scheme = 'light' | 'dark';

export const THEME_STORAGE_KEY = 'fmp-theme';

export function resolveScheme(mode: ThemeMode, systemPrefersDark: boolean): Scheme {
  if (mode === 'system') return systemPrefersDark ? 'dark' : 'light';
  return mode;
}

export function readStoredMode(storage: Pick<Storage, 'getItem'> = localStorage): ThemeMode {
  try {
    const v = storage.getItem(THEME_STORAGE_KEY);
    return v === 'light' || v === 'dark' || v === 'system' ? v : 'system';
  } catch {
    return 'system';
  }
}

export function writeStoredMode(mode: ThemeMode, storage: Pick<Storage, 'setItem'> = localStorage): void {
  try {
    storage.setItem(THEME_STORAGE_KEY, mode);
  } catch {
    /* storage unavailable — ignore */
  }
}