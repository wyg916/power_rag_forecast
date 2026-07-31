import {
  AlertOutlined,
  AppstoreOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  CloudServerOutlined,
  CodeOutlined,
  ColumnHeightOutlined,
  DatabaseOutlined,
  ExportOutlined,
  FilterOutlined,
  FullscreenOutlined,
  MoreOutlined,
  PlayCircleOutlined,
  PlusOutlined,
  ReloadOutlined,
  ScheduleOutlined,
  TeamOutlined,
  WarningOutlined
} from '@ant-design/icons';
import { Button, DatePicker, Descriptions, Dropdown, Form, Input, Modal, Progress, Select, Space, Table, Tag, Timeline, Typography, message } from 'antd';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '../../api';
import { DetailDrawer } from '../../components/actions/DetailDrawer';
import { TaskLogViewer } from '../../components/actions/TaskLogViewer';
import { AppChart } from '../../components/charts/AppChart';
import { baseGrid, chartColors } from '../../components/charts/chartTheme';
import { PageHeader } from '../../components/common/PageHeader';
import { useAuth } from '../../context/AuthContext';
import { getTaskCenterData, statusText } from '../../services/taskApi';
import type { PageProps } from '../../types/ui';

const { RangePicker } = DatePicker;

const taskOptions = [
  { value: 'all', label: '全部' },
  { value: 'knowledge_import', label: '知识库导入' },
  { value: 'embedding_refresh', label: 'Embedding 刷新' },
  { value: 'report_generate', label: '报告生成' },
  { value: 'sync_core_data', label: '数据同步' },
  { value: 'data_clean', label: '数据清洗' },
  { value: 'price_predict', label: '电价预测' },
  { value: 'load_predict', label: '负荷预测' },
  { value: 'strategy_gen', label: '策略生成' },
  { value: 'report_daily', label: '收益分析' },
  { value: 'monitor_rt', label: '异常监测' },
  { value: 'model_train', label: '模型训练' },
  { value: 'fast_forecast', label: '快速预测' },
  { value: 'health_check', label: '健康检查' }
];

const queueOptions = [
  { value: 'all', label: '全部' },
  { value: 'data_sync', label: 'data_sync' },
  { value: 'data_clean', label: 'data_clean' },
  { value: 'price_predict', label: 'price_predict' },
  { value: 'load_predict', label: 'load_predict' },
  { value: 'strategy_gen', label: 'strategy_gen' },
  { value: 'report_daily', label: 'report_daily' },
  { value: 'monitor_rt', label: 'monitor_rt' },
  { value: 'model_train', label: 'model_train' },
  { value: 'default', label: 'default' }
];

const defaultSchedule = { name: 'PowerMarket_WebDaily', mode: 'refresh_fast_forecast', run_time: '06:30', highest: false };

const queuePalette = ['#2563EB', '#10B981', '#8B5CF6', '#F59E0B', '#06B6D4', '#34D399'];

function statusColor(status: string) {
  const value = String(status || '').toLowerCase();
  if (value === 'success') return 'success';
  if (value === 'running') return 'processing';
  if (value === 'queued' || value === 'pending' || value === 'retrying') return 'warning';
  if (value === 'cancel_requested') return 'warning';
  if (value === 'cancelled') return 'default';
  if (value === 'timeout') return 'orange';
  if (value === 'failed') return 'error';
  return 'default';
}

function progressColor(status: string) {
  const value = String(status || '').toLowerCase();
  if (value === 'success') return '#10B981';
  if (value === 'running') return '#2563EB';
  if (value === 'timeout' || value === 'failed') return '#EF4444';
  return '#CBD5E1';
}

function taskProgress(task: any) {
  const raw = Number(task?.progress);
  if (Number.isFinite(raw) && raw >= 0) return Math.min(100, Math.max(0, raw));
  const status = String(task?.status || '').toLowerCase();
  if (status === 'success') return 100;
  if (status === 'running') return 68;
  if (status === 'timeout') return 26;
  if (status === 'failed') return 0;
  return 0;
}

function taskName(task: any) {
  return task?.task_name || task?.name || task?.kind || task?.task_kind || '系统任务';
}

function queueName(task: any) {
  return task?.queue_name || task?.queue || task?.task_kind || 'default';
}

function shortTime(value: unknown) {
  const text = String(value || '');
  if (!text) return '-';
  return text.replace('T', ' ').replace(/\.\d+$/, '').slice(11, 19) || text;
}

function shortDateTime(value: unknown) {
  const text = String(value || '');
  if (!text) return '-';
  return text.replace('T', ' ').replace(/\.\d+$/, '').slice(0, 19);
}

function shortId(value: unknown) {
  const text = String(value || '');
  if (!text) return '-';
  return text.length > 18 ? `${text.slice(0, 18)}...` : text;
}

function failureAdvice(task: any) {
  const status = String(task?.status || '').toLowerCase();
  const messageText = String(task?.error_message || task?.message || '');
  if (messageText.includes('连接') || messageText.toLowerCase().includes('connection')) return '检查源数据库网络与连接配置';
  if (status === 'timeout') return '优化数据量或延长超时时间';
  if (messageText.includes('内存') || messageText.toLowerCase().includes('memory')) return '增加 worker 内存配置';
  if (status === 'failed') return '查看错误日志后立即重试';
  return '确认业务参数后重试';
}

function canCancelTask(status: string) {
  return ['pending', 'queued', 'running', 'retrying', 'cancel_requested'].includes(String(status || '').toLowerCase());
}

function canRetryTask(task: any) {
  const status = String(task?.status || '').toLowerCase();
  const retryCount = Number(task?.retry_count ?? 0);
  const maxRetries = Number(task?.max_retries ?? 3);
  return ['failed', 'timeout', 'cancelled', 'canceled'].includes(status) && retryCount < maxRetries;
}

function taskTimelineItems(task: any) {
  return [
    ['created_at', '创建'],
    ['queued_at', '入队'],
    ['started_at', '开始'],
    ['timeout_at', '超时'],
    ['cancelled_at', '取消'],
    ['finished_at', '完成'],
    ['ended_at', '结束']
  ]
    .filter(([key]) => task?.[key])
    .map(([key, label]) => ({
      color: key === 'timeout_at' ? 'orange' : key === 'cancelled_at' ? 'gray' : key === 'finished_at' && task?.status === 'failed' ? 'red' : 'green',
      children: `${label}：${task[key]}`
    }));
}

function jsonPreview(value: unknown) {
  if (value === undefined || value === null || value === '') return '--';
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

export function TaskCenterPage(_props: PageProps) {
  const [taskData, setTaskData] = useState<any>({ tasks: [], metrics: [], health: {}, retryQueue: [], recentLogs: [], queueRows: [], trendRows: [] });
  const [loading, setLoading] = useState(true);
  const { authRequired, hasPermission } = useAuth();
  const canRunTask = !authRequired || hasPermission('task:manage');
  const [createOpen, setCreateOpen] = useState(false);
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailData, setDetailData] = useState<Record<string, unknown> | null>(null);
  const [detailLogs, setDetailLogs] = useState<any[]>([]);
  const [detailLoading, setDetailLoading] = useState(false);
  const [logOpen, setLogOpen] = useState(false);
  const [logText, setLogText] = useState('');
  const [logLoading, setLogLoading] = useState(false);
  const [selectedTaskKind, setSelectedTaskKind] = useState('all');
  const [selectedQueue, setSelectedQueue] = useState('all');
  const [keyword, setKeyword] = useState('');
  const [dateRange, setDateRange] = useState<any>(null);
  const [cancelReason] = useState('前端用户请求取消');
  const [scheduleDraft, setScheduleDraft] = useState(defaultSchedule);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const startDate = dateRange?.[0]?.format?.('YYYY-MM-DD') || '';
      const endDate = dateRange?.[1]?.format?.('YYYY-MM-DD') || '';
      setTaskData(await getTaskCenterData({
        task_type: selectedTaskKind === 'all' ? '' : selectedTaskKind,
        queue_name: selectedQueue === 'all' ? '' : selectedQueue,
        keyword,
        start_date: startDate,
        end_date: endDate,
        page: 1,
        page_size: 100
      }));
    } finally {
      setLoading(false);
    }
  }, [dateRange, keyword, selectedQueue, selectedTaskKind]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  async function runTask(kind = selectedTaskKind) {
    const safeKind = kind === 'all' ? 'health_check' : kind;
    const res = await api.taskStart({
      task_type: safeKind,
      task_name: taskOptions.find((item) => item.value === safeKind)?.label || safeKind,
      queue_name: selectedQueue === 'all' ? undefined : selectedQueue,
      execution_mode: 'manual',
      payload: { source: 'task_center' }
    });
    message.success(res.deduped ? `已有相同任务：${res.task_id}` : `任务已提交：${res.task_id || safeKind}`);
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
      const payload = await api.taskLogs(taskId, 1, 80);
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

  async function openDetail(record: any) {
    const taskId = record?.task_id;
    if (!taskId) {
      setDetailData(record);
      setDetailLogs([]);
      setDetailOpen(true);
      return;
    }
    setDetailOpen(true);
    setDetailLoading(true);
    setDetailData(record);
    try {
      const [detail, logs] = await Promise.all([
        api.taskDetail(taskId),
        api.taskLogs(taskId, 1, 120).catch(() => ({ items: [] }))
      ]);
      setDetailData(detail || record);
      setDetailLogs(Array.isArray(logs?.items) ? logs.items : []);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '任务详情读取失败');
    } finally {
      setDetailLoading(false);
    }
  }

  async function createSchedule() {
    await api.createScheduledTask(scheduleDraft);
    message.success('定时任务已保存');
    setCreateOpen(false);
    await loadData();
  }

  const rawTasks = Array.isArray(taskData.tasks) ? taskData.tasks : [];
  const tasks = useMemo(() => rawTasks, [rawTasks]);
  const health = taskData.health || {};
  const retryRows = Array.isArray(taskData.retryQueue) ? taskData.retryQueue : [];
  const queueRows = Array.isArray(taskData.queueRows) ? taskData.queueRows : [];
  const recentLogRows = Array.isArray(taskData.recentLogs) ? taskData.recentLogs : [];
  const trendRows = Array.isArray(taskData.trendRows) ? taskData.trendRows : [];
  const overview = taskData.overview || {};

  const successCount = Number(overview.success_total || 0);
  const runningCount = Number(overview.running_total ?? health.running_task_count ?? 0);
  const pendingCount = Number(overview.pending_total ?? health.pending_task_count ?? 0);
  const failedCount = Number(overview.failed_total ?? health.failed_task_count ?? 0);
  const timeoutCount = Number(overview.timeout_total ?? health.timeout_task_count ?? 0);

  const metricIcons = [<ScheduleOutlined />, <CheckCircleOutlined />, <PlayCircleOutlined />, <AlertOutlined />, <DatabaseOutlined />];
  const metricTones = ['green', 'green', 'blue', 'red', 'purple'];
  const kpis = (Array.isArray(taskData.metrics) ? taskData.metrics : []).map((item: any, index: number) => ({
    ...item,
    tone: metricTones[index] || 'green',
    icon: metricIcons[index] || <ScheduleOutlined />
  }));

  const trendOption = useMemo(() => ({
    ...baseGrid(),
    tooltip: { trigger: 'axis' },
    legend: { top: 0, data: ['成功', '失败', '运行中'] },
    grid: { left: 46, right: 24, top: 42, bottom: 28 },
    xAxis: { ...(baseGrid().xAxis as object), data: trendRows.map((item) => item.date) },
    yAxis: { type: 'value', splitLine: { lineStyle: { color: '#EEF2F6' } }, axisLabel: { color: '#64748B' } },
    series: [
      { name: '成功', type: 'line', smooth: true, areaStyle: { color: 'rgba(16, 185, 129, 0.12)' }, data: trendRows.map((item) => item.success), lineStyle: { color: chartColors.green } },
      { name: '失败', type: 'line', smooth: true, data: trendRows.map((item) => item.failed), lineStyle: { color: chartColors.red } },
      { name: '运行中', type: 'line', smooth: true, data: trendRows.map((item) => item.running), lineStyle: { color: chartColors.blue } }
    ]
  }), [trendRows]);

  const queueOption = useMemo(() => ({
    tooltip: { trigger: 'item' },
    color: queuePalette,
    series: [
      {
        type: 'pie',
        radius: ['48%', '72%'],
        center: ['50%', '50%'],
        avoidLabelOverlap: true,
        label: { show: false },
        data: queueRows.map((row: any) => ({ name: row.queue_name, value: Math.max(1, Number(row.total || row.running + row.pending + row.failed || 1)) }))
      }
    ]
  }), [queueRows]);

  const healthCards = [
    { label: 'execution_mode', value: health.execution_mode || 'distributed', tone: 'blue', icon: <CodeOutlined /> },
    { label: 'Redis', value: health.redis?.ok ? '运行中' : '待确认', tone: 'green', icon: <DatabaseOutlined /> },
    { label: 'Celery', value: health.celery?.ok || health.celery_available ? '运行中' : '待确认', tone: 'green', icon: <CloudServerOutlined /> },
    { label: 'active_workers', value: `${(health.active_workers || []).length || 0} / 20`, tone: 'green', icon: <TeamOutlined /> },
    { label: 'running', value: runningCount, tone: 'blue', icon: <PlayCircleOutlined /> },
    { label: 'pending', value: pendingCount, tone: 'blue', icon: <ClockCircleOutlined /> },
    { label: 'failed', value: failedCount, tone: 'red', icon: <WarningOutlined /> },
    { label: 'timeout', value: timeoutCount, tone: 'red', icon: <ClockCircleOutlined /> }
  ];

  const taskColumns = [
    { title: '', width: 34, render: () => <input type="checkbox" aria-label="选择任务" /> },
    { title: '任务名称', width: 168, render: (_: any, record: any) => taskName(record) },
    { title: '状态', width: 80, dataIndex: 'status', render: (value: string) => <Tag color={statusColor(value)}>{statusText(value)}</Tag> },
    { title: '进度', width: 116, render: (_: any, record: any) => <Progress percent={taskProgress(record)} size="small" showInfo={false} strokeColor={progressColor(record.status)} /> },
    { title: '队列', width: 118, render: (_: any, record: any) => queueName(record) },
    { title: '创建时间', width: 160, dataIndex: 'created_at', render: shortDateTime },
    { title: '开始时间', width: 92, dataIndex: 'started_at', render: shortTime },
    { title: '完成时间', width: 92, render: (_: any, record: any) => shortTime(record.finished_at || record.ended_at) },
    { title: '重试次数', width: 86, render: (_: any, record: any) => record.retry_count ?? 0 },
    { title: '执行模式', width: 92, dataIndex: 'execution_mode', render: (value: string) => value || '定时任务' },
    {
      title: '操作',
      width: 150,
      fixed: 'right' as const,
      render: (_: any, record: any) => (
        <Space size={4}>
          <Button type="link" size="small" onClick={() => openDetail(record)}>详情</Button>
          <Button type="link" size="small" onClick={() => openLogs(record.task_id)}>日志</Button>
          <Dropdown
            menu={{
              items: [
                { key: 'cancel', label: '取消任务', disabled: !canCancelTask(record.status) },
                { key: 'retry', label: '立即重试', disabled: !canRetryTask(record) }
              ],
              onClick: ({ key }) => {
                if (key === 'cancel') cancelTask(record.task_id);
                if (key === 'retry') retryTask(record.task_id);
              }
            }}
          >
            <Button type="link" size="small">更多</Button>
          </Dropdown>
        </Space>
      )
    }
  ];

  const logColumns = [
    { title: '时间', width: 76, render: (_: any, record: any) => shortTime(record.updated_at || record.created_at) },
    { title: '任务名称', render: (_: any, record: any) => taskName(record) },
    { title: 'Worker', width: 86, dataIndex: 'worker_id', render: (value: string) => value || 'worker-01' },
    { title: 'Celery Task ID', width: 150, dataIndex: 'celery_task_id', render: shortId },
    { title: '消息', render: (_: any, record: any) => record.error_message || record.message || (record.status === 'success' ? '任务执行完成' : statusText(record.status)) }
  ];

  const retryColumns = [
    { title: '失败时间', width: 140, render: (_: any, record: any) => shortDateTime(record.ended_at || record.finished_at || record.started_at) },
    { title: '任务名称', render: (_: any, record: any) => taskName(record) },
    { title: '原因', render: (_: any, record: any) => record.error_message || statusText(record.status) },
    { title: '处理建议', render: (_: any, record: any) => failureAdvice(record) },
    { title: '操作', width: 98, render: (_: any, record: any) => <Button className="task-retry-button" size="small" disabled={!canRetryTask(record)} onClick={() => retryTask(record.task_id)}>立即重试</Button> }
  ];

  const queueColumns = [
    { title: '队列', dataIndex: 'queue_name' },
    { title: '运行中', dataIndex: 'running' },
    { title: '排队中', dataIndex: 'pending' },
    { title: '失败', dataIndex: 'failed' },
    { title: '占比', render: (_: any, record: any) => `${Number(record.percent ?? record.success_rate ?? 0).toFixed(2)}%` }
  ];

  return (
    <div className="task-workbench-page">
      <PageHeader
        title="任务中心"
        subtitle="集中管理任务调度、运行日志、运行健康与失败重试，保障任务稳定可靠执行。"
        filters={<div className="task-filter-actions">
          <span>任务类型</span>
          <Select value={selectedTaskKind} options={taskOptions} onChange={setSelectedTaskKind} />
          <span>日期范围</span>
          <RangePicker value={dateRange} onChange={setDateRange} />
          <span>关键词</span>
          <Input value={keyword} onChange={(event) => setKeyword(event.target.value)} placeholder="请输入任务名称/任务ID" allowClear />
          <span>队列标签</span>
          <Select value={selectedQueue} options={queueOptions} onChange={setSelectedQueue} />
        </div>}
        actions={[
          { key: 'refresh', label: '刷新', icon: <ReloadOutlined />, loading, onClick: loadData },
          {
            key: 'run',
            label: '启动任务',
            icon: <PlayCircleOutlined />,
            type: 'primary',
            disabled: !canRunTask || selectedTaskKind === 'all',
            disabledReason: !canRunTask ? '需要 task:run 权限' : '请先选择具体任务类型',
            onClick: () => runTask()
          }
        ]}
      />

      <div className="task-body-grid">
        <div className="task-left-column">
          <div className="task-kpi-grid">
            {kpis.map((item) => (
              <div className={`task-kpi-card tone-${item.tone}`} key={item.title}>
                <i>{item.icon}</i>
                <div>
                  <span>{item.title}</span>
                  <strong>{item.value}</strong>
                  <p>{item.note}</p>
                </div>
              </div>
            ))}
          </div>

          <section className="task-card task-list-card">
            <div className="task-card-head">
              <div>
                <h2>任务列表</h2>
                <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>新建定时任务</Button>
              </div>
              <Space size={8}>
                <Button icon={<ColumnHeightOutlined />}>列设置</Button>
                <Button icon={<FilterOutlined />}>筛选</Button>
                <Button icon={<FullscreenOutlined />} />
              </Space>
            </div>
            <Table
              className="task-table"
              size="small"
              rowKey={(record) => record.task_id || `${taskName(record)}-${record.created_at}`}
              loading={loading}
              dataSource={tasks}
              columns={taskColumns}
              pagination={{ total: Math.max(8, tasks.length), pageSize: 8, showSizeChanger: false, showQuickJumper: true }}
              scroll={{ x: 1250, y: 520 }}
            />
          </section>

          <section className="task-card task-trend-card">
            <div className="task-card-head">
              <div>
                <h2>任务执行趋势</h2>
                <div className="task-trend-legend">
                  <span className="green">成功 <b>{successCount}</b></span>
                  <span className="red">失败 <b>{failedCount}</b></span>
                  <span className="blue">运行中 <b>{runningCount}</b></span>
                </div>
              </div>
              <Space size={6}>
                <Button className="active">近 7 天</Button>
                <Button>近 30 天</Button>
                <Button icon={<ExportOutlined />} />
              </Space>
            </div>
            <AppChart option={trendOption} height={168} />
          </section>
        </div>

        <div className="task-right-column">
          <div className="task-right-top-stack">
            <section className="task-card task-health-card">
              <div className="task-card-head">
                <h2>任务健康</h2>
                <Button type="link">详情</Button>
              </div>
              <div className="task-health-grid">
                {healthCards.map((item) => (
                  <div className={`task-health-item tone-${item.tone}`} key={item.label}>
                    <i>{item.icon}</i>
                    <span>{item.label}</span>
                    <strong>{item.value}</strong>
                  </div>
                ))}
              </div>
            </section>

            <section className="task-card task-side-table-card">
              <div className="task-card-head"><h2>运行日志（最近）</h2><Button type="link">更多</Button></div>
              <Table size="small" rowKey={(record) => record.task_id || record.created_at} pagination={false} dataSource={recentLogRows} columns={logColumns} scroll={{ y: 88, x: 650 }} />
            </section>

            <section className="task-card task-side-table-card">
              <div className="task-card-head"><h2>失败重试（最近）</h2><Button type="link">更多</Button></div>
              <Table size="small" rowKey={(record) => record.task_id || record.created_at} pagination={false} dataSource={retryRows.slice(0, 10)} columns={retryColumns} scroll={{ y: 88, x: 720 }} />
            </section>
          </div>

          <section className="task-card task-queue-card">
            <div className="task-card-head"><h2>队列概览</h2><Button type="link">更多</Button></div>
            <div className="task-queue-content">
              <AppChart option={queueOption} height={158} />
              <Table size="small" rowKey="queue_name" pagination={false} dataSource={queueRows.slice(0, 6)} columns={queueColumns} scroll={{ y: 120 }} />
            </div>
          </section>
        </div>
      </div>

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
            <Descriptions column={1} size="small" bordered>
              <Descriptions.Item label="任务 ID">{String(detailData.task_id || '--')}</Descriptions.Item>
              <Descriptions.Item label="任务名称">{taskName(detailData)}</Descriptions.Item>
              <Descriptions.Item label="任务状态">{statusText(detailData.status)}</Descriptions.Item>
              <Descriptions.Item label="队列">{String(detailData.queue_name || detailData.queue || '--')}</Descriptions.Item>
              <Descriptions.Item label="Worker">{String(detailData.worker_id || detailData.worker_name || '--')}</Descriptions.Item>
              <Descriptions.Item label="Celery Task ID">{String(detailData.celery_task_id || '--')}</Descriptions.Item>
              <Descriptions.Item label="处理建议">{failureAdvice(detailData)}</Descriptions.Item>
              <Descriptions.Item label="任务参数">
                <Typography.Text code>{jsonPreview(detailData.payload_json || detailData.payload)}</Typography.Text>
              </Descriptions.Item>
              <Descriptions.Item label="执行结果">
                <Typography.Text code>{jsonPreview(detailData.result_json || (detailData.metadata as any)?.result || detailData.result_ref)}</Typography.Text>
              </Descriptions.Item>
              <Descriptions.Item label="错误信息">
                <Typography.Text code>{jsonPreview(detailData.error_json || {
                  error_message: detailData.error_message,
                  error_code: detailData.error_code,
                  error_detail: detailData.error_detail
                })}</Typography.Text>
              </Descriptions.Item>
            </Descriptions>
            <Timeline items={taskTimelineItems(detailData)} />
            <Descriptions column={1} size="small" bordered>
              <Descriptions.Item label={detailLoading ? '执行日志加载中' : '执行日志'}>
                <pre className="task-log-viewer">
                  {detailLogs.length
                    ? detailLogs.map((item) => `[${String(item.level || 'info').toUpperCase()}] ${item.step || 'summary'} ${item.created_at || ''} ${item.message || item.log_text || ''}`).join('\n')
                    : '暂无日志'}
                </pre>
              </Descriptions.Item>
            </Descriptions>
          </div>
        ) : null}
      </DetailDrawer>
      <TaskLogViewer open={logOpen} title="任务分页日志" log={logText} loading={logLoading} onClose={() => setLogOpen(false)} />
    </div>
  );
}
