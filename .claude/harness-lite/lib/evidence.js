'use strict';

const EVENTS = ['SessionStart', 'UserPromptSubmit', 'Stop', 'PreToolUse'];
const HOST_EVENT = { SessionStart: 'sessionStart', UserPromptSubmit: 'userPromptSubmit', Stop: 'stop', PreToolUse: 'preToolUse' };

function sameHook(before, after) {
  return before && after && before.key === after.key && before.eventName === after.eventName
    && before.currentHash && before.currentHash === after.currentHash && before.enabled === true && after.enabled === true;
}

function hookSnapshot(value = {}) {
  return {
    connectionId: value.connectionId || null,
    cwdFingerprint: value.cwdFingerprint || null,
    hooks: (value.hooks || []).map((item) => ({ eventName: item.eventName || null, key: item.key || null,
      currentHash: item.currentHash || null, enabled: item.enabled === true, trustStatus: item.trustStatus || null,
      isManaged: item.isManaged === true, source: item.source || null })),
  };
}
function runs(values = []) {
  return values.map((item) => ({ threadId: item.threadId || null, turnId: item.turnId || null,
    run: { id: item.run?.id || null, eventName: item.run?.eventName || null, status: item.run?.status || null } }));
}
function receipts(values = []) {
  return values.map((item) => ({ event: item.event || null, runId: item.runId || null, decision: item.decision || null,
    generation: Number.isInteger(item.generation) ? item.generation : null, digestPrefix: item.digestPrefix || null,
    errorCode: item.errorCode || null }));
}

function build(input = {}) {
  const before = input.hooksBefore || {}, after = input.hooksAfter || {};
  const sameSurface = !!before.connectionId && before.connectionId === after.connectionId
    && before.connectionId === input.binding?.connectionId && !!before.cwdFingerprint
    && before.cwdFingerprint === after.cwdFingerprint && before.cwdFingerprint === input.projectRootFingerprint;
  const configuredByEvent = {}, observed = {};
  let ambiguous = false, missing = !sameSurface;

  for (const event of EVENTS) {
    const eventName = HOST_EVENT[event];
    const left = (before.hooks || []).filter((item) => item.eventName === eventName);
    const right = (after.hooks || []).filter((item) => item.eventName === eventName);
    const stable = left.length === 1 && right.length === 1 && sameHook(left[0], right[0]);
    const trust = stable && (input.profile === 'managed'
      ? left[0].isManaged === true && left[0].trustStatus === 'managed' && left[0].source === 'system'
      : left[0].isManaged !== true && left[0].trustStatus === 'trusted' && left[0].source === 'project');
    configuredByEvent[event] = !!trust;

    const started = (input.started || []).filter((item) => item.run?.eventName === eventName);
    const completed = (input.completed || []).filter((item) => item.run?.eventName === eventName);
    if (started.length > 1 || completed.length > 1) ambiguous = true;
    const start = started[0], finish = completed[0];
    const receipt = finish && (input.receipts || []).filter((item) => item.event === event && item.runId === finish.run?.id
      && item.decision === 'executed' && Number.isInteger(item.generation) && /^sha256:[0-9a-f]{64}$/.test(input.identities?.projectPackageDigest || '')
      && item.digestPrefix === input.identities.projectPackageDigest.slice(7, 19));
    if (!trust || started.length !== 1 || completed.length !== 1 || !finish || start.run?.id !== finish.run?.id
      || start.threadId !== finish.threadId || start.turnId !== finish.turnId
      || finish.run?.status !== 'completed' || receipt?.length !== 1) missing = true;
    if ((receipt || []).length > 1) ambiguous = true;
    observed[event] = !!trust && input.proofType !== 'offline' && input.hostKind !== 'synthetic'
      && started.length === 1 && completed.length === 1 && start.run?.id === finish?.run?.id
      && start.threadId === finish?.threadId && start.turnId === finish?.turnId
      && finish?.run?.status === 'completed' && receipt?.length === 1;
  }

  const configured = sameSurface && EVENTS.every((event) => configuredByEvent[event]);
  const joinVerdict = ambiguous ? 'ambiguous' : missing ? 'missing' : 'exact';
  if (joinVerdict !== 'exact') for (const event of EVENTS) observed[event] = false;
  const desktopAttributed = input.hostKind === 'desktop' && input.proofType !== 'offline'
    && input.binding?.connectionId === before.connectionId && Number.isInteger(input.binding?.desktopProcessId)
    && Number.isInteger(input.binding?.appServerProcessId) && input.binding?.existingConnection === true;

  return {
    schemaVersion: 1,
    profile: input.profile === 'managed' ? 'managed' : 'project',
    hostKind: ['desktop', 'cli', 'unknown-live', 'synthetic'].includes(input.hostKind) ? input.hostKind : 'unknown-live',
    proofType: input.proofType === 'offline' ? 'offline' : 'protocol-direct',
    transport: input.transport === 'stdio' ? 'stdio' : null,
    fingerprints: {
      codeHome: input.codeHomeFingerprint || null,
      projectRoot: input.projectRootFingerprint || null,
    },
    identities: {
      projectPackageDigest: input.identities?.projectPackageDigest || null,
      gatewayDigest: input.identities?.gatewayDigest || null,
      allowlistDigest: input.identities?.allowlistDigest || null,
    },
    binding: {
      connectionId: input.binding?.connectionId || null,
      desktopProcessId: Number.isInteger(input.binding?.desktopProcessId) ? input.binding.desktopProcessId : null,
      appServerProcessId: Number.isInteger(input.binding?.appServerProcessId) ? input.binding.appServerProcessId : null,
      existingConnection: input.binding?.existingConnection === true,
    },
    hookSnapshots: { before: hookSnapshot(before), after: hookSnapshot(after) },
    runs: { started: runs(input.started), completed: runs(input.completed) },
    receipts: receipts(input.receipts),
    joinVerdict,
    claims: {
      configured,
      policyTrusted: configured && input.profile === 'managed',
      desktopAttributed,
      observed,
    },
  };
}

module.exports = { EVENTS, HOST_EVENT, build };
