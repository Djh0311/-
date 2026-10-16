# P28 人工页面核对与历史 UI 诊断

当前方式：用户已明确停用图像UI，页面由用户本人操作。Devin/Peekaboo截图及自动点击已停止；以下CLI准备内容只保留历史诊断，不是当前启动入口。开发者继续负责既有数据的解析、关联和验证。

用户随后明确改为统一抓取数据后分析，当前操作见 [批量入口](p28-batch-operations.md)。不再把单面板切换反馈作为开始采集的前置；需要具体语义补证时再提出最少核对项。未显示的费用保持未知，页面事实不补写成网络规格字段。下面CLI说明仅保留历史诊断，不重新启用。

用途：用户明确要求 Devin SWE-2 用 CLI 协助目标店铺公开商品页面截图和必要点击。本入口只核对 P28 的规格与价格；页面图像不作为网络字段路径证据，也不替代采集、分页或全店覆盖。

本次目标是用户已确认的小程序及店铺；具体业务名称只在本次私有 CLI 提示中传入。桌面应用选择器来自当次运行进程/应用清单，使用 `com.tencent.flue.WeApp`。读取目标窗口元数据后必须锁定准确窗口；对象不明、窗口不唯一或出现非目标页面时停止，不切换到微信聊天窗口或全桌面截图。

当前工具版本：Devin CLI 3000.11.3、模型 `swe-2-high`；Peekaboo 4.9.0，来自官方 npm registry，执行文件签名检查通过。CLI MCP 工具发现已实际成功，见 [准备收据](reports/P28-ui-preparation.json)。用户已明确许可两项权限，macOS本地实查Accessibility与Screen Recording均已true。用户移动目标窗口后已通过位置变化隔离对象；精确窗口截图目前返回空白，尚无可用实时页面或点击证据，见 [窗口诊断](reports/P28-ui-window-diagnostic.json)。

本次工作目录为 `/private/tmp/p28-devin-ui-_5fvss5r`，模式 0700。软件、私有提示、MCP 配置及临时图像只位于该目录，不写入 Git。`.devin/mcp_config.local.json` 模式 0600；未修改项目 `.devin/` 或用户全局 MCP 配置。

## 历史准备与启动（当前停用）

准备查询不会截图或点击，也不启动真实接收器、读业务响应或消耗抓包额度：

```sh
cd /private/tmp/p28-devin-ui-_5fvss5r
./package/peekaboo permissions status --all-sources --json
devin --model swe-2-high --permission-mode auto -p '只发现 p28-ui 的工具，不执行桌面工具，不读取其它资料；分别报告连接状态与实际权限状态。'
```

MCP 子进程直接运行 `package/peekaboo mcp serve --input-strategy actionOnly --log-level error`，仅公开 `window`、`image`、`see`、`click`、`action`、`verify_state`。`image`仅允许准确app_target与window_id、background及私有路径；`window`只允许`action=list`及准确目标应用。未开启 foreground、临时剪贴板、浏览器或外部视觉模型；不用包装器的自动重启。

本会话已有新增屏幕录制与辅助功能的明确许可，不重复询问授权。系统弹窗/设置由用户本人操作，之后重新查询。当前私有 MCP 默认使用本地进程，执行前用 `permissions status --no-remote --json` 核实该来源；`--all-sources` 用于同时比对 Bridge 与本地，不能把 Bridge 的状态当成本地 MCP 已具备能力。权限仍为 false 时不派发实际 UI，不仅凭终端或模型名称认定生效。

用户许可后可调用原生请求入口，由用户确认系统提示：

```sh
./package/peekaboo permissions request screen-recording --no-remote --json
./package/peekaboo permissions request accessibility --no-remote --json
./package/peekaboo permissions status --no-remote --json
```

本次 UI 工作在两个必需权限实查为 true 后启动：

```sh
devin --model swe-2-high --permission-mode smart --prompt-file ./ui-task.txt
```

主线程已生成0600私有`ui-task.txt`，包括当次目标、按应用列窗口后锁定准确窗口、允许步骤和停止条件。实际non-interactive smart调用在工具确认处停止，因此执行使用交互模式，开发者只逐次确认参数明确、已获准的动作；不选择all-tools/always/bypass，不让用户重复授权或填写技术参数。CLI审查或工具返回不是页面操作成功，必须看实际窗口反馈。

本轮实查小程序进程无自有窗口，相关WeChatAppEx父宿主初次返回4个无标题窗口。只列该相关宿主的窗口元数据，不列主微信聊天；竖屏尺寸只能形成候选。用户仅移动正在显示目标店铺的窗口，开发者比较移动前后的x/y/width/height，同一宿主只有一个窗口位置变化，完成对象隔离。后续调用始终绑定实际owner与准确window_id。不得要求用户修系统窗口标题或配置AX。

MCP `see`的`include_elements=false`不等于跳过AX；该参数仅控制元素表是否返回。本轮先复现AX缺失失败，再按官方本机帮助改用CLI `see --no-elements`，或MCP纯截图`image`。显式现代CLI截图必须先退出本轮拥有截图资源的MCP；只可关闭本轮子进程，不终止其它调用者。上述三种精确图像路径仍为空白时，报告PIXELS_BLANK、保持零点击，先核实用户眼前页面，不把capture success当成页面已核对。

## 本次运行边界

- 只核对已提供页面样本对应的一个多规格商品。允许看面板、选择另一规格并核对底部价、恢复原选项；必要时关闭/重开同一商品面板。
- 只观察目标应用的准确窗口；最多保留三张该窗口图像，每张至多 8 MiB，放在上述私有临时目录，文件 0600；核对结束删除本次图像。不输出全屏、私人界面、配置/凭据或自由错误日志。
- 未显示费用保持未知。商品单位不复制成所有 SKU 的规格；同名或价格相近不证明 SKU 身份。
- 不点击购物车、下单、支付、账户、地址、订单、聊天、外部链接或系统权限按钮。不读剪贴板，不自动切前台，不重放请求，不改代理、CA、keychain。
- 对象不符、敏感界面、权限缺失、工具拒绝、截图目标归属不明或后台动作不支持时停止。不得因后台失败改成全桌面控制或自动重复点击；新的能力按具体缺口另行说明。
- 首次 UI 只在工具确认和截图中核对事实；`delivery`/命令退出不等于页面已改变。最终明确实际点击、核对结果和恢复状态。两采集 latch 保持 CLOSED，新增抓包次数为零。

## 关闭与恢复

CLI 一次任务返回后关闭其 MCP 子进程；不自动重开。停止本轮创建的 Peekaboo 宿主后再删除自有临时图像；若系统权限尚在等待，软件/配置目录保留用于后续核实，但宿主不保持监控。

```sh
./package/peekaboo daemon status --json
./package/peekaboo daemon stop
```

只停止本轮所创建宿主；不得停止其它现有调用者。系统权限由用户在“系统设置 → 隐私与安全性 → 屏幕与系统音频录制 / 辅助功能”关闭 Peekaboo 对应项，撤销后再次实查。系统安全提示要求用户本人操作，开发者不代点。

工具依据：[Peekaboo MCP 说明](https://github.com/openclaw/Peekaboo/blob/main/docs/commands/mcp.md)、[权限说明](https://github.com/openclaw/Peekaboo/blob/main/docs/permissions.md)。说明中的通用能力不扩大本轮目标。
