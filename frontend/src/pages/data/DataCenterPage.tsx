import { DownloadOutlined, ReloadOutlined, SyncOutlined } from '@ant-design/icons';
import { App } from 'antd';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '../../api';
import { DetailDrawer } from '../../components/actions/DetailDrawer';
import {
  CatalogPanel,
  DataContextBar,
  DataFlowPanel,
  DataHealthOverview,
  DataOverviewMetrics,
  ExceptionTable,
  OverviewQuickActions,
  OverviewSideRail,
  QualityMetrics,
  QualityMonitor,
  SourceStatusBar,
  SyncRecordsTable
} from '../../components/data/DataCenterDesign';
import { PageHeader } from '../../components/common/PageHeader';
import type { PageHeaderAction } from '../../components/common/PageHeader';
import { PageDataState } from '../../components/common/States';
import { useAuth } from '../../context/AuthContext';
import { getDataCenterData } from '../../services/dataApi';
import { resolvePageDataMeta } from '../../services/viewState';
import type { PageProps } from '../../types/ui';
import './data-center-workspace.css';

const developmentRole = String(import.meta.env.VITE_DEV_ROLE || 'developer').toLowerCase();
const developmentCanSync = ['admin', 'analyst', 'operator'].includes(developmentRole);
const developmentCanExport = ['admin', 'analyst', 'operator', 'developer'].includes(developmentRole);

function exportCsv(filename: string, rows: any[]) {
  if (!rows.length) {
    return false;
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
  return true;
}

function downloadBlob(filename: string, blob: Blob) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

export function DataCenterPage({ activeSubKey, onSubNavigate }: PageProps) {
  const { message } = App.useApp();
  const syncPageSize = 7;
  const tablePageSize = 10;
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [requestError, setRequestError] = useState<unknown>(null);
  const [lastUpdatedAt, setLastUpdatedAt] = useState('');
  const [syncing, setSyncing] = useState(false);
  const [syncPage, setSyncPage] = useState(1);
  const [search, setSearch] = useState('');
  const [domainFilter, setDomainFilter] = useState('all');
  const [objectTypeFilter, setObjectTypeFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');
  const [taskTypeFilter, setTaskTypeFilter] = useState('all');
  const [selectedCatalog, setSelectedCatalog] = useState<any>(null);
  const [tablePreview, setTablePreview] = useState<any>(null);
  const [tablePreviewLoading, setTablePreviewLoading] = useState(false);
  const [tablePreviewError, setTablePreviewError] = useState<unknown>(null);
  const [tablePage, setTablePage] = useState(1);
  const [tableSearch, setTableSearch] = useState('');
  const [tableSearchDraft, setTableSearchDraft] = useState('');
  const [tableExporting, setTableExporting] = useState(false);
  const [detail, setDetail] = useState<any>(null);
  const { authRequired, hasPermission } = useAuth();
  const canSync = authRequired ? hasPermission('data:sync') : developmentCanSync;
  const canExport = authRequired ? hasPermission('data:export') : developmentCanExport;
  const canManageSettings = !authRequired || hasPermission('settings:read');
  const qualityMode = activeSubKey === 'data-quality';

  const loadData = useCallback(async () => {
    setLoading(true);
    setRequestError(null);
    try {
      const result = await getDataCenterData({ syncPage, syncPageSize });
      setData(result);
      setSelectedCatalog((current: any) => current || result.catalog?.[0] || null);
      setLastUpdatedAt(new Date().toISOString());
    } catch (error) {
      setRequestError(error);
    } finally {
      setLoading(false);
    }
  }, [syncPage]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  useEffect(() => {
    setSearch('');
    setDomainFilter('all');
    setObjectTypeFilter('all');
    setStatusFilter('all');
    setTaskTypeFilter('all');
  }, [qualityMode]);

  const loadTablePreview = useCallback(async () => {
    const datasetId = selectedCatalog?.dataset_id;
    if (!qualityMode || !datasetId) {
      if (qualityMode && !datasetId) {
        setTablePreview(null);
        setTablePreviewError(null);
        setTablePreviewLoading(false);
      }
      return;
    }
    if (selectedCatalog?.runtime?.exists === false) {
      setTablePreview({
        available: false,
        dataset_id: datasetId,
        records: [],
        columns: [],
        pagination: { page: 1, page_size: tablePageSize, total: 0 },
        message: '当前注册数据集暂不可用。'
      });
      setTablePreviewError(null);
      setTablePreviewLoading(false);
      return;
    }
    setTablePreviewLoading(true);
    setTablePreviewError(null);
    try {
      setTablePreview(await api.datasetRows(datasetId, {
        page: tablePage,
        pageSize: tablePageSize,
        search: tableSearch
      }));
    } catch (error) {
      setTablePreviewError(error);
    } finally {
      setTablePreviewLoading(false);
    }
  }, [qualityMode, selectedCatalog?.runtime?.exists, selectedCatalog?.dataset_id, tablePage, tableSearch]);

  useEffect(() => {
    loadTablePreview();
  }, [loadTablePreview]);

  function selectCatalog(row: any) {
    setSelectedCatalog(row);
    setTablePage(1);
    setTableSearch('');
    setTableSearchDraft('');
  }

  async function exportSelectedTable() {
    const datasetId = selectedCatalog?.dataset_id;
    if (!datasetId || !canExport) return;
    setTableExporting(true);
    try {
      const blob = await api.exportDataset(datasetId, tableSearch);
      downloadBlob(`${datasetId}_${new Date().toISOString().slice(0, 10)}.csv`, blob);
      message.success(`已导出 ${selectedCatalog?.display_name || datasetId}${tableSearch ? `（筛选：${tableSearch}）` : ''}`);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '数据集导出失败');
    } finally {
      setTableExporting(false);
    }
  }

  const enrichedCatalog = useMemo(() => {
    const qualityById = new Map((data?.qualityItems || []).map((row: any) => [row.dataset_id, row]));
    const freshnessById = new Map((data?.freshnessItems || []).map((row: any) => [row.dataset_id, row]));
    return (data?.catalog || []).map((row: any) => {
      const quality = qualityById.get(row.dataset_id) as any;
      const freshness = freshnessById.get(row.dataset_id) as any;
      return {
        ...row,
        quality,
        freshness,
        recordCount: freshness?.row_count ?? quality?.row_count ?? null,
        businessTime: freshness?.latest_time ?? quality?.latest_time ?? null
      };
    });
  }, [data]);

  const filteredCatalog = useMemo(() => {
    const rows = enrichedCatalog;
    const keyword = search.trim().toLowerCase();
    return rows.filter((row: any) => {
      const keywordMatched = !keyword || [row.dataset_id, row.display_name, row.business_domain, row.description]
        .some((value) => String(value || '').toLowerCase().includes(keyword));
      const domainMatched = domainFilter === 'all' || String(row.business_domain || '') === domainFilter;
      const typeMatched = objectTypeFilter === 'all' || String(row.object_type || '') === objectTypeFilter;
      const rowStatus = row.runtime?.exists === false ? 'unavailable' : 'available';
      const statusMatched = statusFilter === 'all' || rowStatus === statusFilter;
      return keywordMatched && domainMatched && typeMatched && statusMatched;
    });
  }, [domainFilter, enrichedCatalog, objectTypeFilter, search, statusFilter]);

  useEffect(() => {
    if (!qualityMode) return;
    setSelectedCatalog((current: any) => {
      if (!filteredCatalog.length) return null;
      if (current) {
        const refreshed = filteredCatalog.find((row: any) => row.dataset_id === current.dataset_id);
        if (refreshed) return refreshed;
      }
      return filteredCatalog[0];
    });
  }, [filteredCatalog, qualityMode]);

  const filteredImports = useMemo(() => {
    const rows = data?.imports || [];
    const keyword = search.trim().toLowerCase();
    return rows.filter((row: any) => {
      const keywordMatched = !keyword || [row.name, row.type, row.status, row.runId]
        .some((value) => String(value || '').toLowerCase().includes(keyword));
      const typeMatched = taskTypeFilter === 'all' || String(row.type || '') === taskTypeFilter;
      const statusMatched = statusFilter === 'all' || String(row.status || '') === statusFilter;
      return keywordMatched && typeMatched && statusMatched;
    });
  }, [data, search, statusFilter, taskTypeFilter]);

  const filterOptions = useMemo(() => {
    const unique = (values: unknown[]) => Array.from(new Set(values.map((value) => String(value || '').trim()).filter(Boolean))).sort();
    return {
      domains: unique(enrichedCatalog.map((row: any) => row.business_domain)),
      objectTypes: unique(enrichedCatalog.map((row: any) => row.object_type)),
      catalogStatuses: enrichedCatalog.length ? ['available', 'unavailable'] : [],
      taskTypes: unique((data?.imports || []).map((row: any) => row.type)),
      taskStatuses: unique((data?.imports || []).map((row: any) => row.status))
    };
  }, [data, enrichedCatalog]);

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

  const exportRows = qualityMode ? data?.qualityItems || [] : data?.freshnessItems || [];
  const exportCurrentView = useCallback(() => {
    if (!canExport) {
      message.warning('需要 data:export 权限');
      return;
    }
    if (!exportCsv(qualityMode ? 'data_quality' : 'data_overview', exportRows)) {
      message.info('当前没有可导出的记录');
      return;
    }
    message.success(qualityMode ? '质量报告已导出' : '数据概览已导出');
  }, [canExport, exportRows, message, qualityMode]);

  const actions = useMemo<PageHeaderAction[]>(() => [
    {
      key: 'refresh',
      label: qualityMode ? '刷新质量' : '刷新总览',
      icon: <ReloadOutlined />,
      loading,
      onClick: loadData
    },
    {
      key: 'sync',
      label: '手动同步',
      icon: <SyncOutlined />,
      type: 'primary',
      loading: syncing,
      hidden: !canSync,
      onClick: syncData
    },
    {
      key: 'export',
      label: qualityMode ? '导出质量报告' : '导出概览',
      icon: <DownloadOutlined />,
      collapseAtNarrow: true,
      hidden: !canExport,
      disabled: !exportRows.length,
      disabledReason: !exportRows.length ? '当前没有可导出的接口记录' : undefined,
      onClick: exportCurrentView
    }
  ], [canExport, canSync, exportCurrentView, exportRows, loading, loadData, qualityMode, syncing]);

  const viewMeta = useMemo(() => resolvePageDataMeta({
    loading,
    hasData: Boolean(data?.available && !data?.empty),
    empty: Boolean(data?.empty),
    error: requestError || data?.error,
    partialErrors: data?.partialErrors,
    source: data?.dataSource,
    generatedAt: data?.generatedAt || data?.checkedAt,
    updatedAt: lastUpdatedAt,
    isStale: Boolean(data?.isStale),
    staleReason: data?.staleReason,
    emptyReason: '所选页面与搜索条件下，接口未返回可用接入项、目录或数据库表记录。',
    queryScope: `${qualityMode ? '数据质量 / 数据目录' : '数据总览'}${search ? `；关键词：${search}` : '；全部记录'}`
  }), [data, lastUpdatedAt, loading, qualityMode, requestError, search]);
  const showContent = viewMeta.state === 'success' || viewMeta.state === 'stale';
  const exceptions = data?.exceptions || [];
  const detailForDisplay = useMemo(() => {
    if (!detail) return null;
    const hiddenTraceKeys = new Set([
      'alertId', 'source', 'dataSource', 'data_source', 'sourceType', 'source_type',
      'isSimulated', 'is_simulated', 'generationMode', 'generation_mode',
      'runId', 'run_id', 'modelVersion', 'model_version', 'featureVersion', 'feature_version',
      'generatedAt', 'generated_at', 'updatedAt', 'updated_at', 'predictionDate', 'prediction_date',
      'region', 'inferenceModel', 'inference_model', 'applicableWindow', 'applicable_window',
      'batchStatus', 'batch_status', 'staleReason', 'stale_reason', 'statusReason', 'status_reason'
    ]);
    return Object.fromEntries(Object.entries(detail).filter(([key]) => !hiddenTraceKeys.has(key)));
  }, [detail]);

  return (
    <div className={`data-design-page ${qualityMode ? 'quality-catalog-page' : 'data-overview-page'}`}>
      <PageHeader
        className="data-page-header"
        title={qualityMode ? '数据质量与数据目录' : '数据中心'}
        subtitle={qualityMode ? '缺失率、重复率、新鲜度、校验通过率与数据目录可追溯管理。' : '数据接入、质量监控、目录管理、同步记录的一体化入口。'}
        filters={(
          <DataContextBar
            qualityMode={qualityMode}
            search={search}
            onSearch={setSearch}
            domains={filterOptions.domains}
            domain={domainFilter}
            onDomainChange={setDomainFilter}
            objectTypes={filterOptions.objectTypes}
            objectType={objectTypeFilter}
            onObjectTypeChange={setObjectTypeFilter}
            statuses={qualityMode ? filterOptions.catalogStatuses : filterOptions.taskStatuses}
            status={statusFilter}
            onStatusChange={setStatusFilter}
            taskTypes={filterOptions.taskTypes}
            taskType={taskTypeFilter}
            onTaskTypeChange={setTaskTypeFilter}
            onReset={() => {
              setSearch('');
              setDomainFilter('all');
              setObjectTypeFilter('all');
              setStatusFilter('all');
              setTaskTypeFilter('all');
            }}
          />
        )}
        actions={actions}
      />
      {!showContent ? <PageDataState meta={viewMeta} onRetry={loadData} /> : null}

      {showContent && !qualityMode ? (
        <>
          <div className="data-overview-top">
            <DataOverviewMetrics data={data} loading={loading} />
            <OverviewQuickActions
              onDataAccess={syncData}
              onCatalog={() => onSubNavigate('data-quality')}
              onQuality={() => onSubNavigate('data-quality')}
              onExport={exportCurrentView}
              onAlerts={() => onSubNavigate('data-quality')}
              onSyncRecords={() => document.querySelector('.data-sync-table')?.scrollIntoView({ behavior: 'smooth', block: 'center' })}
              onPermissions={() => { window.location.hash = '/settings/settings-user'; }}
              onSettings={() => { window.location.hash = '/settings/settings-api'; }}
              syncing={syncing}
              canSync={canSync}
              canExport={canExport && Boolean(exportRows.length)}
              canManageSettings={canManageSettings}
            />
          </div>
          <div className="data-overview-workspace">
            <div className="data-overview-left">
              <DataFlowPanel data={data} onCatalog={() => onSubNavigate('data-quality')} />
              <SyncRecordsTable
                rows={filteredImports}
                total={Number(data?.syncPagination?.total || 0)}
                page={Number(data?.syncPagination?.page || syncPage)}
                pageSize={Number(data?.syncPagination?.page_size || syncPageSize)}
                loading={loading}
                onPageChange={setSyncPage}
                onDetail={setDetail}
              />
            </div>
            <div className="data-overview-right">
              <DataHealthOverview data={data} />
              <OverviewSideRail data={data} onDetail={setDetail} />
            </div>
          </div>
        </>
      ) : null}
      {showContent && qualityMode ? (
        <>
          <QualityMetrics data={data} loading={loading} />
          <div className="data-quality-main">
            <div className="data-quality-left">
              <QualityMonitor data={data} />
              <div className="data-exception-card">
                <div className="data-card-heading"><h2>异常明细表</h2><span>{exceptions.length} 条</span></div>
                <ExceptionTable rows={exceptions} loading={loading} onRefresh={loadData} onDetail={setDetail} />
              </div>
            </div>
            <CatalogPanel
              rows={filteredCatalog}
              selected={selectedCatalog}
              onSelect={selectCatalog}
              preview={tablePreview}
              previewLoading={tablePreviewLoading}
              previewError={tablePreviewError}
              previewPage={tablePage}
              previewPageSize={tablePageSize}
              previewSearch={tableSearchDraft}
              exporting={tableExporting}
              canExport={canExport}
              onManage={() => { window.location.hash = '/settings/settings-api'; }}
              onPreviewPageChange={setTablePage}
              onPreviewSearchDraft={setTableSearchDraft}
              onPreviewSearch={(value) => {
                setTableSearch(value.trim());
                setTablePage(1);
              }}
              onPreviewRetry={loadTablePreview}
              onExport={exportSelectedTable}
            />
          </div>
          <SourceStatusBar
            rows={data?.qualityItems || []}
            onAllSources={() => {
              setSearch('');
              setDomainFilter('all');
              setObjectTypeFilter('all');
              setStatusFilter('all');
            }}
          />
        </>
      ) : null}

      <DetailDrawer
        title={qualityMode ? '数据质量异常详情' : '同步任务详情'}
        open={Boolean(detail)}
        data={detailForDisplay}
        onClose={() => setDetail(null)}
      />
    </div>
  );
}
