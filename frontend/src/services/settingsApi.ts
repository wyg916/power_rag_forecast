import { settingsMock } from '../mock/settingsMock';
import { api } from '../api';
import { mockFallback, withServiceState } from './serviceState';

export async function getSettingsData(): Promise<any> {
  try {
    const partialErrors: string[] = [];
    const [config, health, permissions, me] = await Promise.all([
      api.settingsConfig(),
      api.settingsHealth().catch((error) => {
        partialErrors.push(error instanceof Error ? error.message : String(error));
        return null;
      }),
      api.permissions().catch((error) => {
        partialErrors.push(error instanceof Error ? error.message : String(error));
        return null;
      }),
      api.securityMe().catch((error) => {
        partialErrors.push(error instanceof Error ? error.message : String(error));
        return null;
      })
    ]);
    const roles = permissions?.roles || {};
    return withServiceState({
      ...settingsMock,
      dataSource: 'runtime_config',
      config,
      healthRaw: health,
      currentUser: me,
      metrics: [
        { ...settingsMock.metrics[0], value: me ? 1 : 0, note: me?.username || '当前会话' },
        { ...settingsMock.metrics[1], value: Object.keys(roles).length || settingsMock.metrics[1].value },
        { ...settingsMock.metrics[2], value: Object.keys(config || {}).length || settingsMock.metrics[2].value },
        { ...settingsMock.metrics[3], value: health?.database === 'ok' ? '98.6' : '80.0', unit: '%' }
      ],
      users: me ? [[me.username, me.username, me.role, me.auth_mode, '启用', '--']] : settingsMock.users,
      permissions: Object.entries(roles).map(([role, values]: any) => [role, values.includes('dashboard:read') || values.includes('*'), values.includes('task:run') || values.includes('*'), values.includes('settings:write') || values.includes('*'), values.includes('*'), values.includes('audit:read') || values.includes('*')]) || settingsMock.permissions,
      health: health ? Object.entries(health).map(([key, value]) => [key, String(value)]) : settingsMock.health
    }, {
      empty: !config,
      mockFallback: false,
      partialErrors
    });
  } catch (error) {
    return mockFallback(settingsMock, error, '系统设置接口请求失败，已切换到本地兜底配置。');
  }
}
