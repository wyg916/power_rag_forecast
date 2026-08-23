import { Table } from 'antd';
import type { TableProps } from 'antd';
import type { ReactNode } from 'react';
import { EmptyState } from '../common/States';
import { SectionCard } from './SectionCard';

interface TableCardProps<T extends object> extends Omit<TableProps<T>, 'title'> {
  title: ReactNode;
  extra?: ReactNode;
  minHeight?: number;
  height?: number | string;
  empty?: boolean;
  scrollable?: boolean;
}

export function TableCard<T extends object>({
  title,
  extra,
  minHeight = 320,
  height,
  pagination,
  scroll,
  loading,
  empty,
  scrollable,
  locale,
  className,
  ...tableProps
}: TableCardProps<T>) {
  return (
    <SectionCard title={title} extra={extra} minHeight={minHeight} height={height} loading={Boolean(loading)} empty={empty} scrollable={scrollable}>
      <Table<T>
        size="small"
        scroll={scroll || { x: 'max-content' }}
        className={`public-data-table ${className || ''}`.trim()}
        pagination={pagination === undefined ? { pageSize: 8, showSizeChanger: false } : pagination}
        locale={locale || { emptyText: <EmptyState description="暂无表格数据" /> }}
        loading={false}
        {...tableProps}
      />
    </SectionCard>
  );
}
