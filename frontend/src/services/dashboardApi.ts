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

const countByStatus = (items: any[] = [], status = 'ok') => items.filter((item) => String(item.status || '').toLowerCase() === status).length;

const taskProblemCount = (health: any) => Number(health?.failed_task_count || 0) + Number(health?.timeout_task_count || 0);

const operationStatus = (status: 'success' | 'warning' | 'danger' | 'info', value: unknown, title: string, description: string) => ({
  status,
  value,
  title,
  description
});

export async function getDashboardData() {
  try {
    const partialErrors: string[] = [];
    const [summary, forecast, tasks, freshness, taskHealth, ragHealth, dbHealth, backtest] = await Promise.all([
      api.dashboard(),
      api.forecastLatest().catch((error) => {
        partialErrors.push(error instanceof Error ? error.message : String(error));
        return null;
      }),
      api.tasks().catch((error) => {
        partialErrors.push(error instanceof Error ? error.message : String(error));
        return null;
      }),
      api.dataFreshness().catch((error) => {
        partialErrors.push(error instanceof Error ? error.message : String(error));
        return null;
      }),
      api.tasksHealth().catch((error) => {
        partialErrors.push(error instanceof Error ? error.message : String(error));
        return null;
      }),
      api.knowledgeHealth().catch((error) => {
        partialErrors.push(error instanceof Error ? error.message : String(error));
        return null;
      }),
      api.dbHealth().catch((error) => {
        partialErrors.push(error instanceof Error ? error.message : String(error));
        return null;
      }),
      api.modelBacktestSummary().catch((error) => {
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
    const freshnessItems = Array.isArray(freshness?.items) ? freshness.items : [];
    const okFreshness = countByStatus(freshnessItems);
    const staleTables = freshnessItems.filter((item: any) => String(item.status || '').toLowerCase() !== 'ok');
    const ragFallback = Boolean(ragHealth?.fallback_enabled || ragHealth?.status === 'fallback');
    const ragComplete = Number(ragHealth?.kb_chunk_count || 0) === 0
      ? 0
      : Math.round((Number(ragHealth?.embedded_chunk_count || 0) / Math.max(Number(ragHealth?.kb_chunk_count || 0), 1)) * 100);
    const taskProblems = taskProblemCount(taskHealth);
    const backtestOk = backtest?.available && backtest?.acceptable_for_backtest !== false && backtest?.leakage_check?.acceptable_for_backtest !== false;
    const reference = backtest?.reference_baseline?.overall || {};
    const alertSummary = [
      ...staleTables.slice(0, 3).map((item: any) => `数据表 ${item.table_name} 新鲜度异常：${item.not_found_reason || item.status || '需检查'}`),
      ...(taskProblems ? [`任务中心存在失败/超时任务 ${taskProblems} 个，建议查看任务中心运行健康。`] : []),
      ...(ragFallback ? [`RAG 当前处于降级模式：${(ragHealth?.fallback_reasons || []).join('；') || '模型路径或 embedding 状态需检查'}`] : []),
      ...(backtest?.available && !backtestOk ? ['P2 回测或泄露检查未通过，进入模型优化前需复核。'] : [])
    ];
    const operationalCards = [
      operationStatus(
        staleTables.length ? 'warning' : freshnessItems.length ? 'success' : 'info',
        freshnessItems.length ? `${okFreshness}/${freshnessItems.length}` : '--',
        '数据新鲜度',
        freshnessItems.length ? `核心数据表 ${okFreshness} 个正常，${staleTables.length} 个需关注。` : '数据新鲜度接口未返回表状态。'
      ),
      operationStatus(
        dbHealth?.ok ? 'success' : 'danger',
        dbHealth?.active || '--',
        '数据库',
        dbHealth?.message || (dbHealth?.ok ? 'PostgreSQL 主事实源可用。' : '数据库健康接口异常或未返回。')
      ),
      operationStatus(
        taskProblems ? 'warning' : 'success',
        taskHealth?.execution_mode || '--',
        '任务中心',
        `运行 ${taskHealth?.running_task_count ?? 0}，排队 ${taskHealth?.pending_task_count ?? 0}，失败/超时 ${taskProblems}。`
      ),
      operationStatus(
        ragFallback ? 'warning' : 'success',
        ragHealth?.embedding_dim || '--',
        'RAG / BGE',
        ragFallback ? 'RAG 发生 fallback，知识检索质量可能下降。' : `embedding 完整度 ${ragComplete}% ，rerank=${ragHealth?.rerank_provider || '--'}。`
      ),
      operationStatus(
        backtestOk ? 'success' : backtest?.available ? 'warning' : 'info',
        reference.mae !== undefined ? Number(reference.mae).toFixed(4) : '--',
        'P2 回测基线',
        backtest?.available ? `baseline=${backtest.reference_baseline?.model || '--'}，样本数 ${reference.sample_count ?? '--'}。` : 'P2 回测摘要暂不可用。'
      )
    ];
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
      dataFreshness: freshnessItems,
      taskHealth,
      ragHealth,
      dbHealth,
      modelBacktest: backtest,
      operationalCards,
      alertSummary,
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
