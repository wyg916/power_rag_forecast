import { Alert, Button, Empty, Result, Skeleton, Space, Tag } from 'antd';
import type { ReactNode } from 'react';

type SourceType = 'real' | 'historical' | 'demo' | 'seed' | 'fallback' | 'derived' | 'unavailable';
interface SourceMeta {
  source_type: SourceType;
  domain: string;
  run_id: string | null;
  generated_at: string | null;
  model_version: string | null;
  feature_version: string | null;
  is_stale: boolean;
  stale_reason: string | null;
  unavailable_reason: string | null;
}

export function LoadingBlock({ rows = 4 }: { rows?: number }) {
  return <Skeleton active paragraph={{ rows }} />;
}

export function EmptyState({
  description = '暂无数据',
  title,
  action
}: {
  description?: ReactNode;
  title?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="empty-state">
      {title && <div className="empty-state-title">{title}</div>}
      <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={description}>
        {action}
      </Empty>
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message?: ReactNode; onRetry?: () => void }) {
  if (!message) return null;
  return (
    <Result
      status="warning"
      title="加载失败"
      subTitle={message}
      extra={onRetry ? <a onClick={onRetry}>重新加载</a> : undefined}
    />
  );
}

export function InlineError({ message }: { message?: ReactNode }) {
  if (!message) return null;
  return <Alert type="error" showIcon message={message} />;
}

export function DataSourceTag({ source }: { source?: string }) {
  const value = source || 'unknown';
  const lower = value.toLowerCase();
  const labels: Record<string, [string, string]> = {
    real: ['真实数据', 'success'],
    historical: ['历史数据', 'blue'],
    demo: ['演示数据', 'warning'],
    seed: ['初始化样例', 'warning'],
    fallback: ['降级数据', 'warning'],
    derived: ['派生数据', 'processing'],
    unavailable: ['不可用', 'default']
  };
  const normalized: SourceType | string =
    Object.keys(labels).find((item) => lower === item || lower.includes(item))
    || (lower.includes('postgres') || lower.includes('registry') ? 'real' : value);
  const [label, color] = labels[normalized] || ['数据源', 'default'];
  const isMock = ['demo', 'seed', 'fallback'].includes(normalized);
  return <Tag className={`data-source-tag ${isMock ? 'data-source-warning' : ''}`} color={color}>{label}：{value}</Tag>;
}

function timeText(value?: string | null) {
  if (!value) return '--';
  return value.replace('T', ' ').replace('Z', '').slice(0, 19);
}

export function FactStatusBar({
  meta,
  loading,
  error,
  lastRefreshedAt,
  onRefresh
}: {
  meta?: SourceMeta | null;
  loading?: boolean;
  error?: string;
  lastRefreshedAt?: string | null;
  onRefresh?: () => void;
}) {
  if (loading) {
    return <Alert className="fact-status-bar" type="info" showIcon message="正在核对事实来源与最新成功批次" />;
  }
  if (error || !meta || meta.source_type === 'unavailable') {
    return (
      <Alert
        className="fact-status-bar"
        type="warning"
        showIcon
        message="当前无可用真实预测"
        description={`原因：${meta?.unavailable_reason || error || '来源元数据不可用'}；操作建议：执行预测任务或查看明确标识的历史批次。`}
        action={onRefresh ? <Button size="small" onClick={onRefresh}>重新核对</Button> : undefined}
      />
    );
  }
  const warning = ['demo', 'seed', 'fallback'].includes(meta.source_type) || meta.is_stale || meta.source_type === 'historical';
  return (
    <div className={`fact-status-bar fact-status-grid ${warning ? 'fact-status-warning' : ''}`}>
      <strong>事实状态</strong>
      <span><small>数据来源</small><DataSourceTag source={meta.source_type} /></span>
      <span><small>运行批次</small><b>{meta.run_id || '--'}</b></span>
      <span><small>生成时间</small><b>{timeText(meta.generated_at)}</b></span>
      <span><small>模型版本</small><b>{meta.model_version || '--'}</b></span>
      <span><small>特征版本</small><b>{meta.feature_version || '--'}</b></span>
      <span>
        <small>事实状态</small>
        <b>{meta.source_type === 'historical' ? '历史批次' : meta.is_stale ? `已过期：${meta.stale_reason || 'unknown'}` : '最新成功批次'}</b>
      </span>
      <span><small>最后刷新</small><b>{timeText(lastRefreshedAt)}</b></span>
      {onRefresh && <Button size="small" onClick={onRefresh}>刷新状态</Button>}
    </div>
  );
}

export function DataStateBanner({
  loading,
  source,
  error,
  empty,
  mockFallback,
  fallbackReason,
  partialErrors,
  onRetry,
  scope = '当前页面'
}: {
  loading?: boolean;
  source?: string;
  error?: ReactNode;
  empty?: boolean;
  mockFallback?: boolean;
  fallbackReason?: ReactNode;
  partialErrors?: ReactNode[];
  onRetry?: () => void;
  scope?: string;
}) {
  const action = onRetry ? <Button size="small" onClick={onRetry}>重试</Button> : undefined;
  if (loading) {
    return <Alert className="data-state-banner" type="info" showIcon message={`${scope}正在读取真实接口数据`} />;
  }
  if (error || mockFallback || String(source || '').includes('mock')) {
    return (
      <Alert
        className="data-state-banner"
        type="warning"
        showIcon
        message={`${scope}已启用兜底数据`}
        description={
          <Space direction="vertical" size={4}>
            <span>{fallbackReason || '真实接口暂不可用，页面正在使用本地 mock 兜底数据。'}</span>
            {error ? <span>接口错误：{error}</span> : null}
            {source ? <span>当前数据源：<DataSourceTag source={source} /></span> : null}
          </Space>
        }
        action={action}
      />
    );
  }
  if (partialErrors?.length) {
    return (
      <Alert
        className="data-state-banner"
        type="warning"
        showIcon
        message={`${scope}存在部分接口异常`}
        description={partialErrors.map((item, index) => <div key={index}>{item}</div>)}
        action={action}
      />
    );
  }
  if (empty) {
    return (
      <Alert
        className="data-state-banner"
        type="info"
        showIcon
        message={`${scope}暂无真实数据`}
        description={source ? <span>当前数据源：<DataSourceTag source={source} /></span> : '接口返回为空，页面保留结构但不隐藏空状态。'}
        action={action}
      />
    );
  }
  if (!source) return null;
  return (
    <div className="data-state-inline">
      <span>数据源</span>
      <DataSourceTag source={source} />
    </div>
  );
}

export function RiskTag({ value }: { value?: string }) {
  const text = String(value || '--');
  const lower = text.toLowerCase();
  const isHigh = lower.includes('high') || text.includes('高');
  const isMedium = lower.includes('medium') || text.includes('中');
  const color = isHigh ? 'error' : isMedium ? 'warning' : 'success';
  return <Tag color={color}>{text}</Tag>;
}
