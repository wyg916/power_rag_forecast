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
import { Button, Empty, Input, Progress, Select, Space, Table, Tag, Tooltip } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import type { ReactNode } from 'react';
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

export function StrategyPageHeader({ mode }: { mode: 'overview' | 'storage' | 'review' }) {
  const copy = mode === 'overview'
    ? ['策略中心 / 总览主页面', '承接预测结果并形成交易决策的核心页面，提供可执行策略与风险管理建议。']
    : mode === 'storage'
      ? ['策略中心 / 低价窗口与储能策略', '将价格预测转化为采购与储能动作建议，平衡成本、收益与风险。']
      : ['策略中心 / 人工复核', '承接高风险策略的人工审核与人机协同闭环，确保关键交易决策安全、合规、可追溯。'];
  return (
    <header className="strategy-design-header">
      <h1>{copy[0]}</h1>
      <p>{copy[1]}</p>
    </header>
  );
}

export function StrategyContextBar({
  data,
  mode,
  actions
}: {
  data: any;
  mode: 'overview' | 'storage' | 'review';
  actions: ReactNode;
}) {
  return (
    <div className="strategy-context-bar">
      <div className="strategy-context-fields">
        <label>{mode === 'review' ? '复核日期' : '策略日期'}<strong>{data?.strategyDate || '--'}</strong></label>
        <label>区域<Select size="small" defaultValue={data?.region || '浙江省'} options={[{ value: '浙江省', label: '浙江省' }]} /></label>
        {mode === 'review' ? (
          <>
            <label>风险等级<Select size="small" defaultValue="all" options={[{ value: 'all', label: '全部' }, { value: 'high', label: '高风险' }, { value: 'medium', label: '中风险' }]} /></label>
            <label>审核状态<Select size="small" defaultValue="all" options={[{ value: 'all', label: '全部' }, { value: 'pending', label: '待复核' }]} /></label>
            <Input size="small" allowClear placeholder="搜索编号 / 复核原因 / 责任人" />
          </>
        ) : (
          <>
            <label>模型版本<strong>{data?.modelVersion || '--'} <Tag color="success">最新</Tag></strong></label>
            {mode === 'storage' && <label>执行对象<Select size="small" defaultValue="all" options={[{ value: 'all', label: '全部' }]} /></label>}
          </>
        )}
      </div>
      <Space size={8} className="strategy-context-actions">{actions}</Space>
    </div>
  );
}

const overviewIcons = [<CheckCircleOutlined />, <AlertOutlined />, <SafetyCertificateOutlined />, <DollarOutlined />, <UserOutlined />];
const storageIcons = [<SafetyCertificateOutlined />, <ThunderboltOutlined />, <DollarOutlined />, <CheckCircleOutlined />, <AlertOutlined />];
const reviewIcons = [<AuditOutlined />, <CheckCircleOutlined />, <ExclamationCircleOutlined />, <AlertOutlined />, <ClockCircleOutlined />];

export function StrategyMetricStrip({ data, mode }: { data: any; mode: 'overview' | 'storage' | 'review' }) {
  const summary = data?.summary || {};
  const metrics = mode === 'overview'
    ? [
        ['今日策略结论', data?.available ? '已生成策略' : '暂无策略', '建议：人工复核后执行', 'green'],
        ['高价风险时段', `${summary.highRiskHours ?? 0} 段`, `${summary.highRiskCount ?? 0} 条风险建议`, 'red'],
        ['低价采购窗口', `${summary.lowWindowCount ?? 0} 段`, '来自预测与策略结果', 'green'],
        ['峰谷价差空间', fmt(summary.spread), '元/kWh，不等同实际收益', 'blue'],
        ['人工复核数', summary.reviewCount ?? 0, '状态流转待后端补齐', 'orange']
      ]
    : mode === 'storage'
      ? [
          ['低价采购窗口数量', `${summary.lowWindowCount ?? 0} 段`, '按真实预测结果识别', 'green'],
          ['储能建议时段数', `${summary.storageCount ?? 0} 段`, '充放电功率来自运行配置', 'blue'],
          ['峰谷价差空间', fmt(summary.spread), '元/kWh，不等同实际收益', 'orange'],
          ['可执行动作数', data?.hourlyPlan?.filter((item: any) => item.action !== '观望').length ?? 0, '执行清单后端待接入', 'green'],
          ['风险等级概览', summary.highRiskCount ? '需复核' : '低风险', `${summary.highRiskCount ?? 0} 条高风险建议`, 'orange']
        ]
      : [
          ['待复核数量', summary.reviewCount ?? 0, '来自策略风险与异常结果', 'orange'],
          ['已通过', '--', '复核状态机待接入', 'green'],
          ['已驳回', '--', '复核状态机待接入', 'red'],
          ['紧急高风险', data?.reviewRows?.filter((row: any) => row.risk === 'high').length ?? 0, '需要优先人工判断', 'red'],
          ['平均处理时长', '--', 'SLA 统计待接入', 'blue']
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
      <div className="strategy-card-head"><h2>策略建议说明</h2><div><Tag color="success">优先执行</Tag><Tag color="warning">需人工确认</Tag></div></div>
      <InsightBlock tone="green" title="结论">已基于预测与策略接口形成候选动作；实际执行前必须结合合同、设备和实时市场复核。</InsightBlock>
      <InsightBlock tone="blue" title="业务建议">
        <ul><li>低价候选时段：{lowLabel}</li><li>高风险候选时段：{highLabel}</li><li>储能动作仅作为辅助决策建议。</li></ul>
      </InsightBlock>
      <InsightBlock tone="green" title="执行优先级">
        <div className="priority-row"><strong>{summary.priorityScore >= 80 ? '高' : summary.priorityScore >= 50 ? '中' : '低'}（建议优先复核）</strong><Progress percent={summary.priorityScore || 0} showInfo={false} strokeColor={chartColors.green} /><span>{summary.priorityScore || 0} / 100</span></div>
      </InsightBlock>
      <InsightBlock tone="red" title="风险提示">
        <ul><li>峰谷价差仅表示候选空间，不等同已实现收益。</li><li>当前未接入真实执行反馈与收益回填。</li><li>高风险策略必须人工确认。</li></ul>
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
  const typeCounts = risks.reduce((result: Record<string, number>, item: any) => {
    const key = item.anomaly_type || riskLabel(item.risk_level);
    result[key] = (result[key] || 0) + 1;
    return result;
  }, {});
  const riskRows = Object.entries(typeCounts).slice(0, 4);
  return (
    <div className="strategy-overview-bottom">
      <section className="strategy-card mini-panel"><div className="strategy-card-head"><h2>关键操作建议</h2></div>
        <p><SafetyCertificateOutlined /> 低价补仓：优先复核 {summary.lowWindowCount || 0} 个候选窗口</p>
        <p><AlertOutlined /> 晚高峰风险：关注 {summary.highRiskHours || 0} 个高风险时段</p>
        <p><ThunderboltOutlined /> 储能优化：当前 SOC 与设备状态未接入</p>
      </section>
      <section className="strategy-card mini-panel risk-source-panel"><div className="strategy-card-head"><h2>风险来源分布</h2></div>
        {riskRows.length ? riskRows.map(([name, count], index) => <p key={name}><i className={`dot dot-${index}`} /><span>{name}</span><strong>{String(count)}</strong></p>) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无风险来源" />}
      </section>
      <section className="strategy-card mini-panel execution-panel"><div className="strategy-card-head"><h2>执行状态摘要</h2></div>
        <div><span>策略生成</span><strong>{summary.strategyCount || 0}</strong></div>
        <div><span>人工确认项</span><strong>{summary.reviewCount || 0}</strong></div>
        <div><span>已执行策略</span><strong>待接入</strong></div>
        <Progress type="circle" size={68} percent={0} format={() => '待接入'} strokeColor={chartColors.green} />
      </section>
      <section className="strategy-card mini-panel revenue-panel"><div className="strategy-card-head"><h2>收益对比</h2></div>
        <p><span>峰谷价差空间</span><strong>{fmt(summary.spread)} 元/kWh</strong></p>
        <p><span>实际执行收益</span><strong>待回填</strong></p>
        <small>{summary.spreadNote}</small>
      </section>
    </div>
  );
}

export function StorageWorkspace({ data, selectedKey, onSelect }: { data: any; selectedKey?: string; onSelect: (row: any) => void }) {
  const plan = data?.hourlyPlan || [];
  const actionable = plan.filter((item: any) => item.action !== '观望');
  const selected = plan.find((item: any) => item.key === selectedKey) || actionable[0] || plan[0];
  return (
    <div className="storage-workspace">
      <section className="strategy-card storage-window-list">
        <div className="strategy-card-head"><h2>低价采购窗口（{actionable.length} 条）</h2></div>
        <div className="storage-window-scroll">
          {actionable.map((item: any) => (
            <button className={selected?.key === item.key ? 'active' : ''} key={item.key} onClick={() => onSelect(item)}>
              <span><strong>{item.time}</strong><small>{item.action}建议</small></span>
              <b>{item.power} MW</b>
              <Tag color={riskColor(item.risk)}>{riskLabel(item.risk)}</Tag>
            </button>
          ))}
        </div>
        <div className="storage-note"><strong>说明</strong><p>候选窗口由真实预测和策略结果识别；执行前需核对 SOC、容量、效率、合同与并网约束。</p></div>
      </section>
      <section className="storage-center-column">
        <StorageChart data={data} />
        <StoragePlanTable rows={plan} onSelect={onSelect} />
      </section>
      <StorageDetail data={data} selected={selected} />
    </div>
  );
}

function StorageChart({ data }: { data: any }) {
  const plan = data?.hourlyPlan || [];
  const option = {
    animation: false,
    tooltip: { trigger: 'axis', backgroundColor: '#fff', borderColor: '#dbe5ed', textStyle: { color: '#17223b' } },
    legend: { top: 0, data: ['建议充电', '建议放电', '预测价格', '参数化 SOC'] },
    grid: { left: 48, right: 52, top: 46, bottom: 34 },
    xAxis: { type: 'category', data: plan.map((item: any) => item.time), axisTick: { show: false } },
    yAxis: [{ type: 'value', name: '功率（MW）' }, { type: 'value', name: '价格 / SOC', splitLine: { show: false } }],
    series: [
      { name: '建议充电', type: 'bar', data: plan.map((item: any) => item.power > 0 ? item.power : 0), itemStyle: { color: chartColors.green } },
      { name: '建议放电', type: 'bar', data: plan.map((item: any) => item.power < 0 ? item.power : 0), itemStyle: { color: chartColors.blue } },
      { name: '预测价格', type: 'line', yAxisIndex: 1, smooth: true, symbolSize: 4, data: plan.map((item: any) => item.price), lineStyle: { color: '#ff8a00', width: 2 } },
      { name: '参数化 SOC', type: 'line', yAxisIndex: 1, smooth: true, symbolSize: 4, data: plan.map((item: any) => item.derivedSoc), lineStyle: { color: chartColors.green, type: 'dashed', width: 2 } }
    ]
  };
  return (
    <section className="strategy-card storage-chart-card">
      <div className="strategy-card-head"><h2>储能充放电计划与 SOC 趋势</h2><Tooltip title="SOC 为策略配置参数化估算，不代表真实设备状态"><Tag color="warning">参数化 SOC</Tag></Tooltip></div>
      {plan.length ? <AppChart option={option} height={286} /> : <Empty description="暂无储能计划" />}
    </section>
  );
}

function StoragePlanTable({ rows, onSelect }: { rows: any[]; onSelect: (row: any) => void }) {
  const columns: ColumnsType<any> = [
    { title: '时间', dataIndex: 'time', width: 86 },
    { title: '建议动作', dataIndex: 'action', width: 82, render: (value) => <Tag color={value === '充电' ? 'success' : value === '放电' ? 'blue' : 'default'}>{value}</Tag> },
    { title: '功率(MW)', dataIndex: 'power', align: 'right' },
    { title: '预测价格', dataIndex: 'price', align: 'right', render: (value) => fmt(value, 3) },
    { title: 'SOC(%)', dataIndex: 'derivedSoc', align: 'right' },
    { title: '风险', dataIndex: 'risk', render: (value) => <Tag color={riskColor(value)}>{riskLabel(value)}</Tag> },
    { title: '执行建议', render: (_, row) => <Button type="link" size="small" onClick={() => onSelect(row)}>查看详情</Button> }
  ];
  return (
    <section className="strategy-card storage-plan-table">
      <div className="strategy-card-head"><h2>每小时动作建议</h2></div>
      <Table size="small" rowKey="key" columns={columns} dataSource={rows} pagination={false} scroll={{ y: 145, x: 700 }} />
    </section>
  );
}

function StorageDetail({ data, selected }: { data: any; selected: any }) {
  return (
    <section className="strategy-card storage-detail-panel">
      <div className="strategy-card-head"><h2>时段详情</h2></div>
      {selected ? (
        <>
          <h3>{selected.time} <Tag color={selected.action === '充电' ? 'success' : selected.action === '放电' ? 'blue' : 'default'}>{selected.action}</Tag></h3>
          <InsightBlock tone="blue" title="推荐动作"><p>建议功率：{selected.power} MW</p><p>{selected.advice}</p></InsightBlock>
          <InsightBlock tone="green" title="价格与风险"><p>预测价格：{fmt(selected.price, 3)} 元/kWh</p><p>风险概率：{selected.riskProbability == null ? '--' : `${fmt(selected.riskProbability * 100, 1)}%`}</p></InsightBlock>
          <InsightBlock tone="orange" title="执行条件"><p>SOC 范围：{data?.config?.soc_lower ?? '--'}% - {data?.config?.soc_upper ?? '--'}%</p><p>当前 SOC 未接入，图中仅为参数化估算。</p></InsightBlock>
          <InsightBlock tone="red" title="人工复核建议"><p>执行前核对实时价格、设备可用容量、效率、合同与并网约束。</p></InsightBlock>
          <Tooltip title="缺少 strategy_execution_items 状态持久化接口">
            <Button type="primary" block disabled>加入执行清单（待接入）</Button>
          </Tooltip>
          <Tooltip title="缺少真实执行反馈与状态持久化接口">
            <Button block disabled>标记为已执行（待接入）</Button>
          </Tooltip>
        </>
      ) : <Empty description="请选择时段" />}
    </section>
  );
}

export function ReviewWorkspace({
  data,
  selectedKey,
  onSelect,
  onAudit
}: {
  data: any;
  selectedKey?: string;
  onSelect: (row: any) => void;
  onAudit: (row: any, comment: string) => void;
}) {
  const rows = data?.reviewRows || [];
  const selected = rows.find((row: any) => row.key === selectedKey) || rows[0];
  const columns: ColumnsType<any> = [
    { title: '编号', dataIndex: 'id', width: 126 },
    { title: '复核原因', dataIndex: 'reason', ellipsis: true },
    { title: '策略建议', dataIndex: 'action', ellipsis: true },
    { title: '风险等级', dataIndex: 'risk', width: 92, render: (value) => <Tag color={riskColor(value)}>{riskLabel(value)}</Tag> },
    { title: '置信度', dataIndex: 'confidence', width: 82, render: (value) => value == null ? '--' : `${fmt(value, 1)}%` },
    { title: '提交时间', dataIndex: 'submittedAt', width: 142, render: (value) => String(value).slice(5, 16) },
    { title: '审核状态', dataIndex: 'status', width: 92, render: () => <Tooltip title="当前仅支持写入复核审计，不具备状态流转"><Tag color="warning">待复核</Tag></Tooltip> },
    { title: '操作', width: 105, render: (_, row) => <Space size={2}><Button type="link" size="small" onClick={() => onSelect(row)}>查看</Button><Button type="link" size="small" onClick={() => onSelect(row)}>记录复核</Button></Space> }
  ];
  return (
    <div className="review-workspace">
      <div className="review-list-column">
        <section className="strategy-card review-table-card">
          <div className="review-tabs"><strong>全部（{rows.length}）</strong><b>待复核（{rows.length}）</b><span>已处理（待接入）</span><span>紧急（{rows.filter((row: any) => row.risk === 'high').length}）</span></div>
          <Table size="small" rowKey="key" columns={columns} dataSource={rows} pagination={{ pageSize: 10, showSizeChanger: false }} scroll={{ y: 365, x: 980 }} onRow={(row) => ({ onClick: () => onSelect(row) })} rowClassName={(row) => selected?.key === row.key ? 'selected-review-row' : ''} />
        </section>
        <ReviewBottomSummary rows={rows} />
      </div>
      <ReviewDetail row={selected} onAudit={onAudit} />
    </div>
  );
}

function ReviewBottomSummary({ rows }: { rows: any[] }) {
  return (
    <div className="review-bottom-summary">
      <section className="strategy-card"><div className="strategy-card-head"><h2>复核队列摘要（实时）</h2></div>
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

function ReviewDetail({ row, onAudit }: { row: any; onAudit: (row: any, comment: string) => void }) {
  let comment = '';
  return (
    <section className="strategy-card review-detail-panel">
      <div className="strategy-card-head"><h2>复核详情</h2><Tag color="warning">仅审计记录</Tag></div>
      {row ? (
        <>
          <div className="review-detail-scroll">
            <InsightBlock tone="green" title="策略摘要"><p>编号：{row.id}</p><p>候选动作：{row.action}</p><p>目标时段：{row.period}</p></InsightBlock>
            <InsightBlock tone="orange" title="复核原因"><Tag color={riskColor(row.risk)}>{riskLabel(row.risk)}</Tag><p>{row.reason}</p></InsightBlock>
            <InsightBlock tone="red" title="AI 风险摘要"><p>{row.evidence?.explanation}</p><p>风险概率：{row.evidence?.riskProbability == null ? '--' : `${fmt(row.evidence.riskProbability * 100, 1)}%`}</p></InsightBlock>
            <div className="review-evidence-grid">
              <InsightBlock tone="blue" title="模型依据"><p>预测价格：{fmt(row.evidence?.predictedPrice, 3)}</p><p>预测负荷：{fmt(row.evidence?.forecastLoad, 0)}</p></InsightBlock>
              <InsightBlock tone="green" title="证据来源"><p>价格预测结果</p><p>负荷预测结果</p><p>策略与异常接口</p></InsightBlock>
            </div>
            <div className="review-related"><h3>相关时段数据</h3><p><span>时段</span><strong>{row.period}</strong></p><p><span>峰谷价差</span><strong>{fmt(row.evidence?.peakValleySpread)}</strong></p></div>
            <label className="review-comment">备注（选填）<Input.TextArea maxLength={200} showCount rows={3} placeholder="输入复核备注，将写入审计日志" onChange={(event) => { comment = event.target.value; }} /></label>
          </div>
          <div className="review-actions">
            <Tooltip title="通过/驳回状态机尚未接入"><Button type="primary" disabled>通过（待接入）</Button></Tooltip>
            <Tooltip title="通过/驳回状态机尚未接入"><Button danger disabled>驳回（待接入）</Button></Tooltip>
            <Button onClick={() => onAudit(row, comment)}>记录复核审计</Button>
          </div>
        </>
      ) : <Empty description="暂无待复核记录" />}
    </section>
  );
}

export const strategyActions = {
  refresh: <ReloadOutlined />,
  export: <DownloadOutlined />,
  config: <DatabaseOutlined />
};
