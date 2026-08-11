'use strict';
const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');
const io = require('./io.js');
const tree = require('./tree.js');

const OWN = ['docs/harness/', '.claude/harness-lite/', '.codex/hooks.json'];
const own = (file) => OWN.some((prefix) => file === prefix.replace(/\/$/, '') || file.startsWith(prefix));
function git(root, args) {
  const result = spawnSync('git', args, { cwd: root, encoding: 'utf8', maxBuffer: 32 * 1024 * 1024 });
  return result.status === 0 ? result.stdout : null;
}
function statusPaths(root) {
  const text = git(root, ['status', '--porcelain', '-uall']);
  if (text == null) return null;
  return text.split('\n').filter(Boolean).map((line) => {
    let file = line.slice(3).trim();
    if (file.includes(' -> ')) file = file.split(' -> ').pop();
    if (file.startsWith('"') && file.endsWith('"')) { try { file = JSON.parse(file); } catch { file = file.slice(1, -1); } }
    return { path: file, xy: line.slice(0, 2) };
  });
}
function headTree(root) {
  const text = git(root, ['ls-tree', '-rz', '--full-tree', 'HEAD']); if (text == null) return {};
  const out = {};
  for (const row of text.split('\0').filter(Boolean)) { const match = row.match(/^(\d+)\s+\w+\s+([0-9a-f]+)\t([\s\S]+)$/); if (match) out[match[3]] = `${match[1]}:${match[2]}`; }
  return out;
}
function snapshot(root) {
  const rows = statusPaths(root);
  if (rows == null) return { repo: false, head: null, action: null, files: {}, tree: {}, unknown: ['git-status'] };
  const files = {}, unknown = [];
  for (const row of rows) {
    try {
      const item = io.inspect(root, row.path);
      files[row.path] = { xy: row.xy, type: item.type, mode: item.mode || null,
        digest: item.digest || (item.type === 'symlink' ? io.sha(fs.readlinkSync(item.abs)) : item.type) };
    } catch { files[row.path] = { xy: row.xy, type: 'unknown', mode: null, digest: null }; unknown.push(row.path); }
  }
  return { repo: true, head: (git(root, ['rev-parse', 'HEAD']) || '').trim() || null,
    action: (git(root, ['reflog', '-1', '--format=%gs']) || '').trim() || null, files, tree: headTree(root), unknown };
}
function delta(before, after) {
  if (!before?.repo || !after?.repo) return { changed: [], inherited: [], unknown: ['git-state'], headChanged: false };
  const changed = [], inherited = [], keys = new Set([...Object.keys(before.files), ...Object.keys(after.files)]);
  for (const key of [...keys].sort()) {
    const a = before.files[key], b = after.files[key];
    (a && b && JSON.stringify(a) === JSON.stringify(b) ? inherited : changed).push(key);
  }
  for (const key of new Set([...Object.keys(before.tree || {}), ...Object.keys(after.tree || {})])) {
    if (before.tree?.[key] !== after.tree?.[key] && !changed.includes(key)) changed.push(key);
  }
  changed.sort();
  return { changed, inherited, unknown: [...new Set([...(before.unknown || []), ...(after.unknown || [])])],
    headChanged: before.head !== after.head, beforeHead: before.head, afterHead: after.head, afterAction: after.action || null };
}
function outOfScope(files, allowed) {
  return files.filter((file) => !own(file) && !(allowed || []).some((prefix) => {
    const value = prefix.replace(/\/$/, ''); return file === value || file.startsWith(`${value}/`);
  }));
}
const clip = (items, limit = 5) => items.length > limit ? `${items.slice(0, limit).join('、')}…等${items.length}项` : items.join('、');
function report(root, data, opts = {}) {
  const chain = data.chain || tree.readChain(root), progress = tree.progress(root, chain);
  const change = data.delta || { changed: [], inherited: [], unknown: [] }, productChanges = change.changed.filter((x) => !own(x));
  const out = outOfScope(change.changed, chain.allowed), verification = data.verification;
  const carrier = change.headChanged && /merge/i.test(change.afterAction || '') ? `merged-local ${change.afterHead?.slice(0, 12)}`
    : change.headChanged && /^commit/i.test(change.afterAction || '') ? `local-commit ${change.afterHead?.slice(0, 12)}`
      : change.headChanged ? `HEAD-changed ${change.afterHead?.slice(0, 12) || 'unknown'}` : 'working-copy-only';
  const lines = [
    `Harness：${chain.stage?.title || '无 current stage'}；${progress.total} 个 leaf，完成 ${progress.done}，当前 ${chain.leaf?.title || '无'}`,
    `产品：${chain.leaf?.product || '未知；Harness 文件完成不代表产品完成'}`,
    `证据：${verification ? `${verification.ok ? '通过' : '失败'} ${verification.summary}` : chain.leaf?.evidence || '本轮没有 verify receipt'}`,
    `载体：${carrier}；pushed 未验证；已有 WIP ${change.inherited.length} 项`,
    `这轮：${productChanges.length ? clip(productChanges) : '无产品文件变化'}${change.unknown.length ? `；未知 ${clip(change.unknown)}` : ''}`,
    `判断：${data.judgment || '仅报告机器差异，不推断真实运行或发布'}`,
    `范围外：${out.length}${out.length ? `（${clip(out)}）` : ''}`,
    `下一步/阻塞：${data.next || (chain.health.ok ? '按 current leaf 继续' : chain.health.conflicts.join('；'))}`,
    ...(data.details || []).map((item) => `明细：${String(item)}`),
  ];
  const date = opts.date || new Date(), stamp = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
  const suffix = String(opts.id || 'manual').replace(/[^A-Za-z0-9._-]/g, '_').slice(0, 120);
  const file = path.join(tree.hdir(root), 'reports', `${stamp}-${suffix}.md`), text = lines.join('\n');
  if (opts.write) io.atomic(file, `${text}\n`, 0o644);
  return { file, text, lines, outOfScope: out.length, productChanges, carrier };
}
function appendUsage(root, data, opts = {}) {
  const date = opts.date || new Date(), month = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`;
  const file = path.join(tree.hdir(root), 'usage', `${month}.log`);
  const row = { at: date.toISOString(), session: data.session || '-', turn: data.turn || '-', receipt: data.receipt || null,
    events: data.events || [], files: data.files || 0, outOfScope: data.outOfScope || 0, verify: data.verify || null };
  if (opts.write) { fs.mkdirSync(path.dirname(file), { recursive: true }); fs.appendFileSync(file, `${JSON.stringify(row)}\n`); }
  return { file, text: JSON.stringify(row), row };
}
function receipt(root, id) {
  if (!id) return null;
  const usage = path.join(tree.hdir(root), 'usage'), turnRows = io.list(path.join(usage, '.turn'), false)
    .filter((file) => file.endsWith('.json')).map((file) => io.json(file, {}));
  for (const row of turnRows) if (row.receipt?.receiptId === id) return row.receipt;
  const logs = io.list(usage, false).filter((file) => file.endsWith('.log'));
  for (const file of logs) for (const line of io.read(file, '').split('\n').filter(Boolean)) {
    let row; try { row = JSON.parse(line); } catch { continue; }
    if (row.receipt?.receiptId === id) return row.receipt;
  }
  return null;
}
function latestVerify(root, since) {
  const file = path.join(tree.hdir(root), 'verify.jsonl'), text = io.read(file, '');
  const rows = text.split('\n').filter(Boolean).flatMap((line) => { try { return [JSON.parse(line)]; } catch { return []; } });
  return rows.reverse().find((row) => !since || new Date(row.at) >= new Date(since)) || null;
}
const PROFILES = new Set(['quick', 'task', 'full', 'manual']), TIMEOUT = { quick: 30000, task: 120000, full: 3600000 };
function checks(root) {
  const config = io.json(path.join(tree.hdir(root), 'checks.json'), { version: 1, checks: [] });
  if (config.version !== 1 || !Array.isArray(config.checks)) throw new Error('checks.json 格式错误');
  const ids = new Set();
  for (const check of config.checks) {
    if (!/^[a-z0-9][a-z0-9-]*$/.test(check?.id || '') || ids.has(check.id)) throw new Error('check id 缺失、重复或不合规'); ids.add(check.id);
    if (!PROFILES.has(check.profile)) throw new Error(`${check.id} profile 未知`);
    if (check.profile === 'manual') { if (typeof check.note !== 'string' || !check.note.trim() || check.argv !== undefined) throw new Error(`${check.id} manual 只能写 note`); continue; }
    if (!Array.isArray(check.argv) || !check.argv.length || check.argv.some((x) => typeof x !== 'string' || !x || x.includes('\0'))) throw new Error(`${check.id} argv 不合规`);
    if (!Number.isInteger(check.timeoutMs) || check.timeoutMs < 1 || check.timeoutMs > TIMEOUT[check.profile]) throw new Error(`${check.id} timeout 超限`);
    if (check.profile === 'task' ? !Array.isArray(check.paths) || !check.paths.length : check.paths !== undefined) throw new Error(`${check.id} paths 与 profile 不匹配`);
    for (const rel of check.paths || []) io.safe(root, rel);
  }
  return config.checks;
}
function pushArgv(argv, root) {
  const exe = path.basename(argv[0] || ''), body = argv.join(' ');
  if ((exe === 'git' && argv.slice(1).includes('push')) || /\bgit\b[\s\S]*\bpush\b/i.test(body)) return true;
  if (root && /^(?:npm|pnpm|yarn)$/.test(exe)) { const at = argv.findIndex((x) => x === 'run' || x === 'run-script'), name = at >= 0 ? argv[at + 1] : null;
    return !!name && /\bgit\b[\s\S]*\bpush\b/i.test(io.json(path.join(root, 'package.json'), {})?.scripts?.[name] || ''); }
  return false;
}
function testsFor(root, files) {
  const testRe = /\.(?:test|spec)\.[cm]?[jt]sx?$/, all = io.list(root, true).map((file) => path.relative(root, file).replaceAll('\\', '/'))
    .filter((file) => testRe.test(file) && !/(?:^|\/)(?:node_modules|dist|build|coverage|done)\//.test(file)), map = io.json(path.join(tree.hdir(root), 'test-map.json'), {}), found = new Set();
  for (const raw of files || []) {
    const file = raw.replace(/^\.\//, '').replaceAll('\\', '/'), mapped = Object.entries(map || {}).filter(([prefix]) => file === prefix.replace(/\/$/, '') || file.startsWith(`${prefix.replace(/\/$/, '')}/`)).flatMap(([, value]) => [].concat(value));
    if (testRe.test(file)) found.add(file);
    for (const target of mapped) for (const test of all) if (test === target || test.startsWith(`${String(target).replace(/\/$/, '')}/`)) found.add(test);
    const stem = path.posix.basename(file).replace(/\.[^.]+$/, ''); for (const test of all) if (path.posix.basename(test).replace(testRe, '') === stem) found.add(test);
  }
  return [...found].sort();
}
function verify(root, args = {}) {
  const profile = args.profile || 'task'; if (!PROFILES.has(profile)) throw new Error(`未知 profile ${profile}`);
  const files = args.files || [], seen = new Set(), selected = checks(root).filter((check) => check.profile === profile && (profile !== 'task'
    || files.some((file) => check.paths.some((prefix) => file === prefix.replace(/\/$/, '') || file.startsWith(`${prefix.replace(/\/$/, '')}/`)))))
    .filter((check) => { const key = JSON.stringify(check.argv || [check.id]); if (seen.has(key)) return false; seen.add(key); return true; });
  const selectedTests = testsFor(root, files);
  if (profile === 'manual') return { ran: false, profile, selected: selected.map((x) => x.id), selectedTests, notes: selected.map((x) => ({ id: x.id, note: x.note })), command: '人工检查不自动执行' };
  if (!args.run) return { ran: false, profile, selected: selected.map((x) => x.id), selectedTests, command: selected.map((x) => x.argv.join(' ')).join(' && ') || (selectedTests.length ? `npm test -- ${selectedTests.join(' ')}` : '无登记检查') };
  const results = selected.map((check) => {
    if (pushArgv(check.argv, root)) return { id: check.id, ok: false, status: null, blocked: 'push-only-gate' };
    const run = spawnSync(check.argv[0], check.argv.slice(1), { cwd: root, shell: false, encoding: 'utf8', timeout: check.timeoutMs });
    return { id: check.id, ok: !run.error && run.status === 0, status: run.status,
      summary: String(run.stdout || run.stderr || '').trim().split('\n').slice(-1)[0]?.slice(0, 160) || `exit ${run.status}` };
  });
  const receipt = { at: new Date().toISOString(), profile, selectedTests, ok: results.every((x) => x.ok), ids: results.map((x) => x.id),
    summary: results.map((x) => `${x.id}:${x.ok ? 'pass' : 'fail'}`).join(',') || 'no checks', results };
  const file = path.join(tree.hdir(root), 'verify.jsonl'); fs.mkdirSync(path.dirname(file), { recursive: true }); fs.appendFileSync(file, `${JSON.stringify(receipt)}\n`);
  return { ran: true, ...receipt };
}
function usageSummary(root) {
  const now = new Date(), month = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
  const rows = io.read(path.join(tree.hdir(root), 'usage', `${month}.log`), '').split('\n').filter(Boolean).flatMap((line) => { try { return [JSON.parse(line)]; } catch { return []; } });
  return { turns: rows.length, files: rows.reduce((sum, row) => sum + Number(row.files || 0), 0), lastVerify: rows.at(-1)?.verify || null };
}
function map(root, dirs = []) {
  const bases = dirs.length ? dirs.map((dir) => io.safe(root, dir)) : ['src', 'lib', 'bin', 'hooks'].map((dir) => path.join(root, dir));
  return bases.flatMap((base) => io.list(base, true)).filter((file) => /\.(?:js|ts|py|rs|go)$/.test(file) && !/[/\\](?:test|tests|node_modules)[/\\]/.test(file))
    .map((file) => ({ file: path.relative(root, file).replaceAll('\\', '/'), lines: io.read(file, '').split('\n').length,
      exports: [...io.read(file, '').matchAll(/(?:module\.exports\s*=|export\s+(?:function|class|const)\s+)([A-Za-z0-9_]*)/g)].map((m) => m[1]).filter(Boolean) })).slice(0, 40);
}
function mistake(root, text, opts = {}) {
  const file = path.join(tree.hdir(root), 'MISTAKES.md'), body = io.read(file, '');
  if (!opts.add) return body.split('\n').filter((line) => line.startsWith('- ') && (!text || line.toLowerCase().includes(text.toLowerCase())));
  const value = String(text || '').replace(/\s+/g, ' ').trim(); if (!value) throw new Error('错题内容为空');
  const line = `- ${new Date().toISOString().slice(0, 10)} ${value}`;
  if (opts.write) { fs.mkdirSync(path.dirname(file), { recursive: true }); fs.appendFileSync(file, `${body ? '' : '# 错题本\n\n'}${line}\n`); }
  return { wrote: !!opts.write, line, file };
}
function status(root) {
  const chain = tree.readChain(root), snap = snapshot(root), health = (() => { try { return require('./install.js').health(root); } catch { return {}; } })(), usage = usageSummary(root);
  return { chain, progress: tree.progress(root, chain), git: { repo: snap.repo, head: snap.head, dirty: Object.keys(snap.files) }, usage, health,
    text: `${tree.format(chain)}\nUsage：${usage.turns} 轮，${usage.files} 个产品文件\nRuntime：${JSON.stringify(health)}` };
}

module.exports = { OWN, own, git, statusPaths, snapshot, delta, outOfScope, report, appendUsage, receipt, latestVerify, checks, pushArgv, testsFor, verify, usageSummary, map, mistake, status };
