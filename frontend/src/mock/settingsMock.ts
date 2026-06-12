import type { MetricItem } from '../types/ui';

export const settingsMock = {
  metrics: [
    { title: '在线用户数', value: 28, trend: 16.7, trendLabel: '较昨日', status: 'success' },
    { title: '角色数', value: 16, trend: 0, trendLabel: '较昨日', status: 'info' },
    { title: '已配置接口', value: 38, trend: 2, trendLabel: '较昨日', status: 'info' },
    { title: '系统健康度', value: '98.6', unit: '%', trend: 0.6, trendLabel: '较昨日', status: 'success' }
  ] as MetricItem[],
  users: [
    ['admin', '李满', '系统管理员', '平台运营部', '启用', '2025-06-21 10:18:23'],
    ['zhangsan', '张三', '交易员', '交易运营部', '启用', '2025-06-21 09:42:11'],
    ['lisi', '李四', '分析师', '策略分析部', '启用', '2025-06-21 08:55:07'],
    ['wangwu', '王五', '运维管理员', '运维部', '启用', '2025-06-20 17:33:54'],
    ['zhaoliu', '赵六', '只读用户', '战略发展部', '启用', '2025-06-20 16:22:31']
  ],
  permissions: [
    ['数据中心', true, true, true, true, true],
    ['预测中心', true, true, false, true, true],
    ['策略中心', true, true, true, true, true],
    ['AI助手', true, true, false, true, false],
    ['报告中心', true, true, true, true, true],
    ['模型中心', true, true, false, true, false],
    ['系统设置', true, false, false, false, false]
  ],
  apiConfigs: [
    ['电力交易市场API', 'https://api.marketpower.com/v1', '已启用'],
    ['气象数据接口', 'https://api.weather.com/v2', '已启用'],
    ['电价数据接口', 'https://api.prices.com/v1', '已启用']
  ],
  health: [
    ['服务状态', '正常'],
    ['数据库状态', '正常'],
    ['缓存状态', '正常'],
    ['磁盘使用率', '42%'],
    ['内存使用率', '63%'],
    ['CPU使用率', '28%']
  ]
};
