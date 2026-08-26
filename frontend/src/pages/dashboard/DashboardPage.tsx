import { FileTextOutlined, ReloadOutlined, RobotOutlined } from '@ant-design/icons';
import { App } from 'antd';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '../../api';
import { TaskLogViewer } from '../../components/actions/TaskLogViewer';
import { PageHeader } from '../../components/common/PageHeader';
import { PageDataState } from '../../components/common/States';
import { HomeAuxiliaryGrid } from '../../components/dashboard/HomeAuxiliaryGrid';
import { HomeForecastChart } from '../../components/dashboard/HomeForecastChart';
import { HomeKpiStrip } from '../../components/dashboard/HomeKpiStrip';
import { homeQuickActions } from '../../components/dashboard/HomeQuickActions';
import { HomeSideRail } from '../../components/dashboard/HomeSideRail';
import { useAuth } from '../../context/AuthContext';
import { loadHomeDashboard, type HomeDashboardData } from '../../services/homeDashboardApi';
import { resolvePageDataMeta } from '../../services/viewState';
import type { PageProps } from '../../types/ui';

function formatTaskLogs(payload: any) {
  if (typeof payload === 'string') return payload;
  const items = Array.isArray(payload?.items) ? payload.items : [];
  if (!items.length) return payload?.text || '暂无任务日志';
  return items
    .map((item: any) => {
      const level = String(item.level || 'info').toUpperCase();
      const step = item.step || 'summary';
      const time = item.created_at || item.updated_at || '';
      return `[${level}] ${step} ${time} ${item.message || item.log_text || ''}`;
    })
    .join('\n');
}

export function DashboardPage(_: PageProps) {
  const { message } = App.useApp();
  const [data, setData] = useState<HomeDashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [logOpen, setLogOpen] = useState(false);
  const [logLoading, setLogLoading] = useState(false);
  const [logText, setLogText] = useState('');
  const { hasPermission, canPerformAction } = useAuth();
  const canGenerateReport = canPerformAction('report.generate');
  const canUseAssistant = canPerformAction('assistant.use');
  const canReadData = hasPermission('data:read');
  const canReadModel = hasPermission('model:read');
  const canReadTasks = hasPermission('task:read');
  const canDiagnoseTasks = hasPermission('task:diagnostics');

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      setData(await loadHomeDashboard());
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  async function generateReport() {
    try {
      const reportRunId = data?.runId ?? '--';
      const result = await api.generateReport(reportRunId === '--' ? 'latest' : reportRunId);
      message.success(`报告任务已启动：${result.task_id || result.id || 'report_generate'}`);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '生成日报失败');
    }
  }

  async function openTaskLog(taskId?: string) {
    if (!taskId) {
      message.warning('该任务记录缺少 task_id，无法读取日志。');
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

  const viewMeta = useMemo(() => resolvePageDataMeta({
    loading,
    hasData: Boolean(data?.available && data?.kpi?.items?.length),
    empty: Boolean(data && !data?.kpi?.items?.length && !data?.partialErrors?.length),
    error: data?.partialErrors?.[0],
    partialErrors: data?.partialErrors,
    source: data?.data_source,
    generatedAt: data?.generatedAt,
    updatedAt: data?.updatedAt,
    runId: data?.runId,
    modelVersion: data?.modelVersion,
    featureVersion: data?.featureVersion,
    isStale: data?.isStale,
    staleReason: data?.staleReason,
    queryScope: '首页经营总览'
  }), [data, loading]);
  const showContent = viewMeta.state === 'success' || viewMeta.state === 'stale';
  const kpiItems = data?.kpi?.items || [];
  return (
    <div className="home-dashboard-page">
      <style>{`
        @media (max-width: 1180px) {
          .home-dashboard-page .home-kpi-grid {
            grid-template-columns: repeat(3, minmax(0, 1fr));
          }
        }

      `}</style>
      <PageHeader
        title="首页 / 总览驾驶舱"
        subtitle="汇总供需、预测、策略、模型、报告与任务状态，辅助经营决策。"
        className="home-dashboard-header"
        actions={[
          {
            key: 'report',
            label: '生成日报',
            icon: <FileTextOutlined />,
            type: 'primary',
            hidden: !canGenerateReport,
            onClick: generateReport
          },
          {
            key: 'assistant',
            label: 'AI 智能问答',
            icon: <RobotOutlined />,
            hidden: !canUseAssistant,
            onClick: () => { window.location.hash = '/assistant/assistant-chat'; }
          },
          {
            key: 'refresh',
            label: '刷新总览',
            icon: <ReloadOutlined />,
            onClick: loadData
          },
          ...homeQuickActions().map((action) => ({
            ...action,
            hidden: action.key === 'assistant-chat' ? !canUseAssistant
              : action.key === 'report-review' ? !hasPermission('report:review')
                : action.key === 'model-evaluation' ? !canReadModel
                  : action.key === 'task-center' ? !canReadTasks
                    : false
          }))
        ]}
      />

      {!showContent ? <PageDataState meta={viewMeta} onRetry={loadData} /> : null}

      {showContent ? <section className="home-dashboard-content">
        <HomeKpiStrip items={kpiItems} />
        <div className="home-dashboard-left">
          <HomeForecastChart forecast={data?.forecast} risk={data?.risk} />
          <HomeAuxiliaryGrid forecast={data?.forecast} kpi={data?.kpi} canReadData={canReadData} canReadModel={canReadModel} />
        </div>
        <HomeSideRail
          risk={data?.risk}
          strategy={data?.strategy}
          tasks={data?.tasks}
          canUseAssistant={canUseAssistant}
          canReadTasks={canReadTasks}
          canDiagnoseTasks={canDiagnoseTasks}
          onOpenTaskLog={canDiagnoseTasks ? openTaskLog : undefined}
        />
      </section> : null}

      <TaskLogViewer open={logOpen} log={logText} loading={logLoading} onClose={() => setLogOpen(false)} />
    </div>
  );
}
