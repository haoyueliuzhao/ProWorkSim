# v053：正式模型之前的准备修订

日期：2026-10-20。本文记录准备阶段遇到的问题及处置，不是模型能力结果。全部修订发生在正式面板冻结和首次模型调用之前；原始记录保留，未消耗正式模型回合或生成 token。

## v1：镜像传输等待

已提交实现 `34a445d4fedbc39583d144792b18b512e501a8db` 后，后台流水线首先进入 CPU 环境准入。Docker 的一个公共基础层连接很慢，首批八个仓库均在等待镜像，尚未创建任务容器。

按官方 registry 的 manifest、config 和 layer SHA 并行下载缺失分段，并只读复用已完整下载的层。八镜像标准归档共 4,430,786,560 bytes、41 个独立层。导入成功，八个实际 image ID 全部匹配官方原始 config SHA；没有重新构建或替换源码镜像。详见 [镜像传输说明](software-panel-v053-image-transfer.md)。

为使新缓存立即生效，停止 v1 的旧下载等待进程及本实验八个 CLI pull。停止前已确认正式监督器未进入、任务容器为 0；保留 `pre-model-transfer-transition.json` 和原 `pipeline-v1/pipeline-state.json`。原流水线正常记录 `paused`、`SIGTERM`、环境阶段退出 `-15`，并生成 [v1 准备报告](software-panel-v053-result-v1.json)。这不是模型失败或任务换题。

## v2：上游提交与镜像提交不能混用

相同代码和模型配置在独立 v2 准备目录接续。实际容器能够创建、执行命令和清理，但首批八个仓库都在 `git reset --hard <profile.commit>` 处失败，尚未进入任何测试节点。

最初适配器将这些异常记为 `source_not_admitted`。随后核对官方固定源码，确认这是共同初始化假设错误，**这八个 false 不能作为有效来源淘汰依据**。已在下一批镜像等待阶段暂停 v2；没有形成正式 200 题清单，没有任何正式模型调用。原八个记录、阶段日志和 [v2 准备报告](software-panel-v053-result-v2.json) 保持原样，不把旧 false 改写为 true。

固定官方实现的规则是：

- `swesmith/profiles/base.py:364,374–386` 先检出 profile 声明的上游提交 U，随后删除 `.git`，重建 `Initial commit` 与 `main`，建立 SWE-smith mirror。
- `swesmith/profiles/python.py:57–66` 从该 mirror 克隆 `/testbed` 并安装依赖。
- `swesmith/harness/valid.py:102–108` 在新镜像默认基线上应用数据集 patch，并不检出 U；`swesmith/utils.py:173` 后的 checkout 分支仅在调用者明确传入 commit 时执行。

来源是固定 [SWE-smith revision 9b74ac0](https://github.com/SWE-bench/SWE-smith/tree/9b74ac08118a85c39c356802f7961893af73e07f)。源题单的 40 位上游 SHA 提取本身正确；错误是把 U 当成镜像内的 Git 对象。

两个原始镜像的实际只读观察：

| 仓库 | 镜像 main／HEAD 提交 C | 镜像 Git tree T |
| --- | --- | --- |
| Faker | `a225b71e4979d5414eb9b38768621c7ee26e4dac` | `9b924f5645898ad3341cbc5a8b7eeae954b9b990` |
| Pydantic | `f62e04832924116e3969698d81fdad6b0f5c5ead` | `c43e64f6ab95f0f67e82142716b5360d0c92de44` |

两者的 `HEAD`、`main`、`origin/main` 一致，tracked 及非 ignored untracked 状态为空；上游 U 对象不存在，官方任务 remote branch 存在。原始诊断保存在 `runs/software-panel-v053/mirror-base-diagnostic-v1/summary.json`。

## v3：分开冻结来源身份与实际基线

修订使用新源码提交及独立 `environments-v3`、`pipeline-v3`，不复用 v2 的错误来源结论。抽样种子、候选仓库顺序、每仓库十题、重复子集规则、原模型／SDK／采样／预算均保持。

上游 U 仅作为来源声明；镜像 ID、Git 来源锚 C／T、默认引用和实际工作树 B 另行冻结。B 不一定等于 T：例如官方 fvcore 安装命令会删除 `tests/test_focal_loss.py`，盲目 reset 会恢复官方构建刻意删除的文件。clean、bug、gold 和实际 Agent 均从同一 B 准备，正向应用数据集 patch，逆向恢复时核对回到 B。已有官方任务分支提供额外树对照时记录其可比较性，不能猜测父提交、强行合并安装差异或临时拉取远端来替换初态。详细源码证据见 [镜像基线说明](software-panel-v053-mirror-baseline-v3.md)。

通用初始化异常改为公共故障暂停；只有有明确任务／来源证据的失败才能成为来源不合格。正式模型仍必须等待完整 200 题环境资格、40 题子集与 280 个 seed 冻结，以及全部实际初始请求容量检查。修复初始化本身不等于这些条件已通过。

## v4：保留离线构建依赖

v3 实际进入了官方测试，但 Pydantic 的 clean 日志显示 pytest 尚未启动：适配器整删 `/root/.cache`，移除了镜像自带的 hatchling、hatch-fancy-pypi-readme 等 uv 构建依赖缓存。其 `5438 MISSING` 是共同适配错误，不能作为有效来源淘汰或模型失败。

已在正式面板冻结之前停止 v3，保留 [v3 准备报告](software-panel-v053-result-v3.json)。停止收口时共保留 161 个阶段进入记录、160 个阶段回执和 76 个任务资格记录（64 true、12 false）；这些是被中止准备的原始记录，不是正式面板。停止后精确清理了本实验唯一遗留的 `admission-bug` 容器，无宿主挂载，没有停止专用 Docker／containerd 或触碰默认服务。完整处置记录在 `runs/software-panel-v053/v3-common-cache-fault.json`。

v4 改为保留官方依赖缓存、继续清除任务源码历史和字节码，并固定 `UV_OFFLINE=true`。第一次仅保留缓存仍因 uv 尝试更新索引而在离线环境失败；该记录原样保留。补上离线解析后，Pydantic 原官方 clean 命令实际执行成功：5,810 passed、420 skipped、17 xfailed；第一道预选题的 5,438 项 required 测试全部为 PASSED／XFAIL。此成功回执写入新 `environments-v4` 的 clean 复用路径，正式准入不重复执行它。测试数字只说明这份 clean 控制，不是十题资格、200 题资格或模型成绩。

修订另有一项针对依赖缓存保留和源码清理的 CPU 回归通过，限定 Ruff 通过；未重复此前整套控制。详见 [缓存适配证据与限制](software-panel-v053-cache-adaptation-v4.md)。新流水线使用独立 `pipeline-v4` 与 `environments-v4`，保留原候选顺序、抽样规则、数值配置和全部预算。正式模型调用数仍为零。

## v5：Git 诊断与树 SHA 分离，复用既有完成证据

v4 的 `records` 安装差异投影实际成功，但 Git 空白警告与 tree SHA 被合并读取，导致后续 Git 命令将警告文本误作对象名。共享停止事件使该窗口八个仓库保持未决，环境汇总因此暂停；正式模型仍未进入。修订仅分离这个机器读取通道的输出流并严格校验 40 位树 SHA，不更改缺陷补丁、空白字节或测试定义。一次实际产生 Git 空白警告的 CPU 回归及限定 Ruff 通过，详见 [v5 修复证据](software-panel-v053-git-output-v5.md)。

新 `environments-v5` 用真实目录和 2443 个逐文件链接复用 v4 的不可变证据。原有 16 份仓库资格、167 份任务资格和 370 份 completed 回执保留原身份，避免重复执行；8 份旧公共故障摘要原样留在 v4 并由 transition 逐个引用。未完成尝试只能在新路径继续，不能当作完成结果。配置、证据与写入边界见 [v5 复用说明](software-panel-v053-preparation-reuse-v5.md)。候选、种子、模型和科学 contract 均不变。

用户另要求取消 GPU2／GPU5 的临时占位。两个占位服务已停止，CUDA 预留归零，并写入 `runs/software-panel-v053/gpu-hold-2-5/cancellation.json`；不会自动重新占位。该操作不取消原正式评测任务，也未产生任何模型调用。
