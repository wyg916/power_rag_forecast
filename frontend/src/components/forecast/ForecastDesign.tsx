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
import { Button, Empty, Progress, Space, Table, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import type { ReactNode } from 'react';
import { AppChart } from '../charts/AppChart';
import { chartColors } from '../charts/chartTheme';
import { GaugeChart } from '../charts/GaugeChart';
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

function metricIcon(index: number) {
  return [<RiseOutlined />, <CloudDownloadOutlined />, <LineChartOutlined />, <ReloadOutlined />, <SafetyCertificateOutlined />, <ExperimentOutlined />][index] || <BarChartOutlined />;
}

export function ForecastContextBar({ data }: { data: any }) {
  const unavailable = !data?.available || data?.freshnessStatus === 'unavailable';
  return (
    <div className="forecast-context-bar">
      <div className="forecast-filter-items">
        <span className="forecast-meta-date">预测日期 <strong>{data?.date || '--'}</strong></span>
        <span className="forecast-meta-region">区域 <strong>{data?.region || '--'}</strong></span>
        <span className="forecast-meta-model">推理模型 <strong title={data?.modelVersion || undefined}>{data?.modelVersion || '--'}</strong></span>
        <span className="forecast-meta-feature">特征版本 <strong title={data?.featureVersion || undefined}>{data?.featureVersion || '--'}</strong></span>
        <span className="forecast-meta-window">适用窗口 <strong title={data?.validFrom && data?.validTo ? `${data.validFrom} 至 ${data.validTo}` : undefined}>{data?.validFrom && data?.validTo ? `${String(data.validFrom).slice(0, 16)} 至 ${String(data.validTo).slice(0, 16)}` : '--'}</strong></span>
        <span className="forecast-meta-status">批次状态 <Tag color={unavailable ? 'default' : data?.isStale ? 'warning' : 'success'}>{unavailable ? '暂不可用' : data?.isStale ? '历史窗口已结束' : '当前可用'}</Tag></span>
        {data?.developmentMode ? <span className="forecast-meta-boundary">运行边界 <Tag color="warning">开发/演示闭环（非生产）</Tag></span> : null}
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
          <span className="forecast-metric-source">{item.sourceLabel || '当前预测批次'}</span>
        </div>
      ))}
    </div>
  );
}

export function ForecastChartCard({ data }: { data: any }) {
  const series = data?.series || [];
  const times = series.map((item: any) => item.time);
  const values = series.map((item: any) => item.value);
  const peak = series.reduce((best: any, item: any) => Number(item.value) > Number(best?.value ?? -Infinity) ? item : best, null);
  const option = {
    color: [chartColors.green, chartColors.red],
    tooltip: { trigger: 'axis', backgroundColor: '#fff', borderColor: '#D8E2EC', textStyle: { color: '#18233A' } },
    legend: { top: 0, left: 0, data: ['预测电价', '峰值点'] },
    grid: { left: 48, right: 28, top: 54, bottom: 46 },
    xAxis: { type: 'category', data: times, axisTick: { show: false }, axisLine: { lineStyle: { color: '#E5EAF0' } }, axisLabel: { color: '#667085' } },
    yAxis: { type: 'value', name: '元/kWh', splitLine: { lineStyle: { color: '#EDF2F7' } }, axisLabel: { color: '#667085' } },
    series: [
      {
        name: '预测电价',
        type: 'line',
        smooth: true,
        showSymbol: true,
        symbolSize: 6,
        data: values,
        z: 5,
        lineStyle: { width: 3, color: chartColors.green },
        itemStyle: { color: chartColors.green }
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
        <div><h2>{data?.isStale ? '历史 24 小时电价预测' : '24 小时电价预测'}</h2><p>{data?.isStale ? '展示已结束适用窗口的可追溯预测序列，仅供复盘。' : '展示当前可用预测序列与峰值点；低价窗口和高风险时段在右侧说明。'}</p></div>
        <Space wrap>
          <Tag>小时</Tag>
          <span className="card-unit">单位：元/kWh</span>
          <Tag color={data?.quality?.confidenceIntervalAvailable ? 'success' : 'warning'}>
            {data?.quality?.confidenceIntervalAvailable ? '正式置信区间' : '置信区间待接入'}
          </Tag>
        </Space>
      </div>
      {series.length ? <div className="forecast-chart-body"><AppChart option={option} height="100%" /></div> : <Empty description="暂无 24 小时预测曲线" />}
    </div>
  );
}

export function StrategyInsightPanel({ data }: { data: any }) {
  const highItems = (data?.highWindow || []).slice(0, 5);
  const insights = data?.strategy?.must_watch || data?.strategy?.items || [];
  const strategyItems = data?.strategy?.items || [];
  const highAdvice = strategyItems.find((item: any) => String(item.risk_level).toLowerCase() === 'high');
  const lowAdvice = strategyItems.find((item: any) => String(item.risk_level).toLowerCase() === 'low');
  return (
    <div className="forecast-card forecast-insight-panel">
      <div className="forecast-card-head"><h2>策略洞察</h2></div>
      <StrategyBlock type={data?.isStale ? 'warning' : 'success'} title={data?.isStale ? '历史预测摘要' : '预测事实摘要'}>
        {data?.isStale ? '该批次曾预测' : '预计'} {data?.highWindowLabel} 出现高价风险窗口，峰值 {hour(data?.summary?.maxHour)} 为 {fmt(data?.summary?.maxPrice, 2)} 元/kWh；{data?.lowWindowLabel} 为低价候选窗口。{data?.isStale ? ' 适用窗口已结束，不可作为当前交易依据。' : ''}
      </StrategyBlock>
      <StrategyBlock type="danger" title="高价风险时段">
        <div className="tag-row">{highItems.map((item: any) => <Tag color="error" key={item.time}>{item.time}</Tag>)}</div>
        <p>{highAdvice?.advice_text || '策略接口未返回该时段建议。'}</p>
      </StrategyBlock>
      <StrategyBlock type="success" title="低价采购窗口">
        <Tag color="success">{data?.lowWindowLabel || '--'}</Tag>
        <p>{lowAdvice?.advice_text || '策略接口未返回该时段建议。'}</p>
      </StrategyBlock>
      <StrategyBlock type="info" title="接口建议摘要">
        {(insights.length ? insights : [{ advice_text: '当前策略接口暂无建议，页面仅展示预测与风险窗口。' }]).slice(0, 3).map((item: any, index: number) => (
          <p key={index}><b>{index + 1}</b> {item.advice_text || item.description || item.message || item.title}</p>
        ))}
      </StrategyBlock>
      <StrategyBlock type="info" title="风险提示 / 可信度说明">
        该预测批次可信度为 {data?.confidence?.value == null ? '--' : data.confidence.value.toFixed(1)}%（{data?.confidence?.source || '来源待接入'}）；
        {data?.quality?.confidenceIntervalAvailable ? '接口已返回正式置信区间。' : data?.quality?.confidenceIntervalReason || '置信区间待接入。'}
      </StrategyBlock>
    </div>
  );
}

export function StrategyBlock({ title, children, type = 'info' }: { title: string; children: ReactNode; type?: 'success' | 'danger' | 'info' | 'warning' }) {
  return (
    <section className={`forecast-strategy-block ${type}`}>
      <h3>{title}</h3>
      <div>{children}</div>
    </section>
  );
}

export function ForecastDetailTable({ rows, compact = false, onExplain }: { rows: any[]; compact?: boolean; onExplain?: (row: any) => void }) {
  const columns: ColumnsType<any> = [
    { title: '时间', dataIndex: 'time', width: 120 },
    { title: '预测电价（元/kWh）', dataIndex: 'price', align: 'right' },
    { title: '风险等级', dataIndex: 'risk', render: (value) => <RiskTag value={value} /> },
    { title: '接口建议', dataIndex: 'action', width: 240, ellipsis: true, render: (value, row) => <span title={`${value}；来源：${row.actionSource}`}>{value}</span> },
    { title: '置信度（%）', dataIndex: 'confidence', align: 'right' },
    { title: '置信区间', dataIndex: 'interval', width: 190 },
    { title: '操作', render: (_, row) => <Button type="link" size="small" onClick={() => onExplain?.(row)}>小时解释</Button> }
  ];
  return <Table size="small" rowKey="key" columns={columns} dataSource={rows} pagination={compact ? false : { pageSize: 8, showSizeChanger: false }} scroll={{ y: compact ? 142 : 210, x: 1080 }} />;
}

export function ForecastSummaryCards({ data }: { data: any }) {
  const inferenceModel = data?.inferenceModel || {};
  return (
    <div className="forecast-bottom-summary">
      <ModelStatusCard model={inferenceModel} data={data} />
      <PeakSummaryCard data={data} />
      <DataHealthCard health={data?.dataHealth} />
    </div>
  );
}

function ModelStatusCard({ model, data }: { model: any; data: any }) {
  const activeVersion = data?.activeModel?.model_version || data?.activeModel?.version || '';
  const inferenceVersion = model?.model_version || data?.modelVersion || '';
  const isActive = Boolean(inferenceVersion && activeVersion && inferenceVersion === activeVersion && !data?.developmentMode);
  const statusLabel = data?.developmentMode ? 'Candidate · 开发演示' : isActive ? 'Active' : inferenceVersion ? '本次推理模型' : '待接入';
  return (
    <div className="forecast-card compact-card">
      <div className="forecast-card-head"><h2>本次推理模型</h2><Tag color={data?.developmentMode ? 'warning' : inferenceVersion ? 'success' : 'default'}>{statusLabel}</Tag></div>
      <dl className="kv-list">
        <dt>模型版本</dt><dd>{inferenceVersion || '--'}</dd>
        <dt>特征版本</dt><dd>{model?.feature_version || data?.featureVersion || '--'}</dd>
        <dt>输入批次</dt><dd title={data?.inputBatchId || undefined}>{data?.inputBatchId || '--'}</dd>
        <dt>run_id</dt><dd title={data?.runId || undefined}>{data?.runId || '--'}</dd>
        <dt>生成时间</dt><dd>{String(data?.generatedAt || '--').slice(0, 16)}</dd>
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
  return (
    <div className="forecast-card compact-card">
      <div className="forecast-card-head"><h2>数据健康状态</h2></div>
      <div className="forecast-health-inline">
        <Progress type="circle" size={64} percent={Math.round(health?.score || 0)} strokeColor={chartColors.green} />
        <dl className="kv-list">
          <dt>同步状态</dt><dd>{health?.status || '待接入'}</dd>
          <dt>异常数</dt><dd>{health?.exceptionCount ?? '--'} 条</dd>
          <dt>缺失数据</dt><dd>{health?.missingCount ?? '--'} 条</dd>
          <dt>更新时间</dt><dd>{health?.updatedAt || '--'}</dd>
          <dt>异常原因</dt><dd title={health?.staleReason || ''}>{health?.staleReason || '--'}</dd>
        </dl>
      </div>
      <Button block href="#/data/quality">数据健康详情</Button>
    </div>
  );
}

export function ComparisonChartCard({ data }: { data: any }) {
  const comparison = data?.comparison || {};
  const times = (data?.series || []).map((item: any) => item.time);
  const historyLabel = '历史小时均值（接口范围）';
  const legend = ['最新预测', ...(comparison.previousAvailable ? ['上一成功批次'] : []), historyLabel];
  const chartSeries: any[] = [
    { name: '最新预测', type: 'line', smooth: true, data: comparison.latest, lineStyle: { width: 3, color: chartColors.green }, itemStyle: { color: chartColors.green } },
    ...(comparison.previousAvailable ? [{ name: '上一成功批次', type: 'line', smooth: true, data: comparison.previous, lineStyle: { width: 2, type: 'dashed', color: chartColors.blue }, itemStyle: { color: chartColors.blue } }] : []),
    { name: historyLabel, type: 'line', smooth: true, data: comparison.historyMean, lineStyle: { width: 2, color: chartColors.orange }, itemStyle: { color: chartColors.orange } }
  ];
  const option = {
    tooltip: { trigger: 'axis', backgroundColor: '#fff', borderColor: '#D8E2EC', textStyle: { color: '#18233A' } },
    legend: { top: 0, left: 0, data: legend },
    grid: { left: 48, right: 28, top: 54, bottom: 46 },
    xAxis: { type: 'category', data: times, axisTick: { show: false }, axisLine: { lineStyle: { color: '#E5EAF0' } }, axisLabel: { color: '#667085' } },
    yAxis: { type: 'value', name: '元/kWh', splitLine: { lineStyle: { color: '#EDF2F7' } }, axisLabel: { color: '#667085' } },
    series: chartSeries
  };
  return (
    <div className="forecast-card comparison-chart-card">
      <div className="forecast-card-head">
        <div>
          <h2>历史对比趋势（元/kWh）</h2>
          <p>{comparison.previousAvailable ? `上一成功批次：${comparison.previousRunId}` : comparison.previousUnavailableReason} 历史均值保持独立参考口径。</p>
        </div>
        <Space><Tag color="success">历史接口 {comparison.historyRecordCount || 0} 条</Tag></Space>
      </div>
      <AppChart option={option} height={300} />
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
          ? `较上一成功批次的全天均值变化 ${data.comparison.avgChange == null ? '--' : `${data.comparison.avgChange.toFixed(2)}%`}。`
          : data?.comparison?.previousUnavailableReason}
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

export function ComparisonDetailTable({ rows, comparison }: { rows: any[]; comparison?: any }) {
  const columns: ColumnsType<any> = [
    { title: '时间', dataIndex: 'time' },
    { title: '最新预测', dataIndex: 'latest', align: 'right' },
    { title: comparison?.previousAvailable ? '上一成功批次' : '上一成功批次（不可用）', dataIndex: 'previous', align: 'right' },
    { title: '历史小时均值（接口范围）', dataIndex: 'historyMean', align: 'right' },
    { title: '差值（较上一成功批次）', dataIndex: 'diff', align: 'right' },
    { title: '变化率', dataIndex: 'rate', align: 'right' },
    { title: '备注', dataIndex: 'remark' }
  ];
  return <Table size="small" rowKey="key" columns={columns} dataSource={rows} pagination={false} scroll={{ y: 160, x: 900 }} />;
}

export function PeakAndModelTop({ data }: { data: any }) {
  const pv = data?.peakValley || {};
  return (
    <div className="forecast-peak-model-grid">
      <div className="forecast-card peak-gauge-card">
        <div className="forecast-card-head"><h2>峰谷分析（基于24小时预测）</h2><Button type="link" href="#/forecast/24h">查看24小时明细</Button></div>
        <div className="peak-gauge-layout">
          <GaugeChart value={pv.index || 0} name="价差/均价" height={210} />
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
        <StrategyBlock type={data?.isStale ? 'warning' : 'info'} title="结论">{data?.isStale ? '该历史预测窗口的' : '当前预测窗口的'}峰谷价差/均价比例（封顶 100%）为 {pv.index || 0}%，高价集中在 {pv.peakRange}，低价窗口在 {pv.valleyRange}。{data?.isStale ? ' 仅供复盘。' : ''}</StrategyBlock>
        <StrategyBlock type="success" title="数据依据">
          基于 24 小时预测曲线和风险概率识别高 / 低价时段；
          {data?.quality?.confidenceIntervalAvailable ? '正式置信区间可用。' : '正式置信区间未接入，不参与解释。'}
        </StrategyBlock>
        <StrategyBlock type="warning" title="接口建议">
          {(data?.strategy?.items || []).slice(0, 2).map((item: any) => item.advice_text).join('；') || '策略接口未返回建议。'}
        </StrategyBlock>
      </div>
    </div>
  );
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
    { title: 'Feature Schema', icon: <FileSearchOutlined />, rows: [['Schema Version', schema.schema_version || data?.modelVersion], ['特征数量', schema.feature_count == null ? '--' : `${schema.feature_count} features`], ['状态', schema.schema_gate?.ok ? 'passed' : '待接入']] },
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
            {card.rows.map(([label, value]) => <p key={label}><span>{label}</span><strong>{value || '--'}</strong></p>)}
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
      <div className="forecast-card">
        <div className="forecast-card-head"><h2>Baseline 对比表（与 persistence_24h 对比）</h2></div>
        <Table size="small" columns={columns} dataSource={rows} pagination={false} locale={{ emptyText: <Empty description="暂无 Baseline 对比结果" /> }} />
      </div>
      <div className="forecast-card">
        <div className="forecast-card-head"><h2>训练与回测状态</h2></div>
        <dl className="kv-list large">
          <dt>训练任务 ID</dt><dd>{data?.retrainSuggestion?.task_id || '待接入'}</dd>
          <dt>训练状态</dt><dd>{data?.backtestSummary?.available ? '完成' : '待接入'}</dd>
          <dt>样本数</dt><dd>{data?.backtestSummary?.sample_count || '--'}</dd>
          <dt>最近回测时间</dt><dd>{data?.backtestSummary?.generated_at || data?.generatedAt || '--'}</dd>
          <dt>下次自动训练</dt><dd>{data?.retrainSuggestion?.recommended_time || '待接入'}</dd>
        </dl>
        <Space><Button type="link" href="#/task/log">查看训练日志</Button><Button type="link" href="#/report/list">查看回测报告</Button></Space>
      </div>
    </div>
  );
}
