import { describe, expect, it } from 'vitest';
import { resolveScheme, readStoredMode, writeStoredMode, THEME_STORAGE_KEY } from '../lib/theme';

const memory = (init: Record<string, string> = {}) => {
  const m = new Map(Object.entries(init));
  return { getItem: (k: string) => (m.has(k) ? m.get(k) ?? null : null), setItem: (k: string, v: string) => { m.set(k, v); } };
};

describe('resolveScheme', () => {
  it('returns the explicit mode regardless of system preference', () => {
    expect(resolveScheme('light', true)).toBe('light');
    expect(resolveScheme('dark', false)).toBe('dark');
  });
  it('follows system when mode is system', () => {
    expect(resolveScheme('system', true)).toBe('dark');
    expect(resolveScheme('system', false)).toBe('light');
  });
});

describe('stored theme mode', () => {
  it('defaults to system when nothing stored', () => {
    expect(readStoredMode(memory())).toBe('system');
  });
  it('reads a stored mode', () => {
    expect(readStoredMode(memory({ [THEME_STORAGE_KEY]: 'dark' }))).toBe('dark');
  });
  it('falls back to system for garbage values', () => {
    expect(readStoredMode(memory({ [THEME_STORAGE_KEY]: 'neon' }))).toBe('system');
  });
  it('writes a mode', () => {
    const s = memory();
    writeStoredMode('light', s);
    expect(readStoredMode(s)).toBe('light');
  });
  it('does not throw when storage is unavailable', () => {
    const broken = { setItem: () => { throw new Error('denied'); }, getItem: () => { throw new Error('denied'); } };
    expect(() => writeStoredMode('dark', broken)).not.toThrow();
    expect(readStoredMode(broken)).toBe('system');
  });
});
