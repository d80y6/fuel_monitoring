import { describe, expect, it } from 'vitest';
import { chartThemeName } from '../lib/chartTheme';

describe('chartThemeName', () => {
  it('maps schemes to registered theme names', () => {
    expect(chartThemeName('light')).toBe('fmp-light');
    expect(chartThemeName('dark')).toBe('fmp-dark');
  });
});