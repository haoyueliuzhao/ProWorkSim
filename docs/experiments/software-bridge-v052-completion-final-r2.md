# v052 原十二槽唯一接续合并报告

2026-10-18，用户要求恢复后，原三条未开始任务全部完成本轮执行。唯一十二槽现为 **8 条正式结果已知、4 条技术未知、0 条未启动**；已知结果中 1 条完整代码通过、7 条未完整通过。原四个中断槽没有重采或补验，完整六题主均值和条件差仍为 null。本报告不把“宿主 complete”解释为十二槽科学结果全部已知。

宿主`complete`；原12行状态`{'closed': 8, 'technical_unknown': 4}`。raw与正式结果分列，未知不填0。

## 六题等权主端点

| 端点/条件 | 已知/6 | 正式均值 | 未决界限 |
|---|---:|---:|---|
| R_code/OH_ref | 5/6 | null | [0.0, 0.16666666666666666] |
| R_code/PS1 | 3/6 | null | [0.16666666666666666, 0.6666666666666666] |
| R_code/PS1−OH_ref | 2/6 pairs | null | [0.0, 0.6666666666666666] |
| Q_task_terminal/OH_ref | 5/6 | null | [0.41432699293309555, 0.5809936595997622] |
| Q_task_terminal/PS1 | 3/6 | null | [0.48807982740021577, 0.9880798274002158] |
| Q_task_terminal/PS1−OH_ref | 2/6 pairs | null | [-0.09291383219954648, 0.5737528344671201] |

## 逐槽原始与正式端点

| 槽 | 状态 | raw R_code | 正式R_code | raw Q_terminal | 正式Q_terminal | PS1 R_joint |
|---|---|---:|---:|---:|---:|---:|
| v052-cal2-boltons-1-OH_ref | closed | 0 | 0 | 0.9951456310679612 | 0.9951456310679612 | N/A |
| v052-cal2-boltons-1-PS1 | closed | 0 | 0 | 0.9951456310679612 | 0.9951456310679612 | 0 |
| v052-cal2-boltons-2-PS1 | technical_unknown | null | null | null | null | null |
| v052-cal2-boltons-2-OH_ref | closed | 0 | 0 | 0.0 | 0.0 | N/A |
| v052-cal2-parse-1-OH_ref | closed | 0 | 0 | 0.0 | 0.0 | N/A |
| v052-cal2-parse-1-PS1 | technical_unknown | null | null | null | null | null |
| v052-cal2-parse-2-PS1 | technical_unknown | null | null | null | null | null |
| v052-cal2-parse-2-OH_ref | closed | 0 | 0 | 0.5408163265306123 | 0.5408163265306123 | N/A |
| v052-cal2-xmltodict-1-OH_ref | technical_unknown | null | null | null | null | N/A |
| v052-cal2-xmltodict-1-PS1 | closed | 0 | 0 | 0.9333333333333333 | 0.9333333333333333 | 0 |
| v052-cal2-xmltodict-2-PS1 | closed | 1 | 1 | 1.0 | 1.0 | 1 |
| v052-cal2-xmltodict-2-OH_ref | closed | 0 | 0 | 0.95 | 0.95 | N/A |

OH固定交付端点不适用；PS1 R_joint/Q_joint六题摘要及raw指标见JSON。测试未观察节点保持not-run/未知，不冒称已执行失败。

## 费用与限制

本轮账本：`{"known_actual_tokens": 2683508, "uncertain_reservation_tokens": 14512, "started_generations": 238, "complete_generations": 237, "ledger_tokens": 2698020, "new_actor_steps": 0, "new_critic_steps": 0, "new_backward_calls": 0, "complete_actual_tokens": null, "logical_inventory": 12, "stage_logical_inventories": [12, 3], "scope": "First-stage sealed scalars once plus continuation-only ledger once; overlapping inventory is not15 slots."}`。

唯一worker `18` 段，已知秒数 `3776.746076107025`，完整秒数 `3776.746076107025`；缺失时不填0。

- Six fixed development tasks from three repositories; not a new independent holdout or vendor benchmark reproduction.
- Same raw/no-adapter project numerical provider; native OH tools/history/finish differ from managed S1 Gamma and fixed submission.
- Each task is equally weighted. Any required unknown makes the full mean or paired difference null; bounds are not confidence intervals.
- R_code/Q_task_terminal compare sole terminal production trees. PS1 R_joint/Q_joint are additional fixed-delivery endpoints; OH is not applicable.
- Safe context or budget closure with all source/guard/test bindings can have known code zero. A fault, missing guard or unstarted slot is not imputed zero.
- No rescore, model retry, additional seed or reward threshold. Report construction performs no new experiment.
- This is the unique original12 inventory, not15 samples. First nine rows remain verbatim; only original three unstarted identities are replaced.
- Four interrupted outcomes remain null. Complete call billing does not prove a terminal business score or exact recovery state.
- The original14512 uncertain reservation remains uncertain; complete actual generation cost stays null after continuation.
- The original file named final.json remains the immutable first-stage report; each stage binds its own plan and supervisor.
- The failed r1 bootstrap entered no slot/model/generation; it adds no scientific row or model fee, but its three worker lifetimes add15.057310104370117 seconds once.
- First-stage nine rows and r2 replacement three remain the same12. r1 is an operational stage, not three new samples.

完整来源与紧凑guard/停止/测试/复用字段见JSON；大段原始调用和测试正文仅在原worker report保留。

首阶段九行原样保留，仅替换原三个未开始槽；四中断评分与 14512 不确定预约保留。完整实际 token 成本仍为 null，分阶段标量与来源见 JSON；未重评分或恢复中断回合。

r1 零模型启动阶段没有新增科学行或模型账单；三个 worker 区间 15.057310104370117 秒单列且仅计一次。r2 仍仅替换原三个未开始槽。

## 本次接续的具体结果

新宿主冻结为 `c3ead22`，科学源码仍逐字节复用原 `7d95912` 的 616 文件；没有改变 raw Qwen3.5-9B、数值 provider、工具、种子、初态、18,432/2,048 容量、预算或验收。只在物理 GPU0、GPU2 实际运行，驻留峰值为 2；授权上限 4 没有被解释为必须占满。

| 原未开始槽 | 完整模型调用 | 实际 token | 唯一末树测试 | 终止与交付 |
|---|---:|---:|---:|---|
| xmltodict-1 / PS1 | 43 | 484,279 | 56/60 | 成员固定模型预算执行前拒绝；未固定提交，R_joint=0 |
| xmltodict-2 / PS1 | 9 | 99,999 | 60/60 | 正常闭合，固定交付通过，R_joint=1 |
| xmltodict-2 / OH_ref | 28 | 304,011 | 57/60 | 完整 native context 执行前拒绝；固定交付端点不适用 |

本次共 82 个决定、80 次实际调用且 80 次全部完整回包，888,289 实际 token，无新增不确定预约。三槽的 actor、软件绑定、RNG 和学习状态 guard 均通过，宿主判断均为 continue，没有新全局暂停或行政删失。两次执行前拒绝与已发生的生成费用分列，不把它们当成额外模型回包，也不归为 SIGTERM 故障。

三槽的终态评价共实际执行 3 次、每次 60 个预期节点全部观察到。xmltodict-2/PS1 的固定提交树与末树及完整评价身份相同，末树端点直接复用原权威回执，新增末树执行为 0；其 1 次固定评价已在上述 3 次中，不重复计。这里描述的是宿主固定/末树验收，不是模型期间全部公开测试次数。

## 三阶段费用和修复边界

| 阶段 | 开始/完整生成 | 已知实际 token | 不确定预约 | 唯一 worker 秒数 |
|---|---:|---:|---:|---:|
| 原首阶段 | 158/157 | 1,795,219 | 14,512 | 2,683.403012275696 |
| r1 入口故障 | 0/0 | 0 | 0 | 15.057310104370117 |
| r2 原三槽 | 80/80 | 888,289 | 0 | 1,078.2857537269592 |
| 合计 | 238/237 | 2,683,508 | 14,512 | 3,776.746076107025 |

合计约 1.049096132 GPU worker 小时，是三个阶段的唯一进程区间之和；零模型启动也保留进程成本，装载、生成、测试等嵌套时长不另相加。账本扣账为 2,698,020 token；其中 14,512 是历史未完整回包的预约，不是已测实际用量，因此完整实际费用仍为 null。原余额不转移，没有参数更新、反向或自动后继。

r1 三个 worker 在原 worker 的第一项来源校验处失败，尚未进入槽、装载模型或消费科学样本。一次两实际解释器探针确认 Python 3.14 与 3.12 的 `ast.dump` 空字段表示差异。独立 r2 改为版本化规范结构表示，保留源码 SHA 约束；原 r1 源码、plan、release 与停止事实均不改写。新增跨解释器控制、最小零入口反例和限定 Ruff 通过，提交后另以正式 native Python 执行一次真实冻结入口检查；这些都没有模型、SDK 或 tokenizer 调用。[宿主方法](software-bridge-v052-resume-r2-host-method.md)和[实际入口回执](../../artifacts/software-bridge-v052/resume-r2-production-entry/summary.json)保存执行范围。

合并报告只运行一次并通过，新增报告控制仅覆盖 r2 绑定与零模型阶段成本；旧控制、旧来源资格、初态分词和旧模型槽没有重跑。上面的自动统计原稿、实际执行源码和日志保存在[报告执行目录](../../artifacts/software-bridge-v052/completion-final-r2-execution/summary.json)，机器结果见[完整 JSON](software-bridge-v052-completion-final-r2.json)。本 Markdown 的说明段在报告生成后补充，不改变机器结果。归档过程中一次启动回执路径假设错误单独保留，仅修正文件复制路径，不影响报告或实验。

## 异常信号排查结论

历史首 worker 的 SIGTERM 发送者，以及随后监督器所受 SIGTERM 的发送者，均仍未知。原首 worker 没有宿主主动停止记录，最后已有资源遥测没有触发原因；其余三个在途 worker 可绑定到监督器异常后的清理路径。现有证据不足以归因于 OOM、会话结束、用户操作或某个调度器，详见[窄只读审计](software-bridge-v052-interruption-audit.md)。

本次实际使用独立 transient user service、Restart=no，以及只跟踪监督器的 SIGTERM/SIGINT 观察。r2 监督器 trace 正常退出 0，没有记录新的这两类信号；一次终态服务读取为 inactive/dead、Result=success，原读取凭据见[service-status.json](../../artifacts/software-bridge-v052/resume-r2-terminal-observation/service-status.json)。这不反推历史原因；未使用 fork 跟踪，也不能据此宣称观察了任意 native worker 的所有信号。[观察范围说明](software-bridge-v052-resume-signal-observation.md)区分了已证事实和预防性安排。

## 整体证据适用范围

本轮先完成了旧 HOLD 全 16 条只读过程诊断，没有为旧未提交工作区补验或改旧分数。六题来自三个既有开发仓库，不是新的独立确认集；OH_ref 是明确披露的官方 1.49.6 Agent/Conversation、TerminalTool/finish 组合和有界终端后端，不是完整默认工具 preset。双方模型数值 provider 相同，工具、历史处理、结束与交付制度不同，不能把本结果解释为纯模型能力差异。

共同来源资格的 18 逻辑单元去重为 9 次实际执行、1,710 测试节点；十二逻辑初态硬容量通过。十一份原 provider 请求已保存，首 PS1 原请求 SHA 仍为 null，该一份由实际 SDK 事件与冻结源码确定性重物化，不能称原 SHA 复现；这些资格限制和失败原件见[准备完成报告](software-bridge-v052-preparation-completion.md)。初态容量通过也没有保证后续 OH 历史全部 fit，本次 OH_ref 的真实 context 拒绝予以保留。

当前只有两题的两条件正式端点都已知；表中界限是原六题分母下对未决值的确定性范围，不是置信区间。单条 PS1 成功及这两对观察不支持一般组织优势或学习收益。本窗口收口后没有自动新增样本、恢复四个中断回合或重开旧训练队列。
