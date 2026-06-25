import { DownloadOutlined, ReloadOutlined, SettingOutlined } from '@ant-design/icons';
import { Button, Form, InputNumber, Modal, Switch, Tooltip, message } from 'antd';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '../../api';
import { DataStateBanner } from '../../components/common/States';
import {
  ReviewWorkspace,
  StorageWorkspace,
  StrategyContextBar,
  StrategyMetricStrip,
  StrategyOverviewBottom,
  StrategyOverviewMain,
  StrategyPageHeader
} from '../../components/strategy/StrategyDesign';
import { getStrategyCenterData } from '../../services/strategyApi';
import type { PageProps } from '../../types/ui';

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

export function StrategyCenterPage({ activeSubKey }: PageProps) {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [configOpen, setConfigOpen] = useState(false);
  const [configValues, setConfigValues] = useState<Record<string, any>>({});
  const [selectedStorage, setSelectedStorage] = useState<string>();
  const [selectedReview, setSelectedReview] = useState<string>();

  const mode = useMemo<'overview' | 'storage' | 'review'>(() => {
    if (activeSubKey === 'strategy-review') return 'review';
    if (activeSubKey === 'strategy-low' || activeSubKey === 'strategy-storage') return 'storage';
    return 'overview';
  }, [activeSubKey]);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const result = await getStrategyCenterData();
      setData(result);
      setConfigValues(result.config || {});
      setSelectedStorage((current) => current || result.hourlyPlan?.find((item: any) => item.action !== '观望')?.key);
      setSelectedReview((current) => current || result.reviewRows?.[0]?.key);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '策略数据加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

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

  async function saveAudit(row: any, comment: string) {
    try {
      await api.saveStrategyReview({
        id: row.id,
        period: row.period,
        risk_level: row.risk,
        decision: 'reviewed',
        review_comment: comment,
        evidence: row.evidence,
        status: 'audit_recorded'
      });
      message.success('复核内容已写入审计日志；当前未改变业务状态');
    } catch (error) {
      message.error(error instanceof Error ? error.message : '复核审计保存失败');
    }
  }

  const stateVisible = loading || data?.empty || Boolean(data?.partialErrors?.length);
  const commonActions = (
    <>
      <Button icon={<ReloadOutlined />} loading={loading} onClick={loadData}>刷新</Button>
      {mode !== 'review' && <Button icon={<DownloadOutlined />} onClick={() => exportCsv('strategy', data?.hourlyPlan || [])}>导出策略</Button>}
      {mode === 'overview' && <Button icon={<SettingOutlined />} onClick={() => setConfigOpen(true)}>策略配置</Button>}
      {mode === 'review' && (
        <>
          <Tooltip title="后端尚未提供批量状态流转接口"><Button type="primary" disabled>批量通过（待接入）</Button></Tooltip>
          <Tooltip title="后端尚未提供批量状态流转接口"><Button danger disabled>批量驳回（待接入）</Button></Tooltip>
        </>
      )}
    </>
  );

  return (
    <div className={`strategy-design-page strategy-${mode}-page`}>
      <StrategyPageHeader mode={mode} />
      <StrategyContextBar data={data} mode={mode} actions={commonActions} />
      {stateVisible && (
        <DataStateBanner
          scope="策略中心"
          loading={loading}
          empty={data?.empty}
          partialErrors={data?.partialErrors}
          mockFallback={false}
          onRetry={loadData}
        />
      )}
      <StrategyMetricStrip data={data} mode={mode} />
      {mode === 'overview' && (
        <>
          <StrategyOverviewMain data={data} />
          <StrategyOverviewBottom data={data} />
        </>
      )}
      {mode === 'storage' && (
        <StorageWorkspace
          data={data}
          selectedKey={selectedStorage}
          onSelect={(row) => setSelectedStorage(row.key)}
        />
      )}
      {mode === 'review' && (
        <ReviewWorkspace
          data={data}
          selectedKey={selectedReview}
          onSelect={(row) => setSelectedReview(row.key)}
          onAudit={saveAudit}
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
    </div>
  );
}
