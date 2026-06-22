import {
  FileDoneOutlined,
  FundOutlined,
  RobotOutlined,
  SafetyCertificateOutlined,
  ScheduleOutlined,
  ThunderboltOutlined
} from '@ant-design/icons';

const quickEntries = [
  { label: '24h预测', icon: <FundOutlined />, hash: '/forecast/forecast-24h' },
  { label: '策略中心', icon: <SafetyCertificateOutlined />, hash: '/strategy/strategy-high' },
  { label: 'AI助手', icon: <RobotOutlined />, hash: '/assistant/assistant-chat' },
  { label: '审核报告', icon: <FileDoneOutlined />, hash: '/report/report-review' },
  { label: '模型评估', icon: <ThunderboltOutlined />, hash: '/model/model-active' },
  { label: '任务中心', icon: <ScheduleOutlined />, hash: '/task/task-schedule' }
];

export function HomeQuickActions() {
  return (
    <div className="home-quick-strip" aria-label="首页快捷入口">
      {quickEntries.map((entry) => (
        <button key={entry.hash} type="button" onClick={() => { window.location.hash = entry.hash; }}>
          {entry.icon}
          <span>{entry.label}</span>
        </button>
      ))}
    </div>
  );
}
