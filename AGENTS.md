# 项目协作边界

本项目仍处于离线基础阶段。所有实现和验证默认在本地合成、脱值 fixture 上完成；当前资格结论和 latch 不因代码测试通过而自动提升。

## 明确禁区

- `LIVE_CAPTURE_LATCH` 和 `EXECUTION_LATCH` 保持关闭；
- 不启动真实网络、微信、浏览器 UI 或真实采集；
- 不修改系统代理、CA、keychain、管理员配置或系统级网络设置；
- 不读取真实流量、响应、凭据、Cookie、会话、私人消息或历史 raw capture 正文；
- 不把原始值、值哈希、自由日志或敏感错误文本写入代码、fixture、合同、报告或 Git；
- 不把 `parser_candidate/` 描述成正式 Parser、Provider 或已集成产品；
- 不修改其它 worktree、旁边的 stage2/dispatch 目录或仓外归档；
- 不 commit、push、发布或开启真实能力，除非用户另行明确授权。

## 当前允许的工作

- 维护 `autocapture/` 的离线、默认拒绝安全基础；
- 在合成、脱值 fixture 上维护隔离 `parser_candidate/`；
- 维护通用 closed-object 合同和无值资格文档；
- 运行 README 中的离线单测、strict verifier、静态检查和 Git 检查。

真实来源资格、Provider build、正式 Parser、网络/UI 能力或任何 latch 变更，都属于新的产品决定，必须有新的事实输入和用户明确授权。

<!-- HARNESS-LITE:BEGIN -->
Harness Lite 内部规则：用户用清晰自然语言给目标和边界，直接生效；用户日常命令为 0。读取 docs/harness/ 的 plan、唯一 current leaf 及其 stage；leaf 是模型维护的工作投影，不是授权票或范围最高权威。发现仍服务同一目标的必要相邻路径，模型更新 leaf 并继续；按当前目标影响、后果、可信可能和直接证据做最小处理，低概率低影响理论问题只报告。普通 leaf 范围外只报告；明确“不许动”的路径和 push 按既有停点处理。文件位置是生命周期事实；退场只原子移动一个文件。报告必须分 Harness、产品、证据、载体，不把 working copy 或离线 fixture 冒充发布或真实运行。
<!-- HARNESS-LITE:END -->
