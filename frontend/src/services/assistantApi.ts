import { api, clearStoredAccessToken, downloadUrl, getStoredAccessToken } from '../api';
import { errorMessage, withServiceState } from './serviceState';

const assistantAuthRequired = String(import.meta.env.VITE_AUTH_REQUIRED ?? '1') !== '0';
const assistantDevelopmentHeaders: Record<string, string> = assistantAuthRequired ? {} : {
  'X-User': String(import.meta.env.VITE_DEV_USERNAME || 'frontend-development-reader'),
  'X-Role': String(import.meta.env.VITE_DEV_ROLE || 'developer')
};

type StreamHandler = (event: string, payload: any) => void;

export type AssistantMode = 'general' | 'chatbi' | 'rag' | 'file' | 'vision';
export type KnowledgeScope = 'none' | 'authorized_enterprise' | 'attachments' | 'authorized_enterprise_and_attachments';
export type AttachmentStatus = 'uploading' | 'parsing' | 'ready' | 'failed' | 'cancelled' | 'deleted';

export interface AssistantPageContext {
  route_key: string;
  page_title: string;
  active_filters: Record<string, unknown>;
  selected_entity: { type: string; id: string } | null;
  visible_summary: Record<string, unknown>;
  permission_snapshot_hash: string;
}

export interface AssistantChatRequest {
  request_id: string;
  session_id: string | null;
  message: string;
  mode: AssistantMode;
  stream: boolean;
  requested_tier: 'standard' | 'premium';
  premium_confirmed: boolean;
  model_provider: 'auto' | 'kimi' | 'mimo' | 'deepseek' | 'ollama';
  answer_style?: string;
  attachment_ids: string[];
  page_context: AssistantPageContext | null;
  knowledge_scope: KnowledgeScope;
}

export interface AssistantAttachmentRecord {
  attachment_id: string;
  session_id?: string;
  file_name: string;
  media_type: string;
  size_bytes: number;
  status: AttachmentStatus;
  created_at?: string;
  expires_at?: string;
  error?: { code?: string; message?: string; retryable?: boolean } | string | null;
}

export function createAssistantRequestId() {
  const random = globalThis.crypto?.randomUUID?.() || `${Date.now().toString(36)}_${Math.random().toString(36).slice(2)}`;
  return `req_${random.replace(/-/g, '')}`;
}

export function buildAssistantChatRequest(
  message: string,
  options: Partial<AssistantChatRequest> = {}
): AssistantChatRequest {
  const attachmentIds = (options.attachment_ids || []).filter(Boolean);
  return {
    request_id: options.request_id || createAssistantRequestId(),
    session_id: options.session_id || null,
    message: message.trim(),
    mode: options.mode || (attachmentIds.length ? 'file' : 'general'),
    stream: options.stream ?? true,
    requested_tier: options.requested_tier || 'standard',
    premium_confirmed: options.premium_confirmed ?? false,
    model_provider: options.model_provider || 'auto',
    answer_style: options.answer_style,
    attachment_ids: attachmentIds,
    page_context: options.page_context || null,
    knowledge_scope: options.knowledge_scope || (attachmentIds.length ? 'attachments' : 'none')
  };
}

function authHeaders(json = true) {
  const token = getStoredAccessToken();
  return {
    ...(json ? { 'Content-Type': 'application/json' } : {}),
    ...assistantDevelopmentHeaders,
    ...(token ? { Authorization: `Bearer ${token}` } : {})
  };
}

async function readError(response: Response) {
  if (response.status === 401) return '登录状态已失效，请重新登录。';
  if (response.status === 403) return '当前账号未开通此项能力。';
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
  return api.chat(buildAssistantChatRequest(question, {
    ...options,
    session_id: sessionId || options.session_id || null,
    stream: false
  }) as unknown as Record<string, unknown>);
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
  const request = buildAssistantChatRequest(question, {
    ...options,
    session_id: sessionId || options.session_id || null,
    stream: true
  });
  const response = await fetch(downloadUrl('/api/ai/chat/stream'), {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(request),
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
  let streamedMarkdown = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.replace(/\r\n/g, '\n').split('\n\n');
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
      if (event === 'delta') streamedMarkdown += payload?.text || payload?.delta || payload?.markdown || '';
      if (event === 'error') throw new Error(payload?.error?.message || payload?.message || '流式问答返回错误');
      if (event === 'done') finalPayload = payload;
    }
  }

  if (!finalPayload) throw new Error('流式问答未返回完成事件。');
  return {
    ...finalPayload,
    request_id: finalPayload.request_id || request.request_id,
    answer: finalPayload.answer || { markdown: streamedMarkdown }
  };
}

export async function uploadAssistantAttachment(file: File, sessionId: string, kind = 'attachment') {
  const body = new FormData();
  body.append('file', file);
  body.append('session_id', sessionId);
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
  const payload = await response.json();
  return normalizeAttachmentRecord(payload, file);
}

function normalizeAttachmentRecord(payload: any, file?: File): AssistantAttachmentRecord {
  const record = payload?.attachment || payload?.data || payload || {};
  return {
    attachment_id: String(record.attachment_id || record.id || ''),
    session_id: record.session_id,
    file_name: String(record.file_name || record.filename || file?.name || '附件'),
    media_type: String(record.media_type || record.content_type || file?.type || 'application/octet-stream'),
    size_bytes: Number(record.size_bytes ?? record.size ?? file?.size ?? 0),
    status: (record.status || (record.attachment_id || record.id ? 'parsing' : 'failed')) as AttachmentStatus,
    created_at: record.created_at,
    expires_at: record.expires_at,
    error: record.error || null
  };
}

export async function getAssistantAttachment(attachmentId: string, sessionId?: string) {
  const query = sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : '';
  const response = await fetch(downloadUrl(`/api/ai/attachments/${encodeURIComponent(attachmentId)}${query}`), {
    headers: authHeaders(false)
  });
  if (!response.ok) {
    handleUnauthorized(response);
    throw new Error(await readError(response));
  }
  return normalizeAttachmentRecord(await response.json());
}

export async function deleteAssistantAttachment(attachmentId: string) {
  const response = await fetch(downloadUrl(`/api/ai/attachments/${encodeURIComponent(attachmentId)}`), {
    method: 'DELETE',
    headers: authHeaders(false)
  });
  if (!response.ok) {
    handleUnauthorized(response);
    throw new Error(await readError(response));
  }
  return normalizeAttachmentRecord(await response.json());
}

export async function sendAssistantFeedback(payload: {
  request_id?: string;
  session_id?: string | null;
  rating: 'up' | 'down';
}) {
  return api.chatFeedback(payload);
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
