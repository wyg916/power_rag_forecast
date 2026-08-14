import {
  BarChartOutlined,
  CheckCircleOutlined,
  CloudDownloadOutlined,
  DatabaseOutlined,
  ExperimentOutlined,
  FileSearchOutlined,
  LineChartOutlined,
  ReloadOutlined,
  RiseOutlined,
  SafetyCertificateOutlined,
  ThunderboltOutlined,
  WarningOutlined
} from '@ant-design/icons';
import { Button, Empty, Space, Table, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import type { ReactNode } from 'react';
import { AppChart } from '../charts/AppChart';
import { chartColors } from '../charts/chartTheme';
import { RiskTag } from '../common/States';

const toneIcons: Record<string, ReactNode> = {
  orange: <RiseOutlined />,
  green: <CloudDownloadOutlined />,
  blue: <LineChartOutlined />,
  red: <ReloadOutlined />,
  purple: <SafetyCertificateOutlined />
};

function num(value: unknown) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function fmt(value: unknown, digits = 4) {
  const parsed = num(value);
  return parsed == null ? '--' : parsed.toFixed(digits);
}

function hour(value: unknown) {
  const text = String(value || '');
  return text.length >= 16 ? text.slice(11, 16) : text || '--';
}

function conciseAdvice(value: unknown, fallback: string) {
  const text = String(value || '').replace(/^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}\s*/, '').trim();
  return text || fallback;
}

function observedPrice(row: any) {
  for (const key of ['actual_price', 'clearing_price', 'market_price', 'price']) {
    const value = num(row?.[key]);
    if (value != null) return value;
  }
  return null;
}

function historyMeanForRange(records: any[], rangeDays: 7 | 30) {
  const normalized = records
    .map((row) => {
      const datetime = String(row.datetime || row.forecast_datetime || row.date || '');
      const timestamp = Date.parse(datetime);
      return {
        hour: datetime.length >= 13 ? Number(datetime.slice(11, 13)) : Number.NaN,
        timestamp,
        price: observedPrice(row)
      };
    })
    .filter((item) => Number.isFinite(item.hour) && Number.isFinite(item.timestamp) && item.price != null);
  const latestTimestamp = normalized.reduce((latest, item) => Math.max(latest, item.timestamp), Number.NEGATIVE_INFINITY);
  const cutoff = latestTimestamp - rangeDays * 24 * 60 * 60 * 1000;
  const buckets = new Map<number, number[]>();
  normalized.filter((item) => item.timestamp >= cutoff).forEach((item) => {
    const values = buckets.get(item.hour) || [];
    values.push(Number(item.price));
    buckets.set(item.hour, values);
  });
  return Array.from({ length: 24 }, (_, index) => {
    const values = buckets.get(index) || [];
    return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null;
  });
}

function comparisonRowsForRange(rows: any[], historyRecords: any[], rangeDays: 7 | 30) {
  const historyMeans = historyMeanForRange(historyRecords, rangeDays);
  return rows.map((row) => {
    const latest = num(row.latest);
    const previous = num(row.previous);
    const hourMatch = String(row.time || '').match(/^(\d{1,2})/);
    const hour = hourMatch ? Number(hourMatch[1]) : Number.NaN;
    const historyMean = (Number.isInteger(hour) ? historyMeans[hour] : null) ?? num(row.historyMean);
    const reference = previous ?? historyMean;
    const diff = latest == null || reference == null ? null : latest - reference;
    const rate = diff == null || !reference ? null : diff / reference * 100;
    return {
      ...row,
      historyMean: historyMean == null ? '--' : historyMean.toFixed(4),
      diff: diff == null ? '--' : `${diff >= 0 ? '+' : ''}${diff.toFixed(4)}`,
      rate: rate == null ? '--' : `${rate >= 0 ? '+' : ''}${rate.toFixed(2)}%`,
      remark: rate == null ? '参考不足' : Math.abs(rate) >= 8 ? (rate > 0 ? '高于参考' : '低于参考') : '平稳'
    };
  });
}

function aggregateComparisonRows(rows: any[], granularity: 'hour' | 'day' | 'week') {
  if (granularity === 'hour' || !rows.length) return rows;
  const average = (key: string) => {
    const values = rows.map((row) => num(row[key])).filter((value): value is number => value != null);
    return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null;
  };
  const latest = average('latest');
  const previous = average('previous');
  const historyMean = average('historyMean');
  const reference = previous ?? historyMean;
  const diff = latest == null || reference == null ? null : latest - reference;
  const rate = diff == null || !reference ? null : diff / reference * 100;
  return [{
    key: granularity,
    time: granularity === 'day' ? '当前预测日' : '当前预测周',
    latest: latest == null ? '--' : latest.toFixed(4),
    previous: previous == null ? '--' : previous.toFixed(4),
    historyMean: historyMean == null ? '--' : historyMean.toFixed(4),
    diff: diff == null ? '--' : `${diff >= 0 ? '+' : ''}${diff.toFixed(4)}`,
    rate: rate == null ? '--' : `${rate >= 0 ? '+' : ''}${rate.toFixed(2)}%`,
    remark: rate == null ? '参考不足' : Math.abs(rate) >= 8 ? (rate > 0 ? '高于参考' : '低于参考') : '平稳'
  }];
}

function metricIcon(index: number) {
  return [<RiseOutlined />, <CloudDownloadOutlined />, <LineChartOutlined />, <ReloadOutlined />, <SafetyCertificateOutlined />, <ExperimentOutlined />][index] || <BarChartOutlined />;
}

export function ForecastContextBar({
  data,
  view,
  granularity = 'hour',
  onGranularityChange
}: {
  data: any;
  view: '24h' | 'history' | 'model';
  granularity?: 'hour' | 'day' | 'week';
  onGranularityChange?: (value: 'hour' | 'day' | 'week') => void;
}) {
  const contextItems = view === 'history'
    ? [
        ['对比时点', `${data?.comparison?.rows?.length || 0} 个`],
        ['上一成功结果', data?.comparison?.previousAvailable ? '可对比' : '未形成'],
        ['历史参考', `${data?.comparison?.historyRecordCount || 0} 条`],
        ['数据状态', data?.dataHealth?.status || '待核验']
      ]
    : view === 'model'
      ? [
          ['评估数据', data?.backtestSummary?.available ? '可用' : '待接入'],
          ['特征门禁', data?.featureSchema?.schema_gate?.ok ? '通过' : '待复核'],
          ['泄漏门禁', String(data?.leakageCheck?.gate_status || data?.leakageCheck?.status || '').toLowerCase() === 'passed' ? '通过' : '待复核'],
          ['峰谷波动', data?.peakValley?.volatility == null ? '--' : `${data.peakValley.volatility}%`]
        ]
      : [
          ['预测时点', `${data?.series?.length || 0} 个`],
          ['高价窗口', data?.highWindowLabel || '--'],
          ['低价窗口', data?.lowWindowLabel || '--'],
          ['预测可信度', data?.confidence?.value == null ? '待接入' : `${Number(data.confidence.value).toFixed(1)}%`]
        ];
  return (
    <div className="forecast-context-bar">
      <div className="forecast-filter-items">
        {contextItems.map(([label, value]) => (
          <span className="forecast-filter-field" key={label} title={`${label}：${value}`}>
            <small>{label}</small>
            <strong>{value}</strong>
          </span>
        ))}
        {view === 'history' ? (
          <span className="forecast-granularity" aria-label="时间粒度">
            <small>时间粒度</small>
            <span>
              {(['hour', 'day', 'week'] as const).map((value) => (
                <Button
                  key={value}
                  size="small"
                  type={granularity === value ? 'primary' : 'default'}
                  onClick={() => onGranularityChange?.(value)}
                >
                  {{ hour: '小时', day: '天', week: '周' }[value]}
                </Button>
              ))}
            </span>
          </span>
        ) : null}
      </div>
    </div>
  );
}

export function ForecastMetricCards({ metrics }: { metrics: any[] }) {
  return (
    <div className={`forecast-metric-grid metric-count-${metrics.length}`}>
      {metrics.map((item, index) => (
        <div className={`forecast-metric-card tone-${item.tone || 'green'}`} key={item.key || item.title}>
          <div className="forecast-metric-top">
            <span className="forecast-metric-icon">{toneIcons[item.tone] || metricIcon(index)}</span>
            <div>
              <h3>{item.title}</h3>
              <strong>{item.value}<em>{item.unit}</em></strong>
            </div>
          </div>
          <p>
            {item.note || '--'}
            {Number.isFinite(Number(item.trend)) ? (
              <span className={Number(item.trend) >= 0 ? 'trend-up' : 'trend-down'}>{Number(item.trend) >= 0 ? '↑' : '↓'} {Math.abs(Number(item.trend)).toFixed(2)}%</span>
            ) : null}
          </p>
        </div>
      ))}
    </div>
  );
}

export function ForecastChartCard({ data }: { data: any }) {
  const series = data?.series || [];
  const times = series.map((item: any) => item.time);
  const values = series.map((item: any) => item.value);
  const intervalAvailable = Boolean(series.length && series.every((item: any) => item.intervalAvailable && num(item.lower) != null && num(item.upper) != null));
  const intervalLower = series.map((item: any) => num(item.lower));
  const intervalBand = series.map((item: any) => {
    const lower = num(item.lower);
    const upper = num(item.upper);
    return lower == null || upper == null ? null : Math.max(0, upper - lower);
  });
  const peak = series.reduce((best: any, item: any) => Number(item.value) > Number(best?.value ?? -Infinity) ? item : best, null);
  const lowTimes = (data?.lowWindow || []).map((item: any) => item.time).filter(Boolean);
  const highTimes = (data?.highWindow || []).map((item: any) => item.time).filter(Boolean);
  const markAreas = [
    ...(lowTimes.length ? [[{ name: '低价窗口', xAxis: lowTimes[0], itemStyle: { color: 'rgba(0, 184, 148, 0.11)' }, label: { color: chartColors.green } }, { xAxis: lowTimes.at(-1) }]] : []),
    ...(highTimes.length ? [[{ name: '高价风险', xAxis: highTimes[0], itemStyle: { color: 'rgba(255, 77, 79, 0.09)' }, label: { color: chartColors.red } }, { xAxis: highTimes.at(-1) }]] : [])
  ];
  const option = {
    color: [chartColors.green, '#BDEADF', chartColors.red],
    tooltip: { trigger: 'axis', backgroundColor: '#fff', borderColor: '#D8E2EC', textStyle: { color: '#18233A' } },
    legend: { top: 0, left: 0, itemWidth: 24, itemHeight: 8, data: ['预测电价', ...(intervalAvailable ? ['置信区间（95%）'] : []), '峰值点'] },
    grid: { left: 48, right: 26, top: 48, bottom: 44 },
    xAxis: { type: 'category', boundaryGap: false, data: times, axisTick: { show: false }, axisLine: { lineStyle: { color: '#E5EAF0' } }, axisLabel: { color: '#667085', interval: 1 } },
    yAxis: { type: 'value', splitNumber: 5, splitLine: { lineStyle: { color: '#E7EDF4' } }, axisLabel: { color: '#667085' } },
    series: [
      ...(intervalAvailable ? [
        {
          name: '置信区间下界',
          type: 'line',
          stack: 'confidence-band',
          symbol: 'none',
          silent: true,
          data: intervalLower,
          lineStyle: { opacity: 0 },
          areaStyle: { opacity: 0 },
          tooltip: { show: false }
        },
        {
          name: '置信区间（95%）',
          type: 'line',
          stack: 'confidence-band',
          symbol: 'none',
          silent: true,
          data: intervalBand,
          lineStyle: { opacity: 0 },
          areaStyle: { color: 'rgba(0, 184, 148, 0.19)' }
        }
      ] : []),
      {
        name: '预测电价',
        type: 'line',
        smooth: true,
        showSymbol: false,
        data: values,
        z: 5,
        lineStyle: { width: 3.2, color: chartColors.green },
        itemStyle: { color: chartColors.green },
        markArea: { silent: true, data: markAreas }
      },
      ...(peak ? [{
        name: '峰值点',
        type: 'scatter',
        symbolSize: 14,
        data: [[peak.time, peak.value]],
        itemStyle: { color: chartColors.red },
        label: { show: true, formatter: `${hour(peak.raw_time || peak.time)} ${fmt(peak.value, 2)} 元/kWh`, position: 'top', color: '#1f2a44' }
      }] : [])
    ]
  };
  return (
    <div className="forecast-card forecast-chart-card">
      <div className="forecast-card-head">
        <div><h2>24小时电价预测</h2></div>
        <Space wrap>
          <Tag>小时</Tag>
          <span className="card-unit">单位：元/kWh</span>
          <Tag color={intervalAvailable ? 'success' : 'warning'}>
            {intervalAvailable ? '95% 置信区间' : '置信区间待接入'}
          </Tag>
        </Space>
      </div>
      {series.length ? <div className="forecast-chart-body"><AppChart option={option} height="100%" /></div> : <Empty description="暂无 24 小时预测曲线" />}
    </div>
  );
}

export function StrategyInsightPanel({ data }: { data: any }) {
  const highItems = (data?.highWindow || []).slice(0, 4);
  const insights = data?.strategy?.must_watch || data?.strategy?.items || [];
  const strategyItems = data?.strategy?.items || [];
  const highAdvice = strategyItems.find((item: any) => String(item.risk_level).toLowerCase() === 'high');
  const lowAdvice = strategyItems.find((item: any) => String(item.risk_level).toLowerCase() === 'low');
  return (
    <div className="forecast-card forecast-insight-panel">
      <div className="forecast-card-head"><h2>策略洞察</h2></div>
      <StrategyBlock type="success" title="今日核心结论">
        高价集中在 {data?.highWindowLabel}，峰值 {hour(data?.summary?.maxHour)} 为 {fmt(data?.summary?.maxPrice, 2)} 元/kWh；低价候选窗口为 {data?.lowWindowLabel}。
      </StrategyBlock>
      <StrategyBlock type="danger" title="高价风险时段">
        <div className="tag-row">{highItems.map((item: any) => <Tag color="error" key={item.time}>{item.time}</Tag>)}</div>
        <p title={highAdvice?.advice_text}>{conciseAdvice(highAdvice?.advice_text, '策略接口未返回该时段建议。')}</p>
      </StrategyBlock>
      <StrategyBlock type="success" title="低价采购窗口">
        <Tag color="success">{data?.lowWindowLabel || '--'}</Tag>
        <p title={lowAdvice?.advice_text}>{conciseAdvice(lowAdvice?.advice_text, '策略接口未返回该时段建议。')}</p>
      </StrategyBlock>
      <StrategyBlock type="info" title="分析建议摘要">
        {(insights.length ? insights : [{ advice_text: '当前策略接口暂无建议，页面仅展示预测与风险窗口。' }]).slice(0, 1).map((item: any, index: number) => (
          <p key={index} title={item.advice_text || item.description || item.message || item.title}><b>{index + 1}</b> {conciseAdvice(item.advice_text || item.description || item.message || item.title, '暂无可用建议')}</p>
        ))}
      </StrategyBlock>
    </div>
  );
}

export function StrategyBlock({ title, children, type = 'info' }: { title: string; children: ReactNode; type?: 'success' | 'danger' | 'info' | 'warning' }) {
  const icon = {
    success: <CheckCircleOutlined />,
    danger: <WarningOutlined />,
    warning: <ThunderboltOutlined />,
    info: <LineChartOutlined />
  }[type];
  return (
    <section className={`forecast-strategy-block ${type}`}>
      <span className="forecast-strategy-icon">{icon}</span>
      <div className="forecast-strategy-content">
        <h3>{title}</h3>
        <div>{children}</div>
      </div>
    </section>
  );
}

export function ForecastDetailTable({ rows, compact = false, onExplain }: { rows: any[]; compact?: boolean; onExplain?: (row: any) => void }) {
  const columns: ColumnsType<any> = [
    { title: '时间', dataIndex: 'time', width: '16%' },
    { title: '预测电价（元/kWh）', dataIndex: 'price', width: '22%', align: 'right' },
    { title: '风险等级', dataIndex: 'risk', width: '14%', align: 'center', render: (value) => <RiskTag value={value} /> },
    { title: '建议动作', dataIndex: 'action', width: '25%', ellipsis: true, render: (value) => <span title={value}>{value}</span> },
    { title: '置信度（%）', dataIndex: 'confidence', width: '12%', align: 'right' },
    { title: '操作', width: '11%', align: 'right', render: (_, row) => <Button type="link" size="small" onClick={() => onExplain?.(row)}>小时解释</Button> }
  ];
  return <Table size="small" rowKey="key" columns={columns} dataSource={rows} tableLayout="fixed" pagination={{ pageSize: 8, showSizeChanger: false, size: 'small', showLessItems: true }} />;
}

export function ForecastSummaryCards({ data }: { data: any }) {
  return (
    <div className="forecast-bottom-summary">
      <ModelStatusCard data={data} />
      <PeakSummaryCard data={data} />
      <DataHealthCard health={data?.dataHealth} />
    </div>
  );
}

function ModelStatusCard({ data }: { data: any }) {
  const overall = data?.backtestSummary?.reference_baseline?.overall || {};
  const available = Boolean(data?.backtestSummary?.available);
  return (
    <div className="forecast-card compact-card">
      <div className="forecast-card-head"><h2>模型状态摘要</h2><Tag color={available ? 'success' : 'default'}>{available ? '可评估' : '待接入'}</Tag></div>
      <dl className="kv-list">
        <dt>评估状态</dt><dd>{available ? '已完成' : '待接入'}</dd>
        <dt>MAE</dt><dd>{fmt(overall.mae)} 元/kWh</dd>
        <dt>RMSE</dt><dd>{fmt(overall.rmse)} 元/kWh</dd>
        <dt>特征门禁</dt><dd>{data?.featureSchema?.schema_gate?.ok ? '通过' : '待复核'}</dd>
        <dt>泄漏门禁</dt><dd>{String(data?.leakageCheck?.gate_status || data?.leakageCheck?.status || '').toLowerCase() === 'passed' ? '通过' : '待复核'}</dd>
      </dl>
    </div>
  );
}

function PeakSummaryCard({ data }: { data: any }) {
  return (
    <div className="forecast-card compact-card">
      <div className="forecast-card-head"><h2>峰谷分析小结</h2></div>
      <dl className="kv-list">
        <dt>峰值时段</dt><dd>{data?.peakValley?.peakRange}</dd>
        <dt>峰值电价</dt><dd>{fmt(data?.peakValley?.peakPrice, 2)} 元/kWh</dd>
        <dt>谷值时段</dt><dd>{data?.peakValley?.valleyRange}</dd>
        <dt>谷值电价</dt><dd>{fmt(data?.peakValley?.valleyPrice, 2)} 元/kWh</dd>
        <dt>价格变异系数</dt><dd>{data?.peakValley?.volatility == null ? '--' : `${data.peakValley.volatility}%`}</dd>
      </dl>
    </div>
  );
}

export function DataHealthCard({ health }: { health: any }) {
  const healthStatus = health?.status === '已过期' ? '需复核' : health?.status || '待接入';
  const healthy = healthStatus === '正常';
  return (
    <div className="forecast-card compact-card">
      <div className="forecast-card-head"><h2>数据健康状态</h2></div>
      <dl className="kv-list forecast-health-list">
        <dt>数据完整性</dt><dd>{health?.score == null ? '--' : `${Number(health.score).toFixed(1)}%`}</dd>
        <dt>同步状态</dt><dd>{healthStatus}</dd>
        <dt>异常数据</dt><dd>{health?.exceptionCount ?? '--'} 条</dd>
        <dt>缺失数据</dt><dd>{health?.missingCount ?? '--'} 条</dd>
        <dt>延迟数据</dt><dd>{health?.delayCount ?? '--'} 条</dd>
      </dl>
      <div className={`forecast-health-status ${healthy ? 'healthy' : 'review'}`}>{healthy ? '正常' : healthStatus}</div>
      <Button block href="#/data/quality">数据健康详情</Button>
    </div>
  );
}

export function ComparisonChartCard({
  data,
  granularity,
  rangeDays,
  onRangeChange
}: {
  data: any;
  granularity: 'hour' | 'day' | 'week';
  rangeDays: 7 | 30;
  onRangeChange: (value: 7 | 30) => void;
}) {
  const comparison = data?.comparison || {};
  const rangeRows = comparisonRowsForRange(comparison.rows || [], data?.historyApi?.records || [], rangeDays);
  const displayRows = aggregateComparisonRows(rangeRows, granularity);
  const times = displayRows.map((item: any) => item.time);
  const latestValues = displayRows.map((item: any) => num(item.latest));
  const previousValues = displayRows.map((item: any) => num(item.previous));
  const historyValues = displayRows.map((item: any) => num(item.historyMean));
  const historyLabel = `历史均值（近${rangeDays}天）`;
  const previousAvailable = previousValues.some((value: number | null) => value != null);
  const legend = ['最新预测', ...(previousAvailable ? ['上一批次'] : []), historyLabel];
  const calloutTimes = new Set(['05:00', '12:00', '17:00', '20:00']);
  const markPoints = granularity === 'hour'
    ? displayRows.filter((row: any) => calloutTimes.has(String(row.time).slice(0, 5))).map((row: any) => ({
        coord: [row.time, num(row.latest)],
        value: row.rate,
        label: {
          formatter: `${String(row.time).slice(0, 5)} ${row.remark}\n${row.rate}`,
          position: String(row.time).startsWith('17') ? 'top' : 'bottom',
          color: chartColors.green,
          fontSize: 10,
          fontWeight: 700,
          lineHeight: 14,
          padding: [5, 7],
          backgroundColor: '#fff',
          borderColor: '#9BCFC2',
          borderWidth: 1,
          borderRadius: 4
        },
        itemStyle: { color: chartColors.green }
      }))
    : [];
  const chartSeries: any[] = [
    {
      name: '最新预测',
      type: 'line',
      smooth: true,
      showSymbol: false,
      data: latestValues,
      lineStyle: { width: 3, color: chartColors.green },
      itemStyle: { color: chartColors.green },
      markPoint: { symbol: 'circle', symbolSize: 9, data: markPoints }
    },
    ...(previousAvailable ? [{ name: '上一批次', type: 'line', smooth: true, showSymbol: false, data: previousValues, lineStyle: { width: 2.5, type: 'dashed', color: chartColors.blue }, itemStyle: { color: chartColors.blue } }] : []),
    { name: historyLabel, type: 'line', smooth: true, showSymbol: false, data: historyValues, lineStyle: { width: 2.5, color: chartColors.orange }, itemStyle: { color: chartColors.orange } }
  ];
  const option = {
    tooltip: { trigger: 'axis', backgroundColor: '#fff', borderColor: '#D8E2EC', textStyle: { color: '#18233A' } },
    legend: { top: 0, left: 0, itemWidth: 24, itemHeight: 8, data: legend },
    grid: { left: 48, right: 26, top: 52, bottom: 44 },
    xAxis: { type: 'category', boundaryGap: false, data: times, axisTick: { show: false }, axisLine: { lineStyle: { color: '#E5EAF0' } }, axisLabel: { color: '#667085', interval: granularity === 'hour' ? 1 : 0 } },
    yAxis: { type: 'value', splitNumber: 5, splitLine: { lineStyle: { color: '#E7EDF4' } }, axisLabel: { color: '#667085' } },
    series: chartSeries
  };
  return (
    <div className="forecast-card comparison-chart-card">
      <div className="forecast-card-head">
        <div>
          <h2>历史对比趋势（元/kWh）</h2>
        </div>
        <Space className="forecast-range-switch" size={6}>
          <Button size="small" type={rangeDays === 7 ? 'primary' : 'default'} onClick={() => onRangeChange(7)}>近7天</Button>
          <Button size="small" type={rangeDays === 30 ? 'primary' : 'default'} onClick={() => onRangeChange(30)}>近30天</Button>
        </Space>
      </div>
      <div className="forecast-chart-body"><AppChart option={option} height="100%" /></div>
    </div>
  );
}

export function ComparisonInsightPanel({ data }: { data: any }) {
  const rows = data?.comparison?.rows || [];
  const notable = rows.filter((row: any) => String(row.rate).includes('%') && Math.abs(Number(String(row.rate).replace('%', ''))) >= 6).slice(0, 4);
  return (
    <div className="forecast-card forecast-insight-panel">
      <div className="forecast-card-head"><h2>关键变化洞察</h2></div>
      <StrategyBlock type="success" title="差值摘要">
        {data?.comparison?.previousAvailable
          ? `较上一成功结果的全天均值变化 ${data.comparison.avgChange == null ? '--' : `${data.comparison.avgChange.toFixed(2)}%`}。`
          : '当前仅展示最新预测与历史小时均值。'}
      </StrategyBlock>
      <StrategyBlock type="danger" title="关键变化点（相对参考）">
        {notable.length ? notable.map((row: any) => <p key={row.time}>{row.time} {row.remark} {row.rate}</p>) : <p>历史参考数据不足，暂无显著变化点。</p>}
      </StrategyBlock>
      <StrategyBlock type="info" title="变化原因说明">
        {(data?.modelExplain?.main_factors || []).slice(0, 3).map((item: any, index: number) => <p key={index}>• {typeof item === 'string' ? item : item.factor || item.name || JSON.stringify(item)}</p>)}
        {!data?.modelExplain?.main_factors?.length ? <p>模型解释接口未返回主要因素。</p> : null}
      </StrategyBlock>
      <StrategyBlock type="info" title="接口建议摘要">
        {(data?.strategy?.must_watch || []).slice(0, 1).map((item: any) => item.advice_text).join('') || '策略接口未返回建议。'}
      </StrategyBlock>
    </div>
  );
}

export function ComparisonDetailTable({
  rows,
  comparison,
  granularity,
  rangeDays,
  historyRecords
}: {
  rows: any[];
  comparison?: any;
  granularity: 'hour' | 'day' | 'week';
  rangeDays: 7 | 30;
  historyRecords: any[];
}) {
  const displayRows = aggregateComparisonRows(comparisonRowsForRange(rows, historyRecords, rangeDays), granularity);
  const columns: ColumnsType<any> = [
    { title: '时间', dataIndex: 'time', width: '11%' },
    { title: '最新预测', dataIndex: 'latest', width: '15%', align: 'right' },
    { title: comparison?.previousAvailable ? '上一批次' : '上一批次（无）', dataIndex: 'previous', width: '17%', align: 'right' },
    { title: `历史均值（近${rangeDays}天）`, dataIndex: 'historyMean', width: '18%', align: 'right' },
    { title: comparison?.previousAvailable ? '差值（较上一批次）' : '差值（较历史均值）', dataIndex: 'diff', width: '15%', align: 'right' },
    { title: '变化率', dataIndex: 'rate', width: '12%', align: 'right' },
    { title: '备注', dataIndex: 'remark', width: '12%', align: 'center' }
  ];
  return <Table size="small" rowKey="key" columns={columns} dataSource={displayRows} tableLayout="fixed" pagination={granularity === 'hour' ? { pageSize: 7, showSizeChanger: false, size: 'small', showLessItems: true } : false} />;
}

export function PeakAndModelTop({ data }: { data: any }) {
  const pv = data?.peakValley || {};
  return (
    <div className="forecast-peak-model-grid">
      <div className="forecast-card peak-gauge-card">
        <div className="forecast-card-head"><h2>峰谷分析</h2><span className="forecast-card-kicker">基于 24 小时预测</span><Button type="link" href="#/forecast/24h">查看明细</Button></div>
        <div className="peak-gauge-layout">
          <PeakGauge value={pv.volatility || 0} />
          <dl className="kv-list large">
            <dt>峰值时段</dt><dd>{pv.peakRange}</dd>
            <dt>谷值时段</dt><dd>{pv.valleyRange}</dd>
            <dt>价格变异系数</dt><dd>{pv.volatility == null ? '--' : `${pv.volatility}%`}</dd>
            <dt>峰值电价</dt><dd>{fmt(pv.peakPrice)} 元/kWh（{pv.peakHour}）</dd>
            <dt>谷值电价</dt><dd>{fmt(pv.valleyPrice)} 元/kWh（{pv.valleyHour}）</dd>
          </dl>
        </div>
      </div>
      <div className="forecast-card peak-explain-card">
        <div className="forecast-card-head"><h2>峰谷策略解释（业务视角）</h2></div>
        <StrategyBlock type="info" title="结论">峰谷价差/均价比例（封顶 100%）为 {pv.index || 0}%，高价集中在 {pv.peakRange}，低价窗口在 {pv.valleyRange}。</StrategyBlock>
        <StrategyBlock type="success" title="数据依据">
          基于 24 小时预测曲线和风险概率识别高 / 低价时段；
          {data?.quality?.confidenceIntervalAvailable ? '正式置信区间可用。' : '正式置信区间未接入，不参与解释。'}
        </StrategyBlock>
        <StrategyBlock type="warning" title="接口建议">
          {(data?.strategy?.items || []).slice(0, 1).map((item: any) => item.advice_text).join('；') || '策略接口未返回建议。'}
        </StrategyBlock>
      </div>
    </div>
  );
}

function PeakGauge({ value }: { value: number }) {
  const option: any = {
    series: [{
      type: 'gauge',
      startAngle: 205,
      endAngle: -25,
      min: 0,
      max: 100,
      radius: '92%',
      center: ['50%', '57%'],
      axisLine: {
        lineStyle: {
          width: 16,
          color: [
            [0.34, chartColors.green],
            [0.58, chartColors.blue],
            [0.82, chartColors.orange],
            [1, '#E5EAF0']
          ]
        }
      },
      axisTick: { show: false },
      splitLine: { show: false },
      axisLabel: { show: false },
      pointer: { show: false },
      anchor: { show: false },
      detail: {
        valueAnimation: true,
        formatter: '{value}%',
        color: '#152238',
        fontSize: 28,
        fontWeight: 850,
        offsetCenter: [0, '8%']
      },
      title: {
        offsetCenter: [0, '47%'],
        color: '#667085',
        fontSize: 12
      },
      data: [{ value: Number(value.toFixed(1)), name: value >= 60 ? '波动性较强' : '波动性平稳' }]
    }]
  };
  return <AppChart option={option} height="100%" />;
}

export function ModelEvaluationCards({ data }: { data: any }) {
  const ref = data?.backtestSummary?.reference_baseline || {};
  const overall = ref.overall || {};
  const peak = ref.peak || {};
  const spike = ref.spike || {};
  const weather = ref.extreme_weather || {};
  const schema = data?.featureSchema || {};
  const leakage = data?.leakageCheck || {};
  const cards = [
    { title: 'Baseline 指标', icon: <DatabaseOutlined />, rows: [['persistence_24h', ref.model], ['MAE', fmt(overall.mae)], ['RMSE', fmt(overall.rmse)], ['MAPE', fmt(overall.mape, 2)]] },
    { title: '高峰指标 peak', icon: <RiseOutlined />, rows: [['MAE', fmt(peak.mae)], ['RMSE', fmt(peak.rmse)], ['样本数', peak.sample_count ?? '--']] },
    { title: '尖峰识别 spike', icon: <WarningOutlined />, rows: [['Precision', fmt(spike.precision, 3)], ['Recall', fmt(spike.recall, 3)], ['F1 Score', fmt(spike.f1, 3)]] },
    { title: '极端天气 weather', icon: <ThunderboltOutlined />, rows: [['MAE', fmt(weather.mae)], ['RMSE', fmt(weather.rmse)], ['样本数', weather.sample_count ?? '--']] },
    { title: 'Feature Schema', icon: <FileSearchOutlined />, rows: [['校验状态', schema.schema_gate?.ok ? 'passed' : '待接入'], ['特征数量', schema.feature_count == null ? '--' : `${schema.feature_count} features`], ['缺失字段', schema.schema_gate?.missing_features?.length ?? 0]] },
    { title: 'Leakage Gate', icon: <SafetyCertificateOutlined />, rows: [['状态', leakage.gate_status || '--'], ['风险', leakage.high_risk_count ?? 0], ['切分方式', leakage.checks?.time_split_chronological ? '按时间切分' : '待确认']] },
    { title: 'Backtest', icon: <CheckCircleOutlined />, rows: [['Backtest', data?.backtestSummary?.available ? 'available' : '待接入'], ['Validation', data?.backtestSummary?.acceptable_for_backtest === false ? 'blocked' : 'passed'], ['Test', data?.backtestSummary?.available ? 'passed' : '--']] }
  ];
  return (
    <div className="forecast-card model-eval-section">
      <div className="forecast-card-head"><h2>模型评估摘要（P2 工程化能力）</h2></div>
      <div className="model-metric-grid">
        {cards.map((card) => (
          <div className="model-metric-card" key={card.title}>
            <h3><span>{card.icon}</span>{card.title}</h3>
            {card.rows.map(([label, value]) => <p key={label}><span>{label}</span><strong>{value ?? '--'}</strong></p>)}
          </div>
        ))}
      </div>
    </div>
  );
}

export function BaselineAndTraining({ data }: { data: any }) {
  const rows = (data?.backtestSummary?.baseline_comparisons || []).map((row: any, index: number) => ({ key: index, ...row }));
  const columns: ColumnsType<any> = [
    { title: 'split', dataIndex: 'split' },
    { title: '模型', dataIndex: 'model' },
    { title: '参考模型', dataIndex: 'reference_model' },
    { title: 'RMSE 差值（↓）', dataIndex: 'overall_rmse_delta', render: (value) => fmt(value, 2) },
    { title: 'MAE 差值（↓）', dataIndex: 'overall_mae_delta', render: (value) => fmt(value, 2) },
    { title: '是否优于参考', dataIndex: 'is_better_than_reference_overall_rmse', render: (value) => <Tag color={value ? 'success' : 'warning'}>{value ? '优于' : '待复核'}</Tag> }
  ];
  return (
    <div className="forecast-baseline-grid">
      <div className="forecast-card forecast-baseline-table-card">
        <div className="forecast-card-head"><h2>Baseline 对比表（与 persistence_24h 对比）</h2></div>
        <Table size="small" columns={columns} dataSource={rows} tableLayout="fixed" pagination={false} locale={{ emptyText: <Empty description="暂无 Baseline 对比结果" /> }} />
      </div>
      <div className="forecast-card">
        <div className="forecast-card-head"><h2>训练与回测状态</h2></div>
        <dl className="kv-list large">
          <dt>训练任务 ID</dt><dd>{data?.retrainSuggestion?.task_id || '待接入'}</dd>
          <dt>训练状态</dt><dd>{data?.backtestSummary?.available ? '完成' : '待接入'}</dd>
          <dt>样本数</dt><dd>{data?.backtestSummary?.sample_count || '--'}</dd>
          <dt>验证集状态</dt><dd>{data?.backtestSummary?.acceptable_for_backtest === false ? '未通过' : data?.backtestSummary?.available ? '通过' : '待接入'}</dd>
          <dt>测试集状态</dt><dd>{data?.backtestSummary?.available ? '通过' : '待接入'}</dd>
        </dl>
        <Space><Button type="link" href="#/task/log">查看训练日志</Button><Button type="link" href="#/report/list">查看回测报告</Button></Space>
      </div>
    </div>
  );
}
