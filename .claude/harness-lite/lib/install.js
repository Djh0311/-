'use strict';
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');
const io = require('./io.js');
const authorization = require('./authorization.js');
const GIT_ENV = Object.freeze({ PATH: '/usr/bin:/bin', LANG: 'C', LC_ALL: 'C' });
const gitRun = (args, opts = {}) => spawnSync('/usr/bin/git', args, { ...opts, env: GIT_ENV });

const VERSION = '0.13.0';
const SOURCE_COMMIT = 'working-copy:0.13.0-candidate';
const RUNTIME = '.claude/harness-lite';
const MANIFEST = `${RUNTIME}/ownership.json`;
const INSTALLATION_ANCHOR = '.codex/harness-lite/installation.json';
const EVENTS = ['SessionStart', 'UserPromptSubmit', 'Stop', 'PreToolUse'];
const OWNED05_REQUIRED = `bin/hl.js hooks/README.md hooks/pre-push.js hooks/session-start.js hooks/stop.js hooks/user-prompt.js lib/authorization.js lib/checks.js lib/close-stage.js lib/done.js lib/extensions.js lib/gate.js lib/git-pre-push.js lib/gitfacts.js lib/hookio.js lib/leaf.js lib/lifecycle.js lib/limits.js lib/map.js lib/mistakes.js lib/ownership.js lib/report.js lib/tests-pick.js lib/tree.js lib/usage.js skills/root-cause.md skills/split-work.md skills/test-first.md settings-snippet.json`.split(' ').map((x) => `${RUNTIME}/${x}`).concat('.codex/harness-lite/hooks-snippet.json');
const LEGACY_CONTROL = ['.codex/harness-lite/hooks-snippet.json', 'docs/harness/policy.json', 'docs/harness/authorization.json', 'docs/harness/authorization.example.json', 'docs/harness/templates/leaf.md', 'docs/harness/templates/report.md'];
const PREVIOUS_06_INSTRUCTION = `<!-- HARNESS-LITE:BEGIN -->
Harness Lite 内部规则：用户用清晰自然语言给目标和边界，直接生效；用户日常命令为 0。读取 docs/harness/ 的 plan、唯一 current leaf 及其 stage；清晰新目标且没有 current leaf 时，由模型直接创建最小 stage/leaf 并引用本轮 Hook 来源收据，不让用户操作内部状态。非 push 偏差只报告；push 使用精确一次性确认。文件位置是生命周期事实；退场只原子移动一个文件。报告必须分 Harness、产品、证据、载体，不把 working copy 或离线 fixture 冒充发布或真实运行。
<!-- HARNESS-LITE:END -->`;
const PREVIOUS_07_INSTRUCTION = `<!-- HARNESS-LITE:BEGIN -->
Harness Lite 内部规则：用户用清晰自然语言给目标和边界，直接生效；用户日常命令为 0。读取 docs/harness/ 的 plan、唯一 current leaf 及其 stage；leaf 是模型维护的工作投影，不是授权票或范围最高权威。发现仍服务同一目标的必要相邻路径，模型更新 leaf 并继续；按当前目标影响、后果、可信可能和直接证据做最小处理，低概率低影响理论问题只报告。普通 leaf 范围外只报告；明确“不许动”的路径和 push 按既有停点处理。文件位置是生命周期事实；退场只原子移动一个文件。报告必须分 Harness、产品、证据、载体，不把 working copy 或离线 fixture 冒充发布或真实运行。
<!-- HARNESS-LITE:END -->`;
const OFFICIAL_06 = Object.freeze({
  runtimeVersion: '0.6.0', sourceCommit: 'working-copy:640ad4d0d81828cd80bfee9ff6be6c87d20a7aa6',
  packageDigest: 'sha256:2f644436a6d69af6ed51ca007f250df1daa0a1a39c7bb43726d69226bc338b92',
  instructionBlockDigest: 'sha256:ff7591b87500d31e2fc1400052db4c1e10efb396db881e52642a6ca73f900b4c',
  managedPaths: Object.freeze(['bin/hl.js', 'hooks/README.md', 'hooks/dispatcher.js', 'lib/hook.js', 'lib/install.js', 'lib/io.js', 'lib/limits.js', 'lib/tree.js', 'lib/work.js', 'skills/root-cause.md', 'skills/split-work.md', 'skills/test-first.md']),
});
const OFFICIAL_07 = Object.freeze({
  runtimeVersion: '0.7.0', sourceCommit: 'working-copy:640ad4d0d81828cd80bfee9ff6be6c87d20a7aa6',
  packageDigest: 'sha256:99323df550792f5dc34a33ae7e09df17fae727f5c8d20195f736e746057bafb3',
  hookDefinitionDigest: 'sha256:9dcc3c8b3f4c028956aa42ff34ca21e807903dff9d407d947837ac39186e5054',
  instructionBlockDigest: 'sha256:4a87ff5ab56331b588057614ab5f1c824589017088b38404ea4923bbc3fe9320',
  managedPaths: Object.freeze(['bin/hl.js', 'hooks/README.md', 'hooks/dispatcher.js', 'lib/hook.js', 'lib/install.js', 'lib/io.js', 'lib/limits.js', 'lib/tree.js', 'lib/work.js', 'skills/root-cause.md', 'skills/split-work.md', 'skills/test-first.md']),
});
const OFFICIAL_08 = Object.freeze({
  runtimeVersion: '0.8.0', sourceCommit: 'working-copy:90b5f8c14a71a415d87374821fff4af35ad6372e', profile: 'project',
  packageDigest: 'sha256:a24ed01605b7041976308da65e3c02f0276cc9b03c17fdc43f32cda6a94edc78',
  instructionBlockDigest: 'sha256:e2181c9ecdfe38f0c4b4a84ed9b53ec8d2ed2da902d16d71f4c70cbd01efd51d',
  managedPaths: Object.freeze(['LICENSE', 'bin/hl.js', 'hooks/README.md', 'hooks/dispatcher.js', 'lib/authorization.js', 'lib/evidence.js',
    'lib/hook.js', 'lib/install.js', 'lib/io.js', 'lib/limits.js', 'lib/managed.js', 'lib/tree.js', 'lib/work.js', 'package.json',
    'skills/root-cause.md', 'skills/split-work.md', 'skills/test-first.md']),
});
const PREVIOUS_09_RUNTIME_FILES = Object.freeze([
  Object.freeze({ path: 'LICENSE', mode: '0644', size: 11306, sha256: 'sha256:562f37e174cfc898700736e9a37b2b5b9626c5460f27d07898aa1a96fe4a93b5' }),
  Object.freeze({ path: 'bin/hl.js', mode: '0755', size: 5642, sha256: 'sha256:68dde57c042110d2ad1c03363f1258701e3a96e47462f6f73ad8c24f2ae4d2e2' }),
  Object.freeze({ path: 'hooks/README.md', mode: '0644', size: 2016, sha256: 'sha256:410cdac32043e04aac50563a12394c184e0a602db0b68237bd6b645e700c72f6' }),
  Object.freeze({ path: 'hooks/dispatcher.js', mode: '0755', size: 2670, sha256: 'sha256:a8761bbe3a18d7f58450d32f02dea21b869b460261e4b3793e26b4f7b82e4f84' }),
  Object.freeze({ path: 'lib/authorization.js', mode: '0644', size: 12313, sha256: 'sha256:664ff8e9f1b0cf8b492ac90dcacec010078d730b0bb91b89212b3be1ce872afa' }),
  Object.freeze({ path: 'lib/evidence.js', mode: '0644', size: 6053, sha256: 'sha256:e0381ceba0f4d1968855b07d66d55aac28839ba26f7d110a385676d1e56acd88' }),
  Object.freeze({ path: 'lib/hook.js', mode: '0644', size: 18801, sha256: 'sha256:2f4ab6690902c276a6f8813e9870f59c2cd21c89bfae06707b71327b5674d227' }),
  Object.freeze({ path: 'lib/install.js', mode: '0644', size: 101568, sha256: 'sha256:e52b38c90e5a89a479677616db3fafaaaf4adc2943cf45935a9c6c3535af7be1' }),
  Object.freeze({ path: 'lib/io.js', mode: '0644', size: 3499, sha256: 'sha256:f7c12d31fd7adc9adaa70e45a80a1681abf201aa3c8deb60c75b55763133ddaf' }),
  Object.freeze({ path: 'lib/limits.js', mode: '0644', size: 2155, sha256: 'sha256:9a9cb06cae32a5274b661e77b54d34d42f6da3739447702996cd0e655dc933bc' }),
  Object.freeze({ path: 'lib/managed.js', mode: '0644', size: 34516, sha256: 'sha256:d05316f208596e80ab2e7d9661246b80f2c5f97d0a41d875b142ece658460a7b' }),
  Object.freeze({ path: 'lib/tree.js', mode: '0644', size: 11645, sha256: 'sha256:5c64de35c7e337f9345bffeda16591ec9054fa48994257a7167aba65d1e15dd5' }),
  Object.freeze({ path: 'lib/work.js', mode: '0644', size: 28430, sha256: 'sha256:d837161d620f018a756ca3968b4021b1aded61296946852936b68fd8a1fa4e29' }),
  Object.freeze({ path: 'package.json', mode: '0644', size: 373, sha256: 'sha256:f47824188a169f998e85191241c4871f26551cf9dff9be7bf92829c5de82dfba' }),
  Object.freeze({ path: 'skills/root-cause.md', mode: '0644', size: 805, sha256: 'sha256:9cec231f6d8a8b3233278350b083ae2fdf171a474dcb4b00bdc4f51761f40cf0' }),
  Object.freeze({ path: 'skills/split-work.md', mode: '0644', size: 770, sha256: 'sha256:cd6df777ddfe2458d6ba149e83023a67671888010a6f6c9c4f19e18d2ef31231' }),
  Object.freeze({ path: 'skills/test-first.md', mode: '0644', size: 699, sha256: 'sha256:c415d818b52d99e319ac9a03daf5fc79dcbc072d1aa4d647a9afe2daf6b34eff' }),
]);
const PREVIOUS_09_RUNTIME_PATHS = Object.freeze(PREVIOUS_09_RUNTIME_FILES.map((row) => row.path));
const PREVIOUS_09_SNAPSHOT = Object.freeze({
  runtimeVersion: '0.9.1',
  sourceCommit: 'working-copy:0.9.1-unreleased',
  packageDigest: 'sha256:947fb2f97b239a56fc71fb0fb424e0dba4ea4eb585784134d13cc92a79da9b0b',
  hookDefinitionDigest: 'sha256:08f85bbbd212b37b729ae27971755d7327d6efc463a4411f68defada55934d6e',
  instructionBlockDigest: 'sha256:a2af0dc1023aa4b446782273d21236ff49fc54462977f493b8062da984505eda',
  managedPaths: PREVIOUS_09_RUNTIME_PATHS,
  files: PREVIOUS_09_RUNTIME_FILES,
  productJavaScriptFiles: 11,
  productDigest: 'sha256:bee1870e20c5cd766a1b84eaeb779025a5b16558e4da783e9ce3b911d6781666',
  fileDigest: 'sha256:b623a2ec7818426b8f13faa6b6d516b25a6a33522bd1372f60b96556d0dbe824',
  label: '0.9.1 working-copy snapshot fixture (NV00 17-path baseline)',
});
const CURRENT_REQUIRED_RUNTIME_PATHS = Object.freeze([
  'LICENSE',
  'bin/hl.js',
  'hooks/README.md',
  'hooks/dispatcher.js',
  'lib/authorization.js',
  'lib/capabilities.js',
  'lib/delegation.js',
  'lib/evidence.js',
  'lib/guidance.js',
  'lib/hook.js',
  'lib/install.js',
  'lib/io.js',
  'lib/limits.js',
  'lib/managed.js',
  'lib/tree.js',
  'lib/work.js',
  'package.json',
  'skills/root-cause.md',
  'skills/split-work.md',
  'skills/test-first.md',
]);
const PREVIOUS_12_SNAPSHOT = Object.freeze({
  runtimeVersion: '0.12.0',
  sourceCommit: 'working-copy:0.12.0-candidate',
  packageDigest: 'sha256:dca4e9590b0439e48bd0168faf597c413575031bdcccd517243aec9c4454bdf9',
  hookDefinitionDigest: 'sha256:08f85bbbd212b37b729ae27971755d7327d6efc463a4411f68defada55934d6e',
  instructionBlockDigest: 'sha256:4169fa27286a8c7a3ab8b1167d31893c2a1ecf5342dad9ee9489191193371c43',
  managedPaths: Object.freeze([...CURRENT_REQUIRED_RUNTIME_PATHS]),
  label: 'retained Harness Lite 0.12.0 candidate runtime before Astra guidance upgrade',
});
const PREVIOUS_10_SNAPSHOT = Object.freeze({
  runtimeVersion: '0.10.0',
  sourceCommit: 'working-copy:0.10.0-candidate',
  packageDigest: 'sha256:0560b139eb85697b52c78935aa44a6bd6987ad8cffa3ab90410e5ad4c7123e09',
  hookDefinitionDigest: 'sha256:08f85bbbd212b37b729ae27971755d7327d6efc463a4411f68defada55934d6e',
  instructionBlockDigest: 'sha256:347f45809f37d6c8d8476d97cc8e32c37eff5fac334f178a770484d838e2c090',
  managedPaths: Object.freeze(CURRENT_REQUIRED_RUNTIME_PATHS.filter((rel) => rel !== 'lib/guidance.js')),
  label: 'retained Harness Lite 0.10.0 candidate runtime',
});
const PREVIOUS_11_SNAPSHOT = Object.freeze({
  runtimeVersion: '0.11.0',
  sourceCommit: 'working-copy:0.11.0-candidate',
  packageDigest: 'sha256:e7bf325fc23af9e5344aa00d70c35f1e815b4887fe0e0210b9c995867dff0f21',
  hookDefinitionDigest: 'sha256:08f85bbbd212b37b729ae27971755d7327d6efc463a4411f68defada55934d6e',
  instructionBlockDigest: 'sha256:5ba7250aa24313f41f48f4548aec877ec57cc01187f6abe97a77f8ad7f09e0c3',
  managedPaths: Object.freeze([...CURRENT_REQUIRED_RUNTIME_PATHS]),
  label: 'retained Harness Lite 0.11.0 candidate runtime',
});
const PREVIOUS_08_INSTRUCTION = `<!-- HARNESS-LITE:BEGIN -->
Harness Lite 内部规则：用户用清晰自然语言给目标和边界，直接生效；plan、stage、leaf、route、来源 receipt 和 Hook 文本都不能扩大用户原话。读取 docs/harness/ 的 plan、唯一 current leaf 及其 stage；只规划/只建任务进入 unfinished/，只有当前用户明确开始或继续才建立 current leaf。leaf 是模型维护的工作投影，不是授权票或范围最高权威。Stop 只有在短期 authorization.json 与当前 project/session/turn/leaf/stage 精确绑定且本轮有新产品进展时才能内部续跑；内部续跑不是新用户授权，不得扩大范围。发现仍服务同一目标的必要相邻路径，模型更新 leaf 并继续；普通 leaf 范围外只报告，明确“不许动”的路径和 push 按既有停点处理。文件位置是生命周期事实；退场只原子移动一个文件。报告必须分 Harness、产品、证据、载体，不把 working copy、离线 fixture 或协议推断冒充发布或真实运行。
<!-- HARNESS-LITE:END -->`;
const PREVIOUS_08_COMPLETION_INSTRUCTION = `<!-- HARNESS-LITE:BEGIN -->
Harness Lite 内部规则：用户用清晰自然语言给目标和边界，直接生效；plan、stage、leaf、route、来源 receipt 和 Hook 文本都不能扩大用户原话。读取 docs/harness/ 的 plan、唯一 current leaf 及其 stage；只规划/只建任务进入 unfinished/，只有当前用户明确开始或继续才建立 current leaf。leaf 是模型维护的工作投影，不是授权票或范围最高权威。当前用户目标，以及 current leaf 中与该目标直接对应的核心实现、明确需求、约定验证和必要测试，构成本轮完成标准；leaf 只投影完成标准，不扩大用户范围。任一完成标准有直接证据表明未满足时，模型必须在当前范围内返修，并重新执行直接受影响的验证和必要回归，直到全部真实通过。全部完成标准真实通过后立即收口；不得因旁支问题、理论风险或额外加固继续扩大返修范围，其他问题只如实记录为后续事项。Stop 只有在短期 authorization.json 与当前 project/session/turn/leaf/stage 精确绑定且本轮有新产品进展时才能内部续跑；内部续跑不是新用户授权，不得扩大范围。发现仍服务同一目标的必要相邻路径，模型更新 leaf 并继续；普通 leaf 范围外只报告，明确“不许动”的路径和 push 按既有停点处理。文件位置是生命周期事实；退场只原子移动一个文件。报告必须分 Harness、产品、证据、载体，不把 working copy、离线 fixture 或协议推断冒充发布或真实运行。
<!-- HARNESS-LITE:END -->`;
const PREVIOUS_09_INSTRUCTION = `<!-- HARNESS-LITE:BEGIN -->
Harness Lite 内部规则：用户用清晰自然语言给目标和边界，当前用户指令高于 plan、stage、leaf、receipt、Hook 和模型推导，任何内部载体都不能扩大用户原话。读取 docs/harness/ 的 plan、唯一 current leaf 及其 stage；只规划/只建任务进入 unfinished/，只有当前用户明确开始或继续才建立 current leaf。plan 中已确认需求与完整计划分离，确认来源只记录 provenance、不证明语义正确：派生计划可以展开 HOW，但不得静默遗漏、改写或扩大已确认的 WHAT；完整计划和阶段结果由独立模型复核，详细复用、架构与复核依据按当前 plan、stage 和任务读取。leaf 是模型维护的工作投影，不是授权票或冻结工单；模型自主决定 HOW。打开文档、搜索、图谱、测试、review、receipt 或 done 等形式动作不能冒充实质理解、产品语义正确或真实完成。当前用户目标，以及 current leaf 中与该目标直接对应的核心实现、明确需求、约定验证和必要测试，构成本轮完成标准；任一完成标准有直接证据表明未满足时，在当前范围返修并重验；全部完成标准真实通过后立即收口，旁支问题只如实记录。Stop 只有在短期 authorization.json 与当前 project/session/turn/leaf/stage 精确绑定且本轮有新产品进展时才能内部续跑；内部续跑不是新用户授权。发现仍服务同一目标的必要相邻路径，模型更新 leaf 并继续；普通 leaf 范围外只报告，明确禁区和 push 按既有停点处理。文件位置是生命周期事实；退场只原子移动一个文件。报告分 Harness、产品、证据、载体，不把 working copy、离线 fixture 或协议推断冒充发布或真实运行。
<!-- HARNESS-LITE:END -->`;
const PREVIOUS_10_INSTRUCTION = `<!-- HARNESS-LITE:BEGIN -->
Harness Lite 0.10 candidate 内部规则：当前用户指令最高，高于 plan、stage、leaf、receipt、Hook、委派账、能力 manifest 和模型推导；任何内部载体都不能扩大用户原话，push/release/部署/真实宿主维护动作只按用户精确授权执行，且绝不干扰 Poracode、watchdog、bridge 等宿主进程。读取 docs/harness/ 的 plan、唯一 current leaf 及其 stage；只规划/只建任务进入 unfinished/，只有当前用户明确开始或继续才建立 current leaf；产品实现/修复要求指导模型直接派 writer，讨论、只读分析、计划准备不因形式强制派 writer。leaf 是生命周期总容器，不被 work unit 取代；一个 current leaf 内可有多个 work unit，每个 work unit 只携带 goal、directAcceptance、allowed、forbidden、facts、entryPoints、disprovenRoutes、unknowns、routeBasis、dependencies 和 resultContract，并投影 boundaries(allowed/forbidden)，缺项显式 UNKNOWN，使指导模型无需全仓预读即可开工。Harness 不调度 agent，不连接 provider，不保存 credential，不维护静态模型目录，不抓 UI，不持久化完整 prompt/transcript/代码，不用 transcript 或错误文本猜可用性，也不运行 daemon；它只把当前最小任务、真实工具定义或宿主显式结构化 capability manifest、依赖、写面、300000ms 只读 heartbeat、验收、恢复租约和升级状态投影给指导模型，缺失能力信息记 UNKNOWN。无结构化 manifest 时，指导模型读取自己当前真实工具定义；真实工具定义缺失则 UNKNOWN。模型名不能推断 availability 或 family；未知 family 标为 unclassified；availability、capability 和 suitability 必须分开；Grok 偏工程，Gemini 偏前端，Terra/Sol 仅用于问题级恢复。指导模型直接从本轮真实工具定义或结构化 manifest 选择并调用 spawn、wait/status、message、interrupt、takeover 等宿主现有工具，并按真实依赖、写面和共享状态决定串并行；Harness 账只是本地投影/记账，不能冒充 live agent status。无依赖且写面不重叠的 work unit 可并行；依赖只由 accepted 解锁，reported_complete 只启动指导模型验收；写面前缀重叠、共享状态冲突或越界必须 integration owner、重拆或串行。heartbeat 只是只读提醒，不是 progress；activity 只记录 activityAt/activityKind；semantic progress 只接受 verified-fact、route-eliminated、acceptance-advanced、root-cause-isolated、actionable-blocker 且必须 evidenceRef。沉默、思考、长工具、tool wait、provider delay 或 heartbeat overdue 本身不触发介入；只有直接 live evidence 的 stopped/stall、actual blocker、drift/重复已否定 route、forbidden/write-scope 越界或未协调共享状态冲突，才可建议 message/interrupt/takeover。有效语义失败必须绑定 leaf、稳定 work-unit identity、acceptanceGate、stableProblemFingerprint、显式 modelFamily、evidenceRef、primary cause 和实质不同 route；同一主因/同根断言/replay 去重，重复已否定 route 只标 drift。普通 family 同问题 5 次实质不同有效失败后进入 Terra xhigh complete recovery；Terra 一次完整恢复仍有效失败即进入 Sol xhigh；Sol 默认 3 次，可由问题级有效配置在 1..5 内绑定，耗尽后 blocked/exhausted 需用户决定或新证据；direct acceptance PASS 只清当前 problem lease。只有真实产品选择、关键术语或重大架构歧义才向用户问；能从代码、文档、现场或工具直接查明的事实由模型自行查；先用最短直接证据验证关键判断，诊断手段不自动成为最终产品架构。将被淘汰的服务器或旧系统不能作为未来产品权威，但不自动禁止只读查看其当前调用关系、真实行为或诊断事实。打开文档、搜索、图谱、测试、review、receipt、done、文件数、日志、运行中和自报 COMPLETE 都不能冒充实质理解、semantic progress 或 accepted。Stop 只有在短期 authorization.json 与当前 project/session/turn/leaf/stage 精确绑定且本轮有新 semantic progress 时才能内部续跑；内部续跑不是新用户授权。普通 leaf 范围外只报告，明确禁区和 push 按既有停点处理。文件位置是生命周期事实；退场只原子移动一个文件。报告分 Harness、产品、证据、载体，不把 working copy、离线 fixture、协议推断或 candidate 冒充发布、真实运行、push 或 release。
<!-- HARNESS-LITE:END -->`;
const INSTRUCTION = `<!-- HARNESS-LITE:BEGIN -->
Harness Lite 面向 GPT-6 Astra：用户指令决定目标、范围和权限，内部载体不能扩权；current leaf 只是工作投影。先用直接证据判断用户结果，再推进普通且已授权的可恢复工作；只派发、记账、测试绿或自报不等于结果完成，缺结果保持 complete=false、productResult=incomplete。reported unit 先按自己的完成标准和 evidenceRef 验收，只有 accepted 才解锁真实依赖它的下游；没有对象不虚构暂停目标。局部故障只影响当前问题或 unit，独立分支继续。Astra 从完整请求和上下文补齐安全范围并持续推进；能直接查证就不问，只有不可替代的用户选择才问。表达先给结论，再给证据和缺口；按需审阅技能与常驻指令，冲突时说明来源。委派须有真实工具和质量/时间收益；小任务不形式拆分，独立写面可并行，依赖/共享写面决定串行。普通层五次不同有效语义失败后进入 Astra xhigh 恢复，默认三次、问题级 1..5；工具、队列、传输、认证、中间红和沉默不计，耗尽只影响当前问题。只有真实硬风险才精确拦截并说明动作、目标、边界、风险和用户决定。未知记 UNKNOWN，不扩大为全局 blocked；每次事件只给一个 focus、decisionQuestion、nextAction；carrier 不截断伪装完整。Harness 异常只停用受影响能力，按 ownership 可逆撤回，不拖死宿主；测试按行为风险选择，用户日常 Harness 命令为 0。
<!-- HARNESS-LITE:END -->`;
const PREVIOUS_12_INSTRUCTION = `<!-- HARNESS-LITE:BEGIN -->
Harness Lite 0.12 内部核心：当前用户明确要求决定目标、范围、取舍和权限，优先于 plan、stage、leaf、receipt、Hook、委派账或模型推导；内部载体不能扩大用户原意。用与当前目标直接相关的权威产品设计解释需求，用已核实的代码、调用、数据和运行事实判断现状，二者分开记录；current leaf 只是最小工作投影。先用最短直接证据判断产品结果，再继续普通且已授权的可恢复工作；产品结果完成标准必须逐条对上，任何内部状态不能单独冒充用户需要的功能或产品结果。只派发或只记录不等于用户结果完成，结果未出现就保持 complete=false、productResult=incomplete；若 B 依赖未验收的 A，第一动作先 HOLD/暂停 B，A 未经主管验收且没有 evidenceRef 前不得启动；局部故障只修当前 unit A，B 有结果不代表整个目标或 leaf 完成，A 未修好时保持 complete=false、productResult=incomplete，不扩大到全局；能直接查证就不问用户，只有不可替代的用户选择才问。只有现有硬风险真实命中时，才对当前具体动作精确拦截并说清动作、目标、边界、风险和需要用户决定的事项。状态无法核实时记 UNKNOWN，不冒充可信或已完成，也不把单个内部异常扩大成全项目 blocked。每次事件只给一个当前 focus、一个 decisionQuestion 和一个 nextAction；完整用户目标与完成标准、证据通过带完整性和 sentinel 的 carrier 传递，不能用截断假装完整。Harness 自身异常时停用受影响的自动能力但不拖死宿主普通任务；Harness 写入的内容必须按 ownership 精确撤回，存在歧义时零写 HOLD。工作事件变化时读取当次 guidance；用户日常 Harness 命令仍为 0。
<!-- HARNESS-LITE:END -->`;
const KNOWN_CURRENT_INSTRUCTION_DIGESTS = new Set([
  '99e3bbbe0272c09f02eb635cab1c8ee561b49003feee888b7e85a8382ae32585',
  '5ba7250aa24313f41f48f4548aec877ec57cc01187f6abe97a77f8ad7f09e0c3',
]);

const sourceRoot = () => path.join(__dirname, '..');
function runtimePaths(source = sourceRoot()) {
  const packageFile = path.join(source, 'package.json');
  let packageStat, packageValue;
  try { packageStat = fs.lstatSync(packageFile); packageValue = JSON.parse(fs.readFileSync(packageFile, 'utf8')); }
  catch { throw new Error('runtime source package.json 缺失或不是有效 JSON'); }
  if (!packageStat.isFile() || packageStat.isSymbolicLink() || packageValue?.type !== 'commonjs') throw new Error('runtime source package.json 必须是普通文件并声明 type=commonjs');
  const files = [packageFile, ...['bin', 'hooks', 'lib', 'skills'].flatMap((dir) => io.list(path.join(source, dir), true))];
  if (fs.existsSync(path.join(source, 'LICENSE'))) files.push(path.join(source, 'LICENSE'));
  return files.filter((file) => fs.lstatSync(file).isFile()).map((file) => path.relative(source, file).replaceAll('\\', '/')).sort();
}
const desiredMode = (rel) => rel === 'bin/hl.js' || rel === 'hooks/dispatcher.js' ? 0o755 : 0o644;
function canonical(value) {
  if (Array.isArray(value)) return value.map(canonical);
  if (value && typeof value === 'object') return Object.fromEntries(Object.keys(value).sort().map((key) => [key, canonical(value[key])]));
  return value;
}
const canonicalDigest = (value) => `sha256:${io.sha(JSON.stringify(canonical(value)))}`;
function samePath(a, b) { try { return fs.realpathSync(a) === fs.realpathSync(b); } catch { return path.resolve(a) === path.resolve(b); } }
function canonicalPathWithMissing(value) {
  const absolute = path.resolve(value), suffix = [];
  let cursor = absolute;
  for (;;) {
    try { return path.resolve(fs.realpathSync(cursor), ...suffix); }
    catch (error) {
      if (error.code !== 'ENOENT' && error.code !== 'ENOTDIR') throw error;
      const parent = path.dirname(cursor);
      if (parent === cursor) return absolute;
      suffix.unshift(path.basename(cursor)); cursor = parent;
    }
  }
}
function globalCodexRoot(opts = {}) {
  return path.resolve(opts.codexHome || process.env.CODEX_HOME || path.join(os.homedir(), '.codex'));
}
function targetBoundary(root, opts = {}) {
  const target = path.resolve(root), global = globalCodexRoot(opts);
  let targetCanonical, globalCanonical;
  try { targetCanonical = canonicalPathWithMissing(target); globalCanonical = canonicalPathWithMissing(global); }
  catch (error) { return { ok: false, status: 'HOLD', kind: 'boundary-unknown', reason: `无法 canonicalize 安装目标边界：${error.message}`, target, global }; }
  const inside = targetCanonical === globalCanonical || targetCanonical.startsWith(`${globalCanonical}${path.sep}`);
  let inodeAlias = false;
  try {
    const globalStat = fs.statSync(global), wanted = `${globalStat.dev}:${globalStat.ino}`;
    let cursor = target;
    for (;;) {
      try { const stat = fs.statSync(cursor); if (`${stat.dev}:${stat.ino}` === wanted) { inodeAlias = true; break; } }
      catch (error) { if (error.code !== 'ENOENT' && error.code !== 'ENOTDIR') throw error; }
      const parent = path.dirname(cursor); if (parent === cursor) break; cursor = parent;
    }
  } catch (error) { if (error.code !== 'ENOENT' && error.code !== 'ENOTDIR') return { ok: false, status: 'HOLD', kind: 'boundary-unknown', reason: `无法核对安装目标 inode 边界：${error.message}`, target, global }; }
  if (inside || inodeAlias) return { ok: false, status: 'HOLD', kind: 'global-codex-root', reason: '目标是当前用户的全局 Codex 配置根或其内部路径；Harness Lite 只允许安装到项目根', target, global, targetCanonical, globalCanonical };
  return { ok: true, target, global, targetCanonical, globalCanonical };
}
function boundaryHold(boundary, extra = {}) {
  return { status: 'HOLD', ok: false, kind: boundary.kind, written: 0, removed: false,
    differences: [boundary.kind || 'global-codex-root'], reason: boundary.reason, ...extra };
}
function unsafeParent(root, file) {
  let cursor = path.resolve(root); for (const part of path.relative(root, path.dirname(file)).split(path.sep).filter(Boolean)) {
    cursor = path.join(cursor, part); try { const stat = fs.lstatSync(cursor); if (stat.isSymbolicLink() || !stat.isDirectory()) return cursor; } catch (error) { if (error.code !== 'ENOENT') throw error; }
  } return null;
}
function hookConfigRoot(root) {
  const result = gitRun(['worktree', 'list', '--porcelain'], { cwd: root, encoding: 'utf8' });
  if (result.status !== 0) return path.resolve(root);
  const first = result.stdout.split('\n').find((line) => line.startsWith('worktree '));
  return first ? path.resolve(first.slice(9).trim()) : path.resolve(root);
}
function projectDefinition(root, version, frozen = false, nodeExecutable = process.execPath) {
  const command = frozen ? `node "$(git rev-parse --show-toplevel)/${RUNTIME}/hooks/dispatcher.js"`
    : `${JSON.stringify(path.resolve(nodeExecutable))} "$(/usr/bin/git rev-parse --show-toplevel)/${RUNTIME}/hooks/dispatcher.js"`;
  const handler = (timeout, canAddContext = true) => ({ type: 'command', command, timeout,
    ...(canAddContext ? { additionalContextLimit: 1800 } : {}) });
  const config = { description: `Harness Lite ${version} lifecycle hooks`, hooks: {
    SessionStart: [{ matcher: 'startup|resume|clear|compact', hooks: [handler(15)] }],
    UserPromptSubmit: [{ hooks: [handler(10)] }],
    Stop: [{ hooks: [handler(30, false)] }],
    PreToolUse: [{ matcher: '^Bash$', hooks: [handler(10)] }],
  } };
  return { config, digest: `sha256:${io.sha(JSON.stringify(canonical(config.hooks)))}`, command };
}
const definition = (root) => projectDefinition(root, VERSION);
const official07Definition = (root) => projectDefinition(root, OFFICIAL_07.runtimeVersion, true);
const official08Definition = (root, nodeExecutable = process.execPath) => projectDefinition(root, OFFICIAL_08.runtimeVersion, false, nodeExecutable);
function manifest(root, staged, source = sourceRoot(), profile = 'project', hookPreimage = { fileExisted: true, addedEvents: [] }, extensions = {}, instructionOwnership = null, rollbackCarriers = []) {
  const managedPaths = runtimePaths(source), def = definition(root);
  return { runtimeVersion: VERSION, sourceCommit: SOURCE_COMMIT, profile, managedPaths,
    packageDigest: io.digest(staged, managedPaths), hookDefinitionDigest: def.digest,
    instructionBlockDigest: `sha256:${io.sha(INSTRUCTION)}`, hookPreimage, extensions,
    instructionOwnership, rollbackCarriers };
}
function validHookPreimage(value) {
  return !!value && typeof value === 'object' && typeof value.fileExisted === 'boolean' && Array.isArray(value.addedEvents)
    && new Set(value.addedEvents).size === value.addedEvents.length && value.addedEvents.every((event) => EVENTS.includes(event));
}
function runtimeProbe(root, runtime, operation) {
  const script = operation === 'definition'
    ? "const api=require(process.argv[1]);process.stdout.write(JSON.stringify({digest:api.definition(process.argv[2]).digest}))"
    : "const api=require(process.argv[1]);const value=api.verify06(process.argv[2]);process.stdout.write(JSON.stringify(value));process.exit(value.ok?0:1)";
  const run = spawnSync(process.execPath, ['-e', script, path.join(runtime, 'lib', 'install.js'), root], { encoding: 'utf8' });
  let value = null; try { value = JSON.parse(run.stdout || 'null'); } catch { /* malformed probe is a failure */ }
  return { ok: run.status === 0 && !!value, value, reason: String(run.stderr || run.stdout || `runtime ${operation} probe failed`).trim() };
}
function actualRuntimeFiles(runtime) {
  return io.list(runtime, true).map((file) => path.relative(runtime, file).replaceAll('\\', '/'))
    .filter((rel) => rel !== 'ownership.json' && !rel.startsWith('extensions/')).sort();
}
function extensionDifferences(runtime, extensions) {
  const differences = [];
  if (!extensions || typeof extensions !== 'object' || Array.isArray(extensions)) return ['extensions-ledger'];
  const claimed = new Set();
  for (const [id, spec] of Object.entries(extensions)) {
    if (!/^[a-z0-9][a-z0-9-]*$/.test(id) || !spec || typeof spec !== 'object' || !spec.packageVersion
      || !Array.isArray(spec.managedPaths) || !/^sha256:[0-9a-f]{64}$/.test(spec.packageDigest || '')) { differences.push(`extension-schema:${id}`); continue; }
    const paths = [...spec.managedPaths].sort(), prefix = `extensions/${id}/`;
    if (!paths.length || paths.some((rel) => typeof rel !== 'string' || !rel.startsWith(prefix) || claimed.has(rel))) { differences.push(`extension-paths:${id}`); continue; }
    for (const rel of paths) { claimed.add(rel); const type = io.inspect(runtime, rel).type; if (type !== 'file') differences.push(`extension-${type}:${rel}`); }
    let extensionDigest = null; try { extensionDigest = io.digest(runtime, paths); } catch (error) { differences.push(`extension-identity:${id}:${error.message}`); }
    if (extensionDigest !== spec.packageDigest) differences.push(`extension-packageDigest:${id}`);
  }
  const physical = io.list(path.join(runtime, 'extensions'), true).map((file) => path.relative(runtime, file).replaceAll('\\', '/')).sort();
  for (const rel of physical.filter((item) => !claimed.has(item))) differences.push(`extension-extra:${rel}`);
  return differences;
}
function verify06(root, opts = {}) {
  const boundary = targetBoundary(root, opts); if (!boundary.ok) return boundaryHold(boundary);
  root = path.resolve(root);
  const runtime = path.join(root, RUNTIME), value = io.json(path.join(root, MANIFEST));
  if (!value || value.runtimeVersion !== VERSION || !Array.isArray(value.managedPaths)) return { ok: false, kind: 'not-current', differences: ['ownership.json'] };
  const actual = actualRuntimeFiles(runtime), expected = [...value.managedPaths].sort(), differences = [];
  const def = definition(root), allowedHookDefinitions = new Set([def.digest, previous06Digest(def)]);
  if (value.sourceCommit !== SOURCE_COMMIT) differences.push('sourceCommit');
  if (value.instructionBlockDigest !== `sha256:${io.sha(INSTRUCTION)}`) differences.push('instructionBlockDigest');
  if (!['project', 'managed'].includes(value.profile)) differences.push('profile');
  if (!allowedHookDefinitions.has(value.hookDefinitionDigest)) differences.push('hookDefinitionDigest');
  if ('hookPreimage' in value && !validHookPreimage(value.hookPreimage)) differences.push('hookPreimage');
  let localPackageDigest = null;
  try { const localPaths = runtimePaths(sourceRoot()); localPackageDigest = io.digest(sourceRoot(), localPaths, desiredMode); } catch { /* source comparison is advisory */ }
  const currentOwnershipRequired = value.packageDigest === localPackageDigest;
  if ((value.instructionOwnership != null || currentOwnershipRequired) && !validInstructionOwnership(value.instructionOwnership)) differences.push('instructionOwnership');
  if ((value.rollbackCarriers != null || currentOwnershipRequired) && !validRollbackCarriers(value.rollbackCarriers)) differences.push('rollbackCarriers');
  for (const rel of CURRENT_REQUIRED_RUNTIME_PATHS) if (!expected.includes(rel)) differences.push(`managedPath:${rel}`);
  for (const rel of expected) { const type = io.inspect(runtime, rel).type; if (type !== 'file') differences.push(`${type}:${rel}`); }
  for (const rel of actual.filter((x) => !expected.includes(x))) differences.push(`extra:${rel}`);
  let digest = null; try { digest = io.digest(runtime, expected); } catch (error) { differences.push(`identity:${error.message}`); }
  if (digest !== value.packageDigest) differences.push('packageDigest');
  differences.push(...extensionDifferences(runtime, value.extensions));
  const anchor = verifyInstallationAnchor(root, value);
  if (!anchor.ok) differences.push(...anchor.differences);
  return { ok: differences.length === 0, kind: differences.length ? 'drift' : 'current', differences, manifest: value, digest, anchor };
}
function verifyPrevious12Snapshot(root) {
  const boundary = targetBoundary(root); if (!boundary.ok) return boundaryHold(boundary);
  const runtime = path.join(root, RUNTIME), value = io.json(path.join(root, MANIFEST));
  if (!value || value.runtimeVersion !== PREVIOUS_12_SNAPSHOT.runtimeVersion || !Array.isArray(value.managedPaths)) {
    return { ok: false, kind: 'drift', differences: ['ownership.json'] };
  }
  const expected = [...PREVIOUS_12_SNAPSHOT.managedPaths], actual = actualRuntimeFiles(runtime), differences = [];
  for (const key of ['sourceCommit', 'packageDigest', 'hookDefinitionDigest', 'instructionBlockDigest']) {
    if (value[key] !== PREVIOUS_12_SNAPSHOT[key]) differences.push(key);
  }
  if (!['project', 'managed'].includes(value.profile)) differences.push('profile');
  if (JSON.stringify([...value.managedPaths].sort()) !== JSON.stringify(expected)) differences.push('managedPaths');
  if (!validHookPreimage(value.hookPreimage)) differences.push('hookPreimage');
  for (const rel of expected) { const type = io.inspect(runtime, rel).type; if (type !== 'file') differences.push(`${type}:${rel}`); }
  for (const rel of actual.filter((rel) => !expected.includes(rel))) differences.push(`extra:${rel}`);
  let digest = null; try { digest = io.digest(runtime, expected); } catch (error) { differences.push(`identity:${error.message}`); }
  if (digest !== PREVIOUS_12_SNAPSHOT.packageDigest) differences.push('fixed-packageDigest');
  const instructionRows = value.instructionOwnership?.files || [];
  const expectedInstructionDigest = `sha256:${io.sha(PREVIOUS_12_INSTRUCTION)}`;
  if (value.instructionBlockDigest !== expectedInstructionDigest || !validInstructionOwnership(value.instructionOwnership, PREVIOUS_12_INSTRUCTION)) differences.push('instructionOwnership');
  differences.push(...extensionDifferences(runtime, value.extensions));
  const anchor = verifyInstallationAnchor(root, value);
  if (!anchor.ok) differences.push(...anchor.differences);
  return { ok: differences.length === 0, kind: differences.length ? 'drift' : 'previous-12-snapshot', profile: value.profile,
    differences, manifest: value, digest, anchor, evidence: { carrier: PREVIOUS_12_SNAPSHOT.label, packageDigest: digest, instructionRows: instructionRows.length } };
}
function verifyPrevious11Snapshot(root) {
  const boundary = targetBoundary(root); if (!boundary.ok) return boundaryHold(boundary);
  const runtime = path.join(root, RUNTIME), value = io.json(path.join(root, MANIFEST));
  if (!value || value.runtimeVersion !== PREVIOUS_11_SNAPSHOT.runtimeVersion || !Array.isArray(value.managedPaths)) {
    return { ok: false, kind: 'drift', differences: ['ownership.json'] };
  }
  const expected = [...PREVIOUS_11_SNAPSHOT.managedPaths], actual = actualRuntimeFiles(runtime), differences = [];
  for (const key of ['sourceCommit', 'packageDigest', 'hookDefinitionDigest', 'instructionBlockDigest']) {
    if (value[key] !== PREVIOUS_11_SNAPSHOT[key]) differences.push(key);
  }
  const keys = ['extensions', 'hookDefinitionDigest', 'hookPreimage', 'instructionBlockDigest', 'managedPaths', 'packageDigest', 'profile', 'runtimeVersion', 'sourceCommit'];
  if (Object.keys(value).sort().join(',') !== keys.sort().join(',')) differences.push('manifest-schema');
  if (!['project', 'managed'].includes(value.profile)) differences.push('profile');
  if (JSON.stringify([...value.managedPaths].sort()) !== JSON.stringify(expected)) differences.push('managedPaths');
  if (!validHookPreimage(value.hookPreimage)) differences.push('hookPreimage');
  for (const rel of expected) { const type = io.inspect(runtime, rel).type; if (type !== 'file') differences.push(`${type}:${rel}`); }
  for (const rel of actual.filter((rel) => !expected.includes(rel))) differences.push(`extra:${rel}`);
  let digest = null; try { digest = io.digest(runtime, expected); } catch (error) { differences.push(`identity:${error.message}`); }
  if (digest !== PREVIOUS_11_SNAPSHOT.packageDigest) differences.push('fixed-packageDigest');
  differences.push(...extensionDifferences(runtime, value.extensions));
  return { ok: differences.length === 0, kind: differences.length ? 'drift' : 'previous-11-snapshot',
    profile: value.profile, differences, manifest: value, digest,
    evidence: { carrier: PREVIOUS_11_SNAPSHOT.label, packageDigest: digest } };
}
function verifyPrevious10Snapshot(root) {
  const boundary = targetBoundary(root); if (!boundary.ok) return boundaryHold(boundary);
  const runtime = path.join(root, RUNTIME), value = io.json(path.join(root, MANIFEST));
  if (!value || value.runtimeVersion !== PREVIOUS_10_SNAPSHOT.runtimeVersion || !Array.isArray(value.managedPaths)) {
    return { ok: false, kind: 'drift', differences: ['ownership.json'] };
  }
  const expected = [...PREVIOUS_10_SNAPSHOT.managedPaths], actual = actualRuntimeFiles(runtime), differences = [];
  for (const key of ['sourceCommit', 'packageDigest', 'hookDefinitionDigest', 'instructionBlockDigest']) {
    if (value[key] !== PREVIOUS_10_SNAPSHOT[key]) differences.push(key);
  }
  if (!['project', 'managed'].includes(value.profile)) differences.push('profile');
  if (JSON.stringify([...value.managedPaths].sort()) !== JSON.stringify(expected)) differences.push('managedPaths');
  if ('hookPreimage' in value && !validHookPreimage(value.hookPreimage)) differences.push('hookPreimage');
  for (const rel of expected) { const type = io.inspect(runtime, rel).type; if (type !== 'file') differences.push(`${type}:${rel}`); }
  for (const rel of actual.filter((rel) => !expected.includes(rel))) differences.push(`extra:${rel}`);
  let digest = null; try { digest = io.digest(runtime, expected); } catch (error) { differences.push(`identity:${error.message}`); }
  if (digest !== PREVIOUS_10_SNAPSHOT.packageDigest) differences.push('fixed-packageDigest');
  differences.push(...extensionDifferences(runtime, value.extensions));
  return { ok: differences.length === 0, kind: differences.length ? 'drift' : 'previous-10-snapshot',
    profile: value.profile, differences, manifest: value, digest,
    evidence: { carrier: PREVIOUS_10_SNAPSHOT.label, packageDigest: digest } };
}
function verifyPrevious09Snapshot(root) {
  const boundary = targetBoundary(root); if (!boundary.ok) return boundaryHold(boundary);
  const runtime = path.join(root, RUNTIME), value = io.json(path.join(root, MANIFEST));
  if (!value || value.runtimeVersion !== PREVIOUS_09_SNAPSHOT.runtimeVersion || !Array.isArray(value.managedPaths)) {
    return { ok: false, kind: 'drift', differences: ['ownership.json'] };
  }
  const actual = actualRuntimeFiles(runtime), expected = [...PREVIOUS_09_SNAPSHOT.managedPaths], claimed = [...value.managedPaths].sort(), differences = [];
  if (value.sourceCommit !== PREVIOUS_09_SNAPSHOT.sourceCommit) differences.push('sourceCommit');
  if (value.profile !== 'project') differences.push('profile');
  if (value.packageDigest !== PREVIOUS_09_SNAPSHOT.packageDigest) differences.push('packageDigest');
  if (value.hookDefinitionDigest !== PREVIOUS_09_SNAPSHOT.hookDefinitionDigest) differences.push('hookDefinitionDigest');
  if (value.instructionBlockDigest !== PREVIOUS_09_SNAPSHOT.instructionBlockDigest) differences.push('instructionBlockDigest');
  if (JSON.stringify(claimed) !== JSON.stringify(expected)) differences.push('managedPaths');
  if ('hookPreimage' in value && !validHookPreimage(value.hookPreimage)) differences.push('hookPreimage');
  if (!value.extensions || typeof value.extensions !== 'object' || Array.isArray(value.extensions) || Object.keys(value.extensions).length) differences.push('extensions');
  for (const { path: rel, mode, size, sha256 } of PREVIOUS_09_SNAPSHOT.files) {
    const item = io.inspect(runtime, rel);
    if (item.type !== 'file') { differences.push(`${item.type}:${rel}`); continue; }
    if (item.mode !== mode) differences.push(`mode:${rel}`);
    let body = null; try { body = fs.readFileSync(item.abs); } catch (error) { differences.push(`read:${rel}:${error.message}`); }
    if (body && body.length !== size) differences.push(`size:${rel}`);
    if (body && `sha256:${io.sha(body)}` !== sha256) differences.push(`content:${rel}`);
  }
  for (const rel of actual.filter((x) => !expected.includes(x))) differences.push(`extra:${rel}`);
  let digest = null; try { digest = io.digest(runtime, expected); } catch (error) { differences.push(`identity:${error.message}`); }
  if (digest !== PREVIOUS_09_SNAPSHOT.packageDigest) differences.push('fixed-packageDigest');
  differences.push(...extensionDifferences(runtime, {}));
  return { ok: differences.length === 0, kind: differences.length ? 'drift' : 'previous-09-snapshot',
    profile: value.profile, differences, manifest: value, digest, evidence: { carrier: PREVIOUS_09_SNAPSHOT.label, packageDigest: digest } };
}
function verifyOfficial08(root, nodeExecutable = process.execPath) {
  const boundary = targetBoundary(root); if (!boundary.ok) return boundaryHold(boundary);
  const runtime = path.join(root, RUNTIME), value = io.json(path.join(root, MANIFEST));
  if (!value || value.runtimeVersion !== OFFICIAL_08.runtimeVersion || !Array.isArray(value.managedPaths)) return { ok: false, kind: 'drift', differences: ['ownership.json'] };
  const expected = [...OFFICIAL_08.managedPaths], actual = actualRuntimeFiles(runtime), differences = [];
  for (const key of ['sourceCommit', 'profile', 'packageDigest', 'instructionBlockDigest']) {
    if (value[key] !== OFFICIAL_08[key]) differences.push(key);
  }
  if (value.hookDefinitionDigest !== official08Definition(root, nodeExecutable).digest) differences.push('hookDefinitionDigest');
  if (JSON.stringify([...value.managedPaths].sort()) !== JSON.stringify(expected)) differences.push('managedPaths');
  if ('hookPreimage' in value && !validHookPreimage(value.hookPreimage)) differences.push('hookPreimage');
  for (const rel of expected) { const type = io.inspect(runtime, rel).type; if (type !== 'file') differences.push(`${type}:${rel}`); }
  for (const rel of actual.filter((x) => !expected.includes(x))) differences.push(`extra:${rel}`);
  let digest = null; try { digest = io.digest(runtime, expected); } catch (error) { differences.push(`identity:${error.message}`); }
  if (digest !== OFFICIAL_08.packageDigest) differences.push('official-packageDigest');
  differences.push(...extensionDifferences(runtime, value.extensions));
  return { ok: differences.length === 0, kind: differences.length ? 'drift' : 'official-08', profile: value.profile, differences, manifest: value, digest };
}
function verifyOfficial07(root) {
  const boundary = targetBoundary(root); if (!boundary.ok) return boundaryHold(boundary);
  const runtime = path.join(root, RUNTIME), value = io.json(path.join(root, MANIFEST));
  if (!value || value.runtimeVersion !== OFFICIAL_07.runtimeVersion || !Array.isArray(value.managedPaths)) return { ok: false, kind: 'drift', differences: ['ownership.json'] };
  const expected = [...OFFICIAL_07.managedPaths], actual = actualRuntimeFiles(runtime), differences = [];
  if (value.sourceCommit !== OFFICIAL_07.sourceCommit) differences.push('sourceCommit');
  if (JSON.stringify([...value.managedPaths].sort()) !== JSON.stringify(expected)) differences.push('managedPaths');
  if (value.packageDigest !== OFFICIAL_07.packageDigest) differences.push('packageDigest');
  if (value.hookDefinitionDigest !== OFFICIAL_07.hookDefinitionDigest) differences.push('hookDefinitionDigest');
  if (value.instructionBlockDigest !== OFFICIAL_07.instructionBlockDigest) differences.push('instructionBlockDigest');
  if ('profile' in value) differences.push('unexpected-profile');
  if (!value.extensions || typeof value.extensions !== 'object' || Array.isArray(value.extensions) || Object.keys(value.extensions).length) differences.push('extensions');
  for (const rel of expected) {
    const item = io.inspect(runtime, rel), wantedMode = (rel === 'bin/hl.js' || rel === 'hooks/dispatcher.js') ? '0755' : '0644';
    if (item.type !== 'file') differences.push(`${item.type}:${rel}`); else if (item.mode !== wantedMode) differences.push(`mode:${rel}`);
  }
  for (const rel of actual.filter((x) => !expected.includes(x))) differences.push(`extra:${rel}`);
  let digest = null; try { digest = io.digest(runtime, expected); } catch (error) { differences.push(`identity:${error.message}`); }
  if (digest !== OFFICIAL_07.packageDigest) differences.push('official-packageDigest');
  return { ok: differences.length === 0, kind: differences.length ? 'drift' : 'official-07', profile: 'project', differences, manifest: value, digest };
}
function verifyOfficial06(root) {
  const boundary = targetBoundary(root); if (!boundary.ok) return boundaryHold(boundary);
  const runtime = path.join(root, RUNTIME), value = io.json(path.join(root, MANIFEST));
  if (!value || value.runtimeVersion !== OFFICIAL_06.runtimeVersion || !Array.isArray(value.managedPaths)) {
    return { ok: false, kind: 'drift', differences: ['ownership.json'] };
  }
  const expected = [...OFFICIAL_06.managedPaths], actual = actualRuntimeFiles(runtime), differences = [];
  if (value.sourceCommit !== OFFICIAL_06.sourceCommit) differences.push('sourceCommit');
  if (JSON.stringify([...value.managedPaths].sort()) !== JSON.stringify(expected)) differences.push('managedPaths');
  if (value.packageDigest !== OFFICIAL_06.packageDigest) differences.push('packageDigest');
  if (value.instructionBlockDigest !== OFFICIAL_06.instructionBlockDigest) differences.push('instructionBlockDigest');
  if (value.hookDefinitionDigest !== definition(root).digest) differences.push('hookDefinitionDigest');
  if (!value.extensions || typeof value.extensions !== 'object' || Array.isArray(value.extensions) || Object.keys(value.extensions).length) differences.push('extensions');
  for (const rel of expected) { const type = io.inspect(runtime, rel).type; if (type !== 'file') differences.push(`${type}:${rel}`); }
  for (const rel of actual.filter((x) => !expected.includes(x))) differences.push(`extra:${rel}`);
  let digest = null; try { digest = io.digest(runtime, expected); } catch (error) { differences.push(`identity:${error.message}`); }
  if (digest !== OFFICIAL_06.packageDigest) differences.push('official-packageDigest');
  return { ok: differences.length === 0, kind: differences.length ? 'drift' : 'official-06', differences, manifest: value, digest };
}
function verifyOwned05(root, value) {
  const boundary = targetBoundary(root); if (!boundary.ok) return boundaryHold(boundary);
  const pkg = value?.version === 1 && value.managedBy === 'harness-lite' && value.packages?.core;
  if (!pkg || pkg.packageVersion !== '0.5.0' || !pkg.files || typeof pkg.files !== 'object') return { ok: false, kind: 'hybrid', differences: ['legacy-manifest-shape'] };
  const differences = [];
  for (const rel of OWNED05_REQUIRED) if (!(rel in pkg.files)) differences.push(`unowned:${rel}`);
  for (const [rel, expected] of Object.entries(pkg.files)) {
    const item = io.inspect(root, rel);
    if (item.type !== 'file') differences.push(`${item.type}:${rel}`);
    else if (item.digest !== expected) differences.push(`content:${rel}`);
  }
  const recorded = Object.keys(pkg.files).filter((rel) => rel.startsWith(`${RUNTIME}/`) && rel !== MANIFEST).map((rel) => rel.slice(RUNTIME.length + 1));
  const actual = actualRuntimeFiles(path.join(root, RUNTIME));
  for (const rel of actual.filter((x) => !recorded.includes(x) && x !== 'settings-snippet.json')) differences.push(`extra:${rel}`);
  return { ok: differences.length === 0, kind: differences.length ? 'hybrid' : 'owned-05', differences, manifest: value };
}
function legacyUnowned(root) {
  const boundary = targetBoundary(root); if (!boundary.ok) return boundaryHold(boundary);
  const runtime = path.join(root, RUNTIME), actual = actualRuntimeFiles(runtime);
  const items = actual.map((rel) => io.inspect(runtime, rel));
  const anomalies = new Set(items.filter((item) => item.type !== 'file').map((item) => `${item.type}:${item.path}`));
  const rows = items.slice(0, 50).map((item) => `${item.type}:${item.mode || '-'}:${item.path}`);
  if (items.length > 50) rows.push(`…等${items.length}项`);
  let rootDigest = null;
  try { rootDigest = io.digest(runtime, items.filter((item) => item.type === 'file').map((item) => item.path)); } catch { /* 只读诊断允许缺失 */ }
  return { ok: false, kind: 'legacy-unowned', differences: rows, evidence: { files: items.length, anomalies: [...anomalies], rootDigest } };
}
function inspect(root, source = sourceRoot(), opts = {}) {
  const boundary = targetBoundary(root, opts); if (!boundary.ok) return boundaryHold(boundary);
  root = path.resolve(root);
  const runtime = path.join(root, RUNTIME), stat = (() => { try { return fs.lstatSync(runtime); } catch { return null; } })();
  if (!stat) return { ok: true, kind: 'fresh', differences: [] };
  if (!stat.isDirectory() || stat.isSymbolicLink()) return { ok: false, kind: 'drift', differences: [`type:${RUNTIME}`] };
  const value = io.json(path.join(root, MANIFEST));
  if (!value) return legacyUnowned(root);
  if (value.runtimeVersion === VERSION) {
    const current = verify06(root); if (current.ok) return current;
    const previous12 = verifyPrevious12Snapshot(root); if (previous12.ok) return previous12;
    const previous11 = verifyPrevious11Snapshot(root); return previous11.ok ? previous11 : current;
  }
  if (value.runtimeVersion === PREVIOUS_12_SNAPSHOT.runtimeVersion) return verifyPrevious12Snapshot(root);
  if (value.runtimeVersion === PREVIOUS_11_SNAPSHOT.runtimeVersion) return verifyPrevious11Snapshot(root);
  if (value.runtimeVersion === PREVIOUS_10_SNAPSHOT.runtimeVersion) return verifyPrevious10Snapshot(root);
  if (value.runtimeVersion === PREVIOUS_09_SNAPSHOT.runtimeVersion) return verifyPrevious09Snapshot(root);
  if (value.runtimeVersion === OFFICIAL_08.runtimeVersion) return verifyOfficial08(root);
  if (value.runtimeVersion === OFFICIAL_07.runtimeVersion) return verifyOfficial07(root);
  if (value.runtimeVersion === OFFICIAL_06.runtimeVersion) return verifyOfficial06(root);
  if (value.runtimeVersion) return { ok: false, kind: 'drift', differences: ['runtimeVersion'] };
  return verifyOwned05(root, value);
}
function surfacePreflight(root) {
  const boundary = targetBoundary(root); if (!boundary.ok) return [boundary.kind || 'global-codex-root'];
  const configRoot = hookConfigRoot(root), dirs = ['.claude', 'docs', 'docs/harness', 'docs/harness/archive', 'docs/harness/archive/legacy-0.5', ...['stages', 'leaves', 'unfinished', 'done', 'reports', 'usage'].map((x) => `docs/harness/${x}`), '.codex'];
  const files = ['AGENTS.md', 'CLAUDE.md', 'docs/harness/plan.md', 'docs/harness/MISTAKES.md'];
  if (path.resolve(configRoot) === path.resolve(root)) files.push('.codex/hooks.json'); else {
    const item = io.inspect(configRoot, '.codex'); if (item.type !== 'missing' && item.type !== 'directory') return [`${item.type}:${item.path}`];
    const hookFile = io.inspect(configRoot, '.codex/hooks.json'); if (hookFile.type !== 'missing' && hookFile.type !== 'file') return [`${hookFile.type}:${hookFile.path}`];
  }
  const differences = [];
  for (const rel of dirs) { const item = io.inspect(root, rel); if (item.type !== 'missing' && item.type !== 'directory') differences.push(`${item.type}:${rel}`); }
  for (const rel of files) { const item = io.inspect(root, rel); if (item.type !== 'missing' && item.type !== 'file') differences.push(`${item.type}:${rel}`); }
  return differences;
}
function runtimeImage(dir, prefix = '') {
  const root = fs.lstatSync(dir);
  if (!root.isDirectory() || root.isSymbolicLink()) throw new Error(`runtime root 不安全：${dir}`);
  const rows = [[prefix, 'directory', root.mode & 0o777, `${root.dev}:${root.ino}`]];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
    const file = path.join(dir, entry.name), rel = path.join(prefix, entry.name).replaceAll('\\', '/'), stat = fs.lstatSync(file);
    const type = stat.isSymbolicLink() ? 'symlink' : stat.isFile() ? 'file' : stat.isDirectory() ? 'directory' : 'other';
    rows.push([rel, type, stat.mode & 0o777, type === 'file' ? io.sha(fs.readFileSync(file)) : type === 'symlink' ? fs.readlinkSync(file) : type === 'directory' ? `${stat.dev}:${stat.ino}` : null]);
    if (type === 'directory') rows.push(...runtimeImage(file, rel).slice(1));
  }
  return rows;
}
function sameRuntimeImage(dir, before) {
  try { return JSON.stringify(runtimeImage(dir)) === JSON.stringify(before); } catch { return false; }
}
function directoryFence(root, dir) {
  const stat = fs.lstatSync(dir);
  if (!stat.isDirectory() || stat.isSymbolicLink() || unsafeParent(root, dir)) throw new Error(`runtime directory 不安全：${dir}`);
  const fence = fileImage(path.join(dir, '.harness-lite-directory-fence'));
  if (fence.type !== 'missing' || fence.parent.type !== 'directory') throw new Error(`runtime directory fence 不安全：${dir}`);
  return fence;
}
function removeRuntimeIfExact(root, dir, image, fence) {
  try {
    if (!sameRuntimeImage(dir, image) || !sameImage(fence) || unsafeParent(root, dir)) return `${path.basename(dir)}:concurrent-change`;
    fs.rmSync(dir, { recursive: true, force: false });
    return fs.existsSync(dir) ? `${path.basename(dir)}:cleanup-incomplete` : null;
  } catch (error) { return `${path.basename(dir)}:${error.message}`; }
}
function reserveRuntimeCarrier(root, kind) {
  const parent = path.join(root, '.claude'), stat = fs.lstatSync(parent);
  if (!stat.isDirectory() || stat.isSymbolicLink() || unsafeParent(root, parent)) throw new Error(`runtime carrier parent 不安全：${parent}`);
  const container = fs.mkdtempSync(path.join(parent, `.harness-lite.${kind}-`)); fs.chmodSync(container, 0o700);
  return { container, runtime: path.join(container, path.basename(RUNTIME)), fence: directoryFence(root, container) };
}
function removeRuntimeCarrier(root, carrier) {
  if (!carrier) return null;
  try {
    if (!sameImage(carrier.fence) || unsafeParent(root, carrier.container)) return `${path.basename(carrier.container)}:concurrent-change`;
    if (fs.readdirSync(carrier.container).length) return `${path.basename(carrier.container)}:not-empty`;
    fs.rmdirSync(carrier.container); return fs.existsSync(carrier.container) ? `${path.basename(carrier.container)}:cleanup-incomplete` : null;
  } catch (error) { return `${path.basename(carrier.container)}:${error.message}`; }
}
const runtimeImageDigest = (image) => `sha256:${io.sha(JSON.stringify(image))}`;
function validRollbackCarriers(value) {
  if (!Array.isArray(value)) return false;
  const seen = new Set();
  return value.every((spec) => {
    if (!spec || typeof spec.container !== 'string' || typeof spec.runtime !== 'string' || typeof spec.receipt !== 'string'
      || !/^sha256:[0-9a-f]{64}$/.test(spec.imageDigest || '') || !/^sha256:[0-9a-f]{64}$/.test(spec.receiptDigest || '')) return false;
    const container = spec.container.replaceAll('\\', '/'), runtime = spec.runtime.replaceAll('\\', '/'), receipt = spec.receipt.replaceAll('\\', '/');
    if (!/^\.claude\/\.harness-lite\.rollback-[^/]+$/.test(container)
      || runtime !== `${container}/${path.basename(RUNTIME)}` || receipt !== `${container}/rollback-ownership.json` || seen.has(container)) return false;
    seen.add(container); return true;
  });
}
function rollbackReceipt(root, carrier, image, stablePackageDigest) {
  const targetCanonical = canonicalPathWithMissing(root), imageDigest = runtimeImageDigest(image);
  const value = { schemaVersion: 1, managedBy: 'harness-lite', targetCanonical, stablePackageDigest, imageDigest };
  const text = `${JSON.stringify(value, null, 2)}\n`, file = path.join(carrier.container, 'rollback-ownership.json');
  io.atomic(file, text, 0o600);
  const receiptImage = fileImage(file);
  const spec = {
    container: path.relative(root, carrier.container).replaceAll('\\', '/'),
    runtime: path.relative(root, carrier.runtime).replaceAll('\\', '/'),
    receipt: path.relative(root, file).replaceAll('\\', '/'),
    imageDigest,
    receiptDigest: `sha256:${io.sha(Buffer.from(text))}`,
  };
  return { value, text, file, image: receiptImage, spec };
}
function removeRollbackReceipt(receipt) {
  if (!receipt) return null;
  try {
    if (!sameImage(receipt.image)) return 'rollback-receipt:concurrent-change';
    fs.unlinkSync(receipt.file); return fs.existsSync(receipt.file) ? 'rollback-receipt:cleanup-incomplete' : null;
  } catch (error) { return `rollback-receipt:${error.message}`; }
}
function rollbackRemovalPlan(root, specs) {
  if (!validRollbackCarriers(specs)) return { ok: false, reason: 'rollback ownership receipt schema 损坏', rows: [] };
  const parent = path.join(root, '.claude'); let physical = [];
  try {
    const stat = fs.lstatSync(parent); if (!stat.isDirectory() || stat.isSymbolicLink()) return { ok: false, reason: 'rollback carrier parent 不安全', rows: [] };
    physical = fs.readdirSync(parent).filter((name) => name.startsWith('.harness-lite.rollback-')).sort();
  } catch (error) { if (error.code !== 'ENOENT') throw error; }
  const expected = specs.map((spec) => path.basename(spec.container)).sort();
  if (JSON.stringify(physical) !== JSON.stringify(expected)) return { ok: false, reason: 'rollback carrier 与 ownership receipt 不一致或存在未声明 carrier', rows: [] };
  const rows = [];
  for (const spec of specs) {
    let container, runtime, receiptFile;
    try { container = io.safe(root, spec.container); runtime = io.safe(root, spec.runtime); receiptFile = io.safe(root, spec.receipt); }
    catch (error) { return { ok: false, reason: error.message, rows }; }
    try {
      const stat = fs.lstatSync(container);
      if (!stat.isDirectory() || stat.isSymbolicLink() || unsafeParent(root, container)) return { ok: false, reason: `rollback carrier 不安全：${spec.container}`, rows };
      if (JSON.stringify(fs.readdirSync(container).sort()) !== JSON.stringify([path.basename(RUNTIME), 'rollback-ownership.json'].sort())) return { ok: false, reason: `rollback carrier 内容歧义：${spec.container}`, rows };
      const receiptImage = fileImage(receiptFile);
      if (receiptImage.type !== 'file' || receiptImage.mode !== 0o600 || receiptImage.parent.path !== container
        || `sha256:${io.sha(receiptImage.body)}` !== spec.receiptDigest) return { ok: false, reason: `rollback receipt identity 漂移：${spec.container}`, rows };
      let receipt; try { receipt = JSON.parse(receiptImage.body.toString('utf8')); } catch { return { ok: false, reason: `rollback receipt JSON 损坏：${spec.container}`, rows }; }
      if (receipt?.schemaVersion !== 1 || receipt.managedBy !== 'harness-lite' || receipt.targetCanonical !== canonicalPathWithMissing(root)
        || !/^sha256:[0-9a-f]{64}$/.test(receipt.stablePackageDigest || '') || receipt.imageDigest !== spec.imageDigest) {
        return { ok: false, reason: `rollback receipt 与当前 target 不匹配：${spec.container}`, rows };
      }
      const image = runtimeImage(runtime);
      if (runtimeImageDigest(image) !== spec.imageDigest) return { ok: false, reason: `rollback runtime identity 漂移：${spec.container}`, rows };
      const fence = fileImage(path.join(container, '.harness-lite-directory-fence'));
      if (fence.type !== 'missing' || fence.parent.type !== 'directory') return { ok: false, reason: `rollback carrier fence 不安全：${spec.container}`, rows };
      rows.push({ spec, container, runtime, receiptFile, receiptImage, image, fence });
    } catch (error) { return { ok: false, reason: `rollback carrier 无法核对：${spec.container}:${error.message}`, rows }; }
  }
  return { ok: true, rows };
}
function moveDirectoryNoClobber(source, dest) {
  const src = fs.lstatSync(source), parent = fs.lstatSync(path.dirname(dest));
  if (!src.isDirectory() || src.isSymbolicLink()) throw new Error('只移动安全目录');
  if (!parent.isDirectory() || parent.isSymbolicLink()) throw new Error('目录移动目标 parent 不安全');
  if (path.basename(source) !== path.basename(dest)) throw new Error('no-clobber 目录移动要求同名 source/dest');
  if (fs.existsSync(dest)) throw new Error(`目录移动目标已存在：${dest}`);
  if (src.dev !== parent.dev) throw new Error('目录移动必须位于同一文件系统');
  // 把同名 source 移进目标 parent：即使 dest 在检查后并发出现，mv -n 也只会保留 source，
  // 不会把 source 当成另一个名字嵌进并发目录。
  const args = ['-n', '--', source, path.dirname(dest)];
  const moved = spawnSync('/bin/mv', args, { encoding: 'utf8' });
  if (moved.status !== 0 || fs.existsSync(source)) throw new Error(String(moved.stderr || 'directory no-clobber move 未完成').trim());
  const target = fs.lstatSync(dest);
  if (!target.isDirectory() || target.isSymbolicLink() || target.dev !== src.dev || target.ino !== src.ino) throw new Error('directory no-clobber move postimage 不安全');
}
function stage(root, source, fault = () => {}, profile = 'project', hookPreimage = { fileExisted: true, addedEvents: [] }, extensions = {}, instructionOwnership = null, rollbackCarriers = []) {
  const parent = path.join(root, '.claude'); fs.mkdirSync(parent, { recursive: true });
  const carrier = reserveRuntimeCarrier(root, 'stage'), dir = carrier.runtime;
  fs.mkdirSync(dir, { mode: 0o700 });
  let preimage = null, fence = null;
  try {
    fence = directoryFence(root, dir); preimage = runtimeImage(dir);
    for (const rel of runtimePaths(source)) {
      const dest = path.join(dir, rel); fs.mkdirSync(path.dirname(dest), { recursive: true });
      fs.copyFileSync(path.join(source, rel), dest); fs.chmodSync(dest, desiredMode(rel)); preimage = runtimeImage(dir); fault(`stage:${rel}`);
    }
    for (const spec of Object.values(extensions)) for (const rel of spec.managedPaths) {
      const src = io.safe(path.join(root, RUNTIME), rel), dest = io.safe(dir, rel), stat = fs.lstatSync(src);
      if (!stat.isFile() || stat.isSymbolicLink()) throw new Error(`扩展源文件不合规：${rel}`);
      fs.mkdirSync(path.dirname(dest), { recursive: true }); fs.copyFileSync(src, dest); fs.chmodSync(dest, stat.mode & 0o777);
      preimage = runtimeImage(dir); fault(`stage:${rel}`);
    }
    const preservedExtensions = canonical(extensions), extensionErrors = extensionDifferences(dir, preservedExtensions);
    if (extensionErrors.length) throw new Error(`staged extensions ${extensionErrors.join(',')}`);
    const value = manifest(root, dir, source, profile, hookPreimage, preservedExtensions, instructionOwnership, rollbackCarriers); fs.writeFileSync(path.join(dir, 'ownership.json'), `${JSON.stringify(value, null, 2)}\n`, { mode: 0o600 });
    preimage = runtimeImage(dir); fault('stage:manifest');
    const check = { ...value, packageDigest: io.digest(dir, value.managedPaths) };
    if (check.packageDigest !== value.packageDigest) throw new Error('stage digest mismatch');
    const ownDefinition = runtimeProbe(root, dir, 'definition');
    if (!ownDefinition.ok || ownDefinition.value.digest !== value.hookDefinitionDigest) throw new Error(`staged Hook definition mismatch${ownDefinition.reason ? `: ${ownDefinition.reason}` : ''}`);
    return { dir, manifest: value, preimage, fence, carrier };
  } catch (error) {
    const cleanup = preimage && fence ? removeRuntimeIfExact(root, dir, preimage, fence) : 'stage-preimage-unavailable';
    const carrierCleanup = !cleanup ? removeRuntimeCarrier(root, carrier) : null;
    if (cleanup || carrierCleanup) error.message = `${error.message};${[cleanup, carrierCleanup].filter(Boolean).join('|')}`;
    throw error;
  }
}
function swap(root, built, currentImage, anchorPlan, fault = () => {}) {
  const stable = path.join(root, RUNTIME), newFence = built.fence || directoryFence(root, built.dir);
  let newPreimage = built.preimage || runtimeImage(built.dir);
  let rollbackCarrier = null, rollback = null, rollbackPreimage = null, rollbackOwnership = null, anchorResult = null, oldMoved = false, newMoved = false;
  try {
    if (!sameRuntimeImage(built.dir, newPreimage) || !sameImage(newFence)) throw new Error('staged runtime 在 swap 前发生变化');
    if (currentImage) {
      if (!sameRuntimeImage(stable, currentImage)) throw new Error('current runtime 在 upgrade staging 期间发生变化');
      rollbackPreimage = currentImage; rollbackCarrier = reserveRuntimeCarrier(root, 'rollback'); rollback = rollbackCarrier.runtime;
      moveDirectoryNoClobber(stable, rollback); oldMoved = true; fault('swap:old');
      rollbackOwnership = rollbackReceipt(root, rollbackCarrier, rollbackPreimage, built.manifest.packageDigest);
      const ownershipFile = path.join(built.dir, 'ownership.json'), value = JSON.parse(fs.readFileSync(ownershipFile, 'utf8'));
      value.rollbackCarriers = [...(Array.isArray(value.rollbackCarriers) ? value.rollbackCarriers : []), rollbackOwnership.spec];
      io.atomic(ownershipFile, `${JSON.stringify(value, null, 2)}\n`, 0o600); built.manifest = value; newPreimage = runtimeImage(built.dir);
      fault('swap:rollback-receipt');
    }
    moveDirectoryNoClobber(built.dir, stable); newMoved = true; fault('swap:new');
    anchorResult = writeInstallationAnchor(root, anchorPlan, fault);
    const verified = verify06(root); if (!verified.ok) throw new Error(`post-swap ${verified.differences.join(',')}`);
    const self = runtimeProbe(root, stable, 'verify'); if (!self.ok) throw new Error(`installed runtime self-verify failed: ${self.reason}`);
    fault('swap:verified');
    if (!sameRuntimeImage(stable, newPreimage)) throw new Error('installed runtime 在验证后发生变化');
    const stageCleanup = removeRuntimeCarrier(root, built.carrier); if (stageCleanup) throw new Error(`stage-carrier:${stageCleanup}`);
    return { rollback: oldMoved ? rollbackCarrier.container : null, rollbackRuntime: rollback, rollbackCarrier, rollbackOwnership,
      rollbackPreimage, newPreimage, newFence, verified, anchorResult };
  } catch (error) {
    let failedCarrier = null, failed = null; const recovery = [];
    recovery.push(...restoreInstallationAnchor(anchorResult));
    try {
      if (newMoved && fs.existsSync(stable)) {
        if (!sameRuntimeImage(stable, newPreimage)) recovery.push('new-runtime:concurrent-change');
        else { failedCarrier = reserveRuntimeCarrier(root, 'failed'); failed = failedCarrier.runtime; moveDirectoryNoClobber(stable, failed); }
      }
    } catch (restore) { recovery.push(`new-runtime:${restore.message}`); }
    try {
      if (oldMoved && fs.existsSync(rollback) && !fs.existsSync(stable)) {
        if (!sameRuntimeImage(rollback, rollbackPreimage) || !sameImage(rollbackCarrier.fence)) recovery.push('old-runtime:concurrent-change');
        else moveDirectoryNoClobber(rollback, stable);
      }
    } catch (restore) { recovery.push(`old-runtime:${restore.message}`); }
    try {
      if (failed && fs.existsSync(failed) && (!oldMoved || fs.existsSync(stable))) {
        const cleanup = removeRuntimeIfExact(root, failed, newPreimage, failedCarrier.fence);
        if (cleanup) recovery.push(`failed-runtime:${cleanup}`);
        else { const carrierCleanup = removeRuntimeCarrier(root, failedCarrier); if (carrierCleanup) recovery.push(`failed-runtime:${carrierCleanup}`); }
      }
    } catch (restore) { recovery.push(`failed-runtime:${restore.message}`); }
    if (rollbackCarrier && !fs.existsSync(rollback) && fs.existsSync(stable)) {
      const receiptCleanup = removeRollbackReceipt(rollbackOwnership); if (receiptCleanup) recovery.push(`rollback:${receiptCleanup}`);
      const cleanup = removeRuntimeCarrier(root, rollbackCarrier); if (cleanup) recovery.push(`rollback:${cleanup}`);
    }
    if (fs.existsSync(built.dir)) { const cleanup = removeRuntimeIfExact(root, built.dir, newPreimage, newFence); if (cleanup) recovery.push(`stage:${cleanup}`); }
    if (built.carrier && !fs.existsSync(built.dir)) { const cleanup = removeRuntimeCarrier(root, built.carrier); if (cleanup) recovery.push(`stage-carrier:${cleanup}`); }
    error.recovery = { rollback: rollbackCarrier?.container || null, failed: failedCarrier?.container || null, recovery };
    if (recovery.length) error.message = `${error.message};${recovery.join('|')}`;
    throw error;
  }
}
const harnessishCommand = (handler) => typeof handler?.command === 'string' && /(?:^|[\s"'\\/])\.claude[\\/]harness-lite[\\/]hooks[\\/]/.test(handler.command);
const LEGACY_HOOK = { SessionStart: ['session-start.js', 15], UserPromptSubmit: ['user-prompt.js', 10], Stop: ['stop.js', 30], PreToolUse: ['pre-push.js', 10] };
const hookGroupKey = (group) => JSON.stringify(canonical(group));
function previous06Stop(expected) {
  const group = JSON.parse(JSON.stringify(expected.config.hooks.Stop[0]));
  group.hooks[0].additionalContextLimit = 1800;
  return group;
}
function previous06Digest(expected) {
  const hooks = JSON.parse(JSON.stringify(expected.config.hooks)); hooks.Stop[0] = previous06Stop(expected);
  return `sha256:${io.sha(JSON.stringify(canonical(hooks)))}`;
}
function isExactPrevious06(data, expected) {
  return EVENTS.every((event) => {
    const groups = (Array.isArray(data.hooks?.[event]) ? data.hooks[event] : [])
      .filter((group) => Array.isArray(group?.hooks) && group.hooks.some(harnessishCommand));
    const wanted = event === 'Stop' ? previous06Stop(expected) : expected.config.hooks[event][0];
    return groups.length === 1 && hookGroupKey(groups[0]) === hookGroupKey(wanted);
  });
}
function hookGroupKind(event, group, expected, allowPrevious06 = false, definitionExpected = null, legacyRoot = null, frozenDefinition = null) {
  const key = hookGroupKey(group);
  if (key === hookGroupKey(expected)) return 'current';
  if (allowPrevious06 && event === 'Stop' && key === hookGroupKey(previous06Stop(definitionExpected))) return 'previous';
  if (frozenDefinition && key === hookGroupKey(frozenDefinition.config.hooks[event]?.[0])) return 'legacy';
  const handlers = group?.hooks || [], legacy = LEGACY_HOOK[event], handler = handlers[0], keys = handler ? Object.keys(handler).sort().join(',') : '';
  const legacyCommand = legacyRoot && legacy ? `node ${JSON.stringify(path.join(legacyRoot, RUNTIME, 'hooks', legacy[0]))}${event === 'PreToolUse' ? ' --surface codex' : ''}` : null;
  if (legacyCommand && handlers.length === 1 && !group.matcher && Object.keys(group).sort().join(',') === 'hooks' && keys === 'command,timeout,type'
    && handler.type === 'command' && handler.timeout === legacy[1] && handler.command === legacyCommand) return 'legacy';
  return handlers.some(harnessishCommand) ? 'unknown' : 'external';
}
function parseJsonDocument(text) {
  let at = 0;
  const whitespace = () => { while (/\s/.test(text[at] || '')) at++; };
  function stringNode() {
    const start = at++; let escaped = false;
    while (at < text.length) {
      const char = text[at++];
      if (escaped) escaped = false; else if (char === '\\') escaped = true; else if (char === '"') break;
    }
    const raw = text.slice(start, at); return { type: 'string', start, end: at, value: JSON.parse(raw) };
  }
  function valueNode() {
    whitespace(); const start = at, char = text[at];
    if (char === '"') return stringNode();
    if (char === '[') {
      at++; whitespace(); const items = [];
      if (text[at] !== ']') for (;;) { items.push(valueNode()); whitespace(); if (text[at] === ']') break; if (text[at++] !== ',') throw new Error('invalid JSON array'); }
      if (text[at++] !== ']') throw new Error('invalid JSON array end');
      return { type: 'array', start, end: at, items, value: items.map((item) => item.value) };
    }
    if (char === '{') {
      at++; whitespace(); const properties = [], keys = new Set(), value = {};
      if (text[at] !== '}') for (;;) {
        whitespace(); if (text[at] !== '"') throw new Error('invalid JSON key'); const keyNode = stringNode();
        if (keys.has(keyNode.value)) throw new Error(`duplicate JSON key: ${keyNode.value}`); keys.add(keyNode.value);
        whitespace(); if (text[at++] !== ':') throw new Error('invalid JSON colon'); const child = valueNode();
        properties.push({ key: keyNode.value, keyNode, valueNode: child }); value[keyNode.value] = child.value;
        whitespace(); if (text[at] === '}') break; if (text[at++] !== ',') throw new Error('invalid JSON object');
      }
      if (text[at++] !== '}') throw new Error('invalid JSON object end');
      return { type: 'object', start, end: at, properties, value };
    }
    while (at < text.length && !/[\s,\]}]/.test(text[at])) at++;
    const raw = text.slice(start, at); return { type: 'primitive', start, end: at, value: JSON.parse(raw) };
  }
  const root = valueNode(); whitespace(); if (at !== text.length) throw new Error('trailing JSON content'); return root;
}
function transformHookDocument(text, expected, options = {}) {
  const root = parseJsonDocument(text); if (root.type !== 'object') throw new Error('Hook config root 不是 object');
  const hookProperty = root.properties.find((item) => item.key === 'hooks'), hooks = hookProperty?.valueNode;
  if (!hooks || hooks.type !== 'object') throw new Error('Hook config hooks 不是 object');
  const replacements = [], missing = [], pruned = new Set();
  for (const event of EVENTS) {
    const property = hooks.properties.find((item) => item.key === event), wanted = expected.config.hooks[event][0];
    if (!property) { if (options.append) missing.push(`${JSON.stringify(event)}:[${JSON.stringify(wanted)}]`); continue; }
    const array = property.valueNode; if (array.type !== 'array') throw new Error(`Hook event 不是 array：${event}`);
    const kept = array.items.filter((item) => !options.removeKinds.has(hookGroupKind(event, item.value, wanted,
      options.previous, expected, options.legacyRoot, options.frozenDefinition))).map((item) => text.slice(item.start, item.end));
    if (!options.append && kept.length === 0 && options.pruneEvents?.has(event)) { pruned.add(property); continue; }
    if (options.append) kept.push(JSON.stringify(wanted));
    const original = text.slice(array.start, array.end);
    const prefix = array.items.length ? text.slice(array.start, array.items[0].start) : text.slice(array.start, array.end - 1);
    const suffix = array.items.length ? text.slice(array.items.at(-1).end, array.end) : ']';
    const replacement = `${prefix}${kept.join(',')}${suffix}`;
    if (replacement !== original) replacements.push({ start: array.start, end: array.end, text: replacement });
  }
  if (pruned.size) {
    const properties = hooks.properties;
    for (let index = properties.length - 1; index >= 0;) {
      if (!pruned.has(properties[index])) { index--; continue; }
      const endIndex = index; while (index > 0 && pruned.has(properties[index - 1])) index--;
      const startIndex = index; let start, end;
      if (startIndex > 0) {
        start = properties[startIndex].keyNode.start;
        while (start > properties[startIndex - 1].valueNode.end && /\s/.test(text[start - 1])) start--;
        if (text[start - 1] === ',') start--;
        end = properties[endIndex].valueNode.end;
      } else if (endIndex < properties.length - 1) {
        start = properties[startIndex].keyNode.start; end = properties[endIndex + 1].keyNode.start;
      } else { start = hooks.start + 1; end = hooks.end - 1; }
      replacements.push({ start, end, text: '' }); index--;
    }
  }
  if (missing.length) replacements.push({ start: hooks.end - 1, end: hooks.end - 1,
    text: `${hooks.properties.length ? ',' : ''}${missing.join(',')}` });
  let output = text;
  for (const replacement of replacements.sort((a, b) => b.start - a.start)) output = `${output.slice(0, replacement.start)}${replacement.text}${output.slice(replacement.end)}`;
  return output;
}
const freshHookDocument = (expected) => `${JSON.stringify({ description: 'Project hooks', hooks: Object.fromEntries(EVENTS.map((event) => [event, [expected.config.hooks[event][0]]])) }, null, 2)}\n`;
function fileImage(file) {
  let cursor = path.dirname(file), parent;
  for (;;) {
    try { const stat = fs.lstatSync(cursor); parent = { path: cursor, type: stat.isDirectory() && !stat.isSymbolicLink() ? 'directory' : 'unsafe', dev: stat.dev, ino: stat.ino, real: fs.realpathSync(cursor) }; break; }
    catch (error) { if (error.code !== 'ENOENT' || cursor === path.dirname(cursor)) throw error; cursor = path.dirname(cursor); }
  }
  try {
    const stat = fs.lstatSync(file); if (!stat.isFile() || stat.isSymbolicLink()) return { file, type: 'unsafe', parent };
    return { file, type: 'file', mode: stat.mode & 0o777, body: fs.readFileSync(file), parent };
  } catch (error) { if (error.code === 'ENOENT') return { file, type: 'missing', parent }; throw error; }
}
function sameImage(expected) {
  const actual = fileImage(expected.file), parent = actual.parent, prior = expected.parent;
  return actual.type === expected.type && parent.type === prior.type && parent.dev === prior.dev && parent.ino === prior.ino && parent.real === prior.real
    && (actual.type === 'missing' || (actual.type === 'file' && actual.mode === expected.mode && actual.body.equals(expected.body)));
}
function sameWriteParent(file, actual, prior) {
  if (prior.path === path.dirname(file)) return actual.type === prior.type && actual.dev === prior.dev && actual.ino === prior.ino && actual.real === prior.real;
  let anchor = false;
  try { const stat = fs.lstatSync(prior.path); anchor = stat.isDirectory() && !stat.isSymbolicLink() && stat.dev === prior.dev && stat.ino === prior.ino && fs.realpathSync(prior.path) === prior.real; } catch { anchor = false; }
  const expectedReal = path.resolve(prior.real, path.relative(prior.path, path.dirname(file)));
  return anchor && actual.type === 'directory' && actual.path === path.dirname(file) && actual.real === expectedReal;
}
function instructionPostimage(row) {
  return !!row.preimage && sameImage({ ...row.preimage, type: 'file', mode: row.mode, body: Buffer.from(row.text) });
}
function restoreImage(image) {
  if (image.type === 'missing') { fs.rmSync(image.file, { force: true }); return; }
  if (image.type !== 'file') throw new Error(`不能恢复非普通文件：${image.file}`);
  io.atomic(image.file, image.body, image.mode);
}
function installationAnchorFile(root) { return path.join(root, INSTALLATION_ANCHOR); }
function validAnchorDirectories(value) {
  const allowed = ['.claude', '.codex', '.codex/harness-lite'];
  return Array.isArray(value) && new Set(value).size === value.length
    && value.every((rel) => allowed.includes(rel))
    && JSON.stringify(value) === JSON.stringify(allowed.filter((rel) => value.includes(rel)));
}
function installationAnchorBase(root, manifestValue, manifestBody, createdDirectories) {
  return {
    schemaVersion: 1,
    managedBy: 'harness-lite',
    targetCanonical: canonicalPathWithMissing(root),
    runtimeVersion: manifestValue.runtimeVersion,
    sourceCommit: manifestValue.sourceCommit,
    profile: manifestValue.profile,
    sourcePackageDigest: manifestValue.packageDigest,
    hookDefinitionDigest: manifestValue.hookDefinitionDigest,
    manifestDigest: `sha256:${io.sha(manifestBody)}`,
    managedPathsDigest: canonicalDigest(manifestValue.managedPaths),
    instructionOwnershipDigest: canonicalDigest(manifestValue.instructionOwnership ?? null),
    rollbackCarriersDigest: canonicalDigest(manifestValue.rollbackCarriers ?? []),
    extensionsDigest: canonicalDigest(manifestValue.extensions ?? {}),
    createdDirectories: [...createdDirectories],
  };
}
function installationAnchorValue(root, manifestValue, manifestBody, createdDirectories) {
  const base = installationAnchorBase(root, manifestValue, manifestBody, createdDirectories);
  return { ...base, anchorDigest: canonicalDigest(base) };
}
const installationAnchorText = (value) => `${JSON.stringify(value, null, 2)}\n`;
function verifyInstallationAnchor(root, manifestValue = null) {
  root = path.resolve(root);
  const file = installationAnchorFile(root), manifestFile = path.join(root, MANIFEST), differences = [];
  const badAnchorParent = unsafeParent(root, file), badManifestParent = unsafeParent(root, manifestFile);
  if (badAnchorParent || badManifestParent) return { ok: false, differences: [badAnchorParent ? 'installationAnchor:unsafe-parent' : 'installationManifest:unsafe-parent'], file };
  let anchorImage, manifestImage;
  try { anchorImage = fileImage(file); manifestImage = fileImage(manifestFile); }
  catch (error) { return { ok: false, differences: [`installationAnchor:read:${error.message}`], file }; }
  if (anchorImage.type !== 'file') differences.push(`installationAnchor:${anchorImage.type}`);
  else {
    if (anchorImage.mode !== 0o600) differences.push('installationAnchor:mode');
    if (anchorImage.parent.type !== 'directory' || anchorImage.parent.path !== path.dirname(file)) differences.push('installationAnchor:parent');
  }
  if (manifestImage.type !== 'file') differences.push(`installationManifest:${manifestImage.type}`);
  else if (manifestImage.mode !== 0o600) differences.push('installationManifest:mode');
  if (differences.length) return { ok: false, differences, file, image: anchorImage, manifestImage };
  let anchor, installedManifest;
  try { anchor = JSON.parse(anchorImage.body.toString('utf8')); } catch { differences.push('installationAnchor:json'); }
  try { installedManifest = JSON.parse(manifestImage.body.toString('utf8')); } catch { differences.push('installationManifest:json'); }
  if (!anchor || typeof anchor !== 'object' || Array.isArray(anchor)) differences.push('installationAnchor:schema');
  if (!installedManifest || typeof installedManifest !== 'object' || Array.isArray(installedManifest)) differences.push('installationManifest:schema');
  if (differences.length) return { ok: false, differences, file, image: anchorImage, manifestImage };
  if (manifestValue && JSON.stringify(canonical(manifestValue)) !== JSON.stringify(canonical(installedManifest))) differences.push('installationManifest:value-race');
  if (!validAnchorDirectories(anchor.createdDirectories)) differences.push('installationAnchor:createdDirectories');
  if (!differences.length) {
    let expected;
    try { expected = installationAnchorValue(root, installedManifest, manifestImage.body, anchor.createdDirectories); }
    catch (error) { differences.push(`installationAnchor:binding:${error.message}`); }
    if (expected) {
      for (const key of Object.keys(expected)) if (anchor[key] !== expected[key]
        && JSON.stringify(anchor[key]) !== JSON.stringify(expected[key])) differences.push(`installationAnchor:${key}`);
      if (Object.keys(anchor).sort().join(',') !== Object.keys(expected).sort().join(',')) differences.push('installationAnchor:keys');
      if (!anchorImage.body.equals(Buffer.from(installationAnchorText(expected)))) differences.push('installationAnchor:bytes');
    }
  }
  return { ok: differences.length === 0, differences, file, image: anchorImage, manifestImage,
    value: differences.length ? anchor : installationAnchorValue(root, installedManifest, manifestImage.body, anchor.createdDirectories), manifest: installedManifest };
}
function prepareInstallationAnchor(root, before) {
  root = path.resolve(root); const file = installationAnchorFile(root), badParent = unsafeParent(root, file);
  if (badParent) return { ok: false, reason: `installation anchor 路径不安全：${path.relative(root, badParent)}` };
  const preimage = fileImage(file);
  if (!['file', 'missing'].includes(preimage.type) || preimage.parent.type !== 'directory') {
    return { ok: false, reason: 'installation anchor 路径不是安全普通文件' };
  }
  let prior = null;
  if (preimage.type === 'file') {
    prior = verifyInstallationAnchor(root, before.manifest);
    const anchoredIdentity = before.kind === 'current' || before.kind === 'previous-12-snapshot';
    if (!anchoredIdentity || !prior.ok) return { ok: false, reason: `installation anchor 与 ${before.kind} identity 不一致：${prior.differences.join(',')}` };
  } else if (before.kind === 'current') return { ok: false, reason: 'current runtime 缺少 installation anchor' };
  const directoryRels = ['.claude', '.codex', '.codex/harness-lite'], missing = [];
  for (const rel of directoryRels) {
    const dir = path.join(root, rel);
    try { const stat = fs.lstatSync(dir); if (!stat.isDirectory() || stat.isSymbolicLink() || fs.realpathSync(dir) !== canonicalPathWithMissing(dir)) return { ok: false, reason: `installation anchor directory 不安全：${rel}` }; }
    catch (error) { if (error.code === 'ENOENT') missing.push(rel); else return { ok: false, reason: `installation anchor directory 无法核对：${rel}:${error.message}` }; }
  }
  return { ok: true, file, preimage, createdDirectories: prior ? [...prior.value.createdDirectories] : missing,
    createNow: missing.filter((rel) => rel !== '.claude') };
}
function removeEmptyAnchorDirectories(root, directories) {
  const failures = [];
  for (const rel of [...directories].reverse()) {
    const dir = path.join(root, rel);
    try {
      const stat = fs.lstatSync(dir);
      if (!stat.isDirectory() || stat.isSymbolicLink() || unsafeParent(root, dir)) { failures.push(`${rel}:unsafe`); continue; }
      if (fs.readdirSync(dir).length === 0) fs.rmdirSync(dir);
    } catch (error) { if (error.code !== 'ENOENT') failures.push(`${rel}:${error.message}`); }
  }
  return failures;
}
function writeInstallationAnchor(root, plan, fault = () => {}) {
  if (!plan?.ok) throw new Error(plan?.reason || 'installation anchor plan 缺失');
  if (!sameImage(plan.preimage)) throw new Error('installation anchor 在 preflight 后发生变化');
  const createdNow = []; let postimage = null, text = null;
  try {
    fault('anchor:before'); if (!sameImage(plan.preimage)) throw new Error('installation anchor 在写入前发生变化');
    for (const rel of plan.createNow) {
      const dir = path.join(root, rel); fs.mkdirSync(dir, { mode: 0o700 }); createdNow.push(rel);
      const stat = fs.lstatSync(dir); if (!stat.isDirectory() || stat.isSymbolicLink()) throw new Error(`installation anchor directory 创建后不安全：${rel}`);
    }
    const manifestImage = fileImage(path.join(root, MANIFEST));
    if (manifestImage.type !== 'file' || manifestImage.mode !== 0o600) throw new Error('installation manifest 不是 0600 普通文件');
    let manifestValue; try { manifestValue = JSON.parse(manifestImage.body.toString('utf8')); } catch { throw new Error('installation manifest JSON 损坏'); }
    const value = installationAnchorValue(root, manifestValue, manifestImage.body, plan.createdDirectories);
    text = installationAnchorText(value); io.atomic(plan.file, text, 0o600); postimage = fileImage(plan.file); fault('anchor:written');
    const verified = verifyInstallationAnchor(root, manifestValue); if (!verified.ok) throw new Error(`installation anchor verify failed:${verified.differences.join(',')}`);
    fault('anchor:verified'); if (!sameImage(postimage)) throw new Error('installation anchor 在验证后发生变化');
    return { ok: true, root: path.resolve(root), file: plan.file, preimage: plan.preimage, postimage, value, createdNow, createdDirectories: plan.createdDirectories, verified };
  } catch (error) {
    const recovery = [];
    try {
      const actual = fileImage(plan.file), expected = text === null ? null : { ...actual, type: 'file', mode: 0o600, body: Buffer.from(text) };
      if (text !== null && actual.type === 'file' && actual.mode === 0o600 && actual.body.equals(Buffer.from(text))) restoreImage(plan.preimage);
      else if (text === null && sameImage(plan.preimage)) { /* no anchor write */ }
      else if (actual.type !== plan.preimage.type || (actual.type === 'file' && !actual.body.equals(plan.preimage.body))) recovery.push('anchor:concurrent-change');
      else if (expected && !sameImage(expected)) recovery.push('anchor:concurrent-change');
    } catch (restore) { recovery.push(`anchor:${restore.message}`); }
    recovery.push(...removeEmptyAnchorDirectories(root, createdNow));
    if (recovery.length) error.message = `${error.message};${recovery.join('|')}`;
    throw error;
  }
}
function restoreInstallationAnchor(result) {
  if (!result?.ok) return [];
  const failures = [];
  try { if (!sameImage(result.postimage)) failures.push('anchor:concurrent-change'); else restoreImage(result.preimage); }
  catch (error) { failures.push(`anchor:${error.message}`); }
  if (!failures.length) failures.push(...removeEmptyAnchorDirectories(result.root, result.createdNow));
  return failures;
}
function installationAnchorRemovalPlan(root, checked) {
  const verified = checked?.anchor?.ok ? checked.anchor : verifyInstallationAnchor(root, checked?.manifest);
  if (!verified.ok) return { ok: false, reason: `installation anchor identity 漂移：${verified.differences.join(',')}` };
  return { ok: true, root: path.resolve(root), file: verified.file, preimage: verified.image, createdDirectories: [...verified.value.createdDirectories] };
}
function writeInstallationAnchorRemoval(plan, fault = () => {}) {
  if (!sameImage(plan.preimage)) return { ok: false, wrote: false, reason: 'installation anchor 在 uninstall preflight 后发生变化' };
  try {
    fault('anchor:uninstall:before'); if (!sameImage(plan.preimage)) throw new Error('installation anchor 在 uninstall 写入前发生变化');
    fs.unlinkSync(plan.file); fault('anchor:uninstall:removed');
    if (fileImage(plan.file).type !== 'missing') throw new Error('installation anchor 删除后仍存在');
    return { ok: true, wrote: true, plan };
  } catch (error) {
    const recovery = [];
    try { if (fileImage(plan.file).type === 'missing') restoreImage(plan.preimage); else recovery.push('anchor:concurrent-change'); }
    catch (restore) { recovery.push(`anchor:${restore.message}`); }
    return { ok: false, wrote: false, reason: recovery.length ? `${error.message};${recovery.join('|')}` : error.message, plan };
  }
}
function restoreInstallationAnchorRemoval(result) {
  if (!result?.ok || !result.wrote) return [];
  try { if (fileImage(result.plan.file).type !== 'missing') return ['anchor:concurrent-change']; restoreImage(result.plan.preimage); return []; }
  catch (error) { return [`anchor:${error.message}`]; }
}
function writeHookPlan(plan, fault = () => {}) {
  const { file, before, text, mode, digest, preimage } = plan;
  if (!sameImage(preimage)) return { ok: false, status: 'HOLD', wrote: false, reason: 'Hook 配置或父目录在 preflight 后发生变化', file };
  if (text === before) return { ok: true, wrote: false, file, digest };
  try { fault('hooks:before'); } catch (error) { return { ok: false, status: 'HOLD', wrote: false, reason: error.message, file }; }
  if (!sameImage(preimage)) return { ok: false, status: 'HOLD', wrote: false, reason: 'Hook 配置或父目录在写入前发生变化', file };
  try {
    if (text === null) fs.unlinkSync(file); else io.atomic(file, text, mode); fault('hooks:written');
    if (!hookPlanPostimage(plan)) throw new Error('hooks verify failed'); fault('hooks:verified');
    if (!hookPlanPostimage(plan)) throw new Error('Hook postimage 在验证后发生变化');
    return { ok: true, wrote: true, file, digest };
  } catch (error) {
    let recovery = null;
    try { if (!hookPlanPostimage(plan)) recovery = 'Hook postimage 已并发变化'; else restoreImage(preimage); } catch (restore) { recovery = restore.message; }
    return { ok: false, status: 'HOLD', wrote: false, reason: recovery ? `${error.message}；Hook preimage 恢复失败：${recovery}` : error.message, file };
  }
}
function mergeHooks(root, opts = {}) {
  const identity = inspect(root);
  if (!['fresh', 'current', 'previous-12-snapshot', 'previous-11-snapshot', 'previous-10-snapshot', 'previous-09-snapshot', 'official-08', 'official-07', 'official-06', 'owned-05'].includes(identity.kind)) {
    return { ok: false, status: 'HOLD', reason: 'runtime identity 不允许 Hook 配置写入', file: path.join(hookConfigRoot(root), '.codex', 'hooks.json') };
  }
  const configRoot = hookConfigRoot(root), file = path.join(configRoot, '.codex', 'hooks.json'), expected = definition(root);
  const present = fs.existsSync(file), before = present ? fs.readFileSync(file, 'utf8') : null;
  let data = present ? io.json(file) : { description: 'Project hooks', hooks: {} };
  if (!data || !data.hooks || Array.isArray(data.hooks)) return { ok: false, status: 'HOLD', reason: 'invalid .codex/hooks.json', file };
  const previous = identity.kind === 'current' && isExactPrevious06(data, expected)
    && [expected.digest, previous06Digest(expected)].includes(identity.manifest?.hookDefinitionDigest);
  const legacyRoot = identity.kind === 'owned-05' ? root : null;
  const frozenDefinition = identity.kind === 'official-07' ? official07Definition(root) : null;
  const malformed = Object.entries(data.hooks).filter(([, groups]) => !Array.isArray(groups) || groups.some((group) => !group || !Array.isArray(group.hooks)));
  if (malformed.length) return { ok: false, status: 'HOLD', reason: `invalid hook groups: ${malformed.map(([event]) => event).join(',')}`, file };
  const unknown = Object.entries(data.hooks).flatMap(([event, groups]) => groups
    .filter((group) => hookGroupKind(event, group, expected.config.hooks[event]?.[0], previous, expected, legacyRoot, frozenDefinition) === 'unknown').map((group) => `${event}:${group.hooks.map((x) => x.command).join('|')}`));
  if (unknown.length) return { ok: false, status: 'HOLD', reason: `unknown Harness hook: ${unknown.join(',')}`, file };
  const hookPreimage = { fileExisted: present, addedEvents: EVENTS.filter((event) => !Object.hasOwn(data.hooks, event)) };
  let text;
  try {
    text = present ? transformHookDocument(before, expected, { append: true, previous, legacyRoot, frozenDefinition, removeKinds: new Set(['current', 'previous', 'legacy']) })
      : freshHookDocument(expected);
  } catch (error) { return { ok: false, status: 'HOLD', reason: error.message, file }; }
  const preimage = fileImage(file); if (!['file', 'missing'].includes(preimage.type) || preimage.parent.type !== 'directory') return { ok: false, status: 'HOLD', reason: 'Hook 配置路径不是安全普通文件', file };
  const plan = { file, before, text, mode: present ? fs.statSync(file).mode & 0o777 : 0o600, digest: expected.digest, preimage };
  if (opts.write) return { ...writeHookPlan(plan, opts.fault), hookPreimage };
  return { ok: true, wrote: false, file, digest: expected.digest, hookPreimage, plan };
}
const OLD_INSTRUCTIONS = {
  'AGENTS.md': new Set(['4417f9dd90075b53b668c8cab24610d112ba40e8a17741904435f22ecea7cfb4', '80d945a4ecaf76dde35d1a89e1aa624ea5504b703cda485ed7b227697c054128']),
  'CLAUDE.md': new Set(['b7ca0575486c601cc1fc90460c7946e3068733f4e9e0cd2eed47b8f494564162']),
};
const INSTRUCTION_BEGIN = '<!-- HARNESS-LITE:BEGIN -->';
const INSTRUCTION_END = '<!-- HARNESS-LITE:END -->';
const instructionNames = Object.freeze(['AGENTS.md', 'CLAUDE.md']);
function occurrences(text, needle) {
  const positions = []; let at = 0;
  while ((at = text.indexOf(needle, at)) !== -1) { positions.push(at); at += needle.length; }
  return positions;
}
function instructionBlock(text, name) {
  const begins = occurrences(text, INSTRUCTION_BEGIN), ends = occurrences(text, INSTRUCTION_END);
  if (!begins.length && !ends.length) return { ok: true, block: null, start: -1, end: -1 };
  if (begins.length !== 1 || ends.length !== 1 || ends[0] < begins[0]) {
    return { ok: false, reason: `Harness instruction marker 损坏或重复：${name}` };
  }
  const end = ends[0] + INSTRUCTION_END.length;
  return { ok: true, block: text.slice(begins[0], end), start: begins[0], end };
}
function ownedInstructionRow(name, original, installedMode, installedText, ownedSegment) {
  const originalBody = original.type === 'file' && Buffer.isBuffer(original.body) ? original.body : Buffer.alloc(0), segment = Buffer.from(ownedSegment);
  return {
    path: name,
    originalExisted: original.type === 'file',
    originalMode: original.type === 'file' ? original.mode : null,
    originalDigest: original.type === 'file' && /^sha256:[0-9a-f]{64}$/.test(original.digest || '') ? original.digest : `sha256:${io.sha(originalBody)}`,
    installedMode,
    installedBodyDigest: `sha256:${io.sha(Buffer.from(installedText))}`,
    ownedSegmentBase64: segment.toString('base64'),
    ownedSegmentDigest: `sha256:${io.sha(segment)}`,
    blockDigest: `sha256:${io.sha(INSTRUCTION)}`,
  };
}
function validInstructionOwnership(value, instruction = INSTRUCTION) {
  if (!value || value.schemaVersion !== 1 || !Array.isArray(value.files) || value.files.length !== instructionNames.length) return false;
  if (JSON.stringify(value.files.map((row) => row?.path).sort()) !== JSON.stringify([...instructionNames].sort())) return false;
  return value.files.every((row) => {
    if (!row || !instructionNames.includes(row.path) || typeof row.originalExisted !== 'boolean'
      || !Number.isInteger(row.installedMode) || row.installedMode < 0 || row.installedMode > 0o777
      || (row.originalExisted ? !Number.isInteger(row.originalMode) || row.originalMode < 0 || row.originalMode > 0o777 : row.originalMode !== null)
      || !/^sha256:[0-9a-f]{64}$/.test(row.originalDigest || '') || typeof row.ownedSegmentBase64 !== 'string') return false;
    const segment = Buffer.from(row.ownedSegmentBase64, 'base64'), legacyOriginal = typeof row.originalBodyBase64 === 'string' ? Buffer.from(row.originalBodyBase64, 'base64') : null;
    return segment.toString('base64') === row.ownedSegmentBase64
      && (legacyOriginal === null || (legacyOriginal.toString('base64') === row.originalBodyBase64 && row.originalDigest === `sha256:${io.sha(legacyOriginal)}`))
      && row.ownedSegmentDigest === `sha256:${io.sha(segment)}`
      && /^sha256:[0-9a-f]{64}$/.test(row.installedBodyDigest || '')
      && row.blockDigest === `sha256:${io.sha(instruction)}` && segment.length > 0 && occurrences(segment.toString('utf8'), instruction).length === 1
      && (row.originalExisted || row.originalDigest === `sha256:${io.sha(Buffer.alloc(0))}`);
  });
}
function legacyInstructionOwnership(name, before, preimage, blockInfo, text) {
  let start = blockInfo.start, end = blockInfo.end;
  if (end < before.length && before[end] === '\n') end += 1;
  if (start > 0 && before.slice(0, start).endsWith('\n\n')) start -= 1;
  const oldSegment = before.slice(start, end), newSegment = oldSegment.replace(blockInfo.block, INSTRUCTION);
  const generated = start === 0 && end === before.length;
  const originalBody = generated ? Buffer.alloc(0) : Buffer.from(`${before.slice(0, start)}${before.slice(end)}`);
  const original = generated ? { type: 'missing' } : { type: 'file', body: originalBody, mode: preimage.mode };
  return ownedInstructionRow(name, original, preimage.type === 'file' ? preimage.mode : 0o644, text, newSegment);
}
function instructionPlan(root, opts = {}) {
  const boundary = targetBoundary(root, opts); if (!boundary.ok) return { ok: false, status: 'HOLD', reason: boundary.reason, rows: [] };
  const rows = [], priorOwnership = opts.ownership, previousInstruction = opts.previousInstruction || null;
  if (priorOwnership != null && !validInstructionOwnership(priorOwnership, previousInstruction || INSTRUCTION)) return { ok: false, reason: 'instruction ownership receipt 损坏', rows };
  const priorByName = new Map((priorOwnership?.files || []).map((row) => [row.path, row]));
  for (const name of instructionNames) {
    const file = path.join(root, name), preimage = fileImage(file);
    if (!['file', 'missing'].includes(preimage.type) || preimage.parent.type !== 'directory') return { ok: false, reason: `instruction 路径不安全：${name}`, rows };
    const before = preimage.type === 'file' ? preimage.body.toString('utf8') : '', digest = io.sha(before);
    if (preimage.type === 'file' && !Buffer.from(before).equals(preimage.body)) return { ok: false, reason: `instruction 不是可逆 UTF-8 文本：${name}`, rows };
    const parsed = instructionBlock(before, name); if (!parsed.ok) return { ok: false, reason: parsed.reason, rows };
    const block = parsed.block, blockDigest = block ? io.sha(block) : null, prior = priorByName.get(name);
    if (block && ![INSTRUCTION, previousInstruction, PREVIOUS_12_INSTRUCTION, PREVIOUS_10_INSTRUCTION, PREVIOUS_09_INSTRUCTION, PREVIOUS_08_COMPLETION_INSTRUCTION, PREVIOUS_08_INSTRUCTION, PREVIOUS_07_INSTRUCTION, PREVIOUS_06_INSTRUCTION].includes(block)
      && !KNOWN_CURRENT_INSTRUCTION_DIGESTS.has(blockDigest)) return { ok: false, reason: `unknown Harness instruction edit: ${name}`, rows };
    if (block && !prior && opts.identityKind === 'fresh') return { ok: false, reason: `发现没有 runtime ownership 的 Harness instruction block：${name}`, rows };
    if (!block && /Harness Lite|HARNESS-AUTHORIZATION|hl (?:done|park|auth|chain)/i.test(before) && !OLD_INSTRUCTIONS[name].has(digest)) {
      return { ok: false, reason: `unknown legacy Harness instruction: ${name}`, rows };
    }
    const text = block ? before.replace(block, INSTRUCTION) : OLD_INSTRUCTIONS[name].has(digest) ? `${INSTRUCTION}\n`
      : `${before}${before && !before.endsWith('\n') ? '\n' : ''}${before ? '\n' : ''}${INSTRUCTION}\n`;
    let ownership;
    if (prior) {
      if (!block) return { ok: false, reason: `instruction ownership 与文件不一致：${name}`, rows };
      const oldSegment = Buffer.from(prior.ownedSegmentBase64, 'base64').toString('utf8');
      if (occurrences(before, oldSegment).length !== 1 || occurrences(oldSegment, block).length !== 1) return { ok: false, reason: `instruction owned segment 已被修改或出现歧义：${name}`, rows };
      const newSegment = oldSegment.replace(block, INSTRUCTION);
      const original = prior.originalExisted
        ? { type: 'file', digest: prior.originalDigest, mode: prior.originalMode }
        : { type: 'missing' };
      ownership = ownedInstructionRow(name, original, preimage.type === 'file' ? preimage.mode : 0o644, text, newSegment);
    } else if (block) ownership = legacyInstructionOwnership(name, before, preimage, parsed, text);
    else {
      const prefixLength = before.length, ownedSegment = text.slice(prefixLength);
      const original = preimage.type === 'file' && !OLD_INSTRUCTIONS[name].has(digest) ? preimage : { type: 'missing' };
      ownership = ownedInstructionRow(name, original, preimage.type === 'file' ? preimage.mode : 0o644, text, OLD_INSTRUCTIONS[name].has(digest) ? text : ownedSegment);
    }
    rows.push({ file, before, text, changed: text !== before, existed: preimage.type === 'file', mode: preimage.type === 'file' ? preimage.mode : 0o644, preimage, ownership });
  }
  return { ok: true, rows, ownership: { schemaVersion: 1, files: rows.map((row) => row.ownership) } };
}
function mergeInstructions(root, opts = {}) {
  const plan = opts.plan || instructionPlan(root); if (!plan.ok) return plan;
  const changed = [];
  try { if (opts.write) for (const row of plan.rows) if (row.changed) {
    if (!sameImage(row.preimage)) throw new Error(`instruction:${path.basename(row.file)}:concurrent-change`);
    opts.fault?.(`instruction:${path.basename(row.file)}:before`);
    if (!sameImage(row.preimage)) throw new Error(`instruction:${path.basename(row.file)}:concurrent-change`);
    io.atomic(row.file, row.text, row.mode); changed.push(row);
    opts.fault?.(`instruction:${path.basename(row.file)}:written`);
    if (!instructionPostimage(row)) throw new Error(`instruction:${path.basename(row.file)}:postimage-concurrent-change`);
  } } catch (error) {
    const recovery = [];
    for (const row of changed.reverse()) try {
      if (!instructionPostimage(row)) recovery.push(`${path.basename(row.file)}:concurrent-change`); else restoreImage(row.preimage);
    } catch (restore) { recovery.push(`${path.basename(row.file)}:${restore.message}`); }
    return { ok: false, reason: recovery.length ? `${error.message};${recovery.join('|')}` : error.message, rows: plan.rows };
  }
  return plan;
}
function skeleton(root, opts = {}) {
  const hd = path.join(root, 'docs', 'harness');
  const dirs = ['stages', 'leaves', 'unfinished', 'done', 'reports', 'usage'];
  if (opts.write) for (const dir of dirs) fs.mkdirSync(path.join(hd, dir), { recursive: true });
  const files = { 'plan.md': '# 总计划\n\n目标：由用户清晰自然语言建立。\n', 'MISTAKES.md': '# 错题本\n' };
  if (opts.write) for (const [name, text] of Object.entries(files)) if (!fs.existsSync(path.join(hd, name))) fs.writeFileSync(path.join(hd, name), text);
}
function archive05(root, checked, opts = {}) {
  const owned = checked?.manifest?.packages?.core?.files || {}, rows = LEGACY_CONTROL.filter((rel) => (owned[rel] || rel === 'docs/harness/authorization.json') && fs.existsSync(path.join(root, rel)))
    .map((rel) => ({ source: path.join(root, rel), dest: path.join(root, 'docs', 'harness', 'archive', 'legacy-0.5', rel) }));
  const unsafe = rows.map((row) => unsafeParent(root, row.dest)).find(Boolean); if (unsafe) return { ok: false, reason: `legacy archive parent 不安全：${path.relative(root, unsafe)}`, rows };
  const conflict = rows.find((row) => fs.existsSync(row.dest)); if (conflict) return { ok: false, reason: `legacy archive 已存在：${path.relative(root, conflict.dest)}`, rows };
  const moved = [];
  try { if (opts.write) for (const row of rows) { try { io.moveNoClobber(row.source, row.dest, opts.fault); moved.push(row); }
    catch (error) { try { const a = fs.statSync(row.source), b = fs.statSync(row.dest); if (a.dev === b.dev && a.ino === b.ino) fs.unlinkSync(row.dest); } catch { /* foreign dest preserved */ } throw error; } } }
  catch (error) { for (const row of moved.reverse()) try { io.moveNoClobber(row.dest, row.source); } catch { /* source retained by no-clobber */ } return { ok: false, reason: error.message, rows }; }
  return { ok: true, wrote: !!opts.write && rows.length > 0, rows };
}
function restoreInstructionRows(rows) {
  const failures = [];
  for (const row of [...(rows || [])].reverse().filter((item) => item.changed)) {
    try {
      if (!instructionPostimage(row)) { failures.push(`${path.basename(row.file)}:concurrent-change`); continue; }
      restoreImage(row.preimage);
    } catch (error) { failures.push(`${path.basename(row.file)}:${error.message}`); }
  }
  return failures;
}
function instructionRemovalPostimage(row) {
  const actual = fileImage(row.file), prior = row.preimage.parent;
  return (row.text === null ? actual.type === 'missing' : actual.type === 'file' && actual.mode === row.mode && actual.body.equals(row.text))
    && sameWriteParent(row.file, actual.parent, prior);
}
function instructionRemovalPlan(root, ownership, instruction = INSTRUCTION) {
  if (!validInstructionOwnership(ownership, instruction)) return { ok: false, reason: 'instruction ownership receipt 缺失或损坏', rows: [] };
  const rows = [];
  for (const owned of ownership.files) {
    const file = path.join(root, owned.path), preimage = fileImage(file);
    if (preimage.type !== 'file' || preimage.parent.type !== 'directory') return { ok: false, reason: `owned instruction 文件缺失或不安全：${owned.path}`, rows };
    const before = preimage.body.toString('utf8');
    if (!Buffer.from(before).equals(preimage.body)) return { ok: false, reason: `owned instruction 不是可逆 UTF-8 文本：${owned.path}`, rows };
    const parsed = instructionBlock(before, owned.path);
    if (!parsed.ok) return { ok: false, reason: parsed.reason, rows };
    if (!parsed.block || parsed.block !== instruction || `sha256:${io.sha(parsed.block)}` !== owned.blockDigest) {
      return { ok: false, reason: `owned instruction block 已被用户修改：${owned.path}`, rows };
    }
    const segment = Buffer.from(owned.ownedSegmentBase64, 'base64').toString('utf8');
    if (occurrences(before, segment).length !== 1) return { ok: false, reason: `owned instruction segment 已被修改或出现歧义：${owned.path}`, rows };
    const exactPostimage = `sha256:${io.sha(preimage.body)}` === owned.installedBodyDigest, kept = before.replace(segment, ''), keptBody = Buffer.from(kept);
    if (exactPostimage && `sha256:${io.sha(keptBody)}` !== owned.originalDigest) return { ok: false, reason: `instruction ownership preimage digest 不一致：${owned.path}`, rows };
    const text = !owned.originalExisted && kept.length === 0 ? null : keptBody;
    const mode = exactPostimage && owned.originalExisted ? owned.originalMode : preimage.mode;
    rows.push({ file, owned, preimage, before, text, mode, changed: text === null || !preimage.body.equals(text) || preimage.mode !== mode });
  }
  return { ok: true, rows };
}
function writeInstructionRemovalPlan(plan, fault = () => {}) {
  if (!plan.rows.every((row) => sameImage(row.preimage))) return { ok: false, wrote: false, reason: 'instruction 文件或父目录在 uninstall preflight 后变化', rows: plan.rows };
  const changed = [];
  try {
    for (const row of plan.rows.filter((item) => item.changed)) {
      fault(`uninstall:instruction:${path.basename(row.file)}:before`);
      if (!sameImage(row.preimage)) throw new Error(`uninstall:instruction:${path.basename(row.file)}:concurrent-change`);
      if (row.text === null) fs.unlinkSync(row.file); else io.atomic(row.file, row.text, row.mode);
      changed.push(row); fault(`uninstall:instruction:${path.basename(row.file)}:written`);
      if (!instructionRemovalPostimage(row)) throw new Error(`uninstall:instruction:${path.basename(row.file)}:postimage-concurrent-change`);
    }
    return { ok: true, wrote: changed.length > 0, rows: plan.rows };
  } catch (error) {
    const recovery = [];
    for (const row of changed.reverse()) try {
      if (!instructionRemovalPostimage(row)) recovery.push(`${path.basename(row.file)}:concurrent-change`); else restoreImage(row.preimage);
    } catch (restore) { recovery.push(`${path.basename(row.file)}:${restore.message}`); }
    return { ok: false, wrote: false, reason: recovery.length ? `${error.message};${recovery.join('|')}` : error.message, rows: plan.rows };
  }
}
function restoreInstructionRemovalRows(result) {
  const failures = [];
  if (!result?.ok || !result.wrote) return failures;
  for (const row of [...result.rows].reverse().filter((item) => item.changed)) try {
    if (!instructionRemovalPostimage(row)) failures.push(`${path.basename(row.file)}:concurrent-change`); else restoreImage(row.preimage);
  } catch (error) { failures.push(`${path.basename(row.file)}:${error.message}`); }
  return failures;
}
function reverseArchive(rows) {
  const failures = [];
  for (const row of [...(rows || [])].reverse()) {
    try {
      if (!fs.existsSync(row.dest)) continue;
      if (fs.existsSync(row.source)) { failures.push(`${path.relative(path.dirname(row.source), row.source)}:source-exists`); continue; }
      io.moveNoClobber(row.dest, row.source);
    } catch (error) { failures.push(`${path.basename(row.source)}:${error.message}`); }
  }
  return failures;
}
function rollbackSwap(root, swapped) {
  if (!swapped) return [];
  const failures = [], stable = path.join(root, RUNTIME), rollback = swapped.rollbackRuntime;
  failures.push(...restoreInstallationAnchor(swapped.anchorResult));
  let failedCarrier = null, failed = null, moved = false;
  try {
    if (fs.existsSync(stable)) {
      if (!sameRuntimeImage(stable, swapped.newPreimage)) failures.push('new-runtime:concurrent-change');
      else { failedCarrier = reserveRuntimeCarrier(root, 'failed-install'); failed = failedCarrier.runtime; moveDirectoryNoClobber(stable, failed); moved = true; }
    }
  } catch (error) { failures.push(`new-runtime:${error.message}`); }
  try {
    if (rollback && fs.existsSync(rollback) && !fs.existsSync(stable)) {
      if (!sameRuntimeImage(rollback, swapped.rollbackPreimage) || !sameImage(swapped.rollbackCarrier.fence)) failures.push('old-runtime:concurrent-change');
      else moveDirectoryNoClobber(rollback, stable);
    }
  } catch (error) { failures.push(`old-runtime:${error.message}`); }
  try {
    if (moved && (!rollback || fs.existsSync(stable))) {
      const cleanup = removeRuntimeIfExact(root, failed, swapped.newPreimage, failedCarrier.fence);
      if (cleanup) failures.push(`failed-runtime:${cleanup}`);
      else { const carrierCleanup = removeRuntimeCarrier(root, failedCarrier); if (carrierCleanup) failures.push(`failed-runtime:${carrierCleanup}`); }
    }
  } catch (error) { failures.push(`failed-runtime:${error.message}`); }
  if (swapped.rollbackCarrier && !fs.existsSync(rollback) && fs.existsSync(stable)) {
    const receiptCleanup = removeRollbackReceipt(swapped.rollbackOwnership); if (receiptCleanup) failures.push(`rollback:${receiptCleanup}`);
    const cleanup = removeRuntimeCarrier(root, swapped.rollbackCarrier); if (cleanup) failures.push(`rollback:${cleanup}`);
  }
  return failures;
}
function hookPlanPostimage(plan) {
  const actual = fileImage(plan.file), parent = actual.parent, prior = plan.preimage.parent;
  return (plan.text === null ? actual.type === 'missing' : actual.type === 'file' && actual.mode === plan.mode && actual.body.equals(Buffer.from(plan.text)))
    && sameWriteParent(plan.file, parent, prior);
}
function install(root, opts = {}) {
  root = path.resolve(root); const boundary = targetBoundary(root, opts); if (!boundary.ok) return boundaryHold(boundary);
  const source = opts.source || sourceRoot(), surfaceDifferences = surfacePreflight(root);
  if (surfaceDifferences.length) return { status: 'HOLD', kind: 'unsafe-surface', written: 0, differences: surfaceDifferences, reason: '安装 surface type/symlink 不安全' };
  const before = inspect(root, source, opts);
  const profile = opts.profile || before.manifest?.profile || (before.kind === 'official-07' ? 'project' : 'project');
  if (!['project', 'managed'].includes(profile)) return { status: 'HOLD', kind: before.kind, written: 0, differences: ['profile'], reason: 'profile 必须是 project 或 managed' };
  const authorizationPlan = authorization.prepare(root, { operation: 'install', identityKind: before.kind });
  if (!authorizationPlan.ok) return { status: 'HOLD', kind: before.kind, written: 0, differences: [authorizationPlan.reason], reason: authorizationPlan.reason };
  const desiredPaths = runtimePaths(source), desiredDigest = io.digest(source, desiredPaths, desiredMode);
  const sourceChanged = before.kind === 'current' && (JSON.stringify([...before.manifest.managedPaths].sort()) !== JSON.stringify(desiredPaths)
    || before.manifest.packageDigest !== desiredDigest);
  const definitionChanged = before.kind === 'current' && before.manifest.hookDefinitionDigest !== definition(root).digest;
  if (before.kind === 'official-06' && !opts.upgrade) return { status: 'HOLD', kind: before.kind, written: 0, differences: ['official-06-upgrade'], reason: '官方 0.6 runtime 需要显式 upgrade' };
  if (before.kind === 'official-07' && !opts.upgrade) return { status: 'HOLD', kind: before.kind, written: 0, differences: ['official-07-upgrade'], reason: '官方 0.7 runtime 需要显式 upgrade' };
  if (before.kind === 'official-08' && !opts.upgrade) return { status: 'HOLD', kind: before.kind, written: 0, differences: ['official-08-upgrade'], reason: '官方 0.8 runtime 需要显式 upgrade' };
  if (before.kind === 'previous-12-snapshot' && !opts.upgrade) return { status: 'HOLD', kind: before.kind, written: 0,
    differences: ['previous-12-snapshot-upgrade'], reason: '0.12.0 retained candidate runtime 需要显式 upgrade' };
  if (before.kind === 'previous-11-snapshot' && !opts.upgrade) return { status: 'HOLD', kind: before.kind, written: 0,
    differences: ['previous-11-snapshot-upgrade'], reason: '0.11.0 retained candidate runtime 需要显式 upgrade' };
  if (before.kind === 'previous-10-snapshot' && !opts.upgrade) return { status: 'HOLD', kind: before.kind, written: 0,
    differences: ['previous-10-snapshot-upgrade'], reason: '0.10.0 retained candidate runtime 需要显式 upgrade' };
  if (before.kind === 'previous-09-snapshot' && !opts.upgrade) return { status: 'HOLD', kind: before.kind, written: 0,
    differences: ['previous-09-snapshot-upgrade'], reason: '0.9.1 working-copy snapshot fixture 需要显式 upgrade' };
  const allowed = before.kind === 'fresh' || before.kind === 'current'
    || (['previous-12-snapshot', 'previous-11-snapshot', 'previous-10-snapshot', 'previous-09-snapshot', 'official-08', 'official-07', 'official-06', 'owned-05'].includes(before.kind) && opts.upgrade);
  if (!allowed) return { status: 'HOLD', kind: before.kind, written: 0, differences: before.differences,
    reason: before.kind === 'legacy-unowned' ? '无 ownership legacy：Core 全部写入口零写 HOLD，转独立一次性迁移包' : 'runtime identity 不允许增量混装' };
  if (sourceChanged && !opts.upgrade) return { status: 'HOLD', kind: before.kind, written: 0, differences: ['source-package-digest'], reason: 'source package 变化需要显式 upgrade' };
  const instruction = instructionPlan(root, { ownership: before.manifest?.instructionOwnership, identityKind: before.kind,
    previousInstruction: before.kind === 'previous-12-snapshot' ? PREVIOUS_12_INSTRUCTION : null });
  if (!instruction.ok) return { status: 'HOLD', kind: before.kind, written: 0, differences: [instruction.reason], reason: instruction.reason };
  const rollbackPlan = rollbackRemovalPlan(root, before.manifest?.rollbackCarriers || []);
  if (!rollbackPlan.ok) return { status: 'HOLD', kind: before.kind, written: 0, differences: [rollbackPlan.reason], reason: rollbackPlan.reason };
  const anchorPlan = prepareInstallationAnchor(root, before);
  if (!anchorPlan.ok) return { status: 'HOLD', kind: before.kind, written: 0, differences: [anchorPlan.reason], reason: anchorPlan.reason };
  const managedApi = require('./managed.js'), needsGlobal = profile === 'managed' || before.manifest?.profile === 'managed';
  if (needsGlobal && !opts.globalRoot) return { status: 'HOLD', kind: before.kind, written: 0, differences: ['globalRoot'], reason: 'managed profile 迁移需要 globalRoot' };
  const hookPreflight = profile === 'managed' ? removeHooks(root) : mergeHooks(root);
  if (!hookPreflight.ok) return { status: 'HOLD', kind: before.kind, written: 0, differences: [hookPreflight.reason], reason: hookPreflight.reason };
  const hookPreimage = ['current', 'previous-12-snapshot', 'previous-11-snapshot', 'previous-10-snapshot', 'previous-09-snapshot', 'official-08'].includes(before.kind) && validHookPreimage(before.manifest?.hookPreimage)
    ? before.manifest.hookPreimage : hookPreflight.hookPreimage || { fileExisted: true, addedEvents: [] };
  const registryPlan = opts.globalRoot ? managedApi.prepareProject(opts.globalRoot, root, profile === 'managed', desiredDigest) : null;
  if (registryPlan && !registryPlan.ok) return { status: 'HOLD', kind: before.kind, written: 0, differences: [registryPlan.reason], reason: registryPlan.reason };
  const archivePlan = before.kind === 'owned-05' ? archive05(root, before) : { ok: true, rows: [] };
  if (!archivePlan.ok) return { status: 'HOLD', kind: before.kind, written: 0, differences: [archivePlan.reason], reason: archivePlan.reason };
  if (!opts.write) return { status: 'READY', kind: before.kind, written: 0, differences: [], dryRun: true };
  let archive = archivePlan, instructionResult = { ok: true, rows: instruction.rows }, hooks = { ok: true, wrote: false }, registry = { ok: true, wrote: false }, authorizationResult = { ok: true, wrote: false, written: [] };
  let swapped = null;
  try {
    if (before.kind !== 'current' || sourceChanged || definitionChanged || before.manifest?.profile !== profile) {
      const currentImage = before.kind === 'fresh' ? null : runtimeImage(path.join(root, RUNTIME));
      const extensions = ['current', 'previous-12-snapshot', 'previous-11-snapshot', 'previous-10-snapshot', 'previous-09-snapshot', 'official-08'].includes(before.kind) ? before.manifest.extensions : {};
      swapped = swap(root, stage(root, source, opts.fault, profile, hookPreimage, extensions, instruction.ownership,
        before.manifest?.rollbackCarriers || []), currentImage, anchorPlan, opts.fault);
      if (hookPreflight.plan?.preimage.type === 'missing' && !sameImage(hookPreflight.plan.preimage)
        && swapped.anchorResult?.createdNow.includes('.codex')) {
        const refreshed = fileImage(hookPreflight.plan.file);
        if (refreshed.type === 'missing' && refreshed.parent.type === 'directory' && refreshed.parent.path === path.dirname(hookPreflight.plan.file)) {
          hookPreflight.plan.preimage = refreshed;
        }
      }
    }
    archive = before.kind === 'owned-05' ? archive05(root, before, { write: true, fault: opts.fault }) : archivePlan;
    if (!archive.ok) throw new Error(archive.reason);
    instructionResult = mergeInstructions(root, { write: true, fault: opts.fault, plan: instruction }); if (!instructionResult.ok) throw new Error(instructionResult.reason);
    if (profile === 'project' && registryPlan) { registry = managedApi.applyProject(registryPlan, opts.fault); if (!registry.ok) throw new Error(registry.reason); }
    hooks = hookPreflight.plan ? writeHookPlan(hookPreflight.plan, opts.fault) : { ok: true, wrote: false }; if (!hooks.ok) throw new Error(hooks.reason);
    if (profile === 'managed' && registryPlan) { registry = managedApi.applyProject(registryPlan, opts.fault); if (!registry.ok) throw new Error(registry.reason); }
    authorizationResult = authorization.apply(authorizationPlan, opts.fault); if (!authorizationResult.ok) throw new Error(authorizationResult.reason);
    skeleton(root, { write: true });
    return { status: 'INSTALLED', kind: before.kind, written: before.kind === 'current' && !sourceChanged && !definitionChanged ? 0 : 1,
      rollback: swapped?.rollback || null, archive, hooks, registry, authorization: authorizationResult, instructions: instructionResult.rows, manifest: io.json(path.join(root, MANIFEST)) };
  } catch (error) {
    const recovery = [];
    recovery.push(...authorization.rollback(authorizationResult));
    recovery.push(...managedApi.rollbackProject(registry));
    if (hooks.ok && hooks.wrote) { try { if (hookPlanPostimage(hookPreflight.plan)) restoreImage(hookPreflight.plan.preimage); else recovery.push('hooks:concurrent-change'); } catch (restore) { recovery.push(`hooks:${restore.message}`); } }
    recovery.push(...restoreInstructionRows(instructionResult.ok ? instructionResult.rows : []));
    recovery.push(...reverseArchive(archive.rows)); recovery.push(...rollbackSwap(root, swapped));
    if (anchorPlan.createdDirectories.includes('.claude')) recovery.push(...removeEmptyAnchorDirectories(root, ['.claude']));
    return { status: 'PARTIAL', kind: before.kind, written: 0, differences: [error.message, ...recovery], reason: error.message,
      rollback: swapped?.rollback || null, archive, hooks, registry, instructions: instructionResult.rows };
  }
}
function configured(root) {
  const boundary = targetBoundary(root); if (!boundary.ok) return false;
  const file = path.join(hookConfigRoot(root), '.codex', 'hooks.json'), data = io.json(file), expected = definition(root);
  if (!data?.hooks) return false;
  return EVENTS.every((event) => (data.hooks[event] || []).some((group) => JSON.stringify(canonical(group)) === JSON.stringify(canonical(expected.config.hooks[event][0]))));
}
function hostDefinition(root, profile, globalRoot) {
  if (profile !== 'managed') {
    const value = definition(root); return { ...value, source: 'project', sourcePath: path.join(hookConfigRoot(root), '.codex', 'hooks.json') };
  }
  if (!globalRoot) return null;
  const managedApi = require('./managed.js'), target = managedApi.layout(globalRoot), config = managedApi.hooksDefinition(target.gateway, VERSION);
  return { config, command: target.gateway, digest: `sha256:${io.sha(JSON.stringify(canonical(config.hooks)))}`, source: 'system', sourcePath: target.definition };
}
const normalizeHostId = (value) => String(value || '-').replace(/[^A-Za-z0-9._-]/g, '_').slice(0, 120);
function trustedHostSnapshot(snapshot, profile, expected) {
  return snapshot?.definitionDigest === expected.digest && snapshot.profile === profile && !(snapshot.warnings || []).length && !(snapshot.errors || []).length
    && EVENTS.every((event) => {
      const item = snapshot.events?.[event]; return item?.matched === true && item.enabled === true && !!item.currentHash
        && (profile === 'managed' ? item.isManaged === true && item.trustStatus === 'managed' : item.isManaged !== true && item.trustStatus === 'trusted');
    });
}
function trustedHostLedger(host, profile, expected, root) {
  const before = host.before, after = host.after, fingerprint = `sha256:${io.sha(fs.realpathSync(root))}`;
  return !!expected && host.source === 'codex-hooks-list' && typeof host.connectionId === 'string' && !!host.connectionId
    && host.cwdFingerprint === fingerprint && trustedHostSnapshot(before, profile, expected) && trustedHostSnapshot(after, profile, expected) && EVENTS.every((event) => {
      const left = before.events?.[event], right = after.events?.[event];
      return left?.matched === true && right?.matched === true && left.enabled === true && right.enabled === true
        && !!left.currentHash && left.currentHash === right.currentHash
        && (profile === 'managed' ? left.isManaged === true && right.isManaged === true && left.trustStatus === 'managed' && right.trustStatus === 'managed'
          : left.isManaged !== true && right.isManaged !== true && left.trustStatus === 'trusted' && right.trustStatus === 'trusted');
    });
}
function eventJoin(hostEvents, host, event, expected, packageDigest) {
  const currentHash = host.after?.events?.[event]?.currentHash, lower = Date.parse(host.before?.at || ''), upper = Date.parse(host.after?.at || '');
  const records = (hostEvents.records || []).filter((row) => row.event === event && Number.isFinite(lower) && Number.isFinite(upper)
    && Date.parse(row.at) >= lower && Date.parse(row.at) <= upper
    && row.definitionDigest === expected.digest && row.packageDigest === packageDigest && row.handlerHash === currentHash
    && row.connectionId === host.connectionId && typeof row.runId === 'string' && row.runId);
  const completed = records.filter((row) => row.phase === 'completed').sort((a, b) => String(a.at).localeCompare(String(b.at)));
  if (!completed.length) return { observed: false, verdict: 'missing' };
  const runId = completed.at(-1).runId, starts = records.filter((row) => row.runId === runId && row.phase === 'started'), finishes = records.filter((row) => row.runId === runId && row.phase === 'completed');
  if (starts.length > 1 || finishes.length > 1 || finishes.some((row) => row.receiptVerdict === 'ambiguous')) return { observed: false, verdict: 'ambiguous', runId };
  const exact = starts.length === 1 && finishes.length === 1 && finishes[0].status === 'completed' && finishes[0].receiptVerdict === 'exact'
    && starts[0].thread === finishes[0].thread && starts[0].turn === finishes[0].turn;
  return { observed: exact, verdict: exact ? 'exact' : 'missing', runId };
}
function health(root, opts = {}) {
  const boundary = targetBoundary(root, opts); if (!boundary.ok) return { profile: 'unknown', installed: false, configured: false, trusted: false, policyTrusted: false,
    observed: Object.fromEntries(EVENTS.map((event) => [event, false])), evidenceJoin: Object.fromEntries(EVENTS.map((event) => [event, 'missing'])), effective: false,
    nativePrePush: { configured: false, probed: false }, status: 'HOLD', reason: boundary.reason };
  const checked = verify06(root, opts), value = checked.manifest || {}, def = definition(root);
  const profile = value.profile || 'project', expected = hostDefinition(root, profile, opts.globalRoot), managedApi = profile === 'managed' ? require('./managed.js') : null;
  const host = io.json(path.join(root, 'docs', 'harness', 'usage', 'host-health.json'), {}), hostEvents = io.json(path.join(root, 'docs', 'harness', 'usage', 'host-events.json'), { events: {} });
  const configuredValue = profile === 'project' ? configured(root) : !!expected && checked.ok && !configured(root)
    && managedApi.verifyGlobal(opts.globalRoot).ok && managedApi.projectState(opts.globalRoot, root).active;
  const trusted = checked.ok && !!expected && trustedHostLedger(host, profile, expected, root), joins = Object.fromEntries(EVENTS.map((event) => [event,
    trusted && hostEvents.source === 'codex-app-server-hooks' && hostEvents.connectionId === host.connectionId
      ? eventJoin(hostEvents, host, event, expected, value.packageDigest) : { observed: false, verdict: 'missing' }]));
  const seen = Object.fromEntries(EVENTS.map((event) => [event, joins[event].observed]));
  const native = nativeState(root, value.packageDigest);
  const nativeConfigured = checked.ok && native.configured, nativeProbed = nativeConfigured && native.probed;
  return { profile, installed: checked.ok, configured: configuredValue, trusted, policyTrusted: profile === 'managed' && trusted, observed: seen, evidenceJoin: Object.fromEntries(EVENTS.map((event) => [event, joins[event].verdict])),
    effective: checked.ok && configuredValue && trusted && EVENTS.every((event) => seen[event]) && nativeConfigured && nativeProbed,
    nativePrePush: { configured: nativeConfigured, probed: nativeProbed } };
}
const HOST_EVENT = { SessionStart: 'sessionStart', UserPromptSubmit: 'userPromptSubmit', Stop: 'stop', PreToolUse: 'preToolUse' };
function recordHostList(root, response, opts = {}) {
  const boundary = targetBoundary(root, opts); if (!boundary.ok) return boundaryHold(boundary, { events: {} });
  const checked = verify06(root), profile = checked.manifest?.profile || 'project';
  if (opts.write && !checked.ok) return { ok: false, status: 'HOLD', reason: 'runtime identity 不允许写宿主健康账' };
  const entry = response?.data?.find((x) => samePath(x.cwd, root)) || { hooks: [], warnings: [], errors: [] };
  const expected = hostDefinition(root, profile, opts.globalRoot), events = {};
  if (!expected) return { ok: false, status: 'HOLD', reason: 'managed host list 需要 globalRoot', events: {} };
  for (const event of EVENTS) {
    const matcher = expected.config.hooks[event][0].matcher || null, matches = (entry.hooks || []).filter((item) => item.eventName === HOST_EVENT[event]
      && item.command === expected.command && (item.matcher || null) === matcher
      && (profile === 'managed' ? item.isManaged === true && ['system', 'managed'].includes(item.source) : item.source === 'project')
      && samePath(item.sourcePath, expected.sourcePath)), found = matches.length === 1 ? matches[0] : null;
    events[event] = found ? { matched: true, ambiguous: false, enabled: found.enabled === true, trustStatus: found.trustStatus,
      isManaged: found.isManaged === true, currentHash: found.currentHash || null, sourcePath: found.sourcePath }
      : { matched: false, ambiguous: matches.length > 1, enabled: false, isManaged: false, trustStatus: null, currentHash: null };
  }
  const file = path.join(root, 'docs', 'harness', 'usage', 'host-health.json'), prior = io.json(file, {}), connectionId = typeof opts.connectionId === 'string' && opts.connectionId ? opts.connectionId : null;
  const snapshot = { profile, at: new Date().toISOString(), definitionDigest: expected.digest, warnings: entry.warnings || [], errors: entry.errors || [], events };
  const before = prior.source === 'codex-hooks-list' && prior.connectionId === connectionId ? prior.after : null;
  const value = { source: 'codex-hooks-list', profile, at: snapshot.at, connectionId, cwdFingerprint: `sha256:${io.sha(fs.realpathSync(root))}`,
    definitionDigest: expected.digest, warnings: snapshot.warnings, errors: snapshot.errors, events, before, after: snapshot };
  if (opts.write) io.atomic(file, `${JSON.stringify(value, null, 2)}\n`);
  return value;
}
function recordHostEvent(root, notification, opts = {}) {
  const boundary = targetBoundary(root, opts); if (!boundary.ok) return boundaryHold(boundary);
  const run = notification?.run || {}, event = Object.entries(HOST_EVENT).find(([, value]) => value === run.eventName)?.[0];
  const checked = verify06(root), profile = checked.manifest?.profile || 'project', expected = hostDefinition(root, profile, opts.globalRoot), def = expected || definition(root), host = io.json(path.join(root, 'docs', 'harness', 'usage', 'host-health.json'), {});
  if (!checked.ok) return { ok: false, reason: 'runtime identity 不允许写宿主事件账' };
  if (!expected) return { ok: false, reason: 'managed host event 需要 globalRoot' };
  const listed = host.after?.events?.[event], phase = notification?.method === 'hook/started' ? 'started' : notification?.method === 'hook/completed' ? 'completed' : null;
  const valid = !!event && !!phase && typeof run.id === 'string' && !!run.id && run.handlerType === 'command'
    && (profile === 'managed' ? run.isManaged === true && ['system', 'managed'].includes(run.source) : run.source === 'project')
    && samePath(run.sourcePath || '/', expected.sourcePath) && (phase === 'started' || run.status === 'completed')
    && trustedHostSnapshot(host.after, profile, expected) && listed?.currentHash && opts.connectionId === host.connectionId;
  if (!valid) return { ok: false, reason: `${notification?.method || 'unknown'} 与 Harness definition/connection 不匹配` };
  const file = path.join(root, 'docs', 'harness', 'usage', 'host-events.json');
  const value = io.json(file, { source: 'codex-app-server-hooks', connectionId: host.connectionId, records: [] });
  if (value.connectionId !== host.connectionId) { value.records = []; value.connectionId = host.connectionId; }
  value.source = 'codex-app-server-hooks';
  const row = { at: new Date().toISOString(), phase, runId: run.id, event, handlerHash: listed.currentHash, status: phase === 'completed' ? run.status : null,
    thread: notification.threadId || null, turn: notification.turnId || null, connectionId: host.connectionId,
    definitionDigest: def.digest, packageDigest: checked.manifest?.packageDigest || null };
  let receiptRows = [];
  if (profile === 'managed') {
      const global = require('./managed.js'), target = global.layout(opts.globalRoot), manifest = global.verifyGlobal(opts.globalRoot).manifest;
      receiptRows = io.read(target.receipts, '').split('\n').filter(Boolean).flatMap((line) => { try { return [JSON.parse(line)]; } catch { return []; } });
      row.expectedGeneration = manifest?.generation ?? null;
  } else receiptRows = io.read(path.join(root, 'docs', 'harness', 'usage', '.observed.jsonl'), '').split('\n').filter(Boolean).flatMap((line) => { try { return [JSON.parse(line)]; } catch { return []; } });
  if (phase === 'started') row.receiptCursor = receiptRows.length;
  if (phase === 'completed') {
    const starts = (value.records || []).filter((item) => item.phase === 'started' && item.runId === run.id && item.event === event
      && item.connectionId === host.connectionId && item.thread === (notification.threadId || null)
      && item.turn === (notification.turnId || null)), start = starts.length === 1 ? starts[0] : null;
    const candidates = start && Number.isInteger(start.receiptCursor) ? receiptRows.slice(start.receiptCursor) : [];
    const receiptTurnMatches = (item) => event === 'SessionStart' ? item.turn === null
      : item.turn === (profile === 'managed' ? (notification.turnId || null) : (notification.turnId ? normalizeHostId(notification.turnId) : null));
    const receiptMatches = profile === 'managed' ? candidates.filter((item) => item.event === event && item.session === (notification.threadId || '-')
      && receiptTurnMatches(item) && item.decision === 'executed' && item.generation === start.expectedGeneration
      && item.digestPrefix === checked.manifest.packageDigest.slice(7, 19)) : candidates.filter((item) => item.event === event
        && item.session === normalizeHostId(notification.threadId) && receiptTurnMatches(item)
        && item.decision === 'executed' && item.definitionDigest === def.digest && item.packageDigest === checked.manifest.packageDigest);
    row.receiptVerdict = starts.length > 1 ? 'ambiguous' : receiptMatches.length === 1 ? 'exact' : receiptMatches.length ? 'ambiguous' : 'missing';
    if (receiptMatches.length === 1) row.receipt = { at: receiptMatches[0].at || null, decision: 'executed',
      generation: Number.isInteger(receiptMatches[0].generation) ? receiptMatches[0].generation : null, digestPrefix: receiptMatches[0].digestPrefix || null };
  }
  value.records = [...(Array.isArray(value.records) ? value.records : []), row];
  if (opts.write) io.atomic(file, `${JSON.stringify(value, null, 2)}\n`);
  return { ok: phase === 'started' || row.receiptVerdict === 'exact', event, phase, receiptVerdict: row.receiptVerdict || null, value,
    ...(phase === 'completed' && row.receiptVerdict !== 'exact' ? { reason: `runtime receipt ${row.receiptVerdict}` } : {}) };
}
function removeHooks(root, opts = {}) {
  const identity = inspect(root), file = path.join(hookConfigRoot(root), '.codex', 'hooks.json'), present = fs.existsSync(file), data = io.json(file), expected = definition(root);
  const hookPreimage = validHookPreimage(identity.manifest?.hookPreimage) ? identity.manifest.hookPreimage
    : { fileExisted: present, addedEvents: EVENTS.filter((event) => !Object.hasOwn(data?.hooks || {}, event)) };
  if (!['fresh', 'current', 'previous-11-snapshot', 'previous-10-snapshot', 'previous-09-snapshot', 'official-08', 'official-07', 'official-06', 'owned-05'].includes(identity.kind)) {
    return { ok: false, wrote: false, reason: 'runtime identity 不允许 Hook 配置写入' };
  }
  if (!present) return { ok: true, wrote: false, hookPreimage };
  if (!data || !data.hooks || Array.isArray(data.hooks)) return { ok: false, wrote: false, reason: 'invalid .codex/hooks.json' };
  const malformed = Object.entries(data.hooks).filter(([, groups]) => !Array.isArray(groups) || groups.some((group) => !group || !Array.isArray(group.hooks)));
  if (malformed.length) return { ok: false, wrote: false, reason: `invalid hook groups: ${malformed.map(([event]) => event).join(',')}` };
  const previous = identity.kind === 'current' && isExactPrevious06(data, expected)
    && [expected.digest, previous06Digest(expected)].includes(identity.manifest?.hookDefinitionDigest);
  for (const event of EVENTS) {
    const groups = data.hooks[event] || [];
    if (groups.some((group) => ['legacy', 'unknown'].includes(hookGroupKind(event, group, expected.config.hooks[event][0], previous, expected)))) return { ok: false, wrote: false, reason: `unknown Harness hook: ${event}` };
  }
  const before = fs.readFileSync(file, 'utf8');
  let text; try { text = transformHookDocument(before, expected,
    { append: false, previous, legacyRoot: null, pruneEvents: new Set(hookPreimage.addedEvents), removeKinds: new Set(['current', 'previous']) }); }
  catch (error) { return { ok: false, wrote: false, reason: error.message }; }
  if (!hookPreimage.fileExisted && before === freshHookDocument(expected)) text = null;
  const preimage = fileImage(file);
  if (preimage.type !== 'file' || preimage.parent.type !== 'directory') return { ok: false, wrote: false, reason: 'Hook 配置路径不是安全普通文件' };
  const plan = { file, before, text, mode: preimage.mode, digest: expected.digest, preimage };
  if (opts.write) return writeHookPlan(plan, opts.fault);
  return { ok: true, wrote: false, hookPreimage, plan };
}
function uninstall(root, opts = {}) {
  root = path.resolve(root); const boundary = targetBoundary(root, opts); if (!boundary.ok) return boundaryHold(boundary);
  const checked = (() => { const current = verify06(root, opts); return current.ok ? current : verifyPrevious12Snapshot(root); })();
  if (!checked.ok) return { status: 'HOLD', differences: checked.differences, reason: checked.reason, removed: false };
  const authorizationPlan = authorization.prepare(root, { operation: 'uninstall', identityKind: checked.kind });
  if (!authorizationPlan.ok) return { status: 'HOLD', differences: [authorizationPlan.reason], reason: authorizationPlan.reason, removed: false };
  if (Object.keys(checked.manifest.extensions || {}).length) return { status: 'HOLD', differences: ['extensions-installed'], removed: false };
  const managedApi = require('./managed.js');
  if (checked.manifest.profile === 'managed' && !opts.globalRoot) return { status: 'HOLD', differences: ['globalRoot'], reason: 'managed uninstall 需要 globalRoot', removed: false };
  const registryPlan = opts.globalRoot ? managedApi.prepareProject(opts.globalRoot, root, false, checked.manifest.packageDigest) : null;
  if (registryPlan && !registryPlan.ok) return { status: 'HOLD', differences: [registryPlan.reason], reason: registryPlan.reason, removed: false };
  const hookPlan = removeHooks(root), nativePlan = removeNative(root), instructionsPlan = instructionRemovalPlan(root, checked.manifest.instructionOwnership,
    checked.kind === 'previous-12-snapshot' ? PREVIOUS_12_INSTRUCTION : INSTRUCTION),
    rollbackPlan = rollbackRemovalPlan(root, checked.manifest.rollbackCarriers), anchorPlan = installationAnchorRemovalPlan(root, checked);
  if (!hookPlan.ok || !nativePlan.ok || !instructionsPlan.ok || !rollbackPlan.ok || !anchorPlan.ok) {
    const reason = hookPlan.reason || nativePlan.reason || instructionsPlan.reason || rollbackPlan.reason || anchorPlan.reason;
    return { status: 'HOLD', differences: [reason], reason, removed: false };
  }
  if (!opts.write) return { status: 'READY', removed: false };
  const stable = path.join(root, RUNTIME), tomb = path.join(root, '.claude', `.harness-lite.uninstall-${Date.now()}`);
  let hooks, native, instructions, anchorRemoval, registry = { ok: true, wrote: false }; const rollbackTombs = [];
  try {
    fs.renameSync(stable, tomb); opts.fault?.('uninstall:tomb');
    for (const [index, row] of rollbackPlan.rows.entries()) {
      if (!sameRuntimeImage(row.runtime, row.image) || !sameImage(row.receiptImage) || !sameImage(row.fence)) throw new Error(`rollback carrier 在 uninstall preflight 后变化：${row.spec.container}`);
      const moved = path.join(root, '.claude', `.harness-lite.uninstall-rollback-${process.pid}-${Date.now()}-${index}`);
      if (fs.existsSync(moved)) throw new Error(`rollback uninstall tomb 已存在：${path.basename(moved)}`);
      fs.renameSync(row.container, moved); rollbackTombs.push({ row, moved }); opts.fault?.('uninstall:rollback-tomb');
    }
    if (registryPlan) { registry = managedApi.applyProject(registryPlan, opts.fault); if (!registry.ok) throw new Error(registry.reason); }
    instructions = writeInstructionRemovalPlan(instructionsPlan, opts.fault); if (!instructions.ok) throw new Error(instructions.reason);
    hooks = hookPlan.plan ? writeHookPlan(hookPlan.plan, opts.fault) : { ok: true, wrote: false };
    if (!hooks.ok) throw new Error(hooks.reason);
    native = nativePlan.plan ? writeNativeRemovalPlan(nativePlan.plan, opts.fault) : { ok: true, wrote: false };
    if (!native.ok) throw new Error(native.reason);
    anchorRemoval = writeInstallationAnchorRemoval(anchorPlan, opts.fault); if (!anchorRemoval.ok) throw new Error(anchorRemoval.reason);
    opts.fault?.('uninstall:commit');
    for (const item of rollbackTombs) fs.rmSync(item.moved, { recursive: true });
    fs.rmSync(tomb, { recursive: true });
    const anchorDirectoryCleanup = removeEmptyAnchorDirectories(root, anchorPlan.createdDirectories);
    return { status: 'UNINSTALLED', removed: true, hooks, native, instructions, registry, rollbackCarriersRemoved: rollbackTombs.length,
      anchorRemoved: true, anchorDirectoryCleanup };
  } catch (error) {
    const recovery = [];
    recovery.push(...restoreInstallationAnchorRemoval(anchorRemoval));
    recovery.push(...managedApi.rollbackProject(registry));
    try { if (hooks?.ok && hooks.wrote) restoreImage(hookPlan.plan.preimage); } catch (restore) { recovery.push(`hooks:${restore.message}`); }
    try { if (native?.ok && native.wrote) for (const image of [nativePlan.plan.backup, nativePlan.plan.hook, nativePlan.plan.marker]) restoreImage(image); } catch (restore) { recovery.push(`native:${restore.message}`); }
    recovery.push(...restoreInstructionRemovalRows(instructions));
    for (const item of [...rollbackTombs].reverse()) try {
      if (fs.existsSync(item.row.container)) recovery.push(`rollback:${path.basename(item.row.container)}:source-exists`);
      else if (fs.existsSync(item.moved)) fs.renameSync(item.moved, item.row.container);
    } catch (restore) { recovery.push(`rollback:${restore.message}`); }
    try { if (!fs.existsSync(stable) && fs.existsSync(tomb)) fs.renameSync(tomb, stable); } catch (restore) { recovery.push(`runtime:${restore.message}`); }
    return { status: 'PARTIAL', removed: false, differences: [error.message, ...recovery], reason: error.message, hooks, native, instructions, registry, anchorRemoval };
  }
}
function loadExtension(dir) {
  const data = io.json(path.join(dir, 'manifest.json'));
  if (data?.version !== 1 || !/^[a-z0-9][a-z0-9-]*$/.test(data.id || '') || !data.packageVersion || !data.files || Array.isArray(data.files)) throw new Error('扩展 manifest 不合规');
  const base = fs.realpathSync(dir), prefix = `${RUNTIME}/extensions/${data.id}/`, files = [];
  for (const [target, source] of Object.entries(data.files)) {
    const cleanTarget = target.replaceAll('\\', '/'); if (!cleanTarget.startsWith(prefix)) throw new Error(`扩展目标必须位于 ${prefix}`);
    const abs = fs.realpathSync(io.safe(dir, source)), stat = fs.lstatSync(abs);
    if (!abs.startsWith(`${base}${path.sep}`) || !stat.isFile() || stat.isSymbolicLink()) throw new Error(`扩展源文件不合规：${source}`);
    files.push({ target: cleanTarget.slice(RUNTIME.length + 1), source: abs });
  }
  return { ...data, files: files.sort((a, b) => a.target.localeCompare(b.target)) };
}
function verifyExtension(root, id) {
  const core = verify06(root), spec = core.manifest?.extensions?.[id]; if (!core.ok || !spec) return { ok: false, differences: ['extension-manifest'] };
  const runtime = path.join(root, RUNTIME), actual = io.list(path.join(runtime, 'extensions', id), true).map((x) => path.relative(runtime, x).replaceAll('\\', '/')).sort(), differences = [];
  for (const rel of spec.managedPaths) { const type = io.inspect(runtime, rel).type; if (type !== 'file') differences.push(`${type}:${rel}`); }
  for (const rel of actual.filter((x) => !spec.managedPaths.includes(x))) differences.push(`extra:${rel}`);
  let digest; try { digest = io.digest(runtime, spec.managedPaths); } catch (error) { differences.push(`identity:${error.message}`); }
  if (digest !== spec.packageDigest) differences.push('packageDigest'); return { ok: differences.length === 0, differences, spec };
}
function installExtension(root, dir, opts = {}) {
  root = path.resolve(root); const boundary = targetBoundary(root, opts); if (!boundary.ok) return boundaryHold(boundary);
  const core = verify06(root, opts); if (!core.ok) return { status: 'HOLD', differences: core.differences };
  const anchorPlan = prepareInstallationAnchor(root, { kind: 'current', manifest: core.manifest });
  if (!anchorPlan.ok) return { status: 'HOLD', differences: [anchorPlan.reason], reason: anchorPlan.reason };
  const ext = loadExtension(path.resolve(dir)), prior = core.manifest.extensions?.[ext.id], priorCheck = prior ? verifyExtension(root, ext.id) : null;
  if (prior && !priorCheck.ok) return { status: 'HOLD', differences: priorCheck.differences };
  const parent = path.join(root, '.claude'), staged = path.join(parent, `.harness-lite.ext-stage-${process.pid}-${Date.now()}`), managedPaths = ext.files.map((x) => x.target);
  for (const item of ext.files) { const dest = path.join(staged, item.target); fs.mkdirSync(path.dirname(dest), { recursive: true }); fs.copyFileSync(item.source, dest); fs.chmodSync(dest, 0o644); }
  const packageDigest = io.digest(staged, managedPaths), spec = { packageVersion: ext.packageVersion, managedPaths, packageDigest };
  if (prior && JSON.stringify(canonical(prior)) === JSON.stringify(canonical(spec))) { fs.rmSync(staged, { recursive: true }); return { status: opts.write ? 'INSTALLED' : 'READY', id: ext.id, written: 0 }; }
  if (prior && !opts.upgrade) { fs.rmSync(staged, { recursive: true }); return { status: 'HOLD', differences: ['extension-upgrade-required'] }; }
  if (!opts.write) { fs.rmSync(staged, { recursive: true }); return { status: 'READY', id: ext.id, written: 0 }; }
  const extensionsRoot = path.join(root, RUNTIME, 'extensions'), extensionsRootExisted = fs.existsSync(extensionsRoot),
    stable = path.join(extensionsRoot, ext.id), rollback = path.join(root, '.claude', `.harness-lite.ext-rollback-${ext.id}-${process.pid}-${Date.now()}`);
  const ledger = path.join(root, MANIFEST), ledgerBefore = fs.readFileSync(ledger, 'utf8'); let old = false, fresh = false, ledgerChanged = false, anchorResult = null;
  try {
    fs.mkdirSync(path.dirname(stable), { recursive: true }); if (fs.existsSync(stable)) { fs.renameSync(stable, rollback); old = true; opts.fault?.('extension:old'); }
    fs.renameSync(path.join(staged, 'extensions', ext.id), stable); fresh = true; fs.rmSync(staged, { recursive: true }); opts.fault?.('extension:new');
    const value = io.json(ledger); value.extensions = { ...(value.extensions || {}), [ext.id]: spec };
    io.atomic(ledger, `${JSON.stringify(value, null, 2)}\n`, 0o600); ledgerChanged = true; opts.fault?.('extension:manifest');
    anchorResult = writeInstallationAnchor(root, anchorPlan, opts.fault);
    if (!verifyExtension(root, ext.id).ok) throw new Error('extension verify failed'); opts.fault?.('extension:verified');
    if (old) fs.rmSync(rollback, { recursive: true });
    return { status: 'INSTALLED', id: ext.id, written: 1, rollback: null };
  } catch (error) {
    const recovery = restoreInstallationAnchor(anchorResult);
    try { if (ledgerChanged) io.atomic(ledger, ledgerBefore, 0o600); } catch (restore) { recovery.push(`extension-manifest:${restore.message}`); }
    try { if (fresh && fs.existsSync(stable)) fs.rmSync(stable, { recursive: true, force: true }); } catch (restore) { recovery.push(`extension-new:${restore.message}`); }
    try { if (old && fs.existsSync(rollback)) fs.renameSync(rollback, stable); } catch (restore) { recovery.push(`extension-old:${restore.message}`); }
    if (!extensionsRootExisted) try { if (fs.existsSync(extensionsRoot) && fs.readdirSync(extensionsRoot).length === 0) fs.rmdirSync(extensionsRoot); } catch (restore) { recovery.push(`extension-root:${restore.message}`); }
    if (fs.existsSync(staged)) try { fs.rmSync(staged, { recursive: true }); } catch { /* disposable stage remains diagnosable */ }
    if (recovery.length) error.message = `${error.message};${recovery.join('|')}`; throw error;
  }
}
function uninstallExtension(root, id, opts = {}) {
  const boundary = targetBoundary(root, opts); if (!boundary.ok) return boundaryHold(boundary);
  const checked = verifyExtension(root, id); if (!checked.ok) return { status: 'HOLD', differences: checked.differences };
  const core = verify06(root, opts), anchorPlan = prepareInstallationAnchor(root, { kind: 'current', manifest: core.manifest });
  if (!anchorPlan.ok) return { status: 'HOLD', differences: [anchorPlan.reason], reason: anchorPlan.reason };
  if (!opts.write) return { status: 'READY', removed: false };
  const stable = path.join(root, RUNTIME, 'extensions', id), tomb = path.join(root, '.claude', `.harness-lite.ext-uninstall-${id}-${process.pid}-${Date.now()}`),
    ledger = path.join(root, MANIFEST), before = fs.readFileSync(ledger, 'utf8');
  let moved = false, ledgerChanged = false, anchorResult = null;
  try {
    fs.renameSync(stable, tomb); moved = true; opts.fault?.('extension-uninstall:tomb');
    const value = io.json(ledger); delete value.extensions[id]; io.atomic(ledger, `${JSON.stringify(value, null, 2)}\n`, 0o600); ledgerChanged = true; opts.fault?.('extension-uninstall:manifest');
    anchorResult = writeInstallationAnchor(root, anchorPlan, opts.fault);
    const verified = verify06(root, opts); if (!verified.ok) throw new Error(`extension uninstall verify failed:${verified.differences.join(',')}`);
    opts.fault?.('extension-uninstall:verified'); fs.rmSync(tomb, { recursive: true }); return { status: 'UNINSTALLED', removed: true };
  } catch (error) {
    const recovery = restoreInstallationAnchor(anchorResult);
    try { if (ledgerChanged) io.atomic(ledger, before, 0o600); } catch (restore) { recovery.push(`extension-manifest:${restore.message}`); }
    try { if (moved && !fs.existsSync(stable) && fs.existsSync(tomb)) fs.renameSync(tomb, stable); } catch (restore) { recovery.push(`extension-runtime:${restore.message}`); }
    if (recovery.length) error.message = `${error.message};${recovery.join('|')}`; throw error;
  }
}
function installNative(root, opts = {}) {
  const boundary = targetBoundary(root, opts); if (!boundary.ok) return boundaryHold(boundary);
  const checked = verify06(root, opts); if (!checked.ok) return { ok: false, reason: `runtime 未通过 identity：${checked.differences.join(',')}` };
  const common = (gitRun(['rev-parse', '--git-common-dir'], { cwd: root, encoding: 'utf8' }).stdout || '').trim();
  if (!common) return { ok: false, reason: 'not a git repository' };
  const dispatcherDigest = `sha256:${io.sha(fs.readFileSync(path.join(root, RUNTIME, 'hooks', 'dispatcher.js')))}`;
  const dir = path.resolve(root, common, 'hooks'), file = path.join(dir, 'pre-push'), backup = `${file}.harness-lite.foreign`, script = nativeScript(backup, dispatcherDigest);
  const markerFile = path.join(root, '.codex', 'harness-lite', 'native.json'), hookImage = fileImage(file), backupImage = fileImage(backup), markerImage = fileImage(markerFile);
  if (![hookImage, backupImage, markerImage].every((image) => ['file', 'missing'].includes(image.type) && image.parent.type === 'directory')) return { ok: false, reason: 'native 安装 surface 不是安全普通文件', file, backup };
  let marker = null;
  if (markerImage.type === 'file') { try { marker = JSON.parse(markerImage.body.toString('utf8')); } catch { return { ok: false, reason: 'native marker JSON 损坏', file, backup }; } }
  const looksHarness = hookImage.type === 'file' && hookImage.body.includes('dispatcher="$root/.claude/harness-lite/hooks/dispatcher.js"')
    && hookImage.body.includes('exec node "$dispatcher" --native-pre-push');
  const priorOwned = !!marker?.configured && /^sha256:[0-9a-f]{64}$/.test(marker.dispatcherDigest || '') && marker.commonDir === path.resolve(root, common)
    && hookImage.type === 'file' && marker.hookDigest === `sha256:${io.sha(hookImage.body)}`
    && /^sha256:[0-9a-f]{64}$/.test(marker.packageDigest || '') && looksHarness;
  if (marker && !priorOwned) return { ok: false, reason: 'native marker 或 common pre-push identity 漂移', file, backup };
  if (!marker && (backupImage.type === 'file' || looksHarness)) return { ok: false, reason: '发现无有效 marker 的 Harness/backup 现场，保持零写 HOLD', file, backup };
  const current = nativeState(root, checked.manifest.packageDigest);
  if (current.configured) return { ok: true, configured: true, wrote: false, file, backup, dispatcherDigest };
  const markerText = `${JSON.stringify({ configured: true, probed: false, hookDigest: `sha256:${io.sha(script)}`,
    dispatcherDigest, packageDigest: checked.manifest.packageDigest, commonDir: path.resolve(root, common) }, null, 2)}\n`;
  if (!opts.write) return { ok: true, configured: false, wrote: false, file, backup, dispatcherDigest };
  const images = [hookImage, backupImage, markerImage];
  try {
    if (!images.every(sameImage)) throw new Error('native 安装 surface 在 preflight 后发生变化'); opts.fault?.('native-install:before');
    if (!images.every(sameImage)) throw new Error('native 安装 surface 在写入前发生变化');
    fs.mkdirSync(dir, { recursive: true });
    if (!priorOwned && hookImage.type === 'file') io.atomic(backup, hookImage.body, hookImage.mode); opts.fault?.('native-install:backup');
    io.atomic(file, script, 0o755); opts.fault?.('native-install:hook'); io.atomic(markerFile, markerText, 0o600); opts.fault?.('native-install:marker');
    if (!nativeState(root, checked.manifest.packageDigest).configured) throw new Error('native 安装后 identity 校验失败');
    return { ok: true, configured: true, wrote: true, file, backup, dispatcherDigest };
  } catch (error) {
    const recovery = [];
    for (const image of [backupImage, hookImage, markerImage]) try { restoreImage(image); } catch (restore) { recovery.push(restore.message); }
    return { ok: false, configured: false, wrote: false, reason: recovery.length ? `${error.message}；native preimage 恢复失败：${recovery.join('|')}` : error.message, file, backup };
  }
}
function probeNative(root, opts = {}) {
  const boundary = targetBoundary(root, opts); if (!boundary.ok) return boundaryHold(boundary, { probed: false });
  const checked = verify06(root, opts);
  if (!checked.ok) return { ok: false, status: 'HOLD', probed: false, reason: `runtime 未通过 identity：${checked.differences.join(',')}` };
  const native = nativeState(root, checked.manifest?.packageDigest);
  if (!native.configured) return { ok: false, probed: false, reason: 'native pre-push 未配置或 identity 漂移' };
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'hl-native-probe-')), remote = path.join(dir, 'remote.git');
  try {
    const init = gitRun(['init', '--bare', '-q', remote], { encoding: 'utf8' });
    const run = init.status === 0 ? gitRun(['push', '--dry-run', remote, 'HEAD:refs/heads/harness-lite-probe'], { cwd: root, encoding: 'utf8' }) : init;
    const probed = run.status !== 0 && /Harness pre-push/.test(`${run.stdout || ''}${run.stderr || ''}`);
    if (opts.write) { const value = io.json(path.join(root, '.codex', 'harness-lite', 'native.json'), {}); io.atomic(path.join(root, '.codex', 'harness-lite', 'native.json'), `${JSON.stringify({ ...value, probed,
      probedHookDigest: native.actualDigest, probedAt: new Date().toISOString(), probe: 'disposable-local-bare-remote' }, null, 2)}\n`); }
    return { ok: probed, probed, remote: 'disposable-local-bare-remote', reason: probed ? null : '未观察到 native pre-push' };
  } finally { fs.rmSync(dir, { recursive: true, force: true }); }
}

function nativeScript(backup, dispatcherDigest) {
  const expected = String(dispatcherDigest || '').replace(/^sha256:/, '');
  return `#!/bin/sh\nroot=$(/usr/bin/git rev-parse --show-toplevel 2>/dev/null) || exit 0\ndispatcher="$root/${RUNTIME}/hooks/dispatcher.js"\nmarker="$root/.codex/harness-lite/native.json"\nactual=$(/usr/bin/shasum -a 256 "$dispatcher" 2>/dev/null | /usr/bin/awk '{print $1}')\nif [ "$actual" = ${JSON.stringify(expected)} ]; then\n  if [ ! -f "$marker" ]; then echo "Harness pre-push：native marker 缺失，fail closed" >&2; exit 1; fi\n  exec ${JSON.stringify(path.resolve(process.execPath))} "$dispatcher" --native-pre-push "$@" --foreign ${JSON.stringify(backup)}\nfi\nif [ -f "$marker" ]; then echo "Harness pre-push：runtime identity 损坏，fail closed" >&2; exit 1; fi\nif [ -x ${JSON.stringify(backup)} ]; then exec ${JSON.stringify(backup)} "$@"; fi\nexit 0\n`;
}
	function nativeState(root, packageDigest) {
	  const boundary = targetBoundary(root); if (!boundary.ok) return { configured: false, probed: false, reason: boundary.reason };
	  const value = io.json(path.join(root, '.codex', 'harness-lite', 'native.json'), {}), common = (gitRun(['rev-parse', '--git-common-dir'], { cwd: root, encoding: 'utf8' }).stdout || '').trim();
  const file = common ? path.join(path.resolve(root, common, 'hooks'), 'pre-push') : null, backup = file ? `${file}.harness-lite.foreign` : null;
  const actualDigest = file && fs.existsSync(file) ? `sha256:${io.sha(fs.readFileSync(file))}` : null, expectedDigest = backup ? `sha256:${io.sha(nativeScript(backup, value.dispatcherDigest))}` : null;
  const configured = /^sha256:[0-9a-f]{64}$/.test(packageDigest || '') && value.configured === true && value.commonDir === (common ? path.resolve(root, common) : null) && value.hookDigest === actualDigest
    && actualDigest === expectedDigest && value.packageDigest === packageDigest;
  return { ...value, file, backup, actualDigest, configured, probed: configured && value.probed === true && value.probedHookDigest === actualDigest };
}
function writeNativeRemovalPlan(plan, fault = () => {}) {
  const images = [plan.marker, plan.hook, plan.backup];
  if (!images.every(sameImage)) return { ok: false, status: 'HOLD', wrote: false, reason: 'native pre-push 或 marker 在 preflight 后发生变化' };
  try { fault('native:before'); } catch (error) { return { ok: false, status: 'HOLD', wrote: false, reason: error.message }; }
  if (!images.every(sameImage)) return { ok: false, status: 'HOLD', wrote: false, reason: 'native pre-push 或 marker 在写入前发生变化' };
  try {
    if (plan.backup.type === 'file') io.atomic(plan.hook.file, plan.backup.body, plan.backup.mode); else fs.unlinkSync(plan.hook.file);
    fault('native:hook'); fs.rmSync(plan.marker.file, { force: true }); fault('native:marker');
    if (plan.backup.type === 'file') fs.rmSync(plan.backup.file, { force: true }); fault('native:backup');
    return { ok: true, wrote: true };
  } catch (error) {
    const recovery = [];
    for (const image of [plan.backup, plan.hook, plan.marker]) try { restoreImage(image); } catch (restore) { recovery.push(restore.message); }
    return { ok: false, status: 'HOLD', wrote: false, reason: recovery.length ? `${error.message}；native preimage 恢复失败：${recovery.join('|')}` : error.message };
  }
}
function removeNative(root, opts = {}) {
  const markerFile = path.join(root, '.codex', 'harness-lite', 'native.json'), marker = fileImage(markerFile);
  if (!['missing', 'file'].includes(marker.type) || marker.parent.type !== 'directory') return { ok: false, wrote: false, reason: 'native marker 不是安全普通文件' };
  const common = (gitRun(['rev-parse', '--git-common-dir'], { cwd: root, encoding: 'utf8' }).stdout || '').trim();
  const hookFile = common ? path.join(path.resolve(root, common, 'hooks'), 'pre-push') : null;
  const physical = hookFile ? fileImage(hookFile) : null;
  const harnessWrapper = physical?.type === 'file' && physical.body.includes('--native-pre-push');
  if (marker.type === 'missing') return harnessWrapper
    ? { ok: false, wrote: false, reason: 'native marker 缺失但 common pre-push 仍是 Harness wrapper' }
    : { ok: true, wrote: false, plan: null };
  let value; try { value = JSON.parse(marker.body.toString('utf8')); } catch { return { ok: false, wrote: false, reason: 'native marker JSON 损坏' }; }
  if (!common || !physical || physical.type !== 'file' || physical.parent.type !== 'directory') return { ok: false, wrote: false, reason: 'native pre-push 不是安全普通文件' };
  const state = nativeState(root, value.packageDigest); if (!state.configured) return { ok: false, wrote: false, reason: 'native pre-push identity 漂移' };
  const backup = fileImage(state.backup);
  if (!['missing', 'file'].includes(backup.type) || backup.parent.type !== 'directory') return { ok: false, wrote: false, reason: 'native backup 不是安全普通文件' };
  const plan = { marker, hook: physical, backup };
  if (opts.write) return writeNativeRemovalPlan(plan, opts.fault);
  return { ok: true, wrote: false, plan };
}

module.exports = { VERSION, SOURCE_COMMIT, RUNTIME, MANIFEST, INSTALLATION_ANCHOR, EVENTS, INSTRUCTION, PREVIOUS_12_INSTRUCTION, PREVIOUS_12_SNAPSHOT, PREVIOUS_10_INSTRUCTION, PREVIOUS_11_SNAPSHOT, PREVIOUS_10_SNAPSHOT,
  PREVIOUS_09_INSTRUCTION, PREVIOUS_09_SNAPSHOT,
  PREVIOUS_08_COMPLETION_INSTRUCTION, PREVIOUS_08_INSTRUCTION, PREVIOUS_07_INSTRUCTION, PREVIOUS_06_INSTRUCTION,
  OFFICIAL_06, OFFICIAL_07, OFFICIAL_08, CURRENT_REQUIRED_RUNTIME_PATHS, runtimePaths, hookConfigRoot,
  definition, official07Definition, official08Definition, manifest, targetBoundary, installationAnchorFile, verifyInstallationAnchor,
  verify06, verifyPrevious12Snapshot, verifyPrevious11Snapshot, verifyPrevious10Snapshot, verifyPrevious09Snapshot, verifyOfficial08, verifyOfficial07, verifyOfficial06, verifyOwned05, legacyUnowned, inspect, surfacePreflight, instructionPlan,
  install, configured, health, recordHostList, recordHostEvent, uninstall, loadExtension, verifyExtension,
  installExtension, uninstallExtension, nativeScript, nativeState, installNative, probeNative };
