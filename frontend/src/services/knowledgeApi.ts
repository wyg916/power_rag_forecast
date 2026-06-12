import { knowledgeMock } from '../mock/knowledgeMock';
import { api } from '../api';
import { mockFallback, withServiceState } from './serviceState';

export async function getKnowledgeBaseData() {
  try {
    const stats = await api.knowledgeStats();
    const statData = stats?.data || stats || {};
    return withServiceState({
      ...knowledgeMock,
      dataSource: 'postgresql.kb_documents',
      metrics: [
        { ...knowledgeMock.metrics[0], value: statData.documents || 0 },
        { ...knowledgeMock.metrics[1], value: statData.chunks || 0, unit: '片' },
        { ...knowledgeMock.metrics[2], value: statData.available ? 0 : 1 },
        { ...knowledgeMock.metrics[3], value: statData.available ? '100.00' : '0.00', unit: '%' }
      ]
    }, {
      empty: !statData.available || (!Number(statData.documents || 0) && !Number(statData.chunks || 0)),
      mockFallback: false,
      fallbackReason: !statData.available ? '知识库接口可访问，但 PostgreSQL RAG 索引暂不可用。' : undefined
    });
  } catch (error) {
    return mockFallback(knowledgeMock, error, '知识库统计接口请求失败，已切换到本地兜底数据。');
  }
}

export async function searchKnowledge(q: string, topK = 5) {
  const payload = await api.knowledgeSearch(q, topK);
  return payload?.data || payload;
}
