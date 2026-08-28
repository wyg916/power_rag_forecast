import {
  AlertOutlined,
  AuditOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  DatabaseOutlined,
  DollarOutlined,
  DownloadOutlined,
  ExclamationCircleOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
  ThunderboltOutlined,
  UserOutlined
} from '@ant-design/icons';
import { Button, Empty, Input, Progress, Space, Table, Tag, Tooltip } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useEffect, useState, type ReactNode } from 'react';
import { AppChart } from '../charts/AppChart';
import { chartColors } from '../charts/chartTheme';

function num(value: unknown) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function fmt(value: unknown, digits = 2) {
  const parsed = num(value);
  return parsed == null ? '--' : parsed.toFixed(digits);
}

function riskLabel(value: string) {
  if (value === 'high') return '高风险';
  if (value === 'medium') return '中风险';
  return '低风险';
}

function riskColor(value: string) {
  if (value === 'high') return 'error';
  if (value === 'medium') return 'warning';
  return 'success';
}

function statusColor(value: string) {
  if (value === 'approved' || value === 'published') return 'success';
  if (value === 'rejected' || value === 'cancelled' || value === 'expired') return 'error';
  if (value === 'pending_review') return 'warning';
  if (value === 'superseded') return 'default';
  return 'processing';
}

const overviewIcons = [<CheckCircleOutlined />, <AlertOutlined />, <SafetyCertificateOutlined />, <DollarOutlined />, <UserOutlined />];
const storageIcons = [<SafetyCertificateOutlined />, <ThunderboltOutlined />, <DollarOutlined />, <CheckCircleOutlined />, <AlertOutlined />];
const reviewIcons = [<AuditOutlined />, <CheckCircleOutlined />, <ExclamationCircleOutlined />, <AlertOutlined />, <ClockCircleOutlined />];

export function StrategyMetricStrip({ data, mode }: { data: any; mode: 'overview' | 'storage' | 'review' }) {
  const summary = data?.summary || {};
  const reviewRows = data?.reviewRows || [];
  const waitingReviews = reviewRows.filter((row: any) => ['draft', 'pending_review'].includes(row.status)).length;
  const approvedReviews = reviewRows.filter((row: any) => ['approved', 'published'].includes(row.status)).length;
  const rejectedReviews = reviewRows.filter((row: any) => row.status === 'rejected').length;
  const metrics = mode === 'overview'
    ? [
        ['策略结论', data?.available ? data?.strategyStatusLabel || '策略记录' : '暂无策略', '策略与人工复核状态汇总', 'green'],
        ['预测高价时段', summary.highRiskHours == null ? '--' : `${summary.highRiskHours} 段`, summary.highRiskCount == null ? '策略事实暂不可用' : `${summary.highRiskCount} 条绑定预测建议`, 'red'],
        ['预测低价窗口', summary.lowWindowCount == null ? '--' : `${summary.lowWindowCount} 段`, '候选窗口与策略批次绑定', 'green'],
        ['收益测算', summary.realizedRevenue == null ? '--' : `¥${Number(summary.realizedRevenue).toLocaleString()}`, '按当前策略批次的计划与反馈口径计算', 'blue'],
        ['人工复核数', summary.reviewCount ?? '--', summary.reviewCount == null ? '审核事实暂不可用' : `${waitingReviews} 条待处理`, 'orange']
      ]
    : mode === 'storage'
      ? [
          ['储能设备', summary.deviceCount == null ? '--' : `${summary.onlineDeviceCount ?? '--'} / ${summary.deviceCount}`, '可用 / 全部设备记录', 'green'],
          ['平均 SOC', summary.averageSoc == null ? '--' : `${fmt(summary.averageSoc, 1)}%`, '当前业务批次中的设备状态点', 'blue'],
          ['计划反馈', summary.executionCount == null ? '--' : `${summary.completedExecutionCount ?? '--'} / ${summary.executionCount}`, '完成 / 全部计划项', 'orange'],
          ['执行中', summary.inProgressExecutionCount ?? '--', '只读反馈，不下发设备指令', 'green'],
          ['收益测算', summary.realizedRevenue == null ? '--' : `¥${Number(summary.realizedRevenue).toLocaleString()}`, '按策略批次核算口径计算', 'orange']
        ]
      : [
          ['待处理数量', waitingReviews, '草稿与待复核策略', 'orange'],
          ['已通过', approvedReviews, '审核流程已记录', 'green'],
          ['已驳回', rejectedReviews, '审核流程已记录', 'red'],
          ['紧急高风险', data?.reviewRows?.filter((row: any) => row.risk === 'high').length ?? 0, '需要优先人工判断', 'red'],
          ['平均处理时长', '--', '当前无已处理记录', 'blue']
        ];
  const icons = mode === 'overview' ? overviewIcons : mode === 'storage' ? storageIcons : reviewIcons;
  return (
    <div className="strategy-metric-strip">
      {metrics.map((metric, index) => (
        <article className={`strategy-metric tone-${metric[3]}`} key={String(metric[0])}>
          <span className="strategy-metric-icon">{icons[index]}</span>
          <div><h3>{metric[0]}</h3><strong>{metric[1]}</strong><p>{metric[2]}</p></div>
        </article>
      ))}
    </div>
  );
}

function chartPlan(data: any) {
  return data?.hourlyPlan || [];
}

export function StrategyOverviewMain({ data }: { data: any }) {
  const plan = chartPlan(data);
  const highTimes = plan.filter((item: any) => item.risk === 'high').map((item: any) => item.time);
  const lowTimes = plan.filter((item: any) => item.action === '充电').map((item: any) => item.time);
  const option = {
    animation: false,
    tooltip: { trigger: 'axis', backgroundColor: '#fff', borderColor: '#dbe5ed', textStyle: { color: '#17223b' } },
    legend: { top: 0, left: 0, data: ['预测价格', '充电功率', '放电功率'] },
    grid: { left: 48, right: 48, top: 48, bottom: 46 },
    xAxis: { type: 'category', data: plan.map((item: any) => item.time), axisTick: { show: false }, axisLine: { lineStyle: { color: '#dfe7ef' } } },
    yAxis: [
      { type: 'value', name: '价格（元/kWh）', splitLine: { lineStyle: { color: '#edf2f7' } } },
      { type: 'value', name: '功率（MW）', splitLine: { show: false } }
    ],
    dataZoom: [{ type: 'inside' }, { type: 'slider', height: 14, bottom: 5 }],
    series: [
      {
        name: '预测价格',
        type: 'line',
        smooth: true,
        symbolSize: 5,
        data: plan.map((item: any) => item.price),
        lineStyle: { width: 2, color: chartColors.blue },
        itemStyle: { color: chartColors.blue },
        markArea: {
          silent: true,
          data: [
            ...(lowTimes.length ? [[{ name: '低价窗口', xAxis: lowTimes[0], itemStyle: { color: 'rgba(0,184,148,.10)' } }, { xAxis: lowTimes.at(-1) }]] : []),
            ...(highTimes.length ? [[{ name: '高风险', xAxis: highTimes[0], itemStyle: { color: 'rgba(255,77,79,.09)' } }, { xAxis: highTimes.at(-1) }]] : [])
          ]
        }
      },
      { name: '充电功率', type: 'bar', yAxisIndex: 1, data: plan.map((item: any) => item.power > 0 ? item.power : 0), itemStyle: { color: chartColors.green } },
      { name: '放电功率', type: 'bar', yAxisIndex: 1, data: plan.map((item: any) => item.power < 0 ? item.power : 0), itemStyle: { color: '#ff8a00' } }
    ]
  };
  return (
    <div className="strategy-overview-main">
      <section className="strategy-card strategy-timeline-card">
        <div className="strategy-card-head"><h2>策略时间轴图</h2><div><Tag color="success">日视图</Tag><Tag>列视图</Tag></div></div>
        {plan.length ? <AppChart option={option} height={400} /> : <Empty description="暂无策略时间轴" />}
      </section>
      <OverviewInsight data={data} />
    </div>
  );
}

function OverviewInsight({ data }: { data: any }) {
  const summary = data?.summary || {};
  const highLabel = (summary.highHours || []).slice(0, 5).join('、') || '--';
  const lowLabel = (summary.lowHours || []).slice(0, 5).join('、') || '--';
  return (
    <section className="strategy-card strategy-advice-card">
      <div className="strategy-card-head"><h2>策略建议说明</h2><div><Tag color={data?.strategyUsable ? 'success' : 'warning'}>{data?.strategyUsable ? '人工复核后参考' : '发布门禁未通过'}</Tag><Tag color="warning">需人工确认</Tag></div></div>
      <InsightBlock tone={data?.strategyUsable ? 'green' : 'red'} title="结论">{data?.strategyUsable ? '已形成通过治理门禁的策略记录；实际执行前仍须结合合同、设备与当前市场复核。' : `当前记录状态为${data?.strategyStatusLabel || '不可用'}；使用前请完成业务复核和发布门禁校验。`}</InsightBlock>
      <InsightBlock tone="blue" title="业务建议">
        <ul><li>低价候选时段：{lowLabel}</li><li>高风险候选时段：{highLabel}</li><li>储能动作仅作为辅助决策建议。</li></ul>
      </InsightBlock>
      <InsightBlock tone="green" title="执行优先级">
        <div className="priority-row"><strong>{summary.priorityScore >= 80 ? '高' : summary.priorityScore >= 50 ? '中' : '低'}（建议优先复核）</strong><Progress percent={summary.priorityScore || 0} showInfo={false} strokeColor={chartColors.green} /><span>{summary.priorityScore || 0} / 100</span></div>
      </InsightBlock>
      <InsightBlock tone="red" title="风险提示">
        <ul><li>预测峰谷价差仅表示候选空间，不等同收益。</li><li>设备状态、计划反馈和收益测算均须结合批次时间及核算口径复核。</li><li>高风险策略必须人工确认。</li></ul>
      </InsightBlock>
    </section>
  );
}

function InsightBlock({ tone, title, children }: { tone: string; title: string; children: ReactNode }) {
  return <div className={`strategy-insight-block tone-${tone}`}><h3>{title}</h3><div>{children}</div></div>;
}

export function StrategyOverviewBottom({ data }: { data: any }) {
  const summary = data?.summary || {};
  const risks = data?.anomalies || [];
  const executionPercent = summary.executionCount
    ? Math.round((summary.completedExecutionCount / summary.executionCount) * 100)
    : 0;
  const typeCounts = risks.reduce((result: Record<string, number>, item: any) => {
    const key = item.anomaly_type || riskLabel(item.risk_level);
    result[key] = (result[key] || 0) + 1;
    return result;
  }, {});
  const riskRows = Object.entries(typeCounts).slice(0, 4);
  return (
    <div className="strategy-overview-bottom">
      <section className="strategy-card mini-panel"><div className="strategy-card-head"><h2>关键操作建议</h2></div>
        <p><SafetyCertificateOutlined /> 低价补仓：优先复核 {summary.lowWindowCount ?? '--'} 个候选窗口</p>
        <p><AlertOutlined /> 晚高峰风险：关注 {summary.highRiskHours ?? '--'} 个高风险时段</p>
        <p><ThunderboltOutlined /> 储能状态：{summary.onlineDeviceCount ?? '--'} 台在线，平均 SOC {summary.averageSoc == null ? '--' : `${fmt(summary.averageSoc, 1)}%`}</p>
      </section>
      <section className="strategy-card mini-panel risk-source-panel"><div className="strategy-card-head"><h2>风险类型分布</h2></div>
        {riskRows.length ? riskRows.map(([name, count], index) => <p key={name}><i className={`dot dot-${index}`} /><span>{name}</span><strong>{String(count)}</strong></p>) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无风险记录" />}
      </section>
      <section className="strategy-card mini-panel execution-panel"><div className="strategy-card-head"><h2>执行状态摘要</h2></div>
        <div className="execution-summary-body">
          <div className="execution-status-list">
            <p><span>策略生成</span><strong>{summary.strategyCount ?? '--'}</strong></p>
            <p><span>执行反馈</span><strong>{summary.executionCount ?? '--'}</strong></p>
            <p><span>已完成</span><strong>{summary.completedExecutionCount ?? '--'}</strong></p>
          </div>
          <div className="execution-progress-wrap" aria-label={`执行完成率 ${executionPercent}%`}>
            <Progress
              type="circle"
              size={82}
              strokeWidth={10}
              percent={executionPercent}
              strokeColor={chartColors.green}
              trailColor="#e7eef3"
              format={(percent) => <strong>{percent ?? 0}%</strong>}
            />
            <span>执行完成率</span>
          </div>
        </div>
      </section>
      <section className="strategy-card mini-panel revenue-panel"><div className="strategy-card-head"><h2>收益对比</h2></div>
        <p><span>峰谷价差空间</span><strong>{fmt(summary.spread)} 元/kWh</strong></p>
        <p><span>收益测算</span><strong>{summary.realizedRevenue == null ? '--' : `¥${Number(summary.realizedRevenue).toLocaleString()}`}</strong></p>
        <small>{summary.spreadNote || '按当前策略批次的计划与反馈口径计算。'}</small>
      </section>
    </div>
  );
}

export function StorageWorkspace({
  data,
  selectedKey,
  selectedDeviceId,
  onSelect,
  onDeviceChange
}: {
  data: any;
  selectedKey?: string;
  selectedDeviceId?: string;
  onSelect: (row: any) => void;
  onDeviceChange: (deviceId: string) => void;
}) {
  const devices = data?.devices || [];
  const device = devices.find((item: any) => item.device_id === selectedDeviceId) || devices[0];
  const plan = device ? (data?.devicePlans?.[device.device_id] || []) : [];
  const executions = (data?.executionItems || []).filter((item: any) => item.device_id === device?.device_id);
  const selected = executions.find((item: any) => item.key === selectedKey) || executions[0];
  const completedExecutions = executions.filter((item: any) => item.execution_status === 'completed').length;
  return (
    <div className="storage-workspace">
      <section className="strategy-card storage-window-list">
        <div className="strategy-card-head"><h2>设备清单（{devices.length} 台）</h2></div>
        <div className="storage-window-scroll">
          {devices.map((item: any) => (
            <button className={device?.device_id === item.device_id ? 'active' : ''} key={item.device_id} onClick={() => onDeviceChange(item.device_id)}>
              <span><strong>{item.device_name}</strong><small>{item.station_name}</small></span>
              <b>{item.latest_soc?.soc_pct == null ? '--' : `${fmt(item.latest_soc.soc_pct, 1)}%`}</b>
              <Tag color={item.operating_status === 'online' ? 'success' : 'default'}>{item.operating_status === 'online' ? '在线' : item.operating_status}</Tag>
            </button>
          ))}
        </div>
        {device && (
          <>
            <div className="storage-note">
              <strong>{device.device_name}</strong>
              <p>容量 {fmt(device.rated_capacity_mwh, 1)} MWh · 功率 {fmt(device.rated_power_mw, 1)} MW</p>
              <p>SOC 约束 {fmt(device.soc_lower_pct, 0)}% - {fmt(device.soc_upper_pct, 0)}%</p>
            </div>
            <div className="storage-device-summary">
              <div className="storage-subsection-title"><span>当前设备概览</span><small>随所选设备联动</small></div>
              <div className="storage-device-summary-grid">
                <p><span>SOC 状态点</span><strong>{plan.length || '--'}</strong></p>
                <p><span>反馈项</span><strong>{executions.length || '--'}</strong></p>
                <p><span>已完成</span><strong>{completedExecutions}</strong></p>
                <p><span>可用电量</span><strong>{device.latest_soc?.available_energy_mwh == null ? '--' : `${fmt(device.latest_soc.available_energy_mwh, 1)} MWh`}</strong></p>
              </div>
              <div className="storage-soc-overview">
                <div><span>当前 SOC</span><strong>{device.latest_soc?.soc_pct == null ? '--' : `${fmt(device.latest_soc.soc_pct, 1)}%`}</strong></div>
                <Progress
                  percent={device.latest_soc?.soc_pct == null ? 0 : Number(device.latest_soc.soc_pct)}
                  showInfo={false}
                  strokeColor={chartColors.green}
                  trailColor="#e7eef3"
                />
              </div>
            </div>
          </>
        )}
      </section>
      <section className="storage-center-column">
        <StorageChart plan={plan} />
        <StorageExecutionTable rows={executions} onSelect={onSelect} />
      </section>
      <StorageDetail data={data} device={device} selected={selected} />
    </div>
  );
}

function StorageChart({ plan }: { plan: any[] }) {
  const option = {
    animation: false,
    tooltip: { trigger: 'axis', backgroundColor: '#fff', borderColor: '#dbe5ed', textStyle: { color: '#17223b' } },
    legend: { top: 0, data: ['充电功率', '放电功率', 'SOC'] },
    grid: { left: 48, right: 52, top: 46, bottom: 34 },
    xAxis: { type: 'category', data: plan.map((item: any) => item.time), axisTick: { show: false } },
    yAxis: [{ type: 'value', name: '功率（MW）' }, { type: 'value', name: 'SOC（%）', min: 0, max: 100, splitLine: { show: false } }],
    series: [
      { name: '充电功率', type: 'bar', data: plan.map((item: any) => item.power < 0 ? Math.abs(item.power) : 0), itemStyle: { color: chartColors.green } },
      { name: '放电功率', type: 'bar', data: plan.map((item: any) => item.power > 0 ? -item.power : 0), itemStyle: { color: chartColors.blue } },
      { name: 'SOC', type: 'line', yAxisIndex: 1, smooth: true, symbolSize: 4, data: plan.map((item: any) => item.actualSoc), lineStyle: { color: '#ff8a00', width: 2 } }
    ]
  };
  return (
    <section className="strategy-card storage-chart-card">
      <div className="strategy-card-head"><h2>设备 SOC 与充放电功率</h2><Tooltip title="按当前业务批次展示"><Tag color="success">批次状态记录</Tag></Tooltip></div>
      {plan.length ? <AppChart option={option} height={286} /> : <Empty description="当前设备暂无 SOC 事实" />}
    </section>
  );
}

function StorageExecutionTable({ rows, onSelect }: { rows: any[]; onSelect: (row: any) => void }) {
  const completedCount = rows.filter((row) => row.execution_status === 'completed').length;
  const activeCount = rows.filter((row) => row.execution_status === 'in_progress').length;
  const plannedEnergy = rows.reduce((total, row) => total + (num(row.plannedEnergy) || 0), 0);
  const actualEnergyItems = rows.map((row) => num(row.actualEnergy)).filter((value): value is number => value != null);
  const actualEnergy = actualEnergyItems.reduce((total, value) => total + value, 0);
  const columns: ColumnsType<any> = [
    { title: '窗口', dataIndex: 'time', width: 56 },
    { title: '动作', dataIndex: 'actionLabel', width: 54, render: (value) => <Tag color={value === '充电' ? 'success' : value === '放电' ? 'blue' : 'default'}>{value}</Tag> },
    { title: '计划功率', dataIndex: 'plannedPower', width: 66, align: 'right', render: (value) => `${fmt(value, 1)} MW` },
    { title: '反馈功率', dataIndex: 'actualPower', width: 66, align: 'right', render: (value) => value == null ? '--' : `${fmt(value, 1)} MW` },
    { title: '状态', dataIndex: 'statusLabel', width: 60, render: (value, row) => <Tag color={row.execution_status === 'completed' ? 'success' : row.execution_status === 'failed' ? 'error' : 'processing'}>{value}</Tag> },
    { title: '收益/测算', dataIndex: 'realizedRevenue', width: 74, align: 'right', render: (value) => value == null ? '--' : `¥${Number(value).toLocaleString()}` },
    { title: '反馈', width: 68, render: (_, row) => <Button type="link" size="small" onClick={() => onSelect(row)}>查看详情</Button> }
  ];
  return (
    <section className="strategy-card storage-plan-table">
      <div className="strategy-card-head"><h2>执行反馈清单（{rows.length} 条）</h2></div>
      <Table size="small" rowKey="key" columns={columns} dataSource={rows} pagination={false} tableLayout="fixed" scroll={{ y: 145 }} />
      <div className="storage-execution-summary" aria-label="当前设备执行反馈摘要">
        <p><span>已完成</span><strong>{completedCount}</strong></p>
        <p><span>执行中</span><strong>{activeCount}</strong></p>
        <p><span>计划电量</span><strong>{rows.length ? `${fmt(plannedEnergy, 1)} MWh` : '--'}</strong></p>
        <p><span>反馈电量</span><strong>{actualEnergyItems.length ? `${fmt(actualEnergy, 1)} MWh` : '--'}</strong></p>
      </div>
    </section>
  );
}

function StorageDetail({ data, device, selected }: { data: any; device: any; selected: any }) {
  return (
    <section className="strategy-card storage-detail-panel">
      <div className="strategy-card-head"><h2>计划与收益详情</h2><Tag color="success">业务批次记录</Tag></div>
      {selected ? (
        <>
          <h3>{selected.time} <Tag color={selected.actionLabel === '充电' ? 'success' : selected.actionLabel === '放电' ? 'blue' : 'default'}>{selected.actionLabel}</Tag></h3>
          <InsightBlock tone="blue" title="执行对象"><p>{device?.device_name || selected.device_id}</p><p>执行编号：{selected.execution_id}</p></InsightBlock>
          <InsightBlock tone="green" title="计划与实绩"><p>功率：{fmt(selected.plannedPower, 1)} / {selected.actualPower == null ? '--' : fmt(selected.actualPower, 1)} MW（计划 / 实际）</p><p>电量：{fmt(selected.plannedEnergy, 1)} / {selected.actualEnergy == null ? '--' : fmt(selected.actualEnergy, 1)} MWh</p></InsightBlock>
          <InsightBlock tone="orange" title="SOC 反馈"><p>执行前：{fmt(selected.socBefore, 1)}%</p><p>执行后：{selected.socAfter == null ? '--' : `${fmt(selected.socAfter, 1)}%`}</p></InsightBlock>
          <InsightBlock tone="red" title="执行反馈"><p>状态：{selected.statusLabel}</p><p>{selected.feedback_message || '暂无反馈说明'}</p></InsightBlock>
          <div className="strategy-runtime-revenue"><span>收益测算</span><strong>{selected.realizedRevenue == null ? '--' : `¥${Number(selected.realizedRevenue).toLocaleString()}`}</strong><small>核算口径：{selected.settlement_method || '接口未提供'}</small></div>
          <Tag color="blue">只读事实，不自动交易、不控制设备</Tag>
        </>
      ) : <Empty description="当前设备暂无执行反馈" />}
    </section>
  );
}

export function ReviewWorkspace({
  data,
  selectedKey,
  onSelect,
  onAction,
  permissions,
  reviewHistory,
  rows,
  totalRows
}: {
  data: any;
  selectedKey?: string;
  onSelect: (row: any) => void;
  onAction: (row: any, action: string, comment: string) => void;
  permissions: { canSubmit: boolean; canReview: boolean; canPublish: boolean };
  reviewHistory: any[];
  rows: any[];
  totalRows: number;
}) {
  const allRows = data?.reviewRows || [];
  const selected = rows.find((row: any) => row.key === selectedKey) || rows[0];
  const columns: ColumnsType<any> = [
    {
      title: '编号',
      dataIndex: 'id',
      width: 92,
      ellipsis: { showTitle: false },
      render: (value) => <Tooltip title={value}><span className="strategy-cell-ellipsis">{value}</span></Tooltip>
    },
    {
      title: '复核原因',
      dataIndex: 'reason',
      width: 82,
      ellipsis: { showTitle: false },
      render: (value) => <Tooltip title={value}><span className="strategy-cell-ellipsis">{value}</span></Tooltip>
    },
    {
      title: '策略建议',
      dataIndex: 'action',
      width: 96,
      ellipsis: { showTitle: false },
      render: (value) => <Tooltip title={value}><span className="strategy-cell-ellipsis">{value}</span></Tooltip>
    },
    { title: '风险等级', dataIndex: 'risk', width: 64, render: (value) => <Tag color={riskColor(value)}>{riskLabel(value)}</Tag> },
    { title: '置信度', dataIndex: 'confidence', width: 56, render: (value) => value == null ? '--' : `${fmt(value, 1)}%` },
    { title: '提交时间', dataIndex: 'submittedAt', width: 74, render: (value) => String(value).slice(5, 16) },
    { title: '审核状态', dataIndex: 'status', width: 64, render: (value, row) => <Tag color={statusColor(value)}>{row.statusLabel || value}</Tag> },
    { title: '操作', width: 72, render: (_, row) => <Space size={2}><Button type="link" size="small" onClick={() => onSelect(row)}>查看</Button><Button type="link" size="small" onClick={() => onSelect(row)}>复核</Button></Space> }
  ];
  return (
    <div className="review-workspace">
      <div className="review-list-column">
        <section className="strategy-card review-table-card">
          <div className="review-tabs"><b>全部（{totalRows}）</b><span>当前筛选（{rows.length}）</span><span>待处理（{allRows.filter((row: any) => ['draft', 'pending_review'].includes(row.status)).length}）</span><span>已处理（{allRows.filter((row: any) => !['draft', 'pending_review'].includes(row.status)).length}）</span><span>紧急（{allRows.filter((row: any) => row.risk === 'high').length}）</span></div>
          <Table size="small" rowKey="key" columns={columns} dataSource={rows} pagination={{ pageSize: 10, showSizeChanger: false }} tableLayout="fixed" scroll={{ y: 'clamp(154px, calc(100dvh - 560px), 392px)' }} onRow={(row) => ({ onClick: () => onSelect(row) })} rowClassName={(row) => selected?.key === row.key ? 'selected-review-row' : ''} />
        </section>
        <ReviewBottomSummary rows={rows} />
      </div>
      <ReviewDetail row={selected} onAction={onAction} permissions={permissions} reviewHistory={reviewHistory} />
    </div>
  );
}

function ReviewBottomSummary({ rows }: { rows: any[] }) {
  return (
    <div className="review-bottom-summary">
      <section className="strategy-card"><div className="strategy-card-head"><h2>复核队列摘要（当前筛选）</h2></div>
        <div className="review-kpis"><p><span>队列总数</span><strong>{rows.length}</strong></p><p><span>紧急</span><strong className="danger">{rows.filter((row) => row.risk === 'high').length}</strong></p><p><span>中风险</span><strong className="warning">{rows.filter((row) => row.risk === 'medium').length}</strong></p><p><span>低风险</span><strong>{rows.filter((row) => row.risk === 'low').length}</strong></p></div>
      </section>
      <section className="strategy-card"><div className="strategy-card-head"><h2>风险分布</h2></div>
        <div className="review-risk-bars">
          {['high', 'medium', 'low'].map((risk) => <div key={risk}><span>{riskLabel(risk)}</span><Progress percent={rows.length ? Math.round(rows.filter((row) => row.risk === risk).length / rows.length * 100) : 0} showInfo={false} strokeColor={risk === 'high' ? '#ff4d4f' : risk === 'medium' ? '#f59e0b' : '#00b894'} /></div>)}
        </div>
      </section>
    </div>
  );
}

function ReviewDetail({ row, onAction, permissions, reviewHistory }: {
  row: any;
  onAction: (row: any, action: string, comment: string) => void;
  permissions: { canSubmit: boolean; canReview: boolean; canPublish: boolean };
  reviewHistory: any[];
}) {
  const [comment, setComment] = useState('');
  useEffect(() => setComment(''), [row?.key]);
  return (
    <section className="strategy-card review-detail-panel">
      <div className="strategy-card-head"><h2>复核详情</h2><Tag color="blue">仅决策支持，不自动执行</Tag></div>
      {row ? (
        <>
          <div className="review-detail-scroll">
            <InsightBlock tone="green" title="策略摘要"><p>编号：{row.id}</p><p>候选动作：{row.action}</p><p>目标时段：{row.period}</p><p>状态：<Tag color={statusColor(row.status)}>{row.statusLabel || row.status}</Tag></p></InsightBlock>
            <InsightBlock tone="orange" title="复核原因"><Tag color={riskColor(row.risk)}>{riskLabel(row.risk)}</Tag><p>{row.reason}</p></InsightBlock>
            <InsightBlock tone="red" title="受控解释"><p>{row.evidence?.explanation}</p><p>风险概率：{row.evidence?.riskProbability == null ? '--' : `${fmt(row.evidence.riskProbability * 100, 1)}%`}</p></InsightBlock>
            <div className="review-evidence-grid">
              <InsightBlock tone="blue" title="模型依据"><p>最高预测价格：{fmt(row.evidence?.predictedPrice, 3)}</p><p>峰谷价差：{fmt(row.evidence?.peakValleySpread, 3)}</p><p>置信度：{row.confidence == null ? '未提供' : `${fmt(row.confidence, 1)}%`}</p></InsightBlock>
            </div>
            <div className="review-related"><h3>不可变审核历史（{reviewHistory.length}）</h3>
              {reviewHistory.length ? reviewHistory.map((item: any) => <p key={item.review_id}><span>{item.action} · {item.reviewer}</span><strong>{item.previous_status} → {item.new_status}</strong></p>) : <p><span>暂无状态流转记录</span><strong>--</strong></p>}
            </div>
            <label className="review-comment">复核意见（驳回/退回必填）<Input.TextArea value={comment} maxLength={2000} showCount rows={3} placeholder="输入人工判断依据；每次动作均写入不可变审核记录" onChange={(event) => setComment(event.target.value)} /></label>
          </div>
          <div className="review-actions">
            {row.status === 'draft' && permissions.canSubmit ? <Button type="primary" onClick={() => onAction(row, 'submit', comment)}>提交复核</Button> : null}
            {row.status === 'pending_review' && permissions.canReview ? <>
              <Button type="primary" onClick={() => onAction(row, 'approve', comment)}>通过</Button>
              <Button danger onClick={() => onAction(row, 'reject', comment)}>驳回</Button>
              <Button onClick={() => onAction(row, 'return', comment)}>退回补充</Button>
            </> : null}
            {row.status === 'approved' && permissions.canPublish ? <Tooltip title={row.isStale ? (row.staleReason || '当前记录未通过发布门禁，点击查看原因') : '发布仅形成受控记录，不触发执行'}><Button type="primary" onClick={() => onAction(row, 'publish', comment)}>发布策略记录</Button></Tooltip> : null}
            {!['draft', 'pending_review', 'approved'].includes(row.status) && <Tag color={statusColor(row.status)}>该状态无可用人工动作</Tag>}
          </div>
        </>
      ) : <Empty description="暂无策略复核记录" />}
    </section>
  );
}

export const strategyActions = {
  refresh: <ReloadOutlined />,
  export: <DownloadOutlined />,
  config: <DatabaseOutlined />
};
