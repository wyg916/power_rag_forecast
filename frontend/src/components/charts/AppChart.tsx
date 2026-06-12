import ReactECharts from 'echarts-for-react';

interface AppChartProps {
  option: any;
  height?: number | string;
}

export function AppChart({ option, height = 260 }: AppChartProps) {
  return <ReactECharts className="app-chart" option={option} style={{ height, width: '100%' }} notMerge lazyUpdate opts={{ renderer: 'canvas' }} />;
}
