# 架构

## Autocapture 离线安全基础

```text
精确策略与 endpoint selector
→ 请求/响应元数据门
→ 有界、一次性内存 lease
→ 严格 JSON 与 value-free shape
→ 敏感/未知/预算异常停止
→ 原子、无覆盖 Publisher
```

`autocapture/` 不负责取得真实来源。它只定义输入已经由外部显式提供时，怎样在最小能力面内失败关闭地分类、投影和发布无值结构。

## Parser 候选

```text
合成脱值 event
→ capture contract 与 read-scope 绑定
→ family/version profile registry
→ candidate parser
→ 同 observation 的结构化候选结果
```

`parser_candidate/` 是隔离验证面，未接入 `autocapture/`、正式 Provider、Publisher 或业务发布链。测试 fixture 只证明离线候选行为，不证明真实来源语义。

## 合同

`contracts/` 使用 closed object、固定 `schema_version` 和语义校验边界，描述资格、Provider 控制面、观察、字段、业务记录、证据和 value-free stop。JSON Schema 通过只是结构证据，不会自动提升来源资格或执行 latch。
