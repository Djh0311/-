# 证据基线

## 本次重建直接验证

- `autocapture` 单元测试：154 项；
- `autocapture` strict verifier：16 个文件、15 个 manifest entry；
- `parser_candidate` 单元测试：41 项；
- 测试均使用本地代码和合成、脱值 fixture；
- 没有读取历史 raw capture、真实响应、凭据或私人消息；
- 没有运行真实网络、微信或浏览器 UI。

最终 commit、tree、逐文件摘要和命令退出码记录在根目录 `MIGRATION_MANIFEST.md`。历史报告只用于保留资格结论，不作为当前代码快照的测试收据。
