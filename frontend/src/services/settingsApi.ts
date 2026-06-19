import { settingsMock } from '../mock/settingsMock';
import { api } from '../api';
import { mockFallback, withServiceState } from './serviceState';

const secretKeyPattern = /(key|secret|token|password|authorization)/i;

function sanitizeConfig(value: any, key = ''): any {
  if (Array.isArray(value)) return value.map((item) => sanitizeConfig(item, key));
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.entries(value).map(([itemKey, itemValue]) => [itemKey, sanitizeConfig(itemValue, itemKey)]));
  }
  if (secretKeyPattern.test(key) && value) return '******';
  return value;
}

function statusRow(name: string, ok: boolean, summary: string, detail: any = {}) {
  return {
    key: name,
    name,
    ok,
    status: ok ? '正常' : '需检查',
    summary,
    detail
  };
}

export async function getSettingsData(): Promise<any> {
  try {
    const partialErrors: string[] = [];
    const [configRaw, health, permissions, me, dbHealth, taskHealth, ragHealth, localModel] = await Promise.all([
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
      }),
      api.dbHealth().catch((error) => {
        partialErrors.push(error instanceof Error ? error.message : String(error));
        return null;
      }),
      api.tasksHealth().catch((error) => {
        partialErrors.push(error instanceof Error ? error.message : String(error));
        return null;
      }),
      api.knowledgeHealth().catch((error) => {
        partialErrors.push(error instanceof Error ? error.message : String(error));
        return null;
      }),
      api.localModelStatus().catch((error) => {
        partialErrors.push(error instanceof Error ? error.message : String(error));
        return null;
      })
    ]);
    const config = sanitizeConfig(configRaw || {});
    const roles = permissions?.roles || {};
    const taskOk = Boolean(taskHealth?.ok);
    const ragOk = Boolean(ragHealth && !ragHealth.fallback_enabled);
    const localModelOk = Boolean(localModel?.available || localModel?.ok);
    const systemStatus = [
      statusRow('认证', Boolean(me?.username), me?.username ? `${me.username} / ${me.role}` : '当前会话不可用', me),
      statusRow('数据库', Boolean(dbHealth?.ok), dbHealth?.message || dbHealth?.active || '数据库状态未知', dbHealth),
      statusRow('任务运行态', taskOk, `${taskHealth?.execution_mode || '--'}，running=${taskHealth?.running_task_count ?? 0}`, taskHealth),
      statusRow('RAG / BGE', ragOk, ragOk ? `dim=${ragHealth?.embedding_dim || '--'}，fallback=false` : `fallback：${(ragHealth?.fallback_reasons || []).join('；') || '状态未知'}`, ragHealth),
      statusRow('LLM', localModelOk, localModelOk ? `provider=${localModel?.provider || localModel?.model_provider || '--'}` : (localModel?.message || localModel?.reason || '本地模型或模型网关不可用'), sanitizeConfig(localModel || {})),
      statusRow('系统健康', health?.service === 'ok', health?.timestamp || 'settings health 未返回时间戳', health)
    ];
    return withServiceState({
      ...settingsMock,
      dataSource: 'runtime_config',
      config,
      healthRaw: health,
      dbHealth,
      taskHealth,
      ragHealth,
      localModel,
      systemStatus,
      currentUser: me,
      metrics: [
        { ...settingsMock.metrics[0], value: me ? 1 : 0, note: me?.username || '当前会话' },
        { ...settingsMock.metrics[1], value: Object.keys(roles).length || settingsMock.metrics[1].value },
        { ...settingsMock.metrics[2], value: Object.keys(config || {}).length || settingsMock.metrics[2].value },
        { ...settingsMock.metrics[3], value: systemStatus.filter((item) => item.ok).length, unit: `/${systemStatus.length}` }
      ],
      users: me ? [[me.username, me.username, me.role, me.auth_mode, '启用', '--']] : settingsMock.users,
      permissions: Object.entries(roles).map(([role, values]: any) => [role, values.includes('dashboard:read') || values.includes('*'), values.includes('task:run') || values.includes('*'), values.includes('settings:write') || values.includes('*'), values.includes('*'), values.includes('audit:read') || values.includes('*')]) || settingsMock.permissions,
      health: systemStatus.map((item) => [item.name, item.status, item.summary])
    }, {
      empty: !config,
      mockFallback: false,
      partialErrors
    });
  } catch (error) {
    return mockFallback(settingsMock, error, '系统设置接口请求失败，已切换到本地兜底配置。');
  }
}
