import { AppChart } from './AppChart';
import { chartColors } from './chartTheme';

interface SparklineProps {
  data: number[];
  color?: string;
}

export function Sparkline({ data, color = chartColors.green }: SparklineProps) {
  const option: any = {
    grid: { left: 0, right: 0, top: 4, bottom: 4 },
    xAxis: { show: false, type: 'category', data: data.map((_, index) => index) },
    yAxis: { show: false, type: 'value' },
    series: [
      {
        type: 'line',
        smooth: true,
        symbol: 'none',
        lineStyle: { color, width: 2 },
        areaStyle: { color: `${color}22` },
        data
      }
    ]
  };
  return <AppChart option={option} height={48} />;
}
