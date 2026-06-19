import { BellOutlined, CheckCircleOutlined, CloseCircleOutlined, PlayCircleOutlined, PlusOutlined, ReloadOutlined, ScheduleOutlined } from '@ant-design/icons';
import { Alert, Button, DatePicker, Descriptions, Form, Input, Modal, Select, Space, Tag, Timeline, message } from 'antd';
import { useEffect, useMemo, useState } from 'react';
import { api } from '../../api';
import { DetailDrawer } from '../../components/actions/DetailDrawer';
import { TaskLogViewer } from '../../components/actions/TaskLogViewer';
import { SectionCard } from '../../components/cards/SectionCard';
import { TableCard } from '../../components/cards/TableCard';
import { PageTabs } from '../../components/common/PageTabs';
import { DataStateBanner } from '../../components/common/States';
import { MetricGrid } from '../../components/layout/UnifiedPage';
import { taskMock } from '../../mock/taskMock';
import { durationText, getTaskCenterData, statusText } from '../../services/taskApi';
import type { PageProps } from '../../types/ui';

const icons = [<ScheduleOutlined />, <CheckCircleOutlined />, <PlayCircleOutlined />, <CloseCircleOutlined />, <BellOutlined />];

const tabs = [
  { key: 'task-schedule', label: '任务调度' },
  { key: 'task-log', label: '运行日志' },
  { key: 'task-alert', label: '运行健康' },
  { key: 'task-retry', label: '失败重试' }
];

const taskOptions = [
  { value: 'knowledge_import', label: '知识库导入' },
  { value: 'embedding_refresh', label: 'Embedding 刷新' },
  { value: 'report_generate', label: '报告生成' },
  { value: 'sync_core_data', label: '数据同步' },
  { value: 'fast_forecast', label: '快速预测' },
  { value: 'health_check', label: '健康检查' }
];

const defaultSchedule = { name: 'PowerMarket_WebDaily', mode: 'refresh_fast_forecast', run_time: '06:30', highest: false };

function statusColor(status: string) {
  const value = String(status || '').toLowerCase();
  if (value === 'success') return 'success';
  if (value === 'running') return 'processing';
  if (value === 'queued' || value === 'pending' || value === 'retrying') return 'blue';
  if (value === 'cancel_requested') return 'warning';
  if (value === 'cancelled') return 'default';
  if (value === 'timeout') return 'orange';
  if (value === 'failed') return 'error';
  return 'default';
}

function failureAdvice(task: any) {
  if (task.status === 'timeout') return '任务超时。建议检查 timeout_seconds、worker 资源和外部服务耗时后重试。';
  if (task.status === 'failed') return '任务失败。请先查看最后一条 error 日志和 error_detail，再决定是否重试。';
  if (task.status === 'cancelled') return '任务已取消。如需继续，请确认业务参数后重新提交。';
  return '当前状态无需处理。';
}

function canCancelTask(status: string) {
  return ['pending', 'queued', 'running', 'retrying', 'cancel_requested'].includes(String(status || '').toLowerCase());
}

function canRetryTask(task: any) {
  const status = String(task?.status || '').toLowerCase();
  const retryCount = Number(task?.retry_count ?? 0);
  const maxRetries = Number(task?.max_retries ?? 0);
  return ['failed', 'timeout'].includes(status) && retryCount < maxRetries;
}

function taskTimelineItems(task: any) {
  return [
    ['created_at', '创建'],
    ['queued_at', '入队'],
    ['started_at', '开始'],
    ['timeout_at', '超时'],
    ['cancelled_at', '取消'],
    ['finished_at', '完成']
  ]
    .filter(([key]) => task?.[key])
    .map(([key, label]) => ({
      color: key === 'timeout_at' ? 'orange' : key === 'cancelled_at' ? 'gray' : key === 'finished_at' && task?.status === 'failed' ? 'red' : 'green',
      children: `${label}：${task[key]}`
    }));
}

export function TaskCenterPage({ activeSubKey, onSubNavigate }: PageProps) {
  const [taskData, setTaskData] = useState<any>(taskMock);
  const [loading, setLoading] = useState(true);
  const [createOpen, setCreateOpen] = useState(false);
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailData, setDetailData] = useState<Record<string, unknown> | null>(null);
  const [logOpen, setLogOpen] = useState(false);
  const [logText, setLogText] = useState('');
  const [logLoading, setLogLoading] = useState(false);
  const [selectedTaskKind, setSelectedTaskKind] = useState('knowledge_import');
  const [cancelReason, setCancelReason] = useState('前端用户请求取消');
  const [scheduleDraft, setScheduleDraft] = useState(defaultSchedule);

  async function loadData() {
    setLoading(true);
    try {
      setTaskData(await getTaskCenterData());
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData();
  }, []);

  async function runTask(kind = selectedTaskKind) {
    const res = await api.runTask(kind);
    message.success(res.deduped ? `已有相同任务：${res.task_id}` : `任务已提交：${res.task_id || kind}`);
    await loadData();
  }

  async function retryTask(taskId?: string) {
    if (!taskId) {
      message.warning('缺少 task_id');
      return;
    }
    const res = await api.taskRetry(taskId);
    message.success(`重试任务已创建：${res.task_id || taskId}`);
    await loadData();
  }

  async function cancelTask(taskId?: string) {
    if (!taskId) {
      message.warning('缺少 task_id');
      return;
    }
    const res = await api.taskCancel(taskId, cancelReason);
    message.success(res.status === 'cancelled' ? `任务已取消：${taskId}` : `取消请求已记录：${taskId}`);
    await loadData();
  }

  async function openLogs(taskId?: string) {
    if (!taskId) {
      setLogText('该记录没有 task_id，无法读取日志。');
      setLogOpen(true);
      return;
    }
    setLogOpen(true);
    setLogLoading(true);
    try {
      const payload = await api.taskLogs(taskId, 1, 50);
      const lines = (payload.items || []).map((item: any) => {
        const level = String(item.level || 'info').toUpperCase();
        const step = item.step || 'summary';
        const time = item.created_at || '';
        return `[${level}] ${step} ${time} ${item.message || item.log_text || ''}`;
      });
      setLogText(lines.join('\n') || payload.text || '暂无日志');
    } catch (error) {
      setLogText(error instanceof Error ? error.message : '日志读取失败');
    } finally {
      setLogLoading(false);
    }
  }

  async function createSchedule() {
    await api.createScheduledTask(scheduleDraft);
    message.success('定时任务已保存');
    setCreateOpen(false);
    await loadData();
  }

  const tasks = Array.isArray(taskData.tasks) ? taskData.tasks : [];
  const health = taskData.health || {};
  const scheduleRows = Array.isArray(taskData.schedules) ? taskData.schedules.map((row: any, index: number) => ({ key: row.name || index, ...row })) : [];
  const retryRows = Array.isArray(taskData.retryQueue) ? taskData.retryQueue : [];
  const queueRows = Array.isArray(health.queue_summary) ? health.queue_summary.map((row: any) => ({ key: row.queue_name, ...row })) : [];
  const failedRows = useMemo(() => tasks.filter((task: any) => ['failed', 'timeout', 'cancelled'].includes(String(task.status))), [tasks]);

  return (
    <div className="page-stack">
      <PageTabs items={tabs} activeKey={activeSubKey} onChange={onSubNavigate} />
      <div className="page-toolbar">
        <Space wrap>
          <Select value={selectedTaskKind} options={taskOptions} onChange={setSelectedTaskKind} style={{ width: 180 }} />
          <DatePicker />
          <Input value={cancelReason} onChange={(event) => setCancelReason(event.target.value)} placeholder="取消原因" style={{ width: 220 }} />
          <Button onClick={() => runTask('knowledge_import')}>Knowledge</Button>
          <Button onClick={() => runTask('embedding_refresh')}>Embedding</Button>
          <Button onClick={() => runTask('report_generate')}>Report</Button>
          <Button icon={<ReloadOutlined />} onClick={loadData}>刷新</Button>
          <Button type="primary" icon={<PlayCircleOutlined />} onClick={() => runTask()}>启动任务</Button>
        </Space>
      </div>
      <DataStateBanner
        scope="任务中心"
        loading={loading}
        source={taskData.dataSource}
        error={taskData.error}
        empty={taskData.empty}
        mockFallback={taskData.mockFallback}
        fallbackReason={taskData.fallbackReason}
        partialErrors={taskData.partialErrors}
        onRetry={loadData}
      />
      <MetricGrid items={taskData.metrics || []} icons={icons} loading={loading} minColumnWidth={180} />

      {activeSubKey === 'task-schedule' && (
        <TableCard
          title="任务列表"
          loading={loading}
          extra={<Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>新建定时任务</Button>}
          dataSource={tasks.map((task: any) => ({ key: task.task_id, ...task }))}
          columns={[
            { title: '任务类型', dataIndex: 'kind', render: (_: any, record: any) => record.task_name || record.kind || record.task_kind },
            { title: '状态', dataIndex: 'status', render: (value: string) => <Tag color={statusColor(value)}>{statusText(value)}</Tag> },
            { title: '进度', dataIndex: 'progress', render: (value: any) => `${value ?? 0}%` },
            { title: '队列', dataIndex: 'queue_name', render: (value: string) => value || 'default' },
            { title: '创建时间', dataIndex: 'created_at', render: (value: string) => value || '--' },
            { title: '开始时间', dataIndex: 'started_at', render: (value: string) => value || '--' },
            { title: '完成时间', render: (_: any, record: any) => record.finished_at || record.ended_at || '--' },
            { title: '重试', render: (_: any, record: any) => `${record.retry_count ?? 0}/${record.max_retries ?? 0}` },
            { title: '执行模式', dataIndex: 'execution_mode', render: (value: string) => value || '--' },
            {
              title: '操作',
              render: (_: any, record: any) => (
                <Space>
                  <Button type="link" size="small" onClick={() => openLogs(record.task_id)}>日志</Button>
                  <Button type="link" size="small" disabled={!canCancelTask(record.status)} onClick={() => cancelTask(record.task_id)}>取消</Button>
                  <Button type="link" size="small" disabled={!canRetryTask(record)} onClick={() => retryTask(record.task_id)}>重试</Button>
                  <Button type="link" size="small" onClick={() => { setDetailData(record); setDetailOpen(true); }}>详情</Button>
                </Space>
              )
            }
          ]}
        />
      )}

      {activeSubKey === 'task-log' && (
        <TableCard
          title="运行日志"
          loading={loading}
          dataSource={tasks.map((task: any) => ({ key: task.task_id, ...task }))}
          columns={[
            { title: '任务', render: (_: any, record: any) => record.task_name || record.kind || '--' },
            { title: '状态', dataIndex: 'status', render: (value: string) => <Tag color={statusColor(value)}>{statusText(value)}</Tag> },
            { title: '耗时', dataIndex: 'duration_seconds', render: durationText },
            { title: 'worker', dataIndex: 'worker_id', render: (value: string) => value || '--' },
            { title: 'celery_task_id', dataIndex: 'celery_task_id', render: (value: string) => value || '--' },
            { title: 'timeout', dataIndex: 'timeout_seconds', render: (value: any) => (value ? `${value}s` : '--') },
            { title: '消息', render: (_: any, record: any) => record.error_message || record.message || '--' },
            {
              title: '操作',
              render: (_: any, record: any) => (
                <Space>
                  <Button type="link" size="small" onClick={() => openLogs(record.task_id)}>分页日志</Button>
                  <Button type="link" size="small" onClick={() => { setDetailData({ payload: record.payload, result_ref: record.result_ref, error_detail: record.error_detail, metadata: record.metadata }); setDetailOpen(true); }}>详情</Button>
                </Space>
              )
            }
          ]}
        />
      )}

      {activeSubKey === 'task-retry' && (
        <TableCard
          title="失败/超时/取消任务"
          loading={loading}
          dataSource={retryRows}
          columns={[
            { title: '任务名称', dataIndex: 'task_name' },
            { title: '状态', dataIndex: 'status', render: (value: string) => <Tag color={statusColor(value)}>{statusText(value)}</Tag> },
            { title: '失败时间', dataIndex: 'failed_at' },
            { title: '原因', dataIndex: 'error_message' },
            { title: '重试次数', render: (_: any, record: any) => `${record.retry_count ?? 0}/${record.max_retries ?? 0}` },
            { title: '处理建议', render: (_: any, record: any) => failureAdvice(record) },
            { title: '操作', render: (_: any, record: any) => <Button type="link" size="small" disabled={!canRetryTask(record)} onClick={() => retryTask(record.task_id)}>重试</Button> }
          ]}
        />
      )}

      {activeSubKey === 'task-alert' && (
        <div className="knowledge-two-column">
          <SectionCard title="运行态健康" loading={loading}>
            <Descriptions column={1} size="small">
              <Descriptions.Item label="execution_mode">{health.execution_mode || '--'}</Descriptions.Item>
              <Descriptions.Item label="redis">{health.redis?.ok ? '正常' : '异常或未配置'}</Descriptions.Item>
              <Descriptions.Item label="celery">{health.celery?.ok || health.celery_available ? '正常' : '异常或未配置'}</Descriptions.Item>
              <Descriptions.Item label="active_workers">{(health.active_workers || []).join(', ') || '--'}</Descriptions.Item>
              <Descriptions.Item label="running">{health.running_task_count ?? 0}</Descriptions.Item>
              <Descriptions.Item label="pending">{health.pending_task_count ?? 0}</Descriptions.Item>
              <Descriptions.Item label="failed">{health.failed_task_count ?? 0}</Descriptions.Item>
              <Descriptions.Item label="timeout">{health.timeout_task_count ?? 0}</Descriptions.Item>
            </Descriptions>
            {!health.ok && <Alert type="warning" showIcon message={health.message || '任务运行态异常'} />}
          </SectionCard>
          <TableCard
            title="队列概览"
            loading={loading}
            dataSource={queueRows}
            columns={[
              { title: '队列', dataIndex: 'queue_name' },
              { title: '总数', dataIndex: 'total' },
              { title: '待执行', dataIndex: 'pending' },
              { title: '运行中', dataIndex: 'running' },
              { title: '失败', dataIndex: 'failed' },
              { title: '超时', dataIndex: 'timeout' }
            ]}
          />
        </div>
      )}

      <Modal title="新建定时任务" open={createOpen} onCancel={() => setCreateOpen(false)} onOk={createSchedule}>
        <Form layout="vertical">
          <Form.Item label="任务名称" required>
            <Select value={scheduleDraft.name} onChange={(value) => setScheduleDraft((prev) => ({ ...prev, name: value }))} options={[{ value: 'PowerMarket_WebDaily', label: 'PowerMarket_WebDaily' }]} />
          </Form.Item>
          <Form.Item label="执行模式">
            <Select
              value={scheduleDraft.mode}
              onChange={(value) => setScheduleDraft((prev) => ({ ...prev, mode: value }))}
              options={[
                { value: 'refresh_fast_forecast', label: '刷新预测' },
                { value: 'model_ops_daily', label: '模型运维' },
                { value: 'health_check', label: '健康检查' }
              ]}
            />
          </Form.Item>
          <Form.Item label="执行时间">
            <Select value={scheduleDraft.run_time} onChange={(value) => setScheduleDraft((prev) => ({ ...prev, run_time: value }))} options={[{ value: '06:30', label: '06:30' }, { value: '08:00', label: '08:00' }]} />
          </Form.Item>
        </Form>
      </Modal>
      <DetailDrawer title="任务详情" open={detailOpen} data={detailData} onClose={() => setDetailOpen(false)}>
        {detailData?.task_id ? (
          <div className="task-detail-summary">
            <Alert
              showIcon
              type={['failed', 'timeout'].includes(String(detailData.status)) ? 'warning' : String(detailData.status) === 'cancelled' ? 'info' : 'success'}
              message={`当前状态：${statusText(detailData.status)}`}
              description={failureAdvice(detailData)}
            />
            <Timeline items={taskTimelineItems(detailData)} />
            {(detailData.error_message || detailData.error_detail) && (
              <Alert showIcon type="error" message="最后错误摘要" description={String(detailData.error_message || detailData.error_detail)} />
            )}
            {(detailData.parent_task_id || detailData.original_task_id) && (
              <Alert showIcon type="info" message="重试链路" description={`parent=${detailData.parent_task_id || '--'}，original=${detailData.original_task_id || '--'}`} />
            )}
          </div>
        ) : null}
      </DetailDrawer>
      <TaskLogViewer open={logOpen} title="任务分页日志" log={logText} loading={logLoading} onClose={() => setLogOpen(false)} />
    </div>
  );
}
