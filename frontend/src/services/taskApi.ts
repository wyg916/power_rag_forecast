import { api } from '../api';
import { taskMock } from '../mock/taskMock';
import { mockFallback, withServiceState } from './serviceState';

const activeStatuses = new Set(['pending', 'queued', 'running', 'retrying', 'cancel_requested']);

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

export async function getTaskCenterData() {
  try {
    const partialErrors: string[] = [];
    const [tasksPayload, healthPayload, schedulesPayload] = await Promise.all([
      api.tasks(),
      api.tasksHealth().catch((error) => {
        partialErrors.push(error instanceof Error ? error.message : String(error));
        return null;
      }),
      api.scheduledTasks().catch((error) => {
        partialErrors.push(error instanceof Error ? error.message : String(error));
        return null;
      })
    ]);
    const tasks = Array.isArray(tasksPayload?.tasks) ? tasksPayload.tasks : [];
    const health = healthPayload || {};
    const schedules = Array.isArray(schedulesPayload?.tasks) ? schedulesPayload.tasks : [];
    const success = tasks.filter((item: any) => item.status === 'success').length;
    const running = tasks.filter((item: any) => activeStatuses.has(String(item.status))).length;
    const failed = tasks.filter((item: any) => ['failed', 'timeout'].includes(String(item.status))).length;
    const retryRows = tasks
      .filter((item: any) => ['failed', 'timeout', 'cancelled'].includes(String(item.status)))
      .map((item: any) => ({
        key: item.task_id,
        task_id: item.task_id,
        task_name: item.task_name || item.kind || '系统任务',
        status: item.status,
        failed_at: item.ended_at || item.finished_at || item.started_at || '--',
        error_message: item.error_message || item.message || '任务未成功完成',
        retry_count: item.retry_count ?? 0,
        max_retries: item.max_retries ?? 0
      }));
    return withServiceState(
      {
        ...taskMock,
        tasks,
        health,
        schedules,
        retryQueue: retryRows,
        metrics: [
          { title: '任务总数', value: tasks.length, status: 'info' },
          { title: '成功任务', value: success, note: tasks.length ? `成功率 ${((success / tasks.length) * 100).toFixed(1)}%` : '暂无运行记录', status: 'success' },
          { title: '运行/排队', value: running, status: 'running' },
          { title: '失败/超时', value: failed, status: failed ? 'danger' : 'success' },
          { title: '队列数', value: Array.isArray(health.queue_summary) ? health.queue_summary.length : 0, status: 'info' }
        ],
        dataSource: 'postgresql.task_runs'
      },
      {
        empty: !tasks.length,
        mockFallback: false,
        fallbackReason: !tasks.length ? '任务中心接口可用，但当前没有任务记录。' : undefined,
        partialErrors
      }
    );
  } catch (error) {
    return mockFallback(taskMock, error, '任务中心真实接口请求失败，已切换到本地兜底数据。');
  }
}
