import ReactECharts from 'echarts-for-react';
import type { TelemetryPoint } from '../../lib/apiTypes';
import type { LiveReading } from '../../store/telemetry';
import { buildChartOption } from '../../lib/chartOptions';

interface TelemetryChartProps {
  points: TelemetryPoint[];
  live?: LiveReading;
  tankTitle: string;
  lowVolume?: number | null;
  highVolume?: number | null;
}

export function TelemetryChart({ points, live, tankTitle, lowVolume, highVolume }: TelemetryChartProps) {
  const option = buildChartOption(points, live, tankTitle, lowVolume, highVolume);
  return (
    <ReactECharts
      option={option}
      notMerge
      style={{ height: 360, width: '100%' }}
      opts={{ renderer: 'canvas' }}
    />
  );
}
