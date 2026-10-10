# v0.45 冻结模型组织诊断

状态 `closed_with_unknowns`；已知 `1/24`。四个人工派生业务root、两个任务家族、两个seed，八个配对块。

S1真实单成员；F2固定两名出生集合、可退休不补员；O3初始两名、活动≤4、累计≤6。同根目标与公共事实、中性说明、空任务表，允许集中完成。

原9B完整common3/3冻结；16K/2048、3072精确分页，每槽128决定/attempt、500000实际token、32测试；不转旧预算。

| 条件 | 已知/8 | 成功 | 提交 | 完整条件均值 |
|---|---:|---:|---:|---:|
| S1 | 1/8 | 1 | 1 | None |
| F2 | 0/8 | 0 | 0 | None |
| O3 | 0/8 | 0 | 0 | None |

| 块 | root | S1 | F2 | O3 | F2−S1 | O3−F2 |
|---|---|---:|---:|---:|---:|---:|
| block-r0-s0 | LA | 1 | None | None | None | None |
| block-r0-s1 | LA | None | None | None | None | None |
| block-r1-s0 | HA | None | None | None | None | None |
| block-r1-s1 | HA | None | None | None | None | None |
| block-r2-s0 | LB | None | None | None | None | None |
| block-r2-s1 | LB | None | None | None | None | None |
| block-r3-s0 | HB | None | None | None | None | None |
| block-r3-s1 | HB | None | None | None | None | None |

原八块等权均差：`{'F2_minus_S1': None, 'O3_minus_F2': None}`。必要结果未齐保持null，不填零、不筛context-free子集。

F2−S1含多份私有历史、多个行动者与协调开销；O3−F2是动态人数选择权比较。没有实际出生时，不能解释成已测得增员收益。24episode不是24独立任务来源。

| slot | 状态 | R | 提交 | 决定/调用 | 实际token | context反馈未见 | 宿主决定 | 已证实使用 | 连至固定交付 | 待审语义关系 |
|---|---|---:|---|---|---:|---:|---|---|---|---:|
| org45-r0-s0-S1 | closed | 1 | True | 7/7 | 87890 | 0 | global_pause | False | False | 0 |
| org45-r0-s0-F2 | not_started | None | None | None/None | None | None | None | None | None | None |
| org45-r0-s0-O3 | not_started | None | None | None/None | None | None | None | None | None | None |
| org45-r0-s1-F2 | not_started | None | None | None/None | None | None | None | None | None | None |
| org45-r0-s1-O3 | not_started | None | None | None/None | None | None | None | None | None | None |
| org45-r0-s1-S1 | not_started | None | None | None/None | None | None | None | None | None | None |
| org45-r1-s0-O3 | not_started | None | None | None/None | None | None | None | None | None | None |
| org45-r1-s0-S1 | not_started | None | None | None/None | None | None | None | None | None | None |
| org45-r1-s0-F2 | not_started | None | None | None/None | None | None | None | None | None | None |
| org45-r1-s1-S1 | not_started | None | None | None/None | None | None | None | None | None | None |
| org45-r1-s1-O3 | not_started | None | None | None/None | None | None | None | None | None | None |
| org45-r1-s1-F2 | not_started | None | None | None/None | None | None | None | None | None | None |
| org45-r2-s0-O3 | not_started | None | None | None/None | None | None | None | None | None | None |
| org45-r2-s0-F2 | not_started | None | None | None/None | None | None | None | None | None | None |
| org45-r2-s0-S1 | not_started | None | None | None/None | None | None | None | None | None | None |
| org45-r2-s1-F2 | not_started | None | None | None/None | None | None | None | None | None | None |
| org45-r2-s1-S1 | not_started | None | None | None/None | None | None | None | None | None | None |
| org45-r2-s1-O3 | not_started | None | None | None/None | None | None | None | None | None | None |
| org45-r3-s0-S1 | not_started | None | None | None/None | None | None | None | None | None | None |
| org45-r3-s0-F2 | not_started | None | None | None/None | None | None | None | None | None | None |
| org45-r3-s0-O3 | not_started | None | None | None/None | None | None | None | None | None | None |
| org45-r3-s1-F2 | not_started | None | None | None/None | None | None | None | None | None | None |
| org45-r3-s1-O3 | not_started | None | None | None/None | None | None | None | None | None | None |
| org45-r3-s1-S1 | not_started | None | None | None/None | None | None | None | None | None | None |

当前成果产生、合法公开、实际取得、可核验使用、连至最终固定交付分别记录。初始代码与诊断不冒作成员新成果；阅读不等于使用，合作后失败保留原使用链与失败。

全部实际成本：`{'episodes_with_recorded_usage': 1, 'recorded_usage': {'decisions': 7, 'attempts': 7, 'prompt_tokens': 86263, 'completion_tokens': 1627, 'total_tokens': 87890, 'output_bearing_calls': 7, 'budget_charged_tokens': 87890, 'uncertain_usage_attempts': 0}, 'run_tests': 2, 'cost_incomplete': False, 'partial_cost_episodes': 0, 'unreported_started_episodes': 0, 'unsettled_attempts': 0, 'partial_episodes_without_settlement_counts': 0, 'attempts_without_reported_token_usage': 0, 'metrics_with_missing_episode_records': {'decisions': 0, 'attempts': 0, 'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0, 'output_bearing_calls': 0, 'budget_charged_tokens': 0, 'uncertain_usage_attempts': 0, 'run_tests': 0}, 'closed_worker_gpu_seconds': 129.69554543495178, 'running_worker_gpu_seconds': 0, 'scope': 'All recorded work, including unsuccessful and technically unknown episodes. Totals are partial when indicated; absent token usage and held reservations are never inferred as actual tokens. Initial environment diagnostics remain separate from member work, nested within worker time.'}`。未按条件分摊GPU worker时间，条件级对应字段为null。嵌套CPU/测试/验收不重复加到worker GPU时间。

全局暂停：`[{'kind': 'global_pause', 'reason': 'global_pause', 'worker': 'block-r0-s0', 'observed_at': 1791639573.7657707, 'worker_state': {'worker': 'block-r0-s0', 'status': 'stopped', 'attempted': True, 'gpu': 5, 'gpu_uuid': 'GPU-f731a280-01e3-2359-ace9-aa2ad2112f55', 'pid': 2508634, 'process_identity': {'pid': 2508634, 'available': True, 'alive': True, 'start_ticks': 406383924, 'state': 'R'}, 'started_at': 1791639444.0702252, 'command': ['/data1/zhuxinrui/projects/ProWorkSim/runs/v016-sdk/resident-venv/bin/python', '-m', 'scripts.software_organization_v045', 'worker', '--run-root', '/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v045', '--worker', 'block-r0-s0', '--output', '/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v045/block-r0-s0/actual'], 'stop_reason': None, 'exit_code': 0, 'ended_at': 1791639573.7657707, 'elapsed_gpu_seconds': 129.69554543495178}}, {'kind': 'global_pause', 'reason': 'batch_stop_policy_assessment', 'slot_id': 'org45-r0-s0-S1', 'worker': 'block-r0-s0', 'observed_at': 1791639571.9831424, 'assessment': {'path': '/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v045/block-r0-s0/actual/episodes/org45-r0-s0-S1/batch-stop-assessment.json', 'sha256': '7481f6a3b9f1eab2593dd97fed11694bd22deace9af0743147d2a2282d8256d0'}, 'feedback': {'path': '/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v045/block-r0-s0/actual/episodes/org45-r0-s0-S1/feedback-loop.json', 'sha256': '0c283cf2a75269eda7fe79a867e8b33ebddd847a8212e386807c7df3106c9bf1'}, 'result': {'path': '/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v045/block-r0-s0/actual/episodes/org45-r0-s0-S1/slot-result.json', 'sha256': '565249dba538f691b981e59ba1a829cce9a38011d85cbee432388e3d433a2190'}}]`。已知安全局部终止保留成员停止与未呈现反馈，继续其它独立槽；输入、权限、身份、账目、记录或共同服务故障仍暂停，缺证pending。

新增actor/critic/反向：0/0/0。旧训练/Contribution/正式更新/独立确认及缓存生产暂停，无自动后继。

额外C/A探针未启用，没有自动追加预算。

[冻结协议](software-organization-v045-protocol.md) · [新审计](../reference/audit-v044-complete-next-v045.md)
