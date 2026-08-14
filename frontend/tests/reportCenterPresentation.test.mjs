import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const source = await readFile(new URL('../src/pages/report/ReportCenterPage.tsx', import.meta.url), 'utf8');
const layoutSource = await readFile(new URL('../src/layout/BasicLayout.tsx', import.meta.url), 'utf8');

test('报告中心业务内容不展示指定的过期追溯详情', () => {
  const forbiddenPresentation = [
    '数据已过期',
    '原因：',
    '重新刷新',
    '追溯信息',
    '模型 / 特征',
    '业务批次已加载',
    '生成时间',
    '更新时间',
    '数据时间',
    '日期范围',
    '当前报告未提供适用窗口',
    '数据版本'
  ];
  for (const text of forbiddenPresentation) {
    assert.equal(source.includes(text), false, `不应在报告中心页面展示：${text}`);
  }
});

test('报告路由使用独立内容工作台并完整保留左侧目录', () => {
  assert.equal(layoutSource.includes("route === 'report' ? 'app-shell--report' : ''"), true);
  assert.equal(layoutSource.includes('<Sidebar collapsed={collapsed} route={route}'), true);
  assert.equal(layoutSource.includes("route !== 'report' && <Sidebar"), false);
  for (const marker of ['report-page-toolbar', 'report-workspace-grid', 'report-workspace-left', 'report-workspace-right', '<ReportMetricPair']) {
    assert.equal(source.includes(marker), true, `应保留报告工作台结构：${marker}`);
  }
});

test('报告中心继续保留阻塞状态和真实功能入口', () => {
  for (const marker of [
    '<PageDataState',
    "'loading'",
    "'empty'",
    "'error'",
    "'unauthorized'",
    "'forbidden'",
    'onGenerate={generateReport}',
    'onDownload={downloadReport}',
    "review('approve')",
    "review('reject')",
    "review('publish')"
  ]) {
    assert.equal(source.includes(marker), true, `应保留状态或真实功能标记：${marker}`);
  }
});

test('审核页重置使用空搜索词重新请求而不是沿用旧闭包值', () => {
  assert.equal(source.includes("changeFilters('', '', '')"), true);
  assert.equal(source.includes('loadData(nextKeyword, 1, nextType, nextStatus)'), true);
});
