export interface ServiceState {
  dataSource?: string;
  error?: string;
  empty?: boolean;
  mockFallback?: boolean;
  fallbackReason?: string;
  partialErrors?: string[];
}

export function errorMessage(error: unknown) {
  if (error instanceof Error) return error.message;
  return String(error || '未知错误');
}

export function mockFallback<T extends object>(mock: T, error: unknown, fallbackReason = '真实接口请求失败，已切换到本地兜底数据。'): T & ServiceState {
  return {
    ...mock,
    dataSource: 'mock_fallback',
    error: errorMessage(error),
    empty: false,
    mockFallback: true,
    fallbackReason
  };
}

export function withServiceState<T extends object>(payload: T, state: ServiceState): T & ServiceState {
  return {
    ...payload,
    ...state,
    partialErrors: state.partialErrors?.filter(Boolean)
  };
}
