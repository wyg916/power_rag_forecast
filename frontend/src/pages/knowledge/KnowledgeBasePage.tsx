import {
  ApiOutlined,
  CheckCircleOutlined,
  CloudUploadOutlined,
  CopyOutlined,
  DatabaseOutlined,
  DeploymentUnitOutlined,
  DownloadOutlined,
  FileDoneOutlined,
  FileSearchOutlined,
  FileTextOutlined,
  PartitionOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
  SearchOutlined,
  SyncOutlined,
  WarningOutlined
} from '@ant-design/icons';
import { Alert, App, Button, Empty, Input, Select, Space, Table, Tag, Upload } from 'antd';
import { useEffect, useMemo, useState } from 'react';
import { api } from '../../api';
import { DetailDrawer } from '../../components/actions/DetailDrawer';
import { SectionCard } from '../../components/cards/SectionCard';
import { PageHeader } from '../../components/common/PageHeader';
import { useAuth } from '../../context/AuthContext';
import { getKnowledgeBaseData, searchKnowledge, type KnowledgeData, type KnowledgeRelease } from '../../services/knowledgeApi';
import type { PageProps } from '../../types/ui';

type KnowledgeMetric = {
  key: string;
  title: string;
  value: string;
  unit?: string;
  trend: string;
  tone: 'success' | 'info' | 'warning' | 'danger';
  icon: JSX.Element;
};

type AnswerBlock = {
  key: string;
  title: string;
  icon?: JSX.Element;
  tone: 'success' | 'info' | 'warning' | 'purple';
  content: string;
};

const defaultKnowledgeData: KnowledgeData = {
  dataSource: '业务知识库',
  stats: {},
  ragHealth: {},
  documents: [],
  totalDocuments: 0,
  releases: [],
  empty: false,
  metrics: [
    { key: 'documents', title: '文档总数', value: 0, unit: '份', trend: '可检索资料', tone: 'info' },
    { key: 'indexed', title: '已索引', value: 0, unit: 'chunks', trend: '知识片段', tone: 'success' },
    { key: 'pending', title: '待处理', value: 0, unit: '份', trend: '索引队列', tone: 'success' },
    { key: 'qa', title: 'QA 通过率', value: 0, unit: '%', trend: '最近校验', tone: 'warning' }
  ]
};

function formatNumber(value: any, fallback = '0') {
  if (value === undefined || value === null || value === '') return fallback;
  const normalized = String(value).replace(/,/g, '');
  const numeric = Number(normalized);
  if (Number.isFinite(numeric)) return numeric.toLocaleString('zh-CN');
  return String(value);
}

function formatPercent(value: any) {
  const numeric = Number(String(value ?? '').replace('%', ''));
  if (!Number.isFinite(numeric)) return '0.0%';
  return `${numeric.toFixed(1)}%`;
}

function formatDate(value?: string) {
  if (!value) return '-';
  return String(value).replace('T', ' ').slice(0, 19);
}

function statusLabel(status?: string, fallback?: boolean) {
  const value = String(status || '').toLowerCase();
  if (fallback || value === 'fallback') return { text: '降级', color: 'warning' };
  if (value === 'normal') return { text: '正常', color: 'success' };
  if (value === 'partial') return { text: '部分完成', color: 'processing' };
  if (value === 'unavailable') return { text: '不可用', color: 'error' };
  if (value === 'disabled') return { text: '未启用', color: 'default' };
  if (value === 'not_configured') return { text: '需配置', color: 'default' };
  return { text: '运行中', color: 'processing' };
}

const releaseStatusMeta: Record<KnowledgeRelease['status'], { text: string; color: string }> = {
  candidate: { text: '候选版本', color: 'gold' },
  validated: { text: '已校验', color: 'blue' },
  published: { text: '已发布', color: 'green' },
  superseded: { text: '历史版本', color: 'default' },
  rolled_back: { text: '已回滚', color: 'orange' },
  failed: { text: '发布失败', color: 'red' }
};

function documentStatusTag(value: string) {
  if (value === '索引中' || value === 'partial') return <Tag color="processing">索引中</Tag>;
  if (value === '待处理' || value === 'pending') return <Tag color="warning">待处理</Tag>;
  return <Tag color="success">已索引</Tag>;
}

function normalizeSearchItems(payload: any) {
  return Array.isArray(payload?.items) ? payload.items : [];
}

function normalizeAnswerBlocks(payload: any): AnswerBlock[] {
  const blocks = Array.isArray(payload?.answer_blocks) ? payload.answer_blocks : [];
  if (!blocks.length) {
    return [
      {
        key: 'empty',
        title: '结论',
        tone: 'info',
        content: '执行检索后，将根据后端返回的知识片段整理答案。'
      }
    ];
  }
  return blocks.map((item: any, index: number) => ({
    key: String(item.key || `block-${index}`),
    title: String(item.title || '分析'),
    tone: item.tone || 'info',
    content: String(item.content || '')
  }));
}

function blockIcon(key: string) {
  if (key === 'conclusion') return <CheckCircleOutlined />;
  if (key === 'evidence') return <FileSearchOutlined />;
  if (key === 'risk') return <WarningOutlined />;
  return <SafetyCertificateOutlined />;
}

export function KnowledgeBasePage(_: PageProps) {
  const { message } = App.useApp();
  const [data, setData] = useState<KnowledgeData>(defaultKnowledgeData);
  const [loading, setLoading] = useState(true);
  const { canPerformAction } = useAuth();
  const canWriteKnowledge = canPerformAction('knowledge:write');
  const canPublishKnowledge = canPerformAction('knowledge:publish');
  const canExportKnowledge = canPerformAction('knowledge:export');
  const [error, setError] = useState('');
  const [query, setQuery] = useState('分时电价、现货交易风险和购电建议是什么？');
  const [topK, setTopK] = useState(5);
  const [searching, setSearching] = useState(false);
  const [results, setResults] = useState<any[]>([]);
  const [answerBlocks, setAnswerBlocks] = useState<AnswerBlock[]>(normalizeAnswerBlocks(null));
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailData, setDetailData] = useState<Record<string, unknown> | null>(null);
  const [releaseActionLoading, setReleaseActionLoading] = useState('');

  async function loadData() {
    setLoading(true);
    setError('');
    try {
      setData(await getKnowledgeBaseData());
    } catch (err) {
      setError(err instanceof Error ? err.message : '知识库数据加载失败');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData();
  }, []);

  async function rebuildIndex() {
    setLoading(true);
    try {
      const res = await api.knowledgeIndexLocal();
      message.success(`知识库索引任务已提交：${res.task_id || res.indexed_documents || 'knowledge_import'}`);
      await loadData();
    } catch (err) {
      message.error(err instanceof Error ? err.message : '重建索引失败');
    } finally {
      setLoading(false);
    }
  }

  async function refreshEmbeddings() {
    setLoading(true);
    try {
      const res = await api.knowledgeEmbeddingRefresh();
      message.success(`Embedding 刷新任务已提交：${res.task_id || 'embedding_refresh'}`);
      await loadData();
    } catch (err) {
      message.error(err instanceof Error ? err.message : '刷新 Embedding 失败');
    } finally {
      setLoading(false);
    }
  }

  async function runSearch() {
    const text = query.trim();
    if (!text) {
      message.warning('请输入检索问题');
      return;
    }
    setSearching(true);
    try {
      const payload = await searchKnowledge(text, topK);
      const items = normalizeSearchItems(payload);
      setResults(items);
      setAnswerBlocks(normalizeAnswerBlocks(payload));
      if (!items.length) message.info('未检索到可用证据');
      await loadData();
    } catch (err) {
      setResults([]);
      setAnswerBlocks(normalizeAnswerBlocks(null));
      message.error(err instanceof Error ? err.message : '检索失败');
    } finally {
      setSearching(false);
    }
  }

  async function uploadDocument(file: File) {
    setLoading(true);
    try {
      const res = await api.knowledgeUpload(file);
      message.success(`文档已写入知识库：${res.doc_id || file.name}`);
      await loadData();
    } catch (err) {
      message.error(err instanceof Error ? err.message : '上传失败');
    } finally {
      setLoading(false);
    }
  }

  async function batchValidate() {
    setSearching(true);
    try {
      const res = await api.knowledgeBatchValidate({ top_k: topK });
      message.success(`批量校验完成：${res.passed}/${res.total} 通过`);
      await loadData();
    } catch (err) {
      message.error(err instanceof Error ? err.message : '批量校验失败');
    } finally {
      setSearching(false);
    }
  }

  async function exportResult() {
    try {
      const blob = await api.knowledgeExport();
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `knowledge_export_${Date.now()}.csv`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      message.error(err instanceof Error ? err.message : '导出失败');
    }
  }

  async function runReleaseAction(release: KnowledgeRelease, action: 'validate' | 'publish' | 'rollback') {
    const actionKey = `${release.release_id}:${action}`;
    setReleaseActionLoading(actionKey);
    try {
      await api.knowledgeReleaseAction(release.release_id, action);
      const labels = { validate: '校验', publish: '发布', rollback: '回滚' };
      message.success(`${release.release_id} ${labels[action]}完成`);
      await loadData();
    } catch (err) {
      message.error(err instanceof Error ? err.message : '版本操作失败');
    } finally {
      setReleaseActionLoading('');
    }
  }

  const ragHealth = data.ragHealth || {};
  const ragStatus = statusLabel(ragHealth.status, Boolean(ragHealth.fallback_enabled));
  const activeRelease = (data.releases || []).find((item) => item.is_current) || data.releases?.[0];
  const runtimeHealthy = ragHealth.ok === true && ragHealth.status === 'normal';
  const retrievalAvailable = Boolean(
    runtimeHealthy
    && (
      ragHealth.enterprise_profile !== true
      || (activeRelease?.is_current && activeRelease.status === 'published')
    )
  );
  const documentRows = useMemo(
    () =>
      (data.documents || []).map((row: any, index: number) => ({
        key: row.doc_id || `${row.title}-${index}`,
        name: row.title,
        category: row.category || row.domain || row.metadata?.domain || '业务知识',
        updatedAt: formatDate(row.updated_at || row.indexed_at),
        chunks: row.chunk_count ?? 0,
        status: row.status_label || row.status,
        raw: row
      })),
    [data.documents]
  );
  const docCount = data.stats.documents ?? ragHealth.kb_document_count ?? data.totalDocuments ?? 0;
  const chunkCount = data.stats.chunks ?? ragHealth.kb_chunk_count ?? 0;
  const embeddedCount = data.stats.embedded_chunks ?? ragHealth.embedded_chunk_count ?? 0;
  const pendingCount = data.stats.pending_documents ?? 0;
  const qaRate = data.stats.qa_pass_rate ?? 0;
  const releaseLedgerCount = activeRelease
    ? activeRelease.documents + activeRelease.isolated + activeRelease.duplicates
    : docCount;
  const releaseChunkCount = activeRelease?.chunks ?? chunkCount;
  const releaseCompletedCount = activeRelease ? releaseLedgerCount : Math.max(0, Number(docCount) - Number(pendingCount));
  const releasePendingCount = activeRelease ? 0 : pendingCount;
  const releaseUpdatedAt = activeRelease?.updated_at || ragHealth.last_embedding_refresh_at;
  const releaseIndexStatus = activeRelease
    ? releaseStatusMeta[activeRelease.status] || ragStatus
    : (pendingCount > 0 ? { text: '处理中', color: 'processing' } : { text: '已完成', color: 'success' });
  const metricIcons: Record<string, JSX.Element> = {
    documents: <FileTextOutlined />,
    indexed: <DatabaseOutlined />,
    pending: <FileDoneOutlined />,
    qa: <SafetyCertificateOutlined />
  };
  const metrics: KnowledgeMetric[] = data.metrics.map((item) => ({
    ...item,
    value: item.key === 'qa'
      ? formatPercent(item.value)
      : formatNumber(item.key === 'documents'
        ? releaseLedgerCount
        : item.key === 'indexed'
          ? releaseChunkCount
          : item.key === 'pending'
            ? releasePendingCount
            : item.value),
    unit: item.key === 'qa' ? undefined : item.unit,
    icon: metricIcons[item.key] || <DatabaseOutlined />
  }));

  const flowNodes = [
    { title: '文档台账', value: `${formatNumber(releaseLedgerCount)} 份资料`, icon: <FileTextOutlined /> },
    { title: '治理终态', value: `${formatNumber(releaseCompletedCount)}/${formatNumber(releaseLedgerCount)} 已确认`, icon: <PartitionOutlined /> },
    { title: '向量化', value: `${formatNumber(activeRelease ? releaseChunkCount : embeddedCount)} chunks`, icon: <DeploymentUnitOutlined /> },
    { title: '建索引', value: releaseIndexStatus.text, icon: <DatabaseOutlined /> },
    { title: '发布门禁', value: activeRelease ? `${activeRelease.gates.passed}/${activeRelease.gates.total}` : `QA ${formatPercent(qaRate)}`, icon: <SafetyCertificateOutlined /> }
  ];

  return (
    <div className="knowledge-workbench-page">
      <PageHeader
        title="知识库"
        subtitle="管理政策文档、RAG 检索、索引状态和 QA 测试"
        filters={<div className="knowledge-source-control">
          <span>知识范围</span>
          <Tag color="blue">业务知识库</Tag>
        </div>}
        actions={[
          {
            key: 'rebuild',
            label: '重建索引',
            icon: <SyncOutlined />,
            type: 'primary',
            loading,
            hidden: !canWriteKnowledge,
            onClick: rebuildIndex
          },
          {
            key: 'embedding',
            label: '刷新 Embedding',
            icon: <ReloadOutlined />,
            loading,
            hidden: !canWriteKnowledge,
            onClick: refreshEmbeddings
          },
          { key: 'validate', label: '批量校验', icon: <SafetyCertificateOutlined />, loading: searching, collapseAtNarrow: true, hidden: !canWriteKnowledge, onClick: batchValidate },
          { key: 'export', label: '导出结果', icon: <DownloadOutlined />, collapseAtNarrow: true, hidden: !canExportKnowledge, onClick: exportResult }
        ]}
        extra={canWriteKnowledge ? <Upload
          showUploadList={false}
          beforeUpload={(file) => {
            uploadDocument(file as File);
            return false;
          }}
          accept=".txt,.md,.csv,.json"
        >
          <Button className="knowledge-upload-button" icon={<CloudUploadOutlined />}>上传文档</Button>
        </Upload> : null}
      />
      <div className="knowledge-top-workspace">
        <SectionCard title="索引状态" className="knowledge-flow-card knowledge-flow-card-top" compact>
          <div className="knowledge-flow">
            {flowNodes.map((item, index) => (
              <div className="knowledge-flow-node" key={item.title}>
                <span>{item.icon}</span>
                <div>
                  <strong>{item.title}</strong>
                  <p>{item.value}</p>
                </div>
                {index < flowNodes.length - 1 && <i />}
              </div>
            ))}
          </div>
        </SectionCard>
      </div>

      {error && <Alert type="error" showIcon message="知识库数据加载失败" description={error} action={<Button onClick={loadData}>重试</Button>} />}

      <div className="knowledge-content-grid">
        <div className="knowledge-kpi-grid">
          {metrics.map((item) => (
            <div className={`knowledge-kpi-card tone-${item.tone}`} key={item.key}>
              <div>
                <span>{item.title}</span>
                <strong>{item.value}<small>{item.unit || ''}</small></strong>
                <p>{item.trend}</p>
              </div>
              <div className="knowledge-kpi-icon">{item.icon}</div>
            </div>
          ))}
        </div>
        <SectionCard
          title={
            <Space size={8}>
              <span>文档列表</span>
              <small>共 {formatNumber(data.totalDocuments || docCount)} 份</small>
            </Space>
          }
          className="knowledge-doc-card"
          loading={loading}
          extra={<Button type="link" size="small" onClick={loadData}>刷新</Button>}
        >
          <Table
            size="small"
            rowKey="key"
            pagination={{ pageSize: 8, showSizeChanger: false, size: 'small' }}
            dataSource={documentRows}
            scroll={{ y: 220 }}
            columns={[
              { title: '文档名称', dataIndex: 'name', ellipsis: true },
              { title: '文档分类', dataIndex: 'category', width: 96, render: (value) => <Tag>{value}</Tag> },
              { title: '更新时间', dataIndex: 'updatedAt', width: 132 },
              { title: 'Chunk', dataIndex: 'chunks', width: 82 },
              { title: '状态', dataIndex: 'status', width: 92, render: documentStatusTag },
              {
                title: '操作',
                width: 124,
                render: (_, record: any) => (
                  <Space size={4}>
                    <Button type="link" size="small" onClick={() => { setDetailData(record.raw || record); setDetailOpen(true); }}>详情</Button>
                    {canWriteKnowledge ? <Button
                      type="link"
                      size="small"
                      onClick={rebuildIndex}
                    >重新索引</Button> : null}
                  </Space>
                )
              }
            ]}
          />
        </SectionCard>

        <SectionCard title="索引与 RAG 状态" className="knowledge-rag-panel" loading={loading}>
          <div className="knowledge-rag-content">
            <div className="knowledge-rag-section">
              <div className="knowledge-rag-title">
                <strong>索引与向量化状态摘要</strong>
                <Tag color={releaseIndexStatus.color as any}>{releaseIndexStatus.text}</Tag>
              </div>
              <dl>
                <div><dt>索引总量</dt><dd>{formatNumber(releaseChunkCount)} chunks</dd></div>
                <div><dt>已向量化</dt><dd>{formatNumber(activeRelease ? releaseChunkCount : embeddedCount)} chunks</dd></div>
                <div><dt>最近更新时间</dt><dd>{formatDate(releaseUpdatedAt)}</dd></div>
                <div><dt>索引状态</dt><dd><Tag color={releaseIndexStatus.color}>{releaseIndexStatus.text}</Tag></dd></div>
              </dl>
            </div>
            <div className="knowledge-rag-section">
              <div className="knowledge-rag-title">
                <strong>RAG 运行状态</strong>
                <Tag color={retrievalAvailable ? 'success' : 'default'}>{retrievalAvailable ? '可用' : '未发布'}</Tag>
              </div>
              <p>检索服务：{retrievalAvailable ? '可用' : '暂不可用'}</p>
              <p>知识片段：{formatNumber(releaseChunkCount)}；已完成处理：{formatNumber(activeRelease ? releaseChunkCount : embeddedCount)}</p>
              <p>最近更新时间：{formatDate(releaseUpdatedAt)}</p>
              {!retrievalAvailable && (
                <Alert type="warning" showIcon message="检索服务暂不可用" description="当前不会返回未经发布的候选知识，请稍后重试或联系管理员。" />
              )}
            </div>
            <div className="knowledge-rag-section knowledge-release-section">
              <div className="knowledge-rag-title">
                <strong>知识版本</strong>
                {activeRelease ? (
                  <Space size={4}>
                    <Tag color={releaseStatusMeta[activeRelease.status]?.color}>{releaseStatusMeta[activeRelease.status]?.text}</Tag>
                    {activeRelease.is_current && <Tag color="green">当前版本</Tag>}
                  </Space>
                ) : <Tag>暂无版本</Tag>}
              </div>
              {activeRelease ? (
                <>
                  <dl>
                    <div><dt>门禁</dt><dd>{activeRelease.gates.passed}/{activeRelease.gates.total}</dd></div>
                    <div><dt>台账</dt><dd>{formatNumber(releaseLedgerCount)}/{formatNumber(releaseLedgerCount)}</dd></div>
                    <div><dt>可发布</dt><dd>{formatNumber(activeRelease.documents)}</dd></div>
                    <div><dt>隔离</dt><dd>{formatNumber(activeRelease.isolated)}</dd></div>
                    <div><dt>重复</dt><dd>{formatNumber(activeRelease.duplicates)}</dd></div>
                    <div><dt>知识片段</dt><dd>{formatNumber(activeRelease.chunks)}</dd></div>
                  </dl>
                  <Space className="knowledge-release-actions" wrap>
                    {canPublishKnowledge && (activeRelease.status === 'candidate' || activeRelease.status === 'rolled_back') && (
                      <Button
                        size="small"
                        disabled={!activeRelease.gates.ready}
                        loading={releaseActionLoading === `${activeRelease.release_id}:validate`}
                        title={!activeRelease.gates.ready ? '全部发布门禁通过后才可校验' : undefined}
                        onClick={() => runReleaseAction(activeRelease, 'validate')}
                      >校验版本</Button>
                    )}
                    {canPublishKnowledge && activeRelease.status === 'validated' && (
                      <Button
                        type="primary"
                        size="small"
                        loading={releaseActionLoading === `${activeRelease.release_id}:publish`}
                        onClick={() => runReleaseAction(activeRelease, 'publish')}
                      >发布版本</Button>
                    )}
                    {canPublishKnowledge && activeRelease.status === 'published' && activeRelease.is_current && (
                      <Button
                        danger
                        size="small"
                        loading={releaseActionLoading === `${activeRelease.release_id}:rollback`}
                        onClick={() => runReleaseAction(activeRelease, 'rollback')}
                      >回滚版本</Button>
                    )}
                  </Space>
                </>
              ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无可用知识版本" />}
            </div>
          </div>
        </SectionCard>
      </div>

      <div className="knowledge-search-grid">
        <SectionCard title="检索测试 / QA 测试区" className="knowledge-search-card">
          <div className="knowledge-search-form">
            <label>输入业务问题（支持多行）</label>
            <Input.TextArea value={query} onChange={(event) => setQuery(event.target.value)} autoSize={{ minRows: 4, maxRows: 5 }} />
            <div className="knowledge-search-actions">
              <Space>
                <span>Top K</span>
                <Select value={topK} onChange={setTopK} options={[3, 5, 8, 10].map((value) => ({ value, label: String(value) }))} style={{ width: 86 }} />
              </Space>
              <Button type="primary" loading={searching} icon={<SearchOutlined />} onClick={runSearch}>检索 / 测试</Button>
            </div>
          </div>
        </SectionCard>

        <SectionCard title={`检索结果（Top ${topK}）`} className="knowledge-result-card" loading={searching}>
          <Table
            size="small"
            rowKey={(record: any) => record.chunk_id || record.id || `${record.title || 'result'}-${record.content || record.snippet || ''}`}
            pagination={false}
            dataSource={results}
            scroll={{ y: 160 }}
            locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="执行检索后显示结果" /> }}
            columns={[
              { title: '文档', dataIndex: 'title', width: 190, ellipsis: true },
              {
                title: '分数',
                width: 76,
                render: (_, record: any) => <strong className="knowledge-score">{Number(record.final_score ?? record.score ?? 0).toFixed(3)}</strong>
              },
              { title: '片段（命中高亮）', dataIndex: 'content', ellipsis: true },
              {
                title: '操作',
                width: 92,
                render: (_, record: any) => <Button type="link" size="small" onClick={() => { setDetailData(record); setDetailOpen(true); }}>查看片段</Button>
              }
            ]}
          />
        </SectionCard>

        <SectionCard
          title={<Space size={8}>AI 整理答案 <Tag color="processing">智能整理</Tag></Space>}
          className="knowledge-answer-card"
          extra={<Button type="link" size="small" icon={<CopyOutlined />} onClick={() => navigator.clipboard?.writeText(answerBlocks.map((item) => `${item.title}：${item.content}`).join('\n'))}>复制</Button>}
        >
          <div className="knowledge-answer-blocks">
            {answerBlocks.map((item) => (
              <section className={`knowledge-answer-block tone-${item.tone}`} key={item.key}>
                <span>{item.icon || blockIcon(item.key)}</span>
                <div>
                  <strong>{item.title}</strong>
                  <p>{item.content}</p>
                </div>
              </section>
            ))}
          </div>
        </SectionCard>
      </div>

      <DetailDrawer title="知识库详情" open={detailOpen} data={detailData} onClose={() => setDetailOpen(false)} />
    </div>
  );
}
