import {
  BarChartOutlined,
  ClockCircleOutlined,
  DatabaseOutlined,
  FileTextOutlined,
  LineChartOutlined,
  RiseOutlined,
  RobotOutlined,
  SafetyCertificateOutlined,
  ThunderboltOutlined
} from '@ant-design/icons';
import { Alert, Button, List, Space, Table, Tag, message } from 'antd';
import { useEffect, useState } from 'react';
import { api } from '../../api';
import { DetailDrawer } from '../../components/actions/DetailDrawer';
import { TaskLogViewer } from '../../components/actions/TaskLogViewer';
import { RiskAlertCard } from '../../components/cards/RiskAlertCard';
import { SectionCard } from '../../components/cards/SectionCard';
import { PriceCurveChart } from '../../components/charts/PriceCurveChart';
import { PageTabs } from '../../components/common/PageTabs';
import { DataSourceTag, DataStateBanner, EmptyState } from '../../components/common/States';
import { MetricGrid, ResponsiveGrid, TwoColumnLayout } from '../../components/layout/UnifiedPage';
import { dashboardMock } from '../../mock/dashboardMock';
import { getDashboardData } from '../../services/dashboardApi';
import type { PageProps, UiStatus } from '../../types/ui';

const metricIcons = [
  <RiseOutlined />,
  <ThunderboltOutlined />,
  <LineChartOutlined />,
  <BarChartOutlined />,
  <ClockCircleOutlined />,
  <SafetyCertificateOutlined />
];

const tabs = [
  { key: 'dashboard-overview', label: '驾驶舱' },
  { key: 'dashboard-risk', label: '风险提醒' },
  { key: 'dashboard-shortcut', label: '快捷入口' }
];

function operationColor(status?: string) {
  if (status === 'success') return 'success';
  if (status === 'danger') return 'error';
  if (status === 'warning') return 'warning';
  return 'processing';
}

function formatTaskLogs(payload: any) {
  if (typeof payload === 'string') return payload;
  const items = Array.isArray(payload?.items) ? payload.items : [];
  if (!items.length) return payload?.text || '暂无日志';
  return items
    .map((item: any) => {
      const level = String(item.level || 'info').toUpperCase();
      const step = item.step || 'summary';
      const time = item.created_at || '';
      return `[${level}] ${step} ${time} ${item.message || item.log_text || ''}`;
    })
    .join('\n');
}

function parseAmount(value: unknown) {
  const num = Number(String(value ?? '0').replace(/,/g, ''));
  return Number.isFinite(num) ? num : 0;
}

function formatMoney(value: number) {
  return `¥ ${value.toLocaleString('zh-CN', { maximumFractionDigits: 0 })}`;
}

function metricValue(metrics: any[] = [], index: number, fallback = '--') {
  const item = metrics[index];
  if (!item) return fallback;
  return item.unit ? `${item.value}${item.unit}` : String(item.value ?? fallback);
}

export function DashboardPage({ activeSubKey, onSubNavigate }: PageProps) {
  const [dashboardData, setDashboardData] = useState<any>(dashboardMock);
  const [loading, setLoading] = useState(true);
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailTitle, setDetailTitle] = useState('详情');
  const [detailData, setDetailData] = useState<Record<string, unknown> | null>(null);
  const [logOpen, setLogOpen] = useState(false);
  const [logLoading, setLogLoading] = useState(false);
  const [logText, setLogText] = useState('');

  async function loadData() {
    setLoading(true);
    try {
      setDashboardData(await getDashboardData());
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData();
  }, []);

  function openDetail(title: string, data: Record<string, unknown>) {
    setDetailTitle(title);
    setDetailData(data);
    setDetailOpen(true);
  }

  async function openTaskLog(taskId?: string) {
    if (!taskId) {
      openDetail('任务详情', { message: '该任务来自历史兼容数据，暂无 task_id。' });
      return;
    }
    setLogOpen(true);
    setLogLoading(true);
    try {
      setLogText(formatTaskLogs(await api.taskLogs(taskId)));
    } catch (error) {
      setLogText(error instanceof Error ? error.message : '日志读取失败');
    } finally {
      setLogLoading(false);
    }
  }

  const riskCount = dashboardData.risks?.length || 0;
  const operationCards = dashboardData.operationalCards || [];
  const alertSummary = dashboardData.alertSummary || [];
  const taskHealth = dashboardData.taskHealth || {};
  const taskProblemCount = Number(taskHealth.failed_task_count || 0) + Number(taskHealth.timeout_task_count || 0);
  const strategyRevenue = (dashboardData.storagePlan || []).reduce((sum: number, row: any) => sum + parseAmount(row.revenue), 0);
  const dataHealth = operationCards.find((item: any) => String(item.title || '').includes('数据新鲜度'));
  const forecastTrust = dashboardData.modelBacktest?.reference_baseline?.overall?.mae !== undefined
    ? `MAE ${Number(dashboardData.modelBacktest.reference_baseline.overall.mae).toFixed(4)}`
    : metricValue(dashboardData.metrics, 5);
  const reportPending = Array.isArray(dashboardData.reports) ? dashboardData.reports.length : 0;
  const aiAdvice = [
    alertSummary[0] || `高风险窗口 ${metricValue(dashboardData.metrics, 4)}，建议提前复核敞口。`,
    `低价窗口 ${metricValue(dashboardData.metrics, 5)}，可联动低价采购或储能充电策略。`,
    taskProblemCount ? `任务中心存在 ${taskProblemCount} 个失败/超时项，建议先处理再生成日报。` : '任务运行状态未发现阻塞项，可继续推进日报和策略复核。'
  ];
  const executiveSignals = [
    {
      title: '供需风险',
      value: riskCount ? `${riskCount} 项` : '低风险',
      desc: dashboardData.risks?.[0]?.description || '当前未发现高优先级供需风险。',
      status: riskCount ? 'danger' : 'success',
      icon: <SafetyCertificateOutlined />
    },
    {
      title: '预测可信度',
      value: forecastTrust,
      desc: dashboardData.modelBacktest?.available ? '来自 P2 回测基线与最新预测批次。' : '当前以预测曲线派生可信度摘要。',
      status: dashboardData.modelBacktest?.available ? 'success' : 'info',
      icon: <LineChartOutlined />
    },
    {
      title: '策略收益',
      value: formatMoney(strategyRevenue),
      desc: '按储能充放电建议收益合计派生，待执行回填接入。',
      status: 'success',
      icon: <ThunderboltOutlined />
    },
    {
      title: '报告待审',
      value: `${reportPending} 份`,
      desc: '当前报告数据未含真实审核状态，按最新报告列表待接入展示。',
      status: 'warning',
      icon: <FileTextOutlined />
    },
    {
      title: '任务提醒',
      value: taskProblemCount ? `${taskProblemCount} 项` : '无阻塞',
      desc: `运行 ${taskHealth.running_task_count ?? 0}，排队 ${taskHealth.pending_task_count ?? 0}。`,
      status: taskProblemCount ? 'danger' : 'success',
      icon: <ClockCircleOutlined />
    },
    {
      title: '数据健康',
      value: dataHealth?.value || '--',
      desc: dataHealth?.description || '数据健康摘要来自 freshness / db health 聚合。',
      status: dataHealth?.status || 'info',
      icon: <DatabaseOutlined />
    }
  ];

  return (
    <div className="dashboard-grid">
      <PageTabs items={tabs} activeKey={activeSubKey} onChange={onSubNavigate} />
      <DataStateBanner
        scope="首页"
        loading={loading}
        source={dashboardData.dataSource}
        error={dashboardData.error}
        empty={dashboardData.empty}
        mockFallback={dashboardData.mockFallback}
        fallbackReason={dashboardData.fallbackReason}
        partialErrors={dashboardData.partialErrors}
        onRetry={loadData}
      />

      <MetricGrid items={dashboardData.metrics || []} icons={metricIcons} loading={loading} minColumnWidth={164} />

      {activeSubKey === 'dashboard-risk' ? (
        <SectionCard title="完整风险预警列表" extra={<Space><DataSourceTag source={dashboardData.dataSource} /><Button onClick={loadData}>刷新</Button></Space>} loading={loading}>
          <div className="risk-list">
            {(dashboardData.risks || []).map((item: any, index: number) => (
              <div onClick={() => openDetail('风险预警详情', item)} key={`${item.title}-${index}`}>
                <RiskAlertCard level={item.level as UiStatus} title={item.title} description={item.description} time={item.time} />
              </div>
            ))}
          </div>
        </SectionCard>
      ) : activeSubKey === 'dashboard-shortcut' ? (
        <SectionCard title="快捷操作" extra={<Button onClick={loadData}>刷新数据</Button>}>
          <Space wrap>
            <Button type="primary" onClick={() => { window.location.hash = '/forecast/forecast-24h'; }}>查看预测</Button>
            <Button onClick={() => { window.location.hash = '/strategy/strategy-high'; }}>策略中心</Button>
            <Button onClick={() => { window.location.hash = '/data/data-tables'; }}>数据库表</Button>
            <Button onClick={() => api.runTask('today_analysis').then((res) => message.success(`任务已启动：${res.task_id || res.id || 'today_analysis'}`))}>启动今日分析</Button>
            <Button onClick={() => api.generateReport().then((res) => message.success(`报告任务已启动：${res.task_id || 'report_only'}`))}>生成报告</Button>
          </Space>
        </SectionCard>
      ) : (
        <>
          <div className="dashboard-action-row">
            <Space wrap>
              <Button type="primary" icon={<FileTextOutlined />} onClick={() => api.generateReport().then((res) => message.success(`报告任务已启动：${res.task_id || 'report_only'}`))}>生成日报</Button>
              <Button icon={<RobotOutlined />} onClick={() => { window.location.hash = '/assistant/assistant-chat'; }}>AI 智能问答</Button>
              <Button icon={<LineChartOutlined />} onClick={() => { window.location.hash = '/forecast/forecast-24h'; }}>查看 24h 预测</Button>
              <Button onClick={loadData}>刷新总览</Button>
            </Space>
            <DataSourceTag source={dashboardData.mockFallback ? 'mock_fallback' : dashboardData.dataSource || 'derived_dashboard'} />
          </div>
          <div className="executive-signal-grid">
            {executiveSignals.map((item) => (
              <button
                type="button"
                className={`executive-signal executive-signal-${item.status}`}
                key={item.title}
                onClick={() => openDetail(item.title, { ...item, data_source: dashboardData.dataSource || 'derived_dashboard' })}
              >
                <span className="executive-signal-icon">{item.icon}</span>
                <span className="executive-signal-main">
                  <small>{item.title}</small>
                  <strong>{item.value}</strong>
                  <em>{item.desc}</em>
                </span>
              </button>
            ))}
          </div>
          <Alert
            showIcon
            type={alertSummary.length ? 'warning' : 'success'}
            message={alertSummary.length ? `当前有 ${alertSummary.length} 条运营关注项` : '当前核心运行态未发现阻塞项'}
            description={alertSummary.length ? alertSummary.map((item: string) => <div key={item}>{item}</div>) : '数据新鲜度、任务中心、RAG 和 P2 回测摘要已纳入首页巡检。'}
          />
          <div className="dashboard-first-screen">
            <SectionCard
              className="dashboard-chart-card"
              title="今日供需风险总览（24小时）"
              loading={loading}
              extra={<Space><span className="card-unit">预测电价 / 置信区间</span><DataSourceTag source={dashboardData.dataSource || 'derived_dashboard'} /></Space>}
            >
              <div className="window-summary-row">
                <Tag color="red">高风险：{metricValue(dashboardData.metrics, 4)}</Tag>
                <Tag color="success">低价窗口：{metricValue(dashboardData.metrics, 5)}</Tag>
                <Tag color="blue">均价：{metricValue(dashboardData.metrics, 2)}</Tag>
              </div>
              <PriceCurveChart data={dashboardData.priceCurve || []} height={360} showActual={false} />
            </SectionCard>
            <div className="dashboard-right-stack">
              <SectionCard title="AI 建议摘要" compact extra={<DataSourceTag source="derived_dashboard" />} loading={loading}>
                <div className="ai-advice-list">
                  {aiAdvice.map((item, index) => (
                    <div className="ai-advice-item" key={item}>
                      <span>{index + 1}</span>
                      <p>{item}</p>
                    </div>
                  ))}
                </div>
              </SectionCard>
              <SectionCard title="策略执行摘要" compact extra={<a className="card-link" onClick={() => { window.location.hash = '/strategy/strategy-high'; }}>更多</a>} loading={loading}>
                <div className="summary-metric-row">
                  <div><small>预计收益</small><strong>{formatMoney(strategyRevenue)}</strong></div>
                  <div><small>高风险</small><strong>{riskCount}</strong></div>
                  <div><small>人工复核</small><strong>{Math.max(1, Math.min(riskCount, 3))}</strong></div>
                </div>
              </SectionCard>
              <SectionCard title="任务提醒" compact extra={<a className="card-link" onClick={() => { window.location.hash = '/task/task-schedule'; }}>任务中心</a>} loading={loading}>
                <div className="task-reminder-list">
                  {(dashboardData.rawTasks || dashboardData.taskLogs || []).slice(0, 4).map((item: any, index: number) => {
                    const row = Array.isArray(item) ? { name: item[0], status: item[1], time: item[2], task_id: item[3] } : item;
                    return (
                      <button key={`${row.task_id || row.name || index}`} type="button" onClick={() => openTaskLog(row.task_id)}>
                        <Tag color={operationColor(row.status === 'failed' ? 'danger' : row.status === 'success' ? 'success' : 'info')}>{row.status || '--'}</Tag>
                        <span>{row.task_name || row.kind || row.name || '系统任务'}</span>
                        <small>{String(row.updated_at || row.started_at || row.time || '--').slice(0, 16)}</small>
                      </button>
                    );
                  })}
                </div>
              </SectionCard>
            </div>
          </div>

          <ResponsiveGrid minColumnWidth={300} className="dashboard-bottom-grid">
            <SectionCard title="24小时电价趋势" extra={<Tag>最新预测</Tag>} loading={loading}>
              <PriceCurveChart data={dashboardData.priceCurve || []} height={270} showActual={false} />
            </SectionCard>
            <SectionCard title="储能充放电建议" extra={<Tag color="success">策略</Tag>} loading={loading}>
              <Table
                size="small"
                pagination={false}
                scroll={{ x: 'max-content' }}
                dataSource={dashboardData.storagePlan || []}
                columns={[
                  { title: '时段', dataIndex: 'period' },
                  { title: '策略', dataIndex: 'action', render: (text) => <Tag color={text === '放电' ? 'blue' : text === '充电' ? 'success' : 'default'}>{text}</Tag> },
                  { title: '功率', dataIndex: 'power', align: 'right' },
                  { title: '收益', dataIndex: 'revenue', align: 'right' },
                  { title: '操作', render: (_, record) => <Button type="link" size="small" onClick={() => openDetail('储能策略详情', record as unknown as Record<string, unknown>)}>详情</Button> }
                ]}
              />
            </SectionCard>
            <SectionCard title="最新报告" extra={<a className="card-link" onClick={() => { window.location.hash = '/report/report-daily'; }}>全部报告</a>} loading={loading}>
              <List
                className="compact-list"
                dataSource={dashboardData.reports || []}
                renderItem={(item: any[]) => (
                  <List.Item onClick={() => openDetail('报告详情', { title: item[0], generated_at: item[1] })}>
                    <Space>
                      <FileTextOutlined className="list-icon" />
                      <div><strong>{item[0]}</strong><p>{item[1]}</p></div>
                    </Space>
                  </List.Item>
                )}
              />
            </SectionCard>
            <SectionCard title="任务日志" extra={<a className="card-link" onClick={() => { window.location.hash = '/task/task-log'; }}>全部任务</a>} loading={loading}>
              <List
                className="compact-list"
                dataSource={dashboardData.taskLogs || []}
                renderItem={(item: any[]) => (
                  <List.Item onClick={() => openTaskLog(item[3])}>
                    <Space className="task-log-row">
                      <Tag color={item[1] === 'success' || item[1] === '完成' ? 'success' : item[1] === 'running' || item[1] === '运行中' ? 'processing' : 'default'}>{item[1]}</Tag>
                      <strong>{item[0]}</strong>
                      <span>{item[2]}</span>
                    </Space>
                  </List.Item>
                )}
              />
            </SectionCard>
          </ResponsiveGrid>
        </>
      )}

      <DetailDrawer title={detailTitle} open={detailOpen} data={detailData} onClose={() => setDetailOpen(false)} />
      <TaskLogViewer open={logOpen} log={logText} loading={logLoading} onClose={() => setLogOpen(false)} />
    </div>
  );
}
