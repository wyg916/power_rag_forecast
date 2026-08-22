export type ViewState =
  | 'loading'
  | 'empty'
  | 'error'
  | 'stale'
  | 'success'
  | 'unauthorized'
  | 'forbidden';

export interface PageDataMeta {
  state: ViewState;
  source?: string;
  generatedAt?: string;
  updatedAt?: string;
  runId?: string;
  modelVersion?: string;
  featureVersion?: string;
  staleReason?: string;
  errorCode?: string;
  errorMessage?: string;
  canRetry?: boolean;
  emptyReason?: string;
  queryScope?: string;
}

interface ErrorDescriptor {
  status?: number;
  code?: string;
  message?: string;
}

export interface ResolvePageDataMetaInput {
  loading?: boolean;
  hasData?: boolean;
  empty?: boolean;
  error?: unknown;
  partialErrors?: unknown[];
  source?: string | null;
  generatedAt?: string | null;
  updatedAt?: string | null;
  runId?: string | null;
  modelVersion?: string | null;
  featureVersion?: string | null;
  isStale?: boolean;
  staleReason?: string | null;
  canRetry?: boolean;
  emptyReason?: string;
  queryScope?: string;
}

function textOrUndefined(value: unknown) {
  const text = String(value || '').trim();
  return text || undefined;
}

export function describeViewError(error: unknown): ErrorDescriptor {
  if (!error) return {};
  const candidate = error as {
    status?: unknown;
    code?: unknown;
    message?: unknown;
  };
  const message = textOrUndefined(candidate.message ?? error);
  const statusValue = Number(candidate.status);
  const status = Number.isInteger(statusValue) && statusValue >= 100 ? statusValue : undefined;
  const statusFromMessage = message?.match(/(?:HTTP|\[)\s*(401|403|4\d\d|5\d\d)/i);
  const resolvedStatus = status ?? (statusFromMessage ? Number(statusFromMessage[1]) : undefined);
  return {
    status: resolvedStatus,
    code: textOrUndefined(candidate.code) || (resolvedStatus ? `HTTP_${resolvedStatus}` : 'REQUEST_FAILED'),
    message
  };
}

export function resolvePageDataMeta(input: ResolvePageDataMetaInput): PageDataMeta {
  const {
    loading = false,
    hasData = false,
    empty = false,
    error,
    partialErrors = [],
    isStale = false,
    canRetry = true
  } = input;
  const errorDescriptor = describeViewError(error);
  const firstPartialError = partialErrors.find(Boolean);
  const partialDescriptor = describeViewError(firstPartialError);
  const descriptor = errorDescriptor.message ? errorDescriptor : partialDescriptor;
  const common = {
    source: textOrUndefined(input.source),
    generatedAt: textOrUndefined(input.generatedAt),
    updatedAt: textOrUndefined(input.updatedAt),
    runId: textOrUndefined(input.runId),
    modelVersion: textOrUndefined(input.modelVersion),
    featureVersion: textOrUndefined(input.featureVersion),
    queryScope: textOrUndefined(input.queryScope)
  };

  if (descriptor.status === 401) {
    return {
      ...common,
      state: 'unauthorized',
      errorCode: descriptor.code || 'HTTP_401',
      errorMessage: descriptor.message || '登录状态已失效，请重新登录。',
      canRetry: false
    };
  }
  if (descriptor.status === 403) {
    return {
      ...common,
      state: 'forbidden',
      errorCode: descriptor.code || 'HTTP_403',
      errorMessage: '当前账号未开通此项能力。',
      canRetry: false
    };
  }
  if (loading && !hasData) {
    return { ...common, state: 'loading', canRetry: false };
  }
  if (hasData && (loading || descriptor.message || isStale)) {
    const staleReason = textOrUndefined(input.staleReason)
      || (loading ? 'refresh_in_progress' : undefined)
      || (descriptor.message ? `refresh_failed: ${descriptor.message}` : undefined)
      || 'data_expired';
    return {
      ...common,
      state: 'stale',
      staleReason,
      errorCode: descriptor.message ? descriptor.code : undefined,
      errorMessage: descriptor.message,
      canRetry
    };
  }
  if (descriptor.message) {
    return {
      ...common,
      state: 'error',
      errorCode: descriptor.code || 'REQUEST_FAILED',
      errorMessage: descriptor.message,
      canRetry
    };
  }
  if (empty || !hasData) {
    return {
      ...common,
      state: 'empty',
      emptyReason: textOrUndefined(input.emptyReason) || '接口请求成功，但当前查询范围内没有有效记录。',
      canRetry
    };
  }
  return { ...common, state: 'success', canRetry };
}
