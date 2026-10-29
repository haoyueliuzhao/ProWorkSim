# v094：恢复身份的模型桥接作用域修复

v093 的前两项已经创建并清理环境，但没有进入 API。问题发生在实际模型线程：`software_benchmark_host_usage_v066.serve_model_channel` 在函数内部直接导入旧 `require_v066_allowed`，把新恢复身份交给原6000项身份表校验。外部 episode 的私有作用域替换不能改变这条局部 import；而且原校验位于 `try` 外，线程异常未返回完整桥接回执。

新增 [API 专用桥接](../../src/proworksim/software_benchmark_api_bridge_v094.py)，显式接收新 guard，不再从函数内部取得旧 guard。它仅接受已注入的 DeepSeek broker（18219、1800秒、无控制器密钥），保留原帧协议、请求／计数／生成上限及原 `model_response`。授权、身份和就绪帧检查全部位于结果保护范围内，失败返回 `ready=false`、失败阶段和原错误，不能伪装成正常关闭或无成本成功。

[新 runtime](../../src/proworksim/software_benchmark_recovery_runtime_v094.py)在 IO 与失败分类绑定之后调用 `bind_episode(..., scope_guard=policy.require_v066_allowed)`。安装器只接受新建的私有 episode，核对 `_run` 与 `run_episode` 的实际全局字典一致，并替换真正被 `model_loop` 读取的 `serve_model_channel`。旧源码和运行字典不作全局替换。

## 整条调用链的核查

| 环节 | 已核实情况 |
| --- | --- |
| 线程启动授权 | 旧 host-usage 内部 import 是本次实际漏点；新 API 入口显式使用新 scope |
| 同名旧实现 | `model_fifo_v064.serve_model_channel` 也有旧 import，但实际 episode 使用 host-usage 版本。安装器拒绝错接这一同名函数 |
| 帧与转发 | 原 `model_response` 校验路径、序号和 envelope，再进入原 `HostDeepSeekTransport.post`；这里没有另一个旧 dispatch guard |
| 计数与前缀计数 | 使用真实本地 DeepSeek tokenizer、原 incomplete-prefix 路径，不产生供应商请求 |
| 生成授权 | broker 调用 runtime 实例的 `_require_allowed`；原 v067 方法虽包含旧 guard，但实际 v089 runtime 已覆盖该方法，动态进入新 scope。FIFO 控制实际执行了这一调用 |
| 单题与现金预算 | 原 broker 核对真实计数、任务用途和累计额度，原1700元 client／ledger 预约并结算；fork 使用实际子类，不退回1500元 client |
| 响应与记录 | 原 FIFO 错误封装、原 controller `_record`／`save`、SDK 投影及账本逻辑保持。记录与用量读取没有新的固定6000身份表入口；物理编号由新 view 严格回映 canonical 身份 |

本次没有放宽路径、工具、用户标识、请求前缀、token、采样、评分或候选选择规则。

## 实际离线验证

[check_model_bridge_v094.py](../../tools/check_model_bridge_v094.py)从最终新 runtime 工厂构造 episode，**读取并实际调用其 `_run.__globals__` 中的入口**。通过临时 named FIFO、原 `container_bridge` 和原 `FifoModelTransport`，运行真实 SDK 消息序列化、原计数器、原 broker、真实客户端和临时 SQLite 账本。

REF、PROJECT 各完成3条程序化供应商响应：两条已结算（含空正文），一条保留未知预约。普通计数、SDK 未完成工具尾的 `/tokenize-prefix`、生成、错误回执及控制器原件落盘均实际经过 FIFO；两条已知用量与临时现金表一致。未知响应没有被填零或重试。另验证非法身份在读取通道前就返回可信初始化错误回执。

最终 [summary.json](../../artifacts/software-benchmark-v094/real-FIFO-control-r1/summary.json)记录两条件完整通过，真实模型、HTTP、Docker、GPU操作为0，网络阻断审计触发为0；真实唯一账本仍为46,504条请求。写能力 client 仅接临时数据库副本。Ruff通过。

第一次失败控制曾在安装阻断器之前导入 SDK，LiteLLM 尝试获取远程成本表并因 DNS 失败回退；其后又因空正文表示为 `TextContent("")` 而非空列表触发测试断言。这次失败不计为无网络通过。修订将本地成本表配置和网络审计提前到所有 SDK 导入之前，并按真实 SDK 空文本语义判断，之后完整重跑通过；原事实见[失败记录](../../artifacts/software-benchmark-v094/real-FIFO-control-r1/initial-control-failure.json)。

## 尚未验证

这是离线协议和计费链路控制，供应商响应是程序数据；没有验证真实 Docker stdio 封装、PID1 进程、真实供应商生成、候选导出或官方评分。PROJECT 使用冻结真实 schema 清单与 SDK 消息路径，没有执行实际受管世界动作。管理器及 parent cgroup 使用显式临时夹具，不冒称内核部署检查。

因此，CPU 通过不代表系统或实验已恢复。后续仍应按已规定的 REF／PROJECT 首项健康门执行可信生成与结算，再扩大原队列。
