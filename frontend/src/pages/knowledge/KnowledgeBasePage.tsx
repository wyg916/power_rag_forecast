import { DatabaseOutlined, FileTextOutlined, ReloadOutlined, SearchOutlined, SyncOutlined } from '@ant-design/icons';
import { Alert, Button, Col, Descriptions, Input, Row, Space, Tag, message } from 'antd';
import { useEffect, useMemo, useState } from 'react';
import { api } from '../../api';
import { DetailDrawer } from '../../components/actions/DetailDrawer';
import { SectionCard } from '../../components/cards/SectionCard';
import { TableCard } from '../../components/cards/TableCard';
import { PageTabs } from '../../components/common/PageTabs';
import { DataSourceTag, DataStateBanner, EmptyState } from '../../components/common/States';
import { MetricGrid } from '../../components/layout/UnifiedPage';
import { knowledgeMock } from '../../mock/knowledgeMock';
import { getKnowledgeBaseData, searchKnowledge } from '../../services/knowledgeApi';
import type { PageProps } from '../../types/ui';

const tabs = [
  { key: 'knowledge-policy', label: '文档管理' },
  { key: 'knowledge-index', label: '索引管理' },
  { key: 'knowledge-rag', label: '知识检索' },
  { key: 'knowledge-qa', label: 'QA 测试' }
];

function ragStatusTag(status: string, fallback: boolean) {
  if (status === 'normal' && !fallback) return <Tag color="success">正常</Tag>;
  if (status === 'partial') return <Tag color="processing">部分完成</Tag>;
  if (status === 'disabled' || status === 'not_configured') return <Tag color="default">未配置</Tag>;
  return <Tag color="warning">降级</Tag>;
}

export function KnowledgeBasePage({ activeSubKey, onSubNavigate }: PageProps) {
  const [data, setData] = useState<any>(knowledgeMock);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState('分时电价 现货交易 风险');
  const [searching, setSearching] = useState(false);
  const [results, setResults] = useState<any[]>([]);
  const [answer, setAnswer] = useState('');
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailData, setDetailData] = useState<Record<string, unknown> | null>(null);

  async function loadData() {
    setLoading(true);
    try {
      setData(await getKnowledgeBaseData());
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
    } finally {
      setLoading(false);
    }
  }

  async function runSearch() {
    setSearching(true);
    try {
      const payload = await searchKnowledge(query, 5);
      const items = payload.items || [];
      setResults(items);
      setAnswer(items.length ? `检索到 ${items.length} 条证据，请优先查看相似度最高的片段。` : '未检索到可用证据。');
    } catch (error) {
      message.error(error instanceof Error ? error.message : '检索失败');
    } finally {
      setSearching(false);
    }
  }

  const ragHealth = data.ragHealth || {};
  const fallbackReasons = Array.isArray(ragHealth.fallback_reasons) ? ragHealth.fallback_reasons : [];
  const documentRows = useMemo(
    () =>
      results.length
        ? results.map((item) => [item.title, item.source_type || 'local_file', item.source, item.chunk_id, '已检索'])
        : data.documents || [],
    [data.documents, results]
  );

  return (
    <div className="page-stack">
      <PageTabs items={tabs} activeKey={activeSubKey} onChange={onSubNavigate} />
      <DataStateBanner
        scope="知识库"
        loading={loading}
        source={data.dataSource}
        error={data.error}
        empty={data.empty}
        mockFallback={data.mockFallback}
        fallbackReason={data.fallbackReason}
        partialErrors={data.partialErrors}
        onRetry={loadData}
      />

      <div className="knowledge-top-grid">
        <MetricGrid items={data.metrics || []} icons={(data.metrics || []).map(() => <FileTextOutlined />)} loading={loading} minColumnWidth={180} />
        <SectionCard title="RAG 运行状态" loading={loading} compact>
          <div className="index-status">
            {ragStatusTag(String(ragHealth.status || 'unknown'), Boolean(ragHealth.fallback_enabled))}
            <p><DatabaseOutlined /> Provider：{ragHealth.embedding_provider || 'unknown'} / {ragHealth.rerank_provider || 'unknown'}</p>
            <p>Embedding 维度：{ragHealth.embedding_dim || 0}；Chunks：{ragHealth.kb_chunk_count || 0}；已向量化：{ragHealth.embedded_chunk_count || 0}</p>
            <p>Embedding 路径：{ragHealth.embedding_model_path || '未配置'}（{ragHealth.embedding_model_path_exists ? '存在' : '不存在'}）</p>
            <p>Reranker 路径：{ragHealth.rerank_model_path || '未配置'}（{ragHealth.rerank_model_path_exists ? '存在' : '不存在'}）</p>
            {fallbackReasons.length > 0 && <Alert type="warning" showIcon message="RAG 当前处于降级模式" description={fallbackReasons.join('；')} />}
            <DataSourceTag source={data.dataSource} />
          </div>
        </SectionCard>
      </div>

      {activeSubKey === 'knowledge-policy' && (
        <TableCard
          title="文档列表"
          loading={loading}
          minHeight={420}
          extra={<Button onClick={loadData} icon={<ReloadOutlined />}>刷新</Button>}
          dataSource={documentRows.map((row: any[], index: number) => ({ key: `${row[0]}-${index}`, row }))}
          columns={[
            { title: '文档名称', render: (_, record: any) => record.row[0] },
            { title: '来源', render: (_, record: any) => <Tag>{record.row[1]}</Tag> },
            { title: '路径/时间', render: (_, record: any) => record.row[2] },
            { title: 'Chunk', render: (_, record: any) => record.row[3] },
            { title: '状态', render: (_, record: any) => <Tag color="success">{record.row[4]}</Tag> },
            {
              title: '操作',
              render: (_, record: any) => (
                <Button type="link" size="small" onClick={() => { setDetailData({ name: record.row[0], type: record.row[1], source: record.row[2], chunk: record.row[3] }); setDetailOpen(true); }}>
                  详情
                </Button>
              )
            }
          ]}
        />
      )}

      {activeSubKey === 'knowledge-index' && (
        <Row gutter={[16, 16]}>
          <Col xs={24} lg={12}>
            <SectionCard title="索引与向量刷新" loading={loading}>
              <Space wrap>
                <Button type="primary" icon={<SyncOutlined />} loading={loading} onClick={rebuildIndex}>重建本地索引</Button>
                <Button icon={<ReloadOutlined />} loading={loading} onClick={refreshEmbeddings}>刷新 Embedding</Button>
              </Space>
              <Descriptions column={1} size="small" style={{ marginTop: 16 }}>
                <Descriptions.Item label="文档数">{ragHealth.kb_document_count || 0}</Descriptions.Item>
                <Descriptions.Item label="Chunk 数">{ragHealth.kb_chunk_count || 0}</Descriptions.Item>
                <Descriptions.Item label="已向量化">{ragHealth.embedded_chunk_count || 0}</Descriptions.Item>
                <Descriptions.Item label="最近刷新">{ragHealth.last_embedding_refresh_at || '未知'}</Descriptions.Item>
              </Descriptions>
            </SectionCard>
          </Col>
          <Col xs={24} lg={12}>
            <SectionCard title="模型挂载检查" loading={loading}>
              <Descriptions column={1} size="small">
                <Descriptions.Item label="Embedding provider">{ragHealth.embedding_provider || 'unknown'}</Descriptions.Item>
                <Descriptions.Item label="Embedding path">{ragHealth.embedding_model_path || '未配置'}</Descriptions.Item>
                <Descriptions.Item label="Embedding path exists">{String(Boolean(ragHealth.embedding_model_path_exists))}</Descriptions.Item>
                <Descriptions.Item label="Rerank provider">{ragHealth.rerank_provider || 'unknown'}</Descriptions.Item>
                <Descriptions.Item label="Rerank path">{ragHealth.rerank_model_path || '未配置'}</Descriptions.Item>
                <Descriptions.Item label="Rerank path exists">{String(Boolean(ragHealth.rerank_model_path_exists))}</Descriptions.Item>
              </Descriptions>
            </SectionCard>
          </Col>
        </Row>
      )}

      {(activeSubKey === 'knowledge-rag' || activeSubKey === 'knowledge-qa') && (
        <Row gutter={[16, 16]} className="balanced-row">
          <Col xs={24} lg={7} xl={6}>
            <SectionCard title={activeSubKey === 'knowledge-qa' ? 'QA 测试' : '检索测试'}>
              <Input.TextArea rows={6} value={query} onChange={(event) => setQuery(event.target.value)} />
              <div className="search-config">
                <span>Top K = 5</span>
                <Button type="primary" loading={searching} icon={<SearchOutlined />} onClick={runSearch}>检索</Button>
              </div>
            </SectionCard>
          </Col>
          <Col xs={24} lg={10} xl={11}>
            <TableCard
              title="检索结果"
              loading={searching}
              dataSource={results.map((row, index) => ({ key: index, ...row }))}
              locale={{ emptyText: <EmptyState description="请先执行检索" /> }}
              pagination={false}
              columns={[
                { title: '文档', dataIndex: 'title' },
                { title: '分数', dataIndex: 'score' },
                { title: '片段', dataIndex: 'content', ellipsis: true },
                { title: '操作', render: (_, record: any) => <Button type="link" size="small" onClick={() => { setDetailData(record); setDetailOpen(true); }}>查看</Button> }
              ]}
            />
          </Col>
          <Col xs={24} lg={7}>
            <SectionCard title="AI 整理答案" extra={<Button type="link" onClick={() => navigator.clipboard?.writeText(answer)}>复制</Button>}>
              <div className="rag-answer">
                <p>{answer || '执行检索后生成整理答案。'}</p>
                <strong>依据来源</strong>
                <ol>{results.slice(0, 3).map((item) => <li key={item.chunk_id || item.title}>{item.title}</li>)}</ol>
              </div>
            </SectionCard>
          </Col>
        </Row>
      )}

      <DetailDrawer title="知识库详情" open={detailOpen} data={detailData} onClose={() => setDetailOpen(false)} />
    </div>
  );
}
