# Qwen异常集合：生成审计、并行补评与四项r6修复

本轮处理Qwen已完成主库存之后的异常，不重新生成补丁或清除claim。原队列1500槽、原模型配置和候选均保留。生成异常与评分异常分开，评分端只允许原协议的一次additional attempt；新结果独立保存，不覆盖原primary或原失败记录。

## 生成异常的只读审计

15个generation technical_unknown为REF 7、MATCH 4、PROJECT 4。13例原controller已closed，但锁候选前的完整静止证明失败：11例model CPU sentinel、2例actor记录FileNotFoundError。另1例PROJECT公开工具停止后代超时；1例MATCH启动controller读取start.json发生JSONDecodeError。

15例都已entered／claimed，全部没有候选锁、官方评分请求或既有scores，不能直接恢复一个原已锁定结果。只读核对没有重放模型、创建新候选或用当前quiet改写历史。13例ENOENT与后来修复的PID退出竞态相容，但旧回执无完整堆栈，不能逐例断言根因已证。

14例保留的controller摘要合计6378076 tokens；这是可引用的部分摘要小计，不是15例完整成本。按原billing规则，完整用量仍有2例未知：MATCH django15380没有controller摘要；PROJECT sympy20801虽有209257已扣tokens，但execution_integrity_failure仍使完整用量未知。15例外层model_calls=null均不作为零。

完整逐题引用与简明说明见 `artifacts/software-benchmark-v055/exception-reconciliation-r1/qwen-generation-audit.json` 及同名Markdown。

## 串行末尾评分的安全接管

原watcher `proworksim-v054-deferred-scoring-r1.service` 的PID为1170718，实际停止语义为 `KillMode=control-group`，不是只停止manager。它在单进程内依序处理34条异常记录：17个scoring、15个generation、2个accounting。后两类不运行评分或模型，accounting与generation记录存在重叠，不能把34条当作34个独立任务。

接管时唯一在途的是REF scikit14710的原attempt2，09:12:35启动，child PID689935。先封存精确父PID/start_ticks、unit InvocationID、argv、原trigger/progress、子PID身份和started引用；仅SIGSTOP父进程，child信号数0。父进程处于wait，原progress在冻结前后保持相同SHA。没有停止评分子树，也没有让并行代码抢占其attempt.lock。

09:43:57观察到原child已经为Z、父仍为T；其既有评分receipt是technical_unknown，没有确定官方结果。因为父未恢复收割，原driver completion尚未写出；没有从Z状态推断返回码，也没有把未知改成结果。停止旧服务前再次确认旧cgroup除了冻结父已没有存活后代；随后停止旧服务，证明cgroup为空，启动独立 `proworksim-v054-deferred-scoring-parallel-r2.service`，PID798666。

新实现 `tools/run_deferred_scoring_parallel_v054_r2.py` 接管原watch.lock与driver.lock，复用同一inventory、每endpoint原目录和原两个grader锁。两个worker仅调用冻结的原process_exception，使用线程独立dataset缓存。容量暂忙时等待，不把容量锁冲突写成评分失败；旧started没有可信结果时保留未知，不进行第三次评分。新进度、summary、adoption写入独立r2目录，原watch-trigger、progress与原结果保持。

09:47:17的首观察证实PROJECT django13925和django10554同时处于原attempt2评分，原progress SHA未变。当时requests1142三组与REF matplotlib26466四项都没有started或result，按照事先声明的确定性故障hold保留，未交给原r5盲跑。

r2于 **09:49:10** 完成34条记录，结果为30 unresolved、4 hold。其中17条为保留的generation／accounting记录；其余13条评分仍technical_unknown。原串行阶段已消耗的4条没有重跑，后9条实际r5评分进程返回0但receipt仍为technical_unknown，不能把进程成功退出当作确定官方结果，也不能把13条未知当作模型代码错误。此修订改善了调度，并未声称原r5环境问题已解决。

封存plan为 `runs/software-benchmark-v054/deferred-scoring-parallel-r2/plan.json`，SHA `4aeafc44cfab0f2574b82d58a2a40dbb7a77db9fa32283b15862e5ec7573807c`。8项必要CPU控制通过，限定新增工具Ruff通过。控制脚本随后仅修正分号格式，测试时的完整源码另存 `tested-control-source.py`，没有重复运行已经通过的控制。部署与结果小证据保存在 `artifacts/software-benchmark-v055/exception-reconciliation-r1/qwen-deferred-parallel-r2/`，14文件、43866字节（不含索引），未复制大inventory或全队列state。

## 四项hold的独立r6评分

这四项此前没有消耗additional attempt，因此可以在保留原候选、补丁语义和评分规则的前提下，使用独立评分执行revision进行其唯一attempt2。独立r6修复由另一实现分支提供：明确只向测试进程暴露4个CPU，按固定官方image证据接纳requests1142的65个build副本，并允许有双向tree校验的无损UTF8补丁运输。原1800秒、16 GiB、4 CPU quota、pids16384、network none等资源限制不变；不是通过增加资源上限获取成绩。

`tools/run_qwen_four_endpoint_scoring_r6_v055.py` 固定仅处理这四个endpoint，分配CPU0–3和4–7；它与前述r2共用原Qwen grader两锁，因此两服务合计最多2个Qwen grader。等待锁只排队，不消耗评分attempt或记录失败。新的request保留所有原字段，仅改变attempt到2、独立receipt_output，并附original request、scoring execution revision、cpuset及可选patch_transport引用。每项新run ID包括独立执行身份，不能复用原r5缓存。

登记时持原endpoint attempt.lock，为原目录增加明确的r6 transfer和unresolved指针，避免原process_exception日后再次派发；**没有伪造原r5 started.json**。旧未定结果保留，权威r6结果位于独立目录。新started意图先于Popen、child继承原grader与endpoint锁；启动不明确或已started无报告时不重派发，不追加第三次。收回结果时核对整份expected identity、原request、revision、cpuset和run ID，exit0本身不足以判定官方结果。

六项CPU控制与限定Ruff通过。plan为 `runs/software-benchmark-v055/exception-reconciliation-r1/qwen-four-endpoint-r6/plan.json`，SHA `f20e4b91b09ce3a54ca9d187d4c68f9fb96843b36663a2dbede67203052ce285`；评分revision为 `scorer-r6/revision.json`，SHA `9b65e88c6c5a9d0313c5e304c8aaf296439142cc1b96fe3a89d34bbe8b2750d2`。

服务 `proworksim-v055-qwen-four-endpoint-r6.service` 于 **10:02:00** 启动，PID861114；于 **10:03:05** 完成。4项均取得确定official_report：

| 原槽 | resolved |
| --- | --- |
| REF matplotlib26466 | false |
| MATCH requests1142 | true |
| PROJECT requests1142 | false |
| REF requests1142 | true |

这恢复了4个既有锁定候选的评分确定性，新增模型调用为0；不是4个新增生成回合，也没有把原unknown历史删除。13个已消耗过补评的其余Qwen评分异常仍保留，不因新的r6可用就加第三次。完整九组统计应按原slot合并独立评分端点，避免将原r2的hold或unresolved转交指针重复计入最终状态。

四项request／expected identity、transfer、started、completion、result、实际官方identity／receipt、实际initial-container证据及summary，原字节封存于 `artifacts/software-benchmark-v055/exception-reconciliation-r1/qwen-four-endpoint-r6/`：51文件、165612字节（不含索引）。没有复制rootfs或候选源码。所有GPU／驻留模型保持，本轮没有自动释放显卡。
