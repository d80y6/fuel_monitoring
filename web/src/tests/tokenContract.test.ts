// @ts-expect-error Node built-in available at runtime via vitest/node
import { readFileSync } from 'node:fs';
// @ts-expect-error Node built-in available at runtime via vitest/node
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

declare var __dirname: string;

const css = readFileSync(resolve(__dirname, '../index.css'), 'utf8');

const REQUIRED: Record<string, string> = {
  '--color-canvas': '',
  '--color-surface': '',
  '--color-surface-raised': '',
  '--color-inset': '',
  '--color-text-primary': '',
  '--color-text-secondary': '',
  '--color-text-muted': '',
  '--color-line': '',
  '--color-line-strong': '',
  '--color-brand': '',
  '--color-brand-dark': '',
  '--color-ok-bg': '', '--color-ok-text': '',
  '--color-warn-bg': '', '--color-warn-text': '',
  '--color-danger-bg': '', '--color-danger-text': '',
  '--color-info-bg': '', '--color-info-text': '',
};

describe('theme token contract', () => {
  it('defines every token in both :root and .dark blocks', () => {
    const root = css.split('.dark')[0] ?? '';
    const dark = css.split('.dark')[1] ?? '';
    for (const name of Object.keys(REQUIRED)) {
      expect(root, `${name} missing in :root`).toContain(`${name}:`);
      expect(dark, `${name} missing in .dark`).toContain(`${name}:`);
    }
  });

  it('sets darkMode and maps tokens in tailwind config', () => {
    const config = readFileSync(resolve(__dirname, '../../tailwind.config.js'), 'utf8');
    expect(config).toMatch(/darkMode:\s*'class'/);
    for (const name of Object.keys(REQUIRED)) {
      expect(config).toContain(`'${name}': 'var(${name})'`);
    }
  });
});
