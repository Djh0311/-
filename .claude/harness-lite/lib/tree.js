'use strict';
const fs = require('fs');
const path = require('path');
const io = require('./io.js');

const hdir = (root) => path.join(root, 'docs', 'harness');
const md = (dir) => io.list(dir, false).filter((f) => f.endsWith('.md'));
const field = (text, name) => (String(text).match(new RegExp(`^\\s*${name}[:：]\\s*(.+)$`, 'm')) || [])[1]?.trim() || null;
const title = (text, fallback) => (String(text).match(/^#\s+(.+)$/m) || [])[1]?.trim() || fallback;
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
function parse(file) {
  const text = io.read(file);
  if (text == null) return null;
  const name = path.basename(file, '.md'), stage = field(text, '阶段');
  const type = /^stage-/i.test(name) || /^##\s*叶子/m.test(text) ? 'stage' : stage ? 'leaf' : 'unknown';
  return { file, name, id: name, type, title: title(text, name), stage: stage || null,
    stageId: stage ? stage.split(/\s+/)[0] : null, goal: field(text, '目标'),
    sourceReceipt: field(text, '来源收据'), product: field(text, '产品'), evidence: field(text, '证据'),
    carrier: field(text, '载体'), allowed: bullets(text, '允许动'), forbidden: bullets(text, '不许动') };
}
function done(root) {
  return io.list(path.join(hdir(root), 'done'), true).filter((f) => f.endsWith('.md')).map(parse).filter(Boolean);
}
function readChain(root) {
  const hd = hdir(root), planText = io.read(path.join(hd, 'plan.md'));
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
    plan: planText == null ? null : { title: title(planText, '总计划'), goal: field(planText, '目标') },
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

module.exports = { hdir, md, field, bullets, parse, done, readChain, progress, format, exit, pause, resume };
