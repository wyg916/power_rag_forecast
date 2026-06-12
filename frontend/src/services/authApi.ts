import { api, clearStoredAccessToken, setStoredAccessToken } from '../api';

export interface AuthUser {
  id: string;
  username: string;
  email?: string;
  display_name?: string;
  role: string;
  permissions: string[];
  auth_mode?: string;
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
    if (payload?.access_token) setStoredAccessToken(payload.access_token);
    return payload;
  },

  async me(): Promise<AuthUser> {
    const payload = await api.authMe();
    return payload.user;
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

