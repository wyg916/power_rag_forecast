import { api } from '../api';
import { withServiceState } from './serviceState';

const toNumber = (value: unknown, fallback = 0) => {
  const num = Number(value);
  return Number.isFinite(num) ? num : fallback;
};

const hourText = (value: unknown) => {
  const text = String(value || '');
  return text.length >= 16 ? text.slice(11, 16) : text || '--';
};

const statusLabel = (status?: string) => {
  const value = String(status || '').toLowerCase();
  if (value.includes('high') || value.includes('danger') || value.includes('failed')) return 'danger';
  if (value.includes('medium') || value.includes('warning') || value.includes('pending')) return 'warning';
  if (value.includes('success') || value.includes('low') || value.includes('active')) return 'success';
  return 'info';
};

export async function getDashboardData() {
  const overview = await api.dashboardOverview();
  const forecast = overview?.forecast || {};
  const risk = overview?.risk || {};
  const kpiItems = Array.isArray(overview?.kpi?.items) ? overview.kpi.items : [];
  const series = Array.isArray(forecast?.series) ? forecast.series : [];
  const taskRows = Array.isArray(overview?.tasks?.items) ? overview.tasks.items : [];
  const riskAlerts = Array.isArray(risk?.alerts) ? risk.alerts : [];
  const context = overview?.context || {};

  const metrics = kpiItems.map((item: any) => ({
    label: item.title,
    value: item.value,
    unit: item.unit,
    status: statusLabel(item.status),
    note: item.trend_label || '当前统计周期'
  }));
  const priceCurve = series.map((row: any) => ({
    time: hourText(row.datetime || row.time),
    value: toNumber(row.price),
    actual: null,
    upper: toNumber(row.upper, toNumber(row.price)),
    lower: toNumber(row.lower, toNumber(row.price)),
    load: row.load,
    riskProbability: row.risk_probability
  }));
  const risks = riskAlerts.map((item: any) => ({
    level: statusLabel(item.level),
    title: item.title || '风险提醒',
    description: item.description || item.message || '',
    time: hourText(item.target_time)
  }));
  const taskLogs = taskRows.slice(0, 5).map((row: any) => [
    row.kind || row.task_kind || row.task_name || '系统任务',
    row.status || '--',
    String(row.started_at || row.updated_at || row.created_at || '').slice(5, 16),
    row.task_id || ''
  ]);
  const operationalCards = kpiItems.map((item: any) => ({
    status: statusLabel(item.status),
    value: item.value,
    title: item.title,
    description: item.trend_label || item.data_source || ''
  }));
  const partialErrors = overview?.partialErrors || overview?.partial_errors || [];

  return withServiceState(
    {
      metrics,
      priceCurve,
      risks,
      reports: [],
      taskLogs,
      rawTasks: taskRows,
      dataFreshness: context?.data_health?.sources || [],
      taskHealth: overview?.tasks?.health || {},
      modelStatus: context?.forecast_confidence || {},
      operationalCards,
      alertSummary: [
        ...risks.map((item: any) => item.description).filter(Boolean),
        ...partialErrors
      ],
      dataSource: overview?.data_source || 'postgresql_dashboard_overview',
      overview
    },
    {
      empty: !series.length,
      mockFallback: false,
      partialErrors
    }
  );
}
