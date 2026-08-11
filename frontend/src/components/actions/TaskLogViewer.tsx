import { Drawer, Empty, Typography } from 'antd';

interface TaskLogViewerProps {
  open: boolean;
  title?: string;
  log?: string;
  loading?: boolean;
  onClose: () => void;
}

export function TaskLogViewer({ open, title = '任务日志', log, loading, onClose }: TaskLogViewerProps) {
  return (
    <Drawer width={820} title={title} open={open} onClose={onClose} destroyOnHidden>
      {loading ? (
        <Typography.Text>日志加载中...</Typography.Text>
      ) : log ? (
        <pre className="task-log-viewer">{log}</pre>
      ) : (
        <Empty description="暂无日志内容" />
      )}
    </Drawer>
  );
}
