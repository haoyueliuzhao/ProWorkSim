# v0.39 冻结模型自主组织开发

状态：`closed_with_unknowns`；主库存24条，已知结果`21/24`；接口诊断另计2条，闭合`2/2`。源码`5159c13011d000e2949bc5e6b379463f63eeb9ef`。

原9B 3/3 common、四个全新schema应用根目标、16K上下文/2048输出。F2固定两人与A3自然动态组构成16条主比较；X3的8条是外生中性成员辅助对照。主实验每条共同预算128决定/128attempt/500000实际token/32次测试，诊断每条12/12/150000/32。仅物理GPU 3、4、5、7。旧26次Contribution试训、正式更新、TextFSM确认与缓存生产测试继续暂停。

| 条件 | 已知/计划 | 成功 | 提交 | 有新增出生的已知槽 | 自然/外生出生 | 全8槽平均R |
|---|---:|---:|---:|---:|---:|---:|
| F2 | 7/8 | 2 | 2 | 0 | 0/0 | None |
| A3 | 7/8 | 2 | 2 | 0 | 0/0 | None |
| X3 | 7/8 | 1 | 1 | 7 | 0/7 | None |

| 条件 | 有测量的槽 | 新成员有实际输出 | 有伙伴代码采用链 | 新成员直接交付 | 信息候选待人工核查/未闭合 |
|---|---:|---:|---:|---:|---|
| F2 | 7 | 0 | 0 | 0 | 0/0 |
| A3 | 7 | 0 | 0 | 0 | 0/0 |
| X3 | 7 | 7 | 0 | 1 | 0/0 |

以上为已记录关系的计数；测量缺失或不支持的复杂关系保留在逐槽记录中，不能把零计数解释成零贡献。代码采用链与交付质量R分别报告。

| root | F2成功/已知/计划 | A3成功/已知/计划 | X3成功/已知/计划 |
|---|---|---|---|
| sc-label-index-v039 | 1/1/2 | 1/1/2 | 1/1/2 |
| sc-row-projection-v039 | 0/2/2 | 1/2/2 | 0/2/2 |
| sc-record-views-v039 | 1/2/2 | 0/2/2 | 0/2/2 |
| sc-record-catalog-v039 | 0/2/2 | 0/2/2 | 0/2/2 |

完整配对平均差：`{'A3_minus_F2': None, 'X3_minus_A3': None}`。None为未闭合，不填零；X3−A3是外生加入中性会话的辅助效果。

新增actor/critic步：`0/0`；新增反向：`0`。

| slot | 状态 | R | 提交 | 有输出调用 | 输入/输出token | 初始/累计/输出人数 | 秒 |
|---|---|---:|---|---:|---|---|---:|
| org-r0-F2-s0 | closed | 1 | True | 29 | 333687/5156 | 2/2/2 | 302.6180317401886 |
| org-r0-A3-s0 | closed | 1 | True | 40 | 486214/8264 | 2/2/2 | 468.4844398498535 |
| org-r0-X3-s0 | closed | 1 | True | 42 | 488189/6493 | 2/3/3 | 391.17299342155457 |
| org-r0-A3-s1 | technical_unknown | None | True | 34 | 390081/7641 | 2/2/2 | 419.83064913749695 |
| org-r0-X3-s1 | not_started | None | None | None | None/None | None/None/None | None |
| org-r0-F2-s1 | not_started | None | None | None | None/None | None/None/None | None |
| org-r1-X3-s0 | closed | 0 | False | 41 | 483350/11207 | 2/3/3 | 595.925511598587 |
| org-r1-F2-s0 | closed | 0 | False | 40 | 479938/13004 | 2/2/2 | 670.9337630271912 |
| org-r1-A3-s0 | closed | 0 | False | 40 | 481590/9234 | 2/2/2 | 507.2466332912445 |
| org-r1-F2-s1 | closed | 0 | False | 41 | 487872/8934 | 2/2/2 | 491.79322719573975 |
| org-r1-A3-s1 | closed | 1 | True | 35 | 405194/5719 | 2/2/2 | 336.82073497772217 |
| org-r1-X3-s1 | closed | 0 | False | 41 | 482798/7843 | 2/3/3 | 647.3519988059998 |
| org-r2-A3-s0 | closed | 0 | False | 40 | 489639/8613 | 2/2/2 | 488.10451221466064 |
| org-r2-X3-s0 | closed | 0 | False | 41 | 486612/11110 | 2/3/3 | 590.371780872345 |
| org-r2-F2-s0 | closed | 1 | True | 39 | 479921/6929 | 2/2/2 | 410.6706681251526 |
| org-r2-X3-s1 | closed | 0 | False | 41 | 483189/13307 | 2/3/3 | 683.9393455982208 |
| org-r2-F2-s1 | closed | 0 | False | 41 | 487703/10532 | 2/2/2 | 564.4239706993103 |
| org-r2-A3-s1 | closed | 0 | False | 39 | 478577/13110 | 2/2/2 | 885.0159401893616 |
| org-r3-F2-s0 | closed | 0 | False | 40 | 483594/9414 | 2/2/2 | 520.0516595840454 |
| org-r3-A3-s0 | closed | 0 | False | 39 | 480263/6149 | 2/2/2 | 374.3802671432495 |
| org-r3-X3-s0 | closed | 0 | False | 41 | 481806/10198 | 2/3/3 | 765.4280936717987 |
| org-r3-A3-s1 | closed | 0 | False | 40 | 487662/9192 | 2/2/2 | 512.835414648056 |
| org-r3-X3-s1 | closed | 0 | False | 41 | 480341/13799 | 2/3/3 | 707.5237505435944 |
| org-r3-F2-s1 | closed | 0 | False | 41 | 491318/5236 | 2/2/2 | 331.95719838142395 |

| 辅助X3槽 | 第8次决定后处置 | 原因 | 外生成员 |
|---|---|---|---|
| org-r0-X3-s0 | implemented | None | member_003 |
| org-r0-X3-s1 | None | None | None |
| org-r1-X3-s0 | implemented | None | member_003 |
| org-r1-X3-s1 | implemented | None | member_003 |
| org-r2-X3-s0 | implemented | None | member_003 |
| org-r2-X3-s1 | implemented | None | member_003 |
| org-r3-X3-s0 | implemented | None | member_003 |
| org-r3-X3-s1 | implemented | None | member_003 |

| 独立接口诊断 | 状态 | 全部接口目标达成 | 决定/attempt/token |
|---|---|---|---|
| interface-birth-message | closed | True | 12/12/114959 |
| interface-replacement-patch | closed | True | 11/11/122132 |

主24槽闭合usage：`{'decisions': 908, 'attempts': 866, 'prompt_tokens': 10329538, 'completion_tokens': 201084, 'total_tokens': 10530622, 'output_bearing_calls': 866, 'budget_charged_tokens': 10530622, 'uncertain_usage_attempts': 0}`；测试`108`；已结束worker GPU秒`11899.990646123886`、运行中`0`。

主24槽控制器成本（嵌套计时，不再叠加GPU时间）：`{'world_actions': 7, 'world_transaction_wall_seconds': 0.32161356462165713, 'session_creation_wall_seconds': 0.9319583643227816, 'initial_workspace_bytes': 355323, 'model_calls': 0, 'generated_tokens': 0}`。

独立诊断闭合usage：`{'decisions': 23, 'attempts': 23, 'prompt_tokens': 232553, 'completion_tokens': 4538, 'total_tokens': 237091, 'output_bearing_calls': 23, 'budget_charged_tokens': 237091, 'uncertain_usage_attempts': 0}`；测试`0`；已结束worker GPU秒`292.31583881378174`、运行中`0`。

独立诊断控制器成本（嵌套计时，不再叠加GPU时间）：`{'world_actions': 0, 'world_transaction_wall_seconds': 0.0, 'session_creation_wall_seconds': 0.0, 'initial_workspace_bytes': 0, 'model_calls': 0, 'generated_tokens': 0}`。

逐槽work-use.json记录真实出生、实际selected输入中的briefing、工作事件、伙伴取得与消费候选、最终固定版本连接；无新成员的槽也保留。代码消费要求改变的生产单元、实际取得和最终保留链。信息/反例的语义使用若缺证据标为待人工核查，不把消息数、补丁ID或代码未保留直接当成合作成功/失败。机器记录逐槽保留原始工作关系及未知状态。

逐成员调用、控制机会、selected输入、出生/退出、任务、版本、诊断CPU setup及冻结护栏保存在原始episode目录。未提交的可变工作区不补验。技术未知保留原槽，不自动重试；全24槽保留，包括X3未实施和A3无增员。

同一episode各成员在一个resident上顺序调用，独立root可并行。新增会话不增加总资源，未招募是合法结果；诊断受提示创建和X3控制器创建均不能补作自然招募证据。组织开发结果不等于训练或ID-VTDO分配收益，后续不自动扩至144条或恢复学习。

协议：[software-organization-v039-protocol.md](software-organization-v039-protocol.md)；实际接口审计：[software-organization-v039-interface-audit.md](software-organization-v039-interface-audit.md)；新任务与对照：[software-organization-v039-tasks.md](software-organization-v039-tasks.md)。
