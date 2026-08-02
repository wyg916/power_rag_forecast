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
import { Alert, Button, Empty, Input, Modal, Select, Space, Table, Tag, Upload, message } from 'antd';
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
  stats: {},
  ragHealth: {},
  releases: [],
  documents: [],
  totalDocuments: 0,
  empty: false,
  metrics: [
    { key: 'documents', title: '文档总数', value: 0, unit: '份', trend: '知识资产', tone: 'info' },
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
  if (value === 'unavailable') return { text: '暂不可用', color: 'error' };
  if (fallback || value === 'fallback') return { text: '降级', color: 'warning' };
  if (value === 'normal') return { text: '正常', color: 'success' };
  if (value === 'partial') return { text: '部分完成', color: 'processing' };
  if (value === 'disabled') return { text: '未启用', color: 'default' };
  if (value === 'not_configured') return { text: '需配置', color: 'default' };
  return { text: '运行中', color: 'processing' };
}

function releaseStatus(status?: string) {
  const value = String(status || '').toLowerCase();
  if (value === 'candidate') return { label: '候选版本', gate: '待准入校验', color: 'gold' };
  if (value === 'validated') return { label: '准入已通过', gate: '可进入发布流程', color: 'blue' };
  if (value === 'published') return { label: '已发布', gate: '当前服务版本', color: 'green' };
  if (value === 'superseded') return { label: '已替换', gate: '保留回溯记录', color: 'default' };
  if (value === 'rolled_back') return { label: '已回滚', gate: '已退出服务', color: 'orange' };
  return { label: '状态未知', gate: '等待状态同步', color: 'default' };
}

function safeError(error: unknown, fallback: string) {
  const text = error instanceof Error ? error.message : String(error || '');
  if (/\b401\b|unauthorized|未登录/i.test(text)) return '登录状态已失效，请重新登录';
  if (/\b403\b|forbidden|permission|权限/i.test(text)) return '当前账号没有执行该操作的权限';
  if (/\b409\b|conflict/i.test(text)) return '当前版本状态不允许执行该操作，请刷新后重试';
  return fallback;
}

function documentStatusTag(value: string) {
  if (value === '索引中' || value === 'partial') return <Tag color="processing">索引中</Tag>;
  if (value === '待处理' || value === 'pending') return <Tag color="warning">待处理</Tag>;
  return <Tag color="success">已索引</Tag>;
}

function normalizeSearchItems(payload: any) {
  return Array.isArray(payload?.items) ? payload.items : [];
}

function businessSafeText(value: unknown) {
  return String(value || '')
    .replace(/真实可追踪\s*citation/gi, '可核验的知识依据')
    .replace(/\bcitations?\b/gi, '知识依据')
    .replace(/\bsource_type\b/gi, '来源分类')
    .replace(/\brun_id\b/gi, '分析批次')
    .replace(/\btrace_id\b/gi, '追踪批次');
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
    content: businessSafeText(item.content)
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
  const { authRequired, hasPermission } = useAuth();
  const canWriteKnowledge = !authRequired || hasPermission('knowledge:write');
  const canPublishKnowledge = !authRequired || hasPermission('knowledge:publish');
  const canDiagnoseKnowledge = !authRequired || hasPermission('knowledge:diagnose');
  const [messageApi, messageContextHolder] = message.useMessage();
  const [error, setError] = useState('');
  const [query, setQuery] = useState('分时电价、现货交易风险和购电建议是什么？');
  const [topK, setTopK] = useState(5);
  const [searching, setSearching] = useState(false);
  const [results, setResults] = useState<any[]>([]);
  const [answerBlocks, setAnswerBlocks] = useState<AnswerBlock[]>(normalizeAnswerBlocks(null));
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailTitle, setDetailTitle] = useState('知识库详情');
  const [detailData, setDetailData] = useState<Record<string, unknown> | null>(null);
  const [releaseActionLoading, setReleaseActionLoading] = useState('');

  async function loadData() {
    setLoading(true);
    setError('');
    try {
      setData(await getKnowledgeBaseData());
    } catch (err) {
      setError(safeError(err, '知识库数据加载失败，请稍后重试'));
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
      messageApi.success(res.task_id || res.indexed_documents ? '知识库索引任务已提交' : '知识库索引已更新');
      await loadData();
    } catch (err) {
      messageApi.error(safeError(err, '重建索引失败，请稍后重试'));
    } finally {
      setLoading(false);
    }
  }

  async function refreshEmbeddings() {
    setLoading(true);
    try {
      const res = await api.knowledgeEmbeddingRefresh();
      messageApi.success(res.task_id ? '知识向量更新任务已提交' : '知识向量已更新');
      await loadData();
    } catch (err) {
      messageApi.error(safeError(err, '知识向量更新失败，请稍后重试'));
    } finally {
      setLoading(false);
    }
  }

  async function runSearch() {
    const text = query.trim();
    if (!text) {
      messageApi.warning('请输入检索问题');
      return;
    }
    setSearching(true);
    try {
      const payload = await searchKnowledge(text, topK);
      const items = normalizeSearchItems(payload);
      setResults(items);
      setAnswerBlocks(normalizeAnswerBlocks(payload));
      if (!items.length) messageApi.info('未检索到可用证据');
      await loadData();
    } catch (err) {
      setResults([]);
      setAnswerBlocks(normalizeAnswerBlocks(null));
      messageApi.error(safeError(err, '检索失败，请稍后重试'));
    } finally {
      setSearching(false);
    }
  }

  async function uploadDocument(file: File) {
    setLoading(true);
    try {
      const res = await api.knowledgeUpload(file);
      messageApi.success(res.doc_id ? '文档已写入知识库' : `${file.name} 已完成上传`);
      await loadData();
    } catch (err) {
      messageApi.error(safeError(err, '上传失败，请稍后重试'));
    } finally {
      setLoading(false);
    }
  }

  async function batchValidate() {
    setSearching(true);
    try {
      const res = await api.knowledgeBatchValidate({ top_k: topK });
      messageApi.success(`批量校验完成：${res.passed}/${res.total} 通过`);
      await loadData();
    } catch (err) {
      messageApi.error(safeError(err, '批量校验失败，请稍后重试'));
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
      messageApi.error(safeError(err, '导出失败，请稍后重试'));
    }
  }

  async function openDiagnostics() {
    if (!canDiagnoseKnowledge) return;
    setDetailTitle('知识库诊断信息（受限）');
    setDetailOpen(true);
    setDetailData({ 状态: '正在加载诊断信息…' });
    try {
      const payload = await api.knowledgeDiagnostics();
      setDetailData(payload?.diagnostics || { 状态: '当前没有可用的诊断明细' });
    } catch (err) {
      setDetailData({ 状态: safeError(err, '诊断信息加载失败') });
    }
  }

  function runReleaseAction(release: KnowledgeRelease, action: 'validate' | 'publish' | 'rollback') {
    const labels = {
      validate: { title: '执行准入校验', content: '该操作将按后端质量门禁校验候选版本，不会自动发布。', ok: '开始校验' },
      publish: { title: '发布知识版本', content: '仅应发布已通过准入的版本。发布会切换线上检索版本，请确认评测与审批均已完成。', ok: '确认发布' },
      rollback: { title: '回滚知识版本', content: '回滚会退出当前服务版本并恢复上一可用版本，请确认已具备回滚依据。', ok: '确认回滚' }
    } as const;
    const copy = labels[action];
    Modal.confirm({
      title: copy.title,
      content: copy.content,
      okText: copy.ok,
      cancelText: '取消',
      okButtonProps: { danger: action === 'rollback' },
      onOk: async () => {
        setReleaseActionLoading(`${action}:${release.release_id}`);
        try {
          if (action === 'validate') await api.knowledgeReleaseValidate(release.release_id);
          if (action === 'publish') await api.knowledgeReleasePublish(release.release_id);
          if (action === 'rollback') await api.knowledgeReleaseRollback(release.release_id);
          messageApi.success(`${copy.title}已完成`);
          await loadData();
        } catch (err) {
          messageApi.error(safeError(err, `${copy.title}失败，请核对版本状态和准入条件`));
          throw err;
        } finally {
          setReleaseActionLoading('');
        }
      }
    });
  }

  const ragHealth = data.ragHealth || {};
  const ragStatus = statusLabel(ragHealth.status, Boolean(ragHealth.fallback_enabled));
  const degradedComponents = Array.isArray(ragHealth.degraded_components) ? ragHealth.degraded_components : [];
  const degradedLabels = degradedComponents.map((item: string) => ({
    embedding: '知识向量',
    reranker: '结果排序',
    release: '版本服务',
    retrieval: '知识检索',
    knowledge_store: '知识存储'
  }[item] || '知识服务'));
  const documentRows = useMemo(
    () =>
      (data.documents || []).map((row: any, index: number) => ({
        key: row.doc_id || `${row.title}-${index}`,
        name: row.title,
        category: row.category || '未分类',
        updatedAt: formatDate(row.updated_at || row.indexed_at),
        chunks: row.chunk_count ?? 0,
        status: row.status_label || row.status
      })),
    [data.documents]
  );
  const releases = useMemo(
    () => [...(data.releases || [])].sort((left, right) => String(right.updated_at).localeCompare(String(left.updated_at))),
    [data.releases]
  );
  const activeRelease = releases.find((item) => item.status === 'published');
  const latestRelease = activeRelease || releases[0];
  const latestReleaseStatus = releaseStatus(latestRelease?.status);
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
    unit: item.key === 'qa' || item.key === 'indexed' ? '' : item.unit,
    icon: metricIcons[item.key] || <DatabaseOutlined />
  }));

  const flowNodes = [
    { title: '文档上传', value: `${formatNumber(docCount)} 份文档`, icon: <FileTextOutlined /> },
    { title: '清洗切块', value: '已完成', icon: <PartitionOutlined /> },
    { title: '向量化', value: `${formatNumber(embeddedCount)} 个片段`, icon: <DeploymentUnitOutlined /> },
    { title: '建索引', value: pendingCount > 0 ? '运行中' : '已完成', icon: <DatabaseOutlined /> },
    { title: '检索验证', value: `QA ${formatPercent(qaRate)}`, icon: <SafetyCertificateOutlined /> }
  ];

  return (
    <div className="knowledge-workbench-page">
      {messageContextHolder}
      <PageHeader
        title="知识库"
        subtitle="统一管理知识资产、检索质量、版本准入与服务状态"
        filters={<div className="knowledge-source-control">
          <span>知识资产范围</span>
          <Tag color="blue">企业知识库</Tag>
        </div>}
        actions={[
          {
            key: 'rebuild',
            label: '重建索引',
            icon: <SyncOutlined />,
            type: 'primary',
            loading,
            disabled: !canWriteKnowledge,
            disabledReason: '当前账号无知识库维护权限',
            onClick: rebuildIndex
          },
          {
            key: 'embedding',
            label: '更新知识向量',
            icon: <ReloadOutlined />,
            loading,
            disabled: !canWriteKnowledge,
            disabledReason: '当前账号无知识库维护权限',
            onClick: refreshEmbeddings
          },
          { key: 'validate', label: '批量校验', icon: <SafetyCertificateOutlined />, loading: searching, collapseAtNarrow: true, onClick: batchValidate },
          { key: 'export', label: '导出结果', icon: <DownloadOutlined />, collapseAtNarrow: true, onClick: exportResult }
        ]}
        extra={<Upload
          disabled={!canWriteKnowledge}
          showUploadList={false}
          beforeUpload={(file) => {
            uploadDocument(file as File);
            return false;
          }}
          accept=".txt,.md,.csv,.json"
        >
          <Button className="knowledge-upload-button" disabled={!canWriteKnowledge} title={!canWriteKnowledge ? '当前账号无知识库维护权限' : undefined} icon={<CloudUploadOutlined />}>上传文档</Button>
        </Upload>}
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
              { title: '业务分类', dataIndex: 'category', width: 108, render: (value) => <Tag>{value}</Tag> },
              { title: '更新时间', dataIndex: 'updatedAt', width: 132 },
              { title: '片段', dataIndex: 'chunks', width: 76 },
              { title: '状态', dataIndex: 'status', width: 92, render: documentStatusTag },
              {
                title: '操作',
                width: 124,
                render: (_, record: any) => (
                  <Space size={4}>
                    <Button type="link" size="small" onClick={() => {
                      setDetailTitle('知识文档详情');
                      setDetailData({
                        文档名称: record.name,
                        业务分类: record.category,
                        更新时间: record.updatedAt,
                        知识片段数: record.chunks,
                        处理状态: record.status || '状态未知'
                      });
                      setDetailOpen(true);
                    }}>详情</Button>
                    <Button type="link" size="small" onClick={rebuildIndex}>重新索引</Button>
                  </Space>
                )
              }
            ]}
          />
        </SectionCard>

        <SectionCard
          title="版本治理与服务状态"
          className="knowledge-rag-panel"
          loading={loading}
          extra={canDiagnoseKnowledge ? <Button size="small" type="link" icon={<ApiOutlined />} onClick={openDiagnostics}>诊断信息</Button> : null}
        >
          <div className="knowledge-rag-content">
            <div className="knowledge-rag-section knowledge-release-summary">
              <div className="knowledge-rag-title">
                <strong>{activeRelease ? '当前服务版本' : '版本准入状态'}</strong>
                <Tag color={latestReleaseStatus.color}>{latestReleaseStatus.label}</Tag>
              </div>
              <dl>
                <div><dt>版本</dt><dd>{latestRelease?.release_id || '暂无可用版本'}</dd></div>
                <div><dt>准入结论</dt><dd>{latestReleaseStatus.gate}</dd></div>
                <div><dt>服务状态</dt><dd><Tag color={ragStatus.color as any}>{ragStatus.text}</Tag></dd></div>
                <div><dt>状态时间</dt><dd>{formatDate(latestRelease?.updated_at)}</dd></div>
              </dl>
              {!activeRelease && latestRelease && <Alert type="warning" showIcon message="当前没有已发布版本" description="候选版本仍需完成离线评测、准入校验和人工确认，知识检索将保持失败关闭。" />}
              {data.releaseError && <Alert type="error" showIcon message="版本信息暂不可用" description="页面不会把未知版本状态视为已发布，请稍后重试。" />}
            </div>

            <div className="knowledge-rag-section knowledge-release-list-section">
              <div className="knowledge-rag-title">
                <strong>版本记录</strong>
                <span>{releases.length} 个版本</span>
              </div>
              <div className="knowledge-release-list">
                {releases.length ? releases.slice(0, 4).map((release) => {
                  const meta = releaseStatus(release.status);
                  const action = release.status === 'candidate' ? 'validate' : release.status === 'validated' ? 'publish' : release.status === 'published' ? 'rollback' : null;
                  const actionLabel = action === 'validate' ? '准入校验' : action === 'publish' ? '发布' : action === 'rollback' ? '回滚' : '';
                  return (
                    <div className="knowledge-release-row" key={release.release_id}>
                      <div>
                        <strong>{release.release_id}</strong>
                        <span>{formatDate(release.updated_at)}</span>
                      </div>
                      <Tag color={meta.color}>{meta.label}</Tag>
                      {action && <Button
                        type="link"
                        size="small"
                        danger={action === 'rollback'}
                        disabled={!canPublishKnowledge}
                        title={!canPublishKnowledge ? '当前账号无版本发布权限' : undefined}
                        loading={releaseActionLoading === `${action}:${release.release_id}`}
                        onClick={() => runReleaseAction(release, action)}
                      >{actionLabel}</Button>}
                    </div>
                  );
                }) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无版本记录" />}
              </div>
            </div>

            <div className="knowledge-rag-section knowledge-service-summary">
              <div className="knowledge-rag-title">
                <strong>检索服务</strong>
                <Tag color={ragStatus.color as any}>{ragStatus.text}</Tag>
              </div>
              <dl>
                <div><dt>知识片段</dt><dd>{formatNumber(chunkCount)}</dd></div>
                <div><dt>可检索片段</dt><dd>{formatNumber(embeddedCount)}</dd></div>
                <div><dt>最近更新时间</dt><dd>{formatDate(ragHealth.last_embedding_refresh_at)}</dd></div>
                <div><dt>待处理文档</dt><dd>{formatNumber(pendingCount)}</dd></div>
              </dl>
              {degradedLabels.length > 0 && <Alert type="warning" showIcon message="部分知识服务暂不可用" description={`受影响能力：${Array.from(new Set(degradedLabels)).join('、')}。页面不会将降级结果标记为正常服务。`} />}
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
                render: (_, record: any) => <Button type="link" size="small" onClick={() => {
                  setDetailTitle('知识证据片段');
                  setDetailData({
                    文档名称: record.title || '未命名文档',
                    相关度: Number(record.final_score ?? record.score ?? 0).toFixed(3),
                    内容摘要: record.content || record.snippet || '暂无内容'
                  });
                  setDetailOpen(true);
                }}>查看片段</Button>
              }
            ]}
          />
        </SectionCard>

        <SectionCard
          title={<Space size={8}>AI 整理答案 <Tag color="processing">知识归纳</Tag></Space>}
          className="knowledge-answer-card"
          extra={<Button type="link" size="small" aria-label="复制知识答案" icon={<CopyOutlined />} onClick={() => navigator.clipboard?.writeText(answerBlocks.map((item) => `${item.title}：${item.content}`).join('\n'))}>复制</Button>}
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

      <DetailDrawer title={detailTitle} open={detailOpen} data={detailData} onClose={() => setDetailOpen(false)} />
    </div>
  );
}
