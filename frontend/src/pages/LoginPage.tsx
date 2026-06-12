import { LockOutlined, UserOutlined } from '@ant-design/icons';
import { Alert, Button, Card, Form, Input, Typography } from 'antd';
import { useState } from 'react';
import { useAuth } from '../context/AuthContext';

export function LoginPage() {
  const { authRequired, closeLogin, login } = useAuth();
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function handleFinish(values: { username: string; password: string }) {
    setLoading(true);
    setError('');
    try {
      await login(values.username, values.password);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : '登录失败，请检查用户名和密码。');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="login-page">
      <Card className="login-card">
        <Typography.Title level={3}>AI 售电交易决策平台</Typography.Title>
        <Typography.Paragraph type="secondary">请输入账号密码登录系统。</Typography.Paragraph>
        {error && <Alert type="error" showIcon message={error} className="login-error" />}
        <Form layout="vertical" onFinish={handleFinish}>
          <Form.Item name="username" label="用户名" rules={[{ required: true, message: '请输入用户名' }]}>
            <Input prefix={<UserOutlined />} autoComplete="username" />
          </Form.Item>
          <Form.Item name="password" label="密码" rules={[{ required: true, message: '请输入密码' }]}>
            <Input.Password prefix={<LockOutlined />} autoComplete="current-password" />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={loading} block>
            登录
          </Button>
          {!authRequired && (
            <Button type="link" block onClick={closeLogin}>
              继续使用开发模式
            </Button>
          )}
        </Form>
      </Card>
    </div>
  );
}
