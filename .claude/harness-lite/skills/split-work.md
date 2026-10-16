---
name: split-work
description: 在 current leaf 内拆 work unit，让产品连续推进
---

先在唯一 current leaf 内拆 unit。每个 unit 只带完成结果、相关设计/事实、允许与禁止写面、入口、依赖、未知项和结果合同；设计与事实分开，缺失就写 `UNKNOWN`。用户目标和完整完成标准不清楚时，先补清楚再派发。

并行只看真实依赖和写面：无依赖且写面分离可以并行；重叠、共享状态或运行时互斥就串行、重拆或指定唯一 integration owner。`reported_complete` 不解锁下游，只有主管按完成标准验收并绑定 `evidenceRef` 的 `accepted` 才解锁。blocked/partial 只影响依赖它的下游，独立分支照常推进。

实现时只引用当前 decision package 的 `focus`、`decisionQuestion` 和 `nextAction`，不要在 skill 里复述九类事件或整套状态机。保留现有边界：activity/progress 分开；heartbeat 是 300000ms 只读观察；沉默、思考、等待和文件/测试数量不算 semantic progress。只有直接证据显示 stopped/stall、实际 blocker、跑偏、越界或共享冲突，才建议指导模型介入。

真实 agent 调用、等待和介入由指导模型使用宿主工具完成；Harness 只从项目内 runtime 读回状态并记账。推进前自查：这些 unit 加起来等于 leaf 目标，且 Harness 进度没有冒充产品结果。用户目标清楚时直接继续，不增加内部确认。
