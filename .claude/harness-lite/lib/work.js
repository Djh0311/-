'use strict';
const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');
const io = require('./io.js');
const tree = require('./tree.js');
const delegation = require('./delegation.js');
const guidance = require('./guidance.js');
const capabilities = require('./capabilities.js');

const OWN = ['docs/harness/', '.claude/harness-lite/', '.codex/hooks.json'];
const own = (file) => OWN.some((prefix) => file === prefix.replace(/\/$/, '') || file.startsWith(prefix));
const turnDir = (root) => path.join(tree.hdir(root), 'usage', '.turns');
function git(root, args) {
  const result = spawnSync('/usr/bin/git', args, { cwd: root, encoding: 'utf8', maxBuffer: 32 * 1024 * 1024,
    env: { PATH: '/usr/bin:/bin', LANG: 'C', LC_ALL: 'C' } });
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
function compact(items, limit = 6) {
  const rows = (items || []).map((item) => String(item || '').replace(/\s+/g, ' ').trim()).filter(Boolean)
    .map((item) => item.length > 64 ? `${item.slice(0, 61)}...` : item);
  if (!rows.length) return '无';
  return rows.length > limit ? `${rows.slice(0, limit).join('、')}…等${rows.length}项` : rows.join('、');
}
function briefItems(items, limit = 3, itemLimit = 42) {
  const rows = (items || []).map((item) => String(item || '').replace(/\s+/g, ' ').trim()).filter(Boolean)
    .map((item) => item.length > itemLimit ? `${item.slice(0, Math.max(0, itemLimit - 3))}...` : item);
  const hidden = Math.max(0, rows.length - limit), visible = rows.slice(0, limit);
  return { text: visible.length ? `${visible.join('、')}${hidden ? `…+${hidden}` : ''}` : '无',
    count: rows.length, truncated: hidden > 0 };
}
function briefLine(label, items, limit = 3, countName = 'count', itemLimit = 42) {
  const value = briefItems(items, limit, itemLimit);
  return `${label}：${value.text}；${countName}=${value.count}；truncated=${value.truncated}`;
}
function agentLabel(unit) {
  const fields = [unit.channel, unit.model, unit.modelFamily, unit.reasoning].filter(Boolean);
  return fields.length ? `${unit.id}:${fields.join('/')}` : null;
}
function agentRows(summary) {
  return (summary.units || []).map(agentLabel).filter(Boolean);
}
function recoveryNextCode(recovery) {
  if (recovery?.tier === 'astra') return 'astra-xhigh';
  if (recovery?.tier === 'terra') return 'terra-xhigh';
  if (recovery?.tier === 'sol') return 'sol-xhigh';
  if (recovery?.tier === 'exhausted') return 'blocked';
  if (recovery?.tier === 'mixed') return 'per-problem';
  if (recovery?.tier === delegation.UNKNOWN || recovery?.tier === undefined) return 'UNKNOWN';
  return 'ordinary';
}
function recoveryLimitLabel(recovery) {
  return recovery?.tier === 'astra' || (recovery?.leases || []).some((lease) => lease.tier === 'astra' || lease.reason === 'astra-exhausted')
    ? 'recoveryLimit' : 'solLimit';
}
function delegationView(root, chain = tree.readChain(root), opts = {}) {
  const state = delegation.read(root, chain);
  const summary = delegation.summary(state.live ? state.ledger : null, { now: opts.now || opts.date || new Date() });
  return { state, summary };
}
function delegationBriefLines(view) {
  const state = view?.state || {}, summary = view?.summary || delegation.summary(null);
  if (!state.live) return [
    `Delegation：live=false；state=${state.state || delegation.UNKNOWN}；status=UNKNOWN；reason=${state.reason || 'UNKNOWN'}`,
    'Recovery：tier=UNKNOWN；status=UNKNOWN；failureCount=UNKNOWN；next=UNKNOWN；active=UNKNOWN/UNKNOWN；blocked=UNKNOWN/UNKNOWN；drift=UNKNOWN/UNKNOWN；solLimit=UNKNOWN/UNKNOWN；truncated=false',
    'Activity：UNKNOWN；count=UNKNOWN；truncated=false',
    'Progress：UNKNOWN；count=UNKNOWN；truncated=false',
    'Reported：UNKNOWN；count=UNKNOWN；truncated=false',
    'Accepted：UNKNOWN；count=UNKNOWN；truncated=false',
    'Blocked+Partial：Blocked：UNKNOWN；blocked=UNKNOWN；Partial：UNKNOWN；partial=UNKNOWN；truncated=false',
    'Dependencies：UNKNOWN；waiting=UNKNOWN；truncated=false',
    `Heartbeat：read-only；intervalMs=${delegation.HEARTBEAT_MS}；due=UNKNOWN；count=UNKNOWN；truncated=false`,
  ];
  const activity = summary.units.filter((unit) => unit.activityAt || unit.activityKind)
    .map((unit) => `${unit.id}:${unit.activityKind || 'UNKNOWN'}@${unit.activityAt || 'UNKNOWN'}`);
  const progress = summary.semanticProgress.map((unit) => `${unit.id}:${unit.progressKind}@${unit.progressAt} ${unit.evidenceRef}`);
  const waiting = summary.waiting.map((row) => `${row.id}<-${briefItems(row.blockers.map((item) => `${item.id}:${item.status}`), 2).text}`);
  const conflicts = summary.conflicts.map((row) => `${row.units.join('+')}:${row.action}`);
  const blocked = briefItems(summary.blocked, 1, 24), partial = briefItems(summary.partial, 1, 24);
  const hiddenBlockedPartial = blocked.truncated || partial.truncated;
  const heartbeat = briefItems(summary.heartbeat.due);
  const recoveryActive = briefItems(summary.recovery.active, 1, 10);
  const recoveryBlocked = briefItems(summary.recovery.blocked, 1, 10);
  const recoveryDrift = briefItems(summary.recovery.drift, 1, 10);
  const recoveryLimits = briefItems(summary.recovery.recoveryAttemptLimits || summary.recovery.solAttemptLimits, 1, 8);
  return [
    `Delegation：live=true；units=${summary.units.length}；active=${summary.active.length}；runnable=${summary.runnable.length}；conflicts=${conflicts.length}；sample=${briefItems(summary.active, 1, 24).text}`,
    `Recovery：tier=${summary.recovery.tier}；failureCount=${summary.recovery.failureCount}；status=${summary.recovery.status}；next=${recoveryNextCode(summary.recovery)}；active=${recoveryActive.text}/${recoveryActive.count}；blocked=${recoveryBlocked.text}/${recoveryBlocked.count}；drift=${recoveryDrift.text}/${recoveryDrift.count}；${recoveryLimitLabel(summary.recovery)}=${recoveryLimits.text}/${recoveryLimits.count}；truncated=${recoveryActive.truncated || recoveryBlocked.truncated || recoveryDrift.truncated || recoveryLimits.truncated}`,
    briefLine('Activity', activity, 1, 'count', 25),
    briefLine('Progress', progress, 1, 'count', 25),
    briefLine('Reported', summary.reported, 1, 'count', 24),
    briefLine('Accepted', summary.accepted, 1, 'count', 24),
    `Blocked+Partial：Blocked：${blocked.text}；Partial：${partial.text}；blocked=${blocked.count}；partial=${partial.count}；truncated=${hiddenBlockedPartial}`,
    briefLine('Dependencies', waiting, 3, 'waiting'),
    `Heartbeat：read-only；intervalMs=${summary.heartbeat.intervalMs}；mode=${summary.heartbeat.mode}；due=${heartbeat.text}；count=${heartbeat.count}；truncated=${heartbeat.truncated}`,
  ];
}
function delegationLines(view) {
  const state = view?.state || {}, summary = view?.summary || delegation.summary(null);
  if (!state.live) return [
    `Delegation：live=false；state=${state.state || delegation.UNKNOWN}；status=UNKNOWN；reason=${state.reason || 'UNKNOWN'}`,
    `Recovery：tier=UNKNOWN；status=UNKNOWN；failureCount=UNKNOWN；next=UNKNOWN；solLimit=UNKNOWN`,
    `Activity：UNKNOWN`,
    `Progress：UNKNOWN`,
    `Reported：UNKNOWN`,
    `Accepted：UNKNOWN`,
    `Blocked：UNKNOWN；Partial：UNKNOWN`,
    `Dependencies：UNKNOWN`,
    `Heartbeat：read-only；intervalMs=${delegation.HEARTBEAT_MS}；due=UNKNOWN`,
  ];
  const activity = summary.units.filter((unit) => unit.activityAt || unit.activityKind)
    .map((unit) => `${unit.id}:${unit.activityKind || 'UNKNOWN'}@${unit.activityAt || 'UNKNOWN'}`);
  const progress = summary.semanticProgress.map((unit) => `${unit.id}:${unit.progressKind}@${unit.progressAt} ${unit.evidenceRef}`);
  const waiting = summary.waiting.map((row) => `${row.id}<-${compact(row.blockers.map((item) => `${item.id}:${item.status}`), 4)}`);
  const conflicts = summary.conflicts.map((row) => `${row.units.join('+')}:${row.action}`);
  const agents = agentRows(summary);
  return [
    `Delegation：live=true；units=${summary.units.length}；active=${compact(summary.active)}；runnable=${compact(summary.runnable)}；conflicts=${compact(conflicts)}；agents=${compact(agents)}`,
    `Recovery：tier=${summary.recovery.tier}；status=${summary.recovery.status}；failureCount=${summary.recovery.failureCount}；next=${summary.recovery.nextTier}；${recoveryLimitLabel(summary.recovery)}=${compact(summary.recovery.recoveryAttemptLimits || summary.recovery.solAttemptLimits)}；active=${compact(summary.recovery.active)}；blocked=${compact(summary.recovery.blocked)}；drift=${compact(summary.recovery.drift)}`,
    `Activity：${compact(activity)}`,
    `Progress：${compact(progress)}`,
    `Reported：${compact(summary.reported)}`,
    `Accepted：${compact(summary.accepted)}`,
    `Blocked：${compact(summary.blocked)}；Partial：${compact(summary.partial)}`,
    `Dependencies：${waiting.length ? compact(waiting) : '无等待；accepted-only unlock'}`,
    `Heartbeat：read-only；intervalMs=${summary.heartbeat.intervalMs}；mode=${summary.heartbeat.mode}；due=${compact(summary.heartbeat.due)}`,
  ];
}
function relativeSource(root, file) {
  if (!file) return delegation.UNKNOWN;
  return path.relative(root, file).replaceAll('\\', '/') || '.';
}
function knownUnitList(...lists) {
  for (const list of lists) {
    if (Array.isArray(list) && !(list.length === 1 && list[0] === delegation.UNKNOWN)) return list;
  }
  return [delegation.UNKNOWN];
}
function explicit(value) {
  return value || delegation.UNKNOWN;
}
function declaredRunnablePackageIds(packageList) {
  return (packageList?.units || []).filter((pkg) => {
    if (pkg?.status !== 'work-unit' || pkg.dispatchReady !== true) return false;
    const dependencies = Array.isArray(pkg.dependencies) ? pkg.dependencies : [delegation.UNKNOWN];
    // A leaf declaration is enough to expose an independent runnable unit
    // before a delegation ledger exists.  Dependencies still require the
    // normal accepted-only ledger path; never unlock a dependent from a
    // static leaf projection alone.
    return dependencies.length === 0 || dependencies.every((item) => {
      const value = String(item || '').trim().toLowerCase();
      return !value || value === '无' || value === 'none' || value === 'none.';
    });
  }).map((pkg) => pkg.workUnit).filter(Boolean);
}
function parallelWorkUnitContext(root, opts = {}) {
  root = path.resolve(root);
  const chain = opts.chain || tree.readChain(root), view = opts.delegation || delegationView(root, chain, opts);
  const summary = view?.summary || delegation.summary(null), state = view?.state || {};
  const source = {
    leaf: chain.leaf ? relativeSource(root, chain.leaf.file) : delegation.UNKNOWN,
    stage: chain.stage ? relativeSource(root, chain.stage.file) : delegation.UNKNOWN,
    delegation: delegation.RELATIVE_PATH,
  };
  const base = {
    schemaVersion: 1,
    kind: 'harness-lite-parallel-work-unit-context',
    acceptedOnlyUnlock: true,
    branchLocalFreeze: true,
    source,
    carrier: {
      readApi: 'work.parallelWorkUnitContext',
      complete: delegation.UNKNOWN,
      truncated: false,
      source,
    },
  };
  const declaredPackages = tree.workUnitPackages(root, null, chain);
  const declaredRunnable = declaredRunnablePackageIds(declaredPackages);
  const missingLedger = state.state === delegation.UNKNOWN && state.reason === 'missing';
  if (!state.live && missingLedger && declaredRunnable.length) {
    const packageIds = declaredRunnable;
    const packageList = tree.workUnitPackages(root, packageIds, chain);
    const packages = new Map((packageList.units || []).map((pkg) => [pkg.workUnit, pkg]));
    const units = packageIds.map((id) => {
      const pkg = packages.get(id) || tree.workUnitPackage(root, id, chain);
      const dependencies = knownUnitList(pkg.dependencies);
      const writeScope = knownUnitList(pkg.writeScope, pkg.allowed);
      return {
        schemaVersion: pkg.schemaVersion || 1,
        kind: pkg.kind || 'harness-lite-work-unit-package',
        id,
        workUnit: explicit(pkg.workUnit),
        stage: explicit(pkg.stage),
        leaf: explicit(pkg.leaf),
        // No ledger row means no claimed execution state.  The package is
        // nevertheless runnable because the current leaf explicitly declares
        // it and its dependency set is empty.
        status: 'runnable',
        packageStatus: explicit(pkg.status),
        goal: explicit(pkg.goal),
        completionStandards: knownUnitList(pkg.completionStandards),
        dispatchReady: pkg.dispatchReady === true,
        readiness: explicit(pkg.readiness),
        allowed: knownUnitList(pkg.allowed),
        forbidden: knownUnitList(pkg.forbidden),
        authorityDesign: knownUnitList(pkg.authorityDesign),
        facts: knownUnitList(pkg.facts),
        entryPoints: knownUnitList(pkg.entryPoints),
        disprovenRoutes: knownUnitList(pkg.disprovenRoutes),
        unknowns: knownUnitList(pkg.unknowns),
        routeBasis: explicit(pkg.routeBasis),
        dependencies,
        writeScope,
        resultContract: explicit(pkg.resultContract),
        source: pkg.source || { leaf: null, stage: null },
        package: pkg,
        boundaries: {
          allowed: knownUnitList(pkg.boundaries?.allowed, pkg.allowed),
          forbidden: knownUnitList(pkg.boundaries?.forbidden, pkg.forbidden),
          writeScope,
        },
        channel: delegation.UNKNOWN,
        model: delegation.UNKNOWN,
        modelFamily: delegation.UNKNOWN,
        reasoning: delegation.UNKNOWN,
        agent: { channel: delegation.UNKNOWN, model: delegation.UNKNOWN, modelFamily: delegation.UNKNOWN, reasoning: delegation.UNKNOWN, status: 'runnable' },
        selection: pkg.selection || 'declared-runnable',
      };
    });
    const complete = Object.hasOwn(packageList, 'complete') ? packageList.complete : delegation.UNKNOWN;
    const status = complete === 'complete' ? 'complete' : complete === 'incomplete' ? 'incomplete' : delegation.UNKNOWN;
    return {
      ...base,
      state: 'known',
      delegationState: 'declared',
      status,
      complete,
      reason: state.reason || 'declared-runnable-without-ledger',
      active: [],
      activeCount: packageIds.length,
      runningCount: 0,
      packageIds,
      packageCount: packageIds.length,
      selection: packageIds.length > 1 ? 'runnable' : 'single-declared-runnable',
      runnable: packageIds,
      units,
      conflicts: [],
      waiting: [],
      reported: [],
      accepted: [],
      blocked: [],
      partial: [],
      packageList: { complete, missing: packageList.missing || [], count: packageList.count || 0 },
      carrier: { readApi: 'work.parallelWorkUnitContext', complete, truncated: false, source },
    };
  }
  if (!state.live) {
    return {
      ...base,
      state: state.state || delegation.UNKNOWN,
      status: delegation.UNKNOWN,
      complete: delegation.UNKNOWN,
      reason: state.reason || delegation.UNKNOWN,
      active: [],
      activeCount: delegation.UNKNOWN,
      runnable: [],
      units: [],
      conflicts: [],
      waiting: [],
      reported: [],
      accepted: [],
      blocked: [],
      partial: [],
    };
  }
  const active = summary.active || [];
  // Once a ledger is live, its accepted-only lifecycle remains authoritative;
  // Static declarations may supplement a ledger that contains only rejected
  // or otherwise non-running rows (there is no active/blocking claim).  Once
  // an active/reported/partial/blocked/accepted row exists, the ledger stays
  // authoritative and unrecorded declarations are not unlocked.
  const ledgerUnitIds = new Set((summary.units || []).map((unit) => unit.id));
  const blockingStatuses = new Set(['active', 'reported_complete', 'partial', 'blocked', 'accepted']);
  const canProjectUnrecorded = active.length === 0 && !(summary.units || []).some((unit) => blockingStatuses.has(unit.status));
  const unrecordedRunnable = canProjectUnrecorded ? declaredRunnable.filter((id) => !ledgerUnitIds.has(id)) : [];
  const runnable = [...new Set([...(summary.runnable || []), ...unrecordedRunnable])];
  const packageIds = runnable.length > 1 ? [...new Set([...active, ...runnable])] : active.length ? [...active] : [...runnable];
  const packageList = tree.workUnitPackages(root, packageIds, chain);
  const packages = new Map((packageList.units || []).map((pkg) => [pkg.workUnit, pkg]));
  const summaryUnits = new Map((summary.units || []).map((unit) => [unit.id, unit]));
  const units = packageIds.map((id) => {
    const pkg = packages.get(id) || tree.workUnitPackage(root, id, chain), unit = summaryUnits.get(id) || {};
    const dependencies = knownUnitList(unit.dependencies, pkg.dependencies);
    const writeScope = knownUnitList(unit.writeScope, pkg.writeScope, pkg.allowed);
    return {
      schemaVersion: pkg.schemaVersion || 1,
      kind: pkg.kind || 'harness-lite-work-unit-package',
      id,
      workUnit: explicit(pkg.workUnit),
      stage: explicit(pkg.stage),
      leaf: explicit(pkg.leaf),
      status: Object.hasOwn(unit, 'status') ? explicit(unit.status) : declaredRunnable.includes(id) ? 'runnable' : delegation.UNKNOWN,
      packageStatus: explicit(pkg.status),
      goal: explicit(pkg.goal),
      completionStandards: knownUnitList(pkg.completionStandards),
      dispatchReady: pkg.dispatchReady === true,
      readiness: explicit(pkg.readiness),
      allowed: knownUnitList(pkg.allowed),
      forbidden: knownUnitList(pkg.forbidden),
      authorityDesign: knownUnitList(pkg.authorityDesign),
      facts: knownUnitList(pkg.facts),
      entryPoints: knownUnitList(pkg.entryPoints),
      disprovenRoutes: knownUnitList(pkg.disprovenRoutes),
      unknowns: knownUnitList(pkg.unknowns),
      routeBasis: explicit(pkg.routeBasis),
      dependencies,
      writeScope,
      resultContract: explicit(pkg.resultContract),
      source: pkg.source || { leaf: null, stage: null },
      package: pkg,
      boundaries: {
        allowed: knownUnitList(pkg.boundaries?.allowed, pkg.allowed),
        forbidden: knownUnitList(pkg.boundaries?.forbidden, pkg.forbidden),
        writeScope,
      },
      channel: explicit(unit.channel),
      model: explicit(unit.model),
      modelFamily: explicit(unit.modelFamily),
      reasoning: explicit(unit.reasoning),
      agent: {
        channel: explicit(unit.channel),
        model: explicit(unit.model),
        modelFamily: explicit(unit.modelFamily),
        reasoning: explicit(unit.reasoning),
        status: Object.hasOwn(unit, 'status') ? explicit(unit.status) : declaredRunnable.includes(id) ? 'runnable' : delegation.UNKNOWN,
      },
      selection: pkg.selection || delegation.UNKNOWN,
    };
  });
  const status = (summary.conflicts || []).length ? 'conflict' : packageList.complete === 'incomplete' ? 'incomplete' : 'complete';
  const complete = Object.hasOwn(packageList, 'complete') ? packageList.complete : delegation.UNKNOWN;
  return {
    ...base,
    state: 'known',
    delegationState: 'live',
    status,
    complete,
    reason: null,
    active,
    activeCount: packageIds.length,
    runningCount: active.length,
    packageIds,
    packageCount: packageIds.length,
    selection: runnable.length > 1 ? active.length ? 'active-and-runnable' : 'runnable'
      : active.length ? 'active' : runnable.length ? 'runnable' : 'none',
    runnable,
    units,
    conflicts: summary.conflicts || [],
    waiting: summary.waiting || [],
    reported: summary.reported || [],
    accepted: summary.accepted || [],
    blocked: summary.blocked || [],
    partial: summary.partial || [],
    packageList: {
      complete,
      missing: packageList.missing || [],
      count: packageList.count || 0,
    },
    carrier: {
      readApi: 'work.parallelWorkUnitContext',
      complete,
      truncated: false,
      source,
    },
  };
}
function parallelUnitLine(unit) {
  const standards = briefItems(unit.completionStandards, 2, 38);
  const design = briefItems(unit.authorityDesign, 1, 32);
  const facts = briefItems(unit.facts, 1, 32);
  const deps = briefItems(unit.dependencies, 3, 24);
  const writeScope = briefItems(unit.writeScope, 3, 30);
  const agent = [unit.channel, unit.model, unit.modelFamily, unit.reasoning]
    .filter((item) => item && item !== delegation.UNKNOWN).map((item) => String(item).replace(/\s+/g, ' ').trim()).join('/');
  return `ParallelUnit：id=${unit.id}；status=${unit.status}；goal=${String(unit.goal || delegation.UNKNOWN).replace(/\s+/g, ' ').trim().slice(0, 72)}；完成标准=${standards.text}；相关权威设计=${design.text}；相关事实=${facts.text}；deps=${deps.text}；writeScope=${writeScope.text}；agent=${agent || delegation.UNKNOWN}`;
}
function parallelWorkUnitLines(context, opts = {}) {
  const ctx = context || {}, maxInline = Number.isInteger(opts.maxInlineUnits) ? opts.maxInlineUnits : 6;
  const runningCount = ctx.runningCount ?? ctx.active?.length ?? ctx.activeCount ?? delegation.UNKNOWN;
  const header = `ParallelWorkUnits：state=${ctx.state || delegation.UNKNOWN}；status=${ctx.status || delegation.UNKNOWN}；complete=${ctx.complete || delegation.UNKNOWN}；active=${runningCount}；units=${ctx.units?.length ?? 0}；conflicts=${ctx.conflicts?.length ?? 0}；carrier=${ctx.carrier?.readApi || 'work.parallelWorkUnitContext'}；runnable=${ctx.runnable?.length ?? delegation.UNKNOWN}`;
  if (ctx.state !== 'known') return [header];
  if ((ctx.units || []).length <= maxInline) return [header, ...(ctx.units || []).map(parallelUnitLine)];
  const visible = (ctx.units || []).slice(0, maxInline).map(parallelUnitLine);
  return [
    header,
    ...visible,
    `ParallelWorkUnitsCarrier：complete=${ctx.complete || delegation.UNKNOWN}；remaining=${ctx.units.length - visible.length}；source=${ctx.source?.delegation || delegation.RELATIVE_PATH}；readApi=${ctx.carrier?.readApi || 'work.parallelWorkUnitContext'}`,
  ];
}
function semanticProgressSince(view, since) {
  const sinceTime = Date.parse(since || '');
  return (view?.summary?.semanticProgress || []).filter((item) => {
    const at = Date.parse(item.progressAt || '');
    return Number.isFinite(at) && (!Number.isFinite(sinceTime) || at >= sinceTime);
  });
}
function report(root, data, opts = {}) {
  const chain = data.chain || tree.readChain(root), progress = tree.progress(root, chain);
  const change = data.delta || { changed: [], inherited: [], unknown: [] }, productChanges = change.changed.filter((x) => !own(x));
  const out = outOfScope(change.changed, chain.allowed), verification = data.verification;
  const delegate = data.delegation || delegationView(root, chain, opts);
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
    ...delegationLines(delegate),
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
  const usage = path.join(tree.hdir(root), 'usage'), turnRows = io.list(turnDir(root), false)
    .filter((file) => file.endsWith('.json') && path.basename(file) !== '.push.json').map((file) => io.json(file, {}));
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
const GRAPH_VERSION = 1;
const MAX_EXTERNAL_GRAPH_BYTES = 32 * 1024 * 1024;
const MAX_EXTERNAL_META_BYTES = 64 * 1024;
const CODE_FILE = /\.(?:[cm]?js|jsx|tsx?|py|rs|go|java|cs|rb|php)$/i;
const GRAPH_EXCLUDE = /(?:^|\/)(?:node_modules|dist|build|coverage|vendor|\.git|\.ua|\.understand-anything)(?:\/|$)/;
const normalizeRel = (value) => String(value || '').replaceAll('\\', '/').replace(/^\.\//, '');
const codeFile = (file) => CODE_FILE.test(file) && !GRAPH_EXCLUDE.test(normalizeRel(file));
function graphFile(root) {
  const raw = (git(root, ['rev-parse', '--git-path', 'harness-lite/code-map.json']) || '').trim();
  if (!raw) return null;
  return path.isAbsolute(raw) ? raw : path.resolve(root, raw);
}
const head = (root) => (git(root, ['rev-parse', 'HEAD']) || '').trim() || null;
function validGraph(value) {
  return !!value && value.version === GRAPH_VERSION && value.kind === 'harness-lite-code-map'
    && /^[0-9a-f]{40,64}$/.test(value.baseHead || '') && value.files && typeof value.files === 'object' && !Array.isArray(value.files);
}
function cachedGraph(root) {
  const file = graphFile(root), value = file ? io.json(file) : null;
  return { file, value: validGraph(value) ? value : null, invalid: !!file && fs.existsSync(file) && !validGraph(value) };
}
function regularJson(file, maxBytes) {
  let stat; try { stat = fs.lstatSync(file); } catch { return { ok: false, reason: 'missing' }; }
  if (!stat.isFile() || stat.isSymbolicLink()) return { ok: false, reason: 'not-regular-file' };
  if (stat.size > maxBytes) return { ok: false, reason: 'too-large' };
  const value = io.json(file); return value == null ? { ok: false, reason: 'invalid-json' } : { ok: true, value };
}
function safeExternalPath(value) {
  if (typeof value !== 'string' || !value || value.includes('\0') || path.isAbsolute(value) || /^[A-Za-z]:[\\/]/.test(value)) return false;
  const normalized = value.replaceAll('\\', '/'); return !normalized.split('/').includes('..') && !normalized.startsWith('/');
}
function externalGraph(root) {
  for (const dir of ['.ua', '.understand-anything']) {
    const dataDir = path.join(root, dir); let dirStat; try { dirStat = fs.lstatSync(dataDir); } catch { continue; }
    const file = path.join(dataDir, 'knowledge-graph.json'), metaFile = path.join(dataDir, 'meta.json');
    if (!dirStat.isDirectory() || dirStat.isSymbolicLink()) return { file, valid: false, head: null, value: null, reason: 'unsafe-directory' };
    const graphInput = regularJson(file, MAX_EXTERNAL_GRAPH_BYTES), metaInput = regularJson(metaFile, MAX_EXTERNAL_META_BYTES);
    if (!graphInput.ok || !metaInput.ok) return { file, valid: false, head: null, value: null, reason: graphInput.ok ? `meta-${metaInput.reason}` : `graph-${graphInput.reason}` };
    const value = graphInput.value, meta = metaInput.value;
    if (!value.project || typeof value.project !== 'object' || Array.isArray(value.project) || !Array.isArray(value.nodes) || !Array.isArray(value.edges)
      || value.nodes.some((node) => node?.filePath != null && !safeExternalPath(node.filePath))) {
      return { file, valid: false, head: null, value: null, reason: 'invalid-shape-or-path' };
    }
    const baseHead = meta?.gitCommitHash || null;
    return { file, valid: /^[0-9a-f]{40,64}$/.test(baseHead || ''), head: baseHead, value,
      reason: /^[0-9a-f]{40,64}$/.test(baseHead || '') ? null : 'invalid-head' };
  }
  return null;
}
function dirtyCode(root) {
  return (statusPaths(root) || []).map((row) => row.path).filter(codeFile).sort();
}
function graphState(root) {
  const currentHead = head(root), cache = cachedGraph(root), external = externalGraph(root), dirty = dirtyCode(root);
  const candidates = [cache.value ? { source: 'harness-lite', file: cache.file, baseHead: cache.value.baseHead } : null,
    external?.valid ? { source: 'understand-anything', file: external.file, baseHead: external.head } : null].filter(Boolean);
  const current = candidates.find((item) => currentHead && item.baseHead === currentHead);
  const selected = current || candidates[0] || null;
  return { status: current ? 'current' : selected ? 'stale' : 'unavailable', source: selected?.source || null,
    file: selected?.file || cache.file || external?.file || null, baseHead: selected?.baseHead || null, head: currentHead,
    dirty, dirtyCount: dirty.length, invalid: cache.invalid || (!!external && !external.valid) };
}
function rawImports(file, text) {
  const found = new Set(), source = String(text || '');
  if (/\.(?:[cm]?js|jsx|tsx?)$/i.test(file)) {
    for (const match of source.matchAll(/(?:\bfrom\s*|\brequire\s*\(|\bimport\s*\()\s*['"]([^'"]+)['"]/g)) found.add(match[1]);
  } else if (/\.py$/i.test(file)) {
    for (const match of source.matchAll(/^\s*(?:from|import)\s+([A-Za-z0-9_.]+)/gm)) found.add(match[1]);
  } else if (/\.go$/i.test(file)) {
    for (const match of source.matchAll(/(?:^|\s)"([^"]+)"/gm)) found.add(match[1]);
  } else if (/\.rs$/i.test(file)) {
    for (const match of source.matchAll(/^\s*(?:mod|use)\s+([A-Za-z0-9_:]+)/gm)) found.add(match[1]);
  }
  return [...found];
}
function exportsOf(file, text) {
  const found = new Set(), source = String(text || '');
  for (const match of source.matchAll(/\bexport\s+(?:async\s+)?(?:function|class|const|let|var|interface|type|enum)\s+([A-Za-z_$][\w$]*)/g)) found.add(match[1]);
  for (const match of source.matchAll(/\b(?:module\.)?exports\.([A-Za-z_$][\w$]*)\s*=/g)) found.add(match[1]);
  for (const match of source.matchAll(/\bmodule\.exports\s*=\s*\{([\s\S]*?)\}/g)) {
    for (const item of match[1].split(',')) { const name = item.trim().match(/^([A-Za-z_$][\w$]*)/)?.[1]; if (name) found.add(name); }
  }
  if (/\.py$/i.test(file)) for (const match of source.matchAll(/^(?:async\s+def|def|class)\s+([A-Za-z_][\w]*)/gm)) found.add(match[1]);
  return [...found].sort();
}
function resolveImport(file, specifier, paths) {
  if (!specifier.startsWith('.')) return null;
  const base = path.posix.normalize(path.posix.join(path.posix.dirname(file), specifier.replace(/[?#].*$/, ''))), candidates = [base];
  if (!path.posix.extname(base)) for (const ext of ['.js', '.cjs', '.mjs', '.jsx', '.ts', '.tsx', '.py', '.rs', '.go']) candidates.push(`${base}${ext}`, `${base}/index${ext}`);
  return candidates.map(normalizeRel).find((item) => paths.has(item)) || null;
}
function moduleRow(file, text, paths) {
  const imports = rawImports(file, text);
  return { file, lines: String(text || '').split('\n').length, exports: exportsOf(file, text), rawImports: imports,
    imports: [...new Set(imports.map((item) => resolveImport(file, item, paths)).filter(Boolean))].sort() };
}
function headCodeFiles(root, currentHead) {
  const output = git(root, ['ls-tree', '-rz', '--name-only', currentHead]);
  return output == null ? null : output.split('\0').filter(Boolean).map(normalizeRel).filter(codeFile).sort();
}
function headSource(root, currentHead, file) { return git(root, ['show', `${currentHead}:${file}`]); }
function buildHeadGraph(root, currentHead, files) {
  const paths = new Set(files), out = {};
  for (const file of files) { const text = headSource(root, currentHead, file); if (text != null) out[file] = moduleRow(file, text, paths); }
  return out;
}
function refreshGraph(root, opts = {}) {
  const currentHead = head(root), file = graphFile(root);
  if (!currentHead || !file) return { ok: false, wrote: false, status: 'unavailable', reason: '没有可用 Git HEAD' };
  const all = headCodeFiles(root, currentHead); if (!all) return { ok: false, wrote: false, status: 'unavailable', reason: '无法读取 HEAD tree' };
  const prior = cachedGraph(root).value, allSet = new Set(all); let mode = 'rebuild', changed = all, files;
  if (prior && prior.baseHead === currentHead) { mode = 'current'; changed = []; files = prior.files; }
  else if (prior && git(root, ['merge-base', '--is-ancestor', prior.baseHead, currentHead]) !== null) {
    const raw = git(root, ['diff', '--name-only', '-z', prior.baseHead, currentHead]);
    if (raw != null) {
      changed = raw.split('\0').filter(Boolean).map(normalizeRel);
      const structural = changed.some((item) => /(?:^|\/)(?:package\.json|pyproject\.toml|go\.mod|Cargo\.toml|tsconfig[^/]*\.json|pnpm-workspace\.yaml)$/.test(item));
      const affected = changed.filter((item) => codeFile(item) || prior.files[item]).length;
      if (!structural && affected <= Math.max(200, Math.ceil(all.length * 0.25))) {
        mode = 'incremental'; files = { ...prior.files };
        for (const old of Object.keys(files)) if (!allSet.has(old)) delete files[old];
        for (const item of changed) {
          if (!allSet.has(item)) { delete files[item]; continue; }
          const text = headSource(root, currentHead, item); if (text != null) files[item] = moduleRow(item, text, allSet);
        }
        for (const item of Object.values(files)) item.imports = [...new Set((item.rawImports || []).map((spec) => resolveImport(item.file, spec, allSet)).filter(Boolean))].sort();
      }
    }
  }
  if (!files) files = buildHeadGraph(root, currentHead, all);
  const value = { version: GRAPH_VERSION, kind: 'harness-lite-code-map', baseHead: currentHead,
    generatedAt: new Date().toISOString(), updateMode: mode, files };
  if (opts.write && mode !== 'current') io.atomic(file, `${JSON.stringify(value, null, 2)}\n`, 0o600);
  return { ok: true, wrote: !!opts.write && mode !== 'current', status: 'current', mode, baseHead: currentHead,
    changed: changed.filter((item) => codeFile(item) || prior?.files?.[item]).sort(), file, graph: value };
}
function externalRows(value) {
  const fileTypes = new Set(['file', 'config', 'service', 'pipeline', 'schema', 'resource', 'endpoint']), byId = new Map();
  for (const node of value.nodes || []) if (fileTypes.has(node?.type) && typeof node.filePath === 'string' && codeFile(node.filePath)) byId.set(node.id, normalizeRel(node.filePath));
  const imported = new Map([...byId.values()].map((file) => [file, []]));
  for (const edge of value.edges || []) if (edge?.type === 'imports' && byId.has(edge.source) && byId.has(edge.target)) imported.get(byId.get(edge.source)).push(byId.get(edge.target));
  return [...byId.entries()].map(([id, file]) => ({ file, lines: null, exports: [], imports: [...new Set(imported.get(file))].sort(), graphNode: id }));
}
function walkCode(root, dir, out) {
  let entries; try { entries = fs.readdirSync(dir, { withFileTypes: true }); } catch { return; }
  for (const entry of entries) {
    const file = path.join(dir, entry.name), rel = normalizeRel(path.relative(root, file));
    if (GRAPH_EXCLUDE.test(rel)) continue;
    if (entry.isDirectory()) walkCode(root, file, out);
    else if (entry.isFile() && codeFile(rel)) out.push(rel);
  }
}
function workingRows(root, dirs) {
  const scopes = dirs.map((dir) => { io.safe(root, dir); return normalizeRel(dir).replace(/\/$/, ''); });
  const listed = git(root, ['ls-files', '-z', '--cached', '--others', '--exclude-standard']); let candidates = [];
  if (listed != null) candidates = listed.split('\0').filter(Boolean).map(normalizeRel).filter(codeFile);
  else {
    const bases = scopes.length ? scopes.map((scope) => io.safe(root, scope)) : [root];
    for (const base of bases) {
      let stat; try { stat = fs.lstatSync(base); } catch { continue; }
      if (stat.isFile() && !stat.isSymbolicLink()) candidates.push(normalizeRel(path.relative(root, base)));
      else if (stat.isDirectory() && !stat.isSymbolicLink()) walkCode(root, base, candidates);
    }
  }
  const files = [...new Set(candidates)].filter((file) => !scopes.length || scopes.some((scope) => file === scope || file.startsWith(`${scope}/`)))
    .filter((file) => { try { const stat = fs.lstatSync(io.safe(root, file)); return stat.isFile() && !stat.isSymbolicLink(); } catch { return false; } }).sort();
  const paths = new Set(files); return files.map((file) => moduleRow(file, fs.readFileSync(io.safe(root, file), 'utf8'), paths));
}
function scoped(rows, dirs) {
  const scopes = dirs.map((item) => normalizeRel(item).replace(/\/$/, ''));
  return (scopes.length ? rows.filter((row) => scopes.some((scope) => row.file === scope || row.file.startsWith(`${scope}/`))) : rows).slice(0, 40);
}
function map(root, dirs = [], opts = {}) {
  let state = graphState(root), rows, refresh = null, mode;
  if (opts.refresh) {
    refresh = refreshGraph(root, { write: !!opts.write });
    if (refresh.ok) { rows = Object.values(refresh.graph.files); state = { ...state, status: 'current', source: 'harness-lite', baseHead: refresh.baseHead, file: refresh.file }; mode = refresh.mode; }
  }
  if (!rows && state.status === 'current' && state.source === 'harness-lite') { rows = Object.values(cachedGraph(root).value.files); mode = 'commit-graph'; }
  if (!rows && state.status === 'current' && state.source === 'understand-anything') { rows = externalRows(externalGraph(root).value); mode = 'external-graph'; }
  if (!rows) { rows = workingRows(root, dirs); mode = 'source-fallback'; }
  const result = scoped(rows, dirs); result.ok = !refresh || refresh.ok; result.graph = { ...state, mode, refresh: refresh ? { ok: refresh.ok, wrote: refresh.wrote, mode: refresh.mode, reason: refresh.reason || null } : null,
    bounded: true, returned: result.length };
  return result;
}
function mistake(root, text, opts = {}) {
  const file = path.join(tree.hdir(root), 'MISTAKES.md'), body = io.read(file, '');
  if (!opts.add) return body.split('\n').filter((line) => line.startsWith('- ') && (!text || line.toLowerCase().includes(text.toLowerCase())));
  const value = String(text || '').replace(/\s+/g, ' ').trim(); if (!value) throw new Error('错题内容为空');
  const line = `- ${new Date().toISOString().slice(0, 10)} ${value}`;
  if (opts.write) { fs.mkdirSync(path.dirname(file), { recursive: true }); fs.appendFileSync(file, `${body ? '' : '# 错题本\n\n'}${line}\n`); }
  return { wrote: !!opts.write, line, file };
}
function status(root, opts = {}) {
  const chain = tree.readChain(root), snap = snapshot(root), health = (() => { try { return require('./install.js').health(root); } catch { return {}; } })(), usage = usageSummary(root), graph = graphState(root);
  const delegate = delegationView(root, chain, opts);
  const authority = chain.authority, baselineText = authority.status === 'current'
    ? `current ${authority.digest.slice(0, 19)}；确认来源 ${authority.confirmationSource}（仅 provenance）` : authority.status;
  const reviewText = authority.review.status === 'current' ? `current ${path.basename(authority.review.file)}` : authority.review.status;
  const graphText = `${graph.status}${graph.baseHead ? ` ${graph.baseHead.slice(0, 12)}` : ''}${graph.dirtyCount ? `；${graph.dirtyCount} 个未提交代码文件未进入图谱` : ''}`;
  const eventGuidance = guidance.select(chain, delegate, { intent: opts.intent });
  const guidanceEvents = new Set(eventGuidance.events);
  if (guidanceEvents.has('pre-dispatch')) {
    const runnable = delegate.summary.runnable || [];
    eventGuidance.workUnits = tree.workUnitPackages(root, runnable.length ? runnable : null, chain);
    eventGuidance.capabilities = capabilities.project(root, { writeDynamicCarrier: false });
  }
  if (guidanceEvents.has('agent-active')) {
    eventGuidance.active = [...delegate.summary.active];
    eventGuidance.heartbeat = { ...delegate.summary.heartbeat };
  }
  if (guidanceEvents.has('agent-reported')) eventGuidance.reported = [...delegate.summary.reported];
  if (guidanceEvents.has('problem-recovery')) eventGuidance.recovery = delegate.summary.recovery;
  if (guidanceEvents.has('leaf-closeout')) {
    eventGuidance.closeout = {
      accepted: [...delegate.summary.accepted],
      completionStandards: [...(chain.leaf?.completionStandards || [delegation.UNKNOWN])],
    };
  }
  const guidanceText = eventGuidance.text ? `\nGuidanceEvents：${eventGuidance.events.join('、')}\n${eventGuidance.text}` : '';
  return { chain, progress: tree.progress(root, chain), git: { repo: snap.repo, head: snap.head, dirty: Object.keys(snap.files) }, usage, health, authority, graph,
    delegation: delegate, guidance: eventGuidance,
    text: `${tree.format(chain)}\n需求基线：${baselineText}；计划复核：${reviewText}\n代码图谱：${graphText}${guidanceText}\nUsage：${usage.turns} 轮，${usage.files} 个产品文件\nRuntime：${JSON.stringify(health)}` };
}

module.exports = { OWN, own, turnDir, git, statusPaths, snapshot, delta, outOfScope, report, appendUsage, receipt, latestVerify, checks,
  pushArgv, testsFor, verify, usageSummary, graphFile, graphState, refreshGraph, map, mistake, delegationView, delegationBriefLines, delegationLines,
  parallelWorkUnitContext, parallelWorkUnitLines, semanticProgressSince, status };
