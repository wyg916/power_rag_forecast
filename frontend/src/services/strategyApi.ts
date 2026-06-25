import { api } from '../api';
import { errorMessage, withServiceState } from './serviceState';

function numberValue(value: unknown) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function hourText(value: unknown) {
  const text = String(value || '');
  return text.length >= 16 ? text.slice(11, 16) : text || '--';
}

function dateText(value: unknown) {
  const text = String(value || '');
  return text.length >= 10 ? text.slice(0, 10) : text || '--';
}

function normalizeRisk(value: unknown) {
  const text = String(value || '').toLowerCase();
  if (text.includes('high') || text.includes('紧急') || text.includes('高')) return 'high';
  if (text.includes('medium') || text.includes('中')) return 'medium';
  return 'low';
}

function compactWindows(items: any[], predicate: (item: any) => boolean) {
  return items.filter(predicate).map((item) => hourText(item.target_hour)).filter((value) => value !== '--');
}

export async function getStrategyCenterData(): Promise<any> {
  const partialErrors: string[] = [];
  const safe = async <T>(label: string, loader: () => Promise<T>): Promise<T | null> => {
    try {
      return await loader();
    } catch (error) {
      partialErrors.push(`${label}: ${errorMessage(error)}`);
      return null;
    }
  };

  const [today, latest, anomaly, config, forecast] = await Promise.all([
    safe('strategyToday', api.strategyToday),
    safe('strategyLatest', api.strategyLatest),
    safe('anomalyLatest', api.anomalyLatest),
    safe('strategyConfig', api.strategyConfig),
    safe('forecast24h', api.forecast24h)
  ]);

  const strategyItems = Array.isArray(today?.items)
    ? today.items
    : Array.isArray(latest?.items)
      ? latest.items
      : [];
  const anomalies = Array.isArray(anomaly?.items) ? anomaly.items : [];
  const forecastSeries = Array.isArray(forecast?.series) ? forecast.series : [];
  const resolvedConfig = {
    high_price_threshold: 160,
    low_price_threshold: 40,
    soc_upper: 90,
    soc_lower: 20,
    charge_power: 80,
    discharge_power: 80,
    risk_threshold: 0.5,
    auto_suggestion: true,
    ...(config || {})
  };
  const storageItems = strategyItems.filter((item: any) => String(item.scenario || '').includes('储能'));
  const reviewItems = strategyItems.filter((item: any) => String(item.advice_type || '').includes('复核'));
  const highRiskItems = strategyItems.filter((item: any) => normalizeRisk(item.risk_level) === 'high');
  const lowItems = strategyItems.filter((item: any) =>
    String(item.advice_type || '').includes('低价') || String(item.advice_type || '').includes('充电')
  );
  const chargeHours = new Set(compactWindows(storageItems, (item) => String(item.advice_type || '').includes('充电')));
  const dischargeHours = new Set(compactWindows(storageItems, (item) => String(item.advice_type || '').includes('放电')));
  const chargePower = Number(resolvedConfig.charge_power || 0);
  const dischargePower = Number(resolvedConfig.discharge_power || 0);
  const socLower = Number(resolvedConfig.soc_lower || 20);
  const socUpper = Number(resolvedConfig.soc_upper || 90);
  let soc = (socLower + socUpper) / 2;

  const hourlyPlan = forecastSeries.map((point: any, index: number) => {
    const time = point.time || hourText(point.datetime);
    const action = chargeHours.has(time) ? '充电' : dischargeHours.has(time) ? '放电' : '观望';
    const power = action === '充电' ? chargePower : action === '放电' ? -dischargePower : 0;
    soc = Math.max(socLower, Math.min(socUpper, soc + (action === '充电' ? 4 : action === '放电' ? -4 : 0)));
    return {
      key: `${today?.run_id || latest?.run_id || 'strategy'}-${index}`,
      time,
      datetime: point.datetime,
      price: numberValue(point.price),
      load: numberValue(point.load),
      riskProbability: numberValue(point.risk_probability),
      risk: normalizeRisk(point.risk_level),
      action,
      power,
      derivedSoc: Number(soc.toFixed(1)),
      executionStatus: '未接入',
      advice: action === '充电' ? '低价窗口，建议核对设备约束后充电' : action === '放电' ? '高价窗口，建议核对敞口后放电' : '保持状态，关注价格变化'
    };
  });

  const reviewRows = (reviewItems.length ? reviewItems : anomalies.filter((item: any) => normalizeRisk(item.risk_level) !== 'low'))
    .map((item: any, index: number) => {
      const evidence = item.evidence || {};
      const targetHour = item.target_hour || evidence.target_hour;
      return {
        key: item.id || `${today?.run_id || latest?.run_id || 'RV'}-${index + 1}`,
        id: item.id || `RV${String(index + 1).padStart(6, '0')}`,
        reason: item.anomaly_type || item.advice_type || '策略风险复核',
        action: item.recommendation || item.advice_text || '建议人工复核',
        risk: normalizeRisk(item.risk_level),
        confidence: numberValue(evidence.spike_risk_probability) == null ? null : Number(evidence.spike_risk_probability) * 100,
        submittedAt: targetHour || item.created_at || '--',
        period: hourText(targetHour),
        status: '待复核',
        assignee: '待分配',
        evidence: {
          predictedPrice: numberValue(evidence.predicted_price),
          forecastLoad: numberValue(evidence.forecast_load),
          riskProbability: numberValue(evidence.spike_risk_probability),
          peakValleySpread: numberValue(evidence.peak_valley_spread),
          explanation: item.explanation || item.advice_text || '--'
        }
      };
    });

  const thresholds = today?.summary?.thresholds || latest?.thresholds || {};
  const spread = numberValue(today?.summary?.estimated_revenue) ?? numberValue(thresholds.spread) ?? numberValue(forecast?.summary?.peak_valley_spread);
  const maxRiskProbability = Math.max(0, ...forecastSeries.map((item: any) => Number(item.risk_probability || 0)));

  return withServiceState({
    available: Boolean(strategyItems.length || forecastSeries.length),
    runId: today?.run_id || latest?.run_id || forecast?.run_id || '',
    strategyDate: dateText(forecast?.summary?.forecast_start || forecast?.generated_at),
    generatedAt: forecast?.generated_at || strategyItems[0]?.created_at || '',
    modelVersion: 'v3.2.1',
    region: '浙江省',
    strategyItems,
    storageItems,
    anomalies,
    forecastSeries,
    hourlyPlan,
    reviewRows,
    config: resolvedConfig,
    summary: {
      strategyCount: Number(today?.summary?.strategy_count ?? strategyItems.length),
      highRiskCount: highRiskItems.length,
      highRiskHours: new Set(highRiskItems.map((item: any) => hourText(item.target_hour))).size,
      lowWindowCount: new Set(lowItems.map((item: any) => hourText(item.target_hour))).size,
      storageCount: storageItems.length,
      reviewCount: reviewRows.length,
      spread,
      spreadNote: today?.summary?.estimated_revenue_note || '由预测峰谷价差计算，不等同实际收益',
      priorityScore: Math.round(maxRiskProbability * 100),
      lowHours: compactWindows(lowItems, () => true),
      highHours: compactWindows(highRiskItems, () => true)
    },
    capability: {
      reviewAudit: true,
      reviewStateMachine: false,
      executionPersistence: false,
      actualSoc: false,
      realizedRevenue: false
    }
  }, {
    empty: !strategyItems.length && !forecastSeries.length,
    mockFallback: false,
    partialErrors
  });
}
