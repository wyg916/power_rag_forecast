import {
  BellOutlined,
  ClockCircleOutlined,
  DownOutlined,
  LoginOutlined,
  LogoutOutlined,
  ProjectOutlined,
  QuestionCircleOutlined,
  ThunderboltFilled,
  SyncOutlined,
  UserOutlined
} from '@ant-design/icons';
import { Avatar, Badge, Button, Dropdown, Select, Space, Tag, Tooltip } from 'antd';
import { useEffect, useState } from 'react';
import { api } from '../api';
import { useAuth } from '../context/AuthContext';

function formatBusinessTime(value: unknown) {
  if (!value) return '--';
  const date = new Date(String(value));
  if (Number.isNaN(date.getTime())) return String(value).replace('T', ' ').slice(0, 16);
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hour12: false
  }).format(date).replace(/\//g, '-');
}

export function HeaderBar({ workspaceMode = 'default' }: { workspaceMode?: 'default' | 'data' }) {
  const { openLogin, user, logout } = useAuth();
  const [context, setContext] = useState<any>(null);
  const displayName = user?.display_name || user?.username || '当前用户';
  const role = user?.role || '未登录';
  const projectName = context?.project?.name || '--';
  const dataTime = formatBusinessTime(context?.data_time);
  const notificationCount = Number(context?.notification_count ?? 0);
  const dataWorkspace = workspaceMode === 'data';

  useEffect(() => {
    let active = true;
    api.dashboardContext()
      .then((payload) => {
        if (active) setContext(payload);
      })
      .catch(() => {
        if (active) setContext(null);
      });
    return () => {
      active = false;
    };
  }, []);

  const menuItems = [
    {
      key: 'profile',
      label: (
        <div>
          <strong>{displayName}</strong>
          <div className="user-menu-subtitle">{user?.username || '未登录'} · {role}</div>
        </div>
      ),
      disabled: true
    },
    user
      ? { key: 'logout', icon: <LogoutOutlined />, label: '退出登录', onClick: () => logout() }
      : { key: 'login', icon: <LoginOutlined />, label: '登录正式账号', onClick: openLogin }
  ];

  return (
    <div className={`header-bar ${dataWorkspace ? 'data-workspace-header' : ''}`}>
      <div className="header-brand">
        <div className="header-brand-mark">
          <ThunderboltFilled />
        </div>
        <strong>AI 售电交易决策平台</strong>
      </div>
      <div className={`header-context ${dataWorkspace ? 'data-workspace-context' : ''}`}>
        {dataWorkspace ? (
          <>
            <div className="data-context-item data-context-project" title={projectName}>
              <ProjectOutlined /><span>项目：</span><strong>{projectName}</strong>
            </div>
            <div className="data-context-item data-context-time" title={dataTime}>
              <ClockCircleOutlined /><span>数据时间：</span><strong>{dataTime}</strong>
            </div>
          </>
        ) : (
          <Select
            className="project-select"
            value={projectName}
            disabled
            title="当前会话项目"
            options={[{ value: projectName, label: `项目：${projectName}` }]}
          />
        )}
      </div>
      <Space size={10} className="header-actions">
        <Tooltip title="通知中心">
          <Badge count={notificationCount} size="small" offset={[-2, 4]}>
            <Button type="text" shape="circle" aria-label="通知中心" icon={<BellOutlined />} onClick={() => { window.location.hash = '/task/task-alert'; }} />
          </Badge>
        </Tooltip>
        <Tooltip title="帮助中心">
          <Button type="text" shape="circle" aria-label="帮助中心" icon={<QuestionCircleOutlined />} onClick={() => { window.location.hash = '/assistant/assistant-faq'; }} />
        </Tooltip>
        <Tooltip title="刷新当前视图">
          <Button type="text" shape="circle" aria-label="刷新当前视图" icon={<SyncOutlined />} onClick={() => window.location.reload()} />
        </Tooltip>
        <Dropdown trigger={['click']} menu={{ items: menuItems }}>
          <Button type="text" className="user-area">
            <Avatar icon={<UserOutlined />} />
            <strong title={displayName}>{displayName}</strong>
            <Tag>{role}</Tag>
            <DownOutlined />
          </Button>
        </Dropdown>
      </Space>
    </div>
  );
}
