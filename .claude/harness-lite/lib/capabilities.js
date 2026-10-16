'use strict';

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const io = require('./io.js');

const UNKNOWN = 'UNKNOWN';
const KIND = 'harness-lite-capability-manifest';
const PROJECTION_KIND = 'harness-lite-capability-projection';
const CARRIER_KIND = 'harness-lite-capability-projection-carrier';
const KNOWN_FAMILIES = new Set(['grok', 'gemini', 'astra', 'terra', 'sol']);
const KNOWN_STATUS = new Set(['available', 'unavailable', 'unknown', UNKNOWN]);
const MANIFEST_RELATIVE_PATHS = Object.freeze([
  '.codex/harness-lite/capabilities.json',
  'docs/harness/capabilities.json',
]);
const MAX_MANIFEST_BYTES = 64 * 1024;
const MAX_HOOK_INPUT_BYTES = MAX_MANIFEST_BYTES;
const MAX_DYNAMIC_CARRIER_BYTES = MAX_MANIFEST_BYTES;
const DYNAMIC_CARRIER_RELATIVE_DIR = '.codex/harness-lite/caps';
const DYNAMIC_CARRIER_TTL_MS = 30 * 60 * 1000;
const MAX_FRESHNESS_FUTURE_SKEW_MS = 0;
const MODEL_FIELDS = Object.freeze([
  'channel',
  'model',
  'reasoning',
  'family',
  'status',
  'availability.status',
  'capabilities',
  'suitability',
]);

function text(value) {
  return typeof value === 'string' && value.trim() ? value.trim() : null;
}
function plainObject(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
  try { const proto = Object.getPrototypeOf(value); return proto === Object.prototype || proto === null; } catch { return false; }
}
function strings(value) {
  if (typeof value === 'string') return [value.trim()].filter(Boolean);
  if (!Array.isArray(value) || value.some((item) => typeof item !== 'string' || !item.trim())) return null;
  return value.map((item) => item.trim());
}
function normalizeFamily(value) {
  const family = text(value)?.toLowerCase();
  if (family === 'gpt-6-astra' || family === 'gpt6-astra') return 'astra';
  return family && KNOWN_FAMILIES.has(family) ? family : 'unclassified';
}
function normalizeStatus(value) {
  const status = text(value);
  if (!status) return UNKNOWN;
  const lower = status.toLowerCase();
  if (!KNOWN_STATUS.has(status) && !KNOWN_STATUS.has(lower)) return UNKNOWN;
  return lower === 'unknown' ? UNKNOWN : lower;
}
function stableSuitability(family, reasoning) {
  if (family === 'grok') return ['engineering'];
  if (family === 'gemini') return ['frontend'];
  if (family === 'astra' && reasoning === 'xhigh') return ['problem-recovery'];
  if ((family === 'terra' || family === 'sol') && reasoning === 'xhigh') return ['problem-recovery'];
  return [];
}
function unknown(reason) {
  return {
    schemaVersion: 1,
    kind: PROJECTION_KIND,
    state: UNKNOWN,
    reason,
    models: [{
      channel: UNKNOWN,
      model: UNKNOWN,
      reasoning: UNKNOWN,
      family: 'unclassified',
      status: UNKNOWN,
      availability: { status: UNKNOWN },
      capabilities: [],
      suitability: [],
    }],
  };
}
function sha(value) {
  return crypto.createHash('sha256').update(String(value)).digest('hex');
}
function projectionPayload(projection) {
  return {
    schemaVersion: projection.schemaVersion,
    kind: projection.kind,
    state: projection.state,
    reason: projection.reason,
    models: projection.models || [],
  };
}
function manifestBody(manifest) {
  try {
    const body = JSON.stringify(manifest);
    const bytes = Buffer.byteLength(body);
    return { ok: true, body, bytes, sourceDigest: `sha256:${sha(body)}` };
  } catch {
    return { ok: false, reason: 'hook-input-manifest-unserializable' };
  }
}
function isoNow(value) {
  let date;
  try { date = value ? new Date(value) : new Date(); } catch { return new Date(NaN); }
  return Number.isFinite(date.getTime()) ? date : new Date();
}
function parseDate(value) {
  try { const date = new Date(value); return Number.isFinite(date.getTime()) ? date : null; } catch { return null; }
}
function canonicalRoot(root) {
  if (typeof root !== 'string' || !root.trim()) return null;
  let resolved;
  try { resolved = path.resolve(root); } catch { return null; }
  try { return fs.realpathSync(resolved); } catch { return resolved; }
}
function bindingValue(manifest, key) {
  const binding = plainObject(manifest?.binding) ? manifest.binding : {};
  const aliases = {
    project: ['project', 'projectRoot', 'cwd'],
    session: ['session', 'sessionId'],
    turn: ['turn', 'turnId'],
    event: ['event', 'eventName'],
    source: ['source', 'sourceType'],
  };
  for (const name of aliases[key] || [key]) {
    if (Object.hasOwn(binding, name)) return binding[name];
    if (Object.hasOwn(manifest || {}, name)) return manifest[name];
  }
  return null;
}
function validateFreshness(freshness, now) {
  if (!freshness || typeof freshness !== 'object' || Array.isArray(freshness)) return { ok: false, reason: 'missing-freshness' };
  if (freshness.status !== 'fresh') return { ok: false, reason: 'stale-freshness' };
  const createdDate = parseDate(freshness.createdAt), expiresDate = parseDate(freshness.expiresAt);
  const createdAt = createdDate ? createdDate.getTime() : NaN, expiresAt = expiresDate ? expiresDate.getTime() : NaN;
  const ttlMs = freshness.ttlMs;
  if (!Number.isFinite(createdAt) || !Number.isFinite(expiresAt) || !Number.isSafeInteger(ttlMs)
    || ttlMs <= 0 || ttlMs > DYNAMIC_CARRIER_TTL_MS || expiresAt - createdAt !== ttlMs) {
    return { ok: false, reason: 'invalid-freshness' };
  }
  const atDate = now === undefined || now === null ? new Date() : parseDate(now);
  if (!atDate) return { ok: false, reason: 'invalid-freshness-now' };
  const at = atDate.getTime();
  if (createdAt > at + MAX_FRESHNESS_FUTURE_SKEW_MS) return { ok: false, reason: 'future-freshness' };
  if (at >= expiresAt) return { ok: false, reason: 'expired-freshness' };
  return { ok: true, createdAt: new Date(createdAt).toISOString(), expiresAt: new Date(expiresAt).toISOString(), ttlMs };
}
function validateBoundManifest(root, manifest, opts, details) {
  const eventName = text(opts.eventName), sessionId = text(opts.sessionId);
  const turnId = opts.turnId == null ? null : text(opts.turnId);
  if (!eventName || !sessionId) return { ok: false, reason: 'missing-binding' };
  if (eventName !== 'SessionStart' && !turnId) return { ok: false, reason: 'missing-binding' };
  const optionSource = opts.source || opts.sourceType;
  if (optionSource && optionSource !== 'hook-input') return { ok: false, reason: 'source-binding-mismatch' };
  if (opts.project != null && (typeof opts.project !== 'string' || canonicalRoot(opts.project) !== canonicalRoot(root))) return { ok: false, reason: 'project-binding-mismatch' };
  const source = bindingValue(manifest, 'source');
  if (source && source !== 'hook-input') return { ok: false, reason: 'source-binding-mismatch' };
  if (Object.hasOwn(manifest || {}, 'binding') && !plainObject(manifest.binding)) return { ok: false, reason: 'binding-shape-mismatch' };
  const provenance = manifest?.provenance;
  if (Object.hasOwn(manifest || {}, 'provenance') && !plainObject(provenance)) return { ok: false, reason: 'provenance-shape-mismatch' };
  if (provenance) {
    const provenanceSource = provenance.source || provenance.sourceType || provenance.binding?.source;
    if (provenanceSource && provenanceSource !== 'hook-input') return { ok: false, reason: 'source-binding-mismatch' };
    const direct = [['project', root], ['projectRoot', root], ['cwd', root], ['sessionId', sessionId], ['session', sessionId],
      ['turnId', turnId], ['turn', turnId], ['eventName', eventName], ['event', eventName]];
    for (const [key, expected] of direct) {
      if (!Object.hasOwn(provenance, key)) continue;
      const actual = provenance[key];
      if (key === 'project' || key === 'projectRoot' || key === 'cwd') {
        if (typeof actual !== 'string' || canonicalRoot(actual) !== canonicalRoot(root)) return { ok: false, reason: 'project-binding-mismatch' };
      } else if (key === 'turnId' || key === 'turn') {
        if (actual !== null && typeof actual !== 'string') return { ok: false, reason: 'turn-binding-mismatch' };
        if (String(actual || '') !== String(expected || '')) return { ok: false, reason: 'turn-binding-mismatch' };
      } else if (typeof actual !== 'string' || actual !== expected) {
        return { ok: false, reason: key === 'sessionId' || key === 'session' ? 'session-binding-mismatch' : 'event-binding-mismatch' };
      }
    }
    if (Object.hasOwn(provenance, 'binding')) {
      const nested = provenance.binding;
      if (!plainObject(nested)) return { ok: false, reason: 'binding-shape-mismatch' };
      const fields = [['project', root, true], ['sessionId', sessionId, false], ['turnId', turnId, false], ['eventName', eventName, false], ['source', 'hook-input', false]];
      for (const [key, expected, isProject] of fields) {
        if (!Object.hasOwn(nested, key)) return { ok: false, reason: 'binding-shape-mismatch' };
        const actual = nested[key];
        if (isProject) {
          if (typeof actual !== 'string' || canonicalRoot(actual) !== canonicalRoot(root)) return { ok: false, reason: 'project-binding-mismatch' };
        } else if (key === 'turnId') {
          if (actual !== null && typeof actual !== 'string') return { ok: false, reason: 'turn-binding-mismatch' };
          if (String(actual || '') !== String(expected || '')) return { ok: false, reason: 'turn-binding-mismatch' };
        } else if (typeof actual !== 'string' || actual !== expected) return { ok: false, reason: `${key === 'source' ? 'source' : key === 'sessionId' ? 'session' : 'event'}-binding-mismatch` };
      }
    }
  }
  const project = bindingValue(manifest, 'project');
  const bindingObject = manifest && typeof manifest.binding === 'object' && !Array.isArray(manifest.binding) ? manifest.binding : null;
  const projectDeclared = Object.hasOwn(manifest || {}, 'project') || Object.hasOwn(manifest || {}, 'projectRoot') || Object.hasOwn(manifest || {}, 'cwd')
    || !!(bindingObject && (Object.hasOwn(bindingObject, 'project') || Object.hasOwn(bindingObject, 'projectRoot') || Object.hasOwn(bindingObject, 'cwd')));
  if (projectDeclared && (typeof project !== 'string' || !project.trim() || canonicalRoot(project) !== canonicalRoot(root))) return { ok: false, reason: 'project-binding-mismatch' };
  const boundSession = bindingValue(manifest, 'session');
  const boundTurn = bindingValue(manifest, 'turn');
  const boundEvent = bindingValue(manifest, 'event');
  if (boundSession != null && String(boundSession) !== sessionId) return { ok: false, reason: 'session-binding-mismatch' };
  if (boundTurn != null && String(boundTurn) !== String(turnId || '')) return { ok: false, reason: 'turn-binding-mismatch' };
  if (boundEvent != null && String(boundEvent) !== eventName) return { ok: false, reason: 'event-binding-mismatch' };
  const freshness = manifest?.freshness || manifest?.provenance?.freshness;
  if (freshness) {
    const checked = validateFreshness(freshness, opts.now);
    if (!checked.ok) return checked;
  }
  if (Object.hasOwn(opts, 'now') && opts.now != null && !parseDate(opts.now)) return { ok: false, reason: 'invalid-freshness-now' };
  // Hook input is bound by the live invocation (event/session/turn) and receives
  // a newly generated carrier. Optional manifest metadata is checked when present.
  return { ok: true };
}
function validateProjectManifest(root, manifest, opts, details) {
  // A project file has no live caller provenance. It is historical/cache input
  // only; accepting self-described metadata here would recreate CEX-05.
  return { ok: false, reason: 'project-file-no-live-source' };
}
function dynamicCarrierRelativePath(projectionDigest, opts = {}) {
  const digest = sha(JSON.stringify([
    projectionDigest,
    opts.sourceDigest || null,
    opts.eventName || null,
    opts.sessionId || null,
    opts.turnId || null,
  ]));
  return `${DYNAMIC_CARRIER_RELATIVE_DIR}/c-${digest.slice(0, 32)}.json`;
}
function carrierFilePayload(projection, details, opts = {}) {
  const created = isoNow(opts.now);
  const expires = new Date(created.getTime() + DYNAMIC_CARRIER_TTL_MS);
  return {
    schemaVersion: 1,
    kind: CARRIER_KIND,
    source: 'hook-input',
    sourceType: 'hook-input',
    eventName: opts.eventName || null,
    sessionId: opts.sessionId || null,
    turnId: opts.turnId || null,
    binding: {
      project: opts.project || null,
      sessionId: opts.sessionId || null,
      turnId: opts.turnId || null,
      eventName: opts.eventName || null,
      source: 'hook-input',
    },
    modelCount: (projection.models || []).length,
    modelFields: MODEL_FIELDS,
    sourceDigest: details.sourceDigest,
    sourceBytes: details.bytes,
    sourceManifest: details.manifest || null,
    projectionDigest: `sha256:${sha(JSON.stringify(projectionPayload(projection)))}`,
    freshness: {
      status: 'fresh',
      createdAt: created.toISOString(),
      expiresAt: expires.toISOString(),
      ttlMs: DYNAMIC_CARRIER_TTL_MS,
    },
    projection: projectionPayload(projection),
  };
}
function cleanupDynamicCarriers(root, now = new Date()) {
  const dir = path.join(path.resolve(root), DYNAMIC_CARRIER_RELATIVE_DIR);
  let entries;
  try {
    const stat = fs.lstatSync(dir);
    if (!stat.isDirectory() || stat.isSymbolicLink()) return;
    entries = fs.readdirSync(dir, { withFileTypes: true });
  } catch { return; }
  for (const entry of entries) {
    if (!/^c-[0-9a-f]{32}\.json$/.test(entry.name)) continue;
    const file = path.join(dir, entry.name);
    try {
      const stat = fs.lstatSync(file);
      if (!stat.isFile() || stat.isSymbolicLink()) continue;
      const value = io.json(file, {});
      const expiresAt = Date.parse(value?.freshness?.expiresAt || '');
      if (!Number.isFinite(expiresAt) || expiresAt <= now.getTime()) fs.unlinkSync(file);
    } catch {
      /* cleanup is opportunistic; Hook output must not depend on deleting old carriers */
    }
  }
}
function ensureDynamicCarrierDir(root) {
  const base = path.resolve(root);
  let rel = '';
  for (const part of DYNAMIC_CARRIER_RELATIVE_DIR.split('/')) {
    rel = rel ? path.join(rel, part) : part;
    const abs = path.join(base, rel);
    let stat;
    try { stat = fs.lstatSync(abs); } catch (error) {
      if (error.code !== 'ENOENT') throw error;
      fs.mkdirSync(abs, { mode: 0o700 });
      stat = fs.lstatSync(abs);
    }
    if (!stat.isDirectory() || stat.isSymbolicLink()) throw new Error('unsafe-carrier-dir');
  }
  return path.join(base, DYNAMIC_CARRIER_RELATIVE_DIR);
}
function writeDynamicCarrier(root, projection, details, opts = {}) {
  const payload = carrierFilePayload(projection, details, opts);
  const rel = dynamicCarrierRelativePath(payload.projectionDigest, {
    sourceDigest: details.sourceDigest,
    eventName: opts.eventName || null,
    sessionId: opts.sessionId || null,
    turnId: opts.turnId || null,
  });
  const body = `${JSON.stringify(payload, null, 2)}\n`;
  const bytes = Buffer.byteLength(body);
  if (bytes > MAX_DYNAMIC_CARRIER_BYTES) {
    return { ok: false, reason: 'hook-input-carrier-too-large', rel, projectionDigest: payload.projectionDigest,
      sourceDigest: details.sourceDigest, manifestBytes: details.bytes, carrierBytes: bytes };
  }
  try {
    const now = new Date(payload.freshness.createdAt);
    ensureDynamicCarrierDir(root);
    cleanupDynamicCarriers(root, now);
    io.atomic(io.safe(root, rel), body, 0o600);
    return { ok: true, rel, manifestBytes: details.bytes, sourceDigest: details.sourceDigest,
      projectionDigest: payload.projectionDigest, carrierBytes: bytes, createdAt: payload.freshness.createdAt,
      expiresAt: payload.freshness.expiresAt, ttlMs: payload.freshness.ttlMs,
      binding: payload.binding };
  } catch (error) {
    const reason = error.message === 'unsafe-carrier-dir' ? 'unsafe-carrier-dir' : 'hook-input-carrier-write-failed';
    return { ok: false, reason, rel, projectionDigest: payload.projectionDigest,
      sourceDigest: details.sourceDigest, manifestBytes: details.bytes, carrierBytes: bytes };
  }
}
function hookInputProjection(root, manifest, opts = {}) {
  if (!canonicalRoot(root) || !opts || typeof opts !== 'object' || Array.isArray(opts)) {
    return withGuidance(unknown('invalid-input'), { source: 'hook-input', sourceType: 'hook-input', complete: false, incompleteReason: 'invalid-input', read: null });
  }
  const details = manifestBody(manifest);
  if (details.ok) details.manifest = manifest;
  if (!details.ok) return withGuidance(unknown(details.reason), { source: 'hook-input', sourceType: 'hook-input',
    complete: false, incompleteReason: details.reason, read: null });
  if (details.bytes > MAX_HOOK_INPUT_BYTES) return withGuidance(unknown('hook-input-manifest-too-large'), {
    source: 'hook-input',
    sourceType: 'hook-input',
    complete: false,
    incompleteReason: 'hook-input-manifest-too-large',
    read: null,
    manifestBytes: details.bytes,
    sourceDigest: details.sourceDigest,
    manifestDigest: details.sourceDigest,
  });
  const bound = validateBoundManifest(root, manifest, opts, details);
  if (!bound.ok) return withGuidance(unknown(bound.reason), {
    source: 'hook-input', sourceType: 'hook-input', complete: false,
    incompleteReason: bound.reason, read: null, manifestBytes: details.bytes,
    sourceDigest: details.sourceDigest, manifestDigest: details.sourceDigest,
  });
  const projection = normalizeManifest(manifest);
  if (projection.state !== 'known') return withGuidance(projection, {
    source: 'hook-input',
    sourceType: 'hook-input',
    read: null,
    manifestBytes: details.bytes,
    sourceDigest: details.sourceDigest,
    manifestDigest: details.sourceDigest,
  });
  if (!opts.writeDynamicCarrier) return withGuidance(projection, {
    source: 'hook-input',
    sourceType: 'hook-input',
    manifestBytes: details.bytes,
    sourceDigest: details.sourceDigest,
    manifestDigest: details.sourceDigest,
    binding: {
      project: canonicalRoot(root),
      sessionId: opts.sessionId,
      turnId: opts.turnId == null ? null : opts.turnId,
      eventName: opts.eventName,
      source: 'hook-input',
    },
  });
  const carrier = writeDynamicCarrier(root, projection, details, { ...opts, project: canonicalRoot(root) });
  if (!carrier.ok) return withGuidance(unknown(carrier.reason), {
    source: 'hook-input',
    sourceType: 'hook-input',
    complete: false,
    incompleteReason: carrier.reason,
    read: null,
    manifestBytes: carrier.manifestBytes,
    sourceDigest: carrier.sourceDigest,
    manifestDigest: details.sourceDigest,
    projectionDigest: carrier.projectionDigest,
    carrierBytes: carrier.carrierBytes,
    path: carrier.rel,
  });
  return withGuidance(projection, {
    source: 'hook-input',
    sourceType: 'hook-input',
    path: carrier.rel,
    read: { type: 'project-relative-json', path: carrier.rel, maxBytes: MAX_DYNAMIC_CARRIER_BYTES },
    manifestBytes: carrier.manifestBytes,
    sourceDigest: carrier.sourceDigest,
    manifestDigest: details.sourceDigest,
    projectionDigest: carrier.projectionDigest,
    carrierBytes: carrier.carrierBytes,
    createdAt: carrier.createdAt,
    expiresAt: carrier.expiresAt,
    ttlMs: carrier.ttlMs,
    binding: carrier.binding,
  });
}
function normalizeEntry(entry) {
  if (!entry || typeof entry !== 'object' || Array.isArray(entry)) return null;
  const channel = text(entry.channel), model = text(entry.model), reasoningValues = strings(entry.reasoning);
  if (!channel || !model || !reasoningValues || reasoningValues.length === 0) return null;
  const family = normalizeFamily(entry.family), status = normalizeStatus(entry.status), capabilities = strings(entry.capabilities) || [];
  return reasoningValues.map((reasoning) => ({
    channel,
    model,
    reasoning,
    family,
    status,
    availability: { status },
    capabilities,
    suitability: stableSuitability(family, reasoning),
  }));
}
function normalizeManifest(manifest) {
  if (manifest == null) return unknown('missing');
  if (!manifest || typeof manifest !== 'object' || Array.isArray(manifest)) return unknown('invalid-shape');
  if (manifest.schemaVersion !== 1 || manifest.kind !== KIND || !Array.isArray(manifest.models)) return unknown('invalid-shape');
  const rows = [];
  for (const entry of manifest.models) {
    const normalized = normalizeEntry(entry);
    if (!normalized) return unknown('invalid-shape');
    rows.push(...normalized);
  }
  if (!rows.length) return unknown('empty');
  rows.sort((a, b) => `${a.channel}\0${a.model}\0${a.reasoning}`.localeCompare(`${b.channel}\0${b.model}\0${b.reasoning}`));
  return { schemaVersion: 1, kind: PROJECTION_KIND, state: 'known', reason: null, models: rows };
}

function withGuidance(projection, carrier = {}) {
  const source = carrier.source || null;
  const sourceType = carrier.sourceType || (source ? 'project-file' : 'none');
  const complete = projection.state === 'known' && carrier.complete !== false;
  const modelCount = complete ? (projection.models || []).length : 0;
  const projectionDigest = carrier.projectionDigest || `sha256:${sha(JSON.stringify(projectionPayload(projection)))}`;
  const read = Object.hasOwn(carrier, 'read') ? carrier.read : sourceType === 'project-file'
    ? { type: 'project-relative-json', path: source, maxBytes: MAX_MANIFEST_BYTES } : sourceType === 'hook-input'
      ? { type: 'embedded-projection', path: null, maxBytes: null } : null;
  const guidance = projection.state === 'known'
    ? 'Use only this structured manifest and current real tool definitions; do not infer availability from model names, UI, errors, or providers.'
    : 'Read current real tool definitions; if absent report UNKNOWN. Do not infer from UI, errors, names, or providers.';
  return {
    ...projection,
    source,
    modelsComplete: complete,
    modelCount,
    carrier: {
      schemaVersion: 1,
      kind: CARRIER_KIND,
      source,
      sourceType,
      path: Object.hasOwn(carrier, 'path') ? carrier.path : sourceType === 'project-file' ? source : null,
      complete,
      incompleteReason: complete ? null : carrier.incompleteReason || projection.reason || UNKNOWN,
      modelCount,
      modelFields: MODEL_FIELDS,
      projectionDigest,
      manifestDigest: carrier.manifestDigest || null,
      manifestBytes: Number.isSafeInteger(carrier.manifestBytes) ? carrier.manifestBytes : null,
      sourceDigest: carrier.sourceDigest || null,
      binding: carrier.binding || (sourceType === 'hook-input' ? {
        project: carrier.project || null,
        sessionId: carrier.sessionId || null,
        turnId: carrier.turnId || null,
        eventName: carrier.eventName || null,
        source: 'hook-input',
      } : null),
      carrierBytes: Number.isSafeInteger(carrier.carrierBytes) ? carrier.carrierBytes : null,
      maxHookInputBytes: MAX_HOOK_INPUT_BYTES,
      maxCarrierBytes: MAX_DYNAMIC_CARRIER_BYTES,
      maxManifestBytes: MAX_MANIFEST_BYTES,
      createdAt: carrier.createdAt || null,
      expiresAt: carrier.expiresAt || null,
      ttlMs: Number.isSafeInteger(carrier.ttlMs) ? carrier.ttlMs : null,
      read,
    },
    guidance,
  };
}
function manifestCandidates(root) {
  return MANIFEST_RELATIVE_PATHS.map((rel) => ({ rel, file: path.join(root, rel) }));
}
function readManifestFile(file) {
  const stat = fs.lstatSync(file);
  if (!stat.isFile() || stat.isSymbolicLink()) return { ok: false, reason: 'unsafe-manifest' };
  if (stat.size > MAX_MANIFEST_BYTES) return { ok: false, reason: 'manifest-too-large', manifestBytes: stat.size };
  const body = fs.readFileSync(file, 'utf8');
  const details = { manifestBytes: Buffer.byteLength(body), manifestDigest: `sha256:${sha(body)}` };
  try { return { ok: true, value: JSON.parse(body), ...details }; }
  catch { return { ok: false, reason: 'invalid-json', ...details }; }
}
function readDynamicCarrier(root, relative, opts = {}) {
  const base = canonicalRoot(root);
  if (!base || !opts || typeof opts !== 'object' || Array.isArray(opts)) {
    return { ok: false, state: UNKNOWN, reason: 'invalid-binding' };
  }
  const expectedEvent = text(opts.eventName), expectedSession = text(opts.sessionId);
  const expectedTurn = opts.turnId == null ? null : text(opts.turnId);
  if (!expectedEvent || !expectedSession || (expectedEvent !== 'SessionStart' && !expectedTurn)) {
    return { ok: false, state: UNKNOWN, reason: 'missing-binding' };
  }
  if (typeof relative !== 'string' || path.isAbsolute(relative) || relative.split(/[\\/]/).includes('..')
    || !relative.startsWith(`${DYNAMIC_CARRIER_RELATIVE_DIR}/`) || !/^c-[0-9a-f]{32}\.json$/.test(path.basename(relative))) {
    return { ok: false, state: UNKNOWN, reason: 'unsafe-carrier-path' };
  }
  const file = path.join(base, relative);
  let stat;
  try { stat = fs.lstatSync(file); } catch { return { ok: false, state: UNKNOWN, reason: 'carrier-missing' }; }
  if (!stat.isFile() || stat.isSymbolicLink()) return { ok: false, state: UNKNOWN, reason: 'unsafe-carrier' };
  if (stat.size > MAX_DYNAMIC_CARRIER_BYTES) return { ok: false, state: UNKNOWN, reason: 'carrier-too-large' };
  let value;
  try { value = JSON.parse(fs.readFileSync(file, 'utf8')); } catch { return { ok: false, state: UNKNOWN, reason: 'invalid-carrier-json' }; }
  if (!value || value.schemaVersion !== 1 || value.kind !== CARRIER_KIND || value.sourceType !== 'hook-input' || value.source !== 'hook-input'
    || !plainObject(value.projection) || value.projection.schemaVersion !== 1
    || value.projection.kind !== PROJECTION_KIND || value.projection.state !== 'known'
    || value.projection.reason !== null || !Array.isArray(value.projection.models)) {
    return { ok: false, state: UNKNOWN, reason: 'invalid-carrier-shape' };
  }
  for (const model of value.projection.models) {
    if (!plainObject(model) || typeof model.channel !== 'string' || !model.channel.trim()
      || typeof model.model !== 'string' || !model.model.trim() || typeof model.reasoning !== 'string' || !model.reasoning.trim()
      || typeof model.family !== 'string' || !model.family.trim() || typeof model.status !== 'string' || !model.status.trim()
      || !plainObject(model.availability) || typeof model.availability.status !== 'string'
      || !Array.isArray(model.capabilities) || !Array.isArray(model.suitability)) {
      return { ok: false, state: UNKNOWN, reason: 'invalid-carrier-model-shape' };
    }
  }
  const freshness = validateFreshness(value.freshness, opts.now);
  if (!freshness.ok) return { ok: false, state: UNKNOWN, reason: freshness.reason };
  const expectedProjection = `sha256:${sha(JSON.stringify(projectionPayload(value.projection)))}`;
  if (value.projectionDigest !== expectedProjection) return { ok: false, state: UNKNOWN, reason: 'projection-digest-mismatch' };
  if (value.modelCount !== value.projection.models.length) return { ok: false, state: UNKNOWN, reason: 'model-count-mismatch' };
  if (value.eventName !== expectedEvent) return { ok: false, state: UNKNOWN, reason: 'event-binding-mismatch' };
  if (value.sessionId !== expectedSession) return { ok: false, state: UNKNOWN, reason: 'session-binding-mismatch' };
  if (String(value.turnId || '') !== String(expectedTurn || '')) return { ok: false, state: UNKNOWN, reason: 'turn-binding-mismatch' };
  const bindingKeys = ['project', 'sessionId', 'turnId', 'eventName', 'source'];
  if (!value.binding || typeof value.binding !== 'object' || Array.isArray(value.binding)
    || JSON.stringify(Object.keys(value.binding).sort()) !== JSON.stringify(bindingKeys.sort())
    || typeof value.binding.project !== 'string' || !value.binding.project.trim() || canonicalRoot(value.binding.project) !== base
    || typeof value.binding.sessionId !== 'string' || !value.binding.sessionId.trim()
    || (value.binding.turnId !== null && typeof value.binding.turnId !== 'string')
    || typeof value.binding.eventName !== 'string' || !value.binding.eventName.trim()
    || value.binding.source !== 'hook-input') {
    return { ok: false, state: UNKNOWN, reason: 'project-binding-mismatch' };
  }
  if (value.binding.eventName !== value.eventName || value.binding.sessionId !== value.sessionId
    || String(value.binding.turnId || '') !== String(value.turnId || '') || value.binding.source !== 'hook-input') {
    return { ok: false, state: UNKNOWN, reason: 'binding-mismatch' };
  }
  if (!value.sourceManifest || `sha256:${sha(JSON.stringify(value.sourceManifest))}` !== value.sourceDigest) {
    return { ok: false, state: UNKNOWN, reason: 'source-digest-mismatch' };
  }
  if (!Array.isArray(value.modelFields) || JSON.stringify(value.modelFields) !== JSON.stringify(MODEL_FIELDS)) {
    return { ok: false, state: UNKNOWN, reason: 'model-fields-mismatch' };
  }
  if (!Number.isSafeInteger(value.sourceBytes) || value.sourceBytes !== Buffer.byteLength(JSON.stringify(value.sourceManifest))) {
    return { ok: false, state: UNKNOWN, reason: 'source-bytes-mismatch' };
  }
  const normalizedSource = normalizeManifest(value.sourceManifest);
  if (normalizedSource.state !== 'known'
    || JSON.stringify(projectionPayload(normalizedSource)) !== JSON.stringify(projectionPayload(value.projection))) {
    return { ok: false, state: UNKNOWN, reason: 'projection-source-mismatch' };
  }
  const expectedRel = dynamicCarrierRelativePath(value.projectionDigest, {
    sourceDigest: value.sourceDigest, eventName: value.eventName, sessionId: value.sessionId, turnId: value.turnId,
  });
  if (relative !== expectedRel) return { ok: false, state: UNKNOWN, reason: 'carrier-path-mismatch' };
  return { ok: true, state: 'known', value, freshness };
}
function project(root, opts = {}) {
  if (!canonicalRoot(root) || !opts || typeof opts !== 'object' || Array.isArray(opts)) {
    return withGuidance(unknown('invalid-input'), { source: null, sourceType: 'none', complete: false, incompleteReason: 'invalid-input', read: null });
  }
  if (Object.hasOwn(opts, 'manifest')) return hookInputProjection(root, opts.manifest, opts);
  for (const candidate of manifestCandidates(canonicalRoot(root))) {
    if (!fs.existsSync(candidate.file)) continue;
    const read = readManifestFile(candidate.file);
    if (!read.ok) return withGuidance(unknown(read.reason), {
      source: candidate.rel,
      sourceType: 'project-file',
      manifestBytes: read.manifestBytes,
      manifestDigest: read.manifestDigest,
    });
    const bound = validateProjectManifest(root, read.value, opts, { sourceDigest: read.manifestDigest });
    if (!bound.ok) return withGuidance(unknown(bound.reason), {
      source: candidate.rel,
      sourceType: 'project-file',
      complete: false,
      incompleteReason: bound.reason,
      manifestBytes: read.manifestBytes,
      manifestDigest: read.manifestDigest,
      read: null,
    });
    return withGuidance(normalizeManifest(read.value), {
      source: candidate.rel,
      sourceType: 'project-file',
      manifestBytes: read.manifestBytes,
      manifestDigest: read.manifestDigest,
      sourceDigest: read.manifestDigest,
      createdAt: bound.freshness.createdAt,
      expiresAt: bound.freshness.expiresAt,
      ttlMs: bound.freshness.ttlMs,
    });
  }
  return withGuidance(unknown('missing'), { source: null, sourceType: 'none' });
}

module.exports = {
  UNKNOWN,
  KIND,
  PROJECTION_KIND,
  CARRIER_KIND,
  KNOWN_FAMILIES,
  MANIFEST_RELATIVE_PATHS,
  MAX_MANIFEST_BYTES,
  MAX_HOOK_INPUT_BYTES,
  MAX_DYNAMIC_CARRIER_BYTES,
  DYNAMIC_CARRIER_RELATIVE_DIR,
  DYNAMIC_CARRIER_TTL_MS,
  MAX_FRESHNESS_FUTURE_SKEW_MS,
  MODEL_FIELDS,
  normalizeManifest,
  manifestCandidates,
  dynamicCarrierRelativePath,
  readDynamicCarrier,
  project,
};
