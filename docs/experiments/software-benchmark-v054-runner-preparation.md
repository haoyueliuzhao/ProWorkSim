# v054 三组单题执行器装配与 CPU 全链路准备

本轮把原先独立的 SDK、数值 transport、受管 S1、宿主监控和候选导出接成了可执行单题入口。三个准备回合均使用真实隔离的 Astropy 公开仓库、原生解释器与真实工具，但响应由明确标记的程序化 CPU fixture 提供；没有调用实际模型、加载权重、占用 GPU、执行训练或消费正式 1,500 题槽。CPU 链路通过不能替代 GPU 容量、真实数值 provider 或标准基准能力成绩。

## 可执行入口

```bash
.venv/bin/python tools/run_benchmark_episode_v054.py \
  --config /absolute/path/to/frozen-slot-config.json \
  --output /absolute/path/to/new-slot-directory
```

`tools/prepare_runner_control_v054.py` 物化一个合成任务及 REF、MATCH、PROJECT 三个独立准备槽。它需要实际 rootfs 环境、Actor 环境、共同初态 mapping 和评分器安装 manifest，不会用假仓库或假隔离标志替代这些输入。

正式入口另外要求原始固定题槽清单 SHA、明确的逐槽模型／预算授权、完整公开题目投影及源文件冻结记录。正式问题文本必须等于公开投影中的原文，不能改写成准备合同。PROJECT 正式入口还要求从完整 500 条公开测试 registry 选择同题条目，并绑定同一个评分 baseline mapping。这里的 CPU 回执和 condition 文件本身保留 `formal_execution_authorized=false`；用户后来对三组各 500 题、总计 1,500 回合／750M token 上限的执行授权由独立新 permit 表达，旧准备回执不改写为授权或真实实验结果。

宿主 runner 先完成按需的该题真实环境初始化，再原子取得物理 GPU／全局驻留锁及 REF 独占端口预约，随后领取唯一槽、克隆独立公共初态、创建资源 slice，分别启动 actor、model、controller 服务。controller 只通过真实 SDK 工具或原 S1 受管接口工作。模型进入、公开测试、关闭、候选锁定、评分请求形成均有分开的持久化记录；已进入槽不重采，不因失败另选候选。

## 数值与计量路径

REF 继续使用固定本地 vLLM HTTP 协议和共同精确计量包装：官方 `/tokenize` 完整 token IDs、同一模板参数、生成前完整输入加 32,768 输出预约、返回 usage 精确核对，无远程端点、重试或 fallback。准备控制使用单独的 `127.0.0.1:18055` 程序化 HTTP fixture；正式端口仍为 18054。

MATCH 的实际 `CalibrationActor`、原始 `generate_native` 方法、原始数值配置、MATCH bridge 与 episode ledger 全部留在独立 owner 服务内。controller 的 Unix IPC 客户端只传完整请求／精确计量证明和响应，不把代理对象冒充真实 `CalibrationActor`，也不放宽 bridge 原有的真实 owner 门。condenser 和 agent 使用同一个 adapter／服务账本，保留总计 500,000 token、128 次全部尝试及 128 次 agent decision 限制。短准备回合未触发 condenser；其独立共同账本控制沿用之前已通过的精确 transport 证据，不重复执行。

PROJECT 保留真实 S1 工具、原 Γ1 历史表示、原上下文投影和 `SingleMemberBudget`。本轮使用真实 SDK staff worker 走 `build_runtime`／`run_fragment`，没有直接替模型调用 World 方法，也没有给 PROJECT 增加 bash 工具。实际模型请求仍交给同一 raw release owner 的原 `complete`／`generate_native` 数值路径。

真实 owner CLI 为 `tools/serve_benchmark_owner_v054.py`，显式区分加载准入、capacity smoke 和正式题槽授权。`load_actor` 的 manifest 实参是文件路径，并复用已有完整模型 stat 审计回执。MATCH 与 PROJECT 均使用同一 r3/r5 `acquire_startup` 和逐次 `native_context`，保持 native allocator、物理 UUID 与真实 BF16／FP32 路径。没有通过替换 `owner.generate_native` 实现缓存包装。

capacity smoke 只接受 `synthetic-` 槽，最多两次实际生成；`smoke_count` 使用同一真实 tokenizer／模板，但不消耗生成次数。容量 smoke 可保留正式 18,432／2,048 合同，短提示实际提前停止不等于修改输出上限。真实 GPU smoke 由另一个准备监控器执行，未混入这里的 CPU 数据。

## 隔离、公开测试与关闭

controller、actor 和每次公开测试的全部执行子孙共享同一项目专用 **system slice**，内核上限为 4 CPU、16 GiB、16,384 pids；model 服务在独立范围。这里使用 system slice，是因为当前 user manager 没有委派 CPU controller，不能把不存在的 `cpu.max` 当作资源约束已生效。

正式模型启动前还须获得物理 UUID 的非阻塞 flock，以及四个全局 resident slot 中的一个。锁位于 `runs/v054-gpu/locks`，不分配显存，不启动占位进程。CPU fixture 跳过 GPU lease。服务 RuntimeMaxSec 兜底包含有界准备时间；另一个独立宿主 watchdog 从正式 episode 进入时刻计算原定 5,400／6,000 秒 soft／hard 边界。

PROJECT 的 `run_tests` 将当时完整受管源树放入该任务基线的全新 rootfs clone，在共同 slice 内运行预先准入的公开 argv。模型只能调用原 `run_tests`，不能自由指定 shell 命令。每次公开测试使用独立初态；实际 stdout／stderr、退出码和执行树身份返回原分页反馈。嵌套子模块的已准入 `.git` 控制目录在物化前暂存、物化后恢复，公开子模块文件仍是完整候选的一部分。

公开测试服务动态加入带 flock 的 episode scope registry；监控器停止时先封住新登记，再停止所有已登记服务。worker closed ACK 不等于静默。候选锁定要求 cgroup 为空、实际 writer 已退出、外层 launcher 已回收。原生两组复用完整树捕获与 Git patch roundtrip；PROJECT 复用原双端点锁，保留 terminal code 和最后合法提交的区别。

锁定之后才生成官方评分请求，包含 condition、endpoint、候选、baseline mapping 和独立 cache identity 输入。评分器及隐藏材料保持在宿主评测侧。三组准备共生成四份请求；本轮没有再次运行官方评分，也没有把任何评分结果反馈给 controller。

## 实际 CPU 结果

完整汇总为 `artifacts/software-benchmark-v054/runner/cpu-integration.json`。同一合成任务采用独立初态与同一个 seed，三个成功回合如下：

| 条件 | 成功记录 | 程序化尝试／decision | 程序化 token-ID 计账 | 公开检查 | 最终端点 |
| --- | --- | ---: | ---: | --- | --- |
| REF | `runner-control-r2/REF` | 3／3 | 23,027 | 实际 Astropy import 与文件检查通过 | code |
| MATCH | `runner-control-r1/MATCH` | 3／3 | 22,931 | 同上 | code |
| PROJECT | `runner-control-r2/PROJECT` | 5／5 | 65,029 | 真实 `run_tests` 一次通过 | code 与合法 delivery |

这些数字来自实际 tokenizer 对程序化输入／输出的计账，**不是模型生成消耗、模型完成率或费用估计**。PROJECT 实际经历创建文件、公开测试、固定补丁、提交、结束五次 SDK decision；最后工作树与最后合法提交同树。三组的全部 writer 均已退出，共同资源 slice 均已释放。

初始完整公共树 SHA 三组相同：`6f33cb1116758186a7b1c2e713621bb5e689411fcffe28d118ad6228d74010ad`。原生组的公开 import 在其实际工作树创建了 24 个 Python bytecode cache 文件，按既有完整工作树规则随候选保留；PROJECT 的公开测试发生于独立 clone，受管工作树只增加 probe 文件。因此两种执行方式的最终树不同，本轮没有为了相等而临时过滤文件。

首轮 REF 因 keyword-only transport 参数传法错误在生成前失败；首轮 PROJECT 因 Unix socket 路径过长在进入 owner 窗口前失败。两份失败记录保留，修复后只重跑这两个受影响分支。MATCH 已通过链路没有重跑。

其后收尾增加了正式槽／原始问题／公开 registry 校验、物理 GPU lease、SDK import-ready 屏障、包含准备时间的服务兜底、gitlink descriptor 传递和已准入嵌套 Git 控制目录恢复。这些是独立准入或编排边界；没有据此声称新的真实模型或 500 套测试已执行。新增源码进行限定 Ruff 检查，既有通过的工具／数值／评分组件控制不重复运行。

## 基线修订与剩余准入

三个 CPU 链路控制使用当时已经准入的 r2 Actor 派生镜像。后续公开入口观察发现，单根 Git 会改变部分仓库的 Git 派生版本字符串；r3 基线因此恢复合法 official setup HEAD 及其祖先／合法 tags，同时移除未来和不可达对象。三组控制保留为不变执行器、资源和关闭链的证据；r3 的实际基线与版本等价性使用新的独立回执，不整体重跑本轮链路。

公开测试 registry 绑定最终 r3 的逐题映射与 setup tree，另外说明其 21 个仓库×Python 代表入口观察的覆盖范围；它不意味着已执行 500 套完整 suite。真实 GPU 容量／数值 smoke、最终配置冻结和正式预算授权独立保留。任何缺失真实候选、usage 或评分闭合的情况仍是技术未知，不计为普通模型失败或零费用。

## 完整面板与正式服务装配收尾

`config/v054-public-test-registry.json` 实际包含 **500 个唯一任务、500 个准入公开入口、0 个未解决入口**。每条绑定最终 r3/r3.1 mapping、official setup tree、公共解释器和逐题实际版本等价证据。Django 使用仓库公开 `tests/runtests.py --noinput --parallel 1`，Sympy 使用 `bin/test`，其余仓库采用预先固定的 `python -m pytest` 常规入口；未读取 F2P、参考修复或隐藏测试来选择入口。Python 2.7 的 Requests 环境没有加不支持的 `-I` 参数。

21 组前端 help／依赖观察来自此前 r2 Actor；r3/r3.1 与其公开源树、解释器和前端脚本的关系单独记在 registry。Django／Matplotlib 的 Git 派生目标包版本正是后续修复对象，因此不宣称旧 r2 目标版本与 r3 相同；最终 500 条目标版本与原官方镜像相同由新逐题回执证明。没有再次执行 21 组 help，更没有运行 500 套完整 suite。

`software_benchmark_slot_factory_v054.build_slot_config` 只接受固定 `config/v054-condition-{REF,MATCH,PROJECT}.json` 和专用 `software_benchmark_service_factory_v054.build_service` 生成的真实服务声明。条件具体记录 checkpoint、原始采样／窗口／输出、原生五工具或真实 S1、condenser、共同账本、时间及候选终态，不接受调用者任意替代 JSON。运行前校验完整小源码 manifest，覆盖全部项目 Python、脚本、v054 launchers/config，以及固定 OpenHands SDK／工具／模板；没有再次散列模型或镜像大文件。

服务工厂从 `model-capacity-admission.json` 读取分别通过的 REF／MATCH 真实容量回执，核对原模型 manifest、数值配置、实际 runtime 源和环境变量；PROJECT 使用同一个 MATCH raw owner 数值准入。不同容量准备修订保留各自 seal，允许操作性监控修复，不能把数值源变更默默视为已通过。没有真实通过凭据时只能输出静态模板，不能制造 owner/loading 准入。

正式宿主解释器固定项目 `.venv/bin/python`，`PYTHONPATH=src:项目根目录`。系统 `/usr/bin/python3` 的实际导入检查缺 `openpyxl`，因此不能用于该入口；GPU／SDK 仍使用各自原独立环境。REF 仍端口 18054、至多一个 REF resident；每个服务使用新私有 API key，`/tokenize` 和生成 HTTP 都鉴权，不会误连旧服务。REF 的 `TRITON_LIBCUDA_PATH=/opt/host-nvidia` 使用已挂载只读驱动目录，`VLLM_RPC_BASE_PATH` 使用每服务短目录，完整 IPC 路径 100 字符，均属部署修复，未改变采样、窗口、KV 或输出上限。

REF 的采样内核需要当前服务器已有 CUDA 13.0 编译工具，私有 runtime 仅只读绑定 `/usr/local/cuda-13.0` 并设 `CUDA_HOME=/usr/local/cuda-13.0`；没有另下载 CUDA，也没有改变 MATCH／PROJECT 的数值服务环境。其真实可用性仍以独立最终 REF 容量回执为准。

物理 UUID／全局驻留 lease 和 REF 端口预约均先于正式 claim。资源暂不可用返回 `resource_not_ready`、退出 75、`slot_claimed=false`，原因限定为 `gpu_lease_busy`、`ref_port_busy`、`gpu_capacity_gate`。环境初始化、文件身份、权限、容器或配置故障不能伪装成资源等待；已 claim 的技术故障不自动重采。

收尾还修复了一个会直接中断大面板的正常预算闭合缺口：原 native controller 将 `DispatchStopped` 一律作为技术未知，而 MATCH RPC 原 handler 又会令 owner 服务关闭，导致完整输入预约不足或 128 次上限本来没有新生成，却无法执行原 finish／RNG guard。正式服务现在用独立 `FormalOwnerService` 子类包装 RPC dispatch；原 `CalibrationActor`、`generate_native`、MatchBridge、原账本扣数、缓存和已封存源码均未改变。仅当异常类型恰为 `DispatchStopped`、原因属于固定的预算／soft 预执行停止、原账本无 inflight 且实际费用完整时，返回唯一 terminal boundary，随后调用原 finish、关闭 writer 并锁定已有候选。REF 同样保留原 reserve／ledger，再准确分类这一停止。单个合成账本／dispatch 控制验证了 MATCH 原 128 次门、REF condenser 完整预约不足，以及正常停止后仍能执行原 finish guard；未重跑真实模型或三组 CPU 链路。

这不是一般异常降级：`AccountingFault`、不完整 usage、错误授权、HTTP／格式故障仍为技术未知，禁止重采；硬期限中断尚未结算的请求也不会冒充已知费用的正常预算停止。

controller 同时接受精确的 `NormalEpisodeBoundary` 和官方 `ConversationRunError` 的直接包装：后一种必须满足 `original_exception` 的精确类型及 `__cause__` 对象相同，并再次核对原因白名单和完整账本；不使用异常文本匹配或递归查找。独立补控制只构造已安装 SDK 的真实异常类型，验证正常直接／包装路径及错误 cause、AccountingFault、普通同文异常的拒绝，没有重新运行 Conversation 或模型。

宿主通过 Unix `SCM_RIGHTS` 将同一 flock 的描述符复制给独立 model 服务。宿主 PID／start_ticks 不再存在时，服务停止生成并关闭自己的子进程；只有严格限定的本 model cgroup 中其他进程全部退出后才释放这些描述符。这样宿主崩溃不会让显卡锁提前空闲。新增唯一窄控制 `deployment-control-r2/receipt.json` 实际验证了宿主 SIGKILL 后两把锁仍忙、受管子孙退出后才可再取锁，以及本地 HTTP 鉴权／401 不重试。控制没有读取模型权重、加载 GPU 或 claim 正式槽。r1 发现项目 Python 没暴露 `os.pidfd_open`，修为本机 Linux x86_64 的原生 pidfd 系统调用后，仅重跑受影响的窄控制；原三组链路未重跑。

## 输出安全与规模所需回收

公开测试输出通过根目录 fd 逐层 `O_NOFOLLOW` 打开，只允许完整普通文件。stdout、stderr 各上限 16 MiB；符号链接、FIFO 或超限都是明确异常，保留现场，不静默截断或跟随到宿主隐藏材料。输出先另存宿主证据，再回收测试 clone。

回收只作用于当前 episode 下、manifest 证明是克隆的那个 `rootfs`，拒绝共享模板、符号链接和仍有进程的 cgroup。正常公开测试保存输入树、argv、完整输出与退出证据；正常 episode 保存最终候选、PROJECT 双端点锁、patch／源树及官方评分请求后才删除一次性完整 rootfs。技术未知、未锁候选或输出异常现场保留。独立安全读／清理的两项小控制已通过，沿用 `native-environment/rootfs-io-control-r1.json`；本轮没有为了回收重跑三个 CPU 回合。

最终汇总为 `artifacts/software-benchmark-v054/runner/preparation-manifest.json`。其中执行器、500 入口、lazy factory、服务模板、源冻结和部署控制与真实容量准入分栏；CPU 准备成功不填写正式模型完成率，也不把仅生成评分请求表述为评分已完成。

第二版封源仅跟进 REF 私有 `/usr` overlay 的 `cc → gcc`、`c++ → g++` 链接修复：实际 FlashInfer 采样扩展的编译／加载已在独立准备控制中通过，没有更改本单题服务 argv、模型窗口、输出或采样。第一版 source／preparation／service-template manifest、三组 condition，以及当时 REF wrapper／capacity monitor 源码完整保存在 `runner/revisions/r1`，由 `snapshot-index.json` 同时记录原身份和快照身份。第二版只更新当前源清单及其引用，原 CPU 三组、部署锁和预算边界控制均未重跑；最终真实 REF 容量结果仍由独立 admission 发布。
