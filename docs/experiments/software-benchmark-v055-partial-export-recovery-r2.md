# v055 单题导出恢复 r2：实际 system cgroup 硬限

## 事实与状态

r1 于 2026-10-23 00:34:45（北京时间）实际登记并运行一次，在读取准备 worker 的 `cpu.max` 时失败。错误路径位于 `user.slice/user-1021.slice/user@1021.service/app.slice/...service/cpu.max`，文件不存在。r1 已产生独立 preparation-result 和完成回执，原队列按约定将其记为环境失败；**新增导出 0、模型调用 0、正式 claim 0**，没有 staging 目录。原截断 tar、原磁盘故障和这次失败全部保留，不能把 r1 记作恢复成功。

r2 独立工具、计划和新 worker identity 只处理上述已证实的执行前故障。r2 已于 2026-10-23 00:44:39—00:47:21（北京时间）完成，结果为 qualified，新增 1 次本地完整导出、0 次模型调用、0 正式 claim、0 隐藏评分。它没有热改 r1 文件，没有更换任务或镜像，没有重复已进入的模型回合。

## 本机 cgroup 调查

实际只读结果：

- `/sys/fs/cgroup` 为 cgroup v2。
- `/sys/fs/cgroup/user.slice/cgroup.subtree_control` 为 `memory pids`，没有 `cpu`。
- `user-1021.slice`、`user@1021.service`、`app.slice` 的 controllers/subtree_control 也只有 memory、pids；这些分支没有 `cpu.max`。
- 因此 **在 user service 中传入 CPUQuota=400% 仅是配置声明，不能据此宣称本机已有该 CPU 内核硬限**。r1 的新检查正确拒绝了这个不满足的执行环境。
- 正式 actor/controller 使用项目独立 system resource slice。此次观察到仍运行的 DeepSeek claim `93d405b3089f4d5bb2b2a1caba7a7b84` 的实际内核值为：`cpu.max=400000 100000`、`memory.max=17179869184`、`pids.max=16384`，与原 contract 相符。

边界：原普通 DeepSeek 预热的 user unit 也曾声明 CPUQuota，因此不能把其导出阶段的声明追述为已经实测有效。公共初始化及正式 actor 的独立 system slice 是另一层约束，本次没有发现它们失效。本修复不修改共享 user.slice、不为历史执行补造资源凭据、不重新运行历史预热。

## 新执行方式

保留正常 user preparation worker 作为原 r9 collector 识别的等待外壳。真正的导出和可信准备代码由该外壳创建一个精确独立的 system transient service：

- `User=1021`、`Group=1022`，不以 root 执行任务代码。
- `CPUQuota=400%`、`MemoryMax=17179869184`、`TasksMax=16384`。
- `KillMode=control-group`、`Restart=no`、`RuntimeMaxSec=3540`、`TimeoutStopSec=40`。
- 服务内部读取自己的 cgroup membership，并要求它恰为本次独有 system unit，实际 `cpu.max`／`memory.max`／`pids.max` 精确匹配后才允许导出。
- 外层 user worker 使用 `systemd-run --pipe --wait` 等待并保留 bounded-system-intent/completion；不把外壳宣称为 CPU enforcement boundary。
- 外层 `ExecStopPost` 仅停止这次独有的 bounded system unit，防止外层结束后内层仍运行、使原队列过早释放预约。内层期限 3540 秒低于 job 3600 秒，外层 service 上限 3660 秒；停止清理沿用原队列 active/deactivating 识别。

公共初始化仍通过原 `create_episode_resources` / `launch_owned` 使用既有独立 system slice；导出与初始化顺序执行。原九槽未进入检查、原实例锁、共享磁盘预约、4CPU/16GiB/PID限制、固定镜像、原失败/tar保留及最后发布 qualified 的逻辑保持。

新 plan 额外封存 r1 的源码、plan、job、registration、completion、实际失败 result 引用，以及“kernel_limits 在任何导出和 staging 创建前失败”的证据。若 r1 出现实际导出、资格或不明错误，r2 拒绝，不把该途径变成自动重试循环。

## 验证与复用

新增 `tools/check_partial_export_v055_r2.py`，只做四项必要纯 CPU 控制：

1. 对不变的九槽、原件身份、状态交接、payload发布、初始化及执行主体做 AST 同值确认，复用 r1 七项控制，不重跑无关检查。
2. 唯一本次 system unit＋真实 CPU/RAM/PID 值允许；user wrapper、其他 unit、无限 CPU 或内存拒绝。
3. 只接受精确 r1 zero-export kernel 错误；发生导出记录时拒绝。
4. 外壳调用正确的 system UID/GID/期限和 cpu-run；合格结果按原引用返回，缺结果保持环境异常。

四项控制通过，定向 Ruff 通过；实际 Docker、服务启动、模型调用、GPU调用和正式队列写入均为 0。控制脚本随后仅将等价 lambda helper 改成 def 以符合 Ruff，没有更改控制逻辑，未重复整套控制。

新 worker 的实际 preparation-result 已保存 kernel_limits，真实 system service 路径和三个内核值均通过。这里分别保留合成控制与实际服务器资格，纯 CPU 控制不替代后者。

## 实际部署交接

r9 同名 runtime service link 已由操作侧保留，可沿用其原定义 stop/start，不用重新建立链接或换 host revision。

1. 记录 r9 manager 身份及 state，按已有静止交接仅停止 manager。正在运行的旧 worker、GPU 和评分服务保持。
2. 执行新 `repair_partial_export_v055_r2.py register --plan runs/software-benchmark-v055/partial-export-recovery-r2/plan.json --sha256 <sealed SHA>`。它在原协调器锁与磁盘预约锁内登记一个正常 preparation intent，保留 r1 attempt/result 和全部旧异常。
3. 以同名、同定义恢复 r9。即使其已自然进入唯一六题 deferred-environment 终态，显式交接也只恢复该原 pending 环境；不清其他 halt 或预算门。
4. 检查 bounded system service 的实际内核限制、导出和初始化结果；原 collector 根据 completion 更新 qualified 或 failed。若任何启动观察不明确，依据 durable intent 与实际单元状态处理，不盲目重复 register。

工具：`tools/repair_partial_export_v055_r2.py`。独立证据：`runs/software-benchmark-v055/partial-export-recovery-r2/`；可发布小证据：`artifacts/software-benchmark-v055/partial-export-recovery-r2/`。


## 实际结果与原队列承接

- r2 登记前，DeepSeek 已于 00:39:10.009156 自然进入 `primary_finished_with_deferred_environment`，只有本题六槽仍因环境 failed 而 pending。登记回执封存该旧 status、ended_utc、旧 preparation 及全部 rows/exceptions SHA，然后仅恢复本题原 pending 环境的可调度状态。r1 attempt/result 和原异常仍存在。
- r9 于 00:44:38.652203 以相同 host revision 和同一 service 定义恢复，manager PID 2457090；worker/GPU 服务信号计数均为 0。没有重载模型。
- r2 `cpu-run` 开始于 00:44:39.050112，结束于 00:47:21.022138，约 161.972 秒。实际路径为 `/sys/fs/cgroup/system.slice/proworksim-v055-export-recovery-bounded-a065523e3106ee97d676a18f.service`，实测 `cpu.max=400000 100000`、`memory.max=17179869184`、`pids.max=16384`。
- 运行前共享预约重查：主盘普通可用 479,078,244,352 B，含该准备任务在内的活动预约 211,064,400,103 B，扣除后 268,013,844,249 B，满足 137,438,953,472 B 门槛；没有放宽安全门。
- 从同一固定 image ID 新完整导出 1 次并规范发布。原 6,928,990,208 B 部分 tar、原 457 B 磁盘失败仍保留。没有下载镜像、修改问题、使用参考修复或隐藏验收。
- 原公共初始化 `passed=true`；model_calls=0、slot_claimed=false、benchmark_tests_run=0、hidden_grader_called=false。初始化 scope 已静止、独立资源 slice 释放、临时克隆删除。该初始化是环境资格，**不是任务修复通过或官方 resolved**。
- 最终 lazy-preparation SHA256 为 `a5816f4d3406ece869d322e3296dc72ec69c38b7673b635d912f2108f5e289e3`；公共初始化 receipt SHA256 为 `d4d760f142d402d6c5fc2bd31e2358aad31c6565838a731c5364b745de6bda64`。
- 原 r9 collector 已自然收取 qualified。00:47:49.310070 的首次承接快照显示：DeepSeek 六个原槽均首次 running、environment_status=qualified；Qwen 三个原槽仍 pending、attempts=0，按既有顺序等待资源。未人工提前执行 Qwen，也未重放任何已进入回合。

“修复调用模型 0 次”仅描述 r2 准备过程。00:47 之后六个正式 DeepSeek 回合是原计划的第一次生成，正常计入各条件的原 500 题与共享预算，不能把它们说成全程无模型，也不能提前宣布六个回合完成或代码通过。后续进度由九组运行监控文档单独报告。

小证据在 `artifacts/software-benchmark-v055/partial-export-recovery-r2/`：plan、registration、launch、worker request/job/completion/result、bounded-system intent/completion、首次队列承接观察、实际公共初始化/lazy-preparation、原 failure，以及部署脚本、交接与重启回执。`evidence-index.json` 逐文件记录来源、大小、SHA。完整 21 MB 以上的 state-before 和 52 MB manifest 仅在原 runs 保存，未复制发布；没有再次哈希大 payload 或重跑资格测试。
