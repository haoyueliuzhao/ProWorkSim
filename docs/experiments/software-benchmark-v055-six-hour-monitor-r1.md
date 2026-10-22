# 九组实验六小时监控：方法与恢复边界（r1）

本轮根据用户“持续监控6个小时，每隔一个小时检测查询一次，期间自主修复”的要求开展。计划窗口为 **2026年10月23日00:12:51—06:12:51，北京时间（Asia/Shanghai，UTC+08:00）**。本文件初稿记录计划、已取得的首次观察、有限定时采样部署及必要恢复边界；六小时观察尚未完成。

## 固定计划与观察材料

执行方式是有限定时采样器保障每小时只读采样，活动助手持续至窗口结束，解释进度变化并针对具体证据开展修复。定时采样器不执行修复，不能仅部署采样器，就把六小时判断和自主处理视为完成。

| 材料 | 路径 | SHA-256 |
| --- | --- | --- |
| 一次性观察工具 | `tools/observe_nine_conditions_hourly_v055_r1.py` | `f3810815c329ce2158d6b836d18e04bbd00ede6c5f00022a127821c5e7e76260` |
| 固定时间表 | `runs/software-benchmark-v055/six-hour-monitor-r1/schedule.json` | `6e60866a40b613e10999acc7ce8093b9fe983c8d12a4e5c3e2be142c213159a6` |
| 首次观察 | `runs/software-benchmark-v055/six-hour-monitor-r1/summary-00.json` | 由其原文件和相应快照保留，不用后续快照覆盖 |

计划共7个观察点：起点和之后每小时一次，共覆盖6小时。首次观察实际延迟至 **00:20:00.512895**，没有把该时间回填为00:12:51；结束窗口仍按原计划保持。后续计划时刻为 **01:12:51、02:12:51、03:12:51、04:12:51、05:12:51、06:12:51**，每份记录均以实际观察时间为准。若某次迟到或修复跨越计划时刻，应明确记录偏差，不补造漏失时段的数据。

观察工具只读取原队列、账本、systemd、GPU与宿主资源信息，并写入本监控目录的独立快照和摘要。它不调用模型、派发工作、遍历rootfs、重新计算权重或镜像负载哈希，也不修改队列、账本和服务。首次摘要记录 `model_calls=0`、`job_dispatches=0`、`runtime_or_services_mutated=false`、`errors=[]`。

为避免助手会话延迟造成漏采，已通过 `tools/schedule_nine_conditions_hourly_v055_r1.py` 部署6个一次性systemd user timer/service，编号1至6，名称为 `proworksim-v055-six-hour-monitor-r1-sample-<编号>.timer` 及对应 `.service`。它们分别对应上述01:12:51至06:12:51时刻，timer精度设为1秒；实际采样时间仍记录在输出中，不宣称调度能保证零延迟。每个service声明 `CPUQuota=100%`、`MemoryMax=512M`、`RuntimeMaxSec=120`、`Restart=no`，仅调用冻结的只读collector。上述为unit配置：本机user.slice未下放cpu controller，因此不能把 `CPUQuota=100%` 写成已生效的1 CPU硬限制；这些采样单元未进行对应cgroup实际硬约束核验。它们只做单次只读聚合，没有因此重装timer或更改采样器。部署器已通过Ruff；`runs/software-benchmark-v055/six-hour-monitor-r1/timer-deployment-01.json` 至 `timer-deployment-06.json` 的部署返回码均为0。六个有限采样单元不承担实验派发或无人值守修复，也不是新增永久daemon。

## 首次观察：00:20:00

正式题单保持Qwen三组共1500回合、DeepSeek六组共3000回合，每组500题。下表是生成生命周期计数，不是官方测试通过数。

| 组别 | 生成闭合 | 生成技术未知 | 运行中 | 待运行 |
| --- | ---: | ---: | ---: | ---: |
| Qwen REF | 475 | 7 | 1 | 17 |
| Qwen MATCH | 338 | 3 | 2 | 157 |
| Qwen PROJECT | 337 | 3 | 4 | 156 |
| DeepSeek REF 非思考 | 496 | 3 | 0 | 1 |
| DeepSeek REF 思考 | 492 | 7 | 0 | 1 |
| DeepSeek MATCH 非思考 | 478 | 21 | 0 | 1 |
| DeepSeek MATCH 思考 | 433 | 66 | 0 | 1 |
| DeepSeek PROJECT 非思考 | 455 | 34 | 10 | 1 |
| DeepSeek PROJECT 思考 | 466 | 28 | 5 | 1 |
| 合计 | 3970 | 172 | 22 | 336 |

Qwen保持7路生成；DeepSeek此时15路运行全部位于PROJECT两组。DeepSeek剩余6个pending均被共享准备状态分类为 `environment_failed`，每组1个；Qwen每组也各有1个相同分类的pending。该分类来自现有准备元数据，没有重新运行环境验证，不能直接作为模型失败，也不能为凑齐500题改写结果。这些剩余环境问题与仍在生成的长尾需要分别判断；DeepSeek低于当时26路资源目标，本身不证明新的容量阻塞。

两个队列均处于 `running`，state观察年龄分别约4.19秒与4.09秒。四个受观察管理服务均为 `active/running`。Pool转换状态仍为空，不能据此宣称GPU7已转接MATCH／PROJECT。

主、副、第三卷普通可用容量约为 **431.3、296.4、297.4 GiB**。这是观察时的物理可用容量，不等同于扣除活动任务增长预约后的派发余量；准入仍以各队列的预约门判定。首次快照中DeepSeek CPU／内存准入和生成／准备磁盘门均通过。

DeepSeek首次账本快照的已结算费用为 **538.06597822元**，含在途及未知保留金额的承诺费用为 **553.79461822元**，总上限仍为2000元。其中未知与补充保留共10.48576元，在途保留5.24288元。账本未halt、未处于冷却，累计记录的HTTP 429为0。金额在一次只读SQLite事务中读取，包含 `requests` 与 `budget_adjustments`，不把技术未知成本当成零。

## 每小时判读方法

每次对比前后实际时间与队列快照，报告九组的生成闭合、技术未知、运行、pending，以及代码评分和PROJECT交付评分各自状态。速率按实际经过时间计算；生成正常闭合与技术未知新增分别报告，不把两者相加称为成功速度。单次基线不足以估计本窗口速率。

同时检查manager生命周期与heartbeat、正在运行的预热、备用环境、磁盘预约门、CPU／内存、GPU资源健康、API冷却／限流、账本总承诺金额与剩余预算。GPU瞬时利用率低或一小时无新增某组闭合，不单独构成故障证据，须结合公开测试、评分、工作单元存活和长尾状态判断。

预计完成时间仅针对当时可运行的首轮生成与异步评分；环境失败、技术未知与后续异常集合处理单列。完整500题分母始终保留，不能把已闭合子集当成完整基准，也不能将代码正确性与项目交付混为一项。

## 服务与安全恢复边界

当前精确服务如下。四者均配置 `Restart=no`，监控不会把已正常收尾的服务误当成需要恢复的故障。

| 功能 | 服务 | 停止语义 |
| --- | --- | --- |
| Qwen队列 | `proworksim-v054-formal-queue-three-volumes-r6.service` | `KillMode=process` |
| DeepSeek队列 | `proworksim-v055-deepseek-six-conditions-native-host-r9.service` | `KillMode=process` |
| REF显卡转接 | `proworksim-v054-dynamic-pool-ref-handoff-r1.service` | `KillMode=process` |
| 共享缓存回收 | `proworksim-v055-cache-reclamation-r2.service` | `KillMode=control-group` |

### 队列管理器

管理器自然failed／inactive且MainPID为0时，先判断队列是否已经正常完成、因预算闭合，或因共享完整性故障暂停。只有原封存输入完整、原状态允许继续、没有其他控制器持锁，才可用同一服务的封存启动参数恢复。原worker保持独立运行，协调器沿原durable state收集结果；缺失完成证据的entered工作进入技术未知，不自动重放。

Qwen r6继承的VolumeCoordinator要求 `state.status == running`。`paused_technical_unknown`、`source_changed`或新的共享故障不能靠重启消除，更不能手改状态或重新执行旧adopt。此类修复需要明确的新故障证据和独立恢复revision。DeepSeek r9同参数重启会经过r8构造器，可能在host历史追加r8→r9两条元数据；这不是正式回合重放，也不能描述为“所有元数据完全未变”。

服务active但state显著不更新时，先读取精确unit日志、PID／InvocationID、wchan及阻塞的子命令。若确需只交接manager，采用现有已验证流程：确认身份，等待 `hrtimer_nanosleep`，保存state字节，暂挂仅manager并证明state未变，写入操作intent，再停止仅manager并使用封存参数启动，最后检查原worker身份和新heartbeat。无法取得安全边界时不强杀；不对GPU、worker或整个cgroup进行连带重启。旧三卷部署脚本绑定历史前驱，不能原样再执行。

### 驻留模型与REF转接

单resident的PID、socket或poisoned健康异常由既有健康过滤隔离，其余健康资源继续。实际模型load失败、控制调用未知、账本隔离和 `failed_manual_action_required` 不自动重载；只有明确尚未load、零模型调用的容量／lease拒绝，才沿已有 `resource_wait` 政策等待。

REF转接若停在 `retirement_intent` 或失败状态，必须核对原REF进程／cgroup、retirement记录及MP启动是否已经进入，独立修复并记录新证据。不能清空conversion或删除目录以再次执行转换，也不能为获得GPU7容量把未定题静默改成已完成。

### 缓存回收

共享缓存watcher继续执行原九组消费者及评分全部terminal、当前进程和锁静止、精确模板身份等门槛。每批最多4个helper，每个最长620秒，状态文件可能约41分钟不更新；不能仅据heartbeat年龄判断卡死。由于其 `KillMode=control-group`，active期间不能按队列manager方式直接restart，避免中断删除helper。

watcher自然退出且helper已结束后可按原seal恢复。`.completed`、`.failed`、`.intent`、`.dispatch-uncertain`均保留，原工具自动跳过未闭合删除现场，后续单独审计。不得删标记“解锁”，也不得删除仍由Qwen消费的共享模板。

## 修复不得改变的约束

- 保留原题单、seed、模型、模板、科学配置与最终候选规则；不把entered generation改回pending，不删除claims或既有目录绕过重放保护。
- 保留DeepSeek总预算2000元、API并发64及CPU／内存硬约束；不清账本halt、不删除未知保留、不重建账本或重复使用旧财务恢复授权。
- 保留生成100 GiB、准备128 GiB的磁盘底线及增长预约。挂载或卷身份异常时继续拒绝派发；仅在核对原device与marker后修复原bind，不让任务写到丢失挂载下的主盘目录。
- 不热改封存源码，不重复旧adoption。修复与观察分开保存实际时间、触发证据、范围、变更及恢复后观察；未恢复的问题保持明确的技术未知／资源限制，不填成模型失败。

## 窗口内修复进展：00:44:38

针对首次观察中阻塞九个未进入槽的单题环境问题，已开展独立的partial-export恢复。首次r1尝试在导出前失败，原失败记录保留，没有将其覆盖为成功。后续r2改用system unit，于 **2026年10月23日00:44:38** 实际启动，启动时PID为2457109。操作侧实读其cgroup：`cpu.max=400000 100000`、`memory.max=17179869184`、`pids.max=16384`，对应4 CPU配额、16 GiB内存及16384任务上限。这里的实读证明只属于该r2准备worker，不能外推为前述user采样单元的CPU硬限制已生效。

该次交接保持r9的原service定义与执行参数，仅在停止manager并登记恢复worker后恢复同名manager。00:44:38阶段的队列状态为 `preparing`；这一时点仅证明恢复准备已启动，不表示当时环境已通过准入或正式九槽已完成。后续须按真实结果更新，保留任何新失败，不能重新执行已有durable intent来重试。

### 00:47:21准备成功及00:47:49队列接入

r2准备实际开始于 **00:44:39**，于 **00:47:21** 返回 `qualified`。本次恢复只对固定本地image重新导出1次，修复模型调用为0；没有更换镜像版本、参考题目成绩选环境或重放已进入的生成回合。首次r1失败仍作为独立历史保留。

`runs/software-benchmark-v055/partial-export-recovery-r2/first-queue-adoption-observation.json` 记录 **00:47:49** 的首次队列接入观察：原先从未进入的DeepSeek六个槽均已取得 `qualified` 环境并首次进入 `running`，Qwen三个槽仍按原队列顺序保持pending。该对比表明阻塞环境已恢复并被原队列消费，不表示这些正式回合已完成生成或通过官方评分；其后结果仍计入各自原组和原500题分母。

六小时窗口仍在进行。后续小时观察、准备恢复结果、窗口终止状态和六小时净进度由后续真实记录补充。

## 第一次小时观察：01:12:51

编号01的实际观察时间为 **2026年10月23日01:12:51.199363（北京时间）**，采集局部错误为0。相对编号00的00:20:00.512895，实际间隔为 **3170.686468秒，即52.844774分钟**；没有把迟到的基线按完整60分钟计算速率。

| 组别 | 生成闭合 | 生成技术未知 | 运行中 | 待运行 | 较基线新增闭合 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Qwen REF | 493 | 7 | 0 | 0 | 18 |
| Qwen MATCH | 354 | 4 | 3 | 139 | 16 |
| Qwen PROJECT | 355 | 3 | 3 | 139 | 18 |
| DeepSeek REF 非思考 | 497 | 3 | 0 | 0 | 1 |
| DeepSeek REF 思考 | 493 | 7 | 0 | 0 | 1 |
| DeepSeek MATCH 非思考 | 479 | 21 | 0 | 0 | 1 |
| DeepSeek MATCH 思考 | 434 | 66 | 0 | 0 | 1 |
| DeepSeek PROJECT 非思考 | 464 | 36 | 0 | 0 | 9 |
| DeepSeek PROJECT 思考 | 472 | 28 | 0 | 0 | 6 |
| 合计 | **4041** | **175** | **6** | **278** | **71** |

本间隔Qwen新增正常生成闭合 **52**、生成技术未知 **1**，按实际间隔为 **59.040842回合/小时**；其中REF为20.437215，MATCH／PROJECT合计38.603628回合/小时。DeepSeek新增正常生成闭合 **19**、生成技术未知 **2**，区间速率 **21.572615回合/小时**。DeepSeek这段时间进入首轮库存收尾，后一速率包含收尾后的空闲时间，不能当作仍有足量待运行任务时的稳态吞吐或性能下降证据。以上只计算生成正常闭合，不把技术未知加入“成功速率”。

DeepSeek原3000槽此时为 **2839生成闭合、161生成技术未知，pending与running均为0**；状态明确为 `primary_inventory_finished`，最后state更新时间01:02:05。manager为 `inactive/dead`、`MainPID=0`、`Result=success`，结合库存终态判定为正常收尾，不因它不再刷新state而重启。共享准备状态已记录 **500/500 qualified**；基线中的单题环境阻塞已消除。首轮库存结束不代表完整实验结论已经得出：代码评分另有 **42个technical_unknown端点**，PROJECT交付评分另有 **5个technical_unknown端点**，这些与161个生成技术未知分别保留，不能合并为独立失败任务数或填成模型失败，也不能把只读resolved计数当作完整500题最终点估计。

Qwen REF的500槽已达到 **493闭合＋7技术未知** 的生成库存边界；MATCH／PROJECT仍有278个pending、6个running，pending全部按准备元数据分类为 `ready_waiting`。REF→MP转换在本快照中为 `failed_manual_action_required`，错误为 **`KeyError('invocation_id')`**，并保留原 `retirement_intent`。该具体故障已进入独立修复处理；此观察点尚无成功转接证据，不能写成GPU7已承接MATCH／PROJECT。Qwen队列、pool monitor和共享缓存回收manager均仍为active/running，既有MATCH／PROJECT任务继续。

本次宿主1分钟load为8.9424，可用内存约 **941.4GiB**；主、副、第三卷普通可用空间约 **461.1、312.5、338.6GiB**。Qwen最近一次生成磁盘准入通过，预计发出该任务后扣预约余量428,047,139,006B，仍高于100GiB门；CPU、内存、磁盘与预算没有出现新的准入阻塞证据。DeepSeek已结算 **539.96575482元**，总承诺 **550.45151482元**，含未知及补充保留10.48576元、在途保留0元，剩余未承诺预算 **1449.54848518元**。账本halt与cooldown均为空，HTTP 429累计仍为0。

本记录只整理既有编号01观察，没有补采系统数据或执行修复。独立不可覆盖副本：[snapshot-01.json](../../artifacts/software-benchmark-v055/six-hour-monitor-r1/snapshot-01.json)、[summary-01.json](../../artifacts/software-benchmark-v055/six-hour-monitor-r1/summary-01.json)。六小时窗口继续，转换修复的实际结果需用后续独立证据追加。

## GPU7转接故障实际恢复：01:27—01:29

针对编号01观察中的 `KeyError('invocation_id')`，独立身份恢复已完成，原失败与retirement intent保留。北京时间 **01:27:44.635** 完成原REF驻留实例退役；**01:27:45**，原pool monitor开始GPU7上的第一次MATCH／PROJECT驻留模型加载；**01:29:17** 新实例达到 `qualified_registered`。该过程是明确记录的REF→MP资源转换，没有把先前失败时点改写成已成功转接。

身份修复工具本身的模型调用为0；随后完整资源转接的资格验证实际包含 **6次准备性模型生成请求，共1620 token，未结算请求0，模型加载1次**。因此不能将“修复工具0模型调用”表述成整个转接没有模型调用。资格请求属于驻留实例准备，不增加正式500题面板的回合数。

**01:29:59.718311** 的既有 `first-mp-dispatch-observation.json` 记录Qwen队列继续为running，实际生成并发已从6路升至 **8路**。新实例 `mp-g7-0303dcc7` 在GPU7同时承接两个首次运行的正式槽：`v054-PROJECT-pytest-dev__pytest-7236` 与 `v054-MATCH-django__django-11433`。该观察证明GPU7已通过资格准入并进入正式派发；仅凭这一时点不能宣称已获得稳定小时吞吐提升，实际速度仍待后续小时快照比较。

本节只整理已落盘的修复及首次派发证据，没有新查系统、额外采样或执行新操作。原始观察：[first-mp-dispatch-observation.json](../../runs/software-benchmark-v054/ref-handoff-identity-recovery-r2/first-mp-dispatch-observation.json)。

原monitor不会在MP注册后继续更新conversion中的 `ref_retired_waiting_for_mp_capacity` 标签；后续观察以GPU7的 `qualified_registered` 与实际派发为准，不能仅凭这个保留字段判定仍在等待容量。
