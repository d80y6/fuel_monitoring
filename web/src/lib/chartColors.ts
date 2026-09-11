import type { Scheme } from './theme';

export interface ChartColors {
  text: string;
  muted: string;
  axisLine: string;
  splitLine: string;
  legend: string;
  tooltipBg: string;
  tooltipBorder: string;
  threshArea: string;
}

export const chartColors: Record<Scheme, ChartColors> = {
  light: {
    text: '#1e293b',
    muted: '#94a3b8',
    axisLine: '#cbd5e1',
    splitLine: '#e2e8f0',
    legend: '#334155',
    tooltipBg: 'rgba(255,255,255,0.95)',
    tooltipBorder: '#cbd5e1',
    threshArea: 'rgba(248,113,113,0.12)',
  },
  dark: {
    text: '#e2e8f0',
    muted: '#64748b',
    axisLine: '#334155',
    splitLine: '#1e293b',
    legend: '#cbd5e1',
    tooltipBg: 'rgba(15,23,42,0.95)',
    tooltipBorder: '#334155',
    threshArea: 'rgba(248,113,113,0.25)',
  },
};