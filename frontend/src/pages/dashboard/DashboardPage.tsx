import {
  BarChartOutlined,
  ClockCircleOutlined,
  FileTextOutlined,
  LineChartOutlined,
  RiseOutlined,
  SafetyCertificateOutlined,
  ThunderboltOutlined
} from '@ant-design/icons';
import { Button, List, Space, Table, Tag, message } from 'antd';
import { useEffect, useState } from 'react';
import { api } from '../../api';
import { DetailDrawer } from '../../components/actions/DetailDrawer';
import { TaskLogViewer } from '../../components/actions/TaskLogViewer';
import { RiskAlertCard } from '../../components/cards/RiskAlertCard';
import { SectionCard } from '../../components/cards/SectionCard';
import { PriceCurveChart } from '../../components/charts/PriceCurveChart';
import { EnergyScene } from '../../components/common/EnergyScene';
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
      setLogText(await api.taskLogs(taskId));
    } catch (error) {
      setLogText(error instanceof Error ? error.message : '日志读取失败');
    } finally {
      setLogLoading(false);
    }
  }

  const riskCount = dashboardData.risks?.length || 0;

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
          <TwoColumnLayout className="dashboard-main-layout" left={{ xs: 24, lg: 17 }} right={{ xs: 24, lg: 7 }}>
            <EnergyScene />
            <SectionCard
              title="风险预警"
              loading={loading}
              scrollable
              extra={<a className="card-link" onClick={() => onSubNavigate('dashboard-risk')}>全部({riskCount})</a>}
            >
              {riskCount ? (
                <div className="risk-list">
                  {dashboardData.risks.slice(0, 6).map((item: any, index: number) => (
                    <div onClick={() => openDetail('风险预警详情', item)} key={`${item.title}-${index}`}>
                      <RiskAlertCard level={item.level as UiStatus} title={item.title} description={item.description} time={item.time} />
                    </div>
                  ))}
                </div>
              ) : (
                <EmptyState description="暂无风险预警" />
              )}
              <a className="section-footer-link" onClick={() => onSubNavigate('dashboard-risk')}>查看全部预警 →</a>
            </SectionCard>
          </TwoColumnLayout>

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
