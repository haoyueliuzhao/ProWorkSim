# v054 kernel 单卡切换实施记录 r1

记录日期：2026-10-21，Asia/Shanghai。前半部分保留截至 21:26 的部署回执及队列快照；文末依次追加来源审计、r4/r5 数值失败、r6 分布门协议与 CPU 准备、新协议六请求通过、22:43 正式激活及 23:13 完成的 30 分钟观察。各时段分别表述，不覆盖原失败。r6 原 nRMSE 门仍未通过；任务级整体提速尚未证实。

## 当前概览（r6 已上线，30 分钟观察已完成）

- **GPU6 已上线部署 r6**：22:43 激活，仅优化 FP32 cached recurrent delta rule；chunk 和两项卷积保留参考实现，早期 FLA 两算子方案没有上线。GPU3/7 继续各自原运行实现。
- **新分布门与交错准入均通过，原数值门仍失败**：T=0.7 全词表分布六请求通过，三配对的 `original_gate_passed` 均为 false。新门是看到中性准备结果后的显式工程修订，不是独立确认或完整正式长度/面板同值证明。
- **准备成本已结算为 18 次生成、37972 tokens**，包括历史失败；正式旧槽没有重采，模型权重没有更新。
- **30 分钟观察已完成**：22:43:11.329844—23:13:11.329844，共 60 次设备采样；GPU6 新版闭合 4 个 MATCH 回合，8 个/小时、回合时长中位数 672.34 秒，旧 45 分钟 MATCH 基线为 9.33 个/小时、555.95 秒。不同题目组成下，尚未证实任务级整体提速。
- **请求级观察有条件差异**：同输入长度分桶的 MATCH 输出/native 秒，在小于 8192-token 桶约高 11–13%，8192–12287 桶约高 2.5%，12288–16384 桶约低 0.5%。它包含 prefill 和 decode 等原生调用耗时，不是纯 decode 或因果 kernel 加速；长上下文收益尚未证实。
- 实际上线绑定为 `9664f6d348f388bd966fdf888d290f88fa396e5c9586e8b21535b68bb2f68daf`；完整准入、激活、成本和证据见文末 r6 各节。

以下先保留 21:26 的旧方案历史快照及后续失败审计。历史内容中的 r3、FLA 两算子和未激活状态不代表当前 r6 状态。

## 21:26 历史结果快照（r3 来源门失败）

新的 host router 已接管原 1500 槽队列，服务为 `proworksim-v054-formal-queue-kernel-r1.service`。它仅停止向旧 GPU6 resident 派发新任务，GPU3、GPU7 继续处理原库存。21:17:32 接管时继承五个在途生成 worker 及两个在途评分 worker，未改变这些 worker，控制器交接本身没有模型重载、正式重采或新槽认领。

21:25:05 原 GPU6 两会话自然排空后，确认会话为空、无 inflight、无活跃 GPU6 槽，才停止旧 GPU6 resident 并向预载的新 guard 发布 predecessor-release。原 GPU3/7 resident 未被停止。新 r3 guard 此前已按 UUID 在受限 namespace 中持有 512 MiB 缓冲，释放交接后进入一次模型加载尝试。

**随后新 r3 在完整模型诊断的实际 kernel 来源检查处失败**：回执为 `ValueError: An optimized kernel came from outside the frozen overlay`，`model_load_started=true`、`model_calls=null`、`automatic_retry=false`。截至本记录，不能称新版本通过或已承接正式任务，也不能把该 `null` 无证据改成 0。该故障属于新运行环境的技术准备，不能记为 SWE-bench 正式题目修复失败。

21:26:29 队列仍为 running：179 槽生成闭合、3 槽运行、1318 槽待执行，161 槽评分完整；三个在途回合分别为 GPU3 的两个 PROJECT、GPU7 的一个 REF。该数字包含整个既有实验，不是新 kernel 的成绩或速度结果。

## 任务边界与不变条件

本次用户明确授权优化，并追加要求验证后切换新版本、监测一段时间的运行速度。授权用于原始 Qwen3.5-9B 的执行实现优化和必要准入，不恢复训练，不新增多 Agent 对照，不重跑已进入的正式槽。

既有 SWE-bench Verified 500 题、REF/MATCH/PROJECT 共 1500 个槽、原 seed、唯一候选导出、官方评分和完整计划分母保持。模型权重仍为原始检查点，不挂项目训练适配器；MATCH/PROJECT 既有上下文、输出、采样、调用及 token 限制保持。新计算实现可能改变浮点舍入和采样轨迹，因此绑定为独立 runtime 修订，按实际版本保留结果，不能把跨修订结果称为完全同一数值配置。

21:26 历史快照所对应的当时方案，仅尝试在 GPU6 切换 FLA 两个 gated-delta-rule 算子；该方案之后未通过完整模型门，未正式上线。GPU3 当时继续旧原生 MATCH/PROJECT，GPU7 继续原 REF。两项 causal-conv1d 优化未准入，当时候选保持其参考实现。后续实际上线的 r6 已改为仅 FP32 recurrent 优化，详见顶部当前概览与文末。早期 FLA 算子验证的完整方法、数值误差、JIT 开销和限制见[准备记录](software-benchmark-v054-kernel-preparation-r1.md)。

## 21:26 历史方案的隔离构建与绑定

新源码位于独立 `revision-root-r3/`，数据、既有工作区/claims/leases 等共享原根。source builder 复制源码与配置、处理必要的共享数据根定位，并形成独立 assembly、source manifest 和部署 bindings；没有原地更改运行中的旧源码或原虚拟环境，没有复制模型、镜像层或依赖大资产。

| 身份 | SHA256 |
| --- | --- |
| 原 `formal-bindings-r7.json` | `43fb7dde14a7c7abf3a0dc97de8b0de119f41d4f4199f8482793b9b6c24bc3de` |
| r3 新部署 bindings | `45d2e236b82f7e3fc59047310e11bf6de668419c2b2f716aee3b1670e2de4a48` |
| r3 最终 source manifest | `209e09103e36cd55e8680c45b2cc52de464a3000bb49892a398a66d6f5fe4748` |
| r3 source assembly | `0ebbef33f0f2878633184aa01d8701840262bed7322d37f48bed0e149aa2ae1d` |
| 独立 FLA overlay manifest | `786df9ea121c95828d7b755777b285a7238666db9c37ad211682e8c5abd71eeb` |
| 完整模型诊断 plan | `0f832f8670432d25f98b04f52e47a9688c76012b076b6a992a94eb932a1652ca` |
| host router policy | `62156b64b6b69e42cdfbf95024783c5bd210f2ed844d7065f1f18a1cc27951f4` |

r3 assembly 原件列 813 个装配文件。assembly 是构建阶段记录，之后部署可能绑定新的 condition 引用；最终可执行身份以部署 source manifest 和 bindings 为准，不把构建阶段 copied SHA 当成后续文件永远不变的证明。归档仅保留 assembly 摘要和完整大文件 hash 引用，不把约 1.14 MB bindings 或整个源码副本重复入库。

host router policy 同时绑定旧 deferred-fault policy、新独立源码 bridge、旧 GPU6 registration 和显式 activation 文件位置。新版本必须提供完成准入的 registration 后才能激活；旧队列及其他设备维持原 bindings。任务级评分异常继续按原异常集合策略处理，不因本次单卡改造重启模型或重跑已进入槽。

## 21:26 历史方案的准入与必要 CPU 控制

原算子阶段已有两个 delta 算子的四场景通过记录；没有重跑通过项。完整模型诊断计划固定 128、512、16384 tokens 三对参考/优化合成输入，每次输出最多 64 tokens，六请求最多 34,432 输入加输出 tokens。它检查真实绑定、首个完整词表 logits 的固定 KL/NRMSE 工程门、有限值、实际 token、同一个模型对象及只读状态/RNG 归还，不宣称逐位输出相同。

独立双会话交错准入仍有六请求，许可上界为 61,440 tokens；和完整模型六请求属于不同子项。两项上界相加为 95,872 tokens，外层准备预算上界 100,000。**这些是准入预算，不能当作实际消耗。** 新正式服务必须先取得相应完整回执再 registration/activation；static `deployment.json` 的零模型/零服务字段是创建时快照，不可拿它覆盖之后真实加载记录。

必要 CPU 证据分开保留：

- 旧完整模型诊断六项数学/provenance/预算控制通过，AST 未变化部分直接复用；新增绑定/环境门七项纯 CPU 控制通过，没有重新运行已通过数学门。
- r2 部署 CPU 控制通过：共同 bindings 不变、原 claims/leases、错误 GPU 策略拒绝、controller 路由、新 bridge 冻结、402 个依赖小文件绑定、复制 Python AST 可解析；耗时 1.326 秒，GPU/模型/服务启动均为 0。
- r3 UUID remap CPU 控制通过：物理 GPU6 与 runtime NVML index0 按同一 UUID 建立对应，保留原物理 index，错误 UUID、重复 UUID/错误可见性等四个拒绝控制通过；耗时约 0.000203 秒，GPU/模型操作为 0。
- router 的 CPU 控制与 assembled bridge 控制原件归档；它们证明受测调度边界，不替代完整模型数值准入。
- 30 分钟只读观察器已有七项 CPU fixture 控制，通过后冻结；没有通过启动模型或占用正式任务来测试观察器。

## 实际交接顺序

新 guard 与旧 resident 可以短时间并存，但只先分配 512 MiB 缓冲；这不是预先加载第二份完整模型。r3 的 `preloaded.json` 记录物理 GPU6 UUID 为 `GPU-35ddcc29-b60c-a106-93e6-175ccf9abd0c`，namespace 内 runtime NVML index=0，初次观测剩余 6440 MiB，成功进入缓冲等待阶段。

控制器交接脚本 `handoff_kernel_controller.py` 在旧控制器的睡眠 tick 验证 PID/start ticks 与队列状态，停止并替换控制器，继承原在途 worker；没有向任务或模型 unit 发信号。adoption 时间为 **2026-10-21 21:17:32.375765 +08:00**。

此后旧 GPU6 不再接受新任务，已有回合自然完成；GPU3/7 可继续派发。21:25:05.627625 的 drain proof 显示旧 GPU6 resident idle、两个会话槽均可用、无 active claims/inflight。停止旧 unit 后，独立检查 MainPID=0、旧 launcher 已退出、cgroup 为空，再发布 predecessor-release，允许新 guard 在已确认边界后进入一次加载。

旧 GPU6 unit 的 systemd 最终状态为 failed/exit-code，归档保留该真实状态；退出后的空 cgroup、无 launcher 和已排空会话才是释放证明，不能把 systemd 状态改写成正常退出。其余 unit 未被修改。

`cross_process_memory_handoff_atomic=false` 从计划到回执保持：512 MiB guard 与后续 allocator cache 只是减少显存空窗，不构成跨进程原子容量保证。新实例资源绑定记录目标为 73,728 MiB，释放后的缓存准备记录剩余 80,215 MiB、allocator reserved 77,309,411,328 B；该缓存准备本身没有生成 token。不得把缓存保留容量解释成模型真实分配峰值或成功生成。

## 各修订和失败原件

| 阶段 | 实际发生 | 成本与结果口径 |
| --- | --- | --- |
| 源码/部署 r1 | 独立静态候选构建，未启动，随后弃用 | 0 模型加载、0 生成；保留静态候选身份 |
| 部署 r2 首次 guard | 误将物理 index6 用于 namespace NVML 查询；该 namespace 中同一 UUID 实际 index0，报缓冲空间不足 | `model_load_started=false`、0 模型调用；准备故障，不是正式任务失败 |
| r2 明确停止 | 停止失败的新 guard；外层 stop wrapper 等待 45 秒超时，随后 unit 最终 failed、MainPID=0 | 保留 stop intent/final，旧模型 unit 未修改；不声称首次 stop 命令立即成功 |
| r3 UUID 修订与预载 | 按 UUID 找到 runtime index0，同时保留物理 index6；成功预载 512 MiB | 预载阶段 0 模型加载/调用 |
| router 接管 | 原队列接管，旧 GPU6 停止新派发，其他卡继续 | 控制器交接 0 模型重载、0 正式重采；继承原在途 worker |
| r3 边界释放与加载 | 旧 GPU6 排空并退出；新 guard 一次加载尝试开始 | 不能再称此阶段 0 模型加载 |
| r3 kernel 来源门失败 | 报优化 kernel 来源不在冻结 overlay 内，未取得完整准入/activation 通过回执 | 失败回执 `model_calls=null`，需要按实际诊断 intent/ledger 后续核实，不改成正式任务 R0 |

r3 失败原因还需实际来源链证据。本阶段源码存在一种待核实解释：诊断对带装饰器的 callable 使用 `inspect.getfile(target)`，而算子控制对实现使用 `inspect.unwrap` 后的来源；包装器可能被识别为 overlay 以外的文件。这只是代码层面的排查方向，不是已完成的根因证明，也不授权跳过来源边界。后续修订必须保留 r3 原件并单独标识。

## 成本按阶段区分

算子控制的成功 delta-r3 是合成张量运算，四场景各包含首次调用、warmup 和计时样本；不能说它只执行了四次算子。它没有完整模型加载、模型生成 token 或正式评分，宿主耗时 120.906 秒、观察 GPU 进程峰值 1070 MiB；前两次启动异常另存。

静态构建、CPU 控制、controller 交接和 512 MiB guard 预载均不是模型生成。完整模型加载、六请求模型准入、六请求交错准入，以及之后实际正式回合应分别记账；截至本阶段 r3 回执，加载已开始、正式新版本准入尚未完成，未知实际请求数保留未知。既有旧版本正式任务仍独立积累成本，不划入新 kernel 的准备消耗。

没有训练、反向传播、优化器 step 或参数更新。没有把合成准入占用正式 1500 槽，也没有因新的技术准备失败重置旧回合的 token 账本或选择其他题目替代。

## 后续实际观察的固定边界

观察器入口为 `tools/monitor_kernel_rollout_v054.py`，仅读取队列、原始小 completion/controller ledger 和 GPU3/6/7 设备采样，不启动模型或改变任务。`activation_utc` 使用本次 router adoption 的 **21:17:32.375765 +08:00**；基线为 **20:32:32.375765 至 21:17:32.375765** 内 GPU6 闭合回合，排除之后 drain/加载/准入停顿。

真正 30 分钟新版本观察窗口由匹配新 bindings 的 GPU6 首个 `worker_started_utc` 独立触发，约每 30 秒采样一次，保存真实样本数/错误及逐槽闭合记录。未取得新正式 dispatch 时不能开始计时或补造监测结果。若后续修订改变 bindings，应把明确的新 SHA 传入观察器，不沿用失败 r3 的 SHA。

报告按 GPU、arm、runtime 分组列实际关闭率、回合 wall time、输入/输出 token、GPU UTL 和显存分位。设备采样包含其他进程；窗口中尚未关闭的任务是右删失。不同题目组成和时间窗的比值只能作为运行观察，不能称为 kernel 的因果加速；19.12 倍算子切片计时也不能替代正式吞吐实测。

## 归档与后续补充位置

小文件归档位于 [`artifacts/software-benchmark-v054/kernel-optimization-r1/rollout/`](../../artifacts/software-benchmark-v054/kernel-optimization-r1/rollout/)，包括各静态部署的 spec/policy/declaration/permit、guard 的成功与失败小回执、controller handoff、drain/exit/release、CPU 原件、stage 源码及 root 交接脚本。`source-assembly-summary.json` 与 `large-binding-references.json` 只保留大对象身份与摘要；`archive-manifest.json` 保留原始路径、大小和 SHA。

没有复制源码全集、包/权重资产、完整队列状态、隐藏测试、参考补丁或评分日志。归档过程未修改冻结源码、模型服务、任务状态或 README，也未重跑任何已通过 GPU 控制。

本阶段尚无可报告的新版本完整模型通过率、正式任务成绩或 30 分钟吞吐收益。后续应补充实际修订的完整模型/交错准入、原始失败归因与成本、registration/activation、首个新 dispatch 和完整监测终态，并保留本阶段事实。

## 之后的来源门审计与窄修订（独立于上述 21:26 快照）

`model-qualification-r1/pre-generation-failure-audit.json` 已完成 r3 成本归因：根据冻结源码中该报错唯一的抛出位置，失败发生在首个 case 和 `generate_native` 之前；执行目录中观测到 0 个 case intent、0 个 case result、0 个 clone actor 目录，与控制流一致。因此该次准备可明确记为 **1 次模型加载、0 次实际生成请求、0 个生成 token**。审计保留原 guard 回执中的 generic `model_calls=null`，用独立证据解释它，没有覆写原件。这一成本澄清不能被理解为完整模型数值诊断通过。

新的 staged 来源定位仅把实际实现路径改为 `inspect.getsourcefile(inspect.unwrap(target))`，同时新增 `wrapper_source` 保留最外层 callable 的文件。新源 SHA 为 `743759aea313b95310cf20d32d62e8d6645068037bd90b7691c689d963299294`；原冻结 r3 源未修改。新 `model-qualification-r2/plan.json` 关联上述零生成审计，保留原数值门、六请求/seed 和两个优化算子，仅使用独立输出目录与修订原因。

对此只新增一次纯 CPU 装饰器来源 fixture：overlay 内真实文件定义内核，另一真实文件定义 `functools.wraps` wrapper 和选择器，使用实际 `compile` filename/正常模块加载。wrapper 虽复制内核 `__module__`，其 `inspect.getfile` 仍在外部文件；unwrap 后的实现来源正确位于 overlay 内，`wrapper_source` 正确保留外部文件。没有手工伪造 `__module__` 或替换 inspect 返回值，未放宽 overlay 边界。该 fixture 通过，回执为 `model-cpu-control/wrapper-source-control.json`；GPU操作、模型调用、数学门重测和已通过四场景算子重测均为 0。

该 CPU 控制证明本次装饰器来源处理方式，不能代替后续实际新 owner 的来源回执。修复后的 guard、再次加载、完整模型六请求、交错准入及正式 activation 的真实发生与结果，必须由后续回执另行补充；本节没有把准备中的下一次重载写成已经成功。

## r4/r5 数值拒绝与准备成本补记

来源门修订后，r4 的实际模型诊断仍被原数值门拒绝。它完成 128-token 与 512-token 两对合成请求，共 **4 次生成、1536 输入加输出 tokens**，其中每次均输出 64 tokens；16384-token 两请求未启动。失败发生在 512-token 配对后的首个完整词表 KL/nRMSE 工程门。该版在抛出异常前没有保存比较数值，因此保留的 logits 哈希不能还原具体 KL、nRMSE，也不能据此断定是哪一个阈值失败。四个请求的输出 ID 哈希一致不构成数值门通过。该次模型加载为 1 次、正式任务进入为 0，权重/学习状态不变、Torch RNG 精确恢复。

r4 的 generic guard failure 原件仍为 `model_calls=null`。独立 `model-qualification-r2/numerical-rejection-admission-audit.json` 以已完成请求、closure 与源码路径确认上述 4 次/1536 tokens；这属于补充归因，没有覆写原失败或把未知值静默置零。

随后 r5 改为本项目的 FP32 recurrent Triton 实现，仅优化单 token cached recurrence，chunk 与两项卷积继续参考实现。其算子准入使用两项固定合成场景，`fp32-recurrent-r1/receipt.json` 为 `passed=true`、模型调用 0；没有重复此前 FLA 四场景，也不能用该算子控制代替全模型准入。r5 的来源安装器精确绑定模块、函数、源 SHA 和依赖 manifest，安装发生在模型加载前。

r5 完成首对 128-token 请求后仍被原门拒绝：**2 次生成、384 输入加输出 tokens**，后续 512/16384-token 请求均未启动。此次已逐位置落盘，64 个合法位置都具有相同生成前缀，64 个输出 ID 完全相同，首个 prefill logits 字节相同；但是 **位置 47 的 raw-logit nRMSE 为 0.031371165066957474，超过 0.03**。该位置 T=1 全词表 KL 为 `5.257969704075549e-08`，全部 64 位置 KL 最大为 `1.5004521856099018e-06`。原 `passed=false` 保留，不能因为输出 ID 相同或 KL 很小改称原门通过。`model-qualification-r3/numerical-rejection-admission-audit.json` 同样以独立审计解释 guard 的 `model_calls=null`，原件未改写。

| 已完成准备阶段 | 实际生成请求 | 实际输入加输出 tokens | 是否通过当时模型门 |
| --- | ---: | ---: | --- |
| r3 来源拒绝 | 0 | 0 | 否，未进入生成 |
| r4 原 FLA 候选 | 4 | 1536 | 否，512-token 配对后拒绝 |
| r5 FP32 recurrent 候选 | 2 | 384 | 否，位置 47 nRMSE 超限 |
| r6 新协议之前累计 | **6** | **1920** | 不把历史失败合并为通过 |

这里的 6 次/1920 tokens 是本轮 kernel 候选准备的实际已结算生成消耗，不包含正式任务、算子张量运算或其他历史交错实验。r4/r5 均只有一次模型加载；加上 r3 来源拒绝阶段，本系列已有三次进入模型加载的准备尝试。停止失败 owner 及后继启动属于显式技术修订，不构成原准备请求的自动重试，也不新增正式题目样本。

## r6 分布门协议：观察后的工程修订

在见到上述中性准备结果后，本次明确另立 `v054-kernel-model-diagnostic-r2` 协议，以实际 MATCH/PROJECT 采样分布作为数值准入对象。它是**观察后的工程准入修订**，不是事前独立确认，不依据正式任务成绩挑选配置，不回填或撤销 r4/r5 失败。部署修订号为 r6；模型诊断计划目录为 `model-qualification-r4`，这两个编号与诊断格式版本 r2 各有含义。

对任意公共标量偏移 c，数学上 `softmax((logits+c)/T)=softmax(logits/T)`，但 raw-logit nRMSE 会随 c 增大。因此 nRMSE 可能拒绝采样分布不变的公共偏移。该恒等式解释修订测量对象的理由，**没有证明 r5 的实际误差全部属于常数平移**。浮点计算仍可能有舍入差异，新增门也不宣称模型逐位等同、任务准确率等同或算法训练收益。

新门固定 `temperature=0.7`、`top_k=0`、`top_p=1.0`，使用全词表 `log_softmax(logits.float()/0.7)`，每个可比较位置同时要求 `KL(reference||optimized)≤1e-4`、`max(abs(p_reference-p_optimized))≤5e-4`。保持 shape/finite、head 与实际输出对齐、真实 token 账本、权重只读及 RNG 恢复检查。实际 owner 的采样参数必须与该固定设计一致，不能使用 T=1 结果代替实际温度门。

原 T=1 KL≤0.02、raw nRMSE≤0.03 继续分别计算；逐 step、逐 pair 及最终 receipt 保存 `original_gate_passed`。新 receipt 另设 `original_gate_is_diagnostic=true`，明确旧门不再是 r6 必须通过的数值准入项。每对比较先写独立文件及累计文件，再执行拒绝；所有旧失败结果保留。比较仍只覆盖共同输出前缀条件下合法的 prefill/decode 位置，首次输出分叉对应的 logits 仍可比较，后续不同前缀不混比；不改采样、不 teacher-force、不强制输出 ID 相同。

新六请求仍为 128/512/16384-token 配对，每次最多输出 64 tokens，seed 分别固定 202610210601/602/603。数学计算与 FP32 recurrent 源码没有再次改动，安装器 exact-reference 逻辑不变。新协议、门及预算在该协议首个模型请求前冻结，不能因此把它描述为在此前所有观察前冻结。

预算分别列为：历史实际 1920、新六请求最多 34432、后继六请求交错准入最多 61440，累计上界 **97792≤100000**。这些后两项是尚待实际回执结算的上界，不是已发生消耗；新模型及交错两项均完成后才可注册/激活。详细协议及源身份见[分布门修订说明](software-benchmark-v054-kernel-distribution-v2-protocol.md)。

## r6 必要 CPU 检查与当前准备状态

只新增一次纯 CPU 数学及证据落盘 fixture，在项目私有 Python 运行环境执行，未传 `--gpu`，模型/GPU 调用均为 0。共 9 项控制通过，覆盖常数平移、新门拒绝实际概率扰动、实际温度 0.7、KL 门、nonfinite/shape 拒绝、逐 pair 旧门标志保存、失败前落盘、共同前缀位置和累计预算。

两个具体 fixture 结果体现新旧门测量对象不同：

| CPU 合成情形 | raw nRMSE | T=0.7 KL | 最大概率差 | 原门 | 新门 |
| --- | ---: | ---: | ---: | --- | --- |
| 全 logits 加 10 | 7.0710678101 | 4.8987610e-8 | 1.7881393e-7 | 失败 | 通过 |
| 固定非均匀 logits 扰动 | 0.0077459593 | 1.4325058e-4 | 0.0069887042 | 通过 | 失败 |

此 CPU 通过只验证被测数学与保存行为，不是全模型验证。执行时仅将 fixture ROOT 定位到私有环境可见的项目临时目录，并把写 plan-fields 的语句换成内容断言，避免更改已冻结计划；诊断源码 SHA 与 plan-fields 字节未变。`execution-receipt.json` SHA 为 `f7b5fa7e0c3166f53ad718fc64882c448ee33487846e903a95a070d2f5fe132b`。

小证据归档位于 [`distribution-v2/`](../../artifacts/software-benchmark-v054/kernel-optimization-r1/distribution-v2/)，包含 CPU fixture/结果/执行回执、协议字段/说明/单文件诊断源码、r4/r5 原失败与独立成本审计、r5 逐位置比较以及源路径/SHA 清单，总原件约 115 KB。不复制完整源码树、权重、缓存、模型 logits 向量或原始任务材料。stage manifest 是 CPU 执行前快照，CPU 后续成功由独立 execution receipt 记载，保留两者而不篡改历史状态。

**以上保留模型执行前的准备快照**：当时 CPU 9 项通过，r6 完整模型/交错准入、registration/activation、首个新 bindings 正式 dispatch 与 30 分钟监测尚待回执。GPU3/7 的既有正式运行不计作 r6 已成功上线或速度结果。

## r6 新分布门六请求实际完成

`model-qualification-r4/execution/receipt.json` 已形成，SHA 为 `43365394dc03dffc7236d2937bb045b9c241f8de915cca7a7cd9d8349a348058`：新协议 `passed=true`，**6 次实际生成、34432 输入加输出 tokens**，一次模型加载、同一个模型对象、正式任务使用 0、参数更新 0。closure 确认 learning unchanged、Torch RNG 精确恢复及优化函数恢复。该通过只针对明确事后修订的分布门，不是原门补通过或独立确认。

三个输入长度配对均实际比较 64 个合法位置，所有捕获 logits 有限，每对两个生成结果的 64 输出 ID 一致。实际温度仍为 0.7、top-k 0、top-p 1.0，各配对最大指标如下：

| 输入 tokens | 最大 T=0.7 KL | 最大概率差 | 最大 raw-logit nRMSE | 新分布门 | 原门 |
| --- | ---: | ---: | ---: | --- | --- |
| 128 | 3.3230895e-7 | 1.1444092e-5 | 0.0313711651 | 通过 | 失败 |
| 512 | 2.9080247e-7 | 1.4364719e-5 | 0.0431654155 | 通过 | 失败 |
| 16384 | 2.5356960e-7 | 1.6168866e-5 | 0.1246379018 | 通过 | 失败 |

**三个配对的 `original_gate_passed` 都为 false**；原 nRMSE 超限位置分别为 128 输入的 47，512 输入的 9/35，以及 16384 输入的 36/47/56/59/63。最大 raw nRMSE 达 0.1246379018，不能淡化为全部误差均小或把旧 0.03 阈值描述为通过。实测概率差小、有限位置输出相同不证明全部 logits 差是常数平移，也不证明任意上下文/生成长度等同。

此次只覆盖三种中性输入长度及每次 64 输出，未覆盖正式完整 18432/2048 上限组合，不能外推完整正式长度的数值等同性、完整 500 题面板分数同值或总体任务准确率等同。它提供当前新工程门下的有限运行准入证据；协议看过 r4/r5 中性结果后才修订这一事实保持。

实际成本现为历史 6 次/1920 加本次 6 次/34432，即 **累计已结算准备生成 12 次、36352 tokens**。交错六请求正在另行执行，尚未在本节并入已完成成本；它的 61440-token 许可上界仍只是上界。已有六请求不能当成正式新版本派发，原正式队列分母不变。

本次 receipt、closure、kernel installation 和 `gpu6-distribution-handoff-r1/model-observation.json` 已追加归档到 `distribution-v2/model-qualification/`。初始 `preparation-status.json` 保留；新增 `model-qualification-status.json` 独立记录当时模型门通过、原门失败、交错/activation/监测尚待回执的阶段。后续实际上线另记如下，不覆写这一阶段快照。

## r6 交错准入、正式激活与监测开始

新 owner 的双会话交错准入已完成。`deployment-r6/interleave-qualification/receipt.json` SHA 为 `66183cfc7d0a47bddb542ef15bf4c95c3233650aa699289ba5393ea6a923d7a3`，`status=passed`，**6 次实际生成、1620 tokens、unsettled=0**。顺序基线与交错的三组输出、token trace 及 RNG 转移一致，两个会话隔离、请求 FIFO 串行，共用同一个 resident PID 与模型对象；两项准入之间及会话之间没有另行重载权重。该测试没有使用正式题目，也没有重新覆盖完整容量上限，不能写成正式 18432/2048 全范围数值验证。

本轮 kernel 准备实际结算为 **18 次生成、37972 tokens**：r4/r5 历史 1920 + r6 模型分布门 34432 + r6 交错 1620。小于冻结累计上界 97792，也小于外层 100000；差额不是需要补跑的预算。CPU/算子控制、模型加载、正式任务成本仍分别记账。r6 模型诊断和交错检查使用同一次初始化加载，不能把两个 receipt 各自的 `model_loads=1` 相加成两次加载。

22:42:57 完成新的 `mp-g6-kernel-r6` registration，22:43:07 产生 `kernel-activation-r4.json`。实际身份如下：

| 对象 | SHA256 |
| --- | --- |
| qualification registration | `7d1636442ad07ea87621ef4b819fc035af467ba4207e8eff00a47bf3674217ee` |
| activation-r4 | `314ab3eb58004bbd1e1780364d6fc9c7555d64d02ee17148aed81dc7b69de939` |
| 正式 r6 bindings | `9664f6d348f388bd966fdf888d290f88fa396e5c9586e8b21535b68bb2f68daf` |

`gpu6-distribution-handoff-r1/completed.json` 明确本次仅停止先前失败的 r5 GPU6 unit、核实退出后发布 r6 predecessor-release；没有正式生成重试。控制器 r4 交接保留原在途任务，GPU3/7 继续原运行实现。此次 GPU6 启用的是 recurrent-only FP32 Triton 与分布门 v2；此前 FLA 两算子失败方案没有上线。旧原件中宽泛的 `runtime_revision=kernel-g6-r1` 字符串不能代替上述精确 bindings、registration 和 diagnostic version 区分实现。

新 bindings 的 GPU6 首次正式派发为 **22:43:11.329844**，首槽 `v054-MATCH-sympy__sympy-19495`；22:43 的运行观察确认 GPU6 原计划槽 138/140 两个 MATCH 已运行。同期全队列 5 个活跃、221 个生成闭合是全实验累计进度，不能记为 r6 完成了 221 题或作为优化收益。

`speed-monitor-r4/trigger.json` 将真实 30 分钟窗口固定为 **22:43:11.329844—23:13:11.329844（Asia/Shanghai）**，检测时间为 22:43:20.522511，检测延迟约 9.193 秒，窗口起点使用实际 dispatch 而非检测时间。在此启动阶段，监测尚未完成，没有提前报告完整窗口吞吐或加速比。它沿用既定旧 GPU6 基线，并按 runtime/arm 和设备分组；旧失败版本的观察器记录不冒充此次成功窗口。

交错 receipt、admission/registration/activation、必要释放及控制器交接小证据和固定 monitor intent/trigger 已归档到 `distribution-v2/activation/`、`handoff/`、`monitor/`。`activation-status.json` 单独记录此次上线；没有归档滚动 queue state 或未终结的 monitor summary。最终监测结果另行追加，不修改这些阶段原件。

本轮新增 12 个源码文件另完成一次必要 Ruff `F821/F823` 检查并通过；未运行全套测试，也未重复已通过的 GPU 算子控制。该静态检查仅覆盖未定义名称/局部绑定问题，不替代上述真实模型、交错及运行观察证据。

## 最终 30 分钟观察：上线完成，整体提速尚未证实

`speed-monitor-r4/summary.json` 终态为 `completed`，观察时长 **1800 秒、60 次采样**。窗口为 22:43:11.329844—23:13:11.329844，观察器于 23:13:11.404795 写出结束时间。它没有启动模型、改变任务或追加 GPU 测试；GPU6 的正式任务自然运行，GPU3/7 保持各自原版。最后队列读取错误列表为空，窗口终点仍有 5 个在途生成回合。

| 时间窗与运行版本 | GPU / arm | 窗口内闭合回合 | 闭合率（个/小时） | 回合 wall 中位数（秒） |
| --- | --- | ---: | ---: | ---: |
| 旧版基线 20:32:32—21:17:32，45 分钟 | GPU6 MATCH | 7 | 9.33 | 555.95 |
| 同一旧版基线 | GPU6 PROJECT | 2 | 2.67 | 1054.29 |
| 新版观察 22:43:11—23:13:11，30 分钟 | GPU6 MATCH | 4 | 8.00 | 672.34 |
| 同一观察窗，原版 | GPU3 MATCH | 1 | 2.00 | 552.63 |
| 同一观察窗，原版 | GPU3 PROJECT | 5 | 10.00 | 580.32 |
| 同一观察窗，原版 | GPU7 REF | 7 | 14.00 | 122.66 |

三卡合计闭合 **17 回合**，其中只有 GPU6 的 4 个 MATCH 使用本次新 bindings。GPU6 窗口没有闭合 PROJECT，不能为其补造同 arm 新旧速度比较。GPU6 MATCH 的观察闭合率低于旧 MATCH 基线，回合时长中位数更长，因此本窗口不能声称任务级整体提速；不同题目、输出长度、工具工作与并发条件也不支持据此断言 kernel 导致减速。旧基线另有 PROJECT 工作，不能把旧总 12 个/小时与新版纯 MATCH 8 个/小时当同构配置的因果比较。

GPU6 60 次整卡采样的利用率中位数 **90%**、均值 **72.6833%**、p90 **100%**，10 次为 0%；显存所有采样均为 **74379 MiB**。GPU3/7 的利用率中位数分别为 94%/100%。这些是整张设备的离散采样，可能包含其他进程，不是本 kernel profiler；0% 样本也不能直接归因为调度器、工具或 kernel 的某一瓶颈。

GPU6 新版四个闭合回合的完整账本合计输入 **1926521**、输出 **28198**、总 **1954719 tokens**；旧 MATCH 七回合为输入 **3106951**、输出 **43272**、总 **3150223 tokens**。以闭合回合完整 token 除以窗口秒分别为 1085.955 与 1166.749，但它包含属于该回合的完整工作，不能当作窗口内逐 token 的设备速率或 decode tokens/s。旧 PROJECT 基线 2 回合中有 1 份完整 token ledger，观察窗 GPU3 PROJECT 的 5 回合中有 2 份；其余不完整账本没有按零补入完整 token 分母。开始于窗口前的回合、窗口终点仍在途的右删失回合均在原件显式记录，不能忽略这些范围差异。

## 一次请求计时补充：短输入有观察差异，长输入收益不足

窗口结束后，一次只读 `request-timing-supplement-r1` 从上述闭合回合抽取必要身份、usage 和计时字段。共选择/汇总 **13 回合**（旧 GPU6 基线 9、新 GPU6 4），取得 **518 个 native 请求计时**、**1290 条队列回执**，提取错误与排除列表均为空。模型 prompt/任务正文不纳入计时分析或补充归档，没有模型调用、新 GPU 采样或任务/服务变更；不是重跑实验。

下表仅将同 arm 的 MATCH 按输入 token 桶比较，速率定义为该组 `sum(output_tokens)/sum(native_seconds)`，变化为新版/旧版减一。旧/新请求数分别来自已选闭合回合，不能当作独立随机样本数量或等题配对。

| 输入 tokens | 旧请求数 / 新请求数 | 旧输出/native 秒 | 新输出/native 秒 | 观察变化 |
| --- | ---: | ---: | ---: | ---: |
| 0–2047 | 9 / 12 | 28.983 | 32.409 | +11.82% |
| 2048–4095 | 12 / 7 | 29.317 | 32.446 | +10.67% |
| 4096–8191 | 19 / 14 | 21.413 | 24.242 | +13.21% |
| 8192–12287 | 129 / 82 | 21.098 | 21.626 | +2.50% |
| 12288–16384 | 110 / 69 | 19.797 | 19.698 | −0.50% |

小于 8192-token 的三个桶显示约 11–13% 的观察速率提高，但 8192–12287 仅约 2.5%，12288–16384 没有提高。因此长上下文收益和任务级整体加速尚未证实，不能用短桶结果代替全工作负载效果。不同请求的输出长度、任务内容和设备干扰未做控制；这些百分比只是该次分桶汇总差异，不是因果加速或完整面板等效结论。

`native_seconds` 包含 prefill、decode、输入 tensor/开始记录准备以及输出/logprob 传输，排除外层 FIFO 等待和更早的 prompt 准备，故输出/native 秒不是隔离 decode 吞吐。补充分析包含所选闭合回合的所有已结算请求，也可能包含其窗口前工作；仍在途回合的请求被排除，不按零补齐。

FIFO 等待另按 cohort/arm/operation 汇总。MATCH `match_complete` 的旧/新队列回执分别为 285/188 条，等待合计约 308.636/390.886 秒，中位数约 0.059/0.121 秒。这些回执缺少可直接关联 native attempt/输入长度的键，未按 ordinal 猜测关联，也没有按输入桶杜撰队列等待。并发会话等待可能重叠，等待和不能视为 GPU idle 时间。实际工具 CPU/wall 计时未被记录或不在本次元数据读取范围，均保留 null，不用 episode 剩余时间或配置上限代替。

补充工具的必要合成 CPU fixture 与窄检查曾在工具会话中通过，但 TemporaryDirectory 未保留，**没有持久机器回执**；未为归档而重跑或伪造 receipt。这与已有持久回执的九项分布门 CPU 控制分开表述。

## 终态留存与实验范围

本次完整窗口的 `summary.json/.md`、`samples.jsonl`、`closed-episodes.jsonl`、`baseline.json` 已追加到 `distribution-v2/monitor/`。补充 `report.json/.md`、`sources.json`、`requests.jsonl`、`queue-receipts.jsonl` 已归档到 `distribution-v2/request-timing/`；逐请求文件 442195 B，队列回执文件 941994 B，均小于 1 MB，保留其元数据证据。没有复制滚动 queue state、模型权重、完整源码树或任务全文。所有来源与归档 SHA 位于 archive manifest，另加 `final-observation-status.json`；各准备/模型准入/激活快照与旧失败保持原样。

23:15:42.328583 的一次必要运行检查记于 `post-monitor-operational-observation.json`（SHA `da5b359ccf713a4776ff3e7ba7a4f22a6b75bfeb136cee1288d00e609dfe84be`）：r6 unit 仍 active/running，launcher 与 guard 沿用启动/预载以来同一进程，resident `model_loads=1`、`weights_reloaded_between_episodes=false`、`poisoned=null`，队列仍 running。该检查没有模型调用或服务修改，之后没有为文档重复核验服务。小回执已归档至 `distribution-v2/monitor/`。

该次检查的队列快照为 **240 个生成闭合、5 个运行、1255 个 pending，235 个评分完整**。它晚于此前 239/5/1256、234 评分完整的观察，体现任务仍在继续；两者都是原 1500 槽整个实验的窗口后累计状态，**不是本 30 分钟窗口的计数**或新 kernel 单独成绩。窗口结束后闭合的其他新版本槽不回填本窗口四个 MATCH 的统计。任务继续按原库存运行，不因本次观察追加模型回合或升级 GPU3/7。

本次已完成用户授权的 GPU6 验证、切换与 30 分钟监测；工程准入通过的是明示事后修订的新分布门，原门失败仍保留。准备实际成本固定为 **18 次、37972 tokens**，监测和请求补充新增模型调用均为 0。运行观察支持新版可承接受测任务、短输入请求部分速率改善，尚不支持整体任务提速、长上下文收益或因果 kernel 加速的结论。
