import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { clearStoredAccessToken, getStoredAccessToken } from '../api';
import { authApi } from '../services/authApi';
import type { AuthUser } from '../services/authApi';

interface AuthContextValue {
  authRequired: boolean;
  loginRequested: boolean;
  loading: boolean;
  user: AuthUser | null;
  permissions: string[];
  isAuthenticated: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  openLogin: () => void;
  closeLogin: () => void;
  hasPermission: (permission: string) => boolean;
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
    setUser(payload.user);
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
  const hasPermission = useCallback(
    (permission: string) => permissions.includes('*') || permissions.includes(permission),
    [permissions]
  );

  const value = useMemo<AuthContextValue>(
    () => ({
      authRequired,
      loginRequested,
      loading,
      user,
      permissions,
      isAuthenticated: Boolean(user),
      login,
      logout,
      openLogin,
      closeLogin,
      hasPermission
    }),
    [loginRequested, loading, user, permissions, login, logout, openLogin, closeLogin, hasPermission]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error('useAuth must be used inside AuthProvider');
  return value;
}
