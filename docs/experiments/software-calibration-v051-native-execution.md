# v051 CAL2 原生 mini-SWE 与统一仓库评分接入

本说明记录 CAL2 模型运行前完成的执行接口与有限 CPU 控制。它不是新的模型实验结果，也不把程序控制记为模型能力。这里没有加载模型、启动 GPU、执行反向或 optimizer 更新。

## 原生 R 的实际含义

R 使用原始 Qwen3.5-9B 发布权重，没有已训练适配器，执行框架为固定的 mini-SWE-agent 2.4.6。其固定提交为 `a83fcae82d2a08f0ee0c688f9d137b3566c097f8`。[原始 DefaultAgent 源码](https://github.com/SWE-agent/mini-swe-agent/blob/a83fcae82d2a08f0ee0c688f9d137b3566c097f8/src/minisweagent/agents/default.py)

R、P、U 共同使用项目 v020 BF16 attention 与 FP32 LM head 数值路径。R 不是 CAL1 的 reference arm；R/P 的比较以执行框架为主要变化，P/U 以已有 actor 状态为主要变化。三者共同固定 non-thinking、18432 上下文、2048 输出、温度 0.7、top-p 1、top-k 0、双 EOS、pad 248044、单请求 HF `max_time=600` 秒。HF 的时间停止按生成迭代检查，不能代替宿主 100 分钟硬界。

每 R episode 最多 500000 实际输入加输出 token、128 次 query/attempt、128 次 bash action。90 分钟后不开始新 query，100 分钟为宿主硬界。没有新增模型资格请求或自动重试。R 不设置虚构的“与 P/U 32 次公开测试相等”的限制；每次完整公开测试也占用真实 query/action，但一个 bash 可以包含多条普通 shell 操作。两种框架的工具机会不同，应在结果解释中保留。

## 固定来源与未改变的主循环

实际来源快照是 `runs/v051-mini-deps/` 中的 15 个必要小文件；每个文件的实际 Git blob SHA-1 均与固定提交的返回值一致，另存 SHA-256。清单在 `artifacts/software-calibration-v051/mini-source/manifest.json`。这不是完整 wheel 安装。首次 PyPI 元数据访问发生 TLS EOF，未修改旧环境；随后从同一固定 Git 提交取得必要源码。原始访问失败记录保留。

实际使用原 `DefaultAgent.run/query/step/execute_actions`、原完成标志判断和原 tool observation formatter，不改原主循环。新增的是 Model 协议适配器和受限 Environment。原 mini tool 配置允许至少一个 bash 调用，本地公共桥接另明确每次生成只能有一个完整原生 Qwen XML bash 调用；该调用的字符串内部可以组合 shell 命令。格式失败保存原始响应并结算实际 token，不通过免费修补、隐藏请求或重采恢复。

模型输入排除 mini 消息的宿主 `extra` 元数据。对输入过长或 token 预约不足，运行器保存完整封印 native input、P/O/C、fits、剩余 token、决定/attempt 计数、actor/seed/初态绑定及零模型执行标志，再局部闭合。已经开始但没有完整返回的调用保留不确定预约，不补成零费用。

## 工作树、生产范围与评分树

`prepare_buggy_worktree` 从实际 buggy 文件映射新建仓库，仅创建一个 buggy 初态 commit，不克隆上游 `.git`、不导入正确版本历史，也没有 remote。宿主初态记录与模型最终 raw candidate 均保留。最后的原生完成标志只说明 mini 结束工作，不代表代码已通过。

最终评分使用独立文件树：恢复固定原测试、配置及 support；保留原 editable 生产文件的真实修改/删除。合法新增生产范围事前固定为 boltons 包目录内的 `.py` helper，或 parse/xmltodict 的顶层 `.py` helper。新增 conftest 和 pytest/build 配置不进入评分树。排除项仍留在 raw candidate，不改写原件。

R 工作树中的公开测试可以被模型修改，这是原生文件系统框架的实际行为。P/U 公开测试由世界接口保持只读。不能把 R 自改测试得到的通过当作最终 oracle 通过。两者使用同一个固定节点 pytest runner；R 的唯一规范完整公开测试命令为独立的 `calibration_public_tests`，每次调用执行一次完整 suite，不能混在其他 shell 语法中。它也使用下述有限 TCP fixture，因此不会出现只有宿主评分能跑 TCP 测试、R 正常公开测试必然报网络错误的接入差异。

## 本地 shell 隔离的已证明范围

当前主机没有可用 Docker 权限，也不能使用无密码 sudo；没有修改这些权限或旧环境。新 shell 使用本机已有 Landlock ABI 4 和 seccomp。

工作树是唯一可写的业务目录；明确的 Python/系统运行路径只读。网络 socket 创建、connect/bind/listen、跨进程控制和不受 Landlock 文件内容权限约束的危险元数据操作由 seccomp 拒绝。匿名 AF_UNIX socketpair 与必要的子进程/线程允许。新 user/network namespace 创建被拒绝。每个命令使用独立 process group，正常结束或超限时执行组清理。

独立 shell/pytest 进程在执行候选代码前写入不可覆盖的 `process.json`，绑定自身 PID/start ticks/PGID/SID、启动父 PID/start ticks 及 spec SHA。`cleanup_registered_children` 只清理由这些记录及实际进程身份共同证明归属的独立组，保留 TERM/KILL 和未决回执；不能宣称覆盖任意逃逸或未登记后代的全进程树。未来 CAL2 宿主必须在主动停止前和 worker 退出后调用此接口，以覆盖已登记子组及登记与退出之间的竞态。完整 CAL2 宿主本轮尚未实现，这个 helper 不会自动开启 GPU 运行。

命令墙钟上限 30 秒，公开 pytest 60 秒；另有限 CPU、地址空间、单文件和输出上限。工作树总字节/文件数为周期采样守卫，不宣称内核硬配额。原生普通文件工具不访问宿主 reference、其他 episode 或原正确源码。Landlock 不隐藏所有文件元数据；本控制验证的是内容读写与执行边界，不宣称完整容器等价。

不重设 `HOME`。显式 Git 配置隔离，shell 使用基础 C locale，Python 使用显式 UTF-8。这个选择发生在 CAL2 模型前：必要边界控制的原输出有 locale warning，它会遮住 mini 要求位于 stdout 首行的完成标志。修订后只补了一个真实完成标志检查，没有重跑先前完整边界控制。

## 有限真实 loopback FD fixture

固定 boltons 完整节点集包含两个必须使用 localhost TCP 的测试，不能删除：

- `tests/test_socketutils.py::test_socketutils_netstring`
- `tests/test_socketutils.py::test_socketutils_netstring_timeout`

它们合计需要两个 `127.0.0.1:0` listener 和 4+1 个 client。宿主先创建这五条真实 TCP 连接，将有限 FD 传给评分进程。窄适配把这两个原测试的 socket 构造、同一 localhost bind、backlog 100 listen 和已知地址 create_connection 对应到这些现成 FD；原测试文件、断言、accept/send/recv、关闭、长度检查及读超时保持实际内核操作。子进程创建新 AF_INET socket/connect/bind/listen 依然被 OS 拒绝；该 Python 适配本身不是安全边界。

连接建立提前于测试。因此这是明确的本地环境桥接，不是原容器网络的完整复现，也不用于测量连接建立性能。原测试断言不考察 bind/connect 时序。原两测试在该 fixture 下各执行一次，2/2 通过；原文件未变，missing/unexpected 节点均空。

## 评分与 collection failure

共享入口为 `run_repository_tests(files=..., task=..., run_root=...)`。它将候选物化到 `/tmp/v051c/<纯数字>`，保留固定原 node IDs。parse 使用其原 `.pytest.ini` 和 doctest 配置，boltons 使用原 pytest 配置，xmltodict 才使用固定空配置。显式加载已冻结 pytest-cov；coverage 写到单独 scratch，不改生产文件。

返回真实 pytest code，与 wrapper process code 分列。完整回执包含每个实际节点的 outcome/longrepr、missing/unexpected、输入文件 SHA、执行前后输入文件比较，以及实际 collection exception chain/trace paths。

常规已知评分要求外层 worker code 为 0、没有超时/输入变更/额外节点、固定节点全部实际观察到，且 pytest code 只能为 0 或 1；全部通过还要求 pytest code 为 0。pytest code 3 即使附带所有节点通过记录也保持 unknown，外层 worker 异常退出同样保持 unknown。充分绑定的候选 collection failure 为下述独立例外，不能用完整节点记录绕过终态 code 检查。新增三个纯元数据反例只检查这些边界，没有执行新的 pytest。

可信的候选生产代码语法或导入错误可以使固定节点无法收集，不能一概变成基础设施技术未知。只有原 tests/config hash 匹配、运行中输入未变化、实际异常链落在已改变的声明生产文件或充分绑定的新 helper/被删生产模块时，才把 collection failure 归为已知代码不通过。未执行节点仍记未运行，不伪造失败执行。其他缺证、命令/配置/隔离问题保持 unknown。

必要的一个 synthetic SyntaxError 控制发现：显式传 node selector 时，pytest 7 会返回 4（no collector），而不一定返回 2。首个控制判定失败及全部输出保留；随后仅从该原件重物化归因，允许带完整证据的 2/4，普通 code 4 仍不合格，没有重复运行 pytest。

## 必要控制与接口交付

本轮控制分开记账：两个原 TCP 测试；一个真实 native shell 负例脚本的七个边界/可用性断言；一个新完成标志检查；一次原 mini 主循环的三条程序化假响应（含格式失败和账单结算）及一个执行前预算反例；一个 synthetic collection failure 与纯元数据反例/配置绑定检查。程序化假响应不是模型调用。原六题×三态来源资格以及此前 raw provider 的控制均未重复运行。

另仅执行一次必要子组生命周期控制：模拟 worker 被 SIGTERM 后，已登记独立子进程仍存活且 parent PID 变为 1；helper 核验原 spec、父身份绑定及实际 PID/start ticks/PGID/SID 后清理成功，`owned_group_terminated`、`unresolved=[]`、`passed=true`。原件为 `controls/lifecycle-first/result.json`。没有重复执行旧 TCP、shell、mini 或 collection 控制。

正式文件：

- `src/proworksim/software_calibration_v051_mini.py`：原 mini loop、raw native Model、账单、buggy-only worktree 与结束回执。
- `src/proworksim/software_calibration_shell_v051.py`：独立受限 shell。
- `src/proworksim/software_calibration_repo_tests_v051.py`：P/U 与 R 统一的固定节点 pytest 和 FD fixture。
- `src/proworksim/software_calibration_process_v051.py`：宿主侧已登记独立进程组归属核验、清理及回执。

R episode API 为 `run_native_case(owner, task=..., worktree=..., seed=..., output=..., mini_manifest=..., workspace_receipt=..., initial_files=...)`。不自行加载模型，不自行选择检查点，不执行最终权威评分。宿主负责资源准入、最新 GPU 范围/并发、硬截止、固定测试恢复后的权威评分和全局停止。

控制原件、原型及交付清单位于 `artifacts/software-calibration-v051/mini-work/`。这里的所有接口与控制均为校准准备；真实 R/P/U 结果须由其后独立科学槽报告给出。
