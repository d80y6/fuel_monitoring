import * as echarts from 'echarts';
import { chartColors } from './chartColors';

export const CHART_THEME_LIGHT = 'fmp-light';
export const CHART_THEME_DARK = 'fmp-dark';

let registered = false;

export function registerChartThemes(): void {
  if (registered) return;
  const mk = (c: (typeof chartColors)['light']) => ({
    textStyle: { color: c.text },
    title: { textStyle: { color: c.text } },
    legend: { textStyle: { color: c.legend } },
    tooltip: { backgroundColor: c.tooltipBg, borderColor: c.tooltipBorder, textStyle: { color: c.text } },
    categoryAxis: { axisLine: { lineStyle: { color: c.axisLine } }, axisLabel: { color: c.muted }, splitLine: { lineStyle: { color: c.splitLine } } },
    valueAxis: { axisLabel: { color: c.muted }, splitLine: { lineStyle: { color: c.splitLine } } },
  });
  echarts.registerTheme(CHART_THEME_LIGHT, mk(chartColors.light));
  echarts.registerTheme(CHART_THEME_DARK, mk(chartColors.dark));
  registered = true;
}

export function chartThemeName(scheme: 'light' | 'dark'): string {
  return scheme === 'dark' ? CHART_THEME_DARK : CHART_THEME_LIGHT;
}

void registerChartThemes();