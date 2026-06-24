import { DownloadOutlined, ReloadOutlined, SyncOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { Button, message } from 'antd';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '../../api';
import {
  BaselineAndTraining,
  ComparisonChartCard,
  ComparisonDetailTable,
  ComparisonInsightPanel,
  DataHealthCard,
  ForecastChartCard,
  ForecastContextBar,
  ForecastDetailTable,
  ForecastMetricCards,
  ForecastPageHeader,
  ForecastSummaryCards,
  ModelEvaluationCards,
  PeakAndModelTop,
  StrategyInsightPanel
} from '../../components/forecast/ForecastDesign';
import { PageTabs } from '../../components/common/PageTabs';
import { DataStateBanner } from '../../components/common/States';
import { getForecastCenterData } from '../../services/forecastApi';
import type { PageProps } from '../../types/ui';

const historyTabs = [
  { key: 'forecast-24h', label: '24小时预测' },
  { key: 'forecast-history', label: '历史对比' }
];

const modelTabs = [
  { key: 'forecast-peak', label: '峰谷分析' },
  { key: 'forecast-model', label: '模型评估' }
];

function csvExport(filename: string, rows: any[]) {
  const keys = Object.keys(rows[0] || {});
  if (!keys.length) {
    message.warning('当前没有可导出的数据');
    return;
  }
  const csv = [keys, ...rows.map((row) => keys.map((key) => row[key]))]
    .map((line) => line.map((item) => `"${String(item ?? '').replace(/"/g, '""')}"`).join(','))
    .join('\n');
  const blob = new Blob([`\uFEFF${csv}`], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${filename}_${Date.now()}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

export function ForecastCenterPage({ activeSubKey, onSubNavigate }: PageProps) {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      setData(await getForecastCenterData());
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const view = activeSubKey === 'forecast-history'
    ? 'history'
    : activeSubKey === 'forecast-peak' || activeSubKey === 'forecast-model'
      ? 'model'
      : '24h';

  const title = view === 'history'
    ? '预测中心 / 历史对比'
    : view === 'model'
      ? '预测中心 / 峰谷分析与模型评估'
      : '预测中心 / 24小时预测';
  const subtitle = view === 'history'
    ? '比较当前预测与历史 / 上一批次预测结果，辅助业务判断与策略制定。'
    : view === 'model'
      ? '预测不是黑盒：强化峰谷时段解释、模型评估摘要、Baseline 对比、Schema、Leakage、Backtest 等 P2 工程化能力。'
      : '查看未来 24 小时电价预测、风险窗口与交易建议，辅助制定最优采购策略。';

  async function runForecast() {
    const result = await api.runForecast();
    message.success(`预测任务已启动：${result.task_id || result.run_id || 'refresh_fast_forecast'}`);
  }

  async function generateStrategy() {
    const result = await api.generateStrategy();
    message.success(`策略生成已触发：${result.task_id || result.run_id || 'strategy_generate'}`);
  }

  const actions = useMemo(() => {
    if (view === '24h') {
      return (
        <>
          <Button icon={<ReloadOutlined />} onClick={loadData}>刷新预测</Button>
          <Button icon={<DownloadOutlined />} onClick={() => csvExport('forecast_details', data?.detailRows || [])}>导出结果</Button>
          <Button type="primary" icon={<ThunderboltOutlined />} onClick={generateStrategy}>生成策略</Button>
        </>
      );
    }
    if (view === 'history') {
      return (
        <>
          <Button icon={<ReloadOutlined />} onClick={loadData}>刷新</Button>
          <Button type="primary" icon={<SyncOutlined />} onClick={runForecast}>更新预测</Button>
          <Button icon={<DownloadOutlined />} onClick={() => csvExport('forecast_comparison', data?.comparison?.rows || [])}>导出对比</Button>
        </>
      );
    }
    return (
      <>
        <Button icon={<ReloadOutlined />} onClick={loadData}>刷新</Button>
        <Button icon={<DownloadOutlined />} onClick={() => csvExport('baseline_comparison', data?.backtestSummary?.baseline_comparisons || [])}>导出评估</Button>
        <Button type="primary" icon={<SyncOutlined />} onClick={runForecast}>更新预测</Button>
      </>
    );
  }, [data, loadData, view]);

  const tabs = view === 'history'
    ? <PageTabs items={historyTabs} activeKey={activeSubKey} onChange={onSubNavigate} />
    : view === 'model'
      ? <PageTabs items={modelTabs} activeKey={activeSubKey === 'forecast-peak' ? 'forecast-peak' : 'forecast-model'} onChange={onSubNavigate} />
      : null;

  const metricItems = useMemo(() => {
    const base = data?.metrics || [];
    if (view === 'history') {
      const avgChange = Number(data?.comparison?.avgChange);
      return [
        ...base,
        {
          key: 'batch-change',
          title: '相对上一批次变化',
          value: Number.isFinite(avgChange) ? `${avgChange >= 0 ? '+' : ''}${avgChange.toFixed(2)}` : '--',
          unit: '%',
          note: '均价变化',
          trend: Number.isFinite(avgChange) ? avgChange : 0,
          tone: 'orange',
          source: data?.comparison?.derivedSource
        }
      ];
    }
    if (view === 'model') {
      const checks = [
        data?.backtestSummary?.available,
        data?.featureSchema?.schema_version || data?.featureSchema?.version,
        String(data?.leakageCheck?.status || '').toLowerCase() === 'passed'
      ];
      const passed = checks.filter(Boolean).length;
      const score = checks.length ? Number((passed / checks.length * 100).toFixed(1)) : null;
      return [
        ...base,
        {
          key: 'evaluation',
          title: '评估结论',
          value: score == null ? '--' : score.toFixed(1),
          unit: '/100',
          note: String(data?.leakageCheck?.status || '待接入'),
          trend: score == null ? 0 : score - 90,
          tone: 'purple'
        }
      ];
    }
    return base;
  }, [data, view]);

  const rows = data?.detailRows || [];
  const comparisonRows = data?.comparison?.rows || [];
  const shouldShowStateBanner = loading || data?.empty || Boolean(data?.partialErrors?.length) || data?.mockFallback;

  return (
    <div className="forecast-design-page">
      <ForecastPageHeader
        title={title}
        subtitle={subtitle}
        tabs={tabs}
        controls={<ForecastContextBar data={data} actions={actions} />}
      />
      {shouldShowStateBanner ? (
        <DataStateBanner
          scope="预测中心"
          loading={loading}
          empty={data?.empty}
          mockFallback={false}
          partialErrors={data?.partialErrors}
          onRetry={loadData}
        />
      ) : null}

      <ForecastMetricCards metrics={metricItems} series={data?.series || []} />

      {view === '24h' ? (
        <>
          <div className="forecast-primary-grid">
            <ForecastChartCard data={data} />
            <StrategyInsightPanel data={data} />
          </div>
          <div className="forecast-detail-grid">
            <div className="forecast-card forecast-table-card">
              <div className="forecast-card-head"><h2>24小时预测明细</h2></div>
              <ForecastDetailTable rows={rows} compact />
            </div>
            <ForecastSummaryCards data={data} />
          </div>
        </>
      ) : null}

      {view === 'history' ? (
        <>
          <div className="forecast-primary-grid">
            <ComparisonChartCard data={data} />
            <ComparisonInsightPanel data={data} />
          </div>
          <div className="forecast-history-bottom">
            <div className="forecast-card forecast-table-card">
              <div className="forecast-card-head"><h2>对比明细表</h2></div>
              <ComparisonDetailTable rows={comparisonRows} />
            </div>
            <HistorySideCards data={data} />
          </div>
        </>
      ) : null}

      {view === 'model' ? (
        <>
          <PeakAndModelTop data={data} />
          <ModelEvaluationCards data={data} />
          <BaselineAndTraining data={data} />
        </>
      ) : null}
    </div>
  );
}

function HistorySideCards({ data }: { data: any }) {
  const topFactors = data?.modelExplain?.feature_importance || [];
  return (
    <div className="history-side-cards">
      <div className="forecast-card compact-card">
        <div className="forecast-card-head"><h2>变化结论</h2></div>
        <p className="decision-pill">结论：{Number(data?.comparison?.avgChange || 0) >= 0 ? '上行' : '下行'}</p>
        <p>可信度：{data?.confidence?.value == null ? '待接入' : data.confidence.value >= 80 ? '高' : '中'}</p>
      </div>
      <div className="forecast-card compact-card">
        <div className="forecast-card-head"><h2>可解释性说明</h2></div>
        {(topFactors.length ? topFactors : ['负荷预测', '新能源出力', '气温变化']).slice(0, 3).map((item: any, index: number) => (
          <p key={index}>{typeof item === 'string' ? item : item.feature || item.name} <strong>{item.weight ? `${Math.round(Number(item.weight) * 100)}%` : '--'}</strong></p>
        ))}
      </div>
      <DataHealthCard health={data?.dataHealth} />
    </div>
  );
}
