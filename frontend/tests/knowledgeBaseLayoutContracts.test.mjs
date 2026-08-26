import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const read = (path) => readFile(new URL(path, import.meta.url), 'utf8');

test('knowledge base keeps every existing functional entry while refining only its layout', async () => {
  const page = await read('../src/pages/knowledge/KnowledgeBasePage.tsx');

  for (const handler of [
    'loadData',
    'rebuildIndex',
    'refreshEmbeddings',
    'batchValidate',
    'exportResult',
    'uploadDocument',
    'runSearch',
    'runReleaseAction'
  ]) {
    assert.match(page, new RegExp(`(?:async function ${handler}|onClick=\\{${handler}\\}|onClick: ${handler})`));
  }

  for (const apiCall of [
    'api.knowledgeIndexLocal()',
    'api.knowledgeEmbeddingRefresh()',
    'api.knowledgeBatchValidate({ top_k: topK })',
    'api.knowledgeExport()',
    'api.knowledgeUpload(file)',
    'searchKnowledge(text, topK)'
  ]) {
    assert.ok(page.includes(apiCall), `missing existing API call: ${apiCall}`);
  }

  assert.match(page, /title="知识库 \/ 业务知识库"/);
  assert.match(page, /className="knowledge-page-header"/);
  assert.match(page, /className="knowledge-upload-button"/);
  assert.match(page, /onClick=\{\(\) => \{ setDetailData\(record\.raw \|\| record\); setDetailOpen\(true\); \}\}/);
  assert.match(page, /onClick=\{\(\) => navigator\.clipboard\?\.writeText/);
});

test('knowledge document table preserves six columns and makes long fields inspectable', async () => {
  const page = await read('../src/pages/knowledge/KnowledgeBasePage.tsx');
  const start = page.indexOf('className="knowledge-doc-card"');
  const end = page.indexOf('<SectionCard title="索引与 RAG 状态"');
  const table = page.slice(start, end);

  for (const title of ['文档名称', '文档分类', '更新时间', 'Chunk', '状态', '操作']) {
    assert.match(table, new RegExp(`title: '${title}'`));
  }
  assert.match(table, /tableLayout="fixed"/);
  assert.match(table, /scroll=\{\{ x: 970 \}\}/);
  assert.match(table, /<Tooltip title=\{value\}/);
  assert.match(table, /className="knowledge-doc-name" title=\{value\}/);
  assert.match(table, /className="knowledge-doc-category" title=\{value\}/);
});

test('knowledge status remains visible while the specified yellow warning block is removed', async () => {
  const page = await read('../src/pages/knowledge/KnowledgeBasePage.tsx');
  assert.match(page, /检索服务：\{retrievalAvailable \? '可用' : '暂不可用'\}/);
  assert.match(page, /RAG 运行状态/);
  assert.match(page, /索引与向量化状态摘要/);
  assert.doesNotMatch(page, /当前不会返回未经发布的候选知识/);
  assert.doesNotMatch(page, /message="检索服务暂不可用"/);
});

test('knowledge page owns a compact opaque sticky header, natural flow and assistant safe area', async () => {
  const css = await read('../src/pages/knowledge/knowledge-base-layout.css');
  assert.match(css, /\.knowledge-workbench-page\s*\{[\s\S]*?height:\s*auto[\s\S]*?padding-bottom:\s*80px[\s\S]*?overflow:\s*visible/);
  assert.match(css, /\.knowledge-page-header\.page-heading-unified\s*\{[\s\S]*?position:\s*sticky[\s\S]*?z-index:\s*var\(--z-page-header\)[\s\S]*?isolation:\s*isolate[\s\S]*?min-height:\s*56px[\s\S]*?background:\s*#fff/);
  assert.match(css, /\.knowledge-content-grid\s*\{[\s\S]*?minmax\(300px, 320px\)/);
  assert.match(css, /\.knowledge-rag-content\s*\{[\s\S]*?overflow:\s*visible/);
  assert.match(css, /\.knowledge-doc-card \.ant-table-pagination\s*\{[\s\S]*?margin-right:\s*76px/);
  assert.match(css, /\.knowledge-answer-card \.ant-card-head\s*\{[\s\S]*?padding-right:\s*76px/);
  assert.match(css, /@media \(max-width: 900px\)[\s\S]*?grid-template-columns:\s*minmax\(0, 1fr\)/);
});
