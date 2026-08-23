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
  const [header, container, styles] = await Promise.all([
    read('../src/components/common/PageHeader.tsx'),
    read('../src/layout/PageContainer.tsx'),
    read('../src/styles.css')
  ]);
  assert.match(header, /page-heading-unified/);
  assert.match(header, /data-max-rows="2"/);
  assert.match(header, /className="page-heading-actions" size=\{8\} wrap/);
  assert.doesNotMatch(header, /page-heading-subtitle/);
  assert.match(container, /page-header-area/);
  assert.match(container, /page-content-area/);
  assert.match(styles, /\.page-heading-unified\s*\{[\s\S]*?position:\s*sticky/);
  assert.match(styles, /\.page-heading-unified\s*\{[\s\S]*?z-index:\s*var\(--z-page-header\)/);
});

test('Phase 2 design tokens expose one global typography, spacing and semantic contract', async () => {
  const [variables, theme] = await Promise.all([
    read('../src/theme/variables.css'),
    read('../src/theme/themeConfig.ts')
  ]);
  assert.match(variables, /--font-family-base:\s*Inter, "PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC", system-ui, sans-serif/);
  for (const token of [
    '--font-page-title: 24px', '--font-section-title: 16px', '--font-card-title: 15px',
    '--font-body: 14px', '--font-table: 14px', '--font-control: 14px', '--font-helper: 13px',
    '--font-meta: 12px', '--font-ai-answer: 15px', '--font-code: 13px', '--font-chart: 12px',
    '--page-padding: var(--space-4)', '--card-gap: var(--space-3)', '--control-height: 36px',
    '--radius-card: 10px', '--color-success:', '--color-warning:', '--color-danger:', '--color-info:', '--color-neutral:'
  ]) assert.match(variables, new RegExp(token.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
  assert.match(theme, /export const globalFontStack/);
  assert.match(theme, /borderRadiusLG:\s*10/);
  assert.match(theme, /controlHeight:\s*36/);
  assert.match(theme, /zIndexPopupBase:\s*1000/);
});

test('Phase 2 AppShell fixes navigation and delegates scrolling to the main content area', async () => {
  const styles = await read('../src/styles.css');
  assert.match(styles, /\.app-shell > \.header-bar,[\s\S]*?position:\s*fixed !important/);
  assert.match(styles, /\.app-shell \.app-body > \.sidebar-shell\s*\{[\s\S]*?position:\s*fixed !important/);
  assert.match(styles, /\.app-shell \.main-shell > \.content-shell,[\s\S]*?overflow-y:\s*auto !important/);
  assert.match(styles, /\.page-container--headerless > \.page-content-area > :has\(> \.page-heading-unified\)[\s\S]*?overflow:\s*visible !important/);
  assert.match(styles, /padding-bottom:\s*calc\(var\(--page-padding\) \+ var\(--floating-ai-safe-zone\)\) !important/);
  assert.match(styles, /z-index:\s*var\(--z-floating-assistant\) !important/);
  assert.match(styles, /@media \(max-width: 1366px\), \(max-height: 768px\)/);
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

test('attachment uploads and polling preserve the session-scoped backend contract', async () => {
  const [api, drawer, page] = await Promise.all([
    read('../src/services/assistantApi.ts'),
    read('../src/features/globalAssistant/GlobalAssistantDrawer.tsx'),
    read('../src/pages/assistant/AssistantPage.tsx')
  ]);
  assert.match(api, /body\.append\('session_id', sessionId\)/);
  assert.match(api, /\?session_id=\$\{encodeURIComponent\(sessionId\)\}/);
  assert.match(drawer, /uploadAssistantAttachment\(file, uploadSessionId,/);
  assert.match(page, /uploadAssistantAttachment\(file, uploadSessionId,/);
});

test('premium is forwarded only after the user explicitly selects premium mode', async () => {
  const [page, api] = await Promise.all([
    read('../src/pages/assistant/AssistantPage.tsx'),
    read('../src/services/assistantApi.ts')
  ]);
  assert.match(page, /高阶模式（明确选择）/);
  assert.match(page, /premium_confirmed:\s*modelProvider === 'premium'/);
  assert.match(api, /premium_confirmed:\s*options\.premium_confirmed \?\? false/);
});

test('user cancellation has an explicit cancelled state and does not render a provider failure', async () => {
  const page = await read('../src/pages/assistant/AssistantPage.tsx');
  assert.match(page, /status\?: 'pending' \| 'streaming' \| 'done' \| 'cancelled' \| 'error'/);
  assert.match(page, /cancelled \? '已停止生成。' : content/);
  assert.match(page, /cancelled \? 'cancelled' : 'error'/);
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

test('local development identities load their real permission manifest instead of bypassing RBAC', async () => {
  const source = await read('../src/context/AuthContext.tsx');
  assert.match(source, /if \(!token && authRequired\)/);
  assert.doesNotMatch(source, /!authRequired \|\| resolveRouteAccess/);
  assert.doesNotMatch(source, /!authRequired \|\| resolveChildAccess/);
  assert.doesNotMatch(source, /!authRequired \|\| resolveActionAccess/);
});
