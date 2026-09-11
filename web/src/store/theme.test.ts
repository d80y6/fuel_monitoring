import { describe, expect, it, beforeEach } from 'vitest';
import { useThemeStore, themeStoreReset } from './theme';

describe('useThemeStore', () => {
  beforeEach(() => themeStoreReset());
  it('starts with system mode', () => {
    expect(useThemeStore.getState().mode).toBe('system');
  });
  it('setMode updates the mode', () => {
    useThemeStore.getState().setMode('dark');
    expect(useThemeStore.getState().mode).toBe('dark');
  });
  it('applyResolvedScheme updates the resolved scheme', () => {
    useThemeStore.getState().applyResolvedScheme('dark');
    expect(useThemeStore.getState().resolvedScheme).toBe('dark');
  });
});
