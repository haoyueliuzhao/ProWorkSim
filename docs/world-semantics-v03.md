# v0.3：工作世界语义与生命周期完善

本轮以 [最新审计](reference/world-semantics-audit.md) 为依据，继续完善有限合成经营分析世界。验收对象是确认、阻塞、等待、变更、审阅和交付的实际后果；不扩大训练、GPU 使用或上下文效果研究。旧训练冒烟保留归档。

## W1：工作与发布的联合可达性

从 `initial` 发布组开始，交替扩展所有可能接受的工作和可能触发的发布规则，直到不动点。工作前驱和事件接受条件为 AND，同一发布组的多个生产者为 OR。无入口循环及互相等待配置被构建入口拒绝，错误列出不可达节点与所等发布/工作。启动即满足的空 guard 规则也实际排入事件队列。

这只是在“已激活工作可以正确完成”的乐观假设下检查结构可达，不是专业任务可解性证明。有限规则有入口、可结束的修订循环可以保留，不采用一律禁止回环的办法。

阻塞变为 `blocker_id / work_item_id / kind / requested_role / required_scope_version / status / resolution_ref`，另存请求 ID、创建时需求版本及历史。不同 blocker 不互相覆盖。回复只有同时匹配请求、工作、类型、角色和版本才可解除；所有相关阻塞解决且前驱已接受，工作才重新开放。

scope 的版本字段指分析依据需求版本，不是文件的 `v2` 字符串。受众需求更新可增加整体任务版本而不改变分析依据需求版本。旧回复保留为历史，不公开新版凭据，也不解除替换工作的 blocker。

支持先声明阻塞再请求，也支持先收到明确“不可得”的定向回复，再关联请求声明阻塞。没有可取得的批准依据时，运行器以 `blocked_unavailable` 结束当前 episode，`complete=false`，不会把它计为业务成功。

## W2：已批准工作依据

`ApprovedBasis` 是经理正式确认的可引用文件，保存依据/版本、项目、适用逻辑工作节点、分析需求版本、期间、生效逻辑时间、确认者、确认记录及被替代版本。

- manager 的 `can_confirm_basis` 与 reviewer 的交付批准权分开。
- 私有 `scope` 仍不能由分析师读取。mail 配置公开适用 basis；clarification 配置由真实定向回复授权指定版本。
- 访问权按版本记录。v2 的晚到回复只允许读取 v2，不会顺带开放私有 v3。
- 模型的必要依赖变为 financials + basis。读取历史不是采用声明；工作人员须在真实写入时明确绑定实际采用版本。
- 既有可读凭据适用时可直接使用，不要求每轮重新询问。

分别记录 `data_freshness`、`basis_applicability` 和总体 `freshness`。仅批准假设变化时，数据来源可保持 current，而 model/memo 的依据适用性变为 stale；后台不修改这些文件。

声明当前依据也不证明公式和输入正确。独立评价还用批准假设与实际单元格比对，再进行独立数值计算和扰动。`root_causes` 与 `propagated_failures` 记录依据/输入错误的传播，不将利润、股价和 memo 连带错误当作多个独立能力缺口，也不推断模型的心理原因。

## W3：执行中的需求变化

新增有限生命周期事件策略：在实际编辑、请求或提交动作之后发布依据修订。支持以下配置：

| scenario | 变化 |
| --- | --- |
| standard | 保留原有工作配置与完成后发布规则 |
| basis_only | 第二阶段只修订批准假设，financials 不变 |
| during_update | 首次模型编辑后修订依据 |
| waiting_reply | 发出 scope 请求后修订，旧回复随后到达 |
| during_review | 提交后、审阅前修订依据 |
| unavailable | 当前所需确认确实不存在，可合理阻塞 |

需求修订生成新工作实例，例如 `work-1@r2`。原逻辑节点通过 replacement 关系指向当前工作；后续前驱与事件 guard 使用当前实例。未完成旧任务标为 superseded，待审提交失效。既有 accepted 记录、批准者、文件版本和时间不改写，仅另外标记当前适用性已被替代。

本领域共享一个经营模型，因此分析依据修订按当前分析阶段整体处理。若另一个分析阶段已经激活，拒绝向过去阶段回写修订，要求对当前阶段另行处理。该限制避免把旧期间依据错误传播到新期间，并不宣称支持通用字段级因果分析。

工作人员可通过 `withdraw` 显式撤回待审提交，保留文件及撤回记录，然后重新提交。替换后的工作若仍等前驱，则为 waiting_dependencies，不假装已经就绪。已解决的旧 blocker 继续保留，不再次作废或抹除。

独立评价区分 `artifact_valid`（相对于当时绑定要求）与 `currently_applicable`（是否仍是当前要求）。历史正确交付不因为后续变化被重写为从来错误，旧批准也不自动批准新工作。

## W4：有限角色与交付语义

经理回复绑定具体工作和批准依据；客户端受众要求产生明确内容字段：

| 受众 | note.audience_content 的要求 |
| --- | --- |
| internal_management | executive_summary、action_items |
| external_client | plain_language_summary、assumption_disclosure、limitations |
| investment_committee | decision_context、scenario_risks |

同一合约公开在 guide/brief，并被业务审阅和独立评价读取。未知受众明确拒绝；错误或缺字段仍允许写入文件，由审阅暴露。检查仅覆盖字段、类型和非空要求，不宣称评完解释质量、专业充分性或客户沟通能力。

## 配置与覆盖标注

原“chain/fork/selective/coordination”是四种工作配置，其中 coordination 与 chain 的工作图相同。现在明确保存：

- configuration_id：四种配置。
- work_graph_id / topology_id：chain、fork、selective 三种图。
- role_information_id：mail 或 clarification。
- event_policy_id / scenario_id：事件与生命周期情境。
- error_injection_id：世界的错误注入标注；程序错误策略在实验报告中另记。
- layout_id：standard 或 shifted。

布局实验有相应指南，证明语义位置映射可用；selective 明示只改 note，证明遵守已说明的范围。二者均不扩大解释为任意表格理解或自主发现所有影响范围。

## 使用与验收

```bash
.venv/bin/proworksim build runs/review-change --scenario during_review --information clarification
.venv/bin/proworksim run runs/review-change --provider baseline
.venv/bin/proworksim evaluate runs/review-change

.venv/bin/python scripts/world_mechanism_suite.py --output runs/world-mechanisms --workers 4
.venv/bin/python scripts/basis_error_diagnosis.py runs/basis-diagnosis
.venv/bin/python scripts/world_staff_trials.py runs/world-staff --workers 3 --max-turns 45
```

机制套件固定一个种子，覆盖拒绝死锁、定向阻塞、依据变更、受众变更、晚到回复、待审变化、不可得信息、直接交付、进行中变化及撤回。错误策略另外复现“仍采用旧依据”和“只换标签未换输入”。固定模型是测试工作人员，模型一次做对不替代世界机制验收。

所有实验保存版本、实际工具动作、来源和失败。本轮不进行参数更新，不重新改写历史 API 轨迹。详细结果另见实验报告。
