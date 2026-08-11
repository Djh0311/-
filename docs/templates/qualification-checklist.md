# 来源资格检查清单

状态：`TEMPLATE_ONLY / VALUE_FREE / LATCH_CLOSED`

## 1. 来源与用途

- 候选来源引用、所有权依据和允许用途是否明确；
- 候选与正式引用是否一对一；
- 来源类型是否落在闭合枚举内。

## 2. 输入锁

每个输入必须是显式普通文件，并冻结：相对身份、mode、bytes、SHA-256、读取方式和无值语义范围。目录、glob、symlink、运行中追加和自动替换均不接受。

## 3. 语义合同

- `payload_family`、`payload_version` 和稳定边界；
- 字段 presence、shape path、类型、基数和缺失原因；
- store/product/price 的同 observation/context 绑定；
- 禁止跨来源、跨时间和历史补值；
- coverage、evidence、source integrity 和观察时间规则。

## 4. 能力与隐私

- 网络、UI、本地读取、写入、进程、代理、CA、管理员、凭据/会话、交易和外部成本逐项闭合；
- raw payload 只允许短时有界内存，成功、错误、取消和敏感停止均有销毁规则；
- 敏感或值承载材料在 Parser 前停止，停止收据保持 value-free。

## 5. 一次性执行门

校验器、输入 pre-state、输出边界和一次性 latch 必须全部冻结并由新的用户授权引用。模板填写完成本身不打开 latch。

任一缺口、漂移、范围外输入或敏感材料都保持 `EXECUTION_LATCH=CLOSED`，停止且不自动重试。
