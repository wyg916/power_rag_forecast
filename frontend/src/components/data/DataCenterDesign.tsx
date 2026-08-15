import {
  ApiOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  CloudDownloadOutlined,
  DatabaseOutlined,
  DownloadOutlined,
  EyeOutlined,
  ExclamationCircleOutlined,
  FileSearchOutlined,
  FilterOutlined,
  SafetyCertificateOutlined,
  SettingOutlined,
  SyncOutlined,
  UserSwitchOutlined,
  WarningOutlined
} from '@ant-design/icons';
import { Button, Empty, Input, Modal, Pagination, Progress, Select, Table, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import * as React from 'react';
import { MetricCard } from '../cards/MetricCard';
import { SectionCard } from '../cards/SectionCard';
import { TableCard } from '../cards/TableCard';
import { chartColors } from '../charts/chartTheme';
import { FilterBar } from '../common/FilterBar';
import { EmptyState, InlineError, LoadingBlock } from '../common/States';

const metricIcons = [
  <DatabaseOutlined />,
  <SyncOutlined />,
  <WarningOutlined />,
  <SafetyCertificateOutlined />,
  <CloudDownloadOutlined />,
  <ClockCircleOutlined />
];

function compact(value: unknown) {
  if (value === null || value === undefined || value === '') return '--';
  const number = Number(value);
  if (!Number.isFinite(number)) return '--';
  return number >= 100000000 ? `${(number / 100000000).toFixed(2)}亿`
    : number >= 10000 ? `${(number / 10000).toFixed(2)}万`
      : number.toLocaleString();
}

const hiddenAuditFieldIds = new Set([
  'run_id', 'model_version', 'feature_version', 'generated_at', 'updated_at',
  'source_type', 'data_source', 'is_simulated', 'prediction_date', 'region',
  'inference_model', 'applicable_window', 'batch_status'
]);

function visibleBusinessField(field: any) {
  return !hiddenAuditFieldIds.has(String(field?.field_id || '').toLowerCase());
}

function businessTime(value: unknown) {
  if (!value) return '--';
  return String(value).replace('T', ' ').slice(0, 16);
}

function statusColor(value: unknown) {
  const text = String(value || '').toLowerCase();
  if (text.includes('fail') || text.includes('error') || text.includes('异常') || text.includes('缺失')) return 'error';
  if (text.includes('running') || text.includes('进行')) return 'processing';
  if (text.includes('warning') || text.includes('stale') || text.includes('empty') || text.includes('检查') || text.includes('延迟')) return 'warning';
  return 'success';
}

function statusText(value: unknown) {
  const text = String(value || '');
  const lower = text.toLowerCase();
  if (lower === 'available') return '已接入';
  if (lower === 'unavailable') return '暂不可用';
  if (lower === 'table') return '业务表';
  if (lower === 'view') return '业务视图';
  if (lower === 'success') return '成功';
  if (lower === 'pending') return '排队中';
  if (lower === 'queued') return '排队中';
  if (lower === 'cancelled' || lower === 'canceled') return '已取消';
  if (lower === 'missing_table') return '缺表';
  if (lower === 'stale') return '时效异常';
  if (lower === 'empty') return '空表';
  if (lower === 'warning') return '需关注';
  if (lower === 'ok') return '正常';
  if (lower === 'running') return '进行中';
  if (lower === 'failed') return '失败';
  return text || '需关注';
}

export function DataContextBar({
  qualityMode,
  search,
  onSearch,
  domains = [],
  domain = 'all',
  onDomainChange,
  objectTypes = [],
  objectType = 'all',
  onObjectTypeChange,
  statuses = [],
  status = 'all',
  onStatusChange,
  taskTypes = [],
  taskType = 'all',
  onTaskTypeChange,
  onReset
}: {
  qualityMode?: boolean;
  search: string;
  onSearch: (value: string) => void;
  domains?: string[];
  domain?: string;
  onDomainChange?: (value: string) => void;
  objectTypes?: string[];
  objectType?: string;
  onObjectTypeChange?: (value: string) => void;
  statuses?: string[];
  status?: string;
  onStatusChange?: (value: string) => void;
  taskTypes?: string[];
  taskType?: string;
  onTaskTypeChange?: (value: string) => void;
  onReset?: () => void;
}) {
  const selectOptions = (values: string[]) => [
    { value: 'all', label: '全部' },
    ...values.map((value) => ({ value, label: statusText(value) }))
  ];
  return (
    <FilterBar className="data-design-filter" label={null} compact onReset={onReset} resetText="重置筛选">
      {qualityMode ? (
        <>
          <label className="data-filter-field">
            <span>数据域</span>
            <Select
              aria-label="数据域"
              value={domain}
              options={selectOptions(domains)}
              onChange={onDomainChange}
            />
          </label>
          <label className="data-filter-field">
            <span>对象类型</span>
            <Select
              aria-label="对象类型"
              value={objectType}
              options={selectOptions(objectTypes)}
              onChange={onObjectTypeChange}
            />
          </label>
          <label className="data-filter-field">
            <span>接入状态</span>
            <Select
              aria-label="接入状态"
              value={status}
              options={selectOptions(statuses)}
              onChange={onStatusChange}
            />
          </label>
        </>
      ) : (
        <>
          <label className="data-filter-field">
            <span>任务类型</span>
            <Select
              aria-label="任务类型"
              value={taskType}
              options={selectOptions(taskTypes)}
              onChange={onTaskTypeChange}
            />
          </label>
          <label className="data-filter-field">
            <span>同步状态</span>
            <Select
              aria-label="同步状态"
              value={status}
              options={selectOptions(statuses)}
              onChange={onStatusChange}
            />
          </label>
        </>
      )}
      <Input
        allowClear
        aria-label={qualityMode ? '搜索数据目录' : '搜索同步记录'}
        value={search}
        onChange={(event) => onSearch(event.target.value)}
        placeholder={qualityMode ? '搜索数据集 / 数据域 / 业务说明' : '搜索同步任务 / 类型 / 状态'}
        prefix={<FileSearchOutlined />}
      />
    </FilterBar>
  );
}

export function DataOverviewMetrics({ data, loading }: { data: any; loading: boolean }) {
  const summary = data?.summary || {};
  const completeness = summary.missingRate == null ? null : Math.max(0, 100 - Number(summary.missingRate));
  const items = [
    { title: '数据源数量', value: summary.sourceCount ?? '--', note: `已检查 ${summary.checkedSourceCount ?? '--'} 个数据对象`, status: 'success' },
    { title: '同步任务数', value: summary.syncCount ?? '--', note: `当前共 ${summary.syncCount ?? 0} 条任务记录`, status: 'info' },
    { title: '异常对象数', value: summary.exceptionCount ?? '--', note: `其中 ${summary.freshnessProblemCount ?? 0} 个时效异常`, status: summary.exceptionCount ? 'warning' : 'success' },
    { title: '数据完整率', value: completeness == null ? '--' : completeness.toFixed(2), unit: completeness == null ? undefined : '%', note: `覆盖 ${compact(summary.totalRows)} 条业务记录`, status: completeness != null && completeness < 99 ? 'warning' : 'success' },
    { title: '昨日更新量', value: compact(summary.todayProcessedRows), note: summary.todayProcessedRows == null ? '任务记录未提供处理量' : `${summary.todayTaskCount || 0} 个任务已计数`, status: 'info' }
  ];
  return (
    <div className="data-metric-grid">
      {items.map((item, index) => <MetricCard key={item.title} {...item as any} icon={metricIcons[index]} loading={loading} />)}
    </div>
  );
}

export function DataFlowPanel({ data, onCatalog }: { data: any; onCatalog: () => void }) {
  const summary = data?.summary || {};
  const steps = [
    { title: '采集', value: `${summary.sourceCount || 0} 个接入项`, icon: <CloudDownloadOutlined />, note: '业务源接入', status: '接入链路' },
    { title: '清洗', value: `${compact(summary.totalRows)} 条记录`, icon: <FilterOutlined />, note: '标准化处理', status: '记录口径' },
    { title: '校验', value: summary.passRate == null ? '--' : `${Number(summary.passRate).toFixed(2)}%`, icon: <SafetyCertificateOutlined />, note: '质量规则检查', status: '综合通过率' },
    { title: '入库', value: `${summary.tableCount || 0} 张表`, icon: <DatabaseOutlined />, note: '受控持久化', status: '数据表' },
    { title: '特征/服务', value: `${summary.catalogCount || 0} 个目录项`, icon: <ApiOutlined />, note: '预测与策略服务', status: '服务目录' }
  ];
  return (
    <SectionCard title="数据接入流程" className="data-flow-panel" extra={<Button type="link" onClick={onCatalog}>查看流程详情</Button>}>
      <div className="data-process-flow">
        {steps.map((step, index) => (
          <div className="data-process-step" key={step.title}>
            <div className="data-process-icon">{step.icon}</div>
            <strong>{step.title}</strong>
            <span>{step.value}</span>
            <small>{step.note}</small>
            <span className="data-process-status"><CheckCircleOutlined />{step.status}</span>
            {index < steps.length - 1 && <i />}
          </div>
        ))}
      </div>
    </SectionCard>
  );
}

export function DataHealthOverview({ data }: { data: any }) {
  const imports = data?.healthImports || data?.imports || [];
  const normalized = imports.map((row: any) => String(row.status || '').toLowerCase());
  const timedOut = imports.filter((row: any) => `${row.statusReason || ''} ${row.error || ''}`.toLowerCase().includes('timeout')).length;
  const succeeded = normalized.filter((status: string) => status === 'success' || status === 'succeeded' || status === 'completed').length;
  const failed = normalized.filter((status: string) => ['failed', 'error', 'cancelled', 'canceled'].includes(status)).length - timedOut;
  const running = normalized.filter((status: string) => ['running', 'pending', 'queued'].includes(status)).length;
  const total = imports.length;
  const successRate = total ? Number(((succeeded / total) * 100).toFixed(2)) : 0;
  const latestTimestamp = imports
    .map((row: any) => new Date(row.startedAt || row.createdAt).getTime())
    .filter(Number.isFinite)
    .sort((a: number, b: number) => b - a)[0] || Date.now();
  const dayKey = (time: number) => {
    const date = new Date(time);
    return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
  };
  const sevenDays = Array.from({ length: 7 }, (_, index) => {
    const time = latestTimestamp - (6 - index) * 86400000;
    const key = dayKey(time);
    const value = imports.filter((row: any) => {
      const rowTime = new Date(row.startedAt || row.createdAt).getTime();
      return Number.isFinite(rowTime) && dayKey(rowTime) === key && ['success', 'succeeded', 'completed'].includes(String(row.status || '').toLowerCase());
    }).length;
    return { key, label: key.slice(5), value };
  });
  const maxDay = Math.max(1, ...sevenDays.map((item) => item.value));
  return (
    <SectionCard title="数据健康摘要" className="data-health-panel">
      <div className="data-health-main">
        <Progress
          type="circle"
          size={132}
          percent={successRate}
          strokeWidth={9}
          strokeColor={chartColors.green}
          trailColor="#e9f1f4"
          format={(value) => <span className="data-health-rate"><strong>{Number(value || 0).toFixed(2)}%</strong><small>整体成功率</small></span>}
        />
        <div className="data-health-legend">
          <div><i className="success" /><span>成功</span><strong>{succeeded}</strong><small>{total ? `${((succeeded / total) * 100).toFixed(2)}%` : '--'}</small></div>
          <div><i className="danger" /><span>失败</span><strong>{Math.max(0, failed)}</strong><small>{total ? `${((Math.max(0, failed) / total) * 100).toFixed(2)}%` : '--'}</small></div>
          <div><i className="warning" /><span>超时</span><strong>{timedOut}</strong><small>{total ? `${((timedOut / total) * 100).toFixed(2)}%` : '--'}</small></div>
          <div><i className="info" /><span>进行中</span><strong>{running}</strong><small>{total ? `${((running / total) * 100).toFixed(2)}%` : '--'}</small></div>
        </div>
      </div>
      <div className="data-health-trend" aria-label="近7日成功任务趋势">
        <strong>近7日成功率趋势</strong>
        <div className="data-health-trend-bars">
          {sevenDays.map((item) => (
            <div key={item.key} title={`${item.key}：${item.value} 个成功任务`}>
              <i style={{ height: `${Math.max(item.value ? 28 : 5, (item.value / maxDay) * 48)}px` }} />
              <span>{item.label}</span>
            </div>
          ))}
        </div>
      </div>
    </SectionCard>
  );
}

export function OverviewQuickActions({
  onDataAccess,
  onCatalog,
  onQuality,
  onExport,
  onAlerts,
  onSyncRecords,
  onPermissions,
  onSettings,
  syncing,
  canSync,
  canExport
}: {
  onDataAccess: () => void;
  onCatalog: () => void;
  onQuality: () => void;
  onExport: () => void;
  onAlerts: () => void;
  onSyncRecords: () => void;
  onPermissions: () => void;
  onSettings: () => void;
  syncing: boolean;
  canSync: boolean;
  canExport: boolean;
}) {
  return (
    <SectionCard title="快捷操作" compact className="data-quick-actions-panel">
      <div className="data-quick-actions">
        <Button icon={<DatabaseOutlined />} loading={syncing} disabled={!canSync} onClick={onDataAccess}>数据接入</Button>
        <Button icon={<EyeOutlined />} onClick={onCatalog}>查看目录</Button>
        <Button icon={<SafetyCertificateOutlined />} onClick={onQuality}>质量巡检</Button>
        <Button icon={<DownloadOutlined />} disabled={!canExport} onClick={onExport}>导出概览</Button>
        <Button icon={<WarningOutlined />} onClick={onAlerts}>查看异常</Button>
        <Button icon={<UserSwitchOutlined />} onClick={onPermissions}>数据权限</Button>
        <Button icon={<SyncOutlined />} onClick={onSyncRecords}>同步记录</Button>
        <Button icon={<SettingOutlined />} onClick={onSettings}>配置管理</Button>
      </div>
    </SectionCard>
  );
}

export function SyncRecordsTable({
  rows,
  total,
  page,
  pageSize,
  loading,
  onPageChange,
  onDetail
}: {
  rows: any[];
  total: number;
  page: number;
  pageSize: number;
  loading?: boolean;
  onPageChange: (page: number) => void;
  onDetail: (row: any) => void;
}) {
  const columns: ColumnsType<any> = [
    { title: '任务名', dataIndex: 'name', width: 190, ellipsis: true },
    { title: '任务类型', dataIndex: 'type', width: 112, ellipsis: true },
    { title: '开始时间', dataIndex: 'startedAt', width: 155, render: (value) => String(value || '--').slice(0, 19) },
    { title: '耗时', dataIndex: 'duration', width: 82, align: 'center' },
    { title: '状态', dataIndex: 'status', width: 82, align: 'center', render: (value) => <Tag color={statusColor(value)}>{statusText(value)}</Tag> },
    { title: '同步量', dataIndex: 'processedRows', width: 104, align: 'right', render: compact },
    { title: '操作', width: 86, align: 'center', render: (_, row) => <Button type="link" size="small" onClick={() => onDetail(row)}>查看日志</Button> }
  ];
  return (
    <TableCard
      title="同步记录"
      className="data-sync-table"
      columns={columns}
      dataSource={rows}
      loading={loading}
      pagination={{
        current: page,
        pageSize,
        total,
        showSizeChanger: false,
        showTotal: (value) => `共 ${value} 条`,
        onChange: onPageChange
      }}
      scroll={{ x: 812 }}
    />
  );
}

export function OverviewSideRail({
  data,
  onDetail
}: {
  data: any;
  onDetail: (row: any) => void;
}) {
  const alerts = (data?.alerts || []).slice(0, 5);
  return (
    <div className="data-overview-rail">
      <SectionCard title="最近告警 / 异常提醒" compact className="data-alert-panel">
        {alerts.length ? alerts.map((item: any) => (
          <div className="data-alert-row" key={item.alert_id}>
            <span className={item.severity === 'critical' || item.severity === 'high' ? 'danger' : 'warning'} />
            <strong title={item.object_name || '数据异常'}>{item.object_name || '数据异常'}</strong>
            <p title={item.message || item.alert_type}>{item.message || item.alert_type}</p>
            <small>{String(item.detected_at || '--').slice(0, 16)}</small>
            <Button
              type="link"
              size="small"
              onClick={() => onDetail({
                alertId: item.alert_id,
                level: item.severity,
                type: item.alert_type,
                object: item.object_name,
                detectedAt: item.detected_at,
                status: item.status,
                source: item.source,
                message: item.message,
                latestTime: item.latest_time,
                staleReason: item.stale_reason
              })}
            >
              详情
            </Button>
          </div>
        )) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无异常提醒" />}
      </SectionCard>
    </div>
  );
}

export function QualityMetrics({ data, loading }: { data: any; loading: boolean }) {
  const summary = data?.summary || {};
  const metrics = [
    { title: '缺失率', value: summary.missingRate == null ? '--' : Number(summary.missingRate).toFixed(2), unit: summary.missingRate == null ? undefined : '%', note: '字段完整性检查', status: Number(summary.missingRate || 0) > 1 ? 'warning' : 'success' },
    { title: '重复率', value: summary.duplicateRate == null ? '--' : Number(summary.duplicateRate).toFixed(2), unit: summary.duplicateRate == null ? undefined : '%', note: '记录唯一性检查', status: Number(summary.duplicateRate || 0) > 0 ? 'warning' : 'success' },
    { title: '新鲜度得分', value: summary.freshnessScore == null ? '--' : Number(summary.freshnessScore).toFixed(0), unit: summary.freshnessScore == null ? undefined : '分', note: '业务时效性评分', status: summary.freshnessScore != null && Number(summary.freshnessScore) < 80 ? 'warning' : 'success' },
    { title: '校验通过率', value: summary.passRate == null ? '--' : Number(summary.passRate).toFixed(2), unit: summary.passRate == null ? undefined : '%', note: `已检查 ${summary.checkedSourceCount ?? 0} 个对象`, status: summary.passRate != null && Number(summary.passRate) < 95 ? 'warning' : 'success' },
    { title: '异常对象数', value: summary.exceptionCount ?? '--', unit: '个', note: '需要进一步治理', status: summary.exceptionCount ? 'danger' : 'success' }
  ];
  return (
    <div className="data-metric-grid">
      {metrics.map((item, index) => <MetricCard key={item.title} {...item as any} icon={metricIcons[index]} loading={loading} />)}
    </div>
  );
}

export function QualityMonitor({ data }: { data: any }) {
  const summary = data?.summary || {};
  const items = [
    ['缺失率', summary.missingRate ?? null, 'missing', '%'],
    ['重复率', summary.duplicateRate ?? null, 'duplicate', '%'],
    ['新鲜度得分', summary.freshnessScore ?? null, 'freshness', '分'],
    ['校验通过率', summary.passRate ?? null, 'pass', '%']
  ];
  return (
    <SectionCard title="数据质量监控" className="data-quality-monitor" extra={<span className="quality-range-pill">近7天</span>}>
      <div className="quality-progress-grid">
        {items.map(([label, value, key, unit]) => (
          <div className={`quality-progress-item quality-progress-item-${key}`} key={String(label)}>
            <div><span>{label}</span><strong>{value == null ? '--' : `${Number(value).toFixed(2)}${unit}`}</strong></div>
            <Progress
              className={`quality-progress quality-progress-${key}`}
              percent={value == null ? 0 : Math.min(100, Number(value))}
              showInfo={false}
              strokeColor={(key === 'missing' || key === 'duplicate') && Number(value || 0) > 0 ? chartColors.orange : chartColors.green}
            />
            <div className="quality-progress-scale"><span>0</span><span>25</span><span>50</span><span>75</span><span>100</span></div>
          </div>
        ))}
      </div>
    </SectionCard>
  );
}

export function ExceptionTable({
  rows,
  loading,
  onRefresh,
  onDetail
}: {
  rows: any[];
  loading?: boolean;
  onRefresh: () => void;
  onDetail: (row: any) => void;
}) {
  const [scope, setScope] = React.useState<'all' | 'stale' | 'empty' | 'other'>('all');
  const scopedRows = rows.filter((row) => {
    const status = String(row.status || '').toLowerCase();
    if (scope === 'all') return true;
    if (scope === 'stale') return status === 'stale' || Boolean(row.is_stale);
    if (scope === 'empty') return status === 'empty';
    return status !== 'stale' && status !== 'empty';
  });
  const scopes = [
    { key: 'all', label: '全部', count: rows.length },
    { key: 'stale', label: '时效异常', count: rows.filter((row) => String(row.status || '').toLowerCase() === 'stale' || row.is_stale).length },
    { key: 'empty', label: '空表', count: rows.filter((row) => String(row.status || '').toLowerCase() === 'empty').length },
    { key: 'other', label: '其他', count: rows.filter((row) => !['stale', 'empty'].includes(String(row.status || '').toLowerCase()) && !row.is_stale).length }
  ] as const;
  const columns: ColumnsType<any> = [
    { title: '数据集', render: (_, row) => row.source_name || row.dataset_id || '--', width: 148, ellipsis: true },
    { title: '问题类型', render: (_, row) => <Tag color={statusColor(row.status)}>{statusText(row.status)}</Tag>, width: 84 },
    { title: '缺失率', dataIndex: 'missing_rate', width: 76, render: (value) => value == null ? '--' : `${value}%` },
    { title: '重复率', dataIndex: 'duplicate_rate', width: 70, render: (value) => value == null ? '--' : `${value}%` },
    { title: '新鲜度', dataIndex: 'freshness_score', width: 70, render: (value) => value == null ? '--' : `${value}分` },
    { title: '一致性', dataIndex: 'consistency_score', width: 70, render: (value) => value == null ? '--' : `${value}%` },
    { title: '状态', dataIndex: 'status', width: 84, render: (value) => <Tag color={statusColor(value)}>{statusText(value)}</Tag> },
    { title: '操作', width: 56, align: 'center', render: (_, row) => <Button type="link" size="small" onClick={() => onDetail(row)}>详情</Button> }
  ];
  return (
    <div className="data-exception-table-wrap">
      <div className="data-exception-toolbar">
        <div className="data-exception-scopes" role="tablist" aria-label="异常类型筛选">
          {scopes.map((item) => (
            <Button
              key={item.key}
              type={scope === item.key ? 'primary' : 'text'}
              size="small"
              role="tab"
              aria-selected={scope === item.key}
              onClick={() => setScope(item.key)}
            >
              {item.label}（{item.count}）
            </Button>
          ))}
        </div>
        <Button size="small" icon={<SyncOutlined />} loading={loading} onClick={onRefresh}>刷新</Button>
      </div>
      <Table
        size="small"
        rowKey={(row) => row.dataset_id || row.source_name}
        columns={columns}
        dataSource={scopedRows}
        pagination={{ pageSize: 8, showSizeChanger: false, showTotal: (total) => `共 ${total} 条` }}
      />
    </div>
  );
}

export function CatalogPanel({
  rows,
  selected,
  onSelect,
  preview,
  previewLoading,
  previewError,
  previewPage,
  previewPageSize,
  previewSearch,
  exporting,
  canExport,
  onManage,
  onPreviewPageChange,
  onPreviewSearchDraft,
  onPreviewSearch,
  onPreviewRetry,
  onExport
}: {
  rows: any[];
  selected?: any;
  onSelect: (row: any) => void;
  preview?: any;
  previewLoading: boolean;
  previewError?: unknown;
  previewPage: number;
  previewPageSize: number;
  previewSearch: string;
  exporting: boolean;
  canExport: boolean;
  onManage: () => void;
  onPreviewPageChange: (page: number) => void;
  onPreviewSearchDraft: (value: string) => void;
  onPreviewSearch: (value: string) => void;
  onPreviewRetry: () => void;
  onExport: () => void;
}) {
  const catalogPageSize = 6;
  const [catalogPage, setCatalogPage] = React.useState(1);
  const [previewOpen, setPreviewOpen] = React.useState(false);
  const catalogPageCount = Math.max(1, Math.ceil(rows.length / catalogPageSize));
  const safeCatalogPage = Math.min(catalogPage, catalogPageCount);
  const visibleCatalogRows = rows.slice((safeCatalogPage - 1) * catalogPageSize, safeCatalogPage * catalogPageSize);

  React.useEffect(() => {
    setCatalogPage(1);
  }, [rows.length]);

  const previewColumns = (preview?.columns || []).filter(visibleBusinessField).map((column: any) => ({
    title: (
      <span title={`${column.display_name || column.field_id} / ${column.data_type || 'unknown'}`}>
        {column.display_name || column.field_id}<small className="catalog-column-type">{column.data_type || ''}</small>
      </span>
    ),
    dataIndex: column.field_id,
    key: column.field_id,
    width: 150,
    ellipsis: true,
    render: (value: unknown) => {
      const text = value == null ? '--' : typeof value === 'object' ? JSON.stringify(value) : String(value);
      return <span title={text}>{text}</span>;
    }
  }));
  const previewRows = preview?.records || [];
  const previewTotal = Number(preview?.pagination?.total ?? preview?.total ?? 0);
  const selectedFields = (selected?.fields || []).filter(visibleBusinessField);
  return (
    <SectionCard title="数据目录" className="data-catalog-panel" extra={<Button size="small" onClick={onManage}>目录管理</Button>}>
      <div className="catalog-card-grid">
        {visibleCatalogRows.length ? visibleCatalogRows.map((row, index) => (
          <button className={`${selected?.dataset_id === row.dataset_id ? 'active' : ''} catalog-tone-${index % 3}`} key={row.dataset_id} onClick={() => onSelect(row)}>
            <DatabaseOutlined />
            <span>
              <strong>{row.display_name || row.dataset_id}</strong>
              <small>记录数 {compact(row.recordCount)} · {row.fields?.filter(visibleBusinessField).length || 0} 个字段</small>
              <small>业务时间 {businessTime(row.businessTime)}</small>
            </span>
            <Tag color={row.runtime?.exists === false ? 'warning' : 'success'}>{row.runtime?.exists === false ? '暂不可用' : '已接入'}</Tag>
          </button>
        )) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前筛选条件下暂无数据目录" />}
      </div>
      {rows.length > catalogPageSize ? (
        <Pagination
          className="catalog-card-pagination"
          size="small"
          current={safeCatalogPage}
          pageSize={catalogPageSize}
          total={rows.length}
          showSizeChanger={false}
          showLessItems
          onChange={setCatalogPage}
        />
      ) : null}
      {selected ? (
        <div className="catalog-detail">
          <div className="catalog-meta">
            <h3>{selected.display_name} <small>{selected.dataset_id}</small></h3>
            <dl>
              <dt>所属目录</dt><dd>{selected.business_domain || '--'}</dd>
              <dt>数据形态</dt><dd>{selected.object_type === 'view' ? '业务视图' : '业务数据集'}</dd>
              <dt>记录数量</dt><dd>{compact(selected.recordCount)} 条</dd>
              <dt>字段数量</dt><dd>{selectedFields.length} 个</dd>
              <dt>数据状态</dt><dd>{selected.runtime?.exists === false ? '暂不可用' : '已接入'}</dd>
              <dt>业务时间</dt><dd>{businessTime(selected.businessTime)}</dd>
              <dt>缺失率</dt><dd>{selected.quality?.missing_rate == null ? '--' : `${Number(selected.quality.missing_rate).toFixed(2)}%`}</dd>
              <dt>新鲜度</dt><dd>{selected.quality?.freshness_score == null ? '--' : `${Number(selected.quality.freshness_score).toFixed(0)} 分`}</dd>
              <dt>用途说明</dt><dd>{selected.description || '--'}</dd>
            </dl>
            <div className="catalog-meta-actions">
              <Button type="primary" size="small" onClick={() => setPreviewOpen(true)}>查看数据明细</Button>
              <Button size="small" loading={exporting} disabled={!canExport || !selected.export_allowed || !preview?.available || previewTotal === 0} onClick={onExport}>导出当前范围</Button>
            </div>
          </div>
          <Table
            size="small"
            rowKey="field_id"
            pagination={{ pageSize: 8, showSizeChanger: false, size: 'small', hideOnSinglePage: true }}
            dataSource={selectedFields}
            columns={[
              { title: '字段标识', dataIndex: 'field_id' },
              { title: '业务名称', dataIndex: 'display_name' },
              { title: '类型', dataIndex: 'data_type' },
              { title: '说明', dataIndex: 'description' }
            ]}
          />
          <Modal
            className="catalog-preview-modal"
            title={`${selected.display_name} · 数据集明细`}
            open={previewOpen}
            footer={null}
            width={1120}
            destroyOnHidden
            onCancel={() => setPreviewOpen(false)}
          >
          <div className="catalog-preview">
            <div className="catalog-preview-toolbar">
              <div>
                <h3>数据集明细</h3>
                <small>
                  受控字段 · 共 {previewTotal.toLocaleString()} 条
                  {preview?.order_by ? ` · 按 ${preview.order_by} ${preview.order_direction || 'desc'} 排序` : ''}
                </small>
              </div>
              <div className="catalog-preview-actions">
                <Input.Search
                  allowClear
                  value={previewSearch}
                  placeholder="搜索当前数据集"
                  onChange={(event) => {
                    onPreviewSearchDraft(event.target.value);
                    if (!event.target.value) onPreviewSearch('');
                  }}
                  onSearch={onPreviewSearch}
                />
                <Button
                  icon={<DownloadOutlined />}
                  loading={exporting}
                  disabled={!canExport || !selected.export_allowed || !preview?.available || previewTotal === 0}
                  onClick={onExport}
                >
                  导出当前范围
                </Button>
              </div>
            </div>
            {previewLoading ? <LoadingBlock rows={3} /> : null}
            {!previewLoading && previewError ? (
              <div className="catalog-preview-error">
                <InlineError message={previewError instanceof Error ? previewError.message : '数据集加载失败'} />
                <Button size="small" onClick={onPreviewRetry}>重试</Button>
              </div>
            ) : null}
            {!previewLoading && !previewError && (!preview?.available || !previewRows.length) ? (
              <EmptyState
                title="当前范围没有数据集记录"
                description="数据库查询已完成，但没有可展示的明细。"
                reason={preview?.message || (previewSearch ? `未找到包含“${previewSearch}”的记录` : '当前数据集为空')}
                queryScope={`${selected.display_name}${previewSearch ? `；筛选：${previewSearch}` : '；全部记录'}`}
                action={<Button size="small" onClick={onPreviewRetry}>重新查询</Button>}
              />
            ) : null}
            {!previewLoading && !previewError && preview?.available && previewRows.length ? (
              <Table
                className="catalog-preview-table"
                size="small"
                rowKey={(row) => String(
                  row.id
                  ?? row.task_id
                  ?? row.event_id
                  ?? `${row[preview?.order_by] ?? 'row'}-${row.market_code ?? ''}-${row.node_label ?? ''}-${row.price_category ?? ''}`
                )}
                columns={previewColumns}
                dataSource={previewRows}
                scroll={{ x: Math.max(760, previewColumns.length * 150) }}
                pagination={{
                  current: Number(preview?.pagination?.page || previewPage),
                  pageSize: Number(preview?.pagination?.page_size || previewPageSize),
                  total: previewTotal,
                  showSizeChanger: false,
                  showTotal: (total) => `共 ${total} 条`,
                  onChange: onPreviewPageChange
                }}
              />
            ) : null}
          </div>
          </Modal>
        </div>
      ) : null}
    </SectionCard>
  );
}

export function SourceStatusBar({ rows, onAllSources }: { rows: any[]; onAllSources: () => void }) {
  return (
    <div className="data-source-status">
      <strong>接入状态</strong>
      {rows.slice(0, 6).map((row) => (
        <div key={row.dataset_id}>
          <span>{row.source_name || row.dataset_id}</span>
          <Tag color={statusColor(row.status)}>{statusText(row.status)}</Tag>
          <small>{row.latest_time ? `业务时间 ${businessTime(row.latest_time)}` : row.check_pass_rate == null ? '质量检查待完善' : `校验通过率 ${Number(row.check_pass_rate).toFixed(2)}%`}</small>
        </div>
      ))}
      <Button type="link" size="small" onClick={onAllSources}>全部数据源 ›</Button>
    </div>
  );
}

export const dataTabs = [
  { key: 'data-overview', label: '数据总览' },
  { key: 'data-quality', label: '数据质量 / 数据目录' }
];

export { DownloadOutlined, CheckCircleOutlined, ExclamationCircleOutlined };
