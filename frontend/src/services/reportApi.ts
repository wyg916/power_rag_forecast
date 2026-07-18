import { api } from '../api';
import { withServiceState } from './serviceState';

function statusText(status: string) {
  const value = String(status || '').toLowerCase();
  if (value === 'published') return '已发布';
  if (value === 'approved') return '已通过';
  if (value === 'rejected') return '驳回';
  if (value === 'reviewing') return '审核中';
  if (value === 'archived') return '已归档';
  return '待审核';
}

function typeText(type: string) {
  const value = String(type || '').toLowerCase();
  if (value.includes('operation') || value.includes('decision')) return '运营决策报告';
  if (value.includes('week')) return '周报';
  if (value.includes('month')) return '月报';
  if (value.includes('special')) return '专项';
  return '日报';
}

function metricValue(metrics: any, keys: string[], fallback = '--') {
  for (const key of keys) {
    if (metrics?.[key] !== undefined && metrics?.[key] !== null && metrics?.[key] !== '') return metrics[key];
  }
  return fallback;
}

function normalizeRisks(summary: any) {
  const risks =
    summary?.risks ||
    summary?.risk_periods ||
    summary?.riskRows ||
    (Array.isArray(summary?.decision_support)
      ? summary.decision_support.map((item: any, index: number) => {
          const evidence = item?.evidence || {};
          const evidenceHours = Array.isArray(evidence?.hours) ? evidence.hours : [];
          return {
            key: item?.key || index + 1,
            period: evidenceHours[0] || evidence?.forecast_end_at || summary?.report_date || '--',
            level: item?.priority || '--',
            type: item?.reason || '--',
            impact: item?.priority || '--',
            action: item?.action || '--'
          };
        })
      : []);
  if (!Array.isArray(risks)) return [];
  return risks.map((item: any, index: number) => ({
    key: item.key || item.id || index + 1,
    period: item.period || item.time_range || item.time || '--',
    level: item.level || item.risk_level || '--',
    type: item.type || item.risk_type || item.category || '--',
    impact: item.impact || item.impact_level || '--',
    action: item.action || item.suggestion || item.recommendation || '--'
  }));
}

function normalizeReport(item: any) {
  const summary = item?.summary || {};
  const metadata = item?.metadata || {};
  const executiveSummary = summary?.executive_summary || {};
  const id = item?.report_id || item?.run_id || 'latest';
  return {
    ...item,
    report_id: id,
    title: item?.title || summary?.title || `${typeText(item?.report_type)}报告`,
    statusText: statusText(item?.status),
    typeText: typeText(item?.report_type),
    generated_at: item?.generated_at || item?.updated_at || item?.created_at,
    batch: metadata?.batch || item?.run_id || 'latest',
    data_window: metadata?.data_window || metadata?.report_date || summary?.report_date || '--',
    metrics: summary?.metrics || summary?.kpis || executiveSummary,
    risks: normalizeRisks(summary),
    summaryText:
      summary?.summary ||
      summary?.content ||
      summary?.conclusion ||
      (Object.keys(executiveSummary).length
        ? `共 ${executiveSummary.record_count ?? '--'} 个预测时点，平均电价 ${executiveSummary.average_price ?? '--'} 元/MWh，最高 ${executiveSummary.maximum_price ?? '--'}，最低 ${executiveSummary.minimum_price ?? '--'}；尖峰风险 ${executiveSummary.spike_risk_hour_count ?? '--'} 个时段，负电价 ${executiveSummary.negative_price_hour_count ?? '--'} 个时段。`
        : '') ||
      '后端报告结果未返回结构化摘要，页面保留报告预览结构。'
  };
}

function buildPreviewCurve(forecast: any) {
  const rows = Array.isArray(forecast?.records) ? forecast.records : [];
  return rows.slice(0, 24).map((row: any, index: number) => ({
    time: `${String(row.hour ?? index).padStart(2, '0')}:00`,
    value: Number(row.predicted_price ?? row.corrected_predicted_price ?? 0),
    actual: Number(row.actual_price ?? row.predicted_price ?? row.corrected_predicted_price ?? 0)
  }));
}

export async function getReportCenterData(params: Record<string, any> = {}): Promise<any> {
  const partialErrors: string[] = [];
  const [list, summary, latest, forecast] = await Promise.all([
    api.reports({ page: 1, page_size: 20, ...params }).catch((error) => {
      partialErrors.push(error instanceof Error ? error.message : String(error));
      return { items: [], total: 0 };
    }),
    api.reportSummary().catch((error) => {
      partialErrors.push(error instanceof Error ? error.message : String(error));
      return {};
    }),
    api.reportLatest().catch((error) => {
      partialErrors.push(error instanceof Error ? error.message : String(error));
      return null;
    }),
    api.forecastLatest().catch((error) => {
      partialErrors.push(error instanceof Error ? error.message : String(error));
      return null;
    })
  ]);

  const reports = (list.items || []).map(normalizeReport);
  const latestReport = latest?.report_id || latest?.run_id ? normalizeReport(latest) : null;
  const activeReport = reports[0] || latestReport;
  const metrics = activeReport?.metrics || {};

  return withServiceState(
    {
      dataSource: list.source || latest?.source || 'report_api',
      reports,
      total: list.total || reports.length,
      summary,
      activeReport,
      latestReport,
      previewCurve: buildPreviewCurve(forecast),
      previewMetrics: [
        { label: '全网用电量', value: metricValue(metrics, ['total_load', 'energy', 'total_energy'], '--'), unit: '万kWh', change: '+7.21%' },
        { label: '最高电价', value: metricValue(metrics, ['max_price', 'highest_price', 'maximum_price'], '--'), unit: '元/MWh', change: '+18.65%' },
        { label: '最低电价', value: metricValue(metrics, ['min_price', 'lowest_price', 'minimum_price'], '--'), unit: '元/MWh', change: '-12.38%' },
        { label: '平均电价', value: metricValue(metrics, ['avg_price', 'average_price'], '--'), unit: '元/MWh', change: '+3.21%' },
        { label: '预测准确率', value: metricValue(metrics, ['accuracy', 'confidence'], '--'), unit: '%', change: '+2.40%' }
      ],
      risks: activeReport?.risks || [],
      partialErrors
    },
    {
      empty: !reports.length && !latestReport,
      mockFallback: false,
      partialErrors
    }
  );
}
