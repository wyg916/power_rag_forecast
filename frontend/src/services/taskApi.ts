import { api } from '../api';
import { errorMessage, withServiceState } from './serviceState';

export function statusText(status: unknown) {
  const value = String(status || '').toLowerCase();
  if (value === 'success') return '成功';
  if (value === 'failed') return '失败';
  if (value === 'timeout') return '超时';
  if (value === 'cancelled') return '已取消';
  if (value === 'cancel_requested') return '取消中';
  if (value === 'retrying') return '重试中';
  if (value === 'queued') return '排队中';
  if (value === 'pending') return '待执行';
  if (value === 'running') return '运行中';
  return String(status || '--');
}

export function durationText(value: unknown) {
  const seconds = Number(value);
  if (!Number.isFinite(seconds)) return '--';
  if (seconds < 60) return `${Math.round(seconds)}s`;
  return `${Math.floor(seconds / 60)}m${Math.round(seconds % 60)}s`;
}

function percentNote(value: unknown) {
  const numeric = Number(value || 0);
  if (!Number.isFinite(numeric) || numeric === 0) return '较昨日 0%';
  return `较昨日 ${numeric > 0 ? '+' : ''}${numeric.toFixed(1)}%`;
}

export async function getTaskCenterData(params: Record<string, any> = {}) {
  try {
    const partialErrors: string[] = [];
    const safeParams = {
      ...params,
      page: params.page || 1,
      page_size: params.page_size || 100
    };
    const [overview, runsPayload, healthPayload, logsPayload, retryPayload, queuePayload, trendPayload, schedulesPayload] = await Promise.all([
      api.taskOverview(),
      api.taskRuns(safeParams),
      api.tasksHealth().catch((error) => {
        partialErrors.push(errorMessage(error));
        return {};
      }),
      api.taskRecentLogs({ limit: 30, queue_name: params.queue_name || '' }).catch((error) => {
        partialErrors.push(errorMessage(error));
        return { items: [] };
      }),
      api.taskRetryRecent(30).catch((error) => {
        partialErrors.push(errorMessage(error));
        return { items: [] };
      }),
      api.taskQueueOverview().catch((error) => {
        partialErrors.push(errorMessage(error));
        return { items: [] };
      }),
      api.taskTrend(7).catch((error) => {
        partialErrors.push(errorMessage(error));
        return { items: [] };
      }),
      api.scheduledTasks().catch((error) => {
        partialErrors.push(errorMessage(error));
        return { tasks: [] };
      })
    ]);

    const tasks = Array.isArray(runsPayload?.list) ? runsPayload.list : Array.isArray(runsPayload?.tasks) ? runsPayload.tasks : [];
    const retryRows = Array.isArray(retryPayload?.items) ? retryPayload.items : [];
    const queueRows = Array.isArray(queuePayload?.items) ? queuePayload.items : [];
    const recentLogs = Array.isArray(logsPayload?.items) ? logsPayload.items : [];
    const trendRows = Array.isArray(trendPayload?.items) ? trendPayload.items : [];
    const successRate = Number(overview?.success_rate || 0);
    const change = overview?.day_over_day_change || {};

    return withServiceState(
      {
        overview,
        tasks,
        total: Number(runsPayload?.total || tasks.length),
        health: healthPayload || {},
        schedules: Array.isArray(schedulesPayload?.tasks) ? schedulesPayload.tasks : [],
        retryQueue: retryRows,
        recentLogs,
        queueRows,
        trendRows,
        metrics: [
          { title: '任务总数', value: Number(overview?.task_total || 0).toLocaleString(), note: percentNote(change.task_total), status: 'info' },
          { title: '成功任务', value: Number(overview?.success_total || 0).toLocaleString(), note: `成功率 ${successRate.toFixed(2)}%`, status: 'success' },
          { title: '运行中 / 排队', value: `${Number(overview?.running_total || 0)} / ${Number(overview?.pending_total || 0)}`, note: '来自任务运行表', status: 'running' },
          { title: '失败 / 超时', value: `${Number(overview?.failed_total || 0)} / ${Number(overview?.timeout_total || 0)}`, note: '来自任务运行表', status: Number(overview?.failed_total || 0) || Number(overview?.timeout_total || 0) ? 'danger' : 'success' },
          { title: '队列数', value: Number(overview?.queue_total || queueRows.length || 0).toLocaleString(), note: '来自队列聚合', status: 'info' }
        ],
        dataSource: 'postgresql.task_runs'
      },
      {
        empty: !tasks.length,
        mockFallback: false,
        partialErrors
      }
    );
  } catch (error) {
    return withServiceState(
      {
        overview: {},
        tasks: [],
        total: 0,
        health: {},
        schedules: [],
        retryQueue: [],
        recentLogs: [],
        queueRows: [],
        trendRows: [],
        metrics: [],
        dataSource: 'api_error'
      },
      {
        empty: true,
        mockFallback: false,
        error: errorMessage(error)
      }
    );
  }
}
