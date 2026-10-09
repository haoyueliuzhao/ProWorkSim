# v0.40 互补技术证据与共同工作定位

状态：`complete`；原16槽中正式结果已知`16/16`。执行源码`2de5c032f87c06193942b9510318e32480fe9bc6`。

SB=shared/base，ST=shared/team，PB=split/base，PT=split/team。两个承接态root与两个新seed构成4个完整配对块；每块四条件共享相同初态代码、根要求、先手、测试和总预算。所有条件初始2人、允许自主增员（活动≤4/累计≤6），无外生出生。

原9B 3/3 common，16K/2048，每槽128决定/attempt、500000实际token、32次测试。环境事先实际运行两组公开检查，shared两人各获两份，split各获一份；成员可自己同权限检查重得信息。G-team额外的共同交付说明是明确提示干预，信息位置和说明都会影响输入长度与取得成本。

| 条件 | 已知/计划 | 已知成功 | 已知固定提交 | 自然出生 | 全4槽平均R |
|---|---:|---:|---:|---:|---:|
| SB | 4/4 | 0 | 0 | 0 | 0.0 |
| ST | 4/4 | 0 | 0 | 0 | 0.0 |
| PB | 4/4 | 0 | 0 | 0 | 0.0 |
| PT | 4/4 | 0 | 0 | 0 | 0.0 |

| 条件 | 已证实跨成员链 | 完整记录未证实 | 未知/未测量 | 可恢复未知名字/参数错误 | 禁止过程请求 |
|---|---:|---:|---:|---|---:|
| SB | 0 | 4 | 0 | 0/0 | 0 |
| ST | 0 | 4 | 0 | 0/0 | 0 |
| PB | 0 | 4 | 0 | 0/0 | 0 |
| PT | 0 | 4 | 0 | 0/0 | 0 |

工作链列为保守机械证据；信息语义候选、复杂关系或未测量保持未知，不以0代替。测试是否通过、是否连接最后交付及正式R分别记录。

| 配对块 | SB | ST | PB | PT | 信息主效应 | 说明主效应 | 交互 |
|---|---:|---:|---:|---:|---:|---:|---:|
| block-r0-s0 | 0 | 0 | 0 | 0 | 0.0 | 0.0 | 0 |
| block-r0-s1 | 0 | 0 | 0 | 0 | 0.0 | 0.0 | 0 |
| block-r1-s0 | 0 | 0 | 0 | 0 | 0.0 | 0.0 | 0 |
| block-r1-s1 | 0 | 0 | 0 | 0 | 0.0 | 0.0 | 0 |

全库存平均对比：`{'split_minus_shared_base': 0.0, 'split_minus_shared_team': 0.0, 'team_minus_base_shared': 0.0, 'team_minus_base_split': 0.0, 'information_main_effect': 0.0, 'framing_main_effect': 0.0, 'interaction': 0.0}`。None表示所需配对未完整，未知或未启动不填零。

信息主效应=[(PB+PT)−(SB+ST)]/2；说明主效应=[(ST+PT)−(SB+PB)]/2；交互=PT−PB−ST+SB。每项先在root/seed块内计算，再取原4块平均。这是两root有限开发观察，不是总体稳定性认证。

| slot | 状态 | R | 提交 | 决定/调用 | 输入/输出token | 初始/累计人数 | 测试 |
|---|---|---:|---|---|---|---|---:|
| org40-r0-s0-SB | closed | 0 | False | 13/11 | 146421/1906 | 2/2 | 1 |
| org40-r0-s0-ST | closed | 0 | False | 4/2 | 19168/464 | 2/2 | 0 |
| org40-r0-s0-PB | closed | 0 | False | 19/17 | 220400/4173 | 2/2 | 2 |
| org40-r0-s0-PT | closed | 0 | False | 12/10 | 121955/2167 | 2/2 | 2 |
| org40-r0-s1-ST | closed | 0 | False | 4/2 | 19192/355 | 2/2 | 0 |
| org40-r0-s1-PB | closed | 0 | False | 12/10 | 121564/2350 | 2/2 | 2 |
| org40-r0-s1-PT | closed | 0 | False | 15/13 | 164049/3711 | 2/2 | 2 |
| org40-r0-s1-SB | closed | 0 | False | 6/4 | 47355/597 | 2/2 | 0 |
| org40-r1-s0-PB | closed | 0 | False | 12/10 | 124824/2715 | 2/2 | 2 |
| org40-r1-s0-PT | closed | 0 | False | 11/9 | 112514/2298 | 2/2 | 2 |
| org40-r1-s0-SB | closed | 0 | False | 4/2 | 19569/468 | 2/2 | 0 |
| org40-r1-s0-ST | closed | 0 | False | 4/2 | 19727/302 | 2/2 | 0 |
| org40-r1-s1-PT | closed | 0 | False | 15/13 | 167087/3105 | 2/2 | 2 |
| org40-r1-s1-SB | closed | 0 | False | 4/2 | 19557/589 | 2/2 | 0 |
| org40-r1-s1-ST | closed | 0 | False | 4/2 | 19744/634 | 2/2 | 0 |
| org40-r1-s1-PB | closed | 0 | False | 12/10 | 124090/1989 | 2/2 | 2 |

全部实际成本：`{'episodes_with_recorded_usage': 16, 'recorded_usage': {'decisions': 151, 'attempts': 119, 'prompt_tokens': 1467216, 'completion_tokens': 27823, 'total_tokens': 1495039, 'output_bearing_calls': 119, 'budget_charged_tokens': 1495039, 'uncertain_usage_attempts': 0}, 'run_tests': 17, 'cost_incomplete': False, 'partial_cost_episodes': 0, 'unreported_started_episodes': 0, 'unsettled_attempts': 0, 'partial_episodes_without_settlement_counts': 0, 'attempts_without_reported_token_usage': 0, 'metrics_with_missing_episode_records': {'decisions': 0, 'attempts': 0, 'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0, 'output_bearing_calls': 0, 'budget_charged_tokens': 0, 'uncertain_usage_attempts': 0, 'run_tests': 0}, 'closed_worker_gpu_seconds': 1701.8648600578308, 'running_worker_gpu_seconds': 0, 'scope': 'All recorded work, including unsuccessful and technically unknown episodes. Totals are partial when indicated; absent token usage and held reservations are never inferred as actual tokens. Initial environment diagnostics remain separate from member work, nested within worker time.'}`。新增actor/critic步`0/0`，新增反向`0`。

初始环境准备实际新增成本：`{'actual_public_driver_executions': 8, 'sandbox_elapsed_seconds': 0.9157959623262286, 'prepare_function_wall_seconds': 1.2488828510977328, 'model_calls': 0, 'model_output_tokens': 0, 'team_run_tests_charged': 0}`；每槽缓存复用与原来源见JSON，原准备成本不随复用次数重复累计。

逐槽work-use.json记录所有成员（包括初始成员）的事实/产物→分享→伙伴实际selected输入→修改/验证→工作结果关系，最终固定交付连接另列。环境初始代码与诊断不算当前模型发现或编辑；信息语义候选保留待人工核查，不能把消息数、任务ID或相同代码自动判成使用。

未知工具名在可靠记录、执行前成功阻断时为可恢复动作错误；保留输出和费用，下一真实机会看反馈，不自动改名或免费重试。明确禁止的controller请求仍拒绝、过程违规单列；真正身份/执行效果/记录完整性失败仍停止。正式R与原固定内容验收分层，旧v039未知及两个未启动槽不回改。

仅允许物理GPU3、4、5、7；不恢复旧训练、Contribution、独立确认或缓存生产队列。无新增出生接口题、X3、模型筛选或参数学习。

[冻结协议](software-organization-v040-protocol.md)；[承接态任务](software-organization-v040-tasks.md)；[审计原文](../reference/audit-v039-next-v040.md)。
