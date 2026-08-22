import { DownloadOutlined, ReloadOutlined, SyncOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { App } from 'antd';
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
  ForecastSummaryCards,
  ModelEvaluationCards,
  PeakAndModelTop,
  StrategyInsightPanel
} from '../../components/forecast/ForecastDesign';
import { DetailDrawer } from '../../components/actions/DetailDrawer';
import { PageHeader } from '../../components/common/PageHeader';
import type { PageHeaderAction } from '../../components/common/PageHeader';
import { PageTabs } from '../../components/common/PageTabs';
import { PageDataState } from '../../components/common/States';
import { useAuth } from '../../context/AuthContext';
import { getForecastCenterData } from '../../services/forecastApi';
import { resolvePageDataMeta } from '../../services/viewState';
import type { PageProps } from '../../types/ui';

const forecastTabs = [
  { key: 'forecast-24h', label: '24小时预测' },
  { key: 'forecast-history', label: '历史对比' },
  { key: 'forecast-model', label: '峰谷分析 / 模型评估' }
];

function csvExport(filename: string, rows: any[]) {
  const keys = Object.keys(rows[0] || {});
  if (!keys.length) {
    return false;
  }
  const csv = [keys, ...rows.map((row) => keys.map((key) => row[key]))]
    .map((line) => line.map((item) => `"${String(item ?? '').replace(/"/g, '""')}"`).join(','))
    .join('\n');
  const blob = new Blob([`\uFEFF${csv}`], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${filename}_${Date.now()}.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
  return true;
}

export function ForecastCenterPage({ activeSubKey, onSubNavigate }: PageProps) {
  const { message } = App.useApp();
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [runningForecast, setRunningForecast] = useState(false);
  const [requestError, setRequestError] = useState<unknown>(null);
  const [selectedHour, setSelectedHour] = useState<any>(null);
  const [historyGranularity, setHistoryGranularity] = useState<'hour' | 'day' | 'week'>('hour');
  const [historyRangeDays, setHistoryRangeDays] = useState<7 | 30>(30);
  const { hasPermission } = useAuth();
  const canRunForecast = hasPermission('forecast:run');
  const canGenerateStrategy = hasPermission('strategy:generate');
  const canReadData = hasPermission('data:read');
  const canReadModel = hasPermission('model:read');

  const loadData = useCallback(async () => {
    setLoading(true);
    setRequestError(null);
    try {
      setData(await getForecastCenterData({ canReadData, canReadModel }));
    } catch (error) {
      setRequestError(error);
    } finally {
      setLoading(false);
    }
  }, [canReadData, canReadModel]);

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
    ? '对照最新预测、上一成功结果与历史小时均值，定位关键变化。'
    : view === 'model'
      ? '集中呈现峰谷特征、评估指标、工程门禁与回测表现。'
      : '查看 24 小时电价曲线、峰谷窗口与可执行建议。';

  async function runForecast() {
    setRunningForecast(true);
    try {
      const result = await api.runForecast();
      message.success(`预测任务已启动：${result.task_id || 'refresh_fast_forecast'}`);
      await loadData();
    } catch (error) {
      message.error(error instanceof Error ? error.message : '预测任务启动失败');
    } finally {
      setRunningForecast(false);
    }
  }

  const exportRows = view === '24h'
    ? data?.detailRows || []
    : view === 'history'
      ? data?.comparison?.rows || []
      : data?.backtestSummary?.baseline_comparisons || [];
  const actions = useMemo<PageHeaderAction[]>(() => {
    const refreshAction: PageHeaderAction = {
      key: 'refresh',
      label: '刷新',
      icon: <ReloadOutlined />,
      loading,
      onClick: loadData
    };
    const runAction: PageHeaderAction = {
      key: 'run',
      label: '更新预测',
      icon: <SyncOutlined />,
      type: 'primary',
      loading: runningForecast,
      hidden: !canRunForecast,
      onClick: runForecast
    };
    const exportAction: PageHeaderAction = {
      key: 'export',
      label: view === '24h' ? '导出结果' : view === 'history' ? '导出对比' : '导出评估',
      icon: <DownloadOutlined />,
      collapseAtNarrow: true,
      disabled: !exportRows.length,
      disabledReason: '当前没有可导出的接口记录',
      onClick: () => {
        const exported = csvExport(
          view === '24h' ? 'forecast_details' : view === 'history' ? 'forecast_comparison' : 'baseline_comparison',
          exportRows
        );
        if (!exported) {
          message.warning('当前没有可导出的接口记录');
        } else {
          message.success(`已导出 ${exportRows.length} 条记录`);
        }
      }
    };
    const strategyAction: PageHeaderAction = {
      key: 'strategy',
      label: '生成策略',
      icon: <ThunderboltOutlined />,
      collapseAtNarrow: true,
      hidden: !canGenerateStrategy,
      onClick: () => {
        message.info('已进入策略中心，请在完整业务上下文中生成策略。');
        window.location.hash = '#/strategy/strategy-high';
      }
    };
    if (view === '24h') return [refreshAction, exportAction, strategyAction];
    if (view === 'history') return [refreshAction, runAction, exportAction];
    return [refreshAction, exportAction, runAction];
  }, [canGenerateStrategy, canRunForecast, exportRows, loading, loadData, message, runningForecast, view]);

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
          trend: Number.isFinite(avgChange) ? avgChange : undefined,
          tone: 'orange',
          source: data?.comparison?.derivedSource
        }
      ];
    }
    if (view === 'model') {
      const checks = [
        data?.backtestSummary?.available,
        data?.featureSchema?.schema_gate?.ok,
        String(data?.leakageCheck?.gate_status || data?.leakageCheck?.status || '').toLowerCase() === 'passed'
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
          note: String(data?.leakageCheck?.gate_status || data?.leakageCheck?.status || '待接入'),
          trend: score == null ? 0 : score - 90,
          tone: 'purple'
        }
      ];
    }
    return base;
  }, [data, view]);

  const rows = data?.detailRows || [];
  const comparisonRows = data?.comparison?.rows || [];
  const viewMeta = useMemo(() => resolvePageDataMeta({
    loading,
    hasData: Boolean(data?.available && !data?.empty),
    empty: Boolean(data?.empty),
    error: requestError || data?.error,
    partialErrors: data?.partialErrors,
    isStale: Boolean(data?.isStale),
    emptyReason: '所选预测子页面的接口已成功返回，但当前没有有效预测记录。',
    queryScope: title
  }), [data, loading, requestError, title]);
  const showContent = viewMeta.state === 'success' || viewMeta.state === 'stale';

  return (
    <div className={`forecast-design-page forecast-view-${view}`}>
      <PageHeader
        title={title}
        subtitle={subtitle}
        className="forecast-page-header"
        navigation={<PageTabs items={forecastTabs.filter((item) => item.key !== 'forecast-model' || canReadModel)} activeKey={activeSubKey} onChange={onSubNavigate} />}
        metadata={(
          <ForecastContextBar
            data={data}
            view={view}
            granularity={historyGranularity}
            onGranularityChange={setHistoryGranularity}
          />
        )}
        actions={actions}
      />
      {!showContent ? <PageDataState meta={viewMeta} onRetry={loadData} /> : null}

      {showContent ? <ForecastMetricCards metrics={metricItems} /> : null}

      {showContent && view === '24h' ? (
        <>
          <div className="forecast-primary-grid">
            <ForecastChartCard data={data} />
            <StrategyInsightPanel data={data} />
          </div>
          <div className="forecast-detail-grid">
            <div className="forecast-card forecast-table-card">
              <div className="forecast-card-head"><h2>24小时预测明细</h2></div>
              <ForecastDetailTable rows={rows} compact onExplain={setSelectedHour} />
            </div>
            <ForecastSummaryCards data={data} />
          </div>
        </>
      ) : null}

      {showContent && view === 'history' ? (
        <>
          <div className="forecast-primary-grid">
            <ComparisonChartCard
              data={data}
              granularity={historyGranularity}
              rangeDays={historyRangeDays}
              onRangeChange={setHistoryRangeDays}
            />
            <ComparisonInsightPanel data={data} />
          </div>
          <div className="forecast-history-bottom">
            <div className="forecast-card forecast-table-card">
              <div className="forecast-card-head"><h2>对比明细表</h2></div>
              <ComparisonDetailTable
                rows={comparisonRows}
                comparison={data?.comparison}
                granularity={historyGranularity}
                rangeDays={historyRangeDays}
                historyRecords={data?.historyApi?.records || []}
              />
            </div>
            <HistorySideCards data={data} />
          </div>
        </>
      ) : null}

      {showContent && view === 'model' ? (
        <>
          <PeakAndModelTop data={data} />
          <ModelEvaluationCards data={data} />
          <BaselineAndTraining data={data} />
        </>
      ) : null}
      <DetailDrawer
        title="小时预测解释"
        open={Boolean(selectedHour)}
        data={selectedHour ? {
          时间范围: selectedHour.time,
          预测电价: `${selectedHour.price} 元/kWh`,
          风险等级: selectedHour.risk,
          风险概率: selectedHour.riskProbability == null ? '接口未返回' : selectedHour.riskProbability,
          建议动作: selectedHour.action || '接口未返回',
          建议来源: selectedHour.action === '待接入' ? '接口未返回' : '策略建议',
          置信度: selectedHour.confidence === '--' ? '接口未返回' : `${selectedHour.confidence}%`,
          正式置信区间: selectedHour.interval
        } : null}
        onClose={() => setSelectedHour(null)}
      />
    </div>
  );
}

function HistorySideCards({ data }: { data: any }) {
  const topFactors = (data?.modelExplain?.feature_importance || []).length
    ? data.modelExplain.feature_importance
    : data?.modelExplain?.main_factors || [];
  const previousAvailable = Boolean(data?.comparison?.previousAvailable);
  const comparisonRows = data?.comparison?.rows || [];
  const avgChange = Number(data?.comparison?.avgChange);
  const notableCount = comparisonRows.filter((row: any) => Math.abs(Number(String(row.rate).replace('%', ''))) >= 6).length;
  return (
    <div className="history-side-cards">
      <div className="forecast-card compact-card">
        <div className="forecast-card-head"><h2>变化结论</h2></div>
        <p className="decision-pill">
          {previousAvailable
            ? avgChange >= 0 ? '结论：上行 ↗' : '结论：下行 ↘'
            : '上一成功批次不可用'}
        </p>
        <dl className="kv-list history-conclusion-list">
          <dt>均价变化</dt><dd>{Number.isFinite(avgChange) ? `${avgChange >= 0 ? '+' : ''}${avgChange.toFixed(2)}%` : '--'}</dd>
          <dt>显著变化点</dt><dd>{notableCount} 个</dd>
          <dt>可信度</dt><dd>{data?.confidence?.value == null ? '待接入' : data.confidence.value >= 80 ? '高' : '中'}</dd>
        </dl>
      </div>
      <div className="forecast-card compact-card">
        <div className="forecast-card-head"><h2>可解释性说明</h2></div>
        {topFactors.slice(0, 3).map((item: any, index: number) => (
          <p key={index}>{typeof item === 'string' ? item : item.feature || item.name} <strong>{item.weight ? `${Math.round(Number(item.weight) * 100)}%` : '--'}</strong></p>
        ))}
        {!topFactors.length ? <p className="forecast-mini-empty">接口未返回特征重要性</p> : null}
      </div>
      <DataHealthCard health={data?.dataHealth} />
    </div>
  );
}
