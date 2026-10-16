# 来源与执行资格

```text
SOURCE_QUALIFICATION=NO_QUALIFIED_SOURCE
PROVIDER_QUALIFIED_FOR_BUILD=false
EXECUTION_LATCH=CLOSED
LIVE_CAPTURE_LATCH=CLOSED
P02_FORMAL_PARSER=NOT_ENTERED
```

## 保留下来的历史结论

- 历史 CP1 和 R2B 做过受控实验，但没有产生可接受的同观察业务记录，不能作为当前 Provider；
- H31/H34 产生了无值 shape 和合成 fixture，只支持离线 Parser 候选，不证明稳定 family/version、同观察或 provenance；
- H36 没有消费事件、没有产生真实观察；H37/H38 在事件消费前因没有项目可读的脱敏输入停止；
- 因此不能把历史 raw archive、外部现场、元数据候选或合成 fixture 当作当前项目输入；
- 这些结论是产品资格事实，不是要在新 Harness 中恢复的旧 leaf、stage 或授权票。

各路线直接证据和证据上限见 `docs/history/route-ledger.md`。

## 资格提升条件

只有新的、闭合的资格任务同时提供来源依据、用途、冻结输入锁、value-free shape、family/version、同观察语义、能力和隐私合同，并取得用户明确授权后，才能重新评估 Provider build 或执行 latch。

## 新计划的衔接

2026-10-08 的 [产品计划](harness/plan.md)安排 P25 接入准备、P26 真实识别与首份结果、P28/P31 真实关联及字段适配。接口或字段尚未知时，先明确受控识别的事实需求和读取边界，不能用合成 profile 充当真实来源合同。

任务进展（2026-10-16）：P25–P28 已 accepted 并退场、P29/P31 active/incomplete（采集已停、两 latch=CLOSED）；P30、P32 真实采集入口、P33 未启动。这些任务进展、真实结果交付、本轮计划修订、旧资格任务名称、离线测试通过及单次运行收据，均不自动改变本页资格结论；计划验收、当次运行范围和正式 Provider/Parser 资格分别判断。
