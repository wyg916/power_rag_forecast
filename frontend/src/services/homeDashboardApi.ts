import { api } from '../api';

export interface HomeDashboardData {
  kpi?: any;
  risk?: any;
  strategy?: any;
  forecast?: any;
  tasks?: any;
  context?: any;
  sources?: string[];
  data_source?: string;
  generatedAt?: string;
  validFrom?: string;
  validTo?: string;
  runId?: string;
  modelVersion?: string;
  featureVersion?: string;
  dataVersion?: string;
  updatedAt?: string;
  isStale?: boolean;
  staleReason?: string;
  available?: boolean;
  loadedAt: string;
  partialErrors: string[];
}

function normalizeSeries(series: any[] = []) {
  return series.map((item) => ({
    ...item,
    price: item.price ?? item.predicted_price,
    load: item.load ?? item.predicted_load,
    risk_probability: item.risk_probability ?? item.spike_risk_probability,
    lower: item.lower ?? item.confidence_low,
    upper: item.upper ?? item.confidence_high
  }));
}

function normalizeForecast(payload: any) {
  const riskChart = payload?.risk_chart || {};
  const fallback = payload?.forecast || {};
  const series = normalizeSeries(riskChart.series || fallback.series || []);
  return {
    ...fallback,
    available: riskChart.available ?? fallback.available ?? Boolean(series.length),
    data_source: riskChart.data_source || fallback.data_source || 'postgresql',
    unit: riskChart.unit || fallback.unit || '元/kWh',
    series,
    summary: riskChart.summary || fallback.summary || {},
    windows: riskChart.windows || fallback.windows || { high_risk: riskChart.risk_windows || [] }
  };
}

function normalizeKpi(payload: any) {
  const items = (payload?.kpis || payload?.kpi?.items || []).map((item: any) => item?.key === 'strategy_revenue'
    ? {
        ...item,
        key: 'strategy_spread',
        title: '预测峰谷价差',
        unit: '元/kWh',
        status: payload?.meta?.is_stale ? 'warning' : item.status,
        trend_label: '由绑定预测曲线计算，不代表收益或结算结果'
      }
    : item);
  return {
    ...(payload?.kpi || {}),
    items,
    context: {
      ...(payload?.kpi?.context || {}),
      forecast_confidence: payload?.model_status || payload?.kpi?.context?.forecast_confidence || {},
      data_health: payload?.data_health || payload?.kpi?.context?.data_health || {},
      tasks: payload?.task_reminders?.health || payload?.kpi?.context?.tasks || {}
    }
  };
}

function normalizeStrategy(payload: any) {
  const summary = payload?.strategy_summary || {};
  const items = payload?.ai_suggestions || payload?.strategy?.items || [];
  return {
    ...(payload?.strategy || {}),
    data_source: summary.data_source || payload?.strategy?.data_source || 'derived_from_forecast_results',
    items,
    must_watch: payload?.strategy?.must_watch || items.filter((item: any) => String(item.risk_level || item.level || '').toLowerCase() === 'high'),
    storage_items: payload?.strategy?.storage_items || payload?.strategy?.storage || [],
    summary: {
      ...(payload?.strategy?.summary || {}),
      strategy_count: summary.generated_strategies ?? payload?.strategy?.summary?.strategy_count ?? items.length,
      must_watch_count: summary.high_price_risk_windows ?? payload?.strategy?.summary?.must_watch_count ?? 0,
      storage_count: summary.low_price_storage_windows ?? payload?.strategy?.summary?.storage_count ?? 0,
      estimated_revenue: summary.expected_spread ?? payload?.strategy?.summary?.estimated_revenue,
      estimated_revenue_unit: payload?.strategy?.summary?.estimated_revenue_unit || '元/kWh 价差',
      estimated_revenue_note: payload?.strategy?.summary?.estimated_revenue_note || '由绑定预测曲线派生，不代表收益'
    }
  };
}

function normalizeRisk(payload: any) {
  const riskChart = payload?.risk_chart || {};
  const fallback = payload?.risk || {};
  const riskWindows = riskChart.risk_windows || fallback.high_risk_windows || [];
  return {
    ...fallback,
    data_source: fallback.data_source || riskChart.data_source || 'derived_from_forecast_results',
    risk_level: fallback.risk_level || riskChart.summary?.risk_level,
    high_risk_count: fallback.high_risk_count ?? riskChart.summary?.high_risk_count ?? riskWindows.length,
    medium_risk_count: fallback.medium_risk_count ?? riskChart.summary?.medium_risk_count ?? 0,
    high_risk_windows: riskWindows,
    alerts: fallback.alerts || (payload?.ai_suggestions || []).slice(0, 3)
  };
}

function normalizeTasks(payload: any) {
  const reminders = payload?.task_reminders || {};
  return {
    ...(payload?.tasks || {}),
    data_source: reminders.data_source || payload?.tasks?.data_source || 'postgresql.task_runs',
    items: reminders.items || payload?.tasks?.items || [],
    reminders: reminders.reminders || payload?.tasks?.reminders || reminders.items || [],
    health: reminders.health || payload?.tasks?.health || {
      running_task_count: reminders.summary?.running,
      pending_task_count: reminders.summary?.queued,
      failed_task_count: reminders.summary?.failed_or_timeout,
      timeout_task_count: 0
    }
  };
}

export async function loadHomeDashboard(): Promise<HomeDashboardData> {
  try {
    const payload = await api.dashboardOverview();
    const meta = payload?.meta || {};
    return {
      kpi: normalizeKpi(payload),
      risk: normalizeRisk(payload),
      strategy: normalizeStrategy(payload),
      forecast: normalizeForecast(payload),
      tasks: normalizeTasks(payload),
      context: payload?.context,
      sources: payload?.sources || [],
      data_source: payload?.data_source,
      generatedAt: meta.generated_at || payload?.generated_at,
      validFrom: meta.valid_from,
      validTo: meta.valid_to,
      runId: meta.run_id || payload?.run_id,
      modelVersion: meta.model_version,
      featureVersion: meta.feature_version,
      dataVersion: meta.data_version,
      isStale: Boolean(meta.is_stale || ['historical', 'stale'].includes(String(meta.freshness_status || ''))),
      staleReason: meta.staleness_reason || meta.stale_reason || '',
      updatedAt: meta.updated_at || payload?.generated_at,
      available: meta.availability ? meta.availability !== 'unavailable' : Boolean(payload?.kpis?.length || payload?.risk_chart?.series?.length),
      loadedAt: payload?.loadedAt || payload?.generated_at || new Date().toISOString(),
      partialErrors: payload?.partialErrors || payload?.partial_errors || []
    };
  } catch (error) {
    return {
      loadedAt: new Date().toISOString(),
      partialErrors: [`dashboard_overview: ${error instanceof Error ? error.message : String(error || '接口请求失败')}`]
    };
  }
}
