import {
  FileDoneOutlined,
  FundOutlined,
  RobotOutlined,
  SafetyCertificateOutlined,
  ScheduleOutlined,
  ThunderboltOutlined
} from '@ant-design/icons';
import type { PageHeaderAction } from '../common/PageHeader';

const quickEntries = [
  { key: 'forecast-24h', label: '查看24小时预测', icon: <FundOutlined />, hash: '/forecast/forecast-24h' },
  { key: 'strategy-center', label: '进入策略中心', icon: <SafetyCertificateOutlined />, hash: '/strategy/strategy-high' },
  { key: 'assistant-chat', label: '打开AI助手', icon: <RobotOutlined />, hash: '/assistant/assistant-chat' },
  { key: 'report-review', label: '审核报告', icon: <FileDoneOutlined />, hash: '/report/report-review' },
  { key: 'model-evaluation', label: '模型评估', icon: <ThunderboltOutlined />, hash: '/forecast/forecast-model' },
  { key: 'task-center', label: '任务中心', icon: <ScheduleOutlined />, hash: '/task/task-schedule' }
];

export function homeQuickActions(): PageHeaderAction[] {
  return quickEntries.map((entry) => ({
    key: entry.key,
    label: entry.label,
    icon: entry.icon,
    type: 'default',
    collapseAtNarrow: true,
    onClick: () => { window.location.hash = entry.hash; }
  }));
}
