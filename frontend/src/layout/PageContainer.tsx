import type { ReactNode } from 'react';
import { PageHeader } from '../components/common/PageHeader';

interface PageContainerProps {
  title: string;
  subtitle?: string;
  extra?: ReactNode;
  hideHeader?: boolean;
  children: ReactNode;
}

export function PageContainer({ title, subtitle, extra, hideHeader, children }: PageContainerProps) {
  return (
    <section className="page-container page-container-standard">
      {!hideHeader && <PageHeader title={title} subtitle={subtitle} extra={extra} />}
      {children}
    </section>
  );
}
