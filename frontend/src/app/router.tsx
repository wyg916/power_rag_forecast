import {
  BookOutlined,
  DatabaseOutlined,
  FileTextOutlined,
  HomeOutlined,
  RobotOutlined,
  SafetyCertificateOutlined,
  ScheduleOutlined,
  SettingOutlined,
  ThunderboltOutlined,
  FundOutlined
} from '@ant-design/icons';
import type { MenuGroup, RouteKey, RouteState } from '../types/ui';

export const menuGroups: MenuGroup[] = [
  {
    key: 'dashboard',
    label: '首页',
    icon: <HomeOutlined />,
    children: [
      { key: 'dashboard-overview', label: '驾驶舱' },
      { key: 'dashboard-risk', label: '风险提醒' },
      { key: 'dashboard-shortcut', label: '快捷入口' }
    ]
  },
  {
    key: 'data',
    label: '数据中心',
    icon: <DatabaseOutlined />,
    children: [
      { key: 'data-access', label: '数据接入' },
      { key: 'data-quality', label: '数据质量' },
      { key: 'data-catalog', label: '数据目录' },
      { key: 'data-tables', label: '数据源表' },
      { key: 'data-import', label: '导入导出' }
    ]
  },
  {
    key: 'forecast',
    label: '预测中心',
    icon: <FundOutlined />,
    children: [
      { key: 'forecast-24h', label: '24小时预测' },
      { key: 'forecast-history', label: '历史对比' },
      { key: 'forecast-detail', label: '预测明细' },
      { key: 'forecast-peak', label: '峰谷分析' }
    ]
  },
  {
    key: 'strategy',
    label: '策略中心',
    icon: <SafetyCertificateOutlined />,
    children: [
      { key: 'strategy-high', label: '高价风险' },
      { key: 'strategy-low', label: '低价窗口' },
      { key: 'strategy-storage', label: '储能策略' },
      { key: 'strategy-review', label: '人工复核' }
    ]
  },
  {
    key: 'assistant',
    label: 'AI助手',
    icon: <RobotOutlined />,
    children: [
      { key: 'assistant-chat', label: '智能问答' },
      { key: 'assistant-tools', label: '工具调用' },
      { key: 'assistant-trace', label: 'Trace' },
      { key: 'assistant-faq', label: '常见问题' }
    ]
  },
  {
    key: 'report',
    label: '报告中心',
    icon: <FileTextOutlined />,
    children: [
      { key: 'report-daily', label: '日报' },
      { key: 'report-weekly', label: '周报' },
      { key: 'report-review', label: '审核' },
      { key: 'report-publish', label: '发布记录' }
    ]
  },
  {
    key: 'model',
    label: '模型中心',
    icon: <ThunderboltOutlined />,
    children: [
      { key: 'model-active', label: 'Active模型' },
      { key: 'model-candidate', label: '候选模型' },
      { key: 'model-error', label: '误差趋势' },
      { key: 'model-rollback', label: '模型回滚' }
    ]
  },
  {
    key: 'knowledge',
    label: '知识库',
    icon: <BookOutlined />,
    children: [
      { key: 'knowledge-policy', label: '政策文档' },
      { key: 'knowledge-index', label: '索引管理' },
      { key: 'knowledge-rag', label: 'RAG检索' },
      { key: 'knowledge-qa', label: 'QA测试' }
    ]
  },
  {
    key: 'task',
    label: '任务中心',
    icon: <ScheduleOutlined />,
    children: [
      { key: 'task-schedule', label: '任务调度' },
      { key: 'task-log', label: '运行日志' },
      { key: 'task-alert', label: '告警管理' },
      { key: 'task-retry', label: '失败重试' }
    ]
  },
  {
    key: 'settings',
    label: '系统设置',
    icon: <SettingOutlined />,
    children: [
      { key: 'settings-user', label: '用户权限' },
      { key: 'settings-role', label: '角色配置' },
      { key: 'settings-param', label: '参数配置' },
      { key: 'settings-api', label: '接口配置' }
    ]
  }
];

export const routeTitles: Record<RouteKey, { title: string; subtitle: string }> = {
  dashboard: { title: '首页', subtitle: '预测、策略、风险、报告与任务的统一驾驶舱' },
  data: { title: '数据中心', subtitle: '管理数据接入、质量、数据库表与导入导出记录' },
  forecast: { title: '预测中心', subtitle: '查看未来 24 小时电价预测、历史对比和峰谷分析' },
  strategy: { title: '策略中心', subtitle: '展示高价风险、低价窗口、储能策略与复核清单' },
  assistant: { title: 'AI助手', subtitle: '基于工具调用、知识库和 Trace 的售电交易智能问答' },
  report: { title: '报告中心', subtitle: '查看、审核与管理日报、周报和专题报告' },
  model: { title: '模型中心', subtitle: '管理预测模型生命周期、误差趋势和回滚操作' },
  knowledge: { title: '知识库', subtitle: '管理政策文档、RAG 检索、索引状态和 QA 测试' },
  task: { title: '任务中心', subtitle: '集中管理平台任务调度、运行日志、告警和失败重试' },
  settings: { title: '系统设置', subtitle: '配置平台用户、权限、参数、接口和系统健康信息' }
};

export function normalizeRoute(value: string | null): RouteKey {
  return normalizeRouteState(value).route;
}

export function getDefaultChildKey(route: RouteKey): string {
  return menuGroups.find((item) => item.key === route)?.children[0]?.key || `${route}-overview`;
}

const routeAliases: Record<string, RouteKey> = {
  home: 'dashboard',
  'data-center': 'data',
  'forecast-center': 'forecast',
  'strategy-center': 'strategy',
  'ai-assistant': 'assistant',
  'report-center': 'report',
  'model-center': 'model',
  'knowledge-base': 'knowledge',
  'task-center': 'task',
  'system-settings': 'settings'
};

const childAliases: Partial<Record<RouteKey, Record<string, string>>> = {
  dashboard: {
    overview: 'dashboard-overview',
    risk: 'dashboard-risk'
  },
  forecast: {
    '24h': 'forecast-24h',
    '24h-forecast': 'forecast-24h',
    history: 'forecast-history',
    detail: 'forecast-detail',
    peak: 'forecast-peak'
  },
  strategy: {
    'high-risk': 'strategy-high',
    'low-window': 'strategy-low',
    storage: 'strategy-storage',
    review: 'strategy-review'
  },
  assistant: {
    chat: 'assistant-chat',
    tools: 'assistant-tools',
    trace: 'assistant-trace',
    faq: 'assistant-faq'
  },
  report: {
    daily: 'report-daily',
    weekly: 'report-weekly',
    review: 'report-review',
    publish: 'report-publish'
  },
  model: {
    active: 'model-active',
    candidate: 'model-candidate',
    error: 'model-error',
    rollback: 'model-rollback'
  },
  knowledge: {
    policy: 'knowledge-policy',
    index: 'knowledge-index',
    rag: 'knowledge-rag',
    qa: 'knowledge-qa'
  },
  task: {
    schedule: 'task-schedule',
    log: 'task-log',
    alert: 'task-alert',
    retry: 'task-retry'
  },
  settings: {
    user: 'settings-user',
    role: 'settings-role',
    param: 'settings-param',
    api: 'settings-api'
  }
};

export function normalizeRouteState(value: string | null): RouteState {
  const hash = (value || '').replace(/^#\/?/, '');
  const [routePart, childPart] = hash.split('/').filter(Boolean);
  const route = menuGroups.some((item) => item.key === routePart)
    ? (routePart as RouteKey)
    : routeAliases[routePart || ''] || 'dashboard';
  const group = menuGroups.find((item) => item.key === route);
  const defaultChild = getDefaultChildKey(route);
  const normalizedChild = childAliases[route]?.[childPart || ''] || childPart;
  const childKey = group?.children.some((child) => child.key === normalizedChild) ? String(normalizedChild) : defaultChild;
  return { route, childKey };
}
