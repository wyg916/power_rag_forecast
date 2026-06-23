import { lazy, Suspense, useEffect, useMemo, useState } from 'react';
import type { LazyExoticComponent } from 'react';
import { BasicLayout } from '../layout/BasicLayout';
import { PageContainer } from '../layout/PageContainer';
import { LoadingBlock } from '../components/common/States';
import { useAuth } from '../context/AuthContext';
import { LoginPage } from '../pages/LoginPage';
import { getDefaultChildKey, normalizeRouteState, routeTitles } from './router';
import type { PageProps, RouteKey, RouteState } from '../types/ui';

const pages: Record<RouteKey, LazyExoticComponent<(props: PageProps) => JSX.Element>> = {
  dashboard: lazy(() => import('../pages/dashboard/DashboardPage').then((mod) => ({ default: mod.DashboardPage }))),
  data: lazy(() => import('../pages/data/DataCenterPage').then((mod) => ({ default: mod.DataCenterPage }))),
  forecast: lazy(() => import('../pages/forecast/ForecastCenterPage').then((mod) => ({ default: mod.ForecastCenterPage }))),
  strategy: lazy(() => import('../pages/strategy/StrategyCenterPage').then((mod) => ({ default: mod.StrategyCenterPage }))),
  assistant: lazy(() => import('../pages/assistant/AssistantPage').then((mod) => ({ default: mod.AssistantPage }))),
  report: lazy(() => import('../pages/report/ReportCenterPage').then((mod) => ({ default: mod.ReportCenterPage }))),
  model: lazy(() => import('../pages/model/ModelCenterPage').then((mod) => ({ default: mod.ModelCenterPage }))),
  knowledge: lazy(() => import('../pages/knowledge/KnowledgeBasePage').then((mod) => ({ default: mod.KnowledgeBasePage }))),
  task: lazy(() => import('../pages/task/TaskCenterPage').then((mod) => ({ default: mod.TaskCenterPage }))),
  settings: lazy(() => import('../pages/settings/SettingsPage').then((mod) => ({ default: mod.SettingsPage })))
};

export function App() {
  const { authRequired, loginRequested, loading: authLoading, isAuthenticated } = useAuth();
  const [routeState, setRouteState] = useState<RouteState>(() => normalizeRouteState(window.location.hash));
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    const handleHashChange = () => setRouteState(normalizeRouteState(window.location.hash));
    window.addEventListener('hashchange', handleHashChange);
    if (!window.location.hash) window.location.hash = `/dashboard/${getDefaultChildKey('dashboard')}`;
    return () => window.removeEventListener('hashchange', handleHashChange);
  }, []);

  const title = useMemo(() => routeTitles[routeState.route], [routeState.route]);
  const ActivePage = pages[routeState.route];

  if ((authRequired || loginRequested) && authLoading) {
    return <LoadingBlock rows={8} />;
  }

  if ((authRequired || loginRequested) && !isAuthenticated) {
    return <LoginPage />;
  }

  function handleNavigate(nextRoute: RouteKey, nextChildKey?: string) {
    const childKey = nextChildKey || getDefaultChildKey(nextRoute);
    const nextState = { route: nextRoute, childKey };
    window.location.hash = `/${nextRoute}/${childKey}`;
    setRouteState(nextState);
  }

  return (
    <BasicLayout
      route={routeState.route}
      activeSubKey={routeState.childKey}
      collapsed={collapsed}
      onCollapse={() => setCollapsed((value) => !value)}
      onNavigate={handleNavigate}
    >
      <PageContainer title={title.title} subtitle={title.subtitle} hideHeader={routeState.route === 'dashboard' || routeState.route === 'forecast'}>
        <Suspense fallback={<LoadingBlock rows={8} />}>
          <ActivePage
            activeSubKey={routeState.childKey}
            onSubNavigate={(childKey) => handleNavigate(routeState.route, childKey)}
          />
        </Suspense>
      </PageContainer>
    </BasicLayout>
  );
}
