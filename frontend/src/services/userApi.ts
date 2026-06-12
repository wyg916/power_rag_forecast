import { api } from '../api';

export interface UserItem {
  id?: string | number | null;
  user_id: string;
  username: string;
  email?: string;
  display_name?: string;
  role: string;
  is_active: boolean;
  is_superuser: boolean;
  last_login_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface RoleInfo {
  name: string;
  label: string;
  description: string;
  permissions: string[];
}

export const userApi = {
  listUsers(params: Record<string, any> = {}) {
    return api.users(params) as Promise<{ items: UserItem[]; total: number; page: number; page_size: number }>;
  },
  getRoles() {
    return api.userRoles() as Promise<{ roles: RoleInfo[] }>;
  },
  createUser(payload: any) {
    return api.createUser(payload) as Promise<{ user: UserItem }>;
  },
  updateUser(userId: string, payload: any) {
    return api.updateUser(userId, payload) as Promise<{ user: UserItem }>;
  },
  resetPassword(userId: string, newPassword: string) {
    return api.resetUserPassword(userId, newPassword) as Promise<{ ok: boolean }>;
  },
  disableUser(userId: string) {
    return api.disableUser(userId) as Promise<{ user: UserItem }>;
  },
  enableUser(userId: string) {
    return api.updateUser(userId, { is_active: true }) as Promise<{ user: UserItem }>;
  }
};

