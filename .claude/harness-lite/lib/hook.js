'use strict';
const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');
const io = require('./io.js');
const tree = require('./tree.js');
const work = require('./work.js');

const eventName = (input) => input?.hook_event_name || '';
const cleanId = (value) => String(value || '-').replace(/[^A-Za-z0-9._-]/g, '_').slice(0, 120);
const turnDir = (root) => path.join(tree.hdir(root), 'usage', '.turn');
const turnFile = (root, input) => path.join(turnDir(root), `${cleanId(input.session_id)}--${cleanId(input.turn_id)}.json`);
function readTurn(root, input) { return io.json(turnFile(root, input), {}); }
function writeTurn(root, input, state) { io.atomic(turnFile(root, input), `${JSON.stringify(state, null, 2)}\n`); }
function definitionDigest(root) {
  try { return require('./install.js').definition(root).digest; } catch { return null; }
}
function packageDigest(root) {
  return io.json(path.join(root, '.claude', 'harness-lite', 'ownership.json'), {})?.packageDigest || null;
}
function observe(root, input) {
  const event = eventName(input); if (!event) return;
  const file = path.join(tree.hdir(root), 'usage', '.observed.json'), current = io.json(file, { events: {} });
  current.source = 'codex-host-hook';
  current.events[event] = { at: new Date().toISOString(), session: cleanId(input.session_id), turn: input.turn_id ? cleanId(input.turn_id) : null,
    definitionDigest: definitionDigest(root), packageDigest: packageDigest(root) };
  io.atomic(file, `${JSON.stringify(current, null, 2)}\n`);
}
function sessionStart(root, input) {
  observe(root, input);
  const status = work.status(root), chain = status.chain, context = [status.text,
    `Scope：允许 ${chain.allowed.join('、') || '未登记'}；禁止 ${chain.forbidden.join('、') || '未登记'}`,
    `范围来源：${chain.leaf?.sourceReceipt ? `${chain.leaf.sourceReceipt}（${work.receipt(root, chain.leaf.sourceReceipt) ? 'host receipt 已记录' : 'provenance 未核验'}）` : 'current leaf 未登记来源收据'}；只报告，不作工具门禁。`].join('\n');
  return { hookSpecificOutput: { hookEventName: 'SessionStart', additionalContext: context.slice(0, 4000) } };
}
const pushFile = (root) => path.join(turnDir(root), '.push.json');
const readPush = (root) => io.json(pushFile(root), {});
const writePush = (root, value) => io.atomic(pushFile(root), `${JSON.stringify(value, null, 2)}\n`);
function userPrompt(root, input) {
  const prompt = typeof input.prompt === 'string' ? input.prompt : '';
  const digest = io.sha(prompt), prior = readTurn(root, input);
  if (prior.continuations?.includes(digest) || input.agent_id || input.agent_type) return { kind: 'internal', context: '' };
  const receipt = { receiptId: `u-${io.sha(`${root}\0${input.session_id}\0${input.turn_id}\0${prompt}`).slice(0, 20)}`,
    promptDigest: `sha256:${digest}`, project: root, thread: input.session_id || null, turn: input.turn_id || null };
  const state = { ...prior, startedAt: new Date().toISOString(), receipt, baseline: work.snapshot(root),
    stage: tree.readChain(root).stage?.name || prior.stage || null, events: [...new Set([...(prior.events || []), 'UserPromptSubmit'])] };
  const push = readPush(root);
  let pushDirty = false;
  if (push.assertion && push.assertion.confirmationTurn !== (input.turn_id || null)) { delete push.assertion; delete push.pending; pushDirty = true; }
  if (push.pending && !push.pending.confirmationReceiptId && push.pending.session === (input.session_id || null)
    && push.pending.turn !== (input.turn_id || null)) {
    push.pending.confirmationTurn = input.turn_id || null; push.pending.confirmationReceiptId = receipt.receiptId; pushDirty = true;
  }
  if (pushDirty) writePush(root, push);
  writeTurn(root, input, state); observe(root, input);
  const chain = tree.readChain(root);
  return { kind: 'receipt', receipt, context: `本轮用户消息已记录为来源收据 ${receipt.receiptId}；当前 ${chain.leaf?.title || '无 current leaf'}。清晰的新目标或边界由模型直接更新最小工作状态，用户无需维护 Harness；非 push 偏差只报告。` };
}
function shellSegments(command) {
  const out = []; let part = '', quote = null, escaped = false;
  for (let i = 0; i < String(command).length; i++) {
    const c = String(command)[i], n = String(command)[i + 1];
    if (escaped) { part += c; escaped = false; continue; }
    if (c === '\\' && quote !== "'") { part += c; escaped = true; continue; }
    if (quote) { part += c; if (c === quote) quote = null; continue; }
    if (c === "'" || c === '"') { quote = c; part += c; continue; }
    if (c === '#') { while (i < String(command).length && String(command)[i] !== '\n') i++; if (part.trim()) out.push(part.trim()); part = ''; continue; }
    if (c === ';' || c === '\n' || c === '|' || c === '&') {
      if (part.trim()) out.push(part.trim()); part = ''; if ((c === '|' || c === '&') && n === c) i++; continue;
    }
    part += c;
  }
  if (part.trim()) out.push(part.trim()); return out;
}
function tokens(segment) {
  const out = []; let value = '', quote = null, escaped = false;
  for (const c of segment.trim()) {
    if (escaped) { value += c; escaped = false; continue; }
    if (c === '\\' && quote !== "'") { escaped = true; continue; }
    if (quote) { if (c === quote) quote = null; else value += c; continue; }
    if (c === "'" || c === '"') { quote = c; continue; }
    if (/\s/.test(c)) { if (value) { out.push(value); value = ''; } } else value += c;
  }
  if (value) out.push(value); return quote ? [] : out;
}
function classifyPush(command) {
  let changedDirectory = false;
  for (const segment of shellSegments(command)) {
    const argv = tokens(segment); let at = 0;
    if (argv[0] === 'cd') { changedDirectory = true; continue; }
    const assignment = (value) => /^[A-Za-z_][A-Za-z0-9_]*=/.test(value || ''); let unsafeWrapper = false, prefixInexact = false;
    while (assignment(argv[at])) at++;
    while (true) {
      const base = path.basename(argv[at] || '');
      if (base === 'command' || base === 'exec') { at++; if (argv[at] === '--') at++; while (assignment(argv[at])) at++; continue; }
      if (base === 'sudo') { unsafeWrapper = true; at++; continue; }
      if (base === 'env') {
        at++; while (assignment(argv[at])) at++;
        while ((argv[at] || '').startsWith('-')) { const option = argv[at++]; prefixInexact = true; if (/^(?:-u|--unset|-C|--chdir|-S|--split-string)$/.test(option)) at++; while (assignment(argv[at])) at++; }
        if (argv[at] === '--') at++; continue;
      }
      break;
    }
    if (/^(?:sh|bash|zsh|eval)$/.test(path.basename(argv[at] || '')) && /\bgit\b[\s\S]*\bpush\b/i.test(argv.slice(at + 1).join(' '))) {
      return { command: segment, remote: null, refspec: null, exact: false };
    }
    if (!/(?:^|\/)git$/.test(argv[at] || '')) {
      if (/\$\([^)]*\bgit\b[^)]*\bpush\b|`[^`]*\bgit\b[^`]*\bpush\b/i.test(segment)) return { command: segment, remote: null, refspec: null, exact: false };
      continue;
    }
    if (argv[at + 1] !== 'push') {
      if (argv.slice(at + 1).includes('push')) return { command: segment, remote: null, refspec: null, exact: false };
      continue;
    }
    const rest = argv.slice(at + 2), values = rest.filter((x) => !x.startsWith('-'));
    const canonical = /^\+?HEAD:[^\s:]+$/.test(values[1] || '');
    return { command: segment, remote: values[0] || null, refspec: values[1] || null, canonical,
      exact: !unsafeWrapper && !prefixInexact && !changedDirectory && !rest.includes('--no-verify') && values.length === 2 && canonical };
  }
  return null;
}
function repoFacts(root) {
  const top = (work.git(root, ['rev-parse', '--show-toplevel']) || '').trim() || path.resolve(root);
  const head = (work.git(root, ['rev-parse', 'HEAD']) || '').trim() || null;
  return { repo: top, head };
}
const projectRoot = (cwd) => repoFacts(cwd).repo;
const deny = (reason) => ({ hookSpecificOutput: { hookEventName: 'PreToolUse', permissionDecision: 'deny', permissionDecisionReason: reason } });
const allow = () => ({ hookSpecificOutput: { hookEventName: 'PreToolUse', permissionDecision: 'allow' } });
const BINDING_KEYS = ['project', 'head', 'remote', 'pushUrl', 'destinationRef', 'commandDigest', 'session', 'agentId', 'agentType'];
function pushBinding(root, input, parsed) {
  const facts = repoFacts(root);
  const pushUrl = (work.git(facts.repo, ['remote', 'get-url', '--push', parsed.remote]) || '').trim() || null;
  const destination = parsed.refspec.replace(/^\+/, '').split(':').pop();
  const binding = { project: facts.repo, head: facts.head, remote: parsed.remote, pushUrl,
    refspec: parsed.refspec, destinationRef: destination.startsWith('refs/') ? destination : `refs/heads/${destination}`,
    commandDigest: `sha256:${io.sha(parsed.command)}`, session: input.session_id || null, turn: input.turn_id || null,
    agentId: input.agent_id || null, agentType: input.agent_type || null };
  binding.pendingId = `p-${io.sha(JSON.stringify(BINDING_KEYS.map((key) => [key, binding[key]]))).slice(0, 20)}`;
  return binding;
}
const sameBinding = (value, binding) => !!value && BINDING_KEYS.every((key) => value[key] === binding[key]);
function pushAssert(root, claim) {
  const keys = Object.keys(claim || {}).sort();
  if (keys.join(',') !== 'confirmationTurn,pendingId,sessionId,userReceiptId') return { ok: false, reason: 'push-assert 只接受固定字段 pendingId/userReceiptId/sessionId/confirmationTurn' };
  const state = readPush(root), pending = state.pending;
  if (!pending || state.assertion) return { ok: false, reason: '没有等待确认的 push pending' };
  if (!pending.confirmationReceiptId) return { ok: false, reason: 'pending 之后还没有真实 user event' };
  const matched = claim.pendingId === pending.pendingId && claim.userReceiptId === pending.confirmationReceiptId
    && claim.sessionId === pending.session && claim.confirmationTurn === pending.confirmationTurn;
  if (!matched) return { ok: false, reason: 'assertion 与 pending 或紧随其后确认 turn 的真实 user event 不匹配' };
  const facts = repoFacts(root), pushUrl = (work.git(facts.repo, ['remote', 'get-url', '--push', pending.remote]) || '').trim() || null;
  if (facts.head !== pending.head || pushUrl !== pending.pushUrl) return { ok: false, reason: 'HEAD 或 push URL 已漂移；需要重新尝试 push 生成 pending' };
  state.assertion = { ...pending, userReceiptId: claim.userReceiptId, createdAt: new Date().toISOString(), preToolUsed: false, nativeUsed: false };
  writePush(root, state);
  return { ok: true, pendingId: pending.pendingId, confirmationTurn: pending.confirmationTurn };
}
function preTool(root, input) {
  if (input.tool_name !== 'Bash' || typeof input.tool_input?.command !== 'string') return null;
  observe(root, input);
  const parsed = classifyPush(input.tool_input.command); if (!parsed) return null;
  if (!parsed.exact) {
    return deny(parsed.refspec && !parsed.canonical
      ? `Harness push gate：Lite 只保证 canonical 形式 git push <remote> HEAD:<destination-ref>；请改用 HEAD 作为源。`
      : 'Harness push gate：请使用精确的 git push <remote> HEAD:<destination-ref>。');
  }
  const binding = pushBinding(root, input, parsed), file = pushFile(root);
  if (!binding.head || !binding.pushUrl) return deny(`Harness push gate：无法解析 HEAD 或 remote ${parsed.remote} 的 push URL。`);
  const current = readPush(root), assertion = current.assertion;
  if (assertion && !assertion.preToolUsed && assertion.confirmationTurn === (input.turn_id || null) && sameBinding(assertion, binding)) {
    assertion.preToolUsed = true; assertion.toolUseId = input.tool_use_id || null;
    writePush(root, current); return allow();
  }
  current.pending = { ...binding, attempt: Number(current.pending?.attempt || 0) + 1, createdAt: new Date().toISOString() };
  delete current.assertion; writePush(root, current);
  return deny(`Harness push gate：待确认这一次 git push ${parsed.remote} ${parsed.refspec}。`);
}
function stop(root, input, opts = {}) {
  observe(root, input);
  const state = readTurn(root, input), after = work.snapshot(root), change = work.delta(state.baseline, after), chain = tree.readChain(root);
  const tokenFiles = change.changed.filter((file) => !file.startsWith('docs/harness/usage/') && !file.startsWith('docs/harness/reports/'));
  const verification = work.latestVerify(root, state.startedAt), token = io.sha(JSON.stringify({ change: tokenFiles.map((file) => [file, after.files[file] || null]), head: after.head,
    leaf: chain.leaf?.name, verify: verification?.at }));
  const failure = verification && !verification.ok ? io.sha(JSON.stringify({ ids: verification.ids, results: verification.results?.map((x) => [x.id, x.status]) })) : null;
  const forbidden = tokenFiles.some((file) => (chain.forbidden || []).some((prefix) => file === prefix.replace(/\/$/, '') || file.startsWith(`${prefix.replace(/\/$/, '')}/`)));
  const failures = { ...(state.failures || {}) };
  if (failure) failures[failure] = Number(failures[failure] || 0) + 1;
  const progress = change.changed.some((x) => !work.own(x)) || change.headChanged || !!verification;
  const push = readPush(root), pushWaiting = !!push.pending && !push.pending.confirmationReceiptId;
  const blocked = !!chain.leaf && progress && state.lastStopToken !== token
    && (!failure || failures[failure] < 3) && !forbidden && !pushWaiting && chain.health.ok && !!chain.plan;
  state.failures = failures; state.lastStopToken = token; state.events = [...new Set([...(state.events || []), 'Stop'])];
  if (blocked) {
    const reason = '继续 current leaf；Harness 只表示流程续跑，不表示产品完成。';
    state.continuations = [...new Set([...(state.continuations || []), io.sha(reason)])]; writeTurn(root, input, state);
    return { output: { decision: 'block', reason }, delta: change, state };
  }
  const shouldReport = change.changed.some((file) => !file.startsWith('docs/harness/usage/')
    && !file.startsWith('docs/harness/reports/') && file !== 'docs/harness/verify.jsonl') || !!verification;
  const r = shouldReport ? work.report(root, { chain, delta: change, verification,
    next: failure && failures[failure] >= 3 ? `同处失败 ${failures[failure]} 次，停止` : chain.leaf ? '等待下一轮真实进展' : 'stage 停点，等待用户验收' },
  { write: opts.write !== false, id: `${cleanId(input.session_id)}-${cleanId(input.turn_id)}` }) : null;
  const u = work.appendUsage(root, { session: input.session_id, turn: input.turn_id, receipt: state.receipt || null,
    events: state.events, files: r?.productChanges.length || 0, outOfScope: r?.outOfScope || 0, verify: verification?.summary }, { write: opts.write !== false });
  if (opts.write !== false) try { fs.unlinkSync(turnFile(root, input)); } catch { /* no turn */ }
  return { output: {}, delta: change, report: r, usage: u, state };
}
const SECRET = /-----BEGIN [A-Z ]*PRIVATE KEY-----|\bAKIA[0-9A-Z]{16}\b|\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}|sk-(?:proj-)?[A-Za-z0-9_-]{20,})\b/;
function scanRefs(root, input) {
  const zero = /^0+$/;
  for (const line of String(input).trim().split(/\r?\n/).filter(Boolean)) {
    const parts = line.trim().split(/\s+/); if (parts.length !== 4) return false;
    const [, local, , remote] = parts; if (zero.test(local)) continue;
    const range = zero.test(remote) ? local : `${remote}..${local}`;
    const log = spawnSync('git', ['log', '--format=', '-p', '-U0', '--no-ext-diff', '--diff-merges=first-parent', range], { cwd: root, encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 });
    if (log.status !== 0 || log.stdout.split('\n').some((row) => /^\+[^+]/.test(row) && SECRET.test(row))) return false;
  }
  return true;
}
function nativePrePush(root, remote, url, refs) {
  const marker = io.json(path.join(root, '.codex', 'harness-lite', 'native.json'), null);
  if (!marker?.configured) return { ok: true, bypassed: true };
  if (!require('./install.js').verify06(root).ok) return { ok: false, reason: '已声明 0.7 但 runtime identity 损坏，fail closed' };
  const state = readPush(root), assertion = state.assertion, facts = repoFacts(root);
  if (!assertion || !assertion.preToolUsed || assertion.nativeUsed || assertion.project !== facts.repo || assertion.head !== facts.head
    || assertion.remote !== remote || assertion.pushUrl !== (url || assertion.pushUrl)) return { ok: false, reason: '没有匹配的一次性 push assertion' };
  const lines = String(refs).trim().split(/\r?\n/).filter(Boolean);
  if (lines.length !== 1 || lines[0].trim().split(/\s+/).length !== 4) return { ok: false, reason: 'native ref 与 push assertion 不匹配' };
  const parts = lines[0].trim().split(/\s+/), localOid = parts[1], remoteRef = parts[2];
  if (localOid !== assertion.head || remoteRef !== assertion.destinationRef) return { ok: false, reason: 'native local OID 或 remote ref 与 push assertion 漂移' };
  if (!scanRefs(root, refs)) return { ok: false, reason: '待推提交不可读或含高置信密钥' };
  assertion.nativeUsed = true; writePush(root, state); return { ok: true };
}
function dispatch(root, input, opts = {}) {
  const event = eventName(input);
  if (event === 'SessionStart') return sessionStart(root, input);
  if (event === 'UserPromptSubmit') { const result = userPrompt(root, input); return result.context ? { hookSpecificOutput: { hookEventName: event, additionalContext: result.context } } : {}; }
  if (event === 'Stop') return stop(root, input, opts).output;
  if (event === 'PreToolUse') return preTool(root, input);
  return {};
}

module.exports = { turnDir, turnFile, readTurn, writeTurn, observe, sessionStart, userPrompt, readPush,
  shellSegments, tokens, classifyPush, projectRoot, pushBinding, pushAssert, preTool, stop, scanRefs, nativePrePush, dispatch };
