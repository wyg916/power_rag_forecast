import { Layout } from 'antd';
import type { ReactNode } from 'react';
import { HeaderBar } from './HeaderBar';
import { Sidebar } from './Sidebar';
import type { RouteKey } from '../types/ui';
import { GlobalAssistantDrawer } from '../features/globalAssistant/GlobalAssistantDrawer';
import { useAuth } from '../context/AuthContext';
import { menuGroups } from '../app/router';

interface BasicLayoutProps {
  route: RouteKey;
  activeSubKey: string;
  collapsed: boolean;
  onCollapse: () => void;
  onNavigate: (route: RouteKey, childKey?: string) => void;
  children: ReactNode;
}

export function BasicLayout({ route, activeSubKey, collapsed, onCollapse, onNavigate, children }: BasicLayoutProps) {
  const dataWorkspace = route === 'data';
  const { canAccessRoute, permissionSnapshotHash } = useAuth();
  const group = menuGroups.find((item) => item.key === route);
  const child = group?.children.find((item) => item.key === activeSubKey);
  const pageTitle = child?.label && child.label !== group?.label ? `${group?.label} / ${child.label}` : group?.label || '业务页面';
  const routeKey = `${route}.${activeSubKey.replace(`${route}-`, '').replace(/-/g, '_')}`;
  return (
    <Layout className={['app-shell', route === 'report' ? 'app-shell--report' : '', dataWorkspace ? 'data-workspace-shell' : ''].filter(Boolean).join(' ')}>
      <HeaderBar workspaceMode={dataWorkspace ? 'data' : 'default'} />
      <Layout className="app-body">
        <Sidebar collapsed={collapsed} route={route} activeSubKey={activeSubKey} onCollapse={onCollapse} onNavigate={onNavigate} />
        <Layout className={`main-shell ${dataWorkspace ? 'data-workspace-main' : ''}`}>
          <main className="content-shell">
            {children}
          </main>
        </Layout>
      </Layout>
      <GlobalAssistantDrawer
        routeKey={routeKey}
        pageTitle={pageTitle}
        permissionSnapshotHash={permissionSnapshotHash}
        assistantAllowed={canAccessRoute('assistant')}
        onOpenFullAssistant={() => onNavigate('assistant', 'assistant-chat')}
      />
    </Layout>
  );
}
