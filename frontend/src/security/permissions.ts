import type { RouteKey } from '../types/ui';

export interface CapabilityManifest {
  routes?: Partial<Record<RouteKey, boolean>>;
  actions?: Record<string, boolean>;
  generated_at?: string;
  policy_version?: string;
}

export const routePermissions: Record<RouteKey, string[]> = {
  dashboard: ['dashboard:read'],
  data: ['data:read'],
  forecast: ['forecast:read'],
  strategy: ['strategy:read'],
  assistant: ['assistant:use'],
  report: ['report:read'],
  model: ['model:read'],
  knowledge: ['knowledge:read'],
  task: ['task:read'],
  settings: ['settings:read']
};

export const childPermissions: Record<string, string[]> = {
  'dashboard-overview': ['dashboard:read'],
  'data-overview': ['data:read'],
  'data-quality': ['data:read'],
  'forecast-24h': ['forecast:read'],
  'forecast-history': ['forecast:read'],
  'forecast-model': ['forecast:read', 'model:read'],
  'strategy-high': ['strategy:read'],
  'strategy-storage': ['strategy:read'],
  'strategy-review': ['strategy:read', 'strategy:review'],
  'assistant-chat': ['assistant:use'],
  'assistant-tools': ['assistant:use'],
  'assistant-trace': ['assistant:use', 'trace:read'],
  'assistant-faq': ['assistant:use'],
  'report-daily': ['report:read'],
  'report-weekly': ['report:read'],
  'report-review': ['report:read', 'report:review'],
  'report-publish': ['report:read', 'report:review'],
  'model-active': ['model:read'],
  'model-candidate': ['model:read'],
  'model-error': ['model:read'],
  'model-rollback': ['model:read', 'model:manage'],
  'knowledge-policy': ['knowledge:read'],
  'knowledge-index': ['knowledge:read'],
  'knowledge-rag': ['knowledge:read'],
  'knowledge-qa': ['knowledge:read'],
  'task-schedule': ['task:read'],
  'task-log': ['task:read', 'task:diagnostics'],
  'task-alert': ['task:read', 'task:diagnostics'],
  'task-retry': ['task:read', 'task:diagnostics'],
  'settings-status': ['settings:read'],
  'settings-user': ['settings:read', 'user:read'],
  'settings-api': ['settings:read']
};

// Keys are the frozen capability-manifest action names returned by the
// backend; values are the endpoint permissions from API_PERMISSION_MATRIX.
export const actionPermissions: Record<string, string> = {
  'forecast.run': 'forecast:run',
  'data.export': 'data:export',
  'strategy.generate': 'strategy:generate',
  'report.generate': 'report:generate',
  'settings.write': 'settings:write',
  'assistant.use': 'assistant:use',
  'assistant.export': 'assistant:export'
};

export function hasAllPermissions(permissions: string[], required: string[] = []) {
  if (!required.length) return true;
  if (permissions.includes('*')) return true;
  return required.every((permission) => permissions.includes(permission));
}

export function hasAnyPermission(permissions: string[], required: string[] = []) {
  if (!required.length) return true;
  if (permissions.includes('*')) return true;
  return required.some((permission) => permissions.includes(permission));
}

export function canAccessRoute(
  route: RouteKey,
  permissions: string[],
  capabilityManifest?: CapabilityManifest | null
) {
  if (capabilityManifest?.routes?.[route] === false) return false;
  return hasAllPermissions(permissions, routePermissions[route]);
}

export function canAccessChild(childKey: string, permissions: string[]) {
  return hasAllPermissions(permissions, childPermissions[childKey] || []);
}

export function canPerformAction(
  action: string,
  permissions: string[],
  capabilityManifest?: CapabilityManifest | null
) {
  if (capabilityManifest?.actions?.[action] === false) return false;
  const permission = actionPermissions[action] || action;
  if (permissions.includes('*')) return true;
  return permissions.includes(permission);
}

export function permissionSnapshotHash(permissions: string[]) {
  const value = [...new Set(permissions)].sort().join('|');
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return `perm_${(hash >>> 0).toString(16).padStart(8, '0')}`;
}
