import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { clearStoredAccessToken, getStoredAccessToken } from '../api';
import { authApi } from '../services/authApi';
import type { AuthUser } from '../services/authApi';
import {
  canAccessChild as resolveChildAccess,
  canAccessRoute as resolveRouteAccess,
  canPerformAction as resolveActionAccess,
  permissionSnapshotHash as buildPermissionSnapshotHash
} from '../security/permissions';
import type { CapabilityManifest } from '../security/permissions';
import type { RouteKey } from '../types/ui';

interface AuthContextValue {
  authRequired: boolean;
  loginRequested: boolean;
  loading: boolean;
  user: AuthUser | null;
  permissions: string[];
  capabilityManifest: CapabilityManifest | null;
  permissionSnapshotHash: string;
  isAuthenticated: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  openLogin: () => void;
  closeLogin: () => void;
  hasPermission: (permission: string) => boolean;
  canAccessRoute: (route: RouteKey) => boolean;
  canAccessChild: (childKey: string) => boolean;
  canPerformAction: (action: string) => boolean;
}

const AuthContext = createContext<AuthContextValue | null>(null);
const authRequired = String(import.meta.env.VITE_AUTH_REQUIRED ?? '1') !== '0';

export function AuthProvider({ children }: { children: ReactNode }) {
  const [loading, setLoading] = useState(Boolean(getStoredAccessToken()));
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loginRequested, setLoginRequested] = useState(false);

  const refreshMe = useCallback(async () => {
    const token = getStoredAccessToken();
    if (!token) {
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      const current = await authApi.me();
      setUser(current);
    } catch {
      clearStoredAccessToken();
      setUser(null);
      setLoginRequested(authRequired);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshMe();
    const handler = () => {
      clearStoredAccessToken();
      setUser(null);
      setLoginRequested(authRequired);
    };
    window.addEventListener('auth:unauthorized', handler);
    return () => window.removeEventListener('auth:unauthorized', handler);
  }, [refreshMe]);

  const login = useCallback(async (username: string, password: string) => {
    const payload = await authApi.login(username, password);
    const current = await authApi.me().catch(() => payload.user);
    setUser(current);
    setLoginRequested(false);
  }, []);

  const logout = useCallback(async () => {
    await authApi.logout();
    setUser(null);
    setLoginRequested(false);
  }, []);

  const openLogin = useCallback(() => setLoginRequested(true), []);
  const closeLogin = useCallback(() => setLoginRequested(false), []);

  const permissions = user?.permissions || [];
  const capabilityManifest = (user?.capability_manifest || null) as CapabilityManifest | null;
  const hasPermission = useCallback(
    (permission: string) => permissions.includes('*') || permissions.includes(permission),
    [permissions]
  );
  const canAccessRoute = useCallback(
    (route: RouteKey) => !authRequired || resolveRouteAccess(route, permissions, capabilityManifest),
    [permissions, capabilityManifest]
  );
  const canAccessChild = useCallback(
    (childKey: string) => !authRequired || resolveChildAccess(childKey, permissions),
    [permissions]
  );
  const canPerformAction = useCallback(
    (action: string) => !authRequired || resolveActionAccess(action, permissions, capabilityManifest),
    [permissions, capabilityManifest]
  );
  const permissionSnapshotHash = useMemo(() => buildPermissionSnapshotHash(permissions), [permissions]);

  const value = useMemo<AuthContextValue>(
    () => ({
      authRequired,
      loginRequested,
      loading,
      user,
      permissions,
      capabilityManifest,
      permissionSnapshotHash,
      isAuthenticated: Boolean(user),
      login,
      logout,
      openLogin,
      closeLogin,
      hasPermission,
      canAccessRoute,
      canAccessChild,
      canPerformAction
    }),
    [loginRequested, loading, user, permissions, capabilityManifest, permissionSnapshotHash, login, logout, openLogin, closeLogin, hasPermission, canAccessRoute, canAccessChild, canPerformAction]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error('useAuth must be used inside AuthProvider');
  return value;
}
