import { reportMock } from '../mock/reportMock';
import { api } from '../api';
import { mockFallback, withServiceState } from './serviceState';

export async function getReportCenterData(): Promise<any> {
  try {
    const partialErrors: string[] = [];
    const [latest, forecast] = await Promise.all([
      api.reportLatest(),
      api.forecastLatest().catch((error) => {
        partialErrors.push(error instanceof Error ? error.message : String(error));
        return null;
      })
    ]);
    const report = latest || {};
    const summary = report.summary || {};
    const forecastRows = Array.isArray(forecast?.records) ? forecast.records : [];
    const previewCurve = forecastRows.slice(0, 12).map((row: any, index: number) => ({
      time: `${String(row.hour ?? index).padStart(2, '0')}:00`,
      value: Number(row.predicted_price ?? row.corrected_predicted_price ?? 0),
      actual: Number(row.actual_price ?? row.predicted_price ?? 0)
    }));
    return withServiceState({
      ...reportMock,
      dataSource: report.source || (report.available ? 'file_fallback' : 'postgresql'),
      activeReport: report,
      previewCurve,
      reports: report.report_id
        ? [[report.report_id, report.report_type || '日报', report.status || (report.available ? '待审核' : '未生成'), report.generated_at || '--'], ...reportMock.reports.slice(1)]
        : reportMock.reports,
      previewMetrics: [
        ['平均电价', summary.avg_price || summary.average_price || '--', '元/kWh'],
        ['最高电价', summary.max_price || '--', '元/kWh'],
        ['最低电价', summary.min_price || '--', '元/kWh'],
        ['预测行数', summary.rows || '--', '条'],
        ['模型可信度', summary.confidence || '--', '%']
      ]
    }, {
      empty: !report.available && !report.report_id,
      mockFallback: !report.available && !report.report_id,
      fallbackReason: !report.available && !report.report_id ? '报告接口没有返回可用报告，报告中心展示本地兜底报告列表。' : undefined,
      partialErrors
    });
  } catch (error) {
    return mockFallback(reportMock, error, '报告中心真实接口请求失败，已切换到本地兜底数据。');
  }
}
