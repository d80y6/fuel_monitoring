import { useQuery } from '@tanstack/react-query';
import ReactECharts from 'echarts-for-react';
import { api } from '../../api/client';
import { EmptyState } from '../ui/EmptyState';
import { chartColors } from '../../lib/chartColors';
import { chartThemeName } from '../../lib/chartTheme';
import { useTheme } from '../../hooks/useTheme';

interface ConsumptionCardProps {
  tankId: string;
  days?: number;
}

export default function ConsumptionCard({ tankId, days = 30 }: ConsumptionCardProps) {
  const { resolvedScheme } = useTheme();
  const c = chartColors[resolvedScheme];
  const q = useQuery({
    queryKey: ['consumption', tankId, days],
    queryFn: () => api.getConsumption(tankId, days),
  });

  if (q.isLoading) return <p className="text-sm text-secondary">Loading consumption…</p>;
  if (q.isError) return <p className="text-sm text-danger-fg">Failed to load consumption analytics.</p>;

  const data = q.data;
  if (!data || data.series.length === 0) {
    return (
      <EmptyState
        title="No consumption data"
        hint="Daily consumption will appear once the tank has readings."
      />
    );
  }

  const option = {
    tooltip: {
      trigger: 'axis' as const,
      backgroundColor: c.tooltipBg,
      borderColor: c.tooltipBorder,
      textStyle: { color: c.text },
    },
    grid: { left: 64, right: 24, top: 32, bottom: 40 },
    xAxis: {
      type: 'category' as const,
      data: data.series.map((p) => p.date),
      axisLine: { lineStyle: { color: c.axisLine } },
      axisLabel: { color: c.muted },
    },
    yAxis: {
      type: 'value' as const,
      name: 'Liters/day',
      axisLabel: { color: c.muted },
      splitLine: { lineStyle: { color: c.splitLine } },
    },
    series: [
      {
        name: 'Consumption',
        type: 'line' as const,
        smooth: true,
        data: data.series.map((p) => p.liters),
        lineStyle: { color: c.legend },
        itemStyle: { color: c.legend },
      },
    ],
  };

  return (
    <div>
      <h3 className="font-semibold text-primary mb-2">Consumption (last {data.days} days)</h3>
      <p className="text-xs text-secondary mb-2">
        {data.forecast.liters_per_day == null
          ? 'Forecast: —'
          : `Forecast: ${Math.round(data.forecast.liters_per_day).toLocaleString('en-US')} L/day`}
      </p>
      <ReactECharts
        option={option}
        theme={chartThemeName(resolvedScheme)}
        notMerge
        style={{ height: 260, width: '100%' }}
      />
    </div>
  );
}