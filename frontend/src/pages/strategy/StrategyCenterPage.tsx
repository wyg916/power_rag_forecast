import { CheckCircleOutlined, ReloadOutlined, SafetyCertificateOutlined, UserOutlined, WarningOutlined } from '@ant-design/icons';
import { Button, Col, Form, Input, InputNumber, Modal, Row, Space, Switch, Table, Tag, message } from 'antd';
import { useEffect, useState } from 'react';
import { api } from '../../api';
import { DetailDrawer } from '../../components/actions/DetailDrawer';
import { SectionCard } from '../../components/cards/SectionCard';
import { TableCard } from '../../components/cards/TableCard';
import { AppChart } from '../../components/charts/AppChart';
import { baseGrid, chartColors } from '../../components/charts/chartTheme';
import { PageTabs } from '../../components/common/PageTabs';
import { DataSourceTag, DataStateBanner } from '../../components/common/States';
import { MetricGrid } from '../../components/layout/UnifiedPage';
import { strategyMock } from '../../mock/strategyMock';
import { getStrategyCenterData } from '../../services/strategyApi';
import type { PageProps } from '../../types/ui';

const icons = [<CheckCircleOutlined />, <WarningOutlined />, <SafetyCertificateOutlined />, <ReloadOutlined />, <UserOutlined />];

const tabs = [
  { key: 'strategy-high', label: '高价风险' },
  { key: 'strategy-low', label: '低价窗口' },
  { key: 'strategy-storage', label: '储能策略' },
  { key: 'strategy-review', label: '人工复核' }
];

export function StrategyCenterPage({ activeSubKey, onSubNavigate }: PageProps) {
  const [strategyData, setStrategyData] = useState<any>(strategyMock);
  const [loading, setLoading] = useState(true);
  const [configOpen, setConfigOpen] = useState(false);
  const [configValues, setConfigValues] = useState<Record<string, any>>({});
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailData, setDetailData] = useState<Record<string, unknown> | null>(null);

  async function loadData() {
    setLoading(true);
    try {
      const data = await getStrategyCenterData();
      setStrategyData(data);
      setConfigValues(data.config || {});
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData();
  }, []);

  const timelineOption = {
    ...baseGrid(),
    legend: { top: 0, data: ['充电', '放电', '高价风险', '低价窗口'] },
    xAxis: { ...(baseGrid().xAxis as object), data: ['00:00', '03:00', '06:00', '09:00', '12:00', '15:00', '18:00', '21:00', '24:00'] },
    yAxis: { ...(baseGrid().yAxis as object), name: '功率（MW）' },
    series: [
      { name: '充电', type: 'line', step: 'middle', areaStyle: { color: 'rgba(0,184,148,0.12)' }, data: [-80, -96, -40, 0, 0, 0, 0, -65, 0], lineStyle: { color: chartColors.green } },
      { name: '放电', type: 'line', step: 'middle', areaStyle: { color: 'rgba(59,130,246,0.12)' }, data: [0, 0, 0, 10, 60, 58, 0, 0, 0], lineStyle: { color: chartColors.blue } },
      { name: '高价风险', type: 'bar', data: [0, 0, 0, 42, 0, 0, 48, 0, 0], itemStyle: { color: 'rgba(255,77,79,0.25)' } },
      { name: '低价窗口', type: 'bar', data: [0, 0, 0, 0, 0, 0, 0, -35, 0], itemStyle: { color: 'rgba(0,184,148,0.25)' } }
    ]
  };

  async function saveConfig() {
    await api.saveStrategyConfig(configValues);
    message.success('策略配置已保存');
    setConfigOpen(false);
    await loadData();
  }

  async function saveReview(row: any[]) {
    await api.saveStrategyReview({ id: row[0], type: row[1], period: row[2], action: row[3], reason: row[4], status: '已复核' });
    message.success('复核记录已保存');
  }

  function exportStrategy() {
    const csv = (strategyData.timeline || []).map((row: any[]) => row.join(',')).join('\n');
    const blob = new Blob([`\uFEFF时段,动作,功率,收益\n${csv}`], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `strategy_${Date.now()}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  const timelineTable = (
    <Table
      size="small"
      pagination={false}
      scroll={{ x: 'max-content' }}
      dataSource={(strategyData.timeline || []).map((row: any[], index: number) => ({ key: index, row }))}
      columns={[
        { title: '时段', render: (_, record: any) => record.row[0] },
        { title: '策略动作', render: (_, record: any) => <Tag color={String(record.row[1]).includes('充') ? 'success' : String(record.row[1]).includes('放') ? 'blue' : String(record.row[1]).includes('风险') ? 'error' : 'default'}>{record.row[1]}</Tag> },
        { title: '功率（MW）', align: 'right', render: (_, record: any) => record.row[2] },
        { title: '预计收益（元）', align: 'right', render: (_, record: any) => record.row[3] },
        { title: '操作', render: (_, record: any) => <Button type="link" size="small" onClick={() => { setDetailData({ period: record.row[0], action: record.row[1], power: record.row[2], revenue: record.row[3], data_source: strategyData.dataSource }); setDetailOpen(true); }}>详情</Button> }
      ]}
    />
  );

  return (
    <div className="page-stack">
      <PageTabs items={tabs} activeKey={activeSubKey} onChange={onSubNavigate} />
      <div className="page-toolbar">
        <Space>
          <DataSourceTag source={strategyData.dataSource} />
          <Button icon={<ReloadOutlined />} loading={loading} onClick={loadData}>刷新</Button>
          <Button onClick={() => setConfigOpen(true)}>策略配置</Button>
          <Button onClick={exportStrategy}>导出策略</Button>
        </Space>
      </div>
      <DataStateBanner
        scope="策略中心"
        loading={loading}
        source={strategyData.dataSource}
        error={strategyData.error}
        empty={strategyData.empty}
        mockFallback={strategyData.mockFallback}
        fallbackReason={strategyData.fallbackReason}
        partialErrors={strategyData.partialErrors}
        onRetry={loadData}
      />
      <MetricGrid items={strategyData.metrics || []} icons={icons} loading={loading} minColumnWidth={180} />

      {activeSubKey === 'strategy-high' && (
        <Row gutter={[16, 16]} className="balanced-row">
          <Col xs={24} xl={16}>
            <SectionCard title="高价风险时间轴" loading={loading}><AppChart option={timelineOption} height={330} /></SectionCard>
          </Col>
          <Col xs={24} xl={8}>
            <SectionCard title="策略建议" loading={loading}>
              <div className="advice-panel">
                <h4>结论</h4><p>{strategyData.advice.conclusion}</p>
                <h4>风险提示</h4><ul>{strategyData.advice.warning.map((item: string) => <li key={item}>{item}</li>)}</ul>
              </div>
            </SectionCard>
          </Col>
        </Row>
      )}

      {activeSubKey === 'strategy-low' && (
        <Row gutter={[16, 16]} className="balanced-row">
          <Col xs={24} xl={14}><SectionCard title="低价采购窗口" loading={loading}>{timelineTable}</SectionCard></Col>
          <Col xs={24} xl={10}><SectionCard title="低价窗口说明"><p>低价窗口优先用于补充采购、储能充电和风险敞口修正，执行前需结合 SOC 与合同约束。</p></SectionCard></Col>
        </Row>
      )}

      {activeSubKey === 'strategy-storage' && (
        <Row gutter={[16, 16]} className="balanced-row">
          <Col xs={24} xl={14}><SectionCard title="储能充放电建议" loading={loading}>{timelineTable}</SectionCard></Col>
          <Col xs={24} xl={10}>
            <SectionCard title="风险分级卡片">
              <div className="risk-grade-list">
                {(strategyData.riskCards || []).map((item: any[]) => (
                  <div className={`risk-grade risk-${item[3]}`} key={item[0]} onClick={() => { setDetailData({ title: item[0], count: item[1], description: item[2] }); setDetailOpen(true); }}>
                    <strong>{item[0]}</strong><span>{item[1]}</span><p>{item[2]}</p>
                  </div>
                ))}
              </div>
            </SectionCard>
          </Col>
        </Row>
      )}

      {activeSubKey === 'strategy-review' && (
        <TableCard
          title="人工复核清单"
          loading={loading}
          dataSource={(strategyData.reviewList || []).map((row: any[]) => ({ key: row[0], row }))}
          columns={[
            { title: '编号', render: (_, record: any) => record.row[0] },
            { title: '复核类型', render: (_, record: any) => record.row[1] },
            { title: '时段', render: (_, record: any) => record.row[2] },
            { title: '策略动作', render: (_, record: any) => record.row[3] },
            { title: '复核原因', render: (_, record: any) => record.row[4] },
            { title: '状态', render: (_, record: any) => <Tag color="warning">{record.row[5]}</Tag> },
            { title: '操作', render: (_, record: any) => <Space><Button type="link" size="small" onClick={() => { setDetailData({ row: record.row }); setDetailOpen(true); }}>查看</Button><Button type="link" size="small" onClick={() => saveReview(record.row)}>标记复核</Button></Space> }
          ]}
        />
      )}

      <Modal title="策略配置" open={configOpen} onCancel={() => setConfigOpen(false)} onOk={saveConfig} okText="保存配置">
        <Form layout="vertical">
          <Form.Item label="高价阈值"><InputNumber value={configValues.high_price_threshold} onChange={(value) => setConfigValues((prev) => ({ ...prev, high_price_threshold: value }))} min={0} style={{ width: '100%' }} /></Form.Item>
          <Form.Item label="低价阈值"><InputNumber value={configValues.low_price_threshold} onChange={(value) => setConfigValues((prev) => ({ ...prev, low_price_threshold: value }))} min={0} style={{ width: '100%' }} /></Form.Item>
          <Form.Item label="SOC 上限"><InputNumber value={configValues.soc_upper} onChange={(value) => setConfigValues((prev) => ({ ...prev, soc_upper: value }))} min={0} max={100} style={{ width: '100%' }} /></Form.Item>
          <Form.Item label="SOC 下限"><InputNumber value={configValues.soc_lower} onChange={(value) => setConfigValues((prev) => ({ ...prev, soc_lower: value }))} min={0} max={100} style={{ width: '100%' }} /></Form.Item>
          <Form.Item label="充电功率"><InputNumber value={configValues.charge_power} onChange={(value) => setConfigValues((prev) => ({ ...prev, charge_power: value }))} min={0} style={{ width: '100%' }} /></Form.Item>
          <Form.Item label="放电功率"><InputNumber value={configValues.discharge_power} onChange={(value) => setConfigValues((prev) => ({ ...prev, discharge_power: value }))} min={0} style={{ width: '100%' }} /></Form.Item>
          <Form.Item label="风险等级阈值"><InputNumber value={configValues.risk_threshold} onChange={(value) => setConfigValues((prev) => ({ ...prev, risk_threshold: value }))} min={0} max={1} step={0.05} style={{ width: '100%' }} /></Form.Item>
          <Form.Item label="允许自动建议"><Switch checked={Boolean(configValues.auto_suggestion)} onChange={(value) => setConfigValues((prev) => ({ ...prev, auto_suggestion: value }))} /></Form.Item>
        </Form>
      </Modal>
      <DetailDrawer title="策略详情" open={detailOpen} data={detailData} onClose={() => setDetailOpen(false)} />
    </div>
  );
}
