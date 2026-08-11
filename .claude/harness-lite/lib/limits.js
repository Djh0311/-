'use strict';
const path = require('path');
const io = require('./io.js');

const lines = (file) => { const text = io.read(file, ''); return text ? text.replace(/\n$/, '').split('\n').length : 0; };
function files(dir, ext) { return io.list(dir, true).filter((file) => file.endsWith(ext) && !file.includes(`${path.sep}fixtures${path.sep}`)); }
function check(root) {
  const implementation = ['lib', 'bin', 'hooks', 'scripts'].flatMap((dir) => files(path.join(root, dir), '.js'));
  const skills = files(path.join(root, 'skills'), '.md').concat(files(path.join(root, 'extensions'), '.md'));
  const used = (list) => list.reduce((sum, file) => sum + lines(file), 0);
  const cliSource = io.read(path.join(root, 'bin', 'hl.js'), '');
  const commandList = (cliSource.match(/const CLI_COMMANDS = \[([^\]]+)\]/) || [])[1] || '';
  const interfaces = [...commandList.matchAll(/'([^']+)'/g)].length;
  return [
    { name: '实现', used: used(implementation) },
    { name: '测试', used: used(files(path.join(root, 'test'), '.js')) },
    { name: '技能', used: used(skills) },
    { name: '报告模板', used: lines(path.join(root, 'templates', 'report.md')) },
    { name: '内部接口', used: interfaces, target: 6 },
  ];
}
const format = (rows) => rows.map((row) => `${row.name} ${row.used}${row.target ? `（目标 ${row.target}）` : ''}`).join('\n');
function selfcheck(root, opts = {}) {
  const rows = check(root), started = Date.now(); let tests = null;
  if (opts.run) {
    const run = require('child_process').spawnSync(process.execPath, ['scripts/timed-test.js'], { cwd: root, encoding: 'utf8', timeout: 300000 });
    tests = { ok: !run.error && run.status === 0, status: run.status, output: `${run.stdout || ''}${run.stderr || ''}`.trim(), seconds: (Date.now() - started) / 1000 };
  }
  return { ok: rows.find((row) => row.name === '内部接口').used === 6 && (!tests || tests.ok), rows, tests,
    disclosure: { userCommands: 0, internalInterfaces: 6, executableCli: 1, codexDispatcher: 1, packageScripts: 2, note: '行数与耗时只作趋势披露，不作发布硬门' } };
}

module.exports = { lines, check, format, selfcheck };
