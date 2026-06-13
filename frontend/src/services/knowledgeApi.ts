import { api } from '../api';
import { knowledgeMock } from '../mock/knowledgeMock';
import { mockFallback, withServiceState } from './serviceState';

export async function getKnowledgeBaseData() {
  try {
    const [stats, health] = await Promise.all([api.knowledgeStats(), api.knowledgeHealth()]);
    const statData = stats?.data || stats || {};
    const healthData = health?.data || health || {};
    return withServiceState(
      {
        ...knowledgeMock,
        dataSource: 'postgresql.kb_documents',
        ragHealth: healthData,
        metrics: [
          { ...knowledgeMock.metrics[0], value: statData.documents || healthData.kb_document_count || 0 },
          { ...knowledgeMock.metrics[1], value: statData.chunks || healthData.kb_chunk_count || 0, unit: 'chunks' },
          { ...knowledgeMock.metrics[2], value: statData.available ? 0 : 1 },
          { ...knowledgeMock.metrics[3], value: statData.available ? '100.00' : '0.00', unit: '%' }
        ]
      },
      {
        empty: !statData.available || (!Number(statData.documents || 0) && !Number(statData.chunks || 0)),
        mockFallback: false,
        fallbackReason: !statData.available ? 'Knowledge index API is reachable, but PostgreSQL RAG index is unavailable.' : undefined
      }
    );
  } catch (error) {
    return mockFallback(knowledgeMock, error, 'Knowledge API request failed; switched to local fallback data.');
  }
}

export async function searchKnowledge(q: string, topK = 5) {
  const payload = await api.knowledgeSearch(q, topK);
  return payload?.data || payload;
}
