import {
  BellOutlined,
  ClockCircleOutlined,
  DownOutlined,
  GlobalOutlined,
  LoginOutlined,
  LogoutOutlined,
  QuestionCircleOutlined,
  ThunderboltFilled,
  SyncOutlined,
  UserOutlined
} from '@ant-design/icons';
import { Avatar, Badge, Button, Dropdown, Select, Space, Tag, Tooltip } from 'antd';
import { useEffect, useState } from 'react';
import { api } from '../api';
import { useAuth } from '../context/AuthContext';

export function HeaderBar() {
  const { openLogin, user, logout } = useAuth();
  const [context, setContext] = useState<any>(null);
  const displayName = user?.display_name || user?.username || '超级管理员';
  const role = user?.role || 'dev';
  const projectName = context?.project?.name || '华东虚拟电厂示范项目';
  const region = context?.region || '浙江省';
  const dataTime = context?.data_time || context?.generated_at || '--';
  const modelVersion = context?.model?.version || 'v3.2.1';
  const notificationCount = Number(context?.notification_count ?? 12);

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
          <div className="user-menu-subtitle">{user?.username || 'dev_header_fallback'} · {role}</div>
        </div>
      ),
      disabled: true
    },
    user
      ? { key: 'logout', icon: <LogoutOutlined />, label: '退出登录', onClick: () => logout() }
      : { key: 'login', icon: <LoginOutlined />, label: '登录正式账号', onClick: openLogin }
  ];

  return (
    <div className="header-bar">
      <div className="header-brand">
        <div className="header-brand-mark">
          <ThunderboltFilled />
        </div>
        <strong>AI 售电交易决策平台</strong>
      </div>
      <div className="header-context">
        <Select
          className="project-select"
          value={projectName}
          options={[
            { value: projectName, label: `项目：${projectName}` },
            { value: '浙江新能源聚合项目', label: '项目：浙江新能源聚合项目' }
          ]}
        />
        <span className="header-meta header-meta-card">
          <ClockCircleOutlined />
          数据时间：{dataTime}
        </span>
        <span className="header-meta header-meta-card">
          <GlobalOutlined />
          当前地区：
          <strong>{region}</strong>
          <DownOutlined className="header-down" />
        </span>
        <span className="header-meta header-meta-card header-model-meta">
          模型版本：
          <strong>{modelVersion}</strong>
          <Tag color="success">最新</Tag>
        </span>
      </div>
      <Space size={10} className="header-actions">
        <Tooltip title="通知中心">
          <Badge count={notificationCount} size="small" offset={[-2, 4]}>
            <Button type="text" shape="circle" icon={<BellOutlined />} />
          </Badge>
        </Tooltip>
        <Tooltip title="帮助中心">
          <Button type="text" shape="circle" icon={<QuestionCircleOutlined />} onClick={() => { window.location.hash = '/knowledge/knowledge-search'; }} />
        </Tooltip>
        <Tooltip title="刷新当前视图">
          <Button type="text" shape="circle" icon={<SyncOutlined />} onClick={() => window.location.reload()} />
        </Tooltip>
        <Dropdown trigger={['click']} menu={{ items: menuItems }}>
          <Button type="text" className="user-area">
            <Avatar icon={<UserOutlined />} />
            <strong>{displayName}</strong>
            <Tag>{role}</Tag>
            <DownOutlined />
          </Button>
        </Dropdown>
      </Space>
    </div>
  );
}
