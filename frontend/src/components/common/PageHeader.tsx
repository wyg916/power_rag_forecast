import type { ReactNode } from 'react';

interface PageHeaderProps {
  title: string;
  subtitle?: string;
  extra?: ReactNode;
  eyebrow?: string;
}

export function PageHeader({ title, subtitle, extra, eyebrow = '统一工作台' }: PageHeaderProps) {
  return (
    <div className="page-heading">
      <div className="page-heading-main">
        <div className="page-eyebrow">{eyebrow}</div>
        <h1>{title}</h1>
        {subtitle && <p className="page-subtitle">{subtitle}</p>}
      </div>
      {extra && <div className="page-extra">{extra}</div>}
    </div>
  );
}
