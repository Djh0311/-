# 当前状态

## 一句话结论

项目已经有可验证的离线采集安全基础和隔离 Parser 候选，但没有合格的真实来源或正式 Provider；所有真实执行闩门保持关闭。

## 当前可用

- `autocapture/` 默认 `DISARMED`，只在精确、闭合的策略和短时内存 lease 下处理输入；
- shape 输出只保留结构信息，敏感、未知或不满足预算的输入失败关闭；
- Publisher 使用原子、无覆盖发布，并在发布后复核；
- `parser_candidate/` 可在合成、脱值 fixture 上验证同一 read scope、profile 注册和字段绑定；
- `contracts/` 提供通用、无来源值的闭合 JSON Schema 基线。

## 当前不可声称

- 没有 `PROVIDER_QUALIFIED_FOR_BUILD`；
- 没有正式 Parser 或 Provider；
- 没有真实 loader、真实网络、微信或浏览器 UI 采集证明；
- 没有真实观察、真实运行或发布通过；
- 历史 H36 只保留“暂停且未产生真实观察”的事实，不在新仓恢复为 current work。
