import type { ReactNode } from 'react';
import { PageHeader } from '../components/common/PageHeader';

interface PageContainerProps {
  title: string;
  subtitle?: string;
  extra?: ReactNode;
  children: ReactNode;
}

export function PageContainer({ title, subtitle, extra, children }: PageContainerProps) {
  return (
    <section className="page-container">
      <PageHeader title={title} subtitle={subtitle} extra={extra} />
      {children}
    </section>
  );
}
