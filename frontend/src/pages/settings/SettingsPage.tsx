import {
  ApiOutlined,
  AuditOutlined,
  BellOutlined,
  CheckCircleOutlined,
  CloudServerOutlined,
  DatabaseOutlined,
  DeleteOutlined,
  EditOutlined,
  EyeOutlined,
  HeartOutlined,
  KeyOutlined,
  LockOutlined,
  PlusOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
  SaveOutlined,
  SearchOutlined,
  SettingOutlined,
  ThunderboltOutlined,
  UsergroupAddOutlined
} from '@ant-design/icons';
import type { Dispatch, Key, ReactNode, SetStateAction } from 'react';
import { Alert, App, Button, Form, Input, InputNumber, Modal, Popconfirm, Progress, Select, Space, Switch, Table, Tag, Tooltip } from 'antd';
import { useEffect, useMemo, useState } from 'react';
import { api } from '../../api';
import { SectionCard } from '../../components/cards/SectionCard';
import { TableCard } from '../../components/cards/TableCard';
import { PageTabs } from '../../components/common/PageTabs';
import { DataStateBanner, SourceContextPanel } from '../../components/common/States';
import { MetricGrid } from '../../components/layout/UnifiedPage';
import { useAuth } from '../../context/AuthContext';
import { getSettingsData } from '../../services/settingsApi';
import type { PageProps } from '../../types/ui';

type UserItem = Record<string, any>;
type RoleInfo = Record<string, any>;

const tabs = [
  { key: 'settings-status', label: '系统状态总览' },
  { key: 'settings-user', label: '用户与权限管理' },
  { key: 'settings-api', label: '接口配置总览' }
];

const statusColors: Record<string, string> = {
  正常: 'success',
  异常: 'error',
  告警: 'warning',
  降级: 'warning',
  部分可用: 'warning',
  未配置: 'default',
  不可用: 'error',
  未接入: 'default',
  离线: 'default',
  启用: 'success',
  禁用: 'default',
  在线: 'success',
  离线用户: 'default',
  成功: 'success',
  失败: 'error'
};

const roleLabels: Record<string, string> = {
  admin: '超级管理员',
  analyst: '分析师',
  viewer: '查看者',
  developer: '开发者',
  operator: '操作员'
};

function userKey(row: UserItem) {
  return String(row.user_id || row.id || row.username);
}

function normalizeSettingsTab(key?: string) {
  if (key === 'settings-role' || key === 'settings-param') return 'settings-user';
  return tabs.some((item) => item.key === key) ? String(key) : 'settings-status';
}

function statusLabel(ok: boolean | undefined, unavailable = false) {
  if (unavailable) return '未接入';
  return ok ? '正常' : '告警';
}

function maskText(value: unknown) {
  const text = value === undefined || value === null || value === '' ? '--' : String(value);
  if (text.length <= 8 || text === '--') return text;
  return `${text.slice(0, 4)}${'*'.repeat(Math.min(12, Math.max(6, text.length - 8)))}${text.slice(-4)}`;
}

function formatTime(value: unknown) {
  return value ? String(value).replace('T', ' ').slice(0, 19) : '--';
}

function exportSystemStatus(rows: any[]) {
  const escape = (value: unknown) => `"${String(value ?? '').replace(/"/g, '""')}"`;
  const csv = [['模块', '状态', '摘要', '最近检查时间', '观测指标'], ...rows.map((row) => [row.module, row.status, row.summary, row.checkedAt, row.metric])]
    .map((row) => row.map(escape).join(','))
    .join('\r\n');
  const url = URL.createObjectURL(new Blob([`\uFEFF${csv}`], { type: 'text/csv;charset=utf-8' }));
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = '系统运行状态.csv';
  anchor.click();
  URL.revokeObjectURL(url);
}

export function SettingsPage({ activeSubKey, onSubNavigate }: PageProps) {
  const { message } = App.useApp();
  const { hasPermission, canPerformAction } = useAuth();
  const [data, setData] = useState<any>({ dataSource: 'backend_api', mockFallback: false });
  const [loading, setLoading] = useState(true);
  const [sourceRefreshedAt, setSourceRefreshedAt] = useState<string | null>(null);
  const [configValues, setConfigValues] = useState<Record<string, any>>({});
  const [users, setUsers] = useState<UserItem[]>([]);
  const [roles, setRoles] = useState<RoleInfo[]>([]);
  const [rolePermissionGroups, setRolePermissionGroups] = useState<Record<string, string[]>>({});
  const [auditLogs, setAuditLogs] = useState<any[]>([]);
  const [usersTotal, setUsersTotal] = useState(0);
  const [usersLoading, setUsersLoading] = useState(false);
  const [keyword, setKeyword] = useState('');
  const [selectedUserKeys, setSelectedUserKeys] = useState<Key[]>([]);
  const [createOpen, setCreateOpen] = useState(false);
  const [editing, setEditing] = useState<UserItem | null>(null);
  const [resetting, setResetting] = useState<UserItem | null>(null);
  const [interfaceEditing, setInterfaceEditing] = useState<any | null>(null);
  const [createForm] = Form.useForm();
  const [editForm] = Form.useForm();
  const [passwordForm] = Form.useForm();
  const [interfaceForm] = Form.useForm();
  const canReadUsers = hasPermission('user:read');
  const canWriteUsers = canPerformAction('user:write');
  const canReadAudit = hasPermission('audit:read');
  const canWriteSettings = canPerformAction('settings.write');
  const effectiveSubKey = canReadUsers ? normalizeSettingsTab(activeSubKey) : normalizeSettingsTab(activeSubKey) === 'settings-user' ? 'settings-status' : normalizeSettingsTab(activeSubKey);

  async function loadData(nextKeyword = keyword) {
    setLoading(true);
    try {
      const payload = await getSettingsData({ interfaceKeyword: nextKeyword });
      setData(payload);
      setSourceRefreshedAt(new Date().toISOString());
      setConfigValues(payload.config?.runtime || payload.config?.values || {});
      setAuditLogs(payload.auditLogs || []);
    } finally {
      setLoading(false);
    }
  }

  async function loadUsers(nextKeyword = keyword) {
    if (!canReadUsers) return;
    setUsersLoading(true);
    try {
      const [userPayload, rolePayload] = await Promise.all([
        api.settingsUsers({ keyword: nextKeyword, page: 1, page_size: 50 }),
        api.settingsRolePermissions()
      ]);
      setUsers(userPayload.items || []);
      setUsersTotal(userPayload.total || 0);
      setRoles(rolePayload.matrix || rolePayload.roles || []);
      setRolePermissionGroups(rolePayload.permission_groups || {});
    } catch (error) {
      message.error(error instanceof Error ? error.message : '用户与角色数据加载失败');
    } finally {
      setUsersLoading(false);
    }
  }

  useEffect(() => {
    loadData();
  }, [canReadAudit]);

  useEffect(() => {
    loadUsers();
  }, [canReadUsers]);

  async function saveConfig() {
    if (!canWriteSettings) {
      message.warning('当前账号没有系统配置写入权限');
      return;
    }
    await api.updateSettingsRuntimeConfig({ values: configValues });
    message.success('配置已保存');
    await loadData();
  }

  async function testRuntime(name: string, fn: () => Promise<any>) {
    try {
      await fn();
      message.success(`${name} 连接检查完成`);
    } catch (error) {
      message.error(error instanceof Error ? error.message : `${name} 连接检查失败`);
    } finally {
      await loadData();
    }
  }

  async function testAllInterfaces() {
    const results = await api.testAllSettingsInterfaces();
    const failed = Number(results.failed_count || 0);
    if (failed) message.warning(`接口检测完成，${failed} 项失败`);
    else message.success('全部接口检测完成');
    await loadData();
  }

  function openInterfaceEdit(row: any) {
    const source = row?.raw || row || {};
    setInterfaceEditing(source);
    interfaceForm.setFieldsValue({
      interface_name: source.interface_name || source.name,
      service_url: source.service_url || source.address,
      host: source.host,
      port: source.port,
      database_name: source.database_name,
      username: source.username,
      health_path: source.health_path,
      timeout_seconds: source.timeout_seconds,
      is_enabled: source.is_enabled !== false
    });
  }

  async function submitInterfaceEdit() {
    if (!interfaceEditing) return;
    const values = await interfaceForm.validateFields();
    await api.updateSettingsInterfaceConfig(interfaceEditing.interface_key || interfaceEditing.id, values);
    message.success('接口配置已更新');
    setInterfaceEditing(null);
    interfaceForm.resetFields();
    await loadData(keyword);
  }

  async function toggleInterface(row: any) {
    const id = row.interfaceKey || row.interface_key || row.key || row.id;
    await api.updateSettingsInterfaceConfig(id, { is_enabled: !row.enabled });
    message.success(row.enabled ? '接口已禁用' : '接口已启用');
    await loadData(keyword);
  }

  async function viewInterfaceLogs(row: any) {
    const payload = await api.settingsInterfaceTestLogs({ interface_name: row.name || row.interface_name, limit: 100 });
    setData((prev: any) => ({ ...prev, interfaceTestLogs: payload.items || [] }));
    message.success('已加载该接口测试日志');
  }

  async function submitCreate() {
    const values = await createForm.validateFields();
    await api.createSettingsUser(values);
    message.success('用户已创建');
    setCreateOpen(false);
    createForm.resetFields();
    await Promise.all([loadUsers(), loadData()]);
  }

  async function submitEdit() {
    if (!editing) return;
    const values = await editForm.validateFields();
    await api.updateSettingsUser(userKey(editing), values);
    message.success('用户信息已更新');
    setEditing(null);
    await Promise.all([loadUsers(), loadData()]);
  }

  async function submitResetPassword() {
    if (!resetting) return;
    const values = await passwordForm.validateFields();
    if (values.new_password !== values.confirm_password) {
      message.error('两次输入的密码不一致');
      return;
    }
    await api.resetSettingsUserPassword(userKey(resetting), values.new_password);
    message.success('密码已重置');
    setResetting(null);
    passwordForm.resetFields();
    await loadData();
  }

  async function toggleUser(row: UserItem) {
    if (row.is_active) await api.disableSettingsUser(userKey(row));
    else await api.enableSettingsUser(userKey(row));
    message.success(row.is_active ? '用户已禁用' : '用户已启用');
    await Promise.all([loadUsers(), loadData()]);
  }

  async function updateRolePermission(role: RoleInfo, groupKey: string, enabled: boolean) {
    const backendGroup = groupKey === 'config' ? 'configure' : groupKey;
    if (backendGroup === 'admin') {
      message.info('管理员标识由角色本身决定，不能通过权限矩阵切换');
      return;
    }
    const group = rolePermissionGroups[backendGroup] || [];
    if (!group.length) {
      message.warning('当前权限分组没有可配置项');
      return;
    }
    const permissions = new Set<string>(role.permissions || []);
    group.forEach((permission) => enabled ? permissions.add(permission) : permissions.delete(permission));
    try {
      const payload = await api.updateSettingsRolePermissions({
        roles: [{
          role_id: role.role_id || role.name,
          role_name: role.role_name || role.label || role.role_id || role.name,
          description: role.description || '',
          permissions: Array.from(permissions).sort()
        }]
      });
      setRoles(payload.matrix || payload.roles || []);
      setRolePermissionGroups(payload.permission_groups || rolePermissionGroups);
      message.success('角色权限已更新并写入鉴权配置');
    } catch (error) {
      message.error(error instanceof Error ? error.message : '角色权限更新失败');
    }
  }

  async function updateSecurityPolicy(values: Record<string, any>) {
    try {
      const payload = await api.updateSettingsSecurityPolicy({ values });
      setData((current: any) => ({ ...current, securityPolicy: payload }));
      message.success('安全策略已更新');
      return payload;
    } catch (error) {
      message.error(error instanceof Error ? error.message : '安全策略更新失败');
      throw error;
    }
  }

  const roleOptions = roles.map((role) => {
    const name = role.name || role.role_id;
    return { value: name, label: role.label || role.role_name || roleLabels[name] || name };
  });
  const systemRows = buildSystemRows(data, auditLogs);
  const okCount = systemRows.filter((item) => item.status === '正常').length;
  const alertCount = systemRows.filter((item) => item.status === '告警' || item.status === '异常').length;
  const systemHealth = systemRows.length ? Math.round((okCount / systemRows.length) * 10000) / 100 : 0;
  const interfaceRows = buildInterfaceRows(data);
  const interfaceOk = interfaceRows.filter((item) => item.status === '正常').length;
  const interfaceError = interfaceRows.filter((item) => item.status === '异常' || item.status === '告警').length;
  const avgLatency = averageLatency(interfaceRows);

  const statusMetrics = [
    { title: '在线用户数', value: data.statusOverview?.online_users ?? 0, unit: '人', trendLabel: '用户表活跃状态', note: data.currentUser?.username || '', status: data.statusOverview?.online_users ? 'success' : 'warning', icon: <UsergroupAddOutlined /> },
    { title: '正常服务数', value: `${data.statusOverview?.healthy_services ?? okCount} / ${data.statusOverview?.total_services ?? systemRows.length}`, trendLabel: '实时健康检查', status: (data.statusOverview?.warning_count ?? alertCount) ? 'warning' : 'success', icon: <SafetyCertificateOutlined /> },
    { title: '异常告警数', value: (data.statusOverview?.warning_count ?? 0) + (data.statusOverview?.error_count ?? 0), trendLabel: '需关注模块', status: (data.statusOverview?.warning_count ?? alertCount) ? 'warning' : 'success', icon: <BellOutlined /> },
    { title: '系统健康度', value: (data.statusOverview?.system_health_score ?? systemHealth).toFixed(2), unit: '%', trendLabel: '按健康探针计算', status: (data.statusOverview?.system_health_score ?? systemHealth) >= 90 ? 'success' : 'warning', icon: <HeartOutlined /> }
  ];

  const userMetrics = [
    { title: '用户总数', value: data.usersOverview?.user_total ?? usersTotal ?? users.length, unit: '个', trendLabel: '用户表记录', status: 'info', icon: <UsergroupAddOutlined /> },
    { title: '在线用户', value: data.usersOverview?.online_users ?? 0, unit: '人', trendLabel: '用户表活跃状态', status: data.usersOverview?.online_users ? 'success' : 'warning', icon: <CheckCircleOutlined /> },
    { title: '角色数', value: data.usersOverview?.role_total ?? roles.length, unit: '个', trendLabel: '权限接口返回', status: 'info', icon: <SafetyCertificateOutlined /> },
    { title: '异常登录', value: data.usersOverview?.abnormal_login_count ?? auditLogs.filter((item) => item.action === 'auth.login_failed' || item.status === 'failed').length, unit: '次', trendLabel: '审计日志统计', status: 'success', icon: <BellOutlined /> }
  ];

  const apiMetrics = [
    { title: '接口总数', value: data.interfaceOverview?.interface_total ?? interfaceRows.length, unit: '个', trendLabel: '当前可观测接口', status: 'info', icon: <ApiOutlined /> },
    { title: '正常接口', value: data.interfaceOverview?.normal_count ?? interfaceOk, unit: '个', trendLabel: '健康探针返回', status: 'success', icon: <CheckCircleOutlined /> },
    { title: '异常接口', value: data.interfaceOverview?.abnormal_count ?? interfaceError, unit: '个', trendLabel: '需排查', status: (data.interfaceOverview?.abnormal_count ?? interfaceError) ? 'warning' : 'success', icon: <BellOutlined /> },
    { title: '平均响应耗时', value: (data.interfaceOverview?.average_latency_ms ?? avgLatency) || '--', unit: data.interfaceOverview?.average_latency_ms || avgLatency ? 'ms' : '', trendLabel: data.interfaceOverview?.average_latency_ms || avgLatency ? '可观测项平均值' : '接口未返回耗时', status: 'info', icon: <ThunderboltOutlined /> }
  ];

  return (
    <div className="settings-workbench page-stack">
      <div className="settings-tabs-row">
        <PageTabs items={tabs.filter((item) => item.key !== 'settings-user' || canReadUsers)} activeKey={effectiveSubKey} onChange={onSubNavigate} />
        <SettingsToolbar
          activeKey={effectiveSubKey}
          keyword={keyword}
          setKeyword={setKeyword}
          onUserSearch={() => effectiveSubKey === 'settings-user' ? loadUsers(keyword) : loadData(keyword)}
          onRefresh={() => Promise.all([loadData(), loadUsers()])}
          onCreate={() => setCreateOpen(true)}
          onSave={saveConfig}
          onTestAll={testAllInterfaces}
          canCreate={canWriteUsers}
          canSave={canWriteSettings}
          selectedCount={selectedUserKeys.length}
          onExportStatus={() => {
            exportSystemStatus(systemRows);
            message.success('系统运行状态已导出');
          }}
        />
      </div>
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

      {effectiveSubKey === 'settings-status' && (
        <SystemStatusTab
          loading={loading}
          metrics={statusMetrics}
          rows={systemRows}
          healthRecords={data.healthRecords || []}
          health={data.statusOverview?.system_health_score ?? systemHealth}
          sourceMeta={data.sourceContext?.meta}
          sourceRefreshedAt={sourceRefreshedAt}
          refreshSourceContext={loadData}
          configValues={configValues}
          setConfigValues={setConfigValues}
          saveConfig={saveConfig}
          canWriteSettings={canWriteSettings}
        />
      )}

      {effectiveSubKey === 'settings-user' && (
        canReadUsers ? (
          <UserPermissionTab
            loading={usersLoading}
            metrics={userMetrics}
            users={users}
            usersTotal={usersTotal}
            roles={roles}
            auditLogs={auditLogs}
            securityPolicy={data.securityPolicy}
            selectedKeys={selectedUserKeys}
            setSelectedKeys={setSelectedUserKeys}
            canWrite={canWriteUsers}
            onEdit={(row) => {
              setEditing(row);
              editForm.setFieldsValue({
                email: row.email,
                display_name: row.display_name,
                role: row.role,
                is_active: row.is_active
              });
            }}
            onReset={setResetting}
            onToggle={toggleUser}
            onRolePermissionChange={updateRolePermission}
            onSecurityPolicyChange={updateSecurityPolicy}
          />
        ) : (
          <SectionCard title="无权限">
            <p>当前账号没有用户管理权限。</p>
          </SectionCard>
        )
      )}

      {effectiveSubKey === 'settings-api' && (
        <InterfaceConfigTab
          loading={loading}
          metrics={apiMetrics}
          data={data}
          rows={interfaceRows}
          onTest={testRuntime}
          onEdit={openInterfaceEdit}
          onToggle={toggleInterface}
          onViewLogs={viewInterfaceLogs}
          canWrite={canWriteSettings}
        />
      )}

      <UserModals
        createOpen={createOpen}
        setCreateOpen={setCreateOpen}
        editing={editing}
        setEditing={setEditing}
        resetting={resetting}
        setResetting={setResetting}
        createForm={createForm}
        editForm={editForm}
        passwordForm={passwordForm}
        roleOptions={roleOptions}
        submitCreate={submitCreate}
        submitEdit={submitEdit}
        submitResetPassword={submitResetPassword}
      />
      <InterfaceConfigModal
        editing={interfaceEditing}
        setEditing={setInterfaceEditing}
        form={interfaceForm}
        submit={submitInterfaceEdit}
      />
    </div>
  );
}

function ConfigCard({ title, icon, children }: { title: string; icon: ReactNode; children: ReactNode }) {
  return <SectionCard className="config-card" title={<Space>{icon}{title}</Space>}>{children}</SectionCard>;
}

function SettingsToolbar({
  activeKey,
  keyword,
  setKeyword,
  onUserSearch,
  onRefresh,
  onCreate,
  onSave,
  onTestAll,
  canCreate,
  canSave,
  selectedCount,
  onExportStatus
}: {
  activeKey: string;
  keyword: string;
  setKeyword: (value: string) => void;
  onUserSearch: () => void;
  onRefresh: () => void;
  onCreate: () => void;
  onSave: () => void;
  onTestAll: () => void;
  canCreate: boolean;
  canSave: boolean;
  selectedCount: number;
  onExportStatus: () => void;
}) {
  if (activeKey === 'settings-user') {
    return (
      <Space className="settings-tab-actions" wrap>
        <Input.Search
          allowClear
          placeholder="搜索用户名 / 显示名 / 角色"
          value={keyword}
          onChange={(event) => setKeyword(event.target.value)}
          onSearch={onUserSearch}
          style={{ width: 300 }}
        />
        {canCreate ? <Button type="primary" icon={<PlusOutlined />} onClick={onCreate}>新增用户</Button> : null}
        <Button icon={<ReloadOutlined />} onClick={onRefresh}>刷新</Button>
        <Tooltip title={selectedCount ? '当前仅支持逐个处理已选用户' : '请选择用户后再执行批量操作'}>
          <Button disabled>批量操作</Button>
        </Tooltip>
      </Space>
    );
  }
  if (activeKey === 'settings-api') {
    return (
      <Space className="settings-tab-actions" wrap>
        <Input.Search
          allowClear
          prefix={<SearchOutlined />}
          placeholder="搜索接口名称 / 服务类型"
          value={keyword}
          onChange={(event) => setKeyword(event.target.value)}
          onSearch={onUserSearch}
          style={{ width: 300 }}
        />
        {canSave ? <Button onClick={onTestAll}>测试全部接口</Button> : null}
        <Button icon={<ReloadOutlined />} onClick={onRefresh}>刷新</Button>
        {canSave ? <Button type="primary" icon={<SaveOutlined />} onClick={onSave}>保存配置</Button> : null}
      </Space>
    );
  }
  return (
    <Space className="settings-tab-actions" wrap>
      <Input.Search
        allowClear
        prefix={<SearchOutlined />}
        placeholder="搜索模块或服务"
        value={keyword}
        onChange={(event) => setKeyword(event.target.value)}
        onSearch={onUserSearch}
        style={{ width: 280 }}
      />
      <Button icon={<ReloadOutlined />} onClick={onRefresh}>刷新</Button>
      <Button icon={<SaveOutlined />} onClick={onExportStatus}>导出报告</Button>
    </Space>
  );
}

function SystemStatusTab({
  loading,
  metrics,
  rows,
  healthRecords,
  health,
  sourceMeta,
  sourceRefreshedAt,
  refreshSourceContext,
  configValues,
  setConfigValues,
  saveConfig,
  canWriteSettings
}: {
  loading: boolean;
  metrics: any[];
  rows: any[];
  healthRecords: any[];
  health: number;
  sourceMeta: any;
  sourceRefreshedAt: string | null;
  refreshSourceContext: () => void;
  configValues: Record<string, any>;
  setConfigValues: Dispatch<SetStateAction<Record<string, any>>>;
  saveConfig: () => void;
  canWriteSettings: boolean;
}) {
  const recent = healthRecords.slice(0, 8).map((item, index) => ({
    key: [
      item.id || item.key || item.module_key || item.module || 'health-check',
      item.checked_at || item.checkedAt || 'unknown-time',
      index
    ].join('-'),
    time: item.checked_at || item.checkedAt,
    module: item.module_name || item.module,
    result: item.status_label || item.status,
    latency: item.latency_ms !== undefined && item.latency_ms !== null ? `${item.latency_ms}ms` : '--',
    remark: item.summary
  }));
  return (
    <>
      <MetricGrid items={metrics} loading={loading} minColumnWidth={240} />
      <SourceContextPanel
        meta={sourceMeta}
        loading={loading}
        lastRefreshedAt={sourceRefreshedAt}
        onRefresh={refreshSourceContext}
      />
      <div className="settings-status-grid">
        <SectionCard title="运行状态摘要" loading={loading}>
          <div className="settings-status-list">
            {rows.slice(0, 6).map((item) => (
              <div className="settings-status-row" key={item.key}>
                <span className={`settings-row-icon settings-row-icon-${item.tone}`}>{item.icon}</span>
                <div>
                  <strong>{item.module}</strong>
                  <p>{item.summary}</p>
                </div>
                <Tag color={statusColors[item.status] || 'default'}>{item.status}</Tag>
                <Button type="link" size="small" onClick={() => Modal.info({ title: item.module, content: `${item.summary || '--'}\n${item.metric || ''}` })}>详情</Button>
              </div>
            ))}
          </div>
          <div className="settings-health-progress">
            <span>系统健康度</span>
            <Progress percent={health} strokeColor="#0fb98a" size="small" />
          </div>
        </SectionCard>
        <TableCard
          title="系统健康明细"
          loading={loading}
          minHeight={360}
          dataSource={rows}
          pagination={false}
          columns={[
            { title: '模块', dataIndex: 'module', width: 150 },
            { title: '状态', dataIndex: 'status', width: 90, render: (value) => <Tag color={statusColors[value] || 'default'}>{value}</Tag> },
            { title: '摘要', dataIndex: 'summary', ellipsis: true },
            { title: '最近检查时间', dataIndex: 'checkedAt', width: 170 },
            { title: '延迟 / QPS / 错误率', dataIndex: 'metric', width: 170 }
          ]}
        />
      </div>
      <div className="settings-bottom-grid">
        <SectionCard title="系统运行参数" className="settings-params-card">
          <div className="settings-param-grid">
            <ParamInput label="数据刷新间隔" value={configValues.data_refresh_interval_minutes} suffix="分钟" onChange={(value) => setConfigValues((prev) => ({ ...prev, data_refresh_interval_minutes: value }))} />
            <ParamInput label="预测计算超时时间" value={configValues.forecast_timeout_seconds} suffix="秒" onChange={(value) => setConfigValues((prev) => ({ ...prev, forecast_timeout_seconds: value }))} />
            <ParamInput label="风险阈值" value={configValues.risk_threshold_percent} suffix="%" onChange={(value) => setConfigValues((prev) => ({ ...prev, risk_threshold_percent: value }))} />
            <ParamInput label="异常告警阈值" value={configValues.anomaly_warning_threshold_percent} suffix="%" onChange={(value) => setConfigValues((prev) => ({ ...prev, anomaly_warning_threshold_percent: value }))} />
            <SwitchParam label="邮件通知" checked={Boolean(configValues.email_notification_enabled ?? true)} onChange={(value) => setConfigValues((prev) => ({ ...prev, email_notification_enabled: value }))} />
            <SwitchParam label="短信通知" checked={Boolean(configValues.sms_notification_enabled)} onChange={(value) => setConfigValues((prev) => ({ ...prev, sms_notification_enabled: value }))} />
            <SwitchParam label="系统维护模式" checked={Boolean(configValues.maintenance_mode_enabled)} onChange={(value) => setConfigValues((prev) => ({ ...prev, maintenance_mode_enabled: value }))} />
            <SwitchParam label="自动数据备份" checked={Boolean(configValues.auto_backup_enabled ?? true)} onChange={(value) => setConfigValues((prev) => ({ ...prev, auto_backup_enabled: value }))} />
          </div>
          {canWriteSettings ? <Button type="primary" icon={<SaveOutlined />} onClick={saveConfig}>保存运行参数</Button> : null}
        </SectionCard>
        <TableCard
          title="最近健康检查记录"
          minHeight={280}
          dataSource={recent}
          pagination={false}
          columns={[
            { title: '检查时间', dataIndex: 'time', width: 170 },
            { title: '检查模块', dataIndex: 'module', width: 140 },
            { title: '检查结果', dataIndex: 'result', width: 90, render: (value) => <Tag color={statusColors[value] || 'default'}>{value}</Tag> },
            { title: '响应耗时', dataIndex: 'latency', width: 110 },
            { title: '说明', dataIndex: 'remark', ellipsis: true }
          ]}
        />
      </div>
    </>
  );
}

function UserPermissionTab({
  loading,
  metrics,
  users,
  usersTotal,
  roles,
  auditLogs,
  securityPolicy,
  selectedKeys,
  setSelectedKeys,
  canWrite,
  onEdit,
  onReset,
  onToggle,
  onRolePermissionChange,
  onSecurityPolicyChange
}: {
  loading: boolean;
  metrics: any[];
  users: UserItem[];
  usersTotal: number;
  roles: RoleInfo[];
  auditLogs: any[];
  securityPolicy: any;
  selectedKeys: Key[];
  setSelectedKeys: (keys: Key[]) => void;
  canWrite: boolean;
  onEdit: (row: UserItem) => void;
  onReset: (row: UserItem) => void;
  onToggle: (row: UserItem) => void;
  onRolePermissionChange: (role: RoleInfo, groupKey: string, enabled: boolean) => Promise<void>;
  onSecurityPolicyChange: (values: Record<string, any>) => Promise<any>;
}) {
  const permissionRows = roles.map((role) => ({
    key: role.name || role.role_id,
    role_id: role.role_id || role.name,
    role_name: role.role_name || role.label || role.role_id || role.name,
    description: role.description || '',
    permissions: role.permissions || [],
    role: role.name || role.role_id,
    view: role.view ?? hasAny(role.permissions, ['dashboard:read', 'data:read', '*']),
    execute: role.execute ?? hasAny(role.permissions, ['task:run', 'forecast:run', '*']),
    config: role.configure ?? role.config ?? hasAny(role.permissions, ['settings:write', 'model:write', '*']),
    admin: role.admin ?? hasAny(role.permissions, ['*']),
    audit: role.audit ?? hasAny(role.permissions, ['audit:read', '*'])
  }));
  const [policyValues, setPolicyValues] = useState<Record<string, any>>(securityPolicy?.values || {});
  const [policySaving, setPolicySaving] = useState(false);
  useEffect(() => setPolicyValues(securityPolicy?.values || {}), [securityPolicy]);

  async function persistPolicy(nextValues: Record<string, any>) {
    if (!canWrite || policySaving) return;
    setPolicySaving(true);
    try {
      const payload = await onSecurityPolicyChange(nextValues);
      setPolicyValues(payload?.values || nextValues);
    } catch {
      setPolicyValues(securityPolicy?.values || {});
    } finally {
      setPolicySaving(false);
    }
  }
  return (
    <>
      <MetricGrid items={metrics} loading={loading} minColumnWidth={240} />
      <div className="settings-user-layout">
        <TableCard
          title="用户管理"
          loading={loading}
          minHeight={390}
          dataSource={users}
          rowKey={userKey}
          rowSelection={canWrite ? { selectedRowKeys: selectedKeys, onChange: setSelectedKeys } : undefined}
          pagination={{ total: usersTotal, pageSize: 5, showSizeChanger: false }}
          scroll={{ x: 980, y: 260 }}
          columns={[
            { title: '用户名', dataIndex: 'username', width: 120 },
            { title: '显示名', dataIndex: 'display_name', width: 120, render: (value, row) => value || row.username },
            { title: '角色', dataIndex: 'role', width: 110, render: (value) => <Tag>{roleLabels[value] || value}</Tag> },
            { title: '部门 / 岗位', width: 160, render: () => '平台运营 / 管理岗' },
            { title: '状态', dataIndex: 'is_active', width: 90, render: (value) => <Tag color={value ? 'success' : 'default'}>{value ? '启用' : '禁用'}</Tag> },
            { title: '最近登录', dataIndex: 'last_login_at', width: 170, render: formatTime },
            { title: '创建时间', dataIndex: 'created_at', width: 170, render: formatTime },
            {
              title: '操作',
              fixed: 'right',
              width: 260,
              render: (_, row) => canWrite ? (
                <Space size={4}>
                  <Button type="link" size="small" onClick={() => onEdit(row)}>编辑</Button>
                  <Popconfirm title={row.is_active ? '确认禁用该用户？' : '确认启用该用户？'} onConfirm={() => onToggle(row)}>
                    <Button type="link" size="small" danger={row.is_active}>{row.is_active ? '禁用' : '启用'}</Button>
                  </Popconfirm>
                  <Button type="link" size="small" onClick={() => onReset(row)}>重置密码</Button>
                  <Tooltip title="角色分配通过编辑用户角色完成">
                    <Button type="link" size="small" onClick={() => onEdit(row)}>分配角色</Button>
                  </Tooltip>
                  <Tooltip title="当前后端提供禁用，不提供物理删除接口">
                    <Button type="link" size="small" danger disabled icon={<DeleteOutlined />}>删除</Button>
                  </Tooltip>
                </Space>
              ) : <span className="settings-readonly-label">只读</span>
            }
          ]}
        />
        <div className="settings-user-side">
          <TableCard
            title="角色权限矩阵"
            minHeight={210}
            dataSource={permissionRows}
            pagination={false}
            columns={[
              { title: '角色', dataIndex: 'role', width: 110 },
              ...['view', 'execute', 'config', 'admin', 'audit'].map((key, index) => ({
                title: ['查看', '执行', '配置', '管理员', '审计'][index],
                dataIndex: key,
                align: 'center' as const,
                render: (value: boolean, role: RoleInfo) => {
                  const editable = canWrite && key !== 'admin' && (role.role_id || role.name) !== 'admin';
                  const content = value ? <CheckCircleOutlined className="settings-check" /> : <span className="settings-dash">--</span>;
                  if (!editable) return content;
                  const toggle = () => onRolePermissionChange(role, key, !value);
                  return (
                    <Tooltip title={`点击${value ? '取消' : '授予'}该权限分组`}>
                      <span role="button" tabIndex={0} aria-label={`${role.role_name || role.role_id}-${key}`} onClick={toggle} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') toggle(); }}>
                        {content}
                      </span>
                    </Tooltip>
                  );
                }
              }))
            ]}
          />
          <SectionCard title="密码与安全策略" className="settings-security-card">
            <div className="settings-security-grid">
              <ParamInput label="密码最小长度" value={policyValues.password_min_length ?? '--'} suffix="位" disabled={!canWrite || policySaving} onChange={(value) => setPolicyValues((current) => ({ ...current, password_min_length: value }))} onBlur={() => persistPolicy(policyValues)} />
              <ParamInput label="登录失败锁定次数" value={policyValues.login_failed_lock_count ?? '--'} suffix="次" disabled={!canWrite || policySaving} onChange={(value) => setPolicyValues((current) => ({ ...current, login_failed_lock_count: value }))} onBlur={() => persistPolicy(policyValues)} />
              <ParamInput label="会话超时时间" value={policyValues.session_timeout_minutes ?? '--'} suffix="分钟" disabled={!canWrite || policySaving} onChange={(value) => setPolicyValues((current) => ({ ...current, session_timeout_minutes: value }))} onBlur={() => persistPolicy(policyValues)} />
              <SwitchParam label="双因素认证（2FA）" checked={Boolean(policyValues.two_factor_enabled)} disabled={!canWrite || policySaving} onChange={(value) => { const next = { ...policyValues, two_factor_enabled: value }; setPolicyValues(next); void persistPolicy(next); }} />
              <SwitchParam label="强制定期修改密码" checked={Boolean(policyValues.force_periodic_password_change)} disabled={!canWrite || policySaving} onChange={(value) => { const next = { ...policyValues, force_periodic_password_change: value }; setPolicyValues(next); void persistPolicy(next); }} />
              <SwitchParam label="管理员重置密码" checked={Boolean(policyValues.admin_reset_password_enabled)} disabled={!canWrite || policySaving} onChange={(value) => { const next = { ...policyValues, admin_reset_password_enabled: value }; setPolicyValues(next); void persistPolicy(next); }} />
            </div>
            <Alert type="info" showIcon message="密码长度、登录锁定、会话超时和管理员重置策略会实时生效；2FA 在用户登记链路完成前不能启用。" />
          </SectionCard>
        </div>
      </div>
      <TableCard
        title="操作审计"
        minHeight={260}
        dataSource={auditLogs.map((item, index) => ({ key: item.id || index, ...item }))}
        pagination={{ pageSize: 5, showSizeChanger: false }}
        columns={[
          { title: '操作时间', dataIndex: 'created_at', width: 180, render: formatTime },
          { title: '操作人', dataIndex: 'username', width: 120, render: (value, row) => value || row.user || row.actor || '--' },
          { title: '操作类型', dataIndex: 'action', width: 170 },
          { title: '操作对象', dataIndex: 'resource_type', width: 140, render: (value, row) => [value, row.resource_id].filter(Boolean).join(' / ') || '--' },
          { title: 'IP 地址', dataIndex: 'ip_address', width: 140 },
          { title: '操作结果', dataIndex: 'status', width: 100, render: (value) => <Tag color={value === 'failed' ? 'error' : 'success'}>{value === 'failed' ? '失败' : '成功'}</Tag> }
        ]}
      />
    </>
  );
}

function InterfaceConfigTab({
  loading,
  metrics,
  data,
  rows,
  onTest,
  onEdit,
  onToggle,
  onViewLogs,
  canWrite
}: {
  loading: boolean;
  metrics: any[];
  data: any;
  rows: any[];
  onTest: (name: string, fn: () => Promise<any>) => void;
  onEdit: (row: any) => void;
  onToggle: (row: any) => void;
  onViewLogs: (row: any) => void;
  canWrite: boolean;
}) {
  const cards = (data.interfaceConfigs || []).map((item: any) => ({
    key: item.interface_key || item.id,
    title: item.interface_name || item.name,
    icon: iconForInterface(item.interface_type || item.interface_key),
    status: item.status === 'normal',
    statusText: item.status_label || item.status || '--',
    items: (item.display_fields || []).slice(0, 6).map((field: any) => [field.label, field.value]),
    action: () => onTest(item.interface_name || item.interface_key, () => api.testSettingsInterface(item.interface_key || item.id)),
    edit: () => onEdit(item)
  }));
  return (
    <>
      <MetricGrid items={metrics} loading={loading} minColumnWidth={240} />
      <div className="settings-api-grid">
        {cards.map((card) => (
          <ConfigCard key={card.key || card.title} title={card.title} icon={card.icon}>
            <Tag color={card.status ? 'success' : 'warning'} className="settings-card-status">{card.statusText}</Tag>
            <div className="settings-config-list">
              {card.items.map(([label, value]) => (
                <p key={label}><span>{label}</span><strong>{value || '--'}</strong></p>
              ))}
            </div>
            {canWrite ? <Space>
              <Button onClick={card.action}>测试连接</Button>
              <Button icon={<EditOutlined />} onClick={card.edit}>编辑配置</Button>
            </Space> : null}
          </ConfigCard>
        ))}
      </div>
      <TableCard
        title="接口总览"
        loading={loading}
        minHeight={320}
        dataSource={rows}
        pagination={{ pageSize: 8, showSizeChanger: false }}
        columns={[
          { title: '接口名称', dataIndex: 'name', width: 160 },
          { title: '接口类型', dataIndex: 'type', width: 130 },
          { title: '服务地址', dataIndex: 'address', ellipsis: true },
          { title: '状态', dataIndex: 'status', width: 90, render: (value) => <Tag color={statusColors[value] || 'default'}>{value}</Tag> },
          { title: '响应耗时', dataIndex: 'latency', width: 110 },
          { title: '成功率', dataIndex: 'successRate', width: 100 },
          { title: '最近检测时间', dataIndex: 'checkedAt', width: 170 },
          {
            title: '操作',
            width: 230,
            render: (_, row) => (
              <Space size={4}>
                {canWrite ? <Button type="link" size="small" onClick={() => onTest(row.name, () => api.testSettingsInterface(row.interfaceKey || row.key))}>测试连接</Button> : null}
                {canWrite ? <Button type="link" size="small" onClick={() => onEdit(row.raw || row)}>编辑</Button> : null}
                <Button type="link" size="small" onClick={() => onViewLogs(row)}>查看日志</Button>
                {canWrite ? <Button type="link" size="small" onClick={() => onToggle(row)}>{row.enabled === false ? '启用' : '禁用'}</Button> : null}
              </Space>
            )
          }
        ]}
      />
      <TableCard
        title="接口测试日志"
        minHeight={240}
        dataSource={(data.interfaceTestLogs || []).map((item: any, index: number) => ({
          key: item.id || index,
          checkedAt: item.tested_at,
          name: item.interface_name,
          result: item.test_result === 'success' ? '成功' : '失败',
          latency: item.latency_ms !== undefined && item.latency_ms !== null ? `${item.latency_ms}ms` : '--',
          error: item.error_message || '--',
          operator: item.tested_by || '--'
        }))}
        pagination={false}
        columns={[
          { title: '测试时间', dataIndex: 'checkedAt', width: 170 },
          { title: '接口名称', dataIndex: 'name', width: 170 },
          { title: '测试结果', dataIndex: 'result', width: 90, render: (value) => <Tag color={value === '成功' ? 'success' : 'error'}>{value}</Tag> },
          { title: '响应耗时', dataIndex: 'latency', width: 110 },
          { title: '错误信息', dataIndex: 'error', ellipsis: true },
          { title: '操作人', dataIndex: 'operator' }
        ]}
      />
    </>
  );
}

function UserModals({
  createOpen,
  setCreateOpen,
  editing,
  setEditing,
  resetting,
  setResetting,
  createForm,
  editForm,
  passwordForm,
  roleOptions,
  submitCreate,
  submitEdit,
  submitResetPassword
}: any) {
  return (
    <>
      <Modal title="新增用户" open={createOpen} onCancel={() => setCreateOpen(false)} onOk={submitCreate} okText="创建">
        <Form form={createForm} layout="vertical" initialValues={{ role: 'viewer', is_active: true }}>
          <Form.Item name="username" label="用户名" rules={[{ required: true, min: 3, message: '用户名至少 3 个字符' }]}><Input autoComplete="off" /></Form.Item>
          <Form.Item name="display_name" label="显示名"><Input /></Form.Item>
          <Form.Item name="email" label="邮箱" rules={[{ type: 'email', message: '邮箱格式不正确' }]}><Input autoComplete="off" /></Form.Item>
          <Form.Item name="password" label="初始密码" rules={[{ required: true, min: 8, message: '密码至少 8 个字符' }]}><Input.Password autoComplete="new-password" /></Form.Item>
          <Form.Item name="role" label="角色" rules={[{ required: true }]}><Select options={roleOptions} /></Form.Item>
          <Form.Item name="is_active" label="状态"><Select options={[{ value: true, label: '启用' }, { value: false, label: '禁用' }]} /></Form.Item>
        </Form>
      </Modal>
      <Modal title="编辑用户" open={Boolean(editing)} onCancel={() => setEditing(null)} onOk={submitEdit} okText="保存">
        <Form form={editForm} layout="vertical">
          <Form.Item name="display_name" label="显示名"><Input /></Form.Item>
          <Form.Item name="email" label="邮箱" rules={[{ type: 'email', message: '邮箱格式不正确' }]}><Input /></Form.Item>
          <Form.Item name="role" label="角色"><Select options={roleOptions} /></Form.Item>
          <Form.Item name="is_active" label="状态"><Select options={[{ value: true, label: '启用' }, { value: false, label: '禁用' }]} /></Form.Item>
        </Form>
      </Modal>
      <Modal title="重置密码" open={Boolean(resetting)} onCancel={() => setResetting(null)} onOk={submitResetPassword} okText="重置">
        <Form form={passwordForm} layout="vertical">
          <Form.Item name="new_password" label="新密码" rules={[{ required: true, min: 8, message: '密码至少 8 个字符' }]}><Input.Password autoComplete="new-password" /></Form.Item>
          <Form.Item name="confirm_password" label="确认密码" rules={[{ required: true, message: '请再次输入密码' }]}><Input.Password autoComplete="new-password" /></Form.Item>
        </Form>
      </Modal>
    </>
  );
}

function InterfaceConfigModal({ editing, setEditing, form, submit }: { editing: any | null; setEditing: (value: any | null) => void; form: any; submit: () => void }) {
  return (
    <Modal title="编辑接口配置" open={Boolean(editing)} onCancel={() => setEditing(null)} onOk={submit} okText="保存">
      <Form form={form} layout="vertical">
        <Form.Item name="interface_name" label="接口名称" rules={[{ required: true, message: '请输入接口名称' }]}><Input /></Form.Item>
        <Form.Item name="service_url" label="服务地址"><Input /></Form.Item>
        <Form.Item name="host" label="主机地址"><Input /></Form.Item>
        <Form.Item name="port" label="端口"><InputNumber style={{ width: '100%' }} min={1} max={65535} /></Form.Item>
        <Form.Item name="database_name" label="数据库"><Input /></Form.Item>
        <Form.Item name="username" label="用户名"><Input autoComplete="off" /></Form.Item>
        <Form.Item name="health_path" label="健康检查路径"><Input /></Form.Item>
        <Form.Item name="timeout_seconds" label="请求超时（秒）"><InputNumber style={{ width: '100%' }} min={1} max={120} /></Form.Item>
        <Form.Item name="is_enabled" label="启用状态" valuePropName="checked"><Switch /></Form.Item>
      </Form>
    </Modal>
  );
}

function ParamInput({ label, value, suffix, onChange, onBlur, disabled }: { label: string; value: any; suffix?: string; onChange?: (value: any) => void; onBlur?: () => void; disabled?: boolean }) {
  return (
    <div className="settings-param-item">
      <span>{label}</span>
      <div className="settings-number-wrap">
        <InputNumber value={value} disabled={disabled} onChange={onChange} onBlur={onBlur} />
        {suffix && <em>{suffix}</em>}
      </div>
    </div>
  );
}

function SwitchParam({ label, checked, onChange, disabled }: { label: string; checked: boolean; onChange?: (value: boolean) => void; disabled?: boolean }) {
  return (
    <div className="settings-param-item settings-param-switch">
      <span>{label}</span>
      <Switch checked={checked} disabled={disabled} onChange={onChange} />
    </div>
  );
}

function hasAny(values: string[] = [], needles: string[]) {
  return needles.some((item) => values.includes(item));
}

function buildSystemRows(data: any, auditLogs: any[]) {
  const sourceRows = data.healthDetails?.length ? data.healthDetails : data.statusSummary || [];
  return sourceRows.map((item: any) => ({
    key: item.module_key || item.key,
    module: item.module_name || item.module || item.name,
    status: item.status_label || item.status || '--',
    summary: item.summary || '--',
    checkedAt: formatTime(item.checked_at || item.checkedAt),
    metric: item.metric || '--',
    latency: item.latency_ms ? `${item.latency_ms}ms` : '--',
    icon: iconForModule(item.module_key || item.key),
    tone: toneForStatus(item.status)
  }));
}

function buildInterfaceRows(data: any) {
  const rows = data.interfaces?.length ? data.interfaces : data.interfaceConfigs || [];
  return rows.map((item: any) => ({
    key: item.interface_key || item.key || item.id,
    id: item.id,
    interfaceKey: item.interface_key || item.key,
    name: item.interface_name || item.name,
    type: item.interface_type || item.type,
    address: item.service_url || item.address || '--',
    status: item.status_label || item.status || '--',
    latency: item.last_latency_ms !== undefined && item.last_latency_ms !== null ? `${item.last_latency_ms}ms` : '--',
    successRate: item.success_rate !== undefined && item.success_rate !== null ? `${item.success_rate}%` : '--',
    checkedAt: formatTime(item.last_checked_at || item.checkedAt),
    summary: item.summary || item.response_summary || '--',
    enabled: item.is_enabled !== false,
    raw: item
  }));
}

function iconForModule(key: string) {
  if (key === 'postgresql' || key === 'milvus' || key === 'rag') return <DatabaseOutlined />;
  if (key === 'redis' || key === 'web') return <CloudServerOutlined />;
  if (key === 'celery') return <ThunderboltOutlined />;
  if (key === 'llm') return <ApiOutlined />;
  if (key === 'audit') return <AuditOutlined />;
  return <SafetyCertificateOutlined />;
}

function iconForInterface(key: string) {
  if (['database', 'vector_database', 'postgresql', 'milvus', 'rag'].includes(key)) return <DatabaseOutlined />;
  if (['cache', 'task_queue', 'web_service', 'redis', 'celery', 'web'].includes(key)) return <CloudServerOutlined />;
  if (['llm', 'model_gateway'].includes(key)) return <ApiOutlined />;
  if (key === 'audit') return <AuditOutlined />;
  return <ApiOutlined />;
}

function toneForStatus(status: string) {
  if (status === 'normal') return 'green';
  if (status === 'error' || status === 'unavailable') return 'red';
  if (status === 'warning' || status === 'fallback' || status === 'not_configured') return 'orange';
  return 'blue';
}

function averageLatency(rows: any[]) {
  const values = rows.map((item) => Number(String(item.latency).replace('ms', ''))).filter((value) => Number.isFinite(value));
  if (!values.length) return 0;
  return Math.round(values.reduce((sum, value) => sum + value, 0) / values.length);
}
