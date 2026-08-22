import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const read = (path) => readFile(new URL(path, import.meta.url), 'utf8');

test('PermissionGate and PermissionRoute expose friendly full-page and section fallbacks', async () => {
  const [gate, route, app] = await Promise.all([
    read('../src/components/security/PermissionGate.tsx'),
    read('../src/components/security/PermissionRoute.tsx'),
    read('../src/app/App.tsx')
  ]);
  for (const symbol of ['PermissionGate', 'Can', 'ActionGuard', 'SectionUnavailable', 'FullPageForbidden']) {
    assert.match(gate, new RegExp(`export function ${symbol}`));
  }
  assert.match(route, /FullPageForbidden/);
  assert.match(app, /<PermissionRoute/);
});

test('StickyPageHeader is shared and remains below navigation and overlays', async () => {
  const [header, styles] = await Promise.all([
    read('../src/components/common/PageHeader.tsx'),
    read('../src/styles.css')
  ]);
  assert.match(header, /page-heading-unified/);
  assert.doesNotMatch(header, /page-heading-subtitle/);
  assert.match(styles, /\.page-heading-unified\s*\{[\s\S]*?position:\s*sticky/);
  assert.match(styles, /\.page-heading-unified\s*\{[\s\S]*?z-index:\s*8/);
});

test('AttachmentComposer covers select, drag/drop, clipboard and explicit browser fallback', async () => {
  const source = await read('../src/features/globalAssistant/AttachmentComposer.tsx');
  assert.match(source, /onDrop/);
  assert.match(source, /onPaste/);
  for (const extension of ['png', 'jpg', 'jpeg', 'webp', 'pdf', 'docx', 'txt', 'md', 'xlsx', 'csv']) {
    assert.match(source, new RegExp(`'${extension}'`));
  }
  assert.match(source, /浏览器无法直接读取该文件，请拖拽或选择文件/);
  assert.match(source, /uploading.*parsing.*ready.*failed/s);
});

test('GlobalAssistantDrawer is mounted globally and supports stop, collapse and full page navigation', async () => {
  const [drawer, layout] = await Promise.all([
    read('../src/features/globalAssistant/GlobalAssistantDrawer.tsx'),
    read('../src/layout/BasicLayout.tsx')
  ]);
  assert.match(layout, /<GlobalAssistantDrawer/);
  assert.match(drawer, /FloatButton/);
  assert.match(drawer, /controllerRef\.current\?\.abort/);
  assert.match(drawer, /收起/);
  assert.match(drawer, /onOpenFullAssistant/);
  assert.match(drawer, /includePageContext/);
});

test('AI answers render optional markdown, tables and citations without a forced template', async () => {
  const source = await read('../src/features/globalAssistant/DynamicAnswer.tsx');
  assert.match(source, /parseTable/);
  assert.match(source, /citations/);
  assert.match(source, /复制/);
  assert.doesNotMatch(source, /总结.*分析.*建议.*注意事项/s);
});

test('known unauthorized calls are capability-gated and raw 403 details are sanitized', async () => {
  const [forecast, report, task, api] = await Promise.all([
    read('../src/services/forecastApi.ts'),
    read('../src/services/reportApi.ts'),
    read('../src/services/taskApi.ts'),
    read('../src/api.ts')
  ]);
  assert.match(forecast, /capabilities\.canReadModel\s*\?/);
  assert.match(report, /capabilities\.canReview\s*\?/);
  assert.match(task, /capabilities\.canDiagnose\s*\?/);
  assert.match(api, /status === 403/);
  assert.doesNotMatch(api, /\[403\]/);
});
