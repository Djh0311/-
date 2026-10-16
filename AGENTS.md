# 项目协作边界

## 明确禁区

- 不把原始值、值哈希、自由日志或敏感错误文本写入代码、fixture、合同、报告或 Git；
- 不把 `parser_candidate/` 描述成正式 Parser、Provider 或已集成产品；
- 不修改其它 worktree、`_archive/`（含旧 v2 仓库和旧 stage2/dispatch 目录的原字节归档）或仓外归档；
- 不 commit、push、发布或开启真实能力，除非用户另行明确授权。

## 项目知识索引

- 当前产品计划与未启动任务：`docs/harness/plan.md`；计划和任务文件不构成实现或真实运行授权。
- 历史成果与使用规则：`docs/history/README.md`。
- 仓库结构、`_archive/` 位置与旧路径映射：`docs/archive-boundary.md`；结构迁移收据与回退方法：`MIGRATION_MANIFEST.md`。

## 当前允许的工作

- 维护 `autocapture/` 的离线、默认拒绝安全基础；
- 在合成、脱值 fixture 上维护隔离 `parser_candidate/`；
- 在合成、脱值 fixture 上维护 `collection_adapter/`、`collection_core/` 的离线部分（严格合同、内存 fake、离线入口与测试）；其真实采集/宿主/bridge 路径的启用仍属真实能力，须按窗口显式授权与 latch，不在此离线范围内；
- 维护通用 closed-object 合同和无值资格文档；
- 运行 README 中的离线单测、strict verifier、静态检查和 Git 检查。

真实来源资格、Provider build、正式 Parser、网络/UI 能力或任何 latch 变更，都属于新的产品决定，必须有新的事实输入和用户明确授权。

## Harness 维护验证

- Devin 适配验证：`node --test .devin/hooks/harness-lite.test.cjs`，只使用可丢弃的合成 fixture。
- `.devin/hooks.v1.json` 仅在以仓库根为工作根的新 Devin 会话中加载。
- Devin 适配只读注入上下文并保留 push 停点，不生成 Codex 观测账、执行授权或 Stop 自动续跑。
- 适配单测、配置检查和手动对子进程传入 Hook JSON 均为离线证据，不能写成真实宿主 loaded/observed/effective。

<!-- HARNESS-LITE:BEGIN -->
Harness Lite 面向 GPT-6 Astra：用户指令决定目标、范围和权限，内部载体不能扩权；current leaf 只是工作投影。先用直接证据判断用户结果，再推进普通且已授权的可恢复工作；只派发、记账、测试绿或自报不等于结果完成，缺结果保持 complete=false、productResult=incomplete。reported unit 先按自己的完成标准和 evidenceRef 验收，只有 accepted 才解锁真实依赖它的下游；没有对象不虚构暂停目标。局部故障只影响当前问题或 unit，独立分支继续。Astra 从完整请求和上下文补齐安全范围并持续推进；能直接查证就不问，只有不可替代的用户选择才问。表达先给结论，再给证据和缺口；按需审阅技能与常驻指令，冲突时说明来源。委派须有真实工具和质量/时间收益；小任务不形式拆分，独立写面可并行，依赖/共享写面决定串行。普通层五次不同有效语义失败后进入 Astra xhigh 恢复，默认三次、问题级 1..5；工具、队列、传输、认证、中间红和沉默不计，耗尽只影响当前问题。只有真实硬风险才精确拦截并说明动作、目标、边界、风险和用户决定。未知记 UNKNOWN，不扩大为全局 blocked；每次事件只给一个 focus、decisionQuestion、nextAction；carrier 不截断伪装完整。Harness 异常只停用受影响能力，按 ownership 可逆撤回，不拖死宿主；测试按行为风险选择，用户日常 Harness 命令为 0。
<!-- HARNESS-LITE:END -->
