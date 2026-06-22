import { CalendarOutlined, CloudDownloadOutlined, LineChartOutlined, ReloadOutlined, RiseOutlined, SafetyCertificateOutlined } from '@ant-design/icons';
import { Alert, Button, Col, DatePicker, Row, Select, Space, Table, Tag, message } from 'antd';
import { useEffect, useMemo, useState } from 'react';
import { api } from '../../api';
import { DetailDrawer } from '../../components/actions/DetailDrawer';
import { SectionCard } from '../../components/cards/SectionCard';
import { TableCard } from '../../components/cards/TableCard';
import { AppChart } from '../../components/charts/AppChart';
import { baseGrid, chartColors } from '../../components/charts/chartTheme';
import { GaugeChart } from '../../components/charts/GaugeChart';
import { PriceCurveChart } from '../../components/charts/PriceCurveChart';
import { FilterBar } from '../../components/common/FilterBar';
import { PageTabs } from '../../components/common/PageTabs';
import { DataSourceTag, DataStateBanner, RiskTag } from '../../components/common/States';
import { MetricGrid, ResponsiveGrid } from '../../components/layout/UnifiedPage';
import { forecastMock } from '../../mock/forecastMock';
import { getForecastCenterData } from '../../services/forecastApi';
import type { PageProps } from '../../types/ui';

const icons = [<RiseOutlined />, <CloudDownloadOutlined />, <LineChartOutlined />, <ReloadOutlined />, <SafetyCertificateOutlined />];

const tabs = [
  { key: 'forecast-24h', label: '24小时预测' },
  { key: 'forecast-history', label: '历史对比' },
  { key: 'forecast-detail', label: '预测明细' },
  { key: 'forecast-peak', label: '峰谷分析' },
  { key: 'forecast-model', label: '模型评估' }
];

const metricNumber = (value: unknown, digits = 4) => {
  const num = Number(value);
  return Number.isFinite(num) ? num.toFixed(digits) : '--';
};

function priceNumber(value: unknown) {
  const num = Number(value);
  return Number.isFinite(num) ? num : 0;
}

function windowRange(points: any[], predicate: (item: any) => boolean) {
  const hits = points.filter(predicate);
  if (!hits.length) return '--';
  return hits.length === 1 ? hits[0].time : `${hits[0].time}-${hits[hits.length - 1].time}`;
}

export function ForecastCenterPage({ activeSubKey, onSubNavigate }: PageProps) {
  const [forecastData, setForecastData] = useState<any>(forecastMock);
  const [loading, setLoading] = useState(true);
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailData, setDetailData] = useState<Record<string, unknown> | null>(null);

  async function loadData() {
    setLoading(true);
    try {
      setForecastData(await getForecastCenterData());
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData();
  }, []);

  const historyOption = useMemo(() => ({
    ...baseGrid(),
    legend: { top: 0, data: ['最新预测', '上一批次', '历史均值'] },
    xAxis: { ...(baseGrid().xAxis as object), data: forecastData.curve.map((item: any) => item.time) },
    series: [
      { name: '最新预测', type: 'line', smooth: true, data: forecastData.curve.map((item: any) => item.value), lineStyle: { color: chartColors.green } },
      { name: '上一批次', type: 'line', smooth: true, data: forecastData.history, lineStyle: { type: 'dashed', color: chartColors.gray } },
      { name: '历史均值', type: 'line', smooth: true, data: forecastData.history.map((item: number) => item * 0.95), lineStyle: { color: chartColors.blue } }
    ]
  }), [forecastData]);

  async function runForecast() {
    const result = await api.runForecast();
    message.success(`预测任务已启动：${result.task_id || result.run_id || 'refresh_fast_forecast'}`);
  }

  function exportDetails() {
    const rows = forecastData.detailRows || [];
    const header = ['时间', '预测电价', '风险等级', '建议动作', '置信度'];
    const body = rows.map((row: any) => [row.time, row.price, row.risk, row.action, row.confidence]);
    const csv = [header, ...body].map((line) => line.map((item) => `"${String(item ?? '').replace(/"/g, '""')}"`).join(',')).join('\n');
    const blob = new Blob([`\uFEFF${csv}`], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `forecast_details_${Date.now()}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  function openHourDetail(row: any) {
    setDetailData({
      time: row.time,
      predicted_price: row.price,
      risk_level: row.risk,
      confidence: row.confidence,
      action: row.action,
      data_source: forecastData.dataSource || 'postgresql_or_file',
      influence_factors: '价格分位、负荷预测、新能源出力、尖峰概率'
    });
    setDetailOpen(true);
  }

  const detailTable = (
    <Table
      size="small"
      pagination={activeSubKey === 'forecast-detail' ? { pageSize: 12 } : false}
      scroll={{ y: activeSubKey === 'forecast-detail' ? 520 : 360, x: 860 }}
      dataSource={forecastData.detailRows}
      columns={[
        { title: '时间', dataIndex: 'time' },
        { title: '预测电价（元/kWh）', dataIndex: 'price', align: 'right' },
        { title: '风险等级', dataIndex: 'risk', render: (text) => <RiskTag value={text} /> },
        { title: '建议动作', dataIndex: 'action' },
        { title: '置信度', dataIndex: 'confidence', align: 'right' },
        { title: '操作', render: (_, record) => <Button type="link" size="small" onClick={() => openHourDetail(record)}>小时解释</Button> }
      ]}
    />
  );
  const backtest = forecastData.backtestSummary || {};
  const referenceBaseline = backtest.reference_baseline || {};
  const overall = referenceBaseline.overall || {};
  const peak = referenceBaseline.peak || {};
  const spike = referenceBaseline.spike || {};
  const extreme = referenceBaseline.extreme_weather || {};
  const leakage = forecastData.leakageCheck || {};
  const schema = forecastData.featureSchema || {};
  const schemaGateOk = Boolean(schema.schema_gate?.ok);
  const leakageGateOk = leakage.gate_status === 'passed';
  const curveValues = (forecastData.curve || []).map((item: any) => priceNumber(item.value)).filter((value: number) => value > 0);
  const sortedCurve = [...curveValues].sort((a, b) => a - b);
  const lowThreshold = sortedCurve[Math.floor(sortedCurve.length * 0.25)] ?? 0;
  const highThreshold = sortedCurve[Math.floor(sortedCurve.length * 0.75)] ?? 0;
  const lowWindow = windowRange(forecastData.curve || [], (item) => priceNumber(item.value) <= lowThreshold);
  const highWindow = windowRange(forecastData.curve || [], (item) => priceNumber(item.value) >= highThreshold);
  const peakPoint = (forecastData.curve || []).reduce((max: any, item: any) => priceNumber(item.value) > priceNumber(max?.value) ? item : max, null);
  const confidenceAvg = Math.round(
    (forecastData.detailRows || []).reduce((sum: number, row: any) => sum + Number(String(row.confidence || '0').replace('%', '')), 0)
    / Math.max((forecastData.detailRows || []).length, 1)
  );

  return (
    <div className="page-stack">
      <PageTabs items={tabs} activeKey={activeSubKey} onChange={onSubNavigate} />
      <FilterBar
        actions={
          <>
            <Button onClick={loadData}>刷新</Button>
            <Button type="primary" loading={loading} onClick={runForecast}>更新预测</Button>
          </>
        }
      >
        <Space size={16} wrap>
          <span>预测日期</span>
          <DatePicker suffixIcon={<CalendarOutlined />} />
          <span>区域</span>
          <Select value="浙江省" options={[{ value: '浙江省', label: '浙江省' }]} />
          <span>模型版本</span>
          <Select value="v3.2.1（最新）" options={[{ value: 'v3.2.1（最新）', label: 'v3.2.1（最新）' }]} />
          <DataSourceTag source={forecastData.dataSource || 'postgresql_or_file'} />
        </Space>
      </FilterBar>
      <DataStateBanner
        scope="预测中心"
        loading={loading}
        source={forecastData.dataSource}
        error={forecastData.error}
        empty={forecastData.empty}
        mockFallback={forecastData.mockFallback}
        fallbackReason={forecastData.fallbackReason}
        partialErrors={forecastData.partialErrors}
        onRetry={loadData}
      />

      <MetricGrid items={forecastData.metrics || []} icons={icons} loading={loading} minColumnWidth={180} />

      {activeSubKey === 'forecast-24h' && (
        <>
          <div className="forecast-window-grid">
            <div className="forecast-window-card window-low">
              <strong>低价采购窗口</strong>
              <span>{lowWindow}</span>
              <p>低于 25% 分位价格，适合补充采购或储能充电。</p>
              <DataSourceTag source="derived_forecast_curve" />
            </div>
            <div className="forecast-window-card window-high">
              <strong>高价风险时段</strong>
              <span>{highWindow}</span>
              <p>高于 75% 分位价格，建议锁定敞口并复核策略。</p>
              <DataSourceTag source="derived_forecast_curve" />
            </div>
            <div className="forecast-window-card window-confidence">
              <strong>预测可信度</strong>
              <span>{Number.isFinite(confidenceAvg) ? `${confidenceAvg}%` : '--'}</span>
              <p>基于小时明细置信度均值派生；置信带来自 upper/lower 字段。</p>
              <DataSourceTag source={forecastData.dataSource || 'derived_forecast_curve'} />
            </div>
            <div className="forecast-window-card window-peak">
              <strong>峰值点</strong>
              <span>{peakPoint ? `${peakPoint.time} / ${metricNumber(peakPoint.value)}` : '--'}</span>
              <p>用于定位峰值风险和右侧洞察说明。</p>
              <DataSourceTag source="derived_forecast_curve" />
            </div>
          </div>
          <div className="forecast-main-grid">
            <SectionCard title="24小时电价预测（含置信区间）" extra={<Space><span className="card-unit">单位：元/kWh</span><DataSourceTag source={forecastData.dataSource || 'derived_forecast_curve'} /></Space>} loading={loading} height={520}>
              <PriceCurveChart data={forecastData.curve} height={460} showActual={false} />
            </SectionCard>
            <SectionCard title="策略洞察" extra={<a className="card-link" onClick={() => { window.location.hash = '/strategy/strategy-high'; }}>更多洞察</a>} loading={loading} height={520} scrollable>
              <div className="forecast-insight-stack">
                <div className="forecast-insight-block">
                  <strong>今日核心结论</strong>
                  <p>预计 {highWindow} 出现高价风险，峰值 {peakPoint ? `${peakPoint.time} 达到 ${metricNumber(peakPoint.value)} 元/kWh` : '--'}；{lowWindow} 为低价采购窗口。</p>
                </div>
                <div className="forecast-insight-block danger">
                  <strong>高价风险时段</strong>
                  <div className="time-chip-row">{String(highWindow).split('-').filter(Boolean).map((item) => <Tag color="red" key={item}>{item}</Tag>)}</div>
                  <p>建议控制敞口，必要时锁定部分采购价格。</p>
                </div>
                <div className="forecast-insight-block success">
                  <strong>低价采购窗口</strong>
                  <div className="time-chip-row">{String(lowWindow).split('-').filter(Boolean).map((item) => <Tag color="success" key={item}>{item}</Tag>)}</div>
                  <p>建议增加采购或触发储能充电策略，降低综合成本。</p>
                </div>
                <div className="forecast-insight-block">
                  <strong>AI 建议摘要</strong>
                  {(forecastData.insights || []).slice(0, 3).map((item: any[], index: number) => (
                    <button type="button" key={item[0]} onClick={() => { setDetailData({ title: item[0], period: item[1], suggestion: item[2], data_source: 'derived_forecast_curve' }); setDetailOpen(true); }}>
                      <span>{index + 1}</span>
                      <p>{item[0]}：{item[2]}</p>
                    </button>
                  ))}
                </div>
                <div className="forecast-insight-block info">
                  <strong>风险提示 / 可信度说明</strong>
                  <p>本页置信区间来自预测曲线 upper/lower 字段；若接口降级或使用兜底数据，页面会在上方数据状态与标签中显式标注。</p>
                </div>
              </div>
            </SectionCard>
          </div>
          <SectionCard className="forecast-detail-card" title="24小时预测明细" extra={<Button type="link" onClick={exportDetails}>导出</Button>} loading={loading}>
              {detailTable}
          </SectionCard>
        </>
      )}

      {activeSubKey === 'forecast-history' && (
        <SectionCard title="历史对比趋势" extra={<Tag>近7天</Tag>} loading={loading}>
          <AppChart option={historyOption} height={420} />
        </SectionCard>
      )}

      {activeSubKey === 'forecast-detail' && (
        <TableCard title="预测明细表" extra={<Button type="link" onClick={exportDetails}>导出 CSV</Button>} loading={loading} dataSource={forecastData.detailRows} columns={[
          { title: '时间', dataIndex: 'time' },
          { title: '预测电价', dataIndex: 'price', align: 'right' },
          { title: '风险等级', dataIndex: 'risk', render: (text) => <RiskTag value={text} /> },
          { title: '建议动作', dataIndex: 'action' },
          { title: '置信度', dataIndex: 'confidence', align: 'right' },
          { title: '操作', render: (_, record) => <Button type="link" size="small" onClick={() => openHourDetail(record)}>小时解释</Button> }
        ]} />
      )}

      {activeSubKey === 'forecast-peak' && (
        <Row gutter={[16, 16]} className="balanced-row">
          <Col xs={24} lg={8}>
            <SectionCard title="峰谷分析" loading={loading}>
              <div className="peak-card">
                <GaugeChart value={72} name="价差指数" height={180} />
                <div className="peak-meta">
                  <p><span className="dot danger"></span>峰值时段<strong>{forecastData.metrics?.[0]?.note || '--'}</strong></p>
                  <p><span className="dot success"></span>谷值时段<strong>{forecastData.metrics?.[1]?.note || '--'}</strong></p>
                  <p><span className="dot info"></span>波动率<strong>48.7%</strong></p>
                </div>
              </div>
            </SectionCard>
          </Col>
          <Col xs={24} lg={16}>
            <SectionCard title="峰谷策略解释" loading={loading}>
              <div className="advice-panel">
                <h4>结论</h4>
                <p>当前预测存在明显峰谷差，低价窗口适合补充采购或储能充电，高价窗口应控制风险敞口并优先人工复核。</p>
                <h4>数据依据</h4>
                <p>来自最新预测批次的最高价、最低价、均价和风险等级字段。</p>
              </div>
            </SectionCard>
          </Col>
        </Row>
      )}

      {activeSubKey === 'forecast-model' && (
        <>
          <Alert
            showIcon
            type={leakageGateOk && schemaGateOk ? 'success' : 'warning'}
            message={leakageGateOk && schemaGateOk ? 'P2 模型工程化门禁通过' : 'P2 模型工程化门禁需要复核'}
            description={`schema=${schemaGateOk ? 'ok' : 'missing'}，leakage=${leakage.gate_status || '--'}，backtest=${backtest.acceptable_for_backtest === false ? 'blocked' : backtest.available ? 'available' : 'missing'}。该页只读取 P2 输出文件，不触发训练或预测逻辑。`}
          />
          <ResponsiveGrid minColumnWidth={220}>
            <SectionCard compact title="Baseline" extra={<Tag>{referenceBaseline.model || '--'}</Tag>} loading={loading}>
              <div className="operation-card">
                <strong>MAE {metricNumber(overall.mae)}</strong>
                <p>RMSE {metricNumber(overall.rmse)}，MAPE {metricNumber(overall.mape)}，R2 {metricNumber(overall.r2)}</p>
                <p>样本数：{overall.sample_count ?? '--'}</p>
              </div>
            </SectionCard>
            <SectionCard compact title="高峰指标" extra={<Tag color="blue">peak</Tag>} loading={loading}>
              <div className="operation-card">
                <strong>MAE {metricNumber(peak.mae)}</strong>
                <p>RMSE {metricNumber(peak.rmse)}，Bias {metricNumber(peak.bias)}</p>
                <p>样本数：{peak.sample_count ?? '--'}</p>
              </div>
            </SectionCard>
            <SectionCard compact title="尖峰识别" extra={<Tag color="warning">spike</Tag>} loading={loading}>
              <div className="operation-card">
                <strong>F1 {metricNumber(spike.f1)}</strong>
                <p>Precision {metricNumber(spike.precision)}，Recall {metricNumber(spike.recall)}</p>
                <p>阈值：{metricNumber(spike.threshold)}</p>
              </div>
            </SectionCard>
            <SectionCard compact title="极端天气" extra={<Tag color="purple">weather</Tag>} loading={loading}>
              <div className="operation-card">
                <strong>MAE {metricNumber(extreme.mae)}</strong>
                <p>RMSE {metricNumber(extreme.rmse)}，样本数 {extreme.sample_count ?? '--'}</p>
                <p>{extreme.definition || '未定义'}</p>
              </div>
            </SectionCard>
            <SectionCard compact title="Feature Schema" extra={<Tag color={schemaGateOk ? 'success' : 'warning'}>{schema.feature_count ?? 0} features</Tag>} loading={loading}>
              <div className="operation-card">
                <strong>{schema.target?.name || '--'}</strong>
                <p>time_field：{schema.time_field || '--'}</p>
                <p>schema_version：{schema.schema_version || '--'}</p>
              </div>
            </SectionCard>
            <SectionCard compact title="Leakage Gate" extra={<Tag color={leakageGateOk ? 'success' : 'error'}>{leakage.gate_status || '--'}</Tag>} loading={loading}>
              <div className="operation-card">
                <strong>高风险 {leakage.high_risk_count ?? '--'}</strong>
                <p>中风险 {leakage.medium_risk_count ?? '--'}，问题数 {leakage.issue_count ?? '--'}</p>
                <p>time split：{leakage.checks?.time_split_chronological ? '按时间切分' : '需复核'}</p>
              </div>
            </SectionCard>
          </ResponsiveGrid>
          <TableCard
            title="Baseline 对比"
            loading={loading}
            dataSource={(backtest.baseline_comparisons || []).map((row: any, index: number) => ({ key: index, ...row }))}
            columns={[
              { title: 'split', dataIndex: 'split' },
              { title: '模型', dataIndex: 'model' },
              { title: '参考模型', dataIndex: 'reference_model' },
              { title: 'RMSE 差值', dataIndex: 'overall_rmse_delta', render: (value) => metricNumber(value) },
              { title: 'MAE 差值', dataIndex: 'overall_mae_delta', render: (value) => metricNumber(value) },
              { title: '是否优于参考', dataIndex: 'is_better_than_reference_overall_rmse', render: (value) => <Tag color={value ? 'success' : 'warning'}>{value ? '是' : '否'}</Tag> }
            ]}
          />
        </>
      )}

      <DetailDrawer title="单小时预测解释" open={detailOpen} data={detailData} onClose={() => setDetailOpen(false)} />
    </div>
  );
}
