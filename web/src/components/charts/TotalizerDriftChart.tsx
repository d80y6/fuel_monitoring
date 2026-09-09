import ReactECharts from 'echarts-for-react';
import type { DriftSample } from '../../lib/driftCalc';
import { roundAxisExtent } from '../../lib/chartOptions';

export function TotalizerDriftChart({ series }: { series: DriftSample[] }) {
  const labels = series.map((s) => new Date(s.ts).toLocaleString());
  const maxAbs = Math.max(1, ...series.map((s) => Math.abs(s.drift)));
  const axisMax = roundAxisExtent(maxAbs);

  const option = {
    title: { text: 'Drift = totalizer cumulative − authorized cumulative' },
    tooltip: { trigger: 'axis' },
    grid: { left: 64, right: 32, top: 48, bottom: 48 },
    xAxis: { type: 'category', data: labels },
    yAxis: { type: 'value', name: 'Drift (L)', min: -axisMax, max: axisMax },
    series: [
      {
        name: 'Drift',
        type: 'bar',
        data: series.map((s) => Number(s.drift.toFixed(3))),
        itemStyle: {
          color: (p: { value: number }) => (p.value >= 0 ? '#f59e0b' : '#3b82f6'),
        },
      },
    ],
  };

  return <ReactECharts option={option} notMerge style={{ height: 300, width: '100%' }} />;
}
