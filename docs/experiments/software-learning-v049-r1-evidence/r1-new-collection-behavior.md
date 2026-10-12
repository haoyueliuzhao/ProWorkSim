# v049 r1 新 3 槽只读行为分析

仅分析原剩余 LA r4、LB r3/r4，三槽均保留，不按 R、消息或任务数量筛选。结果与验收读取原件，未重新验收、生成、使用 GPU 或导出训练材料。

| 槽 | R / Q | 实际调用 | 总 token | 测试 | 建任务 | 消息 / 接收者实见 | 唤醒 | 机械决定 |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| org49-train-LA-r4 | 1 / 1.0 | 32 | 448905 | 5 | 0 | 0 / 0 | 2 | continue |
| org49-train-LB-r3 | 1 / 1.0 | 20 | 270431 | 2 | 0 | 0 / 0 | 2 | continue |
| org49-train-LB-r4 | 1 / 1.0 | 35 | 495265 | 5 | 0 | 0 / 0 | 2 | continue |

合计 87 决定、87 实际调用、1214601 token、12 次成员测试。
稳定身份检查：三槽初始任务表为空=True；结束仍为原两名 live 身份、无出生或永久退休=True；学习状态守恒=True。

## 任务责任与会话生命周期

### org49-train-LA-r4

最终任务数 0；责任事件计数 `{}`。
实际动作计数 `{"list_files": 1, "read_file": 3, "replace_file": 2, "write_file": 1, "run_tests": 5, "read_test_result": 4, "submit_integration": 8, "fix_patch": 2, "adopt_candidate": 1, "staff_done": 4}`。
终止原因为 `all_members_stopped_or_no_reachable_event`；不可运行成员 `{}`；休眠唤醒次数 2。
报告页计数 `{"reports_saved": 5, "reports_storage_verified": 5, "reports_with_directory_presented": 5, "reports_with_any_page_presented": 5, "reports_historically_fully_presented": 2, "verified_page_feedback_returns": 9, "actual_page_read_requests": 4, "page_read_outcomes": {"verified": 4}, "continuation_reasons": {"not_requested": 3, "no_unpresented_remainder": 2}}`。
反馈无后继原因 `{"current_work_ended_no_reachable_event": 2}`；资源拒绝 `{}`。

### org49-train-LB-r3

最终任务数 0；责任事件计数 `{}`。
实际动作计数 `{"read_file": 3, "replace_file": 3, "claim_task": 1, "run_tests": 2, "fix_patch": 2, "adopt_candidate": 1, "submit_integration": 3, "staff_done": 4}`。
终止原因为 `all_members_stopped_or_no_reachable_event`；不可运行成员 `{}`；休眠唤醒次数 2。
报告页计数 `{"reports_saved": 2, "reports_storage_verified": 2, "reports_with_directory_presented": 2, "reports_with_any_page_presented": 2, "reports_historically_fully_presented": 0, "verified_page_feedback_returns": 2, "actual_page_read_requests": 0, "page_read_outcomes": {}, "continuation_reasons": {"not_requested": 2}}`。
反馈无后继原因 `{"current_work_ended_no_reachable_event": 2}`；资源拒绝 `{}`。

### org49-train-LB-r4

最终任务数 0；责任事件计数 `{}`。
实际动作计数 `{"list_files": 2, "read_file": 8, "replace_file": 4, "run_tests": 5, "read_test_result": 1, "fix_patch": 2, "submit_integration": 7, "adopt_candidate": 1, "staff_done": 4}`。
终止原因为 `all_members_stopped_or_no_reachable_event`；不可运行成员 `{}`；休眠唤醒次数 2。
报告页计数 `{"reports_saved": 5, "reports_storage_verified": 5, "reports_with_directory_presented": 5, "reports_with_any_page_presented": 5, "reports_historically_fully_presented": 0, "verified_page_feedback_returns": 6, "actual_page_read_requests": 1, "page_read_outcomes": {"verified": 1}, "continuation_reasons": {"not_requested": 5}}`。
反馈无后继原因 `{"current_work_ended_no_reachable_event": 2}`；资源拒绝 `{}`。

## 解释边界

消息发送、消息原结构实际进入接收者 native input、具体使用和因果贡献是不同事实；本报告只给前两项。页覆盖是某成员、某报告、某版本的历史字符并集，不是同时上下文、理解或必须全读的要求。
staff_done 仅结束当前工作并休眠；可运行性终止与身份永久退休不同。没有唤醒时不伪造后继；已拒绝的 context/fixed/shared 请求不算实际调用或新收费。
报告保留原机械判断、未呈现反馈和每个报告覆盖范围；不将工作采用、R 或消息数量解释成 Contribution 或参数学习收益。
详细原始事件、源文件 SHA、每次真实唤醒来源与反馈/报告明细见同名 JSON。

## 业务拒绝、真实唤醒与采用

三槽无 context / 成员 fixed / 团队预约拒绝，但原件保留 13 次正常工具业务拒绝：`{'submit_integration': 11, 'claim_task': 1, 'replace_file': 1}`。资源拒绝为零不表示全部动作成功；LB r3 的 claim_task 请求失败，未产生任务或责任转移。

记录了 12 次 staff_done 和 6 次其后真实唤醒；触发源为 `{'patch_fixed': 3, 'submit': 3}`，均为较晚伙伴事件，均保留计量且有后续本人实际生成。终态仍为六个原成员实例各自休眠，身份没有退休。

三次原生 adopt_candidate 均确认采用合法固定伙伴文件树，其中 2 次相对本人此前文件表非同值。这里只确认实际文件动作，未推断交付增益、因果贡献或 Contribution。

- org49-train-LA-r4：采用变化路径 `[['event_time.py']]`；业务拒绝 `{'submit_integration': 6}`。
- org49-train-LB-r3：采用变化路径 `[['rules.py']]`；业务拒绝 `{'claim_task': 1, 'replace_file': 1, 'submit_integration': 1}`。
- org49-train-LB-r4：采用变化路径 `[[]]`；业务拒绝 `{'submit_integration': 4}`。

12 个不可变测试报告共 39 页；12 个目录/首段均在本人后继输入出现，另实际补读 5 次，合计 17 次页反馈；仅 2 个报告历史全呈现。未要求全读，也不把未请求的余页当成机械失败。
