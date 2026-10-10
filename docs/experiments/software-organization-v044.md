# v0.44 分层准入后的冻结模型组织开发

状态：`stopped_by_first_block_gate`；原16槽中正式结果已知`4/16`。执行源码`e8aa60bd1a427944d8503fb02b30f6379ebd5889`。

本轮新Γ仅修订有运行器来源的普通格式/公开schema反馈生命周期与当前纠错正文；已实际呈现的旧错误按合法调用历史化或新错误替代，未呈现最新错误保留，完整原输出与费用留档。3072字符测试分页、初始shared/split、base/team、工具权限、16K/2048与团队预算不变。新准入绑定112旧形状重编码与有限CPU生命周期路线，1024-token余量仍为风险诊断。旧v043的4已执行/12未启动不改、不与新16槽拼合。

首块机制门槛：`{'version': 'organization-feedback-opportunities-v0.44', 'passed': False, 'reasons': [{'slot_id': 'org44-r1-s0-PT', 'reason': 'gate_unresolved'}], 'measured_slots': 4, 'scope': 'Mechanism-only gate: does not condition on reward, messaging, births, or collaboration success.', 'first_block': 'block-r1-s0', 'checked_at': 1791614794.145318, 'measurements': [{'path': '/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v044/block-r1-s0/actual/episodes/org44-r1-s0-PT/feedback-loop.json', 'sha256': '2cdfe3243c973c54b25b92ba8b31c4101df06ad30da993b9b0d317f15be16c68'}, {'path': '/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v044/block-r1-s0/actual/episodes/org44-r1-s0-SB/feedback-loop.json', 'sha256': 'd676f9e3bdd2e539c453775902f57d247d33558e0374f69af0b319d0f48d8c58'}, {'path': '/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v044/block-r1-s0/actual/episodes/org44-r1-s0-ST/feedback-loop.json', 'sha256': 'beecd3175dbc0c0fc6dbc16384344b544332d1747af14b00d0e18106cc2ed8ac'}, {'path': '/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v044/block-r1-s0/actual/episodes/org44-r1-s0-PB/feedback-loop.json', 'sha256': 'fda62cd644daf4a682f6eadb568a4da6edfdb6a053e6a37ac1d5a6cfce7bc9f4'}]}`。停止不把未启动槽填零；继续与否不依赖R、交流或招募。

SB=shared/base，ST=shared/team，PB=split/base，PT=split/team。两个承接态root与两枚在org44新登记的seed构成4个配对块；每块四条件共享相同初态代码、根要求、先手、测试和总预算。所有条件初始2人、允许自主增员（活动≤4/累计≤6），无外生出生。

原9B完整3/3 common，16K/2048，每槽128决定/attempt、500000实际token、32次测试。环境事先实际运行两组公开检查，shared两人各获两份，split各获一份；成员可自己同权限检查重得信息。G-team额外的共同交付说明是明确提示干预，信息位置和说明都会影响输入长度与取得成本。

| 条件 | 已知/计划 | 已知成功 | 已知固定提交 | 自然出生 | 全4槽平均R |
|---|---:|---:|---:|---:|---:|
| SB | 1/4 | 0 | 0 | 0 | None |
| ST | 1/4 | 0 | 0 | 0 | None |
| PB | 1/4 | 0 | 0 | 0 | None |
| PT | 1/4 | 1 | 1 | 0 | None |

| 条件 | 已证实跨成员链 | 完整记录未证实 | 未知/未测量 | 可恢复未知名字/参数错误 | 禁止过程请求 |
|---|---:|---:|---:|---|---:|
| SB | 0 | 1 | 3 | 0/0 | 0 |
| ST | 0 | 1 | 3 | 0/1 | 0 |
| PB | 0 | 1 | 3 | 0/0 | 0 |
| PT | 0 | 1 | 3 | 1/0 | 0 |

工作链列为保守机械证据；信息语义候选、复杂关系或未测量保持未知，不以0代替。测试是否通过、是否连接最后交付及正式R分别记录。

| 配对块 | SB | ST | PB | PT | 信息主效应 | 说明主效应 | 交互 |
|---|---:|---:|---:|---:|---:|---:|---:|
| block-r0-s0 | None | None | None | None | None | None | None |
| block-r0-s1 | None | None | None | None | None | None | None |
| block-r1-s0 | 0 | 0 | 0 | 1 | 0.5 | 0.5 | 1 |
| block-r1-s1 | None | None | None | None | None | None | None |

全库存平均对比：`{'split_minus_shared_base': None, 'split_minus_shared_team': None, 'team_minus_base_shared': None, 'team_minus_base_split': None, 'information_main_effect': None, 'framing_main_effect': None, 'interaction': None}`。None表示所需配对未完整，未知或未启动不填零。

信息主效应=[(PB+PT)−(SB+ST)]/2；说明主效应=[(ST+PT)−(SB+PB)]/2；交互=PT−PB−ST+SB。每项先在root/seed块内计算，再取原4块平均。这是两root有限开发观察，不是总体稳定性认证。

| slot | 状态 | R | 提交 | 决定/调用 | 输入/输出token | 初始/累计人数 | 测试 |
|---|---|---:|---|---|---|---|---:|
| org44-r0-s0-ST | not_started | None | None | None/None | None/None | None/None | None |
| org44-r0-s0-PB | not_started | None | None | None/None | None/None | None/None | None |
| org44-r0-s0-PT | not_started | None | None | None/None | None/None | None/None | None |
| org44-r0-s0-SB | not_started | None | None | None/None | None/None | None/None | None |
| org44-r0-s1-PB | not_started | None | None | None/None | None/None | None/None | None |
| org44-r0-s1-PT | not_started | None | None | None/None | None/None | None/None | None |
| org44-r0-s1-SB | not_started | None | None | None/None | None/None | None/None | None |
| org44-r0-s1-ST | not_started | None | None | None/None | None/None | None/None | None |
| org44-r1-s0-PT | closed | 1 | True | 34/34 | 420138/7292 | 2/2 | 3 |
| org44-r1-s0-SB | closed | 0 | False | 38/36 | 474975/13677 | 2/2 | 3 |
| org44-r1-s0-ST | closed | 0 | False | 38/36 | 472077/17311 | 2/2 | 3 |
| org44-r1-s0-PB | closed | 0 | False | 40/38 | 473729/13647 | 2/2 | 5 |
| org44-r1-s1-SB | not_started | None | None | None/None | None/None | None/None | None |
| org44-r1-s1-ST | not_started | None | None | None/None | None/None | None/None | None |
| org44-r1-s1-PB | not_started | None | None | None/None | None/None | None/None | None |
| org44-r1-s1-PT | not_started | None | None | None/None | None/None | None/None | None |

| slot | 报告保存 | 报告有页面实际呈现 | 历史完整覆盖报告 | 真实读页请求 | 实际生成中的工程余量警示 |
|---|---:|---:|---:|---:|---:|
| org44-r0-s0-ST | None | None | None | None | None |
| org44-r0-s0-PB | None | None | None | None | None |
| org44-r0-s0-PT | None | None | None | None | None |
| org44-r0-s0-SB | None | None | None | None | None |
| org44-r0-s1-PB | None | None | None | None | None |
| org44-r0-s1-PT | None | None | None | None | None |
| org44-r0-s1-SB | None | None | None | None | None |
| org44-r0-s1-ST | None | None | None | None | None |
| org44-r1-s0-PT | 3 | 3 | 0 | 0 | 2 |
| org44-r1-s0-SB | 3 | 3 | 0 | 1 | 3 |
| org44-r1-s0-ST | 3 | 3 | 0 | 0 | 4 |
| org44-r1-s0-PB | 5 | 5 | 0 | 1 | 1 |
| org44-r1-s1-SB | None | None | None | None | None |
| org44-r1-s1-ST | None | None | None | None | None |
| org44-r1-s1-PB | None | None | None | None | None |
| org44-r1-s1-PT | None | None | None | None | None |

工程余量警示只记录protected距13312的不足，不是运行拒绝或成功标准。历史覆盖是同一报告/事件/源版本的片段并集，不代表同时可见、理解或采用；未请求后页不判机械故障。


全部实际成本：`{'episodes_with_recorded_usage': 4, 'recorded_usage': {'decisions': 150, 'attempts': 144, 'prompt_tokens': 1840919, 'completion_tokens': 51927, 'total_tokens': 1892846, 'output_bearing_calls': 144, 'budget_charged_tokens': 1892846, 'uncertain_usage_attempts': 0}, 'run_tests': 14, 'cost_incomplete': False, 'partial_cost_episodes': 0, 'unreported_started_episodes': 0, 'unsettled_attempts': 0, 'partial_episodes_without_settlement_counts': 0, 'attempts_without_reported_token_usage': 0, 'metrics_with_missing_episode_records': {'decisions': 0, 'attempts': 0, 'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0, 'output_bearing_calls': 0, 'budget_charged_tokens': 0, 'uncertain_usage_attempts': 0, 'run_tests': 0}, 'closed_worker_gpu_seconds': 2806.305519104004, 'running_worker_gpu_seconds': 0, 'scope': 'All recorded work, including unsuccessful and technically unknown episodes. Totals are partial when indicated; absent token usage and held reservations are never inferred as actual tokens. Initial environment diagnostics remain separate from member work, nested within worker time.'}`。新增actor/critic步`0/0`，新增反向`0`。

初始环境准备实际新增成本：`{'actual_public_driver_executions': 2, 'sandbox_elapsed_seconds': 0.22864523902535439, 'prepare_function_wall_seconds': 0.30569366505369544, 'model_calls': 0, 'model_output_tokens': 0, 'team_run_tests_charged': 0}`；每槽缓存复用与原来源见JSON，原准备成本不随复用次数重复累计。

逐槽feedback-loop.json分开记录报告保存、目录呈现、页面片段实际selected呈现、同报告历史覆盖并集、后续工作候选和交付关联；重复页费用照计而覆盖不重复。未请求后续页是自主选择，历史覆盖不等于当前同时可见或理解采用。无后续输入分别记录context、团队预算、正常结束、未请求、等待与故障。

逐槽work-use.json记录所有成员（包括初始成员）的事实/产物→分享→伙伴实际selected输入→修改/验证→工作结果关系，最终固定交付连接另列。环境初始代码与诊断不算当前模型发现或编辑；信息语义候选保留待人工核查，不能把消息数、任务ID或相同代码自动判成使用。

未知工具名在可靠记录、执行前成功阻断时为可恢复动作错误；保留输出和费用，下一真实机会看反馈，不自动改名或免费重试。明确禁止的controller请求仍拒绝、过程违规单列；真正身份/执行效果/记录完整性失败仍停止。正式R与原固定内容验收分层，旧v039未知及两个未启动槽不回改。

仅允许物理GPU3、4、5、7；不恢复旧训练、Contribution、独立确认或缓存生产队列。无新增出生接口题、X3、模型筛选或参数学习。

[冻结协议](software-organization-v044-protocol.md)；[承接态任务](software-organization-v040-tasks.md)；[审计原文](../reference/audit-v043-next-v044.md)。
