import type { MetricItem, TimePoint } from '../types/ui';

export const dashboardMock = {
  metrics: [
    { title: '明日最高价', value: '0.8921', unit: '元/kWh', trend: 12.45, trendLabel: '较今日', status: 'warning' },
    { title: '明日最低价', value: '0.2315', unit: '元/kWh', trend: -8.33, trendLabel: '较今日', status: 'success' },
    { title: '均价', value: '0.5128', unit: '元/kWh', trend: 3.21, trendLabel: '较今日', status: 'info' },
    { title: '峰谷价差', value: '0.6606', unit: '元/kWh', trend: 20.78, trendLabel: '较今日', status: 'info' },
    { title: '高价风险时段', value: '18:00 - 21:00', note: '风险等级：高', status: 'danger' },
    { title: '低价机会时段', value: '02:00 - 05:00', note: '机会等级：优', status: 'success' }
  ] as MetricItem[],
  priceCurve: [
    0.52, 0.43, 0.31, 0.27, 0.23, 0.29, 0.41, 0.38, 0.48, 0.42, 0.51, 0.57,
    0.62, 0.58, 0.55, 0.63, 0.74, 0.82, 0.89, 0.86, 0.84, 0.66, 0.61, 0.55
  ].map((value, index) => ({
    time: `${String(index).padStart(2, '0')}:00`,
    value,
    actual: value * (0.92 + (index % 4) * 0.02),
    upper: value + 0.09,
    lower: Math.max(value - 0.08, 0.1)
  })) as TimePoint[],
  storagePlan: [
    { key: '1', period: '00:00-02:00', action: '充电', power: '-40', revenue: '2,345.60' },
    { key: '2', period: '02:00-05:00', action: '充电', power: '-60', revenue: '4,582.30' },
    { key: '3', period: '05:00-10:00', action: '待机', power: '0', revenue: '0.00' },
    { key: '4', period: '10:00-17:00', action: '放电', power: '60', revenue: '5,712.80' },
    { key: '5', period: '17:00-21:00', action: '放电', power: '80', revenue: '8,965.40' },
    { key: '6', period: '21:00-24:00', action: '待机', power: '0', revenue: '0.00' }
  ],
  reports: [
    ['每日交易策略日报', '2025-06-21 08:30'],
    ['电价预测分析报告', '2025-06-21 07:45'],
    ['储能运行优化周报', '2025-06-20 17:30'],
    ['市场风险评估报告', '2025-06-20 16:20'],
    ['光伏出力预测报告', '2025-06-20 09:15']
  ],
  taskLogs: [
    ['电价预测任务', '完成', '06-21 10:20'],
    ['策略生成任务', '完成', '06-21 10:18'],
    ['数据同步任务', '完成', '06-21 10:15'],
    ['模型训练任务', '运行中', '06-21 10:10'],
    ['报告生成任务', '已取消', '06-21 10:05']
  ],
  risks: [
    { level: 'danger', title: '电价高峰预警', description: '18:00-21:00 电价预计显著高于均值', time: '10:15' },
    { level: 'warning', title: '负荷波动预警', description: '20:00 负荷波动幅度可能超过 15%', time: '09:48' },
    { level: 'warning', title: '可再生出力波动', description: '明日光伏出力存在较大不确定性', time: '09:30' },
    { level: 'info', title: '设备维护提醒', description: '储能系统将于 3 日后进行例行维护', time: '昨天 16:20' },
    { level: 'success', title: '市场信息更新', description: '华东电力市场规则已更新', time: '昨天 09:10' }
  ]
};
