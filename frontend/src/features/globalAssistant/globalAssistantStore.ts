import type { AssistantAttachmentRecord } from '../../services/assistantApi';

export interface GlobalAssistantMessage {
  id: string;
  role: 'user' | 'assistant';
  markdown: string;
  status: 'pending' | 'streaming' | 'completed' | 'cancelled' | 'failed';
  requestId?: string;
  citations?: any[];
  attachmentCitations?: any[];
}

export interface GlobalAssistantAttachment extends AssistantAttachmentRecord {
  client_id: string;
  file?: File;
  preview_url?: string;
}

export interface GlobalAssistantState {
  open: boolean;
  sessionId: string | null;
  draft: string;
  messages: GlobalAssistantMessage[];
  attachments: GlobalAssistantAttachment[];
  streaming: boolean;
  activeRequestId: string | null;
  includePageContext: boolean;
}

const STORAGE_KEY = 'power_trading_global_assistant_v2_12';
const listeners = new Set<() => void>();

const initialState: GlobalAssistantState = {
  open: false,
  sessionId: null,
  draft: '',
  messages: [],
  attachments: [],
  streaming: false,
  activeRequestId: null,
  includePageContext: true
};

function loadPersisted(): Partial<GlobalAssistantState> {
  try {
    if (typeof window === 'undefined') return {};
    const value = window.sessionStorage.getItem(STORAGE_KEY);
    if (!value) return {};
    const parsed = JSON.parse(value);
    return {
      sessionId: parsed.sessionId || null,
      draft: String(parsed.draft || ''),
      messages: Array.isArray(parsed.messages) ? parsed.messages : [],
      attachments: Array.isArray(parsed.attachments) ? parsed.attachments : [],
      includePageContext: parsed.includePageContext !== false
    };
  } catch {
    return {};
  }
}

let state: GlobalAssistantState = { ...initialState, ...loadPersisted() };

function persist(next: GlobalAssistantState) {
  try {
    if (typeof window === 'undefined') return;
    const attachments = next.attachments.map(({ file, preview_url, ...record }) => record);
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify({
      sessionId: next.sessionId,
      draft: next.draft,
      messages: next.messages,
      attachments,
      includePageContext: next.includePageContext
    }));
  } catch {
    // 浏览器禁用 sessionStorage 时仍保留当前运行期内存状态。
  }
}

function commit(updater: Partial<GlobalAssistantState> | ((current: GlobalAssistantState) => GlobalAssistantState)) {
  state = typeof updater === 'function' ? updater(state) : { ...state, ...updater };
  persist(state);
  listeners.forEach((listener) => listener());
}

export const globalAssistantStore = {
  getSnapshot: () => state,
  subscribe(listener: () => void) {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
  setOpen(open: boolean) {
    commit({ open });
  },
  setDraft(draft: string) {
    commit({ draft });
  },
  setIncludePageContext(includePageContext: boolean) {
    commit({ includePageContext });
  },
  setSessionId(sessionId: string | null) {
    commit({ sessionId });
  },
  setStreaming(streaming: boolean, activeRequestId: string | null = null) {
    commit({ streaming, activeRequestId });
  },
  appendMessage(message: GlobalAssistantMessage) {
    commit((current) => ({ ...current, messages: [...current.messages, message] }));
  },
  updateMessage(id: string, patch: Partial<GlobalAssistantMessage>) {
    commit((current) => ({
      ...current,
      messages: current.messages.map((message) => message.id === id ? { ...message, ...patch } : message)
    }));
  },
  replaceAttachment(clientId: string, attachment: GlobalAssistantAttachment) {
    commit((current) => ({
      ...current,
      attachments: current.attachments.map((item) => item.client_id === clientId ? attachment : item)
    }));
  },
  addAttachment(attachment: GlobalAssistantAttachment) {
    commit((current) => ({ ...current, attachments: [...current.attachments, attachment] }));
  },
  removeAttachment(clientId: string) {
    commit((current) => ({ ...current, attachments: current.attachments.filter((item) => item.client_id !== clientId) }));
  },
  newConversation() {
    state.attachments.forEach((item) => {
      if (item.preview_url) URL.revokeObjectURL(item.preview_url);
    });
    commit({
      ...initialState,
      open: true,
      includePageContext: state.includePageContext
    });
  },
  resetForTest() {
    state = { ...initialState };
    listeners.forEach((listener) => listener());
  }
};
