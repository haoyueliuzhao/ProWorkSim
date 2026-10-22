# Qwen未来回合的监督进程退出竞态修复（r1）

## 触发证据与测量边界

2026年10月23日01:29:20，北京时间，Qwen PROJECT的 `django__django-16136`（slot1087，GPU6 kernel-r6）被原队列登记为生成技术未知。该回合的CPU session sentinel停止证明报 `FileNotFoundError`，导致 `quiescence.json` 的 `all_quiet=false`，最终候选未被锁定。actor与controller已静止，session释放回执证明自己的inflight为0、RNG已闭合，最终episode资源slice为空；GPU resident仍健康且保留另一活动session。因此没有据此停止其他任务或重新加载模型，也没有修改该题原技术未知。

实际运行的 `revision-root-r6/src/proworksim/software_benchmark_supervision_v054.py` 在 `stop_owned()` 内先读取systemd的MainPID，再直接读取该PID的 `/proc/<pid>/stat`。PID在两步之间自然退出时，这个读取可抛出未捕获的 `FileNotFoundError`。原函数已经处理后续show→stop期间的unit GC竞态，但未覆盖这一更早的身份读取窗口。原失败回执没有完整堆栈，因此将此定位表述为强推断；本修订的CPU控制验证相应竞态，而不是宣称已重放原现场。

## 独立实现与不变部分

新增文件：

- `tools/supervision_proc_exit_overlay_v054_r1.py`：小型监督overlay及独立watchdog入口。
- `tools/run_benchmark_episode_supervision_v054_r1.py`：未来worker的外层包装。
- `tools/run_qwen_supervision_v054_r7.py`：继承原三卷r6协调器，仅包装未来generation启动命令。
- `tools/check_supervision_proc_exit_v054_r1.py`：有限CPU控制。

没有修改原项目监督源码、r6宿主源码、GPU6 `revision-root-r6`、模型进程、旧worker、旧claim或旧回执。原科学bindings、condition、题单、seed、工具与提示、token和时间预算、候选导出及评分规则仍由原runner执行。新运维revision通过generation记录、job argv及独立 `watchdog-supervision-overlay-r1.json` 留痕；不能把修订前后的监督运行细节描述为完全相同。

父worker必须在导入原runner／Episode之前安装overlay。它同时包装父worker使用的 `stop_owned`，并将 `start_watchdog` 改为启动独立child入口。child重新校验同一seal和选定source root，然后在原监督模块中只包装 `stop_owned`，仍执行原 `watchdog()`。仅在父worker改一个函数不会传播到原先另起的Python watchdog，因此本实现明确覆盖两个进程。

canonical路径先保留原r5 REF handoff包装及其参数，再外包新监督入口；GPU6路径保留原 `/usr/bin/env PYTHONPATH=<revision-root-r6>/src:<revision-root-r6>` 和原runner参数，在对应原source root导入模块。任何未知generation argv拒绝派发，score argv原样透传。三卷预约、GPU6科学bindings、REF转接reader及原所有adoption保持。只有 `status=pending` 且 `claimed=false` 的新generation允许包装，已进入槽不迁移。

## 有限重取的精确范围

新函数不自行判定quiet。它最多调用原 `stop_owned()` 三次，只捕获 `errno=ENOENT` 且 `filename` 恰为 `/proc/<本次登记main PID>/stat` 的 `FileNotFoundError`。其他路径缺失、权限错误、unit复用、PID复用、存活后代或其他异常仍失败。

已绑定的两份原监督源码相同：原函数只有停止命令之前的MainPID身份读取会向外抛出这一精确错误；`assert_quiet()` 自身已经处理PID不存在。因此重取不会重放已经开始的stop/poll阶段。每次重取重新执行原unit invocation、PID和cgroup检查，原完整quiet证据通过才返回。若PID消失但其cgroup还有后代，不能因此认定静止；若原unit继续存在，仍执行原停止与静止检查。

重取不sleep，最多增加两次身份观察；0.25秒限制的是是否准入下一次重取，不是systemctl系统调用的绝对壁钟上限。原systemctl单次15秒timeout、scope的 `stop_seconds`、stop/poll窗口、watchdog `hard_at` 均未修改，且不会在已进入停止轮询后重新开始该阶段。成功恢复的quiet报告附带原ENOENT路径、errno和发生次数；超出次数／时间准入范围仍保留异常，不伪造成功。

## 控制与封存

9项纯CPU控制通过，限定四个新增Python文件的Ruff通过。控制包括：精确PID消失后完整quiet核查、必须保留原stop路径、活后代拒绝、unit复用拒绝、PID复用拒绝、其他异常不重取、次数与重取窗口、canonical/GPU6 argv及score透传、父worker安装与新watchdog启动参数。Popen与systemd操作均为内存替代，没有真实子进程、GPU调用、模型请求或服务修改。

控制回执：`runs/software-benchmark-v054/supervision-proc-exit-control-r1/controls.json`。该控制不等于真实模型任务已通过新生命周期；正式启用后仍需观察首个未来worker与其watchdog回执。

| 封存项 | 路径 | SHA-256 |
| --- | --- | --- |
| 新宿主revision | `runs/software-benchmark-v054/supervision-host-r7/revision.json` | `a39b1b7c25794df9d12bd738dc90e78bd4423c9a466444bbf08238f2d5e4438f` |
| 监督overlay | `runs/software-benchmark-v054/supervision-host-r7/overlay.json` | `37db6f43e5fa5f589877f70a99f41842c0c1a13bf9d70566880e8af9e4038b2d` |
| 原r6前驱 | `runs/software-benchmark-v054/three-volume-host-r6/revision.json` | `8cb5b42cd6b9c49e4709cfb2581032b30e5e00abb00fd3fdc7d273193fdec961` |

实际新unit名为 `proworksim-v054-formal-queue-supervision-r7.service`，入口 `tools/run_qwen_supervision_v054_r7.py run --revision <上述revision绝对路径> --sha256 a39b1b7c25794df9d12bd738dc90e78bd4423c9a466444bbf08238f2d5e4438f`。宿主环境继续采用原 `PYTHONPATH=<项目>/src:<项目>/tools:<项目>`、`Restart=no`、`KillMode=process`。

## 实际部署与首次接入

操作侧于 **2026年10月23日02:33:51，北京时间** 完成manager交接。`runs/software-benchmark-v054/supervision-host-r7/deployment/handoff-intent.json` 保存原r6 PID／InvocationID、原state SHA及新unit定义SHA；`new-manager-started.json` 记录新r7为active/running，PID3078377、InvocationID `2b7f8c7e486e42298f9b429c2eafdf0b`。仅原manager收到信号，worker与GPU服务信号数均为0，没有重放entered回合。

`host-adoption.json` 于02:33:53记录独立r7 adoption。02:34:09的 `first-adoption-observation.json` 证明8个旧在途槽仍全部running、各自job身份完全一致，新r7队列状态为running。该观察时新overlay jobs仍为空，不能用这份回执单独证明新监督路径已运行。

随后操作侧于 **02:37** 观察到4个新canonical槽首次进入running／claimed状态，按 `sha256(slot_id)` 定位的各自claim目录均已出现 `watchdog-supervision-overlay-r1.json`。这是新canonical worker与独立watchdog绑定已接入的阶段证据；当时尚未观察到新路径闭合或新的kernel路径槽，不表示真实运行验证全部完成。首批闭合与kernel路径统一留待03:13小时观察窗口核查，不另起高频监测。

六小时原只读采样的unit名清单保持不变；原r6正常退役与新r7状态须在后续报告中额外说明，不能将旧unit inactive误计成停机。旧unknown、原失败回执与所有已进入槽均保留。

小型证据已按原字节封存于 `artifacts/software-benchmark-v054/supervision-proc-exit-r1/`：revision、overlay、CPU控制、host adoption、首次接入观察、部署脚本、交接intent、原／新unit定义及启动回执，共10个文件、15903字节（不含索引）。`manifest.json` 记录每个来源、大小和SHA。约13.45 MB的 `state-before-stop.json` 仍留在原runs目录，其SHA由交接intent和归档索引引用，没有重复复制进发布材料。本次证据封存未产生新运行采样、GPU探测或模型请求。

## 03:13小时窗口的两条路径实际闭合核查

按既定小时窗口开展一次必要启用核查。读取的队列版本 `updated_utc=2026-10-22T19:14:08.396688+00:00`（北京时间03:14:08）中，带r7 supervision标记的新回合计数为：canonical **21个closed、6个running**；kernel **8个closed、2个running**。这是一份队列元数据计数，没有逐题重复核验全部29个闭合回合。

每条source mode按原队列顺序选择首个closed实例，只核对其小型job／result、按 `sha256(slot_id)` 定位的watchdog sidecar及result绑定的原quiescence：

| source mode | 选定实例 | 原结果与监督证据 |
| --- | --- | --- |
| canonical | `v054-PROJECT-sympy__sympy-23950`，slot1169 | 原结果为 `closed_candidate_and_official_requests_ready`；sidecar绑定canonical原监督文件和同一overlay；3/3 scope静止，`all_quiet=true`、errors为空 |
| kernel | `v054-PROJECT-sympy__sympy-18199`，slot1177 | 原结果为 `closed_candidate_and_official_requests_ready`；sidecar绑定冻结revision-root-r6监督文件和同一overlay；3/3 scope静止，`all_quiet=true`、errors为空 |

两例的job source mode、sidecar mode、原监督来源、quiescence claim与result中的claim一致。两例的停止报告均**没有** `proc_exit_identity_retry` 记录；所以它们证明新canonical与kernel路径能够实际进入并沿原严格静止规则闭合，不证明目标竞态在这两例中被触发，更不证明竞态已经全面消除。目标竞态分支的行为证据仍来自前述有限CPU控制。生成闭合也不等同于官方测试通过。

本次小型运行观察为 `runs/software-benchmark-v054/supervision-host-r7/runtime-observation-r1/runtime-observation.json`，SHA-256 `01d1e9a0ba97ac6106ea4083cfdca7fa24b84e1c542b57b2f48ac60b3e8f1e20`。两份凭据 `canonical-evidence.json`、`kernel-evidence.json` 分别为SHA `951f52e3e5e2a27a0763e3b90d00b2a80df7b0c4cdc5de2a7ac391b3d5b4f3fd`、`93779d2e5345c2402a244f23936bce8ec598d408306078bb7e6b506cf0941ea6`，保存原小型证据引用和判断字段；三份共6549字节，已原字节复制到 `artifacts/software-benchmark-v054/supervision-proc-exit-r1/runtime-observation-r1/`。未重跑控制、调用模型、探测GPU、扫描rootfs或改动在途任务。
