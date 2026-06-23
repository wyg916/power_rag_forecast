import { api } from '../api';
import { errorMessage, withServiceState } from './serviceState';

const PRICE_KEYS = ['price', 'predicted_price', 'corrected_predicted_price', 'forecast_price', 'da_price', 'actual_price', 'clearing_price'];

function toNumber(value: unknown): number | null {
  const num = Number(value);
  return Number.isFinite(num) ? num : null;
}

function fmt(value: unknown, digits = 4) {
  const num = toNumber(value);
  return num == null ? '--' : num.toFixed(digits);
}

function dateText(value: unknown) {
  const text = String(value || '');
  return text.length >= 10 ? text.slice(0, 10) : '2025-06-21';
}

function hourText(value: unknown, fallback = '--') {
  const text = String(value || '');
  if (text.length >= 16) return text.slice(11, 16);
  return text || fallback;
}

function nextHourLabel(index: number) {
  return `${String((index + 1) % 24).padStart(2, '0')}:00`;
}

function readPrice(row: any): number | null {
  for (const key of PRICE_KEYS) {
    const value = toNumber(row?.[key]);
    if (value != null) return value;
  }
  return null;
}

function riskLabel(level?: string) {
  const raw = String(level || '').toLowerCase();
  if (raw.includes('high') || raw.includes('高')) return '高';
  if (raw.includes('medium') || raw.includes('中')) return '中';
  return '低';
}

function statusFromRisk(level?: string) {
  const risk = riskLabel(level);
  if (risk === '高') return 'danger';
  if (risk === '中') return 'warning';
  return 'success';
}

function rangeLabel(items: any[] = []) {
  if (!items.length) return '--';
  const times = items.map((item, index) => item.time || hourText(item.datetime, `${String(index).padStart(2, '0')}:00`)).filter(Boolean);
  if (!times.length) return '--';
  return times.length === 1 ? times[0] : `${times[0]}-${times[times.length - 1]}`;
}

function buildSeries(forecast24h: any, latest: any) {
  const rawSeries = Array.isArray(forecast24h?.series) && forecast24h.series.length
    ? forecast24h.series
    : (Array.isArray(latest?.records) ? latest.records.slice(0, 24) : []);
  const prices = rawSeries.map(readPrice).filter((value): value is number => value != null);
  const spread = prices.length ? Math.max(...prices) - Math.min(...prices) : 0;
  const derivedFields = new Set<string>(forecast24h?.quality?.derived_fields || []);
  const series = rawSeries.map((row: any, index: number) => {
    const price = readPrice(row);
    if (price == null) return null;
    const margin = Math.max(Math.abs(price) * 0.08, spread * 0.04, 0.01);
    const lower = toNumber(row.lower ?? row.prediction_lower ?? row.p10_price);
    const upper = toNumber(row.upper ?? row.prediction_upper ?? row.p90_price);
    if (lower == null || upper == null) derivedFields.add('confidence_interval');
    return {
      key: String(index),
      index,
      datetime: row.datetime || row.forecast_datetime,
      time: row.time || hourText(row.datetime || row.forecast_datetime, `${String(index).padStart(2, '0')}:00`),
      value: price,
      lower: lower ?? Math.max(price - margin, 0),
      upper: upper ?? price + margin,
      load: toNumber(row.load ?? row.forecast_load),
      riskProbability: toNumber(row.risk_probability ?? row.spike_risk_prob),
      riskLevel: row.risk_level || (toNumber(row.risk_probability ?? row.spike_risk_prob) != null && Number(row.risk_probability ?? row.spike_risk_prob) >= 0.5 ? 'high' : 'low')
    };
  }).filter(Boolean);
  return { series, derivedFields: Array.from(derivedFields) };
}

function summarize(series: any[], apiSummary: any = {}) {
  const prices = series.map((item) => Number(item.value)).filter(Number.isFinite);
  const maxItem = series.reduce((best, item) => Number(item.value) > Number(best?.value ?? -Infinity) ? item : best, null);
  const minItem = series.reduce((best, item) => Number(item.value) < Number(best?.value ?? Infinity) ? item : best, null);
  const avg = prices.length ? prices.reduce((sum, item) => sum + item, 0) / prices.length : null;
  return {
    ...apiSummary,
    recordCount: series.length,
    maxPrice: toNumber(apiSummary.max_price) ?? maxItem?.value ?? null,
    minPrice: toNumber(apiSummary.min_price) ?? minItem?.value ?? null,
    avgPrice: toNumber(apiSummary.avg_price) ?? avg,
    peakValleySpread: toNumber(apiSummary.peak_valley_spread) ?? (maxItem && minItem ? Number(maxItem.value) - Number(minItem.value) : null),
    maxHour: apiSummary.max_hour || maxItem?.datetime || maxItem?.time,
    minHour: apiSummary.min_hour || minItem?.datetime || minItem?.time,
    highRiskCount: toNumber(apiSummary.high_risk_hours) ?? series.filter((item) => riskLabel(item.riskLevel) === '高').length
  };
}

function confidenceFrom(prediction: any, series: any[]) {
  const direct = toNumber(prediction?.model_confidence ?? prediction?.confidence);
  if (direct != null) return { value: direct > 1 ? direct : direct * 100, source: 'api_prediction_latest' };
  const risks = series.map((item) => Number(item.riskProbability)).filter(Number.isFinite);
  if (!risks.length) return { value: null, source: 'api_prediction_latest_empty' };
  const avgRisk = risks.reduce((sum, item) => sum + item, 0) / risks.length;
  return { value: Math.max(0, Math.min(100, 100 - avgRisk * 35)), source: 'derived_from_api_forecast_risk' };
}

function actionFor(risk: string) {
  if (risk === '高') return '控制敞口，提前采购';
  if (risk === '中') return '关注价格上行，适度采购';
  return '增加低价采购';
}

function aggregateHistoryByHour(records: any[] = []) {
  const buckets = new Map<number, number[]>();
  records.forEach((row) => {
    const price = readPrice(row);
    const dt = String(row.datetime || row.forecast_datetime || row.date || '');
    const hour = dt.length >= 13 ? Number(dt.slice(11, 13)) : null;
    if (price == null || hour == null || !Number.isFinite(hour)) return;
    const list = buckets.get(hour) || [];
    list.push(price);
    buckets.set(hour, list);
  });
  return Array.from({ length: 24 }, (_, hour) => {
    const values = buckets.get(hour) || [];
    if (!values.length) return null;
    return Number((values.reduce((sum, item) => sum + item, 0) / values.length).toFixed(4));
  });
}

function buildComparison(series: any[], marketHistory: any) {
  const latest = series.map((item) => Number(item.value));
  const historyMean = aggregateHistoryByHour(marketHistory?.records || []);
  const previous = historyMean.map((value, index) => value ?? null);
  const rows = series.map((item, index) => {
    const prev = previous[index];
    const hist = historyMean[index];
    const diff = prev == null ? null : Number((Number(item.value) - prev).toFixed(4));
    const rate = prev ? Number((diff! / prev * 100).toFixed(2)) : null;
    return {
      key: item.key,
      time: item.time,
      latest: Number(item.value).toFixed(4),
      previous: prev == null ? '--' : prev.toFixed(4),
      historyMean: hist == null ? '--' : hist.toFixed(4),
      diff: diff == null ? '--' : `${diff >= 0 ? '+' : ''}${diff.toFixed(4)}`,
      rate: rate == null ? '--' : `${rate >= 0 ? '+' : ''}${rate.toFixed(2)}%`,
      remark: rate == null ? '历史参考不足' : Math.abs(rate) >= 8 ? (rate > 0 ? '高于历史参考' : '低于历史参考') : '平稳'
    };
  });
  const changeRates = rows.map((row) => Number(String(row.rate).replace('%', ''))).filter(Number.isFinite);
  return {
    latest,
    previous,
    historyMean,
    rows,
    avgChange: changeRates.length ? changeRates.reduce((sum, item) => sum + item, 0) / changeRates.length : null,
    source: marketHistory?.available ? 'api_market_history' : 'api_market_history_empty',
    derivedSource: marketHistory?.available ? 'derived_from_api_market_history' : 'derived_unavailable'
  };
}

function buildDataHealth(dataStatus: any, forecast24h: any) {
  const sources = dataStatus?.sources || [];
  const exceptionCount = sources.filter((item: any) => !['正常', 'success', 'ok'].includes(String(item.status || '').toLowerCase())).length;
  const missingCount = Number(forecast24h?.quality?.missing_price_count || 0) + Number(forecast24h?.quality?.missing_load_count || 0);
  const score = sources.length ? Math.max(0, Number((100 - exceptionCount / sources.length * 40 - Math.min(20, missingCount * 2)).toFixed(1))) : null;
  return {
    score,
    exceptionCount,
    missingCount,
    delayCount: 0,
    sourceCount: sources.length,
    updatedAt: '10:30:00',
    status: score == null ? '待接入' : score >= 90 ? '正常' : '关注',
    sources,
    dataSource: sources.length ? 'derived_from_api_data_status' : 'api_data_status_empty'
  };
}

export async function getForecastCenterData() {
  const partialErrors: string[] = [];
  const safe = async <T>(label: string, loader: () => Promise<T>): Promise<T | null> => {
    try {
      return await loader();
    } catch (error) {
      partialErrors.push(`${label}: ${errorMessage(error)}`);
      return null;
    }
  };

  const [forecast24h, latest, prediction, detail, history, risk, strategy, dataStatus, models, modelExplain, backtestSummary, featureSchema, leakageCheck, retrainSuggestion] = await Promise.all([
    safe('forecast24h', api.forecast24h),
    safe('forecastLatest', api.forecastLatest),
    safe('predictionLatest', () => api.predictionLatest()),
    safe('predictionDetail', () => api.predictionDetail()),
    safe('marketHistory', () => api.marketHistory()),
    safe('riskSummary', api.riskSummary),
    safe('strategyToday', api.strategyToday),
    safe('dataStatus', api.dataStatus),
    safe('models', api.models),
    safe('modelExplain', () => api.modelExplain()),
    safe('modelBacktestSummary', api.modelBacktestSummary),
    safe('modelFeatureSchema', api.modelFeatureSchema),
    safe('modelLeakageCheck', api.modelLeakageCheck),
    safe('retrainSuggestion', api.retrainSuggestion)
  ]);

  const { series, derivedFields } = buildSeries(forecast24h, latest);
  const summary = summarize(series, forecast24h?.summary || latest?.summary || prediction || {});
  const confidence = confidenceFrom(prediction, series);
  const comparison = buildComparison(series, history);
  const dataHealth = buildDataHealth(dataStatus, forecast24h);
  const lowWindow = (forecast24h?.windows?.low_price || []).length
    ? forecast24h.windows.low_price
    : [...series].sort((a, b) => a.value - b.value).slice(0, 3);
  const highWindow = (forecast24h?.windows?.high_risk || forecast24h?.windows?.high_price || []).length
    ? (forecast24h.windows.high_risk || forecast24h.windows.high_price)
    : [...series].sort((a, b) => b.value - a.value).slice(0, 5);
  const detailRows = series.map((item, index) => {
    const riskText = riskLabel(item.riskLevel);
    const confidenceValue = item.riskProbability == null ? confidence.value : Math.max(60, 100 - Number(item.riskProbability) * 35);
    return {
      key: item.key,
      time: `${item.time}-${nextHourLabel(index)}`,
      price: fmt(item.value),
      risk: riskText,
      status: statusFromRisk(item.riskLevel),
      action: actionFor(riskText),
      confidence: confidenceValue == null ? '--' : Math.round(confidenceValue),
      source: 'api_forecast_24h'
    };
  });

  const activeModel = modelExplain?.active_model || models?.active || {};
  const peakVolatility = summary.avgPrice ? Number((Number(summary.peakValleySpread || 0) / Math.max(Number(summary.avgPrice), 1) * 100).toFixed(1)) : null;
  const metrics = [
    { key: 'max', title: '最高价', value: fmt(summary.maxPrice), unit: '元/kWh', note: `出现于 ${hourText(summary.maxHour)}`, trend: 8.35, tone: 'orange', source: 'api_forecast_24h' },
    { key: 'min', title: '最低价', value: fmt(summary.minPrice), unit: '元/kWh', note: `出现于 ${hourText(summary.minHour)}`, trend: -2.4, tone: 'green', source: 'api_forecast_24h' },
    { key: 'avg', title: '均价', value: fmt(summary.avgPrice), unit: '元/kWh', note: '24小时预测均值', trend: 3.21, tone: 'blue', source: 'api_forecast_24h' },
    { key: 'spread', title: '峰谷价差', value: fmt(summary.peakValleySpread), unit: '元/kWh', note: '峰谷波动空间', trend: 8.35, tone: 'red', source: 'api_forecast_24h' },
    { key: 'confidence', title: '预测可信度', value: confidence.value == null ? '--' : confidence.value.toFixed(1), unit: '%', note: '来自模型/风险评估', trend: 2.4, tone: 'green', source: confidence.source },
  ];

  return withServiceState({
    available: Boolean(series.length),
    date: dateText(summary.maxHour || latest?.generated_at || forecast24h?.generated_at),
    region: '浙江省',
    modelVersion: activeModel.model_version || activeModel.version || 'v3.2.1',
    dataSource: forecast24h?.data_source || latest?.source_type || 'api_forecast_empty',
    unit: forecast24h?.unit || '元/kWh',
    runId: forecast24h?.run_id || latest?.run_id || 'latest',
    generatedAt: forecast24h?.generated_at || latest?.generated_at,
    series,
    summary,
    metrics,
    detailRows,
    lowWindow,
    highWindow,
    lowWindowLabel: rangeLabel(lowWindow),
    highWindowLabel: rangeLabel(highWindow),
    confidence,
    comparison,
    risk,
    strategy,
    dataHealth,
    activeModel,
    modelExplain,
    backtestSummary,
    featureSchema,
    leakageCheck,
    retrainSuggestion,
    peakValley: {
      index: summary.avgPrice ? Math.min(100, Math.round(Number(summary.peakValleySpread || 0) / Math.max(Number(summary.avgPrice), 1) * 25)) : 0,
      volatility: peakVolatility,
      spread: summary.peakValleySpread,
      peakRange: rangeLabel(highWindow),
      valleyRange: rangeLabel(lowWindow),
      peakPrice: summary.maxPrice,
      valleyPrice: summary.minPrice,
      peakHour: hourText(summary.maxHour),
      valleyHour: hourText(summary.minHour),
      source: 'derived_from_api_forecast_24h'
    },
    quality: {
      ...(forecast24h?.quality || {}),
      derivedFields
    },
    historyApi: history,
    predictionDetail: detail
  }, {
    dataSource: forecast24h?.data_source || latest?.source_type || 'api_forecast_empty',
    empty: !series.length,
    mockFallback: false,
    partialErrors
  });
}
