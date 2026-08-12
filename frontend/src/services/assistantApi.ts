import { api, clearStoredAccessToken, downloadUrl, getStoredAccessToken } from '../api';
import { errorMessage, withServiceState } from './serviceState';

type StreamHandler = (event: string, payload: any) => void;

function authHeaders(json = true) {
  const token = getStoredAccessToken();
  return {
    ...(json ? { 'Content-Type': 'application/json' } : {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {})
  };
}

async function readError(response: Response) {
  const text = await response.text();
  try {
    const payload = JSON.parse(text);
    const detail = payload?.detail;
    return detail?.message || detail?.code || detail || payload?.message || text || `HTTP ${response.status}`;
  } catch {
    return text || `HTTP ${response.status}`;
  }
}

function handleUnauthorized(response: Response) {
  if (response.status === 401) {
    clearStoredAccessToken();
    window.dispatchEvent(new CustomEvent('auth:unauthorized'));
  }
}

const emptyAssistantAnswer = {
  question: '请选择常用问题或输入业务问题',
  conclusion: '输入问题后，AI 助手会基于后端工具调用、RAG 证据和只读查询结果生成结构化回答。',
  evidence: ['尚未发起问题，暂无数据依据。'],
  reason: '当前处于待提问状态，不展示任何预测数值、交易结论或业务回填结果。',
  suggestion: ['可从左侧常用问题开始，或直接输入电价预测、风险识别、策略建议、政策解读等问题。'],
  warning: '未取得可核验业务依据前，本页面不会生成或展示业务数值。'
};

export async function getAssistantData() {
  try {
    const sessions = await api.chatSessions();
    const rows = Array.isArray(sessions?.sessions) ? sessions.sessions : [];
    return withServiceState(
      {
        dataSource: 'postgresql.ai_chat_sessions',
        conversations: rows.map((item: any) => ({
          session_id: item.session_id,
          title: item.title || item.session_id || 'AI 会话',
          created_at: item.created_at,
          updated_at: item.updated_at
        })),
        answer: emptyAssistantAnswer,
        docs: [],
        modelRuns: []
      },
      {
        empty: !rows.length,
        mockFallback: false
      }
    );
  } catch (error) {
    return withServiceState(
      {
        conversations: [],
        answer: emptyAssistantAnswer,
        docs: [],
        modelRuns: []
      },
      {
        empty: true,
        mockFallback: false,
        error: errorMessage(error),
        fallbackReason: '会话历史接口暂时不可用，页面仅保留新问答入口。'
      }
    );
  }
}

export async function askAssistant(question: string, sessionId?: string, options: any = {}) {
  return api.chat(question, sessionId, options);
}

export async function askChatBI(question: string, sessionId: string, options: any = {}) {
  const response = await fetch(downloadUrl('/api/ai/chatbi/analyze'), {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({ question, session_id: sessionId, model_provider: options.model_provider || 'auto' })
  });
  if (!response.ok) {
    handleUnauthorized(response);
    throw new Error(String(await readError(response)));
  }
  return response.json();
}

export async function askAssistantStream(
  question: string,
  sessionId: string | undefined,
  options: any = {},
  onEvent: StreamHandler,
  signal?: AbortSignal
) {
  const response = await fetch(downloadUrl('/api/ai/chat/stream'), {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({ question, session_id: sessionId, ...options }),
    signal
  });
  if (!response.ok || !response.body) {
    handleUnauthorized(response);
    throw new Error(await readError(response));
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';
  let finalPayload: any;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split('\n\n');
    buffer = frames.pop() || '';
    for (const frame of frames) {
      const lines = frame.split('\n');
      const event = lines.find((line) => line.startsWith('event:'))?.slice(6).trim() || 'message';
      const dataText = lines
        .filter((line) => line.startsWith('data:'))
        .map((line) => line.slice(5).trim())
        .join('\n');
      const payload = dataText ? JSON.parse(dataText) : {};
      onEvent(event, payload);
      if (event === 'error') throw new Error(payload?.message || '流式问答返回错误');
      if (event === 'final') finalPayload = payload;
    }
  }

  return finalPayload;
}

export async function uploadAssistantAttachment(file: File, kind = 'attachment') {
  const body = new FormData();
  body.append('file', file);
  body.append('kind', kind);
  const response = await fetch(downloadUrl('/api/ai/attachments'), {
    method: 'POST',
    headers: authHeaders(false),
    body
  });
  if (!response.ok) {
    handleUnauthorized(response);
    throw new Error(await readError(response));
  }
  return response.json();
}

export async function exportAssistantConversation(format: 'docx' | 'pdf', payload: any) {
  const response = await fetch(downloadUrl(`/api/ai/chat/sessions/export?format=${format}`), {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    handleUnauthorized(response);
    throw new Error(await readError(response));
  }
  const disposition = response.headers.get('content-disposition') || '';
  const filename = disposition.match(/filename="?([^"]+)"?/i)?.[1] || `assistant_conversation.${format}`;
  return { blob: await response.blob(), filename };
}

export async function getAssistantReferenceOptions(query = '') {
  const settled = await Promise.allSettled([
    api.forecast24h(),
    api.strategyLatest(),
    api.reportLatest(),
    api.dataDatasets(query),
    api.knowledgeSearch(query || '电力交易', 5)
  ]);
  const options: Array<{ id: string; label: string; type: string; summary: string; payload?: any }> = [];

  const [forecast, strategy, report, datasets, knowledge] = settled;
  if (forecast.status === 'fulfilled') {
    options.push({ id: 'forecast_24h', label: '24小时预测结果', type: 'forecast', summary: '最新可用预测结果', payload: forecast.value });
  }
  if (strategy.status === 'fulfilled') {
    options.push({ id: 'strategy_latest', label: '最新购电策略', type: 'strategy', summary: '最新可用策略记录', payload: strategy.value });
  }
  if (report.status === 'fulfilled') {
    options.push({ id: 'report_latest', label: '最新分析报告', type: 'report', summary: '最新可用分析报告', payload: report.value });
  }
  if (datasets.status === 'fulfilled') {
    const rows = Array.isArray(datasets.value?.datasets) ? datasets.value.datasets : [];
    rows.slice(0, 8).forEach((item: any, index: number) => {
      const datasetId = item.dataset_id || `dataset_${index + 1}`;
      options.push({
        id: `dataset_${datasetId}`,
        label: item.display_name || datasetId,
        type: 'dataset',
        summary: item.description || '可用业务数据集',
        payload: item
      });
    });
  }
  if (knowledge.status === 'fulfilled') {
    const rows = Array.isArray(knowledge.value?.results) ? knowledge.value.results : Array.isArray(knowledge.value?.items) ? knowledge.value.items : [];
    rows.slice(0, 5).forEach((item: any, index: number) => {
      options.push({
        id: `knowledge_${item.id || item.title || index}`,
        label: item.title || item.source || `知识引用 ${index + 1}`,
        type: 'knowledge',
        summary: item.summary || item.content || '可用知识内容',
        payload: item
      });
    });
  }

  return options;
}
