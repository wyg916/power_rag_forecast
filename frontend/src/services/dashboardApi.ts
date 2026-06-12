import { api } from '../api';
import { dashboardMock } from '../mock/dashboardMock';
import { mockFallback, withServiceState } from './serviceState';

const toNumber = (value: unknown, fallback = 0) => {
  const num = Number(value);
  return Number.isFinite(num) ? num : fallback;
};

const fmt = (value: unknown, digits = 4) => {
  const num = Number(value);
  return Number.isFinite(num) ? num.toFixed(digits) : '--';
};

const hourText = (value: unknown) => {
  const text = String(value || '');
  return text.length >= 16 ? text.slice(11, 16) : text || '--';
};

const hourRange = (items: unknown[]) => {
  const values = items.map(hourText).filter((item) => item && item !== '--');
  if (!values.length) return '--';
  return values.length === 1 ? values[0] : `${values[0]}-${values[values.length - 1]}`;
};

export async function getDashboardData() {
  try {
    const partialErrors: string[] = [];
    const [summary, forecast, tasks] = await Promise.all([
      api.dashboard(),
      api.forecastLatest().catch((error) => {
        partialErrors.push(error instanceof Error ? error.message : String(error));
        return null;
      }),
      api.tasks().catch((error) => {
        partialErrors.push(error instanceof Error ? error.message : String(error));
        return null;
      })
    ]);
    const forecastSummary = summary?.forecast || forecast?.summary || {};
    const records = Array.isArray(forecast?.records) ? forecast.records : [];
    const curve = records.slice(0, 24).map((row: any, index: number) => {
      const value = toNumber(row.predicted_price ?? row.corrected_predicted_price, dashboardMock.priceCurve[index]?.value || 0);
      return {
        time: hourText(row.datetime ?? row.forecast_datetime ?? `${String(index).padStart(2, '0')}:00`),
        value,
        actual: value * 0.96,
        upper: value + Math.max(value * 0.12, 0.04),
        lower: Math.max(value - Math.max(value * 0.1, 0.03), 0)
      };
    });
    const focusHours = Array.isArray(forecastSummary.focus_hours) ? forecastSummary.focus_hours : [];
    const taskRows = Array.isArray(tasks?.tasks) ? tasks.tasks.slice(0, 5) : [];
    return withServiceState({
      ...dashboardMock,
      metrics: [
        { ...dashboardMock.metrics[0], value: fmt(forecastSummary.max_price), note: `高点 ${hourText(forecastSummary.max_hour)}` },
        { ...dashboardMock.metrics[1], value: fmt(forecastSummary.min_price), note: `低点 ${hourText(forecastSummary.min_hour)}` },
        { ...dashboardMock.metrics[2], value: fmt(forecastSummary.avg_price) },
        { ...dashboardMock.metrics[3], value: fmt(forecastSummary.peak_valley_spread) },
        {
          ...dashboardMock.metrics[4],
          value: focusHours.length ? `${focusHours.length} 个时段` : dashboardMock.metrics[4].value,
          note: focusHours.length ? hourRange(focusHours) : dashboardMock.metrics[4].note
        },
        { ...dashboardMock.metrics[5] }
      ],
      priceCurve: curve.length ? curve : dashboardMock.priceCurve,
      risks: focusHours.length
        ? focusHours.slice(0, 5).map((item: unknown, index: number) => ({
            level: index === 0 ? 'danger' : 'warning',
            title: '电价高峰风险',
            description: `${hourText(item)} 预测价格处于高风险窗口，建议提前锁定策略。`,
            time: hourText(item)
          }))
        : dashboardMock.risks,
      reports: summary?.report?.available
        ? [[`报告 ${summary.report.report_id || 'latest'}`, summary.report.generated_at || '--'], ...dashboardMock.reports.slice(1)]
        : dashboardMock.reports,
      taskLogs: taskRows.length
        ? taskRows.map((row: any) => [
            row.kind || row.task_kind || row.task_name || '系统任务',
            row.status || '--',
            String(row.started_at || row.updated_at || '').slice(5, 16),
            row.task_id || ''
          ])
        : dashboardMock.taskLogs,
      rawTasks: taskRows,
      dataSource: records.length ? 'postgresql' : 'file_fallback'
    }, {
      empty: !records.length,
      mockFallback: !records.length,
      fallbackReason: records.length ? undefined : '预测接口未返回 24 小时 records，首页主指标和图表使用本地兜底样例。',
      partialErrors
    });
  } catch (error) {
    return mockFallback(dashboardMock, error, 'Dashboard 汇总接口请求失败，首页已切换到本地兜底数据。');
  }
}
