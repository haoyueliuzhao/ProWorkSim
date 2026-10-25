# v061 启动修订：使用本项目进程 CPU 亲和范围

日期：2026-10-25。用户已经明确授权 v061 的限定恢复、容器／专用卷及本项目用户服务。此修订不增加原授权的 CPU、内存、容器、卷、GPU 或生成预算上限，不修改共享服务器的 cgroup 配置。

## 实际发现

诊断1已经通过，原生工具、实际共享仓库视图、RPC和关闭流程正常；2个诊断容器及1个专用卷均已删除，模型调用0。

首次启动正式协调器时，其资源检查发现自身 cgroup 没有 `cpu.max`，主动退出。此时尚无 `execution-started.json`、正式生成、正式评分或模型驻留。只读检查确认，当前用户管理器及其 app.slice 仅委派 `memory`、`pids` 控制器，未委派 `cpu`。因此不能只因 systemd 接受 `CPUQuota=` 属性，就声称已经存在内核 CPU 配额。

该协调器已被回收，按确切单元名查询得到 `LoadState=not-found`、`ActiveState=inactive`，没有停止或修改其他服务。原错误日志、已批准授权、未进入的控制请求与启动计划均另存；诊断1原件和已消耗资源名额保留。

## 修订方式

普通准备进程只读捕获当前允许的176个逻辑CPU，写入项目自己的固定CPU池文件，再按下表给本项目组件分配互不重叠的范围。

| 组件 | 当前服务器 CPU 编号 | 上限 |
| --- | --- | --- |
| 协调器 | 0–3 | 4 CPU |
| 第1对 actor／controller | 4–7／8–9 | 4／2 CPU |
| 第2对 actor／controller | 10–13／14–15 | 4／2 CPU |
| 两个 grader | 16–19／20–23 | 各4 CPU |
| 两个模型驻留 | 24–35／36–47 | 各12 CPU |

协调器和模型单元通过 `CPUAffinity=` 设置本项目进程及其子进程的允许CPU范围，并在进程内核对实际 affinity。内存、swap、PID仍要求各自 cgroup 的真实限制；若 `cpu.max` 存在则继续核验，缺失时明确记录配额控制器不可用。没有启用或重新委派共享 `cpu` 控制器。

Docker任务和评分容器继续保留既定 `NanoCpus`、内存和PID限制，并使用固定CPU池分区。它们的CPU池不再错误地取自协调器自身的4 CPU affinity。无模型诊断仍使用其自身4 CPU范围，不作为性能对照。

这是运行资源配置的修订。模型、题目、原seed、预算、工具schema、SDK r3包和评分规则未改变；worker／controller容器脚本也未变化。模型累计预算仍为13项最多8900万token，原快照恢复仍为0新增模型调用。

## 验证与接续

针对本修订的调度／评分CPU检查21项、actor分配检查29项、模型与启动器检查12项及对应静态检查通过。它们覆盖CPU controller缺失时的精确亲和边界、错误内存限额拒绝、4 CPU协调器控制独立容器分区，以及原配额和对象归属边界。

在同一已授权的最多3组无模型诊断额度内，使用新的诊断2重新验证部署；不复用诊断1编号、不重新生成任何已进入的正式回合。新版本通过后再启动正式协调器。此阶段所有正式回合仍未进入。

修订依据、原失败启动与权限继承见 [revision-history.json](../../artifacts/software-benchmark-v061/cpu-affinity-revision-r1/revision-history.json) 和 [proposal.json](../../artifacts/software-benchmark-v061/cpu-affinity-revision-r1/proposal.json)。原诊断1仍作为其对应版本的真实记录保留。
