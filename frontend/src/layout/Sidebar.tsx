import { MenuFoldOutlined, MenuUnfoldOutlined, ThunderboltFilled } from '@ant-design/icons';
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

export function Sidebar({ collapsed, route, onCollapse, onNavigate }: SidebarProps) {
  const items: ItemType[] = menuGroups.map((group) => ({
    key: group.key,
    icon: group.icon,
    label: group.label
  }));

  const selectedKeys = [route];

  return (
    <aside className={`sidebar-shell ${collapsed ? 'collapsed' : ''}`}>
      <div className="brand-panel">
        <div className="brand-mark">
          <ThunderboltFilled />
        </div>
        {!collapsed && <div className="brand-title">AI 售电交易决策平台</div>}
      </div>
      <Menu
        mode="inline"
        inlineCollapsed={collapsed}
        selectedKeys={selectedKeys}
        items={items}
        onClick={(info) => {
          const parent = menuGroups.find((group) => group.key === info.key);
          if (!parent) return;
          onNavigate(parent.key, parent.children[0]?.key);
        }}
      />
      <div className="collapse-entry">
        <Button type="text" icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />} onClick={onCollapse}>
          {!collapsed && '收起菜单'}
        </Button>
      </div>
    </aside>
  );
}
