# v061：原生控制器的私有容器接入

日期：2026-10-25。状态：实现与必要 CPU 准备完成，尚未执行实际 Docker 部署控制或模型回合。本记录不解除旧全局暂停、不复用已关闭授权。

## 保持的实验条件

继续使用固定 OpenHands SDK 1.49.6 的原生 Agent、三个外部工具及 finish／think 内置工具，原生历史摘要、原题、原模型与采样、预算和 seed 保持。新的回合身份明确关联原未知槽，标记 `fresh_generation_recovery`；完整原终态快照的那一项另标 `original_terminal_snapshot_recovery`。

控制器在自己的 network=none 容器中运行。实际 `/testbed` 与 actor 是同一个本轮新建数据卷，actor 可写、controller 只读；元数据读取不再依赖宿主 bind mount 或 chroot。实际文件和命令操作仍由独立 actor 内的原生工具执行器处理，控制器通过原 NativeToolRPC schema 交互。

控制器移植保留 v056-r2 对空工具摘要请求的规范化：计数与生成都省略空 `tools` 以及对应 `tool_choice=none`，不恢复导致旧 8 项 HTTP 400 的请求形式。结束时总是保存已观察到的 RPC 记录；异常保存完整账本与错误，不用空账本替代未知用量。SIGTERM／SIGINT 进入异常保存路径，独立宿主生命周期上限仍由外层执行器负责。

Actor 和 controller 的 PID1 另各自安装不可由普通异常处理吞掉的 SIGALRM 硬退出。诊断最多 180 秒，正式容器生命周期最多 24,000 秒；即使宿主监督器消失，容器也不会无限运行。这个最终兜底退出可能来不及写完整收尾，因此不能仅凭容器退出就认定结果可信。

## 模型通信与取消

控制器不持有真实模型 API key。两条 mode-0600 的私有 FIFO 只存在于 controller 文件系统；另一个受管 Docker exec 进程把请求字节交给宿主普通用户进程。只有宿主进程读取本轮 resident 的 key，并直连已授权 `127.0.0.1` 端口。Actor 没有这些 FIFO、key 或模型网络入口。此方案不新增宿主或容器 HTTP 监听器，也不使用代理。

本轮端口固定为 18161／18162。原 v056 Adapter 的构造函数也限制旧端口，因此新增窄范围 `RecoveryBudgetRefAdapter` 只更新服务身份准入；原计数和生成方法直接继承，CPU 控制确认请求数值、seed 和预算账本条件保持同值，不伪造旧端口身份。

只接受 `/tokenize` 和 `/v1/chat/completions`，严格按序一问一答，无自动重试。响应仍按原 1800 秒完整响应上限处理，FIFO 允许 1830 秒传输边界，原宿主调用守卫为 1860 秒；本地建连单独上限 10 秒。单帧最多 32 MiB，桥接请求数最多 1100，正式模型调用／预算限制仍由原账本执行。

外层发现 controller 结束时，可取消该回合自己持有的 HTTP socket。取消后禁止 HTTPConnection 自动重新连接或重发 POST，不关闭其他回合的连接，不停止模型服务。原 HTTP 状态和完整错误正文原样返回；响应不完整时继续保留未知预约，不能把取消解释为零消耗。

正常 controller PID1 退出会同时关闭本容器的模型桥 exec。桥处于空闲时的 EOF 单列为 `channel_closed`；空闲状态下的连接重置也只有在 stdout 与 Docker 帧均无残留时才进入同一待归类状态。必须再检查 controller 终态与退出码；模型 HTTP 错误、响应发送失败或截断帧不会被转成正常关闭。

## 私有 SDK 包

私有包从服务器已有资产构造：固定 Python 3.12.3、SDK 依赖闭包、原工具源码及控制器代码。没有下载包、模型或权重。最终 r3 包为 151,918,155 字节压缩数据，未压缩文件总量 408,797,180 字节；通过 Docker archive API 复制到本轮拥有的容器，不挂载宿主目录。r1／r2 的 CPU 准备证据保留，正式批次只使用最终 r3。

运行位置为 `/opt/pws-runtime`。启动器仅执行私有 ELF loader 与 Python，`--argv0` 保持 Python 子进程解释器一致；没有设置全局 LD_LIBRARY_PATH，也没有 mount／namespace／chroot 命令。包不含第三方依赖混入控制 stdlib 的目录。Actor 在可信预加载后删除其 SDK／项目副本，保留控制 stdlib；controller 保留自己的独立 SDK 副本，其 `/testbed` 工作区由只读数据卷提供。

首次 CPU 导入发现项目 package 的初始化还依赖 openpyxl，已补入本地依赖闭包；失败日志保留，未进入 Docker 或模型。最终包实际运行了私有 Python、SDK 导入及三类工具预加载；网络调用由审计钩子拒绝，模型／工具执行均为 0。20 项 FIFO、取消、配置隔离、新端口和内部时限 CPU 检查以及静态检查通过。

计划内的零模型 Docker 对照将进一步验证：五个原生工具 schema、terminal／file_editor／task_tracker、controller 读到 actor 的真实写入、删除临时探针后基线一致，以及原生 close。该控制成功之前，CPU 准备不能被称为实际部署验证通过。

证据摘要见 [summary.json](../../artifacts/software-benchmark-v061/controller-preparation-r1/summary.json)。正式容器创建、模型部署和评分需要本轮独立的具体权限范围；本包本身不是授权凭据。
