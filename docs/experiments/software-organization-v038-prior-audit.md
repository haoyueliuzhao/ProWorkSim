# v0.38 阶段 A：已有 32 条经历的组织行为复核

日期：2026-10-09。仅复核已结束的 P2 16 条与共同 B 开发 16 条；没有调用模型、使用 GPU、重跑测试或验收，也没有读取 TextFSM 确认池。本表描述旧 v0.36 运行，不是新 O1/O2/O3 实验结果。

机器明细：[software-organization-v038-prior-audit.json](software-organization-v038-prior-audit.json)。每槽保留原文件 SHA256；开发数据以 `development-original.tar.gz::slot-n/…` 定位。归档只顺序读取一次，被抽取成员逐项与既有归档回执核对，不重复整包校验。

## 行为表

C/K/R/D 分别为成功创建、认领、修订、直接转交次数；M/V 为已送达工作事件／在收件人实际 selected input 中出现的事件数；I 为显式整合数。重叠编辑按生产文件计数，不称为浪费。P2 为同一 SQL root，开发四 root 以 job/command/room/order 缩写。

| 槽 | root | R/提交 | C/K/R/D | 编辑→建任务 | 重叠生产路径 | M/V | I | 终态原因 A/B |
|---|---|---|---|---|---:|---|---:|---|
| P2-00 | SQL inventory | 1/1 | 2/2/0/0 | W4→W11 | 2 | 0/0 | 1 | A:completed; B:completed |
| P2-01 | SQL inventory | 1/1 | 1/1/0/0 | W2→W16 | 2 | 0/0 | 1 | B:completed; A:completed |
| P2-02 | SQL inventory | 1/1 | 1/1/0/0 | W7→W14 | 2 | 0/0 | 1 | A:completed; B:team_budget_exhausted |
| P2-03 | SQL inventory | 1/1 | 2/2/0/0 | W6→W13 | 2 | 0/0 | 1 | A:completed; B:completed |
| P2-04 | SQL inventory | 1/1 | 2/1/0/0 | W7→W15 | 2 | 0/0 | 1 | A:completed; B:team_budget_exhausted |
| P2-05 | SQL inventory | 1/1 | 2/2/0/0 | W4→W14 | 2 | 0/0 | 1 | B:completed; A:completed |
| P2-06 | SQL inventory | 1/1 | 1/1/0/0 | W7→W19 | 2 | 0/0 | 1 | B:completed; A:no_reachable_wake_event |
| P2-07 | SQL inventory | 1/1 | 2/2/0/0 | W5→W13 | 2 | 0/0 | 1 | A:completed; B:completed |
| P2-08 | SQL inventory | 0/0 | 1/1/0/0 | W4→W18 | 2 | 1/1 | 0 | A:team_budget_exhausted; B:no_reachable_wake_event |
| P2-09 | SQL inventory | 1/1 | 1/1/0/0 | W4→W12 | 2 | 0/0 | 1 | A:completed; B:team_budget_exhausted |
| P2-10 | SQL inventory | 1/1 | 1/1/0/0 | W4→W11 | 2 | 0/0 | 1 | A:completed; B:team_budget_exhausted |
| P2-11 | SQL inventory | 1/1 | 1/1/0/0 | W4→W12 | 2 | 0/0 | 1 | A:completed; B:completed |
| P2-12 | SQL inventory | 0/0 | 0/0/0/0 | 无登记 | 2 | 0/0 | 0 | A:team_budget_exhausted; B:team_budget_exhausted |
| P2-13 | SQL inventory | 1/1 | 2/2/0/0 | W5→W10 | 2 | 1/1 | 1 | B:completed; A:completed |
| P2-14 | SQL inventory | 1/1 | 1/1/0/0 | W6→W12 | 2 | 0/0 | 1 | B:completed; A:completed |
| P2-15 | SQL inventory | 1/1 | 1/1/0/0 | W6→W16 | 2 | 0/0 | 1 | A:completed; B:completed |
| B-00 | job-policy | 1/1 | 1/1/0/0 | W5→W15 | 2 | 0/0 | 1 | B:completed; A:team_budget_exhausted |
| B-01 | command-set | 0/0 | 0/0/0/0 | 无登记 | 2 | 0/0 | 0 | B:team_budget_exhausted; A:team_budget_exhausted |
| B-02 | room-bookings | 1/1 | 1/1/0/0 | W8→W30 | 2 | 0/0 | 1 | B:completed; A:team_budget_exhausted |
| B-03 | order-totals | 0/0 | 0/0/0/0 | 无登记 | 2 | 0/0 | 0 | A:team_budget_exhausted; B:team_budget_exhausted |
| B-04 | job-policy | 0/0 | 0/0/0/0 | 无登记 | 2 | 0/0 | 0 | B:team_budget_exhausted; A:team_budget_exhausted |
| B-05 | command-set | 0/0 | 0/0/0/0 | 无登记 | 2 | 0/0 | 0 | A:context_capacity; B:team_budget_exhausted |
| B-06 | room-bookings | 0/0 | 0/0/0/0 | 无登记 | 2 | 0/0 | 0 | B:team_budget_exhausted; A:team_budget_exhausted |
| B-07 | order-totals | 0/0 | 0/0/0/0 | 无登记 | 2 | 0/0 | 0 | B:team_budget_exhausted; A:team_budget_exhausted |
| B-08 | job-policy | 1/1 | 1/1/0/0 | W8→W15 | 2 | 0/0 | 0 | B:context_capacity; A:completed |
| B-09 | command-set | 1/1 | 1/1/0/0 | W13→W20 | 2 | 0/0 | 1 | A:completed; B:team_budget_exhausted |
| B-10 | room-bookings | 0/0 | 0/0/0/0 | 无登记 | 1 | 0/0 | 0 | B:team_budget_exhausted; A:no_reachable_wake_event |
| B-11 | order-totals | 0/0 | 0/0/0/0 | 无登记 | 2 | 0/0 | 0 | B:team_budget_exhausted; A:team_budget_exhausted |
| B-12 | job-policy | 0/0 | 1/1/0/0 | W13→W26 | 2 | 0/0 | 0 | A:team_budget_exhausted; B:team_budget_exhausted |
| B-13 | command-set | 0/0 | 0/0/0/0 | 无登记 | 2 | 0/0 | 0 | A:team_budget_exhausted; B:team_budget_exhausted |
| B-14 | room-bookings | 1/1 | 1/1/0/0 | W7→W18 | 2 | 0/0 | 1 | B:completed; A:team_budget_exhausted |
| B-15 | order-totals | 0/0 | 0/0/0/0 | 无登记 | 2 | 0/0 | 0 | B:team_budget_exhausted; A:team_budget_exhausted |

## 汇总与真实语义

- **P2**：提交 14/16，R=1 为 14/16；15 槽建过任务，其中 15 槽先编辑后登记；16 槽双方编辑同一生产路径。定向工作事件 2 条，实际收件输入证据覆盖 2 条。
- **B-development**：提交 5/16，R=1 为 5/16；6 槽建过任务，其中 6 槽先编辑后登记；16 槽双方编辑同一生产路径。定向工作事件 0 条，实际收件输入证据覆盖 0 条。

`claim_task` 是成员主动接受无人负责的任务；旧 `delegate_task` 则直接改 owner 并通知，不是“先提议、后接受”，接收者只能随后 `return_task`。本批成功转交、退回、修订和依赖调整次数见机器表，不能以接口存在代替使用证据。普通工作消息没有形式化请求完成状态。

编辑与测试不需要建任务；`fix_patch` 却要求关联本人负责任务，所以后置建任务可能与发布手续有关，但本复核不替模型推断动机。正式 owner 不切分私有文件编辑权限；同范围的实现和测试可以重叠。

整合之后的测试与提交已逐一连接到原版本。整合 ID 出现在提交中不证明最终保留了有效伙伴代码，更不证明因果必要性；本次不重算旧 Mapper。公开测试是否执行、是否通过、是否为终态版本分别记录。

## 11 条开发未提交的可观察断点

下表 T/F/S 是实际测试执行／成功固定／成功提交次数；世界工具拒绝单列，格式拒绝另存机器记录。“当前测试”只说明已有最后测试对应终态可变版本，不对未提交代码补验。预算终止依据运行器原记录，不从接近 50 万 token 推断唯一原因。

| 槽/root | T/F/S（拒绝 F/S） | A 终态版本／最后测试 | B 终态版本／最后测试 | 原终止证据 |
|---|---|---|---|---|
| B-01 sc-command-set-v035 | 3/0/0（0/0） | v4 / W24 v3 public=False 旧版 | v7 / W21 v4 public=False 旧版 | B:team_budget_exhausted; A:team_budget_exhausted |
| B-03 sc-order-totals-v036 | 3/0/0（0/0） | v4 / W39 v4 public=False 当前 | v12 / W19 v3 public=False 旧版 | A:team_budget_exhausted; B:team_budget_exhausted |
| B-04 sc-job-policy-v035 | 5/0/0（0/0） | v7 / W32 v4 public=False 旧版 | v11 / W36 v11 public=False 当前 | B:team_budget_exhausted; A:team_budget_exhausted |
| B-05 sc-command-set-v035 | 3/0/0（0/0） | v7 / W24 v7 public=False 当前 | v4 / W30 v3 public=False 旧版 | A:context_capacity; B:team_budget_exhausted |
| B-06 sc-room-bookings-v036 | 7/0/0（0/0） | v7 / W38 v7 public=False 当前 | v5 / W28 v5 public=False 当前 | B:team_budget_exhausted; A:team_budget_exhausted |
| B-07 sc-order-totals-v036 | 6/0/0（0/0） | v4 / W19 v4 public=False 当前 | v8 / W33 v7 public=False 旧版 | B:team_budget_exhausted; A:team_budget_exhausted |
| B-10 sc-room-bookings-v036 | 2/0/0（0/0） | v6 / 未测试 | v5 / W26 v5 public=False 当前 | B:team_budget_exhausted; A:no_reachable_wake_event |
| B-11 sc-order-totals-v036 | 3/0/0（0/0） | v9 / W20 v4 public=False 旧版 | v4 / W30 v3 public=False 旧版 | B:team_budget_exhausted; A:team_budget_exhausted |
| B-12 sc-job-policy-v035 | 3/1/0（1/0） | v4 / W24 v4 public=True 当前 | v3 / W21 v3 public=False 当前 | A:team_budget_exhausted; B:team_budget_exhausted |
| B-13 sc-command-set-v035 | 8/0/0（0/0） | v10 / W36 v9 public=False 旧版 | v8 / W43 v8 public=False 当前 | A:team_budget_exhausted; B:team_budget_exhausted |
| B-15 sc-order-totals-v036 | 5/0/0（0/0） | v11 / W23 v5 public=False 旧版 | v7 / W36 v7 public=False 当前 | B:team_budget_exhausted; A:team_budget_exhausted |

11 条未提交中，10 条没有成功固定补丁；B-12 是唯一已固定仍未提交的槽。A 在 W24 对 v4 的公开测试已通过，随后将 `root_goal` 当执行任务发布，被 `Unknown task` 拒绝；再创建、认领 `complete_validation` 并固定成功，下一机会因团队剩余 token 无法覆盖预留而终止。其间 B 仍在修复；没有实际 submit_integration 调用。不能把这一槽说成验收失败。

其余 10 槽，两成员各自最后已有公开测试都未通过（B-10 的 A 没有测试）；部分成员最后一次修改还晚于最后一次测试。11 槽均有成员被团队 token 预留边界停止，此外 B-05 的 A 先触及 context_capacity，B-10 的 A 处于等待、终态没有可达唤醒事件。这些是多种并存的断点，不能简化为“只差预算”，也不能替未提交终态下隐藏正确性结论。

另一个上下文停止发生于成功槽 B-08 的 B；A 继续并完成固定提交。两个停止都在生成前发生，不能把预备好的 selected request 当成实际调用；本表可见性只纳入已实际启动并记账的生成，绑定团队账本中的 selected-request/input-ID hash。

## 收件可见、结束与未闭合责任

两个工作请求均来自 P2，且均确实进入收件人的生成输入。P2-08：B 的 W23 请求 A 实现、测试、提交，A 后续 W24/29/32/35 测试及 W31/33 编辑，最终没有固定提交；P2-13：A 的 W14 请求 B 发布，B 随后 W16 测试、W17 固定、W19 提交。后者在收到请求前已于 W11 认领任务，不能把文字中的“请认领”当成新责任已经转移。

P2 有 14 槽在一方 done 后另一方仍获得机会，其中 5 槽另一方随后又提交；B 开发有 4 槽如此继续，但没有后续新提交。最后固定交付在双方最后实际输入中都出现的槽为 P2 9/14 个已提交槽、B 开发 4/5 个已提交槽；可见不等于双方协商认可。P2 的 4 次 wait 分布于槽 06/08/13（槽 13 两人各一次），B 的唯一 wait 在槽 10。

JSON 的 `message_visibility` 区分发送落库、收件人精确 selected input 和后续行为。后续行为仅是时间关联，不能自动认定为理解或因果响应。`members.last_selected_observation` 列出成员最后实际输入看到的交付、任务和人员状态；`other_member_actions_after_stop` 保留另一方后续工作，避免把一人 staff_done 当成团队协调结束。

旧任务记录没有 completed 字段；终态保留 owner 不等于该责任确实未完成。本复核保留所有终态任务、固定补丁及交付关联，同时明确：自由文本请求缺少确认／关闭协议，不能可靠自动判定所有请求均已履行。没有消息或双方分别 done，也不能据此称为已经协调过结束。

## 对新入口的直接约束

1. 明确区分主动认领、提议转交、接收责任和退回；记录修订前后及真正接受者。
2. 不把任务板变成发布手续负担；集中完成与不建复杂图的合法路径仍可运行。
3. 新成员、等待和退出共用预算；退出不删除 owner、请求、固定产物或版本历史。
4. 维持精确 selected input 留档，分别统计事件已送达、已呈现和之后实际动作。
5. 保留当前版本测试与固定提交要求，同时记录拒绝；不要把公开测试通过自动变成提交或验收。
6. 保持终态最后固定交付口径；不因首个交付后仍有工作而强制提前停止。

复现：`python scripts/audit_software_organization_v038.py`。此命令只读取上述 P2 / B 开发数据，只覆盖本报告及对应 JSON，不启动模型、GPU、验收或训练。
