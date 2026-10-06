# v0.36：保留原用途并扩展局部开发／确认面板

本目录新增四个业务根目标，原 v0.35 五个根目标精确委托原任务模块，不复制或改写其合同、starter、公开 driver、参考解、私有验收及 source_contract。训练仍为 `sp-script-inventory-v035`；此前 16 条模型经历已经用于表示开发，只能保留为历史材料，新支持必须来自另冻的新窗口。原 schema 两根目标和 TextFSM 两根目标在 v0.35 未实际执行模型，可以继续保留在原用途。

| 固定用途 | 根目标 | 状态 | 真实 API → 共享产物 → 消费入口 |
|---|---|---|---|
| policy_training | sp-script-inventory-v035 | 原样保留 | sqlparse → reader.statement_records → report.summarize |
| contribution_development | sc-job-policy-v035 | 原样保留 | schema.Schema.validate → policy.validate_job → consumer.review_jobs |
| contribution_development | sc-command-set-v035 | 原样保留 | schema.Schema.validate → rules.validate_commands → consumer.apply_commands |
| contribution_development | sc-room-bookings-v036 | 新增 | schema.Schema.validate → rules.validate_booking → consumer.schedule_bookings |
| contribution_development | sc-order-totals-v036 | 新增 | schema.Schema.validate → rules.validate_order → consumer.price_order |
| independent_confirmation | tf-port-status-v035 | 原样保留 | TextFSM.ParseText → adapter.port_records → consumer.port_report |
| independent_confirmation | tf-batch-totals-v035 | 原样保留 | TextFSM.ParseText → adapter.batch_values → consumer.batch_totals |
| independent_confirmation | tf-latest-readings-v036 | 新增 | TextFSM.ParseText → adapter.readings → consumer.latest_readings |
| independent_confirmation | tf-work-sections-v036 | 新增 | TextFSM.ParseText → adapter.work_items → consumer.work_timeline |

新增房间目标逐条验证有效时段，再按房间和已有区间冲突决定接受或拒绝，明确相邻不冲突、不同房间可重叠、原顺序优先。新增订单目标验证完整嵌套对象，逐行计算整数数量乘价格、整体拒绝非法订单、使用绝对折扣并下限截到零。它们分别增加跨记录时段关系与嵌套整体验证／定价，不是旧队列优先级或 put/drop 指令的改名。

新增 readings 目标保留 parser 的全部原始重复记录，由 consumer 按名字保留最后观测并排序；不能把重复值相加。新增 work-sections 目标用只读 Filldown 模板取得带组头的工作项，并输出每个工作项的前缀 start/finish 以及各组最终时长；每组从零开始，必须保留中间时间点、重复项目及零时长。它与旧 batch 仅计数／求和有不同的业务输出义务。输入均为合同明示的小型合法结构，没有外部系统、复杂领域规则或未声明异常类型。

三份 pristine 上游环境的完整 commit、许可证及已有文件 SHA 保持不变：sqlparse `e57923b3aa823c524c807953cecc48cf6eec2cb2`（BSD-3-Clause，训练）；schema `24a3045773eac497c659f24b32f24a281be9f286`（MIT，贡献开发）；TextFSM `c31b600743895f018e7583f93405a3738a9f4d55`（Apache-2.0，独立确认）。上游只读字节仍取自 `examples/software-sources-v028/*/upstream`，不重施旧 defect.patch。新增 `source-partition.json` 在写 fixtures/reference 前先固定完整九根目标的用途，引用原 partition 的 SHA，未改旧分配。

每个新根目标有 actor 可见的完整合同、有限公开案例、任务内私有验收、两份生产 starter、联合参考解，以及有业务意义的反控制。私有验收和 reference/controls 不进入 actor 初始文件。`contract_symbols` 只列合同已经声明的公共入口；不指定成员角色、方法类别或强制工作顺序。初始 task_definitions 和 initial_owners 仍为空，成员可集中完成或自行组织工作。

实际 API 探针复用 v0.35 的 Python code-object call/return 观察和精确值／类型比较，不 monkeypatch 目标函数、不重新定义返回值。除原始、仅共享侧、仅 consumer 侧和联合参考外，新根目标还各有两种“业务输出仍正确”的反控制：绕开真实库、在 consumer 内自行实现而绕开共享产品入口。它们应因过程 API 条件失败而被拒，不能只凭业务输出给完整通过。这个有限观察并非任意 Python 程序的因果依赖证明。

本来源工作只做 CPU 程序资格：新四根目标六变体，加原四面板根目标的完整参考，共 28 个程序、56 次隔离执行；8 个联合参考通过，20 个反控制失败。没有模型调用、SDK 合成训练轨迹、optimizer 更新、Mapper 在确认池上的开发或算法独立效果观测。具体检查与原件在 `runs/v036-controls/sources/`；说明见 `docs/experiments/software-sources-v036.md`。

模型暴露记录见 `exposure-audit.json`。保留训练 root 已实际暴露，不能称作全新题；原四面板 root 在 v0.35 只冻结未执行，新增四 root 在创建时没有本项目 target-model 执行。这里不声称基础模型预训练无重合，也不把 CPU reference 通过当作模型能力或训练收益。

开发 D=16 与每方法确认 16 的 root×seed 库存由外部协议事前冻结，source case 本身不含 seed。四个 root×四个 seed 不等于 16 个独立任务，更不等于 16 个独立仓库；报告仍须给出逐 root 配对结果。固定一个合格成员块、n+=16、K=2 时，33 个唯一试训×16开发=528 开发经历，加3正式方法×16确认及16支持，条件上界为592条在线经历、36次完整窗口更新；这不是本来源资格的实际执行数或工时预测。
