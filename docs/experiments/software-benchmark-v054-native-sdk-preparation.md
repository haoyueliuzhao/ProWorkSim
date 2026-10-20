# v0.5.4：REF/MATCH 原生 OpenHands 接口准备

日期：2026-10-20（Asia/Shanghai）。本项为数据与环境准备中的合成 CPU 构造控制，不是模型评测。

## 已完成的接口合同

`src/proworksim/software_benchmark_native_v054.py` 为 REF 和 MATCH 提供同一个原生接口工厂。两个条件只有调用者传入的 LLM 推理配置不同；工厂不接受 arm 参数，也不根据条件改变工具、说明、模板或历史组织。

| 项目 | 冻结值 |
| --- | --- |
| SDK、tools | OpenHands 1.49.6 |
| tools checkout | `fcc102a697874d54a357e36004e02c95040dbdc0` |
| 操作工具 | 官方 `TerminalTool/FileEditorTool/TaskTrackerTool` |
| 内置工具 | 官方 `FinishTool/ThinkTool` |
| 实际 schema 名 | `terminal/file_editor/task_tracker/finish/think` |
| Terminal | 官方 `SubprocessTerminal`，`terminal_type=subprocess`，`shell_path=/bin/bash` |
| 系统模板 | 未修改的官方 default preset；`cli_mode=false` |
| 工具说明 | 官方实际 schema；包含其默认 `summary/security_risk` 字段 |
| 工具并发上限 | 1，两个条件相同 |
| condenser | 官方 `LLMSummarizingCondenser`，`max_size=80`、`keep_first=4`、`max_tokens=null`、`hard_context_reset_max_retries=1` |
| condenser LLM | 同条件 LLM 的配置副本，单独 `usage_id=condenser` |
| Agent context | `null`；禁止个人 `SOUL.md` |
| browser、subagent、MCP、plugin | 不启用 |
| 项目受管工具、单调用 XML hint | 不注入原生接口 |
| 单次 conversation 迭代上限 | 128 |

这与 v053 的受限容器 terminal executor 不同。新工厂直接使用官方工具 executor 和官方持久 PTY；没有用项目工具或缩减 terminal 语义来“匹配”MATCH。没有将这一原生 bash 能力加给 PROJECT。

## 新发现的服务器适配及处理

第一次实际构造 `r1` 在官方 `pty.openpty()` 处失败，错误为 `out of pty devices`。原因是已有 CPU 私有 Python runtime 的 `/dev` 不包含 `/dev/pts` 和 `/dev/ptmx`；不是模型、工具 schema 或任务失败。

新增 `tools/run_native_cpu_v054.sh` 在独立用户／挂载 namespace 内：

1. 将该 namespace 内的 sysroot `/dev` 覆盖为私有 tmpfs。
2. 创建私有 `devpts` 和标准 `/dev/ptmx`、`fd/stdin/stdout/stderr` 链接。
3. 复用已有 `enter-namespace.sh` 的 CPU 挂载与清空环境规则，只传入空 GPU 参数。
4. 退出后销毁 namespace 和临时目录。

没有修改共享 runtime 文件或宿主 `/dev`，没有绑定 GPU，入口没有 GPU 选项。该入口用于可信准备进程；它本身不等于正式 Actor 的 Docker 安全边界。正式 task workspace、挂载、网络和隐藏资料隔离仍须使用单独冻结的执行环境。

## 依赖准备

复用已有 Python 3.12.3 和 SDK 1.49.6。所选官方原生工具缺少三个小依赖，本次按现有 tools `uv.lock` 的版本和 wheel SHA，从清华镜像直连安装到独立目录 `runs/software-benchmark-v054/native-sdk-overlay/`：

| 包 | 版本 | wheel bytes |
| --- | --- | ---: |
| binaryornot | 0.4.4 | 9,006 |
| chardet | 5.2.0 | 199,385 |
| libtmux | 0.53.0 | 77,582 |

合计 wheel payload 为 285,973 bytes，不包括小量索引元数据。安装使用 `--require-hashes --only-binary=:all: --no-deps` 和显式国内 index，所有代理变量置空；没有改变 resident 环境。锁文件为 `config/v054-native-sdk-overlay-requirements.txt`，SHA256 `fa9e904b7db83e657a0009d90ecf94be3dc4ece10ba891f83c0535402c4fd0ab`。未安装浏览器依赖，因为本方案不启用浏览器工具。

进程环境明确设置 `LITELLM_LOCAL_MODEL_COST_MAP=True`；由于已有 CPU runtime 使用 `env -i`，该变量和 `PYTHONPATH` 必须在 runtime 内通过 `/usr/bin/env` 设置。

## 实际 CPU 控制结果

`tools/check_native_sdk_v054.py` 的 `r2` 控制于 **2026-10-20 22:20:44–22:20:51（UTC+8）**通过：

- 分别构造真实 SDK `Agent` 和 `LocalConversation`，各注册全部五个官方工具。
- 使用同一合成目录和相同合成消息，分别初始化 REF/MATCH 的原生工具及系统提示；不使用真实题。
- REF 控制构造器传入 `max_input_tokens=131072/max_output_tokens=32768/temperature=0.6`；MATCH 传入 `18432/2048/0.7`。这些值用于确认改变 LLM 配置不改变接口，不构成实际模型数值或上下文准入验证。
- 两者实际工具 schema、工具说明、静态系统提示、condenser 配置及 executor 类型完整相等。
- Terminal 实际类型均为官方 `SubprocessTerminal`，不是替代 executor；官方初始化 shell 已启动并在 conversation 关闭时清理。
- 合成工作区内容保持不变。

测试用 LLM 是 SDK LLM 的禁止调用子类，仅覆写 completion 入口为立即失败并计数；没有伪造模型响应。控制没有调用 `Conversation.run()`。Python audit hook 阻止网络连接、DNS、GPU 文件和模型权重访问。最终 `model_calls/network_attempts/weight_files_opened/gpu_device_opens/task_tool_calls/official_grader_calls` 全部为 0。

| 证据 | SHA256 |
| --- | --- |
| 相同接口的规范内容哈希 | `77636cdc1dfc83e185442897170d88e98d9c565df4f8e39f115134122c7b5d00` |
| `artifacts/software-benchmark-v054/manifests/native-interface.json` 文件 | `000c7b4a8bdcff7c2b5799b3c9f50b46134537e3c7aa099f1e802d5dbc10088b` |
| `software-benchmark-v054-native-sdk-construction-r2.json` 回执 | `37ffb48a107d7f70624bf5b6a3c5186474476036f67c931dcd346076aa0004ce` |
| `r1` 失败回执 | `426608e928925dec20c274897b2cb92ed780a2a6ed4ae5ddfca9e2c6fcb097df` |

两个哈希域分别是紧凑规范 JSON 的接口内容、带缩进 JSON 的完整文件，不能混用。接口清单包含实际完整提示与五个工具 schema，可直接审阅。回执另保留实际源码文件 SHA、解释器路径、依赖版本和运行时间。

`r1` 和 `r2` 均保留；只在修复缺少 PTY 的明确运行故障后重新执行受影响控制，没有重复 v054 先前的受管 SDK 构造测试、17 项文件修复控制或任何旧实验。新 Python 文件 Ruff 和 launcher 的 `bash -n` 检查通过。

## 仍未由这项检查证明的内容

该工厂只完成原生接口和 CPU 装配，不加载 Qwen 权重、不实现 MATCH 对 PROJECT 的数值 bridge、不连接 vLLM、不提供 Docker Actor 隔离、不实现费用／token 账本，也不调用官方评分器。condenser 的模型配置和使用标识已固定，但总预算扣账须由正式数值／调度层覆盖其调用；不能用本次零调用控制宣称实际计费已通过。

后续把这套相同接口接入 REF/MATCH 时，应重新核对最终执行环境绑定和必要的新增 seam；无需重复已完成的无关控制。1500 个槽仍未授权正式执行，不因原生接口准备完成而自动启动模型。
