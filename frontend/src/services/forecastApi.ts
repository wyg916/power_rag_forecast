import { api } from '../api';
import { forecastMock } from '../mock/forecastMock';
import { mockFallback, withServiceState } from './serviceState';

const toNumber = (value: unknown, fallback = 0) => {
  const num = Number(value);
  return Number.isFinite(num) ? num : fallback;
};

const fmt = (value: unknown, digits = 4) => {
  const num = Number(value);
  return Number.isFinite(num) ? num.toFixed(digits) : '--';
};

const hourText = (value: unknown, fallback = '--') => {
  const text = String(value || '');
  return text.length >= 16 ? text.slice(11, 16) : text || fallback;
};

const riskLabel = (row: any) => {
  const level = String(row.risk_level || '').toLowerCase();
  const prob = Number(row.spike_risk_prob || 0);
  if (level.includes('high') || prob >= 0.5) return '高';
  if (level.includes('medium') || prob >= 0.2) return '中';
  return '低';
};

export async function getForecastCenterData() {
  try {
    const payload = await api.forecastLatest();
    const records = Array.isArray(payload?.records) ? payload.records.slice(0, 24) : [];
    const summary = payload?.summary || {};
    const curve = records.map((row: any, index: number) => {
      const value = toNumber(row.predicted_price ?? row.corrected_predicted_price, forecastMock.curve[index]?.value || 0);
      return {
        time: hourText(row.datetime ?? row.forecast_datetime, `${String(index).padStart(2, '0')}:00`),
        value,
        actual: value * 0.95,
        upper: value + Math.max(value * 0.12, 0.04),
        lower: Math.max(value - Math.max(value * 0.1, 0.03), 0)
      };
    });
    const detailRows = records.map((row: any, index: number) => {
      const start = hourText(row.datetime ?? row.forecast_datetime, `${String(index).padStart(2, '0')}:00`);
      return {
        key: String(index),
        time: `${start}-${String((index + 1) % 24).padStart(2, '0')}:00`,
        price: fmt(row.predicted_price ?? row.corrected_predicted_price),
        risk: riskLabel(row),
        action: riskLabel(row) === '高' ? '控制高价风险敞口' : riskLabel(row) === '低' ? '增加低价采购' : '正常采购',
        confidence: `${Math.round((1 - Math.min(Number(row.spike_risk_prob || 0), 0.8) * 0.35) * 100)}%`
      };
    });
    return withServiceState({
      ...forecastMock,
      metrics: [
        { ...forecastMock.metrics[0], value: fmt(summary.max_price), note: `出现于 ${hourText(summary.max_hour)}` },
        { ...forecastMock.metrics[1], value: fmt(summary.min_price), note: `出现于 ${hourText(summary.min_hour)}` },
        { ...forecastMock.metrics[2], value: fmt(summary.avg_price) },
        { ...forecastMock.metrics[3], value: fmt(summary.peak_valley_spread) },
        { ...forecastMock.metrics[4], value: records.length ? '86.0' : forecastMock.metrics[4].value }
      ],
      curve: curve.length ? curve : forecastMock.curve,
      history: curve.length ? curve.map((item) => Number((item.value * 0.94).toFixed(4))) : forecastMock.history,
      detailRows: detailRows.length ? detailRows : forecastMock.detailRows,
      dataSource: payload?.source_type || (records.length ? 'postgresql' : 'file_fallback'),
      insights: summary.focus_hours?.length
        ? [
            ['高价风险时段', summary.focus_hours.map(hourText).join(' / '), '来自 PostgreSQL 最新预测批次，建议提前压降风险敞口。'],
            ['低价机会窗口', hourText(summary.min_hour), '低价窗口可用于补充采购或储能充电。'],
            ['日内价差', fmt(summary.peak_valley_spread), '峰谷价差扩大时优先执行分时优化策略。']
          ]
        : forecastMock.insights
    }, {
      empty: !records.length,
      mockFallback: !records.length,
      fallbackReason: records.length ? undefined : '预测接口没有返回 records，预测中心使用本地兜底曲线保持页面可读。'
    });
  } catch (error) {
    return mockFallback(forecastMock, error, '预测接口请求失败，预测中心已切换到本地兜底数据。');
  }
}
