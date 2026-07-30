import { FileTextOutlined, ReloadOutlined, RobotOutlined } from '@ant-design/icons';
import { message, Tag } from 'antd';
import { useCallback, useEffect, useState } from 'react';
import { api } from '../../api';
import { TaskLogViewer } from '../../components/actions/TaskLogViewer';
import { PageHeader } from '../../components/common/PageHeader';
import { HomeAuxiliaryGrid } from '../../components/dashboard/HomeAuxiliaryGrid';
import { HomeForecastChart } from '../../components/dashboard/HomeForecastChart';
import { HomeKpiStrip } from '../../components/dashboard/HomeKpiStrip';
import { HomeQuickActions } from '../../components/dashboard/HomeQuickActions';
import { HomeSideRail } from '../../components/dashboard/HomeSideRail';
import { useAuth } from '../../context/AuthContext';
import { loadHomeDashboard, type HomeDashboardData } from '../../services/homeDashboardApi';
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
  const [data, setData] = useState<HomeDashboardData | null>(null);
  const [logOpen, setLogOpen] = useState(false);
  const [logLoading, setLogLoading] = useState(false);
  const [logText, setLogText] = useState('');
  const { authRequired, hasPermission } = useAuth();
  const canGenerateReport = !authRequired || hasPermission('report:generate');

  const loadData = useCallback(async () => {
    setData(await loadHomeDashboard());
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  async function generateReport() {
    try {
      const result = await api.generateReport();
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

  const riskLevel = data?.risk?.risk_level === 'high' ? '高风险' : data?.risk?.risk_level === 'medium' ? '需关注' : '运行正常';

  const kpiItems = data?.kpi?.items || [];
  return (
    <div className="home-dashboard-page">
      <PageHeader
        title="总览驾驶舱"
        eyebrow="首页"
        subtitle="汇总今日供需风险、预测、策略、报告与任务状态，辅助经营决策。"
        metadata={<Tag color={data?.risk?.risk_level === 'high' ? 'error' : data?.risk?.risk_level === 'medium' ? 'warning' : 'success'}>{riskLevel}</Tag>}
        filters={<HomeQuickActions />}
        actions={[
          {
            key: 'report',
            label: '生成日报',
            icon: <FileTextOutlined />,
            type: 'primary',
            disabled: !canGenerateReport,
            disabledReason: '需要 report:generate 权限',
            onClick: generateReport
          },
          {
            key: 'assistant',
            label: 'AI 智能问答',
            icon: <RobotOutlined />,
            onClick: () => { window.location.hash = '/assistant/assistant-chat'; }
          },
          {
            key: 'refresh',
            label: '刷新总览',
            icon: <ReloadOutlined />,
            collapseAtNarrow: true,
            onClick: loadData
          }
        ]}
      />

      <section className="home-dashboard-content">
        <HomeKpiStrip items={kpiItems} />
        <div className="home-dashboard-left">
          <HomeForecastChart forecast={data?.forecast} risk={data?.risk} />
          <HomeAuxiliaryGrid forecast={data?.forecast} kpi={data?.kpi} />
        </div>
        <HomeSideRail
          risk={data?.risk}
          strategy={data?.strategy}
          tasks={data?.tasks}
          onOpenTaskLog={openTaskLog}
        />
      </section>

      <TaskLogViewer open={logOpen} log={logText} loading={logLoading} onClose={() => setLogOpen(false)} />
    </div>
  );
}
