import { Empty, Tag } from 'antd';
import { AppChart } from '../charts/AppChart';
import { baseGrid, chartColors } from '../charts/chartTheme';
import { formatNumber } from './utils';

function rangeFromItems(series: any[], items: any[]) {
  if (!items?.length) return null;
  const indexes = items
    .map((item) => series.findIndex((point) => point.time === item.time || point.datetime === item.datetime))
    .filter((index) => index >= 0);
  if (!indexes.length) return null;
  return [Math.min(...indexes), Math.max(...indexes)];
}

export function HomeForecastChart({ forecast, risk }: { forecast?: any; risk?: any }) {
  const series = forecast?.series || [];
  if (!series.length) {
    return (
      <div className="home-card home-chart-card">
        <div className="home-card-head">
          <div>
            <h2>今日供需风险总览（24小时）</h2>
            <p>接口未返回可绘制的 24 小时预测数据。</p>
          </div>
        </div>
        <Empty description="暂无预测数据" />
      </div>
    );
  }
  const times = series.map((item: any) => item.time);
  const lowRange = rangeFromItems(series, forecast?.windows?.low_price || []);
  const riskRange = rangeFromItems(series, forecast?.windows?.high_risk || forecast?.windows?.high_price || []);
  const markAreaData = [
    lowRange ? [{ name: '低价窗口', xAxis: times[lowRange[0]] }, { xAxis: times[lowRange[1]] }] : null,
    riskRange ? [{ name: '高风险时段', xAxis: times[riskRange[0]] }, { xAxis: times[riskRange[1]] }] : null
  ].filter(Boolean);
  const option = {
    ...baseGrid(),
    legend: {
      top: 2,
      left: '56%',
      itemWidth: 18,
      data: ['预测电价', '预测负荷', '尖峰风险概率', '置信区间']
    },
    grid: { left: 48, right: 58, top: 58, bottom: 34 },
    xAxis: { ...(baseGrid().xAxis as object), data: times },
    yAxis: [
      { ...(baseGrid().yAxis as object), name: '电价（元/kWh）' },
      { ...(baseGrid().yAxis as object), name: '负荷（MWh）', position: 'right' },
      { ...(baseGrid().yAxis as object), name: '风险（%）', position: 'right', offset: 46, min: 0, max: 100, show: false }
    ],
    series: [
      {
        name: '置信区间',
        type: 'line',
        data: series.map((item: any) => item.lower ?? item.price),
        lineStyle: { opacity: 0 },
        stack: 'confidence',
        symbol: 'none',
        tooltip: { show: false }
      },
      {
        name: '置信区间',
        type: 'line',
        data: series.map((item: any) => Number(item.upper ?? item.price) - Number(item.lower ?? item.price)),
        lineStyle: { opacity: 0 },
        areaStyle: { color: 'rgba(0, 184, 148, 0.12)' },
        stack: 'confidence',
        symbol: 'none'
      },
      {
        name: '预测电价',
        type: 'line',
        smooth: true,
        symbolSize: 6,
        lineStyle: { width: 3, color: chartColors.green },
        itemStyle: { color: chartColors.green },
        data: series.map((item: any) => item.price),
        markArea: {
          label: { color: '#0F766E', fontWeight: 700 },
          itemStyle: { color: 'rgba(0, 184, 148, 0.10)' },
          data: markAreaData
        }
      },
      {
        name: '预测负荷',
        type: 'line',
        yAxisIndex: 1,
        smooth: true,
        symbolSize: 5,
        lineStyle: { width: 2, color: chartColors.blue },
        itemStyle: { color: chartColors.blue },
        data: series.map((item: any) => item.load)
      },
      {
        name: '尖峰风险概率',
        type: 'line',
        yAxisIndex: 2,
        smooth: true,
        symbol: 'none',
        lineStyle: { width: 2, type: 'dashed', color: chartColors.red },
        data: series.map((item: any) => Number(item.risk_probability || 0) * 100)
      }
    ]
  };

  const summary = forecast?.summary || {};
  return (
    <div className="home-card home-chart-card">
      <div className="home-card-head">
        <div>
          <h2>今日供需风险总览（24小时）</h2>
          <p>
            高风险 {risk?.high_risk_count || 0} 个窗口，峰谷价差 {formatNumber(summary.peak_valley_spread, 3)} 元/kWh。
          </p>
        </div>
        <div className="home-chart-meta">
          <Tag color="success">单位：元/kWh</Tag>
        </div>
      </div>
      <AppChart option={option} height="100%" />
    </div>
  );
}
