# v055 DeepSeek 评分异常的独立同候选补评 r1

本轮只处理原六组的 47 个评分技术未知端点（42 个 code、5 个 delivery）。不新增任务、不重新生成答案、不改变已锁定候选，不覆盖原队列、原评分请求、原评分收据或原异常。每个端点最多一次额外评分，使用新 `r6` 执行身份与独立 `run_id`。原 500 题 × 6 组计划分母保持；code 与 delivery 分开报告。

## 原异常与依据

原主队列已为 `primary_inventory_finished`；本轮原库存快照 SHA 为 `f8a3aa601bd55b20cc0469136e80210e416aa414e80c26ed6b89a468b2e2da04`，21,783,083 字节。47 个评分请求、终止回执、候选锁与分型证据已封存在 `runs/software-benchmark-v055/exception-reconciliation-r1/deepseek-scoring-r1/preflight-inventory.json`。不以恢复后的分数选择补评对象。

| 原类型 | 端点数 | 已知事实与本次处理 |
| --- | ---: | --- |
| scikit-learn 14710 测试超时 | 6 | 原测试在 1,800 秒限额处结束；宿主可见 CPU 数与 4 CPU 配额不一致。本次仅增加 4 CPU 的可见集合约束，保留原配额与超时。 |
| 官方 unresolved，但 strict adapter 保留 unknown | 29 | 原官方报告均 `resolved=false`、`patch_successfully_applied=false`；27 份 `infra_failure=false`、2 份 true。保留官方结果与 strict 结果两个轴，允许一次同候选补评尝试获得可信的 strict 结果。 |
| 官方初态存在 untracked build 副本 | 8 | 都是 requests 1142；官方固定镜像 HEAD/tree 正确，唯一 `?? build/`。65 文件路径、大小、SHA 均与原 mapping 的 build 副本精确一致。本次只准入该清单，不删除文件、不更换镜像。 |
| 原补丁无法 UTF-8 解码 | 4 | 原补丁与候选锁保留。使用另行完成双向应用核验的 UTF-8 binary transport；新旧补丁在相同 base 上均得到相同完整 candidate Git tree，无文件过滤、无重新选择。 |

29 份原报告不能因为 `infra_failure=false` 就推定“模型修复错误”。本地官方 `swebench/harness/grading.py` 在不能取得可信测试解析结果时会保留默认 false 字段；`infra_failure.py` 的分类并不改变官方分母或 resolved 语义。`patch_successfully_applied=false` 也不能独立证明实际 git apply 失败。本轮不修改官方 harness 的判定，也不把原技术未知直接覆写为正常失败。证据与解释单独封存在 `saved-official-unresolved-two-axis.json`。

针对 scikit，先前只读观察发现一个同题评分 pytest 进程有 303 个线程、CPU affinity 为 0–175，而容器 CPU quota 是 4 CPU。原 `eval.sh` 未限制 OMP/BLAS 线程。线程过量是据此形成的执行瓶颈假设；该观察本身不构成因果证明。本次 r6 将实际可见 CPU 限为 4，执行结果单独标注，不冒称旧评分配置不变。

## 独立 r6 评分版本

源码：`src/proworksim/software_benchmark_scorer_r6_v055.py`。

封存：`runs/software-benchmark-v055/exception-reconciliation-r1/scorer-r6/revision.json`，SHA `9b65e88c6c5a9d0313c5e304c8aaf296439142cc1b96fe3a89d34bbe8b2750d2`。

原固定模型输出、镜像、官方任务/测试、候选、scorer installation、评分代码规则均保持。资源仍为 `nano_cpus=4000000000`、内存 17,179,869,184 字节、PIDs 16,384、超时 1,800 秒、网络 none。r6 新增实际 `cpuset_cpus` 及容器内 `/proc/self/status` 的 CPU affinity 核对；评分身份包含执行 revision、原请求、原补丁、可见 CPU 集合，以及可选 transport receipt/replacement SHA。

requests 的 65 文件清单由 `requests-official-untracked-build-audit.json` 与原 mapping 双重固定。r6 在实际评分容器读取 Git status、tracked/index diff、完整 untracked 文件路径与每个文件 SHA；只接受无 tracked/index diff、唯一 `?? build/` 且全部路径/大小/字节散列吻合。原 `working_tree_clean=false` 观察仍保留，新增明确的 build 副本准入字段。

transport 资产来自 `patch-transport-r1/manifest.json`（本轮共 5 份，其中 4 份 DeepSeek，另 1 份属于独立 Qwen 补评），SHA `cd93c1287a8ac3324243e91e3fda8c8d6c925e5a59a40d7f99c5058709c2dc42`。本工具按原评分请求精确匹配，不重做已经完成的 patch round-trip，也不复制大型 bundle/patch 到发布证据目录。

## 驱动、并发与异常隔离

`tools/reconcile_deepseek_scores_v055_r1.py` 封存全部 47 项、固定四个串行 lane；lane 间并行。DeepSeek 四个 lane 分别使用 8–11、12–15、16–19、20–23 的 CPU 集合。Qwen 的两路 r6 使用 0–3、4–7，相关恢复由独立驱动管理。

DeepSeek 与随后六个零模型旧槽恢复的**首次评分**共用四个锁：

`runs/software-benchmark-v055/exception-reconciliation-r1/deepseek-scoring-r1/grader-slots/{0,1,2,3}.lock`

首次评分仍使用原 v055 attempt 1，不套用本轮 attempt-2-only r6。两个 DeepSeek 驱动合计最多四个评分进程；加上 Qwen 原两路，合计最多六个评分器。评分锁、端点锁及驱动锁的 FD 传给子进程，父进程异常退出不会立即释放仍在执行的容量。

原 host capacity 门保持（CPU load < 140、至少 128 GiB 可用内存）。等待容量时不写最终结果、不消耗额外 attempt。永久 `started.json` 在启动前落盘；一旦存在，无论结果是否明确都不自动重放该额外 attempt。每个端点单独捕获异常，其他 lane 继续；无法获得严格结果时保留 technical_unknown，而不是填模型失败。共同启动层异常仍需单独停止未进入项，不能以端点隔离为理由盲目消耗全部库存。

计划：`deepseek-scoring-r1/plan.json`，SHA `57a89757cf6b9bfb4a3db1b55e4180480261703da7823b0b2016445398dd9622`。驱动仅写独立目录与新评分输出，不修改旧主队列。本轮最多 47 次额外评分，新增模型调用为 0。

必要 CPU 控制已通过五项：请求只能改变 attempt/output 和封存执行元数据、四路 CPU 与共享锁约束、资源等待不消耗 attempt/不写 final、永久 intent 防重放、意外端点异常隔离。r6 自身四项 CPU 控制及定向 Ruff 通过；没有为这些控制启动 Docker、模型或真实官方测试。

## 实际启动与完成结果

2026-10-23 10:00:41（Asia/Shanghai），`proworksim-v055-exception-scoring-r1.service` 开始四路补评。首次系统观察 PID 850105、active/running；首四个实际容器都已通过 `official_setup_mapping_verified`，实际 `observed_cpu_affinity` 分别等于四个固定 CPU 集合，未见 ROOT/installation 或共同初态启动错误。

准备期间曾从历史 runtime 的 `/data1` cwd 使用相对路径调用纯 CPU freeze；因原库存引用是 `/data0`，在计划发布前被路径严格比较拒绝，0 模型、0 评分。之后通过宿主绝对 `/data0` 入口完成同字节封存；原队列 SHA/字节数未变化，不修改冻结源码来掩盖路径差异。独立说明为 `freeze-entry-path-observation.json`。

截至 10:02:16，47 项中已有 13 项写出结果：6 项获得严格官方结果，7 项仍为技术未知；其余继续排队/执行。这不是全部补评完成的结论。

六个 scikit-learn 14710 端点已在该新执行版本下闭合，从永久启动 intent 到进程 completion 为 25.24–34.26 秒（包含启动与评分），两个 REF 候选 `resolved=true`，两个 MATCH 与两个 PROJECT 候选 `resolved=false`。原六次 1,800 秒超时与原 unknown 保持，不添加第三次尝试，不将这些结果反馈给 Actor。这一观测支持可见 CPU 限制改善了本次同题评分执行，但不等于对其他未知类型或所有宿主资源瓶颈的保证。

10:04:35 的后续观测已处理 35/47：14 项获得严格官方结果、21 项仍技术未知，驱动记录错误为 0。此时已实际完成 7 个 requests 初态修复端点、1 个 UTF-8 transport 端点；这些路径已经进入真实评分，超过了只做 CPU 合同控制的证据范围。其余端点继续按原冻结顺序执行。

发布小证据目录为 `artifacts/software-benchmark-v055/exception-reconciliation-r1/deepseek-scoring-r1/`：计划、启动脚本/intent/receipt、原分型、官方两轴、必要控制与首次实际容器观察。原 21 MB 主队列快照及大 patch/bundle 保留运行路径引用，不重复复制。最终独立 `summary.json` 与 `final-analysis.json` 已写出，按原请求和端点与主库存关联。它们不覆盖原状态，也不代表所有异常或整个九组实验已经处理完成。


2026-10-23 10:06:45，本轮 47/47 端点全部完成一次额外评分，距离首批启动约 6 分 05 秒。新增模型调用 0，额外评分 47，lane error 0，未追加第三次评分。18 个端点取得严格结果，29 个端点仍为技术未知。

| 原异常类型 | 新 strict resolved | 新 strict unresolved | 仍 technical_unknown |
| --- | ---: | ---: | ---: |
| scikit 超时，6 code | 2 | 4 | 0 |
| requests 官方 build 初态，6 code + 2 delivery | 7 | 1 | 0 |
| 非 UTF-8 传输，4 code | 4 | 0 | 0 |
| 原官方 unresolved / strict unknown，26 code + 3 delivery | 0 | 0 | 29 |

按端点计量，42 个 code 中恢复 16 个确定结果（11 resolved、5 unresolved），26 个仍未知；5 个 delivery 中恢复 2 个 resolved，3 个仍未知。上述计数只描述本次异常集合，不能当作整个六组的完成率，更不能混合 code 与 delivery 计算通过率。

| 条件 | 本次 code resolved / unresolved / unknown | 本次 delivery resolved / unresolved / unknown |
| --- | --- | --- |
| REF nonthinking | 5 / 0 / 5 | 不适用 |
| REF thinking | 3 / 0 / 4 | 不适用 |
| MATCH nonthinking | 1 / 1 / 7 | 不适用 |
| MATCH thinking | 0 / 2 / 3 | 不适用 |
| PROJECT nonthinking | 1 / 1 / 6 | 1 / 0 / 3 |
| PROJECT thinking | 1 / 1 / 1 | 1 / 0 / 0 |

29 个原模糊官方结果在一次 r6 补评后仍未满足 strict 判定。保留新旧官方报告、日志引用和原技术未知，不把重复执行当成消除不确定性的证据。本工具结束后没有自动后继；全部共享评分锁自然释放，由另一路初次评分按同容量门使用。

最终发布证据还包含全部 47 个新端点的 request、永久 intent、completion、result、identity 和 receipt。没有复制大型补丁、模型、rootfs 或原完整主队列；原正式运行目录与镜像不变。本报告没有汇总混合通过率，也没有宣称科学结果全部确定。
