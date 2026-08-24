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
import { PageDataState } from '../../components/common/States';
import { MetricGrid } from '../../components/layout/UnifiedPage';
import { useAuth } from '../../context/AuthContext';
import { getReportCenterData, getReportFacts } from '../../services/reportApi';
import { formatReportValueLines, pickReportScalar } from '../../services/reportValue';
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

function compactRiskPeriod(value: unknown) {
  const text = pickReportScalar(value, ['period', 'time_range', 'time', 'start', 'value']);
  return text.includes('T') ? text.slice(11, 16) : text;
}

function compactRiskLevel(value: unknown) {
  const text = pickReportScalar(value, ['level', 'risk_level', 'priority', 'value', 'label']);
  const normalized = text.toLowerCase();
  if (text.includes('高') || normalized === 'high') return '高';
  if (text.includes('中') || normalized === 'medium') return '中';
  if (text.includes('低') || normalized === 'low') return '低';
  if (normalized === 'guardrail') return '边界';
  return text;
}

function RiskCell({ value }: { value: unknown }) {
  const lines = formatReportValueLines(value);
  const text = lines.join('；');
  return (
    <Tooltip title={text}>
      <span className="report-risk-cell">{lines.map((line, index) => <span key={`${index}-${line}`}>{line}</span>)}</span>
    </Tooltip>
  );
}

function mainMetrics(summary: any) {
  return [
    { title: '今日生成数', value: summary?.today_generated ?? '--', unit: '份', note: '当前筛选范围', status: 'success' as const },
    { title: '待审核', value: summary?.pending_review ?? '--', unit: '份', note: '等待审核处理', status: 'warning' as const },
    { title: '已发布', value: summary?.published ?? '--', unit: '份', note: '已完成发布', status: 'success' as const },
    { title: '驳回数', value: summary?.rejected ?? '--', unit: '份', note: '需要重新处理', status: 'danger' as const }
  ];
}

function reviewMetrics(summary: any) {
  return [
    { title: '待审核', value: summary?.pending_review ?? '--', unit: '份', note: '等待审核处理', status: 'warning' as const },
    { title: '已通过 / 发布', value: summary?.approved ?? summary?.published ?? '--', unit: '份', note: '已完成审核', status: 'success' as const },
    { title: '待发布', value: summary?.pending_publish ?? '--', unit: '份', note: '等待发布处理', status: 'info' as const },
    { title: '已归档', value: summary?.archived ?? '--', unit: '份', note: '已完成归档', status: 'info' as const }
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
    yAxis: { type: 'value', name: '元/MWh', splitLine: { lineStyle: { color: '#edf1f7' } } },
    series: [{ name: review ? '报告绑定预测值' : '绑定预测值', type: 'line', smooth: true, data: data.map((item) => item.value), color: '#2f80ed' }]
  };
}

export function ReportCenterPage({ activeSubKey, onSubNavigate }: PageProps) {
  const { message } = App.useApp();
  const { canPerformAction, user } = useAuth();
  const isReviewPage = activeSubKey === 'report-review' || activeSubKey === 'report-publish';
  const [data, setData] = useState<any>({ reports: [], summary: {} });
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState('');
  const [keyword, setKeyword] = useState('');
  const [reportType, setReportType] = useState(activeSubKey === 'report-weekly' ? 'weekly' : '');
  const [reportStatus, setReportStatus] = useState('');
  const [reviewer, setReviewer] = useState('');
  const [reportPage, setReportPage] = useState(1);
  const [reviewComment, setReviewComment] = useState('');
  const permissions = {
    canDownload: canPerformAction('report:download'),
    canGenerate: canPerformAction('report.generate'),
    canReview: canPerformAction('report:review')
  };

  async function loadData(nextKeyword = keyword, nextPage = reportPage, nextType = reportType, nextStatus = reportStatus) {
    setLoading(true);
    setData((current: any) => ({
      ...current,
      reports: [],
      total: 0,
      activeReport: null,
      previewCurve: [],
      previewMetrics: [],
      risks: [],
      reviews: []
    }));
    setSelectedId('');
    try {
      const payload = await getReportCenterData({
        keyword: nextKeyword,
        page: nextPage,
        page_size: 20,
        report_type: nextType,
        status: nextStatus
      }, { canReview: permissions.canReview });
      setData(payload);
      const first = payload.reports?.[0] || payload.activeReport;
      setSelectedId(first?.report_id || '');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    const nextType = activeSubKey === 'report-weekly' ? 'weekly' : '';
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
    getReportFacts(selected, { canReview: permissions.canReview }).then((facts) => {
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
  const showBlockingState = ['loading', 'error', 'unauthorized', 'forbidden'].includes(viewMeta.state);
  const showEmptyState = viewMeta.state === 'empty';

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

  function changeFilters(nextType: string, nextStatus: string, nextKeyword = keyword) {
    setReportType(nextType);
    setReportStatus(nextStatus);
    setReportPage(1);
    loadData(nextKeyword, 1, nextType, nextStatus);
  }

  function changePage(page: number) {
    setReportPage(page);
    loadData(keyword, page, reportType, reportStatus);
  }

  async function copyLink() {
    if (!activeReport?.report_id) {
      message.warning('当前没有可复制链接的报告');
      return;
    }
    const text = `${window.location.origin}${window.location.pathname}#/report/report-daily?report_id=${activeReport?.report_id || ''}`;
    if (!navigator.clipboard?.writeText) {
      message.error('当前浏览器不支持复制到剪贴板');
      return;
    }
    try {
      await navigator.clipboard.writeText(text);
      message.success('报告链接已复制');
    } catch {
      message.error('复制失败，请检查浏览器剪贴板权限');
    }
  }

  return (
    <div className="report-workbench page-stack">
      <header className="report-page-toolbar">
        <h1>{isReviewPage ? '报告审核与发布' : '报告中心'}</h1>
        <ReportFilterBar
          review={isReviewPage}
          keyword={keyword}
          setKeyword={setKeyword}
          onSearch={() => { setReportPage(1); loadData(keyword, 1); }}
          onGenerate={generateReport}
          onDownload={downloadReport}
          canGenerate={permissions.canGenerate}
          canDownload={permissions.canDownload}
          hasReport={Boolean(activeReport?.report_id)}
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
            changeFilters('', '', '');
          }}
        />
      </header>
      {showBlockingState ? <PageDataState meta={viewMeta} onRetry={() => loadData(keyword)} /> : null}
      {showEmptyState ? (
        <SectionCard title={reportType === 'weekly' ? '周报列表与预览' : '报告列表与预览'} className="report-empty-card">
          <Empty description={reportType === 'weekly' ? '当前筛选下暂无周报' : '当前筛选下暂无报告'} />
          <Button onClick={() => loadData(keyword)}>刷新查询</Button>
        </SectionCard>
      ) : null}
      {viewMeta.state === 'stale' && viewMeta.errorMessage ? (
        <div className="report-refresh-warning" role="status">
          <span>部分报告信息更新失败，当前仍显示最近一次成功加载的内容。</span>
          <Button size="small" onClick={() => loadData(keyword)}>重试</Button>
        </div>
      ) : null}
      {showContent && isReviewPage ? (
        <ReviewPublishView
          metrics={metrics}
          loading={loading}
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
          metrics={metrics}
          loading={loading}
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

function ReportFilterBar({ review, keyword, setKeyword, onSearch, onGenerate, onDownload, canGenerate, canDownload, hasReport, reportType, reportStatus, reviewer, reviewerOptions, onReportTypeChange, onReportStatusChange, onReviewerChange, onReset }: any) {
  return (
    <section className={`report-filter-bar ${review ? 'is-review' : 'is-list'}`}>
      <div className="report-filter-controls">
        <label>
          报告类型
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
          状态
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
        <div className="report-filter-actions">
          {review ? <Button onClick={onReset}>重置</Button> : canGenerate ? <Button type="primary" icon={<PlusCircleOutlined />} onClick={onGenerate}>生成报告</Button> : null}
          {!review && canDownload ? <Button icon={<DownloadOutlined />} disabled={!hasReport} onClick={onDownload}>导出</Button> : null}
        </div>
      </div>
    </section>
  );
}

function ReportListCard({ title, reports, selectedId, setSelectedId, total, page, onPageChange, onReload }: any) {
  return (
    <SectionCard title={title} extra={<Button type="text" size="small" aria-label="刷新报告列表" title="刷新报告列表" icon={<ReloadOutlined />} onClick={onReload} />} className="report-list-card" bodyClassName="report-list-body">
      <div className="report-list-head">
        <span>报告名称 / 报告 ID</span>
        <span>报告类型</span>
        <span>状态</span>
      </div>
      <div className="report-list-scroll">
        {reports.length ? (
          reports.map((item: any) => (
            <button key={item.report_id} className={`report-list-item ${selectedId === item.report_id ? 'active' : ''}`} onClick={() => setSelectedId(item.report_id)}>
              <span>
                <FileTextOutlined />
                <strong title={item.title}>{item.title}</strong>
                <small title={item.report_id}>{item.report_id}</small>
              </span>
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

function ReportMetricPair({ items, start, loading }: { items: any[]; start: number; loading: boolean }) {
  return <div className="report-metric-pair"><MetricGrid items={items.slice(start, start + 2)} icons={metricIcons.slice(start, start + 2)} loading={loading} minColumnWidth={120} /></div>;
}

function ReportPreviewView({ metrics, loading, reports, total, page, onPageChange, onReload, activeReport, selectedId, setSelectedId, curve, previewMetrics, risks, onDownload, onRegenerate, onCopyLink, onReview, permissions }: any) {
  const [summaryExpanded, setSummaryExpanded] = useState(false);
  return (
    <div className="report-main-grid report-workspace-grid">
      <div className="report-workspace-left">
        <ReportMetricPair items={metrics} start={0} loading={loading} />
        <ReportListCard title={`报告列表（共 ${total} 份）`} reports={reports} selectedId={selectedId} setSelectedId={setSelectedId} total={total} page={page} onPageChange={onPageChange} onReload={onReload} />
      </div>
      <SectionCard title="报告预览" className="report-preview-card" bodyClassName="report-preview-body">
        <ReportBaseInfo report={activeReport} />
        <div className="report-mini-metrics">{previewMetrics.map((item: any) => <MiniMetric key={item.label} {...item} />)}</div>
        <div className="report-preview-split">
          <section>
            <h3>报告绑定预测曲线（元/MWh）</h3>
            {curve.length ? <AppChart option={buildPriceOption(curve)} height={220} /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="该报告未绑定可用预测曲线" />}
          </section>
          <section>
            <h3>风险时段提醒</h3>
            <Table
              size="small"
              rowKey="key"
              pagination={false}
              tableLayout="fixed"
              dataSource={risks}
              locale={{ emptyText: '接口未返回结构化风险时段' }}
              columns={[
                { title: '时段', dataIndex: 'period', width: 58, render: (value) => <RiskCell value={compactRiskPeriod(value)} /> },
                {
                  title: '等级',
                  dataIndex: 'level',
                  width: 62,
                  render: (value) => {
                    const level = compactRiskLevel(value);
                    return <Tooltip title={level}><Tag color={level === '高' ? 'error' : level === '中' ? 'warning' : 'success'}>{level}</Tag></Tooltip>;
                  }
                },
                { title: '风险类型', dataIndex: 'type', width: 92, render: (value) => <RiskCell value={value} /> },
                { title: '影响', dataIndex: 'impact', width: 58, render: (value) => <RiskCell value={compactRiskLevel(value)} /> },
                { title: '建议动作', dataIndex: 'action', render: (value) => <RiskCell value={value} /> }
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
      <div className="report-workspace-right report-side-stack">
        <ReportMetricPair items={metrics} start={2} loading={loading} />
        <QuickActions onDownload={onDownload} onRegenerate={onRegenerate} onCopyLink={onCopyLink} onReview={onReview} permissions={permissions} />
        <PublishTimeline report={activeReport} />
      </div>
    </div>
  );
}

function ReviewPublishView({ metrics, loading, reports, total, page, onPageChange, onReload, activeReport, selectedId, setSelectedId, curve, previewMetrics, reviews, reviewComment, setReviewComment, onApprove, onReject, onPublish, onRegenerate, onDownload, permissions, onFullscreenError }: any) {
  const previewRef = useRef<HTMLElement | null>(null);
  return (
    <div className="report-review-grid report-workspace-grid">
      <div className="report-workspace-left">
        <ReportMetricPair items={metrics} start={0} loading={loading} />
        <ReportListCard title="报告版本 / 待审核列表" reports={reports} selectedId={selectedId} setSelectedId={setSelectedId} total={total} page={page} onPageChange={onPageChange} onReload={onReload} />
      </div>
      <section ref={previewRef}>
      <SectionCard title="审核预览区" extra={<Space><Button icon={<FullscreenOutlined />} onClick={() => previewRef.current?.requestFullscreen?.().catch(onFullscreenError)}>全屏预览</Button>{permissions.canDownload ? <Button icon={<DownloadOutlined />} onClick={onDownload}>下载预览</Button> : null}</Space>} className="report-review-preview" bodyClassName="report-review-body">
        <div className="report-review-title">
          <h3>{activeReport?.title || '--'}</h3>
          <Tag color="blue">{activeReport?.reportSchemaVersion || '报告版本未提供'}</Tag>
          <Tag color={statusColor[activeReport?.statusText] || 'warning'}>{activeReport?.statusText || '待审核'}</Tag>
        </div>
        <ReportBaseInfo report={activeReport} compact />
        <p className="report-review-summary">{activeReport?.summaryText || '暂无报告摘要'}</p>
        <div className="report-mini-metrics">{previewMetrics.map((item: any) => <MiniMetric key={item.label} {...item} />)}</div>
        <h3>报告绑定预测曲线（元/MWh）</h3>
        {curve.length ? <AppChart option={buildPriceOption(curve, true)} height={230} /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="该报告未绑定可用预测曲线" />}
        <div className="report-version-grid">
          <div>
            <h3>版本信息</h3>
            <p><span>报告契约版本</span><strong>{activeReport?.reportSchemaVersion || '--'}</strong></p>
            <p><span>版本状态</span><strong>{activeReport?.statusText || '--'}</strong></p>
            <p><span>报告类型</span><strong>{activeReport?.typeText || '--'}</strong></p>
          </div>
          <div>
            <h3>版本说明</h3>
            <p>报告内容与业务批次保持一致。</p>
            <p>当前无上一版本或同比基线，不生成对比结论。</p>
            <p>发布前仍须完成审核并核对业务结论。</p>
          </div>
        </div>
      </SectionCard>
      </section>
      <div className="report-review-side report-workspace-right">
        <ReportMetricPair items={metrics} start={2} loading={loading} />
        <SectionCard title="审核操作区" className="report-review-action-card">
          <div className="report-review-tabs"><b>待审核</b><span>待发布</span></div>
          <label className="report-comment-label">审核意见 <i>*</i></label>
          <Input.TextArea rows={5} maxLength={500} showCount value={reviewComment} onChange={(event) => setReviewComment(event.target.value)} placeholder="请输入审核意见（选填）..." />
          <div className="report-review-actions">
            {permissions.canReview ? <Button type="primary" onClick={onApprove}>通过</Button> : null}
            {permissions.canReview ? <Button danger onClick={onReject}>驳回</Button> : null}
            {permissions.canGenerate ? <Button onClick={onRegenerate}>重新生成</Button> : null}
            {permissions.canReview ? <Button onClick={onPublish}>发布报告</Button> : null}
          </div>
        </SectionCard>
        <SectionCard title="发布归档流程" className="report-process-card"><ProcessSteps report={activeReport} reviews={reviews} /></SectionCard>
        <div className="report-review-info-grid">
          <SmallInfoCard title="状态概览" rows={[`当前状态：${activeReport?.statusText || '--'}`, `报告类型：${activeReport?.typeText || '--'}`]} />
          <SmallInfoCard title="审核记录" rows={(reviews || []).length ? reviews.map((item: any) => `${item.reviewer || '未知审核人'}：${item.status || item.action || '--'}`) : ['暂无持久化审核记录']} />
          <SmallInfoCard title="版本信息" rows={[`报告契约：${activeReport?.reportSchemaVersion || '--'}`, `报告类型：${activeReport?.typeText || '--'}`]} />
          <SmallInfoCard title="操作日志" rows={(reviews || []).length ? reviews.slice(0, 3).map((item: any) => `${item.reviewer || '系统'} · ${item.status || item.action || '--'}`) : [`系统 · 当前状态 ${activeReport?.statusText || '--'}`]} />
        </div>
      </div>
    </div>
  );
}

function ReportBaseInfo({ report, compact }: any) {
  return (
    <div className={`report-base-info ${compact ? 'compact' : ''}`}>
      <p><span>报告名称</span><strong title={report?.title || undefined}>{report?.title || '--'}</strong></p>
      <p><span>报告 ID</span><strong title={report?.report_id || undefined}>{report?.report_id || '--'}</strong></p>
      <p><span>报告类型</span><strong>{report?.typeText || '--'}</strong></p>
      <p><span>报告状态</span><strong>{report?.statusText || '--'}</strong></p>
    </div>
  );
}

function MiniMetric({ label, value, unit }: any) {
  return (
    <div>
      <span>{label}</span>
      <strong>{value}</strong>
      <em>{unit}</em>
      <small>{label.includes('时点') ? '明细已绑定' : '报告统计值'}</small>
    </div>
  );
}

function QuickActions({ onDownload, onRegenerate, onCopyLink, onReview, permissions }: any) {
  const disabledTip = '当前业务流程不支持此操作';
  return (
    <SectionCard title="快捷操作" className="report-quick-card">
      <div className="report-action-grid">
        {permissions.canDownload ? <Button icon={<FilePdfOutlined />} onClick={onDownload}>下载报告（PDF）</Button> : null}
        <Tooltip title={disabledTip}><Button icon={<FileExcelOutlined />} disabled>下载报告（Excel）</Button></Tooltip>
        <Button icon={<EyeOutlined />} onClick={() => document.querySelector('.report-preview-card')?.scrollIntoView({ behavior: 'smooth', block: 'start' })}>查看详情</Button>
        {permissions.canReview ? <Button type="primary" icon={<SendOutlined />} onClick={onReview}>进入审核</Button> : null}
        {permissions.canGenerate ? <Button icon={<SyncOutlined />} onClick={onRegenerate}>重新生成</Button> : null}
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
          { color: 'green', children: <div><strong>系统生成</strong><span>报告内容已形成</span></div> },
          { color: reviewed ? 'orange' : 'gray', children: <div><strong>审核记录</strong><span>{reviewed ? `${review.reviewer || '审核人未提供'} · ${review.review_status || '--'}` : '暂无持久化审核记录'}</span></div> },
          { color: published ? 'green' : 'gray', children: <div><strong>发布</strong><span>{published ? '报告状态为已发布' : '尚未发布'}</span></div> },
          { color: archived ? 'green' : 'gray', children: <div><strong>归档</strong><span>{archived ? '报告状态为已归档' : '尚未归档'}</span></div> }
        ]}
      />
    </SectionCard>
  );
}

function ProcessSteps({ report, reviews = [] }: { report: any; reviews: any[] }) {
  const status = String(report?.status || '').toLowerCase();
  const steps = [
    { label: '系统生成', done: Boolean(report?.generated_at) },
    { label: '形成审核记录', done: reviews.length > 0 },
    { label: '审核完成', done: ['approved', 'rejected', 'published', 'archived'].includes(status) },
    { label: '发布', done: ['published', 'archived'].includes(status) },
    { label: '归档', done: status === 'archived' }
  ];
  return (
    <div className="report-process-steps">
      {steps.map((step, index) => (
        <div key={step.label} className={step.done ? 'done' : ''}>
          <i>{index + 1}</i>
          <span>{step.label}</span>
          <small>{step.done ? '已完成' : '待处理'}</small>
        </div>
      ))}
    </div>
  );
}

function SmallInfoCard({ title, rows }: { title: string; rows: string[] }) {
  return <SectionCard title={title} className="report-small-info">{rows.map((row) => <p key={row}>{row}</p>)}</SectionCard>;
}
