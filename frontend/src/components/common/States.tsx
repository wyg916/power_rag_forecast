import { Alert, Button, Empty, Result, Skeleton, Space, Tag } from 'antd';
import type { ReactNode } from 'react';
import type { PageDataMeta } from '../../services/viewState';

type SourceType = 'real' | 'historical' | 'simulated' | 'mixed' | 'demo' | 'seed' | 'fallback' | 'derived' | 'ai_inferred' | 'unavailable';
export interface SourceMeta {
  source_type: SourceType;
  data_origin?: string;
  source_name?: string;
  domain: string;
  run_id: string | null;
  generated_at: string | null;
  updated_at?: string | null;
  valid_from?: string | null;
  valid_to?: string | null;
  model_version: string | null;
  feature_version: string | null;
  data_version?: string | null;
  freshness_status?: string;
  is_stale: boolean;
  stale_reason: string | null;
  staleness_reason?: string | null;
  simulation?: boolean;
  degraded?: boolean;
  availability?: string;
  unavailable_reason: string | null;
}

export function LoadingBlock({ rows = 4 }: { rows?: number }) {
  return <Skeleton className="page-state-skeleton" active paragraph={{ rows }} />;
}

export function EmptyState({
  description = '暂无数据',
  title,
  action,
  reason,
  queryScope
}: {
  description?: ReactNode;
  title?: ReactNode;
  action?: ReactNode;
  reason?: ReactNode;
  queryScope?: ReactNode;
}) {
  return (
    <div className="empty-state" role="status" aria-live="polite">
      {title && <div className="empty-state-title">{title}</div>}
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description={(
          <Space direction="vertical" size={4}>
            <span>{description}</span>
            {reason ? <small>原因：{reason}</small> : null}
            {queryScope ? <small>查询范围：{queryScope}</small> : null}
          </Space>
        )}
      >
        {action}
      </Empty>
    </div>
  );
}

export function ErrorState({
  message,
  code,
  onRetry,
  canRetry = true
}: {
  message?: ReactNode;
  code?: ReactNode;
  onRetry?: () => void;
  canRetry?: boolean;
}) {
  if (!message) return null;
  return (
    <Result
      className="error-state"
      status="error"
      title="加载失败"
      subTitle={(
        <Space direction="vertical" size={4}>
          <span>{message}</span>
          {code ? <span>错误码：{code}</span> : null}
        </Space>
      )}
      extra={onRetry && canRetry ? <Button type="primary" onClick={onRetry}>重试</Button> : undefined}
    />
  );
}

export function InlineError({ message }: { message?: ReactNode }) {
  if (!message) return null;
  return <Alert type="error" showIcon message={message} />;
}

export function DataSourceTag({ source }: { source?: unknown }) {
  // 工程来源元数据仍由 API、日志和审计链路保留，但业务界面不展示来源分类。
  void source;
  return null;
}

function freshnessReasonText(value?: string | null) {
  const labels: Record<string, string> = {
    forecast_window_expired: '预测适用窗口已结束',
    historical_run: '当前查看的是历史批次',
    generated_at_older_than_36h: '生成时间已超过 36 小时',
    generated_at_missing: '缺少生成时间',
    runtime_facts_older_than_6h: '运行事实已超过 6 小时',
    refresh_in_progress: '正在刷新',
    data_expired: '数据超过有效时限'
  };
  const text = String(value || '').trim();
  if (!text) return '数据超过有效时限';
  if (text.startsWith('refresh_failed:')) return '刷新失败，保留上一批可追溯结果';
  return labels[text] || '数据超过有效时限';
}

function timeText(value?: string | null) {
  if (!value) return '--';
  return value.replace('T', ' ').replace('Z', '').slice(0, 19);
}

function PageStateMeta({ meta }: { meta: PageDataMeta }) {
  const items = [
    ['业务时间', timeText(meta.updatedAt || meta.generatedAt)]
  ].filter(([, value]) => value && value !== '--');
  if (!items.length) return null;
  return (
    <div className="page-state-meta" aria-label="业务时间与版本">
      {items.map(([label, value]) => (
        <span key={label}>
          <small>{label}</small>
          <b title={String(value)}>{value}</b>
        </span>
      ))}
    </div>
  );
}

export function PageDataState({
  meta,
  onRetry,
  loadingRows = 4,
  mockFallback = false
}: {
  meta: PageDataMeta;
  onRetry?: () => void;
  loadingRows?: number;
  mockFallback?: boolean;
}) {
  if (mockFallback) {
    return <ErrorState code="DATA_CONTRACT_INVALID" message="页面数据未通过可用性校验，请稍后重试。" />;
  }
  if (meta.state === 'loading') {
    return (
      <section className="page-state-panel page-state-loading" aria-live="polite" aria-label="页面加载中">
        <div className="page-state-heading">正在加载当前查询范围</div>
        <LoadingBlock rows={loadingRows} />
      </section>
    );
  }
  if (meta.state === 'empty') {
    return (
      <section className="page-state-panel" aria-live="polite">
        <EmptyState
          title="当前查询暂无有效记录"
          description="接口已成功返回，但没有可展示的业务记录。"
          reason={meta.emptyReason}
          queryScope={meta.queryScope}
          action={onRetry && meta.canRetry ? <Button onClick={onRetry}>刷新查询</Button> : undefined}
        />
      </section>
    );
  }
  if (meta.state === 'unauthorized' || meta.state === 'forbidden') {
    const unauthorized = meta.state === 'unauthorized';
    return (
      <section className="page-state-panel" aria-live="assertive">
        <Result
          status={unauthorized ? 'warning' : 'error'}
          title={unauthorized ? '登录状态无效' : '无权访问'}
          subTitle={unauthorized ? '请重新登录后继续。' : '当前账号未开通此项能力，如有业务需要请联系管理员。'}
        />
      </section>
    );
  }
  if (meta.state === 'error') {
    return (
      <section className="page-state-panel" aria-live="assertive">
        <ErrorState
          message={meta.errorMessage || '请求或响应解析失败。'}
          code={meta.errorCode}
          canRetry={meta.canRetry}
          onRetry={onRetry}
        />
      </section>
    );
  }
  if (meta.state === 'stale') {
    return (
      <section className="page-state-stale-inline" aria-label="数据状态：已过期">
        <Tag color="warning">数据已过期</Tag>
        <span>原因：{freshnessReasonText(meta.staleReason)}</span>
        <PageStateMeta meta={meta} />
        {onRetry && meta.canRetry ? <Button size="small" onClick={onRetry}>重新刷新</Button> : null}
      </section>
    );
  }
  return (
    <section className="page-state-success" aria-label="数据状态：有效">
      <span className="page-state-success-label">数据有效</span>
    </section>
  );
}

export function SourceContextPanel({
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
  if (loading && !meta) {
    return <Alert className="source-context-panel-state" type="info" showIcon message="正在加载业务时间与版本信息" />;
  }
  if (error || !meta || meta.source_type === 'unavailable') {
    return (
      <Alert
        className="source-context-panel-state"
        type="warning"
        showIcon
        message="当前业务信息暂不可用"
        description={`原因：${meta?.unavailable_reason || error || '业务上下文不可用'}；操作建议：刷新后重试或查看已有业务批次。`}
        action={onRefresh ? <Button size="small" onClick={onRefresh}>重新核对</Button> : undefined}
      />
    );
  }
  const warning = ['simulated', 'demo', 'seed', 'fallback'].includes(meta.source_type) || meta.is_stale || meta.source_type === 'historical';
  return (
    <section className={`source-context-panel ${warning ? 'source-context-panel-warning' : ''}`} aria-label="业务时间与版本">
      <div className="source-context-panel-head">
        <div>
          <small>时间与版本</small>
          <strong>当前业务上下文</strong>
        </div>
        <Space size={8} wrap>
          {onRefresh && <Button size="small" loading={loading} onClick={() => onRefresh()}>重新核对</Button>}
        </Space>
      </div>
      <div className="source-context-panel-grid">
        <span><small>业务时间</small><b>{timeText(meta.updated_at || meta.generated_at)}</b></span>
        <span>
          <small>批次状态</small>
          <b>{meta.is_stale ? `已过期：${freshnessReasonText(meta.stale_reason)}` : '可用'}</b>
        </span>
        <span><small>更新时间</small><b>{timeText(lastRefreshedAt)}</b></span>
      </div>
    </section>
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
    return <Alert className="data-state-banner" type="info" showIcon message={`${scope}正在加载业务信息`} />;
  }
  if (error || mockFallback || String(source || '').includes('mock')) {
    return (
      <Alert
        className="data-state-banner"
        type="error"
        showIcon
        message={`${scope}数据加载失败`}
        description={
          <Space direction="vertical" size={4}>
            <span>{fallbackReason || '业务请求暂不可用。'}</span>
            {error ? <span>错误信息：{error}</span> : null}
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
        message={`${scope}暂无可用业务记录`}
        description="当前查询返回为空，页面保留结构并如实展示空状态。"
        action={action}
      />
    );
  }
  return null;
}

export function RiskTag({ value }: { value?: string }) {
  const text = String(value || '--');
  const lower = text.toLowerCase();
  const isHigh = lower.includes('high') || text.includes('高');
  const isMedium = lower.includes('medium') || text.includes('中');
  const color = isHigh ? 'error' : isMedium ? 'warning' : 'success';
  return <Tag color={color}>{text}</Tag>;
}
