import { ArrowDownOutlined, ArrowUpOutlined } from '@ant-design/icons';
import { Skeleton, Tooltip } from 'antd';
import type { MetricItem } from '../../types/ui';

const statusClass = {
  success: 'success',
  running: 'info',
  warning: 'warning',
  danger: 'danger',
  offline: 'offline',
  pending: 'warning',
  published: 'success',
  rejected: 'danger',
  info: 'info'
};

const statusLabel = {
  success: '正常',
  running: '运行中',
  warning: '关注',
  danger: '异常',
  offline: '离线',
  pending: '待处理',
  published: '已发布',
  rejected: '已驳回',
  info: '信息'
};

function summarizeValue(value: unknown) {
  const text = value === undefined || value === null || value === '' ? '--' : String(value);
  const timeParts = text.split('/').map((item) => item.trim()).filter(Boolean);
  if (timeParts.length >= 3) {
    return {
      display: `${timeParts.length} 个时段`,
      full: text,
      compact: true
    };
  }
  return {
    display: text,
    full: text,
    compact: text.length >= 14
  };
}

export function MetricCard({ title, value, unit, icon, trend, trendLabel, status = 'success', note, description, loading }: MetricItem & { loading?: boolean }) {
  const trendValue = Number(trend || 0);
  const isUp = trendValue >= 0;
  const cls = statusClass[status] || 'success';
  const summarized = summarizeValue(value);

  return (
    <div className={`metric-card metric-${cls}`}>
      <span className="metric-card-accent" />
      <div className="metric-icon">{icon}</div>
      <div className="metric-main">
        {loading ? (
          <Skeleton active paragraph={false} title={{ width: '80%' }} />
        ) : (
          <>
            <div className="metric-title-row">
              <div className="metric-title">{title}</div>
              <span className={`metric-status metric-status-${cls}`}>{statusLabel[status]}</span>
            </div>
            <Tooltip title={summarized.full !== summarized.display ? summarized.full : undefined}>
              <div className={`metric-value ${summarized.compact ? 'metric-value-compact' : ''}`}>
                <span className="metric-value-text">{summarized.display}</span>
                {unit && <span className="metric-unit">{unit}</span>}
              </div>
            </Tooltip>
            {(trend !== undefined || note) && (
              <div className="metric-note">
                {trend !== undefined && (
                  <span className={isUp ? 'trend-up' : 'trend-down'}>
                    {isUp ? <ArrowUpOutlined /> : <ArrowDownOutlined />}
                    {Math.abs(trendValue).toFixed(2)}%
                  </span>
                )}
                {trendLabel && <span>{trendLabel}</span>}
                {note && <span>{note}</span>}
              </div>
            )}
            {description && <div className="metric-description">{description}</div>}
          </>
        )}
      </div>
    </div>
  );
}
