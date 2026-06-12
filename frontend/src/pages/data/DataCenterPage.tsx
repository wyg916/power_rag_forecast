import { ApiOutlined, DatabaseOutlined, EyeOutlined, SafetyCertificateOutlined, SyncOutlined, WarningOutlined } from '@ant-design/icons';
import { Button, Col, Input, Row, Space, Table, Tag, Upload, message } from 'antd';
import { useEffect, useState } from 'react';
import { api } from '../../api';
import { DetailDrawer } from '../../components/actions/DetailDrawer';
import { SectionCard } from '../../components/cards/SectionCard';
import { TableCard } from '../../components/cards/TableCard';
import { Sparkline } from '../../components/charts/Sparkline';
import { PageTabs } from '../../components/common/PageTabs';
import { DataSourceTag, DataStateBanner, EmptyState } from '../../components/common/States';
import { MetricGrid } from '../../components/layout/UnifiedPage';
import { dataMock } from '../../mock/dataMock';
import { getDataCenterData } from '../../services/dataApi';
import type { PageProps } from '../../types/ui';

const icons = [<DatabaseOutlined />, <SyncOutlined />, <WarningOutlined />, <SafetyCertificateOutlined />];

const tabs = [
  { key: 'data-access', label: '数据接入' },
  { key: 'data-quality', label: '数据质量' },
  { key: 'data-tables', label: '数据库表' },
  { key: 'data-import', label: '导入导出' }
];

export function DataCenterPage({ activeSubKey, onSubNavigate }: PageProps) {
  const [data, setData] = useState<any>(dataMock);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [tableSearch, setTableSearch] = useState('');
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailTitle, setDetailTitle] = useState('详情');
  const [detailData, setDetailData] = useState<Record<string, unknown> | null>(null);
  const [tablePreview, setTablePreview] = useState<any[]>([]);

  async function loadData() {
    setLoading(true);
    try {
      setData(await getDataCenterData());
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData();
  }, []);

  async function syncCoreData(kind: 'core' | 'refresh' = 'core') {
    setSyncing(true);
    try {
      const result = kind === 'core' ? await api.syncCoreData() : await api.dataRefresh();
      message.success(result.task_id ? `任务已创建：${result.task_id}` : '数据同步任务已提交');
      await loadData();
    } catch (error) {
      message.error(error instanceof Error ? error.message : '数据同步失败');
    } finally {
      setSyncing(false);
    }
  }

  async function viewTable(tableName: string) {
    setDetailTitle(`表预览：${tableName}`);
    setDetailData({ table_name: tableName, loading: true });
    setTablePreview([]);
    setDetailOpen(true);
    try {
      const payload = await api.databaseTableRows(tableName, { limit: 20 });
      setDetailData({
        table_name: tableName,
        total: payload.total,
        columns: (payload.columns || []).map((item: any) => `${item.name}:${item.type}`).join(', '),
        data_source: 'postgresql'
      });
      setTablePreview(payload.records || []);
    } catch (error) {
      setDetailData({ table_name: tableName, error: error instanceof Error ? error.message : '读取失败' });
    }
  }

  function exportTable(tableName: string) {
    window.open(api.exportTableUrl(tableName), '_blank');
  }

  const filteredTables = (data.tables || []).filter((row: any[]) => !tableSearch || String(row[0]).toLowerCase().includes(tableSearch.toLowerCase()));

  return (
    <div className="page-stack">
      <PageTabs items={tabs} activeKey={activeSubKey} onChange={onSubNavigate} />
      <DataStateBanner
        scope="数据中心"
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

      {activeSubKey === 'data-access' && (
        <Row gutter={[16, 16]} className="balanced-row">
          <Col xs={24} xl={14}>
            <SectionCard
              title="数据接入流程"
              loading={loading}
              extra={<Space><DataSourceTag source={data.dataSource} /><Button loading={syncing} onClick={() => syncCoreData('core')}>核心数据入库</Button><Button type="primary" loading={syncing} onClick={() => syncCoreData('refresh')}>全部同步</Button></Space>}
            >
              <div className="data-flow">
                {(data.flow || []).map((item: any[], index: number) => (
                  <div className="flow-node" key={item[0]}>
                    <div className="flow-icon"><ApiOutlined /></div>
                    <strong>{item[0]}</strong>
                    <Tag color={String(item[3]).includes('异常') ? 'error' : 'success'}>{item[3]}</Tag>
                    <p>{item[1]}</p>
                    <small>刷新时间：{item[2]}</small>
                    {index < (data.flow || []).length - 1 && <span className="flow-arrow">→</span>}
                  </div>
                ))}
              </div>
            </SectionCard>
          </Col>
          <Col xs={24} xl={10}>
            <TableCard
              title="同步与导入记录"
              loading={loading}
              dataSource={(data.imports || []).map((row: any[], index: number) => ({ key: index, row }))}
              columns={[
                { title: '类型', render: (_, record: any) => record.row[0] },
                { title: '任务/文件', render: (_, record: any) => record.row[1] },
                { title: '状态', render: (_, record: any) => <Tag color={String(record.row[2]).includes('fail') || String(record.row[2]).includes('失败') ? 'error' : 'success'}>{record.row[2]}</Tag> },
                { title: '开始时间', render: (_, record: any) => record.row[4] },
                { title: '操作', render: (_, record: any) => <Button type="link" size="small" onClick={() => { setDetailTitle('同步详情'); setDetailData({ record: record.row }); setDetailOpen(true); }}>详情</Button> }
              ]}
            />
          </Col>
        </Row>
      )}

      {activeSubKey === 'data-quality' && (
        <Row gutter={[16, 16]} className="balanced-row">
          <Col xs={24} xl={10}>
            <SectionCard title="数据质量概览" loading={loading}>
              <div className="quality-grid">
                {(data.qualityCharts || []).map((item: any) => (
                  <div className="quality-card" key={item.title}>
                    <div><strong>{item.title}</strong><span>{item.value}</span></div>
                    <Sparkline data={item.data || []} color={item.title.includes('重复') ? '#3B82F6' : item.title.includes('校验') ? '#7C3AED' : '#00B894'} />
                  </div>
                ))}
              </div>
            </SectionCard>
          </Col>
          <Col xs={24} xl={14}>
            <TableCard
              title="异常明细"
              loading={loading}
              dataSource={(data.exceptions || []).map((row: any, index: number) => ({ key: index, ...row }))}
              columns={[
                { title: '数据源', dataIndex: 'source_name' },
                { title: '状态', dataIndex: 'status', render: (text) => <Tag color={String(text).includes('异常') ? 'error' : 'success'}>{text}</Tag> },
                { title: '缺失率', dataIndex: 'missing_rate', render: (text) => `${text}%` },
                { title: '新鲜度', dataIndex: 'freshness_score', render: (text) => `${text}` },
                { title: '最近时间', dataIndex: 'latest_time' },
                { title: '说明', dataIndex: 'message' }
              ]}
            />
          </Col>
        </Row>
      )}

      {activeSubKey === 'data-tables' && (
        <TableCard
          title="PostgreSQL 表浏览"
          loading={loading}
          extra={<Space><Input.Search allowClear placeholder="搜索表名" onSearch={setTableSearch} /><Button onClick={loadData}>刷新表列表</Button></Space>}
          dataSource={filteredTables.map((row: any[]) => ({ key: row[0], row }))}
          columns={[
            { title: '表名', render: (_, record: any) => record.row[0] },
            { title: '字段样例/说明', render: (_, record: any) => record.row[1] },
            { title: '数据来源', render: (_, record: any) => <DataSourceTag source={record.row[2]} /> },
            { title: '主键', render: (_, record: any) => record.row[3] },
            { title: '记录数', align: 'right', render: (_, record: any) => record.row[4] },
            { title: '字段数', align: 'right', render: (_, record: any) => record.row[5] },
            { title: '操作', render: (_, record: any) => <Space><Button type="link" size="small" icon={<EyeOutlined />} onClick={() => viewTable(record.row[0])}>预览</Button><Button type="link" size="small" onClick={() => exportTable(record.row[0])}>导出</Button></Space> }
          ]}
        />
      )}

      {activeSubKey === 'data-import' && (
        <TableCard
          title="导入导出记录"
          loading={loading}
          extra={<Space><Upload beforeUpload={() => { message.success('文件已登记，请点击“创建入库任务”执行同步'); return false; }}><Button>上传文件</Button></Upload><Button onClick={() => syncCoreData('core')}>创建入库任务</Button></Space>}
          dataSource={(data.imports || []).map((row: any[], index: number) => ({ key: index, row }))}
          columns={[
            { title: '任务类型', render: (_, record: any) => record.row[0] },
            { title: '文件/数据源', render: (_, record: any) => record.row[1] },
            { title: '状态', render: (_, record: any) => <Tag color={String(record.row[2]).includes('失败') ? 'error' : 'success'}>{record.row[2]}</Tag> },
            { title: '记录数', align: 'right', render: (_, record: any) => record.row[3] },
            { title: '开始时间', render: (_, record: any) => record.row[4] },
            { title: '耗时', render: (_, record: any) => record.row[5] },
            { title: '操作', render: (_, record: any) => <Button type="link" size="small" onClick={() => { setDetailTitle('导入导出详情'); setDetailData({ record: record.row, failure_reason: record.row[6] || '' }); setDetailOpen(true); }}>查看</Button> }
          ]}
        />
      )}

      <DetailDrawer title={detailTitle} open={detailOpen} data={detailData} onClose={() => setDetailOpen(false)}>
        {tablePreview.length ? (
          <Table
            size="small"
            pagination={{ pageSize: 5 }}
            scroll={{ x: 'max-content' }}
            dataSource={tablePreview.map((row, index) => ({ key: index, ...row }))}
            columns={Object.keys(tablePreview[0] || {}).map((key) => ({ title: key, dataIndex: key, ellipsis: true }))}
          />
        ) : detailTitle.includes('表预览') ? <EmptyState description="暂无预览数据" /> : null}
      </DetailDrawer>
    </div>
  );
}
