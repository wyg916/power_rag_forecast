import { api } from '../api';
import { withServiceState } from './serviceState';

type Loader<T> = () => Promise<T>;

async function optional<T>(label: string, loader: Loader<T>, errors: string[], fallback: T): Promise<T> {
  try {
    return await loader();
  } catch (error) {
    errors.push(`${label}: ${error instanceof Error ? error.message : String(error)}`);
    return fallback;
  }
}

export async function getSettingsData(options: { interfaceKeyword?: string } = {}): Promise<any> {
  const partialErrors: string[] = [];
  const [
    currentUser,
    sourceContext,
    statusOverview,
    statusSummary,
    healthDetails,
    runtimeConfig,
    checkRecords,
    taskQueueSnapshot,
    usersOverview,
    rolePermissions,
    securityPolicy,
    interfaceOverview,
    interfaceConfigs,
    interfaces,
    interfaceTestLogs,
    auditLogs
  ] = await Promise.all([
    optional('当前用户', api.securityMe, partialErrors, null),
    optional('最近成功业务上下文', api.sourceContext, partialErrors, null),
    optional('系统状态概览', api.settingsStatusOverview, partialErrors, {}),
    optional('运行状态摘要', api.settingsStatusSummary, partialErrors, { items: [] }),
    optional('系统健康明细', api.settingsHealthDetails, partialErrors, { items: [] }),
    optional('系统运行参数', api.settingsRuntimeConfig, partialErrors, { values: {}, categories: {}, items: [] }),
    optional('健康检查记录', () => api.settingsHealthCheckRecords(100), partialErrors, { items: [] }),
    optional('任务队列快照', api.settingsTaskQueueSnapshot, partialErrors, {}),
    optional('用户指标概览', api.settingsUsersOverview, partialErrors, {}),
    optional('角色权限矩阵', api.settingsRolePermissions, partialErrors, { roles: [], permissions: [], matrix: [] }),
    optional('密码与安全策略', api.settingsSecurityPolicy, partialErrors, { values: {}, items: [] }),
    optional('接口指标概览', api.settingsInterfaceOverview, partialErrors, {}),
    optional('接口配置卡片', () => api.settingsInterfaceConfigs({ keyword: options.interfaceKeyword, page_size: 100 }), partialErrors, { items: [], total: 0 }),
    optional('接口总览', () => api.settingsInterfaces({ keyword: options.interfaceKeyword, page_size: 100 }), partialErrors, { items: [], total: 0 }),
    optional('接口测试日志', () => api.settingsInterfaceTestLogs({ limit: 100 }), partialErrors, { items: [], total: 0 }),
    optional('操作审计', () => api.settingsAuditLogs(100), partialErrors, { items: [], total: 0 })
  ]);

  const configValues = runtimeConfig?.values || {};
  return withServiceState(
    {
      dataSource: 'backend_api',
      currentUser,
      sourceContext,
      statusOverview,
      statusSummary: statusSummary?.items || [],
      healthDetails: healthDetails?.items || [],
      runtimeConfig,
      healthRecords: checkRecords?.items || [],
      taskQueueSnapshot,
      usersOverview,
      rolePermissions,
      securityPolicy,
      interfaceOverview,
      interfaceConfigs: interfaceConfigs?.items || [],
      interfaces: interfaces?.items || [],
      interfaceTestLogs: interfaceTestLogs?.items || [],
      auditLogs: auditLogs?.items || [],
      config: {
        ...(runtimeConfig?.categories || {}),
        runtime: configValues,
        values: configValues,
        items: runtimeConfig?.items || []
      }
    },
    {
      empty: false,
      mockFallback: false,
      partialErrors
    }
  );
}
