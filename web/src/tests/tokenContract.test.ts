// @ts-expect-error Node built-in available at runtime via vitest/node
import { readFileSync } from 'node:fs';
// @ts-expect-error Node built-in available at runtime via vitest/node
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

declare var __dirname: string;

const css = readFileSync(resolve(__dirname, '../index.css'), 'utf8');

const TOKENS: Record<string, string> = {
  canvas: '--color-canvas',
  surface: '--color-surface',
  'surface-raised': '--color-surface-raised',
  inset: '--color-inset',
  primary: '--color-text-primary',
  secondary: '--color-text-secondary',
  muted: '--color-text-muted',
  line: '--color-line',
  'line-strong': '--color-line-strong',
  brand: '--color-brand',
  'brand-dark': '--color-brand-dark',
  ok: '--color-ok-bg',
  'ok-fg': '--color-ok-text',
  warn: '--color-warn-bg',
  'warn-fg': '--color-warn-text',
  danger: '--color-danger-bg',
  'danger-fg': '--color-danger-text',
  info: '--color-info-bg',
  'info-fg': '--color-info-text',
};

describe('theme token contract', () => {
  it('defines every CSS variable in both :root and .dark blocks', () => {
    const root = css.split('.dark')[0] ?? '';
    const dark = css.split('.dark')[1] ?? '';
    for (const v of Object.values(TOKENS)) {
      expect(root, `${v} missing in :root`).toContain(`${v}:`);
      expect(dark, `${v} missing in .dark`).toContain(`${v}:`);
    }
  });

  it('sets darkMode and maps every short token to its var in tailwind config', () => {
    const config = readFileSync(resolve(__dirname, '../../tailwind.config.js'), 'utf8');
    expect(config).toMatch(/darkMode:\s*'class'/);
    for (const [key, v] of Object.entries(TOKENS)) {
      expect(config).toContain(`'${key}': 'var(${v})'`);
    }
  });
});