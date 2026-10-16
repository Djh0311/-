'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const test = require('node:test');
const { spawnSync } = require('node:child_process');
const adapter = require('./harness-lite.cjs');
const project = path.resolve(__dirname, '../..');
const runtime = path.join(project, '.claude/harness-lite');
const installer = require(path.join(runtime, 'lib/install.js'));
const authorization = require(path.join(runtime, 'lib/authorization.js'));
function fixture(t) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'devin-harness-fixture-'));
  t.after(() => fs.rmSync(root, { recursive: true, force: false }));
  const result = installer.install(root, { source: runtime, write: true, profile: 'project' });
  assert.equal(result.status, 'INSTALLED', result.reason);
  return root;
}
function snapshot(root) {
  const rows = [];
  function visit(dir) {
    for (const name of fs.readdirSync(dir).sort()) {
      const file = path.join(dir, name), stat = fs.lstatSync(file), relative = path.relative(root, file);
      if (stat.isDirectory()) { rows.push([relative, 'directory']); visit(file); }
      else { assert.equal(stat.isFile(), true); rows.push([relative, stat.mode & 0o777, fs.readFileSync(file).toString('base64')]); }
    }
  }
  visit(root);
  return rows;
}
test('Devin normalization preserves per-turn IDs and shell arguments', () => {
  const value = adapter.normalize({ hook_event_name: 'PreToolUse', session_id: 'synthetic-session', prompt_id: 'synthetic-prompt', tool_name: 'exec', tool_input: { command: 'git status --short' } });
  assert.equal(value.turn_id, 'synthetic-prompt');
  assert.equal(value.tool_name, 'Bash');
  assert.equal(value.tool_input.command, 'git status --short');
});
test('context injection stays read-only without Codex observation or authorization', t => {
  const root = fixture(t), before = snapshot(root);
  for (const event of ['SessionStart', 'UserPromptSubmit']) {
    const result = adapter.handle({ hook_event_name: event, session_id: 'synthetic-session', prompt_id: 'synthetic-prompt', prompt: 'synthetic audit only' }, root);
    assert.equal(result.hookSpecificOutput.hookEventName, event);
    assert.match(result.hookSpecificOutput.additionalContext, /Harness Lite/);
    assert.match(result.hookSpecificOutput.additionalContext, /Devin 适配只读取/);
  }
  assert.deepEqual(snapshot(root), before);
  assert.equal(authorization.read(root).kind, 'closed');
});
test('ordinary commands remain allowed and push fails closed without pending state', t => {
  const root = fixture(t), before = snapshot(root);
  const input = { hook_event_name: 'PreToolUse', tool_name: 'exec', session_id: 'synthetic-session', prompt_id: 'synthetic-prompt' };
  assert.deepEqual(adapter.handle({ ...input, tool_input: { command: 'git status --short' } }, root), {});
  assert.equal(adapter.handle({ ...input, tool_input: { command: 'git push origin HEAD:refs/heads/main' } }, root).decision, 'block');
  assert.deepEqual(snapshot(root), before);
});
test('Stop never creates continuation or execution authorization', t => {
  const root = fixture(t), before = snapshot(root);
  assert.deepEqual(adapter.handle({ hook_event_name: 'Stop', stop_hook_active: false }, root), {});
  assert.deepEqual(snapshot(root), before);
});
test('missing runtime denies push and emits bounded context warnings', t => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'devin-harness-missing-'));
  t.after(() => fs.rmSync(root, { recursive: true, force: false }));
  assert.equal(adapter.handle({ hook_event_name: 'PreToolUse', tool_name: 'exec', tool_input: { command: 'git push origin HEAD:refs/heads/main' } }, root).decision, 'block');
  assert.match(adapter.handle({ hook_event_name: 'SessionStart' }, root).hookSpecificOutput.additionalContext, /未写状态/);
  assert.deepEqual(fs.readdirSync(root), []);
});
test('entry point refuses a different workspace root', () => {
  const run = spawnSync(process.execPath, [path.join(__dirname, 'harness-lite.cjs')], { input: JSON.stringify({ hook_event_name: 'SessionStart' }), encoding: 'utf8', env: { ...process.env, DEVIN_PROJECT_DIR: path.dirname(project) } });
  assert.equal(run.status, 0);
  assert.equal(run.stdout, '');
});
