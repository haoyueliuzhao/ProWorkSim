# 九组实验的条件与接口事实核对 r1

记录日期：2026-10-23。本文只核对已有配置、冻结副本、接口源代码和少量实际回合配置；没有调用模型、执行测试或重新评分。它为九组结果汇总提供条件说明，不用配置差异直接推断分数差异的原因，也不替代逐题结果与异常审计。

## 范围与身份

九组均来自 SWE-bench Verified 官方 test 的同一完整 500 题计划，数据版本为 `78f471bf655a3137b2e8a75af1501690ec009ec3`。每组一个实际 Agent，不挂项目训练适配器、不训练。三种条件均以 OpenHands SDK 为基础：REF 与 MATCH 使用同一原生工具与模板；PROJECT 在同一 SDK 上接入 ProWorkSim 实际受管 S1 接口、观察组织和协作规则。差别位于工具与项目执行层，不是更换基础 Agent 框架。

- Qwen：`Qwen/Qwen3.5-9B` 原始权重，版本 `c202236235762e1c871ad0ccb60c8ee5ba337b9a`。模型清单 SHA-256 为 `030031b27513e399360f26a8db31746e719bb15a3d2f4d68874c1dba3ccc60a6`。
- DeepSeek：API 名 `deepseek-flash`，冻结条件记录的文档版本为 `DeepSeek-V4.1-Flash-1017`。条件明确记录该别名**不是不可变权重哈希**；不能把它写成本地固定权重实验。
- 每题预算均为输入加输出最多 500,000 token、最多 128 次模型 attempt、最多 128 次 Agent decision、软边界 5,400 秒和硬边界 6,000 秒。原生 condenser 的调用也计入同一模型调用与 token 账本，不是额外免费 Agent。
- Actor 资源配置为合计 4 CPU、16 GiB 内存、16,384 PID。实际硬约束证据应引用运行及资源验收记录，不能仅从配置文件宣称每个历史回合都已完成同一种硬约束实测。
- 环境准备和官方评分不属于上述生成 token 预算。任务排队、模型请求排队和 CPU 测试的时间可消耗回合期限；同一调用数不等于同样多的文件操作或测试。

## 推理条件

### Qwen 三组

| 条件 | 接口 / 数值后端 | 总上下文 / 单次输出上限 | 思考模式 | 采样 | 单次请求时间配置 |
|---|---|---:|---|---|---|
| REF | 原生 OpenHands；vLLM 0.32.0 | 131,072 / 32,768；完整输入最多 98,304 | 开启 | temperature 0.6、top_p 0.95、top_k 20、min_p 0、presence_penalty 0、repetition_penalty 1 | 生成 1,800 秒、宿主传输 1,860 秒 |
| MATCH | 同一原生 OpenHands；CalibrationActor，BF16 骨干 / FP32 输出头 | 18,432 / 2,048 | 关闭，不保留思考 | temperature 0.7、top_p 1、top_k 0、repetition_penalty 1 | 600 秒 |
| PROJECT | 实际受管 S1；与 MATCH 相同的 CalibrationActor 配置 | 18,432 / 2,048 | 关闭，不保留思考 | 与 MATCH 相同 | 600 秒 |

Qwen 使用事前登记的逐槽 seed；MATCH / PROJECT 的 EOS 为 `[248044, 248046]`，pad 为 `248044`。REF 声明自动请求重试为 0。MATCH / PROJECT 的 600 秒包含原有生成迭代停止设置，但原代码明确不宣称单个底层算子能在该时点被硬抢占；回合另有宿主边界。

因此 REF 与 MATCH 的**已知配置差别**同时包含上下文、输出、思考、采样、单次请求时间和数值后端。二者差值不能仅按名称解释成单一 token 预算效应。这里没有判断哪一项造成了实际成绩变化。

主要证据：`config/v054-condition-{REF,MATCH,PROJECT}.json`；`src/proworksim/software_calibration_collector_v051.py::validate_execution_contract`；`src/proworksim/software_benchmark_native_v054.py`。已对 `artifacts/software-benchmark-v054/runner/revisions/*/config/` 的小型冻结副本核对：各 arm 的上述 inference、numerical_provider 和 episode_limits 只有一种值；宿主、驻留、调度字段仍有修订。

### DeepSeek 六组

| 条件 | 接口 | 总上下文 / 输入预约上限 / 输出上限 | API 思考设置 | temperature | 请求时间配置 |
|---|---|---:|---|---|---:|
| REF-nonthinking | 原生 OpenHands | 131,072 / 98,304 / 32,768 | `thinking.type=disabled` | 0.6 | 1,800 秒 |
| REF-thinking | 原生 OpenHands | 131,072 / 98,304 / 32,768 | `enabled`，`reasoning_effort=high` | 不发送 | 1,800 秒 |
| MATCH-nonthinking | 原生 OpenHands | 18,432 / 16,384 / 2,048 | `disabled` | 0.7 | 600 秒 |
| MATCH-thinking | 原生 OpenHands | 18,432 / 16,384 / 2,048 | `enabled`，`reasoning_effort=high` | 不发送 | 600 秒 |
| PROJECT-nonthinking | 实际受管 S1 | 18,432 / 16,384 / 2,048 | `disabled` | 0.7 | 600 秒 |
| PROJECT-thinking | 实际受管 S1 | 18,432 / 16,384 / 2,048 | `enabled`，`reasoning_effort=high` | 不发送 | 600 秒 |

六组均为 `stream=false`，不发送 top_p；top_k 和 seed 因接口不支持而不发送。槽记录中的 seed 只保留历史任务身份，不能宣称它控制了 DeepSeek 的生成随机性。思考输出占用同一个 `max_tokens`：MATCH / PROJECT 的 2,048 不是在思考结束后另给 2,048 个答案 token。

本地上下文计数使用冻结的 DeepSeek 官方 recipe / encoding 加工程预约余量；结算以实际 API usage 为准。实际 thinking 历史保留原始 provider `reasoning_content`。后续 financial r4 的保守金额预约不是扩大上下文或输出许可，不能把其金融风险上界写入本表当作模型实际资源配置。

模型请求由可信控制器直连 `api.deepseek.com:443`，清除代理变量，不经反向代理。Actor 为隔离网络命名空间、仅 loopback；六组均无 web_search 工具和 Actor 外网连接。原生 terminal 的存在不代表其可访问互联网。

主要证据：`config/v055-condition-*.json`；`src/proworksim/software_benchmark_deepseek_interfaces_v055.py::{DeepSeekAdapter.request,DeepSeekAdapter.complete}`；`tools/run_deepseek_controller_v055.py`；`src/proworksim/software_benchmark_budget_runtime_v055_r4.py`；`src/proworksim/software_benchmark_deepseek_managed_v055.py`。

## 原生与 PROJECT 的操作能力

| 方面 | REF / MATCH 原生接口 | PROJECT 当前实际接口 |
|---|---|---|
| SDK、Agent | OpenHands SDK / tools 1.49.6，commit `fcc102a697874d54a357e36004e02c95040dbdc0`；一个 Agent | 同 SDK 的实际 S1 受管接入；唯一 `member_001`，无隐藏伙伴或出生 |
| 工具与提示 | TerminalTool、FileEditorTool、TaskTrackerTool，内置 FinishTool / ThinkTool；原官方默认模板，`cli_mode=false` | 项目工具 schema、项目观察、项目说明和私有结束控制；不提供绕过受管规则的 bash |
| 浏览与定位 | 持久 bash session，可用 shell / 仓库内已有程序组合浏览、跨文件搜索、筛选 | `list_files` 每页最多 40 条，导航同时受 4,096 字符界限；`read_file` 每页最多 4,096 字符 / 180 行；`search_file` 是**单个 UTF-8 文件内的字面匹配**，每页最多 20 项 |
| 分页 | 原生 terminal 明确允许大输出被截断；模型可另存结果、改变命令或再次读取。不能称其反馈永不截断 | 返回真实 continuation cursor；游标绑定操作和源版本，编辑后旧游标失效；`read_task` 分页暴露原问题全文，`diff_workspace` 分页暴露实际累计修改 |
| 文件操作 | 编辑器及 shell 可组合多文件修改、创建、删除、移动等仓库操作 | 已支持 `write_file`、唯一匹配 `replace_file`、`create_file`、`delete_file`、`rename_file`；每次编辑产生新版本。创建父目录隐式进行，改名可跨目录且保留字节与元数据 |
| 二进制与元数据 | shell 可操作允许工作区中的二进制及权限 | 完整快照保存二进制、符号链接与可执行位；文本读写仅适用于 UTF-8 普通文件。删除 / 改名可处理已有文件或链接；没有任意 binary-write、chmod 或 symlink-create 工具。保存不丢失不等于模型拥有所有编辑能力 |
| 运行与测试 | terminal 可选择公开测试子集、运行最小复现和仓库内合法脚本；允许一个 shell 命令组合多项操作 | `run_tests` 只能执行事前配置的仓库公开测试入口，无任意命令 / 自选 argv 入口；最多 32 次，读取保存结果不重跑测试。可编辑的测试文件仍受同一文件策略，不能把“固定测试入口”写成“无法新增任何测试文件” |
| 测试反馈 | 原生 terminal 输出 / SDK 事件 | 公共测试报告不可变保存；正文每页最多 3,072 Unicode 字符，`read_test_result` 可继续读。导航目录有界但完整许可正文仍可分页取得；读取更多页面消耗实际交互机会 |
| 单次工具规则 | `tool_concurrency_limit=1` 串行执行；原生 schema 明确允许一个 shell command 使用 `&&` / `;` 组合动作 | 普通响应必须恰好一个合法工具调用；显式 wait / done 控制另有精确格式。多工具或不合法格式会消耗机会并产生可纠正反馈，不能免费重发 |
| 历史 | `LLMSummarizingCondenser(max_size=80, keep_first=4, max_tokens=None, hard_context_reset_max_retries=1)`；agent 与 condenser 共用原预算 | 原 Γ1 v048：普通格式反馈生命周期、同值静态快照去重、同输入中的精确字段引用、按完整工具轮次做容量投影；无新增原生 condenser。较旧完整轮次可能移出上下文，最新完整反馈页及受保护字段保留 |
| 结束 | 原生 finish / 原生命周期；评测侧在闭合后导出代码候选 | `staff_done` 只结束当前工作，不自动固定补丁或提交；正式交付还要求同版本公开测试、固定补丁、显式提交 |

原生配置明确关闭 browser、subagent、MCP 与插件。两种接口都不能读取评测侧参考修复、隐藏验收材料或评分反馈；PROJECT 的公开测试没有接入官方隐藏验收。PROJECT 公共测试命令超时取 1,800 秒与本回合剩余硬期限的较小值。

具体证据：

- 原生五工具实际 schema：`artifacts/software-benchmark-v054/manifests/native-interface.json`；原生构造：`src/proworksim/software_benchmark_native_v054.py`。
- PROJECT 文件与分页：`src/proworksim/software_benchmark_world_v054.py`，版本 `software-benchmark-world-v054-file-operations`。
- 单调用解析及格式反馈：`src/proworksim/harness_sdk.py` 中 `Exactly one native tool call` 和 `Return exactly one public native function call` 分支。
- 测试次数：`src/proworksim/software_collaboration_v033.py::TEAM_LIMITS/TestBudget` 经 v051 / v054 继承；精确正文页：`src/proworksim/software_organization_v042.py`。
- 历史：`src/proworksim/software_context_v048.py`；DeepSeek 投影计数接入：`src/proworksim/software_benchmark_deepseek_managed_v055.py`。
- 测试执行边界：`src/proworksim/software_benchmark_runner_v054.py` 与 `src/proworksim/software_benchmark_public_tests_v055.py`。

## 文件缺陷已修复，仍保留部署上限

当前源码默认策略为 `max_files=null`、总源码最多 1 GiB、单文件最多 256 MiB、默认只读路径 / 前缀为空。超限是整体部署拒绝，不是悄悄只暴露前若干文件；`.git` 控制材料及逃逸路径不属于允许代码树。不能继续写“PROJECT 只能读取几十个文件 / 小文件、不能新增删除重命名”。

本次只读抽核了最早正式 PROJECT 槽 2 的实际公共源清单，其值与上述默认策略一致：

`runs/software-benchmark-v054/formal-queue-r1/slots/2/preclaim-1/episode/public-source/source-manifest.json`

该例为 `matplotlib__matplotlib-25479`；公开测试入口是事前登记的仓库默认 `python -m pytest`，不依据参考答案选择文件。上述一个实际槽用于确认默认策略确实进入过正式运行，不表示逐题穷举复核所有源策略或每一种文件操作都已在模型轨迹中发生。

证据：`src/proworksim/repository_sources_v054.py::{DEFAULT_POLICY,snapshot_repository,validate_tree}`；同槽 `config.json` 的 `public_test_entry`；同槽 `episode/controller-config.json` 的实际源绑定。该正式槽旧条件 SHA 为 `9b6cd4d58b690405d7102bea21c0ebe3cbf2843544b0da6612d66420dae7f640`，与 `artifacts/software-benchmark-v054/runner/revisions/r5/config/v054-condition-PROJECT.json` 对应，不能误把当前同名路径的后续调度修订字节当作当时原件。

## 代码端点与交付端点

三组的统一代码端点是预先规定的闭合边界之后、写入者可信静止时锁定的唯一完整最终工作树，再转换为官方预测补丁评分。评分不反馈模型，不在看过分数后选择另一候选。它并不要求 PROJECT 已完成正式提交。

PROJECT 的额外交付端点是最后一个合法固定提交。原规则要求当前版本真实运行过公开测试、固定当前补丁，并显式 `submit_integration`；公开测试**不需要全部通过**才能提交，提交本身也不等于官方通过。建议路径为 `run_tests → fix_patch(task_ids=[]) → submit_integration`。无任务表项时仍可直接工作，不需要为了提交伪造人工合同。

最后工作树与最后合法提交可能不同。因此应同时记录两者版本身份与“最终候选是否具备该版本合法交付证据”；不能直接把代码分数减交付分数一概当作流程损失。REF / MATCH 的交付列为不适用，不填 0。无法取得可信最终候选或官方评分未完成时应保持技术未知。

证据：各 condition 的 `final_candidate` / `candidate` / `delivery_endpoint`；`src/proworksim/software_calibration_world_v051.py::case_spec`；`src/proworksim/software_collaboration_v027.py::_action_submit_integration`；`src/proworksim/software_benchmark_world_v054.py::member_instruction`。

## 运行修订与结果解读的边界

Qwen 原队列实际记录 `mixed_runtime_revisions=true`、`cross_revision_full_panel_estimate_allowed=false`。虽然冻结条件副本的推理数值相同，驻留、交错调度、kernel 和监督器曾分阶段修订；汇总应保留逐槽实际版本，不能把 1,500 条写成从首题至末题同一个执行程序的完整冻结样本。

DeepSeek 原生执行也存在独立 revision：r2 修复原生 condenser 未完成尾轮的计数路径，r3 保留 SDK 原有 assistant reasoning 字段；financial r4 为三个 arm 绑定新金额预约 client，同时保留既有 PROJECT controller 和原生 r3 controller。这些修订不应被描述成新增模型组，也不应抹去之前异常；逐槽 `generation.runtime_revision` / job / activation 是实际执行身份依据。

配置核对只能确认“哪些条件不同”。若报告要说哪项是主要原因，需要另接逐题配对、实际终止原因、工具轨迹、用量和未知分布；仅凭上述条件表不能对分页、思考长度、交付或底座能力分配因果份额。特别是 Qwen 的 REF→MATCH 有多项同时变化，而 MATCH→PROJECT 测的是工具、说明、历史、执行和交付层的组合。

## 本次读取的当前条件指纹

下表用于定位本次条件说明；历史逐槽原件继续以其已有 SHA 和冻结副本为准。

| 文件（相对仓库根） | SHA-256 |
|---|---|
| `config/v054-condition-REF.json` | `65ca9b3993d5e4b2176b33a510d21d973c347e84f63e651ba6df78e11887586e` |
| `config/v054-condition-MATCH.json` | `f1fae06e7fa28d04133df33c8873b6b69c6fe88f9597383e8c2fd9c44ad17dff` |
| `config/v054-condition-PROJECT.json` | `d6a0dad753e71f18edf899f6327b8c3896c74a13a93984b6ac635de6fd45b68a` |
| `config/v055-condition-REF-nonthinking.json` | `1866412814053f87faf814bee446c2b5fc23757968562d2cb7f0201556268823` |
| `config/v055-condition-REF-thinking.json` | `42d0ed163674736976ce454bc84b92917a7087ea22c3c9f83845dde316017431` |
| `config/v055-condition-MATCH-nonthinking.json` | `395faac0a1c3bc33d5903d2fe7354665c34d54fb4b6073b16a84521f9e11f5cb` |
| `config/v055-condition-MATCH-thinking.json` | `a81c470dd75f8b7e380f7d487625cb2e952e756fab5f50aeeb520375052e4e53` |
| `config/v055-condition-PROJECT-nonthinking.json` | `010a8b303d3cb98f3baf00476816641267fb99f87c1735903b841b2cdaef2ac1` |
| `config/v055-condition-PROJECT-thinking.json` | `86ab183465a570cc4b0ef8e075a2954090193f4e5c3b9e1f322bfdd7a96855d8` |
