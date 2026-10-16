'use strict';
const fs = require('fs');
const path = require('path');
const io = require('./io.js');

const hdir = (root) => path.join(root, 'docs', 'harness');
const md = (dir) => io.list(dir, false).filter((f) => f.endsWith('.md'));
const field = (text, name) => (String(text).match(new RegExp(`^\\s*${name}[:：]\\s*(.+)$`, 'm')) || [])[1]?.trim() || null;
const title = (text, fallback) => (String(text).match(/^#\s+(.+)$/m) || [])[1]?.trim() || fallback;
const BASELINE_BEGIN = '<!-- REQUIREMENT-BASELINE:BEGIN -->';
const BASELINE_END = '<!-- REQUIREMENT-BASELINE:END -->';
const UNKNOWN = 'UNKNOWN';
const FIELD_ALIASES = Object.freeze({
  goal: ['goal', '目标'],
  completionStandards: ['completionStandards', '完成标准', 'directAcceptance', 'direct acceptance', '直接验收', '验收标准'],
  allowed: ['allowed', '允许动'],
  forbidden: ['forbidden', '不许动', '禁止'],
  authorityDesign: ['authorityDesign', 'authority design', '相关权威设计', '权威设计'],
  facts: ['facts', '相关事实', '事实'],
  entryPoints: ['entryPoints', 'entry points', '入口', '相关入口'],
  disprovenRoutes: ['disprovenRoutes', 'disproven routes', '已否定路线', '否定路线'],
  unknowns: ['unknowns', 'UNKNOWN', '未知'],
  routeBasis: ['routeBasis', 'route basis', '路线依据'],
  dependencies: ['dependencies', '依赖'],
  resultContract: ['resultContract', 'result contract', '结果合同', '报告合同'],
});

function bullets(text, name) {
  const lines = String(text).split('\n'), at = lines.findIndex((line) => new RegExp(`^${name}[:：]\\s*$`).test(line.trim()));
  if (at < 0) return [];
  const out = [];
  for (const line of lines.slice(at + 1)) {
    const value = line.trim();
    if (!value) { if (out.length) break; else continue; }
    if (!value.startsWith('- ')) break;
    out.push(value.slice(2).trim());
  }
  return out;
}
function values(text, names) {
  for (const name of names) {
    const list = bullets(text, name); if (list.length) return list;
    const value = field(text, name); if (value) return [value];
  }
  return [];
}
function listValue(text, names, opts = {}) {
  const list = values(text, names).flatMap((item) => String(item).split(/[;,，、]/).map((part) => part.trim()).filter(Boolean));
  if (!list.length) return [UNKNOWN];
  if (opts.noneAsEmpty && list.length === 1 && /^(?:none|no|n\/a|无)$/i.test(list[0])) return [];
  return list;
}
function textValue(text, names) {
  const value = field(text, names[0]) || names.slice(1).map((name) => field(text, name)).find(Boolean);
  if (value) return value;
  const list = values(text, names);
  return list.length ? list.join('；') : UNKNOWN;
}
function isUnknownList(value) {
  return !Array.isArray(value) || (value.length === 1 && value[0] === UNKNOWN);
}
function knownList(...lists) {
  for (const list of lists) if (Array.isArray(list) && !isUnknownList(list)) return list;
  return [UNKNOWN];
}
function knownText(...items) {
  for (const item of items) if (typeof item === 'string' && item && item !== UNKNOWN) return item;
  return UNKNOWN;
}
function writeScopeList(items) {
  return (items || []).map((item) => String(item).trim().replace(/^`([^`]+)`$/, '$1'));
}
const WORK_UNIT_ID_RE = /\b(NV\d{2}|R\d+F\d+|[A-Z]{2,}[A-Z0-9_-]*\d+[A-Z0-9_-]*)\b/i;
function workUnitId(value) {
  const source = String(value || '');
  const explicit = source.match(/\bWork\s+Unit\s+([A-Za-z0-9._:-]{1,120})(?=\s|$)/i)
    || source.match(/工作单元\s*[:：]?\s*([A-Za-z0-9._:-]{1,120})(?=\s|$)/i);
  if (explicit) return explicit[1].toUpperCase();
  const match = source.match(WORK_UNIT_ID_RE);
  return match ? match[1].toUpperCase() : null;
}
function requestedWorkUnitId(value) {
  if (!value) return null;
  return workUnitId(value) || String(value).trim().toUpperCase();
}
function headingSections(text) {
  const source = String(text || ''), headings = [], re = /^(#{2,6})\s+(.+)$/gm;
  let match;
  while ((match = re.exec(source))) headings.push({ level: match[1].length, title: match[2].trim(), start: match.index, bodyStart: re.lastIndex });
  return headings.map((item, index) => {
    const next = headings.slice(index + 1).find((candidate) => candidate.level <= item.level);
    return { ...item, end: next ? next.start : source.length, body: source.slice(item.bodyStart, next ? next.start : source.length) };
  });
}
function projectionFields(text) {
  return {
    goal: textValue(text, FIELD_ALIASES.goal),
    completionStandards: listValue(text, FIELD_ALIASES.completionStandards),
    allowed: listValue(text, FIELD_ALIASES.allowed),
    forbidden: listValue(text, FIELD_ALIASES.forbidden),
    authorityDesign: listValue(text, FIELD_ALIASES.authorityDesign),
    facts: listValue(text, FIELD_ALIASES.facts),
    entryPoints: listValue(text, FIELD_ALIASES.entryPoints),
    disprovenRoutes: listValue(text, FIELD_ALIASES.disprovenRoutes),
    unknowns: listValue(text, FIELD_ALIASES.unknowns),
    routeBasis: textValue(text, FIELD_ALIASES.routeBasis),
    dependencies: listValue(text, FIELD_ALIASES.dependencies, { noneAsEmpty: true }),
    resultContract: textValue(text, FIELD_ALIASES.resultContract),
  };
}
function workUnits(text) {
  return headingSections(text).map((section) => {
    const id = workUnitId(section.title) || workUnitId(field(section.body, 'workUnit') || field(section.body, '工作单元'));
    return id ? { id, title: section.title, ...projectionFields(section.body) } : null;
  }).filter(Boolean);
}
function leafText(text) {
  const firstUnit = headingSections(text).find((section) => workUnitId(section.title)
    || workUnitId(field(section.body, 'workUnit') || field(section.body, '工作单元')));
  return firstUnit ? String(text).slice(0, firstUnit.start) : String(text || '');
}
function planAuthorityText(text) {
  if (text == null) return { status: 'missing', digest: null, text: null, planDigest: null, planText: null };
  const source = String(text), begins = source.split(BASELINE_BEGIN).length - 1, ends = source.split(BASELINE_END).length - 1;
  if (begins === 0 && ends === 0) return { status: 'legacy', digest: null, text: null,
    planDigest: `sha256:${io.sha(source.trim())}`, planText: source };
  if (begins !== 1 || ends !== 1 || source.indexOf(BASELINE_END) < source.indexOf(BASELINE_BEGIN)) {
    return { status: 'invalid', digest: null, text: null, planDigest: null, planText: source };
  }
  const start = source.indexOf(BASELINE_BEGIN), contentStart = start + BASELINE_BEGIN.length, end = source.indexOf(BASELINE_END);
  const baseline = source.slice(contentStart, end).trim(), planText = `${source.slice(0, start)}${source.slice(end + BASELINE_END.length)}`;
  if (!baseline) return { status: 'invalid', digest: null, text: '', planDigest: `sha256:${io.sha(planText.trim())}`, planText };
  const confirmationSource = field(baseline, '确认来源') || field(baseline, 'Confirmation-Source');
  return { status: confirmationSource ? 'current' : 'unconfirmed', confirmationSource: confirmationSource || null,
    digest: `sha256:${io.sha(baseline)}`, text: baseline,
    planDigest: `sha256:${io.sha(planText.trim())}`, planText };
}
function planReview(root, authority = planAuthorityText(io.read(path.join(hdir(root), 'plan.md')))) {
  const file = path.join(hdir(root), 'reports', 'plan-review.md'), item = io.inspect(root, path.relative(root, file));
  if (item.type === 'missing') return { status: 'missing', file: null, claimedVerdict: null };
  if (item.type !== 'file') return { status: 'invalid', file, claimedVerdict: null };
  const text = io.read(file, ''), kind = field(text, '复核类型') || field(text, 'Review-Type');
  const review = { file, baselineDigest: field(text, '需求基线摘要') || field(text, 'Requirement-Digest'),
    planDigest: field(text, '完整计划摘要') || field(text, 'Plan-Digest'), verdict: field(text, '结论') || field(text, 'Verdict') };
  const validDigests = /^sha256:[0-9a-f]{64}$/;
  if (String(kind || '').toLowerCase() !== 'plan') return { status: 'invalid', ...review, claimedVerdict: review.verdict || null };
  if (!validDigests.test(review.baselineDigest || '') || !validDigests.test(review.planDigest || '') || !review.verdict) {
    return { status: 'invalid', ...review, claimedVerdict: review.verdict || null };
  }
  const bound = authority.status === 'current' && review.baselineDigest === authority.digest && review.planDigest === authority.planDigest;
  if (!bound) return { status: 'stale', ...review, claimedVerdict: review.verdict };
  const pass = /^(?:pass|passed|通过)$/i.test(review.verdict);
  return { status: pass ? 'current' : 'failed', ...review, claimedVerdict: review.verdict };
}
function planAuthority(root) {
  const value = planAuthorityText(io.read(path.join(hdir(root), 'plan.md')));
  return { ...value, review: planReview(root, value) };
}
function parse(file) {
  const text = io.read(file);
  if (text == null) return null;
  const baseText = leafText(text);
  const name = path.basename(file, '.md'), stage = field(text, '阶段');
  const type = /^stage-/i.test(name) || /^##\s*叶子/m.test(text) ? 'stage' : stage ? 'leaf' : 'unknown';
  const implementationBasis = type === 'stage' ? {
    authority: values(text, ['相关权威设计', '权威需求']),
    existing: values(text, ['相关现有实现']),
    boundaries: values(text, ['必须保持的架构边界', '架构边界']),
  } : null;
  if (implementationBasis) implementationBasis.complete = Object.values(implementationBasis).slice(0, 3).every((items) => items.length > 0);
  return { file, name, id: name, type, title: title(text, name), stage: stage || null,
    stageId: stage ? stage.split(/\s+/)[0] : null, goal: field(baseText, '目标'),
    sourceReceipt: field(baseText, '来源收据'), product: field(baseText, '产品'), evidence: field(baseText, '证据'),
    carrier: field(baseText, '载体'), allowed: bullets(baseText, '允许动'), forbidden: bullets(baseText, '不许动'),
    ...projectionFields(baseText), workUnits: workUnits(text), implementationBasis };
}
function done(root) {
  return io.list(path.join(hdir(root), 'done'), true).filter((f) => f.endsWith('.md')).map(parse).filter(Boolean);
}
function readChain(root) {
  const hd = hdir(root), planText = io.read(path.join(hd, 'plan.md')), authorityValue = planAuthority(root);
  const { text: _baselineText, planText: _planText, ...authority } = authorityValue;
  const stages = md(path.join(hd, 'stages')).map(parse).filter(Boolean);
  const rawCurrent = md(path.join(hd, 'leaves')).map(parse).filter(Boolean);
  const currentLeaves = rawCurrent.filter((x) => x.type === 'leaf');
  const unfinished = md(path.join(hd, 'unfinished')).map(parse).filter(Boolean);
  const conflicts = [];
  if (rawCurrent.length > 1) conflicts.push(`two-current:${rawCurrent.length}`);
  for (const item of rawCurrent.filter((x) => x.type !== 'leaf')) conflicts.push(`non-leaf-in-leaves:${item.name}.md`);
  for (const item of unfinished.filter((x) => x.type === 'stage')) conflicts.push(`legacy-stage-in-unfinished:${item.name}.md`);
  const leaf = rawCurrent.length === 1 && currentLeaves.length === 1 ? currentLeaves[0] : null;
  const matches = leaf ? stages.filter((s) => s.name === leaf.stageId) : [];
  if (leaf && matches.length === 0) conflicts.push(`orphan:${leaf.name}->${leaf.stageId || '-'}`);
  if (leaf && matches.length > 1) conflicts.push(`cross-stage:${leaf.stageId}`);
  const stage = matches.length === 1 ? matches[0] : null;
  const health = { ok: conflicts.length === 0, conflicts, currentCount: rawCurrent.length,
    unfinishedLeaves: unfinished.filter((x) => x.type === 'leaf').length };
  return { root, installed: fs.existsSync(hd),
    plan: planText == null ? null : { title: title(planText, '总计划'), goal: field(planText, '目标'), authority }, authority,
    stage, leaf: health.ok ? leaf : null, stages, unfinished, health,
    allowed: health.ok && leaf ? leaf.allowed : [], forbidden: stage ? stage.forbidden : [] };
}
function progress(root, chain = readChain(root)) {
  const hd = hdir(root), stageId = chain.stage?.name || null;
  const select = (items) => stageId ? items.filter((x) => x.type === 'leaf' && x.stageId === stageId) : [];
  const current = select(md(path.join(hd, 'leaves')).map(parse).filter(Boolean));
  const unfinished = select(md(path.join(hd, 'unfinished')).map(parse).filter(Boolean));
  const completed = select(done(root));
  return { stage: chain.stage, total: current.length + unfinished.length + completed.length,
    done: completed.length, current: current.length === 1 ? completed.length + 1 : null,
    currentLeafId: current.length === 1 ? current[0].name.split('-')[0] : null,
    remaining: current.concat(unfinished).map((x) => x.title),
    allDone: stageId ? current.length === 0 && unfinished.length === 0 : null,
    conflicts: chain.health.conflicts };
}
function format(chain) {
  if (!chain.installed) return 'Harness：未安装';
  const p = progress(chain.root, chain), current = chain.leaf ? chain.leaf.title : '无';
  return [
    `Harness：${chain.stage ? chain.stage.title : '无 current stage'}；${p.total} 个 leaf，完成 ${p.done}，当前 ${current}`,
    `产品：${chain.leaf?.product || '未知（不得从 leaf 完成推断）'}`,
    `证据：${chain.leaf?.evidence || '未知'}`,
    `载体：${chain.leaf?.carrier || 'working-copy-only/未知'}`,
    `状态：${chain.health.ok ? 'healthy' : chain.health.conflicts.join('；')}`,
  ].join('\n');
}
const month = (date = new Date()) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`;
function exit(root, kind, name, opts = {}) {
  const dir = kind === 'stage' ? 'stages' : 'leaves', sourceDir = path.join(hdir(root), dir);
  const key = String(name || '').replace(/\.md$/, '').toLowerCase();
  const source = md(sourceDir).find((f) => path.basename(f, '.md').toLowerCase() === key)
    || md(sourceDir).find((f) => path.basename(f, '.md').toLowerCase().startsWith(`${key}-`));
  if (!source) return { ok: false, message: `${dir}/ 里没有 ${name}` };
  const dest = path.join(hdir(root), 'done', month(opts.at), path.basename(source));
  try { if (opts.write) io.moveNoClobber(source, dest, opts.fault); }
  catch (error) { return { ok: false, source, dest, message: error.message }; }
  return { ok: true, wrote: !!opts.write, source, dest };
}
function pause(root, reason, resume, opts = {}) {
  const c = readChain(root);
  if (!c.leaf) return { ok: false, message: '没有唯一 current leaf' };
  const dest = path.join(hdir(root), 'unfinished', path.basename(c.leaf.file));
  const before = opts.write ? fs.readFileSync(c.leaf.file) : null;
  const mode = opts.write ? fs.statSync(c.leaf.file).mode & 0o777 : null;
  try {
    if (opts.write) {
      if (fs.existsSync(dest)) throw new Error(`目标已存在：${dest}`);
      fs.appendFileSync(c.leaf.file, `\n等待：${reason}\n恢复：${resume}\n`);
      io.moveNoClobber(c.leaf.file, dest, opts.fault);
    }
    return { ok: true, wrote: !!opts.write, source: c.leaf.file, dest };
  } catch (error) {
    if (opts.write && fs.existsSync(c.leaf.file)) {
      try { const a = fs.statSync(c.leaf.file), b = fs.existsSync(dest) ? fs.statSync(dest) : null; if (b && a.dev === b.dev && a.ino === b.ino) fs.unlinkSync(dest); } catch { /* preserve foreign dest */ }
      io.atomic(c.leaf.file, before, mode);
    }
    return { ok: false, message: error.message, source: c.leaf.file, dest };
  }
}
function resume(root, name, opts = {}) {
  if (md(path.join(hdir(root), 'leaves')).length) return { ok: false, message: '已有 current leaf' };
  const source = md(path.join(hdir(root), 'unfinished')).find((f) => path.basename(f).startsWith(name));
  if (!source || parse(source).type !== 'leaf') return { ok: false, message: `unfinished/ 里没有 leaf ${name}` };
  const dest = path.join(hdir(root), 'leaves', path.basename(source));
  try { if (opts.write) io.moveNoClobber(source, dest, opts.fault); return { ok: true, wrote: !!opts.write, source, dest }; }
  catch (error) { return { ok: false, message: error.message, source, dest }; }
}
function selectedWorkUnit(chain, id) {
  const requested = requestedWorkUnitId(id), units = chain.leaf?.workUnits || [];
  const unit = requested ? units.find((item) => item.id === requested) : units.length === 1 ? units[0] : null;
  return { requested, unit, selection: requested ? unit ? 'requested' : 'undeclared-work-unit'
    : unit ? 'single-leaf-work-unit' : 'leaf-fallback' };
}
function declaredWorkUnit(chain, id) {
  const selected = selectedWorkUnit(chain, id);
  return selected.requested && selected.unit ? selected.unit : null;
}
function workUnitPackage(root, id, chain = readChain(root)) {
  const leaf = chain.leaf || null, selected = selectedWorkUnit(chain, id), unit = selected.unit;
  if (selected.requested && !unit) {
    const unknown = [UNKNOWN];
    return {
      schemaVersion: 1,
      kind: 'harness-lite-work-unit-package',
      status: UNKNOWN,
      stage: chain.stage?.name || UNKNOWN,
      leaf: leaf ? path.relative(root, leaf.file).replaceAll('\\', '/') : UNKNOWN,
      workUnit: selected.requested,
      selection: selected.selection,
      goal: UNKNOWN,
      completionStandards: unknown,
      dispatchReady: false,
      readiness: 'undeclared-work-unit',
      allowed: unknown,
      forbidden: unknown,
      writeScope: unknown,
      boundaries: { allowed: unknown, forbidden: unknown },
      authorityDesign: unknown,
      facts: unknown,
      entryPoints: unknown,
      disprovenRoutes: unknown,
      unknowns: ['work-unit-not-declared-in-current-leaf'],
      routeBasis: UNKNOWN,
      dependencies: unknown,
      resultContract: UNKNOWN,
      source: { leaf: leaf?.file || null, stage: chain.stage?.file || null },
    };
  }
  const stageForbidden = chain.stage?.forbidden || [];
  const forbidden = knownList(unit?.forbidden, leaf?.forbidden, stageForbidden.length ? stageForbidden : [UNKNOWN]);
  const allowed = knownList(unit?.allowed, leaf?.allowed, chain.allowed);
  const completionStandards = knownList(unit?.completionStandards, leaf?.completionStandards);
  const dispatchReady = !isUnknownList(completionStandards);
  return {
    schemaVersion: 1,
    kind: 'harness-lite-work-unit-package',
    status: leaf && unit ? 'work-unit' : leaf ? 'leaf-fallback' : UNKNOWN,
    stage: chain.stage?.name || UNKNOWN,
    leaf: leaf ? path.relative(root, leaf.file).replaceAll('\\', '/') : UNKNOWN,
    workUnit: selected.requested || unit?.id || UNKNOWN,
    selection: selected.selection,
    goal: knownText(unit?.goal, leaf?.goal),
    completionStandards,
    dispatchReady,
    readiness: dispatchReady ? 'ready' : 'completion-standards-unknown',
    allowed,
    forbidden,
    writeScope: writeScopeList(allowed),
    boundaries: { allowed, forbidden },
    authorityDesign: knownList(unit?.authorityDesign, leaf?.authorityDesign),
    facts: knownList(unit?.facts, leaf?.facts),
    entryPoints: knownList(unit?.entryPoints, leaf?.entryPoints),
    disprovenRoutes: knownList(unit?.disprovenRoutes, leaf?.disprovenRoutes),
    unknowns: knownList(unit?.unknowns, leaf?.unknowns),
    routeBasis: knownText(unit?.routeBasis, leaf?.routeBasis),
    dependencies: knownList(unit?.dependencies, leaf?.dependencies),
    resultContract: knownText(unit?.resultContract, leaf?.resultContract),
    source: { leaf: leaf?.file || null, stage: chain.stage?.file || null },
  };
}
function workUnitPackages(root, ids = null, chain = readChain(root)) {
  const leaf = chain.leaf || null;
  const requested = ids == null ? (leaf?.workUnits || []).map((unit) => unit.id)
    : [].concat(ids).map(requestedWorkUnitId).filter(Boolean);
  const unique = [...new Set(requested)];
  const units = unique.map((id) => workUnitPackage(root, id, chain));
  const missing = units.filter((unit) => unit.status !== 'work-unit').map((unit) => unit.workUnit || UNKNOWN);
  const complete = !leaf ? UNKNOWN : missing.length ? 'incomplete' : 'complete';
  return {
    schemaVersion: 1,
    kind: 'harness-lite-work-unit-package-list',
    status: complete,
    complete,
    stage: chain.stage?.name || UNKNOWN,
    leaf: leaf ? path.relative(root, leaf.file).replaceAll('\\', '/') : UNKNOWN,
    requested: unique,
    count: units.length,
    missing,
    units,
    source: { leaf: leaf?.file || null, stage: chain.stage?.file || null },
  };
}

module.exports = { BASELINE_BEGIN, BASELINE_END, hdir, md, field, bullets, planAuthorityText, planReview, planAuthority,
  UNKNOWN, FIELD_ALIASES, projectionFields, workUnitId, workUnits, leafText, selectedWorkUnit, declaredWorkUnit, workUnitPackage, workUnitPackages,
  parse, done, readChain, progress, format, exit, pause, resume };
