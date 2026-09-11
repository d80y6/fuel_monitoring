import { describe, expect, it } from 'vitest';
import { buildChartOption } from '../lib/chartOptions';
import type { TelemetryPoint } from '../lib/apiTypes';

const p = (timestamp: string, extra: Partial<TelemetryPoint> = {}): TelemetryPoint =>
  ({ timestamp, gov_volume: 400, net_volume: 380, temperature: 24, density_at_temperature: 840, ...extra }) as TelemetryPoint;

describe('buildChartOption', () => {
  it('colors the threshold mark area per scheme', () => {
    const light = buildChartOption([p('2026-09-11T00:00:00Z')], undefined, 'T1', 100, 500, 'light');
    const dark = buildChartOption([p('2026-09-11T00:00:00Z')], undefined, 'T1', 100, 500, 'dark');
    const lightArea = (light.series as any)[0].markArea.itemStyle.color;
    const darkArea = (dark.series as any)[0].markArea.itemStyle.color;
    expect(lightArea).not.toBe(darkArea);
  });

  it('sets tooltip background from the scheme', () => {
    const dark = buildChartOption([], undefined, 'T1', undefined, undefined, 'dark');
    expect((dark.tooltip as any).backgroundColor).toBe('rgba(15,23,42,0.95)');
  });

  it('defaults to light scheme when omitted', () => {
    const opt = buildChartOption([], undefined, 'T1');
    expect((opt.tooltip as any).backgroundColor).toBe('rgba(255,255,255,0.95)');
  });
});