import {
  BellOutlined,
  ClockCircleOutlined,
  DownOutlined,
  GlobalOutlined,
  LoginOutlined,
  LogoutOutlined,
  QuestionCircleOutlined,
  SafetyCertificateOutlined,
  SearchOutlined,
  SyncOutlined,
  UserOutlined
} from '@ant-design/icons';
import { Avatar, Badge, Button, Dropdown, Input, Select, Space, Tag, Tooltip } from 'antd';
import { useAuth } from '../context/AuthContext';

export function HeaderBar() {
  const { openLogin, user, logout } = useAuth();
  const displayName = user?.display_name || user?.username || '开发用户';
  const role = user?.role || 'dev';
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
      <div className="header-left">
        <Select
          className="project-select"
          value="华东虚拟电厂示范项目"
          options={[
            { value: '华东虚拟电厂示范项目', label: '项目：华东虚拟电厂示范项目' },
            { value: '浙江新能源聚合项目', label: '项目：浙江新能源聚合项目' }
          ]}
        />
        <Input
          className="header-search"
          prefix={<SearchOutlined />}
          placeholder="搜索页面、任务、策略"
          allowClear
        />
      </div>
      <Space size={14} className="header-meta-group">
        <span className="header-meta">
          <ClockCircleOutlined />
          数据时间：2025-06-21 10:30:00
        </span>
        <span className="header-meta">
          <GlobalOutlined />
          当前地区：
          <strong>浙江省</strong>
          <DownOutlined className="header-down" />
        </span>
        <span className="header-meta">
          模型版本：
          <strong>v3.2.1</strong>
          <Tag color="success">最新</Tag>
        </span>
      </Space>
      <Space size={10} className="header-actions">
        <Tag className="global-status-pill" color="success">
          <SafetyCertificateOutlined />
          只读 SQL 已启用
        </Tag>
        <Badge count={12} size="small">
          <Tooltip title="告警通知">
            <Button type="text" shape="circle" icon={<BellOutlined />} />
          </Tooltip>
        </Badge>
        <Tooltip title="帮助中心">
          <Button type="text" shape="circle" icon={<QuestionCircleOutlined />} />
        </Tooltip>
        <Tooltip title="刷新当前视图">
          <Button type="text" shape="circle" icon={<SyncOutlined />} />
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
