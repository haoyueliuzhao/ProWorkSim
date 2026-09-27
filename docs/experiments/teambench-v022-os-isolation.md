# v0.22 X1：D2 修订变体的实际 OS 角色隔离

本轮在普通用户权限下，用 **Landlock ABI 4 + seccomp** 完成了 D2 固定程序夹具的实际进程隔离：54 项角色权限控制全部符合预声明预期，既有 D2 修订评分的 15 项控制全部符合预期，另确认 grader 重新执行提交代码时也不能泄露 expected。Verifier 在自己的临时空间实际执行副本，原被审 workspace 的文件内容保持不变。

这建立了**一个已有明确名称的 D2 修订变体的评分和 OS 权限基线**，不是原生 TeamBench harness 全面修复，也不是目标模型协作成功。本轮模型、API、GPU、参数更新均为 0；没有自动启动外部模型评测。

## 1. 资产和版本不变

复用官方提交 d185aef1916fd86a9ba554d581fd256319a973af 的 D2_data_quality，仍只有 seeds 0、1、2。沿用 [v0.21 资产清单](teambench-v021-assets.json)及已审读字节的执行白名单，没有扩展第三个任务、增加数据源或重新解释 D1 的历史失败。

评分变体仍为 proworksim-d2-quote-failclosed-v0.21：只修原生 D2 缺失值诊断字符串的 shell quoting，并在外部入口要求 expected 存在、结构完整、SHA-256 与固定实例一致。**grade.sh 字节与上一版相同**，SHA-256 为 8b0a417ea3f810cfa07e376b80b869d479bf574305aef67c62903a738a9a096b。

任务数据仍为官方程序合成的 ETL 记录，非真实企业数据、非 UCI 派生、非独立新来源。这些已用于开发的 seeds 不是未接触外测实例。

实现新增于：

- [OS 边界](../../src/proworksim/teambench_isolation_v022.py)
- [固定 CPU 实验入口](../../scripts/teambench_isolation_v022.py)
- [定向测试](../../tests/test_teambench_isolation_v022.py)

没有改 N/W、现有 sandbox、冻结模型源码或原生 TeamBench 文件。

## 2. 实际设施探测

| 项目 | 实际结果 |
|---|---|
| 当前 UID | 1004，普通用户 |
| Kernel | Linux 6.8.0-41-generic，x86_64 |
| Landlock | syscall 返回 ABI 4，可建立规则并限制实际子进程 |
| libseccomp | 已安装，可装载过滤器 |
| rootless user namespace | unshare --user --map-root-user true 在 uid_map 写入处返回 Operation not permitted |
| bwrap / nsjail / firejail | 未发现可执行文件 |
| 宿主权限变化 | 无 sudo、无 setuid 提权、无 daemon / 用户组 / 内核参数修改 |

本轮不再以 Docker 不可用直接判断无法隔离。选择已有 Landlock，而非安装新容器平台。

每个角色进程先设置 no_new_privs，再装载内核 Landlock 文件访问规则和 seccomp，成功后才执行角色命令。Shell/fork/exec 可以用于真实验证，但子进程继承同一限制。网络 socket、跨进程内存和 FD 读取、namespace/mount、权限变更、修改文件元数据及逃离本次进程组等入口被过滤。

控制器为每次运行创建独立进程组，结束时只清理该组；不操作其他项目进程。任务执行限制为 15 秒 wall time、每进程 8 秒 CPU、512 MiB 地址空间、1 MiB 单文件、128 KiB 捕获输出、128 个 FD。**不是 PID namespace 或通用敌意 fork-bomb 资源隔离平台**；当前接口只运行本轮固定、审读过的程序夹具，没有接入任意模型命令服务。

## 3. 资料与写权限布局

| 角色 | 可读 | 可写 | 明确禁止 |
|---|---|---|---|
| Planner | brief、自身 full spec、合法 inbox | 自身 scratch/outbox | workspace、expected、grader、其他角色私有空间 |
| Executor | brief、workspace 原输入和代码、合法 inbox | clean.py、产物目录、自身 scratch/outbox | full spec、expected、grader、改原输入、伪造 verifier outbox |
| Verifier | full spec、被审 workspace、合法 inbox | 自身 scratch/outbox | 改被审 workspace、expected、grader、写其他角色 outbox |

expected.json、grader、可信解释器分派器均位于不授予工作角色的 trusted 目录。临时目录按角色授予，未授予整个项目、用户主目录、/tmp 或 /proc。运行库目录只读可执行，环境不含模型 API 密钥，文件描述符除受控标准流外关闭。

这是真实内核访问控制，**不是仅修改 cwd、prompt 或 Python read/write allow-list**。Landlock 不创建文件名命名空间；路径名称与某些元数据不等于完全不可发现，本轮验证的是内容访问和修改权限。后者另以 seccomp 阻止 chmod/chown/utime/xattr 等不由当前文件内容规则完整覆盖的操作。

授权文件若被替换为指向 trusted 的 symlink，控制器拒绝建立 profile，避免将该 symlink 的目标错误授予角色。合法目录内新建的软链接不能绕过目标内容的 Landlock 规则。

## 4. 54 项真实权限控制

Planner 16 项、Executor 17 项、Verifier 21 项，全部在独立 Linux 进程中执行。控制同时包含允许项和拒绝项，防止“全部命令都不能运行”冒充隔离成功。

共同控制包括 brief 读取、expected/grader 直接读取、父目录穿越、symlink 读取、hardlink 尝试、shell cat、写其他角色 outbox、自身临时文件/真实 shell 写入、socket 创建和 workspace chmod。

附加控制包括：

- Executor：可以读取原 CSV、直接更新 clean.py；不能修改原 CSV，不能直接或经 shell 读取另一角色 full spec。
- Verifier：可以读取真实代码和 full spec、写自身 attestation；不能直接、经 shell、经 symlink 或父目录穿越修改 workspace，也不能 unlink/rename 被审脚本。
- Planner：可以读取 full spec、写交接夹具；不能读取或修改 workspace。

拒绝的实际 errno 包括读取内容的 EACCES=13、越域 hardlink 的 EXDEV=18、seccomp 元数据/网络操作的 EPERM=1。没有用自编 Python 异常替换真实权限执行结果；shell 拒绝记录来自其子进程实际退出。

随后 Executor 在隔离进程执行正确 clean.py 生成结果；Verifier 将允许读取的 workspace 内容复制到自身 scratch，在那里再次执行 clean.py，得到 29 行结果并写出程序 attestation 夹具。对 verifier 前后的整个被审 workspace 作内容 SHA 对比一致，原 CSV SHA 也未变。

该见证证明可独立执行验证程序，不证明已有模型作出完整独立业务判断。实际模型评价仍须保留产物评分、验证动作、attestation 与联合责任的分项记录。

## 5. 修复一个容易遗漏的可信 grader 边界

原 D2 grader 会先运行 python3 clean.py。如果直接在可以读取 expected 的可信父进程环境执行提交代码，即使之前的 worker 已隔离，评分时仍可能把 gold 暴露给提交代码。

本轮保持 grade.sh 字节不变，在**只由可信 grader 使用**的 PATH 前放入固定解释器分派器：

1. 唯一的 python3 clean.py 调用重新进入 Executor 的 Landlock/seccomp 子进程。
2. 原 grader 内固定的 python3 -c 内容检查继续在可信评价空间执行。
3. 工作角色不能读写分派器、可信 PATH 或 expected；角色自身环境只使用 /usr/bin:/bin。

额外负控提交一个固定 clean.py，在评分器重跑时尝试读取确切 expected 路径。实际返回 PermissionError / errno=13，程序按预声明退出码 9 退出；原生检查记录 clean_crash 和 missing_output，即使伪造 attestation=pass，结果仍为失败（1/3）。这里的 1/3 来自原 grader 在无产物时不进入后续内容检查，保留原始分母，不解释成完整内容部分分。

因此不是“expected 在父进程里”这一布置本身构成隔离证据，而是**提交代码在 grader 重跑时的实际读取也被内核拒绝**。

## 6. 既有修订评分控制：15/15 符合预期

执行前写入 declaration.json，固定 3 seeds × 5 项；没有据结果换 seed。

| 程序控制 | 3 个 seed 的结果 |
|---|---|
| 正确产物 + pass 夹具 | 各 11/11，通过 |
| 错误部门纠正 + 伪造 pass | 各 10/11，department_correction_fail |
| 正确产物 + fail attestation | 各 10/11，bad_attestation |
| 缺 expected | 入口拒绝，score=null |
| expected 改值但保留原冻结 SHA | 入口拒绝，score=null |

9 项实际执行 grader，6 项在调用前拒绝。所有被 grader 重跑的 pipeline 都有独立的 OS 隔离记录。产物检查与 attestation 字符串检查继续分列；以上次数不作为模型 episode 分母或协作成功率。

## 7. 开发失败与保留证据

首次运行已完成 54 项权限控制，但真实 Python 文件入口随后因 blanket ioctl 返回 EPERM 而无法打开脚本。本轮把**仍被禁止**的 ioctl 的返回错误码改为标准 ENOTTY，没有放开 ioctl 或任何文件路径权限；固定 Python 文件入口随即正常执行。没有对具体 libc/Python 内部调用栈做跟踪，不能将该行为进一步归因到某个已确认调用。

- 首次失败及单点兼容控制：runs/teambench-v022-os-isolation/。
- 初步完整运行：runs/teambench-v022-os-isolation-final/。
- 补齐恶意重跑的明确 errno/退出码证据后的最终运行：runs/teambench-v022-os-isolation-verified/。

这些是同一固定小子集的开发重放，不是增加独立情境。原始最终报告与日志的引用、哈希、角色控制和评分结果见[证据记录](teambench-v022-os-isolation.json)。

必要校验：**2 passed in 0.28s**，三个新增 Python 文件 Ruff 通过；没有重跑全仓测试、模型或原 v0.21 业务评分。

## 8. 准入结论与启动边界

| 资格 | 结论 |
|---|---|
| 指定 D2 修订变体的固定评分控制 | 通过 |
| 指定布局的实际 OS 角色读写隔离 | 通过 |
| Verifier 在自身临时空间执行且不改被审 workspace | 通过 |
| grader 重跑提交代码时参考仍不可读 | 通过 |
| 未修改官方 TeamBench harness | 未准入；历史问题仍保留 |
| 当前固定 CPU 夹具入口 | 可运行 |
| 真实模型协作执行 | 未执行，未声称通过 |
| 自动外部模型队列 | 不启动 |

OS 权限缺口已在这个明确布局上闭合。**当前仓库没有由本 X1 runner 接入的模型适配器和外部模型实验预算，因此 model_benchmark_launchable=false。**后续可以在同一边界内接入一个有限、固定预算的 D2 修订版模型流程；须记录新适配器、运行合同与模型轨迹，不能复用原 host 工具让 shell 绕开隔离，也不能把这份程序控制结果报成原生 TeamBench 成绩。
