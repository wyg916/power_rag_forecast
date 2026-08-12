import { MenuFoldOutlined, MenuUnfoldOutlined, RightOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { Button, Menu } from 'antd';
import type { ItemType } from 'antd/es/menu/interface';
import type { RouteKey } from '../types/ui';
import { menuGroups } from '../app/router';

interface SidebarProps {
  collapsed: boolean;
  route: RouteKey;
  activeSubKey: string;
  onCollapse: () => void;
  onNavigate: (route: RouteKey, childKey?: string) => void;
}

export function Sidebar({ collapsed, route, activeSubKey, onCollapse, onNavigate }: SidebarProps) {
  const groupByKey = new Map(menuGroups.map((group) => [group.key, group]));
  const selectedKeys = [route];
  const activeGroup = groupByKey.get(route);
  const activeChild = activeGroup?.children.find((child) => child.key === activeSubKey);

  const handleMenuClick = (key: string) => {
    const parent = groupByKey.get(key as RouteKey);
    if (!parent) return;
    onNavigate(parent.key, parent.children[0]?.key);
  };

  return (
    <aside className={`sidebar-shell ${collapsed ? 'collapsed' : ''}`}>
      <nav className="sidebar-nav" aria-label="主导航">
        <Menu
          mode="inline"
          inlineCollapsed={collapsed}
          selectedKeys={selectedKeys}
          items={menuGroups.map((group): ItemType => ({
            key: group.key,
            icon: group.icon,
            label: group.label
          }))}
          onClick={(info) => handleMenuClick(String(info.key))}
        />
      </nav>
      {!collapsed && activeGroup && (
        <div className="sidebar-current">
          <span>当前工作区</span>
          <strong>{activeGroup.label}</strong>
          <small>{activeChild?.label || activeGroup.children[0]?.label}</small>
        </div>
      )}
      <div className="sidebar-utility">
        <Button type="text" icon={<ThunderboltOutlined />} onClick={() => onNavigate('assistant', 'assistant-chat')}>
          {!collapsed && (
            <>
              <span>快捷操作</span>
              <RightOutlined />
            </>
          )}
        </Button>
      </div>
      <div className="collapse-entry">
        <Button type="text" icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />} onClick={onCollapse}>
          {!collapsed && '收起菜单'}
        </Button>
      </div>
    </aside>
  );
}
