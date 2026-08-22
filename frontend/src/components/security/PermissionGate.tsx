import { Button, Result } from 'antd';
import type { ReactNode } from 'react';
import { useAuth } from '../../context/AuthContext';
import { hasAllPermissions, hasAnyPermission } from '../../security/permissions';

interface PermissionGateProps {
  all?: string[];
  any?: string[];
  children: ReactNode;
  fallback?: ReactNode;
  mode?: 'hide' | 'section';
}

export function SectionUnavailable({ title = '当前内容暂不可用' }: { title?: string }) {
  return (
    <div className="section-unavailable" role="status">
      <strong>{title}</strong>
      <span>当前账号未开通此项能力，如有业务需要请联系管理员。</span>
    </div>
  );
}

export function FullPageForbidden({ onBack }: { onBack?: () => void }) {
  return (
    <section className="full-page-forbidden" aria-label="访问受限">
      <Result
        status="403"
        title="当前账号无法访问此页面"
        subTitle="该页面未向当前账号开放。你可以返回首页，或联系管理员调整权限。"
        extra={<Button type="primary" onClick={onBack || (() => { window.location.hash = '/dashboard/dashboard-overview'; })}>返回首页</Button>}
      />
    </section>
  );
}

export function PermissionGate({ all = [], any = [], children, fallback, mode = 'hide' }: PermissionGateProps) {
  const { permissions } = useAuth();
  const allowed = hasAllPermissions(permissions, all) && hasAnyPermission(permissions, any);
  if (allowed) return <>{children}</>;
  if (fallback !== undefined) return <>{fallback}</>;
  if (mode === 'section') return <SectionUnavailable />;
  return null;
}

export function Can(props: PermissionGateProps) {
  return <PermissionGate {...props} />;
}

export function ActionGuard(props: PermissionGateProps) {
  return <PermissionGate {...props} mode="hide" />;
}
