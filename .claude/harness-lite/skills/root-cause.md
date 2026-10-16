---
name: root-cause
description: 出 bug 先查根因再动代码
---

先分清：当前改动造成的红、当前验收选中的红，还是无关的既有失败。只针对前两类查根因；先写一句“我认为原因是 X，因为 Y”，用一个最小复现验证，验证后再改代码。一次只验证一个猜测。

失败升级只计有直接证据的实质语义失败；工具、测试/lint 中间红、provider/传输/权限、缺证和同根多断言不算。重复同一根因只记一次，重复走已否定路线标为 drift，不凑次数。记录必须绑定 leaf、稳定 work-unit、`acceptanceGate`、`stableProblemFingerprint`、明确 `modelFamily`、`evidenceRef`、primary cause 和本次不同点；缺项就 `UNKNOWN/HOLD`。

失败、恢复和接受仍由项目内 runtime 的 delegation API 记账，报告里的 recovery 计数必须来自同一次落盘后的 ledger。普通层同一问题五个不同有效失败后进入 GPT-6 Astra xhigh 问题级恢复；默认三次完整恢复机会，问题级可在 1..5 配置。只有同一问题的新证据、诊断或实质不同路线才消耗次数；工具、传输、认证、队列、普通中间红和沉默不算语义失败。达到上限报告 exhausted/blocked，等待用户决定或新证据；只影响当前问题。完成标准直接验收通过只清当前问题租约，不影响其他分支。

报告的判断行必须写成：“判断：……（怎么确认的：……）”。括号写不出来，说明还在猜。skill 只提供方法；当前事件的具体 focus、判断和下一动作以运行时 decision package 为准。
