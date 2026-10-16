'use strict';
const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');
const io = require('./io.js');
const tree = require('./tree.js');

const RELATIVE_PATH = 'docs/harness/authorization.json';
const EXCLUDE_LINE = '/docs/harness/authorization.json';
const MAX_BYTES = 4096;
const MAX_LEASE_MS = 24 * 60 * 60 * 1000;
const CLOSED = Object.freeze({ schemaVersion: 1, authorized: false });
const CLOSED_KEYS = ['authorized', 'schemaVersion'];
const ACTIVE_KEYS = ['authorized', 'executionReceipt', 'expiresAt', 'leaf', 'schemaVersion', 'stage'];
const RECEIPT = /^u-[0-9a-f]{20}$/;

const exactKeys = (value, keys) => value && typeof value === 'object' && !Array.isArray(value)
  && Object.keys(value).sort().join(',') === [...keys].sort().join(',');
const canonicalIso = (value) => typeof value === 'string' && Number.isFinite(Date.parse(value)) && new Date(value).toISOString() === value;
function shape(value) {
  if (exactKeys(value, CLOSED_KEYS) && value.schemaVersion === 1 && value.authorized === false) return 'closed';
  if (exactKeys(value, ACTIVE_KEYS) && value.schemaVersion === 1 && value.authorized === true
    && typeof value.leaf === 'string' && value.leaf.length > 0 && !path.isAbsolute(value.leaf) && !value.leaf.split(/[\\/]/).includes('..')
    && typeof value.stage === 'string' && value.stage.length > 0 && RECEIPT.test(value.executionReceipt)
    && canonicalIso(value.expiresAt)) return 'active';
  return 'malformed';
}
function sameStat(a, b) {
  return a.dev === b.dev && a.ino === b.ino && a.size === b.size && a.mtimeNs === b.mtimeNs && a.ctimeNs === b.ctimeNs;
}
function parentSafety(root) {
  let base;
  try { base = fs.realpathSync(root); } catch { return false; }
  for (const rel of ['docs', 'docs/harness']) {
    const target = path.join(base, rel);
    try { const stat = fs.lstatSync(target); if (stat.isSymbolicLink() || !stat.isDirectory()) return false; }
    catch (error) { if (error.code === 'ENOENT') return true; return false; }
  }
  return true;
}
function read(root) {
  root = path.resolve(root); if (!parentSafety(root)) return { kind: 'unsafe' };
  const file = path.join(root, RELATIVE_PATH);
  let beforePath;
  try { beforePath = fs.lstatSync(file); }
  catch (error) { return error.code === 'ENOENT' ? { kind: 'missing' } : { kind: 'unsafe' }; }
  if (!beforePath.isFile() || beforePath.isSymbolicLink() || beforePath.size > MAX_BYTES) return { kind: 'unsafe' };
  let fd;
  try {
    fd = fs.openSync(file, fs.constants.O_RDONLY | (fs.constants.O_NOFOLLOW || 0));
    const before = fs.fstatSync(fd, { bigint: true }); if (!before.isFile() || before.size > BigInt(MAX_BYTES)) return { kind: 'unsafe' };
    const buffer = Buffer.alloc(MAX_BYTES + 1); let offset = 0;
    while (offset < buffer.length) { const count = fs.readSync(fd, buffer, offset, buffer.length - offset, null); if (!count) break; offset += count; }
    const after = fs.fstatSync(fd, { bigint: true }); if (offset > MAX_BYTES || !sameStat(before, after)) return { kind: 'unsafe' };
    let value; try { value = JSON.parse(buffer.subarray(0, offset).toString('utf8')); } catch { return { kind: 'malformed' }; }
    const kind = shape(value); return kind === 'malformed' ? { kind } : { kind, value };
  } catch { return { kind: 'unsafe' }; }
  finally { if (fd !== undefined) try { fs.closeSync(fd); } catch { /* already closed */ } }
}
function validateStop(root, input, state, chain = tree.readChain(root), now = new Date()) {
  const result = read(root); if (result.kind !== 'active' || typeof input?.stop_hook_active !== 'boolean') return { ok: false, reason: `authorization:${result.kind}` };
  const value = result.value, currentLeaf = chain.leaf ? path.relative(root, chain.leaf.file).replaceAll('\\', '/') : null;
  if (!chain.plan || !chain.health.ok || !chain.leaf || !chain.stage || value.leaf !== currentLeaf || value.stage !== chain.stage.name) return { ok: false, reason: 'authorization:chain' };
  const receipt = state?.receipt, source = state?.userPromptSubmit;
  if (!receipt || !source || source.origin !== 'user-prompt-submit' || source.receiptId !== receipt.receiptId
    || value.executionReceipt !== receipt.receiptId || receipt.project !== path.resolve(root)
    || receipt.thread !== (input.session_id || null) || receipt.turn !== (input.turn_id || null)
    || source.project !== path.resolve(root) || source.session !== (input.session_id || null) || source.turn !== (input.turn_id || null)) return { ok: false, reason: 'authorization:receipt' };
  if (!canonicalIso(state.startedAt) || !canonicalIso(value.expiresAt)) return { ok: false, reason: 'authorization:time-shape' };
  const startedAt = Date.parse(state.startedAt), expiresAt = Date.parse(value.expiresAt), at = now.getTime();
  if (startedAt > at || at >= expiresAt || expiresAt > startedAt + MAX_LEASE_MS) return { ok: false, reason: 'authorization:time-window' };
  return { ok: true, value };
}
function issue(root, input, opts = {}) {
  root = path.resolve(root); const current = read(root); if (!['missing', 'closed', 'active'].includes(current.kind)) return { ok: false, reason: `authorization:${current.kind}` };
  const state = require('./hook.js').readTurn(root, input), chain = tree.readChain(root), receipt = state?.receipt;
  if (!receipt || state?.userPromptSubmit?.origin !== 'user-prompt-submit' || receipt.project !== root
    || receipt.thread !== (input.session_id || null) || receipt.turn !== (input.turn_id || null)
    || !canonicalIso(state.startedAt) || !chain.plan || !chain.health.ok || !chain.leaf || !chain.stage) return { ok: false, reason: 'authorization:binding' };
  const expiresAt = opts.expiresAt; if (!canonicalIso(expiresAt)) return { ok: false, reason: 'authorization:expiresAt' };
  const start = Date.parse(state.startedAt), end = Date.parse(expiresAt); if (end <= Date.now() || end > start + MAX_LEASE_MS) return { ok: false, reason: 'authorization:lease' };
  const value = { schemaVersion: 1, authorized: true, leaf: path.relative(root, chain.leaf.file).replaceAll('\\', '/'), stage: chain.stage.name,
    executionReceipt: receipt.receiptId, expiresAt };
  io.atomic(path.join(root, RELATIVE_PATH), `${JSON.stringify(value, null, 2)}\n`, 0o600); return { ok: true, value };
}

function image(file) {
  let cursor = path.dirname(file), parent;
  for (;;) {
    try { const stat = fs.lstatSync(cursor); parent = { path: cursor, type: stat.isDirectory() && !stat.isSymbolicLink() ? 'directory' : 'unsafe', dev: stat.dev, ino: stat.ino, real: fs.realpathSync(cursor) }; break; }
    catch (error) { if (error.code !== 'ENOENT' || cursor === path.dirname(cursor)) throw error; cursor = path.dirname(cursor); }
  }
  try { const stat = fs.lstatSync(file); if (!stat.isFile() || stat.isSymbolicLink()) return { file, type: 'unsafe', parent }; return { file, type: 'file', mode: stat.mode & 0o777, body: fs.readFileSync(file), parent }; }
  catch (error) { if (error.code === 'ENOENT') return { file, type: 'missing', parent }; throw error; }
}
function sameImage(expected) {
  const actual = image(expected.file); return actual.type === expected.type && actual.parent.type === expected.parent.type && actual.parent.dev === expected.parent.dev
    && actual.parent.ino === expected.parent.ino && actual.parent.real === expected.parent.real
    && (actual.type === 'missing' || (actual.type === 'file' && actual.mode === expected.mode && actual.body.equals(expected.body)));
}
function samePostimage(change) {
  const actual = image(change.before.file), prior = change.expected.parent, directParent = prior.path === path.dirname(change.before.file);
  let anchor = false;
  try { const stat = fs.lstatSync(prior.path); anchor = stat.isDirectory() && !stat.isSymbolicLink() && stat.dev === prior.dev && stat.ino === prior.ino && fs.realpathSync(prior.path) === prior.real; } catch { anchor = false; }
  const expectedReal = path.resolve(prior.real, path.relative(prior.path, path.dirname(change.before.file)));
  return actual.type === 'file' && actual.mode === change.mode && actual.body.equals(Buffer.from(change.text))
    && (directParent ? (actual.parent.type === prior.type && actual.parent.dev === prior.dev && actual.parent.ino === prior.ino && actual.parent.real === prior.real)
      : anchor && actual.parent.type === 'directory' && actual.parent.path === path.dirname(change.before.file) && actual.parent.real === expectedReal);
}
function restore(value) { if (value.type === 'missing') fs.rmSync(value.file, { force: true }); else if (value.type === 'file') io.atomic(value.file, value.body, value.mode); else throw new Error('unsafe preimage'); }
function gitExclude(root) {
  const run = spawnSync('/usr/bin/git', ['rev-parse', '--path-format=absolute', '--git-path', 'info/exclude'], { cwd: root, encoding: 'utf8',
    env: { PATH: '/usr/bin:/bin', LANG: 'C', LC_ALL: 'C' } });
  return run.status === 0 && run.stdout.trim() ? path.resolve(run.stdout.trim()) : null;
}
function prepare(root, opts = {}) {
  root = path.resolve(root); const operation = opts.operation || 'install', state = read(root);
  if (operation === 'uninstall') return ['missing', 'closed'].includes(state.kind) ? { ok: true, operation, state, changes: [] } : { ok: false, reason: `authorization:${state.kind}` };
  const legacy = opts.identityKind === 'owned-05';
  if (!legacy && !['missing', 'closed'].includes(state.kind)) return { ok: false, reason: `authorization:${state.kind}` };
  if (legacy && state.kind === 'unsafe') return { ok: false, reason: 'authorization:unsafe' };
  const authFile = path.join(root, RELATIVE_PATH), before = image(authFile);
  if (!['missing', 'file'].includes(before.type)) return { ok: false, reason: 'authorization:unsafe' };
  const authChange = state.kind === 'closed' && !legacy ? null : { name: 'authorization:file', before,
    expected: legacy ? { ...before, type: 'missing', body: undefined, mode: undefined } : before,
    text: `${JSON.stringify(CLOSED, null, 2)}\n`, mode: 0o600 };
  const excludeFile = gitExclude(root); let excludeChange = null;
  if (excludeFile) {
    const exclude = image(excludeFile); if (!['missing', 'file'].includes(exclude.type) || exclude.parent.type !== 'directory') return { ok: false, reason: 'authorization:exclude-unsafe' };
    const body = exclude.type === 'file' ? exclude.body.toString('utf8') : '', lines = body.split(/\r?\n/);
    if (!lines.includes(EXCLUDE_LINE)) { const text = `${body}${body && !body.endsWith('\n') ? '\n' : ''}${EXCLUDE_LINE}\n`; excludeChange = { name: 'authorization:exclude', before: exclude, expected: exclude, text, mode: exclude.type === 'file' ? exclude.mode : 0o600 }; }
  }
  return { ok: true, operation, state, legacy, changes: [authChange, excludeChange].filter(Boolean) };
}
function apply(plan, fault = () => {}) {
  const written = [];
  try {
    for (const change of plan.changes) {
      if (!sameImage(change.expected)) throw new Error(`${change.name}:concurrent-change`);
      fault(`${change.name}:before`); if (!sameImage(change.expected)) throw new Error(`${change.name}:concurrent-change`);
      io.atomic(change.before.file, change.text, change.mode); written.push(change); fault(`${change.name}:written`);
      if (!samePostimage(change)) throw new Error(`${change.name}:postimage-concurrent-change`);
    }
    return { ok: true, wrote: written.length > 0, written };
  } catch (error) {
    const recovery = [];
    for (const change of written.reverse()) try {
      if (!samePostimage(change)) recovery.push(`${change.name}:concurrent-change`); else restore(change.before);
    } catch (restoreError) { recovery.push(`${change.name}:${restoreError.message}`); }
    return { ok: false, wrote: false, reason: recovery.length ? `${error.message};${recovery.join('|')}` : error.message, written: [] };
  }
}
function rollback(result) {
  const failures = [];
  for (const change of [...(result?.written || [])].reverse()) try {
    if (!samePostimage(change)) failures.push(`${change.name}:concurrent-change`); else restore(change.before);
  } catch (error) { failures.push(`${change.name}:${error.message}`); }
  return failures;
}

module.exports = { RELATIVE_PATH, EXCLUDE_LINE, MAX_BYTES, MAX_LEASE_MS, CLOSED, canonicalIso, shape, read, validateStop, issue, prepare, apply, rollback };
