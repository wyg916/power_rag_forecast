import { BellOutlined, CheckCircleOutlined, CloseCircleOutlined, PlayCircleOutlined, PlusOutlined, ScheduleOutlined } from '@ant-design/icons';
import { Button, DatePicker, Form, Modal, Select, Space, Tag, message } from 'antd';
import { useEffect, useState } from 'react';
import { api } from '../../api';
import { DetailDrawer } from '../../components/actions/DetailDrawer';
import { TaskLogViewer } from '../../components/actions/TaskLogViewer';
import { SectionCard } from '../../components/cards/SectionCard';
import { TableCard } from '../../components/cards/TableCard';
import { PageTabs } from '../../components/common/PageTabs';
import { DataStateBanner } from '../../components/common/States';
import { MetricGrid } from '../../components/layout/UnifiedPage';
import { taskMock } from '../../mock/taskMock';
import { getTaskCenterData } from '../../services/taskApi';
import type { PageProps } from '../../types/ui';

const icons = [<ScheduleOutlined />, <CheckCircleOutlined />, <PlayCircleOutlined />, <CloseCircleOutlined />, <BellOutlined />];

const tabs = [
  { key: 'task-schedule', label: '任务调度' },
  { key: 'task-log', label: '运行日志' },
  { key: 'task-alert', label: '告警管理' },
  { key: 'task-retry', label: '失败重试' }
];

const defaultSchedule = { name: 'PowerMarket_WebDaily', mode: 'refresh_fast_forecast', run_time: '06:30', highest: false };

export function TaskCenterPage({ activeSubKey, onSubNavigate }: PageProps) {
  const [taskData, setTaskData] = useState<any>(taskMock);
  const [loading, setLoading] = useState(true);
  const [createOpen, setCreateOpen] = useState(false);
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailData, setDetailData] = useState<Record<string, unknown> | null>(null);
  const [logOpen, setLogOpen] = useState(false);
  const [logText, setLogText] = useState('');
  const [logLoading, setLogLoading] = useState(false);
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

  async function runTask(kind = 'today_analysis') {
    const res = await api.runTask(kind);
    message.success(`任务已启动：${res.task_id || kind}`);
    await loadData();
  }

  async function retryTask(taskId?: string) {
    if (!taskId) {
      message.warning('missing task_id');
      return;
    }
    const res = await api.taskRetry(taskId);
    message.success(`retry task created: ${res.task_id || taskId}`);
    await loadData();
  }

  async function cancelTask(taskId?: string) {
    if (!taskId) {
      message.warning('missing task_id');
      return;
    }
    await api.taskCancel(taskId);
    message.success(`cancel requested: ${taskId}`);
    await loadData();
  }

  async function openLogs(taskId?: string) {
    if (!taskId) {
      setLogText('该记录没有 task_id，无法读取完整日志。');
      setLogOpen(true);
      return;
    }
    setLogOpen(true);
    setLogLoading(true);
    try {
      setLogText(await api.taskLogs(taskId));
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

  const scheduleRows = (taskData.schedules || []).map((row: any[], index: number) => ({ key: index, row }));
  const logRows = (taskData.logs || []).map((row: any[], index: number) => ({ key: index, row }));
  const retryRows = (taskData.retryQueue || []).map((row: any[], index: number) => ({ key: index, row }));

  return (
    <div className="page-stack">
      <PageTabs items={tabs} activeKey={activeSubKey} onChange={onSubNavigate} />
      <div className="page-toolbar">
        <Space>
          <Select value="全部任务类型" options={[{ value: '全部任务类型', label: '全部任务类型' }]} />
          <DatePicker />
          <Button onClick={() => runTask('knowledge_import')}>Knowledge</Button>
          <Button onClick={() => runTask('embedding_refresh')}>Embedding</Button>
          <Button onClick={() => runTask('report_generate')}>Report</Button>
          <Button onClick={loadData}>刷新</Button>
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
          title="任务调度表"
          loading={loading}
          extra={<Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>新建任务</Button>}
          dataSource={scheduleRows}
          columns={[
            { title: '任务名称', render: (_, record: any) => record.row[0] },
            { title: '任务类型', render: (_, record: any) => <Tag color="success">{record.row[1]}</Tag> },
            { title: '执行周期', render: (_, record: any) => record.row[2] },
            { title: '表达式', render: (_, record: any) => record.row[3] },
            { title: '下次执行', render: (_, record: any) => record.row[4] },
            { title: '状态', render: (_, record: any) => <Tag color="processing">{record.row[5]}</Tag> },
            { title: '操作', render: (_, record: any) => <Space><Button type="link" size="small" onClick={() => { setDetailData({ schedule: record.row }); setDetailOpen(true); }}>详情</Button><Button type="link" size="small" onClick={() => runTask(record.row[1])}>立即运行</Button></Space> }
          ]}
        />
      )}

      {activeSubKey === 'task-log' && (
        <TableCard
          title="运行日志"
          loading={loading}
          dataSource={logRows}
          columns={[
            { title: '任务名称', render: (_, record: any) => record.row[0] },
            { title: '任务类型', render: (_, record: any) => record.row[1] },
            { title: '状态', render: (_, record: any) => <Tag color={record.row[2] === '成功' ? 'success' : record.row[2] === '运行中' ? 'processing' : 'error'}>{record.row[2]}</Tag> },
            { title: '开始时间', render: (_, record: any) => record.row[3] },
            { title: '结束时间', render: (_, record: any) => record.row[4] },
            { title: '耗时', render: (_, record: any) => record.row[5] },
            { title: '进度', render: (_, record: any) => `${record.row[8] ?? 0}%` },
            { title: '执行模式', render: (_, record: any) => record.row[9] || '--' },
            { title: '消息', render: (_, record: any) => record.row[10] || '--' },
            { title: '结果', render: (_, record: any) => record.row[11] || '--' },
            { title: '操作', render: (_, record: any) => <Space><Button type="link" size="small" onClick={() => openLogs(record.row[7])}>日志</Button><Button type="link" size="small" onClick={() => cancelTask(record.row[7])}>取消</Button><Button type="link" size="small" onClick={() => { setDetailData({ task: record.row }); setDetailOpen(true); }}>详情</Button></Space> }
          ]}
        />
      )}

      {activeSubKey === 'task-retry' && (
        <TableCard
          title="失败重试队列"
          loading={loading}
          dataSource={retryRows}
          columns={[
            { title: '任务名称', render: (_, record: any) => record.row[0] },
            { title: '失败时间', render: (_, record: any) => record.row[1] },
            { title: '失败原因', render: (_, record: any) => record.row[2] },
            { title: '操作', render: (_, record: any) => <Button type="link" size="small" onClick={() => retryTask(record.row[3])}>重试</Button> }
          ]}
        />
      )}

      {activeSubKey === 'task-alert' && (
        <SectionCard title="监控告警" loading={loading} extra={<Button onClick={loadData}>刷新告警</Button>}>
          <div className="alert-list">
            {(taskData.alerts || []).map((item: any[]) => (
              <div key={item[0]} className="alert-item" onClick={() => { setDetailData({ time: item[0], level: item[1], title: item[2], detail: item[3] }); setDetailOpen(true); }}>
                <span>{item[0]}</span>
                <Tag color={item[1] === '严重' ? 'error' : item[1] === '警告' ? 'warning' : 'default'}>{item[1]}</Tag>
                <strong>{item[2]}</strong>
                <p>{item[3]}</p>
              </div>
            ))}
          </div>
        </SectionCard>
      )}

      <Modal title="新建定时任务" open={createOpen} onCancel={() => setCreateOpen(false)} onOk={createSchedule}>
        <Form layout="vertical">
          <Form.Item label="任务名称" required><Select value={scheduleDraft.name} onChange={(value) => setScheduleDraft((prev) => ({ ...prev, name: value }))} options={[{ value: 'PowerMarket_WebDaily', label: 'PowerMarket_WebDaily' }]} /></Form.Item>
          <Form.Item label="执行模式"><Select value={scheduleDraft.mode} onChange={(value) => setScheduleDraft((prev) => ({ ...prev, mode: value }))} options={[{ value: 'refresh_fast_forecast', label: '刷新预测' }, { value: 'model_ops_daily', label: '模型运维' }, { value: 'health_check', label: '健康检查' }]} /></Form.Item>
          <Form.Item label="执行时间"><Select value={scheduleDraft.run_time} onChange={(value) => setScheduleDraft((prev) => ({ ...prev, run_time: value }))} options={[{ value: '06:30', label: '06:30' }, { value: '08:00', label: '08:00' }]} /></Form.Item>
        </Form>
      </Modal>
      <DetailDrawer title="任务详情" open={detailOpen} data={detailData} onClose={() => setDetailOpen(false)} />
      <TaskLogViewer open={logOpen} log={logText} loading={logLoading} onClose={() => setLogOpen(false)} />
    </div>
  );
}
