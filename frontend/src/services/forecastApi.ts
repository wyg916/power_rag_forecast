import { api } from '../api';
import { errorMessage, withServiceState } from './serviceState';

const PRICE_KEYS = ['price', 'predicted_price', 'corrected_predicted_price', 'forecast_price', 'da_price'];

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
  return text.length >= 10 ? text.slice(0, 10) : '';
}

function hourText(value: unknown, fallback = '--') {
  const text = String(value || '');
  if (text.length >= 16) return text.slice(11, 16);
  return text || fallback;
}

function nextHourLabel(value: unknown) {
  const text = String(value || '');
  const hour = text.length >= 13 ? Number(text.slice(11, 13)) : Number.NaN;
  return Number.isFinite(hour) ? `${String((hour + 1) % 24).padStart(2, '0')}:00` : '--';
}

function readPrice(row: any): number | null {
  for (const key of PRICE_KEYS) {
    const value = toNumber(row?.[key]);
    if (value != null) return value;
  }
  return null;
}

function readObservedPrice(row: any): number | null {
  for (const key of ['actual_price', 'clearing_price', 'market_price', 'price']) {
    const value = toNumber(row?.[key]);
    if (value != null) return value;
  }
  return null;
}

function riskLabel(level?: string) {
  const raw = String(level || '').toLowerCase();
  if (raw.includes('high') || raw.includes('高')) return '高';
  if (raw.includes('medium') || raw.includes('中')) return '中';
  if (raw.includes('low') || raw.includes('低')) return '低';
  return '待接入';
}

function statusFromRisk(level?: string) {
  const risk = riskLabel(level);
  if (risk === '高') return 'danger';
  if (risk === '中') return 'warning';
  return risk === '低' ? 'success' : 'default';
}

function rangeLabel(items: any[] = []) {
  if (!items.length) return '--';
  const normalized = items
    .map((item) => ({
      datetime: String(item.datetime || item.forecast_datetime || item.target_hour || ''),
      time: item.time || hourText(item.datetime || item.forecast_datetime || item.target_hour)
    }))
    .filter((item) => item.time && item.time !== '--')
    .sort((a, b) => a.datetime.localeCompare(b.datetime));
  const times = normalized.map((item) => item.time);
  if (!times.length) return '--';
  if (times.length === 1) return times[0];
  const hours = times.map((time) => Number(String(time).slice(0, 2)));
  const contiguous = hours.every((hour, index) => index === 0 || hour === (hours[index - 1] + 1) % 24);
  return contiguous ? `${times[0]}-${times[times.length - 1]}` : times.join('、');
}

function buildSeries(forecast24h: any, latest: any) {
  const rawSeries = Array.isArray(forecast24h?.series) && forecast24h.series.length
    ? forecast24h.series
    : (Array.isArray(latest?.records) ? latest.records.slice(0, 24) : []);
  const prices = rawSeries.map(readPrice).filter((value): value is number => value != null);
  const derivedFields = new Set<string>(forecast24h?.quality?.derived_fields || []);
  const intervalIsDerived = derivedFields.has('confidence_interval');
  const series = rawSeries.map((row: any, index: number) => {
    const price = readPrice(row);
    if (price == null) return null;
    const lower = toNumber(row.lower ?? row.prediction_lower ?? row.p10_price);
    const upper = toNumber(row.upper ?? row.prediction_upper ?? row.p90_price);
    return {
      key: String(index),
      index,
      datetime: row.datetime || row.forecast_datetime,
      time: row.time || hourText(row.datetime || row.forecast_datetime, `${String(index).padStart(2, '0')}:00`),
      value: price,
      lower: intervalIsDerived ? null : lower,
      upper: intervalIsDerived ? null : upper,
      intervalAvailable: !intervalIsDerived && lower != null && upper != null,
      intervalReason: intervalIsDerived
        ? '后端标记为派生区间，不作为正式置信区间展示'
        : lower == null || upper == null ? '接口未返回正式置信区间' : '',
      load: toNumber(row.load ?? row.forecast_load),
      riskProbability: toNumber(row.risk_probability ?? row.spike_risk_prob),
      riskLevel: row.risk_level || (
        toNumber(row.risk_probability ?? row.spike_risk_prob) == null
          ? 'unavailable'
          : Number(row.risk_probability ?? row.spike_risk_prob) >= 0.5 ? 'high' : 'low'
      )
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

function confidenceFrom(prediction: any) {
  const direct = toNumber(prediction?.model_confidence ?? prediction?.confidence);
  if (direct != null) return { value: direct > 1 ? direct : direct * 100, source: 'api_prediction_latest' };
  return { value: null, source: 'api_prediction_confidence_unavailable' };
}

function adviceForHour(strategy: any, datetime: unknown) {
  const target = String(datetime || '').slice(0, 16).replace('T', ' ');
  const items = Array.isArray(strategy?.items) ? strategy.items : [];
  const match = items.find((item: any) => String(item.target_hour || '').slice(0, 16).replace('T', ' ') === target);
  return {
    action: match?.advice_text || '待接入',
    source: match ? `api_strategy_today:${match.advice_type || 'advice'}` : 'api_strategy_today_unavailable'
  };
}

function aggregateHistoryByHour(records: any[] = []) {
  const buckets = new Map<number, number[]>();
  records.forEach((row) => {
    const price = readObservedPrice(row);
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

function buildComparison(series: any[], previousForecast: any, marketHistory: any) {
  const latest = series.map((item) => Number(item.value));
  const historyMean = aggregateHistoryByHour(marketHistory?.records || []);
  const previousRows = Array.isArray(previousForecast?.records) ? previousForecast.records : [];
  const previous = previousRows.length === 24
    ? previousRows.map((row: any) => readPrice(row))
    : Array.from({ length: series.length }, () => null);
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
    previousAvailable: previousRows.length === 24,
    previousRunId: previousForecast?.run_id || '',
    previousUnavailableReason: previousRows.length === 24 ? '' : '当前只有一个成功预测批次，无法形成真实上一批次对比。',
    historyRecordCount: (marketHistory?.records || []).length,
    source: marketHistory?.available ? 'api_market_history' : 'api_market_history_empty',
    derivedSource: previousRows.length === 24 ? 'api_forecast_previous_success_run' : 'api_forecast_previous_run_unavailable'
  };
}

function buildDataHealth(dataStatus: any, forecast24h: any, dataQuality: any) {
  const sources = dataStatus?.sources || [];
  const summary = dataQuality?.summary || {};
  const exceptionCount = toNumber(summary.exception_count)
    ?? sources.filter((item: any) => !['正常', 'success', 'ok'].includes(String(item.status || '').toLowerCase())).length;
  const missingCount = Number(forecast24h?.quality?.missing_price_count || 0) + Number(forecast24h?.quality?.missing_load_count || 0);
  const score = toNumber(summary.avg_check_pass_rate);
  const sourceUpdatedTimes = sources.map((item: any) => String(item.updated_at || '')).filter(Boolean).sort();
  return {
    score,
    exceptionCount,
    missingCount,
    delayCount: 0,
    sourceCount: sources.length,
    updatedAt: dataQuality?.generated_at || dataQuality?.meta?.generated_at || sourceUpdatedTimes.at(-1) || '',
    status: score == null ? '待接入' : dataQuality?.is_stale ? '已过期' : score >= 90 ? '正常' : '关注',
    staleReason: dataQuality?.stale_reason || dataQuality?.meta?.stale_reason || '',
    generatedAt: dataQuality?.generated_at || dataQuality?.meta?.generated_at || '',
    sources,
    dataSource: dataQuality?.data_source || (sources.length ? 'derived_from_api_data_status' : 'api_data_status_empty')
  };
}

export async function getForecastCenterData() {
  const partialErrors: string[] = [];
  const requestErrors: unknown[] = [];
  const safe = async <T>(label: string, loader: () => Promise<T>): Promise<T | null> => {
    try {
      return await loader();
    } catch (error) {
      requestErrors.push(error);
      partialErrors.push(`${label}: ${errorMessage(error)}`);
      return null;
    }
  };

  const [forecast24h, latest, prediction, detail, history, risk, strategy, dataStatus, dataQuality, models, modelExplain, backtestSummary, featureSchema, leakageCheck, retrainSuggestion, forecastRuns] = await Promise.all([
    safe('forecast24h', api.forecast24h),
    safe('forecastLatest', api.forecastLatest),
    safe('predictionLatest', () => api.predictionLatest()),
    safe('predictionDetail', () => api.predictionDetail()),
    safe('marketHistory', () => api.marketHistory()),
    safe('riskSummary', api.riskSummary),
    safe('strategyToday', api.strategyToday),
    safe('dataStatus', api.dataStatus),
    safe('dataQuality', api.dataQuality),
    safe('models', api.models),
    safe('modelExplain', () => api.modelExplain()),
    safe('modelBacktestSummary', api.modelBacktestSummary),
    safe('modelFeatureSchema', api.modelFeatureSchema),
    safe('modelLeakageCheck', api.modelLeakageCheck),
    safe('retrainSuggestion', api.retrainSuggestion),
    safe('forecastRuns', () => api.forecastRuns('success', 3))
  ]);

  const { series, derivedFields } = buildSeries(forecast24h, latest);
  const currentRunId = forecast24h?.run_id || latest?.run_id || forecast24h?.meta?.run_id || '';
  const previousRun = (forecastRuns?.items || []).find((item: any) => item.run_id !== currentRunId && item.status === 'success' && Number(item.record_count) === 24);
  const previousForecast = previousRun
    ? await safe('previousForecastResults', () => api.forecastRunResults(previousRun.run_id))
    : null;
  const summary = summarize(series, forecast24h?.summary || latest?.summary || prediction || {});
  const confidence = confidenceFrom(prediction);
  const comparison = buildComparison(series, previousForecast, history);
  const dataHealth = buildDataHealth(dataStatus, forecast24h, dataQuality);
  const lowWindow = (forecast24h?.windows?.low_price || []).length
    ? forecast24h.windows.low_price
    : [...series].sort((a, b) => a.value - b.value).slice(0, 3);
  const highWindow = (forecast24h?.windows?.high_risk || forecast24h?.windows?.high_price || []).length
    ? (forecast24h.windows.high_risk || forecast24h.windows.high_price)
    : [...series].sort((a, b) => b.value - a.value).slice(0, 5);
  const detailRows = series.map((item) => {
    const riskText = riskLabel(item.riskLevel);
    const advice = adviceForHour(strategy, item.datetime);
    return {
      key: item.key,
      time: `${item.time}-${nextHourLabel(item.datetime)}`,
      price: fmt(item.value),
      risk: riskText,
      status: statusFromRisk(item.riskLevel),
      action: advice.action,
      actionSource: advice.source,
      confidence: confidence.value == null ? '--' : Math.round(confidence.value),
      riskProbability: item.riskProbability,
      intervalAvailable: item.intervalAvailable,
      interval: item.intervalAvailable ? `${fmt(item.lower)} - ${fmt(item.upper)}` : item.intervalReason,
      source: 'api_forecast_24h'
    };
  });

  const activeModel = { ...(models?.active || {}), ...(modelExplain?.active_model || {}) };
  const sourceMeta = forecast24h?.meta || latest?.meta || prediction?.meta || {};
  const freshnessStatus = sourceMeta.freshness_status
    || (sourceMeta.availability === 'unavailable' ? 'unavailable' : sourceMeta.is_stale ? 'stale' : series.length ? 'current' : 'unavailable');
  const forecastBatchLabel = freshnessStatus === 'unavailable'
    ? '预测批次暂不可用'
    : sourceMeta.is_stale || freshnessStatus === 'historical' || freshnessStatus === 'stale'
      ? '历史预测批次'
      : '当前可用预测批次';
  const seriesValues = series.map((item: any) => Number(item.value)).filter(Number.isFinite);
  const seriesMean = seriesValues.length ? seriesValues.reduce((sum: number, value: number) => sum + value, 0) / seriesValues.length : null;
  const seriesStd = seriesMean == null
    ? null
    : Math.sqrt(seriesValues.reduce((sum: number, value: number) => sum + (value - seriesMean) ** 2, 0) / seriesValues.length);
  const peakVolatility = seriesMean == null || seriesStd == null || seriesMean === 0
    ? null
    : Number((seriesStd / Math.abs(seriesMean) * 100).toFixed(1));
  const metrics = [
    { key: 'max', title: '最高预测价', value: fmt(summary.maxPrice), unit: '元/kWh', note: `预测时点 ${hourText(summary.maxHour)}`, tone: 'orange', sourceLabel: forecastBatchLabel },
    { key: 'min', title: '最低预测价', value: fmt(summary.minPrice), unit: '元/kWh', note: `预测时点 ${hourText(summary.minHour)}`, tone: 'green', sourceLabel: forecastBatchLabel },
    { key: 'avg', title: '预测均价', value: fmt(summary.avgPrice), unit: '元/kWh', note: '绑定 24 小时预测均值', tone: 'blue', sourceLabel: forecastBatchLabel },
    { key: 'spread', title: '预测峰谷价差', value: fmt(summary.peakValleySpread), unit: '元/kWh', note: '由绑定预测曲线计算', tone: 'red', sourceLabel: forecastBatchLabel },
    { key: 'confidence', title: '模型可信度', value: confidence.value == null ? '--' : confidence.value.toFixed(1), unit: '%', note: confidence.source === 'api_prediction_latest' ? '模型接口返回' : '模型接口未返回可信度', tone: 'green', sourceLabel: forecastBatchLabel },
  ];

  return withServiceState({
    available: Boolean(series.length && freshnessStatus !== 'unavailable'),
    date: dateText(sourceMeta.valid_from || forecast24h?.summary?.forecast_start || summary.maxHour),
    region: forecast24h?.region || forecast24h?.market || prediction?.market || '',
    modelVersion: activeModel.model_version || activeModel.version || sourceMeta.model_version || '',
    featureVersion: activeModel.feature_version || sourceMeta.feature_version || featureSchema?.feature_version || '',
    dataSource: sourceMeta.source_type || latest?.source_type || 'unavailable',
    unit: forecast24h?.unit || '元/kWh',
    runId: currentRunId,
    generatedAt: forecast24h?.generated_at || latest?.generated_at || sourceMeta.generated_at || '',
    updatedAt: sourceMeta.updated_at || forecast24h?.generated_at || latest?.generated_at || '',
    validFrom: sourceMeta.valid_from || forecast24h?.summary?.forecast_start || '',
    validTo: sourceMeta.valid_to || forecast24h?.summary?.forecast_end || '',
    dataVersion: sourceMeta.data_version || '',
    freshnessStatus,
    isStale: Boolean(sourceMeta.is_stale),
    staleReason: sourceMeta.staleness_reason || sourceMeta.stale_reason || '',
    series,
    summary,
    metrics,
    detailRows,
    lowWindow,
    highWindow,
    lowWindowDerived: !(forecast24h?.windows?.low_price || []).length,
    highWindowDerived: !(forecast24h?.windows?.high_risk || forecast24h?.windows?.high_price || []).length,
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
      index: summary.avgPrice ? Math.min(100, Math.round(Number(summary.peakValleySpread || 0) / Math.max(Math.abs(Number(summary.avgPrice)), 0.0001) * 100)) : 0,
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
      derivedFields,
      confidenceIntervalAvailable: series.every((item: any) => item.intervalAvailable),
      confidenceIntervalReason: series.every((item: any) => item.intervalAvailable)
        ? ''
        : derivedFields.includes('confidence_interval')
          ? '/api/forecast/24h 将区间标记为 derived，页面未将其作为正式置信区间展示。'
          : 'forecast_results 未提供正式上下界字段，前端未合成。'
    },
    historyApi: history,
    predictionDetail: detail
  }, {
    dataSource: sourceMeta.source_type || latest?.source_type || 'unavailable',
    empty: !series.length || freshnessStatus === 'unavailable',
    error: requestErrors.length && !series.length ? requestErrors[0] : undefined,
    mockFallback: false,
    partialErrors
  });
}
