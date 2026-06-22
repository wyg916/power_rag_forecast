import {
  CheckCircleOutlined,
  DatabaseOutlined,
  FileTextOutlined,
  LineChartOutlined,
  SafetyCertificateOutlined,
  ScheduleOutlined,
  ThunderboltOutlined
} from '@ant-design/icons';
import type { ReactNode } from 'react';
import { formatCompact, formatNumber, statusClass, statusText, toNumber } from './utils';

const iconMap: Record<string, ReactNode> = {
  supply_demand_risk: <SafetyCertificateOutlined />,
  forecast_confidence: <CheckCircleOutlined />,
  strategy_revenue: <ThunderboltOutlined />,
  report_pending: <FileTextOutlined />,
  task_reminder: <ScheduleOutlined />,
  data_health: <DatabaseOutlined />
};

function displayValue(item: any) {
  const num = toNumber(item?.value);
  if (num === null) return '--';
  if (item?.key === 'strategy_revenue') return `¥ ${formatCompact(num, 2)}`;
  if (item?.unit === '%') return formatNumber(num, 1);
  return formatCompact(num, item?.key === 'supply_demand_risk' ? 1 : 0);
}

export function HomeKpiStrip({ items = [] }: { items?: any[] }) {
  const visible = items.slice(0, 6);
  return (
    <section className="home-kpi-grid" aria-label="首页核心 KPI">
      {visible.map((item) => {
        const status = statusClass(item.status);
        return (
          <article className={`home-kpi-card home-kpi-${status}`} key={item.key || item.title}>
            <div className="home-kpi-top">
              <span className="home-kpi-icon">{iconMap[item.key] || <LineChartOutlined />}</span>
              <div>
                <h3>{item.title}</h3>
                <span className={`home-status-pill ${status}`}>{statusText(item.status)}</span>
              </div>
            </div>
            <div className="home-kpi-value">
              <strong>{displayValue(item)}</strong>
              {item.unit && item.key !== 'strategy_revenue' ? <span>{item.unit}</span> : null}
            </div>
            <p>{item.trend_label || item.data_source || '真实接口数据'}</p>
          </article>
        );
      })}
    </section>
  );
}
