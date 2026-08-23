import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const read = (path) => readFile(new URL(path, import.meta.url), 'utf8');

test('header tabs and toolbar preserve callback contracts and use one density scale', async () => {
  const [header, tabs, filter, styles, variables] = await Promise.all([
    read('../src/components/common/PageHeader.tsx'),
    read('../src/components/common/PageTabs.tsx'),
    read('../src/components/common/FilterBar.tsx'),
    read('../src/styles.css'),
    read('../src/theme/variables.css')
  ]);
  assert.match(header, /action\.onClick/);
  assert.match(tabs, /onChange=\{onChange\}/);
  assert.match(filter, /onClick=\{onReset\}/);
  assert.doesNotMatch(header, /\.sort\(|\.splice\(/);
  assert.match(styles, /\.page-toolbar\s*\{[\s\S]*?flex-wrap:\s*wrap[\s\S]*?gap:\s*var\(--button-group-gap\)[\s\S]*?margin-top:\s*0/);
  assert.doesNotMatch(styles, /\.page-toolbar\s*\{[\s\S]*?margin-top:\s*-48px/);
  assert.doesNotMatch(styles, /\.page-toolbar\s*\{[\s\S]*?pointer-events:\s*none/);
  assert.match(styles, /\.page-tabs \.ant-tabs-tab\s*\{[\s\S]*?min-height:\s*var\(--control-height\)/);
  assert.match(variables, /--control-height:\s*36px/);
});

test('cards and metric statuses use natural flow without hidden text clipping', async () => {
  const [section, metric, status, styles] = await Promise.all([
    read('../src/components/cards/SectionCard.tsx'),
    read('../src/components/cards/MetricCard.tsx'),
    read('../src/components/status/StatusTag.tsx'),
    read('../src/styles.css')
  ]);
  assert.match(section, /section-card-body-content/);
  assert.match(section, /error \? <ErrorState[\s\S]*?loading \? <LoadingBlock[\s\S]*?empty \? <EmptyState/);
  assert.match(section, /style=\{height \? \{ height \} : undefined\}/);
  assert.match(section, /style=\{minHeight \? \{ minHeight \} : undefined\}/);
  assert.match(metric, /metric-status/);
  assert.match(status, /status-tag status-tag-\$\{status\}/);
  assert.match(styles, /\.section-card\s*\{[\s\S]*?overflow:\s*visible/);
  assert.match(styles, /\.section-card \.ant-card-head-title\s*\{[\s\S]*?font-weight:\s*600[\s\S]*?line-height:\s*var\(--line-height-card-title\)/);
  assert.match(styles, /\.metric-status\s*\{[\s\S]*?font-size:\s*var\(--font-size-meta\)/);
  assert.match(styles, /\.metric-value-text\s*\{[\s\S]*?white-space:\s*normal/);
});

test('DataTable retains caller props and confines horizontal scrolling to the shared table', async () => {
  const [table, styles] = await Promise.all([
    read('../src/components/cards/TableCard.tsx'),
    read('../src/styles.css')
  ]);
  assert.match(table, /\.\.\.tableProps/);
  assert.match(table, /scroll=\{scroll \|\| \{ x: 'max-content' \}\}/);
  assert.match(table, /className=\{`public-data-table/);
  assert.match(table, /pageSize:\s*8/);
  assert.doesNotMatch(table, /Math\.random/);
  assert.doesNotMatch(table, /rowKey=/);
  assert.match(styles, /\.public-data-table \.ant-table-content\s*\{[\s\S]*?overflow-x:\s*auto/);
  assert.match(styles, /\.public-data-table \.ant-table-thead > tr > th\s*\{[\s\S]*?height:\s*44px/);
  assert.match(styles, /\.public-data-table \.ant-table-tbody > tr > td\s*\{[\s\S]*?min-height:\s*46px/);
  assert.match(styles, /\.public-data-table \.ant-table-pagination\.ant-pagination\s*\{[\s\S]*?flex-wrap:\s*wrap/);
});

test('ScrollPanel and charts remain responsive without a duplicate observer', async () => {
  const [section, chart, styles] = await Promise.all([
    read('../src/components/cards/SectionCard.tsx'),
    read('../src/components/charts/AppChart.tsx'),
    read('../src/styles.css')
  ]);
  assert.match(section, /section-card-scrollable/);
  assert.match(styles, /\.section-card-scrollable \.ant-card-body\s*\{[\s\S]*?min-height:\s*0[\s\S]*?flex:\s*1 1 auto[\s\S]*?overflow:\s*auto[\s\S]*?overscroll-behavior:\s*contain/);
  assert.match(chart, /autoResize/);
  assert.doesNotMatch(chart, /new ResizeObserver/);
  assert.match(chart, /option=\{option\}/);
  assert.match(chart, /style=\{\{ height, width: '100%' \}\}/);
  assert.match(styles, /\.app-chart\s*\{[\s\S]*?min-width:\s*0[\s\S]*?min-height:\s*0[\s\S]*?max-width:\s*100%/);
});

test('empty and error states expose accessible semantics without changing state branches', async () => {
  const states = await read('../src/components/common/States.tsx');
  assert.match(states, /className="empty-state" role="status" aria-live="polite"/);
  assert.match(states, /className="error-state"[\s\S]*?status="error"/);
  for (const state of ['loading', 'empty', 'unauthorized', 'forbidden', 'error', 'stale']) {
    assert.match(states, new RegExp(`meta\\.state === '${state}'`));
  }
  assert.match(states, /onRetry && meta\.canRetry/);
  assert.match(states, /className="page-state-success"/);
});

test('drawer modal popover tooltip and floating assistant keep the documented z-index chain', async () => {
  const [detail, log, confirm, variables, theme, styles] = await Promise.all([
    read('../src/components/actions/DetailDrawer.tsx'),
    read('../src/components/actions/TaskLogViewer.tsx'),
    read('../src/components/actions/ConfirmModal.ts'),
    read('../src/theme/variables.css'),
    read('../src/theme/themeConfig.ts'),
    read('../src/styles.css')
  ]);
  for (const source of [detail, log]) {
    assert.match(source, /open=\{open\}/);
    assert.match(source, /onClose=\{onClose\}/);
    assert.match(source, /destroyOnHidden/);
  }
  assert.match(confirm, /okText/);
  assert.match(confirm, /cancelText/);
  assert.match(variables, /--z-page-header:\s*300/);
  assert.match(variables, /--z-floating-assistant:\s*850/);
  assert.match(variables, /--z-overlay-base:\s*1000/);
  assert.match(variables, /--z-tooltip:\s*1070/);
  assert.match(theme, /Drawer:\s*\{[\s\S]*?zIndexPopup:\s*1000/);
  assert.match(theme, /Popover:\s*\{[\s\S]*?zIndexPopup:\s*1030/);
  assert.match(theme, /Tooltip:\s*\{[\s\S]*?zIndexPopup:\s*1070/);
  assert.match(styles, /\.ant-drawer-content-wrapper\s*\{[\s\S]*?max-width:/);
});
