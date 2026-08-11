import { Descriptions, Drawer, Typography } from 'antd';
import type { ReactNode } from 'react';

interface DetailDrawerProps {
  title: ReactNode;
  open: boolean;
  data?: Record<string, unknown> | null;
  children?: ReactNode;
  onClose: () => void;
}

export function DetailDrawer({ title, open, data, children, onClose }: DetailDrawerProps) {
  return (
    <Drawer className="detail-drawer" width={720} title={title} open={open} onClose={onClose} destroyOnHidden>
      {children}
      {data && (
        <Descriptions className="detail-drawer-descriptions" bordered size="small" column={1}>
          {Object.entries(data).map(([key, value]) => (
            <Descriptions.Item key={key} label={key}>
              {typeof value === 'object' ? (
                <Typography.Text code>{JSON.stringify(value, null, 2)}</Typography.Text>
              ) : (
                String(value ?? '--')
              )}
            </Descriptions.Item>
          ))}
        </Descriptions>
      )}
    </Drawer>
  );
}
