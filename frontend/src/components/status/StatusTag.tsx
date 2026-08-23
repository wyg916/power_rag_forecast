import { Tag } from 'antd';
import type { UiStatus } from '../../types/ui';

const statusMap: Record<UiStatus, { color: string; text: string }> = {
  success: { color: 'success', text: '成功' },
  running: { color: 'processing', text: '运行中' },
  warning: { color: 'warning', text: '告警' },
  danger: { color: 'error', text: '失败' },
  offline: { color: 'default', text: '离线' },
  pending: { color: 'warning', text: '待处理' },
  published: { color: 'success', text: '已发布' },
  rejected: { color: 'error', text: '已驳回' },
  info: { color: 'blue', text: '提示' }
};

interface StatusTagProps {
  status: UiStatus;
  text?: string;
}

export function StatusTag({ status, text }: StatusTagProps) {
  const item = statusMap[status];
  return <Tag className={`status-tag status-tag-${status}`} color={item.color} aria-label={`状态：${text || item.text}`}>{text || item.text}</Tag>;
}
