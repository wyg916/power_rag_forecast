import { Button, Empty, Tag } from 'antd';
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

export function HomeForecastChart({ forecast, risk, isStale = false }: { forecast?: any; risk?: any; isStale?: boolean }) {
  const chartTitle = isStale ? '历史供需风险总览（24小时）' : '供需风险总览（24小时）';
  const series = forecast?.series || [];
  if (!series.length) {
    return (
      <div className="home-card home-chart-card">
        <div className="home-card-head">
          <div>
            <h2>{chartTitle}</h2>
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
    lowRange ? [{ name: '低价窗口', xAxis: times[lowRange[0]], itemStyle: { color: 'rgba(11, 168, 143, 0.12)' } }, { xAxis: times[lowRange[1]] }] : null,
    riskRange ? [{ name: '高风险时段', xAxis: times[riskRange[0]], itemStyle: { color: 'rgba(240, 68, 68, 0.10)' } }, { xAxis: times[riskRange[1]] }] : null
  ].filter(Boolean);
  const option = {
    ...baseGrid(),
    tooltip: {
      ...(baseGrid().tooltip as object),
      confine: true
    },
    legend: {
      top: 0,
      left: 8,
      itemWidth: 18,
      data: ['预测电价', '预测负荷', '尖峰风险概率', '置信区间']
    },
    grid: { left: 48, right: 54, top: 46, bottom: 24 },
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
        symbol: 'none',
        tooltip: { valueFormatter: (value: unknown) => `${formatNumber(value, 3)} 元/kWh` }
      },
      {
        name: '预测电价',
        type: 'line',
        smooth: true,
        symbolSize: 6,
        lineStyle: { width: 3, color: chartColors.green },
        itemStyle: { color: chartColors.green },
        tooltip: { valueFormatter: (value: unknown) => `${formatNumber(value, 3)} 元/kWh` },
        data: series.map((item: any) => item.price),
        markArea: {
          label: { color: '#0F766E', fontWeight: 700 },
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
        tooltip: { valueFormatter: (value: unknown) => `${formatNumber(value, 2)} MWh` },
        data: series.map((item: any) => item.load)
      },
      {
        name: '尖峰风险概率',
        type: 'line',
        yAxisIndex: 2,
        smooth: true,
        symbol: 'none',
        lineStyle: { width: 2, type: 'dashed', color: chartColors.red },
        tooltip: { valueFormatter: (value: unknown) => `${formatNumber(value, 1)}%` },
        data: series.map((item: any) => Number(item.risk_probability || 0) * 100)
      }
    ]
  };

  const summary = forecast?.summary || {};
  return (
    <div className="home-card home-chart-card">
      <div className="home-card-head">
        <div>
          <h2>{chartTitle}</h2>
          <p>
            高风险 {risk?.high_risk_count || 0} 个窗口，峰谷价差 {formatNumber(summary.peak_valley_spread, 3)} 元/kWh。
          </p>
        </div>
        <div className="home-chart-meta">
          {isStale ? <Tag color="warning">仅供历史复盘</Tag> : null}
          <Tag>单位：元/kWh</Tag>
          <Button size="small" onClick={() => { window.location.hash = '/forecast/forecast-24h'; }}>查看详情</Button>
        </div>
      </div>
      <AppChart option={option} height="100%" />
    </div>
  );
}
