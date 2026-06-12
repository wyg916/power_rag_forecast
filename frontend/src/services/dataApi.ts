import { dataMock } from '../mock/dataMock';
import { api } from '../api';
import { mockFallback, withServiceState } from './serviceState';

export async function getDataCenterData() {
  try {
    const partialErrors: string[] = [];
    const [status, quality, tables, importExport] = await Promise.all([
      api.dataStatus(),
      api.dataQuality().catch((error) => {
        partialErrors.push(error instanceof Error ? error.message : String(error));
        return null;
      }),
      api.databaseTables().catch((error) => {
        partialErrors.push(error instanceof Error ? error.message : String(error));
        return null;
      }),
      api.importExportRecords().catch((error) => {
        partialErrors.push(error instanceof Error ? error.message : String(error));
        return null;
      })
    ]);
    const sources = Array.isArray(status?.sources) ? status.sources : [];
    const qualityItems = Array.isArray(quality?.items) ? quality.items : [];
    const tableRows = Array.isArray(tables?.tables) ? tables.tables : [];
    const records = Array.isArray(importExport?.records) ? importExport.records : [];
    const missingRate = Number(quality?.summary?.avg_missing_rate || 0);
    const passRate = Number(quality?.summary?.avg_check_pass_rate || 100);
    const exceptionCount = Number(quality?.summary?.exception_count || 0);
    return withServiceState({
      ...dataMock,
      dataSource: tables?.available ? 'postgresql' : 'file_fallback',
      metrics: [
        { ...dataMock.metrics[0], value: sources.length || tableRows.length, note: '来自数据源状态' },
        { ...dataMock.metrics[1], value: records.length, note: `异常 ${exceptionCount}` },
        { ...dataMock.metrics[2], value: exceptionCount },
        { ...dataMock.metrics[3], value: passRate.toFixed(2), unit: '%' }
      ],
      flow: sources.length
        ? sources.map((item: any) => [
            item.name || '--',
            item.source || item.internal_file || 'file_fallback',
            String(item.latest_time || item.updated_at || '--').slice(11, 19) || '--',
            item.status || '--'
          ])
        : dataMock.flow,
      qualityCharts: [
        { title: '缺失率', value: `${missingRate.toFixed(2)}%`, data: qualityItems.map((item: any) => Number(item.missing_rate || 0)).slice(0, 10) },
        { title: '重复率', value: '0.00%', data: qualityItems.map(() => 0).slice(0, 10) },
        { title: '数据新鲜度', value: `${Math.round(qualityItems.reduce((sum: number, item: any) => sum + Number(item.freshness_score || 0), 0) / Math.max(qualityItems.length, 1))}%`, data: qualityItems.map((item: any) => Number(item.freshness_score || 0)).slice(0, 10) },
        { title: '校验通过率', value: `${passRate.toFixed(2)}%`, data: qualityItems.map((item: any) => Number(item.check_pass_rate || 0)).slice(0, 10) }
      ],
      qualityItems,
      exceptions: quality?.exceptions || [],
      tables: tableRows.length
        ? tableRows.map((row: any) => [
            row.table_name,
            row.sample_columns || '--',
            tables.available ? 'postgresql' : 'file_fallback',
            row.primary_key || '--',
            row.rows ?? '--',
            row.columns ?? '--'
          ])
        : dataMock.tables,
      rawTables: tableRows,
      imports: records.length
        ? records.map((row: any) => [
            row.type || '--',
            row.name || row.record_id || '--',
            row.status || '--',
            row.rows || '--',
            row.started_at || '--',
            row.duration_seconds || '--',
            row.error_message || ''
          ])
        : dataMock.imports,
      rawImportExportRecords: records
    }, {
      empty: !sources.length && !tableRows.length && !records.length,
      mockFallback: !sources.length && !tableRows.length,
      fallbackReason: !sources.length && !tableRows.length ? '数据状态和数据库表接口未返回真实记录，数据中心展示本地兜底结构。' : undefined,
      partialErrors
    });
  } catch (error) {
    return mockFallback(dataMock, error, '数据中心真实接口请求失败，已切换到本地兜底数据。');
  }
}
