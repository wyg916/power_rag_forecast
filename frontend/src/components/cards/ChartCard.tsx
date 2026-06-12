import type { ReactNode } from 'react';
import { SectionCard } from './SectionCard';
import { EmptyState } from '../common/States';

interface ChartCardProps {
  title: ReactNode;
  extra?: ReactNode;
  children: ReactNode;
  hasData?: boolean;
  loading?: boolean;
  error?: ReactNode;
  minHeight?: number;
  height?: number | string;
  className?: string;
}

export function ChartCard({ title, extra, children, hasData = true, loading, error, minHeight = 320, height, className }: ChartCardProps) {
  return (
    <SectionCard title={title} extra={extra} minHeight={minHeight} height={height} className={className} loading={loading} error={error}>
      <div className="chart-card-body" style={{ minHeight }}>
        {hasData ? children : <EmptyState description="暂无图表数据" />}
      </div>
    </SectionCard>
  );
}
