import {
  BarChartOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  CloudDownloadOutlined,
  DatabaseOutlined,
  ExperimentOutlined,
  FileSearchOutlined,
  HistoryOutlined,
  LineChartOutlined,
  ReloadOutlined,
  RetweetOutlined,
  RocketOutlined,
  SafetyCertificateOutlined,
  ThunderboltOutlined
} from '@ant-design/icons';
import { Button, Descriptions, Empty, Input, Modal, Select, Space, Table, Tag, message } from 'antd';
import { useEffect, useMemo, useState } from 'react';
import { DetailDrawer } from '../../components/actions/DetailDrawer';
import { TaskLogViewer } from '../../components/actions/TaskLogViewer';
import { SectionCard } from '../../components/cards/SectionCard';
import { AppChart } from '../../components/charts/AppChart';
import { baseGrid, chartColors } from '../../components/charts/chartTheme';
import {
  activateModel,
  exportModelCenterReport,
  getModelCenterData,
  getModelTrainingLogs,
  getModelVersionDetail,
  rollbackModel,
  startModelTraining
} from '../../services/modelApi';
import type { ModelCenterOverview, ModelVersionDetail, ModelVersionRow } from '../../services/modelApi';
import type { PageProps } from '../../types/ui';

const emptyOverview: ModelCenterOverview = {
  available: false,
  filters: {},
  active: { model_version: '--' },
  candidate: { model_version: '--' },
  versions: [],
  effect: [],
  error_trend: [],
  admission: { rules: [], passed: false, conclusion: '--' },
  evaluation_summary: [],
  training: {},
  rollback: { options: [] },
  events: []
};

function fmt(value: unknown, digits = 2) {
  const num = Number(value);
  return Number.isFinite(num) ? num.toFixed(digits) : '--';
}

function pct(value: unknown) {
  const num = Number(value);
  return Number.isFinite(num) ? `${num.toFixed(2)}%` : '--';
}

function shortDateTime(value: unknown) {
  const text = String(value || '');
  if (!text || text === '--') return '--';
  return text.replace('T', ' ').replace(/\.\d+$/, '').slice(0, 16);
}

function modelTypeLabel(value?: string) {
  const text = String(value || '');
  if (!text) return '';
  if (/负荷|load|forecast/i.test(text)) return '负荷预测';
  if (/电价|price/i.test(text)) return '电价预测';
  return text.replace('模型', '');
}

function shortModelVersion(row: ModelVersionRow, fallback = '--') {
  const candidates = [row.model_version, row.model_name, fallback].map((item) => String(item || '')).filter(Boolean);
  const semver = candidates.find((item) => /^v\d/i.test(item));
  if (semver) return semver;
  if (row.is_active && row.model_type) return modelTypeLabel(row.model_type);
  const raw = candidates[0] || '--';
  if (!raw || raw === '--') return '--';
  const match = raw.match(/^model_(\d{8})_(\d{4})/);
  if (match) return row.model_type ? modelTypeLabel(row.model_type) : `版本_${match[1].slice(4)}`;
  const parts = raw.split('_').filter(Boolean);
  if (parts.length >= 2) {
    const compact = parts.slice(0, 2).join('_');
    if (compact.length <= 16) return compact;
  }
  return raw.length > 16 ? `${raw.slice(0, 13)}...` : raw;
}

function statusColor(status?: string, active?: boolean) {
  if (active || status === 'Active') return 'success';
  if (status === 'Candidate') return 'warning';
  return 'default';
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

function formatTaskLogPayload(payload: any) {
  const items = Array.isArray(payload?.items) ? payload.items : [];
  if (items.length) {
    return items
      .map((item: any) => {
        const time = shortDateTime(item.created_at);
        const step = item.step || 'summary';
        const level = item.level || 'info';
        const messageText = item.message || item.log_text || '';
        return `[${time}] [${level}] ${step} - ${messageText}`;
      })
      .join('\n');
  }
  return payload?.text || '';
}

export function ModelCenterPage(_props: PageProps) {
  const [data, setData] = useState<ModelCenterOverview>(emptyOverview);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [filters, setFilters] = useState({ model_type: '负荷预测模型', region: '浙江省', days: 7, search: '' });
  const [rollbackVersion, setRollbackVersion] = useState<string>();
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailData, setDetailData] = useState<ModelVersionDetail | null>(null);
  const [logOpen, setLogOpen] = useState(false);
  const [logLoading, setLogLoading] = useState(false);
  const [logText, setLogText] = useState('');
  const [eventsOpen, setEventsOpen] = useState(false);

  async function loadData(nextFilters = filters) {
    setLoading(true);
    setError('');
    try {
      const payload = await getModelCenterData(nextFilters);
      setData(payload);
      setRollbackVersion(payload.rollback?.options?.[0]?.model_version || payload.versions.find((item) => !item.is_active)?.model_version);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData();
  }, []);

  const active: ModelVersionRow = data.active || { model_version: '--' };
  const candidate: ModelVersionRow = data.candidate || { model_version: '--' };
  const training = data.training || {};
  const renderNumber = (value: unknown) => fmt(value);
  const activeDisplay = shortModelVersion(active, 'Active');
  const candidateDisplay = shortModelVersion(candidate, 'Candidate');

  const kpis = [
    {
      title: '当前 Active 模型',
      value: activeDisplay,
      fullValue: active.model_version || activeDisplay,
      note: `${active.model_type || '负荷预测模型'} / 浙江省`,
      tag: 'Active',
      tone: 'green',
      icon: <DatabaseOutlined />
    },
    {
      title: 'Candidate 模型',
      value: candidateDisplay,
      fullValue: candidate.model_version || candidateDisplay,
      note: `最近更新：${shortDateTime(candidate.created_at || candidate.updated_at)}`,
      tag: 'Candidate',
      tone: 'orange',
      icon: <ExperimentOutlined />
    },
    { title: 'MAE (kW)', value: fmt(candidate.mae), note: `较 Active ↓ ${pct(data.evaluation_summary?.[0]?.improvement)}`, tone: 'green', icon: <LineChartOutlined /> },
    { title: 'RMSE (kW)', value: fmt(candidate.rmse), note: `较 Active ↓ ${pct(data.evaluation_summary?.[1]?.improvement)}`, tone: 'green', icon: <BarChartOutlined /> },
    { title: '高峰误差 (kW)', value: fmt(candidate.peak_error), note: `较 Active ↓ ${pct(data.evaluation_summary?.[3]?.improvement)}`, tone: 'purple', icon: <ThunderboltOutlined /> },
    { title: '最近训练时间', value: shortDateTime(training.ended_at || candidate.created_at), note: `耗时 ${training.duration_seconds ? `${Math.round(Number(training.duration_seconds) / 60)} 分钟` : '--'}`, tone: 'blue', icon: <ClockCircleOutlined /> }
  ];

  const effectOption = useMemo(() => ({
    ...baseGrid(),
    legend: { top: 0, data: ['实际值', `Active(${activeDisplay})`, `Candidate(${candidateDisplay})`, '误差(Candidate-Active)'] },
    grid: { left: 48, right: 48, top: 44, bottom: 38 },
    xAxis: { ...(baseGrid().xAxis as object), data: data.effect.map((item) => item.time) },
    yAxis: [
      { type: 'value', name: '功率(MW)', splitLine: { lineStyle: { color: '#EEF2F6' } }, axisLabel: { color: '#6B7280' } },
      { type: 'value', name: '误差(MW)', splitLine: { show: false }, axisLabel: { color: '#6B7280' } }
    ],
    series: [
      { name: '实际值', type: 'line', smooth: true, data: data.effect.map((item) => item.actual), lineStyle: { color: chartColors.blue } },
      { name: `Active(${activeDisplay})`, type: 'line', smooth: true, data: data.effect.map((item) => item.active), lineStyle: { color: chartColors.green } },
      { name: `Candidate(${candidateDisplay})`, type: 'line', smooth: true, data: data.effect.map((item) => item.candidate), lineStyle: { color: chartColors.orange } },
      { name: '误差(Candidate-Active)', type: 'bar', yAxisIndex: 1, data: data.effect.map((item) => item.diff), itemStyle: { color: 'rgba(15, 185, 138, 0.22)' } }
    ]
  }), [data.effect, activeDisplay, candidateDisplay]);

  const trendOption = useMemo(() => ({
    ...baseGrid(),
    legend: { top: 0, data: ['MAE (kW)', 'RMSE (kW)', 'MAPE (%)'] },
    grid: { left: 44, right: 48, top: 44, bottom: 38 },
    xAxis: { ...(baseGrid().xAxis as object), data: data.error_trend.map((item) => item.date) },
    yAxis: [
      { type: 'value', name: 'kW', splitLine: { lineStyle: { color: '#EEF2F6' } }, axisLabel: { color: '#6B7280' } },
      { type: 'value', name: '%', splitLine: { show: false }, axisLabel: { color: '#6B7280' } }
    ],
    series: [
      { name: 'MAE (kW)', type: 'line', smooth: true, data: data.error_trend.map((item) => item.mae), lineStyle: { color: chartColors.green } },
      { name: 'RMSE (kW)', type: 'line', smooth: true, data: data.error_trend.map((item) => item.rmse), lineStyle: { color: chartColors.blue } },
      { name: 'MAPE (%)', type: 'line', smooth: true, yAxisIndex: 1, data: data.error_trend.map((item) => item.mape), lineStyle: { color: chartColors.orange } }
    ]
  }), [data.error_trend]);

  async function handleTraining() {
    Modal.confirm({
      title: '确认启动模型训练',
      content: '系统将创建新的模型训练任务，并写入任务记录和模型治理审计记录。',
      onOk: async () => {
        await startModelTraining({ model_type: filters.model_type, region: filters.region, reason: '模型中心手动启动训练' });
        message.success('训练任务已创建');
        await loadData();
      }
    });
  }

  async function handleActivate(version?: string) {
    if (!version) return;
    Modal.confirm({
      title: '确认设为 Active 模型',
      content: `目标版本：${version}。该操作会替换当前 Active 模型，并写入治理记录。`,
      onOk: async () => {
        const result = await activateModel(version, '候选模型通过准入规则后切换 Active');
        if (!result.success) throw new Error(result.message || '切换失败');
        message.success('Active 模型已更新');
        await loadData();
      }
    });
  }

  async function handleRollback(targetVersion = rollbackVersion) {
    if (!targetVersion) return;
    Modal.confirm({
      title: '确认回滚模型',
      content: `回滚目标版本：${targetVersion}。该操作可能影响线上预测效果，请确认后继续。`,
      okButtonProps: { danger: true },
      onOk: async () => {
        const result = await rollbackModel(targetVersion, '模型中心手动回滚');
        if (!result.success) throw new Error(result.message || '回滚失败');
        message.success('模型回滚已完成');
        await loadData();
      }
    });
  }

  async function handleExport() {
    const blob = await exportModelCenterReport();
    downloadBlob(blob, 'model-center-report.csv');
  }

  async function handleViewDetail(version?: string) {
    if (!version) return;
    setDetailOpen(true);
    setDetailLoading(true);
    try {
      const payload = await getModelVersionDetail(version);
      if (!payload.available) {
        message.warning(payload.message || '模型详情不可用');
      }
      setDetailData(payload);
    } catch (err) {
      message.error(err instanceof Error ? err.message : '模型详情加载失败');
      setDetailData(null);
    } finally {
      setDetailLoading(false);
    }
  }

  async function handleViewTrainingLogs() {
    const taskId = String(training.task_id || '');
    if (!taskId) {
      message.info('当前没有可查看的训练任务日志');
      return;
    }
    setLogOpen(true);
    setLogLoading(true);
    try {
      const payload = await getModelTrainingLogs(taskId);
      setLogText(formatTaskLogPayload(payload));
    } catch (err) {
      setLogText(err instanceof Error ? err.message : '训练日志加载失败');
    } finally {
      setLogLoading(false);
    }
  }

  const columns = [
    { title: '版本号', dataIndex: 'model_version', width: 130 },
    { title: '状态', width: 100, render: (_: unknown, row: ModelVersionRow) => <Tag color={statusColor(row.status, row.is_active)}>{row.is_active ? 'Active' : row.status || 'Archived'}</Tag> },
    { title: '训练时间', dataIndex: 'created_at', width: 170, render: shortDateTime },
    { title: 'MAE (kW)', dataIndex: 'mae', width: 100, render: renderNumber },
    { title: 'RMSE (kW)', dataIndex: 'rmse', width: 110, render: renderNumber },
    { title: 'MAPE (%)', dataIndex: 'mape', width: 100, render: renderNumber },
    { title: '峰值误差 (kW)', dataIndex: 'peak_error', width: 130, render: renderNumber },
    {
      title: '操作',
      width: 210,
      render: (_: unknown, row: ModelVersionRow) => (
        <Space size={6}>
          <Button size="small" onClick={() => handleViewDetail(row.model_version)}>查看详情</Button>
          {!row.is_active && row.status === 'Candidate' && <Button size="small" onClick={() => handleActivate(row.model_version)}>设为 Active</Button>}
          {!row.is_active && <Button size="small" danger onClick={() => handleRollback(row.model_version)}>回滚</Button>}
        </Space>
      )
    }
  ];

  const eventColumns = [
    { title: '时间', dataIndex: 'created_at', width: 150, render: shortDateTime },
    { title: '动作', dataIndex: 'action', width: 130 },
    { title: '目标版本', dataIndex: 'target_version', width: 130, render: (value: unknown) => value || '--' },
    { title: '来源版本', dataIndex: 'source_version', width: 130, render: (value: unknown) => value || '--' },
    { title: '操作人', dataIndex: 'operator', width: 100, render: (value: unknown) => value || '--' },
    { title: '状态', dataIndex: 'status', width: 90, render: (value: unknown) => <Tag color={value === 'success' ? 'success' : 'processing'}>{String(value || '--')}</Tag> },
    { title: '原因', dataIndex: 'reason', ellipsis: true, render: (value: unknown) => value || '--' }
  ];

  return (
    <div className="model-workbench-page">
      <div className="model-page-header">
        <div className="model-title-block">
          <h1>模型中心</h1>
          <p>管理预测模型生命周期、误差趋势和回滚操作</p>
        </div>
      </div>

      <div className="model-filterbar">
        <Space size={12} wrap>
          <span className="filter-label">模型类型：</span>
          <Select
            value={filters.model_type}
            style={{ width: 150 }}
            options={[{ value: '负荷预测模型', label: '负荷预测模型' }, { value: '电价预测模型', label: '电价预测模型' }]}
            onChange={(value) => setFilters((prev) => ({ ...prev, model_type: value }))}
          />
          <span className="filter-label">区域：</span>
          <Select
            value={filters.region}
            style={{ width: 120 }}
            options={[{ value: '浙江省', label: '浙江省' }, { value: '江苏省', label: '江苏省' }]}
            onChange={(value) => setFilters((prev) => ({ ...prev, region: value }))}
          />
          <span className="filter-label">时间范围：</span>
          <Select
            value={filters.days}
            style={{ width: 110 }}
            options={[{ value: 7, label: '近7天' }, { value: 30, label: '近30天' }]}
            onChange={(value) => setFilters((prev) => ({ ...prev, days: value }))}
          />
          <Input.Search
            allowClear
            placeholder="搜索版本号 / 模型名称 / 训练任务ID"
            value={filters.search}
            onChange={(event) => setFilters((prev) => ({ ...prev, search: event.target.value }))}
            onSearch={() => loadData()}
            style={{ width: 280 }}
          />
        </Space>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => loadData()}>刷新</Button>
          <Button type="primary" icon={<RocketOutlined />} onClick={handleTraining}>启动训练</Button>
          <Button icon={<HistoryOutlined />} onClick={() => setEventsOpen(true)}>治理记录</Button>
          <Button icon={<CloudDownloadOutlined />} onClick={handleExport}>导出报告</Button>
        </Space>
      </div>

      {error && <div className="model-error-banner">{error}</div>}

      <div className="model-kpi-grid">
        {kpis.map((item) => (
          <div className={`model-kpi-card tone-${item.tone}`} key={item.title}>
            <div>
              <span>{item.title}</span>
              <div className="model-kpi-value-row">
                <strong title={item.fullValue || item.value}>{item.value}</strong>
                {item.tag && <Tag color={item.tone === 'orange' ? 'warning' : 'success'}>{item.tag}</Tag>}
              </div>
              <p>{item.note}</p>
            </div>
            <i>{item.icon}</i>
          </div>
        ))}
      </div>

      <div className="model-chart-grid">
        <SectionCard
          title="预测效果对比图（最近 7 天）"
          extra={<Select size="small" value="15分钟" options={[{ value: '15分钟', label: '粒度：15分钟' }]} />}
          loading={loading}
        >
          <AppChart option={effectOption} height={205} />
        </SectionCard>
        <SectionCard
          title="误差趋势（最近 30 天）"
          extra={<Select size="small" value="按天" options={[{ value: '按天', label: '按天' }]} />}
          loading={loading}
        >
          <AppChart option={trendOption} height={205} />
        </SectionCard>
      </div>

      <div className="model-bottom-grid">
        <SectionCard title={<span>版本对比表 <small>共 {data.versions.length} 条</small></span>} loading={loading} scrollable>
          <Table
            size="small"
            rowKey="model_version"
            dataSource={data.versions}
            columns={columns}
            pagination={{ pageSize: 5, showSizeChanger: false }}
            scroll={{ x: 980 }}
          />
        </SectionCard>

        <div className="model-governance-stack">
          <SectionCard title="候选模型准入规则" loading={loading} compact>
            <div className="model-rule-list">
              {data.admission.rules.map((rule) => (
                <p key={rule.label}>
                  <CheckCircleOutlined className={rule.passed ? 'ok' : 'warn'} />
                  <span>{rule.label}</span>
                  <strong>{rule.passed ? '是' : '否'}（{rule.detail}）</strong>
                </p>
              ))}
              <div className={`model-admission-result ${data.admission.passed ? 'passed' : 'blocked'}`}>
                准入结论：{data.admission.conclusion}
              </div>
            </div>
          </SectionCard>

          <SectionCard title="训练状态" loading={loading} compact>
            <div className="model-status-list">
              <p><span>训练任务 ID</span><strong>{training.task_id || '--'}</strong></p>
              <p><span>训练样本数</span><strong>{training.sample_count ? Number(training.sample_count).toLocaleString() : '--'}</strong></p>
              <p><span>训练时长</span><strong>{training.duration_seconds ? `${Math.round(Number(training.duration_seconds) / 60)} 分钟` : '--'}</strong></p>
              <p><span>开始时间</span><strong>{shortDateTime(training.started_at)}</strong></p>
              <p><span>结束时间</span><strong>{shortDateTime(training.ended_at)}</strong></p>
              <p><span>状态</span><Tag color={training.status === 'success' ? 'success' : 'processing'}>{training.status || '--'}</Tag></p>
            </div>
            <Button className="model-card-link-button" size="small" icon={<FileSearchOutlined />} onClick={handleViewTrainingLogs}>
              查看训练日志
            </Button>
          </SectionCard>

          <SectionCard title="模型评估摘要" loading={loading} compact>
            <Table
              size="small"
              rowKey="metric"
              pagination={false}
              dataSource={data.evaluation_summary.slice(0, 4)}
              columns={[
                { title: '指标', dataIndex: 'metric', width: 88 },
                { title: 'Active', dataIndex: 'active', render: renderNumber },
                { title: 'Candidate', dataIndex: 'candidate', render: renderNumber },
                { title: '提升幅度', dataIndex: 'improvement', render: (value: unknown) => <span className="metric-positive">↓ {pct(value)}</span> }
              ]}
            />
          </SectionCard>

          <SectionCard title="回滚操作" loading={loading} compact>
            <div className="model-rollback-control">
              <Select
                value={rollbackVersion}
                onChange={setRollbackVersion}
                options={data.rollback.options.map((item) => ({ value: item.model_version, label: item.label }))}
                popupMatchSelectWidth={false}
              />
              <Button danger icon={<RetweetOutlined />} onClick={() => handleRollback()}>回滚</Button>
            </div>
            <div className="model-warning"><SafetyCertificateOutlined /> 回滚将替换当前 Active 模型，请确认后操作。</div>
          </SectionCard>
        </div>
      </div>

      <DetailDrawer title="模型版本详情" open={detailOpen} onClose={() => setDetailOpen(false)}>
        {detailLoading ? (
          <p className="model-drawer-muted">模型详情加载中...</p>
        ) : detailData?.available ? (
          <div className="model-detail-drawer">
            <Descriptions bordered size="small" column={1}>
              <Descriptions.Item label="版本号">{detailData.version?.model_version || '--'}</Descriptions.Item>
              <Descriptions.Item label="模型名称">{detailData.version?.model_name || '--'}</Descriptions.Item>
              <Descriptions.Item label="模型类型">{detailData.version?.model_type || '--'}</Descriptions.Item>
              <Descriptions.Item label="状态">
                <Tag color={statusColor(detailData.version?.status, detailData.version?.is_active)}>
                  {detailData.version?.is_active ? 'Active' : detailData.version?.status || '--'}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="训练时间">{shortDateTime(detailData.version?.created_at)}</Descriptions.Item>
              <Descriptions.Item label="产物路径">{detailData.version?.artifact_path || '--'}</Descriptions.Item>
            </Descriptions>

            <h4>近 30 天指标</h4>
            <Table
              size="small"
              rowKey={(row) => String(row.metric_date || row.created_at)}
              pagination={false}
              dataSource={detailData.metrics_history.slice(0, 8)}
              columns={[
                { title: '日期', dataIndex: 'metric_date', render: (value: unknown) => String(value || '--') },
                { title: 'MAE', dataIndex: 'mae', render: renderNumber },
                { title: 'RMSE', dataIndex: 'rmse', render: renderNumber },
                { title: 'MAPE', dataIndex: 'mape', render: renderNumber },
                { title: '峰值误差', dataIndex: 'peak_error', render: renderNumber }
              ]}
            />

            <h4>关联治理事件</h4>
            <Table
              size="small"
              rowKey={(row) => String(row.event_id || row.created_at)}
              pagination={false}
              dataSource={detailData.events.slice(0, 6)}
              columns={[
                { title: '时间', dataIndex: 'created_at', render: shortDateTime },
                { title: '动作', dataIndex: 'action' },
                { title: '状态', dataIndex: 'status', render: (value: unknown) => <Tag color={value === 'success' ? 'success' : 'processing'}>{String(value || '--')}</Tag> }
              ]}
            />
          </div>
        ) : (
          <Empty description={detailData?.message || '暂无模型详情'} />
        )}
      </DetailDrawer>

      <TaskLogViewer
        open={logOpen}
        title="模型训练日志"
        log={logText}
        loading={logLoading}
        onClose={() => setLogOpen(false)}
      />

      <Modal
        width={980}
        title="模型治理记录"
        open={eventsOpen}
        footer={null}
        onCancel={() => setEventsOpen(false)}
        destroyOnClose
      >
        <Table
          size="small"
          rowKey={(row) => String(row.event_id || row.created_at)}
          dataSource={data.events}
          columns={eventColumns}
          pagination={{ pageSize: 8, showSizeChanger: false }}
          scroll={{ x: 920 }}
        />
      </Modal>
    </div>
  );
}
