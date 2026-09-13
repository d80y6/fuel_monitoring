import { useMemo } from 'react';
import ReactECharts from 'echarts-for-react';
import type { TelemetryPoint } from '../../lib/apiTypes';
import type { LiveReading } from '../../store/telemetry';
import { buildChartOption } from '../../lib/chartOptions';
import { chartThemeName } from '../../lib/chartTheme';
import { useTheme } from '../../hooks/useTheme';

interface TelemetryChartProps {
  points: TelemetryPoint[];
  live?: LiveReading;
  tankTitle: string;
  lowVolume?: number | null;
  highVolume?: number | null;
}

export function TelemetryChart({ points, live, tankTitle, lowVolume, highVolume }: TelemetryChartProps) {
  const { resolvedScheme } = useTheme();
  const option = useMemo(
    () => buildChartOption(points, live, tankTitle, lowVolume, highVolume, resolvedScheme),
    [points, live, tankTitle, lowVolume, highVolume, resolvedScheme]
  );
  return (
    <ReactECharts
      option={option}
      theme={chartThemeName(resolvedScheme)}
      notMerge
      style={{ height: 360, width: '100%' }}
      opts={{ renderer: 'canvas' }}
    />
  );
}
