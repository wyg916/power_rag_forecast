import { api } from '../api';
import { formatReportValueLines } from './reportValue';
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

export function normalizeReport(item: any) {
  const summary = item?.summary || {};
  const metadata = item?.metadata || {};
  const meta = item?.meta || {};
  const source = summary?.source || metadata?.source || {};
  const executiveSummary = summary?.executive_summary || {};
  const explicitSummary = summary?.summary || summary?.content || summary?.conclusion;
  const id = item?.report_id || item?.run_id || 'latest';
  return {
    ...item,
    report_id: id,
    title: item?.title || summary?.title || `${typeText(item?.report_type)}报告`,
    statusText: statusText(item?.status),
    typeText: typeText(item?.report_type),
    generated_at: item?.generated_at || item?.updated_at || item?.created_at,
    batch: metadata?.batch || item?.run_id || '--',
    validFrom: source?.forecast_start_at || metadata?.forecast_start_at || meta?.valid_from || null,
    validTo: source?.forecast_end_at || metadata?.forecast_end_at || meta?.valid_to || null,
    data_window: source?.forecast_start_at && source?.forecast_end_at
      ? `${String(source.forecast_start_at).slice(0, 16)} 至 ${String(source.forecast_end_at).slice(0, 16)}`
      : metadata?.data_window || metadata?.report_date || summary?.report_date || '--',
    modelVersion: metadata?.model_version || source?.model_version || meta?.model_version || '--',
    featureVersion: metadata?.feature_version || source?.feature_version || meta?.feature_version || '--',
    reportSchemaVersion: metadata?.report_schema_version || '--',
    dataVersion: source?.result_hash || metadata?.result_hash || metadata?.schema_hash || meta?.data_version || '--',
    isStale: Boolean(metadata?.is_stale || source?.is_stale || meta?.is_stale),
    staleReason: metadata?.stale_reason || source?.stale_reason || meta?.staleness_reason || meta?.stale_reason || '',
    sourceLabel: metadata?.is_stale || source?.is_stale || meta?.is_stale ? '历史报告事实' : '报告事实记录',
    availability: meta?.availability || (item?.available === false ? 'unavailable' : 'available'),
    latestReview: item?.latest_review || {},
    metrics: summary?.metrics || summary?.kpis || executiveSummary,
    risks: normalizeRisks(summary),
    summaryText:
      (explicitSummary ? formatReportValueLines(explicitSummary).join('\n') : '') ||
      (Object.keys(executiveSummary).length
        ? `共 ${executiveSummary.record_count ?? '--'} 个预测时点，平均电价 ${executiveSummary.average_price ?? '--'} 元/MWh，最高 ${executiveSummary.maximum_price ?? '--'}，最低 ${executiveSummary.minimum_price ?? '--'}；尖峰风险 ${executiveSummary.spike_risk_hour_count ?? '--'} 个时段，负电价 ${executiveSummary.negative_price_hour_count ?? '--'} 个时段。`
        : '') ||
      '报告事实未提供结构化摘要。'
  };
}

function buildPreviewCurve(forecast: any) {
  const rows = Array.isArray(forecast?.records) ? forecast.records : [];
  return rows.slice(0, 24).flatMap((row: any, index: number) => {
    const value = Number(row.predicted_price ?? row.corrected_predicted_price);
    if (!Number.isFinite(value)) return [];
    const datetime = String(row.forecast_datetime || row.datetime || '');
    return [{
      time: datetime.length >= 16 ? datetime.slice(11, 16) : `${String(row.hour ?? index).padStart(2, '0')}:00`,
      value
    }];
  });
}

function buildPreviewMetrics(report: any) {
  const metrics = report?.metrics || {};
  return [
    { label: '预测时点数', value: metricValue(metrics, ['record_count'], '--'), unit: '个' },
    { label: '最高预测价', value: metricValue(metrics, ['max_price', 'highest_price', 'maximum_price'], '--'), unit: '元/MWh' },
    { label: '最低预测价', value: metricValue(metrics, ['min_price', 'lowest_price', 'minimum_price'], '--'), unit: '元/MWh' },
    { label: '平均预测价', value: metricValue(metrics, ['avg_price', 'average_price'], '--'), unit: '元/MWh' },
    { label: '尖峰风险时点', value: metricValue(metrics, ['spike_risk_hour_count', 'high_risk_count'], '--'), unit: '个' }
  ];
}

export async function getReportFacts(report: any, capabilities: { canReview?: boolean } = {}): Promise<any> {
  if (!report?.report_id) return { report, previewCurve: [], previewMetrics: [], risks: [], reviews: [] };
  const [detailPayload, forecast, reviewsPayload] = await Promise.all([
    api.reportDetail(report.report_id),
    report?.run_id ? api.forecastRunResults(report.run_id) : Promise.resolve({ records: [] }),
    capabilities.canReview ? api.reportReviews(report.report_id) : Promise.resolve({ reviews: [] })
  ]);
  const detail = normalizeReport(detailPayload?.report_id ? { ...report, ...detailPayload } : report);
  return {
    report: detail,
    previewCurve: buildPreviewCurve(forecast),
    previewMetrics: buildPreviewMetrics(detail),
    risks: detail.risks || [],
    reviews: reviewsPayload?.reviews || []
  };
}

export async function getReportCenterData(
  params: Record<string, any> = {},
  capabilities: { canReview?: boolean } = {}
): Promise<any> {
  const partialErrors: string[] = [];
  const [list, summary, latest] = await Promise.all([
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
    })
  ]);

  const reports = (list.items || []).map(normalizeReport);
  const latestReport = latest?.report_id || latest?.run_id ? normalizeReport(latest) : null;
  const hasActiveFilter = Boolean(params.keyword || params.report_type || params.status);
  const activeReport = reports[0] || (!hasActiveFilter ? latestReport : null);
  let facts = { report: activeReport, previewCurve: [] as any[], previewMetrics: buildPreviewMetrics(activeReport), risks: activeReport?.risks || [], reviews: [] as any[] };
  if (activeReport) {
    try {
      facts = await getReportFacts(activeReport, capabilities);
    } catch (error) {
      partialErrors.push(error instanceof Error ? error.message : String(error));
    }
  }

  return withServiceState(
    {
      dataSource: list?.meta?.source_type || latest?.meta?.source_type || list.source || latest?.source || 'unavailable',
      reports,
      total: list.total || reports.length,
      summary,
      activeReport: facts.report,
      latestReport,
      previewCurve: facts.previewCurve,
      previewMetrics: facts.previewMetrics,
      risks: facts.risks,
      reviews: facts.reviews,
      generatedAt: facts.report?.generated_at || list?.meta?.generated_at,
      validFrom: facts.report?.validFrom || list?.meta?.valid_from,
      validTo: facts.report?.validTo || list?.meta?.valid_to,
      runId: facts.report?.run_id || list?.meta?.run_id,
      isStale: Boolean(facts.report?.isStale ?? list?.meta?.is_stale),
      staleReason: facts.report?.staleReason || list?.meta?.staleness_reason || list?.meta?.stale_reason || '',
      partialErrors
    },
    {
      empty: !reports.length && !latestReport,
      mockFallback: false,
      partialErrors
    }
  );
}
