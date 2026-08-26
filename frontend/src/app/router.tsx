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
import type { MenuGroup, MenuSection, RouteKey, RouteState } from '../types/ui';

export const menuGroups: MenuGroup[] = [
  {
    key: 'dashboard',
    label: '首页',
    icon: <HomeOutlined />,
    children: [{ key: 'dashboard-overview', label: '总览驾驶舱' }]
  },
  {
    key: 'data',
    label: '数据中心',
    icon: <DatabaseOutlined />,
    children: [
      { key: 'data-overview', label: '数据总览' },
      { key: 'data-quality', label: '数据质量 / 数据目录' }
    ]
  },
  {
    key: 'forecast',
    label: '预测中心',
    icon: <FundOutlined />,
    children: [
      { key: 'forecast-24h', label: '24小时预测' },
      { key: 'forecast-history', label: '历史对比' },
      { key: 'forecast-model', label: '峰谷分析 / 模型评估' }
    ]
  },
  {
    key: 'strategy',
    label: '策略中心',
    icon: <SafetyCertificateOutlined />,
    children: [
      { key: 'strategy-high', label: '总览' },
      { key: 'strategy-storage', label: '低价窗口与储能策略' },
      { key: 'strategy-review', label: '人工复核' }
    ]
  },
  {
    key: 'assistant',
    label: 'AI 助手',
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
      { key: 'settings-status', label: '系统状态总览' },
      { key: 'settings-user', label: '用户与权限管理' },
      { key: 'settings-api', label: '接口配置总览' }
    ]
  }
];

export const menuSections: MenuSection[] = [
  {
    key: 'home',
    label: '首页',
    description: '系统入口与总览驾驶舱',
    compact: true,
    routes: ['dashboard']
  },
  {
    key: 'business',
    label: '业务中心',
    description: '数据、预测、策略与报告',
    routes: ['data', 'forecast', 'strategy', 'report']
  },
  {
    key: 'intelligence',
    label: '智能应用',
    description: 'AI 助手与知识库检索',
    routes: ['assistant', 'knowledge']
  },
  {
    key: 'operations',
    label: '运营管理',
    description: '模型、任务与系统配置',
    routes: ['model', 'task', 'settings']
  }
];

export const routeTitles: Record<RouteKey, { title: string; subtitle: string }> = {
  dashboard: { title: '首页', subtitle: '预测、策略、风险、报告与任务的统一驾驶舱' },
  data: { title: '数据中心', subtitle: '管理数据接入、质量、数据库表与导入导出记录' },
  forecast: { title: '预测中心', subtitle: '查看未来 24 小时电价预测、历史对比和峰谷分析' },
  strategy: { title: '策略中心', subtitle: '展示高价风险、低价窗口、储能策略与复核清单' },
  assistant: { title: 'AI 助手 / 智能问答', subtitle: '面向电力交易分析、查数问答、策略解释与风险研判' },
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
    risk: 'dashboard-overview',
    shortcut: 'dashboard-overview'
  },
  data: {
    overview: 'data-overview',
    access: 'data-overview',
    'data-access': 'data-overview',
    catalog: 'data-quality',
    'data-catalog': 'data-quality',
    quality: 'data-quality',
    tables: 'data-quality',
    'data-tables': 'data-quality',
    import: 'data-overview',
    'data-import': 'data-overview'
  },
  forecast: {
    '24h': 'forecast-24h',
    '24h-forecast': 'forecast-24h',
    history: 'forecast-history',
    'forecast-history': 'forecast-history',
    detail: 'forecast-24h',
    'forecast-detail': 'forecast-24h',
    peak: 'forecast-model',
    'forecast-peak': 'forecast-model',
    model: 'forecast-model',
    'forecast-model': 'forecast-model'
  },
  strategy: {
    'high-risk': 'strategy-high',
    'strategy-low': 'strategy-storage',
    'low-window': 'strategy-storage',
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
    status: 'settings-status',
    user: 'settings-user',
    role: 'settings-user',
    param: 'settings-status',
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
