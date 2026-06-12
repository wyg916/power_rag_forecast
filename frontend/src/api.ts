const API_BASE = import.meta.env.VITE_API_BASE_URL || '';
export const ACCESS_TOKEN_KEY = 'power_trading_access_token';

export function getStoredAccessToken() {
  return window.localStorage.getItem(ACCESS_TOKEN_KEY) || '';
}

export function setStoredAccessToken(token: string) {
  if (token) window.localStorage.setItem(ACCESS_TOKEN_KEY, token);
  else window.localStorage.removeItem(ACCESS_TOKEN_KEY);
}

export function clearStoredAccessToken() {
  window.localStorage.removeItem(ACCESS_TOKEN_KEY);
}

function responseErrorMessage(status: number, text: string) {
  if (!text) return `HTTP ${status}`;
  try {
    const payload = JSON.parse(text);
    const detail = payload?.detail || payload?.message || payload?.error;
    if (Array.isArray(detail)) return `[${status}] ${detail.map((item) => item.msg || JSON.stringify(item)).join('; ')}`;
    if (detail && typeof detail === 'object') return `[${status}] ${JSON.stringify(detail)}`;
    if (detail) return `[${status}] ${detail}`;
  } catch {
    // keep raw text below
  }
  return `[${status}] ${text}`;
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const token = getStoredAccessToken();
  const headers = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(options?.headers || {})
  };
  const response = await fetch(`${API_BASE}${path}`, {
    headers,
    ...options
  });
  if (!response.ok) {
    const text = await response.text();
    if (response.status === 401) {
      clearStoredAccessToken();
      window.dispatchEvent(new CustomEvent('auth:unauthorized'));
    }
    throw new Error(responseErrorMessage(response.status, text));
  }
  return response.json() as Promise<T>;
}

export function unwrapApi<T = any>(payload: any): T {
  if (payload && typeof payload === 'object' && 'code' in payload && 'data' in payload) {
    if (payload.code !== 0) throw new Error(payload.message || '接口返回失败');
    return payload.data as T;
  }
  return payload as T;
}

export function downloadUrl(path: string) {
  return `${API_BASE}${path}`;
}

export const api = {
  health: () => request<any>('/api/health'),
  authLogin: (payload: { username: string; password: string }) =>
    request<any>('/api/auth/login', { method: 'POST', body: JSON.stringify(payload) }),
  authMe: () => request<any>('/api/auth/me'),
  authLogout: () => request<any>('/api/auth/logout', { method: 'POST', body: '{}' }),
  authChangePassword: (payload: { old_password: string; new_password: string }) =>
    request<any>('/api/auth/change-password', { method: 'POST', body: JSON.stringify(payload) }),
  users: (params: Record<string, any> = {}) => {
    const search = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') search.set(key, String(value));
    });
    return request<any>(`/api/users${search.toString() ? `?${search}` : ''}`);
  },
  userRoles: () => request<any>('/api/users/roles'),
  createUser: (payload: any) => request<any>('/api/users', { method: 'POST', body: JSON.stringify(payload) }),
  updateUser: (userId: string, payload: any) =>
    request<any>(`/api/users/${encodeURIComponent(userId)}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  resetUserPassword: (userId: string, newPassword: string) =>
    request<any>(`/api/users/${encodeURIComponent(userId)}/reset-password`, {
      method: 'POST',
      body: JSON.stringify({ new_password: newPassword })
    }),
  disableUser: (userId: string) =>
    request<any>(`/api/users/${encodeURIComponent(userId)}`, { method: 'DELETE' }),
  dashboard: () => request<any>('/api/dashboard/summary'),
  dataStatus: () => request<any>('/api/data/status'),
  dataCatalog: (includeRuntime = false) => request<any>(`/api/data/catalog${includeRuntime ? '?include_runtime=true' : ''}`),
  dataFields: (table?: string, search?: string) => {
    const params = new URLSearchParams();
    if (table) params.set('table', table);
    if (search) params.set('search', search);
    return request<any>(`/api/data/fields${params.toString() ? `?${params}` : ''}`);
  },
  dataFreshness: (tables: string[] = []) => {
    const params = new URLSearchParams();
    tables.forEach((table) => params.append('tables', table));
    return request<any>(`/api/data/freshness${params.toString() ? `?${params}` : ''}`);
  },
  readOnlySql: (payload: { sql: string; params?: Record<string, any>; limit?: number }) =>
    request<any>('/api/data/sql/query', { method: 'POST', body: JSON.stringify(payload) }),
  dataRefresh: () => request<any>('/api/data/refresh', { method: 'POST', body: '{}' }),
  syncCoreData: () => request<any>('/api/data/sync-core', { method: 'POST', body: '{}' }),
  dataQuality: () => request<any>('/api/data/quality').then(unwrapApi),
  importExportRecords: () => request<any>('/api/data/import-export-records').then(unwrapApi),
  exportTableUrl: (tableName: string, search?: string) => {
    const params = new URLSearchParams();
    if (search) params.set('search', search);
    return downloadUrl(`/api/data/tables/${encodeURIComponent(tableName)}/export${params.toString() ? `?${params}` : ''}`);
  },
  databaseTables: (search?: string) => {
    const params = new URLSearchParams();
    if (search) params.set('search', search);
    return request<any>(`/api/data/tables${params.toString() ? `?${params}` : ''}`);
  },
  databaseTableRows: (tableName: string, options: any = {}) => {
    const params = new URLSearchParams();
    if (options.search) params.set('search', options.search);
    params.set('limit', String(options.limit || 100));
    params.set('offset', String(options.offset || 0));
    return request<any>(`/api/data/tables/${encodeURIComponent(tableName)}/rows?${params}`);
  },
  forecastLatest: () => request<any>('/api/forecast/latest'),
  runForecast: (mode = 'refresh_fast_forecast') =>
    request<any>('/api/forecast/run', { method: 'POST', body: JSON.stringify({ mode }) }),
  strategyLatest: () => request<any>('/api/strategy/latest'),
  generateStrategy: () => request<any>('/api/strategy/generate', { method: 'POST', body: '{}' }),
  strategyConfig: () => request<any>('/api/strategy/config').then(unwrapApi),
  saveStrategyConfig: (payload: any) => request<any>('/api/strategy/config', { method: 'POST', body: JSON.stringify(payload) }).then(unwrapApi),
  saveStrategyReview: (payload: any) => request<any>('/api/strategy/reviews', { method: 'POST', body: JSON.stringify(payload) }).then(unwrapApi),
  anomalyLatest: () => request<any>('/api/anomaly/latest'),
  explainAnomaly: () => request<any>('/api/anomaly/explain', { method: 'POST', body: '{}' }),
  chat: (question: string, session_id?: string, options: any = {}) =>
    request<any>('/api/ai/chat', { method: 'POST', body: JSON.stringify({ question, session_id, ...options }) }),
  agentAnalyze: (question: string, options: any = {}) =>
    request<any>('/api/ai/agent/analyze', { method: 'POST', body: JSON.stringify({ question, ...options }) }),
  chatFeedback: (payload: any) => request<any>('/api/ai/chat/feedback', { method: 'POST', body: JSON.stringify(payload) }),
  answerFeedback: (payload: any) => request<any>('/api/ai/feedback', { method: 'POST', body: JSON.stringify(payload) }),
  chatSessions: () => request<any>('/api/ai/chat/sessions'),
  aiInsights: () => request<any>('/api/ai/insights'),
  aiTraces: (limit = 30) => request<any>(`/api/ai/traces?limit=${limit}`),
  aiTraceDetail: (traceId: string) => request<any>(`/api/ai/traces/${encodeURIComponent(traceId)}`),
  predictionLatest: (market?: string, date?: string) => {
    const params = new URLSearchParams();
    if (market) params.set('market', market);
    if (date) params.set('date', date);
    return request<any>(`/api/prediction/latest${params.toString() ? `?${params}` : ''}`);
  },
  reportLatest: () => request<any>('/api/reports/latest'),
  reportDetail: (reportId: string) => request<any>(`/api/reports/${encodeURIComponent(reportId)}`),
  reportDownloadUrl: (reportId: string) => downloadUrl(`/api/reports/${encodeURIComponent(reportId)}/download`),
  generateReport: () => request<any>('/api/reports/generate', { method: 'POST', body: JSON.stringify({ run_id: 'latest' }) }),
  approveReport: (reportId: string, payload: any) =>
    request<any>(`/api/reports/${encodeURIComponent(reportId)}/approve`, { method: 'POST', body: JSON.stringify(payload) }),
  rejectReport: (reportId: string, payload: any) =>
    request<any>(`/api/reports/${encodeURIComponent(reportId)}/reject`, { method: 'POST', body: JSON.stringify(payload) }),
  publishReport: (reportId: string, payload: any) =>
    request<any>(`/api/reports/${encodeURIComponent(reportId)}/publish`, { method: 'POST', body: JSON.stringify(payload) }),
  reportReviews: (reportId: string) => request<any>(`/api/reports/${encodeURIComponent(reportId)}/reviews`),
  models: () => request<any>('/api/models/metrics'),
  modelErrors: () => request<any>('/api/models/errors'),
  retrainSuggestion: () => request<any>('/api/models/retrain-suggestion'),
  localModelStatus: () => request<any>('/api/ai/local-model/status'),
  knowledgeStats: () => request<any>('/api/knowledge/stats'),
  knowledgeSearch: (q: string, topK = 5) => {
    const params = new URLSearchParams({ q, top_k: String(topK) });
    return request<any>(`/api/knowledge/search?${params}`);
  },
  knowledgeIndexLocal: () => request<any>('/api/knowledge/index-local', { method: 'POST', body: '{}' }),
  knowledgeEmbeddingRefresh: () => request<any>('/api/knowledge/embedding-refresh', { method: 'POST', body: '{}' }),
  securityMe: () => request<any>('/api/security/me'),
  permissions: () => request<any>('/api/security/permissions'),
  auditLogs: (limit = 100, action?: string) => {
    const params = new URLSearchParams({ limit: String(limit) });
    if (action) params.set('action', action);
    return request<any>(`/api/audit/logs?${params}`);
  },
  settingsConfig: () => request<any>('/api/settings/config').then(unwrapApi),
  saveSettingsConfig: (payload: any) => request<any>('/api/settings/config', { method: 'POST', body: JSON.stringify(payload) }).then(unwrapApi),
  settingsHealth: () => request<any>('/api/settings/health').then(unwrapApi),
  runTask: (kind: string) => request<any>('/api/tasks/run', { method: 'POST', body: JSON.stringify({ kind }) }),
  createTask: (kind: string, payload: any = {}) => request<any>('/api/tasks', { method: 'POST', body: JSON.stringify({ kind, payload }) }),
  tasks: () => request<any>('/api/tasks'),
  taskDetail: (taskId: string) => request<any>(`/api/tasks/${encodeURIComponent(taskId)}`),
  taskCancel: (taskId: string) => request<any>(`/api/tasks/${encodeURIComponent(taskId)}/cancel`, { method: 'POST', body: '{}' }),
  taskRetry: (taskId: string) => request<any>(`/api/tasks/${encodeURIComponent(taskId)}/retry`, { method: 'POST', body: '{}' }),
  scheduledTasks: () => request<any>('/api/scheduled-tasks'),
  createScheduledTask: (payload: any) => request<any>('/api/scheduled-tasks', { method: 'POST', body: JSON.stringify(payload) }),
  deleteScheduledTask: (taskName: string) =>
    request<any>(`/api/scheduled-tasks/${encodeURIComponent(taskName)}`, { method: 'DELETE' }),
  taskLogs: async (taskId: string) => {
    const token = getStoredAccessToken();
    const response = await fetch(`${API_BASE}/api/tasks/${encodeURIComponent(taskId)}/logs`, {
      headers: token ? { Authorization: `Bearer ${token}` } : undefined
    });
    if (!response.ok) throw new Error(await response.text());
    return response.text();
  }
};
