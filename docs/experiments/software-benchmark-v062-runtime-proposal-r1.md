# v062 REF 开发面板与独立运行接入提案

日期：2026-10-26。本文记录离线准备，不记录新模型实验结果。当前没有调用 Docker、GPU、模型 API、systemd 或任何主机网络/挂载配置；`v057` 共享服务器 hold 与各历史 completed 授权保持不变。`pending-authorization.json` 不是可执行授权。

## 固定实验对象与解释边界

完全保留 `artifacts/software-benchmark-v056/plan.json` 的原 50 题和 12 仓库。来源身份再与 v060 最新 `requests-rescore/measurement-state.json` 的完整 200 个历史 slot 核对；不将历史成绩、候选、工作区、工具反馈或评分材料导入新模型工作区。

新三组是 BASE5M、FIX5M、FIX10M。BASE5M 保留原冻结 v061 REF 的执行行为；FIX 两组采用新执行协议，预算分别为 5M 和 10M。每题三个主槽共享一个新 seed，保持独立初态。三组主槽共 150；按原 v056 顺序在每仓库取第一题，共 12 题，在 FIX10M 各增加两个新 seed，新增 24 槽，总计 174。该选择只依赖原 task 顺序与 repo，不依赖任何成绩。主槽按原题序、条件先后循环轮转；重复诊断在主槽之后按固定两轮运行。资源调度可造成实际开始/结束顺序不同，不能按完成成绩更换题、seed、条件或预算。

| 条件 | 主槽 | 额外诊断槽 | 每槽累计输入＋输出 | 总上界 |
|---|---:|---:|---:|---:|
| BASE5M | 50 | 0 | 5,000,000 | 250,000,000 |
| FIX5M | 50 | 0 | 5,000,000 | 250,000,000 |
| FIX10M | 50 | 24 | 10,000,000 | 740,000,000 |
| 合计 | 150 | 24 | — | 1,240,000,000 |

12 题为：pylint-4970、sphinx-7889、sympy-21930、seaborn-3069、pytest-7571、requests-2931、astropy-14995、scikit-learn-10908、matplotlib-23476、flask-5014、xarray-3677、django-13807；完整 ID 已冻结于 panel。Seed 基数为 `20261026062000`，第零基题号乘 10，主槽加 0、两重复加 1/2。相同 seed 不能被解释为跨不同执行协议逐 token 相同随机轨迹。

全部 50 题均为开发/校准面板。新结果可描述在该固定面板上的协议修订差异及 5M→10M 的边际变化，不能声称独立确认、完整 Verified500 成绩或原始 9B 能力的数学上限。10M 仍是右删失观察；额外两次只诊断预选 12 题的波动，不用于选择最佳 seed 汇报。主结果固定分母 50，额外重复单列；技术未知不填作失败，也不自动重采。

共同资源保留 512 模型 attempt、512 Agent 决定/SDK 轮，21600 秒软/23400 秒硬时限，单次生成 1800 秒。全部正式模型 attempt 的算术上限为 89,088。两 resident 各最多一次中性准备，总新增最多 4,096 token，正式＋中性上界为 1,240,004,096；中性准备成本单列。

## v061 组件复用的实际限制

v061 不是一个可用新参数直接重启的通用 runner。下列依赖具有版本和授权边界，不能通过改模块全局变量、替换 `policy`、暂时改 completed 状态或复制批准文本来绕开。

| 组件 | 当前绑定与结论 | v062 最小接入方式 |
|---|---|---|
| `software_benchmark_dispatch_v061` | 固定十四项旧恢复索引、旧 plan、旧资源配额、旧 grant | 新 v062 policy/plan/claims；旧文件不改 |
| `software_benchmark_docker_actor_v061` | `OwnedActorPair` 隐式调用 v061 policy，卷前缀硬编码 `pws-v061-` | 新 owned adapter，或新显式 context/policy 的安全 core；每次 create/start 都消费 v062 durable claim |
| `software_benchmark_recovery_episode_v061` | 旧 slot/config、旧恢复含义、旧路径及 controller 入口 | 新 episode；共用无副作用归档/输出/快照函数前先核实路径边界 |
| `software_benchmark_ref_resident_v061` | v061 units/ports/root 及 `require_v061_allowed` | 新普通用户 resident wrapper，显式 v062 units/ports；延续容量、UUID lease、私有 compiler 环境 |
| `software_benchmark_ref_host_v061` | 有安装/runtime/launch 路径绑定 | 只复用已验证纯计算/验证逻辑，launch/runtime 用新目录与明确资源配置 |
| `software_benchmark_model_fifo_v061` | 逐请求账本/取消/FIFO/stdio 协议可读复用 | 原字节实现可引用，但 host 调用方必须接受新 plan/授权；新 loopback ports 不能绕过任何 admission |
| `software_benchmark_ref_budget_v056` | 固定数值与预算验证、common ledger | 预算算法可复用；新条件映射应明确实现，不能将新 condition ID 伪装成旧授权 |
| `software_benchmark_ref_budget_v061` | adapter 固定只接受旧端口身份 | 新版本构造器绑定 v062 resident；继承实际 ledger/generation 算法并保留必要身份检验 |
| `run_ref_budget_controller_v061` | 已冻结原生 SDK行为 | BASE 路径使用原行为独立封存；FIX 必须新 controller，不热改原文件 |
| `software_benchmark_scorer_v061` | 固定旧 policy、路径、plan、身份与 qualification wrapper | 新 v062 scorer adapter/独立授权；官方 harness规则保持，评分身份重绑定 |
| v058/v060 Requests provider | 任务特定离线/TLS 环境，旧 grants completed | provider算法/证据可以读取，新调用必须用 v062 明确资源门；不可重新启用旧 grant |

实质实现顺序是：新 dispatch 与 ledger → 新 owned lifecycle adapter → 新 resident/coordinator/episode → BASE/FIX controller bundle 与 scorer分支 → 冻结完整源清单及资格等价证明 → 获得限定 rootful 新授权 → 仅按固定库存运行。不要先让通用 wrapper 调用旧授权入口再 monkeypatch 通过。

现已提供的准备模块只有标准库依赖，无资源操作入口；没有声称上表运行接入已全部完成。`proposal.json` 列明剩余接入项，最终 runtime SHA 仍为 null。

## 环境资格复用与评分隔离

已有证据覆盖 11 题：v061 七题（pylint-4970/4604/6528、sphinx-7889、sympy-21930、scikit-learn-14894、xarray-4966），v058 两题 requests-2931/5414，v060 两题 requests-1766/1921。清单保留各原 qualification、gold/empty control identity 及其 scorer/environment 引用，不覆盖历史证据。

“存在历史通过证据”不等于“新 v062 已有资格”。v061 scorer manifest 本身包含 scorer adapter 和 v061 guard 的身份；v060 还绑定环境 revision、原始 CA、真实 TLS provider、解析身份与 transport证据。新运行正式评分身份尚未封存，因此当前 11 项 `reuse_admitted=false`。只有同 image、dataset、baseline、解释器/依赖、eval script、scorer/provider、limits 全部不变，或对纯管理路径迁移给出明确不可变等价凭据时才复用。任一实质身份变化只重做该受影响题的 gold/empty；不为保险重复跑相同身份控制。

其余 39 题没有本提案接纳的既有安全 provider 资格，需新 gold/empty 共 78 容器。额外给 11 题最多 22 个条件资源，仅在严格等价不成立时消耗。总新控制上限为 100；成功复用全部 11 项时为 78。不得读取旧成绩来跳过必要控制或把环境失败题从 50 题分母删除。gold/empty 和候选官方评分只在可信评分路径运行，不向 actor/controller提供官方测试补丁或 gold。

准备模块的模型公开投影仅导出 `instance_id/repo/base_commit/problem_statement`。`panel.json` 还包含宿主来源引用，整个 panel 与资格清单均不得直接挂载 actor；运行时必须再次以明确 allowlist 组装公开工作区及 controller配置，独立验证容器归档不含官方 gold/test patch。

## 有界资源提案

| 对象 | 全批最多新建 | 同时活动最多 | 单对象 CPU / RAM |
|---|---:|---:|---|
| Actor | 176（174 正式＋2 零模型诊断） | 2 | 4 CPU / 16 GiB |
| Controller | 176 | 2 | 2 CPU / 4 GiB |
| 正式 grader | 174 | 与 control 共用 2 | 4 CPU / 16 GiB |
| gold/empty control | 100（78 必需＋22 条件） | 与 grader 共用 2 | 4 CPU / 16 GiB |
| 新命名卷 | 176 | 随当前生成/诊断，静止后回收自建卷 | 无 host bind |
| 普通用户模型服务 | 2 | 2 | 12 CPU / 96 GiB |
| 普通用户调度服务 | 1 | 1 | 4 CPU / 16 GiB |

Docker 容器全批许可硬上界为 `176+176+174+100=626`，若全部 11 项资格可严格复用则实际所需最多 604；这两个数不是并发数。资源清单含 626 容器＋176 卷共 802 个唯一可消费身份。并发 2 生成对＋2 grader 为 6 个容器、20 CPU /72 GiB；加模型与调度总上限 48 CPU /280 GiB。两种执行协议各一个零模型部署诊断，只验证各自工具/只读视图/关闭链，不额外做模型资格题。

模型服务延续普通用户部署、BF16、GPU memory utilization 0.6、131072 context、32768 output、单序列；每个 resident 创建前至少 50176 MiB 空闲、完整 context cache admission通过，并保持既有 GPU UUID/容量租约。最多 2 resident；可用物理 GPU 0–7 仍服从当前共享容量门，不影响其他任务。新 unit 名为 `proworksim-v062-model-{0,1}.service` 与 `proworksim-v062-ref-development.service`，新 loopback 端口 18163/18164，`Restart=no`，不修改旧 unit。若可用 CPU/RAM/GPU 不足则等待，不放宽界限。

所有新容器使用现有 Docker 接口、固定本地 image、`network=none`、drop ALL、no-new-privileges、无 privileged、host bind/device/GPU/ports/host namespace。Actor/Controller 仅共享新卷的 rw/ro视图。所有 create/start 必须先消费准确 durable claim，未知 create 结果不自动再建。清理仅依据新所有权标签、claims、精确 ID 和静止证明操作本批对象。固定 actor lifecycle 24000 秒、diagnostic180 秒、grader test1800 秒/lifecycle3600 秒；关闭失败与未知创建不可伪装成成功。

磁盘采用继承的 128 GiB 空闲下限和逐项资源预约，未声称该下限等于完整磁盘写入硬配额。最终 coordinator 必须冻结每槽写入预约、并发存活卷清理策略和完整证据保留策略，并在不足时停止新派发；不得通过删除别的实验、修改文件系统配额或共享挂载来满足预算。模型中断不自动重采，已确定为安全局部异常的槽保留分类后继续独立库存，公共服务/账本/权限/来源完整性问题暂停未开始槽。

Requests1766/1921 仅允许 v060 真实 TLS exec bridge：原 `requests/cacert.pem` 与 TLS 校验不改，grader 保持 `network=none`，host 仅作为受限 byte transport 发往冻结解析的 `httpbin.org:80/443`，不改宿主 DNS/NAT/routes/firewall，不提供通用公网代理。两题各三主槽，共 6 个候选评分 session，最多再加 4 个条件 gold/empty session；总 10。每 session 最多 512 连接尝试、16 活跃连接、64 MiB application payload；全批最多 640 MiB application payload（不声称包含协议与链路开销）。两评分 lane最多同时 32 活跃连接。上次解析与新 provider 的完整身份如何等价须在最终准入明确；不能把旧证据有效性当作当前外部网络可达性的保证。Requests2931/5414 走任务限定离线 provider，不使用这条公网桥。

## 准备文件与必要验证

- 实现：`src/proworksim/software_benchmark_ref_plan_v062.py`、`tools/prepare_ref_plan_v062.py`。
- 产物：`artifacts/software-benchmark-v062/preparation-r1/` 下 panel、qualification-inventory、resource-plan、proposal、pending-authorization 五个 JSON。
- Panel SHA256：`13cdd30bd13f6ef96f09f4a89844480a634eb09f04eca6e97d59aeaa9f4f93c8`。
- Proposal SHA256：`3d5b56fd833989004955f2c66ca58505a7c82765e296d2d92e5be4c4d72919f6`。
- 三个必要 CPU 测试通过：固定题/seed/预算与公开字段隔离、精确资源总量、缩减题单/改写已冻结计划拒绝。定向 Ruff通过。真实离线准备首次误将原 slots 外层对象当列表，报 TypeError；读取 `.slots` 后成功生成。该失败发生于任何产物/资源创建之前，未加载模型、未调用网络或 Docker。

新限定 rootful 操作必须在完成接入、形成可审查具体源码清单后单独取得明确授权。旧 v058/v059/v060/v061 的 completed grant 不重开，当前准备物不会解除共享 hold。普通代码修复与离线准备仍可继续推进。


## 后续接入修订（2026-10-26，覆盖上述初步资源提案）

原 preparation-r1 五份 JSON 和原题单/seed 保留。新增 `software_benchmark_dispatch_v062.py`、统一 scorer、独立 Requests offline/TLS/transport 模块及 `run_capability_grading_v062.py`，不修改任何旧 v061/v060 源、授权或模块全局 policy。运行计划为 `runs/software-benchmark-v062/capability-probe-r1-20261026/plan.json`，174 新 derived configs 对应零基 slot_index 0–173；每行保留 source_slot_id，运行测量一律 capability_probe，没有原 unknown/snapshot recovery 语义。配置内部的 configuration 仍绑定原 5M/10M condition，而行 configuration 指新 host config；actor侧仍只接公开投影。

主 agent 要求为可能的准备阶段故障预留有限修订验证，现零模型诊断由 2 对增加到最多 4 对：1/2 是 BASE/FIX 首次；3/4 分别只在对应首次失败、零模型且静止证明完整时可消耗。成功后禁止备用冗余重测。policy 的 creation claim检查此前诊断确实失败、model_calls=0、quiescent=true/无清理错误/无unknown-create；每一资源仍单次消费。正式 174 与 1.24B 不变，最终 actor/controller/volume 各178，总容器最多630；全部11旧资格可等价复用时原算术下界608。本实现目前11项未接纳复用，因此新控制上界100。最初2对的运行plan已经另存 `preliminary-plan-r1.json`，没有改写已执行实验。

新模型 loopback端口统一为18171/18172，普通用户模型服务另有本项目短UDS目录 `runs/g62c1/model-{0,1}`；这里都是新普通文件路径，不是宿主挂载配置。48 CPU/280 GiB峰值、最多2模型resident、2生成+2评分不变。最终具体新授权必须使用630容器/178卷及新端口，不能使用上文初步626/176或18163/18164值。

Requests权限分层修正：2931/5414实际仅私有grader NET_ADMIN，使用network=none内的超时dummy route，没有 extra_hosts/NET_BIND_SERVICE；1766/1921额外私有NET_BIND_SERVICE和容器自己的httpbin.org→127.0.0.1，使用限定真实TLS exec bridge。所有actor/controller与其余grader继续cap_dropALL/cap_add空。container创建入口拒绝调用方提供网络或extra_hosts，再按精确task填入最小集合，并验证实际容器属性。绝不操作宿主route/NAT/firewall/DNS。真TLS新准备直接保留v060已验证的冻结数字IP及解析凭据，不做新DNS或网络探测；当前可达性只由将来的授权环境控制确定。

11项未复用的具体决定由 `coordinator/qualification-reuse-decisions.json` 在最终prepare生成。离线Requests两题的历史nominal/actual PidsLimit均16384，新固定512，存在真实资源边界变化；TLS两题历史request写16384而实测512，新identity直接绑定512，transport与v062 claims/watchdog/cleanup组合也不同。普通七题的官方harness/image/test/预算不变，但新统一creator按task路由、request/candidate/source身份绑定和cleanup分支组成的新完整执行路径没有已封存的受控等价证明；因此不能仅凭旧passed=true接纳。清单具体保留原control identity与新实现身份，模型成绩不进入该决定。新controls是必要的新评分身份资格，不是为改变旧成绩而回填旧结果。

新增7项CPU检查覆盖pending/completed授权拒绝、creation claim单次消费与静止释放、备用诊断成功后拒绝、四Requests最小能力分层、host/network资源拒绝、新slot绑定、禁止调用旧grant；定向Ruff通过。没有Docker、DNS、模型API、GPU或service操作。完成后仍需主agent冻结全部运行源码/SDKbundle、最终proposal及获得新限定rootful授权。

### 备用诊断的最终跨来源准入修订

上述最初“对应诊断必须失败”的备用规则在最终集成中修正，4 对总上限、174 正式槽及所有资源预算均不增加。原因是 BASE1 已通过而 FIX2 失败后，修复共享 controller/SDK bundle 会同时改变两路的冻结来源；旧 BASE 通过证明不能直接接纳新来源，但绝对拒绝“此前通过”的备用规则会阻断新来源必需的准入。

最终备用3/4要求：对应1/2的原诊断确为零模型、完整静止（无清理错误和未知create）；原 attempt 和 result 绑定准确；本次新的 intent 已记录当前完整 `policy.sources()`，且与前次来源不同；同一协议不得存在当前来源已通过的资格。此前结果可以失败，也可以是旧来源下通过。只要来源相同或已有当前来源通过资格，备用仍拒绝；这用于重新接纳变化后的来源，并非允许重复成功检查。所有原attempt/result/qualification保留，新的资格存于 `diagnostic-qualifications/{BASE|FIX}/{index}.json`，不覆写旧资格，也不自动选择或启动重跑。来源修订仍须满足新授权中完整source绑定，备用额度不能绕过授权源码检查。

针对这次准入变化，CPU检查覆盖旧来源通过/失败均可重新准入、未改来源拒绝、当前来源已有通过资格拒绝、有模型调用或静止不完整拒绝。代码与测试只读写本地临时证据，没有执行任何诊断、容器或模型。
