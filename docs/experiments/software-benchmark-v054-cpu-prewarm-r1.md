# v054 单 worker、两题前瞻的 CPU 环境准备

本修订把尚未初始化的公开任务环境放到一个独立 CPU worker 中提前准备。原模型、任务、种子、预算、工具、评分器和已经执行的回合不变；原已合格模板直接复用。worker 不占正式 claim、不加载模型、不调用 GPU、隐藏评分或完整基准测试套件。

## 观察依据与范围

只读比较原 worker `started_utc` 和缓存文件时间戳，10 个未经首题修复/手动延续的普通冷题，从 worker 启动到 `lazy-preparation.json` 合格约 47.984–58.690 秒，中位数 54.273 秒。写入 `environment.json` 前约 36.064–45.166 秒，包含导出、解包、属主准备与启动开销；随后公开初始化、关闭与缓存证据完成约 11.920–14.392 秒。这里是原记录的时间差估计，不是独立埋点计时，也没有重新执行这些任务来测速度。

较快的 REF 已经为不少后续 MATCH/PROJECT 槽准备了共享模板。因此预准备的预期收益主要在首次遇到新任务时；实际收益须从修订后记录判断，不能把上述全部时间直接宣称为已经节省的 GPU 时间。

## 选择与有界前瞻

选择只按原 1,500 槽顺序查看 pending 任务，并按 instance 去重，不读取成功率或评分选择任务。一个 worker 串行调用原 `ensure_native_instance`，使用同一公开题单、最终 baseline mapping、Python 环境、Docker 本地镜像和 `native-lazy-cache`。原 per-instance 非阻塞独占锁、64 GiB 磁盘余量门、稀疏 UID 映射与公开版本资格检查保持。

最多保留两个由本 worker 提前准备、但还没有任何正式 generation 开始消费的不同任务。准备满两题后必须等其中某题的正式 generation 进入 intent/running/closed，才能补下一题。已有历史 qualified 模板不会被重新初始化；它们也不计作新前瞻库存。这避免了“每轮找两个尚未准备任务”最终在后台展开全部 500 个模板。

worker 的导出/解包/属主阶段放在专用 system service，内核上限 4 CPU、16 GiB、16,384 PID，启动时实际读取对应 cgroup 值。原公开 initializer 仍使用它已经通过验证的独立 4 CPU/16 GiB slice；重导出处理和该 initializer 阶段依次执行。此处不把两个独立 scope 描述为同一个聚合限额。主准备函数保持原机制，没有新增正式测试或模型调用。

## 与队列、运行器的交界

队列发起每个新正式槽前只接受对应 qualified 模板。`preparation_state(instance_id, mapping_reference=..., cache_root=...)` 是只读检查：tiny receipt 必须绑定相同 mapping；若原 per-instance 独占锁有人持有，则返回 `preparing`，不会启动另一个初始化。没有模板返回 `pending`；未持锁却遗留不完整模板返回 `failed`，保留现场。

原 `ensure_native_instance` 在 qualified 分支也获取独占非阻塞锁。多 GPU 同时启动同一任务的不同条件时，即使模板早已合格，重复独占检查也可能发生锁冲突。新正式运行器通过 `qualified_paths` 获取同样的四个绝对路径：在共享锁下只读验证原四个文件引用，不执行初始化。不同条件允许同时读取同一不可变模板；各自随后仍按原规则创建独立 episode 工作区。没有 prewarm policy 的旧历史路径保持其原身份。

正式 runner 做一次完整四引用核对；队列只检查小 receipt/锁状态，避免每次轮询重复读取数十 MiB 的 manifest。这里不降低正式模型进入前的模板身份核对。

## 失败与可恢复证据

准备 `preparing/prepared/deferred/failed` 以及 worker 生命周期记录写入顺序追加事件。先写完整临时文件并 fsync，再不可覆盖地发布正式事件文件；旧记录不改写。成功事件引用原 `lazy-preparation.json`，失败保留具体异常和原目录。模型调用、GPU 加载、正式 claim、隐藏评分次数均记为零。

`prewarm_health(policy_ref)` 让队列在每次新派发前检查全局准备故障，不等到该题成为队头才发现。实际准备失败或 worker 在未闭合准备期间消失会暂停新增正式 generation；不会换题、自动重新初始化或把准备故障填成模型失败。已经在途的正式任务由原监督器闭合。单纯已有合法 initializer 持锁或磁盘余量暂不足可等待；不执行另一个相同冷初始化。

## 部署与本次控制

`tools/run_prewarm_v054.py prepare --output <新的 runs 目录> --source-manifest <最终源码清单> --queue-state <接续 state.json>` 只产生固定策略和 `launch.json`，不会准备真实任务。启动 argv 使用项目宿主 `.venv/bin/python`，专属 system unit，`PYTHONPATH=src:repo`，CUDA 可见设备为空。队列绑定同一 policy 引用。

本次只增加一个合并的 CPU 状态控制，通过，用时 0.07 秒。控制使用程序化文件系统 initializer，覆盖已持有独占锁时等待、共享只读取得缓存、两题库存上限、正式消费后仅补下一题、失败立即全局可见且不重试。没有重新运行实际 Django 初始化、旧三组 CPU 链路、GPU 容量检查或官方评分。本报告不声称预热已经带来实测吞吐提升；真实运行启动和准备耗时将由后续原始事件记录给出。
