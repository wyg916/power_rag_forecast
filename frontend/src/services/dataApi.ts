import { api } from '../api';
import { errorMessage, withServiceState } from './serviceState';

function average(values: unknown[]) {
  const valid = values.map(Number).filter(Number.isFinite);
  return valid.length ? valid.reduce((sum, value) => sum + value, 0) / valid.length : null;
}

export async function getDataCenterData() {
  const partialErrors: string[] = [];
  const safe = async <T>(label: string, loader: () => Promise<T>): Promise<T | null> => {
    try {
      return await loader();
    } catch (error) {
      partialErrors.push(`${label}: ${errorMessage(error)}`);
      return null;
    }
  };

  const [status, quality, tables, importExport, catalog, freshness] = await Promise.all([
    safe('dataStatus', api.dataStatus),
    safe('dataQuality', api.dataQuality),
    safe('databaseTables', api.databaseTables),
    safe('importExportRecords', api.importExportRecords),
    safe('dataCatalog', () => api.dataCatalog(true)),
    safe('dataFreshness', api.dataFreshness)
  ]);

  const sources = Array.isArray(status?.sources) ? status.sources : [];
  const qualityItems = Array.isArray(quality?.items) ? quality.items : [];
  const exceptions = Array.isArray(quality?.exceptions) ? quality.exceptions : [];
  const tableRows = Array.isArray(tables?.tables) ? tables.tables : [];
  const records = Array.isArray(importExport?.records) ? importExport.records : [];
  const catalogRows = Array.isArray(catalog?.datasets) ? catalog.datasets : [];
  const freshnessItems = Array.isArray(freshness?.items) ? freshness.items : [];
  const freshnessProblems = freshnessItems.filter((item: any) => item.status !== 'ok');
  const totalRows = freshnessItems.reduce((sum: number, item: any) => sum + Number(item.row_count || 0), 0);
  const missingRate = Number(quality?.summary?.avg_missing_rate || 0);
  const duplicateRate = average(qualityItems.map((item: any) => item.duplicate_rate)) ?? 0;
  const passRate = Number(quality?.summary?.avg_check_pass_rate || 0);
  const freshnessScore = average(qualityItems.map((item: any) => item.freshness_score));
  const exceptionCount = Number(quality?.summary?.exception_count ?? exceptions.length);

  const imports = records.map((row: any, index: number) => ({
    key: row.record_id || row.task_id || String(index),
    type: row.type || row.task_kind || '--',
    name: row.name || row.task_name || row.record_id || '--',
    status: row.status || '--',
    rows: Number(row.rows || row.row_count || 0),
    startedAt: row.started_at || row.created_at || '--',
    duration: row.duration_seconds == null ? '--' : `${row.duration_seconds}s`,
    error: row.error_message || ''
  }));

  return withServiceState({
    available: Boolean(sources.length || catalogRows.length || tableRows.length),
    dataSource: tables?.available ? 'postgresql' : 'api_data',
    sources,
    qualityItems,
    exceptions,
    tables: tableRows,
    catalog: catalogRows,
    freshnessItems,
    freshnessProblems,
    imports,
    catalogVersion: catalog?.catalog_version || freshness?.catalog_version || '',
    checkedAt: freshness?.checked_at || '',
    summary: {
      sourceCount: Number(quality?.summary?.source_count || sources.length),
      catalogCount: catalogRows.length,
      tableCount: tableRows.length,
      syncCount: imports.length,
      exceptionCount,
      missingRate,
      duplicateRate,
      passRate,
      freshnessScore,
      freshnessProblemCount: freshnessProblems.length,
      totalRows
    }
  }, {
    empty: !sources.length && !catalogRows.length && !tableRows.length,
    mockFallback: false,
    partialErrors
  });
}
