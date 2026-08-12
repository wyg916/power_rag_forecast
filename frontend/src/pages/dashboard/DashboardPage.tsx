import { FileTextOutlined, ReloadOutlined, RobotOutlined } from '@ant-design/icons';
import { App, Space, Tag } from 'antd';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '../../api';
import { TaskLogViewer } from '../../components/actions/TaskLogViewer';
import { PageHeader } from '../../components/common/PageHeader';
import { PageDataState } from '../../components/common/States';
import { HomeAuxiliaryGrid } from '../../components/dashboard/HomeAuxiliaryGrid';
import { HomeForecastChart } from '../../components/dashboard/HomeForecastChart';
import { HomeKpiStrip } from '../../components/dashboard/HomeKpiStrip';
import { HomeQuickActions } from '../../components/dashboard/HomeQuickActions';
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
  const { authRequired, hasPermission } = useAuth();
  const canGenerateReport = !authRequired || hasPermission('report:generate');

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
  const riskLevel = data?.isStale
    ? '历史预测窗口'
    : data?.risk?.risk_level === 'high'
      ? '高风险'
      : data?.risk?.risk_level === 'medium'
        ? '需关注'
        : data?.risk?.risk_level === 'low'
          ? '低风险'
          : '暂不可用';
  const riskColor = data?.isStale || data?.risk?.risk_level === 'medium'
    ? 'warning'
    : data?.risk?.risk_level === 'high'
      ? 'error'
      : data?.risk?.risk_level === 'low'
        ? 'success'
        : 'default';

  const kpiItems = data?.kpi?.items || [];
  return (
    <div className="home-dashboard-page">
      <style>{`
        @media (min-width: 1181px) and (max-width: 1600px) {
          .home-dashboard-page {
            overflow-x: hidden;
            overflow-y: auto;
          }

          .home-dashboard-page .home-dashboard-content {
            flex: 0 0 auto;
            min-height: 710px;
            grid-template-rows: 178px minmax(260px, 1fr) minmax(238px, 0.52fr);
          }

          .home-dashboard-page .home-dashboard-content.home-dashboard-stale {
            min-height: 450px;
            grid-template-rows: 178px minmax(260px, 1fr);
          }

          .home-dashboard-page .home-kpi-grid {
            grid-template-columns: repeat(3, minmax(0, 1fr));
          }
        }
      `}</style>
      <PageHeader
        title="总览驾驶舱"
        eyebrow="首页"
        subtitle={data?.isStale
          ? '展示最近可追溯的历史预测与关联业务事实；该窗口已结束，不代表当前市场状态。'
          : '汇总当前可用的供需风险、预测、策略、报告与任务状态，辅助经营决策。'}
        metadata={<Space size={6} wrap><Tag color={riskColor}>{riskLevel}</Tag>{data?.validFrom && data?.validTo ? <Tag>{String(data.validFrom).slice(0, 16)} 至 {String(data.validTo).slice(0, 16)}</Tag> : null}</Space>}
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

      <PageDataState meta={viewMeta} onRetry={loadData} />

      {showContent ? <section className={`home-dashboard-content${data?.isStale ? ' home-dashboard-stale' : ''}`}>
        <HomeKpiStrip items={kpiItems} />
        {data?.isStale ? (
          <>
            <div className="home-dashboard-left">
              <section className="home-card home-chart-card">
                <div className="home-card-head"><div><h2>历史预测窗口摘要</h2><p>该批次适用窗口已结束，以下指标只用于复盘与审计。</p></div><Tag color="warning">不可作为当前市场结论</Tag></div>
                <div className="report-base-info">
                  <p><span>run_id</span><strong>{data.runId || '--'}</strong></p>
                  <p><span>适用开始</span><strong>{String(data.validFrom || '--').slice(0, 19)}</strong></p>
                  <p><span>适用结束</span><strong>{String(data.validTo || '--').slice(0, 19)}</strong></p>
                  <p><span>生成时间</span><strong>{String(data.generatedAt || '--').slice(0, 19)}</strong></p>
                  <p><span>最高预测价</span><strong>{data.forecast?.summary?.max_price ?? '--'} 元/kWh</strong></p>
                  <p><span>预测峰谷价差</span><strong>{data.forecast?.summary?.peak_valley_spread ?? '--'} 元/kWh</strong></p>
                </div>
              </section>
            </div>
            <aside className="home-side-rail">
              <section className="home-card home-side-card"><div className="home-card-head compact"><div><h2>历史策略边界</h2><p>预测计算建议仅供回看</p></div></div><p>候选建议 {data.strategy?.summary?.strategy_count ?? '--'} 条；历史高价风险线索 {data.strategy?.summary?.must_watch_count ?? '--'} 条。</p><p className="home-derived-note">预测价差不等同收益，过期策略不可执行。</p></section>
              <section className="home-card home-side-card"><div className="home-card-head compact"><div><h2>当前任务事实</h2><p>任务状态不由历史预测窗口推断</p></div></div><p>运行 {data.tasks?.health?.running_task_count ?? '--'} · 排队 {data.tasks?.health?.pending_task_count ?? '--'} · 失败 {data.tasks?.health?.failed_task_count ?? '--'} · 超时 {data.tasks?.health?.timeout_task_count ?? '--'}</p></section>
            </aside>
          </>
        ) : (
          <>
            <div className="home-dashboard-left">
              <HomeForecastChart forecast={data?.forecast} risk={data?.risk} />
              <HomeAuxiliaryGrid forecast={data?.forecast} kpi={data?.kpi} />
            </div>
            <HomeSideRail risk={data?.risk} strategy={data?.strategy} tasks={data?.tasks} onOpenTaskLog={openTaskLog} />
          </>
        )}
      </section> : null}

      <TaskLogViewer open={logOpen} log={logText} loading={logLoading} onClose={() => setLogOpen(false)} />
    </div>
  );
}
