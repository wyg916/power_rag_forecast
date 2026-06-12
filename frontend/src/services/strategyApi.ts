import { strategyMock } from '../mock/strategyMock';
import { api } from '../api';
import { mockFallback, withServiceState } from './serviceState';

export async function getStrategyCenterData(): Promise<any> {
  try {
    const partialErrors: string[] = [];
    const [strategy, anomaly, config] = await Promise.all([
      api.strategyLatest(),
      api.anomalyLatest().catch((error) => {
        partialErrors.push(error instanceof Error ? error.message : String(error));
        return null;
      }),
      api.strategyConfig().catch((error) => {
        partialErrors.push(error instanceof Error ? error.message : String(error));
        return null;
      })
    ]);
    const items = Array.isArray(strategy?.items) ? strategy.items : Array.isArray(strategy?.strategy) ? strategy.strategy : [];
    const risks = Array.isArray(anomaly?.items) ? anomaly.items : Array.isArray(anomaly?.records) ? anomaly.records : [];
    const highRisk = items.filter((item: any) => String(item.risk_level || item.advice_type || '').includes('高') || String(item.action || '').includes('风险'));
    const lowWindow = items.filter((item: any) => String(item.advice_type || item.action || '').includes('充') || String(item.action || '').includes('低'));
    return withServiceState({
      ...strategyMock,
      dataSource: strategy?.source_type || 'postgresql_or_file',
      config,
      metrics: [
        { ...strategyMock.metrics[0], value: items.length ? '已生成策略' : strategyMock.metrics[0].value },
        { ...strategyMock.metrics[1], value: highRisk.length || risks.length },
        { ...strategyMock.metrics[2], value: lowWindow.length },
        { ...strategyMock.metrics[3], value: strategy?.expected_profit || strategyMock.metrics[3].value },
        { ...strategyMock.metrics[4], value: risks.length || strategyMock.reviewList.length }
      ],
      timeline: items.length
        ? items.slice(0, 12).map((item: any) => [
            item.period || item.time || item.target_hour || '--',
            item.action || item.advice_type || '--',
            item.power ?? item.suggested_power ?? '0',
            item.expected_profit ?? item.revenue ?? '--'
          ])
        : strategyMock.timeline,
      reviewList: risks.length
        ? risks.slice(0, 12).map((item: any, index: number) => [
            item.id || `RV${String(index + 1).padStart(4, '0')}`,
            item.risk_type || item.type || '风险复核',
            item.period || item.hour || item.target_hour || '--',
            item.action || item.suggestion || '--',
            item.reason || item.message || item.description || '--',
            item.status || '待复核'
          ])
        : strategyMock.reviewList
    }, {
      empty: !items.length && !risks.length,
      mockFallback: !items.length && !risks.length,
      fallbackReason: !items.length && !risks.length ? '策略和异常接口没有返回真实记录，策略中心使用本地兜底策略。' : undefined,
      partialErrors
    });
  } catch (error) {
    return mockFallback(strategyMock, error, '策略中心真实接口请求失败，已切换到本地兜底数据。');
  }
}
