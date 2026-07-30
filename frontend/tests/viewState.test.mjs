import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import ts from 'typescript';

const source = readFileSync(new URL('../src/services/viewState.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2020
  }
}).outputText;
const moduleBox = { exports: {} };
new Function('exports', 'module', compiled)(moduleBox.exports, moduleBox);
const { resolvePageDataMeta } = moduleBox.exports;

test('Loading -> Success', () => {
  assert.equal(resolvePageDataMeta({ loading: true, hasData: false }).state, 'loading');
  const success = resolvePageDataMeta({
    hasData: true,
    source: 'postgresql',
    runId: 'run-001',
    modelVersion: 'model-v1',
    featureVersion: 'features-v1'
  });
  assert.equal(success.state, 'success');
  assert.equal(success.runId, 'run-001');
});

test('Loading -> Empty', () => {
  assert.equal(resolvePageDataMeta({ loading: true }).state, 'loading');
  const empty = resolvePageDataMeta({
    empty: true,
    emptyReason: '当前日期无记录',
    queryScope: '2026-07-26'
  });
  assert.equal(empty.state, 'empty');
  assert.equal(empty.emptyReason, '当前日期无记录');
});

test('Loading -> Error', () => {
  assert.equal(resolvePageDataMeta({ loading: true }).state, 'loading');
  const error = resolvePageDataMeta({ error: { status: 500, code: 'UPSTREAM_FAILED', message: '上游失败' } });
  assert.equal(error.state, 'error');
  assert.equal(error.errorCode, 'UPSTREAM_FAILED');
  assert.equal(error.canRetry, true);
});

test('Error -> Retry -> Success', () => {
  const failed = resolvePageDataMeta({ error: new Error('网络异常') });
  assert.equal(failed.state, 'error');
  const retried = resolvePageDataMeta({ hasData: true, source: 'api_forecast_24h' });
  assert.equal(retried.state, 'success');
});

test('Success -> Stale preserves metadata', () => {
  const success = resolvePageDataMeta({ hasData: true, runId: 'run-002' });
  assert.equal(success.state, 'success');
  const stale = resolvePageDataMeta({
    loading: true,
    hasData: true,
    runId: success.runId,
    generatedAt: '2026-07-26T10:00:00Z'
  });
  assert.equal(stale.state, 'stale');
  assert.equal(stale.runId, 'run-002');
  assert.equal(stale.staleReason, 'refresh_in_progress');
});

test('401 -> Unauthorized', () => {
  const unauthorized = resolvePageDataMeta({
    error: { status: 401, code: 'TOKEN_EXPIRED', message: '登录已过期' }
  });
  assert.equal(unauthorized.state, 'unauthorized');
  assert.equal(unauthorized.errorCode, 'TOKEN_EXPIRED');
  assert.equal(unauthorized.canRetry, false);
});

test('403 -> Forbidden', () => {
  const forbidden = resolvePageDataMeta({
    error: { status: 403, code: 'PERMISSION_DENIED', message: '权限不足' }
  });
  assert.equal(forbidden.state, 'forbidden');
  assert.equal(forbidden.errorCode, 'PERMISSION_DENIED');
  assert.equal(forbidden.canRetry, false);
});
