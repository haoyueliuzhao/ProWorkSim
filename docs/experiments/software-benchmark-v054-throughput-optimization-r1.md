# v054 运行耗时分析与吞吐优化 r1

日期：2026-10-21，Asia/Shanghai。用户要求在不干预在途回合的前提下分析和加速，并允许使用任何满足剩余显存门槛的显卡，包括与其他进程共享的卡。性能分析只读既有日志，CPU对照使用已结束任务的独立副本；未向在途模型发探针、附加采样进程或修改输入。后续调度修订和退出竞态的恢复另列于本文末尾，保留各自源版本与原始故障证据。

## 已观察到的耗时

先前“约6分钟／12分钟”各来自一条常驻版本的新完成回合，不是整体均值，也不能据此断言PROJECT恒慢一倍。逐题时间可分成实际模型生成、工具／公开测试、准备和控制开销。`performance-observation-r1.json` 使用原生成器的seconds字段、回合回执及既有文件时间戳，未重复运行任务。

| 任务与条件 | 调度至候选闭合 | 实际生成调用 | 生成阶段合计 | 实际输入＋输出token | 公开测试调用窗口 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Django11276 MATCH | 约358秒 | 41 | 297.89秒 | 492,484 | 没有受管公测调用 |
| Django11276 PROJECT | 约725秒 | 20 | 150.98秒 | 305,698 | 约288.64秒 |
| Sympy12489 PROJECT | 约1,079秒 | 31 | 302.60秒 | 483,342 | 约581秒 |

公开测试窗口按完整输入bundle落盘至隔离副本清理回执计算，包含副本准备、实际公开测试和清理，并非精确独立测试CPU计时。MATCH是否通过原生Terminal自行运行了命令，不能仅凭受管公测计数为0判断；这里不把该计数混称成所有测试次数。

同题Django的PROJECT生成时间反而更少。其最大两次模型调用之间空档约302.84秒，与公测窗口相符；其余普通工具动作间隔约8–14秒。Sympy普通动作间隔约4–6秒，末次公测窗口更长。r3/r5资源日志中这两个Django回合没有重复refill，模型显存reservation保持不变；证据不支持“每请求重复占位导致慢一倍”。原生成日志没有prefill／decode细分，因此不对单个kernel作归因。

另一个已确认的成本是PROJECT世界状态体积：Django结束时state.json为91,426,372字节，Sympy为45,772,621字节。历史交互中包含完整仓库材料，常规工具操作会多次读取状态；这造成独立于模型生成的JSON解析成本。下述缓存仅针对重复读取，保留原公开信息、工具和持久化规则。

## 调度与资源优化

新增固定资源授权覆盖GPU0–7，最多八个独立resident，每卡仍最多一个本项目resident；每个正式回合仍是单Agent。MATCH／PROJECT沿用原门槛：A80080GB、剩余显存至少46,080MiB；其他用户进程和GPU利用率不作为排除条件。仍需原子取得物理UUID／全局lease并在启动前重新读取容量，不停止其他用户进程，不降低上下文或改量化以挤入。

GPU7继续执行唯一REF服务。只有全部500个REF槽的生成、账单和官方代码评分均闭合，且该resident无活动会话时，才允许一次退役并转换为MATCH／PROJECT。独立注册事件保留旧、新服务身份；不是把REF与MATCH数值路径混用。新卡经真实启动及最多两次独立合成会话检查后才能领取正式任务；该检查不冒充完整上下文容量复测，也不占用正式题槽。

注册记录采用固定策略下只追加的事件链。每次派发绑定所用resident、GPU UUID及准入证据；新增卡不改已有任务的绑定，不重复已进入槽、不按模型得分选题。失败保留证据，不对同一张卡无限重新加载；当前符合条件的健康服务继续受原系统故障规则约束。

调度轮询从30秒改为5秒，并在一次tick内为多个独立空闲resident安排任务。原日志中GPU6平均槽间空档约16.75秒，GPU7约17.50秒。仅此改动预计平均每次交接少约12–15秒；这是基于旧轮询间隔的调度估算，不是实测端到端提速。多卡分担才是扩展总体吞吐的主要来源。

## CPU提前准备与缓存

普通冷任务实际准备约48–59秒，中位约54秒，原流程在领取正式模型槽前执行。独立CPU worker将按原题序最多提前准备两个尚未消费的任务，复用原完整环境准入；已合格模板直接复用。队列仅对已qualified的任务派发模型，因此同一任务的多个条件不会争用初始化锁。准备失败明确暂停新增派发，不把不支持的任务换掉，也不预展开500份rootfs。

单worker的公开资源配置和原initializer的资源slice分别记录；不把两个scope声称为一个共同限额。公开测试范围、每回合CPU／内存、S1分页、Γ1历史、交付要求和模型预算保持原值。

状态缓存已完成16项必要CPU控制并采用到后续v054世界：同一91.4MB状态的暖读取中位耗时从1.09289秒降为0.08523秒，局部减少约92.2%；一对真实`read_task`事务从6.29511秒降为5.63270秒，约10.5%。后者只有一对样本，不是整个PROJECT回合的提速承诺。工具输出与完整持久化状态字节一致；对照仅固定request key和wall_seconds以排除自然时间差，正式运行继续记录真实时间。详细控制与边界见[状态缓存说明](software-benchmark-v054-state-cache-r1.md)。

缓存只保存一份真实JSON读回的已提交状态，返回值深复制，避免未保存修改污染后续读取；保存先失效缓存并继续使用原JSON字节、atomic replace和fsync。文件身份变化及外部原子替换会失效。保证范围是既有单写者锁和原子提交协议；不声称可以发现绕过该协议、在同一文件时间戳粒度内保持全部元数据相同的任意原地写入。本轮不增加全文件重复散列，不改原持久化格式或权限。

## 异步与增加并发的边界

用户进一步询问能否异步处理CPU测试、增加并发。需要区分两类测试：候选锁定后的官方隐藏评分已由独立CPU worker异步执行，最多同时两个评分进程，模型可继续领取下一题；Agent求解期间的公开测试则是该题下一步行动的信息来源，当前接口仍等待结果。这类公开测试在已有样本中出现约5–10分钟的调用窗口，其中包含副本准备、真实测试和清理，不能把整个窗口都当成测试CPU占用，也不能提前返回“通过”或删除反馈来换吞吐。

当前实际实施与尚未实施的边界如下：

| 项目 | 当前实现 |
| --- | --- |
| 跨卡执行 | GPU0–7动态准入，最多8个resident／8个活动生成回合；仍受原显存和身份门约束，不代表此时已有8张可用卡 |
| 提前准备 | 单独CPU worker，按固定题序最多向前准备2个任务；不消费模型槽 |
| 交接延迟 | 调度轮询5秒，一次tick可派发多个独立空闲resident |
| PROJECT控制开销 | 已采用v054专用已提交状态缓存，原保存、fsync及工具语义保持 |
| 官方评分 | 候选锁定后异步评分，最多2路；隐藏结果不回传Agent |
| 同卡多题交错 | 尚未实施；一个resident同时仍只绑定一个正式episode |

只读设计评估了同卡两个独立REF回合交错：CPU工具等待时让另一题生成，而GPU仍保持 `max_num_seqs=1`、原上下文与采样。现实现有整题会话锁，正常release还会暂停并清理整个引擎，不能仅放开第二个会话。若将来实施，须改成请求边界交接和清理，单题关闭不能abort另一题；每题账本、seed、工作树和反馈独立，排队仍计原5400／6000秒时间限额。共享引擎故障也可能影响两题，不能承诺完全故障隔离。

只读记录的13个已闭合REF回合、302对请求／响应文件时间戳中，请求窗口外间隔合计约161.24秒，占首请求到末响应总窗口约9.03%；该样本没有支持“同卡双题可直接翻倍”的证据。文件时间戳不是GPU kernel或CPU profiler，且不含全部首尾准备，不能据此给整个实验的吞吐预测。当前优先使用已上线的跨卡并行、预准备与缓存；同GPU交错只完成设计，没有在r8／r9中启用。

## r7→r8：保留原回合后切换吞吐优化

调度器在休眠tick边界停止新增派发，独立回合、评分和两路模型resident继续运行。该次切换时17个回合全部自然闭合，GPU6／GPU7模型保持驻留。旧条件、源清单和任务结果保存在r7快照及原bindings下；r8采用上述跨卡调度、提前准备、5秒轮询和PROJECT状态缓存。后续资源与实现修订使用新的bindings并分层报告，没有通过重跑已看到结果的题目来验证速度。

## r8→r9：退出竞态与原候选的行政闭合

r8中的槽39为 `v054-REF-pydata__xarray-6461`。原控制器已完成27次模型调用，实际输入＋输出合计467,492 token，账本确定；原resident release也已正常完成，回执明确 `engine_unfinished=0`、`engine_paused=true`、`cache_reset=true`，权重未卸载。随后CPU session sentinel自然退出，systemd回收短生命周期unit；监督器在读取状态与执行 `systemctl stop --no-block` 之间遇到竞态，stop返回退出码 **5**，并非“5秒测试超时”。旧监督器将其直接记为清理错误，生成 `all_quiet=false`，外层因此报 `No complete bound quiescence evidence`。

旧异常处理随后尝试poison这个已经release的claim，服务因不再有该活动claim返回HTTP409；宿主兜底对整个REF resident发送SIGSTOP。原始 `technical_unknown` 结果、失败quiescence和poison记录全部保留。这里的故障发生在生成、计费与resident release已经结束之后，不能描述成模型推理失败、预算丢失或需要重新采样。

r9修复收窄到两处：仅在 `systemctl stop` 返回码5、原unit确已被回收且登记的PID／start_ticks、原cgroup均证明退出时，接受这次自然退出竞态；权限错误、复用unit、仍存活后代等继续拒绝。另在与精确session绑定的合法release票据存在、resident仍为同一进程且独立健康idle时，后续行政清理错误保留为回合故障，不再poison或SIGSTOP已释放的resident。其余真正未知调用与无法证明退出的情况继续走原故障停机规则。修复的必要CPU控制及前后源码身份保存在[修复manifest](../../artifacts/software-benchmark-v054/sentinel-close-control-r1/manifest.json)；本次文档更新没有另跑控制。

已对原槽执行一次明确标识的 `administrative-closure-r1`：确认全部原scope与外层launcher实际退出，导出未修改的原终态工作树，锁定唯一候选，再提交原官方评分器。没有创建新正式claim、重新调用模型、修补代码或选择替代候选；行政闭合新增模型调用为0。评分随后完成，原候选官方代码结果为 `resolved=false`；这是该原候选的评分结果，不是一次新的生成回合，也不抹去先前执行故障。

| 证据 | 路径与关键身份 |
| --- | --- |
| 原失败结果 | [原episode/result.json](../../runs/software-benchmark-v054/formal-queue-r1/slots/39/preclaim-1/episode/result.json)，SHA256 `26a0e24ca6c4540744a17923e370386e17ef6431b435c9c2396f0eae2d1129d2` |
| 原正常release | [service/release.json](../../runs/software-benchmark-v054/formal-queue-r1/slots/39/preclaim-1/service/release.json)，SHA256 `44259ef1fe718316ba376d8ebb938e2feef0d91f154b3024c4963797b2854135` |
| 行政闭合意图与原身份 | [intent.json](../../runs/software-benchmark-v054/administrative-closure-r1/intent.json)，固定原claim、原controller结果、原失败quiescence及原bindings |
| 实际进程退出证明 | [quiescence.json](../../runs/software-benchmark-v054/administrative-closure-r1/quiescence.json)，`all_quiet=true`、外层launcher已退出、费用不重建 |
| 原候选闭合结果 | [result.json](../../runs/software-benchmark-v054/administrative-closure-r1/result.json)，原27次／467,492 token，`new_model_calls_from_administrative_closure=0` |
| 官方代码评分 | [receipt.json](../../runs/software-benchmark-v054/official-output/v054-REF-code-39251c94b85d953db9ba8037861f838b9b0731b4/receipt.json)，`status=official_report`、`resolved=false`，SHA256 `f64f7f85ee7f9063893af7cf4a4c615b62e06e9b581f48910d594ae64ca9dc2d` |
| 原resident恢复 | [resume-idle-resident.json](../../runs/software-benchmark-v054/administrative-closure-r1/resume-idle-resident.json)，同一进程、未重载模型、无新增生成请求 |

行政闭合和评分排空后的切换检查点为20个生成回合已闭合、1,480个待运行，活动生成和评分均为0；当时队列仍为 `paused_operator_drain`。这是一份 **r9恢复派发前** 的静态检查点，不是持续更新的当前进度。修复源已纳入r9切换，实际恢复服务、最新bindings和后续动态数量由根调度记录补充；不能凭文档中的检查点宣称新一轮任务已开始。原r8故障证据和所有已消费claim保留，后续仅调度尚未进入的原定任务。

## r9恢复派发观察

队列已恢复为 `proworksim-v054-formal-queue-r5.service`，新bindings-r6 SHA256为 `56af6225e5b28eaadcb920287b02069f8595d8e985cfe36625b13a34bd075c3e`，source-manifest为 `c74c8bcad20afbee9a1e6b2e68cf912eebc45c1070e6f8da854b9ba6f7fccd31`。动态GPU监控器使用pool-r2，CPU提前准备使用prewarm-r2；这些新策略只更新源码身份，已合格缓存及原模型容量证明复用。迁移时仅1480个未进入槽可派发，20个既有回合不重跑。

恢复后的只读观察为20closed、2running、1478pending，GPU6运行PROJECT槽10（Sphinx9229），GPU7运行REF槽41（Sphinx7454）。两个模型host PID仍为3178406和3199584；同次瞬时UTL为95%和100%，不代表持续平均利用率。其他GPU最大剩余37,292MiB，尚未达到46,080MiB准入门槛，故实际仍为两卡并发，不能把上限8写成已启动8张卡。实际排程依据冻结的准备就绪条件，可跳过尚未qualified的早序任务；原ID和seed保持，不按成绩选题。

同卡两个独立回合在公开测试期间交错生成的后续方案见[异步并发设计](software-benchmark-v054-async-concurrency-design-r1.md)。本轮没有实现该方案，也没有承诺消除CPU测试造成的GPU计算间歇。


### r9恢复派发快照

在上述静态检查点之后，根调度已完成r9切换并恢复：queue使用 `proworksim-v054-formal-queue-r5.service`，pool为r2，prewarm策略身份前缀 `5bb9c97b`。新 `formal-bindings-r6.json` 的SHA256为 `56af6225e5b28eaadcb920287b02069f8595d8e985cfe36625b13a34bd075c3e`，源码清单SHA256为 `c74c8bcad20afbee9a1e6b2e68cf912eebc45c1070e6f8da854b9ba6f7fccd31`。

恢复后的即时状态为20个回合已闭合、2个运行中、1,478个待运行：槽10 `PROJECT sphinx-doc__sphinx-9229` 在GPU6，槽41 `REF sphinx-doc__sphinx-7454` 在GPU7。GPU6／GPU7 resident宿主PID分别仍为3178406／3199584，未因本次修复卸载模型。该次观测GPU利用率为95%／100%；其余显卡的最大空闲显存为37,292MiB，低于MATCH／PROJECT原46,080MiB门槛，因此策略允许最多8路并不等于此刻8路已经启动。这些数值是恢复时快照，后续进度以队列状态为准。

## 后续同卡实现

用户在本报告后明确要求继续推进同卡交错。MATCH／PROJECT两会话已在独立r11修订中实现、完成实际六请求准入并恢复正式派发，REF仍单会话。该修订另报7次准备调用／2055 token及两次MP加载（含一次checker格式错误后的受控替换），未重跑正式题。详见[后续实施报告](software-benchmark-v054-interleaved-execution-r1.md)；本报告中“尚未上线”等表述保留为先前阶段事实。
