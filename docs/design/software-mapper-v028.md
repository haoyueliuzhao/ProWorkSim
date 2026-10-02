# v0.28 软件净交付路线 Mapper 与配置变体登记

日期：2026-10-03。对应审计：固定提交 `2751a064…` 的分类噪声反例、C/N 表示与 G 基线命名。本次改动不重判 v0.27 保存的经历、Mapper、分数或报告；不启动学习，不升级旧开发资产用途。

## 问题与修改边界

v0.27 用最终集成人最早的任何编辑与最早跨成员导入的顺序区分 sequential / independent。给 `test_member.py` 添加无关注释再撤销就能改变类别，不能据此建立第二种真实方法支持。v0.28 改为读取已关闭 episode、真实 WorldCore 回执和不可变文件版本，并从**接受独立验收的固定交付版本**反向追踪净变化。

新接口为 `software_training_v028.export_software_episode(prepared, episode, assessment, *, declaration, slot_id, captured)`，返回 `(entry, evidence)`；Mapper ID 为 `software-work-methods-v0.28`。原 TeamRollout、成员自己产生的 token 投影、记录/权限核验、独立验收和支持绑定组件继续复用。没有第二套学习器。

本版输出的是保守的可观察路线，而不是“独立分支”“协同修复”或因果方法名称。完整工作为 false / unknown 时不产生正方法支持。开发来源始终 `optimizer_update_allowed=false`、`source_training_admission=false`。

## 净修改、实际输入与验证关系

1. 保留整段原始事件清单，包括固定提交之后的编辑；只使用该固定提交前的事件判断其路线。所有事件仍需绑定实际行动者的 WorldCore 操作回执。
2. 验证每次读取的历史文件版本 SHA256。以共同不可变基线与固定交付的 Python AST 比较；注释、格式和文档字符串不参与净修改判据。原始字节完整保留。
3. 使用完整顶层定义作为保守单位。当前载体公开根为 `fields.py` 的 `String` 类，`consumer.py` 的 `InventorySchema` 类及 `load_inventory` 函数。导入语句自身不构成已交付实现；其他净定义变化保持不确定，不自动扩展为方法支持。
4. 从最终净定义沿真实 `previous_reference` 反向追溯。编辑前后定义不变则继续回溯；有实质改变则记录实际作者。当发生集成，只有输出定义与确切输入补丁定义一致且不同于集成前定义，才保留该输入边。先编辑、撤销、再重写时，已经撤销的编辑不在最终反向链上。
5. `test_member.py` 不做整文件排除。保留下来的模块必须包含顶层、直接调用已导入项目 API 的 `assert`，且固定交付版本的真实测试驱动已完成并成功。固定驱动先运行可见测试、随后运行成员测试；成功返回才能据此确认成员测试被执行。该证据仅表示实际执行和语法上的契约联系，**不证明断言充分或调用在业务上必要**。
6. 不支持的间接测试、重复定义、无法解析的冲突版本、部分定义合并、原输入被后续重写等情况明确保留不确定。当前抽取粒度不能证明局部行的持续作者归属；不给它们补上“协作修复”类别。

整定义粒度有意降低召回率。例如成员对同一类的部分方法互相增量修改，后续重写可能使旧输入不再可追踪。此时未映射比推断两个独立方法更合适。此规则针对当前 Marshmallow 开发载体；新来源必须冻结自己的契约根或更强的执行溯源规则，不能将本版当成任意 SWE 仓库的通用分类器。

## 类别

| 类别 ID | 必需证据 | 不声称的内容 |
|---|---|---|
| `concentrated_net_delivery` | 固定有效交付；可追踪的净契约编辑只由最终集成人产生；不存在被覆盖而造成不确定的实际跨成员变换 | 不推断另一成员完全没有帮助 |
| `net_work_before_import` | 固定有效交付；最终集成人有保留的净契约编辑，时间早于最早保留的跨成员实际输入 | 不等同于独立开发，也不排除事先通信 |
| `net_work_after_import` | 同上，但最终集成人的最早保留净契约编辑在最早实际输入之后 | 不证明该输入导致了后续修改 |
| `unmapped` | 未完成/未知工作、无固定交付、净修改或输入/验证关系不确定等 | 不补成失败方法或制造多类支持 |

消息数量、任务名、任务领取顺序、声明依赖和补丁 ID 自身都不能决定这些类别。任务与通信原始事件保留，供逐条检查职责形成与内容使用。

## 精确情境与调度协议

成员身份保持 `member_a` / `member_b`，不是把岗位改名后当成新成员。v0.28 导出核验：

- `xi_id = case_id + '::first=' + first_member`；不同先手分开建立支持。
- `xi_fingerprint` 由完整 `case`、`reward_spec` 和事先固定的 `initial_business_sha256` 计算。
- `software_runtime` 的 `first_member`、`role_decision_limits`、`scheduling_protocol` 必须与实际 case 相同；runtime 版本为 `software-runtime-v0.28`。
- 绑定原声明的 Gamma、实际政策身份、成员集合和新 Mapper ID。`declare_window` 拒绝同精确情境中悄悄改变规则；不能合并两个先手或不同预算的经历凑频数。

## 当前分配器的准确变体

数值选择规则保持 v0.27 原样。本次只让新计划和新选择报告带上 `single-window-linear-support-deficit-base-anchor-v0.28-reporting`，明确：

\[
N_z=\max(0,1-Kb_z),\qquad q^0=b.
\]

这是单窗口、线性支持不足、基础组成锚的第一阶变体，**不是**近期理论稿的对数不足量加跨窗口历史锚。没有继承历史配置，也没有跨窗口预测器。G 和 I 使用共同支持及共同覆盖先验。

G 的准确名称为**“共同支持和覆盖先验下的原始轨迹重加权基线”**。它以原始成员轨迹为配置坐标，覆盖参考和 N 仍由共同类别统计展开；不能称为完全无类别或完全无结构基线。I 对同类、同成员经历绑定共享权重。

新计划的每块选择结果并列保存：

- `helmert_zero_arithmetic_mean_slope`：完整 Helmert 有限差分给出的零算术均值坐标斜率 \(g\)。
- `b_centered_contribution`：\(C_z=g_z-\sum_{z'}b_{z'}g_{z'}\)。
- `contribution_centering_offset`：两种表示的共同常数；原 `contribution` 字段保留原坐标斜率含义。

求解器仍接受相同斜率。减去共同常数只改变单纯形上的目标常数项，不改变选择。没有 metadata 的旧冻结计划不自动补字段或重写结果；新测试核验其候选权重和选择与加报告字段后的计划逐值相同。

## CPU 核验与保存边界

`tests/test_software_training_v028.py` 包含 8 个完整控制，均执行 WorldCore 编辑、真实固定补丁集成、真实测试、不可变提交、独立父进程验收和证据提取：

| 控制 | 原独立验收 | 新分类 |
|---|---:|---|
| 上游先行、消费端导入后修改 | 通过 | `net_work_after_import` |
| 相同工作前增加并撤销无关注释 | 通过 | 与无噪声相同；旧 Mapper 实际复现 `split_independent_branches` |
| 相同工作前增加并保留无关注释 | 通过 | 与无噪声相同 |
| 消费端先实际修改、撤销，导入后重新实现 | 通过 | `net_work_after_import`，撤销修改不抢占顺序 |
| 先写并保留项目契约断言，后续在交付版本执行 | 通过 | `net_work_before_import` |
| 消费端实际实现保留在导入前 | 通过 | `net_work_before_import` |
| 保留 `assert True` 的非契约测试 | 通过 | `unmapped`，不把无关执行制造成方法支持 |
| 提交不满足真实契约的消费端实现 | 不通过 | `unmapped`；unknown V 也不映射 |

每个控制另外在固定交付后编辑成员测试，核验该事件被保留但不回溯改变交付路线或独立结果。这些都是明确脚本控制，**不是 8 条模型经历，也不构成训练支持**。

配置报告的 2 项新测试与原配置器 13 项测试共同通过；核验旧候选/权重不变、加权中心化为零、两种贡献表示得到同一 q。Ruff 通过。正式控制证据保存在 `runs/v028-controls/mapper-controls/frozen-evidence/`，包含原始 episode、历史版本、验收、语义证据和 mapping。初次开发检查的原始 episode 另外保存在 `prearchive-pytest-*`；该次验收返回值当时未持久化，不通过事后重判伪造原始文件。
