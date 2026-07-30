export interface ServiceState {
  dataSource?: string;
  error?: unknown;
  empty?: boolean;
  mockFallback?: boolean;
  fallbackReason?: string;
  partialErrors?: unknown[];
}

export function errorMessage(error: unknown) {
  if (error instanceof Error) return error.message;
  return String(error || '未知错误');
}

export function withServiceState<T extends object>(payload: T, state: ServiceState): T & ServiceState {
  return {
    ...payload,
    ...state,
    partialErrors: state.partialErrors?.filter(Boolean)
  };
}
