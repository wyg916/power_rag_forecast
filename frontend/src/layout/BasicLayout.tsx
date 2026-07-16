import { Layout } from 'antd';
import { useCallback, useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { api } from '../api';
import { FactStatusBar } from '../components/common/States';
import { HeaderBar } from './HeaderBar';
import { Sidebar } from './Sidebar';
import type { RouteKey } from '../types/ui';

interface SourceContextResponse {
  meta: Parameters<typeof FactStatusBar>[0]['meta'] extends infer T ? NonNullable<T> : never;
}

interface BasicLayoutProps {
  route: RouteKey;
  activeSubKey: string;
  collapsed: boolean;
  onCollapse: () => void;
  onNavigate: (route: RouteKey, childKey?: string) => void;
  children: ReactNode;
}

export function BasicLayout({ route, activeSubKey, collapsed, onCollapse, onNavigate, children }: BasicLayoutProps) {
  const [sourceContext, setSourceContext] = useState<SourceContextResponse | null>(null);
  const [sourceLoading, setSourceLoading] = useState(true);
  const [sourceError, setSourceError] = useState('');
  const [lastRefreshedAt, setLastRefreshedAt] = useState<string | null>(null);

  const refreshSourceContext = useCallback(async () => {
    setSourceLoading(true);
    setSourceError('');
    try {
      const payload = await api.sourceContext();
      setSourceContext(payload);
      setLastRefreshedAt(new Date().toISOString());
    } catch (error) {
      setSourceContext(null);
      setSourceError(error instanceof Error ? error.message : String(error || '来源状态读取失败'));
    } finally {
      setSourceLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshSourceContext();
  }, [refreshSourceContext, route]);

  return (
    <Layout className="app-shell">
      <HeaderBar />
      <Layout className="app-body">
        <Sidebar collapsed={collapsed} route={route} activeSubKey={activeSubKey} onCollapse={onCollapse} onNavigate={onNavigate} />
        <Layout className="main-shell">
          <main className="content-shell">
            <FactStatusBar
              meta={sourceContext?.meta}
              loading={sourceLoading}
              error={sourceError}
              lastRefreshedAt={lastRefreshedAt}
              onRefresh={refreshSourceContext}
            />
            {children}
          </main>
        </Layout>
      </Layout>
    </Layout>
  );
}
