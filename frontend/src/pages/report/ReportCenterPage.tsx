import { CheckCircleOutlined, CloseCircleOutlined, FileTextOutlined, HourglassOutlined, SendOutlined } from '@ant-design/icons';
import { Button, Col, Input, List, Row, Space, Table, Tag, Timeline, message } from 'antd';
import { useEffect, useState } from 'react';
import { api } from '../../api';
import { DetailDrawer } from '../../components/actions/DetailDrawer';
import { SectionCard } from '../../components/cards/SectionCard';
import { PriceCurveChart } from '../../components/charts/PriceCurveChart';
import { PageTabs } from '../../components/common/PageTabs';
import { DataSourceTag, DataStateBanner } from '../../components/common/States';
import { MetricGrid } from '../../components/layout/UnifiedPage';
import { reportMock } from '../../mock/reportMock';
import { getReportCenterData } from '../../services/reportApi';
import type { PageProps } from '../../types/ui';

const icons = [<FileTextOutlined />, <HourglassOutlined />, <SendOutlined />, <CloseCircleOutlined />];

const tabs = [
  { key: 'report-daily', label: '报告列表' },
  { key: 'report-weekly', label: '报告生成' },
  { key: 'report-review', label: '报告审核' },
  { key: 'report-publish', label: '报告归档' }
];

export function ReportCenterPage({ activeSubKey, onSubNavigate }: PageProps) {
  const [data, setData] = useState<any>(reportMock);
  const [loading, setLoading] = useState(true);
  const [activeReport, setActiveReport] = useState<any>(null);
  const [reviewComment, setReviewComment] = useState('');
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailData, setDetailData] = useState<Record<string, unknown> | null>(null);

  async function loadData() {
    setLoading(true);
    try {
      const payload = await getReportCenterData();
      setData(payload);
      setActiveReport(payload.activeReport || null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData();
  }, []);

  async function generateReport() {
    const res = await api.generateReport();
    message.success(`报告生成任务已启动：${res.task_id || 'report_only'}`);
  }

  async function review(action: 'approve' | 'reject' | 'publish') {
    const reportId = activeReport?.report_id || data.reports?.[0]?.[0] || 'latest';
    const payload = { reviewer: 'web_user', review_comment: reviewComment || (action === 'reject' ? '需要补充说明' : '审核通过') };
    if (action === 'approve') await api.approveReport(reportId, payload);
    if (action === 'reject') await api.rejectReport(reportId, payload);
    if (action === 'publish') await api.publishReport(reportId, payload);
    message.success('报告状态已更新');
    await loadData();
  }

  function downloadReport() {
    const reportId = activeReport?.report_id || data.reports?.[0]?.[0] || 'latest';
    window.open(api.reportDownloadUrl(reportId), '_blank');
  }

  return (
    <div className="page-stack">
      <PageTabs items={tabs} activeKey={activeSubKey} onChange={onSubNavigate} />
      <DataStateBanner
        scope="报告中心"
        loading={loading}
        source={data.dataSource}
        error={data.error}
        empty={data.empty}
        mockFallback={data.mockFallback}
        fallbackReason={data.fallbackReason}
        partialErrors={data.partialErrors}
        onRetry={loadData}
      />
      <MetricGrid items={data.metrics || []} icons={icons} loading={loading} minColumnWidth={190} />

      {activeSubKey === 'report-weekly' && (
        <SectionCard title="报告生成任务" extra={<Button type="primary" onClick={generateReport}>生成最新报告</Button>}>
          <p>报告生成会创建异步任务，任务日志可在任务中心查看。关联预测批次默认使用 latest。</p>
          <DataSourceTag source={data.dataSource} />
        </SectionCard>
      )}

      {activeSubKey !== 'report-weekly' && (
        <div className="report-layout-grid">
            <SectionCard title={activeSubKey === 'report-publish' ? '归档报告' : '报告列表'} loading={loading} extra={<DataSourceTag source={data.dataSource} />} scrollable>
              <List
                className="report-list"
                dataSource={data.reports}
                renderItem={(item: any[], index) => (
                  <List.Item className={index === 0 ? 'active-report' : ''} onClick={() => { setActiveReport({ report_id: item[0], report_type: item[1], status: item[2], generated_at: item[3] }); setDetailData({ report_id: item[0], report_type: item[1], status: item[2], generated_at: item[3] }); setDetailOpen(true); }}>
                    <div>
                      <strong>{item[0]}</strong>
                      <p>生成时间：{item[3]}</p>
                      <Tag>{item[1]}</Tag>
                      <Tag color={String(item[2]).includes('待') ? 'warning' : String(item[2]).includes('发') ? 'success' : 'error'}>{item[2]}</Tag>
                    </div>
                  </List.Item>
                )}
              />
            </SectionCard>
            <SectionCard title="报告预览" extra={<Space><Button onClick={downloadReport}>下载报告</Button><Button onClick={() => { setDetailData(activeReport); setDetailOpen(true); }}>详情</Button></Space>} loading={loading} scrollable>
              <div className="report-preview">
                <p className="muted">报告 ID：{activeReport?.report_id || 'latest'}，生成时间：{activeReport?.generated_at || '--'}</p>
                <h4>1. 数据概览</h4>
                <div className="report-metric-row">
                  {(data.previewMetrics || []).map((item: any[]) => <div key={item[0]}><span>{item[0]}</span><strong>{item[1]}</strong><small>{item[2]}</small></div>)}
                </div>
                <h4>2. 预测摘要</h4>
                <Row gutter={16}>
                  <Col xs={24} lg={14}><p>报告摘要来自最新预测批次、报告元数据或本地报告结构化文件。</p><p>高风险时段、策略建议和人工复核建议会随预测数据刷新。</p></Col>
                  <Col xs={24} lg={10}><PriceCurveChart data={data.previewCurve || []} height={160} showActual={false} /></Col>
                </Row>
                <h4>3. 风险时段</h4>
                <Table size="small" pagination={false} dataSource={data.risks.map((row: any[], index: number) => ({ key: index, row }))} columns={[
                  { title: '时段', render: (_, record: any) => record.row[0] },
                  { title: '风险等级', render: (_, record: any) => <Tag color={record.row[1] === '高' ? 'error' : record.row[1] === '中' ? 'warning' : 'success'}>{record.row[1]}</Tag> },
                  { title: '风险描述', render: (_, record: any) => record.row[2] },
                  { title: '建议关注点', render: (_, record: any) => record.row[3] }
                ]} />
              </div>
            </SectionCard>
          <div className="report-side-stack">
            {activeSubKey === 'report-review' && (
              <SectionCard title="审核操作" extra={<Tag color="warning">{activeReport?.status || '待审核'}</Tag>}>
                <Input.TextArea rows={5} value={reviewComment} onChange={(event) => setReviewComment(event.target.value)} placeholder="请输入审核意见" maxLength={300} showCount />
                <Space wrap className="review-buttons">
                  <Button type="primary" icon={<CheckCircleOutlined />} onClick={() => review('approve')}>通过</Button>
                  <Button danger icon={<CloseCircleOutlined />} onClick={() => review('reject')}>驳回</Button>
                  <Button onClick={generateReport}>重新生成</Button>
                  <Button onClick={() => review('publish')}>发布</Button>
                </Space>
              </SectionCard>
            )}
            {activeSubKey === 'report-publish' && (
              <SectionCard title="归档操作" extra={<Tag color="success">可归档</Tag>}>
                <div className="detail-list">
                  <p><span>当前报告</span><strong>{activeReport?.report_id || 'latest'}</strong></p>
                  <p><span>版本状态</span><strong>{activeReport?.status || '待审核'}</strong></p>
                  <p><span>关联批次</span><strong>{activeReport?.run_id || 'latest'}</strong></p>
                </div>
                <Space wrap className="review-buttons">
                  <Button onClick={downloadReport}>下载归档件</Button>
                  <Button type="primary" onClick={() => review('publish')}>发布归档</Button>
                </Space>
              </SectionCard>
            )}
            {activeSubKey === 'report-daily' && (
              <SectionCard title="快捷操作">
                <Space wrap className="review-buttons">
                  <Button onClick={downloadReport}>下载报告</Button>
                  <Button onClick={() => { setDetailData(activeReport); setDetailOpen(true); }}>查看详情</Button>
                  <Button type="primary" onClick={generateReport}>重新生成</Button>
                </Space>
              </SectionCard>
            )}
            <SectionCard title={activeSubKey === 'report-publish' ? '归档时间线' : '发布记录'}>
              <Timeline items={(data.timeline || []).map((item: any[]) => ({ color: item[0] === '系统生成' ? 'green' : item[0] === '待审核' ? 'orange' : 'gray', children: <div><strong>{item[0]}</strong><p>{item[1]}</p><span>{item[2]}</span></div> }))} />
            </SectionCard>
          </div>
        </div>
      )}

      <DetailDrawer title="报告详情" open={detailOpen} data={detailData} onClose={() => setDetailOpen(false)} />
    </div>
  );
}
