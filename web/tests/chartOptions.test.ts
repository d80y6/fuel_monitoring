import { describe, expect, it } from 'vitest';
import {
  buildChartOption,
  gapFill,
  mergeLivePoints,
  roundAxisExtent,
  toEpochMs,
} from '../src/lib/chartOptions';
import type { TelemetryPoint } from '../src/lib/apiTypes';

const pt = (t: string, over: Partial<TelemetryPoint> = {}): TelemetryPoint => ({
  timestamp: t,
  pressure: null,
  temperature: null,
  level: null,
  volume: null,
  flow_rate: null,
  fill_percent: null,
  is_outlier: false,
  ...over,
});

describe('gapFill', () => {
  it('inserts nulls where consecutive points exceed the max gap', () => {
    const points = [pt('2026-01-01T00:00:00Z'), pt('2026-01-01T01:00:00Z')];
    const filled = gapFill(points, 15);
    expect(filled.length).toBeGreaterThan(2);
    expect(filled.every((p) => p === null || p.timestamp)).toBe(true);
  });

  it('returns the input unchanged for a tight series', () => {
    const points = [pt('2026-01-01T00:00:00Z'), pt('2026-01-01T00:05:00Z')];
    expect(gapFill(points, 15).length).toBe(2);
  });
});

describe('roundAxisExtent', () => {
  it('rounds up to a nice 1/2/5×10^k number', () => {
    expect(roundAxisExtent(6123)).toBe(7000);
    expect(roundAxisExtent(310)).toBe(400);
    expect(roundAxisExtent(99)).toBe(100);
    expect(roundAxisExtent(0)).toBe(1);
  });
});

describe('mergeLivePoints', () => {
  it('appends a live point newer than the last range point', () => {
    const range = [pt('2026-01-01T00:00:00Z', { volume: 100 }), pt('2026-01-01T00:05:00Z', { volume: 110 })];
    const live = pt('2026-01-01T00:06:00Z', { volume: 115 });
    const merged = mergeLivePoints(range, live);
    expect(merged.length).toBe(3);
    expect(merged[2].volume).toBe(115);
  });

  it('replaces a live point whose timestamp matches the last range bucket', () => {
    const range = [pt('2026-01-01T00:05:00Z', { volume: 110 })];
    const live = pt('2026-01-01T00:05:00Z', { volume: 111 });
    const merged = mergeLivePoints(range, live);
    expect(merged.length).toBe(1);
    expect(merged[0].volume).toBe(111);
  });
});

describe('buildChartOption', () => {
  it('produces dual-axis option with GOV/NSV on the left and temp/density on the right', () => {
    const points = [pt('2026-01-01T00:00:00Z', { gov_volume: 900, net_volume: 880, temperature: 30, density_at_temperature: 800 })];
    const opt = buildChartOption(points, undefined, 'Tank A');
    const series = opt.series as Array<{ name: string; yAxisIndex: number }>;
    const names = series.map((s) => s.name);
    expect(names).toContain('GOV');
    expect(names).toContain('NSV');
    const gov = series.find((s) => s.name === 'GOV')!;
    expect(gov.yAxisIndex).toBe(0);
    const temp = series.find((s) => s.name === 'Temperature');
    expect(temp?.yAxisIndex).toBe(1);
    expect(opt.title.text).toBe('Tank A');
  });
});

describe('toEpochMs', () => {
  it('parses ISO timestamps and trusts pre-epoch strings', () => {
    expect(toEpochMs('2026-01-02T03:04:05Z')).toBe(Date.parse('2026-01-02T03:04:05Z'));
    expect(toEpochMs('2026')).toBe(2026);
  });
});
