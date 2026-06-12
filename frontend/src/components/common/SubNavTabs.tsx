import { PageTabs, type PageTabItem } from './PageTabs';

interface SubNavTabsProps {
  items: Array<string | PageTabItem>;
  activeKey?: string;
  onChange?: (key: string) => void;
}

export function SubNavTabs(props: SubNavTabsProps) {
  return <PageTabs {...props} />;
}
