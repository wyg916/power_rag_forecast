import { api } from '../api';

type HomeApiKey = 'kpi' | 'risk' | 'strategy' | 'forecast' | 'tasks';

export interface HomeDashboardData {
  kpi?: any;
  risk?: any;
  strategy?: any;
  forecast?: any;
  tasks?: any;
  loadedAt: string;
  partialErrors: string[];
}

async function readEndpoint(key: HomeApiKey, request: () => Promise<any>) {
  try {
    return { key, value: await request() };
  } catch (error) {
    return {
      key,
      error: error instanceof Error ? error.message : String(error || '接口请求失败')
    };
  }
}

export async function loadHomeDashboard(): Promise<HomeDashboardData> {
  const results = await Promise.all([
    readEndpoint('kpi', api.dashboardKpi),
    readEndpoint('risk', api.riskSummary),
    readEndpoint('strategy', api.strategyToday),
    readEndpoint('forecast', api.forecast24h),
    readEndpoint('tasks', () => api.taskRecent(8))
  ]);
  const payload: HomeDashboardData = {
    loadedAt: new Date().toISOString(),
    partialErrors: []
  };
  results.forEach((item) => {
    if ('error' in item) {
      payload.partialErrors.push(`${item.key}: ${item.error}`);
      return;
    }
    payload[item.key] = item.value;
  });
  return payload;
}
