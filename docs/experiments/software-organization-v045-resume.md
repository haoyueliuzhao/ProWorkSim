# v0.45原23槽接续与完整库存

状态 `closed_with_unknowns`；新增已知9/23，原唯一库存已知10/24。

首槽S1成功、7调用/87890token保留。旧测量误要求v042接口标签，实际v045输入因此被判投影违规；旧global_pause原件保留。新增隔离测量只修严格接口身份绑定，原投影/分页/退休/停止算法及src工作条件不变。首槽7输入只读核对通过后接续23未启动槽，不重采首槽，不转其未用412110token。

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
| org45-r0-s0-F2 | original_remaining_twenty_three | closed | 1 | True | 13/13 | 161382 | continue | False | False | 0 |
| org45-r0-s0-O3 | original_remaining_twenty_three | closed | 1 | True | 21/20 | 248775 | continue | False | False | 0 |
| org45-r0-s1-F2 | original_remaining_twenty_three | closed | 1 | True | 14/14 | 166446 | continue | False | False | 0 |
| org45-r0-s1-O3 | original_remaining_twenty_three | closed | 1 | True | 17/17 | 207680 | continue | False | False | 0 |
| org45-r0-s1-S1 | original_remaining_twenty_three | closed | 1 | True | 10/10 | 127709 | continue | False | False | 0 |
| org45-r1-s0-O3 | original_remaining_twenty_three | closed | 0 | False | 36/34 | 489606 | continue | False | False | 0 |
| org45-r1-s0-S1 | original_remaining_twenty_three | closed | 0 | False | 7/6 | 77766 | continue | False | False | 0 |
| org45-r1-s0-F2 | original_remaining_twenty_three | closed | 0 | False | 37/35 | 497536 | continue | False | False | 0 |
| org45-r1-s1-S1 | original_remaining_twenty_three | closed | 0 | False | 36/35 | 498562 | measurement_pending | None | None | 0 |
| org45-r1-s1-O3 | original_remaining_twenty_three | not_started | None | None | None/None | None | None | None | None | None |
| org45-r1-s1-F2 | original_remaining_twenty_three | not_started | None | None | None/None | None | None | None | None | None |
| org45-r2-s0-O3 | original_remaining_twenty_three | not_started | None | None | None/None | None | None | None | None | None |
| org45-r2-s0-F2 | original_remaining_twenty_three | not_started | None | None | None/None | None | None | None | None | None |
| org45-r2-s0-S1 | original_remaining_twenty_three | not_started | None | None | None/None | None | None | None | None | None |
| org45-r2-s1-F2 | original_remaining_twenty_three | not_started | None | None | None/None | None | None | None | None | None |
| org45-r2-s1-S1 | original_remaining_twenty_three | not_started | None | None | None/None | None | None | None | None | None |
| org45-r2-s1-O3 | original_remaining_twenty_three | not_started | None | None | None/None | None | None | None | None | None |
| org45-r3-s0-S1 | original_remaining_twenty_three | not_started | None | None | None/None | None | None | None | None | None |
| org45-r3-s0-F2 | original_remaining_twenty_three | not_started | None | None | None/None | None | None | None | None | None |
| org45-r3-s0-O3 | original_remaining_twenty_three | not_started | None | None | None/None | None | None | None | None | None |
| org45-r3-s1-F2 | original_remaining_twenty_three | not_started | None | None | None/None | None | None | None | None | None |
| org45-r3-s1-O3 | original_remaining_twenty_three | not_started | None | None | None/None | None | None | None | None | None |
| org45-r3-s1-S1 | original_remaining_twenty_three | not_started | None | None | None/None | None | None | None | None | None |

新暂停：`[{'kind': 'measurement_pending', 'reason': 'measurement_pending', 'worker': 'block-r1-s1', 'observed_at': 1791644923.5837874, 'worker_state': {'worker': 'block-r1-s1', 'status': 'stopped', 'attempted': True, 'gpu': 4, 'gpu_uuid': 'GPU-ae8978c8-5100-933e-78d1-46ed781a8a0e', 'pid': 2586067, 'process_identity': {'pid': 2586067, 'available': True, 'alive': True, 'start_ticks': 406798224, 'state': 'R'}, 'started_at': 1791643587.0654118, 'command': ['/data1/zhuxinrui/projects/ProWorkSim/runs/v016-sdk/resident-venv/bin/python', '-m', 'scripts.software_organization_resume_v045', 'worker', '--run-root', '/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v045-resume', '--worker', 'block-r1-s1', '--output', '/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v045-resume/block-r1-s1/actual'], 'stop_reason': None, 'exit_code': 0, 'ended_at': 1791644923.5837874, 'elapsed_gpu_seconds': 1336.518375635147}}, {'kind': 'measurement_pending', 'reason': 'batch_stop_policy_assessment', 'slot_id': 'org45-r1-s1-S1', 'worker': 'block-r1-s1', 'observed_at': 1791644921.4868832, 'assessment': {'path': '/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v045-resume/block-r1-s1/actual/episodes/org45-r1-s1-S1/batch-stop-assessment.json', 'sha256': '283b1281eeef998a52ddd8a4141890faf4e07712cb2438511ab750265f7bd089'}, 'feedback': {'path': '/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v045-resume/block-r1-s1/actual/episodes/org45-r1-s1-S1/feedback-loop.json', 'sha256': '8beb03b00af8a0aa75fafc18fa613b3e60e0863fa68b2757bb497ba846f7ef21'}, 'result': {'path': '/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v045-resume/block-r1-s1/actual/episodes/org45-r1-s1-S1/slot-result.json', 'sha256': '9e80ee2a9750a853781f809352e4c477980803bb91d6af234a597d04af6a22af'}}]`。旧暂停另存不改；安全局部资源終止仍留在对应槽，真实完整性故障/缺证依原规则暂停。

全部实际费用：`{'episodes_with_recorded_usage': 10, 'recorded_usage': {'decisions': 198, 'attempts': 191, 'prompt_tokens': 2442944, 'completion_tokens': 120408, 'total_tokens': 2563352, 'output_bearing_calls': 191, 'budget_charged_tokens': 2563352, 'uncertain_usage_attempts': 0}, 'run_tests': 19, 'cost_incomplete': False, 'partial_cost_episodes': 0, 'unreported_started_episodes': 0, 'unsettled_attempts': 0, 'partial_episodes_without_settlement_counts': 0, 'attempts_without_reported_token_usage': 0, 'metrics_with_missing_episode_records': {'decisions': 0, 'attempts': 0, 'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0, 'output_bearing_calls': 0, 'budget_charged_tokens': 0, 'uncertain_usage_attempts': 0, 'run_tests': 0}, 'closed_worker_gpu_seconds': 6138.608714342117, 'running_worker_gpu_seconds': 0, 'scope': 'All recorded work, including unsuccessful and technically unknown episodes. Totals are partial when indicated; absent token usage and held reservations are never inferred as actual tokens. Initial environment diagnostics remain separate from member work, nested within worker time.'}`。首阶段与本阶段worker分阶段计一次；GPU未按条件分摊为null，CPU/测试/验收子时不重复加GPU占用。

仅物理GPU3/4/5/7、最多3驻留；新23上限2944决定/attempt、11500000token、736tests。加首槽实际上界2951决定/attempt、11587890token、738tests。

新增actor/critic/反向 0/0/0，训练/Contribution/独立确认资格false；C/A探针未启用，旧队列暂停，无自动后继。

[接续协议](software-organization-v045-resume-protocol.md) · [原协议](software-organization-v045-protocol.md) · [原首槽自动报告](software-organization-v045.md)
