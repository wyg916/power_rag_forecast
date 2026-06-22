import { Alert, Button, Space, Tag } from 'antd';
import { sourceLabel } from './utils';

interface HomeDataStateProps {
  loading: boolean;
  errors: string[];
  sources: string[];
  onRetry: () => void;
}

export function HomeSourceTag({ source }: { source?: string }) {
  const lower = String(source || '').toLowerCase();
  const color = lower.includes('mock') || lower.includes('demo')
    ? 'error'
    : lower.includes('derived')
      ? 'processing'
      : lower.includes('postgres')
        ? 'success'
        : lower.includes('file')
          ? 'blue'
          : 'default';
  return <Tag color={color}>{sourceLabel(source)}</Tag>;
}

export function HomeDataState({ loading, errors, sources, onRetry }: HomeDataStateProps) {
  if (loading) {
    return <Alert className="home-data-state" type="info" showIcon message="正在读取首页真实 API 数据" />;
  }
  if (errors.length) {
    return (
      <Alert
        className="home-data-state"
        type="warning"
        showIcon
        message="首页存在接口异常，页面不会使用 mock 数据兜底"
        description={
          <Space direction="vertical" size={4}>
            {errors.map((item) => <span key={item}>{item}</span>)}
          </Space>
        }
        action={<Button size="small" onClick={onRetry}>重试</Button>}
      />
    );
  }
  return (
    <div className="home-source-row">
      {sources.filter(Boolean).slice(0, 4).map((source) => <HomeSourceTag key={source} source={source} />)}
    </div>
  );
}
