import { EllipsisOutlined } from '@ant-design/icons';
import { Button, Dropdown, Space } from 'antd';
import type { MenuProps } from 'antd';
import type { ReactNode } from 'react';

export interface PageHeaderAction {
  key: string;
  label: ReactNode;
  icon?: ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  loading?: boolean;
  danger?: boolean;
  type?: 'primary' | 'default' | 'text' | 'link';
  collapseAtNarrow?: boolean;
  disabledReason?: string;
}

export interface PageHeaderProps {
  title: string;
  subtitle?: string;
  extra?: ReactNode;
  eyebrow?: string;
  navigation?: ReactNode;
  metadata?: ReactNode;
  filters?: ReactNode;
  actions?: PageHeaderAction[];
  moreLabel?: string;
  className?: string;
}

function HeaderActionButton({ action }: { action: PageHeaderAction }) {
  return (
    <Button
      icon={action.icon}
      type={action.type}
      danger={action.danger}
      disabled={action.disabled}
      loading={action.loading}
      title={action.disabled ? action.disabledReason : undefined}
      onClick={action.onClick}
    >
      {action.label}
    </Button>
  );
}

export function PageHeader({
  title,
  subtitle,
  extra,
  eyebrow,
  navigation,
  metadata,
  filters,
  actions = [],
  moreLabel = '更多',
  className
}: PageHeaderProps) {
  const visibleActions = actions.filter((action) => !action.collapseAtNarrow);
  const collapsibleActions = actions.filter((action) => action.collapseAtNarrow);
  const moreItems: MenuProps['items'] = collapsibleActions.map((action) => ({
    key: action.key,
    label: action.label,
    icon: action.icon,
    disabled: action.disabled || action.loading,
    danger: action.danger,
    title: action.disabled ? action.disabledReason : undefined,
    onClick: action.onClick
  }));

  return (
    <header className={`page-heading page-heading-unified ${className || ''}`}>
      <div className="page-heading-copy">
        <div className="page-heading-title-row">
          <div className="page-heading-main">
            {eyebrow && <div className="page-eyebrow">{eyebrow}</div>}
            <h1 title={title}>{title}</h1>
          </div>
        </div>
        {subtitle && <p className="page-subtitle">{subtitle}</p>}
        {navigation && <nav className="page-heading-navigation" aria-label={`${title}子页面导航`}>{navigation}</nav>}
      </div>
      {(metadata || filters || actions.length || extra) && (
        <div className="page-heading-utility">
          {metadata && <div className="page-heading-context">{metadata}</div>}
          {filters && <div className="page-heading-filters">{filters}</div>}
          {(actions.length || extra) && (
            <Space className="page-heading-actions" size={8}>
              {visibleActions.map((action) => <HeaderActionButton key={action.key} action={action} />)}
              {collapsibleActions.map((action) => (
                <span className="page-heading-secondary-action" key={action.key}>
                  <HeaderActionButton action={action} />
                </span>
              ))}
              {collapsibleActions.length ? (
                <Dropdown menu={{ items: moreItems }} trigger={['click']}>
                  <Button className="page-heading-more" icon={<EllipsisOutlined />}>{moreLabel}</Button>
                </Dropdown>
              ) : null}
              {extra}
            </Space>
          )}
        </div>
      )}
    </header>
  );
}
