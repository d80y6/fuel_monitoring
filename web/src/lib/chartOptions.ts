import type { TelemetryPoint } from './apiTypes';
import type { LiveReading } from '../store/telemetry';

export function toEpochMs(t: string): number {
  if (t.includes('T')) return Date.parse(t);
  return Number(t);
}

/** Insert null markers where consecutive samples exceed maxGapMinutes. */
export function gapFill(points: TelemetryPoint[], maxGapMinutes = 15): (TelemetryPoint | null)[] {
  const out: (TelemetryPoint | null)[] = [];
  for (let i = 0; i < points.length; i++) {
    if (i > 0) {
      const prev = toEpochMs(points[i - 1].timestamp);
      const cur = toEpochMs(points[i].timestamp);
      const gapMin = (cur - prev) / 60_000;
      if (gapMin > maxGapMinutes) out.push(null);
    }
    out.push(points[i]);
  }
  return out;
}

/** Round up to a nice 1/2/5×10^k axis maximum. */
export function roundAxisExtent(max: number): number {
  const m = Math.max(1, max);
  const mag = 10 ** Math.floor(Math.log10(m));
  const norm = m / mag;
  const nice = norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 4 ? 4 : norm <= 7 ? 7 : 10;
  return nice * mag;
}

/** Append live point; replace the trailing bucket when timestamps collide. */
export function mergeLivePoints(range: TelemetryPoint[], live: TelemetryPoint): TelemetryPoint[] {
  const list = [...range];
  if (list.length === 0) return [live];
  const last = list[list.length - 1];
  if (toEpochMs(last.timestamp) >= toEpochMs(live.timestamp)) {
    list[list.length - 1] = live;
    return list;
  }
  return [...list, live];
}

export interface ChartOption {
  title: { text: string };
  tooltip: { trigger: string };
  legend: { data: string[] };
  grid: { left: number; right: number; top: number; bottom: number };
  dataZoom: unknown[];
  xAxis: { type: string; data: string[] };
  yAxis: Array<{ type: string; name: string; min: number; max?: number }>;
  series: Array<Record<string, unknown>>;
}

export function buildChartOption(
  range: TelemetryPoint[],
  live: LiveReading | undefined,
  tankTitle: string,
  lowVolume?: number | null,
  highVolume?: number | null
): ChartOption {
  const merged = live ? mergeLivePoints(range, live) : range;
  const filled = gapFill(merged, 15);
  const xs = filled.map((p) => (p === null ? '' : new Date(p.timestamp).toLocaleTimeString()));

  const volMax = roundAxisExtent(
    Math.max(1, ...filled.flatMap((p) => (p === null ? [] : [p.gov_volume ?? 0, p.net_volume ?? 0])))
  );
  const tempMax = roundAxisExtent(
    Math.max(1, ...filled.flatMap((p) => (p === null ? [] : [p.temperature ?? 0, p.density_at_temperature ?? 0])))
  );

  const markArea =
    lowVolume != null || highVolume != null
      ? [
          {
            name: 'thresholds',
            itemStyle: { color: 'rgba(248,113,113,0.12)' },
            data: [[{ yAxis: lowVolume ?? 0 }, { yAxis: highVolume ?? volMax }]],
          },
        ]
      : undefined;

  const series: Array<Record<string, unknown>> = [
    {
      name: 'GOV',
      type: 'line',
      smooth: true,
      showSymbol: false,
      yAxisIndex: 0,
      data: filled.map((p) => (p === null ? null : p.gov_volume ?? p.volume)),
    },
    {
      name: 'NSV',
      type: 'line',
      smooth: true,
      showSymbol: false,
      yAxisIndex: 0,
      data: filled.map((p) => (p === null ? null : p.net_volume)),
    },
    {
      name: 'Temperature',
      type: 'line',
      smooth: true,
      showSymbol: false,
      yAxisIndex: 1,
      data: filled.map((p) => (p === null ? null : p.temperature)),
    },
    {
      name: 'Density',
      type: 'line',
      smooth: true,
      showSymbol: false,
      yAxisIndex: 1,
      data: filled.map((p) => (p === null ? null : p.density_at_temperature)),
    },
  ];
  if (markArea) series[0] = { ...series[0], markArea };

  return {
    title: { text: tankTitle },
    tooltip: { trigger: 'axis' },
    legend: { data: ['GOV', 'NSV', 'Temperature', 'Density'] },
    grid: { left: 56, right: 56, top: 40, bottom: 56 },
    dataZoom: [{ type: 'inside' }, { type: 'slider', height: 18, bottom: 12 }],
    xAxis: { type: 'category', data: xs },
    yAxis: [
      { type: 'value', name: 'Volume (L)', min: 0, max: volMax },
      { type: 'value', name: 'Temp / Density', min: 0, max: tempMax },
    ],
    series,
  };
}
