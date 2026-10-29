# v091：修复 44 项恢复回合启动前的压力身份死锁

v089 的 44 项恢复没有进入模型或创建任务环境。根因是旧压力监控器只接受原 `v064:task:DEEPSEEK_*:seed` 身份，拒绝新的 `:recovery-v089-r1` 后缀。协调器先登记12个待执行 future，监控器因此报 `Pressure cancellation must bind an active owned 5M API episode` 并关闭准入；episode 又在等待该准入，形成启动前死锁。CPU、可用内存和现金不是这次卡住的原因。

**真实部署结果更新：v091 没有恢复模型执行。** 它随后在 `initialize_for_run()` 阶段因遗漏 `v089.api.request` 操作名而拒绝初始化，尚未写 `execution-started.json`。管理进程自然退出并释放自己的 lease，44 项仍为零模型调用、零任务资源消费，原父组保留。前述 CPU 控制验证了压力修复和函数绑定，但没有完整执行生产授权门与 API 初始化链，未覆盖此缺口。独立 v092 修订保留本轮源码及失败记录，补充真实初始化、host-limit 和 lease 控制后另行封存，不能把本报告的 CPU 通过写成 v091 已正常运行。

## 零消费证据与交接

原 manager 在用户权限内按 pidfd 精确身份冻结后检查：44 项账本请求为0、全局 API inflight 为0、44 项所有任务资源 claim 与 episode 目录均不存在；原事件只有12条 `generation_scheduled`，没有 entered、模型或评分执行。随后原主进程退出，旧 manager lease 单独释放；原 v089 API 父组的同一 live 生命周期保留。证据见 [独立交接回执](../../artifacts/software-benchmark-v091/unentered-handoff-r1/completed.json)。

这些事实允许继续使用原已明确批准的44个未消费恢复身份，不追加第45个回合，不改 seed、不重放模型、不退款、不覆盖旧记录。v091 使用新的普通用户管理服务 `proworksim-v091-api.service` 和管理目录；任务计划、registry、物理索引6000–6043、1700元唯一账本及父组均复用原封存版本。

## 修复范围

新增压力适配从完整封存 registry 构造精确44项白名单，并与原逻辑任务映射校验。没有把旧正则放宽为任意后缀，也没有删除 ownership token、模型、时间、actor/controller、PID、启动时间和 cgroup 身份检查。

三个引用旧身份规则的入口全部私有绑定：基础物理压力 tick、manager 内存紧急取消分支、可选的容器遥测 capture。原模块字典不变；旧协议仍拒绝恢复后缀。主机、父组、manager 三层内存门和迟滞阈值保持，异常取消只通过该 manager 持有的局部 stop event，不操作 Qwen。

新的 episode、评分器和 child、Recorder、Admission、manager claim／release 绑定到新 scope。生成及异步评分继续使用原共享 allocation.lock。评分仍与父组解耦；管理父组在最终无子任务时正常释放。没有新 root 操作、共享主机配置修改、模型配置改变或 GPU 操作。

## 必要核验

六项 CPU 控制通过：12项待进入 registry 能正常准入且缺失单容器遥测不记0；manager 紧急内存分支只取消正确 token 对应的4个本地项；原身份、外来后缀和坏 token 仍拒绝；episode 等待／provider 创建与清理实际闭包指向新 policy；评分管理与 child manifest 一致；新 manager／Recorder 路径独立且无旧绑定；不满足零消费或原父组保留的回执被拒绝。Ruff 通过。

另外用真实44项 registry 和模拟安全余量运行一次 tick，原12项待进入身份得到 `admit=true`、无 observation_error，旧模块仍保持原校验。该控制不创建线程服务、容器或模型请求。部署前再次只读检查得到：API请求0、全局inflight0、已消费claims为空、episode目录为空。

CPU证据只证明新适配满足上述控制，不能冒充真实任务已经完成。实际上线、进入数及后续异常以新 `runs/software-benchmark-v091/unentered-pressure-recovery-r1/api-coordinator/` 的运行回执为准；原v089停滞记录保留。

## 部署

仅在精确旧进程退出及零消费交接回执有效后准备；新source seal包含本次适配，旧v089源码保持原字节。

```bash
.venv/bin/python tools/run_offline_scorer_v058.py tools/prepare_api_pressure_recovery_v091.py --prepare
.venv/bin/python tools/run_offline_scorer_v058.py tools/launch_api_pressure_recovery_v091.py --launch
```
