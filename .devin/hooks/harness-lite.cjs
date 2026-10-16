'use strict';
const fs = require('node:fs');
const path = require('node:path');
const project = path.resolve(__dirname, '../..');
const contextEvents = new Set(['SessionStart', 'UserPromptSubmit']);
const shellTools = new Set(['exec', 'functions.exec', 'Bash']);
const boundary = 'Devin 适配只读取 Harness 上下文，不生成 Codex 宿主观测、执行授权或自动续跑；当前用户目标和项目禁区优先，current leaf 不是执行授权。';
const denyPush = () => ({ decision: 'block', reason: 'Devin 只读适配不签发 push 授权；本项目保持不 commit/push，需单独明确授权与执行路径验收。' });
function normalize(input) {
  const value = input && typeof input === 'object' && !Array.isArray(input) ? input : {};
  return { ...value, turn_id: value.prompt_id || value.turn_id, tool_name: shellTools.has(value.tool_name) ? 'Bash' : value.tool_name };
}
function handle(input, root = project) {
  const normalized = normalize(input), event = normalized.hook_event_name;
  const shell = event === 'PreToolUse' && normalized.tool_name === 'Bash';
  const command = typeof normalized.tool_input?.command === 'string' ? normalized.tool_input.command : '';
  if (!contextEvents.has(event) && !shell) return {};
  try {
    const runtime = path.join(root, '.claude/harness-lite');
    const dispatcher = require(path.join(runtime, 'hooks/dispatcher.js'));
    if (!dispatcher.bootstrapVerify(root).ok) {
      if (shell && /\bgit\b[\s\S]*\bpush\b/.test(command)) return denyPush();
      return contextEvents.has(event) ? { hookSpecificOutput: { hookEventName: event, additionalContext: 'Harness 身份未通过校验；未写状态、未授予权限。' } } : {};
    }
    const hook = require(path.join(runtime, 'lib/hook.js'));
    if (shell) return hook.classifyPush(command) ? denyPush() : {};
    const install = require(path.join(runtime, 'lib/install.js'));
    const chain = require(path.join(runtime, 'lib/tree.js')).readChain(root);
    return { hookSpecificOutput: { hookEventName: event, additionalContext: `${install.INSTRUCTION}\n${boundary}\n${hook.hookContext(root, chain, null, { write: false, input: normalized })}` } };
  } catch {
    if (shell && /\bgit\b[\s\S]*\bpush\b/.test(command)) return denyPush();
    return contextEvents.has(event) ? { hookSpecificOutput: { hookEventName: event, additionalContext: 'Harness 上下文暂不可用；未写状态、未授予权限。' } } : {};
  }
}
function main() {
  let input;
  try { input = JSON.parse(fs.readFileSync(0, 'utf8')); } catch { return; }
  if (process.env.DEVIN_PROJECT_DIR && path.resolve(process.env.DEVIN_PROJECT_DIR) !== project) return;
  const output = handle(input);
  if (Object.keys(output).length) process.stdout.write(`${JSON.stringify(output)}\n`);
}
if (require.main === module) main();
module.exports = { normalize, handle };
