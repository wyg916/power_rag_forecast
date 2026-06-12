import { themeTokens } from '../../theme/themeConfig';

export const chartColors = {
  green: themeTokens.primary,
  greenLight: 'rgba(0, 184, 148, 0.12)',
  blue: '#3B82F6',
  orange: '#F97316',
  red: themeTokens.danger,
  purple: themeTokens.purple,
  gray: '#94A3B8'
};

export function baseGrid(): any {
  return {
    color: [chartColors.green, chartColors.blue, chartColors.orange, chartColors.purple],
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#fff',
      borderColor: '#E5EAF0',
      textStyle: { color: '#374151' }
    },
    grid: { left: 42, right: 24, top: 42, bottom: 36 },
    xAxis: {
      type: 'category',
      axisLine: { lineStyle: { color: '#E5EAF0' } },
      axisTick: { show: false },
      axisLabel: { color: '#6B7280' }
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: '#EEF2F6' } },
      axisLabel: { color: '#6B7280' }
    }
  };
}
