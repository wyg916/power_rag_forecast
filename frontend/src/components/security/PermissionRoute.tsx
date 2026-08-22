import type { ReactNode } from 'react';
import type { RouteKey } from '../../types/ui';
import { useAuth } from '../../context/AuthContext';
import { FullPageForbidden } from './PermissionGate';

export function PermissionRoute({ route, childKey, children }: { route: RouteKey; childKey: string; children: ReactNode }) {
  const { canAccessRoute, canAccessChild } = useAuth();
  if (!canAccessRoute(route) || !canAccessChild(childKey)) {
    return <FullPageForbidden />;
  }
  return <>{children}</>;
}
