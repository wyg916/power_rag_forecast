import { Layout } from 'antd';
import type { ReactNode } from 'react';
import { HeaderBar } from './HeaderBar';
import { Sidebar } from './Sidebar';
import type { RouteKey } from '../types/ui';

interface BasicLayoutProps {
  route: RouteKey;
  activeSubKey: string;
  collapsed: boolean;
  onCollapse: () => void;
  onNavigate: (route: RouteKey, childKey?: string) => void;
  children: ReactNode;
}

export function BasicLayout({ route, activeSubKey, collapsed, onCollapse, onNavigate, children }: BasicLayoutProps) {
  return (
    <Layout className="app-shell">
      <Sidebar collapsed={collapsed} route={route} activeSubKey={activeSubKey} onCollapse={onCollapse} onNavigate={onNavigate} />
      <Layout className="main-shell">
        <HeaderBar />
        <main className="content-shell">{children}</main>
      </Layout>
    </Layout>
  );
}
