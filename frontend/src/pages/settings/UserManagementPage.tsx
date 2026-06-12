import { PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import { Button, Form, Input, Modal, Popconfirm, Select, Space, Table, Tag, message } from 'antd';
import { useEffect, useMemo, useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import { userApi } from '../../services/userApi';
import type { RoleInfo, UserItem } from '../../services/userApi';

const roleLabels: Record<string, string> = {
  admin: '管理员',
  analyst: '分析员',
  viewer: '查看者',
  developer: '开发者'
};

function userKey(row: UserItem) {
  return String(row.user_id || row.id || row.username);
}

export function UserManagementPage() {
  const { hasPermission } = useAuth();
  const canWrite = hasPermission('user:write');
  const [loading, setLoading] = useState(false);
  const [users, setUsers] = useState<UserItem[]>([]);
  const [roles, setRoles] = useState<RoleInfo[]>([]);
  const [total, setTotal] = useState(0);
  const [keyword, setKeyword] = useState('');
  const [createOpen, setCreateOpen] = useState(false);
  const [editing, setEditing] = useState<UserItem | null>(null);
  const [resetting, setResetting] = useState<UserItem | null>(null);
  const [createForm] = Form.useForm();
  const [editForm] = Form.useForm();
  const [passwordForm] = Form.useForm();

  const roleOptions = useMemo(
    () => roles.map((role) => ({ value: role.name, label: role.label || role.name })),
    [roles]
  );

  async function loadData() {
    setLoading(true);
    try {
      const [userPayload, rolePayload] = await Promise.all([
        userApi.listUsers({ keyword, page: 1, page_size: 50 }),
        userApi.getRoles()
      ]);
      setUsers(userPayload.items || []);
      setTotal(userPayload.total || 0);
      setRoles(rolePayload.roles || []);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '用户列表加载失败');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData();
  }, []);

  async function submitCreate() {
    const values = await createForm.validateFields();
    await userApi.createUser(values);
    message.success('用户已创建');
    setCreateOpen(false);
    createForm.resetFields();
    await loadData();
  }

  async function submitEdit() {
    if (!editing) return;
    const values = await editForm.validateFields();
    await userApi.updateUser(userKey(editing), values);
    message.success('用户信息已更新');
    setEditing(null);
    await loadData();
  }

  async function submitResetPassword() {
    if (!resetting) return;
    const values = await passwordForm.validateFields();
    if (values.new_password !== values.confirm_password) {
      message.error('两次输入的密码不一致');
      return;
    }
    await userApi.resetPassword(userKey(resetting), values.new_password);
    message.success('密码已重置');
    setResetting(null);
    passwordForm.resetFields();
  }

  async function toggleActive(row: UserItem) {
    if (row.is_active) await userApi.disableUser(userKey(row));
    else await userApi.enableUser(userKey(row));
    message.success(row.is_active ? '用户已禁用' : '用户已启用');
    await loadData();
  }

  return (
    <div className="page-stack">
      <Space wrap className="page-toolbar">
        <Input.Search
          allowClear
          placeholder="搜索用户名、姓名或邮箱"
          value={keyword}
          onChange={(event) => setKeyword(event.target.value)}
          onSearch={loadData}
          style={{ width: 260 }}
        />
        {canWrite && <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>新增用户</Button>}
        <Button icon={<ReloadOutlined />} onClick={loadData}>刷新</Button>
      </Space>

      <Table<UserItem>
        rowKey={userKey}
        loading={loading}
        dataSource={users}
        pagination={{ total, pageSize: 50, showSizeChanger: false }}
        columns={[
          { title: '用户名', dataIndex: 'username' },
          { title: '显示名', dataIndex: 'display_name' },
          { title: '邮箱', dataIndex: 'email', ellipsis: true },
          { title: '角色', dataIndex: 'role', render: (value) => <Tag>{roleLabels[value] || value}</Tag> },
          { title: '状态', dataIndex: 'is_active', render: (value) => <Tag color={value ? 'success' : 'default'}>{value ? '启用' : '禁用'}</Tag> },
          { title: '超级用户', dataIndex: 'is_superuser', render: (value) => (value ? '是' : '否') },
          { title: '最近登录', dataIndex: 'last_login_at', ellipsis: true },
          { title: '创建时间', dataIndex: 'created_at', ellipsis: true },
          {
            title: '操作',
            fixed: 'right',
            render: (_, row) => (
              <Space>
                <Button
                  type="link"
                  size="small"
                  disabled={!canWrite}
                  onClick={() => {
                    setEditing(row);
                    editForm.setFieldsValue({
                      email: row.email,
                      display_name: row.display_name,
                      role: row.role,
                      is_active: row.is_active
                    });
                  }}
                >
                  编辑
                </Button>
                <Button type="link" size="small" disabled={!canWrite} onClick={() => setResetting(row)}>重置密码</Button>
                <Popconfirm
                  title={row.is_active ? '确认禁用该用户？' : '确认启用该用户？'}
                  onConfirm={() => toggleActive(row)}
                  disabled={!canWrite}
                >
                  <Button type="link" size="small" danger={row.is_active} disabled={!canWrite}>
                    {row.is_active ? '禁用' : '启用'}
                  </Button>
                </Popconfirm>
              </Space>
            )
          }
        ]}
      />

      <Modal title="新增用户" open={createOpen} onCancel={() => setCreateOpen(false)} onOk={submitCreate} okText="创建">
        <Form form={createForm} layout="vertical" initialValues={{ role: 'viewer', is_active: true }}>
          <Form.Item name="username" label="用户名" rules={[{ required: true, min: 3, message: '用户名至少 3 个字符' }]}>
            <Input autoComplete="off" />
          </Form.Item>
          <Form.Item name="display_name" label="显示名"><Input /></Form.Item>
          <Form.Item name="email" label="邮箱" rules={[{ type: 'email', message: '邮箱格式不正确' }]}>
            <Input autoComplete="off" />
          </Form.Item>
          <Form.Item name="password" label="初始密码" rules={[{ required: true, min: 8, message: '密码至少 8 个字符' }]}>
            <Input.Password autoComplete="new-password" />
          </Form.Item>
          <Form.Item name="role" label="角色" rules={[{ required: true }]}>
            <Select options={roleOptions} />
          </Form.Item>
          <Form.Item name="is_active" label="状态">
            <Select options={[{ value: true, label: '启用' }, { value: false, label: '禁用' }]} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal title="编辑用户" open={Boolean(editing)} onCancel={() => setEditing(null)} onOk={submitEdit} okText="保存">
        <Form form={editForm} layout="vertical">
          <Form.Item name="display_name" label="显示名"><Input /></Form.Item>
          <Form.Item name="email" label="邮箱" rules={[{ type: 'email', message: '邮箱格式不正确' }]}>
            <Input />
          </Form.Item>
          <Form.Item name="role" label="角色"><Select options={roleOptions} /></Form.Item>
          <Form.Item name="is_active" label="状态">
            <Select options={[{ value: true, label: '启用' }, { value: false, label: '禁用' }]} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal title="重置密码" open={Boolean(resetting)} onCancel={() => setResetting(null)} onOk={submitResetPassword} okText="重置">
        <Form form={passwordForm} layout="vertical">
          <Form.Item name="new_password" label="新密码" rules={[{ required: true, min: 8, message: '密码至少 8 个字符' }]}>
            <Input.Password autoComplete="new-password" />
          </Form.Item>
          <Form.Item name="confirm_password" label="确认密码" rules={[{ required: true, message: '请再次输入密码' }]}>
            <Input.Password autoComplete="new-password" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

