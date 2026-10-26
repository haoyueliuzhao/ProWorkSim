# v062 独立模型运输与固定面板协调器

日期：2026-10-26。本次完成新版本实现及受影响 CPU 控制，没有启动模型、GPU、Docker、网络服务、systemd unit 或官方评分。执行仍要求 `require_v062_allowed` 验证新的精确批准记录；旧 v061 已完成授权不能放行本轮。

## 模型与运输范围

`software_benchmark_ref_resident_v062.py`、`software_benchmark_model_capacity_v062.py`、`software_benchmark_model_fifo_v062.py`、`software_benchmark_ref_budget_v062.py` 从已经验证的 v061 对应实现另建新版本，未修改旧源码或重置历史回合。改动集中于新资源身份、授权、缓存和槽位绑定。

| 边界 | 固定值 |
| --- | --- |
| 本轮根目录 | `runs/software-benchmark-v062/capability-probe-r1-20261026` |
| 两个 resident | 本轮根下 `residents/model-0`、`residents/model-1` |
| 两个模型 unit | `proworksim-v062-model-0.service`、`proworksim-v062-model-1.service` |
| 本机认证端口 | `18171`、`18172` |
| 短 Unix socket 目录 | 项目内 `runs/g62c1/model-0`、`runs/g62c1/model-1`；独立0700目录 |
| 每 resident 资源 | 12 个固定 CPU affinity、96 GiB RAM、swap 0、pids 2048；可用时另验 CPU quota≤1200% |
| GPU 准入 | 原 A800 80G 及 UUID 门、最少50176 MiB空余、0.6显存预约，最多两个新resident |
| 模型 | 原始 Qwen3.5-9B 固定revision，无adapter，BF16，原 vLLM 0.32.0 |
| 推理 | 上下文131072、输出32768、max-num-seqs=1及原采样值 |
| 自动重启/重采 | 禁止 |

短 socket 目录仅解决本轮完整目录名可能超过 Unix socket 路径上限；其精确路径纳入 resident spec，不复用旧 v061 短路径。模型缓存全部严格位于本轮对应 `resident/cache`。新包装先要求原私有 Python r3 manifest 已存在，再调用原只读验证路径和 `launch_spec(cache=None)`，随后只覆盖新缓存环境变量。不会创建、改写或重新编译旧 runtime source/manifest/头文件，也不把新缓存写入旧 v061 目录。

每个 resident 启动后先从真实 vLLM 日志锁定前缀，要求实际 KV 容量容纳一个完整131072上下文。之后最多执行一次固定中性请求，总输入加输出预约≤2048；两个 resident 合计最多两次、4096。失败、原响应和不确定预约保留，不自动补做。只有容量和中性用量控制均通过才写 `ready.json`。停止只允许 spec 中的本轮精确 unit，且 `systemctl show` 的 description 必须匹配本轮随机 ownership token；未证实归属不会发送 stop。

`CapabilityBudgetRefAdapter` 保留原 v056 完整计数、累计账本与预约算法，仅接收原 `REF_B5000K`/`REF_B10000K` 条件和新 `v062:{instance}:{arm}:{seed}` 身份，核对 arm、预算、seed 以及新部署版本。FIFO host 接口使用 `slot_id` 关键字，通过新策略验证实际新槽，不再接受旧 `original_slot_id` 语义。容器仍不持有服务密钥，不新增监听器，不重试模型请求。

## 固定174槽协调器

`tools/run_ref_capability_v062.py` 只处理新面板，保留150个主面板槽在前、24个事前选定重复槽在后。重复槽必须等待所有主面板生成已结束或按资格保留为未进入；成绩不参与后续选题或重采。环境资格不通过的行仍留在固定分母并记为 `not_qualified`，不换题。

协调器最多同时运行两个生成和两个评分任务。评分与其它独立生成异步进行，不等待全部模型结束；每个评分对象仍是该回合停止并锁定的最终候选。调度维护独立 `entered` 集合，一旦提交过回合就移出待运行队列；异常不会重新放回。整批写入 `execution-started.json` 后不支持自动二次进入，不引入旧 recovery/snapshot/continuation 接续语义。

停止范围以证据判断：

- 明确 `failure_scope=local`、完整确定账本且可信清理的局部技术失败保留为未知，继续其它独立槽。SDK 普通工具失败和正常预算边界由原回合协议记录，不改写为成功。
- 不确定账本、projection fault、明确 `batch_stop_required`、不可信清理、无可验证结果或未分类异常，停止新增派发，并通知本轮在途任务收口。
- 评分清理不可信也停止新增。控制未取得环境资格保持未进入，不重试控制。
- 两个有限 resident 都已有 `closed.json` 且无ready时，结束为 `model_admission_exhausted`，不会无限等待或重新启动这两个身份。尚未具备资源容量且没有耗尽身份时可以等待原容量门。
- 任何协调器异常均先设置本轮停止事件，再等待线程退出，避免先等待一个仍被允许执行的长回合。终止信号仅传给本轮任务。

结束总会调用 `stop_residents` 并保存逐unit回执。无法证明停止时记 `resident_cleanup_unconfirmed`，不把静止误称为对象全部删除。保留容器/卷等对象由 episode 的 `retained_objects` 汇总。轻量 `progress.json` 仅记录已进入、已闭合、待执行和在途计数，以及失败原因；状态查询无需反复读巨大 ledger。

准备同时只读绑定项目独立 daemon 的 `config/daemon.json`、workspace 与 Docker data-root 的文件系统设备号。当前两者设备号均为66306、同一文件系统；不遍历root所属data目录。运行前及循环每5秒检查至少128GiB可用空间；若两个路径分属不同文件系统则分别检查，不修改宿主挂载或Docker配置。空余不足停止新派发并取消本轮在途任务；episode的256GiB准入与resident的384GiB准入继续保留。这是准入和提前停止门，不是磁盘写入硬quota，也不能保证轮询间隔内写入量绝不越过阈值。

## BASE/FIX 真实零模型诊断门

BASE 与 FIX 各需一份当前 source hash、`passed=true`、零模型调用且清理可信的真实部署诊断；FIX5M/FIX10M共享同一协议诊断。预留1/2为首轮，3/4为对应协议源码修订后的唯一备用身份。每个身份有不可覆盖的 intent 和结果；备用不会被自动调用。备用要求同协议首轮零模型调用、有可信清理、源码确已修订；首轮可能失败，也可能因为后续共享源码修订而成为旧版本的成功记录。当前源码已有成功资格时禁止重复诊断；正式面板进入后不再运行诊断。

资格原件分别保存为 `diagnostic-qualifications/BASE/1.json`、`BASE/3.json`、`FIX/2.json`、`FIX/4.json`。selector仅选择与当前完整sources一致的唯一记录；旧成功记录保留，不覆盖、不冒称仍可放行新版本。若首轮已成功且源码未变，不消耗备用；源码变化后必须显式请求相应备用，代码不会自动启动。

`--prepare` 只生成本地不可覆盖计划与资格准备文件。`--diagnostic N`/`--execute` 才进入新批准门。普通用户 launcher 由单独新文件构建 `proworksim-v062-ref-development.service`，协调器实际核验4个固定CPU、16GiB、swap0、pids512；KillMode=mixed、TimeoutStopSec=420、Restart=no。不会修改用户manager或共享系统配置。

## 必要 CPU 控制

新增模型范围测试10项通过，覆盖三个模块端口一致、新unit和资源门、旧runtime仅复用及新缓存路径、待批准时在资源操作前阻断、旧unit/错误nonce禁止停止、FIFO新slot准入、固定中性请求最多一次、旧resident目录拒绝、5M/10M与新seed/arm绑定、spec资源/路径/重启拒绝。

协调器新增12项通过，覆盖主面板先于重复、局部未知保留继续、不确定账本停止新增并收口在途、两个模型身份耗尽退出、资源停止未证不冒称完成、整批二次进入拒绝、两协议当前诊断门、修订备用不可重采、旧成功资格不覆盖、异常先取消再join，以及磁盘准入拒绝与不同文件系统分别检查。首次组合19项通过后，新增磁盘和诊断修订只重跑受影响协调器12项；模型10项不冗余重跑。限定新Python源码的 Ruff 检查通过。

另外为新bundle的最小源码白名单进行了单次普通用户CPU导入枚举：真实SDK preload、构造五工具factory和发送合成初始消息，未调用 `run`，计数/生成/远程工具均不允许。枚举44个项目模块，包括原顶层包引入的通用业务core/domain模块；结果交由bundle作者收窄包初始化并做最终独立打包准入。本枚举不是模型运行、评分或新的SDK行为验证。

这些CPU结果证明指定分支的实现边界，不证明正式部署实际成功、真实模型容量、中性请求通过或任务成绩提升。实际资源操作必须在本轮具体提案获授权后另行开展，并保留新运行证据。
