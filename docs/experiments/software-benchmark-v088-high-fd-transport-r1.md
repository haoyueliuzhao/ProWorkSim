# v088：高编号文件描述符的宿主通信修复

v086 的原任务 `5552` 在开始模型请求之前失败。其 `model-transport.json` 保留了 `ValueError: filedescriptor out of range in select()`，而模型请求数为零。宿主实际创建模型通道的位置是 `software_benchmark_episode_v066._run` 中的 `DockerStdioChannel`；actor/controller attach 还在私有 provider 中使用同一类的另一份引用。只提高 `RLIMIT_NOFILE`、只修改 FIFO 类或只改模块表面的类名，都不能消除这条实际调用链中的 `select()` 限制。

## 修订及接入

新增 `software_benchmark_io_v088.poll_select`，用 `poll()` 实现原 read/write/exception 就绪等待形状，不再受 `FD_SETSIZE` 限制。保持传入对象与顺序（含重复对象）、读取/写入就绪、异常事件、超时和中断后的截止。HUP/ERR 只通知原 read/recv/send 路径继续判断 EOF、reset 和不完整帧；无效描述符仍产生错误，不能被当作通信成功。它不关闭、不重新编号描述符，不更改阻塞模式，也不新增监听或重试。

私有 `DockerStdioChannel` 只替换原 `readline` 的等待器。原 Docker stdout/stderr 拆帧、JSON 行边界、大小限制、错误、EOF、写锁及关闭方法保持。`bind_episode(delegate)` 必须在新 parent/resource 工厂创建私有 episode 后、首次派发前调用；它同时核对并替换实际 `_run.__globals__` 和 `OwnedActorPair.attach.__globals__` 的类引用。传入原冻结模块或原 provider class 会被拒绝，不能用该适配器改写正在运行的旧进程。

```python
delegate = api_episode(new_policy)
delegate = software_benchmark_io_v088.bind_episode(delegate)
# 随后可接入独立的单题初始化故障分类；原 result/wire version 不改。
```

模块也提供私有 FIFO 读写及 TCP/TLS 等待适配器。当前控制器容器有独立描述符表，仍运行已冻结的原 FIFO/relay 脚本；本次没有把宿主的高 FD 序号误当成容器 FD，也没有修改模型可见 bundle 或 container relay source。

## 评分同类路径

原官方评分运行在独立子进程，不与高并发协调器共享描述符表；不过其真实 HTTP/TLS 宿主转发器也使用 `select()`。新增 `software_benchmark_poll_scorer_v088.bind_grading(grading)` 将原已取得资源预约的评分子进程固定重定向到该模块，而不是只改父进程中的一个未被子进程使用的函数。

新 child 继续调用当前 v068 的原授权 guard，保留同一原任务、固定候选、容器身份、资源限额、CA/TLS校验、冻结目标地址、连接/载荷上限、官方测试与验收。它私有构造 scorer 函数、`Containers.create`、TLS `EnvironmentContainer.start` 与 TCP relay 的完整实际绑定，保留 v068 的 finish-before-cleanup 生命周期。原源码和模块全局命名空间不改；新 `host-poll-runtime-v088.json` 单列本次等待器来源，不把新宿主适配器冒称为原实现字节。

```python
grading = existing_resource_guarded_factory(...)
grading = software_benchmark_poll_scorer_v088.bind_grading(grading)
```

该包装不删除来源核验、不改变评分规则、不重放已消费的评分身份。评分准入与 API 父组生命周期的分离由本轮运行器另行实现，本等待器模块不自行放宽权限。

## 必要 CPU 验证

最终 13 项检查通过，限定 Ruff 通过。真实测试把本测试进程的一条匿名 Unix socket 或 pipe 复制到 FD 2048，仅新增少量自己的描述符，没有打开两千个文件或操作主机限制：

- 原 `select()` 对真实高 FD 复现同类 ValueError；新 poll 保持就绪对象和顺序。
- 高 FD FIFO 帧顺序、中文载荷、满管道写截止、空读截止、EOF与无效 FD 检查。
- 高 FD Docker stdout/stderr 多路帧、跨帧 JSON 行、正常关闭与不完整行拒绝。
- 原模型 broker 在高 FD Docker 通道上完成 ready、恰好一次合成请求响应和 STOP；没有真实模型或外部 API 调用。
- 实际私有 episode/provider 双入口、评分 Containers/EnvironmentContainer/TCP 入口以及子进程命令的绑定检查；原冻结对象保持不变。
- 高 FD TCP relay 的 READY/STOP/DONE，以及 premature DONE 继续拒绝；不建立任何公网连接。

初始沙箱试验中，高 FD 的 Python socket 包装被沙箱返回 `EPERM`，六项 socket 测试未进入目标代码，三项 pipe/绑定检查通过；说明 fixture 清理后，普通用户隔离测试进程执行全部控制通过。该权限问题没有被改写成代码通过，也没有通过 root、TCP 监听、Docker、模型、服务或共享主机配置修改绕过。

本模块阶段未部署真实服务。生产恢复须在新版本中封存并接入这两个实际绑定；仅有 CPU 控制不能宣称高并发长时间运行已经通过。单题已证明零派发且清理完整的初始化失败是否可隔离，由独立严格证据分类决定，不能把任意协议、权限或账本错误降级为普通任务失败。

上线前窄审阅另发现 exception-only 监听收到 HUP/ERR（但没有 POLLPRI）时，poll 原始事件不能直接当作原 select 的异常就绪。已改为先按请求集合过滤；不匹配的终态事件只从本次等待集合移除，继续原截止，避免提前空返回或忙轮询。新增真实高 FD peer-HUP 超时反例及原 timeout/NVAL 两项检查通过，限定 Ruff 通过；未重跑完整套件。FIFO 的 post→write_frame、container_bridge→write_frame/LineReader 实际私有命名空间也已静态确认。此窄修后的源 SHA 单列于 `validation-r2.json`，先前 13 项记录保留，不伪称其在最终字节上全部重跑。
