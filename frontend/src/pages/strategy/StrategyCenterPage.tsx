import { DownloadOutlined, ReloadOutlined, SettingOutlined } from '@ant-design/icons';
import { Button, Form, Input, InputNumber, Modal, Select, Switch, Tag, Tooltip, message } from 'antd';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '../../api';
import { PageHeader, type PageHeaderAction } from '../../components/common/PageHeader';
import { PageTabs } from '../../components/common/PageTabs';
import { PageDataState } from '../../components/common/States';
import {
  ReviewWorkspace,
  StorageWorkspace,
  StrategyMetricStrip,
  StrategyOverviewBottom,
  StrategyOverviewMain
} from '../../components/strategy/StrategyDesign';
import { getStrategyCenterData } from '../../services/strategyApi';
import { resolvePageDataMeta } from '../../services/viewState';
import { useAuth } from '../../context/AuthContext';
import type { PageProps } from '../../types/ui';

type ReviewFilters = {
  risk: string;
  status: string;
  search: string;
};

const DEFAULT_REVIEW_FILTERS: ReviewFilters = { risk: 'all', status: 'all', search: '' };
const REVIEW_FILTER_POLICY = 'preserve-within-session';

function displayTimestamp(value: unknown) {
  const text = String(value || '').trim();
  return text ? text.replace('T', ' ').slice(0, 19) : '--';
}

function staleReasonText(value?: string) {
  const labels: Record<string, string> = {
    forecast_window_expired: '预测适用窗口已结束',
    runtime_facts_older_than_6h: '运行事实已超过 6 小时',
    historical_run: '当前查看的是历史批次'
  };
  return labels[String(value || '')] || '数据超过有效时限';
}

const strategyTabs = [
  { key: 'strategy-high', label: '总览主页面' },
  { key: 'strategy-storage', label: '低价窗口与储能策略' },
  { key: 'strategy-review', label: '人工复核' }
];

function exportCsv(filename: string, rows: Record<string, unknown>[]) {
  if (!rows.length) {
    message.info('当前没有可导出的策略记录');
    return;
  }
  const keys = Object.keys(rows[0]);
  const csv = [keys, ...rows.map((row) => keys.map((key) => row[key]))]
    .map((line) => line.map((value) => `"${String(value ?? '').replace(/"/g, '""')}"`).join(','))
    .join('\n');
  const url = URL.createObjectURL(new Blob([`\uFEFF${csv}`], { type: 'text/csv;charset=utf-8' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = `${filename}_${Date.now()}.csv`;
  link.click();
  URL.revokeObjectURL(url);
}

export function StrategyCenterPage({ activeSubKey, onSubNavigate }: PageProps) {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [configOpen, setConfigOpen] = useState(false);
  const [configValues, setConfigValues] = useState<Record<string, any>>({});
  const [selectedStorage, setSelectedStorage] = useState<string>();
  const [selectedDevice, setSelectedDevice] = useState<string>();
  const [selectedReview, setSelectedReview] = useState<string>();
  const [reviewFilters, setReviewFilters] = useState<ReviewFilters>(DEFAULT_REVIEW_FILTERS);

  const [reviewHistory, setReviewHistory] = useState<any[]>([]);
  const { authRequired, hasPermission } = useAuth();
  const allowed = useCallback((permission: string) => !authRequired || hasPermission(permission), [authRequired, hasPermission]);
  const reviewPermissions = {
    canSubmit: allowed('strategy:submit'),
    canReview: allowed('strategy:review'),
    canPublish: allowed('strategy:publish')
  };
  const canConfigure = allowed('task:run');
  const mode = useMemo<'overview' | 'storage' | 'review'>(() => {
    if (activeSubKey === 'strategy-review') return 'review';
    if (activeSubKey === 'strategy-low' || activeSubKey === 'strategy-storage') return 'storage';
    return 'overview';
  }, [activeSubKey]);
  const activeTabKey = mode === 'overview' ? 'strategy-high' : mode === 'storage' ? 'strategy-storage' : 'strategy-review';
  const filteredReviewRows = useMemo(() => {
    const rows = data?.reviewRows || [];
    const needle = reviewFilters.search.trim().toLowerCase();
    return rows.filter((row: any) => {
      const riskMatches = reviewFilters.risk === 'all' || row.risk === reviewFilters.risk;
      const statusMatches = reviewFilters.status === 'all' || row.status === reviewFilters.status;
      const textMatches = !needle || [row.id, row.reason, row.action, row.assignee, row.runId, row.reportId]
        .some((value) => String(value || '').toLowerCase().includes(needle));
      return riskMatches && statusMatches && textMatches;
    });
  }, [data?.reviewRows, reviewFilters]);
  const reviewFiltersActive = reviewFilters.risk !== DEFAULT_REVIEW_FILTERS.risk
    || reviewFilters.status !== DEFAULT_REVIEW_FILTERS.status
    || Boolean(reviewFilters.search.trim());
  const handleStrategyTabChange = useCallback((key: string) => {
    // 产品规则：复核筛选仅在当前页面会话内保留，跨子页切换不隐式清空；刷新页面后恢复默认值。
    onSubNavigate(key);
  }, [onSubNavigate]);
  const resetReviewFilters = useCallback(() => {
    setReviewFilters(DEFAULT_REVIEW_FILTERS);
  }, []);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const result = await getStrategyCenterData();
      setData(result);
      setConfigValues(result.config || {});
      setSelectedDevice((current) => result.devices?.some((item: any) => item.device_id === current) ? current : result.devices?.[0]?.device_id);
      setSelectedStorage((current) => result.executionItems?.some((item: any) => item.key === current) ? current : result.executionItems?.[0]?.key);
      setSelectedReview((current) => result.reviewRows?.some((item: any) => item.key === current) ? current : result.reviewRows?.[0]?.key);
    } catch (error) {
      const reason = error instanceof Error ? error.message : '策略数据加载失败';
      setData({ available: false, empty: false, error: reason, partialErrors: [] });
      message.error(reason);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadReviewHistory = useCallback(async (strategyId?: string) => {
    if (!strategyId) {
      setReviewHistory([]);
      return;
    }
    try {
      const result = await api.strategyReviews(strategyId);
      setReviewHistory(Array.isArray(result?.items) ? result.items : []);
    } catch {
      setReviewHistory([]);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  useEffect(() => {
    const row = data?.reviewRows?.find((item: any) => item.key === selectedReview);
    if (row?.contentHash) loadReviewHistory(row.id);
    else setReviewHistory([]);
  }, [data, selectedReview, loadReviewHistory]);

  useEffect(() => {
    if (mode !== 'review') return;
    setSelectedReview((current) => (
      filteredReviewRows.some((item: any) => item.key === current)
        ? current
        : filteredReviewRows[0]?.key
    ));
  }, [filteredReviewRows, mode]);

  async function saveConfig() {
    try {
      await api.saveStrategyConfig(configValues);
      message.success('策略配置已保存');
      setConfigOpen(false);
      await loadData();
    } catch (error) {
      message.error(error instanceof Error ? error.message : '策略配置保存失败');
    }
  }

  async function handleReviewAction(row: any, action: string, comment: string) {
    if ((action === 'reject' || action === 'return') && !comment.trim()) {
      message.warning('驳回或退回必须填写复核意见');
      return;
    }
    try {
      const requestId = globalThis.crypto?.randomUUID?.() || `p5d-${Date.now()}`;
      await api.strategyAction(row.id, action, { request_id: requestId, review_comment: comment.trim() });
      message.success('策略状态与审计记录已同步更新');
      await loadData();
      await loadReviewHistory(row.id);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '策略状态流转失败');
    }
  }

  const viewMeta = useMemo(() => resolvePageDataMeta({
    loading,
    hasData: Boolean(data?.available && !data?.empty),
    empty: Boolean(data?.empty),
    error: data?.error,
    partialErrors: data?.partialErrors,
    source: data?.sourceType,
    generatedAt: data?.generatedAt,
    runId: data?.runId,
    modelVersion: data?.modelVersion,
    featureVersion: data?.featureVersion,
    isStale: data?.isStale,
    staleReason: data?.staleReason,
    queryScope: mode === 'review' ? '策略人工复核' : mode === 'storage' ? '储能运行与执行反馈' : '策略事实总览'
  }), [data, loading, mode]);
  const showContent = viewMeta.state === 'success' || viewMeta.state === 'stale';
  const headerActions = useMemo<PageHeaderAction[]>(() => {
    const actions: PageHeaderAction[] = [
      {
        key: 'refresh',
        label: '刷新',
        icon: <ReloadOutlined />,
        loading,
        onClick: loadData
      },
      {
        key: 'export',
        label: mode === 'review' ? '导出复核清单' : '导出策略',
        icon: <DownloadOutlined />,
        collapseAtNarrow: true,
        onClick: () => exportCsv(
          mode === 'review' ? 'strategy_review' : 'strategy',
          mode === 'review'
            ? filteredReviewRows
            : mode === 'storage'
              ? (data?.executionItems || []).filter((item: any) => !selectedDevice || item.device_id === selectedDevice)
              : (data?.hourlyPlan || [])
        )
      }
    ];
    if (mode === 'overview') {
      actions.push({
        key: 'config',
        label: '策略配置',
        icon: <SettingOutlined />,
        collapseAtNarrow: true,
        disabled: !canConfigure,
        disabledReason: '缺少 task:run 权限，不能修改运行时策略配置',
        onClick: () => setConfigOpen(true)
      });
    }
    if (mode === 'review') {
      actions.push(
        {
          key: 'batch-approve',
          label: '批量通过（暂不可用）',
          type: 'primary',
          collapseAtNarrow: true,
          disabled: true,
          disabledReason: '为保证逐条证据核验与审计追踪，暂不开放批量审核'
        },
        {
          key: 'batch-reject',
          label: '批量驳回（暂不可用）',
          danger: true,
          collapseAtNarrow: true,
          disabled: true,
          disabledReason: '为保证逐条填写驳回原因与审计追踪，暂不开放批量审核'
        }
      );
    }
    return actions;
  }, [canConfigure, data?.executionItems, data?.hourlyPlan, filteredReviewRows, loadData, loading, mode, selectedDevice]);
  const strategySubtitle = loading
    ? '正在核对策略、审核、预测有效期和运行反馈。'
    : !data?.available
      ? '当前策略事实不可用；页面不会生成默认策略、收益或执行状态。'
      : mode === 'overview'
    ? data?.strategyUsable
      ? '展示处于有效窗口且通过治理门禁的策略事实；执行前仍须人工复核。'
      : '展示可追溯的历史策略记录；当前记录已过期或未通过，不可作为当前策略。'
    : mode === 'storage'
      ? data?.isSimulated
        ? '展示模拟设备、模拟执行与测算收益；所有结果均不代表实际执行或结算。'
        : '展示设备运行、执行反馈与收益口径，支持只读复核。'
      : '承接高风险策略的人工审核与人机协同闭环，确保关键交易决策安全、合规、可追溯。';

  return (
    <div className={`strategy-design-page strategy-${mode}-page`}>
      <PageHeader
        title="策略中心"
        subtitle={strategySubtitle}
        navigation={<div className="strategy-page-tabs"><PageTabs items={strategyTabs} activeKey={activeTabKey} onChange={handleStrategyTabChange} /></div>}
        className="strategy-page-header"
        metadata={(
          <div className="strategy-header-metadata">
            <span><small>{mode === 'review' ? '复核日期' : '策略日期'}</small><strong>{data?.strategyDate || '--'}</strong></span>
            <span><small>策略版本</small><strong>{data?.strategyVersion || '--'}</strong></span>
            <span><small>模型版本</small><strong>{data?.modelVersion || '--'}</strong></span>
            <span className="strategy-meta-run">
              <small>run_id</small>
              <Tooltip title={data?.runId || '当前接口未提供 run_id'}><strong>{data?.runId || '--'}</strong></Tooltip>
            </span>
            <span className="strategy-meta-run">
              <small>事实批次</small>
              <Tooltip title={data?.runtimeBatchId || '当前无运行事实批次'}><strong>{data?.runtimeBatchId || '--'}</strong></Tooltip>
            </span>
            <span>
              <small>生成时间</small>
              <strong>{displayTimestamp(data?.generatedAt)}</strong>
            </span>
            <span>
              <small>业务事实</small>
              <Tag color={data?.isStale ? 'warning' : data?.isSimulated ? 'processing' : data?.sourceType === 'unavailable' ? 'default' : 'success'}>
                {data?.sourceLabel || '--'}
              </Tag>
            </span>
            <span><small>策略状态</small><strong>{data?.strategyStatusLabel || '--'}</strong></span>
            <span className="strategy-meta-run"><small>适用窗口</small><Tooltip title={`${data?.strategyValidFrom || '--'} 至 ${data?.strategyValidTo || '--'}`}><strong>{data?.strategyValidFrom && data?.strategyValidTo ? `${String(data.strategyValidFrom).slice(5, 16)} 至 ${String(data.strategyValidTo).slice(5, 16)}` : '--'}</strong></Tooltip></span>
            {data?.isStale && (
              <span className="strategy-meta-stale">
                <small>过期原因</small>
                <Tooltip title={data?.staleReason || '上游数据已过有效期'}>
                  <Tag color="warning">{staleReasonText(data?.staleReason)}</Tag>
                </Tooltip>
              </span>
            )}
          </div>
        )}
        filters={(
          <div
            className="strategy-header-filters"
            data-filter-policy={mode === 'review' ? REVIEW_FILTER_POLICY : 'page-scoped'}
          >
            <label>
              <span>区域</span>
              <Tooltip title={data?.region ? '接口返回区域，仅用于当前策略上下文' : '当前策略接口未提供区域字段，不能伪造筛选值'}>
                <Select
                  size="small"
                  disabled
                  value={data?.region || 'unavailable'}
                  options={[{ value: data?.region || 'unavailable', label: data?.region || '区域未提供' }]}
                />
              </Tooltip>
            </label>
            {mode === 'review' && (
              <>
                <label>
                  <span>风险等级</span>
                  <Select size="small" value={reviewFilters.risk} onChange={(risk) => setReviewFilters((current) => ({ ...current, risk }))} options={[{ value: 'all', label: '全部' }, { value: 'high', label: '高风险' }, { value: 'medium', label: '中风险' }, { value: 'low', label: '低风险' }]} />
                </label>
                <label>
                  <span>审核状态</span>
                  <Select size="small" value={reviewFilters.status} onChange={(status) => setReviewFilters((current) => ({ ...current, status }))} options={[{ value: 'all', label: '全部' }, { value: 'draft', label: '草稿' }, { value: 'pending_review', label: '待复核' }, { value: 'approved', label: '已通过' }, { value: 'rejected', label: '已驳回' }, { value: 'published', label: '已发布' }]} />
                </label>
                <Input size="small" allowClear value={reviewFilters.search} onChange={(event) => setReviewFilters((current) => ({ ...current, search: event.target.value }))} placeholder="搜索编号 / 原因 / 责任人" />
                <Button
                  className="strategy-filter-reset"
                  type="link"
                  size="small"
                  disabled={!reviewFiltersActive}
                  onClick={resetReviewFilters}
                >
                  清除筛选
                </Button>
              </>
            )}
            {mode === 'storage' && (
              <label>
                <span>执行对象</span>
                <Select
                  size="small"
                  value={selectedDevice}
                  placeholder="选择储能设备"
                  onChange={(deviceId) => {
                    setSelectedDevice(deviceId);
                    setSelectedStorage(data?.executionItems?.find((item: any) => item.device_id === deviceId)?.key);
                  }}
                  options={(data?.devices || []).map((item: any) => ({ value: item.device_id, label: item.device_name }))}
                />
              </label>
            )}
          </div>
        )}
        actions={headerActions}
      />
      <PageDataState meta={viewMeta} onRetry={loadData} mockFallback={false} />
      {showContent ? <StrategyMetricStrip data={data} mode={mode} /> : null}
      {showContent && mode === 'overview' && (
        <>
          <StrategyOverviewMain data={data} />
          <StrategyOverviewBottom data={data} />
        </>
      )}
      {showContent && mode === 'storage' && (
        <StorageWorkspace
          data={data}
          selectedKey={selectedStorage}
          selectedDeviceId={selectedDevice}
          onSelect={(row) => setSelectedStorage(row.key)}
          onDeviceChange={(deviceId) => {
            setSelectedDevice(deviceId);
            setSelectedStorage(data?.executionItems?.find((item: any) => item.device_id === deviceId)?.key);
          }}
        />
      )}
      {showContent && mode === 'review' && (
        <ReviewWorkspace
          data={data}
          selectedKey={selectedReview}
          onSelect={(row) => setSelectedReview(row.key)}
          onAction={handleReviewAction}
          permissions={reviewPermissions}
          reviewHistory={reviewHistory}
          rows={filteredReviewRows}
          totalRows={data?.reviewRows?.length || 0}
        />
      )}

      <Modal title="策略配置" open={configOpen} onCancel={() => setConfigOpen(false)} onOk={saveConfig} okText="保存配置" okButtonProps={{ disabled: !canConfigure }}>
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
    </div>
  );
}
