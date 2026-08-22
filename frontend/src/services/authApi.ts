import { api, clearStoredAccessToken, setStoredAccessToken } from '../api';

export interface AuthUser {
  id: string;
  username: string;
  email?: string;
  display_name?: string;
  role: string;
  permissions: string[];
  auth_mode?: string;
  capability_manifest?: {
    routes?: Record<string, boolean>;
    actions?: Record<string, boolean>;
    generated_at?: string;
    policy_version?: string;
  };
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: AuthUser;
}

export const authApi = {
  async login(username: string, password: string): Promise<LoginResponse> {
    const payload = await api.authLogin({ username, password });
    if (!payload?.access_token || !payload?.user) {
      clearStoredAccessToken();
      throw new Error('登录响应缺少访问令牌或用户信息');
    }
    setStoredAccessToken(payload.access_token);
    return payload;
  },

  async me(): Promise<AuthUser> {
    const authPayload = await api.authMe();
    const baseUser = authPayload?.user || authPayload;
    try {
      const securityPayload = await api.securityMe();
      const securityUser = securityPayload?.user || securityPayload?.data || securityPayload || {};
      return {
        ...baseUser,
        ...securityUser,
        permissions: securityUser.permissions || baseUser.permissions || [],
        capability_manifest: securityUser.capability_manifest || baseUser.capability_manifest
      };
    } catch {
      return { ...baseUser, permissions: baseUser.permissions || [] };
    }
  },

  async logout(): Promise<void> {
    try {
      await api.authLogout();
    } finally {
      clearStoredAccessToken();
    }
  },

  async changePassword(oldPassword: string, newPassword: string): Promise<void> {
    await api.authChangePassword({ old_password: oldPassword, new_password: newPassword });
  }
};

