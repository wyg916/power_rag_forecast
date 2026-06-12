import { api } from '../api';
import { taskMock } from '../mock/taskMock';
import { mockFallback, withServiceState } from './serviceState';

const statusText = (status: unknown) => {
  const value = String(status || '').toLowerCase();
  if (value === 'success') return '成功';
  if (value === 'running' || value === 'queued' || value === 'pending') return '运行中';
  if (value === 'cancel_requested') return '取消中';
  if (value === 'failed') return '失败';
  if (value === 'cancelled') return '已取消';
  return String(status || '--');
};

const durationText = (value: unknown) => {
  const seconds = Number(value);
  if (!Number.isFinite(seconds)) return '--';
  if (seconds < 60) return `${Math.round(seconds)}s`;
  return `${Math.floor(seconds / 60)}m${Math.round(seconds % 60)}s`;
};

export async function getTaskCenterData() {
  try {
    const partialErrors: string[] = [];
    const [tasksPayload, schedulesPayload] = await Promise.all([
      api.tasks(),
      api.scheduledTasks().catch((error) => {
        partialErrors.push(error instanceof Error ? error.message : String(error));
        return null;
      })
    ]);
    const tasks = Array.isArray(tasksPayload?.tasks) ? tasksPayload.tasks : [];
    const success = tasks.filter((item: any) => item.status === 'success').length;
    const running = tasks.filter((item: any) => ['running', 'queued', 'pending', 'cancel_requested'].includes(String(item.status))).length;
    const failed = tasks.filter((item: any) => item.status === 'failed').length;
    const schedules = Array.isArray(schedulesPayload?.tasks) ? schedulesPayload.tasks : [];
    const retryRows = tasks.filter((item: any) => item.status === 'failed').map((item: any) => [
      item.task_name || item.kind || '系统任务',
      item.ended_at || item.finished_at || item.started_at || '--',
      item.error_message || '任务失败',
      item.task_id || ''
    ]);
    return withServiceState({
      ...taskMock,
      metrics: [
        { ...taskMock.metrics[0], value: tasks.length },
        { ...taskMock.metrics[1], value: success, note: tasks.length ? `成功率 ${((success / tasks.length) * 100).toFixed(1)}%` : taskMock.metrics[1].note },
        { ...taskMock.metrics[2], value: running },
        { ...taskMock.metrics[3], value: failed },
        { ...taskMock.metrics[4], value: failed }
      ],
      schedules: schedules.length
        ? schedules.map((item: any) => [
            item.name || item.TaskName || '计划任务',
            item.mode || item.task_kind || '调度任务',
            item.schedule || item.run_time || '--',
            item.cron || item.Trigger || '--',
            item.next_run_time || item.NextRunTime || '--',
            item.status || item.Status || '--',
            item.last_result || item.LastTaskResult || '--'
          ])
        : taskMock.schedules,
      logs: tasks.length
        ? tasks.map((item: any) => [
            item.task_name || item.kind || '系统任务',
            item.task_type || item.task_kind || item.kind || '--',
            statusText(item.status),
            item.started_at || '--',
            item.finished_at || item.ended_at || '--',
            durationText(item.duration_seconds),
            'system',
            item.task_id || '',
            item.progress ?? 0,
            item.execution_mode || item.execution_backend || '--',
            item.message || item.error_message || '--',
            item.result_ref || '--'
          ])
        : taskMock.logs,
      retryQueue: retryRows.length ? retryRows : taskMock.retryQueue,
      alerts: failed
        ? tasks.filter((item: any) => item.status === 'failed').slice(0, 5).map((item: any) => [
            String(item.ended_at || item.finished_at || item.started_at || '').slice(11, 19) || '--',
            '严重',
            `${item.task_name || item.kind || '任务'} 执行失败`,
            item.error_message || '请查看任务日志'
          ])
        : taskMock.alerts,
      dataSource: tasks.length || schedules.length ? 'postgresql_or_windows_tasks' : 'mock_fallback'
    }, {
      empty: !tasks.length && !schedules.length,
      mockFallback: !tasks.length && !schedules.length,
      fallbackReason: !tasks.length && !schedules.length ? '任务接口没有返回运行记录或计划任务，任务中心展示本地兜底样例。' : undefined,
      partialErrors
    });
  } catch (error) {
    return mockFallback(taskMock, error, '任务中心真实接口请求失败，已切换到本地任务兜底数据。');
  }
}
