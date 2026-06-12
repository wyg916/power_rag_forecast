import type { MetricItem, TimePoint } from '../types/ui';

export const modelMock = {
  metrics: [
    { title: '当前 Active 模型', value: '负荷预测模型 v3.2.1', note: '启用时间：2025-06-15 09:00', status: 'success' },
    { title: 'Candidate 模型', value: '负荷预测模型 v3.3.0-rc1', note: '更新于：2025-06-21 08:30', status: 'warning' },
    { title: 'MAE', value: '12.35', unit: 'MW', trend: -8.21, trendLabel: '较昨日', status: 'success' },
    { title: 'RMSE', value: '18.74', unit: 'MW', trend: -6.47, trendLabel: '较昨日', status: 'info' },
    { title: '高峰误差', value: '3.21', unit: '%', trend: -5.12, trendLabel: '较昨日', status: 'warning' },
    { title: '最近训练时间', value: '2025-06-21 08:30', note: '数据区间：06-18 ~ 06-20', status: 'info' }
  ] as MetricItem[],
  comparison: [
    ['v3.2.1', '负荷预测模型', 'Active', '12.35', '18.74', '3.21', '2025-06-21 08:30'],
    ['v3.3.0-rc1', '负荷预测模型', 'Candidate', '11.62', '17.91', '2.98', '2025-06-21 08:30'],
    ['v3.1.4', '负荷预测模型', '已归档', '13.48', '20.31', '3.68', '2025-06-18 08:15'],
    ['v3.0.8', '负荷预测模型', '已归档', '14.22', '21.75', '3.94', '2025-06-15 08:05'],
    ['v2.9.6', '负荷预测模型', '已归档', '15.67', '24.30', '4.31', '2025-06-12 07:50']
  ],
  errorTrend: Array.from({ length: 30 }, (_, index) => ({
    time: `05-${String(22 + index).padStart(2, '0')}`,
    value: 23 - index * 0.32 + (index % 5) * 1.1,
    actual: 31 - index * 0.36 + (index % 4) * 1.4,
    baseline: 12 - index * 0.08 + (index % 6) * 0.3
  })) as TimePoint[],
  effect: Array.from({ length: 7 }, (_, day) => ({
    time: `06-${15 + day}`,
    value: 880 + (day % 3) * 110,
    actual: 850 + (day % 3) * 120,
    baseline: 40 - day * 2
  })) as TimePoint[],
  detail: {
    name: '负荷预测模型',
    type: '时间序列预测',
    granularity: '15分钟',
    horizon: '未来7天',
    features: ['历史负荷', '气象数据', '日历特征', '电价信号', '节假日特征'],
    algorithm: 'LightGBM + LSTM'
  }
};
