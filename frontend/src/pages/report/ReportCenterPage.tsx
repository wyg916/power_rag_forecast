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
import { App, Button, Empty, Input, Pagination, Select, Space, Table, Tag, Timeline, Tooltip } from 'antd';
import { useEffect, useMemo, useRef, useState } from 'react';
import { api } from '../../api';
import { AppChart } from '../../components/charts/AppChart';
import { SectionCard } from '../../components/cards/SectionCard';
import { PageHeader } from '../../components/common/PageHeader';
import { PageTabs } from '../../components/common/PageTabs';
import { PageDataState } from '../../components/common/States';
import { MetricGrid } from '../../components/layout/UnifiedPage';
import { useAuth } from '../../context/AuthContext';
import { getReportCenterData, getReportFacts } from '../../services/reportApi';
import { resolvePageDataMeta } from '../../services/viewState';
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
    { title: '今日生成数', value: summary?.today_generated ?? '--', unit: '份', trendLabel: '当前事实统计，无同比基线', status: 'success' as const },
    { title: '待审核', value: summary?.pending_review ?? '--', unit: '份', trendLabel: '当前事实统计，无同比基线', status: 'warning' as const },
    { title: '已发布', value: summary?.published ?? '--', unit: '份', trendLabel: '当前事实统计，无同比基线', status: 'success' as const },
    { title: '驳回数', value: summary?.rejected ?? '--', unit: '份', trendLabel: '当前事实统计，无同比基线', status: 'danger' as const }
  ];
}

function reviewMetrics(summary: any) {
  return [
    { title: '待审核', value: summary?.pending_review ?? '--', unit: '份报告', trendLabel: '当前事实统计，无昨日基线', status: 'warning' as const },
    { title: '已通过/发布', value: summary?.approved ?? summary?.published ?? '--', unit: '份报告', trendLabel: '按持久化状态统计', status: 'success' as const },
    { title: '待发布', value: summary?.pending_publish ?? '--', unit: '份报告', trendLabel: '接口未提供则不可计算', status: 'info' as const },
    { title: '已归档', value: summary?.archived ?? '--', unit: '份报告', trendLabel: '接口未提供则不可计算', status: 'info' as const }
  ];
}

function buildPriceOption(rows: any[], review = false) {
  const data = rows;
  return {
    grid: { top: 36, right: 22, bottom: 28, left: 44 },
    tooltip: { trigger: 'axis' },
    legend: {
      top: 0,
      itemWidth: 16,
      itemHeight: 8,
      data: [review ? '报告绑定预测值' : '绑定预测值']
    },
    xAxis: { type: 'category', data: data.map((item) => item.time), axisTick: { show: false } },
    yAxis: { type: 'value', name: '元/kWh', splitLine: { lineStyle: { color: '#edf1f7' } } },
    series: [{ name: review ? '报告绑定预测值' : '绑定预测值', type: 'line', smooth: true, data: data.map((item) => item.value), color: '#2f80ed' }]
  };
}

const reportTabs = [
  { key: 'report-daily', label: '报告列表与预览' },
  { key: 'report-review', label: '报告审核与发布' }
];

export function ReportCenterPage({ activeSubKey, onSubNavigate }: PageProps) {
  const { message } = App.useApp();
  const { hasPermission, user } = useAuth();
  const isReviewPage = activeSubKey === 'report-review' || activeSubKey === 'report-publish';
  const activeTabKey = isReviewPage ? 'report-review' : 'report-daily';
  const [data, setData] = useState<any>({ reports: [], summary: {} });
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState('');
  const [keyword, setKeyword] = useState('');
  const [reportType, setReportType] = useState(activeSubKey === 'report-weekly' ? 'weekly' : activeSubKey === 'report-daily' ? 'daily' : '');
  const [reportStatus, setReportStatus] = useState('');
  const [reviewer, setReviewer] = useState('');
  const [reportPage, setReportPage] = useState(1);
  const [reviewComment, setReviewComment] = useState('');
  const permissions = {
    canDownload: hasPermission('report:download'),
    canGenerate: hasPermission('report:generate'),
    canReview: hasPermission('report:review')
  };

  async function loadData(nextKeyword = keyword, nextPage = reportPage, nextType = reportType, nextStatus = reportStatus) {
    setLoading(true);
    try {
      const payload = await getReportCenterData({
        keyword: nextKeyword,
        page: nextPage,
        page_size: 20,
        report_type: nextType,
        status: nextStatus
      });
      setData(payload);
      const first = payload.reports?.[0] || payload.activeReport;
      setSelectedId(first?.report_id || '');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    const nextType = activeSubKey === 'report-weekly' ? 'weekly' : activeSubKey === 'report-daily' ? 'daily' : '';
    setReportType(nextType);
    setReportPage(1);
    loadData(keyword, 1, nextType, reportStatus);
  }, [activeSubKey]);

  const reports = data.reports || [];
  const reviewerOptions = useMemo(() => Array.from(new Set(reports.map((item: any) => item.latestReview?.reviewer).filter(Boolean))) as string[], [reports]);
  const visibleReports = useMemo(
    () => reviewer ? reports.filter((item: any) => item.latestReview?.reviewer === reviewer) : reports,
    [reports, reviewer]
  );
  const activeReport = useMemo(
    () => data.activeReport?.report_id === selectedId
      ? data.activeReport
      : visibleReports.find((item: any) => item.report_id === selectedId) || visibleReports[0] || (!reviewer ? data.activeReport : null),
    [visibleReports, reviewer, selectedId, data.activeReport]
  );
  useEffect(() => {
    const selected = visibleReports.find((item: any) => item.report_id === selectedId);
    if (!selected) return;
    let cancelled = false;
    getReportFacts(selected).then((facts) => {
      if (cancelled) return;
      setData((current: any) => ({
        ...current,
        activeReport: facts.report,
        previewCurve: facts.previewCurve,
        previewMetrics: facts.previewMetrics,
        risks: facts.risks,
        reviews: facts.reviews,
        generatedAt: facts.report?.generated_at,
        validFrom: facts.report?.validFrom,
        validTo: facts.report?.validTo,
        runId: facts.report?.run_id,
        isStale: Boolean(facts.report?.isStale),
        staleReason: facts.report?.staleReason || ''
      }));
    }).catch((error) => {
      if (!cancelled) setData((current: any) => ({ ...current, partialErrors: [...(current.partialErrors || []), String(error)] }));
    });
    return () => { cancelled = true; };
  }, [visibleReports, selectedId]);
  const metrics = isReviewPage ? reviewMetrics(data.summary) : mainMetrics(data.summary);
  const viewMeta = useMemo(() => resolvePageDataMeta({
    loading,
    hasData: Boolean(activeReport),
    empty: !loading && !activeReport,
    partialErrors: data.partialErrors,
    source: data.dataSource,
    generatedAt: data.generatedAt || activeReport?.generated_at,
    runId: data.runId || activeReport?.run_id,
    modelVersion: activeReport?.modelVersion,
    featureVersion: activeReport?.featureVersion,
    isStale: Boolean(data.isStale ?? activeReport?.isStale),
    staleReason: data.staleReason || activeReport?.staleReason,
    queryScope: isReviewPage ? '报告审核与发布' : '报告列表与预览'
  }), [activeReport, data, isReviewPage, loading]);
  const showContent = viewMeta.state === 'success' || viewMeta.state === 'stale';

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
    if (!user?.username) {
      message.error('当前登录身份不可用，无法写入可追溯审核记录');
      return;
    }
    const payload = { reviewer: user.username, review_comment: reviewComment || (action === 'approve' ? '审核通过' : '发布归档') };
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

  function changeFilters(nextType: string, nextStatus: string) {
    setReportType(nextType);
    setReportStatus(nextStatus);
    setReportPage(1);
    loadData(keyword, 1, nextType, nextStatus);
  }

  function changePage(page: number) {
    setReportPage(page);
    loadData(keyword, page, reportType, reportStatus);
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
          onSearch={() => { setReportPage(1); loadData(keyword, 1); }}
          onGenerate={generateReport}
          onDownload={downloadReport}
          canGenerate={permissions.canGenerate}
          source={data.dataSource}
          windowText={activeReport?.data_window}
          reportType={reportType}
          reportStatus={reportStatus}
          reviewer={reviewer}
          reviewerOptions={reviewerOptions}
          onReportTypeChange={(value: string) => changeFilters(value, reportStatus)}
          onReportStatusChange={(value: string) => changeFilters(reportType, value)}
          onReviewerChange={setReviewer}
          onReset={() => {
            setKeyword('');
            setReviewer('');
            changeFilters('', '');
          }}
        />}
      />
      <PageDataState meta={viewMeta} onRetry={() => loadData(keyword)} />
      {showContent ? <div className="report-metric-band">
        <MetricGrid items={metrics} icons={metricIcons} loading={loading} minColumnWidth={160} />
      </div> : null}
      {showContent && isReviewPage ? (
        <ReviewPublishView
          reports={visibleReports}
          total={data.total || reports.length}
          page={reportPage}
          onPageChange={changePage}
          onReload={() => loadData(keyword)}
          activeReport={activeReport}
          selectedId={selectedId}
          setSelectedId={setSelectedId}
          curve={data.previewCurve || []}
          previewMetrics={data.previewMetrics || []}
          reviews={data.reviews || []}
          reviewComment={reviewComment}
          setReviewComment={setReviewComment}
          onApprove={() => review('approve')}
          onReject={() => review('reject')}
          onPublish={() => review('publish')}
          onRegenerate={regenerateReport}
          onDownload={downloadReport}
          permissions={permissions}
          onFullscreenError={() => message.error('当前浏览器未允许全屏显示')}
        />
      ) : showContent ? (
        <ReportPreviewView
          reports={visibleReports}
          total={data.total || reports.length}
          page={reportPage}
          onPageChange={changePage}
          onReload={() => loadData(keyword)}
          activeReport={activeReport}
          selectedId={selectedId}
          setSelectedId={setSelectedId}
          curve={data.previewCurve || []}
          previewMetrics={data.previewMetrics || []}
          risks={data.risks || []}
          onDownload={downloadReport}
          onRegenerate={regenerateReport}
          onCopyLink={copyLink}
          onReview={() => onSubNavigate?.('report-review')}
          permissions={permissions}
        />
      ) : null}
    </div>
  );
}

function ReportFilterBar({ review, keyword, setKeyword, onSearch, onGenerate, onDownload, canGenerate, source, windowText, reportType, reportStatus, reviewer, reviewerOptions, onReportTypeChange, onReportStatusChange, onReviewerChange, onReset }: any) {
  return (
    <section className={`report-filter-bar ${review ? 'is-review' : 'is-list'}`}>
      <div className="report-filter-controls">
        <label>
          {review ? '报告批次' : '报告类型'}
          <Select
            value={reportType}
            onChange={onReportTypeChange}
            options={[
              { value: '', label: '全部' },
              { value: 'daily', label: '日报' },
              { value: 'weekly', label: '周报' },
              { value: 'operation_decision', label: '运营决策报告' }
            ]}
          />
        </label>
        <label>
          {review ? '报告版本' : '状态'}
          <Select
            value={reportStatus}
            onChange={onReportStatusChange}
            options={[
              { value: '', label: '全部' },
              { value: 'ready', label: '待审核' },
              { value: 'approved', label: '已通过' },
              { value: 'rejected', label: '驳回' },
              { value: 'published', label: '已发布' },
              { value: 'archived', label: '已归档' }
            ]}
          />
        </label>
        {review && (
          <label>
            审核人
            <Select
              value={reviewer}
              onChange={onReviewerChange}
              options={[{ value: '', label: '全部审核人' }, ...reviewerOptions.map((value: string) => ({ value, label: value }))]}
            />
          </label>
        )}
        <label>
          日期范围
          <Input value={windowText && windowText !== '--' ? windowText : '当前报告未提供适用窗口'} readOnly />
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
        {source ? <span className="report-source-pill">业务批次已加载</span> : null}
        <div className="report-filter-actions">
          {review ? <Button onClick={onReset}>重置</Button> : <Button type="primary" icon={<PlusCircleOutlined />} disabled={!canGenerate} onClick={onGenerate}>生成报告</Button>}
          {!review && <Button icon={<DownloadOutlined />} disabled={!source} onClick={onDownload}>导出</Button>}
        </div>
      </div>
    </section>
  );
}

function ReportListCard({ title, reports, selectedId, setSelectedId, total, page, onPageChange, onReload }: any) {
  return (
    <SectionCard title={title} extra={<Button type="text" size="small" aria-label="刷新报告列表" title="刷新报告列表" icon={<ReloadOutlined />} onClick={onReload} />} className="report-list-card">
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
        <Pagination size="small" current={page} total={total} pageSize={20} showSizeChanger={false} onChange={onPageChange} />
      </div>
    </SectionCard>
  );
}

function ReportPreviewView({ reports, total, page, onPageChange, onReload, activeReport, selectedId, setSelectedId, curve, previewMetrics, risks, onDownload, onRegenerate, onCopyLink, onReview, permissions }: any) {
  const [summaryExpanded, setSummaryExpanded] = useState(false);
  return (
    <div className="report-main-grid">
      <ReportListCard title={`报告列表（共 ${total} 份）`} reports={reports} selectedId={selectedId} setSelectedId={setSelectedId} total={total} page={page} onPageChange={onPageChange} onReload={onReload} />
      <SectionCard title="报告预览" className="report-preview-card">
        <ReportBaseInfo report={activeReport} />
        <div className="report-mini-metrics">{previewMetrics.map((item: any) => <MiniMetric key={item.label} {...item} />)}</div>
        <div className="report-preview-split">
          <section>
            <h3>报告绑定预测曲线（元/kWh）</h3>
            {curve.length ? <AppChart option={buildPriceOption(curve)} height={220} /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="该报告未绑定可用预测曲线" />}
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
          <p className={summaryExpanded ? 'is-expanded' : ''}>{activeReport?.summaryText || '暂无报告摘要'}</p>
          <Button type="link" onClick={() => setSummaryExpanded((value) => !value)}>{summaryExpanded ? '收起摘要' : '展开全部'}</Button>
        </div>
      </SectionCard>
      <div className="report-side-stack">
        <QuickActions onDownload={onDownload} onRegenerate={onRegenerate} onCopyLink={onCopyLink} onReview={onReview} permissions={permissions} />
        <PublishTimeline report={activeReport} />
      </div>
    </div>
  );
}

function ReviewPublishView({ reports, total, page, onPageChange, onReload, activeReport, selectedId, setSelectedId, curve, previewMetrics, reviews, reviewComment, setReviewComment, onApprove, onReject, onPublish, onRegenerate, onDownload, permissions, onFullscreenError }: any) {
  const previewRef = useRef<HTMLElement | null>(null);
  return (
    <div className="report-review-grid">
      <ReportListCard title="报告版本 / 待审核列表" reports={reports} selectedId={selectedId} setSelectedId={setSelectedId} total={total} page={page} onPageChange={onPageChange} onReload={onReload} />
      <section ref={previewRef}>
      <SectionCard title="审核预览区" extra={<Space><Button icon={<FullscreenOutlined />} onClick={() => previewRef.current?.requestFullscreen?.().catch(onFullscreenError)}>全屏预览</Button><Button icon={<DownloadOutlined />} disabled={!permissions.canDownload} onClick={onDownload}>下载预览</Button></Space>} className="report-review-preview">
        <div className="report-review-title">
          <h3>{activeReport?.title || '--'}</h3>
          <Tag color="blue">{activeReport?.reportSchemaVersion || '报告版本未提供'}</Tag>
          <Tag color={statusColor[activeReport?.statusText] || 'warning'}>{activeReport?.statusText || '待审核'}</Tag>
          {activeReport?.isStale ? <Tag color="warning">历史窗口已结束</Tag> : null}
        </div>
        <ReportBaseInfo report={activeReport} compact />
        <p className="report-review-summary">{activeReport?.summaryText || '暂无报告摘要'}</p>
        <div className="report-mini-metrics">{previewMetrics.map((item: any) => <MiniMetric key={item.label} {...item} />)}</div>
        <h3>报告绑定预测曲线（元/kWh）</h3>
        {curve.length ? <AppChart option={buildPriceOption(curve, true)} height={230} /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="该报告未绑定可用预测曲线" />}
        <div className="report-version-grid">
          <div>
            <h3>版本信息</h3>
            <p><span>报告契约版本</span><strong>{activeReport?.reportSchemaVersion || '--'}</strong></p>
            <p><span>数据版本</span><strong title={activeReport?.dataVersion}>{activeReport?.dataVersion ? `${activeReport.dataVersion.slice(0, 16)}…` : '--'}</strong></p>
            <p><span>版本状态</span><strong>{activeReport?.statusText || '--'}</strong></p>
            <p><span>模型版本</span><strong>{activeReport?.modelVersion || '--'}</strong></p>
          </div>
          <div>
            <h3>事实边界</h3>
            <p>报告内容与业务批次保持一致。</p>
            <p>当前无上一版本或同比基线，不生成对比结论。</p>
            <p>{activeReport?.isStale ? '适用窗口已结束，仅用于审计与复盘。' : '适用窗口内仍须核对最新市场事实。'}</p>
          </div>
        </div>
      </SectionCard>
      </section>
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
        <SectionCard title="发布归档流程" className="report-process-card"><ProcessSteps report={activeReport} reviews={reviews} /></SectionCard>
        <div className="report-review-info-grid">
          <SmallInfoCard title="时间线" rows={[`${fmtTime(activeReport?.generated_at)} 系统生成`, `当前状态：${activeReport?.statusText || '--'}`]} />
          <SmallInfoCard title="审核记录" rows={(reviews || []).length ? reviews.map((item: any) => `${item.reviewer || '未知审核人'}：${item.status || item.action || '--'} · ${fmtTime(item.updated_at || item.created_at)}`) : ['暂无持久化审核记录']} />
          <SmallInfoCard title="版本信息" rows={[`报告契约：${activeReport?.reportSchemaVersion || '--'}`, `数据版本：${activeReport?.dataVersion ? `${activeReport.dataVersion.slice(0, 16)}…` : '--'}`]} />
          <SmallInfoCard title="追溯信息" rows={[`run_id：${activeReport?.run_id || '--'}`, `适用窗口：${activeReport?.data_window || '--'}`]} />
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
      <p><span>模型 / 特征</span><strong>{report?.modelVersion || '--'} / {report?.featureVersion || '--'}</strong></p>
      <p><span>业务状态</span><strong>{report?.isStale ? '历史窗口已结束' : report?.validFrom && report?.validTo ? '报告窗口有效' : '有效期未提供，不判定为当前'}</strong></p>
    </div>
  );
}

function MiniMetric({ label, value, unit }: any) {
  return (
    <div>
      <span>{label}</span>
      <strong>{value}</strong>
      <em>{unit}</em>
      <small>当前报告周期 · 无对比基线</small>
    </div>
  );
}

function QuickActions({ onDownload, onRegenerate, onCopyLink, onReview, permissions }: any) {
  const disabledTip = '当前业务流程不支持此操作';
  return (
    <SectionCard title="快捷操作" className="report-quick-card">
      <div className="report-action-grid">
        <Button icon={<FilePdfOutlined />} disabled={!permissions.canDownload} onClick={onDownload}>下载报告（PDF）</Button>
        <Tooltip title={disabledTip}><Button icon={<FileExcelOutlined />} disabled>下载报告（Excel）</Button></Tooltip>
        <Button icon={<EyeOutlined />} onClick={() => document.querySelector('.report-preview-card')?.scrollIntoView({ behavior: 'smooth', block: 'start' })}>查看详情</Button>
        <Button type="primary" icon={<SendOutlined />} onClick={onReview}>进入审核</Button>
        <Button icon={<SyncOutlined />} disabled={!permissions.canGenerate} onClick={onRegenerate}>重新生成</Button>
        <Button icon={<CopyOutlined />} onClick={onCopyLink}>复制报告链接</Button>
        <Tooltip title={disabledTip}><Button icon={<InboxOutlined />} disabled>归档报告</Button></Tooltip>
        <Tooltip title={disabledTip}><Button danger icon={<DeleteOutlined />} disabled>删除报告</Button></Tooltip>
      </div>
    </SectionCard>
  );
}

function PublishTimeline({ report }: any) {
  const review = report?.latestReview || {};
  const reviewed = Boolean(review?.updated_at || review?.created_at);
  const published = report?.statusText === '已发布';
  const archived = report?.statusText === '已归档';
  return (
    <SectionCard title="发布记录" className="report-timeline-card">
      <Timeline
        items={[
          { color: 'green', children: <div><strong>系统生成</strong><p>{fmtTime(report?.generated_at)}</p><span>报告已由系统自动生成</span></div> },
          { color: reviewed ? 'orange' : 'gray', children: <div><strong>审核记录</strong><p>{reviewed ? fmtTime(review.updated_at || review.created_at) : '--'}</p><span>{reviewed ? `${review.reviewer || '审核人未提供'} · ${review.review_status || '--'}` : '暂无持久化审核记录'}</span></div> },
          { color: published ? 'green' : 'gray', children: <div><strong>发布</strong><p>{published ? fmtTime(review.updated_at || review.created_at) : '--'}</p><span>{published ? '报告状态为已发布' : '尚未发布'}</span></div> },
          { color: archived ? 'green' : 'gray', children: <div><strong>归档</strong><p>{archived ? fmtTime(review.updated_at || review.created_at) : '--'}</p><span>{archived ? '报告状态为已归档' : '尚未归档'}</span></div> }
        ]}
      />
    </SectionCard>
  );
}

function ProcessSteps({ report, reviews = [] }: { report: any; reviews: any[] }) {
  const status = String(report?.status || '').toLowerCase();
  const reviewTime = reviews[0]?.updated_at || reviews[0]?.created_at;
  const steps = [
    { label: '系统生成', done: Boolean(report?.generated_at), time: report?.generated_at },
    { label: '形成审核记录', done: reviews.length > 0, time: reviewTime },
    { label: '审核完成', done: ['approved', 'rejected', 'published', 'archived'].includes(status), time: reviewTime },
    { label: '发布', done: ['published', 'archived'].includes(status), time: reviewTime },
    { label: '归档', done: status === 'archived', time: reviewTime }
  ];
  return (
    <div className="report-process-steps">
      {steps.map((step, index) => (
        <div key={step.label} className={step.done ? 'done' : ''}>
          <i>{index + 1}</i>
          <span>{step.label}</span>
          <small>{step.done ? shortTime(step.time) : '未完成'}</small>
        </div>
      ))}
    </div>
  );
}

function SmallInfoCard({ title, rows }: { title: string; rows: string[] }) {
  return <SectionCard title={title} className="report-small-info">{rows.map((row) => <p key={row}>{row}</p>)}</SectionCard>;
}
