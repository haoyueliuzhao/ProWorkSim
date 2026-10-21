# v054 首个正式回合前的资源就绪调度修订

用户追加要求：“三组实验，可以先安排已经准备完毕的任务”。因此在首个正式模型回合之前，仅将原全局严格顺序改为资源就绪调度。正式 1500 槽、500 题、三个条件、原始 seed、每槽和总 token 上限及官方评分规则保持。

新计划为 `config/v054-formal-execution-plan-r2.json`。队列按原 `slot_index` 扫描，选择当前固定 GPU 已就绪的最早未领取槽。REF 仍只用 GPU 7；MATCH、PROJECT 仍共用 GPU 6；最多两个生成槽。每个 GPU 内保留原相对顺序，未领取的资源等待或仍在执行的前项会阻塞该 GPU 上后续槽，但不会阻塞另一张已经就绪的 GPU。选择只使用资源和领取状态，不读取成绩或按任务内容筛选。

例如原前三槽 MATCH 1、PROJECT 2、REF 3 中，MATCH 1 执行期间 GPU 6 被占用时，可立即为 GPU 7 领取 REF 3；PROJECT 2 必须继续等 GPU 6。若只有 GPU 7 就绪，REF 3 可先执行。原槽身份不变，不能将实际启动顺序冒称原全局顺序。

状态的 `generation_dispatches` 逐条保存派发 intent 序号、原槽 ID/index、GPU、真实 worker 启动回执及时间，以及全局 claim 引用和文件写入时间。这些不同事件分别记录，避免把派发 intent 当成已开始模型执行。源码冻结、两模式实际容量准入、独立初态、原子一次性 claim、无自动重采、r5 两并发评分和技术未知暂停均沿用已审机制。

原 r1 计划、说明和回执保留；修改前 queue/CLI/plan、源清单和条件已保存到 `artifacts/software-benchmark-v054/runner/revisions/r2/snapshot-index.json` 所引用的快照。新的 canonical source manifest 由数据准备分支重新绑定，仅描述这次受影响修订，不改历史证据。

仅新增并运行一项必要 CPU 选择控制，覆盖两卡就绪、仅一张卡就绪、前槽未 claim 但在途、同 GPU 后项不越序、资源等待退避及不同 GPU 放行；结果 **1 passed in 0.07s**。此前两项持久恢复及评分锁控制没有重跑。Ruff 与 `git diff --check` 通过。没有由本修订分支启动模型、停止 holder 或执行官方评分；根协调器在实际容量与新源清单绑定后启动。
