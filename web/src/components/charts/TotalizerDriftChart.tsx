import ReactECharts from 'echarts-for-react';
import type { DriftSample } from '../../lib/driftCalc';
import { roundAxisExtent } from '../../lib/chartOptions';
import { chartColors } from '../../lib/chartColors';
import { chartThemeName } from '../../lib/chartTheme';
import { useTheme } from '../../hooks/useTheme';

export function TotalizerDriftChart({ series }: { series: DriftSample[] }) {
  const { resolvedScheme } = useTheme();
  const c = chartColors[resolvedScheme];
  const labels = series.map((s) => new Date(s.ts).toLocaleString());
  const maxAbs = Math.max(1, ...series.map((s) => Math.abs(s.drift)));
  const axisMax = roundAxisExtent(maxAbs);

  const option = {
    title: {
      text: 'Drift = totalizer cumulative − authorized cumulative',
      textStyle: { color: c.text },
    },
    tooltip: { trigger: 'axis', backgroundColor: c.tooltipBg, borderColor: c.tooltipBorder, textStyle: { color: c.text } },
    grid: { left: 64, right: 32, top: 48, bottom: 48 },
    xAxis: {
      type: 'category' as const,
      data: labels,
      axisLine: { lineStyle: { color: c.axisLine } },
      axisLabel: { color: c.muted },
    },
    yAxis: {
      type: 'value' as const,
      name: 'Drift (L)',
      min: -axisMax,
      max: axisMax,
      axisLabel: { color: c.muted },
      splitLine: { lineStyle: { color: c.splitLine } },
    },
    series: [
      {
        name: 'Drift',
        type: 'bar' as const,
        data: series.map((s) => Number(s.drift.toFixed(3))),
        itemStyle: {
          color: (p: { value: number }) => (p.value >= 0 ? c.legend : c.axisLine),
        },
      },
    ],
  };

  return (
    <ReactECharts
      option={option}
      theme={chartThemeName(resolvedScheme)}
      notMerge
      style={{ height: 300, width: '100%' }}
    />
  );
}