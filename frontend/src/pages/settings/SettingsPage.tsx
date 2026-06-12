import { ApiOutlined, DatabaseOutlined, HeartOutlined, SafetyCertificateOutlined, UsergroupAddOutlined } from '@ant-design/icons';
import type { ReactNode } from 'react';
import { Button, Col, Form, Input, Row, Space, Switch, message } from 'antd';
import { useEffect, useMemo, useState } from 'react';
import { api } from '../../api';
import { SectionCard } from '../../components/cards/SectionCard';
import { TableCard } from '../../components/cards/TableCard';
import { PageTabs } from '../../components/common/PageTabs';
import { DataStateBanner } from '../../components/common/States';
import { MetricGrid } from '../../components/layout/UnifiedPage';
import { useAuth } from '../../context/AuthContext';
import { settingsMock } from '../../mock/settingsMock';
import { getSettingsData } from '../../services/settingsApi';
import type { PageProps } from '../../types/ui';
import { UserManagementPage } from './UserManagementPage';

const icons = [<UsergroupAddOutlined />, <SafetyCertificateOutlined />, <ApiOutlined />, <HeartOutlined />];

const tabs = [
  { key: 'settings-user', label: '用户管理' },
  { key: 'settings-role', label: '角色配置' },
  { key: 'settings-param', label: '参数配置' },
  { key: 'settings-api', label: '接口配置' }
];

export function SettingsPage({ activeSubKey, onSubNavigate }: PageProps) {
  const { hasPermission } = useAuth();
  const [data, setData] = useState<any>(settingsMock);
  const [loading, setLoading] = useState(true);
  const [configValues, setConfigValues] = useState<Record<string, any>>({});
  const canReadUsers = hasPermission('user:read');
  const visibleTabs = useMemo(
    () => (canReadUsers ? tabs : tabs.filter((item) => item.key !== 'settings-user')),
    [canReadUsers]
  );
  const effectiveSubKey = canReadUsers ? activeSubKey : activeSubKey === 'settings-user' ? 'settings-role' : activeSubKey;

  async function loadData() {
    setLoading(true);
    try {
      const payload = await getSettingsData();
      setData(payload);
      setConfigValues(payload.config?.runtime || payload.config || {});
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData();
  }, []);

  async function saveConfig() {
    await api.saveSettingsConfig(configValues);
    message.success('配置已保存');
    await loadData();
  }

  return (
    <div className="page-stack">
      <PageTabs items={visibleTabs} activeKey={effectiveSubKey} onChange={onSubNavigate} />
      <DataStateBanner
        scope="系统设置"
        loading={loading}
        source={data.dataSource}
        error={data.error}
        empty={data.empty}
        mockFallback={data.mockFallback}
        fallbackReason={data.fallbackReason}
        partialErrors={data.partialErrors}
        onRetry={loadData}
      />
      <MetricGrid items={data.metrics || []} icons={icons} loading={loading} minColumnWidth={190} />

      {effectiveSubKey === 'settings-user' && (
        canReadUsers ? <UserManagementPage /> : <SectionCard title="无权限"><p>当前账号没有用户管理权限。</p></SectionCard>
      )}

      {effectiveSubKey === 'settings-role' && (
        <TableCard title="权限矩阵" loading={loading} dataSource={(data.permissions || []).map((row: any[]) => ({ key: row[0], row }))} columns={[
          { title: '角色/模块', render: (_, record: any) => record.row[0] },
          ...['查看', '执行', '配置', '管理员', '审计'].map((title, index) => ({
            title,
            align: 'center' as const,
            render: (_: unknown, record: { row: unknown[] }) => (record.row[index + 1] ? '✓' : '-')
          }))
        ]} />
      )}

      {effectiveSubKey === 'settings-param' && (
        <Row gutter={[16, 16]} className="balanced-row">
          <Col xs={24} lg={8}>
            <ConfigCard title="参数配置" icon={<ApiOutlined />}>
              <Form layout="vertical">
                <Form.Item label="数据刷新间隔">
                  <Input value={configValues.data_refresh_interval} onChange={(event) => setConfigValues((prev) => ({ ...prev, data_refresh_interval: event.target.value }))} placeholder="15 分钟" />
                </Form.Item>
                <Form.Item label="预测计算超时时间">
                  <Input value={configValues.forecast_timeout} onChange={(event) => setConfigValues((prev) => ({ ...prev, forecast_timeout: event.target.value }))} placeholder="60 秒" />
                </Form.Item>
                <Form.Item label="风险预警阈值">
                  <Input value={configValues.risk_threshold} onChange={(event) => setConfigValues((prev) => ({ ...prev, risk_threshold: event.target.value }))} placeholder="85 %" />
                </Form.Item>
                <Button type="primary" onClick={saveConfig}>保存配置</Button>
              </Form>
            </ConfigCard>
          </Col>
          <Col xs={24} lg={8}>
            <ConfigCard title="通知配置" icon={<HeartOutlined />}>
              {['系统告警通知', '任务完成通知', '预警通知', '日报生成通知'].map((item, index) => (
                <div className="switch-row" key={item}>
                  <span>{item}</span>
                  <Switch defaultChecked={index < 3} onChange={() => message.success(`${item} 已更新`)} />
                </div>
              ))}
            </ConfigCard>
          </Col>
          <Col xs={24} lg={8}>
            <ConfigCard title="系统健康信息" icon={<HeartOutlined />}>
              <div className="health-list">{(data.health || []).map((item: any[]) => <p key={item[0]}><span>{item[0]}</span><strong>{item[1]}</strong></p>)}</div>
            </ConfigCard>
          </Col>
        </Row>
      )}

      {effectiveSubKey === 'settings-api' && (
        <Row gutter={[16, 16]} className="balanced-row">
          <Col xs={24} lg={8}><ConfigCard title="PostgreSQL 配置" icon={<DatabaseOutlined />}><pre className="detail-drawer-json">{JSON.stringify(data.config?.database || {}, null, 2)}</pre></ConfigCard></Col>
          <Col xs={24} lg={8}><ConfigCard title="模型网关配置" icon={<ApiOutlined />}><pre className="detail-drawer-json">{JSON.stringify(data.config?.model_gateway || {}, null, 2)}</pre></ConfigCard></Col>
          <Col xs={24} lg={8}><ConfigCard title="Web 服务配置" icon={<ApiOutlined />}><pre className="detail-drawer-json">{JSON.stringify(data.config?.web || {}, null, 2)}</pre></ConfigCard></Col>
        </Row>
      )}
    </div>
  );
}

function ConfigCard({ title, icon, children }: { title: string; icon: ReactNode; children: ReactNode }) {
  return <SectionCard className="config-card" title={<Space>{icon}{title}</Space>}>{children}</SectionCard>;
}

