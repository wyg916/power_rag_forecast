import { api } from '../api';

export type KnowledgeData = {
  dataSource: string;
  stats: Record<string, any>;
  ragHealth: Record<string, any>;
  documents: any[];
  totalDocuments: number;
  releases: KnowledgeRelease[];
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
  status: 'candidate' | 'validated' | 'published' | 'superseded' | 'rolled_back' | 'failed';
  is_current: boolean;
  documents: number;
  chunks: number;
  isolated: number;
  duplicates: number;
  gates: { passed: number; total: number; ready: boolean };
  created_at?: string | null;
  updated_at?: string | null;
  published_at?: string | null;
  rolled_back_at?: string | null;
};

export async function getKnowledgeBaseData(): Promise<KnowledgeData> {
  const [statsPayload, documentsPayload, healthPayload, releasesPayload] = await Promise.all([
    api.knowledgeStats(),
    api.knowledgeDocuments({ page: 1, page_size: 50 }),
    api.knowledgeHealth(),
    api.knowledgeReleases()
  ]);
  const stats = statsPayload?.data || statsPayload || {};
  const documents = documentsPayload?.items || documentsPayload?.data?.items || [];
  const health = healthPayload?.data || healthPayload || {};
  const documentCount = stats.documents ?? health.kb_document_count ?? documentsPayload?.total ?? documents.length ?? 0;
  const chunkCount = stats.chunks ?? health.kb_chunk_count ?? 0;
  const pendingCount = stats.pending_documents ?? 0;
  const qaRate = stats.qa_pass_rate ?? 0;

  return {
    dataSource: '业务知识库',
    stats,
    ragHealth: health,
    documents,
    totalDocuments: documentsPayload?.total ?? documentCount,
    releases: releasesPayload?.items || [],
    empty: !Number(documentCount) && !Number(chunkCount),
    metrics: [
      { key: 'documents', title: '文档总数', value: documentCount, unit: '份', trend: '可检索资料', tone: 'info' },
      { key: 'indexed', title: '已索引', value: chunkCount, unit: 'chunks', trend: '知识片段', tone: 'success' },
      { key: 'pending', title: '待处理', value: pendingCount, unit: '份', trend: '索引队列', tone: pendingCount > 0 ? 'warning' : 'success' },
      { key: 'qa', title: 'QA 通过率', value: qaRate, unit: '%', trend: '最近校验', tone: Number(qaRate) >= 80 ? 'success' : 'warning' }
    ]
  };
}

export async function searchKnowledge(q: string, topK = 5) {
  return api.knowledgeQaTest({ question: q, top_k: topK });
}
