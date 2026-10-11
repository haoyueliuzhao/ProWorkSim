# v0.45原14槽收口与完整库存

状态 `closed_with_unknowns`；新增已知0/14，原唯一库存已知10/24。

原首槽1＋第一次接续9保持，198决定、191调用、2563352token、19测试只计一次。HA/452/S1固定成员预算先于共享预约拒绝的新归因，只读取原准备凭据；原unknown、measurement_pending和首槽global_pause均保留。191反馈＝175呈现＋16无后续，三条结构未知不清零。新运行仅原14未启动槽，不转旧2436648token。

| 制度 | 已知/8 | 成功 | 固定提交 | 完整均值R |
|---|---:|---:|---:|---:|
| S1 | 4/8 | 2 | 2 | None |
| F2 | 3/8 | 2 | 2 | None |
| O3 | 3/8 | 2 | 2 | None |

| 块 | S1 | F2 | O3 | F2−S1 | O3−F2 |
|---|---:|---:|---:|---:|---:|
| block-r0-s0 | 1 | 1 | 1 | 0 | 0 |
| block-r0-s1 | 1 | 1 | 1 | 0 | 0 |
| block-r1-s0 | 0 | 0 | 0 | 0 | 0 |
| block-r1-s1 | 0 | None | None | None | None |
| block-r2-s0 | None | None | None | None | None |
| block-r2-s1 | None | None | None | None | None |
| block-r3-s0 | None | None | None | None | None |
| block-r3-s1 | None | None | None | None | None |

八块等权均差：`{'F2_minus_S1': None, 'O3_minus_F2': None}`。所需结果未齐保持null，未启动不填0，不筛无context子集。

四个人工业务root来自两个相关任务家族。F2−S1是含多私有历史与协调开销的制度组合比较；O3−F2是动态人数选择权，未增员时不推断实际增员收益。S1无伙伴是正常制度，不作为协作失败。

| slot | 阶段 | 状态 | R | 提交 | 决定/调用 | 实际token | 宿主决定 | 已证实使用 | 连至固定交付 | 语义待审 |
|---|---|---|---:|---|---|---:|---|---|---|---:|
| org45-r0-s0-S1 | retained_first_slot | closed | 1 | True | 7/7 | 87890 | continue | False | False | 0 |
| org45-r0-s0-F2 | retained_first_resume_nine | closed | 1 | True | 13/13 | 161382 | continue | False | False | 0 |
| org45-r0-s0-O3 | retained_first_resume_nine | closed | 1 | True | 21/20 | 248775 | continue | False | False | 0 |
| org45-r0-s1-F2 | retained_first_resume_nine | closed | 1 | True | 14/14 | 166446 | continue | False | False | 0 |
| org45-r0-s1-O3 | retained_first_resume_nine | closed | 1 | True | 17/17 | 207680 | continue | False | False | 0 |
| org45-r0-s1-S1 | retained_first_resume_nine | closed | 1 | True | 10/10 | 127709 | continue | False | False | 0 |
| org45-r1-s0-O3 | retained_first_resume_nine | closed | 0 | False | 36/34 | 489606 | continue | False | False | 0 |
| org45-r1-s0-S1 | retained_first_resume_nine | closed | 0 | False | 7/6 | 77766 | continue | False | False | 0 |
| org45-r1-s0-F2 | retained_first_resume_nine | closed | 0 | False | 37/35 | 497536 | continue | False | False | 0 |
| org45-r1-s1-S1 | retained_first_resume_nine | closed | 0 | False | 36/35 | 498562 | continue | False | False | 0 |
| org45-r1-s1-O3 | original_remaining_fourteen | not_started | None | None | None/None | None | None | None | None | None |
| org45-r1-s1-F2 | original_remaining_fourteen | not_started | None | None | None/None | None | None | None | None | None |
| org45-r2-s0-O3 | original_remaining_fourteen | not_started | None | None | None/None | None | None | None | None | None |
| org45-r2-s0-F2 | original_remaining_fourteen | not_started | None | None | None/None | None | None | None | None | None |
| org45-r2-s0-S1 | original_remaining_fourteen | not_started | None | None | None/None | None | None | None | None | None |
| org45-r2-s1-F2 | original_remaining_fourteen | not_started | None | None | None/None | None | None | None | None | None |
| org45-r2-s1-S1 | original_remaining_fourteen | not_started | None | None | None/None | None | None | None | None | None |
| org45-r2-s1-O3 | original_remaining_fourteen | not_started | None | None | None/None | None | None | None | None | None |
| org45-r3-s0-S1 | original_remaining_fourteen | not_started | None | None | None/None | None | None | None | None | None |
| org45-r3-s0-F2 | original_remaining_fourteen | not_started | None | None | None/None | None | None | None | None | None |
| org45-r3-s0-O3 | original_remaining_fourteen | not_started | None | None | None/None | None | None | None | None | None |
| org45-r3-s1-F2 | original_remaining_fourteen | not_started | None | None | None/None | None | None | None | None | None |
| org45-r3-s1-O3 | original_remaining_fourteen | not_started | None | None | None/None | None | None | None | None | None |
| org45-r3-s1-S1 | original_remaining_fourteen | not_started | None | None | None/None | None | None | None | None | None |

新暂停：`[{'kind': 'execution_fault', 'reason': 'worker_exception', 'worker': 'block-r1-s1', 'observed_at': 1791680779.5869064, 'error': {'type': 'ModuleNotFoundError', 'message': "No module named 'torch'"}}, {'kind': 'execution_fault', 'reason': 'worker_exit_error', 'worker': 'block-r1-s1', 'observed_at': 1791680783.9116879, 'worker_state': {'worker': 'block-r1-s1', 'status': 'stopped', 'attempted': True, 'gpu': 4, 'gpu_uuid': 'GPU-ae8978c8-5100-933e-78d1-46ed781a8a0e', 'pid': 4000079, 'process_identity': {'pid': 4000079, 'available': True, 'alive': True, 'start_ticks': 410517402, 'state': 'R'}, 'started_at': 1791680778.8443878, 'command': ['/data1/zhuxinrui/projects/ProWorkSim/.venv/bin/python', '-m', 'scripts.software_organization_complete_v045', 'worker', '--run-root', '/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v045-complete', '--worker', 'block-r1-s1', '--output', '/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v045-complete/block-r1-s1/actual'], 'stop_reason': 'worker_exit_error', 'exit_code': 1, 'ended_at': 1791680783.9116879, 'elapsed_gpu_seconds': 5.067300081253052}}]`。旧暂停另存不改；安全局部资源終止仍留在对应槽，真实完整性故障/缺证依原规则暂停。

全部实际费用：`{'episodes_with_recorded_usage': 10, 'recorded_usage': {'decisions': 198, 'attempts': 191, 'prompt_tokens': 2442944, 'completion_tokens': 120408, 'total_tokens': 2563352, 'output_bearing_calls': 191, 'budget_charged_tokens': 2563352, 'uncertain_usage_attempts': 0}, 'run_tests': 19, 'cost_incomplete': False, 'partial_cost_episodes': 0, 'unreported_started_episodes': 0, 'unsettled_attempts': 0, 'partial_episodes_without_settlement_counts': 0, 'attempts_without_reported_token_usage': 0, 'metrics_with_missing_episode_records': {'decisions': 0, 'attempts': 0, 'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0, 'output_bearing_calls': 0, 'budget_charged_tokens': 0, 'uncertain_usage_attempts': 0, 'run_tests': 0}, 'closed_worker_gpu_seconds': 6143.67601442337, 'running_worker_gpu_seconds': 0, 'scope': 'All recorded work, including unsuccessful and technically unknown episodes. Totals are partial when indicated; absent token usage and held reservations are never inferred as actual tokens. Initial environment diagnostics remain separate from member work, nested within worker time.'}`。首槽、第一次接续9与本阶段14的worker分阶段计一次；GPU未按条件分摊为null，CPU/测试/验收子时不重复加GPU占用。

仅物理GPU3/4/5/7、最多3驻留；新14上限1792决定/attempt、7000000token、448tests。加旧10槽实际上界1990决定、1983attempt、9563352token、467tests。

新增actor/critic/反向 0/0/0，训练/Contribution/独立确认资格false；C/A探针未启用，旧队列暂停，无自动后继。

[原14槽收口协议](software-organization-v045-complete-protocol.md) · [原协议](software-organization-v045-protocol.md) · [原10槽封存报告](software-organization-v045-final.md)
