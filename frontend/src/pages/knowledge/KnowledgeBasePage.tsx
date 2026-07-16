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
import { Alert, Button, Empty, Input, Select, Space, Table, Tag, Upload, message } from 'antd';
import { useEffect, useMemo, useState } from 'react';
import { api } from '../../api';
import { DetailDrawer } from '../../components/actions/DetailDrawer';
import { SectionCard } from '../../components/cards/SectionCard';
import { getKnowledgeBaseData, searchKnowledge, type KnowledgeData } from '../../services/knowledgeApi';
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

const dataSourceOptions = [{ value: 'postgresql_kb_documents', label: 'postgresql_kb_documents' }];

const defaultKnowledgeData: KnowledgeData = {
  dataSource: 'postgresql_kb_documents',
  stats: {},
  ragHealth: {},
  documents: [],
  totalDocuments: 0,
  empty: false,
  metrics: [
    { key: 'documents', title: '文档总数', value: 0, unit: '份', trend: '数据库文档', tone: 'info' },
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

function shortPath(value?: string) {
  const raw = String(value || '').trim();
  if (!raw) return '-';
  if (raw.length <= 42) return raw;
  return `${raw.slice(0, 18)}...${raw.slice(-18)}`;
}

function statusLabel(status?: string, fallback?: boolean) {
  const value = String(status || '').toLowerCase();
  if (fallback || value === 'fallback') return { text: '降级', color: 'warning' };
  if (value === 'normal') return { text: '正常', color: 'success' };
  if (value === 'partial') return { text: '部分完成', color: 'processing' };
  if (value === 'disabled') return { text: '未启用', color: 'default' };
  if (value === 'not_configured') return { text: '需配置', color: 'default' };
  return { text: '运行中', color: 'processing' };
}

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
  const [data, setData] = useState<KnowledgeData>(defaultKnowledgeData);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('分时电价、现货交易风险和购电建议是什么？');
  const [topK, setTopK] = useState(5);
  const [searching, setSearching] = useState(false);
  const [results, setResults] = useState<any[]>([]);
  const [answerBlocks, setAnswerBlocks] = useState<AnswerBlock[]>(normalizeAnswerBlocks(null));
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailData, setDetailData] = useState<Record<string, unknown> | null>(null);

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

  const ragHealth = data.ragHealth || {};
  const ragStatus = statusLabel(ragHealth.status, Boolean(ragHealth.fallback_enabled));
  const fallbackReasons = Array.isArray(ragHealth.fallback_reasons) ? ragHealth.fallback_reasons : [];
  const documentRows = useMemo(
    () =>
      (data.documents || []).map((row: any, index: number) => ({
        key: row.doc_id || `${row.title}-${index}`,
        name: row.title,
        source: row.category || row.source_type || '-',
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
  const metricIcons: Record<string, JSX.Element> = {
    documents: <FileTextOutlined />,
    indexed: <DatabaseOutlined />,
    pending: <FileDoneOutlined />,
    qa: <SafetyCertificateOutlined />
  };
  const metrics: KnowledgeMetric[] = data.metrics.map((item) => ({
    ...item,
    value: item.key === 'qa' ? formatPercent(item.value) : formatNumber(item.value),
    icon: metricIcons[item.key] || <DatabaseOutlined />
  }));

  const flowNodes = [
    { title: '文档上传', value: `${formatNumber(docCount)} 份文档`, icon: <FileTextOutlined /> },
    { title: '清洗切块', value: '已完成', icon: <PartitionOutlined /> },
    { title: '向量化', value: `${formatNumber(embeddedCount)} chunks`, icon: <DeploymentUnitOutlined /> },
    { title: '建索引', value: pendingCount > 0 ? '运行中' : '已完成', icon: <DatabaseOutlined /> },
    { title: '检索验证', value: `QA ${formatPercent(qaRate)}`, icon: <SafetyCertificateOutlined /> }
  ];

  return (
    <div className="knowledge-workbench-page">
      <div className="knowledge-top-workspace">
        <div className="knowledge-title-block">
          <h1>知识库</h1>
          <p>管理政策文档、RAG 检索、索引状态和 QA 测试</p>
        </div>

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

        <div className="knowledge-toolbar-card">
          <div className="knowledge-source-control">
            <span>数据源</span>
            <Select value="postgresql_kb_documents" options={dataSourceOptions} size="small" />
          </div>
          <Upload
            showUploadList={false}
            beforeUpload={(file) => {
              uploadDocument(file as File);
              return false;
            }}
            accept=".txt,.md,.csv,.json"
          >
            <Button className="knowledge-upload-button" icon={<CloudUploadOutlined />}>上传文档</Button>
          </Upload>
          <Space className="knowledge-toolbar-actions" size={8} wrap>
            <Button type="primary" loading={loading} icon={<SyncOutlined />} onClick={rebuildIndex}>重建索引</Button>
            <Button type="primary" loading={loading} icon={<ReloadOutlined />} onClick={refreshEmbeddings}>刷新 Embedding</Button>
            <Button loading={searching} icon={<SafetyCertificateOutlined />} onClick={batchValidate}>批量校验</Button>
            <Button icon={<DownloadOutlined />} onClick={exportResult}>导出结果</Button>
          </Space>
        </div>
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
              { title: '来源', dataIndex: 'source', width: 96, render: (value) => <Tag>{value}</Tag> },
              { title: '更新时间', dataIndex: 'updatedAt', width: 132 },
              { title: 'Chunk', dataIndex: 'chunks', width: 82 },
              { title: '状态', dataIndex: 'status', width: 92, render: documentStatusTag },
              {
                title: '操作',
                width: 124,
                render: (_, record: any) => (
                  <Space size={4}>
                    <Button type="link" size="small" onClick={() => { setDetailData(record.raw || record); setDetailOpen(true); }}>详情</Button>
                    <Button type="link" size="small" onClick={rebuildIndex}>重新索引</Button>
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
                <Tag color={ragStatus.color as any}>{ragStatus.text}</Tag>
              </div>
              <dl>
                <div><dt>索引总量</dt><dd>{formatNumber(chunkCount)} chunks</dd></div>
                <div><dt>已向量化</dt><dd>{formatNumber(embeddedCount)} chunks</dd></div>
                <div><dt>最近更新时间</dt><dd>{formatDate(ragHealth.last_embedding_refresh_at)}</dd></div>
                <div><dt>索引状态</dt><dd><Tag color={pendingCount > 0 ? 'processing' : 'success'}>{pendingCount > 0 ? '运行中' : '已完成'}</Tag></dd></div>
              </dl>
            </div>
            <div className="knowledge-rag-section">
              <div className="knowledge-rag-title">
                <strong>RAG 运行状态</strong>
                <Tag color={ragStatus.color as any}>{ragStatus.text}</Tag>
              </div>
              <p>Provider：{ragHealth.embedding_provider || 'unknown'} / {ragHealth.rerank_provider || 'unknown'}</p>
              <p>Embedding 维度：{ragHealth.embedding_dim || 0}；Chunks：{formatNumber(chunkCount)}；已向量化：{formatNumber(embeddedCount)}</p>
              <p title={ragHealth.embedding_model_path}>Embedding 路径：{shortPath(ragHealth.embedding_model_path)}（{ragHealth.embedding_model_path_exists ? '存在' : '未找到'}）</p>
              <p title={ragHealth.rerank_model_path}>Reranker 路径：{shortPath(ragHealth.rerank_model_path)}（{ragHealth.rerank_model_path_exists ? '存在' : '未找到'}）</p>
              {fallbackReasons.length > 0 && (
                <Alert type="warning" showIcon message="RAG 当前处于降级模式" description="部分本地模型或向量配置未满足完整运行条件，检索功能仍可使用。" />
              )}
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
          title={<Space size={8}>AI 整理答案 <Tag color="processing">后端生成</Tag></Space>}
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
