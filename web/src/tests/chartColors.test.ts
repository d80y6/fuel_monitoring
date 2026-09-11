import { describe, expect, it } from 'vitest';
import { chartColors } from '../lib/chartColors';
import { registerChartThemes } from '../lib/chartTheme';

describe('chartColors', () => {
  it('provides distinct light and dark schemes', () => {
    expect(chartColors.light.text).not.toBe(chartColors.dark.text);
    expect(chartColors.light.splitLine).not.toBe(chartColors.dark.splitLine);
    expect(chartColors.light.tooltipBg).not.toBe(chartColors.dark.tooltipBg);
  });
});

describe('registerChartThemes', () => {
  it('is idempotent', () => {
    expect(() => { registerChartThemes(); registerChartThemes(); }).not.toThrow();
  });
});