import { api } from '../api';
import { errorMessage, withServiceState } from './serviceState';

function numberValue(value: unknown) {
  if (value == null || value === '') return null;
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

function runtimeAction(value: unknown) {
  if (value === 'charge') return '充电';
  if (value === 'discharge') return '放电';
  return '待机';
}

function runtimeStatus(value: unknown) {
  const labels: Record<string, string> = {
    scheduled: '待执行',
    in_progress: '执行中',
    completed: '已完成',
    partial: '部分完成',
    failed: '执行失败',
    cancelled: '已取消'
  };
  return labels[String(value || '')] || String(value || '--');
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

  const [today, latest, anomaly, config, forecast, governance, runtime] = await Promise.all([
    safe('strategyToday', api.strategyToday),
    safe('strategyLatest', api.strategyLatest),
    safe('anomalyLatest', api.anomalyLatest),
    safe('strategyConfig', api.strategyConfig),
    safe('forecast24h', api.forecast24h),
    safe('strategyGovernance', api.strategyGovernanceList),
    safe('strategyRuntimeFacts', api.strategyRuntimeFacts)
  ]);

  const strategyItems = Array.isArray(today?.items)
    ? today.items
    : Array.isArray(latest?.items)
      ? latest.items
      : [];
  const anomalies = Array.isArray(anomaly?.items) ? anomaly.items : [];
  const forecastSeries = Array.isArray(forecast?.series) ? forecast.series : [];
  const governedItems = Array.isArray(governance?.items) ? governance.items : [];
  const resolvedConfig = config && typeof config === 'object' ? config : {};
  const storageItems = strategyItems.filter((item: any) => String(item.scenario || '').includes('储能'));
  const reviewItems = strategyItems.filter((item: any) => String(item.advice_type || '').includes('复核'));
  const highRiskItems = strategyItems.filter((item: any) => normalizeRisk(item.risk_level) === 'high');
  const lowItems = strategyItems.filter((item: any) =>
    String(item.advice_type || '').includes('低价') || String(item.advice_type || '').includes('充电')
  );
  const chargeHours = new Set(compactWindows(storageItems, (item) => String(item.advice_type || '').includes('充电')));
  const dischargeHours = new Set(compactWindows(storageItems, (item) => String(item.advice_type || '').includes('放电')));
  const chargePower = numberValue(resolvedConfig.charge_power);
  const dischargePower = numberValue(resolvedConfig.discharge_power);

  const hourlyPlan = forecastSeries.map((point: any, index: number) => {
    const time = point.time || hourText(point.datetime);
    const action = chargeHours.has(time) ? '充电' : dischargeHours.has(time) ? '放电' : '观望';
    const power = action === '充电' ? chargePower : action === '放电' ? (dischargePower == null ? null : -dischargePower) : 0;
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
      executionStatus: '未接入',
      advice: action === '充电' ? '低价窗口，建议核对设备约束后充电' : action === '放电' ? '高价窗口，建议核对敞口后放电' : '保持状态，关注价格变化'
    };
  });

  const statusLabels: Record<string, string> = {
    unreviewed: '未进入审核',
    draft: '草稿', pending_review: '待复核', approved: '已通过', rejected: '已驳回',
    published: '已发布', superseded: '已替代', expired: '已过期', cancelled: '已取消'
  };
  const governedReviewRows = governedItems.map((item: any) => {
    const explanation = item.explanation || {};
    const supportingFacts = Array.isArray(explanation.supporting_facts) ? explanation.supporting_facts : [];
    const forecastFact = supportingFacts.find((fact: any) => fact.table === 'forecast_results') || {};
    return {
      key: item.strategy_id,
      id: item.strategy_id,
      reason: (explanation.strategy_types || []).join('、') || item.strategy_type || '策略风险复核',
      action: item.summary || explanation.executive_summary || '建议人工复核',
      risk: normalizeRisk(item.risk_level),
      confidence: numberValue(item.confidence) == null ? null : Number(item.confidence) * 100,
      submittedAt: item.generated_at || item.created_at || '--',
      period: `${String(item.applicable_start_at || '--').slice(0, 16)} ~ ${String(item.applicable_end_at || '--').slice(0, 16)}`,
      status: item.status,
      statusLabel: statusLabels[item.status] || item.status || '未知',
      assignee: item.approved_by || item.rejected_by || '待分配',
      isStale: Boolean(item.is_stale),
      staleReason: item.stale_reason,
      sourceType: item.source_type,
      sourceLabel: item.source_type === 'historical' ? '历史策略记录' : item.is_stale ? '过期策略记录' : '策略事实记录',
      runId: item.run_id,
      reportId: item.report_id,
      contentHash: item.content_hash,
      prohibitedActions: item.prohibited_actions_json || [],
      evidence: {
        predictedPrice: numberValue(forecastFact.maximum_price),
        forecastLoad: null,
        riskProbability: numberValue(forecastFact.maximum_spike_probability),
        peakValleySpread: numberValue(forecastFact.peak_valley_spread),
        explanation: explanation.rationale || explanation.executive_summary || item.summary || '--',
        supportingFacts,
        citations: explanation.citations || []
      }
    };
  });
  const legacyReviewRows = (reviewItems.length ? reviewItems : anomalies.filter((item: any) => normalizeRisk(item.risk_level) !== 'low'))
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
        status: 'pending_review',
        statusLabel: '待复核（旧接口）',
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
  const reviewRows = governedReviewRows.length ? governedReviewRows : legacyReviewRows;
  const devices = Array.isArray(runtime?.devices) ? runtime.devices : [];
  const executionItems = (Array.isArray(runtime?.execution_items) ? runtime.execution_items : []).map((item: any) => ({
    ...item,
    key: item.execution_id,
    time: hourText(item.window_start_at),
    actionLabel: runtimeAction(item.action),
    statusLabel: runtimeStatus(item.execution_status),
    plannedPower: numberValue(item.planned_power_mw),
    actualPower: numberValue(item.actual_power_mw),
    plannedEnergy: numberValue(item.planned_energy_mwh),
    actualEnergy: numberValue(item.actual_energy_mwh),
    socBefore: numberValue(item.soc_before_pct),
    socAfter: numberValue(item.soc_after_pct),
    realizedRevenue: numberValue(item.realized_revenue_cny)
  }));
  const devicePlans = Object.fromEntries(devices.map((device: any) => [
    device.device_id,
    (Array.isArray(device.soc_series) ? device.soc_series : []).map((item: any) => ({
      key: item.snapshot_id,
      deviceId: device.device_id,
      deviceName: device.device_name,
      datetime: item.observed_at,
      time: hourText(item.observed_at),
      actualSoc: numberValue(item.soc_pct),
      availableEnergy: numberValue(item.available_energy_mwh),
      power: numberValue(item.active_power_mw),
      operatingMode: item.operating_mode,
      sourceType: item.is_simulated ? 'simulated' : 'real',
      batchId: item.batch_id,
      generatedAt: item.generated_at
    }))
  ]));
  const runtimeSummary = runtime?.summary || {};
  const averageSocValues = devices
    .map((item: any) => numberValue(item.latest_soc?.soc_pct))
    .filter((item: number | null): item is number => item != null);
  const averageSoc = averageSocValues.length
    ? averageSocValues.reduce((total: number, value: number) => total + value, 0) / averageSocValues.length
    : null;

  const thresholds = today?.summary?.thresholds || latest?.thresholds || {};
  const spread = numberValue(today?.summary?.estimated_revenue) ?? numberValue(thresholds.spread) ?? numberValue(forecast?.summary?.peak_valley_spread);
  const maxRiskProbability = Math.max(0, ...forecastSeries.map((item: any) => Number(item.risk_probability || 0)));
  const governedStrategy = governedItems[0] || null;
  const strategyFactsAvailable = Boolean(today || latest || governance);
  const runtimeFactsAvailable = Boolean(runtime);
  const strategyIsStale = Boolean(governedStrategy?.is_stale || today?.is_stale || forecast?.is_stale);
  const strategyStatus = governedStrategy?.status || (strategyItems.length ? 'unreviewed' : 'unavailable');
  const strategyUsable = ['approved', 'published'].includes(strategyStatus) && !strategyIsStale;
  const strategySourceLabel = !governedStrategy
    ? strategyItems.length ? '未治理策略建议' : '策略暂不可用'
    : strategyIsStale
      ? `历史策略记录（${statusLabels[strategyStatus] || strategyStatus}）`
      : `策略事实记录（${statusLabels[strategyStatus] || strategyStatus}）`;

  return withServiceState({
    available: Boolean(runtime?.available || governedItems.length || strategyItems.length || forecastSeries.length),
    runId: governedStrategy?.run_id || today?.run_id || latest?.run_id || forecast?.run_id || '',
    runtimeBatchId: runtime?.batch_ids?.[0] || '',
    strategyDate: dateText(governedStrategy?.applicable_start_at || forecast?.summary?.forecast_start || forecast?.generated_at),
    strategyVersion: governedItems[0]?.strategy_version || '',
    generatedAt: governedStrategy?.generated_at || forecast?.generated_at || strategyItems[0]?.created_at || '',
    modelVersion: governedStrategy?.model_version || forecast?.model_version || '',
    featureVersion: governedStrategy?.feature_version || forecast?.feature_version || forecast?.meta?.feature_version || '',
    sourceType: governedStrategy?.source_type || today?.source_type || forecast?.source_type || 'unavailable',
    sourceLabel: strategySourceLabel,
    strategyStatus,
    strategyStatusLabel: statusLabels[strategyStatus] || strategyStatus,
    strategyUsable,
    strategyValidFrom: governedStrategy?.applicable_start_at || forecast?.meta?.valid_from || '',
    strategyValidTo: governedStrategy?.applicable_end_at || forecast?.meta?.valid_to || '',
    isSimulated: Boolean(runtime?.is_simulated),
    isStale: strategyIsStale,
    staleReason: governedStrategy?.stale_reason || today?.stale_reason || forecast?.stale_reason || '',
    runtimeGeneratedAt: runtime?.generated_at || '',
    runtimeIsStale: Boolean(runtime?.is_stale),
    runtimeStaleReason: runtime?.stale_reason || '',
    runtimeSourceLabel: runtime?.is_simulated ? '模拟设备与执行事实' : runtime?.available ? '设备运行事实' : '运行事实暂不可用',
    region: devices[0]?.region || governedItems[0]?.region || forecast?.region || today?.region || latest?.region || null,
    strategyItems,
    storageItems,
    devices,
    devicePlans,
    executionItems,
    anomalies,
    forecastSeries,
    hourlyPlan,
    reviewRows,
    config: resolvedConfig,
    summary: {
      strategyCount: strategyFactsAvailable ? governedItems.length || Number(today?.summary?.strategy_count ?? strategyItems.length) : null,
      highRiskCount: strategyFactsAvailable ? highRiskItems.length : null,
      highRiskHours: strategyFactsAvailable ? new Set(highRiskItems.map((item: any) => hourText(item.target_hour))).size : null,
      lowWindowCount: strategyFactsAvailable ? new Set(lowItems.map((item: any) => hourText(item.target_hour))).size : null,
      storageCount: strategyFactsAvailable ? storageItems.length : null,
      deviceCount: runtimeFactsAvailable ? Number(runtimeSummary.device_count ?? devices.length) : null,
      onlineDeviceCount: runtimeFactsAvailable ? Number(runtimeSummary.online_device_count ?? 0) : null,
      executionCount: runtimeFactsAvailable ? Number(runtimeSummary.execution_count ?? executionItems.length) : null,
      completedExecutionCount: runtimeFactsAvailable ? Number(runtimeSummary.completed_count ?? 0) : null,
      inProgressExecutionCount: runtimeFactsAvailable ? Number(runtimeSummary.in_progress_count ?? 0) : null,
      realizedRevenue: numberValue(runtimeSummary.realized_revenue_cny),
      averageSoc,
      reviewCount: strategyFactsAvailable ? reviewRows.length : null,
      spread,
      spreadNote: String(today?.summary?.estimated_revenue_note || '由预测峰谷价差计算，不等同实际收益')
        .replace(/真实预测/g, '绑定预测'),
      priorityScore: Math.round(maxRiskProbability * 100),
      lowHours: compactWindows(lowItems, () => true),
      highHours: compactWindows(highRiskItems, () => true)
    },
    capability: {
      reviewAudit: true,
      reviewStateMachine: Boolean(governance),
      executionPersistence: Boolean(executionItems.length),
      actualSoc: Boolean(devices.some((item: any) => item.latest_soc)),
      realizedRevenue: numberValue(runtimeSummary.realized_revenue_cny) != null
    }
  }, {
    empty: !runtime?.available && !governedItems.length && !strategyItems.length && !forecastSeries.length,
    mockFallback: false,
    partialErrors
  });
}
