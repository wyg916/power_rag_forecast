import { AlertOutlined, ExclamationCircleOutlined, InfoCircleOutlined } from '@ant-design/icons';
import type { UiStatus } from '../../types/ui';

interface RiskAlertCardProps {
  level: UiStatus;
  title: string;
  description: string;
  time?: string;
}

export function RiskAlertCard({ level, title, description, time }: RiskAlertCardProps) {
  const icon = level === 'danger' ? <AlertOutlined /> : level === 'warning' ? <ExclamationCircleOutlined /> : <InfoCircleOutlined />;
  return (
    <div className={`risk-alert risk-${level}`}>
      <div className="risk-alert-icon">{icon}</div>
      <div>
        <div className="risk-alert-title">
          {title}
          {time && <span>{time}</span>}
        </div>
        <p>{description}</p>
      </div>
    </div>
  );
}
