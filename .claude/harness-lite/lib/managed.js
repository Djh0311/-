'use strict';

const crypto = require('crypto');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');
const io = require('./io.js');
const RUNTIME_VERSION = require('../package.json').version;

const SCHEMA = 1;
const MAX_INPUT = 64 * 1024;
const EVENTS = ['SessionStart', 'UserPromptSubmit', 'Stop', 'PreToolUse'];

function layout(systemRoot) {
  const root = path.resolve(systemRoot), base = path.join(root, 'usr', 'local', 'lib', 'harness-lite', 'current');
  return {
    root, base,
    requirements: path.join(root, 'etc', 'codex', 'requirements.toml'),
    gateway: path.join(base, 'gateway', 'gateway'),
    gatewayMain: path.join(base, 'gateway', 'main.cjs'),
    runtime: path.join(base, 'runtime'),
    definition: path.join(base, 'policy', 'hooks.json'),
    allowlist: path.join(base, 'policy', 'allowlist.json'),
    registry: path.join(base, 'policy', 'registry.json'),
    manifest: path.join(base, 'manifest.json'),
    receipts: path.join(base, 'logs', 'receipts.jsonl'),
    log: path.join(base, 'logs', 'gateway.log'),
  };
}

function canonical(value) {
  if (Array.isArray(value)) return value.map(canonical);
  if (value && typeof value === 'object') return Object.fromEntries(Object.keys(value).sort().map((key) => [key, canonical(value[key])]));
  return value;
}
const jsonText = (value) => `${JSON.stringify(value, null, 2)}\n`;
function projectBoundary(root) {
  const boundary = require('./install.js').targetBoundary(root);
  return boundary.ok ? null : { status: 'HOLD', ok: false, written: 0, removed: false, differences: [boundary.kind], reason: boundary.reason };
}
const digestObject = (value) => `sha256:${io.sha(JSON.stringify(canonical(value)))}`;
const desiredMode = (rel) => rel === 'bin/hl.js' || rel === 'hooks/dispatcher.js' ? 0o755 : 0o644;

function hooksDefinition(target, version) {
  const handler = (timeout, canAddContext = true) => ({ type: 'command', command: target, timeout,
    ...(canAddContext ? { additionalContextLimit: 1800 } : {}) });
  return { description: `Harness Lite ${version} managed lifecycle hooks`, hooks: {
    SessionStart: [{ matcher: 'startup|resume|clear|compact', hooks: [handler(15)] }],
    UserPromptSubmit: [{ hooks: [handler(10)] }],
    Stop: [{ hooks: [handler(30, false)] }],
    PreToolUse: [{ matcher: '^Bash$', hooks: [handler(10)] }],
  } };
}

function gatewayBootstrap(systemRoot, nodePath, expected) {
  'use strict';
  const crypto = require('crypto');
  const fs = require('fs');
  const path = require('path');
  const { spawnSync } = require('child_process');
  const root = path.resolve(systemRoot), base = path.join(root, 'usr', 'local', 'lib', 'harness-lite', 'current');
  const target = {
    base, requirements: path.join(root, 'etc', 'codex', 'requirements.toml'),
    gateway: path.join(base, 'gateway', 'gateway'), gatewayMain: path.join(base, 'gateway', 'main.cjs'),
    runtime: path.join(base, 'runtime'), definition: path.join(base, 'policy', 'hooks.json'),
    allowlist: path.join(base, 'policy', 'allowlist.json'), registry: path.join(base, 'policy', 'registry.json'),
    manifest: path.join(base, 'manifest.json'), receipts: path.join(base, 'logs', 'receipts.jsonl'), log: path.join(base, 'logs', 'gateway.log'),
  };
  const sha = (value) => crypto.createHash('sha256').update(value).digest('hex');
  const canonical = (value) => Array.isArray(value) ? value.map(canonical) : value && typeof value === 'object'
    ? Object.fromEntries(Object.keys(value).sort().map((key) => [key, canonical(value[key])])) : value;
  const digestObject = (value) => `sha256:${sha(JSON.stringify(canonical(value)))}`;
  function regular(file, mode) {
    try { const stat = fs.lstatSync(file); return stat.isFile() && !stat.isSymbolicLink() && (stat.mode & 0o777) === mode; } catch { return false; }
  }
  function safeParentsFrom(anchor, file) {
    const rel = path.relative(anchor, file); if (rel.startsWith('..') || path.isAbsolute(rel)) return false;
    let cursor = anchor;
    try {
      const rootStat = fs.lstatSync(anchor); if (!rootStat.isDirectory() || rootStat.isSymbolicLink()) return false;
      for (const part of path.dirname(rel).split(path.sep).filter((item) => item && item !== '.')) {
        cursor = path.join(cursor, part); const stat = fs.lstatSync(cursor); if (!stat.isDirectory() || stat.isSymbolicLink()) return false;
      }
      return true;
    } catch { return false; }
  }
  const safeParents = (file) => safeParentsFrom(root, file);
  function readJson(file) { try { return JSON.parse(fs.readFileSync(file, 'utf8')); } catch { return null; } }
  function list(dir, prefix = '') {
    const out = [];
    for (const entry of fs.readdirSync(dir, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
      const rel = prefix ? `${prefix}/${entry.name}` : entry.name, file = path.join(dir, entry.name), stat = fs.lstatSync(file);
      if (stat.isDirectory() && !stat.isSymbolicLink()) out.push(...list(file, rel)); else out.push(rel);
    }
    return out;
  }
  function packageDigest(runtime) {
    const hash = crypto.createHash('sha256');
    for (const item of [...expected.files].sort((a, b) => a.path === b.path ? 0 : a.path < b.path ? -1 : 1)) {
      const file = path.join(runtime, item.path), stat = fs.lstatSync(file);
      if (!safeParentsFrom(path.dirname(runtime), file) || !stat.isFile() || stat.isSymbolicLink() || (stat.mode & 0o777) !== Number.parseInt(item.mode, 8)) return null;
      const body = fs.readFileSync(file);
      for (const value of [item.path, 'file', item.mode, String(body.length)]) hash.update(`${Buffer.byteLength(value)}:${value}`);
      hash.update(body);
    }
    return `sha256:${hash.digest('hex')}`;
  }
  function validInput(value) {
    if (!value || typeof value !== 'object' || Array.isArray(value) || !expected.events.includes(value.hook_event_name)
      || typeof value.cwd !== 'string' || typeof value.session_id !== 'string') return false;
    if (value.hook_event_name === 'Stop' && typeof value.stop_hook_active !== 'boolean') return false;
    if (value.hook_event_name === 'UserPromptSubmit' && typeof value.prompt !== 'string') return false;
    return value.hook_event_name !== 'PreToolUse' || (typeof value.tool_name === 'string' && value.tool_input && typeof value.tool_input === 'object');
  }
  function inputText() {
    const chunks = []; let size = 0;
    for (;;) {
      const chunk = Buffer.alloc(Math.min(8192, expected.maxInput + 1 - size)), count = fs.readSync(0, chunk, 0, chunk.length, null);
      if (!count) break; size += count; if (size > expected.maxInput) return null; chunks.push(chunk.subarray(0, count));
    }
    return Buffer.concat(chunks).toString('utf8');
  }
  function gitIdentity(cwd) {
    const run = (args) => spawnSync('/usr/bin/git', args, { cwd, encoding: 'utf8', env: { PATH: '/usr/bin:/bin', LANG: 'C', LC_ALL: 'C' } });
    const top = run(['rev-parse', '--show-toplevel']), common = run(['rev-parse', '--git-common-dir']); if (top.status !== 0 || common.status !== 0) return null;
    try {
      const worktree = fs.realpathSync(top.stdout.trim()), candidate = path.isAbsolute(common.stdout.trim()) ? common.stdout.trim() : path.resolve(worktree, common.stdout.trim());
      const commonDir = fs.realpathSync(candidate), workStat = fs.lstatSync(worktree), commonStat = fs.lstatSync(commonDir);
      if (!workStat.isDirectory() || workStat.isSymbolicLink() || !commonStat.isDirectory() || commonStat.isSymbolicLink()) return null;
      return { worktree, commonDir, projectId: sha(`${worktree}\0${commonDir}`).slice(0, 24) };
    } catch { return null; }
  }
  let raw;
  try { raw = inputText(); } catch { return; }
  if (raw === null) return;
  let input; try { input = JSON.parse(raw); } catch { return; }
  if (!validInput(input)) return;
  try {
    const fixed = [[target.manifest, 0o600], [target.gateway, 0o755], [target.gatewayMain, 0o644], [target.allowlist, 0o600],
      [target.definition, 0o600], [target.registry, 0o600], [target.receipts, 0o600], [target.log, 0o600], [target.requirements, 0o644]];
    if (fixed.some(([file, mode]) => !safeParents(file) || !regular(file, mode))) return;
    for (const item of expected.files) if (!safeParents(path.join(target.runtime, item.path)) || !regular(path.join(target.runtime, item.path), Number.parseInt(item.mode, 8))) return;
    const manifest = readJson(target.manifest), manifestKeys = ['allowlistDigest', 'definitionDigest', 'gatewayDigest', 'generation', 'managedPaths', 'packageDigest', 'requirementsDigest', 'runtimeVersion', 'schemaVersion'];
    if (!manifest || JSON.stringify(Object.keys(manifest).sort()) !== JSON.stringify(manifestKeys)
      || manifest.schemaVersion !== 1 || manifest.runtimeVersion !== expected.runtimeVersion || manifest.generation !== expected.generation
      || JSON.stringify(manifest.managedPaths) !== JSON.stringify(expected.managedPaths) || manifest.packageDigest !== expected.packageDigest
      || manifest.allowlistDigest !== expected.allowlistDigest || manifest.definitionDigest !== expected.definitionDigest
      || manifest.requirementsDigest !== expected.requirementsDigest) return;
    const wanted = new Set(['gateway/gateway', 'gateway/main.cjs', 'policy/allowlist.json', 'policy/hooks.json', 'policy/registry.json',
      'logs/receipts.jsonl', 'logs/gateway.log', 'manifest.json', ...expected.managedPaths.map((rel) => `runtime/${rel}`)]);
    if (list(base).some((rel) => !wanted.has(rel)) || [...wanted].some((rel) => !list(base).includes(rel))) return;
    if (packageDigest(target.runtime) !== expected.packageDigest) return;
    for (const item of expected.files) if (`sha256:${sha(fs.readFileSync(path.join(target.runtime, item.path)))}` !== item.digest) return;
    const gatewayDigest = digestObject({ wrapper: `sha256:${sha(fs.readFileSync(target.gateway))}`, main: `sha256:${sha(fs.readFileSync(target.gatewayMain))}` });
    if (manifest.gatewayDigest !== gatewayDigest) return;
    if (`sha256:${sha(fs.readFileSync(target.allowlist))}` !== expected.allowlistDigest
      || `sha256:${sha(fs.readFileSync(target.definition))}` !== expected.definitionDigest
      || `sha256:${sha(fs.readFileSync(target.requirements))}` !== expected.requirementsDigest) return;
    const allowlist = readJson(target.allowlist), registry = readJson(target.registry), listed = allowlist?.runtimes?.[0];
    if (allowlist?.schemaVersion !== 1 || allowlist.runtimes?.length !== 1 || !listed
      || listed.runtimeVersion !== expected.runtimeVersion || listed.packageDigest !== expected.packageDigest
      || JSON.stringify(listed.managedPaths) !== JSON.stringify(expected.files)) return;
    const validProjects = Array.isArray(registry?.projects) && registry.projects.every((item) => item
      && Object.keys(item).sort().join(',') === 'active,commonDir,generation,packageDigest,projectId,runtimeVersion,worktree'
      && item.active === true && /^[0-9a-f]{24}$/.test(item.projectId || '') && path.isAbsolute(item.worktree || '') && path.isAbsolute(item.commonDir || '')
      && item.generation === expected.generation && item.runtimeVersion === expected.runtimeVersion && item.packageDigest === expected.packageDigest);
    if (registry?.schemaVersion !== 1 || registry.generation !== expected.generation || !validProjects
      || new Set(registry.projects.map((item) => item.projectId)).size !== registry.projects.length
      || Object.keys(registry).sort().join(',') !== 'generation,projects,schemaVersion') return;
    const identity = gitIdentity(process.cwd()); let inputRoot;
    try { inputRoot = fs.realpathSync(path.resolve(input.cwd)); } catch { return; }
    if (!identity || inputRoot !== identity.worktree) return;
    const matches = registry.projects.filter((item) => item && Object.keys(item).sort().join(',') === 'active,commonDir,generation,packageDigest,projectId,runtimeVersion,worktree'
      && item.active === true && item.projectId === identity.projectId && item.worktree === identity.worktree && item.commonDir === identity.commonDir
      && item.generation === expected.generation && item.runtimeVersion === expected.runtimeVersion && item.packageDigest === expected.packageDigest);
    if (matches.length !== 1) return;
    const ownershipFile = path.join(identity.worktree, '.claude', 'harness-lite', 'ownership.json');
    if (!regular(ownershipFile, 0o600)) return;
    const ownership = readJson(ownershipFile);
    const projectRuntime = path.join(identity.worktree, '.claude', 'harness-lite');
    if (!ownership || ownership.runtimeVersion !== expected.runtimeVersion || ownership.profile !== 'managed' || ownership.packageDigest !== expected.packageDigest
      || JSON.stringify(ownership.managedPaths) !== JSON.stringify(expected.managedPaths) || packageDigest(projectRuntime) !== expected.packageDigest) return;
    const projectFiles = list(projectRuntime).filter((rel) => rel !== 'ownership.json' && !rel.startsWith('extensions/')).sort();
    if (JSON.stringify(projectFiles) !== JSON.stringify([...expected.managedPaths].sort())) return;
    const dispatcher = path.join(target.runtime, 'hooks', 'dispatcher.js'), env = { PATH: '/usr/bin:/bin', LANG: 'C', LC_ALL: 'C',
      HARNESS_LITE_MANAGED_DEFINITION_DIGEST: expected.hookDefinitionDigest };
    const run = spawnSync(nodePath, [dispatcher], { cwd: identity.worktree, input: raw, encoding: 'utf8', env, shell: false });
    if (run.stdout) process.stdout.write(run.stdout); if (run.stderr) process.stderr.write(run.stderr);
    const receipt = { at: new Date().toISOString(), projectId: identity.projectId, event: input.hook_event_name, session: input.session_id,
      turn: typeof input.turn_id === 'string' ? input.turn_id : null, generation: expected.generation, digestPrefix: expected.packageDigest.slice(7, 19),
      decision: run.status === 0 ? 'executed' : 'runtime-error', ...(run.status === 0 ? {} : { errorCode: 'RUNTIME_EXIT' }) };
    const line = `${JSON.stringify(receipt)}\n`; fs.appendFileSync(target.receipts, line, { encoding: 'utf8', mode: 0o600 }); fs.appendFileSync(target.log, line, { encoding: 'utf8', mode: 0o600 });
    process.exitCode = Number.isInteger(run.status) ? run.status : 1;
  } catch { return; }
}

function gatewayMainSource(systemRoot, expected) {
  return `'use strict';\n(${gatewayBootstrap.toString()})(${JSON.stringify(path.resolve(systemRoot))}, ${JSON.stringify(path.resolve(process.execPath))}, ${JSON.stringify(expected)});\n`;
}

function gatewayWrapper(mainFile, mainDigest) {
  const node = path.resolve(process.execPath);
  return `#!/bin/sh\nunset NODE_OPTIONS NODE_PATH DYLD_INSERT_LIBRARIES DYLD_LIBRARY_PATH DYLD_FRAMEWORK_PATH LD_PRELOAD LD_LIBRARY_PATH BASH_ENV ENV CDPATH\nactual=$(/usr/bin/shasum -a 256 ${JSON.stringify(mainFile)} 2>/dev/null | /usr/bin/awk '{print $1}')\n[ "$actual" = ${JSON.stringify(mainDigest)} ] || exit 0\nexec ${JSON.stringify(node)} ${JSON.stringify(mainFile)}\n`;
}

function buildGlobal(stageRoot, systemRoot, source) {
  const target = layout(stageRoot), final = layout(systemRoot), install = require('./install.js');
  const managedPaths = install.runtimePaths(source);
  for (const rel of managedPaths) {
    const dest = path.join(target.runtime, rel); fs.mkdirSync(path.dirname(dest), { recursive: true });
    fs.copyFileSync(path.join(source, rel), dest); fs.chmodSync(dest, desiredMode(rel));
  }
  const packageDigest = io.digest(target.runtime, managedPaths);
  const files = managedPaths.map((rel) => ({ path: rel, mode: desiredMode(rel).toString(8).padStart(4, '0'), digest: `sha256:${io.sha(fs.readFileSync(path.join(target.runtime, rel)))}` }));
  const allowlist = { schemaVersion: SCHEMA, runtimes: [{ runtimeVersion: install.VERSION, packageDigest, managedPaths: files }] };
  const definition = hooksDefinition(final.gateway, install.VERSION);
  const registry = { schemaVersion: SCHEMA, generation: 1, projects: [] };
  const allowlistText = jsonText(allowlist), definitionText = jsonText(definition);
  const requirements = `[hooks]\nmanaged_dir = ${JSON.stringify(path.dirname(final.definition))}\n# gateway = ${JSON.stringify(final.gateway)}\n`;
  const expected = { runtimeVersion: install.VERSION, generation: 1, managedPaths, packageDigest, files, events: EVENTS, maxInput: MAX_INPUT,
    allowlistDigest: `sha256:${io.sha(allowlistText)}`, definitionDigest: `sha256:${io.sha(definitionText)}`,
    requirementsDigest: `sha256:${io.sha(requirements)}`, hookDefinitionDigest: `sha256:${io.sha(JSON.stringify(canonical(definition.hooks)))}` };
  fs.mkdirSync(path.dirname(target.gatewayMain), { recursive: true });
  const main = gatewayMainSource(systemRoot, expected), mainDigest = io.sha(main), wrapper = gatewayWrapper(final.gatewayMain, mainDigest);
  fs.writeFileSync(target.gatewayMain, main, { mode: 0o644 }); fs.writeFileSync(target.gateway, wrapper, { mode: 0o755 });
  fs.mkdirSync(path.dirname(target.allowlist), { recursive: true });
  fs.writeFileSync(target.allowlist, allowlistText, { mode: 0o600 });
  fs.writeFileSync(target.definition, definitionText, { mode: 0o600 });
  fs.writeFileSync(target.registry, jsonText(registry), { mode: 0o600 });
  fs.mkdirSync(path.dirname(target.receipts), { recursive: true });
  fs.writeFileSync(target.receipts, '', { mode: 0o600 }); fs.writeFileSync(target.log, '', { mode: 0o600 });
  const manifest = {
    schemaVersion: SCHEMA, runtimeVersion: install.VERSION, generation: 1, managedPaths, packageDigest,
    gatewayDigest: digestObject({ wrapper: `sha256:${io.sha(wrapper)}`, main: `sha256:${mainDigest}` }),
    allowlistDigest: expected.allowlistDigest,
    definitionDigest: expected.definitionDigest,
    requirementsDigest: expected.requirementsDigest,
  };
  fs.writeFileSync(target.manifest, jsonText(manifest), { mode: 0o600 });
  return { target, final, manifest, requirements };
}

function image(file) {
  try {
    const stat = fs.lstatSync(file);
    if (!stat.isFile() || stat.isSymbolicLink()) return { file, type: 'unsafe' };
    return { file, type: 'file', body: fs.readFileSync(file), mode: stat.mode & 0o777 };
  } catch (error) { if (error.code === 'ENOENT') return { file, type: 'missing' }; throw error; }
}
function restore(imageValue) {
  if (imageValue.type === 'missing') fs.rmSync(imageValue.file, { force: true });
  else if (imageValue.type === 'file') io.atomic(imageValue.file, imageValue.body, imageValue.mode);
  else throw new Error(`unsafe preimage: ${imageValue.file}`);
}
function directoryPreimage(root, targets) {
  const base = path.resolve(root), missing = new Set();
  try { const stat = fs.lstatSync(base); if (!stat.isDirectory() || stat.isSymbolicLink()) return { ok: false, reason: 'global root 不是安全目录', missing: [] }; }
  catch { return { ok: false, reason: 'global root 不存在', missing: [] }; }
  for (const target of targets) {
    let cursor = path.dirname(path.resolve(target));
    while (cursor !== base) {
      if (!cursor.startsWith(`${base}${path.sep}`)) return { ok: false, reason: 'global 路径越界', missing: [] };
      try { const stat = fs.lstatSync(cursor); if (!stat.isDirectory() || stat.isSymbolicLink()) return { ok: false, reason: `global parent 不是安全目录：${cursor}`, missing: [] }; }
      catch (error) { if (error.code !== 'ENOENT') throw error; missing.add(cursor); }
      cursor = path.dirname(cursor);
    }
  }
  return { ok: true, missing: [...missing].sort((a, b) => b.length - a.length) };
}
function removeCreatedDirectories(plan, recovery) {
  for (const dir of plan.missing) try { fs.rmdirSync(dir); } catch (error) { if (error.code !== 'ENOENT') recovery.push(`directory:${dir}:${error.message}`); }
}

function installGlobal(systemRoot, opts = {}) {
  const boundary = projectBoundary(systemRoot); if (boundary) return boundary;
  const final = layout(systemRoot), source = path.resolve(opts.source || path.join(__dirname, '..'));
  if (!opts.write) return { status: 'READY', written: 0 };
  const directoryPlan = directoryPreimage(final.root, [final.base, final.requirements]);
  if (!directoryPlan.ok) return { status: 'HOLD', written: 0, reason: directoryPlan.reason };
  const requirementBefore = image(final.requirements);
  if (requirementBefore.type === 'unsafe') return { status: 'HOLD', written: 0, reason: 'requirements 不是普通文件' };
  let baseStat = null;
  try { baseStat = fs.lstatSync(final.base); } catch (error) { if (error.code !== 'ENOENT') throw error; }
  if (baseStat && (!baseStat.isDirectory() || baseStat.isSymbolicLink())) return { status: 'HOLD', written: 0, reason: 'global bundle 不是安全目录' };
  const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'harness-lite-global-'));
  const built = buildGlobal(tempRoot, opts.identityRoot || systemRoot, source), stagedBase = built.target.base;
  fs.mkdirSync(path.dirname(final.base), { recursive: true });
  const rollback = path.join(path.dirname(final.base), `.current.rollback-${process.pid}-${Date.now()}`);
  let oldMoved = false, newMoved = false;
  try {
    if (baseStat) { fs.renameSync(final.base, rollback); oldMoved = true; }
    fs.renameSync(stagedBase, final.base); newMoved = true; opts.fault?.('global:bundle:written');
    io.atomic(final.requirements, built.requirements, 0o644); opts.fault?.('global:requirements:written');
    const checked = verifyGlobal(systemRoot); if (!checked.ok) throw new Error(`global verify failed: ${checked.differences.join(',')}`);
    if (oldMoved) fs.rmSync(rollback, { recursive: true });
    fs.rmSync(tempRoot, { recursive: true, force: true });
    return { status: 'INSTALLED', written: 1, manifest: checked.manifest };
  } catch (error) {
    const recovery = [];
    try { restore(requirementBefore); } catch (restoreError) { recovery.push(`requirements:${restoreError.message}`); }
    try { if (newMoved && fs.existsSync(final.base)) fs.rmSync(final.base, { recursive: true }); } catch (restoreError) { recovery.push(`bundle:${restoreError.message}`); }
    try { if (oldMoved && fs.existsSync(rollback)) fs.renameSync(rollback, final.base); } catch (restoreError) { recovery.push(`rollback:${restoreError.message}`); }
    removeCreatedDirectories(directoryPlan, recovery);
    fs.rmSync(tempRoot, { recursive: true, force: true });
    return { status: 'PARTIAL', written: 0, reason: error.message, differences: [error.message, ...recovery] };
  }
}

function safeFile(file, wantedMode, differences, label) {
  try {
    const stat = fs.lstatSync(file);
    if (!stat.isFile() || stat.isSymbolicLink()) { differences.push(`type:${label}`); return false; }
    if ((stat.mode & 0o777) !== wantedMode) differences.push(`mode:${label}`);
    return true;
  } catch { differences.push(`missing:${label}`); return false; }
}

function verifyGlobal(systemRoot) {
  const boundary = projectBoundary(systemRoot); if (boundary) return { ok: false, differences: boundary.differences, reason: boundary.reason, manifest: null };
  const target = layout(systemRoot), differences = [], manifest = io.json(target.manifest);
  if (!manifest || manifest.schemaVersion !== SCHEMA || manifest.runtimeVersion !== RUNTIME_VERSION || !Array.isArray(manifest.managedPaths)) {
    return { ok: false, differences: ['manifest'], manifest: manifest || null };
  }
  safeFile(target.manifest, 0o600, differences, 'manifest.json');
  safeFile(target.gateway, 0o755, differences, 'gateway/gateway');
  safeFile(target.gatewayMain, 0o644, differences, 'gateway/main.cjs');
  safeFile(target.allowlist, 0o600, differences, 'policy/allowlist.json');
  safeFile(target.definition, 0o600, differences, 'policy/hooks.json');
  safeFile(target.registry, 0o600, differences, 'policy/registry.json');
  safeFile(target.receipts, 0o600, differences, 'logs/receipts.jsonl');
  safeFile(target.log, 0o600, differences, 'logs/gateway.log');
  safeFile(target.requirements, 0o644, differences, 'requirements.toml');
  for (const rel of manifest.managedPaths) safeFile(path.join(target.runtime, rel), desiredMode(rel), differences, `runtime/${rel}`);
  const expected = new Set([
    'gateway/gateway', 'gateway/main.cjs', 'policy/allowlist.json', 'policy/hooks.json', 'policy/registry.json',
    'logs/receipts.jsonl', 'logs/gateway.log', 'manifest.json', ...manifest.managedPaths.map((rel) => `runtime/${rel}`),
  ]);
  const actual = io.list(target.base, true).map((file) => path.relative(target.base, file).replaceAll('\\', '/'));
  for (const rel of actual) if (!expected.has(rel)) differences.push(`extra:${rel}`);
  let packageDigest = null;
  try { packageDigest = io.digest(target.runtime, manifest.managedPaths); } catch (error) { differences.push(`runtime:${error.message}`); }
  if (packageDigest !== manifest.packageDigest) differences.push('packageDigest');
  const gatewayDigest = digestObject({ wrapper: `sha256:${io.sha(io.read(target.gateway, ''))}`, main: `sha256:${io.sha(io.read(target.gatewayMain, ''))}` });
  if (gatewayDigest !== manifest.gatewayDigest) differences.push('gatewayDigest');
  if (`sha256:${io.sha(io.read(target.allowlist, ''))}` !== manifest.allowlistDigest) differences.push('allowlistDigest');
  if (`sha256:${io.sha(io.read(target.definition, ''))}` !== manifest.definitionDigest) differences.push('definitionDigest');
  if (`sha256:${io.sha(io.read(target.requirements, ''))}` !== manifest.requirementsDigest) differences.push('requirementsDigest');
  const allowlist = io.json(target.allowlist), registry = io.json(target.registry);
  const listed = allowlist?.schemaVersion === SCHEMA && Array.isArray(allowlist.runtimes) && allowlist.runtimes.length === 1 ? allowlist.runtimes[0] : null;
  let files = [];
  try { files = manifest.managedPaths.map((rel) => ({ path: rel, mode: desiredMode(rel).toString(8).padStart(4, '0'), digest: `sha256:${io.sha(fs.readFileSync(path.join(target.runtime, rel)))}` })); }
  catch { differences.push('allowlist-runtime'); }
  if (!listed || listed.runtimeVersion !== manifest.runtimeVersion || listed.packageDigest !== manifest.packageDigest
    || JSON.stringify(listed.managedPaths) !== JSON.stringify(files)) differences.push('allowlist');
  const validProjects = Array.isArray(registry?.projects) && registry.projects.every((item) => item
    && Object.keys(item).sort().join(',') === 'active,commonDir,generation,packageDigest,projectId,runtimeVersion,worktree'
    && item.active === true && /^[0-9a-f]{24}$/.test(item.projectId || '') && path.isAbsolute(item.worktree || '') && path.isAbsolute(item.commonDir || '')
    && item.generation === manifest.generation && item.runtimeVersion === manifest.runtimeVersion && item.packageDigest === manifest.packageDigest);
  if (registry?.schemaVersion !== SCHEMA || registry.generation !== manifest.generation || !validProjects
    || new Set((registry?.projects || []).map((item) => item.projectId)).size !== (registry?.projects || []).length) differences.push('registry');
  return { ok: differences.length === 0, differences, manifest, allowlist, registry };
}

function gitIdentity(root) {
  if (projectBoundary(root)) return null;
  const resolved = path.resolve(root), run = (args) => spawnSync('/usr/bin/git', args, { cwd: resolved, encoding: 'utf8', env: { PATH: '/usr/bin:/bin' } });
  const top = run(['rev-parse', '--show-toplevel']); if (top.status !== 0) return null;
  const topText = top.stdout.trim(), commonRun = run(['rev-parse', '--git-common-dir']); if (commonRun.status !== 0) return null;
  try {
    const worktree = fs.realpathSync(topText), commonCandidate = path.isAbsolute(commonRun.stdout.trim()) ? commonRun.stdout.trim() : path.resolve(worktree, commonRun.stdout.trim());
    const commonDir = fs.realpathSync(commonCandidate), workStat = fs.lstatSync(worktree), commonStat = fs.lstatSync(commonDir);
    if (!workStat.isDirectory() || workStat.isSymbolicLink() || !commonStat.isDirectory() || commonStat.isSymbolicLink()) return null;
    return { worktree, commonDir, projectId: crypto.createHash('sha256').update(`${worktree}\0${commonDir}`).digest('hex').slice(0, 24) };
  } catch { return null; }
}

function registryImage(systemRoot) {
  const target = layout(systemRoot), checked = verifyGlobal(systemRoot);
  if (!checked.ok) return { ok: false, reason: `global identity: ${checked.differences.join(',')}` };
  const preimage = image(target.registry), registry = checked.registry;
  if (preimage.type !== 'file' || !registry) return { ok: false, reason: 'registry 不是安全普通文件' };
  return { ok: true, target, checked, preimage, registry };
}

function prepareProject(systemRoot, root, active, packageDigest) {
  const boundary = projectBoundary(root); if (boundary) return { ok: false, reason: boundary.reason };
  const state = registryImage(systemRoot); if (!state.ok) return state;
  if (active && packageDigest !== state.checked.manifest.packageDigest) return { ok: false, reason: 'project package digest 不在 global allowlist' };
  const identity = gitIdentity(root); if (!identity) return { ok: false, reason: 'project 不是可 canonicalize 的 Git worktree' };
  const projects = state.registry.projects.filter((item) => item.projectId !== identity.projectId);
  if (active) projects.push({ projectId: identity.projectId, worktree: identity.worktree, commonDir: identity.commonDir,
    generation: state.checked.manifest.generation, runtimeVersion: state.checked.manifest.runtimeVersion, packageDigest, active: true });
  projects.sort((a, b) => a.projectId.localeCompare(b.projectId));
  const value = { schemaVersion: SCHEMA, generation: state.checked.manifest.generation, projects };
  return { ok: true, active, identity, file: state.target.registry, preimage: state.preimage, text: jsonText(value), value };
}

function applyProject(plan, fault = () => {}) {
  if (!plan?.ok) return { ok: false, wrote: false, reason: plan?.reason || 'invalid registry plan' };
  const current = image(plan.file);
  if (current.type !== plan.preimage.type || current.mode !== plan.preimage.mode || !current.body?.equals(plan.preimage.body)) return { ok: false, wrote: false, reason: 'registry 在 preflight 后变化' };
  if (current.body.toString('utf8') === plan.text) return { ok: true, wrote: false, plan };
  try { fault('managed:registry:before'); io.atomic(plan.file, plan.text, plan.preimage.mode); fault('managed:registry:written'); return { ok: true, wrote: true, plan }; }
  catch (error) { try { restore(plan.preimage); } catch (restoreError) { return { ok: false, wrote: false, reason: `${error.message}; rollback:${restoreError.message}` }; } return { ok: false, wrote: false, reason: error.message }; }
}
function rollbackProject(result) {
  if (!result?.ok || !result.wrote) return [];
  try { restore(result.plan.preimage); return []; } catch (error) { return [`registry:${error.message}`]; }
}

function projectState(systemRoot, root) {
  const boundary = projectBoundary(root); if (boundary) return { active: false, reason: boundary.reason };
  const checked = verifyGlobal(systemRoot), identity = gitIdentity(root);
  if (!checked.ok || !identity) return { active: false, reason: checked.ok ? 'not-git' : 'global-invalid' };
  const matches = checked.registry.projects.filter((item) => item.active === true && item.projectId === identity.projectId
    && item.worktree === identity.worktree && item.commonDir === identity.commonDir && item.generation === checked.manifest.generation);
  return { active: matches.length === 1, ambiguous: matches.length > 1, entry: matches.length === 1 ? matches[0] : null, identity };
}

function validInput(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value) || !EVENTS.includes(value.hook_event_name)
    || typeof value.cwd !== 'string' || typeof value.session_id !== 'string') return false;
  if (value.hook_event_name === 'Stop' && typeof value.stop_hook_active !== 'boolean') return false;
  if (value.hook_event_name === 'UserPromptSubmit' && typeof value.prompt !== 'string') return false;
  if (value.hook_event_name === 'PreToolUse' && (typeof value.tool_name !== 'string' || !value.tool_input || typeof value.tool_input !== 'object')) return false;
  return true;
}
function readInput() {
  const chunks = []; let size = 0;
  for (;;) {
    const chunk = Buffer.alloc(Math.min(8192, MAX_INPUT + 1 - size)), count = fs.readSync(0, chunk, 0, chunk.length, null);
    if (!count) break; size += count; if (size > MAX_INPUT) return null; chunks.push(chunk.subarray(0, count));
  }
  return Buffer.concat(chunks).toString('utf8');
}
function childEnv(definitionDigest) {
  return { PATH: '/usr/bin:/bin', LANG: 'C', LC_ALL: 'C', HARNESS_LITE_MANAGED_DEFINITION_DIGEST: definitionDigest };
}
function appendReceipt(target, value) {
  const text = `${JSON.stringify(value)}\n`;
  fs.appendFileSync(target.receipts, text, { encoding: 'utf8', mode: 0o600 });
  fs.appendFileSync(target.log, text, { encoding: 'utf8', mode: 0o600 });
}

function gatewayMain(systemRoot) {
  let raw;
  try { raw = readInput(); } catch { return; }
  if (raw === null) return;
  let input; try { input = JSON.parse(raw); } catch { return; }
  if (!validInput(input)) return;
  if (projectBoundary(process.cwd())) return;
  const checked = verifyGlobal(systemRoot); if (!checked.ok) return;
  const identity = gitIdentity(process.cwd());
  let inputRoot = null; try { inputRoot = fs.realpathSync(path.resolve(input.cwd)); } catch { return; }
  if (!identity || inputRoot !== identity.worktree) return;
  const state = projectState(systemRoot, identity.worktree), entry = state.entry;
  if (!state.active || entry.packageDigest !== checked.manifest.packageDigest || entry.runtimeVersion !== checked.manifest.runtimeVersion) return;
  const install = require('./install.js'), project = install.verify06(identity.worktree);
  if (!project.ok || project.manifest.profile !== 'managed' || project.manifest.packageDigest !== entry.packageDigest) return;
  const dispatcher = path.join(layout(systemRoot).runtime, 'hooks', 'dispatcher.js');
  const definitionDigest = `sha256:${io.sha(JSON.stringify(canonical(checked.allowlist && hooksDefinition(layout(systemRoot).gateway, checked.manifest.runtimeVersion).hooks)))}`;
  const run = spawnSync(path.resolve(process.execPath), [dispatcher], { cwd: identity.worktree, input: raw, encoding: 'utf8', env: childEnv(definitionDigest), shell: false });
  if (run.stdout) process.stdout.write(run.stdout); if (run.stderr) process.stderr.write(run.stderr);
  const receipt = { at: new Date().toISOString(), projectId: identity.projectId, event: input.hook_event_name,
    generation: checked.manifest.generation, digestPrefix: checked.manifest.packageDigest.slice(7, 19), decision: run.status === 0 ? 'executed' : 'runtime-error',
    session: input.session_id, turn: typeof input.turn_id === 'string' ? input.turn_id : null, ...(run.status === 0 ? {} : { errorCode: 'RUNTIME_EXIT' }) };
  try { appendReceipt(layout(systemRoot), receipt); } catch { /* Hook protocol result remains authoritative. */ }
  process.exitCode = Number.isInteger(run.status) ? run.status : 1;
}

module.exports = { SCHEMA, MAX_INPUT, EVENTS, layout, hooksDefinition, installGlobal, verifyGlobal, gitIdentity,
  prepareProject, applyProject, rollbackProject, projectState, gatewayMain };
