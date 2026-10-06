# v0.36 来源与局部面板扩展：CPU 资格记录

本修订保留训练根目标 `sp-script-inventory-v035`，并在原两个 schema 贡献根目标和两个 TextFSM 独立确认根目标上，各新增两个不同业务根目标。本版九根目标按用途为训练1、贡献4、确认4。新增模块为 `src/proworksim/software_tasks_v036.py`，程序资格入口为 `scripts/qualify_software_sources_v036.py`。本文件仅报告来源、合同和 CPU 程序检查，不报告模型、Contribution 或独立算法效果。

原 v0.35 Mapper 输出、16条旧经历、支持计数和停止决定都没有变更。原五个根目标的 `build_case` 与 v0.35 逐项相等，包含合同、starter、公开 driver、全部初始文件及 source_contract；相应 public/assessment/reference 接口直接委托旧实现。保留根目标继续携带其原 source_manifest/source_partition SHA，新根目标携带本版扩展 SHA，外部新面板清单负责冻结二者的共同执行库存。没有将旧分配文件重写成九根目标，也没有把已暴露的旧训练经历拼入新支持。

**来源与合同的差异**

| 用途 | 根目标 | 原样／新增 | 主要业务义务 |
|---|---|---|---|
| training | sp-script-inventory-v035 | 原样 | 使用真实 sqlparse 分割／解析 SQL，提供有序记录和库存报告 |
| development | sc-job-policy-v035 | 原样 | 队列／优先级规则验证与逐任务报告 |
| development | sc-command-set-v035 | 原样 | 完整 put/drop 批次验证与原子活动集合更新 |
| development | sc-room-bookings-v036 | 新增 | 每条时段整体验证，按房间对已接受区间执行顺序冲突过滤，相邻可接续 |
| development | sc-order-totals-v036 | 新增 | 嵌套订单整体验证，保留重复行，计算整数行金额、subtotal 与折扣后的 due |
| confirmation | tf-port-status-v035 | 原样 | 平面端口状态记录及 up/down 计数 |
| confirmation | tf-batch-totals-v035 | 原样 | Filldown 批次值及批次计数／求和 |
| confirmation | tf-latest-readings-v036 | 新增 | 保留原读数流后按名字取最后值，按名排序，不按重复值累计 |
| confirmation | tf-work-sections-v036 | 新增 | Filldown 组头下工作项的逐项前缀 start/finish，每组独立从零开始 |

新增四根目标各有两个生产编辑模块，另允许成员自己的 test_member.py。TextFSM 两个新目标分别提供 readings.template、work.template 为只读 grammar。公共接口属于不可变业务根目标，不是预置角色分工；初始执行任务和 owner 均为空。只测试各 contract.md 明示的输入域，所有整数、顺序、重复、空输入及输入保持义务均写在公开合同中，私有输入不新增隐藏行为。

仓库和用途沿用既有冻结：sqlparse `e57923b3aa823c524c807953cecc48cf6eec2cb2`／BSD-3-Clause仅用于训练，schema `24a3045773eac497c659f24b32f24a281be9f286`／MIT仅用于贡献开发，TextFSM `c31b600743895f018e7583f93405a3738a9f4d55`／Apache-2.0仅用于独立确认。环境对象与原 manifest 完整相等，实际库和许可证字节仍由原 pin/SHA 检查；没有下载另一个版本或施加旧 defect。相关原库回归仍是 schema 的 test_callable_error，以及 TextFSM 的 testParseNullText/testReset。根目标数不等于来源仓库数。

新 partition 在编写 fixtures/reference 之前落盘，规范摘要为 `d33cb00f31e1d93bb3b7be048d7e46c87ce0b9784e29550457a3cfa3833a56c5`。它保留原 purpose 映射的引用并追加四项；`old_results_reclassified=false`、`old_development_material_admitted_to_training=false`。

**实际 CPU 检查与结果**

执行命令：

```text
CUDA_VISIBLE_DEVICES='' PYTHONDONTWRITEBYTECODE=1 PROWORKSIM_V036_SOURCE_CONTROL_RUN=runs/v036-controls/sources/development-1 .venv/bin/python -m pytest -q tests/test_software_sources_v036.py
```

结果为 `3 passed in 4.79s`。程序资格内部使用4个CPU线程；每个程序同时检查任务内私有合同和公开合同／原库回归，两次 sandbox 执行分别归档。实际共28程序变体、56隔离执行。没有模型、GPU、SDK合成 token 或参数训练。原训练 root 的程序对照不重复执行，原四面板 root 的旧反控制也不重复；仅重新运行其完整参考以确认当前面板接入。

| 材料 | 变体数 | 完整通过 | 完整不通过 | 解释 |
|---|---:|---:|---:|---|
| 新四 root 的原始 starter | 4 | 0 | 4 | 原始未实现程序不满足完整合同 |
| 新四 root 仅共享 API 侧参考 | 4 | 0 | 4 | 共享接口私有检查通过，consumer 尚未完成 |
| 新四 root 仅 consumer 侧参考 | 4 | 0 | 4 | 原共享产物仍缺失，完整交付不成立 |
| 新四 root 联合参考 | 4 | 4 | 0 | 业务内容、真实 API 观察、共享产物消费和完整公开／私有义务均通过 |
| 新四 root 绕开真实库 | 4 | 0 | 4 | 业务输出仍正确，但真实 schema/TextFSM API 条件失败 |
| 新四 root 绕开共享入口 | 4 | 0 | 4 | consumer 内另行实现可给正确输出，但声明的产品入口没有实际被调用 |
| 保留四面板 root 联合参考 | 4 | 4 | 0 | 原合同和程序在当前来源接入下仍通过 |
| 合计 | 28 | 8 | 20 | 均为离线资格程序，无模型效果含义 |

八个功能正确的 API 绕过反控制均明确表现为 `content_correct=true`、`required_process_satisfied=false`、`process_observation_complete=true`。联合参考则三项都为 true。探针复用原 code-object call/return 观察；Python alias 导入不依赖临时 monkeypatch 才能被计数。保留 `source_api_trace` 中可序列化的实际产品返回和对应 consumer 输出；这是有限调用观察与合同核验，不声称解决任意程序的语义等价或因果必要性。

`source_binding()` 另核对旧五 case 的完整相等、三固定环境完整相等、purpose 与 training_eligible、空任务表／owner，以及 private acceptance、reference、controls 没有进入 actor 初始文件。修改合同的测试被只读文件门拒绝；旧 schema-catalog/textfsm-record-items/sqlparse-comparison-records 和 Marshmallow root 不属于本接口。新旧 API driver 与公开反馈投影算法保持一致。成员自测窄修复和新 Γ 身份由单独的 v0.36 world/runtime 变更绑定，不在本任务层把公开验收规则改松。

静态检查命令为：

```text
CUDA_VISIBLE_DEVICES='' .venv/bin/python -m ruff check src/proworksim/software_tasks_v036.py scripts/qualify_software_sources_v036.py tests/test_software_sources_v036.py
```

结果：`All checks passed!`。程序回执和逐变体原件位于 `runs/v036-controls/sources/development-1/`；完整资格文件及源码／资产 SHA 位于 `runs/v036-controls/sources/checks.json`。

**暴露与独立用途**

`examples/software-sources-v036/exposure-audit.json` 只引用本项目的已归档证据。v0.35实际progress共有16槽，全部是 sp-script-inventory-v035；worker 的 P3_started=false、actor/critic新增更新均0。旧四面板 root 出现在事前库存中，但没有本轮模型执行，不能把“已经冻结”写成“已测过模型效果”。旧训练 root 则已实际暴露，不称为新题；新窗口必须另冻 seed 和窗口身份。

四新增 root 在这次创建时没有本项目 target-model 执行；参考和反控制由离线CPU执行，不进入目标模型提示或训练材料，不产生成员 rollout/entry，不用于从确认池选择 Mapper、权重或超参数。该记录不是基础模型预训练语料无重合证明，也不是对未来各阶段仍未暴露的永久断言。所有历史 Marshmallow 开发题、旧任务和旧结果保持原用途，不做改标。

**面板规模和条件费用的边界**

新局部设计是4 schema root×4配对seed构成D=16开发面板；4 TextFSM root×4seed构成每正式方法16次确认；当前支持仍是相同训练 root 的新M=16。精确seed、次序、共同状态及新反馈Γ由外部冻结协议指定，source case不含seed。D=16仍是有限、少量root和来源家族的机制面板，不保证Contribution精度；必须报告逐root配对结果，不把每个seed当作新的独立任务。

在一个选中成员块、完整正负方向、共同B只计一次且实际n+=16、K=2的条件下，唯一试训为33，开发经历528；另有3次正式更新和48次确认，加16支持，共592条在线工作经历，完整窗口更新36次。这个数是条件上界而非实际执行；本次来源工作实际在线经历为0、模型更新为0。不能从 v0.35 的3.3 GPU小时采样成本推断后继更新或总工时；也没有据此恢复已经撤销的累计GPU／统一wall上限。
