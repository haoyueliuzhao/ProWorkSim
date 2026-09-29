# v0.25 完整工作有效性、方法 Mapper 与当前支持投影

本次把已有独立工作证据接到完整有效性和当前策略支持，不用 `reward==1` 或 `completed` 代替语义准入。真实模型支持仍必须由本轮新窗口产生；本页的程序路线与 synthetic-token 测试不是模型经历、支持计数或学习结果。

## 本轮只对已获规则见证的 A 成员开放配置

训练清单仍为同一精确 A 情境八次、同一精确错误计数初稿 B 情境八次，全部十六槽进入基础分母。A 的主动交接与绑定请求后交接都在原权限、完整职责、固定上下文与角色预算下完成了 CPU 路线见证。B 自检修复也有合格程序路线；反馈修复的多个显式 CPU 程序尝试尚未在固定上下文中完成。失败原件由世界准入报告保留。

因此，在真实模型采样前冻结本轮范围：**候选选择仅 A implementer → A provider**。B 继续真实工作、基础 RL、完整有效性与方法统计，所有 B 成员块保持 `Q=B`；即使后续真实 B 经历出现两类，也不临时开放。程序见证未获资格不是该路线不可能的证明。代码同时保存 `configurable_tasks=['joint_a']` 和明确的 B 排除原因。

## 四个维度分别有证据

- `record`：复用独立公开端口捕获与历史记录比较；真实请求/响应/动作关联必须完整。token 完整性另设门，不由语义有效性冒充。
- `permission`：复用 WorldCore 实际 scoped receipt，实际 bound actor、动作、参数与回复一致。合同允许的被拒动作不因 `ok=false` 被删除；无 apply 业务变更的合法拒绝仍可留在基础经历。
- `basis`：A 要求提供者在当前真实输入中读过适用依据，实际交接已发生，实施者读取并采用同一版本用于当前正确构建和固定交付。B 要求检查真实错误初稿和输入、当前新构建的实际采用、最终审核者读取该固定 code/result 及独立 data/audit；问题路线还须有据处理。
- `delivery`：A 必须有真实 `sql_build` 来源与代码版本、正确新固定提交及实际交接依据的使用。B 必须从实际错误初稿产生正确的新固定提交，完成当前独立核准，并闭合已实际提出的有据问题。准备交付和准备交接不充当当前工作。

以上直接复用 `RetailEvidence` 的真实读取/输入呈现/采用检查，以及既有 `_quality`、`_actual_fixed_build`、`_judgments`、`_implementation_inspected`、`_issue_treatment`，不新增业务答案 oracle。四维通过与否、basis/delivery 引用、事件序号和 episode manifest SHA 都随 rollout 保存。

## 方法定义保持有限

| 情境 | canonical 方法顺序 | 当前证据 |
|---|---|---|
| A | `a_active_handoff`，`a_requested_handoff` | 当前合法实际交接的唯一选定依据确实用于新交付；请求类须实际早先请求的 request ID 与交接响应一致 |
| B | `b_self_repair`，`b_feedback_repair` | 同一个真实错误初稿上先检查再撤回；自检路线在修复起点之前没有有据问题，反馈路线的实际 issue 先于撤回、且出现在实施者撤回前真实模型输入的 `observation.issues`；新提交随后绑定 `respond_issue → decide_issue(accept_fix) → approve` |

B 的类别继续报告，当前不具备配置准入。多个可能导致同一固定产物的交接、缺少实际请求身份、未完成工作或歧义路径保持 `unmapped`，不靠读取顺序、措辞、笔记或奖励标签制造类别。Mapper 是已观测信息关系与执行路线描述，不声称因果成员贡献。方法标签和检查结果不进入 actor 的公共工作提示。

## 支持与基础训练分开

`export_training_episode(...)` 保留 v0.24 接口，返回原 entry 和 proof；entry 新增 `mapping`，rollout 保留四维有效性与真实成员局部视图。各角色只对自身实际生成 token 建立输出掩码，工具结果和其他成员输出保持输入。

`records_from_entries(entries)` 只引用原 rollout/mapping，不重放世界。`diagnose_support(entries,declaration)` 复用原 `diagnose_window → bind_rollout → build_support`，每个精确 xi 独立统计 `M=8`、`n_by_class`、`n_positive`、`v`、`b` 与最低每类两条。窗口/情境/actor/policy fingerprint 不一致不能拼池。完整合法工作而无自身完整 token 的成员不能冒充可训练支持；可信失败、合法被拒、未映射和低频类不会因此失去本来具备的基础 actor mask。

`support.json` 可剔除大体积 `records` 字段，仅存各 xi 支持与原件 digest；分支更新从原 entries 重建记录，不创建新经历。选块不读取开发结果；类别 canonical 顺序中主动/自检在前。保留全窗十六槽、活跃成员与每成员全部输出 token 分母，不按成功数或权重和重归一化。

`purpose='continuation_training'` 只接受 `v025-next-base` / `v025-next-configured` 的两个新情境，各 xi `M=1`，最低类频数仍为二；因此没有配置自由度。其 admission 明确 `optimizer_update_allowed=false`，不把两个后继 rollout 伪装成主窗 `M=8`，不再更新参数。

成员 token 状态分别为 `complete_actual_generation`、`known_no_generation`、`known_no_own_actions`、`incomplete_or_unknown_tokens`。新增的明确零自身动作仅适用于空 decisions、空 diagnostics 且 `no_own_actions=true`；实际产生过 completion 却没有可靠 token 记录仍是未知，不能改成零目标。投影 proof 的 `has_complete_trainable_actual_members` 已允许合法零动作/已知生成前停止，并不要求每个成员都生成 token。

## 必要 CPU 验证

命令 `.venv/bin/python -m pytest -q tests/test_collaboration_training_v025.py`：**4 passed in 2.18s**。对应：

1. 两个新 continuation WorldCore 实际闭合，走真实 native/compact 请求和工具入口；token ID/logp 是明确标注的 synthetic CPU fixture。零奖励失败仍保留本人 token、原二维掩码和两个原槽分母；每 xi `M=1`、无可重配类别、无额外更新。
2. 空自身动作与真正缺失 token 证据分开，前者不制造生成目标，后者不假冒已知零信号。
3. 纯构造八槽支持的两类分别三条、两条，`b=(0.6,0.4)`、`q=(0.3,0.7)`：合格权重和五、所有槽权重和八，可信失败与未映射残余权重仍一；token 缺失成员 actor mask 为 false。低频类不进入支持，不同 xi 不能合并。此表不是模型采样支持。
4. 只读核验两条已合格 A 路线与当前短准备 SQL 版本的 B 自检路线，四维和方法与实际证据一致；这些显式程序按 `origin='rule'` 记语义见证，不用于模型支持计数。高标量回报不能填补缺失完整依据。

首次 projection fixture 使用了默认短上下文参数，按冻结 16384/2048 门在采样前被拒，修正的仅是测试配置。随后旧 B 程序原件因准备 SQL 的显式版本已更新、case ID 改变而被严格拒；测试改绑定新已合格 B 见证目录，没有放宽历史身份检查。原始失败仍保留，不重判。三个新代码/测试文件 Ruff 与 `git diff --check` 通过。

正式十六槽 CPU collector/composition 端到端控制由训练接线报告另行记录，使用同一个投影接口；不得与本页四项测试重复计为独立模型试验。

代码：[完整工作与方法](../../src/proworksim/work_methods_v025.py)、[当前支持投影](../../src/proworksim/collaboration_training_v025.py)、[定向测试](../../tests/test_collaboration_training_v025.py)。实际模型采样、支持是否达标、配置权重与工作效用须阅读本轮后续运行报告，本页不预报其结果。
