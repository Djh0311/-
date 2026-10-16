'use strict';

const fs = require('fs');
const path = require('path');
const io = require('./io.js');
const tree = require('./tree.js');

const SCHEMA_VERSION = 1;
const KIND = 'harness-lite-delegation-ledger';
const RELATIVE_PATH = 'docs/harness/delegation.json';
const UNKNOWN = 'UNKNOWN';
const HEARTBEAT_MS = 300000;
const STATUSES = new Set(['active', 'reported_complete', 'partial', 'blocked', 'accepted', 'rejected']);
const OBSERVATION_KINDS = new Set(['heartbeat', 'activity', 'progress']);
const PROGRESS_KINDS = new Set(['verified-fact', 'route-eliminated', 'acceptance-advanced', 'root-cause-isolated', 'actionable-blocker']);
const AGENT_FIELDS = Object.freeze(['channel', 'model', 'modelFamily', 'reasoning']);
const STORED_EVENT_RECORD_VERSION = 2;
const PASSIVE_OBSERVATIONS = new Set(['silence', 'thinking', 'long-tool', 'tool-wait', 'provider-delay', 'heartbeat-overdue']);
const INTERVENTION_REASONS = new Set(['stopped', 'stall', 'actual-blocker', 'drift', 'repeated-disproven-route', 'forbidden-scope', 'write-scope-overlap']);
const FAILURE_CATEGORIES = new Set(['goal-boundary-misunderstanding', 'disproven-diagnosis', 'rejected-implementation-route',
  'claimed-complete-acceptance-failure', 'false-pass-evidence']);
const NON_COUNTING_FAILURE_REASONS = new Set(['tool-test-lint-intermediate', 'tool', 'test', 'lint', 'intermediate',
  'exploration-negative', 'provider-transport', 'provider', 'transport', 'auth', 'permission', 'quota', 'host',
  'provider-transport-auth-permission-quota-host', 'external-dependency', 'same-root-multiple-assertion', 'incomplete-recovery']);
const RECOVERY_EVENT_KINDS = new Set(['failure', 'acceptance_pass']);
const RECOVERY_TIERS = new Set(['ordinary', 'astra', 'terra', 'sol', 'exhausted']);
const RECOVERY_STATUSES = new Set(['ordinary', 'active', 'blocked', 'accepted', 'observed']);
const DEFAULT_SOL_ATTEMPT_LIMIT = 3;
const SOL_ATTEMPT_LIMIT_MIN = 1;
const SOL_ATTEMPT_LIMIT_MAX = 5;
const DEFAULT_RECOVERY_ATTEMPT_LIMIT = DEFAULT_SOL_ATTEMPT_LIMIT;
const RECOVERY_ATTEMPT_LIMIT_MIN = SOL_ATTEMPT_LIMIT_MIN;
const RECOVERY_ATTEMPT_LIMIT_MAX = SOL_ATTEMPT_LIMIT_MAX;
const CURRENT_RECOVERY_POLICY = 'astra-v1';
const FORBIDDEN_KEYS = /credential|secret|token|password|prompt|transcript|code/i;
const ID_RE = /^[A-Za-z0-9._:-]{1,120}$/;
const SHA_RE = /^sha256:[0-9a-f]{64}$/;
const DECLARED_UNITS = Symbol('harness-lite-declared-work-units');

function canonical(value) {
  if (Array.isArray(value)) return value.map(canonical);
  if (value && typeof value === 'object') return Object.fromEntries(Object.keys(value).sort().map((key) => [key, canonical(value[key])]));
  return value;
}
function ledgerPath(root) {
  return path.join(root, RELATIVE_PATH);
}
function projectIdentity(root) {
  let real;
  try { real = fs.realpathSync(root); } catch { real = path.resolve(root); }
  return `sha256:${io.sha(real)}`;
}
function leafRel(root, chain) {
  return chain?.leaf?.file ? path.relative(root, chain.leaf.file).replaceAll('\\', '/') : UNKNOWN;
}
function binding(root, chain = tree.readChain(root)) {
  return { schemaVersion: SCHEMA_VERSION, project: projectIdentity(root), stage: chain.stage?.name || UNKNOWN, leaf: leafRel(root, chain) };
}
function healthyBinding(expected, chain) {
  return chain?.health?.ok === true && !!chain.stage && !!chain.leaf && expected.stage !== UNKNOWN && expected.leaf !== UNKNOWN;
}
function bindDeclaredUnits(ledger, chain) {
  if (!ledger || typeof ledger !== 'object') return ledger;
  Object.defineProperty(ledger, DECLARED_UNITS, {
    value: new Set((chain?.leaf?.workUnits || []).map((unit) => unit.id)),
    enumerable: false,
    configurable: true,
  });
  return ledger;
}
function declaredInLedger(ledger, id) {
  const declared = ledger?.[DECLARED_UNITS];
  return declared instanceof Set && declared.has(id);
}
function freshLedger(root, chain = tree.readChain(root)) {
  return bindDeclaredUnits({ schemaVersion: SCHEMA_VERSION, kind: KIND, ...binding(root, chain), workUnits: {}, events: {} }, chain);
}
function freshFailures() {
  return { schemaVersion: 1, events: {}, problems: {}, leases: {} };
}
function stale(reason, expected, value = null) {
  return { ok: true, live: false, state: 'stale', reason, expected, ledger: value, workUnits: {}, status: UNKNOWN };
}
function unknown(reason, expected, value = null) {
  return { ok: true, live: false, state: UNKNOWN, reason, expected, ledger: value, workUnits: {}, status: UNKNOWN };
}
function readCarrier(root) {
  const file = ledgerPath(root);
  let stat;
  try { stat = fs.lstatSync(file); }
  catch (error) { return error.code === 'ENOENT' ? { kind: 'missing' } : { kind: 'unsafe-carrier', error }; }
  if (!stat.isFile() || stat.isSymbolicLink()) return { kind: 'unsafe-carrier' };
  try { return { kind: 'json', value: JSON.parse(fs.readFileSync(file, 'utf8')) }; }
  catch (error) { return { kind: 'malformed-json', error }; }
}
function plainObject(value) {
  return !!value && typeof value === 'object' && !Array.isArray(value);
}
function validId(value) {
  return typeof value === 'string' && ID_RE.test(value);
}
function validText(value) {
  return typeof value === 'string' && value.length > 0 && value.length <= 500 && !value.includes('\0');
}
function validOptionalText(value) {
  return value === undefined || value === null || validText(value);
}
function validTime(value) {
  return typeof value === 'string' && eventTime(value) != null;
}
function validOptionalTime(value) {
  return value === undefined || value === null || validTime(value);
}
function validBool(value) {
  return value === undefined || value === true || value === false;
}
function validNonNegativeInt(value) {
  return Number.isInteger(value) && value >= 0;
}
function validSolAttemptLimit(value) {
  return Number.isInteger(value) && value >= SOL_ATTEMPT_LIMIT_MIN && value <= SOL_ATTEMPT_LIMIT_MAX;
}
function validTextArray(value, validator = validId) {
  return Array.isArray(value) && value.every((item) => validator(item));
}
function validAgentFields(value) {
  return AGENT_FIELDS.every((field) => validOptionalText(value?.[field]));
}
function sameMembers(left, right) {
  return left.length === right.length && [...left].sort().every((item, index) => item === [...right].sort()[index]);
}
function recoveryLeaseKeyFrom(row) {
  return keyDigest({ leaf: row.leaf, stableWorkUnit: row.stableWorkUnit,
    acceptanceGate: row.acceptanceGate, stableProblemFingerprint: row.stableProblemFingerprint });
}
function recoveryProblemKeyFrom(row) {
  if (row.policy === CURRENT_RECOVERY_POLICY || row.recoveryRole) {
    return keyDigest({ leaf: row.leaf, stableWorkUnit: row.stableWorkUnit,
      acceptanceGate: row.acceptanceGate, stableProblemFingerprint: row.stableProblemFingerprint });
  }
  return keyDigest({ leaf: row.leaf, stableWorkUnit: row.stableWorkUnit,
    acceptanceGate: row.acceptanceGate, stableProblemFingerprint: row.stableProblemFingerprint, modelFamily: row.modelFamily });
}
function storedRecoveryDigest(event) {
  const { digest: _digest, ...identity } = event;
  if (event.kind === 'failure') {
    identity.counted = false;
    identity.drift = false;
  }
  return recoveryDigest(identity);
}
function recoveryShapeReason(value) {
  if (value.failures === undefined) return null;
  const failures = value.failures;
  if (!plainObject(failures) || failures.schemaVersion !== 1
    || !plainObject(failures.events) || !plainObject(failures.problems) || !plainObject(failures.leases)) return 'shape';
  for (const [problemKey, problem] of Object.entries(failures.problems)) {
    if (!SHA_RE.test(problemKey) || !plainObject(problem) || problem.key !== problemKey || !SHA_RE.test(problem.leaseKey || '')) return 'shape';
    if (!validText(problem.leaf) || !validId(problem.stableWorkUnit) || !validId(problem.acceptanceGate)
      || !validId(problem.stableProblemFingerprint) || !validId(problem.modelFamily)) return 'shape';
    if (problem.leaseKey !== recoveryLeaseKeyFrom(problem) || problem.key !== recoveryProblemKeyFrom(problem)) return 'shape';
    if (!RECOVERY_TIERS.has(problem.tier) || !RECOVERY_STATUSES.has(problem.status)
      || !validNonNegativeInt(problem.effectiveCount) || !validOptionalTime(problem.updatedAt)
      || !validOptionalTime(problem.acceptedAt) || !validBool(problem.drift)) return 'shape';
    if (!validTextArray(problem.events) || !validTextArray(problem.countedSubstantiveKeys)
      || !validTextArray(problem.countedPrimaryCauses, validText) || !validTextArray(problem.driftSubstantiveKeys || [])) return 'shape';
    if (problem.policy !== undefined && problem.policy !== null
      && (problem.policy !== CURRENT_RECOVERY_POLICY || (problem.recoveryRole !== null && !['ordinary', 'recovery'].includes(problem.recoveryRole)))) return 'shape';
  }
  for (const [leaseKey, lease] of Object.entries(failures.leases)) {
    if (!SHA_RE.test(leaseKey) || !plainObject(lease) || lease.leaseKey !== leaseKey) return 'shape';
    if (!validText(lease.leaf) || !validId(lease.stableWorkUnit) || !validId(lease.acceptanceGate)
      || !validId(lease.stableProblemFingerprint) || !RECOVERY_TIERS.has(lease.tier)
      || !['active', 'blocked'].includes(lease.status) || !validTime(lease.updatedAt)
      || !validOptionalText(lease.reason) || !validOptionalText(lease.needed)
      || !validOptionalText(lease.triggerEvent) || !validNonNegativeInt(lease.effectiveCount)
      || !validSolAttemptLimit(lease.solAttemptLimit)
      || (lease.recoveryAttemptLimit !== undefined && lease.recoveryAttemptLimit !== lease.solAttemptLimit)) return 'shape';
    if (Object.keys(lease).some((key) => /family/i.test(key))) return 'shape';
    if (lease.leaseKey !== recoveryLeaseKeyFrom(lease)) return 'shape';
  }
  for (const [eventId, event] of Object.entries(failures.events)) {
    if (!validId(eventId) || !plainObject(event) || event.id !== eventId || !SHA_RE.test(event.digest || '')
      || !RECOVERY_EVENT_KINDS.has(event.kind) || !validTime(event.at) || !SHA_RE.test(event.leaseKey || '')
      || !validId(event.stableWorkUnit) || !validId(event.acceptanceGate) || !validId(event.stableProblemFingerprint)
      || !validText(event.leaf) || !validText(event.evidenceRef)) return 'shape';
    if (!validAgentFields(event)) return 'shape';
    if (event.leaseKey !== recoveryLeaseKeyFrom(event)) return 'shape';
    if (event.digest !== storedRecoveryDigest(event)) return 'shape';
    if (event.kind === 'failure') {
      if (!SHA_RE.test(event.problemKey || '') || !validId(event.modelFamily) || !validId(event.category)
        || typeof event.effective !== 'boolean' || typeof event.completeRecovery !== 'boolean'
        || typeof event.counted !== 'boolean' || typeof event.drift !== 'boolean'
        || !RECOVERY_TIERS.has(event.tier) || !validOptionalText(event.nonCountingReason)
        || !validText(event.primaryCause) || !validId(event.substantiveKey)
        || !(event.solAttemptLimit === null || validSolAttemptLimit(event.solAttemptLimit))) return 'shape';
      if (event.problemKey !== recoveryProblemKeyFrom(event)) return 'shape';
      if (event.policy !== undefined && event.policy !== null
        && (event.policy !== CURRENT_RECOVERY_POLICY || !['ordinary', 'recovery'].includes(event.recoveryRole))) return 'shape';
      if (event.policy === CURRENT_RECOVERY_POLICY
        && ((event.recoveryRole === 'ordinary' && event.tier !== 'ordinary')
          || (event.recoveryRole === 'recovery' && (event.tier !== 'astra' || recoveryTier(event.modelFamily) !== 'astra'))
          || ((event.recoveryRole === 'recovery') !== (event.completeRecovery === true)))) return 'shape';
      if (!FAILURE_CATEGORIES.has(event.category) && !NON_COUNTING_FAILURE_REASONS.has(event.nonCountingReason)) return 'shape';
      if (event.counted && (event.effective !== true || !FAILURE_CATEGORIES.has(event.category))) return 'shape';
      if (event.counted && event.tier !== 'ordinary' && event.completeRecovery !== true) return 'shape';
      if (event.counted && event.nonCountingReason !== null && event.nonCountingReason !== undefined) return 'shape';
    if (event.solAttemptLimit !== null && !['astra', 'terra', 'sol'].includes(event.tier)) return 'shape';
    if (event.recoveryAttemptLimit !== undefined && event.recoveryAttemptLimit !== null
      && !validSolAttemptLimit(event.recoveryAttemptLimit)) return 'shape';
      if (!plainObject(failures.problems[event.problemKey])) return 'shape';
      if (!(failures.problems[event.problemKey].events || []).includes(eventId)) return 'shape';
    } else if (event.kind === 'acceptance_pass') {
      if (event.problemKey !== null && event.problemKey !== undefined) return 'shape';
    }
  }
  for (const problem of Object.values(failures.problems)) for (const eventId of problem.events) {
    const event = failures.events[eventId];
    if (!plainObject(event) || event.problemKey !== problem.key) return 'shape';
  }
  for (const problem of Object.values(failures.problems)) {
    const rows = problem.events.map((eventId) => failures.events[eventId]);
    const counted = rows.filter((event) => event.counted);
    const drift = rows.filter((event) => event.drift);
    if (rows.some((event) => event.kind !== 'failure' || event.problemKey !== problem.key
      || event.leaseKey !== problem.leaseKey || !RECOVERY_TIERS.has(event.tier)
      || (problem.policy === CURRENT_RECOVERY_POLICY ? event.policy !== CURRENT_RECOVERY_POLICY : event.modelFamily !== problem.modelFamily))) return 'shape';
    if (problem.effectiveCount !== counted.length) return 'shape';
    if (!sameMembers(problem.countedSubstantiveKeys, counted.map((event) => event.substantiveKey))) return 'shape';
    if (!sameMembers(problem.countedPrimaryCauses, counted.map((event) => event.primaryCause))) return 'shape';
    if ((problem.drift === true) !== (drift.length > 0)) return 'shape';
    if (!sameMembers(problem.driftSubstantiveKeys || [], [...new Set(drift.map((event) => event.substantiveKey))])) return 'shape';
  }
  for (const lease of Object.values(failures.leases)) {
    if (!Object.values(failures.problems).some((problem) => problem.leaseKey === lease.leaseKey)) return 'shape';
    const trigger = failures.events[lease.triggerEvent];
    if (!plainObject(trigger) || trigger.kind !== 'failure' || trigger.leaseKey !== lease.leaseKey || trigger.counted !== true) return 'shape';
    const triggerProblem = failures.problems[trigger.problemKey];
    const countedRows = (triggerProblem?.events || []).map((eventId) => failures.events[eventId]).filter((event) => event?.counted);
    const leaseCountedRows = Object.values(failures.events).filter((event) => event?.kind === 'failure'
      && event.leaseKey === lease.leaseKey && event.counted === true);
    const leaseAstraRows = leaseCountedRows.filter((event) => event.tier === 'astra');
    const leaseTerraRows = leaseCountedRows.filter((event) => event.tier === 'terra');
    const leaseTerraCount = leaseCountedRows.filter((event) => event.tier === 'terra').length;
    const leaseSolCount = leaseCountedRows.filter((event) => event.tier === 'sol').length;
    const leaseAstraCount = leaseAstraRows.length;
    const triggerOrdinal = countedRows.findIndex((event) => event.id === trigger.id) + 1;
    const recoveryOrdinal = leaseCountedRows.filter((event) => event.tier === trigger.tier).findIndex((event) => event.id === trigger.id) + 1;
    if (!plainObject(triggerProblem) || lease.updatedAt !== trigger.at || triggerOrdinal < 1) return 'shape';
    if (trigger.effective !== true || !FAILURE_CATEGORIES.has(trigger.category)) return 'shape';
    if (trigger.tier !== 'ordinary' && trigger.completeRecovery !== true) return 'shape';
    if (leaseCountedRows.some((event) => eventTime(event.at) > eventTime(trigger.at))) return 'shape';
    if (leaseCountedRows.some((event) => event.solAttemptLimit !== null && event.solAttemptLimit !== lease.solAttemptLimit)) return 'shape';
    if (lease.tier === 'terra') {
      if (lease.status !== 'active' || lease.reason !== 'ordinary-five-effective-failures'
        || lease.needed !== 'Terra xhigh complete recovery' || trigger.tier !== 'ordinary'
        || lease.effectiveCount !== 5 || triggerOrdinal !== 5 || lease.solAttemptLimit !== DEFAULT_SOL_ATTEMPT_LIMIT) return 'shape';
    } else if (lease.tier === 'astra') {
      if (!['active', 'blocked'].includes(lease.status) || !['ordinary-five-effective-failures', 'astra-effective-semantic-failure', 'astra-exhausted'].includes(lease.reason)
        || lease.needed !== 'Astra xhigh complete recovery' || !['ordinary', 'astra'].includes(trigger.tier)
        || lease.effectiveCount < 5 || triggerOrdinal < 5) return 'shape';
      const configuredAstraLimit = leaseAstraRows[0]?.recoveryAttemptLimit
        || leaseAstraRows[0]?.solAttemptLimit
        || (trigger.tier === 'ordinary' ? (trigger.recoveryAttemptLimit || DEFAULT_RECOVERY_ATTEMPT_LIMIT) : DEFAULT_RECOVERY_ATTEMPT_LIMIT);
      if (configuredAstraLimit !== lease.solAttemptLimit) return 'shape';
      if (lease.effectiveCount !== triggerProblem.effectiveCount
        || (trigger.tier === 'astra' && leaseAstraRows.length !== recoveryOrdinal)
        || (trigger.tier === 'ordinary' && leaseAstraRows.length !== 0)) return 'shape';
      if (lease.reason === 'ordinary-five-effective-failures'
        && (trigger.tier !== 'ordinary' || triggerOrdinal !== 5 || lease.effectiveCount !== 5)) return 'shape';
      if (lease.reason === 'astra-effective-semantic-failure'
        && (trigger.tier !== 'astra' || recoveryOrdinal < 1 || lease.effectiveCount < 6
          || recoveryOrdinal !== leaseAstraRows.length || lease.effectiveCount !== triggerProblem.effectiveCount)) return 'shape';
      if (lease.reason === 'astra-exhausted'
        && (lease.status !== 'blocked' || trigger.tier !== 'astra' || recoveryOrdinal !== lease.solAttemptLimit)) return 'shape';
    } else if (lease.tier === 'sol') {
      if (lease.status !== 'active' || !['terra-effective-semantic-failure', 'sol-effective-semantic-failure'].includes(lease.reason)
        || lease.needed !== 'Sol xhigh complete recovery' || !['terra', 'sol'].includes(trigger.tier)
        || lease.effectiveCount < 1 || leaseTerraCount !== 1) return 'shape';
      if ((leaseTerraRows[0].solAttemptLimit || DEFAULT_SOL_ATTEMPT_LIMIT) !== lease.solAttemptLimit) return 'shape';
      if (lease.reason === 'terra-effective-semantic-failure'
        && (trigger.tier !== 'terra' || lease.effectiveCount !== 1 || triggerOrdinal !== 1 || leaseSolCount !== 0)) return 'shape';
      if (lease.reason === 'sol-effective-semantic-failure'
        && (trigger.tier !== 'sol' || lease.effectiveCount >= lease.solAttemptLimit
          || triggerOrdinal !== lease.effectiveCount || leaseSolCount !== lease.effectiveCount)) return 'shape';
    } else if (lease.tier === 'exhausted') {
      if (lease.reason === 'astra-exhausted') {
        if (lease.status !== 'blocked' || !lease.needed.includes('user decision') || trigger.tier !== 'astra'
          || recoveryOrdinal !== lease.solAttemptLimit || lease.effectiveCount < 5) return 'shape';
        const configuredAstraLimit = leaseAstraRows[0]?.recoveryAttemptLimit
          || leaseAstraRows[0]?.solAttemptLimit
          || (trigger.tier === 'ordinary' ? (trigger.recoveryAttemptLimit || DEFAULT_RECOVERY_ATTEMPT_LIMIT) : DEFAULT_RECOVERY_ATTEMPT_LIMIT);
        if (configuredAstraLimit !== lease.solAttemptLimit) return 'shape';
        if (lease.effectiveCount !== triggerProblem.effectiveCount
          || (trigger.tier === 'astra' && recoveryOrdinal !== leaseAstraRows.length)
          || (trigger.tier === 'ordinary' && leaseAstraRows.length !== 0)) return 'shape';
      } else {
        if (lease.status !== 'blocked' || lease.reason !== 'sol-exhausted'
          || !lease.needed.includes('user decision') || trigger.tier !== 'sol' || lease.effectiveCount !== lease.solAttemptLimit
          || triggerOrdinal !== lease.solAttemptLimit || leaseTerraCount !== 1 || leaseSolCount !== lease.solAttemptLimit) return 'shape';
        if ((leaseTerraRows[0].solAttemptLimit || DEFAULT_SOL_ATTEMPT_LIMIT) !== lease.solAttemptLimit) return 'shape';
      }
    } else return 'shape';
  }
  return null;
}
function ledgerShapeReason(value) {
  if (!plainObject(value.workUnits) || !plainObject(value.events)) return 'shape';
  for (const [id, unit] of Object.entries(value.workUnits)) {
    if (!validId(id) || !plainObject(unit) || unit.id !== id || !validId(unit.id)) return 'shape';
    if (!validAgentFields(unit)) return 'shape';
    if (!(unit.status === UNKNOWN || STATUSES.has(unit.status))) return 'shape';
    if (!Array.isArray(unit.dependencies) || unit.dependencies.some((dep) => !validId(dep))) return 'shape';
    if (!Array.isArray(unit.writeScope) || unit.writeScope.some((scope) => !validText(scope))) return 'shape';
    if (!Array.isArray(unit.events) || unit.events.some((eventId) => !validId(eventId))) return 'shape';
    for (const field of ['updatedAt', 'activeAt', 'heartbeatAt', 'activityAt', 'progressAt', 'acceptedAt']) {
      if (!validOptionalTime(unit[field])) return 'shape';
    }
    if (!validOptionalText(unit.activityKind) || !validOptionalText(unit.evidenceRef)
      || !validOptionalText(unit.acceptanceEvidenceRef)) return 'shape';
    if (unit.progressKind !== undefined && unit.progressKind !== null && !PROGRESS_KINDS.has(unit.progressKind)) return 'shape';
    const progressFields = [unit.progressAt, unit.progressKind, unit.evidenceRef].filter((item) => item !== undefined && item !== null);
    if (progressFields.length && (!validTime(unit.progressAt) || !PROGRESS_KINDS.has(unit.progressKind) || !validText(unit.evidenceRef))) return 'shape';
    if (unit.reportedResult !== undefined) {
      const result = unit.reportedResult;
      if (!plainObject(result) || !['reported_complete', 'partial', 'blocked'].includes(result.status)
        || !validTime(result.at) || !validOptionalText(result.summary) || !validOptionalText(result.evidenceRef)) return 'shape';
    }
  }
  for (const [eventId, event] of Object.entries(value.events)) {
    if (!validId(eventId) || !plainObject(event)) return 'shape';
    if (!/^sha256:[0-9a-f]{64}$/.test(event.digest || '') || !validId(event.workUnit)
      || !plainObject(value.workUnits[event.workUnit]) || !validTime(event.at)) return 'shape';
    if (!validAgentFields(event)) return 'shape';
    const type = event.type || 'status';
    if (!['status', 'heartbeat', 'activity', 'progress'].includes(type)) return 'shape';
    if (type === 'status') {
      if (!STATUSES.has(event.status)) return 'shape';
    } else if (event.status !== null && event.status !== undefined) return 'shape';
    if (event.recordVersion !== undefined) {
      if (event.recordVersion !== STORED_EVENT_RECORD_VERSION || event.id !== eventId) return 'shape';
      if (!validOptionalText(event.summary) || !validOptionalText(event.evidenceRef)
        || !Array.isArray(event.dependencies) || event.dependencies.some((dep) => !validId(dep))
        || !Array.isArray(event.writeScope) || event.writeScope.some((scope) => !validText(scope))
        || !validOptionalText(event.activityKind) || !validOptionalText(event.progressKind)) return 'shape';
      if (type === 'activity' && !validText(event.activityKind)) return 'shape';
      if (type === 'progress' && (!PROGRESS_KINDS.has(event.progressKind) || !validText(event.evidenceRef))) return 'shape';
      if (event.digest !== eventDigest(recordFromStoredEvent(event))) return 'shape';
    }
    if (!(value.workUnits[event.workUnit].events || []).includes(eventId)) return 'shape';
  }
  for (const unit of Object.values(value.workUnits)) for (const eventId of unit.events) {
    const event = value.events[eventId];
    if (!plainObject(event) || event.workUnit !== unit.id) return 'shape';
  }
  return recoveryShapeReason(value);
}
function read(root, chain = tree.readChain(root)) {
  root = path.resolve(root);
  const expected = binding(root, chain), carrier = readCarrier(root);
  if (carrier.kind === 'missing') return unknown('missing', expected);
  if (carrier.kind !== 'json') return stale(carrier.kind, expected);
  const value = carrier.value;
  if (!healthyBinding(expected, chain)) return unknown('chain', expected, value);
  if (!value || typeof value !== 'object' || Array.isArray(value)) return stale('shape', expected, value);
  if (value.schemaVersion !== SCHEMA_VERSION || value.kind !== KIND) return stale('schema', expected, value);
  for (const key of ['project', 'stage', 'leaf']) if (value[key] !== expected[key]) return stale(key, expected, value);
  const shapeReason = ledgerShapeReason(value);
  if (shapeReason) return stale(shapeReason, expected, value);
  bindDeclaredUnits(value, chain);
  return { ok: true, live: true, state: 'live', reason: null, expected, ledger: value, workUnits: value.workUnits, status: 'live' };
}
function assertSafe(value, where = 'event') {
  if (Array.isArray(value)) return value.forEach((item, index) => assertSafe(item, `${where}.${index}`));
  if (!value || typeof value !== 'object') return;
  for (const [key, child] of Object.entries(value)) {
    if (FORBIDDEN_KEYS.test(key)) throw new Error(`delegation event cannot persist ${where}.${key}`);
    assertSafe(child, `${where}.${key}`);
  }
}
function cleanText(value) {
  if (value == null) return null;
  return String(value).replace(/\s+/g, ' ').trim().slice(0, 500) || null;
}
function cleanList(value) {
  return Array.isArray(value) ? value.map((item) => cleanText(item)).filter(Boolean).slice(0, 50) : [];
}
function cleanAgentFields(event) {
  const nested = plainObject(event?.agent) ? event.agent : {};
  const fields = {};
  for (const field of AGENT_FIELDS) {
    const value = cleanText(event?.[field] === undefined ? nested[field] : event[field]);
    if (value) fields[field] = value;
  }
  return fields;
}
function applyAgentFields(unit, record) {
  const next = { ...unit };
  for (const field of AGENT_FIELDS) if (record[field]) next[field] = record[field];
  return next;
}
function eventRecord(event, at) {
  assertSafe(event);
  const id = cleanText(event.id);
  const workUnit = cleanText(event.workUnit);
  const rawStatus = cleanText(event.status);
  const rawKind = cleanText(event.kind);
  const type = rawKind && OBSERVATION_KINDS.has(rawKind) ? rawKind : 'status';
  const status = type === 'status' ? cleanText(rawStatus || rawKind) : null;
  if (!id || !ID_RE.test(id)) throw new Error('delegation event id is required');
  if (!workUnit || !ID_RE.test(workUnit)) throw new Error('delegation workUnit is required');
  if (type === 'status' && !STATUSES.has(status)) throw new Error(`delegation status is invalid: ${status}`);
  const progressKind = cleanText(event.progressKind);
  const evidenceRef = cleanText(event.evidenceRef);
  if (type === 'progress' && (!PROGRESS_KINDS.has(progressKind) || !evidenceRef)) throw new Error('delegation progress requires progressKind and evidenceRef');
  if (type === 'status' && status === 'accepted' && !evidenceRef) throw new Error('delegation accepted requires evidenceRef');
  const activityKind = cleanText(event.activityKind);
  if (type === 'activity' && !activityKind) throw new Error('delegation activity requires activityKind');
  return {
    id,
    workUnit,
    type,
    status,
    at: cleanText(event.at) || at,
    summary: cleanText(event.summary),
    evidenceRef,
    dependencies: cleanList(event.dependencies),
    writeScope: cleanList(event.writeScope),
    activityKind,
    progressKind,
    ...cleanAgentFields(event),
  };
}
function storedEventFromRecord(record, digest) {
  return { recordVersion: STORED_EVENT_RECORD_VERSION, digest, ...record };
}
function recordFromStoredEvent(event) {
  const { digest: _digest, recordVersion: _recordVersion, ...record } = event;
  return record;
}
function eventDigest(record) {
  const { at: _at, ...identity } = record;
  return `sha256:${io.sha(JSON.stringify(canonical(identity)))}`;
}
function recoveryDigest(record) {
  const { at: _at, ...identity } = record;
  return `sha256:${io.sha(JSON.stringify(canonical(identity)))}`;
}
function keyDigest(value) {
  return `sha256:${io.sha(JSON.stringify(canonical(value)))}`;
}
function recoveryTier(modelFamily) {
  if (modelFamily === 'astra' || modelFamily === 'gpt-6-astra' || modelFamily === 'gpt6-astra') return 'astra';
  if (modelFamily === 'terra' || modelFamily === 'terra-xhigh') return 'terra';
  if (modelFamily === 'sol' || modelFamily === 'sol-xhigh') return 'sol';
  return 'ordinary';
}
function cleanSolAttemptLimit(value) {
  if (value === undefined || value === null) return null;
  if (!validSolAttemptLimit(value)) throw new Error(`solAttemptLimit must be an integer from ${SOL_ATTEMPT_LIMIT_MIN} to ${SOL_ATTEMPT_LIMIT_MAX}`);
  return value;
}
function cleanRecoveryAttemptLimit(value) {
  if (value === undefined || value === null) return null;
  if (!validSolAttemptLimit(value)) throw new Error(`recoveryAttemptLimit must be an integer from ${RECOVERY_ATTEMPT_LIMIT_MIN} to ${RECOVERY_ATTEMPT_LIMIT_MAX}`);
  return value;
}
function recoveryIdentity(root, event, chain = tree.readChain(root)) {
  const leaf = leafRel(root, chain), stableWorkUnit = cleanText(event.stableWorkUnit);
  const acceptanceGate = cleanText(event.acceptanceGate), stableProblemFingerprint = cleanText(event.stableProblemFingerprint);
  const modelFamily = cleanText(event.modelFamily)?.toLowerCase() || null;
  if (!validText(leaf) || leaf === UNKNOWN) throw new Error('recovery leaf is required');
  if (!stableWorkUnit || !validId(stableWorkUnit)) throw new Error('stableWorkUnit is required');
  if (!acceptanceGate || !validId(acceptanceGate)) throw new Error('acceptanceGate is required');
  if (!stableProblemFingerprint || !validId(stableProblemFingerprint)) throw new Error('stableProblemFingerprint is required');
  const leaseBasis = { leaf, stableWorkUnit, acceptanceGate, stableProblemFingerprint };
  const leaseKey = keyDigest(leaseBasis);
  if (!modelFamily) return { ...leaseBasis, leaseKey, problemKey: null, modelFamily: null, tier: null };
  if (!validId(modelFamily)) throw new Error('explicit modelFamily is required');
  const tier = event.completeRecovery === true ? recoveryTier(modelFamily) : 'ordinary';
  return { ...leaseBasis, modelFamily, leaseKey, problemKey: keyDigest({ ...leaseBasis, modelFamily }), tier };
}
function recoveryEventRecord(root, event, at, chain) {
  assertSafe(event, 'recovery');
  const id = cleanText(event.id), kind = cleanText(event.kind || 'failure');
  if (!id || !validId(id)) throw new Error('recovery event id is required');
  if (!RECOVERY_EVENT_KINDS.has(kind)) throw new Error('recovery event kind is invalid');
  const evidenceRef = cleanText(event.evidenceRef);
  if (!evidenceRef) throw new Error('recovery event requires evidenceRef');
  let identity = recoveryIdentity(root, event, chain);
  const agent = cleanAgentFields(event);
  delete agent.modelFamily;
  const recoveryRole = cleanText(event.recoveryRole) || (event.completeRecovery === true ? 'recovery' : 'ordinary');
  if (!['ordinary', 'recovery'].includes(recoveryRole)) throw new Error('recoveryRole must be ordinary or recovery');
  const policy = CURRENT_RECOVERY_POLICY;
  identity = { ...identity, policy, recoveryRole,
    problemKey: keyDigest({ leaf: identity.leaf, stableWorkUnit: identity.stableWorkUnit,
      acceptanceGate: identity.acceptanceGate, stableProblemFingerprint: identity.stableProblemFingerprint }),
    tier: recoveryRole === 'recovery' ? 'astra' : 'ordinary' };
  const record = { id, kind, at: cleanText(event.at) || at, evidenceRef, ...identity, ...agent };
  if (kind === 'acceptance_pass') return { ...record, problemKey: null };
  const category = cleanText(event.category), primaryCause = cleanText(event.primaryCause);
  const substantiveKey = cleanText(event.substantiveKey), nonCountingReason = cleanText(event.nonCountingReason);
  const effective = event.effective === true, completeRecovery = event.completeRecovery === true;
  if (kind === 'failure' && ((recoveryRole === 'recovery') !== completeRecovery)) throw new Error('recoveryRole and completeRecovery must agree');
  const suppliedRecoveryAttemptLimit = cleanRecoveryAttemptLimit(event.recoveryAttemptLimit);
  const suppliedSolAttemptLimit = cleanSolAttemptLimit(event.solAttemptLimit);
  const recoveryAttemptLimit = suppliedRecoveryAttemptLimit || suppliedSolAttemptLimit;
  const solAttemptLimit = event.solAttemptLimit === undefined ? null : suppliedSolAttemptLimit;
  if (!identity.modelFamily || !identity.problemKey) throw new Error('explicit modelFamily is required');
  if (!category || !validId(category)) throw new Error('failure category is required');
  if (!primaryCause) throw new Error('primaryCause is required');
  if (!substantiveKey || !validId(substantiveKey)) throw new Error('substantiveKey is required');
  if (effective && !FAILURE_CATEGORIES.has(category)) throw new Error('effective failure category is invalid');
  if (!effective && (!nonCountingReason || !NON_COUNTING_FAILURE_REASONS.has(nonCountingReason))) throw new Error('non-counting failure reason is required');
  return { ...record, category, primaryCause, substantiveKey, nonCountingReason: nonCountingReason || null,
    recoveryAttemptLimit: recoveryAttemptLimit || solAttemptLimit, solAttemptLimit,
    effective, completeRecovery, counted: false, drift: false };
}
function dependencyState(ledger, id) {
  const member = declaredInLedger(ledger, id), unit = member ? ledger?.workUnits?.[id] || null : null;
  const dependencies = unit?.dependencies || [];
  const rows = dependencies.map((dep) => {
    const declared = declaredInLedger(ledger, dep), status = declared ? ledger?.workUnits?.[dep]?.status || UNKNOWN : UNKNOWN;
    return { id: dep, status, accepted: declared && status === 'accepted' };
  });
  return { workUnit: id, ready: member && !!unit && rows.every((row) => row.accepted),
    dependencies: rows, accepted: member && unit?.status === 'accepted' };
}
function eventTime(value) {
  const at = Date.parse(value || '');
  return Number.isFinite(at) ? at : null;
}
function parseableEventTime(value) {
  return eventTime(value) != null;
}
function firstEventTime(...values) {
  for (const value of values) {
    const at = eventTime(value);
    if (at != null) return at;
  }
  return null;
}
function latestUnitEventTime(ledger, workUnit) {
  const unit = ledger.workUnits[workUnit] || {};
  return (unit.events || []).map((id) => eventTime(ledger.events[id]?.at)).filter((time) => time != null)
    .reduce((max, time) => Math.max(max, time), -Infinity);
}
function applyRecord(ledger, record) {
  const digest = eventDigest(record), prior = ledger.events[record.id];
  if (prior) {
    if (prior.digest !== digest) return { ok: false, reason: 'event-replay-conflict', ledger };
    return { ok: true, replay: true, wrote: false, ledger };
  }
  const currentTime = eventTime(record.at), latestTime = latestUnitEventTime(ledger, record.workUnit);
  if (currentTime == null) return { ok: false, reason: 'time', ledger };
  if (currentTime != null && latestTime !== -Infinity && currentTime < latestTime) return { ok: false, reason: 'stale-event', ledger };
  const existing = ledger.workUnits[record.workUnit] || null;
  if (record.type !== 'status' && (!existing || existing.status !== 'active')) return { ok: false, reason: `${record.type}-non-active`, ledger };
  const unit = existing || { id: record.workUnit, status: UNKNOWN, dependencies: [], writeScope: [], events: [] };
  const dependencies = record.dependencies.length ? record.dependencies : unit.dependencies;
  const writeScope = record.writeScope.length ? record.writeScope : unit.writeScope;
  const next = applyAgentFields({ ...unit, dependencies, writeScope, events: [...(unit.events || []), record.id] }, record);
  if (record.type === 'status') {
    next.status = record.status; next.updatedAt = record.at;
    if (record.status === 'active' && !next.activeAt) next.activeAt = record.at;
    if (record.status === 'reported_complete') next.reportedResult = { status: 'reported_complete', summary: record.summary, evidenceRef: record.evidenceRef, at: record.at };
    if (record.status === 'partial' || record.status === 'blocked') next.reportedResult = { status: record.status, summary: record.summary, evidenceRef: record.evidenceRef, at: record.at };
    if (record.status === 'accepted') { next.acceptedAt = record.at; next.acceptanceEvidenceRef = record.evidenceRef; }
    if (record.status !== 'accepted') { delete next.acceptedAt; delete next.acceptanceEvidenceRef; }
  } else if (record.type === 'heartbeat') {
    next.heartbeatAt = record.at;
  } else if (record.type === 'activity') {
    next.activityAt = record.at; next.activityKind = record.activityKind;
  } else if (record.type === 'progress') {
    next.progressAt = record.at; next.progressKind = record.progressKind; next.evidenceRef = record.evidenceRef;
  }
  ledger.workUnits[record.workUnit] = next;
  ledger.events[record.id] = storedEventFromRecord(record, digest);
  return { ok: true, replay: false, wrote: true, ledger };
}
function ensureFailures(ledger) {
  if (!ledger.failures) ledger.failures = freshFailures();
  return ledger.failures;
}
function latestRecoveryEventTime(failures, leaseKey) {
  return Object.values(failures.events || {}).filter((event) => event?.leaseKey === leaseKey)
    .map((event) => eventTime(event.at)).filter((time) => time != null)
    .reduce((max, time) => Math.max(max, time), -Infinity);
}
function leaseProblems(failures, leaseKey) {
  return Object.values(failures.problems || {}).filter((problem) => problem?.leaseKey === leaseKey);
}
function acceptedClosed(failures, leaseKey) {
  return !failures.leases[leaseKey] && leaseProblems(failures, leaseKey).some((problem) => problem.status === 'accepted');
}
function leaseDuplicateInfo(failures, record) {
  const problems = leaseProblems(failures, record.leaseKey);
  const cause = problems.some((problem) => (problem.countedPrimaryCauses || []).includes(record.primaryCause));
  const route = problems.some((problem) => (problem.countedSubstantiveKeys || []).includes(record.substantiveKey));
  const drifted = problems.some((problem) => (problem.driftSubstantiveKeys || []).includes(record.substantiveKey));
  return { duplicate: cause || route, drifted };
}
function tierGate(failures, record, duplicateRoot) {
  const lease = failures.leases[record.leaseKey] || null;
  if (acceptedClosed(failures, record.leaseKey)) return { ok: false, reason: 'accepted-problem' };
  if (lease?.status === 'blocked' || lease?.tier === 'exhausted') return { ok: false, reason: 'recovery-exhausted' };
  if (!lease) return record.tier === 'ordinary' ? { ok: true } : { ok: false, reason: 'premature-recovery-tier' };
  if (duplicateRoot) return { ok: true };
  if (lease.tier === 'astra') return record.tier === 'astra' && record.completeRecovery === true
    ? { ok: true } : { ok: false, reason: 'recovery-tier-gate' };
  if (lease.tier === 'terra') return record.tier === 'terra' && record.completeRecovery === true
    ? { ok: true } : { ok: false, reason: 'recovery-tier-gate' };
  if (lease.tier === 'sol') return record.tier === 'sol' && record.completeRecovery === true
    ? { ok: true } : { ok: false, reason: 'recovery-tier-gate' };
  return { ok: false, reason: 'recovery-tier-gate' };
}
function recoveryProblem(record) {
  return { key: record.problemKey, leaseKey: record.leaseKey, leaf: record.leaf, stableWorkUnit: record.stableWorkUnit,
    acceptanceGate: record.acceptanceGate, stableProblemFingerprint: record.stableProblemFingerprint,
    modelFamily: record.policy === CURRENT_RECOVERY_POLICY ? 'mixed' : record.modelFamily,
    policy: record.policy || null, recoveryRole: record.recoveryRole || null,
    tier: record.tier, status: 'ordinary', effectiveCount: 0, events: [],
    countedSubstantiveKeys: [], countedPrimaryCauses: [], driftSubstantiveKeys: [] };
}
function leaseFromRecord(record, tier, status, reason, effectiveCount, needed, solAttemptLimit = DEFAULT_SOL_ATTEMPT_LIMIT) {
  return { leaseKey: record.leaseKey, leaf: record.leaf, stableWorkUnit: record.stableWorkUnit,
    acceptanceGate: record.acceptanceGate, stableProblemFingerprint: record.stableProblemFingerprint,
    tier, status, reason, effectiveCount, needed, recoveryAttemptLimit: solAttemptLimit, solAttemptLimit,
    updatedAt: record.at, triggerEvent: record.id };
}
function applyRecoveryRecord(ledger, record) {
  const failures = ensureFailures(ledger), digest = recoveryDigest(record), prior = failures.events[record.id];
  if (prior) {
    if (prior.digest !== digest) return { ok: false, reason: 'event-replay-conflict', ledger };
    return { ok: true, replay: true, wrote: false, ledger, counted: !!prior.counted, recovery: recoverySummary(ledger) };
  }
  const currentTime = eventTime(record.at), latestTime = latestRecoveryEventTime(failures, record.leaseKey);
  if (currentTime == null) return { ok: false, reason: 'time', ledger };
  if (latestTime !== -Infinity && currentTime < latestTime) return { ok: false, reason: 'stale-event', ledger };
  if (record.kind === 'acceptance_pass') {
    failures.events[record.id] = { ...record, digest };
    for (const problem of Object.values(failures.problems)) if (problem.leaseKey === record.leaseKey) {
      problem.status = 'accepted'; problem.acceptedAt = record.at; problem.updatedAt = record.at;
    }
    delete failures.leases[record.leaseKey];
    return { ok: true, replay: false, wrote: true, ledger, counted: false, recovery: recoverySummary(ledger) };
  }
  let problem = failures.problems[record.problemKey] || recoveryProblem(record);
  if (problem.leaseKey !== record.leaseKey
    || (record.policy === CURRENT_RECOVERY_POLICY
      ? problem.policy !== CURRENT_RECOVERY_POLICY
      : problem.modelFamily !== record.modelFamily)) return { ok: false, reason: 'problem-shape', ledger };
  const existingLease = failures.leases[record.leaseKey] || null;
  if (record.policy === CURRENT_RECOVERY_POLICY && record.recoveryAttemptLimit !== null
    && record.recoveryAttemptLimit !== undefined) {
    const previousLimits = Object.values(failures.events || {})
      .filter((event) => event?.leaseKey === record.leaseKey && event?.policy === CURRENT_RECOVERY_POLICY
        && event.recoveryAttemptLimit !== null && event.recoveryAttemptLimit !== undefined)
      .map((event) => event.recoveryAttemptLimit);
    if (previousLimits.some((limit) => limit !== record.recoveryAttemptLimit)
      || (existingLease?.tier === 'astra' && existingLease.solAttemptLimit !== record.recoveryAttemptLimit)) {
      return { ok: false, reason: 'recovery-attempt-limit-conflict', ledger };
    }
  }
  const effective = record.effective && FAILURE_CATEGORIES.has(record.category);
  const recoveryAttemptReady = record.tier === 'ordinary' || record.completeRecovery === true;
  const duplicateInfo = leaseDuplicateInfo(failures, record), duplicateRoot = duplicateInfo.duplicate;
  if (effective && record.policy === CURRENT_RECOVERY_POLICY && record.recoveryRole === 'recovery'
    && recoveryTier(record.modelFamily) !== 'astra') return { ok: false, reason: 'astra-recovery-family-required', ledger };
  if (record.solAttemptLimit !== null && record.policy !== CURRENT_RECOVERY_POLICY) {
    if (!effective || record.completeRecovery !== true || !['astra', 'terra', 'sol'].includes(record.tier)) return { ok: false, reason: 'sol-attempt-limit-scope', ledger };
    if (['astra', 'sol'].includes(existingLease?.tier) && record.solAttemptLimit !== existingLease.solAttemptLimit) return { ok: false, reason: 'sol-attempt-limit-conflict', ledger };
    if (existingLease?.tier === 'exhausted' && record.solAttemptLimit !== existingLease.solAttemptLimit) return { ok: false, reason: 'sol-attempt-limit-conflict', ledger };
  }
  if (effective) {
    const gate = tierGate(failures, record, duplicateRoot);
    if (!gate.ok) return { ok: false, reason: gate.reason, ledger };
  }
  const canCount = effective && recoveryAttemptReady && !duplicateRoot;
  const routeRepeat = duplicateRoot && ['disproven-diagnosis', 'rejected-implementation-route'].includes(record.category);
  let wroteEvent = true, duplicate = false, drift = false;
  if (duplicateRoot && !routeRepeat) { wroteEvent = false; duplicate = true; }
  else if (routeRepeat) {
    drift = true;
    if (duplicateInfo.drifted) { wroteEvent = false; duplicate = true; }
  }
  if (!wroteEvent) return { ok: true, replay: false, duplicate, wrote: false, ledger, counted: false,
    drift: duplicateInfo.drifted || !!problem.drift, recovery: recoverySummary(ledger) };
  const stored = { ...record, digest, counted: canCount, drift };
  if (!canCount && effective && !recoveryAttemptReady) stored.nonCountingReason = 'incomplete-recovery';
  failures.events[record.id] = stored;
  problem = { ...problem, events: [...problem.events, record.id], updatedAt: record.at };
  if (canCount) {
    problem.effectiveCount += 1;
    problem.countedSubstantiveKeys = [...problem.countedSubstantiveKeys, record.substantiveKey];
    problem.countedPrimaryCauses = [...problem.countedPrimaryCauses, record.primaryCause];
  }
  if (drift) {
    problem.drift = true;
    problem.status = 'observed';
    problem.driftSubstantiveKeys = [...new Set([...(problem.driftSubstantiveKeys || []), record.substantiveKey])];
  } else if (canCount) problem.status = 'active';
  failures.problems[record.problemKey] = problem;
  if (canCount && record.tier === 'ordinary' && problem.effectiveCount >= 5) {
    const recoveryAttemptLimit = record.recoveryAttemptLimit || DEFAULT_RECOVERY_ATTEMPT_LIMIT;
    failures.leases[record.leaseKey] = leaseFromRecord(record, 'astra', 'active', 'ordinary-five-effective-failures',
      problem.effectiveCount, 'Astra xhigh complete recovery', recoveryAttemptLimit);
  } else if (canCount && record.tier === 'astra') {
    const recoveryAttemptLimit = existingLease?.solAttemptLimit || record.recoveryAttemptLimit || record.solAttemptLimit || DEFAULT_RECOVERY_ATTEMPT_LIMIT;
    const priorAstraAttempts = Object.values(failures.events).filter((event) => event?.leaseKey === record.leaseKey
      && event.id !== record.id && event.tier === 'astra' && event.counted === true).length;
    const exhausted = priorAstraAttempts + 1 >= recoveryAttemptLimit;
    failures.leases[record.leaseKey] = leaseFromRecord(record, exhausted ? 'exhausted' : 'astra', exhausted ? 'blocked' : 'active',
      exhausted ? 'astra-exhausted' : 'astra-effective-semantic-failure', problem.effectiveCount,
      exhausted ? 'user decision or new evidence/diagnosis/substantively distinct route' : 'Astra xhigh complete recovery',
      recoveryAttemptLimit);
  } else if (canCount && record.tier === 'terra') {
    const solAttemptLimit = record.recoveryAttemptLimit || record.solAttemptLimit || DEFAULT_SOL_ATTEMPT_LIMIT;
    failures.leases[record.leaseKey] = leaseFromRecord(record, 'sol', 'active', 'terra-effective-semantic-failure',
      problem.effectiveCount, 'Sol xhigh complete recovery', solAttemptLimit);
  } else if (canCount && record.tier === 'sol') {
    const solAttemptLimit = existingLease?.solAttemptLimit || DEFAULT_SOL_ATTEMPT_LIMIT;
    const exhausted = problem.effectiveCount >= solAttemptLimit;
    failures.leases[record.leaseKey] = leaseFromRecord(record, exhausted ? 'exhausted' : 'sol', exhausted ? 'blocked' : 'active',
      exhausted ? 'sol-exhausted' : 'sol-effective-semantic-failure', problem.effectiveCount,
      exhausted ? 'user decision or new evidence/diagnosis/substantively distinct route' : 'Sol xhigh complete recovery',
      solAttemptLimit);
  }
  return { ok: true, replay: false, duplicate, wrote: true, ledger, counted: canCount, drift, recovery: recoverySummary(ledger) };
}
function write(root, ledger) {
  io.atomic(ledgerPath(root), `${JSON.stringify(canonical(ledger), null, 2)}\n`, 0o600);
}
function recordEvent(root, event, opts = {}) {
  root = path.resolve(root);
  const chain = opts.chain || tree.readChain(root), expected = binding(root, chain);
  if (!healthyBinding(expected, chain)) return { ok: false, status: 'HOLD', state: UNKNOWN, wrote: false, reason: 'chain', expected };
  const state = read(root, chain);
  if (state.state === 'stale') return { ok: false, status: 'STALE', wrote: false, reason: state.reason, state };
  const ledger = state.ledger || freshLedger(root, chain);
  const claimedUnit = cleanText(event?.workUnit);
  const declaredUnit = claimedUnit ? tree.declaredWorkUnit(chain, claimedUnit) : null;
  if (claimedUnit && !declaredUnit) {
    return { ok: false, status: 'HOLD', state: UNKNOWN, wrote: false, reason: 'undeclared-work-unit', ledger };
  }
  const requestedStatus = cleanText(event?.status || event?.kind);
  if (requestedStatus === 'accepted' && !cleanText(event?.evidenceRef)) {
    return { ok: false, status: 'HOLD', wrote: false, reason: 'delegation accepted requires evidenceRef', ledger };
  }
  const record = eventRecord(declaredUnit ? { ...event, workUnit: declaredUnit.id } : event, opts.at || new Date().toISOString());
  if (record.status === 'accepted' && tree.workUnitPackage(root, record.workUnit, chain).dispatchReady !== true) {
    return { ok: false, status: 'HOLD', wrote: false, reason: 'completion standards are UNKNOWN', ledger };
  }
  if (!parseableEventTime(record.at)) return { ok: false, status: 'HOLD', wrote: false, reason: 'time', ledger };
  const applied = applyRecord(ledger, record);
  if (!applied.ok) return { ok: false, status: 'HOLD', wrote: false, reason: applied.reason, ledger };
  if (applied.wrote && opts.write !== false) write(root, applied.ledger);
  return { ok: true, status: applied.replay ? 'REPLAY' : 'RECORDED', wrote: applied.wrote && opts.write !== false,
    replay: applied.replay, ledger: applied.ledger, dependency: dependencyState(applied.ledger, record.workUnit) };
}
function recordRecoveryEvent(root, event, opts = {}) {
  root = path.resolve(root);
  const chain = opts.chain || tree.readChain(root), expected = binding(root, chain);
  if (!healthyBinding(expected, chain)) return { ok: false, status: 'HOLD', state: UNKNOWN, wrote: false, reason: 'chain', expected };
  const state = read(root, chain);
  if (state.state === 'stale') return { ok: false, status: 'STALE', wrote: false, reason: state.reason, state };
  const ledger = state.ledger || freshLedger(root, chain);
  let record;
  try { record = recoveryEventRecord(root, event, opts.at || new Date().toISOString(), chain); }
  catch (error) { return { ok: false, status: 'HOLD', wrote: false, reason: error.message, ledger }; }
  const legacyLease = Object.values(ledger.failures?.leases || {}).find((lease) => lease.leaseKey === record.leaseKey
    && ['terra', 'sol'].includes(lease.tier) && ['active', 'blocked'].includes(lease.status));
  if (legacyLease) {
    return { ok: false, status: 'HOLD', wrote: false, reason: 'legacy-recovery-requires-explicit-migration', ledger,
      recovery: recoverySummary(ledger) };
  }
  if (!parseableEventTime(record.at)) return { ok: false, status: 'HOLD', wrote: false, reason: 'time', ledger };
  const applied = applyRecoveryRecord(ledger, record);
  if (!applied.ok) return { ok: false, status: 'HOLD', wrote: false, reason: applied.reason, ledger };
  if (applied.wrote && opts.write !== false) write(root, applied.ledger);
  return { ok: true, status: applied.replay ? 'REPLAY' : applied.duplicate ? 'DUPLICATE' : 'RECORDED',
    wrote: applied.wrote && opts.write !== false, replay: applied.replay, duplicate: applied.duplicate || false,
    counted: applied.counted, drift: applied.drift || false, ledger: applied.ledger, recovery: applied.recovery };
}
function recordFailure(root, event, opts = {}) {
  return recordRecoveryEvent(root, { ...(event || {}), kind: 'failure' }, opts);
}
function agentLedgerReport(ledger) {
  const failures = ledger?.failures || freshFailures();
  const recoveryEvents = Object.values(failures.events || {});
  const failureEvents = recoveryEvents.filter((event) => event?.kind === 'failure');
  const countedFailures = failureEvents.filter((event) => event.counted === true);
  const nonCountingFailures = failureEvents.filter((event) => event.counted !== true);
  return {
    schemaVersion: 1,
    kind: 'harness-lite-agent-record-report',
    unitCount: unitRows(ledger).length,
    recovery: recoverySummary(ledger),
    recoveryLedger: {
      eventCount: recoveryEvents.length,
      failureEventCount: failureEvents.length,
      countedFailureEventCount: countedFailures.length,
      nonCountingFailureEventCount: nonCountingFailures.length,
      driftEventCount: failureEvents.filter((event) => event.drift === true).length,
      problemCount: Object.keys(failures.problems || {}).length,
      leaseCount: Object.keys(failures.leases || {}).length,
      effectiveFailureCount: countedFailures.length,
    },
  };
}
function withAgentReport(result) {
  if (!result?.ledger) return result;
  const report = agentLedgerReport(result.ledger);
  return { ...result, report, recovery: result.recovery || report.recovery };
}
function recordAgentStatus(root, event, opts = {}) {
  return withAgentReport(recordEvent(root, event, opts));
}
function recordAgentObservation(root, event, opts = {}) {
  return recordAgentStatus(root, event, opts);
}
function recordAgentFailure(root, event, opts = {}) {
  return withAgentReport(recordFailure(root, event, opts));
}
function recordAgentRecovery(root, event, opts = {}) {
  return withAgentReport(recordRecoveryEvent(root, event, opts));
}
function normalizeScope(value) {
  const raw = cleanText(value)?.replaceAll('\\', '/').replace(/^\.\//, '').replace(/\/+$/, '') || null;
  if (!raw) return { raw, path: null, invalid: false };
  if (!raw.includes('*')) return { raw, path: raw, invalid: false };
  let base = null;
  if (raw.endsWith('/**')) base = raw.slice(0, -3);
  else if (raw.endsWith('/**/*')) base = raw.slice(0, -5);
  else if (raw.endsWith('/*')) base = raw.slice(0, -2);
  if (!base || base.includes('*')) return { raw, path: null, invalid: true };
  return { raw, path: base.replace(/\/+$/, ''), invalid: false, wildcard: true };
}
function overlappingScope(left, right) {
  const a = normalizeScope(left), b = normalizeScope(right);
  if (!a.raw || !b.raw) return false;
  if (a.invalid || b.invalid) return true;
  return a.path === b.path || a.path.startsWith(`${b.path}/`) || b.path.startsWith(`${a.path}/`);
}
function unitRows(ledger) {
  return Object.values(ledger?.workUnits || {}).filter((unit) => unit && typeof unit === 'object')
    .filter((unit) => declaredInLedger(ledger, unit.id))
    .sort((a, b) => String(a.id || '').localeCompare(String(b.id || '')));
}
function activeRows(ledger) {
  return unitRows(ledger).filter((unit) => unit.status === 'active');
}
function writeConflicts(ledger) {
  const active = activeRows(ledger), conflicts = [];
  for (let i = 0; i < active.length; i++) for (let j = i + 1; j < active.length; j++) {
    const left = active[i], right = active[j], overlap = [];
    for (const a of left.writeScope || []) for (const b of right.writeScope || []) if (overlappingScope(a, b)) overlap.push([a, b]);
    if (overlap.length) conflicts.push({ units: [left.id, right.id], overlap,
      action: 'integration-owner-or-split-or-serial' });
  }
  return conflicts;
}
function blockerRows(ledger, unit) {
  return (unit.dependencies || []).map((dep) => {
    const declared = declaredInLedger(ledger, dep), status = declared ? ledger?.workUnits?.[dep]?.status || UNKNOWN : UNKNOWN;
    return { id: dep, status, accepted: declared && status === 'accepted' };
  }).filter((dep) => !dep.accepted);
}
function runnableRows(ledger) {
  return unitRows(ledger).filter((unit) => !['active', 'reported_complete', 'partial', 'blocked', 'accepted'].includes(unit.status)
    && blockerRows(ledger, unit).length === 0);
}
function waitingRows(ledger) {
  return unitRows(ledger).map((unit) => ({ id: unit.id, blockers: blockerRows(ledger, unit) }))
    .filter((row) => row.blockers.length > 0);
}
function heartbeatSummary(ledger, now = new Date()) {
  const at = now instanceof Date ? now.getTime() : Date.parse(now);
  const due = activeRows(ledger).filter((unit) => {
    const base = firstEventTime(unit.heartbeatAt, unit.activeAt, unit.updatedAt);
    return base != null && Number.isFinite(at) && at - base >= HEARTBEAT_MS;
  }).map((unit) => unit.id);
  return { intervalMs: HEARTBEAT_MS, readOnly: true, mode: 'single-summary', due };
}
function summary(ledger, opts = {}) {
  const units = unitRows(ledger), heartbeat = heartbeatSummary(ledger, opts.now || new Date());
  return {
    schemaVersion: 1,
    kind: 'harness-lite-delegation-summary',
    state: ledger ? 'live' : UNKNOWN,
    concurrencyLimit: null,
    units: units.map((unit) => ({
      id: unit.id,
      status: unit.status || UNKNOWN,
      dependencies: unit.dependencies || [],
      writeScope: unit.writeScope || [],
      activityAt: unit.activityAt || null,
      activityKind: unit.activityKind || null,
      heartbeatAt: unit.heartbeatAt || null,
      progressAt: unit.progressAt || null,
      progressKind: unit.progressKind || null,
      evidenceRef: unit.status === 'accepted' ? unit.acceptanceEvidenceRef || null : unit.evidenceRef || null,
      reportedResult: unit.reportedResult || null,
      acceptedAt: unit.acceptedAt || null,
      channel: unit.channel || null,
      model: unit.model || null,
      modelFamily: unit.modelFamily || null,
      reasoning: unit.reasoning || null,
    })),
    active: activeRows(ledger).map((unit) => unit.id),
    runnable: runnableRows(ledger).map((unit) => unit.id),
    waiting: waitingRows(ledger),
    reported: units.filter((unit) => unit.status === 'reported_complete').map((unit) => unit.id),
    accepted: units.filter((unit) => unit.status === 'accepted').map((unit) => unit.id),
    blocked: units.filter((unit) => unit.status === 'blocked').map((unit) => unit.id),
    partial: units.filter((unit) => unit.status === 'partial').map((unit) => unit.id),
    conflicts: writeConflicts(ledger),
    heartbeat,
    recovery: recoverySummary(ledger),
    semanticProgress: units.filter((unit) => unit.progressAt && eventTime(unit.progressAt) != null && unit.progressKind && unit.evidenceRef)
      .map((unit) => ({ id: unit.id, progressAt: unit.progressAt, progressKind: unit.progressKind, evidenceRef: unit.evidenceRef })),
  };
}
function recoverySummary(ledger) {
  if (!ledger) return { state: UNKNOWN, status: UNKNOWN, tier: UNKNOWN, nextTier: UNKNOWN,
    failureCount: UNKNOWN, recoveryAttemptLimitDefault: DEFAULT_RECOVERY_ATTEMPT_LIMIT, recoveryAttemptLimits: [],
    solAttemptLimitDefault: DEFAULT_SOL_ATTEMPT_LIMIT, solAttemptLimits: [],
    active: [], blocked: [], drift: [], problems: [], leases: [] };
  const failures = ledger.failures || freshFailures();
  const problems = Object.values(failures.problems || {}).sort((a, b) => String(a.key).localeCompare(String(b.key)));
  const leases = Object.values(failures.leases || {}).sort((a, b) => String(a.leaseKey).localeCompare(String(b.leaseKey)));
  const active = leases.filter((lease) => lease.status === 'active');
  const blocked = leases.filter((lease) => lease.status === 'blocked');
  const drift = problems.filter((problem) => problem.drift).map((problem) => problem.stableWorkUnit);
  const legacy = leases.filter((lease) => ['terra', 'sol'].includes(lease.tier)
    && !problems.find((problem) => problem.leaseKey === lease.leaseKey && problem.policy === CURRENT_RECOVERY_POLICY));
  if (legacy.length) {
    return { state: 'live', status: 'blocked', tier: 'legacy', nextTier: 'UNKNOWN: legacy recovery lease requires explicit migration',
      failureCount: problems.reduce((sum, problem) => sum + problem.effectiveCount, 0),
      recoveryAttemptLimitDefault: DEFAULT_RECOVERY_ATTEMPT_LIMIT,
      recoveryAttemptLimits: legacy.map((lease) => `${lease.stableWorkUnit}:${lease.recoveryAttemptLimit || lease.solAttemptLimit || DEFAULT_RECOVERY_ATTEMPT_LIMIT}`),
      solAttemptLimitDefault: DEFAULT_SOL_ATTEMPT_LIMIT,
      solAttemptLimits: legacy.map((lease) => `${lease.stableWorkUnit}:${lease.solAttemptLimit || DEFAULT_SOL_ATTEMPT_LIMIT}`),
      active: [], blocked: [], drift, problems, leases: [], legacyLeases: legacy };
  }
  const activeTiers = [...new Set(active.map((lease) => lease.tier))].sort();
  const mixed = (blocked.length > 0 && active.length > 0) || activeTiers.length > 1;
  const tier = mixed ? 'mixed' : blocked.length ? 'exhausted' : activeTiers[0] || 'ordinary';
  const nextTier = tier === 'astra' ? 'Astra xhigh complete recovery'
    : tier === 'terra' ? 'Terra xhigh complete recovery'
    : tier === 'sol' ? 'Sol xhigh complete recovery'
      : tier === 'exhausted' ? 'blocked: user decision or new evidence/diagnosis'
        : tier === 'mixed' ? 'mixed: per-problem active and blocked recovery branches' : 'ordinary';
  return { state: 'live', status: mixed ? 'mixed' : blocked.length ? 'blocked' : active.length ? 'active' : 'ordinary',
    tier, nextTier, failureCount: problems.reduce((sum, problem) => sum + problem.effectiveCount, 0),
    recoveryAttemptLimitDefault: DEFAULT_RECOVERY_ATTEMPT_LIMIT,
    recoveryAttemptLimits: leases.map((lease) => `${lease.stableWorkUnit}:${lease.recoveryAttemptLimit || lease.solAttemptLimit || DEFAULT_RECOVERY_ATTEMPT_LIMIT}`),
    solAttemptLimitDefault: DEFAULT_SOL_ATTEMPT_LIMIT,
    solAttemptLimits: leases.map((lease) => `${lease.stableWorkUnit}:${lease.solAttemptLimit || DEFAULT_SOL_ATTEMPT_LIMIT}`),
    active: active.map((lease) => lease.stableWorkUnit), blocked: blocked.map((lease) => lease.stableWorkUnit),
    drift, problems, leases };
}
function interventionAdvice(observations = []) {
  const values = [].concat(observations || []).map(cleanText).filter(Boolean);
  const direct = values.filter((item) => INTERVENTION_REASONS.has(item));
  const passive = values.filter((item) => PASSIVE_OBSERVATIONS.has(item));
  return { intervene: direct.length > 0, reasons: direct, passive,
    allowedActions: direct.length ? ['message', 'interrupt', 'takeover'] : [] };
}

module.exports = {
  SCHEMA_VERSION,
  KIND,
  RELATIVE_PATH,
  UNKNOWN,
  HEARTBEAT_MS,
  STATUSES,
  PROGRESS_KINDS,
  AGENT_FIELDS,
  FAILURE_CATEGORIES,
  NON_COUNTING_FAILURE_REASONS,
  DEFAULT_SOL_ATTEMPT_LIMIT,
  SOL_ATTEMPT_LIMIT_MIN,
  SOL_ATTEMPT_LIMIT_MAX,
  DEFAULT_RECOVERY_ATTEMPT_LIMIT,
  RECOVERY_ATTEMPT_LIMIT_MIN,
  RECOVERY_ATTEMPT_LIMIT_MAX,
  ledgerPath,
  projectIdentity,
  binding,
  freshLedger,
  freshFailures,
  read,
  recordEvent,
  recordAgentStatus,
  recordAgentObservation,
  recordAgentFailure,
  recordAgentRecovery,
  recordFailure,
  recordRecoveryEvent,
  agentLedgerReport,
  recoveryIdentity,
  recoverySummary,
  dependencyState,
  summary,
  heartbeatSummary,
  writeConflicts,
  interventionAdvice,
};
