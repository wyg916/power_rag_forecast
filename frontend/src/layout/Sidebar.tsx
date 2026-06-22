import { MenuFoldOutlined, MenuUnfoldOutlined, ThunderboltFilled } from '@ant-design/icons';
import { Button, Menu } from 'antd';
import type { ItemType } from 'antd/es/menu/interface';
import type { RouteKey } from '../types/ui';
import { menuGroups, menuSections } from '../app/router';

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
      <div className="brand-panel">
        <div className="brand-mark">
          <ThunderboltFilled />
        </div>
        {!collapsed && (
          <div className="brand-copy">
            <div className="brand-title">智能运营分析</div>
            <div className="brand-subtitle">售电交易决策平台</div>
          </div>
        )}
      </div>
      <nav className="sidebar-nav" aria-label="主导航">
        {menuSections.map((section) => {
          const items: ItemType[] = section.routes
            .map((key) => groupByKey.get(key))
            .filter(Boolean)
            .map((group) => ({
              key: group!.key,
              icon: group!.icon,
              label: group!.label
            }));

          return (
            <div className="sidebar-section" key={section.key}>
              {!collapsed && !section.compact && (
                <div className="sidebar-section-label">
                  <span>{section.label}</span>
                  <small>{section.description}</small>
                </div>
              )}
              <Menu
                mode="inline"
                inlineCollapsed={collapsed}
                selectedKeys={selectedKeys}
                items={items}
                onClick={(info) => handleMenuClick(String(info.key))}
              />
            </div>
          );
        })}
      </nav>
      {!collapsed && activeGroup && (
        <div className="sidebar-current">
          <span>当前板块</span>
          <strong>{activeGroup.label}</strong>
          <small>{activeChild?.label || activeGroup.children[0]?.label}</small>
        </div>
      )}
      <div className="collapse-entry">
        <Button type="text" icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />} onClick={onCollapse}>
          {!collapsed && '收起菜单'}
        </Button>
      </div>
    </aside>
  );
}
