import { ReloadOutlined } from '@ant-design/icons';
import { Button, Space } from 'antd';
import type { ReactNode } from 'react';

interface FilterBarProps {
  children: ReactNode;
  actions?: ReactNode;
  label?: ReactNode;
  className?: string;
  compact?: boolean;
  onReset?: () => void;
  resetText?: string;
}

export function FilterBar({
  children,
  actions,
  label = '筛选条件',
  className,
  compact,
  onReset,
  resetText = '重置'
}: FilterBarProps) {
  return (
    <div className={`filter-bar ${compact ? 'filter-bar-compact' : ''} ${className || ''}`}>
      <div className="filter-bar-main">
        {label && <div className="filter-bar-label">{label}</div>}
        <div className="filter-bar-controls">{children}</div>
      </div>
      {(actions || onReset) && (
        <Space className="filter-bar-actions" size={8} wrap>
          {onReset && <Button icon={<ReloadOutlined />} onClick={onReset}>{resetText}</Button>}
          {actions}
        </Space>
      )}
    </div>
  );
}
