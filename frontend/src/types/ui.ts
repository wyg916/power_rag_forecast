import type { ReactNode } from 'react';

export type RouteKey =
  | 'dashboard'
  | 'data'
  | 'forecast'
  | 'strategy'
  | 'assistant'
  | 'report'
  | 'model'
  | 'knowledge'
  | 'task'
  | 'settings';

export interface RouteState {
  route: RouteKey;
  childKey: string;
}

export interface PageProps {
  activeSubKey: string;
  onSubNavigate: (childKey: string) => void;
}

export type UiStatus =
  | 'success'
  | 'running'
  | 'warning'
  | 'danger'
  | 'offline'
  | 'pending'
  | 'published'
  | 'rejected'
  | 'info';

export interface MetricItem {
  title: string;
  value: string | number;
  unit?: string;
  icon?: ReactNode;
  trend?: number;
  trendLabel?: string;
  status?: UiStatus;
  note?: string;
  description?: string;
  loading?: boolean;
}

export interface MenuChild {
  label: string;
  key: string;
}

export interface MenuGroup {
  key: RouteKey;
  label: string;
  icon: ReactNode;
  children: MenuChild[];
}

export interface MenuSection {
  key: string;
  label: string;
  description?: string;
  routes: RouteKey[];
}

export interface TimePoint {
  time: string;
  value: number;
  actual?: number;
  baseline?: number;
  upper?: number;
  lower?: number;
}

export interface TableRecord {
  key: string;
  [key: string]: unknown;
}
