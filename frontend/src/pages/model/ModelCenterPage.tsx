import { BookOutlined, ReloadOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { Button, Col, Modal, Row, Select, Space, Table, Tag, message } from 'antd';
import { useEffect, useState } from 'react';
import { api } from '../../api';
import { DetailDrawer } from '../../components/actions/DetailDrawer';
import { SectionCard } from '../../components/cards/SectionCard';
import { AppChart } from '../../components/charts/AppChart';
import { baseGrid, chartColors } from '../../components/charts/chartTheme';
import { PageTabs } from '../../components/common/PageTabs';
import { DataStateBanner } from '../../components/common/States';
import { MetricGrid } from '../../components/layout/UnifiedPage';
import { modelMock } from '../../mock/modelMock';
import { getModelCenterData } from '../../services/modelApi';
import type { PageProps } from '../../types/ui';

const tabs = [
  { key: 'model-active', label: 'Active模型' },
  { key: 'model-candidate', label: '候选模型' },
  { key: 'model-error', label: '误差趋势' },
  { key: 'model-rollback', label: '模型回滚' }
];

export function ModelCenterPage({ activeSubKey, onSubNavigate }: PageProps) {
  const [modelData, setModelData] = useState(modelMock);
  const [loading, setLoading] = useState(true);
  const [rollbackVersion, setRollbackVersion] = useState<string>();
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailData, setDetailData] = useState<Record<string, unknown> | null>(null);

  async function loadModelData() {
    setLoading(true);
    try {
      const data = await getModelCenterData();
      setModelData(data);
      setRollbackVersion(String(data.comparison?.find((row: any[]) => row[2] !== 'Active')?.[0] || data.comparison?.[0]?.[0] || ''));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadModelData();
  }, []);

  const errorOption = {
    ...baseGrid(),
    legend: { top: 0, data: ['MAE（平均绝对误差）', 'RMSE（均方根误差）', 'MAPE（高峰误差）'] },
    xAxis: { ...(baseGrid().xAxis as object), data: modelData.errorTrend.map((item) => item.time) },
    series: [
      { name: 'MAE（平均绝对误差）', type: 'line', smooth: true, data: modelData.errorTrend.map((item) => item.value), lineStyle: { color: chartColors.green } },
      { name: 'RMSE（均方根误差）', type: 'line', smooth: true, data: modelData.errorTrend.map((item) => item.actual), lineStyle: { color: chartColors.blue } },
      { name: 'MAPE（高峰误差）', type: 'line', smooth: true, data: modelData.errorTrend.map((item) => item.baseline), lineStyle: { color: chartColors.orange } }
    ]
  };

  const effectOption = {
    ...baseGrid(),
    legend: { top: 0, data: ['实际值', '预测值', '误差'] },
    xAxis: { ...(baseGrid().xAxis as object), data: modelData.effect.map((item) => item.time) },
    series: [
      { name: '实际值', type: 'line', smooth: true, data: modelData.effect.map((item) => item.actual), lineStyle: { color: chartColors.green } },
      { name: '预测值', type: 'line', smooth: true, data: modelData.effect.map((item) => item.value), lineStyle: { color: chartColors.blue } },
      { name: '误差', type: 'bar', data: modelData.effect.map((item) => item.baseline), itemStyle: { color: 'rgba(0,184,148,0.25)' } }
    ]
  };

  async function startRetrain() {
    const suggestion = await api.retrainSuggestion();
    Modal.confirm({
      title: '确认启动模型训练',
      content: suggestion.retrain_reason || '该操作会创建异步训练任务，请确认是否继续。',
      onOk: async () => {
        const res = await api.runTask('retrain_model');
        message.success(`训练任务已启动：${res.task_id || 'retrain_model'}`);
      }
    });
  }

  function confirmModelAction(action: string, row?: unknown[]) {
    Modal.confirm({
      title: action,
      content: `模型高风险操作需要二次确认。目标版本：${row?.[0] || modelData.detail.name}`,
      onOk: () => message.success(`${action} 已记录`)
    });
  }

  const modelRows = modelData.comparison.map((row) => ({ key: row[0], row }));
  const modelColumns = [
    { title: '版本号', render: (_: unknown, record: any) => record.row[0] },
    { title: '模型类型', render: (_: unknown, record: any) => record.row[1] },
    { title: '状态', render: (_: unknown, record: any) => <Tag color={record.row[2] === 'Active' ? 'success' : record.row[2] === 'Candidate' ? 'warning' : 'default'}>{record.row[2]}</Tag> },
    { title: 'MAE', render: (_: unknown, record: any) => record.row[3] },
    { title: 'RMSE', render: (_: unknown, record: any) => record.row[4] },
    { title: 'MAPE(%)', render: (_: unknown, record: any) => record.row[5] },
    { title: '训练时间', render: (_: unknown, record: any) => record.row[6] },
    {
      title: '操作',
      render: (_: unknown, record: any) => (
        <Space>
          <Button size="small" onClick={() => { setDetailData({ version: record.row }); setDetailOpen(true); }}>查看详情</Button>
          <Button size="small" onClick={() => confirmModelAction(record.row[2] === 'Candidate' ? '设为 Active' : '回滚版本', record.row)}>
            {record.row[2] === 'Candidate' ? '设为Active' : '回滚版本'}
          </Button>
        </Space>
      )
    }
  ];

  const rollbackOptions = modelData.comparison.map((row) => ({ value: String(row[0]), label: `${row[0]} - ${row[2]}` }));

  function renderModelDetail() {
    return (
      <div className="detail-list">
        <p><span>模型名称</span><strong>{modelData.detail.name}</strong></p>
        <p><span>模型类型</span><strong>{modelData.detail.type}</strong></p>
        <p><span>预测粒度</span><strong>{modelData.detail.granularity}</strong></p>
        <p><span>预测范围</span><strong>{modelData.detail.horizon}</strong></p>
        <p><span>算法框架</span><strong>{modelData.detail.algorithm}</strong></p>
        <div className="tag-cloud">{modelData.detail.features.map((item) => <Tag key={item}>{item}</Tag>)}</div>
      </div>
    );
  }

  function renderTrainingStatus() {
    return (
      <div className="detail-list">
        <p><span>训练状态</span><Tag color="success">训练完成</Tag></p>
        <p><span>训练任务ID</span><strong>train_20250621_0830</strong></p>
        <p><span>样本数量</span><strong>287,654</strong></p>
        <p><span>训练时长</span><strong>00:18:42</strong></p>
        <a className="section-footer-link" onClick={() => { window.location.hash = '/task/task-log'; }}>查看训练日志 →</a>
      </div>
    );
  }

  function renderTabContent() {
    if (activeSubKey === 'model-candidate') {
      return (
        <Row gutter={[16, 16]} className="balanced-row">
          <Col xs={24} xl={17}>
            <SectionCard title="Candidate 模型列表" loading={loading}>
              <Table size="small" pagination={false} dataSource={modelRows} columns={modelColumns} scroll={{ x: 900 }} />
            </SectionCard>
          </Col>
          <Col xs={24} xl={7}>
            <SectionCard title="候选模型准入规则" minHeight={220}>
              <div className="detail-list">
                <p><span>准入条件</span><strong>MAE、RMSE 低于 Active 模型</strong></p>
                <p><span>峰段误差</span><strong>需要小于策略阈值</strong></p>
                <p><span>上线方式</span><strong>二次确认后切换 Active</strong></p>
                <Button type="primary" block onClick={() => confirmModelAction('设为 Active', modelData.comparison.find((row) => row[2] !== 'Active'))}>切换 Active 模型</Button>
              </div>
            </SectionCard>
          </Col>
        </Row>
      );
    }

    if (activeSubKey === 'model-error') {
      return (
        <Row gutter={[16, 16]} className="balanced-row">
          <Col xs={24} xl={12}>
            <SectionCard title="误差趋势" loading={loading} extra={<Select value="近30天" options={[{ value: '近30天', label: '近30天' }]} />}>
              <AppChart option={errorOption} height={320} />
            </SectionCard>
          </Col>
          <Col xs={24} xl={12}>
            <SectionCard title="预测效果对比（Active模型）" loading={loading} extra={<Select value="近7天" options={[{ value: '近7天', label: '近7天' }]} />}>
              <AppChart option={effectOption} height={320} />
            </SectionCard>
          </Col>
        </Row>
      );
    }

    if (activeSubKey === 'model-rollback') {
      return (
        <Row gutter={[16, 16]} className="balanced-row">
          <Col xs={24} xl={16}>
            <SectionCard title="模型版本记录" loading={loading}>
              <Table size="small" pagination={false} dataSource={modelRows} columns={modelColumns} scroll={{ x: 900 }} />
            </SectionCard>
          </Col>
          <Col xs={24} xl={8}>
            <SectionCard title="回滚操作" minHeight={180}>
              <Space.Compact block>
                <Select value={rollbackVersion} onChange={setRollbackVersion} options={rollbackOptions} />
                <Button type="primary" onClick={() => confirmModelAction('回滚版本', [rollbackVersion])}>回滚版本</Button>
              </Space.Compact>
            </SectionCard>
            <SectionCard title="训练状态">{renderTrainingStatus()}</SectionCard>
          </Col>
        </Row>
      );
    }

    return (
      <div className="model-active-grid">
        <SectionCard title="Active 模型效果" loading={loading} height={430}>
          <AppChart option={effectOption} height={360} />
        </SectionCard>
        <SectionCard title="模型对比" loading={loading} height={430} scrollable>
          <Table size="small" pagination={false} dataSource={modelRows} columns={modelColumns} scroll={{ x: 900 }} />
        </SectionCard>
        <div className="model-side-stack">
          <SectionCard title="模型详情" scrollable>{renderModelDetail()}</SectionCard>
          <SectionCard title="训练状态">{renderTrainingStatus()}</SectionCard>
        </div>
      </div>
    );
  }

  return (
    <div className="page-stack">
      <PageTabs items={tabs} activeKey={activeSubKey} onChange={onSubNavigate} />
      <div className="page-toolbar">
        <Space>
          <Button icon={<BookOutlined />} onClick={() => { setDetailData(modelData.detail); setDetailOpen(true); }}>模型文档</Button>
          <Button type="primary" icon={<ReloadOutlined />} onClick={startRetrain}>启动重训</Button>
        </Space>
      </div>
      <DataStateBanner
        scope="模型中心"
        loading={loading}
        source={(modelData as any).dataSource}
        error={(modelData as any).error}
        empty={(modelData as any).empty}
        mockFallback={(modelData as any).mockFallback}
        fallbackReason={(modelData as any).fallbackReason}
        partialErrors={(modelData as any).partialErrors}
        onRetry={loadModelData}
      />
      <MetricGrid items={modelData.metrics} icons={modelData.metrics.map(() => <ThunderboltOutlined />)} loading={loading} minColumnWidth={170} />
      {renderTabContent()}
      <DetailDrawer title="模型详情" open={detailOpen} data={detailData} onClose={() => setDetailOpen(false)} />
    </div>
  );
}
