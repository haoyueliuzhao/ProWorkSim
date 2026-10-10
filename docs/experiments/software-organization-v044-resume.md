# v0.44 原十二槽续跑与十六槽合并结果

状态：`closed_with_unknowns`；新增原十二槽已知 `3/12`，唯一原十六槽已知 `7/16`。

本轮只修订只读退休归因及宿主续跑入口。原四槽、旧gate=false、原调用与R完整保留；新门读取原144调用重物化证据。模型可见Γ、common3/3、root/seed/顺序、预算和验收不变，无首块重跑或新增样本。

旧执行源码 `e8aa60bd1a427944d8503fb02b30f6379ebd5889`；新测量/启动冻结源码 `67a4da1194cdad7de66d7621bf568261338f4f01`。

| 条件 | 已知/4 | 成功 | 固定提交 | 均值R |
|---|---:|---:|---:|---:|
| SB | 2/4 | 0 | 0 | None |
| ST | 2/4 | 1 | 1 | None |
| PB | 2/4 | 1 | 1 | None |
| PT | 1/4 | 1 | 1 | None |

| 块 | SB | ST | PB | PT | 信息效应 | 说明效应 | 交互 |
|---|---:|---:|---:|---:|---:|---:|---:|
| block-r0-s0 | None | 1 | None | None | None | None | None |
| block-r0-s1 | None | None | 1 | None | None | None | None |
| block-r1-s0 | 0 | 0 | 0 | 1 | 0.5 | 0.5 | 1 |
| block-r1-s1 | 0 | None | None | None | None | None | None |

四块等权平均：`{'split_minus_shared_base': None, 'split_minus_shared_team': None, 'team_minus_base_shared': None, 'team_minus_base_split': None, 'information_main_effect': None, 'framing_main_effect': None, 'interaction': None}`。None代表必要结果未完整，不补零、不按成功筛选。

信息效应=[(PB+PT)−(SB+ST)]/2；说明效应=[(ST+PT)−(SB+PB)]/2；交互=PT−PB−ST+SB。先块内计算，再取原四块等权均值。仅两开发变体、两seed，不作总体稳定性或学习收益推论。

| 槽 | 来源 | 状态 | R | 决定/调用 | 实际token | 测试 | 跨成员工作链 |
|---|---|---|---:|---|---:|---:|---|
| org44-r0-s0-ST | new_original_remaining_twelve | closed | 1 | 39/37 | 494984 | 3 | False |
| org44-r0-s0-PB | new_original_remaining_twelve | not_started | None | None/None | None | None | None |
| org44-r0-s0-PT | new_original_remaining_twelve | not_started | None | None/None | None | None | None |
| org44-r0-s0-SB | new_original_remaining_twelve | not_started | None | None/None | None | None | None |
| org44-r0-s1-PB | new_original_remaining_twelve | closed | 1 | 39/38 | 488412 | 6 | False |
| org44-r0-s1-PT | new_original_remaining_twelve | not_started | None | None/None | None | None | None |
| org44-r0-s1-SB | new_original_remaining_twelve | not_started | None | None/None | None | None | None |
| org44-r0-s1-ST | new_original_remaining_twelve | not_started | None | None/None | None | None | None |
| org44-r1-s0-PT | retained_original_four | closed | 1 | 34/34 | 427430 | 3 | False |
| org44-r1-s0-SB | retained_original_four | closed | 0 | 38/36 | 488652 | 3 | False |
| org44-r1-s0-ST | retained_original_four | closed | 0 | 38/36 | 489388 | 3 | False |
| org44-r1-s0-PB | retained_original_four | closed | 0 | 40/38 | 487376 | 5 | False |
| org44-r1-s1-SB | new_original_remaining_twelve | closed | 0 | 39/37 | 492896 | 3 | False |
| org44-r1-s1-ST | new_original_remaining_twelve | not_started | None | None/None | None | None | None |
| org44-r1-s1-PB | new_original_remaining_twelve | not_started | None | None/None | None | None | None |
| org44-r1-s1-PT | new_original_remaining_twelve | not_started | None | None/None | None | None | None |

执行/测量暂停记录：`[{'kind': 'mechanism_fault', 'reason': 'mechanism_fault', 'worker': 'block-r0-s0', 'observed_at': 1791620085.9538362, 'worker_state': {'worker': 'block-r0-s0', 'status': 'stopped', 'attempted': True, 'gpu': 3, 'gpu_uuid': 'GPU-004a2d75-6298-df4d-7b95-103bc6c1b02a', 'pid': 1736573, 'process_identity': {'pid': 1736573, 'available': True, 'alive': True, 'start_ticks': 404390150, 'state': 'R'}, 'started_at': 1791619506.3254604, 'command': ['/data1/zhuxinrui/projects/ProWorkSim/runs/v016-sdk/resident-venv/bin/python', '-m', 'scripts.software_organization_resume_v044', 'worker', '--run-root', '/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v044-resume', '--worker', 'block-r0-s0', '--output', '/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v044-resume/block-r0-s0/actual'], 'stop_reason': None, 'exit_code': 0, 'ended_at': 1791620085.9538362, 'elapsed_gpu_seconds': 579.6283757686615}}, {'kind': 'paused_before_next_slot', 'reason': 'paused_before_next_slot', 'worker': 'block-r0-s1', 'observed_at': 1791620186.564465, 'worker_state': {'worker': 'block-r0-s1', 'status': 'stopped', 'attempted': True, 'gpu': 4, 'gpu_uuid': 'GPU-ae8978c8-5100-933e-78d1-46ed781a8a0e', 'pid': 1736574, 'process_identity': {'pid': 1736574, 'available': True, 'alive': True, 'start_ticks': 404390150, 'state': 'R'}, 'started_at': 1791619506.3271053, 'command': ['/data1/zhuxinrui/projects/ProWorkSim/runs/v016-sdk/resident-venv/bin/python', '-m', 'scripts.software_organization_resume_v044', 'worker', '--run-root', '/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v044-resume', '--worker', 'block-r0-s1', '--output', '/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v044-resume/block-r0-s1/actual'], 'stop_reason': None, 'exit_code': 0, 'ended_at': 1791620186.564465, 'elapsed_gpu_seconds': 680.2373597621918}}, {'kind': 'paused_before_next_slot', 'reason': 'paused_before_next_slot', 'worker': 'block-r1-s1', 'observed_at': 1791620381.3794816, 'worker_state': {'worker': 'block-r1-s1', 'status': 'stopped', 'attempted': True, 'gpu': 5, 'gpu_uuid': 'GPU-f731a280-01e3-2359-ace9-aa2ad2112f55', 'pid': 1736575, 'process_identity': {'pid': 1736575, 'available': True, 'alive': True, 'start_ticks': 404390150, 'state': 'R'}, 'started_at': 1791619506.3288293, 'command': ['/data1/zhuxinrui/projects/ProWorkSim/runs/v016-sdk/resident-venv/bin/python', '-m', 'scripts.software_organization_resume_v044', 'worker', '--run-root', '/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v044-resume', '--worker', 'block-r1-s1', '--output', '/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v044-resume/block-r1-s1/actual'], 'stop_reason': None, 'exit_code': 0, 'ended_at': 1791620381.3794816, 'elapsed_gpu_seconds': 875.0506522655487}}, {'kind': 'mechanism_fault', 'reason': 'execution_or_feedback_violation', 'details': {'context_blocked_feedback_ids': ['feedback-361']}, 'slot_id': 'org44-r0-s0-ST', 'worker': 'block-r0-s0', 'observed_at': 1791620079.917641, 'feedback': {'path': '/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v044-resume/block-r0-s0/actual/episodes/org44-r0-s0-ST/feedback-loop.json', 'sha256': '32618f795d97140c00097022715df6c7444d308fd38a85fb584d59b4ce404b81'}, 'result': {'path': '/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v044-resume/block-r0-s0/actual/episodes/org44-r0-s0-ST/slot-result.json', 'sha256': '8be101d4801636321c62f1612ab32b7c78c95cc1687f213582caee328e0140a9'}}]`。正常R0、自退役、预算结束不作为样本继续条件。

原四槽成本：`{'episodes_with_recorded_usage': 4, 'recorded_usage': {'decisions': 150, 'attempts': 144, 'prompt_tokens': 1840919, 'completion_tokens': 51927, 'total_tokens': 1892846, 'output_bearing_calls': 144, 'budget_charged_tokens': 1892846, 'uncertain_usage_attempts': 0}, 'run_tests': 14, 'cost_incomplete': False, 'partial_cost_episodes': 0, 'unreported_started_episodes': 0, 'unsettled_attempts': 0, 'partial_episodes_without_settlement_counts': 0, 'attempts_without_reported_token_usage': 0, 'metrics_with_missing_episode_records': {'decisions': 0, 'attempts': 0, 'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0, 'output_bearing_calls': 0, 'budget_charged_tokens': 0, 'uncertain_usage_attempts': 0, 'run_tests': 0}, 'closed_worker_gpu_seconds': 2806.305519104004, 'running_worker_gpu_seconds': 0, 'scope': 'All recorded work, including unsuccessful and technically unknown episodes. Totals are partial when indicated; absent token usage and held reservations are never inferred as actual tokens. Initial environment diagnostics remain separate from member work, nested within worker time.'}`。

新增十二槽成本：`{'episodes_with_recorded_usage': 3, 'recorded_usage': {'decisions': 117, 'attempts': 112, 'prompt_tokens': 1443034, 'completion_tokens': 33258, 'total_tokens': 1476292, 'output_bearing_calls': 112, 'budget_charged_tokens': 1476292, 'uncertain_usage_attempts': 0}, 'run_tests': 12, 'cost_incomplete': False, 'partial_cost_episodes': 0, 'unreported_started_episodes': 0, 'unsettled_attempts': 0, 'partial_episodes_without_settlement_counts': 0, 'attempts_without_reported_token_usage': 0, 'metrics_with_missing_episode_records': {'decisions': 0, 'attempts': 0, 'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0, 'output_bearing_calls': 0, 'budget_charged_tokens': 0, 'uncertain_usage_attempts': 0, 'run_tests': 0}, 'closed_worker_gpu_seconds': 2134.916387796402, 'running_worker_gpu_seconds': 0, 'scope': 'All recorded work, including unsuccessful and technically unknown episodes. Totals are partial when indicated; absent token usage and held reservations are never inferred as actual tokens. Initial environment diagnostics remain separate from member work, nested within worker time.'}`。

合并唯一十六槽成本：`{'episodes_with_recorded_usage': 7, 'recorded_usage': {'decisions': 267, 'attempts': 256, 'prompt_tokens': 3283953, 'completion_tokens': 85185, 'total_tokens': 3369138, 'output_bearing_calls': 256, 'budget_charged_tokens': 3369138, 'uncertain_usage_attempts': 0}, 'run_tests': 26, 'cost_incomplete': False, 'partial_cost_episodes': 0, 'unreported_started_episodes': 0, 'unsettled_attempts': 0, 'partial_episodes_without_settlement_counts': 0, 'attempts_without_reported_token_usage': 0, 'metrics_with_missing_episode_records': {'decisions': 0, 'attempts': 0, 'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0, 'output_bearing_calls': 0, 'budget_charged_tokens': 0, 'uncertain_usage_attempts': 0, 'run_tests': 0}, 'closed_worker_gpu_seconds': 4941.221906900406, 'running_worker_gpu_seconds': 0, 'scope': 'All recorded work, including unsuccessful and technically unknown episodes. Totals are partial when indicated; absent token usage and held reservations are never inferred as actual tokens. Initial environment diagnostics remain separate from member work, nested within worker time.'}`。

原四槽未用107154 token不转移。新增最多1536决定/attempt、6000000实际token、384测试；原实际成本加新增上界为7892846 token。CPU只读修订另列，嵌套沙箱时间不叠加GPU占用。

新增actor/critic/反向 `0/0/0`。仅物理GPU3、4、5、7，最多三驻留worker；旧训练/Contribution/确认/缓存生产继续暂停，无自动后继。

[续跑协议](software-organization-v044-resume-protocol.md)；[审计原文](../reference/audit-v044-resume.md)；[原四槽详细报告](software-organization-v044-final.md)。
