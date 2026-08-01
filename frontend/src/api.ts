const API_BASE = import.meta.env.VITE_API_BASE_URL || '';
const AUTH_REQUIRED = String(import.meta.env.VITE_AUTH_REQUIRED ?? '1') !== '0';
const DEVELOPMENT_IDENTITY_HEADERS: Record<string, string> = AUTH_REQUIRED
  ? {}
  : {
      'X-User': String(import.meta.env.VITE_DEV_USERNAME || 'frontend-development-reader'),
      'X-Role': 'developer'
    };
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

export function sanitizeErrorMessage(value: unknown) {
  const raw = typeof value === 'string' ? value : JSON.stringify(value);
  return String(raw || '')
    .replace(/(Bearer)\s+[A-Za-z0-9._~+/=-]{8,}/gi, '$1 ******')
    .replace(/\beyJ[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{4,}\b/g, '[JWT REDACTED]')
    .replace(/sk-[A-Za-z0-9_-]{12,}/g, 'sk-******')
    .replace(/(postgresql(?:\+\w+)?:\/\/[^:\s/@]+:)([^@\s]+)(@)/gi, '$1******$3')
    .replace(/\b(password|passwd|pwd|access[_-]?token|refresh[_-]?token|jwt[_-]?secret(?:[_-]?key)?|api[_-]?key|database[_-]?url)\b(\s*[:=]\s*)([^\s,;]+)/gi, '$1$2******');
}

interface ParsedResponseError {
  message: string;
  code: string;
  requestId?: string;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId?: string;

  constructor(status: number, message: string, code = `HTTP_${status}`, requestId?: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.requestId = requestId;
  }
}

function responseError(status: number, text: string): ParsedResponseError {
  if (!text) return { message: `HTTP ${status}`, code: `HTTP_${status}` };
  try {
    const payload = JSON.parse(text);
    const detail = payload?.detail || payload?.message || payload?.error;
    const code = String(payload?.error_code || payload?.code || detail?.code || `HTTP_${status}`);
    const requestId = payload?.request_id || payload?.requestId;
    if (Array.isArray(detail)) {
      return {
        message: `[${status}] ${sanitizeErrorMessage(detail.map((item) => item.msg || JSON.stringify(item)).join('; '))}`,
        code,
        requestId
      };
    }
    if (detail && typeof detail === 'object') {
      return { message: `[${status}] ${sanitizeErrorMessage(detail)}`, code, requestId };
    }
    if (detail) return { message: `[${status}] ${sanitizeErrorMessage(detail)}`, code, requestId };
  } catch {
    // keep raw text below
  }
  return { message: `[${status}] ${sanitizeErrorMessage(text)}`, code: `HTTP_${status}` };
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const token = getStoredAccessToken();
  const headers = {
    'Content-Type': 'application/json',
    ...DEVELOPMENT_IDENTITY_HEADERS,
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(options?.headers || {})
  };
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers
  });
  if (!response.ok) {
    const text = await response.text();
    const parsed = responseError(response.status, text);
    if (response.status === 401) {
      clearStoredAccessToken();
      window.dispatchEvent(new CustomEvent('auth:unauthorized'));
    }
    throw new ApiError(response.status, parsed.message, parsed.code, parsed.requestId);
  }
  return response.json() as Promise<T>;
}

async function requestForm<T>(path: string, formData: FormData): Promise<T> {
  const token = getStoredAccessToken();
  const response = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: {
      ...DEVELOPMENT_IDENTITY_HEADERS,
      ...(token ? { Authorization: `Bearer ${token}` } : {})
    },
    body: formData
  });
  if (!response.ok) {
    const text = await response.text();
    const parsed = responseError(response.status, text);
    if (response.status === 401) {
      clearStoredAccessToken();
      window.dispatchEvent(new CustomEvent('auth:unauthorized'));
    }
    throw new ApiError(response.status, parsed.message, parsed.code, parsed.requestId);
  }
  return response.json() as Promise<T>;
}

async function requestBinaryResponse(path: string, options?: RequestInit): Promise<Response> {
  const token = getStoredAccessToken();
  const response = await fetch(`${API_BASE}${path}`, {
    ...(options || {}),
    headers: {
      ...DEVELOPMENT_IDENTITY_HEADERS,
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options?.headers || {})
    }
  });
  if (!response.ok) {
    const text = await response.text();
    const parsed = responseError(response.status, text);
    if (response.status === 401) {
      clearStoredAccessToken();
      window.dispatchEvent(new CustomEvent('auth:unauthorized'));
    }
    throw new ApiError(response.status, parsed.message, parsed.code, parsed.requestId);
  }
  return response;
}

async function requestBlob(path: string, options?: RequestInit): Promise<Blob> {
  return (await requestBinaryResponse(path, options)).blob();
}

async function requestDownload(path: string): Promise<{ blob: Blob; filename: string }> {
  const response = await requestBinaryResponse(path);
  const disposition = response.headers.get('content-disposition') || '';
  const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
  const plain = disposition.match(/filename="?([^";]+)"?/i)?.[1];
  let filename = plain || '';
  if (encoded) {
    try {
      filename = decodeURIComponent(encoded);
    } catch {
      filename = encoded;
    }
  }
  return { blob: await response.blob(), filename };
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
  dashboardOverview: () => request<any>('/api/dashboard/overview'),
  dashboardContext: () => request<any>('/api/dashboard/context'),
  dashboardKpis: () => request<any>('/api/dashboard/kpis'),
  dashboardSupplyDemandRisk24h: () => request<any>('/api/dashboard/supply-demand-risk-24h'),
  dashboardForecastMetrics: () => request<any>('/api/dashboard/forecast-metrics'),
  dashboardAiSuggestions: () => request<any>('/api/dashboard/ai-suggestions'),
  dashboardStrategyExecutionSummary: () => request<any>('/api/dashboard/strategy-execution-summary'),
  dashboardModelStatus: () => request<any>('/api/dashboard/model-status'),
  dashboardDataHealth: () => request<any>('/api/dashboard/data-health'),
  dashboardTaskReminders: (limit = 8) => request<any>(`/api/dashboard/task-reminders?limit=${limit}`),
  dashboardKpi: () => request<any>('/api/dashboard/kpi'),
  riskSummary: () => request<any>('/api/risk/summary'),
  dbHealth: () => request<any>('/api/db/health'),
  dataStatus: () => request<any>('/api/data/status'),
  dataCatalog: (includeRuntime = false) => request<any>(`/api/data/catalog${includeRuntime ? '?include_runtime=true' : ''}`),
  dataFields: (datasetId: string, search?: string) => {
    const params = new URLSearchParams();
    params.set('dataset_id', datasetId);
    if (search) params.set('search', search);
    return request<any>(`/api/data/fields${params.toString() ? `?${params}` : ''}`);
  },
  dataFreshness: (datasetIds: string[] = []) => {
    const params = new URLSearchParams();
    datasetIds.forEach((datasetId) => params.append('dataset_ids', datasetId));
    return request<any>(`/api/data/freshness${params.toString() ? `?${params}` : ''}`);
  },
  dataRefresh: () => request<any>('/api/data/refresh', { method: 'POST', body: '{}' }),
  syncCoreData: () => request<any>('/api/data/sync-core', { method: 'POST', body: '{}' }),
  dataQuality: () => request<any>('/api/data/quality'),
  importExportRecords: (page = 1, pageSize = 10) => {
    const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
    return request<any>(`/api/data/import-export-records?${params}`);
  },
  exportDatasetUrl: (datasetId: string, search?: string) => {
    const params = new URLSearchParams();
    if (search) params.set('search', search);
    return downloadUrl(`/api/data/datasets/${encodeURIComponent(datasetId)}/export${params.toString() ? `?${params}` : ''}`);
  },
  exportDataset: (datasetId: string, search?: string) => {
    const params = new URLSearchParams();
    if (search) params.set('search', search);
    return requestBlob(`/api/data/datasets/${encodeURIComponent(datasetId)}/export${params.toString() ? `?${params}` : ''}`);
  },
  dataDatasets: (search?: string) => {
    const params = new URLSearchParams();
    if (search) params.set('search', search);
    return request<any>(`/api/data/datasets${params.toString() ? `?${params}` : ''}`);
  },
  datasetRows: (datasetId: string, options: any = {}) => {
    const params = new URLSearchParams();
    if (options.search) params.set('search', options.search);
    if (options.filterField) params.set('filter_field', options.filterField);
    if (options.filterOperator) params.set('filter_operator', options.filterOperator);
    if (options.filterValue !== undefined && options.filterValue !== null) params.set('filter_value', String(options.filterValue));
    if (options.sort) params.set('sort', options.sort);
    if (options.direction) params.set('direction', options.direction);
    params.set('page', String(options.page || 1));
    params.set('page_size', String(options.pageSize || options.page_size || 20));
    return request<any>(`/api/data/datasets/${encodeURIComponent(datasetId)}/rows?${params}`);
  },
  forecastLatest: () => request<any>('/api/forecast/latest'),
  forecastRuns: (status = 'success', limit = 2) => {
    const params = new URLSearchParams({ status, limit: String(limit) });
    return request<any>(`/api/forecast/runs?${params}`);
  },
  forecastRunResults: (runId: string) =>
    request<any>(`/api/forecast/runs/${encodeURIComponent(runId)}/results`),
  sourceContext: (domain = 'electricity_day_ahead_price', runId = 'latest') => {
    const params = new URLSearchParams({ domain, run_id: runId });
    return request<any>(`/api/source/context?${params}`);
  },
  forecast24h: () => request<any>('/api/forecast/24h'),
  runForecast: (mode = 'refresh_fast_forecast') =>
    request<any>('/api/forecast/run', { method: 'POST', body: JSON.stringify({ mode }) }),
  strategyLatest: () => request<any>('/api/strategy/latest'),
  strategyToday: () => request<any>('/api/strategy/today'),
  strategyRuntimeFacts: () => request<any>('/api/strategy/runtime-facts'),
  generateStrategy: () => request<any>('/api/strategy/generate', { method: 'POST', body: '{}' }),
  strategyConfig: () => request<any>('/api/strategy/config').then(unwrapApi),
  saveStrategyConfig: (payload: any) => request<any>('/api/strategy/config', { method: 'POST', body: JSON.stringify(payload) }).then(unwrapApi),
  saveStrategyReview: (payload: any) => request<any>('/api/strategy/reviews', { method: 'POST', body: JSON.stringify(payload) }).then(unwrapApi),
  strategyGovernanceList: (options: any = {}) => {
    const params = new URLSearchParams();
    if (options.run_id) params.set('run_id', options.run_id);
    if (options.report_id) params.set('report_id', options.report_id);
    if (options.status) params.set('status', options.status);
    return request<any>(`/api/strategies${params.toString() ? `?${params}` : ''}`);
  },
  generateGovernedStrategy: (payload: { run_id: string; report_id: string }) => request<any>('/api/strategies/generate', { method: 'POST', body: JSON.stringify(payload) }),
  strategyEvidence: (strategyId: string) => request<any>(`/api/strategies/${encodeURIComponent(strategyId)}/evidence`),
  strategyReviews: (strategyId: string) => request<any>(`/api/strategies/${encodeURIComponent(strategyId)}/reviews`),
  strategyAction: (strategyId: string, action: string, payload: { request_id: string; review_comment: string }) => request<any>(`/api/strategies/${encodeURIComponent(strategyId)}/${encodeURIComponent(action)}`, { method: 'POST', body: JSON.stringify(payload) }),
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
  predictionDetail: (market?: string, date?: string) => {
    const params = new URLSearchParams();
    if (market) params.set('market', market);
    if (date) params.set('date', date);
    return request<any>(`/api/prediction/detail${params.toString() ? `?${params}` : ''}`);
  },
  marketHistory: (market?: string, start?: string, end?: string) => {
    const params = new URLSearchParams();
    if (market) params.set('market', market);
    if (start) params.set('start', start);
    if (end) params.set('end', end);
    return request<any>(`/api/market/history${params.toString() ? `?${params}` : ''}`);
  },
  modelExplain: (market?: string, date?: string) => {
    const params = new URLSearchParams();
    if (market) params.set('market', market);
    if (date) params.set('date', date);
    return request<any>(`/api/model/explain${params.toString() ? `?${params}` : ''}`);
  },
  riskLevel: (market?: string, date?: string) => {
    const params = new URLSearchParams();
    if (market) params.set('market', market);
    if (date) params.set('date', date);
    return request<any>(`/api/risk/level${params.toString() ? `?${params}` : ''}`);
  },
  reportLatest: () => request<any>('/api/reports/latest'),
  reports: (params: Record<string, any> = {}) => {
    const search = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') search.set(key, String(value));
    });
    return request<any>(`/api/reports${search.toString() ? `?${search}` : ''}`);
  },
  reportSummary: () => request<any>('/api/reports/summary'),
  reportDetail: (reportId: string) => request<any>(`/api/reports/${encodeURIComponent(reportId)}`),
  reportDownload: (reportId: string) => requestDownload(`/api/reports/${encodeURIComponent(reportId)}/download`),
  generateReport: () => request<any>('/api/reports/generate', { method: 'POST', body: JSON.stringify({ run_id: 'latest' }) }),
  regenerateReport: (reportId: string) =>
    request<any>(`/api/reports/${encodeURIComponent(reportId)}/regenerate`, { method: 'POST', body: JSON.stringify({}) }),
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
  modelCenterOverview: (params: Record<string, any> = {}) => {
    const search = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') search.set(key, String(value));
    });
    return request<any>(`/api/models/center/overview${search.toString() ? `?${search}` : ''}`);
  },
  modelCenterVersionDetail: (version: string) => request<any>(`/api/models/center/versions/${encodeURIComponent(version)}`),
  modelTrainingStart: (payload: any = {}) => request<any>('/api/models/center/training/start', { method: 'POST', body: JSON.stringify(payload) }),
  modelActivate: (payload: any) => request<any>('/api/models/center/activate', { method: 'POST', body: JSON.stringify(payload) }),
  modelRollback: (payload: any) => request<any>('/api/models/center/rollback', { method: 'POST', body: JSON.stringify(payload) }),
  modelCenterExport: () => requestBlob('/api/models/center/export'),
  modelBacktestSummary: () => request<any>('/api/models/backtest/summary'),
  modelFeatureSchema: () => request<any>('/api/models/feature-schema'),
  modelLeakageCheck: () => request<any>('/api/models/leakage-check'),
  localModelStatus: () => request<any>('/api/ai/local-model/status'),
  knowledgeStats: () => request<any>('/api/knowledge/stats'),
  knowledgeHealth: () => request<any>('/api/knowledge/health'),
  knowledgeDocuments: (params: Record<string, any> = {}) => {
    const search = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') search.set(key, String(value));
    });
    return request<any>(`/api/knowledge/documents${search.toString() ? `?${search}` : ''}`);
  },
  knowledgeSearch: (q: string, topK = 5) => {
    const params = new URLSearchParams({ q, top_k: String(topK) });
    return request<any>(`/api/knowledge/search?${params}`);
  },
  knowledgeSearchPost: (payload: any) => request<any>('/api/knowledge/search', { method: 'POST', body: JSON.stringify(payload) }),
  knowledgeQaTest: (payload: any) => request<any>('/api/knowledge/qa-test', { method: 'POST', body: JSON.stringify(payload) }),
  knowledgeBatchValidate: (payload: any = {}) => request<any>('/api/knowledge/batch-validate', { method: 'POST', body: JSON.stringify(payload) }),
  knowledgeUpload: (file: File) => {
    const form = new FormData();
    form.append('file', file);
    return requestForm<any>('/api/knowledge/upload', form);
  },
  knowledgeExport: () => requestBlob('/api/knowledge/export'),
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
  settingsStatusOverview: () => request<any>('/api/settings/status/overview'),
  settingsStatusSummary: () => request<any>('/api/settings/status/summary'),
  settingsHealthDetails: () => request<any>('/api/settings/status/health-details'),
  settingsRuntimeConfig: () => request<any>('/api/settings/runtime-config'),
  updateSettingsRuntimeConfig: (payload: any) => request<any>('/api/settings/runtime-config', { method: 'PUT', body: JSON.stringify(payload) }),
  settingsHealthCheckRecords: (limit = 100) => request<any>(`/api/settings/status/check-records?limit=${limit}`),
  settingsTaskQueueSnapshot: () => request<any>('/api/settings/status/task-queue-snapshot'),
  settingsUsersOverview: () => request<any>('/api/settings/users/overview'),
  settingsUsers: (params: Record<string, any> = {}) => {
    const search = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') search.set(key, String(value));
    });
    return request<any>(`/api/settings/users${search.toString() ? `?${search}` : ''}`);
  },
  createSettingsUser: (payload: any) => request<any>('/api/settings/users', { method: 'POST', body: JSON.stringify(payload) }),
  updateSettingsUser: (userId: string, payload: any) =>
    request<any>(`/api/settings/users/${encodeURIComponent(userId)}`, { method: 'PUT', body: JSON.stringify(payload) }),
  disableSettingsUser: (userId: string) =>
    request<any>(`/api/settings/users/${encodeURIComponent(userId)}/disable`, { method: 'POST', body: '{}' }),
  enableSettingsUser: (userId: string) =>
    request<any>(`/api/settings/users/${encodeURIComponent(userId)}/enable`, { method: 'POST', body: '{}' }),
  resetSettingsUserPassword: (userId: string, newPassword: string) =>
    request<any>(`/api/settings/users/${encodeURIComponent(userId)}/reset-password`, {
      method: 'POST',
      body: JSON.stringify({ new_password: newPassword })
    }),
  assignSettingsUserRole: (userId: string, role: string) =>
    request<any>(`/api/settings/users/${encodeURIComponent(userId)}/assign-role`, {
      method: 'POST',
      body: JSON.stringify({ role })
    }),
  deleteSettingsUser: (userId: string) =>
    request<any>(`/api/settings/users/${encodeURIComponent(userId)}`, { method: 'DELETE' }),
  settingsRolePermissions: () => request<any>('/api/settings/roles/permissions'),
  updateSettingsRolePermissions: (payload: any) =>
    request<any>('/api/settings/roles/permissions', { method: 'PUT', body: JSON.stringify(payload) }),
  settingsSecurityPolicy: () => request<any>('/api/settings/security-policy'),
  updateSettingsSecurityPolicy: (payload: any) =>
    request<any>('/api/settings/security-policy', { method: 'PUT', body: JSON.stringify(payload) }),
  settingsAuditLogs: (limit = 100, action?: string) => {
    const params = new URLSearchParams({ limit: String(limit) });
    if (action) params.set('action', action);
    return request<any>(`/api/settings/audit-logs?${params}`);
  },
  settingsInterfaceOverview: () => request<any>('/api/settings/interfaces/overview'),
  settingsInterfaceConfigs: (params: Record<string, any> = {}) => {
    const search = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') search.set(key, String(value));
    });
    return request<any>(`/api/settings/interfaces/configs${search.toString() ? `?${search}` : ''}`);
  },
  updateSettingsInterfaceConfig: (interfaceId: string, payload: any) =>
    request<any>(`/api/settings/interfaces/${encodeURIComponent(interfaceId)}`, { method: 'PUT', body: JSON.stringify(payload) }),
  testSettingsInterface: (interfaceId: string) =>
    request<any>(`/api/settings/interfaces/${encodeURIComponent(interfaceId)}/test`, { method: 'POST', body: '{}' }),
  testAllSettingsInterfaces: () => request<any>('/api/settings/interfaces/test-all', { method: 'POST', body: '{}' }),
  settingsInterfaces: (params: Record<string, any> = {}) => {
    const search = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') search.set(key, String(value));
    });
    return request<any>(`/api/settings/interfaces${search.toString() ? `?${search}` : ''}`);
  },
  settingsInterfaceTestLogs: (params: Record<string, any> = {}) => {
    const search = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') search.set(key, String(value));
    });
    return request<any>(`/api/settings/interfaces/test-logs${search.toString() ? `?${search}` : ''}`);
  },
  taskOverview: () => request<any>('/api/tasks/overview'),
  taskRuns: (params: Record<string, any> = {}) => {
    const search = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') search.set(key, String(value));
    });
    return request<any>(`/api/tasks/runs${search.toString() ? `?${search}` : ''}`);
  },
  taskRecentLogs: (params: Record<string, any> = {}) => {
    const search = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') search.set(key, String(value));
    });
    return request<any>(`/api/tasks/logs/recent${search.toString() ? `?${search}` : ''}`);
  },
  taskRetryRecent: (limit = 20) => request<any>(`/api/tasks/retry/recent?limit=${limit}`),
  taskQueueOverview: () => request<any>('/api/tasks/queues/overview'),
  taskTrend: (days = 7) => request<any>(`/api/tasks/trend?days=${days}`),
  taskStart: (payload: any) => request<any>('/api/tasks/start', { method: 'POST', body: JSON.stringify(payload) }),
  runTask: (kind: string, payload: any = {}) => request<any>('/api/tasks/run', { method: 'POST', body: JSON.stringify({ kind, payload }) }),
  createTask: (kind: string, payload: any = {}) => request<any>('/api/tasks', { method: 'POST', body: JSON.stringify({ kind, payload }) }),
  tasks: () => request<any>('/api/tasks'),
  taskRecent: (limit = 8) => request<any>(`/api/task/recent?limit=${limit}`),
  tasksHealth: () => request<any>('/api/tasks/health'),
  taskDetail: (taskId: string) => request<any>(`/api/tasks/${encodeURIComponent(taskId)}`),
  taskCancel: (taskId: string, reason = '前端用户请求取消') => request<any>(`/api/tasks/${encodeURIComponent(taskId)}/cancel`, { method: 'POST', body: JSON.stringify({ reason }) }),
  taskRetry: (taskId: string) => request<any>(`/api/tasks/${encodeURIComponent(taskId)}/retry`, { method: 'POST', body: '{}' }),
  scheduledTasks: () => request<any>('/api/scheduled-tasks'),
  createScheduledTask: (payload: any) => request<any>('/api/scheduled-tasks', { method: 'POST', body: JSON.stringify(payload) }),
  deleteScheduledTask: (taskName: string) =>
    request<any>(`/api/scheduled-tasks/${encodeURIComponent(taskName)}`, { method: 'DELETE' }),
  taskLogs: (taskId: string, page = 1, pageSize = 50) =>
    request<any>(`/api/tasks/${encodeURIComponent(taskId)}/logs?page=${page}&page_size=${pageSize}`)
};
