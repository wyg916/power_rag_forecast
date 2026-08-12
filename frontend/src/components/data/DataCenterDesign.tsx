import {
  ApiOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  CloudDownloadOutlined,
  DatabaseOutlined,
  DownloadOutlined,
  ExclamationCircleOutlined,
  FileSearchOutlined,
  FilterOutlined,
  SafetyCertificateOutlined,
  SyncOutlined,
  WarningOutlined
} from '@ant-design/icons';
import { Button, Empty, Input, Progress, Table, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { MetricCard } from '../cards/MetricCard';
import { SectionCard } from '../cards/SectionCard';
import { TableCard } from '../cards/TableCard';
import { AppChart } from '../charts/AppChart';
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
  if (lower === 'missing_table') return '缺表';
  if (lower === 'stale') return '已过期';
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
  onSearch
}: {
  qualityMode?: boolean;
  search: string;
  onSearch: (value: string) => void;
}) {
  return (
    <FilterBar className="data-design-filter" label={null} compact>
      <Input
        allowClear
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
    { title: '可用接入项', value: summary.sourceCount ?? '--', note: `本次检查 ${summary.checkedSourceCount ?? '--'} 个`, status: 'success' },
    { title: '同步任务', value: summary.syncCount ?? '--', note: '当前任务数量', status: 'info' },
    { title: '异常对象', value: summary.exceptionCount ?? '--', note: '质量与新鲜度检查', status: summary.exceptionCount ? 'warning' : 'success' },
    { title: '数据完整率', value: completeness == null ? '--' : completeness.toFixed(2), unit: completeness == null ? undefined : '%', note: '基于实际登记字段', status: completeness != null && completeness < 99 ? 'warning' : 'success' },
    { title: '最近同步', value: summary.latestSyncAt ? String(summary.latestSyncAt).slice(5, 16) : '--', note: summary.latestSyncRunId || '暂无 run_id', status: summary.latestSyncAt ? 'info' : 'warning' },
    { title: '今日处理量', value: compact(summary.todayProcessedRows), note: summary.todayProcessedRows == null ? '任务未记录行数' : `${summary.todayTaskCount || 0} 个任务`, status: 'info' }
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
    { title: '采集', value: `${summary.sourceCount || 0} 个接入项`, icon: <CloudDownloadOutlined />, note: '外部业务接入' },
    { title: '清洗', value: `${compact(summary.totalRows)} 条记录`, icon: <FilterOutlined />, note: '当前入库记录口径' },
    { title: '校验', value: summary.passRate == null ? '--' : `${Number(summary.passRate).toFixed(2)}%`, icon: <SafetyCertificateOutlined />, note: '聚合质量检查' },
    { title: '入库', value: `${summary.tableCount || 0} 张表`, icon: <DatabaseOutlined />, note: 'PostgreSQL' },
    { title: '特征/服务', value: `${summary.catalogCount || 0} 个目录项`, icon: <ApiOutlined />, note: '预测与策略服务' }
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
            {index < steps.length - 1 && <i />}
          </div>
        ))}
      </div>
    </SectionCard>
  );
}

export function DataHealthOverview({ data }: { data: any }) {
  const summary = data?.summary || {};
  const pass = Number(summary.passRate || 0);
  const chartData = (data?.qualityItems || [])
    .map((item: any) => item.check_pass_rate)
    .filter((value: unknown) => value !== null && value !== undefined)
    .slice(0, 7)
    .map(Number);
  return (
    <SectionCard title="数据健康摘要" className="data-health-panel">
      <div className="data-health-main">
        <Progress type="circle" size={92} percent={Math.round(pass)} strokeColor={chartColors.green} />
        <dl>
          <dt>正常</dt><dd>{Math.max(0, Number(summary.sourceCount || 0) - Number(summary.exceptionCount || 0))}</dd>
          <dt>异常</dt><dd>{summary.exceptionCount || 0}</dd>
          <dt>陈旧对象</dt><dd>{(data?.qualityItems || []).filter((item: any) => item.is_stale).length}</dd>
          <dt>完整率</dt><dd>{summary.missingRate == null ? '--' : `${Math.max(0, 100 - Number(summary.missingRate)).toFixed(2)}%`}</dd>
        </dl>
      </div>
      <AppChart
        height={90}
        option={{
          animation: false,
          grid: { left: 8, right: 8, top: 8, bottom: 20 },
          xAxis: { type: 'category', data: chartData.map((_: number, i: number) => i + 1), axisTick: { show: false }, axisLine: { show: false } },
          yAxis: { type: 'value', min: 0, max: 100, show: false },
          series: [{ type: 'bar', data: chartData, barWidth: 18, itemStyle: { color: chartColors.green, borderRadius: [4, 4, 0, 0] } }]
        }}
      />
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
    { title: '任务名', dataIndex: 'name', width: 180 },
    { title: 'run_id', dataIndex: 'runId', width: 150, ellipsis: true },
    { title: '类型', dataIndex: 'type', width: 90 },
    { title: '开始时间', dataIndex: 'startedAt', width: 170 },
    { title: '结束时间', dataIndex: 'endedAt', width: 170 },
    { title: '耗时', dataIndex: 'duration', width: 90 },
    { title: '状态', dataIndex: 'status', width: 90, render: (value) => <Tag color={statusColor(value)}>{statusText(value)}</Tag> },
    { title: '处理', dataIndex: 'processedRows', width: 80, align: 'right', render: compact },
    { title: '成功', dataIndex: 'successRows', width: 80, align: 'right', render: compact },
    { title: '失败', dataIndex: 'failedRows', width: 80, align: 'right', render: compact },
    { title: '操作', width: 90, fixed: 'right', render: (_, row) => <Button type="link" size="small" onClick={() => onDetail(row)}>查看日志</Button> }
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
      scroll={{ y: 205, x: 1280 }}
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
  const alerts = (data?.alerts || []).slice(0, 8);
  return (
    <div className="data-overview-rail">
      <SectionCard title="最近告警 / 异常提醒" compact className="data-alert-panel">
        {alerts.length ? alerts.map((item: any) => (
          <div className="data-alert-row" key={item.alert_id}>
            <span className={item.severity === 'critical' || item.severity === 'high' ? 'danger' : 'warning'} />
            <div>
              <p><strong>{item.object_name || '数据异常'}</strong>{item.message || item.alert_type}</p>
              <small>{item.alert_type} · {item.status} · {String(item.detected_at || '--').slice(0, 19)}</small>
            </div>
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
    { title: '缺失率', value: summary.missingRate == null ? '--' : Number(summary.missingRate).toFixed(2), unit: summary.missingRate == null ? undefined : '%', status: Number(summary.missingRate || 0) > 1 ? 'warning' : 'success' },
    { title: '重复率', value: summary.duplicateRate == null ? '--' : Number(summary.duplicateRate).toFixed(2), unit: summary.duplicateRate == null ? undefined : '%', status: Number(summary.duplicateRate || 0) > 0 ? 'warning' : 'success' },
    { title: '新鲜度', value: summary.freshnessScore == null ? '--' : Number(summary.freshnessScore).toFixed(0), unit: summary.freshnessScore == null ? undefined : '分', status: summary.freshnessScore != null && Number(summary.freshnessScore) < 80 ? 'warning' : 'success' },
    { title: '字段一致性', value: summary.consistencyScore == null ? '--' : Number(summary.consistencyScore).toFixed(2), unit: summary.consistencyScore == null ? undefined : '%', status: summary.consistencyScore != null && Number(summary.consistencyScore) < 100 ? 'warning' : 'success' },
    { title: '综合通过率', value: summary.passRate == null ? '--' : Number(summary.passRate).toFixed(2), unit: summary.passRate == null ? undefined : '%', status: summary.passRate != null && Number(summary.passRate) < 95 ? 'warning' : 'success' },
    { title: '异常对象', value: summary.exceptionCount ?? '--', unit: '个', status: summary.exceptionCount ? 'danger' : 'success' }
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
    ['完整性', summary.missingRate == null ? null : Math.max(0, 100 - Number(summary.missingRate))],
    ['唯一性', summary.duplicateRate == null ? null : Math.max(0, 100 - Number(summary.duplicateRate))],
    ['新鲜度', summary.freshnessScore ?? null],
    ['字段一致性', summary.consistencyScore ?? null],
    ['综合通过率', summary.passRate ?? null]
  ];
  return (
    <SectionCard title="数据质量监控" className="data-quality-monitor">
      <div className="quality-progress-grid">
        {items.map(([label, value]) => (
          <div key={String(label)}>
            <span>{label}</span><strong>{value == null ? '--' : `${Number(value).toFixed(2)}%`}</strong>
            <Progress percent={value == null ? 0 : Math.min(100, Number(value))} showInfo={false} strokeColor={value != null && Number(value) < 80 ? chartColors.orange : chartColors.green} />
          </div>
        ))}
      </div>
    </SectionCard>
  );
}

export function ExceptionTable({ rows }: { rows: any[] }) {
  const columns: ColumnsType<any> = [
    { title: '数据集', render: (_, row) => row.source_name || row.dataset_id || '--', width: 190 },
    { title: '问题类型', render: (_, row) => row.stale_reason || row.not_found_reason || row.message || row.status || '--', width: 260 },
    { title: '缺失率', dataIndex: 'missing_rate', render: (value) => value == null ? '--' : `${value}%` },
    { title: '重复率', dataIndex: 'duplicate_rate', render: (value) => value == null ? '--' : `${value}%` },
    { title: '新鲜度', dataIndex: 'freshness_score', render: (value) => value == null ? '--' : `${value}分` },
    { title: '一致性', dataIndex: 'consistency_score', render: (value) => value == null ? '--' : `${value}%` },
    { title: '最新时间', dataIndex: 'latest_time', width: 165, render: (value) => value ? String(value).slice(0, 19) : '--' },
    { title: '状态', dataIndex: 'status', render: (value) => <Tag color={statusColor(value)}>{statusText(value)}</Tag> }
  ];
  return <Table size="small" rowKey={(row) => row.dataset_id || row.source_name} columns={columns} dataSource={rows} pagination={false} scroll={{ y: 205, x: 1120 }} />;
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
  onPreviewPageChange: (page: number) => void;
  onPreviewSearchDraft: (value: string) => void;
  onPreviewSearch: (value: string) => void;
  onPreviewRetry: () => void;
  onExport: () => void;
}) {
  const previewColumns = (preview?.columns || []).map((column: any) => ({
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
  return (
    <SectionCard title="数据目录" className="data-catalog-panel">
      <div className="catalog-card-grid">
        {rows.map((row) => (
          <button className={selected?.dataset_id === row.dataset_id ? 'active' : ''} key={row.dataset_id} onClick={() => onSelect(row)}>
            <DatabaseOutlined />
            <span><strong>{row.display_name || row.dataset_id}</strong><small>字段数 {row.fields?.length || 0}</small></span>
            <Tag color={row.runtime?.exists === false ? 'warning' : 'success'}>{row.runtime?.exists === false ? '暂不可用' : '已接入'}</Tag>
          </button>
        ))}
      </div>
      {selected ? (
        <div className="catalog-detail">
          <div className="catalog-meta">
            <h3>{selected.display_name} <small>{selected.dataset_id}</small></h3>
            <dl>
              <dt>所属目录</dt><dd>{selected.business_domain || '--'}</dd>
              <dt>数据形态</dt><dd>{selected.object_type === 'view' ? '业务视图' : '业务数据集'}</dd>
              <dt>默认排序</dt><dd>{selected.default_sort || '--'}</dd>
              <dt>最大分页</dt><dd>{selected.max_page_size || '--'}</dd>
              <dt>导出权限</dt><dd>{selected.export_allowed ? '支持受控导出' : '不可导出'}</dd>
              <dt>用途说明</dt><dd>{selected.description || '--'}</dd>
            </dl>
          </div>
          <Table
            size="small"
            rowKey="field_id"
            pagination={false}
            scroll={{ y: 130 }}
            dataSource={selected.fields || []}
            columns={[
              { title: '字段标识', dataIndex: 'field_id' },
              { title: '业务名称', dataIndex: 'display_name' },
              { title: '类型', dataIndex: 'data_type' },
              { title: '说明', dataIndex: 'description' }
            ]}
          />
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
                  ?? row.run_id
                  ?? row.event_id
                  ?? row[preview?.order_by]
                  ?? JSON.stringify(row)
                )}
                columns={previewColumns}
                dataSource={previewRows}
                scroll={{ x: Math.max(760, previewColumns.length * 150), y: 180 }}
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
        </div>
      ) : null}
    </SectionCard>
  );
}

export function SourceStatusBar({ rows }: { rows: any[] }) {
  return (
    <div className="data-source-status">
      <strong>接入状态</strong>
      {rows.slice(0, 6).map((row) => (
        <div key={row.dataset_id}>
          <span>{row.source_name || row.dataset_id}</span>
          <Tag color={statusColor(row.status)}>{statusText(row.status)}</Tag>
          <small>{row.latest_time ? `更新 ${String(row.latest_time).slice(5, 16)}` : row.message || '暂无更新时间'}</small>
        </div>
      ))}
    </div>
  );
}

export const dataTabs = [
  { key: 'data-overview', label: '数据总览' },
  { key: 'data-quality', label: '数据质量 / 数据目录' }
];

export { DownloadOutlined, CheckCircleOutlined, ExclamationCircleOutlined };
