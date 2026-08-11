# 来源与执行资格

```text
SOURCE_QUALIFICATION=NO_QUALIFIED_SOURCE
PROVIDER_QUALIFIED_FOR_BUILD=false
EXECUTION_LATCH=CLOSED
LIVE_CAPTURE_LATCH=CLOSED
P02_FORMAL_PARSER=NOT_ENTERED
```

## 保留下来的历史结论

- 旧项目没有提供可供当前项目读取的脱敏事件输入；
- 暂停的真实观察任务没有消费事件，也没有产生真实观察；
- 后续检查在事件消费前停止，因此不能把历史 raw archive 或外部现场当作当前项目输入；
- 这些结论是产品资格事实，不是要在新 Harness 中恢复的旧 leaf、stage 或授权票。

## 资格提升条件

只有新的、闭合的资格任务同时提供来源依据、用途、冻结输入锁、value-free shape、family/version、同观察语义、能力和隐私合同，并取得用户明确授权后，才能重新评估 Provider build 或执行 latch。
