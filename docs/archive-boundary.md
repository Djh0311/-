# 仓外归档边界

以下内容已经从当前产品仓边界中移出，只能存在于访问受控、带校验清单的仓外归档：

- 历史 raw capture 和 live evidence；
- 旧 Harness runtime、控制面、生命周期、报告、audit 和 usage；
- 旧任务图、dispatch、authority 副本和迁移现场；
- 被退役 worktree 的完整工作副本、Git refs 和共享 Git 元数据；
- 未被当前产品路线采用的 H5/Wechat 实验源码。

新仓不依赖这些字节运行，也不记录其正文或业务派生值。需要查证历史时先使用归档 manifest；任何语义读取、恢复执行或重新导入都需要新的任务和边界裁决。
