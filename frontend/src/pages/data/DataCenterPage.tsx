import { DownloadOutlined, ReloadOutlined, SyncOutlined } from '@ant-design/icons';
import { Button, message } from 'antd';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '../../api';
import { DetailDrawer } from '../../components/actions/DetailDrawer';
import {
  CatalogPanel,
  DataContextBar,
  DataFlowPanel,
  DataHealthOverview,
  DataOverviewMetrics,
  DataPageHeader,
  ExceptionTable,
  OverviewSideRail,
  QualityMetrics,
  QualityMonitor,
  SourceStatusBar,
  SyncRecordsTable
} from '../../components/data/DataCenterDesign';
import { DataStateBanner } from '../../components/common/States';
import { getDataCenterData } from '../../services/dataApi';
import type { PageProps } from '../../types/ui';

function exportCsv(filename: string, rows: any[]) {
  if (!rows.length) {
    message.info('当前没有可导出的记录');
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

export function DataCenterPage({ activeSubKey, onSubNavigate }: PageProps) {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [search, setSearch] = useState('');
  const [selectedCatalog, setSelectedCatalog] = useState<any>(null);
  const [detail, setDetail] = useState<any>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const result = await getDataCenterData();
      setData(result);
      setSelectedCatalog((current: any) => current || result.catalog?.[0] || null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const qualityMode = activeSubKey === 'data-quality';
  const filteredCatalog = useMemo(() => {
    const rows = data?.catalog || [];
    const keyword = search.trim().toLowerCase();
    if (!keyword) return rows;
    return rows.filter((row: any) => [row.table_name, row.display_name, row.business_domain, row.source_system].some((value) => String(value || '').toLowerCase().includes(keyword)));
  }, [data, search]);

  const filteredImports = useMemo(() => {
    const rows = data?.imports || [];
    const keyword = search.trim().toLowerCase();
    if (!keyword) return rows;
    return rows.filter((row: any) => [row.name, row.type, row.status].some((value) => String(value || '').toLowerCase().includes(keyword)));
  }, [data, search]);

  async function syncData() {
    setSyncing(true);
    try {
      const result = await api.dataRefresh();
      message.success(result.task_id ? `同步任务已创建：${result.task_id}` : '同步任务已提交');
      await loadData();
    } catch (error) {
      message.error(error instanceof Error ? error.message : '同步任务提交失败');
    } finally {
      setSyncing(false);
    }
  }

  const actions = qualityMode ? (
    <>
      <Button icon={<ReloadOutlined />} onClick={loadData}>刷新</Button>
      <Button icon={<DownloadOutlined />} onClick={() => exportCsv('data_quality', data?.qualityItems || [])}>导出报告</Button>
      <Button type="primary" loading={syncing} icon={<SyncOutlined />} onClick={syncData}>质量巡检</Button>
    </>
  ) : (
    <>
      <Button icon={<ReloadOutlined />} onClick={loadData}>刷新总览</Button>
      <Button type="primary" loading={syncing} icon={<SyncOutlined />} onClick={syncData}>手动同步</Button>
      <Button icon={<DownloadOutlined />} onClick={() => exportCsv('data_overview', data?.freshnessItems || [])}>导出概览</Button>
    </>
  );

  const stateVisible = loading || data?.empty || Boolean(data?.partialErrors?.length);
  const exceptions = [...(data?.exceptions || []), ...(data?.freshnessProblems || [])];

  return (
    <div className={`data-design-page ${qualityMode ? 'quality-catalog-page' : 'data-overview-page'}`}>
      <DataPageHeader
        title={qualityMode ? '数据质量与数据目录' : '数据中心 / 数据总览'}
        subtitle={qualityMode ? '缺失率、重复率、新鲜度、校验通过率与数据目录可追溯管理。' : '数据接入、质量监控、目录管理、同步记录的一体化入口。'}
        controls={!qualityMode ? <DataContextBar qualityMode={false} search={search} onSearch={setSearch} actions={actions} /> : null}
      />
      {qualityMode ? <DataContextBar qualityMode search={search} onSearch={setSearch} actions={actions} /> : null}
      {stateVisible ? (
        <DataStateBanner
          scope="数据中心"
          loading={loading}
          empty={data?.empty}
          partialErrors={data?.partialErrors}
          mockFallback={false}
          onRetry={loadData}
        />
      ) : null}

      {!qualityMode ? (
        <>
          <DataOverviewMetrics data={data} loading={loading} />
          <div className="data-overview-main">
            <div className="data-overview-left">
              <DataFlowPanel data={data} onCatalog={() => onSubNavigate('data-quality')} />
              <SyncRecordsTable rows={filteredImports} onDetail={setDetail} />
            </div>
            <div className="data-overview-right">
              <DataHealthOverview data={data} />
              <OverviewSideRail data={data} onNavigate={onSubNavigate} />
            </div>
          </div>
        </>
      ) : (
        <>
          <QualityMetrics data={data} loading={loading} />
          <div className="data-quality-main">
            <div className="data-quality-left">
              <QualityMonitor data={data} />
              <div className="data-exception-card">
                <div className="data-card-heading"><h2>异常明细表</h2><span>{exceptions.length} 条</span></div>
                <ExceptionTable rows={exceptions} />
              </div>
            </div>
            <CatalogPanel rows={filteredCatalog} selected={selectedCatalog} onSelect={setSelectedCatalog} />
          </div>
          <SourceStatusBar rows={data?.freshnessItems || []} />
        </>
      )}

      <DetailDrawer title="同步任务详情" open={Boolean(detail)} data={detail} onClose={() => setDetail(null)} />
    </div>
  );
}
