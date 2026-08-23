import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import ts from 'typescript';

async function importTypeScript(path) {
  const source = await readFile(new URL(path, import.meta.url), 'utf8');
  const output = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.ES2022, target: ts.ScriptTarget.ES2022 }
  }).outputText;
  return import(`data:text/javascript;base64,${Buffer.from(output).toString('base64')}`);
}

test('PermissionRoute policy follows the frozen permission matrix', async () => {
  const policy = await importTypeScript('../src/security/permissions.ts');
  assert.equal(policy.canAccessRoute('dashboard', ['dashboard:read']), true);
  assert.equal(policy.canAccessRoute('assistant', ['forecast:read']), false);
  assert.equal(policy.canAccessRoute('settings', ['*']), true);
});

test('PermissionGate child policy hides protected tabs', async () => {
  const policy = await importTypeScript('../src/security/permissions.ts');
  assert.equal(Object.keys(policy.childPermissions).length, 32);
  assert.equal(policy.canAccessChild('forecast-model', ['forecast:read']), false);
  assert.equal(policy.canAccessChild('forecast-model', ['forecast:read', 'model:read']), true);
  assert.equal(policy.canAccessChild('strategy-review', ['strategy:read']), false);
  assert.equal(policy.canAccessChild('strategy-review', ['strategy:read', 'strategy:review']), true);
});

test('ActionGuard and permission snapshot remain deterministic', async () => {
  const policy = await importTypeScript('../src/security/permissions.ts');
  assert.equal(policy.canPerformAction('report:generate', ['report:read']), false);
  assert.equal(policy.canPerformAction('report:generate', ['report:read', 'report:generate']), true);
  assert.equal(policy.canPerformAction('report.generate', ['report:generate'], { actions: { 'report.generate': true } }), true);
  assert.equal(policy.canPerformAction('report.generate', ['report:generate'], { actions: { 'report.generate': false } }), false);
  assert.equal(policy.permissionSnapshotHash(['b', 'a']), policy.permissionSnapshotHash(['a', 'b']));
});

test('analyst strategy view suppresses review history queries and protected review content', async () => {
  const source = await readFile(new URL('../src/pages/strategy/StrategyCenterPage.tsx', import.meta.url), 'utf8');
  assert.match(source, /activeSubKey === 'strategy-review' && canReview/);
  assert.match(source, /if \(!canReview \|\| mode !== 'review'\)/);
  assert.match(source, /if \(!canReview \|\| !strategyId\)/);
});

test('selected attachments default to isolated attachment knowledge scope', async () => {
  const drawer = await readFile(new URL('../src/features/globalAssistant/GlobalAssistantDrawer.tsx', import.meta.url), 'utf8');
  const page = await readFile(new URL('../src/pages/assistant/AssistantPage.tsx', import.meta.url), 'utf8');
  assert.match(drawer, /readyAttachments\.length \? 'attachments' : 'authorized_enterprise'/);
  assert.match(page, /contextAttachments\.length \? 'attachments' : 'authorized_enterprise'/);
});
