import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  CopyOutlined,
  DeleteOutlined,
  DownloadOutlined,
  EyeOutlined,
  FileDoneOutlined,
  FileExcelOutlined,
  FilePdfOutlined,
  FileTextOutlined,
  FullscreenOutlined,
  HourglassOutlined,
  InboxOutlined,
  PlusCircleOutlined,
  ReloadOutlined,
  SearchOutlined,
  SendOutlined,
  SyncOutlined
} from '@ant-design/icons';
import { Button, Empty, Input, Pagination, Select, Space, Table, Tag, Timeline, Tooltip, message } from 'antd';
import { useEffect, useMemo, useState } from 'react';
import { api } from '../../api';
import { AppChart } from '../../components/charts/AppChart';
import { SectionCard } from '../../components/cards/SectionCard';
import { PageHeader } from '../../components/common/PageHeader';
import { PageTabs } from '../../components/common/PageTabs';
import { DataSourceTag } from '../../components/common/States';
import { MetricGrid } from '../../components/layout/UnifiedPage';
import { useAuth } from '../../context/AuthContext';
import { getReportCenterData } from '../../services/reportApi';
import type { PageProps } from '../../types/ui';

const statusColor: Record<string, string> = {
  待审核: 'warning',
  审核中: 'processing',
  已通过: 'success',
  已发布: 'success',
  驳回: 'error',
  已归档: 'purple'
};

const metricIcons = [<FileTextOutlined />, <HourglassOutlined />, <CheckCircleOutlined />, <CloseCircleOutlined />];

function fmtTime(value: unknown, fallback = '--') {
  return value ? String(value).replace('T', ' ').slice(0, 19) : fallback;
}

function shortTime(value: unknown) {
  const text = fmtTime(value);
  return text === '--' ? '--' : text.slice(5, 16);
}

function mainMetrics(summary: any) {
  return [
    { title: '今日生成数', value: summary?.today_generated ?? 0, unit: '份', trendLabel: '同比 +12.5% ↑', status: 'success' as const },
    { title: '待审核', value: summary?.pending_review ?? 0, unit: '份', trendLabel: '同比 +9.3% ↑', status: 'warning' as const },
    { title: '已发布', value: summary?.published ?? 0, unit: '份', trendLabel: '同比 +18.7% ↑', status: 'success' as const },
    { title: '驳回数', value: summary?.rejected ?? 0, unit: '份', trendLabel: '同比 -20.0% ↓', status: 'danger' as const }
  ];
}

function reviewMetrics(summary: any) {
  return [
    { title: '待审核', value: summary?.pending_review ?? 0, unit: '份报告', trendLabel: '较昨日 +3 份', status: 'warning' as const },
    { title: '已通过', value: summary?.approved ?? summary?.published ?? 0, unit: '份报告', trendLabel: '较昨日 +8 份', status: 'success' as const },
    { title: '待发布', value: summary?.pending_publish ?? 0, unit: '份报告', trendLabel: '较昨日 +1 份', status: 'info' as const },
    { title: '已归档', value: summary?.archived ?? 0, unit: '份报告', trendLabel: '较昨日 +15 份', status: 'info' as const }
  ];
}

function buildPriceOption(rows: any[], review = false) {
  const data = rows.length
    ? rows
    : Array.from({ length: 24 }).map((_, index) => ({ time: `${String(index).padStart(2, '0')}:00`, value: 0, actual: 0 }));
  return {
    grid: { top: 36, right: 22, bottom: 28, left: 44 },
    tooltip: { trigger: 'axis' },
    legend: {
      top: 0,
      itemWidth: 16,
      itemHeight: 8,
      data: review ? ['本期', '上期', '同比'] : ['实时电价', '预测电价']
    },
    xAxis: { type: 'category', data: data.map((item) => item.time), axisTick: { show: false } },
    yAxis: { type: 'value', name: '元/MWh', splitLine: { lineStyle: { color: '#edf1f7' } } },
    series: review
      ? [
          { name: '本期', type: 'line', smooth: true, data: data.map((item) => item.value), color: '#0fb98a' },
          { name: '上期', type: 'line', smooth: true, data: data.map((item) => item.actual), color: '#2f80ed', lineStyle: { type: 'dashed' } },
          { name: '同比', type: 'line', smooth: true, data: data.map((item) => Number(item.value || 0) * 0.85), color: '#f59e0b' }
        ]
      : [
          { name: '实时电价', type: 'line', smooth: true, data: data.map((item) => item.actual), color: '#0fb98a' },
          { name: '预测电价', type: 'line', smooth: true, data: data.map((item) => item.value), color: '#2f80ed', lineStyle: { type: 'dashed' } }
        ]
  };
}

const reportTabs = [
  { key: 'report-daily', label: '报告列表与预览' },
  { key: 'report-review', label: '报告审核与发布' }
];

export function ReportCenterPage({ activeSubKey, onSubNavigate }: PageProps) {
  const { hasPermission } = useAuth();
  const isReviewPage = activeSubKey === 'report-review' || activeSubKey === 'report-publish';
  const activeTabKey = isReviewPage ? 'report-review' : 'report-daily';
  const [data, setData] = useState<any>({ reports: [], summary: {} });
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState('');
  const [keyword, setKeyword] = useState('');
  const [reviewComment, setReviewComment] = useState('');
  const permissions = {
    canDownload: hasPermission('report:download'),
    canGenerate: hasPermission('report:generate'),
    canReview: hasPermission('report:review')
  };

  async function loadData(nextKeyword = keyword) {
    setLoading(true);
    try {
      const payload = await getReportCenterData({ keyword: nextKeyword });
      setData(payload);
      const first = payload.reports?.[0] || payload.activeReport;
      setSelectedId((current) => current || first?.report_id || '');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData();
  }, []);

  const reports = data.reports || [];
  const activeReport = useMemo(
    () => reports.find((item: any) => item.report_id === selectedId) || data.activeReport || reports[0],
    [reports, selectedId, data.activeReport]
  );
  const metrics = isReviewPage ? reviewMetrics(data.summary) : mainMetrics(data.summary);

  async function generateReport() {
    const res = await api.generateReport();
    message.success(`报告生成任务已启动：${res.task_id || res.run_id || 'report_generate'}`);
    await loadData();
  }

  async function regenerateReport() {
    if (!activeReport?.report_id) return;
    const res = await api.regenerateReport(activeReport.report_id);
    message.success(`重新生成任务已启动：${res.task_id || res.run_id || activeReport.report_id}`);
    await loadData();
  }

  async function review(action: 'approve' | 'reject' | 'publish') {
    if (!activeReport?.report_id) return;
    if (action === 'reject' && !reviewComment.trim()) {
      message.warning('驳回报告需要填写审核意见');
      return;
    }
    const payload = { reviewer: 'admin', review_comment: reviewComment || (action === 'approve' ? '审核通过' : '发布归档') };
    if (action === 'approve') await api.approveReport(activeReport.report_id, payload);
    if (action === 'reject') await api.rejectReport(activeReport.report_id, payload);
    if (action === 'publish') await api.publishReport(activeReport.report_id, payload);
    message.success('报告状态已更新');
    setReviewComment('');
    await loadData();
  }

  async function downloadReport() {
    if (!activeReport?.report_id) return;
    const { blob, filename } = await api.reportDownload(activeReport.report_id);
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = filename || `${activeReport.report_id}.bin`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  function copyLink() {
    const text = `${window.location.origin}${window.location.pathname}#/report/report-daily?report_id=${activeReport?.report_id || ''}`;
    navigator.clipboard?.writeText(text);
    message.success('报告链接已复制');
  }

  return (
    <div className="report-workbench page-stack">
      <PageHeader
        className="report-unified-header"
        title={isReviewPage ? '报告审核与发布' : '报告中心'}
        subtitle={isReviewPage
          ? '从待审核到发布归档的全流程管理，确保报告质量与合规发布。'
          : '集中管理各类分析报告，支持查看、审核、发布与归档，保障数据合规与决策高效。'}
        navigation={<PageTabs items={reportTabs} activeKey={activeTabKey} onChange={onSubNavigate} />}
        filters={<ReportFilterBar
          review={isReviewPage}
          keyword={keyword}
          setKeyword={setKeyword}
          onSearch={() => loadData(keyword)}
          onGenerate={generateReport}
          canGenerate={permissions.canGenerate}
          source={data.dataSource}
        />}
      />
      <div className="report-metric-band">
        <MetricGrid items={metrics} icons={metricIcons} loading={loading} minColumnWidth={160} />
      </div>
      {isReviewPage ? (
        <ReviewPublishView
          reports={reports}
          total={data.total || reports.length}
          activeReport={activeReport}
          selectedId={selectedId}
          setSelectedId={setSelectedId}
          curve={data.previewCurve || []}
          previewMetrics={data.previewMetrics || []}
          reviewComment={reviewComment}
          setReviewComment={setReviewComment}
          onApprove={() => review('approve')}
          onReject={() => review('reject')}
          onPublish={() => review('publish')}
          onRegenerate={regenerateReport}
          onDownload={downloadReport}
          permissions={permissions}
        />
      ) : (
        <ReportPreviewView
          reports={reports}
          total={data.total || reports.length}
          activeReport={activeReport}
          selectedId={selectedId}
          setSelectedId={setSelectedId}
          curve={data.previewCurve || []}
          previewMetrics={data.previewMetrics || []}
          risks={data.risks || []}
          onDownload={downloadReport}
          onRegenerate={regenerateReport}
          onCopyLink={copyLink}
          permissions={permissions}
        />
      )}
    </div>
  );
}

function ReportFilterBar({ review, keyword, setKeyword, onSearch, onGenerate, canGenerate, source }: any) {
  return (
    <section className={`report-filter-bar ${review ? 'is-review' : 'is-list'}`}>
      <div className="report-filter-controls">
        <label>
          {review ? '报告批次' : '报告类型'}
          <Select value={review ? '2025-06-21 批次' : '全部'} options={[{ value: review ? '2025-06-21 批次' : '全部', label: review ? '2025-06-21 批次' : '全部' }]} />
        </label>
        <label>
          {review ? '报告版本' : '状态'}
          <Select value="全部" options={[{ value: '全部', label: '全部' }]} />
        </label>
        {review && (
          <label>
            审核人
            <Select value="全部审核人" options={[{ value: '全部审核人', label: '全部审核人' }]} />
          </label>
        )}
        <label>
          日期范围
          <Input value="2025-06-14 ~ 2025-06-21" readOnly />
        </label>
        {!review && (
          <Input.Search
            className="report-filter-search"
            allowClear
            prefix={<SearchOutlined />}
            value={keyword}
            onChange={(event) => setKeyword(event.target.value)}
            onSearch={onSearch}
            placeholder="搜索报告名称 / 报告 ID / 批次号"
          />
        )}
      </div>
      <div className="report-filter-lower">
        {review && (
          <Input.Search
            className="report-filter-search"
            allowClear
            prefix={<SearchOutlined />}
            value={keyword}
            onChange={(event) => setKeyword(event.target.value)}
            onSearch={onSearch}
            placeholder="搜索报告名称 / 版本号 / 批次号"
          />
        )}
        {source ? <span className="report-source-pill">数据源 <DataSourceTag source={source} /></span> : null}
        <div className="report-filter-actions">
          {review ? <Button onClick={() => setKeyword('')}>重置</Button> : <Button type="primary" icon={<PlusCircleOutlined />} disabled={!canGenerate} onClick={onGenerate}>生成报告</Button>}
          {!review && <Button icon={<DownloadOutlined />}>导出</Button>}
        </div>
      </div>
    </section>
  );
}

function ReportListCard({ title, reports, selectedId, setSelectedId, total }: any) {
  return (
    <SectionCard title={title} extra={<ReloadOutlined />} className="report-list-card">
      <div className="report-list-head">
        <span>报告名称 / 报告 ID</span>
        <span>生成时间</span>
        <span>类型</span>
        <span>状态</span>
      </div>
      <div className="report-list-scroll">
        {reports.length ? (
          reports.map((item: any) => (
            <button key={item.report_id} className={`report-list-item ${selectedId === item.report_id ? 'active' : ''}`} onClick={() => setSelectedId(item.report_id)}>
              <span>
                <FileTextOutlined />
                <strong>{item.title}</strong>
                <small>{item.report_id}</small>
              </span>
              <em>{shortTime(item.generated_at)}</em>
              <Tag>{item.typeText}</Tag>
              <Tag color={statusColor[item.statusText] || 'default'}>{item.statusText}</Tag>
            </button>
          ))
        ) : (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无报告数据" />
        )}
      </div>
      <div className="report-pagination">
        <span>共 {total} 条</span>
        <Pagination size="small" current={1} total={total} pageSize={10} showSizeChanger={false} />
      </div>
    </SectionCard>
  );
}

function ReportPreviewView({ reports, total, activeReport, selectedId, setSelectedId, curve, previewMetrics, risks, onDownload, onRegenerate, onCopyLink, permissions }: any) {
  return (
    <div className="report-main-grid">
      <ReportListCard title={`报告列表（共 ${total} 份）`} reports={reports} selectedId={selectedId} setSelectedId={setSelectedId} total={total} />
      <SectionCard title="报告预览" className="report-preview-card">
        <ReportBaseInfo report={activeReport} />
        <div className="report-mini-metrics">{previewMetrics.map((item: any) => <MiniMetric key={item.label} {...item} />)}</div>
        <div className="report-preview-split">
          <section>
            <h3>分时电价走势（元/MWh）</h3>
            <AppChart option={buildPriceOption(curve)} height={220} />
          </section>
          <section>
            <h3>风险时段提醒</h3>
            <Table
              size="small"
              rowKey="key"
              pagination={false}
              dataSource={risks}
              locale={{ emptyText: '接口未返回结构化风险时段' }}
              columns={[
                { title: '时段', dataIndex: 'period' },
                { title: '风险等级', dataIndex: 'level', render: (value) => <Tag color={String(value).includes('高') ? 'error' : 'warning'}>{value}</Tag> },
                { title: '风险类型', dataIndex: 'type' },
                { title: '影响程度', dataIndex: 'impact' },
                { title: '建议操作', dataIndex: 'action' }
              ]}
            />
          </section>
        </div>
        <div className="report-summary-block">
          <strong>摘要</strong>
          <p>{activeReport?.summaryText || '暂无报告摘要'}</p>
          <Button type="link">展开全部</Button>
        </div>
      </SectionCard>
      <div className="report-side-stack">
        <QuickActions onDownload={onDownload} onRegenerate={onRegenerate} onCopyLink={onCopyLink} permissions={permissions} />
        <PublishTimeline report={activeReport} />
      </div>
    </div>
  );
}

function ReviewPublishView({ reports, total, activeReport, selectedId, setSelectedId, curve, previewMetrics, reviewComment, setReviewComment, onApprove, onReject, onPublish, onRegenerate, onDownload, permissions }: any) {
  return (
    <div className="report-review-grid">
      <ReportListCard title="报告版本 / 待审核列表" reports={reports} selectedId={selectedId} setSelectedId={setSelectedId} total={total} />
      <SectionCard title="审核预览区" extra={<Space><Button icon={<FullscreenOutlined />}>全屏预览</Button><Button icon={<DownloadOutlined />} disabled={!permissions.canDownload} onClick={onDownload}>下载预览</Button></Space>} className="report-review-preview">
        <div className="report-review-title">
          <h3>{activeReport?.title || '--'}</h3>
          <Tag color="green">v2.3.1</Tag>
          <Tag color={statusColor[activeReport?.statusText] || 'warning'}>{activeReport?.statusText || '待审核'}</Tag>
        </div>
        <ReportBaseInfo report={activeReport} compact />
        <p className="report-review-summary">{activeReport?.summaryText || '暂无报告摘要'}</p>
        <div className="report-mini-metrics">{previewMetrics.map((item: any) => <MiniMetric key={item.label} {...item} />)}</div>
        <h3>电价趋势（元/MWh）</h3>
        <AppChart option={buildPriceOption(curve, true)} height={230} />
        <div className="report-version-grid">
          <div>
            <h3>版本信息</h3>
            <p><span>当前版本</span><strong>v2.3.1</strong></p>
            <p><span>上个版本</span><strong>v2.3.0</strong></p>
            <p><span>版本状态</span><strong>{activeReport?.statusText || '--'}</strong></p>
            <p><span>报告模板</span><strong>市场运行周报模板 v1.2</strong></p>
          </div>
          <div>
            <h3>变更说明</h3>
            <p>新增：增加分时电价对比图表</p>
            <p>优化：优化负荷预测模型参数</p>
            <p>修正：修正部分数据口径说明</p>
            <p>调整：调整峰谷价差计算方式</p>
          </div>
        </div>
      </SectionCard>
      <div className="report-review-side">
        <SectionCard title="审核操作区" className="report-review-action-card">
          <div className="report-review-tabs"><b>待审核</b><span>待发布</span></div>
          <label className="report-comment-label">审核意见 <i>*</i></label>
          <Input.TextArea rows={5} maxLength={500} showCount value={reviewComment} onChange={(event) => setReviewComment(event.target.value)} placeholder="请输入审核意见（选填）..." />
          <div className="report-review-actions">
            <Button type="primary" disabled={!permissions.canReview} onClick={onApprove}>通过</Button>
            <Button danger disabled={!permissions.canReview} onClick={onReject}>驳回</Button>
            <Button disabled={!permissions.canGenerate} onClick={onRegenerate}>重新生成</Button>
            <Button disabled={!permissions.canReview} onClick={onPublish}>发布归档</Button>
          </div>
        </SectionCard>
        <SectionCard title="发布归档流程" className="report-process-card"><ProcessSteps /></SectionCard>
        <div className="report-review-info-grid">
          <SmallInfoCard title="时间线" rows={['2025-06-21 09:45:21 系统生成', '2025-06-21 09:50:12 提交审核', '当前节点：初审']} />
          <SmallInfoCard title="审核记录" rows={['张三（初审）：审核中', '李四（复审）：待处理', '王五（终审）：待处理']} />
          <SmallInfoCard title="版本信息" rows={['当前版本：v2.3.1', '上个版本：v2.3.0', '文件格式：后端生成文件']} />
          <SmallInfoCard title="操作日志" rows={['系统生成报告', 'admin 提交审核', '查看更多']} />
        </div>
      </div>
    </div>
  );
}

function ReportBaseInfo({ report, compact }: any) {
  return (
    <div className={`report-base-info ${compact ? 'compact' : ''}`}>
      <p><span>报告名称</span><strong>{report?.title || '--'}</strong></p>
      <p><span>报告 ID</span><strong>{report?.report_id || '--'}</strong></p>
      <p><span>报告类型</span><strong>{report?.typeText || '--'}</strong></p>
      <p><span>生成时间</span><strong>{fmtTime(report?.generated_at)}</strong></p>
      <p><span>关联批次</span><strong>{report?.batch || report?.run_id || '--'}</strong></p>
      <p><span>数据时间</span><strong>{report?.data_window || '--'}</strong></p>
    </div>
  );
}

function MiniMetric({ label, value, unit, change }: any) {
  return (
    <div>
      <span>{label}</span>
      <strong>{value}</strong>
      <em>{unit}</em>
      <small className={String(change).startsWith('-') ? 'down' : ''}>同比 {change}</small>
    </div>
  );
}

function QuickActions({ onDownload, onRegenerate, onCopyLink, permissions }: any) {
  const disabledTip = '当前后端接口待接入';
  return (
    <SectionCard title="快捷操作" className="report-quick-card">
      <div className="report-action-grid">
        <Button icon={<FilePdfOutlined />} disabled={!permissions.canDownload} onClick={onDownload}>下载报告（PDF）</Button>
        <Tooltip title={disabledTip}><Button icon={<FileExcelOutlined />} disabled>下载报告（Excel）</Button></Tooltip>
        <Button icon={<EyeOutlined />}>查看详情</Button>
        <Tooltip title={disabledTip}><Button type="primary" icon={<SendOutlined />} disabled>提交审核</Button></Tooltip>
        <Button icon={<SyncOutlined />} disabled={!permissions.canGenerate} onClick={onRegenerate}>重新生成</Button>
        <Button icon={<CopyOutlined />} onClick={onCopyLink}>复制报告链接</Button>
        <Tooltip title={disabledTip}><Button icon={<InboxOutlined />} disabled>归档报告</Button></Tooltip>
        <Tooltip title={disabledTip}><Button danger icon={<DeleteOutlined />} disabled>删除报告</Button></Tooltip>
      </div>
    </SectionCard>
  );
}

function PublishTimeline({ report }: any) {
  return (
    <SectionCard title="发布记录" className="report-timeline-card">
      <Timeline
        items={[
          { color: 'green', children: <div><strong>系统生成</strong><p>{fmtTime(report?.generated_at)}</p><span>报告已由系统自动生成</span></div> },
          { color: 'orange', children: <div><strong>提交审核</strong><p>--</p><span>待写入审核记录</span></div> },
          { color: 'green', children: <div><strong>审核通过</strong><p>--</p><span>审核通过后展示</span></div> },
          { color: 'green', children: <div><strong>发布成功</strong><p>--</p><span>发布后展示</span></div> },
          { color: 'gray', children: <div><strong>归档</strong><p>--</p><span>尚未归档</span></div> }
        ]}
      />
    </SectionCard>
  );
}

function ProcessSteps() {
  const steps = ['系统生成', '提交审核', '审核中', '审核通过', '发布归档'];
  return (
    <div className="report-process-steps">
      {steps.map((step, index) => (
        <div key={step} className={index < 3 ? 'done' : ''}>
          <i>{index + 1}</i>
          <span>{step}</span>
          <small>{index < 3 ? '06-21 09:45' : '未完成'}</small>
        </div>
      ))}
    </div>
  );
}

function SmallInfoCard({ title, rows }: { title: string; rows: string[] }) {
  return <SectionCard title={title} className="report-small-info">{rows.map((row) => <p key={row}>{row}</p>)}</SectionCard>;
}
