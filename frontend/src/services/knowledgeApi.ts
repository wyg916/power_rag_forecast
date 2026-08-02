import { api } from '../api';

export type KnowledgeData = {
  stats: Record<string, any>;
  ragHealth: Record<string, any>;
  releases: KnowledgeRelease[];
  releaseError?: string;
  documents: any[];
  totalDocuments: number;
  metrics: Array<{
    key: string;
    title: string;
    value: string | number;
    unit?: string;
    trend: string;
    tone: 'success' | 'info' | 'warning' | 'danger';
  }>;
  empty?: boolean;
  error?: string;
};

export type KnowledgeRelease = {
  release_id: string;
  status: 'candidate' | 'validated' | 'published' | 'superseded' | 'rolled_back' | string;
  created_at: string;
  updated_at: string;
};

export async function getKnowledgeBaseData(): Promise<KnowledgeData> {
  const [statsPayload, documentsPayload, healthPayload, releaseResult] = await Promise.all([
    api.knowledgeStats(),
    api.knowledgeDocuments({ page: 1, page_size: 50 }),
    api.knowledgeHealth(),
    api.knowledgeReleases()
      .then((payload) => ({ payload, error: '' }))
      .catch((error) => ({ payload: null, error: error instanceof Error ? error.message : '版本信息加载失败' }))
  ]);
  const stats = statsPayload?.data || statsPayload || {};
  const documents = documentsPayload?.items || documentsPayload?.data?.items || [];
  const health = healthPayload?.data || healthPayload || {};
  const documentCount = stats.documents ?? health.kb_document_count ?? documentsPayload?.total ?? documents.length ?? 0;
  const chunkCount = stats.chunks ?? health.kb_chunk_count ?? 0;
  const pendingCount = stats.pending_documents ?? 0;
  const qaRate = stats.qa_pass_rate ?? 0;
  const releases = Array.isArray(releaseResult.payload?.items) ? releaseResult.payload.items : [];

  return {
    stats,
    ragHealth: health,
    releases,
    releaseError: releaseResult.error,
    documents,
    totalDocuments: documentsPayload?.total ?? documentCount,
    empty: !Number(documentCount) && !Number(chunkCount),
    metrics: [
      { key: 'documents', title: '文档总数', value: documentCount, unit: '份', trend: '知识资产', tone: 'info' },
      { key: 'indexed', title: '已索引', value: chunkCount, unit: 'chunks', trend: '知识片段', tone: 'success' },
      { key: 'pending', title: '待处理', value: pendingCount, unit: '份', trend: '索引队列', tone: pendingCount > 0 ? 'warning' : 'success' },
      { key: 'qa', title: 'QA 通过率', value: qaRate, unit: '%', trend: '最近校验', tone: Number(qaRate) >= 80 ? 'success' : 'warning' }
    ]
  };
}

export async function searchKnowledge(q: string, topK = 5) {
  return api.knowledgeQaTest({ question: q, top_k: topK });
}
