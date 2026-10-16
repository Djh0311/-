# 证据基线

## 本次重建直接验证

- `autocapture` 单元测试：154 项；
- `autocapture` strict verifier：16 个文件、15 个 manifest entry；
- `parser_candidate` 单元测试：41 项；
- 测试均使用本地代码和合成、脱值 fixture；
- 没有读取历史 raw capture、真实响应、凭据或私人消息；
- 没有运行真实网络、微信或浏览器 UI。

最终 commit、tree、逐文件摘要和命令退出码记录在根目录 `MIGRATION_MANIFEST.md`。历史报告只用于保留资格结论，不作为当前代码快照的测试收据。

## 历史路线证据

历史原件还证明了工程终态和失败边界，包括 CP1 实际读取但业务记录为 0、R2B 两次单静帧均 0 accepted、multilayer 的五个候选仍未证明因果，以及 reference-crawler v8 敏感停工。这些事实用于防止重复工作，但不是当前代码测试、来源资格、live 或发布收据。

历史原件、证据等级和完整性载体见 `docs/history/README.md` 与 `docs/history/original-carriers.md`。
