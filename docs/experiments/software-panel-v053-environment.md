# v053 原始 SWE-smith 环境、候选导出与最终评分

日期：2026-10-20。本文配合 [主协议](software-panel-v053-protocol.md)，说明本轮新增的环境接入和评分实现，不是一份模型能力结果报告。

## 当前证据边界

本说明建立时，固定数据来源和仓库候选清单已经形成，专用 Docker 服务及镜像下载正在准备。宿主官方 harness 已完成原生导入，固定使用 SWE-bench `4.1.0` 配合 SWE-smith commit `9b74ac08118a85c39c356802f7961893af73e07f`。宿主依赖的实际版本与源码哈希见 `runs/software-panel-v053/harness-venv/bootstrap/official-import-receipt.json`，其 SHA-256 为 `593d6fa376249072fc1555367ab3af0869d47502cb5819b27084ad97cb7d9552`。

首次尝试的 SWE-bench `5.0.2` 缺少该固定 SWE-smith 源码所需的旧导出接口，因此没有用于实际题目评分；随后在独立 harness 虚拟环境内固定为 `4.1.0`，没有给官方源码添加兼容桩，也没有修改模型常驻环境。

前八个官方镜像已通过标准 Docker load 导入，并逐一核对原始 config image ID，见[镜像传输说明](software-panel-v053-image-transfer.md)。pipeline-v2 随后的八个初始化尝试均因错误地将上游 commit 当作镜像内 Git 对象而提前失败，尚未运行测试节点或模型；这些原始 `admitted=false` 是公共接入错误产生的记录，不是有效来源排除，不用于替换仓库。

v3 改用官方镜像实际初态，相关证据及上游／镜像历史差异见[镜像基线修订](software-panel-v053-mirror-baseline-v3.md)。Faker、Pydantic 两份实际镜像已完成无模型源码控制：重建缺陷树等于各自原官方任务分支的 bug tree；逆补丁返回镜像初态；删除 F2P 后的树等于原官方任务分支；删除旧历史及缓存、重建唯一提交后源码树不变。回执位于 `runs/software-panel-v053/mirror-tree-control-v3-r2/summary.json`。首个控制尝试使用了官方 valid 不要求的 `git apply --index`，在测试前遇到 index 匹配错误；日志保留，修订后使用官方的普通精确 `git apply`。

随后 v3 实际执行了 CPU 资格测试，但发现整删官方 uv 缓存的公共接入错误后已暂停。停止时保存 76 份任务资格（64 true／12 false）、161 次阶段尝试及 160 份阶段回执；这些是中断准备阶段的原始记录，不是最终面板，也不能把已知公共错误产生的 false 用于来源排除。状态及证据引用见 `runs/software-panel-v053/v3-common-cache-fault.json`。

v4 缓存修订及必要控制见[缓存适配说明](software-panel-v053-cache-adaptation-v4.md)。目前仍未执行真实候选导出到独立 judge 的完整控制，不能称本地已有 200 个可运行任务，不能称 Docker 端到端评分已通过。没有模型调用、训练或 GPU 准入动作。

## 固定身份和容器边界

主要代码：

- `src/proworksim/software_panel_docker_v053.py`：官方 profile 接入、环境准入、独立 actor／judge、候选锁和严格评分。
- `scripts/software_panel_environment_v053.py`：按预锁仓库顺序并行准入，以及一次完整 CPU 后端控制。
- `tests/test_software_panel_docker_v053.py`：快照路径／链接、不可覆盖、真实测试转移、严格完成口径、公共故障与进程身份边界。

v4 配置文件为 `runs/software-panel-v053/backend-config-v4.json`，新回执目录为 `runs/software-panel-v053/environments-v4`。Docker 客户端必须显式连接：

```text
unix:///data0/zhuxinrui/projects/ProWorkSim/runs/software-panel-v053/docker/docker.sock
```

程序拒绝默认 `/var/run/docker.sock`。镜像只在 CPU 环境准入期间按已预选仓库拉取；不会拉取整个公开资产池。保存请求的官方 image 名称、实际不可变 image ID、可取得的 RepoDigests、操作系统和架构。正式回合使用已准入 image ID，禁止临时拉取另一标签版本。

每个 actor、每次 clean／bug／gold 检查和最终 judge 都使用独立容器；默认每容器 4 CPU、10 GiB 内存、512 PID，关闭网络，不挂载宿主目录或 Docker socket，丢弃 Linux capabilities，启用 `no-new-privileges` 和 Docker init。八仓库 CPU 并行窗口最多对应 32 个 CPU 配额；该数字是配额，不是实际 CPU 使用量。

任务工作目录固定 `/testbed`。官方 profile 类、源码文件、上游来源 commit U、镜像内实际 main commit C／Git tree T、实际源码工作树 B、测试命令、超时、原始测试文件集合、核心官方评分文件及依赖版本都进入资格身份。U 标记上游来源，不能用于重置镜像源码；官方镜像的 mirror 历史经过重建，U 通常不是镜像内存在的对象。

每个仓库事先保存 `image-baseline.json`：精确 image ID、明确 `refs/heads/main`、HEAD／main／origin-main 一致的 C、官方 mirror remote、T、B、初始 Git 状态与 T→B 安装差异哈希。B 的范围是 Git 已跟踪和非忽略的源码文件；依赖及忽略的构建产物仍由不可变 image ID 绑定。计算 B 使用一次性容器的临时 index，不修改原工作树内容。B 不要求等于 T，例如官方 fvcore 安装命令会删除 `tests/test_focal_loss.py`，不能在准入时恢复该文件。每个新容器再次核对这些身份后才应用缺陷。

宿主设置 `PYTHON_DOTENV_DISABLED=1`，并确认当前 python-dotenv 支持此开关。配置 `disable_dotenv` 必须为 true，避免官方模块导入时自动读取项目 `.env`。这不改变官方测试解析器。

## 事前来源资格

按已经锁定的仓库顺序，以最多八仓库的连续窗口并行准备。只有一个仓库原先预选的十个任务全部合格，它才进入可选择集合。不在同仓库里把未通过的任务替换成另一个题目。

每种完整 clean 身份只执行一次。复用键包括 image ID、C／T／B 基线、测试命令、资源配额、profile／评分源码身份和宿主依赖版本；只有完全相同的执行身份才复用其完整测试状态映射。不同任务的预定 F2P／P2P 仍分别核对，不能因为同仓库的另一题通过就默认本题合格。

| 状态 | 来源构建 | 必要观察 |
| --- | --- | --- |
| clean | 官方镜像实际工作树 B，保留安装阶段改动 | 本题全部 F2P 与 P2P 均 PASSED 或 XFAIL |
| bug | 在 B 上精确应用本题官方 `patch` | 每项 F2P 实际 FAILED 或 ERROR；每项 P2P 仍 PASSED 或 XFAIL |
| gold | 独立重建 bug，再精确反向应用同一 `patch` | 工作树严格回到 B；全部 F2P／P2P 均 PASSED 或 XFAIL |

这里的官方 `patch` 是缺陷注入，不是模型答案；官方 gold 语义是反向应用它。使用 `git apply --check` 后精确应用，不用模糊匹配或临时改动测试来使题目通过。每个状态均由独立容器开始，不复用其他状态的运行产物。

镜像已经带有本题官方 remote branch 时，保留其 commit、bug tree、隐藏测试 tree 作为辅助对照。B=T 时直接比较；B≠T 时只尝试将固定安装差异机械投影到官方 bug tree。投影存在上下文冲突时记录“不可比较”和原因，不猜测合并、不改变 B，也不据此淘汰来源。分支缺失同样不构成来源排除；官方 valid 的核心输入本就是固定镜像初态与数据集 patch。可比较而结果不一致属于身份故障，必须暂停。各状态的 `source-state.json` 保存实际树转移证据。

测试命令取固定官方 `profile.get_test_cmd(task, f2p_only=False)`，状态解析取原官方 `profile.log_parser`。clean 使用原 `timeout_ref`；bug／gold 和最终评分使用原 `timeout`。具体秒数来自各仓库 profile，不依据本轮结果调大门槛。

每个最终可用仓库另以它的第一个预锁任务做一次无模型 actor 初始化和候选导出机械检查，用于发现该镜像的文件类型、归档体积、隐藏测试初态等接入差异。此检查不增加测试评分，不对其余九题重复相同的归档机制检查。

中断的 CPU 准入尝试单独保存，恢复时不覆盖原日志；已经完成且身份一致的阶段通过内容引用复用。恢复未完成准备不产生新的模型回合，也不允许按模型成绩挑选来源。

## 模型初态和公开测试

从镜像实际工作树 B 应用缺陷后，actor 删除 F2P 对应的整个测试文件。这是官方 SWE-smith 任务分支的隐藏粒度。若同一个文件也包含 P2P，该部分 P2P 同样随文件隐藏；不会另外删除仅包含 P2P 的文件。有些仓库因此可能没有剩余的公开测试。

所有 clean／bug／gold、actor 和 judge 工作树都清除原 `.git` 历史、已有 `__pycache__`／`.pyc`／`.pyo` 和 pytest 缓存，移除临时缺陷 patch，再建立单初态 git 提交。actor 在删除隐藏测试后才重新提交；judge 的唯一初态是完整测试下的 bug。于是模型不能从 actor 的祖先提交找回原始源码，候选代码在 judge 内执行时也不能通过 `git show` 读取正确祖先。

保留不可变官方镜像的依赖构建缓存，不再整删 `/root/.cache`。Pydantic 的原 editable wheel 已逐项检查，只含指向 `/testbed` 的 `.pth` 及分发元数据，没有 `.py`、字节码或实现二进制。容器固定 `UV_OFFLINE=true`，让 uv 使用镜像内已有依赖与索引缓存；仅有 `network=none` 不能阻止 resolver 主动请求索引并失败。官方 `test_cmd` 和依赖版本未改。这一缓存政策进入 contract 及 clean 复用键，避免复用修订前的失败结果。

这些属于相对原始官方运行包装的显式接入变化。资格检查使用同一历史／缓存清理方法；如果某个来源依赖保留原 git 历史才能通过测试，必须记录为该固定环境下不可准入，而不能在模型启动后临时放宽。

actor 的公开测试仅执行 `profile.test_cmd`，对象是它当前可见的工作树。公开测试不会创建 judge、恢复隐藏测试或读取资格／gold 回执。公开命令成功不能当作最终任务完成。最终 judge 才恢复完整原测试并执行权威命令。

终端文件在同一回合内保留，shell 状态和后台进程不跨命令。actor 命令串行执行：命令前记录容器内 PID 与进程启动时间；命令后清理新增的活进程，包括另建 session 的后台进程。PID 1、清理器自身和仍具有相同启动身份的既有可信进程受保护。PID 复用不被错误当作可信原进程。Docker init 回收孤儿进程；清理失败或仍有活进程时返回执行故障，不继续假定终端合同成立。

## 唯一候选和独立 judge

结束时先暂停 actor，再由 Docker 服务读取完整工作树归档；不信任模型可修改的 `.git`、索引或 `git diff` 作为候选来源。宿主将归档规范化为文件／符号链接清单与内容哈希，移除 `.git`、Python／测试缓存、`.venv`、`.tox`、`node_modules` 等固定环境目录。

工程上限固定为 16 GiB 原始归档传输、512 MiB 实际导出源码。两者不同是因为镜像可能在工作树内包含大型 `.venv`；它可以被流式跳过，不能成为模型提交的环境修改。归档拒绝路径越界、指向树外的符号链接、重复成员、特殊文件／硬链接，以及以符号链接为祖先的成员。规范化时不会解引用模型的链接到宿主文件。

`source.tar`、`entries.json` 和 `lock.json` 均独占创建，已存在即拒绝覆盖。锁包含任务、slot、初态身份和源码引用，并在任何最终评分之前写入。导出后停止 actor，不再接受其命令；不允许根据第一次分数换一个树再评分。

judge 从同一 image ID 重建本题 bug，单独备份原测试，删除其需要被候选替换的旧源码，再导入锁定快照。恢复范围包括原 F2P／P2P 文件、官方 profile 识别的测试路径，以及 `conftest.py`、`pytest.ini`、`tox.ini`、`setup.cfg`、`pyproject.toml`、`.coveragerc`。候选新建的测试／收集配置不能替换判题依据。镜像中的独立依赖环境仍来自原固定镜像，不导入 actor 对其依赖安装目录的修改。

这些恢复和快照规则在首个正式回合前固定，并在模型任务说明中披露。新建 judge 不接触其他任务的候选、测试输出或 seed。

## 主 R 与官方辅助分数

保留官方测试日志解析，不修改官方 parser。同时保存原 `get_eval_report` 给出的 `official_R`，但主 `R_code` 使用更严格的完整覆盖口径：

```text
执行完成、日志可信、无技术异常，
且所有原始 F2P 与 P2P 都有 PASSED 或 XFAIL 状态，才令 R_code = 1。
```

任一 MISSING、SKIPPED、XPASS、FAILED 或 ERROR 在可确定的完整执行下均为主 R=0。原官方实现可能不把 SKIPPED／XPASS 放入成功或失败列表；它们不能因此从本轮主 R 的必要集合中消失。回执记录 `official_R`、`required_not_passed`、总数／实际观察数／通过数，以及两个口径是否一致。本轮不是不加说明地逐位复刻官方原分数，也不是 SWE-bench Verified 分数。

| 情况 | 准入／正式结果处理 |
| --- | --- |
| 正常完整执行，但候选语法、导入、断言或测试收集失败 | 正式主 R=0；即使没有解析出单项测试，缺失项也不能被忽略 |
| 完整执行中任一必要测试缺失、SKIPPED、XPASS | 正式主 R=0；另留官方辅助分数和覆盖诊断 |
| 最终 Docker 失联、OOM、测试超时、命令不可执行、缺少完整日志标记或身份不一致 | 技术未知，R／Q 为 null，暂停后续正式派发 |
| clean／bug／gold 在固定资源和官方超时内不能满足预定状态转移 | 本来源未通过事前环境资格；这不是模型失败 |
| 镜像明确不存在、在已核对镜像初态上精确缺陷检查失败 | 保存来源证据后，允许按预锁顺序考虑下一个仓库 |
| 通用初始化失败、公共 daemon、registry 超时／限流、宿主依赖导入或身份故障 | 准入暂停，仓库保持 `admitted=null` 未决，不能作为来源排除 |

“测试超时”本身不能区分候选死循环、依赖等待和公共资源问题，因此正式回合保守留为技术未知，不据此填一个模型失败。终端中的普通短命令 timeout 则是模型可见工具反馈，后续仍按既定回合规则处理；它与最终 judge 没有得到可闭合判题结果是两种记录。

脚本的公共故障标志 `paused_common_system_fault=true` 会禁止冻结面板；在仓库顺序中遇到 `admitted` 不是 true／false 的未决项也会禁止继续跳过它来凑足二十仓库。对同一问题进行环境修复时，原故障和部分完成证据保留。

## 本轮运行入口

以下命令只做 CPU 环境准备，不加载模型。执行前应使用本轮已准备的独立 harness 虚拟环境和后台 Docker 服务。

```bash
/data0/zhuxinrui/proworksim-runtime/run-cpu.sh --write-project \
  /data1/zhuxinrui/projects/ProWorkSim/runs/software-panel-v053/harness-venv/bin/python \
  scripts/software_panel_environment_v053.py \
  --config runs/software-panel-v053/backend-config-v4.json \
  --inventory artifacts/software-panel-v053/candidate-inventory.json \
  --output artifacts/software-panel-v053/environment-admission-v4.json \
  --max-workers 8 --allow-image-pull
```

每个窗口全部回收后才进入下一窗口。已达到二十个合格仓库才满足数量条件；真正冻结还要求不存在公共故障／早位未决。每仓的十题记录、阶段尝试、日志、严格测试状态、image 和依赖身份、归档机械控制留在 `environment_root`。

实际全链控制只能在最终第一个获准仓库的第一个预锁任务已经合格后运行一次：

```bash
/data0/zhuxinrui/proworksim-runtime/run-cpu.sh --write-project \
  /data1/zhuxinrui/projects/ProWorkSim/runs/software-panel-v053/harness-venv/bin/python \
  scripts/software_panel_environment_v053.py \
  --config runs/software-panel-v053/backend-config-v4.json \
  --control-task-id '<冻结主面板第一题的 task_id>' \
  --control-root runs/software-panel-v053/first-backend-control \
  --output artifacts/software-panel-v053/first-backend-control.json
```

该控制不调用模型：检查普通后台 sleep 与自行 `setsid` 的后台 sleep 都被回收、可信 actor／init 仍能执行下一条命令，然后对未改动的 bug 工作树做一次唯一导出和独立 judge，预期严格 R=0。只有 `passed=true` 才能把后端完整链计为通过。任何失败先保存失败回执并以非零状态退出，不能据此启动正式模型；修订尝试必须另立身份并保留原记录。

测试运行秒数保存在各执行回执，仓库准备及归档控制另记录实际 wall seconds。它们不是 GPU 时间或模型 token 计费。CPU 后端控制的模型调用和生成 token 均明确为零。此文目前没有把上述计划性的实际 Docker 控制写成已通过。
