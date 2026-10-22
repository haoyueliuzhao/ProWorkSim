# 九组实验六小时监控：完成结果、修复与证据（r1）

本轮根据用户“持续监控6个小时，每隔一个小时检测查询一次，期间自主修复”的要求开展，**六小时监控已实际完成**。计划窗口为 **2026年10月23日00:12:51—06:12:51，北京时间（Asia/Shanghai，UTC+08:00）**，最后一份r7管理器补充于 **06:12:56.191783** 取得、06:12:56.290524写完。活动监控及最终补充覆盖至06:12:56；原计划的7个主观察点与后加的4个r7只读补充全部存在，局部采集错误均为0。

首次完整基线实际为 **00:20:00.512895**，较原起点延迟429.512895秒；没有伪造00:12:51的完整快照。以下净增量与速率按00:20:00至06:12:51这段 **21170.686067秒** 的真实主样本跨度计算。监控完成不代表九组实验全部完成：结束时仍有62个Qwen生成非终态槽，生成／评分技术未知集合及最终分析尚未完成。

## 窗口结束概览

相对真实基线，Qwen新增正常生成闭合 **273**、DeepSeek新增 **19**，合计 **292**；生成技术未知分别新增 **2、2**。这些是运行生命周期变化，不是新增正确修复数。最终Qwen为1423正常闭合、15生成技术未知、8运行、54pending；DeepSeek为2839正常闭合、161生成技术未知，运行和pending均为0。DeepSeek已自然结束首轮库存；Qwen继续保持四卡八路，监控窗口结束没有停止其实验服务。

最终统一证据：[final-summary.json](../../artifacts/software-benchmark-v055/six-hour-monitor-r1/final-summary.json)，SHA-256 `5ceef97c64bbde9d7ec08aaebe34ee63a2dcd31de0484dbfc83ea2cec24d9609`。该汇总仅使用已有观察，没有新采样或修改原实验结果。

### 最后九组生成状态（主样本06:12:51）

每组计划分母仍为500题。下表只报告生成状态，不计算跨配置混合通过率。

| 组别 | 正常生成闭合 | 生成技术未知 | 运行中 | 待运行 |
| --- | ---: | ---: | ---: | ---: |
| Qwen REF | 493 | 7 | 0 | 0 |
| Qwen MATCH | 466 | 4 | 3 | 27 |
| Qwen PROJECT | 464 | 4 | 5 | 27 |
| DeepSeek REF 非思考 | 497 | 3 | 0 | 0 |
| DeepSeek REF 思考 | 493 | 7 | 0 | 0 |
| DeepSeek MATCH 非思考 | 479 | 21 | 0 | 0 |
| DeepSeek MATCH 思考 | 434 | 66 | 0 | 0 |
| DeepSeek PROJECT 非思考 | 464 | 36 | 0 | 0 |
| DeepSeek PROJECT 思考 | 472 | 28 | 0 | 0 |
| 运行库存合计 | **4262** | **176** | **8** | **54** |

评分未知与生成未知分开统计，且评分两端点之间也可能对应同一任务，不能相加解释为独立失败题数：

| 家族 | 生成技术未知槽 | 代码评分技术未知端点 | PROJECT交付评分技术未知端点 |
| --- | ---: | ---: | ---: |
| Qwen | 15 | 15 | 0 |
| DeepSeek | 161 | 42 | 5 |
| 合计 | **176** | **57** | **5** |

最终保存状态另有238个代码报告尚未创建；其中包含生成未知和未结束生成，不能自动算成238个已排队评分作业。REF／MATCH不适用项目交付指标，不能填0当作交付失败。技术未知继续作为待审计状态，不填成模型失败，不把已有resolved计数汇成未经闭合的完整500题点估计；异常集合处理与正式结果分析均未在本次监控中宣称完成。

### 逐小时实际进度

“本段新增”与“生成未知”两列均按Qwen／DeepSeek顺序列数；00点是实际迟到基线，01点区间约52.84分钟，其余按实际约一小时计算。

| 编号 | 实际北京时间 | Qwen正常闭合累计 | DeepSeek正常闭合累计 | 本段新增正常闭合（Q／D） | 生成未知累计（Q／D） | Qwen运行 | Qwen待运行 |
| --- | --- | ---: | ---: | --- | --- | ---: | ---: |
| 00 | 00:20:00.512895 | 1150 | 2820 | 基线 | 13／159 | 7 | 330 |
| 01 | 01:12:51.199363 | 1202 | 2839 | 52／19 | 14／161 | 6 | 278 |
| 02 | 02:12:51.199204 | 1241 | 2839 | 39／0 | 15／161 | 8 | 236 |
| 03 | 03:12:51.162618 | 1289 | 2839 | 48／0 | 15／161 | 8 | 188 |
| 04 | 04:12:51.200095 | 1338 | 2839 | 49／0 | 15／161 | 8 | 139 |
| 05 | 05:12:51.198262 | 1380 | 2839 | 42／0 | 15／161 | 8 | 97 |
| 06 | 06:12:51.198962 | 1423 | 2839 | 43／0 | 15／161 | 8 | 54 |

截至末次观察，Qwen最近1、2、3个小时区间分别新增正常闭合 **43、85、134**，按真实时长为 **42.999992、42.500007、44.666516回合/小时**；三个区间均没有新增生成技术未知。该速度仍受任务构成和长尾影响，不是长期稳定性保证，也不能将前后差值完全归因于单个修复。剩余62个生成非终态槽按近期速度并留出长尾余量，首轮生成库存收尾仍粗估为 **10月23日07:00—08:00**；这个时段不包含生成未知、评分异常集合处理和最终分析。

### 三项实际修复与未变边界

1. **恢复单题环境。** 对 `matplotlib__matplotlib-25122` 保留原失败和首次恢复失败记录，以独立r2重新导出固定本地image，00:47:21准备qualified、00:47:49原六个未进入DeepSeek槽首次获准运行；随后共享环境覆盖达到500/500 qualified。没有根据模型成绩换题或重放已进入回合。详见[partial-export恢复r2](software-benchmark-v055-partial-export-recovery-r2.md)。
2. **恢复GPU7 REF→MP转接。** 对 `invocation_id` 身份错误独立恢复，01:27:44.635完成已结束REF实例退役，01:27:45首次加载MP、01:29:17通过资格；01:29:59已有两槽正式派发，MP并发由6升至8。身份修复工具本身0模型调用，但完整转接资格验证实际使用 **6次准备请求、1620 token、0未结算请求、1次模型加载**，不能宣称整个修复窗口零模型成本。详见[转接身份恢复r2](software-benchmark-v054-ref-handoff-identity-recovery-r2.md)。
3. **修复未来回合监督身份读取竞态。** r7在02:33:51交接manager，8个旧在途job身份保持原样。新独立overlay仅对精确已登记PID的 `/proc/<pid>/stat` 消失作有限重取，仍由原完整静止检查决定结果；canonical与kernel两条未来路径均取得真实闭合证据，两份选定实例没有触发目标重取，不能据此宣称现场复现或完全消除竞态。旧unknown不改判。详见[监督进程退出竞态修复及真实接入](software-benchmark-v054-supervision-proc-exit-r1.md)。

这些恢复保留旧worker及其job，不中断既有正式任务，不自动重跑entered生成回合；只对已经到达生成库存边界的原REF驻留实例执行计划内退役。题单、seed、模型、提示与工具的科学bindings、token／时间预算和候选评分规则保持原封存值；独立运维revision及其启用时间另行留痕，不把监督运行细节写成修订前后完全相同。

结束时r7 active/running（PID3078377、绑定匹配，06:12:56的state年龄5.764728秒），pool和cache服务同样active/running；原r6已退役、DeepSeek正常收尾退出，均未误报为需要重启。末次宿主1分钟load为8.6626，可用内存约953.8GiB，主／副／第三卷普通可用空间约673.7／309.0／338.6GiB；Qwen最近磁盘准入通过，无新的资源门阻塞证据。

DeepSeek总预算仍为 **2000元**，已结算 **539.96575482元**，含未知及调整保留的总承诺 **550.45151482元**，剩余未承诺1449.54848518元；未知与调整保留10.48576元，在途保留0元，halt/cooldown为空、HTTP 429累计0。真实基线以来已结算增加1.8997766元；承诺金额下降来自在途预约释放，不能解释成退款。以上账本不含未在此处计价的Qwen GPU驻留和准备成本。

GPU0／1／2／4旧失败未恢复：[静态审计](software-benchmark-v054-failed-extra-gpu-static-audit-20261023.md)只确证原启动记录与限制，没有新增CUDA诊断或盲目加载。当前四卡八路继续运行，不将“未进入loader”写成“没有消耗启动尝试”。共享cache回收仍受九消费者终态及完整writer静止门约束；04:16:40补充记录中的4项因历史静止证明不足而延期、实际删除0项，没有绕过删除门，也不宣称所有旧数据已清空。见[cache-watcher-observation-04.json](../../artifacts/software-benchmark-v055/six-hour-monitor-r1/cache-watcher-observation-04.json)。

以下保留方法、恢复边界及各观察时点的历史记录；其中“窗口继续”“待后续观察”等陈述只表示当时状态，当前完成结论以前置概览和末次记录为准。

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

起点登记的精确服务如下。四者均配置 `Restart=no`，监控不会把已正常收尾的服务误当成需要恢复的故障；02:33:51之后Qwen实际manager为后文独立记录的r7。

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

以上为00:47阶段保留记录；后续实际小时观察、窗口终止状态和净进度见前置最终概览及按时点保留的后续章节。

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

原monitor不会把历史conversion标签 `ref_retired_waiting_for_mp_capacity` 自动更新为complete；后续应结合GPU7设备项的 `qualified_registered` 与真实正式派发证据判读，不能仅凭该历史标签误报GPU7仍在等待容量。

## 第二次小时观察：02:12:51

编号02实际观察于 **2026年10月23日02:12:51.199204（北京时间）**，距编号01为 **3599.999841秒**，局部采集错误为0。Qwen三组此时合计 **1241生成闭合、15生成技术未知、8运行、236待运行**。

| Qwen组别 | 生成闭合 | 生成技术未知 | 运行中 | 待运行 | 本间隔新增闭合 |
| --- | ---: | ---: | ---: | ---: | ---: |
| REF | 493 | 7 | 0 | 0 | 0 |
| MATCH | 375 | 4 | 3 | 118 | 21 |
| PROJECT | 373 | 4 | 5 | 118 | 18 |

MATCH／PROJECT本间隔新增正常生成闭合 **39**，按实际间隔为 **39.000002回合/小时**，另新增1个PROJECT生成技术未知。此区间包含01:29才完成8路正式派发的过渡阶段；前一区间MATCH／PROJECT合计为38.603628回合/小时，现有两个区间不能支持“已稳定提速”的结论。当前8路实际运行与236个 `ready_waiting` 说明队列继续推进，不需要为追求某个瞬时速率重载驻留模型。

DeepSeek六组库存及账本与编号01相同：**2839闭合、161生成技术未知、0运行、0pending**，状态仍为 `primary_inventory_finished`；代码评分42个技术未知端点、PROJECT交付评分5个技术未知端点继续独立保留。manager保持 `inactive/dead`、`Result=success`，这是已收尾库存的正常状态。本间隔DeepSeek无新请求费用：已结算539.96575482元，总承诺550.45151482元，在途保留0元，halt/cooldown为空、累计HTTP 429为0，未因其停止增加生成数而重启。九组总生成闭合为 **4080/4500**，另176生成技术未知、8运行、236pending；该计数不是官方通过率。

GPU7设备项继续为 `qualified_registered`，原有正式派发证据有效；conversion保留的 `ref_retired_waiting_for_mp_capacity` 是历史标签，不表示本时点仍未转接。GPU3、GPU6在这一次瞬时观测中的利用率为0，GPU5为95%、GPU7为100%；单个瞬时0值不能证明resident故障或停工，未据此重启或改派在途任务。

本时点1分钟load为10.5869，可用内存约 **941.3GiB**；主、副、第三卷普通可用空间约 **477.6、309.0、338.6GiB**。Qwen磁盘预约元数据无错误，最近生成准入通过，预计新任务启动并扣预约后余量419,677,922,366B，高于100GiB门；没有新的CPU／内存、磁盘或预算门阻塞证据。Qwen、pool及cache manager保持active/running，DeepSeek正常收尾未重启。

本节只使用已生成的编号02材料，没有新采样或查询系统。独立不可覆盖副本：[snapshot-02.json](../../artifacts/software-benchmark-v055/six-hour-monitor-r1/snapshot-02.json)、[summary-02.json](../../artifacts/software-benchmark-v055/six-hour-monitor-r1/summary-02.json)。

## Qwen管理器r7交接与后续只读补充：02:33:51

北京时间 **02:33:51** 已部署独立 `proworksim-v054-formal-queue-supervision-r7.service`，启动PID为3078377，revision为 `runs/software-benchmark-v054/supervision-host-r7/revision.json`，SHA-256 `a39b1b7c25794df9d12bd738dc90e78bd4423c9a466444bbf08238f2d5e4438f`。既有 `first-adoption-observation.json` 于 **02:34:09.797944** 记录新队列running、对应 `supervision_host` 绑定，8个旧在途槽仍为running且job身份相同。该证据只证明此次manager交接和旧job延续，不提前判定新回合的最终结果。

原r6 manager已正常退役。冻结的r1 collector、原schedule和六个原timer保持不变，因此原编号03—06快照仍会查询r6的精确unit名；后续看到r6 inactive，须与本次交接及r7补充记录结合，不误报为当前Qwen队列停机。

为保留原观察协议，已准备独立最小补充采样器 `tools/observe_qwen_manager_r7_hourly_v055_r1.py`，只读取r7 unit属性、Qwen `supervision_host` 绑定及生成生命周期计数，并关联对应原编号03—06快照。它不重新观察GPU或账本，不重算完整队列hash，不修改原快照、队列或服务。输出为 `manager-r7-03.json` 至 `manager-r7-06.json`，使用不可覆盖写入并记录实际UTC／北京时间；原快照迟到或局部读取失败单独记错，不丢失已经取得的r7信息。

补充计划 `runs/software-benchmark-v055/six-hour-monitor-r1/manager-r7-plan.json` 冻结四个时刻 **03:12:56、04:12:56、05:12:56、06:12:56（北京时间）**，对应原观察时刻后5秒。计划SHA-256为 `e0d304b9077bd551072b72068e377456bdd3abac2784c2aaa0ccdd06debd3e33`；补充collector SHA-256为 `459c50a1a9bc8e0e1a4ec2036d4a6c0211c6ebad5c8e3a2bc282b60288efba93`，部署器 `tools/schedule_qwen_manager_r7_hourly_v055_r1.py` SHA-256为 `463277e003938a61afadeaa6924d89fa69f606761d7f6f13b238c362643062f7`。部署器只创建四个独立一次性只读timer，名字为 `proworksim-v055-six-hour-monitor-r1-manager-r7-<编号>.timer`，不接触原timers。准备时仅执行Ruff、语法与固定索引／时刻参数检查，没有运行补充采样器、创建systemd服务或调用模型。

主协调者随后于 **02:38:09** 实际执行补充部署，编号03—06的四份独立部署回执均为 `returncode=0`，此时四个观察时刻仍在未来。部署成功不等于未来采样已发生；每次实际观察时间和局部错误继续按不可覆盖输出记录。原计划文件保留准备时的 `deployment_status=prepared_not_executed`，实际已部署由较后的intent和四份回执证明，不回写冻结计划。独立副本：[补充计划](../../artifacts/software-benchmark-v055/six-hour-monitor-r1/manager-r7-plan.json)、[部署intent](../../artifacts/software-benchmark-v055/six-hour-monitor-r1/manager-r7-deployment-intent.json)、[03](../../artifacts/software-benchmark-v055/six-hour-monitor-r1/manager-r7-deployment-03.json)、[04](../../artifacts/software-benchmark-v055/six-hour-monitor-r1/manager-r7-deployment-04.json)、[05](../../artifacts/software-benchmark-v055/six-hour-monitor-r1/manager-r7-deployment-05.json)、[06](../../artifacts/software-benchmark-v055/six-hour-monitor-r1/manager-r7-deployment-06.json)。新宿主已接管旧8个job，主协调者随后观察到4个canonical未来worker带有overlay标记；这一阶段尚未取得新overlay正式闭合证据，留待03时观察统一记录，不提前作成功判定。

## 第三次小时观察：03:12:51及r7补充03:12:56

编号03实际观察于 **2026年10月23日03:12:51.162618（北京时间）**，距编号02为 **3599.963414秒**，采集错误0。Qwen合计 **1289生成闭合、15生成技术未知、8运行、188待运行**。

| Qwen组别 | 生成闭合 | 生成技术未知 | 运行中 | 待运行 | 本间隔新增闭合 |
| --- | ---: | ---: | ---: | ---: | ---: |
| REF | 493 | 7 | 0 | 0 | 0 |
| MATCH | 399 | 4 | 3 | 94 | 24 |
| PROJECT | 397 | 4 | 5 | 94 | 24 |

本间隔MATCH／PROJECT共新增正常生成闭合 **48**，生成技术未知新增 **0**，按实际间隔为 **48.000488回合/小时**。相较上一过渡小时的39闭合，观察到约 **23.08%** 的区间吞吐增加；两个区间的任务组成不同，且本区间发生了r7监督修订，不能将差值全部归因于GPU7转接，也不能据此保证长期稳定增速。8路继续运行、188个pending均有ready元数据，正式任务仍沿原队列推进。

独立r7补充实际于 **03:12:56.191875** 取得，局部错误0：`proworksim-v054-formal-queue-supervision-r7.service` 为active/running，PID **3078377**，`expected_revision_binding_matches=true`，队列状态running、state年龄 **4.815305秒**。原r1快照中r6为 `inactive/dead`、`LoadState=not-found`、MainPID0，是前述正常退役后的状态；结合r7实际观测，不构成当前队列掉线。补充记录链接到原编号03快照的准确SHA，原观察与schedule没有被改写。

DeepSeek继续保持首轮终态 **2839闭合、161生成技术未知、0运行、0pending**，六组分项及代码评分42个未知／交付评分5个未知端点未变；正常收尾的manager仍inactive，不启动新生成或自动重放未知任务。费用保持已结算539.96575482元、总承诺550.45151482元，含未知保留10.48576元，在途保留0元，累计HTTP 429仍为0，halt/cooldown为空。九组累计 **4128生成闭合、176生成技术未知、8运行、188pending**，仍以原4500槽为计划分母。

宿主1分钟load为9.4951，可用内存约 **950.0GiB**；主、副、第三卷普通可用空间约 **519.7、309.0、338.6GiB**。Qwen磁盘预约元数据无错误，最近生成准入通过，预计扣预约后的启动余量453,772,319,996B，高于100GiB底线。本次未见CPU／内存、磁盘或API预算的新阻塞证据。

本节只整理已有原样本和r7补充，没有新采样、GPU查询或运行变更。独立不可覆盖副本：[snapshot-03.json](../../artifacts/software-benchmark-v055/six-hour-monitor-r1/snapshot-03.json)、[summary-03.json](../../artifacts/software-benchmark-v055/six-hour-monitor-r1/summary-03.json)、[manager-r7-03.json](../../artifacts/software-benchmark-v055/six-hour-monitor-r1/manager-r7-03.json)。

## 第四次小时观察：04:12:51及r7补充04:12:56

编号04实际观察于 **2026年10月23日04:12:51.200095（北京时间）**，距编号03为 **3600.037477秒**，采集错误0。Qwen合计 **1338生成闭合、15生成技术未知、8运行、139待运行**。

| Qwen组别 | 生成闭合 | 生成技术未知 | 运行中 | 待运行 | 本间隔新增闭合 |
| --- | ---: | ---: | ---: | ---: | ---: |
| REF | 493 | 7 | 0 | 0 | 0 |
| MATCH | 424 | 4 | 3 | 69 | 25 |
| PROJECT | 421 | 4 | 5 | 70 | 24 |

本间隔MATCH／PROJECT共新增正常生成闭合 **49**，生成技术未知新增 **0**，按实际间隔为 **48.999490回合/小时**。最近两个小时合计新增 **97** 个正常生成闭合，实际经过7200.000891秒，约 **48.5000回合/小时**。这表明近两段小时窗口持续推进，但仍受任务组成和长尾影响，不作未来吞吐保证。当前尚有 **147个生成非终态槽（139pending＋8running）**；按近期速度并给长尾留出余量，首轮生成库存收尾谨慎估计为 **10月23日07:00—08:00**。该估计不包含生成技术未知集合处理、评分异常处理和最终统计，也不承诺所有槽都正常闭合或通过官方测试。

r7补充实际于 **04:12:56.192272** 取得，局部错误0：当前manager active/running，PID **3078377**，revision绑定匹配，队列running且state年龄 **1.986797秒**。pool及cache manager同样active/running；原r6 inactive/not-found继续按已完成交接理解。现阶段保持四张已准入显卡、八路生成，额外显卡既有失败记录的判断依据见[额外GPU静态审计](software-benchmark-v054-failed-extra-gpu-static-audit-20261023.md)，本小时未因观察到空余容量而重放失败加载。

DeepSeek库存及账本保持不变：2839生成闭合、161生成技术未知，运行与pending均为0；代码评分42个技术未知端点、交付评分5个技术未知端点继续单列。已结算539.96575482元、总承诺550.45151482元，在途保留0元，halt/cooldown为空、HTTP 429累计0，manager正常收尾保持inactive。九组总计 **4177生成闭合、176生成技术未知、8运行、139pending**；完整计划仍为4500槽。

本时点宿主1分钟load为12.0259，可用内存约 **951.3GiB**，主、副、第三卷普通可用空间约 **581.4、309.0、338.6GiB**。Qwen磁盘预约元数据无错误，最近生成准入通过，预计扣预约后的启动余量525,815,675,923B，高于100GiB底线；本次没有发现新的CPU／内存、磁盘或预算准入阻塞。

本节只整理已生成的原样本和r7补充，没有新采样或运行修改。独立不可覆盖副本：[snapshot-04.json](../../artifacts/software-benchmark-v055/six-hour-monitor-r1/snapshot-04.json)、[summary-04.json](../../artifacts/software-benchmark-v055/six-hour-monitor-r1/summary-04.json)、[manager-r7-04.json](../../artifacts/software-benchmark-v055/six-hour-monitor-r1/manager-r7-04.json)。

## 第五次小时观察：05:12:51及r7补充05:12:56

编号05实际观察于 **2026年10月23日05:12:51.198262（北京时间）**，距编号04为 **3599.998167秒**，采集错误0。Qwen合计 **1380生成闭合、15生成技术未知、8运行、97待运行**。

| Qwen组别 | 生成闭合 | 生成技术未知 | 运行中 | 待运行 | 本间隔新增闭合 |
| --- | ---: | ---: | ---: | ---: | ---: |
| REF | 493 | 7 | 0 | 0 | 0 |
| MATCH | 444 | 4 | 4 | 48 | 20 |
| PROJECT | 443 | 4 | 4 | 49 | 22 |

本间隔MATCH／PROJECT新增正常生成闭合 **42**，生成技术未知新增 **0**，按实际间隔为 **42.000021回合/小时**。最近三个小时共新增 **139** 个正常生成闭合，约 **46.33回合/小时**。单小时由49变为42只反映当前任务窗口的观察，不能据此认定出现新故障，也不表述为稳定提速。当前尚有 **105个生成非终态槽（97pending＋8running）**；结合近期均速和长尾，首轮生成库存收尾仍粗估在 **10月23日07:00—08:00**。生成未知集合、评分异常与最终统计不包含在该估计中，是否正常闭合或通过官方测试仍按各自真实结果判定。

r7补充实际于 **05:12:56.191586** 取得，局部错误0：manager active/running、PID **3078377**、revision绑定匹配；队列running，state年龄 **2.164020秒**。原r6的inactive/not-found仍为正常退役后的历史观察，不能替代对当前r7的判断。Qwen保持8个在途任务，队列没有因DeepSeek已正常收尾而停派。

DeepSeek六组库存和账本没有变化：2839生成闭合、161生成技术未知、0运行、0pending，代码评分42个技术未知端点和交付评分5个技术未知端点继续分开保留。已结算539.96575482元、总承诺550.45151482元，在途保留0元，halt/cooldown为空、HTTP 429累计0。九组累计 **4219生成闭合、176生成技术未知、8运行、97pending**；生成闭合计数不等于官方测试通过数。

本时点1分钟load为12.4429，可用内存约 **953.5GiB**；主、副、第三卷普通可用空间约 **630.9、309.0、338.6GiB**。Qwen磁盘预约元数据无错误，最近生成准入通过，预计扣预约后的启动余量591,022,464,044B，高于100GiB底线。已有观察未显示CPU／内存、磁盘或预算的新准入阻塞，没有为单小时吞吐变化执行额外重载。

本节仅使用既有编号05材料，没有新增采样、查询系统或修改运行状态。独立不可覆盖副本：[snapshot-05.json](../../artifacts/software-benchmark-v055/six-hour-monitor-r1/snapshot-05.json)、[summary-05.json](../../artifacts/software-benchmark-v055/six-hour-monitor-r1/summary-05.json)、[manager-r7-05.json](../../artifacts/software-benchmark-v055/six-hour-monitor-r1/manager-r7-05.json)。

原monitor不会在MP注册后继续更新conversion中的 `ref_retired_waiting_for_mp_capacity` 标签；后续观察以GPU7的 `qualified_registered` 与实际派发为准，不能仅凭这个保留字段判定仍在等待容量。

03:14:08的必要启用核查显示，r7新增canonical为21 closed／6 running，kernel为8 closed／2 running。各选一条已closed回合核对原静止证据，均3/3 scope quiet、errors为空，overlay与原source mode匹配；两例均没有触发重取。它们证明新监督路径实际接入并能正常闭合，不能据此宣称目标竞态已被现场复现或完全消除。详见`software-benchmark-v054-supervision-proc-exit-r1.md`及其独立runtime-observation-r1。

04:16:40的补充回收状态证明watcher仍在循环，当前候选425，本周期尝试4项、实际删除0项。这4项因历史writer静止证据不足而延期（`Historical complete writer quiescence is unproven`），原现场保留；这不阻塞生成/评分，也不表示所有历史缓存已经清空。证据见`cache-watcher-observation-04.json`。本次仅复制watcher已有小状态，新增删除0；磁盘余量充足，未绕过其删除资格门。

## 第六次小时观察及窗口闭合：06:12:51—06:12:56

编号06实际观察于 **2026年10月23日06:12:51.198962（北京时间）**，距编号05为3600.000700秒；r7补充实际于 **06:12:56.191783** 取得，06:12:56.290524完成写入。两份观察的errors均为空，计划内7个主观察点与4份r7补充至此全部取得，六小时监控窗口实际结束，正式实验服务继续按原队列运行。

Qwen最后为 **1423正常生成闭合、15生成技术未知、8运行、54pending**。MATCH为466／4／3／27，PROJECT为464／4／5／27，REF为493／7／0／0（顺序均为闭合／未知／运行／pending）。本小时MATCH新增22、PROJECT新增21，共 **43个正常生成闭合**，新增生成技术未知0；末次54个pending均按准备元数据分类为ready_waiting。DeepSeek保持2839正常闭合、161生成技术未知的终态库存，账本和六组状态未变，正常退出的manager没有重启。

r7补充证明当前manager PID3078377仍active/running、revision绑定匹配、队列running且state年龄5.764728秒；pool、cache管理器保持active/running。Qwen最近生成准入通过，预计扣预约后的启动余量635,062,711,835B，高于100GiB底线；未出现需本次继续修改运行状态的新增资源门故障。原r6 inactive/not-found与pool历史conversion标签继续按各自已有交接证据判读。

末次九组分项、逐小时净进度、近期速率、三项修复及尚未完成事项已在前置最终概览归纳。**本次完成的是用户指定的六小时监控与证据驱动恢复，不是九组实验全部结束或技术未知全部解决。** 剩余62个生成非终态槽的首轮库存仍粗估07:00—08:00收尾；异常集合和最终分析继续单列，未把生成闭合当作官方测试通过。

独立不可覆盖副本：[snapshot-06.json](../../artifacts/software-benchmark-v055/six-hour-monitor-r1/snapshot-06.json)、[summary-06.json](../../artifacts/software-benchmark-v055/six-hour-monitor-r1/summary-06.json)、[manager-r7-06.json](../../artifacts/software-benchmark-v055/six-hour-monitor-r1/manager-r7-06.json)。最终汇总与本文收尾只使用已保存材料，没有再次采样、查询GPU、运行测试、改变服务或新派发模型请求；这不否认窗口内已另行登记的修复与资格准备成本。
