# v054：共同 Docker 初态、公开源码与 Actor 边界准备

日期：2026-10-20，Asia/Shanghai。本文属于用户授权的数据／环境准备；不启动模型、GPU 或正式评测。

## 1. 已实现与尚未准入的范围

新增 `software_benchmark_actor_v054.py` 和 `tools/prepare_actor_v054.py`，实现可执行的共同镜像容器、完整公开树提取、PROJECT 来源 provider 及固定公开测试回调。三项合成 CPU 控制通过；没有用旧 v053 的受限 terminal executor 代替原生工具。

本轮没有可用于实际 Actor 检查的 Verified 本地镜像：首题层下载受到国内 registry HTTP 429 限额影响。因此真实 Actor 容器、公开源码快照、公开测试命令资格均仍为 0。这些缺口与代码已经实现是两件不同的事实。

REF／MATCH 的原生 SDK 工具和持久 PTY 已有独立构造控制，但其 **SDK 依赖文件与 Actor 可读文件系统的隔离仍未完成**。本文不会把无 SDK 挂载的环境壳称为已接通原生 Agent，也不会为了宣称准备完成，挂入整个 resident 环境。

共同部署合同保存在 `config/v054-actor-environment.json`。其中 CPU／内存／公测时间配置已明确写出，但尚未通过真实镜像执行验证；`all_three_conditions_ready=false`。

## 2. 为什么直接挂载 SDK 环境不可作为本轮实现

核对本机固定 OpenHands tools 1.49.6 的真实源码后确认：

- `FileEditor.__init__(workspace_root=...)` 用该目录提供 cwd 和相对路径建议。`validate_path` 检查绝对路径、存在性及命令适用性，没有把读取限制在 workspace 内。
- `FileEditorExecutor.allowed_edits_files` 仅限制修改，明确不限制 `view`。因此它也不是隐藏运行依赖的读取边界。
- Terminal 使用官方 `SubprocessTerminal`：以 PTY 启动持久 bash，环境来自官方 `sanitized_env`。原生 shell 可以读取同一容器内有权限访问的任何路径。
- 官方 agent-server 的 conversation container 将服务及工具放入同一个指定 image；仅改用该容器／remote server，并不会自动让 FileEditor 无权读取服务 image 中的运行依赖。

对应源码在 `runs/v016-sdk/upstream/openhands-tools/openhands/tools/file_editor/{editor,impl}.py`、`terminal/terminal/subprocess_terminal.py`，以及 `openhands-agent-server/openhands/agent_server/docker_runtime/registry.py`。这项判断来自具体执行合同，而不是把某个工具名称视为沙箱保证。

现有有效依赖清单包含 requests 2.34.2、sympy 1.13.1；它们对应本轮 Verified 中的目标仓库。若把整个 resident／REF venv 放进 Actor 可读 rootfs，会引入官方任务初态以外的源码副本。只隐藏 parquet、gold 和评分日志不足以解决这一点。

后续必须实现并核验 SDK 控制／依赖与 Actor 操作文件系统之间的真实权限或执行边界，或提供不引入相关源码副本的可验证运行时。REF 和 MATCH 使用同一解决方案，保持官方工具、说明、模板、历史及持久 PTY 的执行语义。当前没有把额外 path 拒绝规则、单次受限命令或替代文件工具偷偷加入 MATCH。

## 3. 共同容器与准入

Actor 准备入口只接收公开五字段：

`instance_id/repo/base_commit/image/problem_statement`

含 `patch/test_patch/eval_script` 等额外字段的行直接拒绝，程序不读取完整可信评分 JSON。入口还校验公开任务文件 SHA、完整 500 个唯一 ID、本题实际镜像身份及该镜像的预检证据。

共同容器按 image config ID 创建，显式 `--pull never`，检查 linux/amd64。三个条件使用相同配置：

| 项目 | 当前部署合同 |
| --- | --- |
| 初态 | 同一固定官方 image 的完整 `/testbed` |
| 网络 | `none` |
| 宿主挂载、Docker socket、SDK/resident 挂载 | 均无 |
| GPU 映射 | 无 |
| Linux capabilities | `--cap-drop ALL`，`no-new-privileges` |
| CPU／内存／进程数 | 4 CPU、16 GiB、16384 |
| cwd | `/testbed` |

Docker socket 仅由可信宿主控制器使用，不出现在 Actor 容器中。创建失败会清理自己刚创建的容器；不会删除不属于该调用的其他实例，不触碰官方评分镜像。

准入要求当前完整预检合同：baseline HEAD 匹配、工作树干净、all-ref/reflog/unreachable-commit 的未来历史计数为 0、Git connectivity 检查成功、已知 Conda 目标源码副本列表为空。旧版较窄预检、未知状态或发现额外目标副本时一律保持待处理，不自动裁剪任务集。

这是基于既定已知泄露通道的有限准入，不是一次完整文件系统取证证明。若发现额外副本，需要定向处理并验证环境仍能工作；本实现没有盲删 Conda／pip 缓存，也没有把来源不明的包当成一定可删除的冗余依赖。

PROJECT 也必须满足同一容器准入：虽然 provider 不暴露仓库外路径，模型修改的公开测试代码仍可能通过公测进程读取其容器文件系统。因此不能仅凭 provider 文件列表就宣布项目组的环境没有答案副本。

## 4. 完整公开树提取及 PROJECT provider

实际准备流程：

1. 在通过准入的同一不可变 image 创建临时容器。
2. `docker cp` 将完整 `/testbed` archive 流式写入准备目录，避免把全部 Git 历史积存在内存。
3. 逐项解码 tar，忽略根 `.git` 元数据，保留所有其他合法文件，不按扩展名、参考补丁文件或测试清单筛选。
4. 拒绝路径逃逸、特殊设备、重复条目、非法链接及无法解析的 hardlink；资源熔断拒绝整个来源，不截掉超限文件。
5. 保留 UTF-8／二进制原字节、执行权限和仓库内符号链接，交给真实 `capture_repository/RepositorySources` 形成完整树 manifest。
6. 清理临时 archive 和自己创建的容器，保留公开 checkout、source manifest、完整树身份和环境身份回执。

REF／MATCH 的工作树来源仍是同一 immutable image `/testbed`；PROJECT 的 provider 从该树提取完整公开文件。`.git` 不进入受管文件对象；这是既有受管接口的边界，不是假称三个条件具有相同 Git 操作能力。

命令入口示例：

```bash
PYTHONPATH=src .venv/bin/python -B tools/prepare_actor_v054.py \
  --public-tasks /absolute/source/public-tasks.json \
  --public-tasks-sha256 <已冻结公开投影SHA> \
  --image-inventory /absolute/images/image-inventory.json \
  --preflight /absolute/images/preflight/<instance_id>.json \
  --instance-id <固定500题中的ID> \
  --docker-socket unix:///absolute/private/docker.sock \
  --output /absolute/new-actor-source-directory
```

该入口只在实际 image 与预检满足条件时提取，没有创建绕过准入的自动 fallback。当前尚未对真实题执行此命令。

## 5. PROJECT 公开测试接缝

`project_provider(...)` 将真实新 provider 与公开测试回调连接。测试入口必须来自模型成绩出现前的公开仓库检查，显式记录 argv、cwd、解释器、完整 source-manifest SHA；必须独立标记已准入。不得使用隐藏 eval script、F2P/P2P 或 `test_patch` 构造该入口。

本轮没有凭通用经验给 12 个仓库伪造“已验证可运行”的入口表。比如某些 Django 仓库使用自身 runtests，不能因为多数仓库支持 pytest 就给全部 500 题填一个已经通过的 `python -m pytest` 资格。真实入口资格仍为 0，待镜像和公开 checkout 可用后形成。

每次公开测试从独立共同 image 初态创建容器，保留安全的 `.git`，删除原公开工作树，再注入当前受管版本的**完整**文件集合。新增、删除、配置文件、二进制、执行权限和链接均进入测试初态，不仅传递若干 `.py` 文件。随后执行固定公开 argv；没有任意 bash 作为 PROJECT 的模型工具。

结果绑定当前完整树 SHA、公开入口 SHA 和实际执行状态。stdout/stderr 存入每次唯一目录，并作为完整反馈进入现有分页层。超时保留实际已执行事实、部分输出及 `technical_unknown`，不填成正常已知测试失败；容器始终清理。公开测试成功与否不替代官方终评。

## 6. 必要 CPU 控制

`tests/test_software_benchmark_actor_v054.py` 本轮一次运行：**3 passed，0.08 秒**；对应新模块、CLI 和测试 Ruff 通过。

| 控制 | 实际覆盖 |
| --- | --- |
| 公开投影／来源边界 | 隐藏字段、未来 reflog、额外目标包副本均拒绝准入 |
| 完整 archive 解码 | 二进制、CRLF、执行权限、链接保留；根 Git 排除；外逃链接与超限拒绝 |
| 实际 provider 与公测传输 | 合成 Docker transport 驱动真实 source capture/provider；完整新增／删除进入 tar；固定公开 argv；无宿主挂载、GPU、pull 或隐藏评分调用 |

第三项使用合成 Docker transport，没有真实启动容器，也没有执行 Verified 测试。它验证新接缝的数据和参数行为，不能替代之后的实际容器控制。先前的 17 项文件修复、真实 SDK 构造、500 个 TestSpec 与其他旧实验均未重复运行。

补充 manifest-digest 和公开解释器绝对路径检查后，仅重跑受影响的准入控制，1 passed（0.08 秒）。三个不同控制的数量不因此增加。源码、配置及官方边界源码的身份回执见 `artifacts/software-benchmark-v054/actor/preparation-receipt.json`。
