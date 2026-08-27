import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const read = (path) => readFile(new URL(path, import.meta.url), 'utf8');

test('all core page roots use the shared shell scroll owner and natural page flow', async () => {
  const styles = await read('../src/styles.css');
  const phase4 = styles.slice(styles.indexOf('/* Phase 4 core-page layout convergence.'));
  for (const root of [
    '.home-dashboard-page',
    '.data-design-page',
    '.forecast-design-page',
    '.strategy-design-page',
    '.model-workbench-page',
    '.knowledge-workbench-page',
    '.task-workbench-page',
    '.settings-workbench'
  ]) {
    assert.match(phase4, new RegExp(root.replaceAll('.', '\\.')));
  }
  assert.match(phase4, /height:\s*auto/);
  assert.match(phase4, /overflow:\s*visible/);
  assert.match(phase4, /\.report-workbench\.page-stack\s*\{[\s\S]*?grid-template-rows:\s*auto auto/);
  assert.match(phase4, /\.report-page-toolbar\s*\{[\s\S]*?position:\s*sticky[\s\S]*?z-index:\s*var\(--z-page-header\)/);
});

test('assistant keeps the authorized three-column layout and independent work areas', async () => {
  const styles = await read('../src/styles.css');
  const phase4 = styles.slice(styles.indexOf('/* Phase 4 core-page layout convergence.'));
  assert.match(phase4, /\.assistant-workspace-page\s*\{[\s\S]*?min-height:\s*620px/);
  assert.match(phase4, /\.assistant-workspace-grid\s*\{[\s\S]*?grid-template-columns:\s*minmax\(232px, 240px\) minmax\(0, 1fr\) minmax\(300px, 320px\)/);
  assert.match(phase4, /\.assistant-left-rail,[\s\S]*?\.assistant-right-rail,[\s\S]*?min-height:\s*0/);
  assert.doesNotMatch(phase4, /DynamicAnswer|markdown|citation|provider/i);
});

test('forecast, strategy and high-risk grids converge without hiding fixed-height content', async () => {
  const styles = await read('../src/styles.css');
  const phase4 = styles.slice(styles.indexOf('/* Phase 4 core-page layout convergence.'));
  assert.match(phase4, /\.forecast-chart-card,[\s\S]*?height:\s*auto[\s\S]*?max-height:\s*none[\s\S]*?overflow:\s*visible/);
  assert.match(phase4, /\.forecast-detail-grid > \.forecast-table-card,[\s\S]*?min-height:\s*178px/);
  assert.match(phase4, /@media \(max-width: 1366px\)[\s\S]*?\.storage-workspace,[\s\S]*?\.review-workspace,[\s\S]*?grid-template-columns:\s*minmax\(0, 1fr\)/);
  assert.match(phase4, /\.strategy-overview-bottom\s*\{[\s\S]*?flex-basis:\s*auto/);
});

test('stale metadata remains governed but no expiry annotation is rendered in the business UI', async () => {
  const [strategy, states, service] = await Promise.all([
    read('../src/pages/strategy/StrategyCenterPage.tsx'),
    read('../src/components/common/States.tsx'),
    read('../src/services/strategyApi.ts')
  ]);
  assert.doesNotMatch(strategy, /当前记录已过期或未通过，不可作为当前策略/);
  assert.doesNotMatch(strategy, /仅供复盘|数据已过期|适用窗口已结束/);
  assert.match(strategy, /汇总策略结论、风险窗口、执行状态与收益口径/);
  assert.match(states, /if \(meta\.state === 'stale'\) \{[\s\S]*?return null/);
  assert.doesNotMatch(states, /page-state-stale-inline|数据已过期|已过期：/);
  assert.match(service, /isStale: strategyIsStale/);
  assert.match(service, /staleReason:/);
  assert.match(strategy, /data\?\.strategyDate/);
  assert.match(strategy, /data\?\.strategyStatusLabel/);
});

test('data pages restore readable controls and tables while retaining local table scrolling', async () => {
  const styles = await read('../src/pages/data/data-center-workspace.css');
  const phase4 = styles.slice(styles.indexOf('/* Phase 4 data-page convergence:'));
  assert.match(phase4, /\.data-design-page\s*\{[\s\S]*?height:\s*auto[\s\S]*?overflow:\s*visible/);
  assert.match(phase4, /font-size:\s*var\(--font-size-table\)/);
  assert.match(phase4, /min-height:\s*var\(--control-height\)/);
  assert.match(phase4, /\.data-metric-grid\s*\{[\s\S]*?repeat\(auto-fit, minmax\(172px, 1fr\)\)/);
  assert.match(phase4, /@media \(max-width: 1366px\)[\s\S]*?\.data-quality-main[\s\S]*?grid-template-columns:\s*minmax\(0, 1fr\)/);
});

test('page actions reserve the floating assistant safe area without removing controls', async () => {
  const styles = await read('../src/styles.css');
  const phase4 = styles.slice(styles.indexOf('/* Phase 4 core-page layout convergence.'));
  const strategy = await read('../src/components/strategy/StrategyDesign.tsx');
  const knowledge = await read('../src/pages/knowledge/KnowledgeBasePage.tsx');

  assert.match(phase4, /\.home-task-card \.home-task-list,[\s\S]*?\.task-right-column \.task-card-head[\s\S]*?padding-right:\s*64px/);
  assert.match(phase4, /\.data-workspace-main \.data-alert-panel \.data-alert-row\s*\{[\s\S]*?padding-right:\s*64px/);
  assert.match(phase4, /\.knowledge-answer-card \.ant-card-head\s*\{[\s\S]*?padding-right:\s*64px/);
  assert.match(phase4, /\.forecast-bottom-summary \.ant-btn-block,[\s\S]*?width:\s*calc\(100% - 64px\)/);
  assert.match(strategy, /title:\s*'操作',\s*width:\s*72/);
  assert.match(strategy, />查看<\/[\s\S]*?>复核<\//);
  assert.match(knowledge, /title:\s*'操作',[\s\S]*?width:\s*168/);
});

test('report workspace keeps list and preview readable below the three-column desktop width', async () => {
  const styles = await read('../src/styles.css');
  const phase6 = styles.slice(styles.indexOf('/* Phase 6 regression closure:'));

  assert.match(phase6, /@media \(max-width: 1450px\)/);
  assert.match(phase6, /\.report-main-grid,[\s\S]*?grid-template-columns:\s*minmax\(320px, 340px\) minmax\(0, 1fr\)/);
  assert.match(phase6, /\.report-main-grid > \.report-workspace-right,[\s\S]*?grid-column:\s*1 \/ -1/);
  assert.match(phase6, /\.report-list-head,[\s\S]*?grid-template-columns:\s*minmax\(148px, 1fr\) 88px 64px/);
  assert.match(phase6, /\.report-list-item strong\s*\{[\s\S]*?-webkit-line-clamp:\s*2/);
  assert.match(phase6, /\.report-list-item small\s*\{[\s\S]*?text-overflow:\s*ellipsis[\s\S]*?white-space:\s*nowrap/);
});

test('final visual acceptance keeps visible text and forecast chart labels at least 12px', async () => {
  const [styles, dataStyles, forecast] = await Promise.all([
    read('../src/styles.css'),
    read('../src/pages/data/data-center-workspace.css'),
    read('../src/components/forecast/ForecastDesign.tsx')
  ]);

  const cssBelowTwelve = [styles, dataStyles]
    .flatMap((source) => Array.from(source.matchAll(/font-size\s*:\s*([0-9]+(?:\.[0-9]+)?)px/g), (match) => Number(match[1])))
    .filter((size) => size < 12);

  assert.deepEqual(cssBelowTwelve, []);
  assert.match(dataStyles, /\.data-alert-row\s*\{[\s\S]*?grid-template-columns:[^;]*128px/);
  assert.match(dataStyles, /\.catalog-card-grid button\s*\{[\s\S]*?position:\s*relative[\s\S]*?grid-template-columns:\s*30px minmax\(0, 1fr\)/);
  assert.match(dataStyles, /@media \(max-width: 1600px\)[\s\S]*?\.catalog-card-grid\s*\{[\s\S]*?grid-template-columns:\s*repeat\(2/);
  assert.match(styles, /\.task-health-item span,[\s\S]*?overflow-wrap:\s*anywhere[\s\S]*?text-overflow:\s*clip/);
  assert.match(styles, /@media \(max-width: 1366px\)[\s\S]*?\.task-list-card \.task-table\s*\{[\s\S]*?width:\s*calc\(100% - 56px\) !important/);
  assert.match(styles, /\.home-derived-note\s*\{[\s\S]*?display:\s*block[\s\S]*?overflow:\s*visible/);
  assert.doesNotMatch(forecast, /fontSize\s*:\s*(?:[0-9]|10|11)(?:\D|$)/);
});
