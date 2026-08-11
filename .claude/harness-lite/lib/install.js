'use strict';
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');
const io = require('./io.js');

const VERSION = '0.7.0';
const SOURCE_COMMIT = 'working-copy:640ad4d0d81828cd80bfee9ff6be6c87d20a7aa6';
const RUNTIME = '.claude/harness-lite';
const MANIFEST = `${RUNTIME}/ownership.json`;
const EVENTS = ['SessionStart', 'UserPromptSubmit', 'Stop', 'PreToolUse'];
const OWNED05_REQUIRED = `bin/hl.js hooks/README.md hooks/pre-push.js hooks/session-start.js hooks/stop.js hooks/user-prompt.js lib/authorization.js lib/checks.js lib/close-stage.js lib/done.js lib/extensions.js lib/gate.js lib/git-pre-push.js lib/gitfacts.js lib/hookio.js lib/leaf.js lib/lifecycle.js lib/limits.js lib/map.js lib/mistakes.js lib/ownership.js lib/report.js lib/tests-pick.js lib/tree.js lib/usage.js skills/root-cause.md skills/split-work.md skills/test-first.md settings-snippet.json`.split(' ').map((x) => `${RUNTIME}/${x}`).concat('.codex/harness-lite/hooks-snippet.json');
const LEGACY_CONTROL = ['.codex/harness-lite/hooks-snippet.json', 'docs/harness/policy.json', 'docs/harness/authorization.json', 'docs/harness/authorization.example.json', 'docs/harness/templates/leaf.md', 'docs/harness/templates/report.md'];
const PREVIOUS_06_INSTRUCTION = `<!-- HARNESS-LITE:BEGIN -->
Harness Lite 内部规则：用户用清晰自然语言给目标和边界，直接生效；用户日常命令为 0。读取 docs/harness/ 的 plan、唯一 current leaf 及其 stage；清晰新目标且没有 current leaf 时，由模型直接创建最小 stage/leaf 并引用本轮 Hook 来源收据，不让用户操作内部状态。非 push 偏差只报告；push 使用精确一次性确认。文件位置是生命周期事实；退场只原子移动一个文件。报告必须分 Harness、产品、证据、载体，不把 working copy 或离线 fixture 冒充发布或真实运行。
<!-- HARNESS-LITE:END -->`;
const OFFICIAL_06 = Object.freeze({
  runtimeVersion: '0.6.0', sourceCommit: 'working-copy:640ad4d0d81828cd80bfee9ff6be6c87d20a7aa6',
  packageDigest: 'sha256:2f644436a6d69af6ed51ca007f250df1daa0a1a39c7bb43726d69226bc338b92',
  instructionBlockDigest: 'sha256:ff7591b87500d31e2fc1400052db4c1e10efb396db881e52642a6ca73f900b4c',
  managedPaths: Object.freeze(['bin/hl.js', 'hooks/README.md', 'hooks/dispatcher.js', 'lib/hook.js', 'lib/install.js', 'lib/io.js', 'lib/limits.js', 'lib/tree.js', 'lib/work.js', 'skills/root-cause.md', 'skills/split-work.md', 'skills/test-first.md']),
});
const INSTRUCTION = `<!-- HARNESS-LITE:BEGIN -->
Harness Lite 内部规则：用户用清晰自然语言给目标和边界，直接生效；用户日常命令为 0。读取 docs/harness/ 的 plan、唯一 current leaf 及其 stage；leaf 是模型维护的工作投影，不是授权票或范围最高权威。发现仍服务同一目标的必要相邻路径，模型更新 leaf 并继续；按当前目标影响、后果、可信可能和直接证据做最小处理，低概率低影响理论问题只报告。普通 leaf 范围外只报告；明确“不许动”的路径和 push 按既有停点处理。文件位置是生命周期事实；退场只原子移动一个文件。报告必须分 Harness、产品、证据、载体，不把 working copy 或离线 fixture 冒充发布或真实运行。
<!-- HARNESS-LITE:END -->`;

const sourceRoot = () => path.join(__dirname, '..');
function runtimePaths(source = sourceRoot()) {
  return ['bin', 'hooks', 'lib', 'skills'].flatMap((dir) => io.list(path.join(source, dir), true))
    .filter((file) => fs.lstatSync(file).isFile()).map((file) => path.relative(source, file).replaceAll('\\', '/')).sort();
}
const desiredMode = (rel) => rel === 'bin/hl.js' || rel === 'hooks/dispatcher.js' ? 0o755 : 0o644;
function canonical(value) {
  if (Array.isArray(value)) return value.map(canonical);
  if (value && typeof value === 'object') return Object.fromEntries(Object.keys(value).sort().map((key) => [key, canonical(value[key])]));
  return value;
}
function samePath(a, b) { try { return fs.realpathSync(a) === fs.realpathSync(b); } catch { return path.resolve(a) === path.resolve(b); } }
function unsafeParent(root, file) {
  let cursor = path.resolve(root); for (const part of path.relative(root, path.dirname(file)).split(path.sep).filter(Boolean)) {
    cursor = path.join(cursor, part); try { const stat = fs.lstatSync(cursor); if (stat.isSymbolicLink() || !stat.isDirectory()) return cursor; } catch (error) { if (error.code !== 'ENOENT') throw error; }
  } return null;
}
function hookConfigRoot(root) {
  const result = spawnSync('git', ['worktree', 'list', '--porcelain'], { cwd: root, encoding: 'utf8' });
  if (result.status !== 0) return path.resolve(root);
  const first = result.stdout.split('\n').find((line) => line.startsWith('worktree '));
  return first ? path.resolve(first.slice(9).trim()) : path.resolve(root);
}
function definition(root) {
  const command = `node "$(git rev-parse --show-toplevel)/${RUNTIME}/hooks/dispatcher.js"`;
  const handler = (timeout, canAddContext = true) => ({ type: 'command', command, timeout,
    ...(canAddContext ? { additionalContextLimit: 1800 } : {}) });
  const config = { description: 'Harness Lite 0.7 lifecycle hooks', hooks: {
    SessionStart: [{ matcher: 'startup|resume|clear|compact', hooks: [handler(15)] }],
    UserPromptSubmit: [{ hooks: [handler(10)] }],
    Stop: [{ hooks: [handler(30, false)] }],
    PreToolUse: [{ matcher: '^Bash$', hooks: [handler(10)] }],
  } };
  return { config, digest: `sha256:${io.sha(JSON.stringify(canonical(config.hooks)))}`, command };
}
function manifest(root, staged, source = sourceRoot()) {
  const managedPaths = runtimePaths(source), def = definition(root);
  return { runtimeVersion: VERSION, sourceCommit: SOURCE_COMMIT, managedPaths,
    packageDigest: io.digest(staged, managedPaths), hookDefinitionDigest: def.digest,
    instructionBlockDigest: `sha256:${io.sha(INSTRUCTION)}`, extensions: {} };
}
function runtimeProbe(root, runtime, operation) {
  const script = operation === 'definition'
    ? "const api=require(process.argv[1]);process.stdout.write(JSON.stringify({digest:api.definition(process.argv[2]).digest}))"
    : "const api=require(process.argv[1]);const value=api.verify06(process.argv[2]);process.stdout.write(JSON.stringify(value));process.exit(value.ok?0:1)";
  const run = spawnSync(process.execPath, ['-e', script, path.join(runtime, 'lib', 'install.js'), root], { encoding: 'utf8' });
  let value = null; try { value = JSON.parse(run.stdout || 'null'); } catch { /* malformed probe is a failure */ }
  return { ok: run.status === 0 && !!value, value, reason: String(run.stderr || run.stdout || `runtime ${operation} probe failed`).trim() };
}
function actualRuntimeFiles(runtime) {
  return io.list(runtime, true).map((file) => path.relative(runtime, file).replaceAll('\\', '/'))
    .filter((rel) => rel !== 'ownership.json' && !rel.startsWith('extensions/')).sort();
}
function verify06(root) {
  const runtime = path.join(root, RUNTIME), value = io.json(path.join(root, MANIFEST));
  if (!value || value.runtimeVersion !== VERSION || !Array.isArray(value.managedPaths)) return { ok: false, kind: 'not-current', differences: ['ownership.json'] };
  const actual = actualRuntimeFiles(runtime), expected = [...value.managedPaths].sort(), differences = [];
  const def = definition(root), allowedHookDefinitions = new Set([def.digest, previous06Digest(def)]);
  if (!allowedHookDefinitions.has(value.hookDefinitionDigest)) differences.push('hookDefinitionDigest');
  for (const rel of expected) { const type = io.inspect(runtime, rel).type; if (type !== 'file') differences.push(`${type}:${rel}`); }
  for (const rel of actual.filter((x) => !expected.includes(x))) differences.push(`extra:${rel}`);
  let digest = null; try { digest = io.digest(runtime, expected); } catch (error) { differences.push(`identity:${error.message}`); }
  if (digest !== value.packageDigest) differences.push('packageDigest');
  const extensions = value.extensions;
  if (!extensions || typeof extensions !== 'object' || Array.isArray(extensions)) differences.push('extensions-ledger');
  else {
    const claimed = new Set();
    for (const [id, spec] of Object.entries(extensions)) {
      if (!/^[a-z0-9][a-z0-9-]*$/.test(id) || !spec || typeof spec !== 'object' || !spec.packageVersion
        || !Array.isArray(spec.managedPaths) || !/^sha256:[0-9a-f]{64}$/.test(spec.packageDigest || '')) { differences.push(`extension-schema:${id}`); continue; }
      const paths = [...spec.managedPaths].sort(), prefix = `extensions/${id}/`;
      if (!paths.length || paths.some((rel) => typeof rel !== 'string' || !rel.startsWith(prefix) || claimed.has(rel))) { differences.push(`extension-paths:${id}`); continue; }
      for (const rel of paths) { claimed.add(rel); const type = io.inspect(runtime, rel).type; if (type !== 'file') differences.push(`extension-${type}:${rel}`); }
      let extensionDigest = null; try { extensionDigest = io.digest(runtime, paths); } catch (error) { differences.push(`extension-identity:${id}:${error.message}`); }
      if (extensionDigest !== spec.packageDigest) differences.push(`extension-packageDigest:${id}`);
    }
    const physical = io.list(path.join(runtime, 'extensions'), true).map((file) => path.relative(runtime, file).replaceAll('\\', '/')).sort();
    for (const rel of physical.filter((item) => !claimed.has(item))) differences.push(`extension-extra:${rel}`);
  }
  return { ok: differences.length === 0, kind: differences.length ? 'drift' : 'current', differences, manifest: value, digest };
}
function verifyOfficial06(root) {
  const runtime = path.join(root, RUNTIME), value = io.json(path.join(root, MANIFEST));
  if (!value || value.runtimeVersion !== OFFICIAL_06.runtimeVersion || !Array.isArray(value.managedPaths)) {
    return { ok: false, kind: 'drift', differences: ['ownership.json'] };
  }
  const expected = [...OFFICIAL_06.managedPaths], actual = actualRuntimeFiles(runtime), differences = [];
  if (value.sourceCommit !== OFFICIAL_06.sourceCommit) differences.push('sourceCommit');
  if (JSON.stringify([...value.managedPaths].sort()) !== JSON.stringify(expected)) differences.push('managedPaths');
  if (value.packageDigest !== OFFICIAL_06.packageDigest) differences.push('packageDigest');
  if (value.instructionBlockDigest !== OFFICIAL_06.instructionBlockDigest) differences.push('instructionBlockDigest');
  if (value.hookDefinitionDigest !== definition(root).digest) differences.push('hookDefinitionDigest');
  if (!value.extensions || typeof value.extensions !== 'object' || Array.isArray(value.extensions) || Object.keys(value.extensions).length) differences.push('extensions');
  for (const rel of expected) { const type = io.inspect(runtime, rel).type; if (type !== 'file') differences.push(`${type}:${rel}`); }
  for (const rel of actual.filter((x) => !expected.includes(x))) differences.push(`extra:${rel}`);
  let digest = null; try { digest = io.digest(runtime, expected); } catch (error) { differences.push(`identity:${error.message}`); }
  if (digest !== OFFICIAL_06.packageDigest) differences.push('official-packageDigest');
  return { ok: differences.length === 0, kind: differences.length ? 'drift' : 'official-06', differences, manifest: value, digest };
}
function verifyOwned05(root, value) {
  const pkg = value?.version === 1 && value.managedBy === 'harness-lite' && value.packages?.core;
  if (!pkg || pkg.packageVersion !== '0.5.0' || !pkg.files || typeof pkg.files !== 'object') return { ok: false, kind: 'hybrid', differences: ['legacy-manifest-shape'] };
  const differences = [];
  for (const rel of OWNED05_REQUIRED) if (!(rel in pkg.files)) differences.push(`unowned:${rel}`);
  for (const [rel, expected] of Object.entries(pkg.files)) {
    const item = io.inspect(root, rel);
    if (item.type !== 'file') differences.push(`${item.type}:${rel}`);
    else if (item.digest !== expected) differences.push(`content:${rel}`);
  }
  const recorded = Object.keys(pkg.files).filter((rel) => rel.startsWith(`${RUNTIME}/`) && rel !== MANIFEST).map((rel) => rel.slice(RUNTIME.length + 1));
  const actual = actualRuntimeFiles(path.join(root, RUNTIME));
  for (const rel of actual.filter((x) => !recorded.includes(x) && x !== 'settings-snippet.json')) differences.push(`extra:${rel}`);
  return { ok: differences.length === 0, kind: differences.length ? 'hybrid' : 'owned-05', differences, manifest: value };
}
function legacyUnowned(root) {
  const runtime = path.join(root, RUNTIME), actual = actualRuntimeFiles(runtime);
  const items = actual.map((rel) => io.inspect(runtime, rel));
  const anomalies = new Set(items.filter((item) => item.type !== 'file').map((item) => `${item.type}:${item.path}`));
  const rows = items.slice(0, 50).map((item) => `${item.type}:${item.mode || '-'}:${item.path}`);
  if (items.length > 50) rows.push(`…等${items.length}项`);
  let rootDigest = null;
  try { rootDigest = io.digest(runtime, items.filter((item) => item.type === 'file').map((item) => item.path)); } catch { /* 只读诊断允许缺失 */ }
  return { ok: false, kind: 'legacy-unowned', differences: rows, evidence: { files: items.length, anomalies: [...anomalies], rootDigest } };
}
function inspect(root, source = sourceRoot()) {
  const runtime = path.join(root, RUNTIME), stat = (() => { try { return fs.lstatSync(runtime); } catch { return null; } })();
  if (!stat) return { ok: true, kind: 'fresh', differences: [] };
  if (!stat.isDirectory() || stat.isSymbolicLink()) return { ok: false, kind: 'drift', differences: [`type:${RUNTIME}`] };
  const value = io.json(path.join(root, MANIFEST));
  if (!value) return legacyUnowned(root);
  if (value.runtimeVersion === VERSION) return verify06(root);
  if (value.runtimeVersion === OFFICIAL_06.runtimeVersion) return verifyOfficial06(root);
  if (value.runtimeVersion) return { ok: false, kind: 'drift', differences: ['runtimeVersion'] };
  return verifyOwned05(root, value);
}
function surfacePreflight(root) {
  const configRoot = hookConfigRoot(root), dirs = ['.claude', 'docs', 'docs/harness', 'docs/harness/archive', 'docs/harness/archive/legacy-0.5', ...['stages', 'leaves', 'unfinished', 'done', 'reports', 'usage'].map((x) => `docs/harness/${x}`), '.codex'];
  const files = ['AGENTS.md', 'CLAUDE.md', 'docs/harness/plan.md', 'docs/harness/MISTAKES.md'];
  if (path.resolve(configRoot) === path.resolve(root)) files.push('.codex/hooks.json'); else {
    const item = io.inspect(configRoot, '.codex'); if (item.type !== 'missing' && item.type !== 'directory') return [`${item.type}:${item.path}`];
    const hookFile = io.inspect(configRoot, '.codex/hooks.json'); if (hookFile.type !== 'missing' && hookFile.type !== 'file') return [`${hookFile.type}:${hookFile.path}`];
  }
  const differences = [];
  for (const rel of dirs) { const item = io.inspect(root, rel); if (item.type !== 'missing' && item.type !== 'directory') differences.push(`${item.type}:${rel}`); }
  for (const rel of files) { const item = io.inspect(root, rel); if (item.type !== 'missing' && item.type !== 'file') differences.push(`${item.type}:${rel}`); }
  return differences;
}
function stage(root, source, fault = () => {}) {
  const parent = path.join(root, '.claude'); fs.mkdirSync(parent, { recursive: true });
  const dir = path.join(parent, `.harness-lite.stage-${process.pid}-${Date.now()}`); fs.mkdirSync(dir, { mode: 0o700 });
  try {
    for (const rel of runtimePaths(source)) {
      const dest = path.join(dir, rel); fs.mkdirSync(path.dirname(dest), { recursive: true });
      fs.copyFileSync(path.join(source, rel), dest); fs.chmodSync(dest, desiredMode(rel)); fault(`stage:${rel}`);
    }
    const value = manifest(root, dir, source); fs.writeFileSync(path.join(dir, 'ownership.json'), `${JSON.stringify(value, null, 2)}\n`, { mode: 0o600 });
    fault('stage:manifest');
    const check = { ...value, packageDigest: io.digest(dir, value.managedPaths) };
    if (check.packageDigest !== value.packageDigest) throw new Error('stage digest mismatch');
    const ownDefinition = runtimeProbe(root, dir, 'definition');
    if (!ownDefinition.ok || ownDefinition.value.digest !== value.hookDefinitionDigest) throw new Error(`staged Hook definition mismatch${ownDefinition.reason ? `: ${ownDefinition.reason}` : ''}`);
    return { dir, manifest: value };
  } catch (error) { fs.rmSync(dir, { recursive: true, force: true }); throw error; }
}
function swap(root, built, current, fault = () => {}) {
  const stable = path.join(root, RUNTIME), rollback = path.join(root, '.claude', `.harness-lite.rollback-${Date.now()}`);
  let oldMoved = false, newMoved = false;
  try {
    if (current) { fs.renameSync(stable, rollback); oldMoved = true; fault('swap:old'); }
    fs.renameSync(built.dir, stable); newMoved = true; fault('swap:new');
    const verified = verify06(root); if (!verified.ok) throw new Error(`post-swap ${verified.differences.join(',')}`);
    const self = runtimeProbe(root, stable, 'verify'); if (!self.ok) throw new Error(`installed runtime self-verify failed: ${self.reason}`);
    fault('swap:verified'); return { rollback: oldMoved ? rollback : null, verified };
  } catch (error) {
    const failed = path.join(root, '.claude', `.harness-lite.failed-${Date.now()}`);
    try { if (newMoved && fs.existsSync(stable)) fs.renameSync(stable, failed); } catch { /* recovery path reported */ }
    try { if (oldMoved && fs.existsSync(rollback) && !fs.existsSync(stable)) fs.renameSync(rollback, stable); } catch { /* recovery path reported */ }
    try { if (fs.existsSync(built.dir)) fs.rmSync(built.dir, { recursive: true, force: true }); } catch { /* original error */ }
    error.recovery = { rollback, failed }; throw error;
  }
}
const harnessishCommand = (handler) => typeof handler?.command === 'string' && /(?:^|[\s"'\\/])\.claude[\\/]harness-lite[\\/]hooks[\\/]/.test(handler.command);
const LEGACY_HOOK = { SessionStart: ['session-start.js', 15], UserPromptSubmit: ['user-prompt.js', 10], Stop: ['stop.js', 30], PreToolUse: ['pre-push.js', 10] };
const hookGroupKey = (group) => JSON.stringify(canonical(group));
function previous06Stop(expected) {
  const group = JSON.parse(JSON.stringify(expected.config.hooks.Stop[0]));
  group.hooks[0].additionalContextLimit = 1800;
  return group;
}
function previous06Digest(expected) {
  const hooks = JSON.parse(JSON.stringify(expected.config.hooks)); hooks.Stop[0] = previous06Stop(expected);
  return `sha256:${io.sha(JSON.stringify(canonical(hooks)))}`;
}
function isExactPrevious06(data, expected) {
  return EVENTS.every((event) => {
    const groups = (Array.isArray(data.hooks?.[event]) ? data.hooks[event] : [])
      .filter((group) => Array.isArray(group?.hooks) && group.hooks.some(harnessishCommand));
    const wanted = event === 'Stop' ? previous06Stop(expected) : expected.config.hooks[event][0];
    return groups.length === 1 && hookGroupKey(groups[0]) === hookGroupKey(wanted);
  });
}
function hookGroupKind(event, group, expected, allowPrevious06 = false, definitionExpected = null, legacyRoot = null) {
  const key = hookGroupKey(group);
  if (key === hookGroupKey(expected)) return 'current';
  if (allowPrevious06 && event === 'Stop' && key === hookGroupKey(previous06Stop(definitionExpected))) return 'previous';
  const handlers = group?.hooks || [], legacy = LEGACY_HOOK[event], handler = handlers[0], keys = handler ? Object.keys(handler).sort().join(',') : '';
  const legacyCommand = legacyRoot && legacy ? `node ${JSON.stringify(path.join(legacyRoot, RUNTIME, 'hooks', legacy[0]))}${event === 'PreToolUse' ? ' --surface codex' : ''}` : null;
  if (legacyCommand && handlers.length === 1 && !group.matcher && Object.keys(group).sort().join(',') === 'hooks' && keys === 'command,timeout,type'
    && handler.type === 'command' && handler.timeout === legacy[1] && handler.command === legacyCommand) return 'legacy';
  return handlers.some(harnessishCommand) ? 'unknown' : 'external';
}
function fileImage(file) {
  let cursor = path.dirname(file), parent;
  for (;;) {
    try { const stat = fs.lstatSync(cursor); parent = { path: cursor, type: stat.isDirectory() && !stat.isSymbolicLink() ? 'directory' : 'unsafe', dev: stat.dev, ino: stat.ino, real: fs.realpathSync(cursor) }; break; }
    catch (error) { if (error.code !== 'ENOENT' || cursor === path.dirname(cursor)) throw error; cursor = path.dirname(cursor); }
  }
  try {
    const stat = fs.lstatSync(file); if (!stat.isFile() || stat.isSymbolicLink()) return { file, type: 'unsafe', parent };
    return { file, type: 'file', mode: stat.mode & 0o777, body: fs.readFileSync(file), parent };
  } catch (error) { if (error.code === 'ENOENT') return { file, type: 'missing', parent }; throw error; }
}
function sameImage(expected) {
  const actual = fileImage(expected.file), parent = actual.parent, prior = expected.parent;
  return actual.type === expected.type && parent.type === prior.type && parent.dev === prior.dev && parent.ino === prior.ino && parent.real === prior.real
    && (actual.type === 'missing' || (actual.type === 'file' && actual.mode === expected.mode && actual.body.equals(expected.body)));
}
function restoreImage(image) {
  if (image.type === 'missing') { fs.rmSync(image.file, { force: true }); return; }
  if (image.type !== 'file') throw new Error(`不能恢复非普通文件：${image.file}`);
  io.atomic(image.file, image.body, image.mode);
}
function writeHookPlan(plan, fault = () => {}) {
  const { file, before, text, mode, digest, preimage } = plan;
  if (!sameImage(preimage)) return { ok: false, status: 'HOLD', wrote: false, reason: 'Hook 配置或父目录在 preflight 后发生变化', file };
  if (text === before) return { ok: true, wrote: false, file, digest };
  try { fault('hooks:before'); } catch (error) { return { ok: false, status: 'HOLD', wrote: false, reason: error.message, file }; }
  if (!sameImage(preimage)) return { ok: false, status: 'HOLD', wrote: false, reason: 'Hook 配置或父目录在写入前发生变化', file };
  try {
    io.atomic(file, text, mode); fault('hooks:written');
    if (fs.readFileSync(file, 'utf8') !== text) throw new Error('hooks verify failed'); fault('hooks:verified');
    return { ok: true, wrote: true, file, digest };
  } catch (error) {
    let recovery = null;
    try { restoreImage(preimage); } catch (restore) { recovery = restore.message; }
    return { ok: false, status: 'HOLD', wrote: false, reason: recovery ? `${error.message}；Hook preimage 恢复失败：${recovery}` : error.message, file };
  }
}
function mergeHooks(root, opts = {}) {
  const identity = inspect(root);
  if (!['fresh', 'current', 'official-06', 'owned-05'].includes(identity.kind)) {
    return { ok: false, status: 'HOLD', reason: 'runtime identity 不允许 Hook 配置写入', file: path.join(hookConfigRoot(root), '.codex', 'hooks.json') };
  }
  const configRoot = hookConfigRoot(root), file = path.join(configRoot, '.codex', 'hooks.json'), expected = definition(root);
  const present = fs.existsSync(file), before = present ? fs.readFileSync(file, 'utf8') : null;
  let data = present ? io.json(file) : { description: 'Project hooks', hooks: {} };
  if (!data || !data.hooks || Array.isArray(data.hooks)) return { ok: false, status: 'HOLD', reason: 'invalid .codex/hooks.json', file };
  data = JSON.parse(JSON.stringify(data));
  const previous = identity.kind === 'current' && isExactPrevious06(data, expected)
    && [expected.digest, previous06Digest(expected)].includes(identity.manifest?.hookDefinitionDigest);
  const legacyRoot = identity.kind === 'owned-05' ? root : null;
  const malformed = Object.entries(data.hooks).filter(([, groups]) => !Array.isArray(groups) || groups.some((group) => !group || !Array.isArray(group.hooks)));
  if (malformed.length) return { ok: false, status: 'HOLD', reason: `invalid hook groups: ${malformed.map(([event]) => event).join(',')}`, file };
  const unknown = Object.entries(data.hooks).flatMap(([event, groups]) => groups
    .filter((group) => hookGroupKind(event, group, expected.config.hooks[event]?.[0], previous, expected, legacyRoot) === 'unknown').map((group) => `${event}:${group.hooks.map((x) => x.command).join('|')}`));
  if (unknown.length) return { ok: false, status: 'HOLD', reason: `unknown Harness hook: ${unknown.join(',')}`, file };
  for (const event of EVENTS) {
    const groups = Array.isArray(data.hooks[event]) ? data.hooks[event] : [];
    data.hooks[event] = groups.filter((group) => !['current', 'previous', 'legacy'].includes(hookGroupKind(event, group, expected.config.hooks[event][0], previous, expected, legacyRoot)));
    data.hooks[event].push(expected.config.hooks[event][0]);
  }
  const text = `${JSON.stringify(data, null, 2)}\n`;
  const preimage = fileImage(file); if (!['file', 'missing'].includes(preimage.type) || preimage.parent.type !== 'directory') return { ok: false, status: 'HOLD', reason: 'Hook 配置路径不是安全普通文件', file };
  const plan = { file, before, text, mode: present ? fs.statSync(file).mode & 0o777 : 0o600, digest: expected.digest, preimage };
  if (opts.write) return writeHookPlan(plan, opts.fault);
  return { ok: true, wrote: false, file, digest: expected.digest, plan };
}
const OLD_INSTRUCTIONS = {
  'AGENTS.md': new Set(['4417f9dd90075b53b668c8cab24610d112ba40e8a17741904435f22ecea7cfb4', '80d945a4ecaf76dde35d1a89e1aa624ea5504b703cda485ed7b227697c054128']),
  'CLAUDE.md': new Set(['b7ca0575486c601cc1fc90460c7946e3068733f4e9e0cd2eed47b8f494564162']),
};
function instructionPlan(root) {
  const rows = [], re = /<!-- HARNESS-LITE:BEGIN -->[\s\S]*?<!-- HARNESS-LITE:END -->/;
  for (const name of ['AGENTS.md', 'CLAUDE.md']) {
    const file = path.join(root, name), before = io.read(file, ''), block = before.match(re)?.[0], digest = io.sha(before);
    if (block && ![INSTRUCTION, PREVIOUS_06_INSTRUCTION].includes(block)) return { ok: false, reason: `unknown Harness instruction edit: ${name}`, rows };
    if (!block && /Harness Lite|HARNESS-AUTHORIZATION|hl (?:done|park|auth|chain)/i.test(before) && !OLD_INSTRUCTIONS[name].has(digest)) {
      return { ok: false, reason: `unknown legacy Harness instruction: ${name}`, rows };
    }
    const text = block ? before.replace(block, INSTRUCTION) : OLD_INSTRUCTIONS[name].has(digest) ? `${INSTRUCTION}\n`
      : `${before}${before && !before.endsWith('\n') ? '\n' : ''}${before ? '\n' : ''}${INSTRUCTION}\n`;
    rows.push({ file, before, text, changed: text !== before, existed: fs.existsSync(file), mode: fs.existsSync(file) ? fs.statSync(file).mode & 0o777 : 0o644 });
  }
  return { ok: true, rows };
}
function mergeInstructions(root, opts = {}) {
  const plan = instructionPlan(root); if (!plan.ok) return plan;
  const changed = [];
  try { if (opts.write) for (const row of plan.rows) if (row.changed) {
    opts.fault?.(`instruction:${path.basename(row.file)}:before`); io.atomic(row.file, row.text, row.mode); changed.push(row);
    opts.fault?.(`instruction:${path.basename(row.file)}:written`);
  } } catch (error) {
    for (const row of changed.reverse()) row.existed ? io.atomic(row.file, row.before, row.mode) : fs.rmSync(row.file, { force: true });
    return { ok: false, reason: error.message, rows: plan.rows };
  }
  return plan;
}
function skeleton(root, opts = {}) {
  const hd = path.join(root, 'docs', 'harness');
  const dirs = ['stages', 'leaves', 'unfinished', 'done', 'reports', 'usage'];
  if (opts.write) for (const dir of dirs) fs.mkdirSync(path.join(hd, dir), { recursive: true });
  const files = { 'plan.md': '# 总计划\n\n目标：由用户清晰自然语言建立。\n', 'MISTAKES.md': '# 错题本\n' };
  if (opts.write) for (const [name, text] of Object.entries(files)) if (!fs.existsSync(path.join(hd, name))) fs.writeFileSync(path.join(hd, name), text);
}
function archive05(root, checked, opts = {}) {
  const owned = checked?.manifest?.packages?.core?.files || {}, rows = LEGACY_CONTROL.filter((rel) => (owned[rel] || rel === 'docs/harness/authorization.json') && fs.existsSync(path.join(root, rel)))
    .map((rel) => ({ source: path.join(root, rel), dest: path.join(root, 'docs', 'harness', 'archive', 'legacy-0.5', rel) }));
  const unsafe = rows.map((row) => unsafeParent(root, row.dest)).find(Boolean); if (unsafe) return { ok: false, reason: `legacy archive parent 不安全：${path.relative(root, unsafe)}`, rows };
  const conflict = rows.find((row) => fs.existsSync(row.dest)); if (conflict) return { ok: false, reason: `legacy archive 已存在：${path.relative(root, conflict.dest)}`, rows };
  const moved = [];
  try { if (opts.write) for (const row of rows) { try { io.moveNoClobber(row.source, row.dest, opts.fault); moved.push(row); }
    catch (error) { try { const a = fs.statSync(row.source), b = fs.statSync(row.dest); if (a.dev === b.dev && a.ino === b.ino) fs.unlinkSync(row.dest); } catch { /* foreign dest preserved */ } throw error; } } }
  catch (error) { for (const row of moved.reverse()) try { io.moveNoClobber(row.dest, row.source); } catch { /* source retained by no-clobber */ } return { ok: false, reason: error.message, rows }; }
  return { ok: true, wrote: !!opts.write && rows.length > 0, rows };
}
function restoreInstructionRows(rows) {
  const failures = [];
  for (const row of [...(rows || [])].reverse().filter((item) => item.changed)) {
    try {
      const actual = fileImage(row.file);
      if (actual.type !== 'file' || actual.mode !== row.mode || !actual.body.equals(Buffer.from(row.text))) { failures.push(`${path.basename(row.file)}:concurrent-change`); continue; }
      if (row.existed) io.atomic(row.file, row.before, row.mode); else fs.rmSync(row.file, { force: true });
    } catch (error) { failures.push(`${path.basename(row.file)}:${error.message}`); }
  }
  return failures;
}
function reverseArchive(rows) {
  const failures = [];
  for (const row of [...(rows || [])].reverse()) {
    try {
      if (!fs.existsSync(row.dest)) continue;
      if (fs.existsSync(row.source)) { failures.push(`${path.relative(path.dirname(row.source), row.source)}:source-exists`); continue; }
      io.moveNoClobber(row.dest, row.source);
    } catch (error) { failures.push(`${path.basename(row.source)}:${error.message}`); }
  }
  return failures;
}
function rollbackSwap(root, swapped) {
  if (!swapped) return [];
  const failures = [], stable = path.join(root, RUNTIME), failed = path.join(root, '.claude', `.harness-lite.failed-install-${Date.now()}`); let moved = false;
  try { if (fs.existsSync(stable)) { fs.renameSync(stable, failed); moved = true; } } catch (error) { failures.push(`new-runtime:${error.message}`); }
  try { if (swapped.rollback && fs.existsSync(swapped.rollback) && !fs.existsSync(stable)) fs.renameSync(swapped.rollback, stable); } catch (error) { failures.push(`old-runtime:${error.message}`); }
  try { if (moved && (!swapped.rollback || fs.existsSync(stable))) fs.rmSync(failed, { recursive: true }); } catch (error) { failures.push(`failed-runtime:${error.message}`); }
  return failures;
}
function hookPlanPostimage(plan) {
  const actual = fileImage(plan.file), parent = actual.parent, prior = plan.preimage.parent;
  return actual.type === 'file' && actual.mode === plan.mode && actual.body.equals(Buffer.from(plan.text))
    && parent.type === prior.type && parent.dev === prior.dev && parent.ino === prior.ino && parent.real === prior.real;
}
function install(root, opts = {}) {
  root = path.resolve(root); const source = opts.source || sourceRoot(), surfaceDifferences = surfacePreflight(root);
  if (surfaceDifferences.length) return { status: 'HOLD', kind: 'unsafe-surface', written: 0, differences: surfaceDifferences, reason: '安装 surface type/symlink 不安全' };
  const before = inspect(root, source);
  const desiredPaths = runtimePaths(source), desiredDigest = io.digest(source, desiredPaths, desiredMode);
  const sourceChanged = before.kind === 'current' && (JSON.stringify([...before.manifest.managedPaths].sort()) !== JSON.stringify(desiredPaths)
    || before.manifest.packageDigest !== desiredDigest);
  const definitionChanged = before.kind === 'current' && before.manifest.hookDefinitionDigest !== definition(root).digest;
  if (before.kind === 'official-06' && !opts.upgrade) return { status: 'HOLD', kind: before.kind, written: 0, differences: ['official-06-upgrade'], reason: '官方 0.6 runtime 需要显式 upgrade' };
  const allowed = before.kind === 'fresh' || before.kind === 'current' || (['official-06', 'owned-05'].includes(before.kind) && opts.upgrade);
  if (!allowed) return { status: 'HOLD', kind: before.kind, written: 0, differences: before.differences,
    reason: before.kind === 'legacy-unowned' ? '无 ownership legacy：Core 全部写入口零写 HOLD，转独立一次性迁移包' : 'runtime identity 不允许增量混装' };
  if (sourceChanged && !opts.upgrade) return { status: 'HOLD', kind: before.kind, written: 0, differences: ['source-package-digest'], reason: 'source package 变化需要显式 upgrade' };
  const instruction = instructionPlan(root);
  if (!instruction.ok) return { status: 'HOLD', kind: before.kind, written: 0, differences: [instruction.reason], reason: instruction.reason };
  const hookPreflight = mergeHooks(root);
  if (!hookPreflight.ok) return { status: 'HOLD', kind: before.kind, written: 0, differences: [hookPreflight.reason], reason: hookPreflight.reason };
  const archivePlan = before.kind === 'owned-05' ? archive05(root, before) : { ok: true, rows: [] };
  if (!archivePlan.ok) return { status: 'HOLD', kind: before.kind, written: 0, differences: [archivePlan.reason], reason: archivePlan.reason };
  if (!opts.write) return { status: 'READY', kind: before.kind, written: 0, differences: [], dryRun: true };
  let swapped = null;
  if (before.kind !== 'current' || sourceChanged || definitionChanged) swapped = swap(root, stage(root, source, opts.fault), before.kind !== 'fresh', opts.fault);
  let archive = archivePlan, instructionResult = { ok: true, rows: instruction.rows }, hooks = { ok: true, wrote: false };
  try {
    archive = before.kind === 'owned-05' ? archive05(root, before, { write: true, fault: opts.fault }) : archivePlan;
    if (!archive.ok) throw new Error(archive.reason);
    instructionResult = mergeInstructions(root, { write: true, fault: opts.fault }); if (!instructionResult.ok) throw new Error(instructionResult.reason);
    hooks = writeHookPlan(hookPreflight.plan, opts.fault); if (!hooks.ok) throw new Error(hooks.reason);
    skeleton(root, { write: true });
    return { status: 'INSTALLED', kind: before.kind, written: before.kind === 'current' && !sourceChanged && !definitionChanged ? 0 : 1,
      rollback: swapped?.rollback || null, archive, hooks, instructions: instructionResult.rows, manifest: io.json(path.join(root, MANIFEST)) };
  } catch (error) {
    const recovery = [];
    if (hooks.ok && hooks.wrote) { try { if (hookPlanPostimage(hookPreflight.plan)) restoreImage(hookPreflight.plan.preimage); else recovery.push('hooks:concurrent-change'); } catch (restore) { recovery.push(`hooks:${restore.message}`); } }
    recovery.push(...restoreInstructionRows(instructionResult.ok ? instructionResult.rows : []));
    recovery.push(...reverseArchive(archive.rows)); recovery.push(...rollbackSwap(root, swapped));
    return { status: 'PARTIAL', kind: before.kind, written: 0, differences: [error.message, ...recovery], reason: error.message,
      rollback: swapped?.rollback || null, archive, hooks, instructions: instructionResult.rows };
  }
}
function configured(root) {
  const file = path.join(hookConfigRoot(root), '.codex', 'hooks.json'), data = io.json(file), expected = definition(root);
  if (!data?.hooks) return false;
  return EVENTS.every((event) => (data.hooks[event] || []).some((group) => JSON.stringify(canonical(group)) === JSON.stringify(canonical(expected.config.hooks[event][0]))));
}
function health(root) {
  const checked = verify06(root), value = checked.manifest || {}, def = definition(root);
  const host = io.json(path.join(root, 'docs', 'harness', 'usage', 'host-health.json'), {}), hostEvents = io.json(path.join(root, 'docs', 'harness', 'usage', 'host-events.json'), { events: {} });
  const observed = io.json(path.join(root, 'docs', 'harness', 'usage', '.observed.json'), { events: {} });
  const trusted = host.source === 'codex-hooks-list' && host.definitionDigest === def.digest && !(host.warnings || []).length && !(host.errors || []).length
    && EVENTS.every((event) => host.events?.[event]?.matched === true && host.events[event].enabled === true
      && host.events[event].trustStatus === 'trusted' && !!host.events[event].currentHash);
  const seen = Object.fromEntries(EVENTS.map((event) => [event, observed.source === 'codex-host-hook' && observed.events?.[event]?.definitionDigest === def.digest
    && observed.events[event].packageDigest === value.packageDigest && hostEvents.source === 'codex-app-server-hook-completed'
    && hostEvents.events?.[event]?.definitionDigest === def.digest && hostEvents.events[event].packageDigest === value.packageDigest
    && hostEvents.events[event].handlerHash === host.events?.[event]?.currentHash]));
  const native = nativeState(root, value.packageDigest);
  const nativeConfigured = checked.ok && native.configured, nativeProbed = nativeConfigured && native.probed;
  return { installed: checked.ok, configured: configured(root), trusted, observed: seen,
    effective: checked.ok && configured(root) && trusted && EVENTS.every((event) => seen[event]) && nativeConfigured && nativeProbed,
    nativePrePush: { configured: nativeConfigured, probed: nativeProbed } };
}
const HOST_EVENT = { SessionStart: 'sessionStart', UserPromptSubmit: 'userPromptSubmit', Stop: 'stop', PreToolUse: 'preToolUse' };
function recordHostList(root, response, opts = {}) {
  if (opts.write && !verify06(root).ok) return { ok: false, status: 'HOLD', reason: 'runtime identity 不允许写宿主健康账' };
  const entry = response?.data?.find((x) => samePath(x.cwd, root)) || { hooks: [], warnings: [], errors: [] };
  const expected = definition(root), sourcePath = path.join(hookConfigRoot(root), '.codex', 'hooks.json'), events = {};
  for (const event of EVENTS) {
    const matcher = expected.config.hooks[event][0].matcher || null, found = (entry.hooks || []).find((item) => item.eventName === HOST_EVENT[event]
      && item.command === expected.command && (item.matcher || null) === matcher && item.source === 'project' && samePath(item.sourcePath, sourcePath));
    events[event] = found ? { matched: true, enabled: found.enabled === true, trustStatus: found.trustStatus,
      currentHash: found.currentHash || null, sourcePath: found.sourcePath } : { matched: false, enabled: false, trustStatus: null, currentHash: null };
  }
  const value = { source: 'codex-hooks-list', at: new Date().toISOString(), definitionDigest: expected.digest,
    warnings: entry.warnings || [], errors: entry.errors || [], events };
  if (opts.write) io.atomic(path.join(root, 'docs', 'harness', 'usage', 'host-health.json'), `${JSON.stringify(value, null, 2)}\n`);
  return value;
}
function recordHostEvent(root, notification, opts = {}) {
  const run = notification?.run || {}, event = Object.entries(HOST_EVENT).find(([, value]) => value === run.eventName)?.[0];
  const sourcePath = path.join(hookConfigRoot(root), '.codex', 'hooks.json');
  const checked = verify06(root), def = definition(root), observed = io.json(path.join(root, 'docs', 'harness', 'usage', '.observed.json'), {}), host = io.json(path.join(root, 'docs', 'harness', 'usage', 'host-health.json'), {});
  if (!checked.ok) return { ok: false, reason: 'runtime identity 不允许写宿主事件账' };
  const local = observed.events?.[event], listed = host.events?.[event], valid = !!event && run.handlerType === 'command'
    && run.source === 'project' && samePath(run.sourcePath || '/', sourcePath) && ['completed', 'blocked'].includes(run.status)
    && observed.source === 'codex-host-hook' && local?.definitionDigest === def.digest && local?.packageDigest === checked.manifest?.packageDigest
    && (!notification.threadId || local.session === notification.threadId) && (!notification.turnId || !local.turn || local.turn === notification.turnId)
    && host.source === 'codex-hooks-list' && host.definitionDigest === def.digest && listed?.matched && listed.enabled && listed.trustStatus === 'trusted' && listed.currentHash;
  if (!valid) return { ok: false, reason: 'hook/completed 与 Harness definition 不匹配' };
  const file = path.join(root, 'docs', 'harness', 'usage', 'host-events.json');
  const value = io.json(file, { source: 'codex-app-server-hook-completed', events: {} }); value.source = 'codex-app-server-hook-completed';
  value.events[event] = { at: new Date().toISOString(), runId: run.id, handlerHash: listed.currentHash, status: run.status, thread: notification.threadId || null,
    turn: notification.turnId || null, definitionDigest: def.digest, packageDigest: checked.manifest?.packageDigest || null };
  if (opts.write) io.atomic(file, `${JSON.stringify(value, null, 2)}\n`); return { ok: true, event, value };
}
function removeHooks(root, opts = {}) {
  const identity = inspect(root), file = path.join(hookConfigRoot(root), '.codex', 'hooks.json'), present = fs.existsSync(file), data = io.json(file), expected = definition(root);
  if (!present) return { ok: true, wrote: false };
  if (!data || !data.hooks || Array.isArray(data.hooks)) return { ok: false, wrote: false, reason: 'invalid .codex/hooks.json' };
  const malformed = Object.entries(data.hooks).filter(([, groups]) => !Array.isArray(groups) || groups.some((group) => !group || !Array.isArray(group.hooks)));
  if (malformed.length) return { ok: false, wrote: false, reason: `invalid hook groups: ${malformed.map(([event]) => event).join(',')}` };
  const previous = identity.kind === 'current' && isExactPrevious06(data, expected)
    && [expected.digest, previous06Digest(expected)].includes(identity.manifest?.hookDefinitionDigest);
  for (const event of EVENTS) {
    const groups = data.hooks[event] || [];
    if (groups.some((group) => ['legacy', 'unknown'].includes(hookGroupKind(event, group, expected.config.hooks[event][0], previous, expected)))) return { ok: false, wrote: false, reason: `unknown Harness hook: ${event}` };
    data.hooks[event] = groups.filter((group) => !['current', 'previous'].includes(hookGroupKind(event, group, expected.config.hooks[event][0], previous, expected)));
  }
  const text = `${JSON.stringify(data, null, 2)}\n`, preimage = fileImage(file);
  if (preimage.type !== 'file' || preimage.parent.type !== 'directory') return { ok: false, wrote: false, reason: 'Hook 配置路径不是安全普通文件' };
  const plan = { file, before: fs.readFileSync(file, 'utf8'), text, mode: preimage.mode, digest: expected.digest, preimage };
  if (opts.write) return writeHookPlan(plan, opts.fault);
  return { ok: true, wrote: false, plan };
}
function uninstall(root, opts = {}) {
  const checked = verify06(root); if (!checked.ok) return { status: 'HOLD', differences: checked.differences, removed: false };
  if (Object.keys(checked.manifest.extensions || {}).length) return { status: 'HOLD', differences: ['extensions-installed'], removed: false };
  const hookPlan = removeHooks(root), nativePlan = removeNative(root);
  if (!hookPlan.ok || !nativePlan.ok) return { status: 'HOLD', differences: [hookPlan.reason || nativePlan.reason], removed: false };
  if (!opts.write) return { status: 'READY', removed: false };
  const stable = path.join(root, RUNTIME), tomb = path.join(root, '.claude', `.harness-lite.uninstall-${Date.now()}`);
  let hooks, native;
  try {
    fs.renameSync(stable, tomb); opts.fault?.('uninstall:tomb');
    hooks = hookPlan.plan ? writeHookPlan(hookPlan.plan, opts.fault) : { ok: true, wrote: false };
    if (!hooks.ok) throw new Error(hooks.reason);
    native = nativePlan.plan ? writeNativeRemovalPlan(nativePlan.plan, opts.fault) : { ok: true, wrote: false };
    if (!native.ok) throw new Error(native.reason);
    fs.rmSync(tomb, { recursive: true }); return { status: 'UNINSTALLED', removed: true, hooks, native };
  } catch (error) {
    const recovery = [];
    try { if (hooks?.ok && hooks.wrote) restoreImage(hookPlan.plan.preimage); } catch (restore) { recovery.push(`hooks:${restore.message}`); }
    try { if (native?.ok && native.wrote) for (const image of [nativePlan.plan.backup, nativePlan.plan.hook, nativePlan.plan.marker]) restoreImage(image); } catch (restore) { recovery.push(`native:${restore.message}`); }
    try { if (!fs.existsSync(stable) && fs.existsSync(tomb)) fs.renameSync(tomb, stable); } catch (restore) { recovery.push(`runtime:${restore.message}`); }
    return { status: 'PARTIAL', removed: false, differences: [error.message, ...recovery], reason: error.message, hooks, native };
  }
}
function loadExtension(dir) {
  const data = io.json(path.join(dir, 'manifest.json'));
  if (data?.version !== 1 || !/^[a-z0-9][a-z0-9-]*$/.test(data.id || '') || !data.packageVersion || !data.files || Array.isArray(data.files)) throw new Error('扩展 manifest 不合规');
  const base = fs.realpathSync(dir), prefix = `${RUNTIME}/extensions/${data.id}/`, files = [];
  for (const [target, source] of Object.entries(data.files)) {
    const cleanTarget = target.replaceAll('\\', '/'); if (!cleanTarget.startsWith(prefix)) throw new Error(`扩展目标必须位于 ${prefix}`);
    const abs = fs.realpathSync(io.safe(dir, source)), stat = fs.lstatSync(abs);
    if (!abs.startsWith(`${base}${path.sep}`) || !stat.isFile() || stat.isSymbolicLink()) throw new Error(`扩展源文件不合规：${source}`);
    files.push({ target: cleanTarget.slice(RUNTIME.length + 1), source: abs });
  }
  return { ...data, files: files.sort((a, b) => a.target.localeCompare(b.target)) };
}
function verifyExtension(root, id) {
  const core = verify06(root), spec = core.manifest?.extensions?.[id]; if (!core.ok || !spec) return { ok: false, differences: ['extension-manifest'] };
  const runtime = path.join(root, RUNTIME), actual = io.list(path.join(runtime, 'extensions', id), true).map((x) => path.relative(runtime, x).replaceAll('\\', '/')).sort(), differences = [];
  for (const rel of spec.managedPaths) { const type = io.inspect(runtime, rel).type; if (type !== 'file') differences.push(`${type}:${rel}`); }
  for (const rel of actual.filter((x) => !spec.managedPaths.includes(x))) differences.push(`extra:${rel}`);
  let digest; try { digest = io.digest(runtime, spec.managedPaths); } catch (error) { differences.push(`identity:${error.message}`); }
  if (digest !== spec.packageDigest) differences.push('packageDigest'); return { ok: differences.length === 0, differences, spec };
}
function installExtension(root, dir, opts = {}) {
  root = path.resolve(root); const core = verify06(root); if (!core.ok) return { status: 'HOLD', differences: core.differences };
  const ext = loadExtension(path.resolve(dir)), prior = core.manifest.extensions?.[ext.id], priorCheck = prior ? verifyExtension(root, ext.id) : null;
  if (prior && !priorCheck.ok) return { status: 'HOLD', differences: priorCheck.differences };
  const parent = path.join(root, '.claude'), staged = path.join(parent, `.harness-lite.ext-stage-${process.pid}-${Date.now()}`), managedPaths = ext.files.map((x) => x.target);
  for (const item of ext.files) { const dest = path.join(staged, item.target); fs.mkdirSync(path.dirname(dest), { recursive: true }); fs.copyFileSync(item.source, dest); fs.chmodSync(dest, 0o644); }
  const packageDigest = io.digest(staged, managedPaths), spec = { packageVersion: ext.packageVersion, managedPaths, packageDigest };
  if (prior && JSON.stringify(canonical(prior)) === JSON.stringify(canonical(spec))) { fs.rmSync(staged, { recursive: true }); return { status: opts.write ? 'INSTALLED' : 'READY', id: ext.id, written: 0 }; }
  if (prior && !opts.upgrade) { fs.rmSync(staged, { recursive: true }); return { status: 'HOLD', differences: ['extension-upgrade-required'] }; }
  if (!opts.write) { fs.rmSync(staged, { recursive: true }); return { status: 'READY', id: ext.id, written: 0 }; }
  const stable = path.join(root, RUNTIME, 'extensions', ext.id), rollback = `${stable}.rollback-${Date.now()}`;
  const ledger = path.join(root, MANIFEST), ledgerBefore = fs.readFileSync(ledger, 'utf8'); let old = false, fresh = false, ledgerChanged = false;
  try {
    fs.mkdirSync(path.dirname(stable), { recursive: true }); if (fs.existsSync(stable)) { fs.renameSync(stable, rollback); old = true; }
    fs.renameSync(path.join(staged, 'extensions', ext.id), stable); fresh = true; fs.rmSync(staged, { recursive: true });
    const value = io.json(ledger); value.extensions = { ...(value.extensions || {}), [ext.id]: spec };
    io.atomic(ledger, `${JSON.stringify(value, null, 2)}\n`, 0o600); ledgerChanged = true; if (!verifyExtension(root, ext.id).ok) throw new Error('extension verify failed');
    return { status: 'INSTALLED', id: ext.id, written: 1, rollback: old ? rollback : null };
  } catch (error) { if (ledgerChanged) io.atomic(ledger, ledgerBefore, 0o600); if (fresh) fs.rmSync(stable, { recursive: true, force: true }); if (old && fs.existsSync(rollback)) fs.renameSync(rollback, stable); throw error; }
}
function uninstallExtension(root, id, opts = {}) {
  const checked = verifyExtension(root, id); if (!checked.ok) return { status: 'HOLD', differences: checked.differences };
  if (!opts.write) return { status: 'READY', removed: false };
  const stable = path.join(root, RUNTIME, 'extensions', id), tomb = `${stable}.uninstall-${Date.now()}`, ledger = path.join(root, MANIFEST), before = fs.readFileSync(ledger, 'utf8'); fs.renameSync(stable, tomb);
  try { const value = io.json(ledger); delete value.extensions[id]; io.atomic(ledger, `${JSON.stringify(value, null, 2)}\n`, 0o600); fs.rmSync(tomb, { recursive: true }); return { status: 'UNINSTALLED', removed: true }; }
  catch (error) { io.atomic(ledger, before, 0o600); if (!fs.existsSync(stable) && fs.existsSync(tomb)) fs.renameSync(tomb, stable); throw error; }
}
function installNative(root, opts = {}) {
  const checked = verify06(root); if (!checked.ok) return { ok: false, reason: `runtime 未通过 identity：${checked.differences.join(',')}` };
  const common = (spawnSync('git', ['rev-parse', '--git-common-dir'], { cwd: root, encoding: 'utf8' }).stdout || '').trim();
  if (!common) return { ok: false, reason: 'not a git repository' };
  const dispatcherDigest = `sha256:${io.sha(fs.readFileSync(path.join(root, RUNTIME, 'hooks', 'dispatcher.js')))}`;
  const dir = path.resolve(root, common, 'hooks'), file = path.join(dir, 'pre-push'), backup = `${file}.harness-lite.foreign`, script = nativeScript(backup, dispatcherDigest);
  const markerFile = path.join(root, '.codex', 'harness-lite', 'native.json'), hookImage = fileImage(file), backupImage = fileImage(backup), markerImage = fileImage(markerFile);
  if (![hookImage, backupImage, markerImage].every((image) => ['file', 'missing'].includes(image.type) && image.parent.type === 'directory')) return { ok: false, reason: 'native 安装 surface 不是安全普通文件', file, backup };
  let marker = null;
  if (markerImage.type === 'file') { try { marker = JSON.parse(markerImage.body.toString('utf8')); } catch { return { ok: false, reason: 'native marker JSON 损坏', file, backup }; } }
  const looksHarness = hookImage.type === 'file' && hookImage.body.includes('dispatcher="$root/.claude/harness-lite/hooks/dispatcher.js"')
    && hookImage.body.includes('exec node "$dispatcher" --native-pre-push');
  const priorOwned = !!marker?.configured && /^sha256:[0-9a-f]{64}$/.test(marker.dispatcherDigest || '') && marker.commonDir === path.resolve(root, common)
    && hookImage.type === 'file' && marker.hookDigest === `sha256:${io.sha(hookImage.body)}`
    && /^sha256:[0-9a-f]{64}$/.test(marker.packageDigest || '') && looksHarness;
  if (marker && !priorOwned) return { ok: false, reason: 'native marker 或 common pre-push identity 漂移', file, backup };
  if (!marker && (backupImage.type === 'file' || looksHarness)) return { ok: false, reason: '发现无有效 marker 的 Harness/backup 现场，保持零写 HOLD', file, backup };
  const current = nativeState(root, checked.manifest.packageDigest);
  if (current.configured) return { ok: true, configured: true, wrote: false, file, backup, dispatcherDigest };
  const markerText = `${JSON.stringify({ configured: true, probed: false, hookDigest: `sha256:${io.sha(script)}`,
    dispatcherDigest, packageDigest: checked.manifest.packageDigest, commonDir: path.resolve(root, common) }, null, 2)}\n`;
  if (!opts.write) return { ok: true, configured: false, wrote: false, file, backup, dispatcherDigest };
  const images = [hookImage, backupImage, markerImage];
  try {
    if (!images.every(sameImage)) throw new Error('native 安装 surface 在 preflight 后发生变化'); opts.fault?.('native-install:before');
    if (!images.every(sameImage)) throw new Error('native 安装 surface 在写入前发生变化');
    fs.mkdirSync(dir, { recursive: true });
    if (!priorOwned && hookImage.type === 'file') io.atomic(backup, hookImage.body, hookImage.mode); opts.fault?.('native-install:backup');
    io.atomic(file, script, 0o755); opts.fault?.('native-install:hook'); io.atomic(markerFile, markerText, 0o600); opts.fault?.('native-install:marker');
    if (!nativeState(root, checked.manifest.packageDigest).configured) throw new Error('native 安装后 identity 校验失败');
    return { ok: true, configured: true, wrote: true, file, backup, dispatcherDigest };
  } catch (error) {
    const recovery = [];
    for (const image of [backupImage, hookImage, markerImage]) try { restoreImage(image); } catch (restore) { recovery.push(restore.message); }
    return { ok: false, configured: false, wrote: false, reason: recovery.length ? `${error.message}；native preimage 恢复失败：${recovery.join('|')}` : error.message, file, backup };
  }
}
function probeNative(root, opts = {}) {
  const checked = verify06(root), native = nativeState(root, checked.manifest?.packageDigest);
  if (!checked.ok) return { ok: false, status: 'HOLD', probed: false, reason: `runtime 未通过 identity：${checked.differences.join(',')}` };
  if (!native.configured) return { ok: false, probed: false, reason: 'native pre-push 未配置或 identity 漂移' };
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'hl-native-probe-')), remote = path.join(dir, 'remote.git');
  try {
    const init = spawnSync('git', ['init', '--bare', '-q', remote], { encoding: 'utf8' });
    const run = init.status === 0 ? spawnSync('git', ['push', '--dry-run', remote, 'HEAD:refs/heads/harness-lite-probe'], { cwd: root, encoding: 'utf8' }) : init;
    const probed = run.status !== 0 && /Harness pre-push/.test(`${run.stdout || ''}${run.stderr || ''}`);
    if (opts.write) { const value = io.json(path.join(root, '.codex', 'harness-lite', 'native.json'), {}); io.atomic(path.join(root, '.codex', 'harness-lite', 'native.json'), `${JSON.stringify({ ...value, probed,
      probedHookDigest: native.actualDigest, probedAt: new Date().toISOString(), probe: 'disposable-local-bare-remote' }, null, 2)}\n`); }
    return { ok: probed, probed, remote: 'disposable-local-bare-remote', reason: probed ? null : '未观察到 native pre-push' };
  } finally { fs.rmSync(dir, { recursive: true, force: true }); }
}

function nativeScript(backup, dispatcherDigest) {
  const expected = String(dispatcherDigest || '').replace(/^sha256:/, '');
  return `#!/bin/sh\nroot=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0\ndispatcher="$root/${RUNTIME}/hooks/dispatcher.js"\nmarker="$root/.codex/harness-lite/native.json"\nactual=$(/usr/bin/shasum -a 256 "$dispatcher" 2>/dev/null | /usr/bin/awk '{print $1}')\nif [ "$actual" = ${JSON.stringify(expected)} ]; then\n  if [ ! -f "$marker" ]; then echo "Harness pre-push：native marker 缺失，fail closed" >&2; exit 1; fi\n  exec node "$dispatcher" --native-pre-push "$@" --foreign ${JSON.stringify(backup)}\nfi\nif [ -f "$marker" ]; then echo "Harness pre-push：runtime identity 损坏，fail closed" >&2; exit 1; fi\nif [ -x ${JSON.stringify(backup)} ]; then exec ${JSON.stringify(backup)} "$@"; fi\nexit 0\n`;
}
function nativeState(root, packageDigest) {
  const value = io.json(path.join(root, '.codex', 'harness-lite', 'native.json'), {}), common = (spawnSync('git', ['rev-parse', '--git-common-dir'], { cwd: root, encoding: 'utf8' }).stdout || '').trim();
  const file = common ? path.join(path.resolve(root, common, 'hooks'), 'pre-push') : null, backup = file ? `${file}.harness-lite.foreign` : null;
  const actualDigest = file && fs.existsSync(file) ? `sha256:${io.sha(fs.readFileSync(file))}` : null, expectedDigest = backup ? `sha256:${io.sha(nativeScript(backup, value.dispatcherDigest))}` : null;
  const configured = /^sha256:[0-9a-f]{64}$/.test(packageDigest || '') && value.configured === true && value.commonDir === (common ? path.resolve(root, common) : null) && value.hookDigest === actualDigest
    && actualDigest === expectedDigest && value.packageDigest === packageDigest;
  return { ...value, file, backup, actualDigest, configured, probed: configured && value.probed === true && value.probedHookDigest === actualDigest };
}
function writeNativeRemovalPlan(plan, fault = () => {}) {
  const images = [plan.marker, plan.hook, plan.backup];
  if (!images.every(sameImage)) return { ok: false, status: 'HOLD', wrote: false, reason: 'native pre-push 或 marker 在 preflight 后发生变化' };
  try { fault('native:before'); } catch (error) { return { ok: false, status: 'HOLD', wrote: false, reason: error.message }; }
  if (!images.every(sameImage)) return { ok: false, status: 'HOLD', wrote: false, reason: 'native pre-push 或 marker 在写入前发生变化' };
  try {
    if (plan.backup.type === 'file') io.atomic(plan.hook.file, plan.backup.body, plan.backup.mode); else fs.unlinkSync(plan.hook.file);
    fault('native:hook'); fs.rmSync(plan.marker.file, { force: true }); fault('native:marker');
    if (plan.backup.type === 'file') fs.rmSync(plan.backup.file, { force: true }); fault('native:backup');
    return { ok: true, wrote: true };
  } catch (error) {
    const recovery = [];
    for (const image of [plan.backup, plan.hook, plan.marker]) try { restoreImage(image); } catch (restore) { recovery.push(restore.message); }
    return { ok: false, status: 'HOLD', wrote: false, reason: recovery.length ? `${error.message}；native preimage 恢复失败：${recovery.join('|')}` : error.message };
  }
}
function removeNative(root, opts = {}) {
  const markerFile = path.join(root, '.codex', 'harness-lite', 'native.json'), marker = fileImage(markerFile);
  if (!['missing', 'file'].includes(marker.type) || marker.parent.type !== 'directory') return { ok: false, wrote: false, reason: 'native marker 不是安全普通文件' };
  const common = (spawnSync('git', ['rev-parse', '--git-common-dir'], { cwd: root, encoding: 'utf8' }).stdout || '').trim();
  const hookFile = common ? path.join(path.resolve(root, common, 'hooks'), 'pre-push') : null;
  const physical = hookFile ? fileImage(hookFile) : null;
  const harnessWrapper = physical?.type === 'file' && physical.body.includes('--native-pre-push');
  if (marker.type === 'missing') return harnessWrapper
    ? { ok: false, wrote: false, reason: 'native marker 缺失但 common pre-push 仍是 Harness wrapper' }
    : { ok: true, wrote: false, plan: null };
  let value; try { value = JSON.parse(marker.body.toString('utf8')); } catch { return { ok: false, wrote: false, reason: 'native marker JSON 损坏' }; }
  if (!common || !physical || physical.type !== 'file' || physical.parent.type !== 'directory') return { ok: false, wrote: false, reason: 'native pre-push 不是安全普通文件' };
  const state = nativeState(root, value.packageDigest); if (!state.configured) return { ok: false, wrote: false, reason: 'native pre-push identity 漂移' };
  const backup = fileImage(state.backup);
  if (!['missing', 'file'].includes(backup.type) || backup.parent.type !== 'directory') return { ok: false, wrote: false, reason: 'native backup 不是安全普通文件' };
  const plan = { marker, hook: physical, backup };
  if (opts.write) return writeNativeRemovalPlan(plan, opts.fault);
  return { ok: true, wrote: false, plan };
}

module.exports = { VERSION, SOURCE_COMMIT, RUNTIME, MANIFEST, EVENTS, INSTRUCTION, PREVIOUS_06_INSTRUCTION, OFFICIAL_06, runtimePaths, hookConfigRoot,
  definition, manifest, verify06, verifyOfficial06, verifyOwned05, legacyUnowned, inspect, surfacePreflight, instructionPlan,
  install, configured, health, recordHostList, recordHostEvent, uninstall, loadExtension, verifyExtension,
  installExtension, uninstallExtension, nativeScript, nativeState, installNative, probeNative };
