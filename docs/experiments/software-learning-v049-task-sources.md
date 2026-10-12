# v049 新窗口来源绑定与开发合同 CPU 见证

本文件仅报告任务来源和程序合同准备，不报告策略采集、训练更新、开发模型结果或 Contribution 值。事前冻结设计见 `software-learning-v049-design.json`。新任务模块为 `src/proworksim/software_organization_tasks_v049.py`，资产位于 `examples/software-organization-v049/`。

## 用途和来源

新窗口 `v049-o1-learning-window-01` 只将新采集的 LA/LB 经历标记为 `policy_training`。模块完整复用 v045 的 LA/LB 文件、根合同、初始绑定、公开与私有验收、初始公共诊断实现。原 v045 模块、来源清单、资格标记、历史轨迹及结果未修改；历史轨迹没有因此获得训练资格。v049 的用途覆盖附有窗口 ID 和 `new_v049_window_records_only` 范围，原业务身份仍可回查。

开发 DA/DB 是两个新编写的人工业务家族，分别为整数分币分配和依赖图批次规划。它们不由 LA 事件时间或 LB 规则解释器的业务代码、合同和 fixture 派生，`derived_from_training_asset_ids=[]`。开发来源表记录外部仓库数为 0；这些不是外部基准、上游缺陷或独立确认材料。它们共享通用 API driver、Python 隔离沙箱、严格 JSON 比较和组织世界接口；这里的来源隔离不声称独立软件执行栈。参考解及私有验收留在控制端，成员只获得公共初态。

## 事前固定合同

| Root | 固定接口与输入范围 | 业务语义 |
|---|---|---|
| DA / `sc-credit-apportionment-da-v049` | `allocation.allocate(total_cents, accounts)`；总额严格 int，±1e9；accounts 1..16，每项精确字段 id/weight；ID 为 `[a-z][a-z0-9_]{0,15}` 且唯一，weight 严格 int 1..1e6 | 在绝对总额上求整数商与余数，剩余分币按余数降序、ID 升序分配，再恢复总额符号；返回按 ID 排序，精确守恒。所有非法输入为 `ValueError("allocation:invalid")`。 |
| DB / `sc-dependency-batches-db-v049` | `planning.plan_jobs(jobs, max_parallel)`；jobs 1..12，字段精确为 id/needs；ID 同上且唯一；needs 为唯一且已知的 ID 列表；capacity 严格 int 1..8 | 全量验证含环和未知依赖；每轮从仅由前轮解锁的 ready 集合选字典序最小、至多 capacity 个。当前轮新解锁的 job 必须等下一轮。所有非法输入为 `ValueError("plan:invalid")`。 |

两合同均要求成功和失败都不改输入，排除 bool 作为整数，只用标准库。只允许修改一个生产文件及可选 `test_member.py`。正式交付必须为当前同树公开测试过的固定版本；职责分工、消息数量和多人编辑不属于验收条件。world 可直接给两名平等稳定成员共同根目标和空任务表。

两任务各有 6 条公开和 12 条同合同私有检查。输入和期望结果表在运行参考程序前分别编写，并非从参考程序输出生成。清单在程序见证前已冻结：`19704f32bee402a9d04f3ced4787da9d9a9f891e227f539dca5ed77441359c59`。父提交 `4910f616f74ac7242c18339043b612d37d7d093d` 只标识编写上下文，不冒称其中已存在新任务文件。

## 一次有限 CPU 控制结果

命令为 `PROWORKSIM_V049_TASK_CONTROL_ROOT=artifacts/software-learning-v049/task-controls .venv/bin/python -m pytest -q tests/test_software_organization_tasks_v049.py`。12 项检查通过；新模块与测试文件 Ruff 通过。

两 root 并行各执行一次初始公开检查、一套参考解公开/私有验收、两个语义反例各自公开/私有验收和两组初始公共诊断，共 18 次程序执行：公开 driver 8 次、私有 driver 6 次、初始诊断 driver 4 次，合计 132 个 API 请求/观察。两个参考解通过全部公开与私有合同；两个初始程序均保留公开原有 API 检查但未完成新合同。DA 的输入顺序优先并列分配、忽略退款符号两反例被拒绝；DB 的同轮提前解锁、ready 逆序两反例被拒绝。每个初始诊断组均保留真实通过与失败观测，属于环境准备，不扣团队成员测试次数，不是模型自主发现或成员工作。

沙箱累计用时为 2.0706829307600856 秒；两 root 并发，该和不是总墙钟时间。新增模型、tokenizer、GPU 调用均为 0。没有进行新容量资格或旧业务复验。规格和期望值未因执行结果修改。

完整 CPU 回执在 `artifacts/software-learning-v049/task-controls/`；跟踪汇总见 `software-learning-v049-task-sources.json`。资产构建脚本首次存在一个括号语法错误，发生在任何新文件生成和任何程序执行之前，修正后才生成并冻结资产；不构成先看结果改规格。

这些控制确认有界合同可执行、参考解满足已枚举义务、指定反例被拒绝和公共/私有材料隔离。它们不证明验收穷尽了所有输入，也不证明新策略学习收益。

## 模型前资格字段一致性修订

模型调用仍为0时，将新窗口 `contribution_eligible` 的唯一含义明确为“可作为训练组成支持来源”，不是已经具有 Contribution 标签或正值。新 LA/LB overlay 顶层、source_contract 和新 assessment overlay 均为 true；新 DA/DB 顶层、source_contract 和新来源清单均为 false，同时 `development_eligible=true` 保留更新后效用面板用途。旧 v045 元数据全部不变。

该新元数据修订使新清单 SHA 从 `19704f32bee402a9d04f3ced4787da9d9a9f891e227f539dca5ed77441359c59` 更新为 `e979a05ccc59dc052d2135f7739f21be97108d012c575c6144c1f2b24673d1c2`。旧完整清单和回执保存在 `artifacts/software-learning-v049/eligibility-metadata-consistency/`。所有新业务资产逐一核对仍同 SHA，没有改变任何合同、初始/参考程序、公开/私有fixture或driver。新增1项无SDK来源一致性控制通过，Ruff通过，没有重复程序业务验收、SDK路线或跨进程准备；此前CPU case/hash按其当时版本保留，不冒称最终源码与case全同字节。
