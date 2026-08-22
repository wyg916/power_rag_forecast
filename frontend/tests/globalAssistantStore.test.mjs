import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import ts from 'typescript';

async function loadStore() {
  const source = await readFile(new URL('../src/features/globalAssistant/globalAssistantStore.ts', import.meta.url), 'utf8');
  const output = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.ES2022, target: ts.ScriptTarget.ES2022 }
  }).outputText;
  return import(`data:text/javascript;base64,${Buffer.from(output).toString('base64')}`);
}

test('globalAssistantStore preserves session, messages, draft and attachments across route changes', async () => {
  const store = await loadStore();
  store.globalAssistantStore.resetForTest();
  store.globalAssistantStore.setOpen(true);
  store.globalAssistantStore.setSessionId('session-1');
  store.globalAssistantStore.setDraft('未发送草稿');
  store.globalAssistantStore.appendMessage({ id: 'm1', role: 'assistant', markdown: '已存在回答', status: 'completed' });
  store.globalAssistantStore.addAttachment({ client_id: 'a1', attachment_id: 'attachment-1', file_name: 'evidence.pdf', size_bytes: 42, media_type: 'application/pdf', status: 'ready' });
  store.globalAssistantStore.setOpen(false);
  const state = store.globalAssistantStore.getSnapshot();
  assert.equal(state.sessionId, 'session-1');
  assert.equal(state.draft, '未发送草稿');
  assert.equal(state.messages.length, 1);
  assert.equal(state.attachments[0].status, 'ready');
});

test('new conversation is the only store action that clears contextual state', async () => {
  const store = await loadStore();
  store.globalAssistantStore.newConversation();
  const state = store.globalAssistantStore.getSnapshot();
  assert.equal(state.sessionId, null);
  assert.deepEqual(state.messages, []);
  assert.equal(state.draft, '');
  assert.deepEqual(state.attachments, []);
});
