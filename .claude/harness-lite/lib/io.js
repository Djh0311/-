'use strict';
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

const sha = (value) => crypto.createHash('sha256').update(value).digest('hex');
function read(file, fallback = null) {
  try { return fs.readFileSync(file, 'utf8'); } catch { return fallback; }
}
function json(file, fallback = null) {
  try { return JSON.parse(fs.readFileSync(file, 'utf8')); } catch { return fallback; }
}
function safe(root, rel) {
  if (typeof rel !== 'string' || !rel || path.isAbsolute(rel) || rel.split(/[\\/]/).includes('..')) {
    throw new Error(`必须是项目内相对路径：${rel}`);
  }
  const base = path.resolve(root), abs = path.resolve(base, rel);
  if (abs !== base && !abs.startsWith(base + path.sep)) throw new Error(`路径越出项目：${rel}`);
  return abs;
}
function atomic(file, text, mode) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const tmp = path.join(path.dirname(file), `.${path.basename(file)}.${process.pid}.${Date.now()}.tmp`);
  try {
    fs.writeFileSync(tmp, text, { flag: 'wx', mode: mode || 0o600 });
    fs.renameSync(tmp, file);
  } finally { try { fs.unlinkSync(tmp); } catch { /* renamed or absent */ } }
}
function list(dir, recursive = true) {
  let entries;
  try { entries = fs.readdirSync(dir, { withFileTypes: true }); } catch { return []; }
  let out = [];
  for (const entry of entries.sort((a, b) => a.name.localeCompare(b.name))) {
    const abs = path.join(dir, entry.name);
    if (entry.isDirectory() && recursive) out = out.concat(list(abs, true));
    else if (!entry.isDirectory()) out.push(abs);
  }
  return out;
}
function mode(stat) { return (stat.mode & 0o777).toString(8).padStart(4, '0'); }
function inspect(root, rel) {
  const abs = safe(root, rel);
  let stat;
  try { stat = fs.lstatSync(abs); } catch (e) { if (e.code === 'ENOENT') return { path: rel, type: 'missing' }; throw e; }
  const type = stat.isSymbolicLink() ? 'symlink' : stat.isFile() ? 'file' : stat.isDirectory() ? 'directory' : 'other';
  return { path: rel.replaceAll('\\', '/'), abs, type, mode: mode(stat),
    digest: type === 'file' ? sha(fs.readFileSync(abs)) : null };
}
function digest(root, paths, modeFor) {
  const hash = crypto.createHash('sha256');
  for (const rel of [...paths].sort()) {
    const item = inspect(root, rel);
    if (item.type !== 'file') throw new Error(`${rel} 不是普通文件`);
    const body = fs.readFileSync(item.abs);
    const fileMode = modeFor ? Number(modeFor(rel)).toString(8).padStart(4, '0') : item.mode;
    for (const value of [rel, item.type, fileMode, String(body.length)]) hash.update(`${Buffer.byteLength(value)}:${value}`);
    hash.update(body);
  }
  return `sha256:${hash.digest('hex')}`;
}
function moveNoClobber(src, dest, fault = () => {}) {
  if (!fs.lstatSync(src).isFile()) throw new Error('只移动普通文件');
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  if (fs.existsSync(dest)) throw new Error(`目标已存在：${dest}`);
  if (fs.statSync(src).dev !== fs.statSync(path.dirname(dest)).dev) throw new Error('移动必须位于同一文件系统');
  fault('move:before'); const moved = spawnSync('/bin/mv', ['-n', '--', src, dest], { encoding: 'utf8' });
  if (moved.status !== 0 || fs.existsSync(src)) throw new Error(String(moved.stderr || 'no-clobber move 未完成').trim());
}

module.exports = { sha, read, json, safe, atomic, list, mode, inspect, digest, moveNoClobber };
