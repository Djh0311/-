'use strict';

const crypto = require('crypto');
const UNKNOWN = 'UNKNOWN';
const INTENTS = Object.freeze([
  'leaf-definition', 'route-clarification', 'pre-dispatch', 'agent-active',
  'agent-reported', 'problem-recovery', 'leaf-closeout', 'legacy-fact', 'push-attempt',
]);
const INTENT_SET = new Set(INTENTS);

// Compatibility only: select() now synthesizes one decision instead of joining these.
const FRAGMENTS = Object.freeze({
  'leaf-definition': '先把用户最后要拿到的结果和完整成功标准说清楚。',
  'route-clarification': '先找出会改变路线的那个关键假设，用最短证据验证。',
  'pre-dispatch': '先确认这个 unit 必须交付什么，再把完整最小任务包交给 writer。',
  'agent-active': '已有任务在进行；没有直接异常证据就不打断，按 300000ms 只读观察一次。',
  'agent-reported': '先按完成标准读回实际结果；自报完成还不是接受。',
  'problem-recovery': '证据否定了实质路线时先换路；同一问题达到有效失败上限后，按租约进入 Astra 有界恢复。',
  'leaf-closeout': '逐条对照用户结果和完成标准，把已证、未证和未知分开。',
  'legacy-fact': '旧载体只提供事实，不替代当前设计；取会改变路线的一条事实即可。',
  'push-attempt': '只对这一次真实 push 目标核对既有 gate 和授权。',
});
const DECISION_PRIORITY = Object.freeze({
  'push-attempt': 100, 'leaf-definition': 90, 'route-clarification': 80,
  'problem-recovery': 70, 'agent-reported': 60, 'pre-dispatch': 50,
  'leaf-closeout': 40, 'agent-active': 30, 'legacy-fact': 20,
});
const EVENT_ORDER = Object.freeze(INTENTS.reduce((out, event, index) => { out[event] = index; return out; }, {}));

function unknownStandards(chain) {
  const value = chain?.leaf?.completionStandards;
  return !Array.isArray(value) || value.length === 0 || value.some((item) => typeof item !== 'string' || !item.trim() || item === UNKNOWN);
}

function stateEventsInternal(chain, delegationView) {
  let summary = {};
  try { summary = delegationView && typeof delegationView === 'object' && delegationView.summary && typeof delegationView.summary === 'object'
    ? delegationView.summary : {}; } catch { summary = {}; }
  const events = [];
  if (chain?.leaf && unknownStandards(chain)) events.push('leaf-definition');
  const leafRunnable = (Array.isArray(chain?.leaf?.workUnits) ? chain.leaf.workUnits : []).some((unit) => {
    if (!unit || typeof unit !== 'object' || Array.isArray(unit)) return false;
    const standards = unit.completionStandards;
    const ready = Array.isArray(standards) && standards.length > 0
      && !standards.some((item) => typeof item !== 'string' || !item.trim() || item === UNKNOWN);
    return ready && Array.isArray(unit.dependencies) && unit.dependencies.length === 0;
  });
  const runnable = safeArrayField(summary, 'runnable'), active = safeArrayField(summary, 'active'), reported = safeArrayField(summary, 'reported');
  let live = false;
  try { live = !!delegationView?.state?.live; } catch { live = false; }
  if (runnable.length > 0 || (!live && leafRunnable)) events.push('pre-dispatch');
  if (active.length > 0) events.push('agent-active');
  if (reported.length > 0) events.push('agent-reported');
  let recovery = {};
  try { recovery = summary.recovery && typeof summary.recovery === 'object' ? summary.recovery : {}; } catch { recovery = {}; }
  if (safeArrayField(recovery, 'problems').length || safeArrayField(recovery, 'leases').length || safeArrayField(recovery, 'drift').length
    || (() => { try { return Number.isFinite(recovery.failureCount) && recovery.failureCount > 0; } catch { return false; } })()) events.push('problem-recovery');
  const required = (Array.isArray(chain?.leaf?.workUnits) ? chain.leaf.workUnits : []).map((unit) => unit?.id).filter(Boolean);
  const accepted = new Set(safeArrayField(summary, 'accepted').filter((id) => typeof id === 'string'));
  if (chain?.leaf && required.length > 0 && required.every((id) => accepted.has(id))) events.push('leaf-closeout');
  return events;
}
function stateEvents(chain, delegationView) {
  try { return stateEventsInternal(chain, delegationView); } catch { return []; }
}

function normalizeIntent(intent) {
  if (intent === undefined || intent === null || intent === '') return null;
  if (typeof intent !== 'string') return null;
  const value = String(intent).trim();
  if (!INTENT_SET.has(value)) throw new Error(`unknown guidance intent: ${value}`);
  return value;
}
function normalizeEvents(events) {
  if (events === undefined || events === null) return [];
  if (!Array.isArray(events) && typeof events !== 'string') return [];
  const values = Array.isArray(events) ? events : [events];
  return [...new Set(values.filter((event) => typeof event === 'string').map((event) => normalizeIntent(event)).filter(Boolean))];
}
function safeText(value) { return typeof value === 'string' && value.trim() ? value : UNKNOWN; }
function safeList(value) {
  if (!Array.isArray(value) || value.length === 0) return [UNKNOWN];
  const out = [];
  try {
    for (let index = 0; index < value.length; index += 1) out.push(typeof value[index] === 'string' && value[index].trim() ? value[index] : UNKNOWN);
  } catch { return [UNKNOWN]; }
  return out.length ? out : [UNKNOWN];
}
function safeSummary(delegationView) {
  try {
    return delegationView && typeof delegationView === 'object' && delegationView.summary && typeof delegationView.summary === 'object'
      ? delegationView.summary : {};
  } catch { return {}; }
}
function safeArrayField(value, key) {
  try { return Array.isArray(value?.[key]) ? value[key] : []; } catch { return []; }
}
function pushGateFrom(opts) {
  let gate = null;
  try { gate = opts && typeof opts === 'object' ? (opts.pushGate || opts.gate) : null; } catch { return null; }
  try {
    if (!gate || typeof gate !== 'object' || Array.isArray(gate)) return null;
    if (!['action', 'target', 'boundary', 'risk', 'userDecision'].every((key) => typeof gate[key] === 'string' && gate[key].trim())) return null;
    return gate;
  } catch { return null; }
}

function completionCarrier(chain, opts = {}) {
  if (!opts || typeof opts !== 'object') opts = {};
  let leaf = {};
  try { leaf = chain && typeof chain === 'object' && chain.leaf && typeof chain.leaf === 'object' ? chain.leaf : {}; } catch { leaf = {}; }
  let goal = UNKNOWN, standards = [UNKNOWN], authorityDesign = [UNKNOWN], facts = [UNKNOWN];
  try {
    goal = safeText(leaf.goal); standards = safeList(leaf.completionStandards);
    authorityDesign = safeList(leaf.authorityDesign); facts = safeList(leaf.facts);
  } catch { goal = UNKNOWN; standards = [UNKNOWN]; authorityDesign = [UNKNOWN]; facts = [UNKNOWN]; }
  const complete = goal !== UNKNOWN && standards.length > 0
    && !standards.some((item) => typeof item !== 'string' || !item.trim() || item === UNKNOWN);
  const result = {
    complete, truncated: false, carrier: 'inline', source: 'current-leaf', goal,
    completionStandards: standards, authorityDesign, facts,
    sentinel: {
      start: standards[0] || null, end: standards[standards.length - 1] || null, count: standards.length,
      authority: { start: authorityDesign[0] || null, end: authorityDesign[authorityDesign.length - 1] || null, count: authorityDesign.length },
      facts: { start: facts[0] || null, end: facts[facts.length - 1] || null, count: facts.length },
    },
  };
  let requestedMax = null;
  try { requestedMax = opts.maxChars; } catch { requestedMax = null; }
  const maxChars = Number.isInteger(requestedMax) && requestedMax > 0 ? requestedMax : null;
  let serialized = '';
  try { serialized = JSON.stringify(result); } catch { result.complete = false; result.truncated = true; result.carrier = 'external-required'; serialized = ''; }
  result.digest = `sha256:${crypto.createHash('sha256').update(serialized || 'UNKNOWN').digest('hex')}`;
  // Include digest and the size field itself in the reported carrier size.  A
  // short fixed-point loop avoids an off-by-one at digit-boundary lengths.
  result.serializedChars = 0;
  for (let index = 0; index < 4; index += 1) {
    const size = JSON.stringify(result).length;
    if (size === result.serializedChars) break;
    result.serializedChars = size;
  }
  if (maxChars && result.serializedChars > maxChars) {
    let requestedRef = null;
    try { requestedRef = opts.ref; } catch { requestedRef = null; }
    result.complete = false; result.truncated = true; result.carrier = 'external-required'; result.ref = safeText(requestedRef) === UNKNOWN ? null : safeText(requestedRef);
    for (let index = 0; index < 4; index += 1) {
      const size = JSON.stringify(result).length;
      if (size === result.serializedChars) break;
      result.serializedChars = size;
    }
  }
  return result;
}

function eventFacts(event, delegationView) {
  const summary = safeSummary(delegationView);
  const runnable = safeArrayField(summary, 'runnable'), active = safeArrayField(summary, 'active');
  const reported = safeArrayField(summary, 'reported'), accepted = safeArrayField(summary, 'accepted');
  if (event === 'pre-dispatch' && runnable.length) return [`runnable=${runnable.filter((id) => typeof id === 'string').join(',')}`];
  if (event === 'agent-active' && active.length) return [`active=${active.filter((id) => typeof id === 'string').join(',')}`];
  if (event === 'agent-reported' && reported.length) return [`reported=${reported.filter((id) => typeof id === 'string').join(',')}`];
  try { if (event === 'problem-recovery' && Number.isFinite(summary.recovery?.failureCount)) return [`有效问题次数=${summary.recovery.failureCount}`]; } catch { /* malformed recovery is irrelevant */ }
  if (event === 'leaf-closeout' && accepted.length) return [`accepted=${accepted.filter((id) => typeof id === 'string').join(',')}`];
  return [];
}

function declaredUnitRows(chain) {
  try {
    return Array.isArray(chain?.leaf?.workUnits) ? chain.leaf.workUnits.filter((unit) => unit && typeof unit === 'object' && typeof unit.id === 'string') : [];
  } catch { return []; }
}

function reportedDecision(chain, delegationView) {
  const summary = safeSummary(delegationView);
  const reported = safeArrayField(summary, 'reported').filter((id) => typeof id === 'string' && id.trim());
  if (!reported.length) {
    return ['先对照最近的实际结果和证据', '当前没有可核对的报告对象；哪个结果需要直接验收？', '读回真实结果和证据；没有对象就不虚构暂停目标。'];
  }
  const rows = declaredUnitRows(chain);
  const byId = new Map(rows.map((unit) => [unit.id, unit]));
  const dependents = rows.filter((unit) => Array.isArray(unit.dependencies)
    && unit.dependencies.some((dependency) => reported.includes(dependency))
    && !safeArrayField(summary, 'accepted').includes(unit.id));
  const reportedText = reported.join('、');
  const dependentText = dependents.map((unit) => unit.id).join('、');
  if (dependentText) {
    return [
      `先验收已报告的 ${reportedText}，再决定下游 ${dependentText}`,
      `${reportedText} 尚未被主管验收；它影响的下游是 ${dependentText}，证据是否足够？`,
      `先读回 ${reportedText} 的直接结果和 evidenceRef；证据不足就只保持 ${dependentText} 未解锁，不扩大全局。`,
    ];
  }
  const known = reported.filter((id) => byId.has(id)).join('、') || reportedText;
  return [
    `先验收已报告的 ${known}`,
    `${known} 的实际结果和证据是否满足它自己的完成标准？`,
    `逐项读回 ${known} 的结果和 evidenceRef；通过后才可接受，不把自报当作完成。`,
  ];
}

function decisionFor(event, chain, delegationView, opts = {}) {
  const carrier = completionCarrier(chain, opts), known = carrier.complete;
  let choices = {
    'leaf-definition': ['先把用户要得到的结果和成功标准说清楚', '用户最终要看到什么，而且每一条必需完成标准都写全了吗？', '补齐目标、全部完成标准和边界，再决定路线。'],
    'route-clarification': ['先验证会改变路线的关键假设', '现在最不确定、但一旦错了就会改变结果的事实是什么？', '用一个最短、可复核的直接证据验证它；能直接查证就不问用户，只有不可替代的用户选择才问。'],
    'pre-dispatch': ['先保证 writer 拿到能交付结果的最小完整任务包', '这个 unit 必须证明什么结果，当前任务包是否完整？', '核对真实工具面和依赖，然后只派发完整任务包；只派发或只记录不等于用户结果完成，结果未出现就保持 complete=false、productResult=incomplete。'],
    'agent-active': ['先观察正在运行的任务，不因等待本身改变路线', '有没有直接证据表明任务停滞、跑偏或越界？', '没有就等下一个 300000ms 只读观察窗口；有证据再处理。'],
    'agent-reported': ['先对照报告和用户结果', '报告对象是否有直接结果和证据？', '先读回报告对象；证据不足就保持依赖它的下游未解锁，不虚构暂停目标。'],
    'problem-recovery': ['换掉被否定路线', '当前问题是否仍未修复，且恢复租约是否仍在上限内？', '只修当前问题；未修好 complete=false、productResult=incomplete；不扩大全局。'],
    'leaf-closeout': ['先确认用户要的产品结果是否真的全部出现', '每一条完成标准都有直接证据，还是仍有未知？派发、读回或测试绿都不等于用户结果；结果未出现时 complete=false、productResult=incomplete。', '逐条核验导出结果和完成标准；测试绿不等于用户结果；结果未出现时保持未完成，先补直接证据（complete=false、productResult=incomplete）。'],
    'legacy-fact': ['先从旧载体提取会改变当前路线的事实', '这条旧事实能改变什么判断，而当前设计仍以什么为准？', '记录相关事实，回到当前设计和用户结果继续判断。'],
    'push-attempt': ['先确认这一次 push 的精确目标和授权', '目标、runtime identity 和用户授权是否都准确匹配这一次动作？', '把精确目标交给既有 push gate；未命中真实 gate 不增加确认。'],
  }[event] || ['先回到用户要得到的结果', '当前最关键的可验证判断是什么？', '做最短直接证据检查。'];
  if (event === 'agent-reported') choices = reportedDecision(chain, delegationView);
  const stateFacts = eventFacts(event, delegationView);
  if (event === 'leaf-definition' || event === 'pre-dispatch' || event === 'leaf-closeout') stateFacts.unshift(`完成载体=${known ? '完整' : 'UNKNOWN'}`);
  const gate = event === 'push-attempt' ? pushGateFrom(opts) : null;
  const validGate = !!gate;
  const hardBoundaries = validGate ? [gate.boundary.trim()] : [];
  const result = { focus: choices[0], decisionQuestion: choices[1], nextAction: choices[2], stateFacts, hardBoundaries, completionCarrier: carrier };
  if (validGate) result.pushGate = {
    action: gate.action.trim(), target: gate.target.trim(), boundary: gate.boundary.trim(),
    risk: gate.risk.trim(), userDecision: gate.userDecision.trim(),
  };
  // A real push gate must carry its exact target into the primary decision,
  // rather than leaving the model to infer it from a secondary metadata field.
  // Keep the scope local to this action so an unrelated safe path is not
  // turned into a project-wide pause or confirmation request.
  if (validGate && event === 'push-attempt') {
    const target = result.pushGate.target;
    result.focus = `只核对这一次 push 的精确目标：${target} 和授权`;
    result.decisionQuestion = `这一次 push 的目标 ${target}、runtime identity 和用户授权是否都准确匹配？`;
    result.nextAction = `只把这一次 ${target} 交给既有 push gate；只针对该目标，不暂停全局；未命中真实 gate 不增加确认。`;
  }
  return result;
}

function select(chain, delegationView, opts = {}) {
  if (!opts || typeof opts !== 'object') opts = {};
  let intent = null, requested = [], observed = [], rawIntent = null, rawEvents = null;
  try { rawIntent = opts.intent; } catch { rawIntent = null; }
  try { intent = normalizeIntent(rawIntent); } catch (error) { if (typeof rawIntent === 'string') throw error; }
  try { rawEvents = opts.events; } catch { rawEvents = null; }
  try { requested = normalizeEvents(rawEvents); } catch (error) { if (typeof rawEvents === 'string' || (Array.isArray(rawEvents) && rawEvents.some((event) => typeof event === 'string'))) throw error; }
  try { observed = stateEvents(chain, delegationView); } catch { observed = []; }
  const gateEvent = pushGateFrom(opts) ? 'push-attempt' : null;
  const all = [...new Set([...(intent ? [intent] : []), ...(gateEvent ? [gateEvent] : []), ...requested, ...observed])];
  const events = all.sort((left, right) => {
    if (intent && left === intent) return -1;
    if (intent && right === intent) return 1;
    return EVENT_ORDER[left] - EVENT_ORDER[right];
  });
  const decisionEvent = intent || gateEvent || [...events].sort((left, right) => DECISION_PRIORITY[right] - DECISION_PRIORITY[left])[0] || null;
  const decision = decisionEvent ? decisionFor(decisionEvent, chain, delegationView, opts) : {
    focus: '先回到用户要得到的结果', decisionQuestion: '当前最关键的可验证判断是什么？', nextAction: '做最短直接证据检查。',
    stateFacts: [], hardBoundaries: [], completionCarrier: completionCarrier(chain, opts),
  };
  const text = `当前重点：${decision.focus}\n现在要回答：${decision.decisionQuestion}\n下一步：${decision.nextAction}`
    + (decisionEvent === 'agent-active' ? '（300000ms 只读观察）' : '')
    + (decisionEvent === 'problem-recovery' ? '（按问题租约进行 Astra 有界恢复）' : '')
    + (decision.pushGate ? `\n拦截说明：动作=${decision.pushGate.action}；目标=${decision.pushGate.target}；边界=${decision.pushGate.boundary}；风险=${decision.pushGate.risk}；现在请用户决定=${decision.pushGate.userDecision}` : '');
  return {
    schemaVersion: 1, kind: 'harness-lite-event-guidance', ...(intent ? { intent } : {}), events, decisionEvent,
    decision,
    focus: decision.focus, decisionQuestion: decision.decisionQuestion, nextAction: decision.nextAction,
    stateFacts: decision.stateFacts, hardBoundaries: decision.hardBoundaries, completionCarrier: decision.completionCarrier,
    fragments: events.map((event) => ({ event, text: FRAGMENTS[event] })), text,
  };
}

module.exports = { UNKNOWN, INTENTS, FRAGMENTS, DECISION_PRIORITY, normalizeIntent, stateEvents, completionCarrier, decisionFor, select };
