import { Alert, Button, Space } from 'antd';

interface HomeDataStateProps {
  loading: boolean;
  errors: string[];
  sources: string[];
  onRetry: () => void;
}

export function HomeDataState({ loading, errors, onRetry }: HomeDataStateProps) {
  if (loading) {
    return <Alert className="home-data-state" type="info" showIcon message="正在读取首页数据" />;
  }
  if (errors.length) {
    return (
      <Alert
        className="home-data-state"
        type="warning"
        showIcon
        message="首页部分内容加载失败"
        description={
          <Space direction="vertical" size={4}>
            {errors.map((item) => <span key={item}>{item}</span>)}
          </Space>
        }
        action={<Button size="small" onClick={onRetry}>重试</Button>}
      />
    );
  }
  return null;
}
