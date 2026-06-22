import { Alert, Button, Empty, Result, Skeleton, Space, Tag } from 'antd';
import type { ReactNode } from 'react';

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
  const isMock = lower.includes('mock') || lower.includes('fallback');
  const isDerived = lower.includes('derived') || lower.includes('calculated');
  const isFile = lower.includes('file') || lower.includes('import');
  const isReal = lower.includes('postgres') || lower.includes('api') || lower.includes('real');
  const color = isMock ? 'warning' : isDerived ? 'processing' : isFile ? 'blue' : isReal ? 'success' : 'default';
  const label = isMock ? '兜底数据' : isDerived ? '派生数据' : isFile ? '文件数据' : isReal ? '真实数据' : '数据源';
  return <Tag className={`data-source-tag ${isMock ? 'data-source-warning' : ''}`} color={color}>{label}：{value}</Tag>;
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
