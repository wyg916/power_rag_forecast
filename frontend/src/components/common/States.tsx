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
    <div className="empty-state">
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
  const sourceObject = source && typeof source === 'object' ? source as Record<string, unknown> : null;
  const value = String(sourceObject?.source_type || sourceObject?.data_origin || sourceObject?.source_name || source || 'unknown');
  const lower = value.toLowerCase();
  const labels: Record<string, [string, string]> = {
    real: ['业务事实', 'success'],
    historical: ['历史业务记录', 'blue'],
    simulated: ['规则测算', 'processing'],
    mixed: ['业务汇总', 'warning'],
    demo: ['开发样例（受限）', 'warning'],
    seed: ['初始化样例（受限）', 'warning'],
    fallback: ['服务降级', 'warning'],
    derived: ['业务派生结果', 'processing'],
    ai_inferred: ['AI 推断结果', 'processing'],
    unavailable: ['暂不可用', 'default']
  };
  const normalized: SourceType | string =
    Object.keys(labels).find((item) => lower === item || lower.includes(item))
    || (lower.includes('postgres') || lower.includes('registry') ? 'real' : value);
  const [label, color] = labels[normalized] || ['业务事实', 'default'];
  const isMock = ['demo', 'seed', 'fallback'].includes(normalized);
  return <Tag className={`data-source-tag ${isMock ? 'data-source-warning' : ''}`} color={color}>{label}</Tag>;
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
    ['来源', meta.source],
    ['生成时间', timeText(meta.generatedAt)],
    ['更新时间', timeText(meta.updatedAt)],
    ['run_id', meta.runId],
    ['模型版本', meta.modelVersion],
    ['特征版本', meta.featureVersion]
  ].filter(([, value]) => value && value !== '--');
  if (!items.length) return null;
  return (
    <div className="page-state-meta" aria-label="数据来源与版本">
      {items.map(([label, value]) => (
        <span key={label}>
          <small>{label}</small>
          <b title={label === '来源' ? undefined : String(value)}>{label === '来源' ? <DataSourceTag source={value} /> : value}</b>
        </span>
      ))}
    </div>
  );
}

export function PageDataState({
  meta,
  onRetry,
  loadingRows = 4
}: {
  meta: PageDataMeta;
  onRetry?: () => void;
  loadingRows?: number;
}) {
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
          subTitle={(
            <Space direction="vertical" size={4}>
              <span>{meta.errorMessage || (unauthorized ? '请重新登录后继续。' : '请联系管理员申请相应权限。')}</span>
              <span>错误码：{meta.errorCode || (unauthorized ? 'HTTP_401' : 'HTTP_403')}</span>
            </Space>
          )}
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
      <PageStateMeta meta={meta} />
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
    return <Alert className="source-context-panel-state" type="info" showIcon message="正在核对业务事实与最近成功批次" />;
  }
  if (error || !meta || meta.source_type === 'unavailable') {
    return (
      <Alert
        className="source-context-panel-state"
        type="warning"
        showIcon
        message="当前无可用预测事实"
        description={`原因：${meta?.unavailable_reason || error || '来源元数据不可用'}；操作建议：执行预测任务或查看明确标识的历史批次。`}
        action={onRefresh ? <Button size="small" onClick={onRefresh}>重新核对</Button> : undefined}
      />
    );
  }
  const warning = ['simulated', 'demo', 'seed', 'fallback'].includes(meta.source_type) || meta.is_stale || meta.source_type === 'historical';
  return (
    <section className={`source-context-panel ${warning ? 'source-context-panel-warning' : ''}`} aria-label="最近成功事实来源">
      <div className="source-context-panel-head">
        <div>
          <small>来源与时效</small>
          <strong>最近成功事实来源</strong>
        </div>
        <Space size={8} wrap>
          <span className="source-context-panel-source"><small>数据来源</small><DataSourceTag source={meta.source_type} /></span>
          {onRefresh && <Button size="small" loading={loading} onClick={() => onRefresh()}>重新核对</Button>}
        </Space>
      </div>
      <div className="source-context-panel-grid">
        <span><small>运行批次</small><b title={meta.run_id || '--'}>{meta.run_id || '--'}</b></span>
        <span><small>生成时间</small><b>{timeText(meta.generated_at)}</b></span>
        <span><small>模型版本</small><b title={meta.model_version || '--'}>{meta.model_version || '--'}</b></span>
        <span><small>特征版本</small><b title={meta.feature_version || '--'}>{meta.feature_version || '--'}</b></span>
        <span>
          <small>事实状态</small>
          <b>{meta.source_type === 'historical' ? '历史批次' : meta.is_stale ? `已过期：${freshnessReasonText(meta.stale_reason)}` : '最近成功批次'}</b>
        </span>
        <span><small>最后刷新</small><b>{timeText(lastRefreshedAt)}</b></span>
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
    return <Alert className="data-state-banner" type="info" showIcon message={`${scope}正在读取真实接口数据`} />;
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
            <span>{fallbackReason || (mockFallback ? '检测到前端静态兜底数据，已阻止其作为成功结果展示。' : '真实接口暂不可用。')}</span>
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
        message={`${scope}暂无可用业务记录`}
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
