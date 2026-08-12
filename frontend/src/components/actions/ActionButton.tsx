import { App, Button } from 'antd';
import type { ButtonProps } from 'antd';
import { useState } from 'react';

interface ActionButtonProps extends ButtonProps {
  action: () => Promise<unknown> | unknown;
  successText?: string;
  errorText?: string;
}

export function ActionButton({ action, successText = '操作成功', errorText = '操作失败', children, ...props }: ActionButtonProps) {
  const { message } = App.useApp();
  const [loading, setLoading] = useState(false);

  async function run() {
    setLoading(true);
    try {
      await action();
      if (successText) message.success(successText);
    } catch (error) {
      message.error(error instanceof Error ? error.message : errorText);
    } finally {
      setLoading(false);
    }
  }

  return (
    <Button {...props} loading={loading || props.loading} onClick={run}>
      {children}
    </Button>
  );
}
