# v0.44 批次停止政策修订后的原九槽收口

状态 `complete`；新九槽已知 `9/9`，唯一原十六槽已知 `16/16`。

本轮明确修订批次停止作用域。模型可见工作条件与单成员/episode处理不变；充分绑定的安全局部context终止保留为工作结果，不再自动取消其它独立episode。真实权限、身份、输入、计费、原始记录或共同服务故障仍暂停，证据不足保持测量未决。对R0/R1及提交前后相同，不补生成、不复活成员、不改未呈现反馈。

原4及前次接续3全部保留，旧false、修订true和真实ST context停止事实不改。只运行原剩余9槽，无新seed、新首块、新16槽或后继24条研究。原9B完整common3/3、16K/2048及每槽128决定/attempt、500000实际token、32测试不变；旧130862 token不转移。

本次实际宿主源 `519a18c4e9397b008a16bf1f40b12726feb34804`；原两阶段源 `e8aa60bd1a427944d8503fb02b30f6379ebd5889` / `67a4da1194cdad7de66d7621bf568261338f4f01`。

| 条件 | 已知/4 | 成功 | 固定提交 | 均值R |
|---|---:|---:|---:|---:|
| SB | 4/4 | 2 | 2 | 0.5 |
| ST | 4/4 | 2 | 2 | 0.5 |
| PB | 4/4 | 2 | 2 | 0.5 |
| PT | 4/4 | 3 | 3 | 0.75 |

| 块 | SB | ST | PB | PT | 信息效应 | 说明效应 | 交互 |
|---|---:|---:|---:|---:|---:|---:|---:|
| block-r0-s0 | 1 | 1 | 1 | 0 | -0.5 | -0.5 | -1 |
| block-r0-s1 | 1 | 0 | 1 | 1 | 0.5 | -0.5 | 1 |
| block-r1-s0 | 0 | 0 | 0 | 1 | 0.5 | 0.5 | 1 |
| block-r1-s1 | 0 | 1 | 0 | 1 | 0.0 | 1.0 | 0 |

原四块等权平均：`{'split_minus_shared_base': 0.0, 'split_minus_shared_team': 0.25, 'team_minus_base_shared': 0.0, 'team_minus_base_split': 0.25, 'information_main_effect': 0.125, 'framing_main_effect': 0.125, 'interaction': 0.25}`。None代表必要结果未完整，不补零。

信息效应=[PB+PT−SB−ST]/2；说明效应=[ST+PT−SB−PB]/2；交互=PT−PB−ST+SB。固定16K与预算下，此为信息布局、取得成本、历史容量及模型行为共同作用的有限开发比较，不是去除容量影响后的纯协作效应或总体稳定收益。

| slot | 阶段 | 状态 | R | 提交 | 决定/调用 | 实际token | context反馈未见数 | 新批次决定 | 跨成员链 |
|---|---|---|---:|---|---|---:|---:|---|---|
| org44-r0-s0-ST | retained_first_continuation_three | closed | 1 | True | 39/37 | 494984 | 1 | None | False |
| org44-r0-s0-PB | new_original_remaining_nine | closed | 1 | True | 41/39 | 493605 | 0 | continue | False |
| org44-r0-s0-PT | new_original_remaining_nine | closed | 0 | False | 41/39 | 496871 | 0 | continue | False |
| org44-r0-s0-SB | new_original_remaining_nine | closed | 1 | True | 38/37 | 484969 | 0 | continue | False |
| org44-r0-s1-PB | retained_first_continuation_three | closed | 1 | True | 39/38 | 488412 | 0 | None | False |
| org44-r0-s1-PT | new_original_remaining_nine | closed | 1 | True | 40/38 | 487669 | 0 | continue | False |
| org44-r0-s1-SB | new_original_remaining_nine | closed | 1 | True | 19/17 | 211161 | 2 | continue | False |
| org44-r0-s1-ST | new_original_remaining_nine | closed | 0 | False | 39/37 | 497170 | 1 | continue | False |
| org44-r1-s0-PT | retained_original_four | closed | 1 | True | 34/34 | 427430 | 0 | None | False |
| org44-r1-s0-SB | retained_original_four | closed | 0 | False | 38/36 | 488652 | 0 | None | False |
| org44-r1-s0-ST | retained_original_four | closed | 0 | False | 38/36 | 489388 | 0 | None | False |
| org44-r1-s0-PB | retained_original_four | closed | 0 | False | 40/38 | 487376 | 0 | None | False |
| org44-r1-s1-SB | retained_first_continuation_three | closed | 0 | False | 39/37 | 492896 | 0 | None | False |
| org44-r1-s1-ST | new_original_remaining_nine | closed | 1 | True | 40/38 | 495069 | 0 | continue | False |
| org44-r1-s1-PB | new_original_remaining_nine | closed | 0 | False | 40/38 | 485910 | 0 | continue | False |
| org44-r1-s1-PT | new_original_remaining_nine | closed | 1 | True | 40/38 | 490699 | 0 | continue | False |

新全局暂停：`[]`。旧停止记录原样留在历史运行目录，不伪装所有旧门曾通过。

retained_original_four成本：`{'episodes_with_recorded_usage': 4, 'recorded_usage': {'decisions': 150, 'attempts': 144, 'prompt_tokens': 1840919, 'completion_tokens': 51927, 'total_tokens': 1892846, 'output_bearing_calls': 144, 'budget_charged_tokens': 1892846, 'uncertain_usage_attempts': 0}, 'run_tests': 14, 'cost_incomplete': False, 'partial_cost_episodes': 0, 'unreported_started_episodes': 0, 'unsettled_attempts': 0, 'partial_episodes_without_settlement_counts': 0, 'attempts_without_reported_token_usage': 0, 'metrics_with_missing_episode_records': {'decisions': 0, 'attempts': 0, 'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0, 'output_bearing_calls': 0, 'budget_charged_tokens': 0, 'uncertain_usage_attempts': 0, 'run_tests': 0}, 'closed_worker_gpu_seconds': 2806.305519104004, 'running_worker_gpu_seconds': 0, 'scope': 'All recorded work, including unsuccessful and technically unknown episodes. Totals are partial when indicated; absent token usage and held reservations are never inferred as actual tokens. Initial environment diagnostics remain separate from member work, nested within worker time.'}`。

retained_first_continuation_three成本：`{'episodes_with_recorded_usage': 3, 'recorded_usage': {'decisions': 117, 'attempts': 112, 'prompt_tokens': 1443034, 'completion_tokens': 33258, 'total_tokens': 1476292, 'output_bearing_calls': 112, 'budget_charged_tokens': 1476292, 'uncertain_usage_attempts': 0}, 'run_tests': 12, 'cost_incomplete': False, 'partial_cost_episodes': 0, 'unreported_started_episodes': 0, 'unsettled_attempts': 0, 'partial_episodes_without_settlement_counts': 0, 'attempts_without_reported_token_usage': 0, 'metrics_with_missing_episode_records': {'decisions': 0, 'attempts': 0, 'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0, 'output_bearing_calls': 0, 'budget_charged_tokens': 0, 'uncertain_usage_attempts': 0, 'run_tests': 0}, 'closed_worker_gpu_seconds': 2134.916387796402, 'running_worker_gpu_seconds': 0, 'scope': 'All recorded work, including unsuccessful and technically unknown episodes. Totals are partial when indicated; absent token usage and held reservations are never inferred as actual tokens. Initial environment diagnostics remain separate from member work, nested within worker time.'}`。

new_original_remaining_nine成本：`{'episodes_with_recorded_usage': 9, 'recorded_usage': {'decisions': 338, 'attempts': 321, 'prompt_tokens': 4060098, 'completion_tokens': 83025, 'total_tokens': 4143123, 'output_bearing_calls': 321, 'budget_charged_tokens': 4143123, 'uncertain_usage_attempts': 0}, 'run_tests': 43, 'cost_incomplete': False, 'partial_cost_episodes': 0, 'unreported_started_episodes': 0, 'unsettled_attempts': 0, 'partial_episodes_without_settlement_counts': 0, 'attempts_without_reported_token_usage': 0, 'metrics_with_missing_episode_records': {'decisions': 0, 'attempts': 0, 'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0, 'output_bearing_calls': 0, 'budget_charged_tokens': 0, 'uncertain_usage_attempts': 0, 'run_tests': 0}, 'closed_worker_gpu_seconds': 4912.431447982788, 'running_worker_gpu_seconds': 0, 'scope': 'All recorded work, including unsuccessful and technically unknown episodes. Totals are partial when indicated; absent token usage and held reservations are never inferred as actual tokens. Initial environment diagnostics remain separate from member work, nested within worker time.'}`。

逻辑原16全部实际成本：`{'episodes_with_recorded_usage': 16, 'recorded_usage': {'decisions': 605, 'attempts': 577, 'prompt_tokens': 7344051, 'completion_tokens': 168210, 'total_tokens': 7512261, 'output_bearing_calls': 577, 'budget_charged_tokens': 7512261, 'uncertain_usage_attempts': 0}, 'run_tests': 69, 'cost_incomplete': False, 'partial_cost_episodes': 0, 'unreported_started_episodes': 0, 'unsettled_attempts': 0, 'partial_episodes_without_settlement_counts': 0, 'attempts_without_reported_token_usage': 0, 'metrics_with_missing_episode_records': {'decisions': 0, 'attempts': 0, 'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0, 'output_bearing_calls': 0, 'budget_charged_tokens': 0, 'uncertain_usage_attempts': 0, 'run_tests': 0}, 'closed_worker_gpu_seconds': 9853.653354883194, 'running_worker_gpu_seconds': 0, 'scope': 'All recorded work, including unsuccessful and technically unknown episodes. Totals are partial when indicated; absent token usage and held reservations are never inferred as actual tokens. Initial environment diagnostics remain separate from member work, nested within worker time.'}`。

新九槽上限1152决定/attempt、4500000实际token、288测试；原七实际加新增上界1419决定、1408attempt、7869138token、314测试。三阶段成本各计一次，同名worker按阶段分列。CPU修订与嵌套测试/验收成本另列。

新增actor/critic/反向 `0/0/0`。仅GPU3、4、5、7，最多三驻留；旧训练/Contribution/正式更新/确认/缓存生产继续暂停，无自动后继。

[冻结收口协议](software-organization-v044-completion-protocol.md)；[新审计](../reference/audit-v044-resume-next-completion.md)；[前次接续报告](software-organization-v044-resume-final.md)。
