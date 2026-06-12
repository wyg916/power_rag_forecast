import { Tabs } from 'antd';

export interface PageTabItem {
  key: string;
  label: string;
}

interface PageTabsProps {
  items: Array<string | PageTabItem>;
  activeKey?: string;
  onChange?: (key: string) => void;
}

export function PageTabs({ items, activeKey, onChange }: PageTabsProps) {
  const normalized = items.map((item) => (typeof item === 'string' ? { key: item, label: item } : item));
  const selected = activeKey && normalized.some((item) => item.key === activeKey) ? activeKey : normalized[0]?.key;
  return <Tabs className="page-tabs" activeKey={selected} items={normalized} onChange={onChange} />;
}
