import { MessageOutlined } from '@ant-design/icons';
import { Button, Empty, Space, Tag } from 'antd';
import { HomeSourceTag } from './HomeDataState';
import { dateTimeText, formatCompact, formatNumber, statusClass } from './utils';

interface HomeSideRailProps {
  risk?: any;
  strategy?: any;
  tasks?: any;
  onOpenTaskLog: (taskId?: string) => void;
}

function go(hash: string) {
  window.location.hash = hash;
}

function itemText(item: any) {
  return item?.advice_text || item?.description || item?.message || item?.title || '接口未返回建议内容';
}

export function HomeSideRail({ risk, strategy, tasks, onOpenTaskLog }: HomeSideRailProps) {
  const aiItems = [
    ...(strategy?.must_watch || []),
    ...(strategy?.items || []),
    ...(risk?.alerts || [])
  ].slice(0, 3);
  const summary = strategy?.summary || {};
  const taskItems = (tasks?.reminders?.length ? tasks.reminders : tasks?.items || []).slice(0, 5);
  const health = tasks?.health || {};
  const failedCount = Number(health.failed_task_count || 0) + Number(health.timeout_task_count || 0);
  const healthUnavailable = health.available === false || Boolean(health.error);
  const healthErrorText = String(health.error || '暂无真实任务健康统计').slice(0, 90);
  return (
    <aside className="home-side-rail">
      <div className="home-side-top-stack">
      <section className="home-card home-side-card home-ai-card">
        <div className="home-card-head compact">
          <div>
            <h2><MessageOutlined /> AI 建议摘要</h2>
            <p>来自策略与风险接口的可执行建议</p>
          </div>
          <HomeSourceTag source={strategy?.data_source || risk?.data_source} />
        </div>
        <div className="home-ai-list">
          {aiItems.length ? aiItems.map((item: any, index: number) => (
            <button key={`${item.target_hour || item.title || 'advice'}-${item.advice_type || item.level || index}-${index}`} type="button" onClick={() => go('/assistant/assistant-chat')}>
              <span>{index + 1}</span>
              <p>{itemText(item)}</p>
            </button>
          )) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无 AI 策略建议" />}
        </div>
      </section>

      <section className="home-card home-side-card home-strategy-card">
        <div className="home-card-head compact">
          <div>
            <h2>策略执行摘要</h2>
            <p>策略生成、风险窗口与人工复核线索</p>
          </div>
          <Button type="link" onClick={() => go('/strategy/strategy-high')}>更多</Button>
        </div>
        <div className="home-strategy-row">
          <div><span>已生成策略</span><strong>{summary.strategy_count ?? 0}</strong></div>
          <div><span>高价风险段</span><strong>{summary.must_watch_count ?? 0}</strong></div>
          <div><span>低价/储能窗口</span><strong>{summary.storage_count ?? 0}</strong></div>
          <div><span>预计价差</span><strong>{summary.estimated_revenue == null ? '--' : formatNumber(summary.estimated_revenue, 3)}</strong></div>
        </div>
        {summary.estimated_revenue_note ? <p className="home-derived-note">{summary.estimated_revenue_note}</p> : null}
      </section>
      </div>

      <section className="home-card home-side-card home-task-card">
        <div className="home-card-head compact">
          <div>
            <h2>任务提醒</h2>
            <p>失败重试、运行中和待处理任务入口</p>
          </div>
          <Tag color={healthUnavailable ? 'warning' : failedCount ? 'error' : 'success'}>
            {healthUnavailable ? '待接入' : failedCount ? `异常 ${failedCount}` : '健康'}
          </Tag>
        </div>
        <div className="home-task-list">
          {taskItems.length ? taskItems.map((item: any, index: number) => (
            <button key={item.task_id || index} type="button" onClick={() => onOpenTaskLog(item.task_id)}>
              <Tag color={statusClass(item.status) === 'danger' ? 'error' : statusClass(item.status) === 'warning' ? 'warning' : 'success'}>
                {item.status || '--'}
              </Tag>
              <span>{item.task_name || item.kind || item.task_kind || '系统任务'}</span>
              <small>{dateTimeText(item.started_at || item.updated_at || item.created_at)}</small>
            </button>
          )) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无任务提醒" />}
        </div>
        <Space className="home-task-health" wrap>
          <Tag>运行 {formatCompact(health.running_task_count || 0)}</Tag>
          <Tag>排队 {formatCompact(health.pending_task_count || 0)}</Tag>
          <Tag color={failedCount ? 'error' : 'success'}>失败/超时 {failedCount}</Tag>
        </Space>
        {healthUnavailable ? <p className="home-derived-note">任务统计接口异常：{healthErrorText}</p> : null}
      </section>
    </aside>
  );
}
