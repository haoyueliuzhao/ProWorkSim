# v203.2.1 完整性、成员可见性与阶段标签 CPU 控制

本目录只记录离线 CPU 工程控制。没有被测模型请求、API 费用、Docker、GPU、服务操作或世界动作；脚本中 provider receipt 的 token 数值是明确标记为 `cpu_scripted` 的输入夹具，不能计为真实供应商 usage。没有修改冻结的 v203.2 模块。

## 实现边界

实现位于 `src/proworksim/software_observer_views_v203_2_1.py`，测试位于 `tests/test_observer_views_v203_2_1.py`。

`assess_integrity` 按请求、响应、工具回执、所有权、依赖、通信、版本、交付八类默认关键来源分别给出 `COMPLETE/PARTIAL/INVALID`。来源清单、是否闭合及闭合证据必须显式提供，不能把日志“数量较多”当成完整，也不能把语义事件未出现直接当成来源丢失。缺失完整交付回执时，已完整覆盖的早期所有权维度继续可用。PARTIAL 维度有可用来源时可保留局部正向材料，但 `absence_eligible=false`，不允许把未观测事件记作阴性。某维来源损坏使该维 INVALID；其他独立维度继续保留。如果捕获方确认 episode 身份、链或归属整体失效，应通过 `fatal_errors` 标记整体 INVALID，不能把这种错误降为单个事件缺失。

`COMPLETE` 表示声明的关键来源覆盖完整，不是依赖、组织失配或操作必要性的语义真值。覆盖闭合和跨维独立性仍由真实捕获边界提供；此模块不从缺失日志中猜测这些条件。

`AcceptedRequest.from_bytes` 要求不可变原始请求字节、实际 SHA-256、episode、actor、request、接受时间及带一致 usage 的供应商回执。decision_id 有实际来源时绑定，缺失时为 null，不拿 request_id 冒充 SDK decision_id。哈希只能检验所给字节的一致性，无法单独证明远端调用确实发生；真实部署必须由接线层提供经过归属核验的捕获记录。`real_provider` 和 `cpu_scripted` 必须显式标记，本控制仅使用后者。时间使用同一 episode 捕获时钟的非负有限数字，不能混用未归一化的时钟。

`ObserverViews.member_view(actor, at_time, request_id=None)` 返回 typed `MemberView`。默认选择截止时间前该成员最近的一次已接受请求；同时间有多个请求时要求显式 request_id，不按字典顺序猜测。实际请求没有携带的旧上下文不会自动回填。显式选择其他成员请求会拒绝，显式选择未来请求会拒绝，截止点前没有请求则输出 UNKNOWN。原请求中的 patch 发布标记不会展开完整源码，原请求中的预览也不会扩展为全文。模块只确认 PRESENTED，不自动认定理解、读取或采用。

`ObserverViews.global_view(at_time)` 返回另一种 typed `GlobalView`，允许保存评测侧私有/全局材料，但明确 `policy_input_allowed=false`；未来全局事件不会进入当前快照。两种视图没有自动转换接口。输入事件的 `occurred_at` 及事件内容时效仍需由上游真实来源证明，模块不能识别一个被上游错误标记为早期的未来事实。

`make_evidence` 生成请求内 JSON pointer、原请求哈希、值哈希、actor、request、decision 和时间绑定，或显式 GLOBAL_EVALUATOR 事件引用。成员证据必须来自实际 messages/tools；全局事件不能作为成员证据。返回 JSON 的修改不改变捕获原件。

`validate_stage_assessment` 将判断绑定到 episode、task、task revision、T0–T6、时间和来源视图。成员判断还绑定 actor、原请求、decision、原字节哈希和捕获模式。不同阶段/版本保存为独立记录，不是任务级永久标签。缺失的 dependency/misalignment 默认 UNKNOWN，组织决策默认 ABSTAIN；NO_CHANGE 与 ABSTAIN 分开，UNKNOWN 不进入阴性统计。成员判断与全局评测判断具有不同 scope，不能混用。

操作记录保留六个独立层次，任何非 UNKNOWN 项均需来源引用：

| 层次 | 可取值 |
| --- | --- |
| exposure | EXPOSED / NOT_EXPOSED / UNKNOWN |
| preconditions | MET / UNMET / UNKNOWN |
| authorization | ALLOWED / DENIED / UNKNOWN |
| necessity | NECESSARY / UNNECESSARY / UNKNOWN |
| decision | CALLED / NOT_CALLED / UNKNOWN |
| outcome | IMPROVED / UNCHANGED / WORSENED / UNKNOWN |

necessity 额外要求明确 `scoped_work_requirement`、`independent_execution_witness` 或 `human_review` 依据，拒绝 `tool_call_count` 等次数依据。拥有前置条件、权限或调用记录都不会自动填入必要性、失配或收益。此 schema 检验引用与结构，无法独立验证解释是否正确，也不声称完成因果验证，因此每条规范记录均保留 `semantic_truth_not_verified=true`。CALLED 表示工具决策事实，与组织判断 INTERVENE 分开。

## 必要核验与产物

运行 `.venv/bin/python -m pytest -q tests/test_observer_views_v203_2_1.py --junitxml=artifacts/software-benchmark-v203-2-1/view-controls-r1/pytest-junit.xml`，结果 25 项通过（0.37 秒）。覆盖成员权限、未来请求、未知来源、发布不补全文、全局视图隔离、请求哈希与供应商回执结构、重复身份冲突、局部保留、分维度损坏、动态标签与六层 schema，另含 6 项完整后处理路径的合成 CPU 控制。

运行 `.venv/bin/python artifacts/software-benchmark-v203-2-1/view-controls-r1/generate_evidence.py` 重建本目录示例与摘要。原请求夹具分别保留为字节文件，`examples.json` 保存完整性报告、成员和全局快照及阶段判断，`summary.json` 记录源码/测试/夹具哈希及 JUnit 结果。示例均为构造控制，不是12题 Pilot、独立标签参考或自然失配发生率。

本控制不能证明真实模型边界已接线、跨进程持久化可靠、自然任务依赖识别正确、组织调整有益或完整生产环境的观测开销可接受。相关准入必须由对应实测材料独立完成。

## 已完成任务的只读后处理入口

`tools/analyze_passive_capture_v203_2_1.py` 暴露 `analyze_capture(controller, episode, host=None)`，任务总体状态为返回值 `report['integrity']['status']`。CLI 接受 `--controller DIR --episode ID [--host EPISODE_DIR] [--output NEW_JSON]`；不提供 output 时打印 JSON，提供时只新建指定结果文件，不覆盖已有文件。输入 SQLite 使用只读连接和 query_only，读取已提交快照，检查行哈希和连续哈希链；不实例化会创建或修改数据库结构的 ObserverJournal。

独立主来源是 `model-ledger/ledger.json`、逐请求/响应的引用原件、`managed-boundary.json` 或 `controller-result.json` 内的 managed_boundary。工具/机会分母来自完整主 outcomes，并优先使用 `managed-runtime/experience.jsonl` 的 policy_decision 与实际 tool_call/harness_tool_call 精确绑定。原 SDK 的 staff_done/staff_wait 终态 outcome 不含完整 decision/response，因此不能只用 outcome 数量；缺少独立运行轨迹时，对无法穷尽归属的额外回执保持 PARTIAL。

旁路来源为 `model-ledger/passive-observer/events.sqlite`。物理来源为传入单个 episode host 目录内的 `physical-observer/events.sqlite`；若不在根位置，只接受该 episode 子目录中的唯一候选，不搜索其他 episode。物理记录需具有 HTTP_REQUEST/HTTP_RESPONSE、原字节 base64、哈希、长度、时间及 physical_id/logical_id/slot_id/member_id；只把唯一成功配对且与主 ledger、sidecar 完全吻合的实际原字节构造成 AcceptedRequest。缺物理原字节时，不把重新序列化的 sidecar wire 冒称真实物理原文；请求维度保持 PARTIAL，成员请求视图不伪造。

实际 SDK decision_id 通过独立 runtime trace 的 model_response/service_completion_id 与完整原响应对应，既不使用请求编号代替，也不按工具调用次数生成。agent 请求缺少这一关联时，请求完整性维度保持 PARTIAL；字节已证实的输入仍可保存，但 decision_link_status 为 UNKNOWN。原 r1 日志缺少 source.capture_time 时，lifecycle 保持 PARTIAL、对应阶段成员视图不生成，不使用文件 mtime 或物理响应时间补造原事件时间。

后处理增加 lifecycle 完整性维度，用主机会、初态、边界与 capture-closed 对账。各专业维度只依赖相关动作来源；缺最终交付回执不会使完整早期 ownership 维度降为无效。全任务身份错误使任务 INVALID，物理字节损坏可使 requests INVALID 而保留独立 ownership 证据。

阶段只用旧 PassiveState 对 INITIAL/INTENT/RECEIPT 做数据投影，不执行 Harness。INITIAL 显式适配原 issue/organization/members，OPPORTUNITY 的 actor 可取 worker_id。T6 保留提交意图之前状态，不提前加入后续回执；未出现阶段保留未观测，只有来源完整时才允许报告操作化阶段未出现。版本、任务 owner、测试结果与 change_type 只作为客观状态变化，不推断组织调整必要性。

阶段任务列表属于全局评测信息，因此生成的 task/revision 阶段标签明确为 GLOBAL_EVALUATOR 且默认为 UNKNOWN/ABSTAIN，不把全局任务 identity 自动写入成员判断。成员 phase 只关联实际已接受请求，重复使用的请求按 request_id 保存一次。CPU 控制还检查了分析前后输入主文件与数据库内容哈希不变。
