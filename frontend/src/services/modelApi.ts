import { api } from '../api';
import { modelMock } from '../mock/modelMock';
import { mockFallback, withServiceState } from './serviceState';

const fmt = (value: unknown, digits = 2) => {
  const num = Number(value);
  return Number.isFinite(num) ? num.toFixed(digits) : '--';
};

export async function getModelCenterData() {
  try {
    const partialErrors: string[] = [];
    const [payload, errors] = await Promise.all([
      api.models(),
      api.modelErrors().catch((error) => {
        partialErrors.push(error instanceof Error ? error.message : String(error));
        return null;
      })
    ]);
    const versions = Array.isArray(payload?.versions) ? payload.versions : [];
    const active = payload?.active || versions.find((item: any) => item.is_active) || versions[0] || {};
    const candidate = versions.find((item: any) => !item.is_active) || {};
    const errorRows = Array.isArray(errors?.records) ? errors.records : payload?.errors || [];
    return withServiceState({
      ...modelMock,
      dataSource: versions.length ? 'postgresql.model_registry' : 'mock_fallback',
      metrics: [
        { ...modelMock.metrics[0], value: active.model_version || active.model_name || modelMock.metrics[0].value, note: `启用时间：${active.created_at || active.updated_at || '--'}` },
        { ...modelMock.metrics[1], value: candidate.model_version || candidate.model_name || modelMock.metrics[1].value, note: `更新时间：${candidate.created_at || candidate.updated_at || '--'}` },
        { ...modelMock.metrics[2], value: fmt(active.test_mae ?? active.mae) },
        { ...modelMock.metrics[3], value: fmt(active.test_rmse ?? active.rmse) },
        { ...modelMock.metrics[4], value: fmt(active.peak_rmse ?? active.peak_error) },
        { ...modelMock.metrics[5], value: String(active.created_at || active.updated_at || '--') }
      ],
      comparison: versions.length
        ? versions.map((item: any) => [
            item.model_version || '--',
            item.model_name || item.model_type || 'price_forecast_model',
            item.is_active ? 'Active' : item.status || 'Candidate',
            fmt(item.test_mae ?? item.mae),
            fmt(item.test_rmse ?? item.rmse),
            fmt(item.peak_rmse ?? item.peak_error),
            item.created_at || item.updated_at || '--'
          ])
        : modelMock.comparison,
      errorTrend: errorRows.length
        ? errorRows.slice(0, 30).reverse().map((item: any, index: number) => ({
            time: String(item.forecast_date || item.metric_date || index),
            value: Number(item.mae || 0),
            actual: Number(item.max_abs_error || item.rmse || 0),
            baseline: Number(item.peak_error || 0)
          }))
        : modelMock.errorTrend,
      detail: {
        ...modelMock.detail,
        name: active.model_name || modelMock.detail.name,
        type: active.model_type || modelMock.detail.type,
        algorithm: active.algorithm || modelMock.detail.algorithm
      }
    }, {
      empty: !versions.length && !errorRows.length,
      mockFallback: !versions.length,
      fallbackReason: !versions.length ? '模型指标接口没有返回模型版本，模型中心展示本地兜底模型。' : undefined,
      partialErrors
    });
  } catch (error) {
    return mockFallback(modelMock, error, '模型中心真实接口请求失败，已切换到本地兜底数据。');
  }
}
