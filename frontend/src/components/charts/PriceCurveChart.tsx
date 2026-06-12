import { AppChart } from './AppChart';
import { baseGrid, chartColors } from './chartTheme';
import type { TimePoint } from '../../types/ui';

interface PriceCurveChartProps {
  data: TimePoint[];
  height?: number;
  showActual?: boolean;
}

export function PriceCurveChart({ data, height = 300, showActual = true }: PriceCurveChartProps) {
  const times = data.map((item) => item.time);
  const values = data.map((item) => item.value).filter((value) => Number.isFinite(Number(value))).map(Number);
  const sorted = [...values].sort((a, b) => a - b);
  const lowThreshold = sorted[Math.floor(sorted.length * 0.25)] ?? 0;
  const highThreshold = sorted[Math.floor(sorted.length * 0.75)] ?? 0;
  const lowIndexes = data.map((item, index) => Number(item.value) <= lowThreshold ? index : -1).filter((index) => index >= 0);
  const highIndexes = data.map((item, index) => Number(item.value) >= highThreshold ? index : -1).filter((index) => index >= 0);
  const markAreaData = [
    lowIndexes.length ? [{ name: '低价窗口', xAxis: times[Math.min(...lowIndexes)] }, { xAxis: times[Math.max(...lowIndexes)] }] : null,
    highIndexes.length ? [{ name: '高价风险', xAxis: times[Math.min(...highIndexes)] }, { xAxis: times[Math.max(...highIndexes)] }] : null
  ].filter(Boolean);
  const option: any = {
    ...baseGrid(),
    legend: { top: 0, data: showActual ? ['预测电价', '实际电价', '置信区间'] : ['预测电价', '置信区间'] },
    xAxis: { ...(baseGrid().xAxis as object), data: times },
    yAxis: { ...(baseGrid().yAxis as object), name: '元/kWh' },
    series: [
      {
        name: '置信区间',
        type: 'line',
        data: data.map((item) => item.upper || item.value + 0.08),
        lineStyle: { opacity: 0 },
        symbol: 'none',
        stack: 'confidence'
      },
      {
        name: '置信区间',
        type: 'line',
        data: data.map((item) => (item.lower || item.value - 0.08) - (item.upper || item.value + 0.08)),
        lineStyle: { opacity: 0 },
        areaStyle: { color: 'rgba(0, 184, 148, 0.12)' },
        symbol: 'none',
        stack: 'confidence'
      },
      {
        name: '预测电价',
        type: 'line',
        smooth: true,
        symbolSize: 5,
        lineStyle: { width: 3, color: chartColors.green },
        itemStyle: { color: chartColors.green },
        data: data.map((item) => item.value),
        markArea: {
          itemStyle: { color: 'rgba(0, 184, 148, 0.10)' },
          data: markAreaData
        }
      },
      ...(showActual
        ? [
            {
              name: '实际电价',
              type: 'line',
              smooth: true,
              symbol: 'none',
              lineStyle: { width: 2, type: 'dashed', color: chartColors.gray },
              data: data.map((item) => item.actual || item.baseline || item.value * 0.92)
            }
          ]
        : [])
    ]
  };
  return <AppChart option={option} height={height} />;
}
