#!/usr/bin/env node
'use strict';
const path = require('path');

const CLI_COMMANDS = ['status', 'verify', 'map', 'mistake', 'install', 'selfcheck'];
const VALUE_FLAGS = new Set(['--target', '--source', '--extension', '--profile']);
const flag = (args, name) => args.includes(name);
function value(args, name) { const at = args.indexOf(name); return at >= 0 ? args[at + 1] : null; }
function positional(args) {
  const out = [];
  for (let i = 0; i < args.length; i++) {
    if (args[i].startsWith('--')) { if (VALUE_FLAGS.has(args[i])) i++; continue; }
    out.push(args[i]);
  }
  return out;
}
function text(command, result) {
  if (result?.status === 'HOLD') return `HOLD${result.reason ? `；${result.reason}` : ''}`;
  if (command === 'status') return result.text;
  if (command === 'verify') return result.ran ? `${result.ok ? '通过' : '失败'}：${result.summary}` : `计划：${result.command}`;
  if (command === 'map') return result.length ? result.map((x) => `${x.file}  ${x.lines} 行${x.exports.length ? `  ${x.exports.join(',')}` : ''}`).join('\n') : '没有代码模块';
  if (command === 'mistake') return Array.isArray(result) ? result.join('\n') || '没有相关错题' : `${result.wrote ? '已' : '会'}追加 ${result.line}`;
  if (command === 'install') return `${result.status}${result.kind ? `：${result.kind}` : ''}${result.reason ? `；${result.reason}` : ''}${result.differences?.length ? `；${result.differences.join('、')}` : ''}`;
  if (command === 'selfcheck') return `${require('../lib/limits.js').format(result.rows)}${result.tests ? `\n全测：${result.tests.ok ? '通过' : '失败'} ${result.tests.seconds.toFixed(2)}s` : ''}\n用户命令 0；内部接口 ${result.disclosure.internalInterfaces}`;
  return JSON.stringify(result);
}
function main(argv) {
  const [command, ...args] = argv;
  if (!command || command === '--help' || command === '-h') {
    console.log(`内部接口：${CLI_COMMANDS.join('、')}。用户只需用自然语言描述目标、边界和取舍。`); return command ? 0 : 1;
  }
  if (!CLI_COMMANDS.includes(command)) {
    console.error(`0.7 已移除内部命令 ${command}；代理改用 status/verify/map/mistake/install/selfcheck，用户无需运行 Harness 命令。`); return 1;
  }
  const root = path.resolve(value(args, '--target') || process.cwd()), pos = positional(args); let result;
  const writeRequiresCurrent = (command === 'verify' && flag(args, '--run')) || (command === 'mistake' && pos[0] === 'add' && flag(args, '--write'));
  if (writeRequiresCurrent && !require('../lib/install.js').verify06(root).ok) result = { status: 'HOLD', ok: false, reason: 'runtime identity 未通过，内部写接口保持零写' };
  if (!result && command === 'status') result = require('../lib/work.js').status(root);
  if (!result && command === 'verify') result = require('../lib/work.js').verify(root, { files: pos, run: flag(args, '--run'), profile: value(args, '--profile') || 'task' });
  if (!result && command === 'map') result = require('../lib/work.js').map(root, pos);
  if (!result && command === 'mistake') result = require('../lib/work.js').mistake(root, pos[0] === 'add' ? pos.slice(1).join(' ') : pos.join(' '), { add: pos[0] === 'add', write: flag(args, '--write') });
  if (!result && command === 'install') {
    const install = require('../lib/install.js');
    const extension = value(args, '--extension');
    if (extension && flag(args, '--uninstall')) result = install.uninstallExtension(root, extension, { write: flag(args, '--write') });
    else if (extension) result = install.installExtension(root, extension, { write: flag(args, '--write'), upgrade: flag(args, '--upgrade') });
    else if (flag(args, '--probe-native-pre-push')) result = install.probeNative(root, { write: flag(args, '--write') });
    else if (flag(args, '--native-pre-push')) result = install.installNative(root, { write: flag(args, '--write') });
    else if (flag(args, '--uninstall')) result = install.uninstall(root, { write: flag(args, '--write') });
    else result = install.install(root, { write: flag(args, '--write'), upgrade: flag(args, '--upgrade'), source: value(args, '--source') || undefined });
  }
  if (!result && command === 'selfcheck') result = require('../lib/limits.js').selfcheck(path.join(__dirname, '..'), { run: flag(args, '--run') });
  console.log(flag(args, '--json') ? JSON.stringify(result, null, 2) : text(command, result));
  return result?.ok === false || result?.status === 'HOLD' ? 1 : 0;
}
if (require.main === module) { try { process.exit(main(process.argv.slice(2))); } catch (error) { console.error(error.message); process.exit(1); } }
module.exports = { CLI_COMMANDS, main, positional, value };
