import { Card } from 'antd';
import type { ReactNode } from 'react';
import { EmptyState, ErrorState, LoadingBlock } from '../common/States';

interface SectionCardProps {
  title?: ReactNode;
  extra?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
  loading?: boolean;
  empty?: boolean;
  error?: ReactNode;
  minHeight?: number;
  height?: number | string;
  compact?: boolean;
  scrollable?: boolean;
}

export function SectionCard({ title, extra, children, className, bodyClassName, loading, empty, error, minHeight, height, compact, scrollable }: SectionCardProps) {
  const content = error ? <ErrorState message={error} /> : loading ? <LoadingBlock /> : empty ? <EmptyState /> : children;
  return (
    <Card
      className={`section-card ${compact ? 'section-card-compact' : ''} ${scrollable ? 'section-card-scrollable' : ''} ${className || ''}`}
      title={title}
      extra={extra}
      style={height ? { height } : undefined}
    >
      <div
        className={`section-card-body-content ${bodyClassName || ''}`.trim()}
        style={minHeight ? { minHeight } : undefined}
      >
        {content}
      </div>
    </Card>
  );
}
