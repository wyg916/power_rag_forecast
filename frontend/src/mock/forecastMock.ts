import type { MetricItem, TimePoint } from '../types/ui';

export const forecastMock = {
  metrics: [
    { title: '最高价', value: '0.9123', unit: '元/kWh', note: '出现在 18:30', status: 'warning' },
    { title: '最低价', value: '0.1824', unit: '元/kWh', note: '出现在 02:15-05:00', status: 'success' },
    { title: '均价', value: '0.5128', unit: '元/kWh', trend: 3.21, trendLabel: '较昨日', status: 'info' },
    { title: '峰谷价差', value: '0.7299', unit: '元/kWh', trend: 8.35, trendLabel: '较昨日', status: 'danger' },
    { title: '预测可信度', value: '86.7', unit: '%', trend: 2.4, trendLabel: '较昨日', status: 'success' }
  ] as MetricItem[],
  curve: [
    0.54, 0.46, 0.32, 0.24, 0.18, 0.25, 0.36, 0.58, 0.51, 0.39, 0.48, 0.68,
    0.64, 0.59, 0.55, 0.66, 0.78, 0.91, 0.96, 0.94, 0.99, 0.82, 0.72, 0.45
  ].map((value, index) => ({
    time: `${String(index).padStart(2, '0')}:00`,
    value,
    actual: value * (0.84 + (index % 5) * 0.03),
    upper: value + 0.12,
    lower: Math.max(value - 0.1, 0.1)
  })) as TimePoint[],
  history: [
    0.49, 0.42, 0.35, 0.26, 0.22, 0.31, 0.45, 0.63, 0.55, 0.43, 0.52, 0.66,
    0.62, 0.57, 0.53, 0.61, 0.74, 0.86, 0.92, 0.9, 0.87, 0.73, 0.64, 0.5
  ],
  detailRows: Array.from({ length: 12 }, (_, index) => ({
    key: String(index),
    time: `${String(index).padStart(2, '0')}:00-${String(index + 1).padStart(2, '0')}:00`,
    price: (0.2365 + index * 0.038).toFixed(4),
    risk: index >= 17 ? '高' : index <= 5 ? '低' : index % 3 === 0 ? '中' : '低',
    action: index <= 5 ? '建议增加采购' : index >= 9 ? '控制风险敞口' : '正常采购',
    confidence: `${(92 + (index % 5) * 0.7).toFixed(1)}%`
  })),
  insights: [
    ['低价采购窗口', '02:15-05:00', '预计电价处于全天低位区间，建议增加采购量。'],
    ['高风险时段', '17:30-20:30', '电价波动概率较高，存在价格快速上升风险。'],
    ['日内趋势', '午后持续抬升', '早间低位震荡，午后持续上行，晚间高位回落。']
  ]
};
