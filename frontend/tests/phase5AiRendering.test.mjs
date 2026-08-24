import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import ts from 'typescript';

async function loadTs(relativePath) {
  const source = await readFile(new URL(relativePath, import.meta.url), 'utf8');
  const output = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.ES2022, target: ts.ScriptTarget.ES2022 }
  }).outputText;
  return import(`data:text/javascript;base64,${Buffer.from(output).toString('base64')}`);
}

test('the five existing assistant modes keep one explicit request contract', async () => {
  const modes = await loadTs('../src/features/globalAssistant/assistantModes.ts');
  assert.equal(modes.ASSISTANT_MODE_CONTRACTS.length, 5);
  assert.deepEqual(
    modes.ASSISTANT_MODE_CONTRACTS.map((item) => item.auditName),
    ['标准模式', '专业解读', '通俗解释', '业务建议', '报告摘要']
  );
  assert.equal(modes.DEFAULT_ASSISTANT_ANSWER_STYLE, 'professional_brief');
  assert.equal(modes.resolveAssistantRequestMode('chatbi'), 'chatbi');
  assert.equal(modes.resolveAssistantRequestMode('professional_brief'), 'general');
  assert.equal(modes.resolveAssistantRequestMode('plain_language'), 'general');
  assert.equal(modes.resolveAssistantRequestMode('business_advice'), 'general');
  assert.equal(modes.resolveAssistantRequestMode('report_style'), 'general');
  assert.equal(modes.resolveAssistantRequestMode('professional_brief', { hasAttachments: true }), 'file');
  assert.equal(modes.resolveAssistantRequestMode('professional_brief', { hasImage: true, hasAttachments: true }), 'vision');
});

test('professional mode and session changes are bound without changing request fields', async () => {
  const [page, api] = await Promise.all([
    readFile(new URL('../src/pages/assistant/AssistantPage.tsx', import.meta.url), 'utf8'),
    readFile(new URL('../src/services/assistantApi.ts', import.meta.url), 'utf8')
  ]);
  assert.match(page, /answer_style:\s*answerStyle/);
  assert.match(page, /resolveAssistantRequestMode\(answerStyle/);
  assert.match(page, /sessionAnswerStyles/);
  assert.match(page, /setAnswerStyle\(DEFAULT_ASSISTANT_ANSWER_STYLE\)/);
  assert.doesNotMatch(page, /answerStyle === 'plain_language' \? 'general' : 'rag'/);
  for (const field of ['request_id', 'session_id', 'message', 'mode', 'stream', 'requested_tier', 'premium_confirmed', 'model_provider', 'answer_style', 'attachment_ids', 'page_context', 'knowledge_scope']) {
    assert.match(api, new RegExp(`${field}:`), `request field should remain present: ${field}`);
  }
  assert.match(api, /\/api\/ai\/chat\/stream/);
  assert.match(api, /method:\s*'POST'/);
});

test('deterministic SSE parser preserves split markdown, unicode and JSON and ignores duplicate finish', async () => {
  const { AssistantSseParser } = await loadTs('../src/features/globalAssistant/assistantStream.ts');
  const events = [];
  const parser = new AssistantSseParser((event, payload) => events.push([event, payload]));
  parser.push('event: meta\ndata: {"session_id":"sess_1"}\n\n');
  parser.push('event: delta\ndata: {"text":"中文 # 标题\\n\\n|列A|列B|\\n|---|---|\\n"}\n\n');
  parser.push('event: delta\ndata: {"text":"|1|2|\\n\\n```js\\nconst"}\n\n');
  parser.push('event: delta\ndata: {"text":" value = {\\\"ok\\\":true};\\n```"}\n\n');
  parser.push('event: delta\ndata: {"text":""}\n\n');
  parser.push('event: finish\ndata: {"status":"completed"}\n\nevent: done\ndata: {"status":"completed"}\n\n');
  const result = parser.finish();
  assert.equal(result.finalEvent, 'finish');
  assert.match(result.streamedMarkdown, /中文/);
  assert.match(result.streamedMarkdown, /\|列A\|列B\|/);
  assert.match(result.streamedMarkdown, /```js/);
  assert.match(result.streamedMarkdown, /"ok":true/);
  assert.equal(result.terminalEventCount, 2);
  assert.equal(events.filter(([event]) => event === 'finish' || event === 'done').length, 1);
});

test('SSE parser accepts backend done, rejects error, malformed data and network close without finish', async () => {
  const { AssistantSseParser } = await loadTs('../src/features/globalAssistant/assistantStream.ts');
  const done = new AssistantSseParser();
  done.push('event: delta\ndata: {"text":"ok"}\n\nevent: done\ndata: {"answer":"ok"}\n\n');
  assert.equal(done.finish().streamedMarkdown, 'ok');

  const failed = new AssistantSseParser();
  assert.throws(() => failed.push('event: error\ndata: {"error":{"message":"provider unavailable"}}\n\n'), /provider unavailable/);

  const malformed = new AssistantSseParser();
  assert.throws(() => malformed.push('event: delta\ndata: {bad json}\n\n'), /无法解析/);

  const closed = new AssistantSseParser();
  closed.push('event: delta\ndata: {"text":"partial"}\n\n');
  assert.throws(() => closed.finish(), /未返回完成事件/);
});

test('markdown tokenizer supports natural blocks, JSON and stable duplicate table rows', async () => {
  const content = await loadTs('../src/features/globalAssistant/assistantContent.ts');
  const markdown = [
    '# 一级标题',
    '## 二级标题',
    '### 三级标题',
    '',
    '普通文本含 `inline`、**重点** 与 https://example.com/a/very/long/path.',
    '',
    '- 无序一',
    '- 无序二',
    '',
    '1. 有序一',
    '2. 有序二',
    '',
    '> 引用内容',
    '',
    '| 字段 | 值 |',
    '| --- | --- |',
    '| A | 1 |',
    '| A | 1 |',
    '',
    '```sql',
    'select * from safe_view;',
    '```',
    '',
    '```python',
    'print("ok")',
    '```'
  ].join('\n');
  const blocks = content.tokenizeAssistantMarkdown(markdown);
  for (const type of ['heading', 'paragraph', 'unordered-list', 'ordered-list', 'blockquote', 'table', 'code']) {
    assert.ok(blocks.some((block) => block.type === type), `missing block type: ${type}`);
  }
  const table = blocks.find((block) => block.type === 'table');
  assert.equal(table.rows.length, 2);
  assert.notEqual(table.rows[0].key, table.rows[1].key);
  assert.deepEqual(
    content.tokenizeAssistantMarkdown(markdown).find((block) => block.type === 'table').rows.map((row) => row.key),
    table.rows.map((row) => row.key)
  );
  const json = content.tokenizeAssistantMarkdown('{"nested":{"ok":true},"items":[1,2]}');
  assert.equal(json[0].type, 'code');
  assert.equal(json[0].language, 'json');
  assert.match(json[0].value, /\n  "nested"/);
});

test('500, 2000, 5000 and 10000 character fixtures remain complete', async () => {
  const { tokenizeAssistantMarkdown } = await loadTs('../src/features/globalAssistant/assistantContent.ts');
  for (const size of [500, 2000, 5000, 10000]) {
    const fixture = '长'.repeat(size);
    const blocks = tokenizeAssistantMarkdown(fixture);
    assert.equal(blocks.length, 1);
    assert.equal(blocks[0].type, 'paragraph');
    assert.equal(blocks[0].text.length, size);
  }
});

test('assistant object answers and RAG/attachment citations remain truthful and separate', async () => {
  const content = await loadTs('../src/features/globalAssistant/assistantContent.ts');
  const rendered = content.resolveAssistantAnswerMarkdown({ status: 'ok', rows: [{ hour: 1 }] });
  assert.match(rendered, /^```json/);
  assert.doesNotMatch(rendered, /\[object Object\]/);
  const rag = content.normalizeAssistantCitation({ citation_id: 'rag-1', title: '很长的知识标题', quote: '依据' }, 0, 'rag');
  const attachment = content.normalizeAssistantCitation({ attachment_id: 'att-1', file_name: '附件.pdf' }, 0, 'attachment');
  assert.match(rag.key, /^rag-/);
  assert.match(attachment.key, /^attachment-/);
  assert.equal(rag.sourceId, 'rag-1');
  assert.equal(attachment.sourceId, 'att-1');
});

test('report value renderer handles primitives, arrays, nested objects and null without technical literals', async () => {
  const report = await loadTs('../src/services/reportValue.ts');
  const fixtures = [
    '文本',
    42,
    true,
    null,
    ['00:00', '01:00'],
    { reason: '预测窗口过期', evidence: { hours: ['03:00', '04:00'] }, enabled: false }
  ];
  for (const fixture of fixtures) {
    const lines = report.formatReportValueLines(fixture);
    assert.ok(lines.length > 0);
    assert.doesNotMatch(lines.join('；'), /\[object Object\]/);
  }
  assert.equal(report.pickReportScalar({ risk_level: 'high' }, ['risk_level']), 'high');
});

test('renderer CSS keeps message, evidence, code and tables in their own scroll boundaries', async () => {
  const [css, renderer, attachment, drawer] = await Promise.all([
    readFile(new URL('../src/styles.css', import.meta.url), 'utf8'),
    readFile(new URL('../src/features/globalAssistant/DynamicAnswer.tsx', import.meta.url), 'utf8'),
    readFile(new URL('../src/features/globalAssistant/AttachmentComposer.tsx', import.meta.url), 'utf8'),
    readFile(new URL('../src/features/globalAssistant/GlobalAssistantDrawer.tsx', import.meta.url), 'utf8')
  ]);
  assert.match(css, /\.assistant-markdown\s*\{[^}]*font-size:\s*15px;[^}]*line-height:\s*1\.75/s);
  assert.match(css, /\.assistant-code-block pre\s*\{[^}]*overflow-x:\s*auto/s);
  assert.match(css, /\.assistant-markdown-table-scroll\s*\{[^}]*overflow-x:\s*auto/s);
  assert.match(css, /\.assistant-message-scroll,[^}]*overflow-y:\s*auto/s);
  assert.match(css, /\.assistant-right-rail\s*\{[^}]*overflow-y:\s*auto/s);
  assert.doesNotMatch(renderer, /rowKey=\{\(_, index\)/);
  for (const marker of ['onDrop={handleDrop}', 'onPaste={handlePaste}', '选择文件', 'uploading', 'parsing', 'ready', 'failed', 'onRetry', 'onRemove']) {
    assert.match(attachment, new RegExp(marker.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
  }
  assert.match(drawer, /controllerRef\.current\?\.abort/);
  assert.match(drawer, /cancelled \? 'cancelled' : 'failed'/);
});
