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

export function ForecastPageHeader({
  title,
  subtitle,
  tabs,
  controls
}: {
  title: string;
  subtitle: string;
  tabs?: ReactNode;
  controls?: ReactNode;
}) {
  return (
    <div className="forecast-design-header">
      <div className="forecast-heading-copy">
        <h1>{title}</h1>
        <p>{subtitle}</p>
      </div>
      <div className="forecast-header-utility">
        {tabs}
        {controls}
      </div>
    </div>
  );
}

export function ForecastContextBar({ data, actions }: { data: any; actions: ReactNode }) {
  return (
    <div className="forecast-context-bar">
      <div className="forecast-filter-items">
        <span>预测日期 <strong>{data?.date || '待接入'}</strong></span>
        <span>区域 <strong>{data?.region || '浙江省'}</strong></span>
        <span>模型版本 <strong>{data?.modelVersion || 'v3.2.1'}</strong><Tag color="success">最新</Tag></span>
      </div>
      <Space size={8}>{actions}</Space>
    </div>
  );
}

export function MiniSparkline({ values, tone = 'green' }: { values?: number[]; tone?: string }) {
  const data = (values || []).filter((item) => Number.isFinite(Number(item))).slice(-24);
  const color = tone === 'red' ? chartColors.red : tone === 'orange' ? chartColors.orange : tone === 'blue' ? chartColors.blue : chartColors.green;
  if (!data.length) return <div className="forecast-mini-empty">暂无趋势</div>;
  return (
    <AppChart
      height={30}
      option={{
        animation: false,
        grid: { left: 0, right: 0, top: 5, bottom: 5 },
        xAxis: { type: 'category', show: false, data: data.map((_, index) => index) },
        yAxis: { type: 'value', show: false, min: 'dataMin', max: 'dataMax' },
        series: [{ type: 'line', smooth: true, symbol: 'none', data, lineStyle: { width: 2, color }, areaStyle: { color: `${color}18` } }]
      }}
    />
  );
}

export function ForecastMetricCards({ metrics, series }: { metrics: any[]; series: any[] }) {
  const spark = series.map((item) => Number(item.value)).filter(Number.isFinite);
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
          <MiniSparkline values={spark} tone={item.tone} />
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
        <div><h2>24小时电价预测</h2><p>展示真实预测电价序列与峰值点；低价窗口和高风险时段在右侧洞察中说明。</p></div>
        <Space><Tag>小时</Tag><span className="card-unit">单位：元/kWh</span></Space>
      </div>
      {series.length ? <AppChart option={option} height={300} /> : <Empty description="暂无 24 小时预测曲线" />}
    </div>
  );
}

export function StrategyInsightPanel({ data }: { data: any }) {
  const highItems = (data?.highWindow || []).slice(0, 5);
  const insights = data?.strategy?.must_watch || data?.strategy?.items || [];
  return (
    <div className="forecast-card forecast-insight-panel">
      <div className="forecast-card-head"><h2>策略洞察</h2></div>
      <StrategyBlock type="success" title="今日核心结论">
        预计 {data?.highWindowLabel} 出现显著高价风险窗口，峰值 {hour(data?.summary?.maxHour)} 达到 {fmt(data?.summary?.maxPrice, 2)} 元/kWh；{data?.lowWindowLabel} 为低价采购窗口。
      </StrategyBlock>
      <StrategyBlock type="danger" title="高价风险时段">
        <div className="tag-row">{highItems.map((item: any) => <Tag color="error" key={item.time}>{item.time}</Tag>)}</div>
        <p>建议控制敞口，必要时提前部分采购。</p>
      </StrategyBlock>
      <StrategyBlock type="success" title="低价采购窗口">
        <Tag color="success">{data?.lowWindowLabel || '--'}</Tag>
        <p>建议增加采购或储能充电，降低成本。</p>
      </StrategyBlock>
      <StrategyBlock type="info" title="AI 建议摘要">
        {(insights.length ? insights : [{ advice_text: '当前策略接口暂无建议，页面仅展示预测与风险窗口。' }]).slice(0, 3).map((item: any, index: number) => (
          <p key={index}><b>{index + 1}</b> {item.advice_text || item.description || item.message || item.title}</p>
        ))}
      </StrategyBlock>
      <StrategyBlock type="info" title="风险提示 / 可信度说明">
        本次预测可信度为 {data?.confidence?.value == null ? '--' : data.confidence.value.toFixed(1)}%，请结合风险窗口和业务约束审慎决策。
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

export function ForecastDetailTable({ rows, compact = false }: { rows: any[]; compact?: boolean }) {
  const columns: ColumnsType<any> = [
    { title: '时间', dataIndex: 'time', width: 120 },
    { title: '预测电价（元/kWh）', dataIndex: 'price', align: 'right' },
    { title: '风险等级', dataIndex: 'risk', render: (value) => <RiskTag value={value} /> },
    { title: '建议动作', dataIndex: 'action' },
    { title: '置信度（%）', dataIndex: 'confidence', align: 'right' },
    { title: '操作', render: () => <Button type="link" size="small">小时解释</Button> }
  ];
  return <Table size="small" rowKey="key" columns={columns} dataSource={rows} pagination={compact ? false : { pageSize: 8, showSizeChanger: false }} scroll={{ y: compact ? 116 : 210, x: 780 }} />;
}

export function ForecastSummaryCards({ data }: { data: any }) {
  const active = data?.activeModel || {};
  return (
    <div className="forecast-bottom-summary">
      <ModelStatusCard model={active} data={data} />
      <PeakSummaryCard data={data} />
      <DataHealthCard health={data?.dataHealth} />
    </div>
  );
}

function ModelStatusCard({ model, data }: { model: any; data: any }) {
  return (
    <div className="forecast-card compact-card">
      <div className="forecast-card-head"><h2>模型状态摘要</h2><Tag color={model?.model_version ? 'success' : 'warning'}>{model?.model_version ? 'Active' : '待接入'}</Tag></div>
      <dl className="kv-list">
        <dt>模型</dt><dd>{model?.model_name || model?.name || '电价预测模型'} {model?.model_version || data?.modelVersion || ''}</dd>
        <dt>MAE</dt><dd>{fmt(model?.test_mae || model?.mae)}</dd>
        <dt>RMSE</dt><dd>{fmt(model?.test_rmse || model?.rmse)}</dd>
        <dt>训练时间</dt><dd>{String(model?.activated_at || model?.created_at || data?.generatedAt || '--').slice(0, 16)}</dd>
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
        <dt>波动率</dt><dd>{data?.peakValley?.volatility == null ? '--' : `${data.peakValley.volatility}%`}</dd>
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
        </dl>
      </div>
      <Button block>数据健康详情</Button>
    </div>
  );
}

export function ComparisonChartCard({ data }: { data: any }) {
  const comparison = data?.comparison || {};
  const times = (data?.series || []).map((item: any) => item.time);
  const option = {
    tooltip: { trigger: 'axis', backgroundColor: '#fff', borderColor: '#D8E2EC', textStyle: { color: '#18233A' } },
    legend: { top: 0, left: 0, data: ['最新预测', '上一批次/历史参考', '历史均值（近30天）'] },
    grid: { left: 48, right: 28, top: 54, bottom: 46 },
    xAxis: { type: 'category', data: times, axisTick: { show: false }, axisLine: { lineStyle: { color: '#E5EAF0' } }, axisLabel: { color: '#667085' } },
    yAxis: { type: 'value', name: '元/kWh', splitLine: { lineStyle: { color: '#EDF2F7' } }, axisLabel: { color: '#667085' } },
    series: [
      { name: '最新预测', type: 'line', smooth: true, data: comparison.latest, lineStyle: { width: 3, color: chartColors.green }, itemStyle: { color: chartColors.green } },
      { name: '上一批次/历史参考', type: 'line', smooth: true, data: comparison.previous, lineStyle: { width: 2, type: 'dashed', color: chartColors.blue }, itemStyle: { color: chartColors.blue } },
      { name: '历史均值（近30天）', type: 'line', smooth: true, data: comparison.historyMean, lineStyle: { width: 2, color: chartColors.orange }, itemStyle: { color: chartColors.orange } }
    ]
  };
  return (
    <div className="forecast-card comparison-chart-card">
      <div className="forecast-card-head">
        <div><h2>历史对比趋势（元/kWh）</h2><p>最新预测、上一批次/历史参考与近30天历史均值对比。</p></div>
        <Space><Tag>近7天</Tag><Tag color="success">近30天</Tag></Space>
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
      <StrategyBlock type="success" title="差值摘要">全天均值变化 {data?.comparison?.avgChange == null ? '--' : `${data.comparison.avgChange.toFixed(2)}%`}，晚高峰变化更明显。</StrategyBlock>
      <StrategyBlock type="danger" title="关键变化点（相对参考）">
        {notable.length ? notable.map((row: any) => <p key={row.time}>{row.time} {row.remark} {row.rate}</p>) : <p>历史参考数据不足，暂无显著变化点。</p>}
      </StrategyBlock>
      <StrategyBlock type="info" title="变化原因说明">
        {(data?.modelExplain?.main_factors || ['负荷预期抬升', '新能源出力变化', '气温因素']).slice(0, 3).map((item: any, index: number) => <p key={index}>• {typeof item === 'string' ? item : item.factor || item.name || JSON.stringify(item)}</p>)}
      </StrategyBlock>
      <StrategyBlock type="info" title="AI 建议摘要">建议重点关注 {data?.highWindowLabel} 风险时段，结合历史参考和最新预测优化调度与采购策略。</StrategyBlock>
    </div>
  );
}

export function ComparisonDetailTable({ rows }: { rows: any[] }) {
  const columns: ColumnsType<any> = [
    { title: '时间', dataIndex: 'time' },
    { title: '最新预测', dataIndex: 'latest', align: 'right' },
    { title: '上一批次', dataIndex: 'previous', align: 'right' },
    { title: '历史均值（近30天）', dataIndex: 'historyMean', align: 'right' },
    { title: '差值（较上一批次）', dataIndex: 'diff', align: 'right' },
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
        <div className="forecast-card-head"><h2>峰谷分析（基于24小时预测）</h2><Button type="link">详情</Button></div>
        <div className="peak-gauge-layout">
          <GaugeChart value={pv.index || 0} name="价差指数" height={210} />
          <dl className="kv-list large">
            <dt>峰值时段</dt><dd>{pv.peakRange}</dd>
            <dt>谷值时段</dt><dd>{pv.valleyRange}</dd>
            <dt>波动率（标准差）</dt><dd>{pv.volatility == null ? '--' : `${pv.volatility}%`}</dd>
            <dt>峰值电价</dt><dd>{fmt(pv.peakPrice)} 元/kWh（{pv.peakHour}）</dd>
            <dt>谷值电价</dt><dd>{fmt(pv.valleyPrice)} 元/kWh（{pv.valleyHour}）</dd>
          </dl>
        </div>
      </div>
      <div className="forecast-card peak-explain-card">
        <div className="forecast-card-head"><h2>峰谷策略解释（业务视角）</h2></div>
        <StrategyBlock type="info" title="结论">今日价差指数为 {pv.index || 0}%，高价集中在 {pv.peakRange}，低价窗口在 {pv.valleyRange}。</StrategyBlock>
        <StrategyBlock type="success" title="数据依据">基于 24 小时预测曲线、风险概率、置信区间和模型解释结果识别高 / 低价形成机理。</StrategyBlock>
        <StrategyBlock type="warning" title="业务建议">低价窗口建议补充采购或储能充电；高价风险段建议控制敞口，并人工复核大额申报与对冲策略。</StrategyBlock>
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
        <Space><Button type="link">查看训练日志</Button><Button type="link">查看回测报告</Button></Space>
      </div>
    </div>
  );
}
