import { AppChart } from './AppChart';
import { chartColors } from './chartTheme';

interface GaugeChartProps {
  value: number;
  name: string;
  height?: number;
}

export function GaugeChart({ value, name, height = 180 }: GaugeChartProps) {
  const option: any = {
    series: [
      {
        type: 'gauge',
        startAngle: 210,
        endAngle: -30,
        min: 0,
        max: 100,
        progress: { show: true, width: 14, itemStyle: { color: chartColors.green } },
        axisLine: { lineStyle: { width: 14, color: [[1, '#E5EAF0']] } },
        axisTick: { show: false },
        splitLine: { show: false },
        axisLabel: { show: false },
        pointer: { show: false },
        detail: {
          valueAnimation: true,
          formatter: '{value}%',
          color: chartColors.green,
          fontSize: 24,
          fontWeight: 800,
          offsetCenter: [0, '10%']
        },
        title: { offsetCenter: [0, '48%'], color: '#6B7280', fontSize: 12 },
        data: [{ value, name }]
      }
    ]
  };
  return <AppChart option={option} height={height} />;
}
