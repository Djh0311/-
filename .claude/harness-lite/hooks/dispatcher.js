#!/usr/bin/env node
'use strict';
const fs = require('fs');
const { spawnSync } = require('child_process');
const hook = require('../lib/hook.js');
const install = require('../lib/install.js');

function input() { try { return JSON.parse(fs.readFileSync(0, 'utf8')) || {}; } catch { return {}; } }
function main(argv = []) {
  if (argv[0] === '--native-pre-push') {
    const remote = argv[1] || 'origin', url = argv[2] || null, foreignAt = argv.indexOf('--foreign'), foreign = foreignAt >= 0 ? argv[foreignAt + 1] : null;
    const refs = fs.readFileSync(0, 'utf8'), root = hook.projectRoot(process.cwd()), result = hook.nativePrePush(root, remote, url, refs);
    if (!result.ok) { console.error(`Harness pre-push：${result.reason}`); return 1; }
    if (foreign && fs.existsSync(foreign)) return spawnSync(foreign, argv.slice(1, 3), { cwd: process.cwd(), input: refs, stdio: ['pipe', 'inherit', 'inherit'] }).status || 0;
    return 0;
  }
  if (argv[0] === '--push-assert') {
    const root = hook.projectRoot(process.cwd());
    if (!install.verify06(root).ok) { process.stdout.write(`${JSON.stringify({ ok: false, reason: 'runtime identity 未通过；push assertion 零写 HOLD' })}\n`); return 1; }
    let claim = {}; try { claim = JSON.parse(fs.readFileSync(0, 'utf8')); } catch { /* 固定结构校验在 pushAssert */ }
    const result = hook.pushAssert(root, claim);
    process.stdout.write(`${JSON.stringify(result)}\n`);
    return result.ok ? 0 : 1;
  }
  const data = input(), root = hook.projectRoot(data.cwd || process.cwd()), checked = install.verify06(root);
  if (!checked.ok) {
    if (data.hook_event_name === 'PreToolUse' && data.tool_name === 'Bash' && hook.classifyPush(data.tool_input?.command)) {
      process.stdout.write(`${JSON.stringify({ hookSpecificOutput: { hookEventName: 'PreToolUse', permissionDecision: 'deny',
        permissionDecisionReason: 'Harness push gate：runtime identity 未通过，fail closed。' } })}\n`);
    } else if (data.hook_event_name === 'SessionStart' || data.hook_event_name === 'UserPromptSubmit') {
      process.stdout.write(`${JSON.stringify({ hookSpecificOutput: { hookEventName: data.hook_event_name,
        additionalContext: 'Harness runtime identity 未通过；本事件未写状态，请先修复或完成独立迁移。' } })}\n`);
    }
    return 0;
  }
  const output = hook.dispatch(root, data);
  if (output && Object.keys(output).length) process.stdout.write(`${JSON.stringify(output)}\n`);
  return 0;
}
if (require.main === module) { try { process.exit(main(process.argv.slice(2))); } catch (error) { console.error(error.message); process.exit(1); } }
module.exports = { main };
