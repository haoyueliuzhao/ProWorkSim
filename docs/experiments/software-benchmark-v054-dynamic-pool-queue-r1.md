# v054 动态显卡调度、排空迁移与调度开销

用户授权：GPU 7 的 REF 全部完成后可转换为 MATCH/PROJECT；其他物理 GPU 0–7 只要达到原模式的空闲显存门即可加入，允许与其他进程共卡，不要求整卡空闲或低利用率，不停止其他工作。这个修订改变资源调度，不改变原 1500 槽、题目、arm、seed、模型、工具、采样、上下文、128 次调用／决定、500,000 token 单槽上限或 750,000,000 总生成上限。

新授权为 `config/v054-formal-authorization-r2-dynamic-pool.json`，新计划为 `config/v054-formal-execution-plan-r3-dynamic-pool.json`。三组 condition 另记 `resource_scheduling_protocol`，原数值与交付条件保持。已经进入的槽不会重跑，其配置与评分引用仍属于原 binding；报告继续按运行版本分层，混合版本不输出一个“同配置完整 500 题”点估计。

## 池、任务领取与 CPU 准备

全局 binding 冻结注册政策及源码，池的 register/retire 事件只追加。每个 resident 有独立的声明、实际准备资格、GPU UUID、unit/PID 和源身份；既有 GPU 6/7 resident 通过明确的继承事件进入新池，不重载权重。每个新设备仍需独立的启动容量门与两次有限准备会话，准备回合和成本不混入正式任务。增加显卡不改写 global binding；每个正式槽保存实际使用的 registration、resident ID、物理 GPU 和启动记录。

仍只保留一个 REF resident，在 GPU 7 和端口 18054。MATCH 与 PROJECT 可使用多个已准入 resident。最多八个独立生成槽；每卡项目内排他、全局最多八个 resident；原每回合 4 CPU／16 GiB 和最多两个官方评分进程保持。共卡许可是显存准入政策，不是对其他进程的控制权。

队列扫描原 `slot_index`，选择最早满足模式、环境资格与空闲 resident 条件的 pending 槽；不同 resident 可在一次 tick 内同时领取工作。预备中的槽不能再次派发，已有全局 claim 的槽也不能变回未用库存。实际 claim 时间可能受准备耗时影响，不能把派发顺序冒称为严格全局开始顺序。选择不读取任务分数。

CPU 预准备使用独立单 worker，按原题单顺序最多前瞻两个尚未正式开始的不同任务；不领取正式槽、不加载模型。queue 只读资格与全局失败状态，未 qualified 不启动 GPU session。runner 对已 qualified 模板采用共享锁读取原四个路径，不再争抢原初始化的排他锁；这解决同题 MATCH/PROJECT 并行时的 `LOCK_NB` 假故障。真正准备失败会保留不可变证据并暂停新生成，不跳题或填成模型失败。

REF 转换只有在原 500 个 REF 任务全部生成闭合、每个代码端点已有可确定官方报告时才允许，`resolved=false` 同样是正常已定结果；不能按成功率决定提前转换。之后还需 resident idle/quiescence、精确旧 unit 停止及 retire 证据，才能为 GPU 7 建立新的 MATCH/PROJECT 实例。转换不新增或重跑任务。

## 显式排空与版本迁移

`tools/drain_formal_queue_v054.py` 仅在原 controller 的 `hrtimer_nanosleep` tick 边界、无 launch intent、距下一 tick 至少五秒时暂停该 controller PID，再停止其独立 unit。它保留 state 快照及故障历史，将状态改为 `paused_operator_drain`，以原源码、原 binding 启动 drain controller。独立 episode、评分和 resident units 不被停止；在途工作自然闭合，评分排空。该工具已由根协调器实际执行，原 17 槽完成后留下 1483 个未开始槽。

`tools/resume_formal_preclaim_v054.py --allow-dynamic-pool-revision` 只接受 controller 已停且全部已入槽与评分排空的状态。它核对旧、新授权和计划，允许显卡范围、并发数、追加式注册和轮询间隔这些明确资源变化；任务身份、预算、评分、模型等其他字段必须相同。三条件除源码引用及明确的资源协议外保持相同。迁移保留前后 state、原 binding、每次零执行失败和全部旧结果，不删除 claim。默认只读；`--apply` 才迁移，且不会自行启动队列。

## 已观察到的调度开销与优化边界

常驻开始后的只读日志中，GPU 6 三个已闭槽耗时分别为 MATCH 357.73 秒、PROJECT 725.11／1079.26 秒；两次槽间空档为 4.44／29.05 秒，均值 16.75 秒，入场准备均值 16.32 秒。GPU 7 十个已闭 REF 槽附近的十段空档均值 17.50 秒、最大 29.73 秒；入场准备均值 65.63 秒。样本很少，不能把这些均值当作完整任务池的稳定成本。

本修订把调度 poll 从 30 秒改为 5 秒，并一次填充多个空闲 resident。若闭合时刻相对 poll 近似均匀，单段平均轮询等待理论上从约 15 秒降至约 2.5 秒；上述样本中对应的 GPU 6 改善仅约 1–2%，REF 约 7–8%，这不是已经测得的最终加速。GPU 6 的主要耗时仍在真实生成、工具与测试，不能归因于 poll。独立 CPU 预准备可把部分冷环境时间移出 GPU 空等区，但不消除这些 CPU 工作，也不承诺固定比例的提速。

## 必要控制及尚未执行的边界

新动态 queue／排空／迁移合并 CPU 控制通过：`1 passed in 0.13s`，覆盖多个 MP 与单 REF、忙实例排除、八槽上限、追加实例、sleep 边界、未知 REF 结果拒转换、token 预算改动拒绝、旧配置与故障保留。发现同一冷任务的准备锁竞争后，只追加该选择边界控制：`1 passed in 0.11s`。旧 GPU 容量、旧会话和旧正式任务没有重跑。预准备与部署分支有各自独立回执；CPU 合成控制不冒充实际新卡加载资格。

启动顺序为：旧 controller 排空 → 应用并冻结新源码与三条件 → 生成 pool/prewarm policy → 显式导入当前两 resident 的已验证身份 → 冻结新 queue binding → 迁移未用库存 → 启动预准备、pool monitor 与正式 queue。现有两卡应先恢复任务；额外显卡由 monitor 等待合格显存，不让未来资源成为恢复当前工作的一道阻塞。
