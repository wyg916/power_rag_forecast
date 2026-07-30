import { api } from '../api';
import { errorMessage, withServiceState } from './serviceState';

function average(values: unknown[]) {
  const valid = values.filter((value) => value !== null && value !== undefined && value !== '').map(Number).filter(Number.isFinite);
  return valid.length ? valid.reduce((sum, value) => sum + value, 0) / valid.length : null;
}

export async function getDataCenterData(options: { syncPage?: number; syncPageSize?: number } = {}) {
  const syncPage = Math.max(1, Number(options.syncPage || 1));
  const syncPageSize = Math.max(1, Number(options.syncPageSize || 8));
  const partialErrors: string[] = [];
  const requestErrors: unknown[] = [];
  const safe = async <T>(label: string, loader: () => Promise<T>): Promise<T | null> => {
    try {
      return await loader();
    } catch (error) {
      requestErrors.push(error);
      partialErrors.push(`${label}: ${errorMessage(error)}`);
      return null;
    }
  };

  const [status, quality, tables, importExport, catalog, freshness] = await Promise.all([
    safe('dataStatus', api.dataStatus),
    safe('dataQuality', api.dataQuality),
    safe('databaseTables', api.databaseTables),
    safe('importExportRecords', () => api.importExportRecords(syncPage, syncPageSize)),
    safe('dataCatalog', () => api.dataCatalog(true)),
    safe('dataFreshness', api.dataFreshness)
  ]);

  const sources = Array.isArray(status?.sources) ? status.sources : [];
  const qualityItems = Array.isArray(quality?.items) ? quality.items : [];
  const exceptions = Array.isArray(quality?.exceptions) ? quality.exceptions : [];
  const alerts = Array.isArray(quality?.alerts) ? quality.alerts : [];
  const tableRows = Array.isArray(tables?.tables) ? tables.tables : [];
  const records = Array.isArray(importExport?.records) ? importExport.records : [];
  const catalogRows = Array.isArray(catalog?.datasets) ? catalog.datasets : [];
  const freshnessItems = Array.isArray(freshness?.items) ? freshness.items : [];
  const freshnessProblems = freshnessItems.filter((item: any) => item.status !== 'ok');
  const totalRows = freshnessItems.reduce((sum: number, item: any) => sum + Number(item.row_count || 0), 0);
  const missingRate = quality?.summary?.avg_missing_rate ?? average(qualityItems.map((item: any) => item.missing_rate));
  const duplicateRate = quality?.summary?.avg_duplicate_rate ?? average(qualityItems.map((item: any) => item.duplicate_rate));
  const passRate = quality?.summary?.avg_check_pass_rate ?? average(qualityItems.map((item: any) => item.check_pass_rate));
  const freshnessScore = quality?.summary?.avg_freshness_score ?? average(qualityItems.map((item: any) => item.freshness_score));
  const consistencyScore = quality?.summary?.avg_consistency_score ?? average(qualityItems.map((item: any) => item.consistency_score));
  const exceptionCount = Number(quality?.summary?.exception_count ?? exceptions.length);

  const imports = records.map((row: any, index: number) => ({
    key: row.record_id || row.task_id || String(index),
    type: row.type || row.task_kind || '--',
    name: row.name || row.task_name || row.record_id || '--',
    status: row.status || '--',
    runId: row.run_id || '--',
    processedRows: row.processed_rows ?? null,
    successRows: row.success_rows ?? null,
    failedRows: row.failed_rows ?? null,
    createdAt: row.created_at || '--',
    startedAt: row.started_at || row.created_at || '--',
    endedAt: row.ended_at || '--',
    duration: row.duration_seconds == null ? '--' : `${row.duration_seconds}s`,
    errorCode: row.error_code || '',
    error: row.error_message || '',
    statusReason: row.status_reason || '',
    dataSource: row.data_source || 'postgresql.task_runs'
  }));

  return withServiceState({
    available: Boolean(sources.length || catalogRows.length || tableRows.length),
    dataSource: quality?.data_source || importExport?.data_source || (tables?.available ? 'postgresql' : 'api_data'),
    sources,
    qualityItems,
    exceptions,
    tables: tableRows,
    catalog: catalogRows,
    freshnessItems,
    freshnessProblems,
    alerts,
    imports,
    syncPagination: importExport?.pagination || { page: syncPage, page_size: syncPageSize, total: imports.length },
    syncSummary: importExport?.summary || {},
    catalogVersion: catalog?.catalog_version || freshness?.catalog_version || '',
    checkedAt: freshness?.checked_at || '',
    generatedAt: quality?.generated_at || importExport?.generated_at || freshness?.checked_at || status?.generated_at || catalog?.generated_at || '',
    isStale: Boolean(quality?.is_stale || quality?.meta?.is_stale || freshness?.meta?.is_stale || status?.meta?.is_stale || catalog?.meta?.is_stale),
    staleReason: quality?.stale_reason || quality?.meta?.stale_reason || freshness?.meta?.stale_reason || status?.meta?.stale_reason || catalog?.meta?.stale_reason || '',
    summary: {
      sourceCount: Number(quality?.summary?.source_count ?? sources.length),
      checkedSourceCount: Number(quality?.summary?.checked_source_count ?? qualityItems.length),
      catalogCount: catalogRows.length,
      tableCount: tableRows.length,
      syncCount: Number(importExport?.summary?.total ?? importExport?.pagination?.total ?? imports.length),
      latestSyncAt: importExport?.summary?.latest_sync_at || '',
      latestSyncRunId: importExport?.summary?.latest_sync_run_id || '',
      latestSuccessAt: importExport?.summary?.latest_success_at || '',
      todayTaskCount: Number(importExport?.summary?.today_task_count ?? 0),
      todayProcessedRows: importExport?.summary?.today_processed_rows ?? null,
      exceptionCount,
      missingRate,
      duplicateRate,
      passRate,
      freshnessScore,
      consistencyScore,
      freshnessProblemCount: freshnessProblems.length,
      totalRows
    }
  }, {
    empty: !sources.length && !catalogRows.length && !tableRows.length,
    error: requestErrors.length && !sources.length && !catalogRows.length && !tableRows.length ? requestErrors[0] : undefined,
    mockFallback: false,
    partialErrors
  });
}
