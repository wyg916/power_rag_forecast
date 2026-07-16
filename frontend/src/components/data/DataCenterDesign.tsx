import {
  ApiOutlined,
  CheckCircleOutlined,
  CloudDownloadOutlined,
  DatabaseOutlined,
  DownloadOutlined,
  ExclamationCircleOutlined,
  FileSearchOutlined,
  FilterOutlined,
  SafetyCertificateOutlined,
  SyncOutlined,
  TableOutlined,
  WarningOutlined
} from '@ant-design/icons';
import { Button, Empty, Input, Progress, Select, Space, Table, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import type { ReactNode } from 'react';
import { MetricCard } from '../cards/MetricCard';
import { SectionCard } from '../cards/SectionCard';
import { TableCard } from '../cards/TableCard';
import { AppChart } from '../charts/AppChart';
import { chartColors } from '../charts/chartTheme';
import { FilterBar } from '../common/FilterBar';
import { PageTabs } from '../common/PageTabs';

const metricIcons = [
  <DatabaseOutlined />,
  <SyncOutlined />,
  <WarningOutlined />,
  <SafetyCertificateOutlined />,
  <CloudDownloadOutlined />
];

function compact(value: unknown) {
  const number = Number(value || 0);
  return number >= 100000000 ? `${(number / 100000000).toFixed(2)}亿`
    : number >= 10000 ? `${(number / 10000).toFixed(2)}万`
      : number.toLocaleString();
}

function statusColor(value: unknown) {
  const text = String(value || '').toLowerCase();
  if (text.includes('fail') || text.includes('error') || text.includes('异常') || text.includes('缺失')) return 'error';
  if (text.includes('running') || text.includes('进行')) return 'processing';
  if (text.includes('warning') || text.includes('检查') || text.includes('延迟')) return 'warning';
  return 'success';
}

function statusText(value: unknown) {
  const text = String(value || '');
  const lower = text.toLowerCase();
  if (lower === 'missing_table') return '缺表';
  if (lower === 'ok') return '正常';
  if (lower === 'running') return '进行中';
  if (lower === 'failed') return '失败';
  return text || '需关注';
}

export function DataPageHeader({
  title,
  subtitle,
  tabs,
  controls
}: {
  title: string;
  subtitle: string;
  tabs?: ReactNode;
  controls?: ReactNode;
}) {
  return (
    <div className="data-design-header">
      <div>
        <h1>{title}</h1>
        <p>{subtitle}</p>
      </div>
      <div className="data-header-tools">{tabs}{controls}</div>
    </div>
  );
}

export function DataContextBar({
  qualityMode,
  search,
  onSearch,
  actions
}: {
  qualityMode?: boolean;
  search: string;
  onSearch: (value: string) => void;
  actions: ReactNode;
}) {
  return (
    <FilterBar className="data-design-filter" label={null} actions={actions}>
      <Select value="all" options={[{ value: 'all', label: '数据域：全部' }]} />
      <Select value="all" options={[{ value: 'all', label: qualityMode ? '表类型：全部' : '时间范围：近7天' }]} />
      <Select value="all" options={[{ value: 'all', label: qualityMode ? '质量等级：全部' : '数据源状态：全部' }]} />
      {qualityMode && <Select value="all" options={[{ value: 'all', label: '更新状态：全部' }]} />}
      <Input
        allowClear
        value={search}
        onChange={(event) => onSearch(event.target.value)}
        placeholder="请输入表名 / 数据源 / 任务名"
        prefix={<FileSearchOutlined />}
      />
    </FilterBar>
  );
}

export function DataOverviewMetrics({ data, loading }: { data: any; loading: boolean }) {
  const summary = data?.summary || {};
  const items = [
    { title: '数据源数量', value: summary.catalogCount || summary.sourceCount || 0, note: `数据库表 ${summary.tableCount || 0}`, status: 'success' },
    { title: '同步任务数', value: summary.syncCount || 0, note: '来自任务记录', status: 'running' },
    { title: '异常表数', value: summary.exceptionCount || 0, note: `新鲜度关注 ${summary.freshnessProblemCount || 0}`, status: summary.exceptionCount ? 'warning' : 'success' },
    { title: '数据完整率', value: Math.max(0, 100 - Number(summary.missingRate || 0)).toFixed(2), unit: '%', note: `校验通过 ${Number(summary.passRate || 0).toFixed(2)}%`, status: 'success' },
    { title: '有效记录量', value: compact(summary.totalRows), note: '目录表记录汇总', status: 'info' }
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
    { title: '采集', value: `${summary.sourceCount || 0} 个数据源`, icon: <CloudDownloadOutlined />, note: '外部数据接入' },
    { title: '清洗', value: `${compact(summary.totalRows)} 条记录`, icon: <FilterOutlined />, note: '标准化处理中' },
    { title: '校验', value: `${Number(summary.passRate || 0).toFixed(2)}%`, icon: <SafetyCertificateOutlined />, note: '质量规则校验' },
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
  const chartData = (data?.qualityItems || []).slice(0, 7).map((item: any) => Number(item.check_pass_rate || 0));
  return (
    <SectionCard title="数据健康摘要" className="data-health-panel">
      <div className="data-health-main">
        <Progress type="circle" size={92} percent={Math.round(pass)} strokeColor={chartColors.green} />
        <dl>
          <dt>正常</dt><dd>{Math.max(0, Number(summary.sourceCount || 0) - Number(summary.exceptionCount || 0))}</dd>
          <dt>异常</dt><dd>{summary.exceptionCount || 0}</dd>
          <dt>新鲜度关注</dt><dd>{summary.freshnessProblemCount || 0}</dd>
          <dt>完整率</dt><dd>{Math.max(0, 100 - Number(summary.missingRate || 0)).toFixed(2)}%</dd>
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

export function SyncRecordsTable({ rows, onDetail }: { rows: any[]; onDetail: (row: any) => void }) {
  const columns: ColumnsType<any> = [
    { title: '任务名', dataIndex: 'name', width: 210 },
    { title: '类型', dataIndex: 'type' },
    { title: '开始时间', dataIndex: 'startedAt', width: 170 },
    { title: '耗时', dataIndex: 'duration', width: 90 },
    { title: '状态', dataIndex: 'status', render: (value) => <Tag color={statusColor(value)}>{value}</Tag> },
    { title: '同步量', dataIndex: 'rows', align: 'right', render: compact },
    { title: '操作', width: 90, render: (_, row) => <Button type="link" size="small" onClick={() => onDetail(row)}>查看日志</Button> }
  ];
  return <TableCard title="同步记录" className="data-sync-table" columns={columns} dataSource={rows} pagination={false} scroll={{ y: 245, x: 850 }} />;
}

export function OverviewSideRail({
  data,
  onNavigate
}: {
  data: any;
  onNavigate: (key: string) => void;
}) {
  const problems = [...(data?.freshnessProblems || []), ...(data?.exceptions || [])].slice(0, 5);
  return (
    <div className="data-overview-rail">
      <SectionCard title="快捷操作" compact>
        <div className="data-quick-grid">
          <Button icon={<DatabaseOutlined />} onClick={() => onNavigate('data-overview')}>数据总览</Button>
          <Button icon={<TableOutlined />} onClick={() => onNavigate('data-quality')}>查看目录</Button>
          <Button icon={<SafetyCertificateOutlined />} onClick={() => onNavigate('data-quality')}>质量巡检</Button>
          <Button icon={<SyncOutlined />} onClick={() => onNavigate('data-overview')}>同步记录</Button>
        </div>
      </SectionCard>
      <SectionCard title="最近告警 / 异常提醒" compact className="data-alert-panel">
        {problems.length ? problems.map((item: any, index: number) => (
          <div className="data-alert-row" key={`${item.table_name || item.source_name}-${index}`}>
            <span className={index === 0 ? 'danger' : 'warning'} />
            <p><strong>{item.table_name || item.source_name || '数据异常'}</strong>{item.not_found_reason || item.message || item.status}</p>
          </div>
        )) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无异常提醒" />}
      </SectionCard>
    </div>
  );
}

export function QualityMetrics({ data, loading }: { data: any; loading: boolean }) {
  const summary = data?.summary || {};
  const metrics = [
    { title: '缺失率', value: Number(summary.missingRate || 0).toFixed(2), unit: '%', status: Number(summary.missingRate || 0) > 1 ? 'warning' : 'success' },
    { title: '重复率', value: Number(summary.duplicateRate || 0).toFixed(2), unit: '%', status: 'success' },
    { title: '新鲜度', value: summary.freshnessScore == null ? '--' : Number(summary.freshnessScore).toFixed(0), unit: '分', status: Number(summary.freshnessScore || 0) < 80 ? 'warning' : 'success' },
    { title: '校验通过率', value: Number(summary.passRate || 0).toFixed(2), unit: '%', status: 'success' },
    { title: '异常表数', value: summary.exceptionCount || 0, unit: '张', status: summary.exceptionCount ? 'danger' : 'success' }
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
    ['缺失率', Number(summary.missingRate || 0), 2],
    ['重复率', Number(summary.duplicateRate || 0), 2],
    ['新鲜度', Number(summary.freshnessScore || 0), 100],
    ['校验通过率', Number(summary.passRate || 0), 100]
  ];
  return (
    <SectionCard title="数据质量监控" className="data-quality-monitor">
      <div className="quality-progress-grid">
        {items.map(([label, value, max]) => (
          <div key={String(label)}>
            <span>{label}</span><strong>{Number(value).toFixed(2)}{Number(max) === 100 ? '%' : '%'}</strong>
            <Progress percent={Math.min(100, Number(value) / Number(max) * 100)} showInfo={false} strokeColor={Number(value) > Number(max) * .8 && Number(max) === 2 ? chartColors.orange : chartColors.green} />
          </div>
        ))}
      </div>
    </SectionCard>
  );
}

export function ExceptionTable({ rows }: { rows: any[] }) {
  const columns: ColumnsType<any> = [
    { title: '数据源 / 表名', render: (_, row) => row.table_name || row.source_name || '--', width: 190 },
    { title: '问题类型', render: (_, row) => row.not_found_reason || row.message || row.status || '--' },
    { title: '缺失率', dataIndex: 'missing_rate', render: (value) => value == null ? '--' : `${value}%` },
    { title: '重复率', dataIndex: 'duplicate_rate', render: (value) => value == null ? '--' : `${value}%` },
    { title: '新鲜度', dataIndex: 'freshness_score', render: (value) => value == null ? '--' : `${value}分` },
    { title: '状态', dataIndex: 'status', render: (value) => <Tag color={statusColor(value)}>{statusText(value)}</Tag> }
  ];
  return <Table size="small" rowKey={(row) => row.table_name || row.source_name} columns={columns} dataSource={rows} pagination={false} scroll={{ y: 205, x: 780 }} />;
}

export function CatalogPanel({
  rows,
  selected,
  onSelect
}: {
  rows: any[];
  selected?: any;
  onSelect: (row: any) => void;
}) {
  const visible = rows.slice(0, 6);
  return (
    <SectionCard title="数据目录" className="data-catalog-panel">
      <div className="catalog-card-grid">
        {visible.map((row) => (
          <button className={selected?.table_name === row.table_name ? 'active' : ''} key={row.table_name} onClick={() => onSelect(row)}>
            <DatabaseOutlined />
            <span><strong>{row.display_name || row.table_name}</strong><small>字段数 {row.fields?.length || row.runtime?.columns_count || 0}</small></span>
            <Tag color={row.runtime?.exists === false ? 'warning' : 'success'}>{row.runtime?.exists === false ? '未建表' : '正常'}</Tag>
          </button>
        ))}
      </div>
      {selected ? (
        <div className="catalog-detail">
          <div className="catalog-meta">
            <h3>{selected.table_name} <small>{selected.display_name}</small></h3>
            <dl>
              <dt>所属目录</dt><dd>{selected.business_domain || '--'}</dd>
              <dt>表类型</dt><dd>{selected.grain || '--'}</dd>
              <dt>时间字段</dt><dd>{selected.time_field || '--'}</dd>
              <dt>更新频率</dt><dd>{selected.refresh_frequency || '--'}</dd>
              <dt>来源系统</dt><dd>{selected.source_system || '--'}</dd>
              <dt>用途说明</dt><dd>{selected.description || '--'}</dd>
            </dl>
          </div>
          <Table
            size="small"
            rowKey="field_name"
            pagination={false}
            scroll={{ y: 175 }}
            dataSource={selected.fields || []}
            columns={[
              { title: '字段名', dataIndex: 'field_name' },
              { title: '业务名称', dataIndex: 'business_name' },
              { title: '类型', dataIndex: 'role' },
              { title: '说明', dataIndex: 'meaning' }
            ]}
          />
        </div>
      ) : null}
    </SectionCard>
  );
}

export function SourceStatusBar({ rows }: { rows: any[] }) {
  return (
    <div className="data-source-status">
      <strong>数据源状态</strong>
      {rows.slice(0, 6).map((row) => (
        <div key={row.table_name}>
          <span>{row.table_name}</span>
          <Tag color={row.status === 'ok' ? 'success' : 'warning'}>{row.status === 'ok' ? '正常' : '需关注'}</Tag>
          <small>{row.max_datetime ? `更新 ${String(row.max_datetime).slice(5, 16)}` : row.not_found_reason || '暂无更新时间'}</small>
        </div>
      ))}
    </div>
  );
}

export const dataTabs = [
  { key: 'data-quality', label: '数据质量 / 数据目录' },
  { key: 'data-catalog', label: '目录详情' }
];

export { PageTabs, DownloadOutlined, CheckCircleOutlined, ExclamationCircleOutlined };
