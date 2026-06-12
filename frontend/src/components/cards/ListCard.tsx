import { List } from 'antd';
import type { ListProps } from 'antd';
import type { ReactNode } from 'react';
import { SectionCard } from './SectionCard';

interface ListCardProps<T> extends ListProps<T> {
  title: ReactNode;
  extra?: ReactNode;
  minHeight?: number;
}

export function ListCard<T>({ title, extra, minHeight = 260, className, ...listProps }: ListCardProps<T>) {
  return (
    <SectionCard title={title} extra={extra} minHeight={minHeight}>
      <List<T> className={`compact-list ${className || ''}`} {...listProps} />
    </SectionCard>
  );
}
