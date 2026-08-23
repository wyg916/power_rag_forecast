import type { ReactNode } from 'react';
import { Col, Row } from 'antd';
import { MetricCard } from '../cards/MetricCard';
import type { MetricItem } from '../../types/ui';

type ResponsiveSpan = number | { xs?: number; sm?: number; md?: number; lg?: number; xl?: number; xxl?: number };

interface PageSurfaceProps {
  children: ReactNode;
  className?: string;
}

interface ResponsiveGridProps {
  children: ReactNode;
  columns?: number;
  minColumnWidth?: number;
  className?: string;
  align?: 'start' | 'stretch';
}

interface AntGridProps {
  children: ReactNode;
  left?: ResponsiveSpan;
  right?: ResponsiveSpan;
  className?: string;
}

interface PanelGridProps {
  children: ReactNode;
  template?: string;
  className?: string;
  minColumnWidth?: number;
}

interface MetricGridProps {
  items: MetricItem[];
  icons?: ReactNode[];
  loading?: boolean;
  minColumnWidth?: number;
}

export function PageSurface({ children, className }: PageSurfaceProps) {
  return <div className={`unified-page ${className || ''}`}>{children}</div>;
}

export function ResponsiveGrid({ children, columns, minColumnWidth = 280, className, align = 'stretch' }: ResponsiveGridProps) {
  const style = {
    '--grid-min': `${minColumnWidth}px`,
    '--grid-columns': columns ? String(columns) : undefined
  } as React.CSSProperties;

  return (
    <div className={`responsive-grid responsive-grid-${align} ${className || ''}`} style={style}>
      {children}
    </div>
  );
}

export function PanelGrid({ children, template = 'minmax(0, 1fr)', className, minColumnWidth = 280 }: PanelGridProps) {
  const style = {
    '--panel-template': template,
    '--panel-min': `${minColumnWidth}px`
  } as React.CSSProperties;

  return (
    <div className={`panel-grid ${className || ''}`} style={style}>
      {children}
    </div>
  );
}

export function TwoColumnLayout({ children, left = { xs: 24, lg: 16, xl: 17 }, right = { xs: 24, lg: 8, xl: 7 }, className }: AntGridProps) {
  const nodes = Array.isArray(children) ? children : [children];
  return (
    <Row gutter={[12, 12]} className={`unified-row ${className || ''}`}>
      <Col {...(typeof left === 'number' ? { span: left } : left)}>{nodes[0]}</Col>
      <Col {...(typeof right === 'number' ? { span: right } : right)}>{nodes[1]}</Col>
    </Row>
  );
}

export function ThreeColumnLayout({ children, className }: PageSurfaceProps) {
  return <div className={`three-column-layout ${className || ''}`}>{children}</div>;
}

export function MetricGrid({ items, icons = [], loading, minColumnWidth = 180 }: MetricGridProps) {
  return (
    <ResponsiveGrid className="metric-grid" minColumnWidth={minColumnWidth}>
      {items.map((item, index) => (
        <MetricCard key={`${item.title}-${index}`} {...item} icon={item.icon || icons[index]} loading={loading || item.loading} />
      ))}
    </ResponsiveGrid>
  );
}
