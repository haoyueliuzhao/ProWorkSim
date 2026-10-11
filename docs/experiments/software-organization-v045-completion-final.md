# v0.45原24槽组织诊断收口详细报告

**原24槽全部正式结果已知：已执行且正式结果已知24/24，成功12，未提交R0为12，已提交验收失败R0为0。**

本阶段接续原14槽，实际闭合14槽、成功6槽；原首槽1与第一次接续9均保留且只计一次。未启动0，技术未知0。

原八块等权比较：F2−S1=0.0，O3−F2=0.0。完整三制度块8/8。结果未齐时主比较保持null，不把未启动或技术未知填0。

累计637决定、612次实际模型调用、8296556实际token、42次成员公开测试；新增参数与反向更新均0。

独立文件级只读补充确认1次非同值伙伴补丁应用，其中连至接收者新增固定交付0次；原冻结符号跟踪的阶段计数保持原值。跟踪范围外的真实应用不能被原0计数抹去，也不能据此声称交付收益。

## 1. 本轮修订、资格与保留边界

原24设计不变：四个人工新规格root（LA/HA事件接口家族、LB/HB规则接口家族）×完整seed202610100451/202610100452×S1/F2/O3。它们不是四个独立真实项目来源，调用次数、关系数和重复版本都不增加独立任务数。

S1真实1成员累计1，无隐藏伙伴；F2固定出生集合2，退休后仍属F2且不补员；O3初始2、活动≤4、累计≤6，可用同一actor原生创建。共同中性说明、公共初态、空任务表、独立私史，不预设经理或分工。集中完成、不公开、不增员均是可选行为，不能直接判作制度失败。

冻结原9B完整common3/3；16K上下文、2048输出预约、3072字符精确分页及既有反馈生命周期不变。每槽128决定/attempt、500000实际token、32run_tests。剩余14沿原plan排除旧10，无重跑、旧patch/私史继承或审计提示注入。

唯一必要的行为之外修订是宿主测量：把原model_call.started与model_budget_stop、成员meter/cap、输入/调用/机会身份及共享预约前后的原件连接起来。只有可证无实际生成、输出、收费、副作用和后续生成的成员固定预算拒绝才派生member_fixed_budget；普通context、共享预算或服务错误不笼统放行。原批次停止作用范围不变。

原HA/452/S1仍为35调用、498562token、R0未提交。最后P13278+2048=15326能放入16K，但成员余额仅1438，成员固定meter先于共享reserve拒绝。feedback698仍未呈现；只把派生原因由旧unknown修订为member_fixed_budget。原measurement_pending和原首槽接口标签global_pause均封存，不覆盖历史。

旧10反馈恒等式仍为191=175实际后续呈现+16无后续；原因分解为9正常结束、4context、2共享预算、1成员固定预算。工作资源视图补回末次已准备但未生成机会，后续机会25→26，实际后续生成仍25。三个snapshot结构unknown、成果内容、实际输入、费用和R不变。S1聚合null→False仅表示已确认无伙伴不适用，不能当成新增协作失败或清零结构未知。

本轮68项必要CPU控制（27测量反例+41宿主准入/库存/三阶段计费）及全项目Ruff通过。早期36项是同套件开发检查，不另计独立68之外控制；测量测试首次收集括号错误保留。既有业务、分页、tokenizer资格只按来源复用，没有重演旧191调用。

工作只读物化首次误用Python3.14，AST序列化导致指纹差异；窄比较后仅在原SDK Python3.12.3重物化工作，程序指纹及三个未知精确保留，已通过的反馈归因复用。3.14候选与失败日志保留。另有首次CLI缺create子命令和首次plan源码目录绑定不当，均在模型前收口，原件完整保留。

首次09:05启动误用无torch的项目解释器，worker在import torch退出，无模型加载/episode/调用。分配给物理GPU4的宿主生命期5.067300081秒独立计入成本，common核验记“不适用、未到达”，不能记为通过。09:08:57从独立新根用原SDK解释器纠正启动，冻结e62841df、case/seed/顺序/预算均不变；该纠正没有重采模型槽。

新14上限1792决定/attempt、7000000token、448测试；加旧10实际费用的上界为1990决定、1983调用、9563352token、467测试。旧未用2436648token不转移。仅物理GPU3/4/5/7、最多3驻留，原资源稳定性与保护保留。

## 2. 原24槽正式结果

| slot | root | 制度 | 完整seed | 先手 | 阶段 | 状态 | R | 提交 | 决定/调用 | token | 测试 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| org45-r0-s0-S1 | LA | S1 | 202610100451 | member_001 | retained_first_slot | closed | 1 | 是 | 7/7 | 87890 | 2 |
| org45-r0-s0-F2 | LA | F2 | 202610100451 | member_001 | retained_first_resume_nine | closed | 1 | 是 | 13/13 | 161382 | 2 |
| org45-r0-s0-O3 | LA | O3 | 202610100451 | member_001 | retained_first_resume_nine | closed | 1 | 是 | 21/20 | 248775 | 4 |
| org45-r0-s1-F2 | LA | F2 | 202610100452 | member_002 | retained_first_resume_nine | closed | 1 | 是 | 14/14 | 166446 | 2 |
| org45-r0-s1-O3 | LA | O3 | 202610100452 | member_002 | retained_first_resume_nine | closed | 1 | 是 | 17/17 | 207680 | 2 |
| org45-r0-s1-S1 | LA | S1 | 202610100452 | member_001 | retained_first_resume_nine | closed | 1 | 是 | 10/10 | 127709 | 1 |
| org45-r1-s0-O3 | HA | O3 | 202610100451 | member_002 | retained_first_resume_nine | closed | 0 | 否 | 36/34 | 489606 | 3 |
| org45-r1-s0-S1 | HA | S1 | 202610100451 | member_001 | retained_first_resume_nine | closed | 0 | 否 | 7/6 | 77766 | 1 |
| org45-r1-s0-F2 | HA | F2 | 202610100451 | member_002 | retained_first_resume_nine | closed | 0 | 否 | 37/35 | 497536 | 1 |
| org45-r1-s1-S1 | HA | S1 | 202610100452 | member_001 | retained_first_resume_nine | closed | 0 | 否 | 36/35 | 498562 | 1 |
| org45-r1-s1-O3 | HA | O3 | 202610100452 | member_001 | original_remaining_fourteen | closed | 0 | 否 | 37/35 | 498914 | 0 |
| org45-r1-s1-F2 | HA | F2 | 202610100452 | member_001 | original_remaining_fourteen | closed | 0 | 否 | 37/35 | 492735 | 0 |
| org45-r2-s0-O3 | LB | O3 | 202610100451 | member_001 | original_remaining_fourteen | closed | 1 | 是 | 22/21 | 273059 | 3 |
| org45-r2-s0-F2 | LB | F2 | 202610100451 | member_001 | original_remaining_fourteen | closed | 1 | 是 | 37/36 | 483214 | 4 |
| org45-r2-s0-S1 | LB | S1 | 202610100451 | member_001 | original_remaining_fourteen | closed | 1 | 是 | 12/12 | 155071 | 2 |
| org45-r2-s1-F2 | LB | F2 | 202610100452 | member_002 | original_remaining_fourteen | closed | 1 | 是 | 21/20 | 255880 | 4 |
| org45-r2-s1-S1 | LB | S1 | 202610100452 | member_001 | original_remaining_fourteen | closed | 1 | 是 | 11/11 | 140407 | 1 |
| org45-r2-s1-O3 | LB | O3 | 202610100452 | member_002 | original_remaining_fourteen | closed | 1 | 是 | 38/37 | 487233 | 2 |
| org45-r3-s0-S1 | HB | S1 | 202610100451 | member_001 | original_remaining_fourteen | closed | 0 | 否 | 36/35 | 489803 | 2 |
| org45-r3-s0-F2 | HB | F2 | 202610100451 | member_002 | original_remaining_fourteen | closed | 0 | 否 | 38/36 | 487304 | 0 |
| org45-r3-s0-O3 | HB | O3 | 202610100451 | member_002 | original_remaining_fourteen | closed | 0 | 否 | 38/36 | 489331 | 0 |
| org45-r3-s1-F2 | HB | F2 | 202610100452 | member_001 | original_remaining_fourteen | closed | 0 | 否 | 38/36 | 493938 | 1 |
| org45-r3-s1-O3 | HB | O3 | 202610100452 | member_001 | original_remaining_fourteen | closed | 0 | 否 | 38/36 | 494010 | 2 |
| org45-r3-s1-S1 | HB | S1 | 202610100452 | member_001 | original_remaining_fourteen | closed | 0 | 否 | 36/35 | 492305 | 2 |

公开测试、可变副本、固定提交与闭合后私验分开。未提交工作区不补验，同槽多次submit只计一个业务结果。所有已执行成功/失败保留，不筛除context槽或按结果追加样本。

| 制度 | 已知/8 | 成功 | 完整均值R | 实际调用 | 实际token |
|---|---|---|---|---|---|
| S1 | 8/8 | 4 | 0.5 | 151 | 2069513 |
| F2 | 8/8 | 4 | 0.5 | 225 | 3038435 |
| O3 | 8/8 | 4 | 0.5 | 236 | 3188608 |


| 原配对块 | root | S1 | F2 | O3 | F2−S1 | O3−F2 |
|---|---|---|---|---|---|---|
| block-r0-s0 | LA | 1 | 1 | 1 | 0 | 0 |
| block-r0-s1 | LA | 1 | 1 | 1 | 0 | 0 |
| block-r1-s0 | HA | 0 | 0 | 0 | 0 | 0 |
| block-r1-s1 | HA | 0 | 0 | 0 | 0 | 0 |
| block-r2-s0 | LB | 1 | 1 | 1 | 0 | 0 |
| block-r2-s1 | LB | 1 | 1 | 1 | 0 | 0 |
| block-r3-s0 | HB | 0 | 0 | 0 | 0 | 0 |
| block-r3-s1 | HB | 0 | 0 | 0 | 0 | 0 |


| root | 制度 | 成功/已知 | 调用 | token |
|---|---|---|---|---|
| LA | S1 | 2/2（原2） | 17 | 215599 |
| LA | F2 | 2/2（原2） | 27 | 327828 |
| LA | O3 | 2/2（原2） | 37 | 456455 |
| HA | S1 | 0/2（原2） | 41 | 576328 |
| HA | F2 | 0/2（原2） | 70 | 990271 |
| HA | O3 | 0/2（原2） | 69 | 988520 |
| LB | S1 | 2/2（原2） | 23 | 295478 |
| LB | F2 | 2/2（原2） | 56 | 739094 |
| LB | O3 | 2/2（原2） | 58 | 760292 |
| HB | S1 | 0/2（原2） | 70 | 982108 |
| HB | F2 | 0/2（原2） | 72 | 981242 |
| HB | O3 | 0/2（原2） | 72 | 983341 |

先每个原root/seed块求差，再对八块等权平均。F2−S1是包含多私史与协调成本的制度组合比较；O3−F2是动态人数选择权比较。未增员时不能归因为实际增员收益，有限人工载体结果不能外推为稳定总体收益或训练收益。

## 3. 真实输入、局部终止与未呈现反馈

| 分区 | 决定 | 实际调用 | 差额 | 硬context拒绝 | 共享预约拒绝 | 成员固定预算拒绝 |
|---|---|---|---|---|---|---|
| 旧10 | 198 | 191 | 7 | 4 | 2 | 1 |
| 新14实际 | 439 | 421 | 18 | 4 | 12 | 2 |
| 原24实际合计 | 637 | 612 | 25 | 8 | 14 | 3 |


| 槽/成员 | 阶段 | 拒绝类型 | P+输出预约 | 硬余量 | 当时团队余额 | 终态团队余额 | 成员固定余额 |
|---|---|---|---|---|---|---|---|
| org45-r0-s0-O3/member_002 | retained10 | context_capacity | 14479+2048 | -143 | 264211 | 251225 | null |
| org45-r1-s0-O3/member_001 | retained10 | context_capacity | 15604+2048 | -1268 | 25576 | 10394 | null |
| org45-r1-s0-O3/member_002 | retained10 | shared_total_tokens | 13487+2048 | 849 | 10394 | 10394 | null |
| org45-r1-s0-S1/member_001 | retained10 | context_capacity | 14673+2048 | -337 | 422234 | 422234 | null |
| org45-r1-s0-F2/member_002 | retained10 | context_capacity | 14837+2048 | -501 | 395850 | 2464 | null |
| org45-r1-s0-F2/member_001 | retained10 | shared_total_tokens | 13131+2048 | 1205 | 2464 | 2464 | null |
| org45-r1-s1-S1/member_001 | retained10 | fixed_member_model_budget_before_shared_admission | 13278+2048 | 1058 | 1438 | null | 1438 |
| org45-r1-s1-O3/member_001 | new14 | shared_total_tokens | 13929+2048 | 407 | 15861 | 1086 | null |
| org45-r1-s1-O3/member_002 | new14 | shared_total_tokens | 13632+2048 | 704 | 1086 | 1086 | null |
| org45-r1-s1-F2/member_002 | new14 | shared_total_tokens | 13661+2048 | 675 | 7265 | 7265 | null |
| org45-r1-s1-F2/member_001 | new14 | shared_total_tokens | 13569+2048 | 767 | 7265 | 7265 | null |
| org45-r2-s0-O3/member_002 | new14 | context_capacity | 14583+2048 | -247 | 226941 | 226941 | null |
| org45-r2-s0-F2/member_002 | new14 | context_capacity | 15189+2048 | -853 | 16786 | 16786 | null |
| org45-r2-s1-F2/member_002 | new14 | context_capacity | 14411+2048 | -75 | 244120 | 244120 | null |
| org45-r2-s1-O3/member_002 | new14 | shared_total_tokens | 13193+2048 | 1143 | 12767 | 12767 | null |
| org45-r3-s0-S1/member_001 | new14 | fixed_member_model_budget_before_shared_admission | 12434+2048 | 1902 | 10197 | null | 10197 |
| org45-r3-s0-F2/member_002 | new14 | shared_total_tokens | 13510+2048 | 826 | 12696 | 12696 | null |
| org45-r3-s0-F2/member_001 | new14 | shared_total_tokens | 14043+2048 | 293 | 12696 | 12696 | null |
| org45-r3-s0-O3/member_002 | new14 | shared_total_tokens | 13918+2048 | 418 | 10669 | 10669 | null |
| org45-r3-s0-O3/member_001 | new14 | shared_total_tokens | 13998+2048 | 338 | 10669 | 10669 | null |
| org45-r3-s1-F2/member_001 | new14 | context_capacity | 14342+2048 | -6 | 236731 | 6062 | null |
| org45-r3-s1-F2/member_002 | new14 | shared_total_tokens | 13330+2048 | 1006 | 6062 | 6062 | null |
| org45-r3-s1-O3/member_001 | new14 | shared_total_tokens | 13944+2048 | 392 | 5990 | 5990 | null |
| org45-r3-s1-O3/member_002 | new14 | shared_total_tokens | 12721+2048 | 1615 | 5990 | 5990 | null |
| org45-r3-s1-S1/member_001 | new14 | fixed_member_model_budget_before_shared_admission | 12942+2048 | 1394 | 7695 | null | 7695 |

三种执行前终止分开计数；若成员meter先拒同时context不足，保留原先拒顺序并单列并发不足，不能重标成已发生的context拒绝。拒绝没有新增实际attempt/输出/费用；decision_consumed也不等于未准备或未结算。终态余额不替代拒绝当时余额，缺少对应字段保持null。

新14已生成输入最小硬余量7；protected的1024工程余量不足35次，最小余量-1008。工程余量仅诊断，不作结果筛选。

新阶段context相对首次成功世界提交时序：`{"after_first_successful_world_submission":3,"no_successful_world_submission_in_episode":1}`。宿主决定：`{"continue":14}`。新暂停回执0份，机器文件逐项引用；同一故障的槽/监督器两份回执不算两个独立机制故障。

实际actor、完整common3/3、输入/输出/费用、原coordinate-binding和人数分别核对。既有critic坐标members→member_a/member_b/software_inactive会使owner recipe摘要与实际绑定摘要不同；这属于原桥接，不是新参数更新或S1隐藏伙伴。原始采样字段、16K/2048和实际世界注册保持。

## 4. 反馈、页面、出生与五阶段成果证据

| 分区 | 保存反馈 | 首次实际后续呈现 | 无后续 | 无后续原因 | 新增成员 | 有出生槽 |
|---|---|---|---|---|---|---|
| 旧10修订派生 | 191 | 175 | 16 | {"voluntary_end":9,"context_capacity":4,"team_budget":2,"member_fixed_budget":1} | 0 | 0 |
| 新14实际 | 421 | 397 | 24 | {"team_budget":12,"context_capacity":4,"voluntary_end":6,"member_fixed_budget":2} | 0 | 0 |
| 原24实际 | 612 | 572 | 40 | {"voluntary_end":15,"context_capacity":8,"team_budget":14,"member_fixed_budget":3} | 0 | 0 |


| 分区 | 报告保存 | 目录呈现 | 至少1页呈现 | 历史全部呈现 | 额外读页请求 | 格式反馈已见/登记 |
|---|---|---|---|---|---|---|
| 旧10 | 19 | 15 | 15 | 0 | 0 | 14/14 |
| 新14实际 | 23 | 18 | 18 | 1 | 2 | 21/22 |
| 原24实际 | 42 | 33 | 33 | 1 | 2 | 35/36 |

原24实际格式状态：`{"superseded":6,"historicalized_after_legal_native_schema":29,"pending_or_presented":1}`；实际移除记录：`{"registered":36,"actually_presented":35,"actual_presentation_occurrences":35,"ids_with_observed_removal":33,"actual_removal_occurrences":379}`。保存、至少一页实际呈现、完整覆盖和理解/采用是不同事实，全读不作为成功条件。

跨成员适用性：`{"not_applicable_no_partner":8,"applicable":16}`。S1无伙伴是制度定义，表中False或旧null不得作为协作失败；成员停止后也不虚构持续可达的接收者。

下表只统计F2/O3，并把程序与信息分开；全部五阶段计数限于冻结测量的跟踪范围。true/false/unknown来自原测量，关系按被跟踪成果版本和潜在接收者定义，不是独立样本数或已验证有价值成果数。未跟踪函数的修改可能不进入程序产生或公开关系，0不能推断无真实代码修改/补丁公开。

| 制度 | 冻结跟踪工作类型 | 跟踪产生 | 跟踪公开 | 跟踪取得 | 跟踪使用 | 跟踪连交付 |
|---|---|---|---|---|---|---|
| F2 | program | {"true":38} | {"true":2,"false":36} | {"false":38} | {"false":38} | {"false":38} |
| F2 | information | {"true":14} | {"false":14} | {"false":14} | {"false":14} | {"false":14} |
| F2 | all | {"true":52} | {"true":2,"false":50} | {"false":52} | {"false":52} | {"false":52} |
| O3 | program | {"true":41} | {"true":3,"false":38} | {"false":41} | {"false":41} | {"false":41} |
| O3 | information | {"true":16} | {"false":16} | {"false":16} | {"false":16} | {"false":16} |
| O3 | all | {"true":57} | {"true":3,"false":54} | {"false":57} | {"false":57} | {"false":57} |


| 槽 | 制度 | 适用性 | 冻结跟踪程序结构记录（按版本/函数） | 冻结跟踪测试信息 | 结构待定 | 语义待定 | 已证使用 | 连固定交付 | 出生 |
|---|---|---|---|---|---|---|---|---|---|
| org45-r0-s0-S1 | S1 | not_applicable_no_partner | 1 | 2 | 0 | 0 | 不适用 | 不适用 | [] |
| org45-r0-s0-F2 | F2 | applicable | 2 | 2 | 0 | 0 | 否 | 否 | [] |
| org45-r0-s0-O3 | O3 | applicable | 2 | 4 | 0 | 0 | 否 | 否 | [] |
| org45-r0-s1-F2 | F2 | applicable | 2 | 2 | 0 | 0 | 否 | 否 | [] |
| org45-r0-s1-O3 | O3 | applicable | 2 | 2 | 0 | 0 | 否 | 否 | [] |
| org45-r0-s1-S1 | S1 | not_applicable_no_partner | 1 | 1 | 0 | 0 | 不适用 | 不适用 | [] |
| org45-r1-s0-O3 | O3 | applicable | 14 | 3 | 0 | 0 | 否 | 否 | [] |
| org45-r1-s0-S1 | S1 | not_applicable_no_partner | 1 | 1 | 0 | 0 | 不适用 | 不适用 | [] |
| org45-r1-s0-F2 | F2 | applicable | 13 | 1 | 0 | 0 | 否 | 否 | [] |
| org45-r1-s1-S1 | S1 | not_applicable_no_partner | 10 | 1 | 3 | 0 | 不适用 | 不适用 | [] |
| org45-r1-s1-O3 | O3 | applicable | 11 | 0 | 0 | 0 | 否 | 否 | [] |
| org45-r1-s1-F2 | F2 | applicable | 5 | 0 | 0 | 0 | 否 | 否 | [] |
| org45-r2-s0-O3 | O3 | applicable | 0 | 3 | 0 | 0 | 否 | 否 | [] |
| org45-r2-s0-F2 | F2 | applicable | 0 | 4 | 0 | 1 | null | null | [] |
| org45-r2-s0-S1 | S1 | not_applicable_no_partner | 0 | 2 | 0 | 0 | 不适用 | 不适用 | [] |
| org45-r2-s1-F2 | F2 | applicable | 0 | 4 | 0 | 0 | 否 | 否 | [] |
| org45-r2-s1-S1 | S1 | not_applicable_no_partner | 0 | 1 | 0 | 0 | 不适用 | 不适用 | [] |
| org45-r2-s1-O3 | O3 | applicable | 0 | 2 | 0 | 0 | 否 | 否 | [] |
| org45-r3-s0-S1 | S1 | not_applicable_no_partner | 7 | 2 | 0 | 0 | 不适用 | 不适用 | [] |
| org45-r3-s0-F2 | F2 | applicable | 7 | 0 | 0 | 0 | 否 | 否 | [] |
| org45-r3-s0-O3 | O3 | applicable | 3 | 0 | 0 | 0 | 否 | 否 | [] |
| org45-r3-s1-F2 | F2 | applicable | 9 | 1 | 0 | 0 | 否 | 否 | [] |
| org45-r3-s1-O3 | O3 | applicable | 9 | 2 | 0 | 0 | 否 | 否 | [] |
| org45-r3-s1-S1 | S1 | not_applicable_no_partner | 10 | 2 | 0 | 0 | 不适用 | 不适用 | [] |

结构分析不支持留下的produced unknown不等同Python运行时语法错误；旧三条unknown明确保留。阅读、相似代码、可访问、消息或任务数量不替代实际取得/使用。初始材料重执行与转达另计，真实使用后失败也保留，不用R裁剪工作证据。

### 冻结程序跟踪范围与真实世界动作

原LB/451/O3的声明仅跟踪rules.py::evaluate包装函数，真实修改发生在validate_rule/_evaluate；因此原程序产生/公开计数为0，同时世界记录有3次编辑和2次patch_fixed。窄只读原版本差异与公开记录确认这些工程动作，原冻结work计数、指纹、R、验收和停止门均未重算。此覆盖限制应逐槽查看，不能从0跟踪关系推断没有程序产出或公开。

| 槽 | root | 制度 | 世界edit | 世界patch_fixed | 冻结跟踪程序产生true关系 | 冻结跟踪程序公开true关系 |
|---|---|---|---|---|---|---|
| org45-r0-s0-S1 | LA | S1 | 1 | 1 | 1 | 0 |
| org45-r0-s0-F2 | LA | F2 | 2 | 1 | 2 | 1 |
| org45-r0-s0-O3 | LA | O3 | 2 | 1 | 2 | 1 |
| org45-r0-s1-F2 | LA | F2 | 2 | 1 | 2 | 1 |
| org45-r0-s1-O3 | LA | O3 | 2 | 2 | 2 | 2 |
| org45-r0-s1-S1 | LA | S1 | 1 | 1 | 1 | 0 |
| org45-r1-s0-O3 | HA | O3 | 13 | 0 | 14 | 0 |
| org45-r1-s0-S1 | HA | S1 | 1 | 0 | 1 | 0 |
| org45-r1-s0-F2 | HA | F2 | 13 | 0 | 13 | 0 |
| org45-r1-s1-S1 | HA | S1 | 12 | 0 | 10 | 0 |
| org45-r1-s1-O3 | HA | O3 | 16 | 0 | 11 | 0 |
| org45-r1-s1-F2 | HA | F2 | 8 | 0 | 5 | 0 |
| org45-r2-s0-O3 | LB | O3 | 3 | 2 | 0 | 0 |
| org45-r2-s0-F2 | LB | F2 | 2 | 1 | 0 | 0 |
| org45-r2-s0-S1 | LB | S1 | 1 | 1 | 0 | 0 |
| org45-r2-s1-F2 | LB | F2 | 3 | 2 | 0 | 0 |
| org45-r2-s1-S1 | LB | S1 | 1 | 1 | 0 | 0 |
| org45-r2-s1-O3 | LB | O3 | 3 | 1 | 0 | 0 |
| org45-r3-s0-S1 | HB | S1 | 8 | 0 | 7 | 0 |
| org45-r3-s0-F2 | HB | F2 | 9 | 0 | 7 | 0 |
| org45-r3-s0-O3 | HB | O3 | 3 | 0 | 3 | 0 |
| org45-r3-s1-F2 | HB | F2 | 11 | 0 | 9 | 0 |
| org45-r3-s1-O3 | HB | O3 | 11 | 0 | 9 | 0 |
| org45-r3-s1-S1 | HB | S1 | 12 | 0 | 10 | 0 |


| LB/HB槽 | 冻结声明符号 | 原程序工作记录 | 世界edit | 世界patch_fixed | 记录的伙伴patch读取/集成候选 |
|---|---|---|---|---|---|
| org45-r2-s0-O3 | {"rules.py":["evaluate"]} | 0 | 3 | 2 | 0 |
| org45-r2-s0-F2 | {"rules.py":["evaluate"]} | 0 | 2 | 1 | 0 |
| org45-r2-s0-S1 | {"rules.py":["evaluate"]} | 0 | 1 | 1 | 0 |
| org45-r2-s1-F2 | {"rules.py":["evaluate"]} | 0 | 3 | 2 | 0 |
| org45-r2-s1-S1 | {"rules.py":["evaluate"]} | 0 | 1 | 1 | 0 |
| org45-r2-s1-O3 | {"rules.py":["evaluate"]} | 0 | 3 | 1 | 1 |
| org45-r3-s0-S1 | {"migration.py":["migrate_v1_to_v2"],"rule_v2.py":["evaluate_v2"]} | 7 | 8 | 0 | 0 |
| org45-r3-s0-F2 | {"migration.py":["migrate_v1_to_v2"],"rule_v2.py":["evaluate_v2"]} | 7 | 9 | 0 | 0 |
| org45-r3-s0-O3 | {"migration.py":["migrate_v1_to_v2"],"rule_v2.py":["evaluate_v2"]} | 3 | 3 | 0 | 0 |
| org45-r3-s1-F2 | {"migration.py":["migrate_v1_to_v2"],"rule_v2.py":["evaluate_v2"]} | 9 | 11 | 0 | 0 |
| org45-r3-s1-O3 | {"migration.py":["migrate_v1_to_v2"],"rule_v2.py":["evaluate_v2"]} | 9 | 11 | 0 | 0 |
| org45-r3-s1-S1 | {"migration.py":["migrate_v1_to_v2"],"rule_v2.py":["evaluate_v2"]} | 10 | 12 | 0 | 0 |

真实edit和patch_fixed是世界事件，不自动证明被他人取得或使用；冻结关系数与世界补丁数定义不同，不相加为独立成果数。原冻结跟踪范围内未证实的链与文件级窄只读确认的应用须分开列示；不能把前者扩大为全轨迹无成果使用。实际伙伴读取/集成轨迹及字节变化是补充判据，不能仅看跟踪计数0。覆盖补充仅对本次LB/HB原件作有界只读核对；旧LA/HA证据复用，全部来源和字面差异另存机器文件。

## 5. 成果公开机会、业务义务与任务先后

下表为冻结跟踪关系内的公开与接收机会，不能覆盖未跟踪函数所形成的全部真实补丁。

| 槽/成果 | 作者→接收者 | 公开事件 | 当时可接收 | 后续机会 | 后续实际调用 | 取得 | 使用 | 连交付 |
|---|---|---|---|---|---|---|---|---|
| org45-r0-s0-F2/program:2:event_time.py:utc_date_key | member_001→member_002 | 7 | 是 | 4 | 4 | 否 | 否 | 否 |
| org45-r0-s0-O3/program:3:event_time.py:utc_date_key | member_001→member_002 | 12 | 是 | 5 | 4 | 否 | 否 | 否 |
| org45-r0-s1-F2/program:3:event_time.py:utc_date_key | member_002→member_001 | 9 | 是 | 3 | 3 | 否 | 否 | 否 |
| org45-r0-s1-O3/program:4:event_time.py:utc_date_key | member_001→member_002 | 10 | 是 | 5 | 5 | 否 | 否 | 否 |
| org45-r0-s1-O3/program:5:event_time.py:utc_date_key | member_002→member_001 | 13 | 否 | 0 | 0 | 否 | 否 | 否 |


### 文件级伙伴补丁应用的独立补充

已确认1次非同值伙伴补丁应用。这是原生动作、世界合并回执与源/前/后版本字节共同支持的文件级事实，原冻结符号测量的0/False仍保留，不重新定义或重算原stage。它与仅阅读、同值覆盖及信息语义待定不同。

| 槽 | 作者→接收者 | 实际integrate事件 | 接收前→后版本 | 文件确有变化 | 结果等于发布源 | 原跟踪已证链 | 随后测试/固定/提交 | 原交付早于应用 | 连新增接收者交付 |
|---|---|---|---|---|---|---|---|---|---|
| org45-r2-s1-O3 | member_001→member_002 | 29 | {"object_id":"obj-520aa9e6ee8ece99dce73855","version_id":"v2"}→{"object_id":"obj-520aa9e6ee8ece99dce73855","version_id":"v3"} | 是 | 是 | 否 | 0/0/0 | 是 | 否 |


LB/452/O3中，member_001的当前修改被固定为patch-1；member_002通过原生integrate_patch实际合并，自身rules.py由v2到v3，上界比较由<变为<=，结果与发布源逐字一致。集成回执确实进入后续实际输入。member_001的原成功交付已在集成前，002之后没有测试、固定或提交；随后读文件的正文也因团队预算终止未进入另一实际输入。因此该实例证实具体补丁的有效应用，不证明接收者后续验证、新增交付或因果收益。
文件层证据不能自动替换原符号级统计，也不自动成为可训练Contribution标签；两种观察粒度、原固定交付时序与未执行验证一并保留。
语义候选按独立只读证据另存，保留冻结pending；状态/协调消息实际进入接收者输入是通信事实，不能直接升级为具体代码或调查成果的可核验使用。语义待定与S1三条程序结构unknown分开。

| 语义候选槽 | 内容分类 | 实际取得消息 | 具体当前成果使用 | 原pending保留 |
|---|---|---|---|---|
| org45-r2-s0-F2 | completion_status_and_coordination_request | 是 | not_established | 是 |

以下另列LB/HB世界patch_fixed后的真实接收机会，可与冻结关系表重叠，不作为额外独立公开次数。程序跟踪公开为0时仍须检查这张世界事件表。

| 槽/世界patch | 作者→接收者 | 公开事件 | 当时可接收 | 后续机会 | 后续实际调用 |
|---|---|---|---|---|---|
| org45-r2-s0-O3/patch-1 | member_002→member_001 | 9 | 是 | 6 | 6 |
| org45-r2-s0-O3/patch-2 | member_001→member_002 | 16 | 是 | 3 | 2 |
| org45-r2-s0-F2/patch-1 | member_001→member_002 | 12 | 是 | 15 | 14 |
| org45-r2-s1-F2/patch-1 | member_002→member_001 | 8 | 是 | 6 | 6 |
| org45-r2-s1-F2/patch-2 | member_001→member_002 | 14 | 是 | 3 | 2 |
| org45-r2-s1-O3/patch-1 | member_001→member_002 | 23 | 是 | 6 | 5 |

“未公开”和“公开后未取得”分开分析：前者应看作者机会、成果价值及伙伴可达性，后者应看公开时接收者是否仍活动、后续调用、本人是否已有成果和可核验摩擦。上表只描述可达与行动，不推断动机、意识或因果收益。旧10嵌套摘要保留原资源视图；本轮新增的25→26准备机会只在专门修订回执中说明，不把旧摘要冒称已重写。

| 槽 | 工作类型 | 作者 | 首次机会调用 | 实际生成 | P+输出预约 | 硬余量 | 当时团队余额 | 后续实际调用 |
|---|---|---|---|---|---|---|---|---|
| org45-r0-s0-F2 | program | member_001 | model-0fbf5b1951dc1072aaa73461 | 是 | 12276+2048 | 2060 | 458967 | 3 |
| org45-r0-s0-F2 | information | member_001 | model-f48247cd77f57324aa9c8c58 | 是 | 14287+2048 | 49 | 434550 | 2 |
| org45-r0-s0-O3 | program | member_001 | model-2de8257010b17df69ff39026 | 是 | 12058+2048 | 2278 | 458855 | 8 |
| org45-r0-s0-O3 | information | member_001 | model-df43605dbba0357c9878badf | 是 | 13959+2048 | 377 | 434796 | 7 |
| org45-r0-s1-F2 | program | member_002 | model-c7997d356efd42d73540ab1b | 是 | 12007+2048 | 2329 | 437393 | 3 |
| org45-r0-s1-F2 | information | member_002 | model-1f2d11fd1c526518e959de85 | 是 | 13931+2048 | 405 | 413351 | 2 |
| org45-r0-s1-O3 | program | member_001 | model-93c8520e8e6377b0ae23f27b | 是 | 11931+2048 | 2405 | 425176 | 3 |
| org45-r0-s1-O3 | information | member_001 | model-6d8ea355ba71796af3e493aa | 是 | 13661+2048 | 675 | 400202 | 2 |
| org45-r1-s0-O3 | program | member_002 | model-10a1a82861977031fbb6cd43 | 是 | 13953+2048 | 383 | 424602 | 14 |
| org45-r1-s0-O3 | information | member_002 | model-7230777f5f6d88a197a67207 | 是 | 13693+2048 | 643 | 395467 | 13 |
| org45-r1-s0-F2 | program | member_002 | model-71c974d95cc1d34e25639b3f | 是 | 13984+2048 | 352 | 425391 | 0 |
| org45-r1-s1-O3 | program | member_002 | model-da9b3596b1da4de41e048d97 | 是 | 13559+2048 | 777 | 384874 | 13 |
| org45-r1-s1-F2 | program | member_002 | model-cb4dac8835ccf508c36b320b | 是 | 14040+2048 | 296 | 385537 | 12 |
| org45-r2-s0-O3 | information | member_002 | model-4e3e6f08193a6b3390ef323b | 是 | 13115+2048 | 1221 | 390635 | 5 |
| org45-r2-s0-F2 | information | member_001 | model-32adb1ee93aedbb589dd6d89 | 是 | 13205+2048 | 1131 | 404614 | 10 |
| org45-r2-s1-F2 | information | member_002 | model-c8ab04ff541bf8ed0f709c1d | 是 | 13152+2048 | 1184 | 407260 | 5 |
| org45-r2-s1-O3 | information | member_001 | model-023b038078af0416ccf5b7b5 | 是 | 13310+2048 | 1026 | 288241 | 8 |
| org45-r3-s0-F2 | program | member_001 | model-9d8f2f00568562296dcf5ade | 是 | 13238+2048 | 1098 | 342806 | 11 |
| org45-r3-s0-O3 | program | member_002 | model-184c6c477be9b612ac649150 | 是 | 14251+2048 | 85 | 406158 | 13 |
| org45-r3-s1-F2 | program | member_001 | model-5f869794ebee60b8ae9494db | 是 | 13727+2048 | 609 | 407433 | 5 |
| org45-r3-s1-O3 | program | member_002 | model-eff0f7a47ef72ea85ce0fa30 | 是 | 13808+2048 | 528 | 393123 | 13 |
| org45-r3-s1-O3 | information | member_001 | model-7051a6dd41ff5a6469f06921 | 是 | 13437+2048 | 899 | 233570 | 7 |

每槽每种冻结跟踪工作类型仅展示第一条已保存合法分享机会，不代表未跟踪函数产生的全部工程机会；完整关系/资源身份见机器摘要与封存测量，未发生生成的准备机会不能写成已执行分享。

业务义务只根据原合同、已保存的精确版本、既有报告与作者实际可见页分类，不执行新测试、不重验可变副本。有限用例通过不等于完整合同满足；“已有验证”必须结合通过/失败结果。

| 槽/成员 | root | 精确可变版本 | 义务 | 分类 | 当前有限检查 | 完整义务结论 |
|---|---|---|---|---|---|---|
| org45-r1-s0-O3/member_001 | HA | {"object_id":"obj-c567f5b9c7d905481548e89b","version_id":"v10"} | idempotence | 已有验证 | [{"test_id":"import-replay-idempotent","passed":false,"report_id":"test-report-91bad830d7843cc16690c352"}] | 已有反例，当前测试版本未满足 |
| org45-r1-s0-O3/member_001 | HA | {"object_id":"obj-c567f5b9c7d905481548e89b","version_id":"v10"} | revision_update | 已有验证 | [{"test_id":"import-higher-revision","passed":false,"report_id":"test-report-91bad830d7843cc16690c352"},{"test_id":"import-stale-after-restore","passed":false,"report_id":"test-report-91bad830d7843cc16690c352"}] | 已有反例，当前测试版本未满足 |
| org45-r1-s0-O3/member_001 | HA | {"object_id":"obj-c567f5b9c7d905481548e89b","version_id":"v10"} | atomic_conflict | 已有验证 | [{"test_id":"import-conflict-rollback","passed":false,"report_id":"test-report-91bad830d7843cc16690c352"}] | 已有反例，当前测试版本未满足 |
| org45-r1-s0-O3/member_001 | HA | {"object_id":"obj-c567f5b9c7d905481548e89b","version_id":"v10"} | restore_revision | 已有验证 | [{"test_id":"import-stale-after-restore","passed":false,"report_id":"test-report-91bad830d7843cc16690c352"}] | 已有反例，当前测试版本未满足 |
| org45-r1-s0-O3/member_001 | HA | {"object_id":"obj-c567f5b9c7d905481548e89b","version_id":"v10"} | recovery_replay | 尝试后未验证 | [] | 未知：有限通过或未测试不足以证明完整义务 |
| org45-r1-s0-O3/member_002 | HA | {"object_id":"obj-520aa9e6ee8ece99dce73855","version_id":"v5"} | idempotence | 尝试后未验证 | [] | 未知：有限通过或未测试不足以证明完整义务 |
| org45-r1-s0-O3/member_002 | HA | {"object_id":"obj-520aa9e6ee8ece99dce73855","version_id":"v5"} | revision_update | 尝试后未验证 | [] | 未知：有限通过或未测试不足以证明完整义务 |
| org45-r1-s0-O3/member_002 | HA | {"object_id":"obj-520aa9e6ee8ece99dce73855","version_id":"v5"} | atomic_conflict | 尝试后未验证 | [] | 未知：有限通过或未测试不足以证明完整义务 |
| org45-r1-s0-O3/member_002 | HA | {"object_id":"obj-520aa9e6ee8ece99dce73855","version_id":"v5"} | restore_revision | 尝试后未验证 | [] | 未知：有限通过或未测试不足以证明完整义务 |
| org45-r1-s0-O3/member_002 | HA | {"object_id":"obj-520aa9e6ee8ece99dce73855","version_id":"v5"} | recovery_replay | 尝试后未验证 | [] | 未知：有限通过或未测试不足以证明完整义务 |
| org45-r1-s0-S1/member_001 | HA | {"object_id":"obj-c567f5b9c7d905481548e89b","version_id":"v2"} | idempotence | 已有验证 | [{"test_id":"import-replay-idempotent","passed":true,"report_id":"test-report-b5c6d42b8b98e5493c6f8df7"}] | 未知：有限通过或未测试不足以证明完整义务 |
| org45-r1-s0-S1/member_001 | HA | {"object_id":"obj-c567f5b9c7d905481548e89b","version_id":"v2"} | revision_update | 已有验证 | [{"test_id":"import-higher-revision","passed":false,"report_id":"test-report-b5c6d42b8b98e5493c6f8df7"},{"test_id":"import-stale-after-restore","passed":false,"report_id":"test-report-b5c6d42b8b98e5493c6f8df7"}] | 已有反例，当前测试版本未满足 |
| org45-r1-s0-S1/member_001 | HA | {"object_id":"obj-c567f5b9c7d905481548e89b","version_id":"v2"} | atomic_conflict | 已有验证 | [{"test_id":"import-conflict-rollback","passed":true,"report_id":"test-report-b5c6d42b8b98e5493c6f8df7"}] | 未知：有限通过或未测试不足以证明完整义务 |
| org45-r1-s0-S1/member_001 | HA | {"object_id":"obj-c567f5b9c7d905481548e89b","version_id":"v2"} | restore_revision | 已有验证 | [{"test_id":"import-stale-after-restore","passed":false,"report_id":"test-report-b5c6d42b8b98e5493c6f8df7"}] | 已有反例，当前测试版本未满足 |
| org45-r1-s0-S1/member_001 | HA | {"object_id":"obj-c567f5b9c7d905481548e89b","version_id":"v2"} | recovery_replay | 尚无证据 | [] | 未知：有限通过或未测试不足以证明完整义务 |
| org45-r1-s0-F2/member_001 | HA | {"object_id":"obj-c567f5b9c7d905481548e89b","version_id":"v13"} | idempotence | 尝试后未验证 | [] | 未知：有限通过或未测试不足以证明完整义务 |
| org45-r1-s0-F2/member_001 | HA | {"object_id":"obj-c567f5b9c7d905481548e89b","version_id":"v13"} | revision_update | 尝试后未验证 | [] | 未知：有限通过或未测试不足以证明完整义务 |
| org45-r1-s0-F2/member_001 | HA | {"object_id":"obj-c567f5b9c7d905481548e89b","version_id":"v13"} | atomic_conflict | 尝试后未验证 | [] | 未知：有限通过或未测试不足以证明完整义务 |
| org45-r1-s0-F2/member_001 | HA | {"object_id":"obj-c567f5b9c7d905481548e89b","version_id":"v13"} | restore_revision | 尚无证据 | [] | 未知：有限通过或未测试不足以证明完整义务 |
| org45-r1-s0-F2/member_001 | HA | {"object_id":"obj-c567f5b9c7d905481548e89b","version_id":"v13"} | recovery_replay | 尚无证据 | [] | 未知：有限通过或未测试不足以证明完整义务 |
| org45-r1-s0-F2/member_002 | HA | {"object_id":"obj-520aa9e6ee8ece99dce73855","version_id":"v2"} | idempotence | 已有验证 | [{"test_id":"import-replay-idempotent","passed":true,"report_id":"test-report-3e01475a25b30a76790bd2a1"}] | 未知：有限通过或未测试不足以证明完整义务 |
| org45-r1-s0-F2/member_002 | HA | {"object_id":"obj-520aa9e6ee8ece99dce73855","version_id":"v2"} | revision_update | 已有验证 | [{"test_id":"import-higher-revision","passed":true,"report_id":"test-report-3e01475a25b30a76790bd2a1"},{"test_id":"import-stale-after-restore","passed":false,"report_id":"test-report-3e01475a25b30a76790bd2a1"}] | 已有反例，当前测试版本未满足 |
| org45-r1-s0-F2/member_002 | HA | {"object_id":"obj-520aa9e6ee8ece99dce73855","version_id":"v2"} | atomic_conflict | 已有验证 | [{"test_id":"import-conflict-rollback","passed":true,"report_id":"test-report-3e01475a25b30a76790bd2a1"}] | 未知：有限通过或未测试不足以证明完整义务 |
| org45-r1-s0-F2/member_002 | HA | {"object_id":"obj-520aa9e6ee8ece99dce73855","version_id":"v2"} | restore_revision | 已有验证 | [{"test_id":"import-stale-after-restore","passed":false,"report_id":"test-report-3e01475a25b30a76790bd2a1"}] | 已有反例，当前测试版本未满足 |
| org45-r1-s0-F2/member_002 | HA | {"object_id":"obj-520aa9e6ee8ece99dce73855","version_id":"v2"} | recovery_replay | 尚无证据 | [] | 未知：有限通过或未测试不足以证明完整义务 |
| org45-r1-s1-S1/member_001 | HA | {"object_id":"obj-c567f5b9c7d905481548e89b","version_id":"v13"} | idempotence | 尝试后未验证 | [] | 未知：有限通过或未测试不足以证明完整义务 |
| org45-r1-s1-S1/member_001 | HA | {"object_id":"obj-c567f5b9c7d905481548e89b","version_id":"v13"} | revision_update | 尝试后未验证 | [] | 未知：有限通过或未测试不足以证明完整义务 |
| org45-r1-s1-S1/member_001 | HA | {"object_id":"obj-c567f5b9c7d905481548e89b","version_id":"v13"} | atomic_conflict | 尝试后未验证 | [] | 未知：有限通过或未测试不足以证明完整义务 |
| org45-r1-s1-S1/member_001 | HA | {"object_id":"obj-c567f5b9c7d905481548e89b","version_id":"v13"} | restore_revision | 尝试后未验证 | [] | 未知：有限通过或未测试不足以证明完整义务 |
| org45-r1-s1-S1/member_001 | HA | {"object_id":"obj-c567f5b9c7d905481548e89b","version_id":"v13"} | recovery_replay | 尝试后未验证 | [] | 未知：有限通过或未测试不足以证明完整义务 |
| org45-r1-s1-O3/member_001 | HA | {"object_id":"obj-c567f5b9c7d905481548e89b","version_id":"v10"} | idempotence | 尝试后未验证 | [] | 未知；有限通过不覆盖完整合同 |
| org45-r1-s1-O3/member_001 | HA | {"object_id":"obj-c567f5b9c7d905481548e89b","version_id":"v10"} | revision_update | 尝试后未验证 | [] | 未知；有限通过不覆盖完整合同 |
| org45-r1-s1-O3/member_001 | HA | {"object_id":"obj-c567f5b9c7d905481548e89b","version_id":"v10"} | atomic_conflict | 尝试后未验证 | [] | 未知；有限通过不覆盖完整合同 |
| org45-r1-s1-O3/member_001 | HA | {"object_id":"obj-c567f5b9c7d905481548e89b","version_id":"v10"} | restore_revision | 尝试后未验证 | [] | 未知；有限通过不覆盖完整合同 |
| org45-r1-s1-O3/member_001 | HA | {"object_id":"obj-c567f5b9c7d905481548e89b","version_id":"v10"} | recovery_replay_direct | 尚无对应执行证据 | [] | 未知；有限通过不覆盖完整合同 |
| org45-r1-s1-O3/member_002 | HA | {"object_id":"obj-520aa9e6ee8ece99dce73855","version_id":"v8"} | idempotence | 尝试后未验证 | [] | 未知；有限通过不覆盖完整合同 |
| org45-r1-s1-O3/member_002 | HA | {"object_id":"obj-520aa9e6ee8ece99dce73855","version_id":"v8"} | revision_update | 尝试后未验证 | [] | 未知；有限通过不覆盖完整合同 |
| org45-r1-s1-O3/member_002 | HA | {"object_id":"obj-520aa9e6ee8ece99dce73855","version_id":"v8"} | atomic_conflict | 尝试后未验证 | [] | 未知；有限通过不覆盖完整合同 |
| org45-r1-s1-O3/member_002 | HA | {"object_id":"obj-520aa9e6ee8ece99dce73855","version_id":"v8"} | restore_revision | 尚无对应执行证据 | [] | 未知；有限通过不覆盖完整合同 |
| org45-r1-s1-O3/member_002 | HA | {"object_id":"obj-520aa9e6ee8ece99dce73855","version_id":"v8"} | recovery_replay_direct | 尚无对应执行证据 | [] | 未知；有限通过不覆盖完整合同 |
| org45-r1-s1-F2/member_001 | HA | {"object_id":"obj-c567f5b9c7d905481548e89b","version_id":"v6"} | idempotence | 尝试后未验证 | [] | 未知；有限通过不覆盖完整合同 |
| org45-r1-s1-F2/member_001 | HA | {"object_id":"obj-c567f5b9c7d905481548e89b","version_id":"v6"} | revision_update | 尝试后未验证 | [] | 未知；有限通过不覆盖完整合同 |
| org45-r1-s1-F2/member_001 | HA | {"object_id":"obj-c567f5b9c7d905481548e89b","version_id":"v6"} | atomic_conflict | 尝试后未验证 | [] | 未知；有限通过不覆盖完整合同 |
| org45-r1-s1-F2/member_001 | HA | {"object_id":"obj-c567f5b9c7d905481548e89b","version_id":"v6"} | restore_revision | 尚无对应执行证据 | [] | 未知；有限通过不覆盖完整合同 |
| org45-r1-s1-F2/member_001 | HA | {"object_id":"obj-c567f5b9c7d905481548e89b","version_id":"v6"} | recovery_replay_direct | 尚无对应执行证据 | [] | 未知；有限通过不覆盖完整合同 |
| org45-r1-s1-F2/member_002 | HA | {"object_id":"obj-520aa9e6ee8ece99dce73855","version_id":"v4"} | idempotence | 尝试后未验证 | [] | 未知；有限通过不覆盖完整合同 |
| org45-r1-s1-F2/member_002 | HA | {"object_id":"obj-520aa9e6ee8ece99dce73855","version_id":"v4"} | revision_update | 尝试后未验证 | [] | 未知；有限通过不覆盖完整合同 |
| org45-r1-s1-F2/member_002 | HA | {"object_id":"obj-520aa9e6ee8ece99dce73855","version_id":"v4"} | atomic_conflict | 尝试后未验证 | [] | 未知；有限通过不覆盖完整合同 |
| org45-r1-s1-F2/member_002 | HA | {"object_id":"obj-520aa9e6ee8ece99dce73855","version_id":"v4"} | restore_revision | 尝试后未验证 | [] | 未知；有限通过不覆盖完整合同 |
| org45-r1-s1-F2/member_002 | HA | {"object_id":"obj-520aa9e6ee8ece99dce73855","version_id":"v4"} | recovery_replay_direct | 尚无对应执行证据 | [] | 未知；有限通过不覆盖完整合同 |
| org45-r3-s0-S1/member_001 | HB | {"object_id":"obj-c567f5b9c7d905481548e89b","version_id":"v9"} | missing_versus_null | 尝试后未验证 | [] | 未知；有限通过不覆盖完整合同 |
| org45-r3-s0-S1/member_001 | HB | {"object_id":"obj-c567f5b9c7d905481548e89b","version_id":"v9"} | nested_present_null | 尝试后未验证 | [] | 未知；有限通过不覆盖完整合同 |
| org45-r3-s0-S1/member_001 | HB | {"object_id":"obj-c567f5b9c7d905481548e89b","version_id":"v9"} | not_and_semantics | 尝试后未验证 | [] | 未知；有限通过不覆盖完整合同 |
| org45-r3-s0-S1/member_001 | HB | {"object_id":"obj-c567f5b9c7d905481548e89b","version_id":"v9"} | source_error_path | 尝试后未验证 | [] | 未知；有限通过不覆盖完整合同 |
| org45-r3-s0-S1/member_001 | HB | {"object_id":"obj-c567f5b9c7d905481548e89b","version_id":"v9"} | direct_v2_validation | 尚无对应执行证据 | [] | 未知；有限通过不覆盖完整合同 |
| org45-r3-s0-S1/member_001 | HB | {"object_id":"obj-c567f5b9c7d905481548e89b","version_id":"v9"} | complete_bounds_and_mutation_contract | 尚无对应执行证据 | [] | 未知；有限通过不覆盖完整合同 |
| org45-r3-s0-F2/member_001 | HB | {"object_id":"obj-c567f5b9c7d905481548e89b","version_id":"v5"} | missing_versus_null | 尝试后未验证 | [] | 未知；有限通过不覆盖完整合同 |
| org45-r3-s0-F2/member_001 | HB | {"object_id":"obj-c567f5b9c7d905481548e89b","version_id":"v5"} | nested_present_null | 尝试后未验证 | [] | 未知；有限通过不覆盖完整合同 |
| org45-r3-s0-F2/member_001 | HB | {"object_id":"obj-c567f5b9c7d905481548e89b","version_id":"v5"} | not_and_semantics | 尝试后未验证 | [] | 未知；有限通过不覆盖完整合同 |
| org45-r3-s0-F2/member_001 | HB | {"object_id":"obj-c567f5b9c7d905481548e89b","version_id":"v5"} | source_error_path | 尝试后未验证 | [] | 未知；有限通过不覆盖完整合同 |
| org45-r3-s0-F2/member_001 | HB | {"object_id":"obj-c567f5b9c7d905481548e89b","version_id":"v5"} | direct_v2_validation | 尚无对应执行证据 | [] | 未知；有限通过不覆盖完整合同 |
| org45-r3-s0-F2/member_001 | HB | {"object_id":"obj-c567f5b9c7d905481548e89b","version_id":"v5"} | complete_bounds_and_mutation_contract | 尚无对应执行证据 | [] | 未知；有限通过不覆盖完整合同 |
| org45-r3-s0-F2/member_002 | HB | {"object_id":"obj-520aa9e6ee8ece99dce73855","version_id":"v6"} | missing_versus_null | 尝试后未验证 | [] | 未知；有限通过不覆盖完整合同 |
| org45-r3-s0-F2/member_002 | HB | {"object_id":"obj-520aa9e6ee8ece99dce73855","version_id":"v6"} | nested_present_null | 尝试后未验证 | [] | 未知；有限通过不覆盖完整合同 |
| org45-r3-s0-F2/member_002 | HB | {"object_id":"obj-520aa9e6ee8ece99dce73855","version_id":"v6"} | not_and_semantics | 尝试后未验证 | [] | 未知；有限通过不覆盖完整合同 |
| org45-r3-s0-F2/member_002 | HB | {"object_id":"obj-520aa9e6ee8ece99dce73855","version_id":"v6"} | source_error_path | 尝试后未验证 | [] | 未知；有限通过不覆盖完整合同 |
| org45-r3-s0-F2/member_002 | HB | {"object_id":"obj-520aa9e6ee8ece99dce73855","version_id":"v6"} | direct_v2_validation | 尚无对应执行证据 | [] | 未知；有限通过不覆盖完整合同 |
| org45-r3-s0-F2/member_002 | HB | {"object_id":"obj-520aa9e6ee8ece99dce73855","version_id":"v6"} | complete_bounds_and_mutation_contract | 尚无对应执行证据 | [] | 未知；有限通过不覆盖完整合同 |
| org45-r3-s0-O3/member_001 | HB | {"object_id":"obj-c567f5b9c7d905481548e89b","version_id":"v2"} | missing_versus_null | 尝试后未验证 | [] | 未知；有限通过不覆盖完整合同 |
| org45-r3-s0-O3/member_001 | HB | {"object_id":"obj-c567f5b9c7d905481548e89b","version_id":"v2"} | nested_present_null | 尝试后未验证 | [] | 未知；有限通过不覆盖完整合同 |
| org45-r3-s0-O3/member_001 | HB | {"object_id":"obj-c567f5b9c7d905481548e89b","version_id":"v2"} | not_and_semantics | 尝试后未验证 | [] | 未知；有限通过不覆盖完整合同 |
| org45-r3-s0-O3/member_001 | HB | {"object_id":"obj-c567f5b9c7d905481548e89b","version_id":"v2"} | source_error_path | 尝试后未验证 | [] | 未知；有限通过不覆盖完整合同 |
| org45-r3-s0-O3/member_001 | HB | {"object_id":"obj-c567f5b9c7d905481548e89b","version_id":"v2"} | direct_v2_validation | 尚无对应执行证据 | [] | 未知；有限通过不覆盖完整合同 |
| org45-r3-s0-O3/member_001 | HB | {"object_id":"obj-c567f5b9c7d905481548e89b","version_id":"v2"} | complete_bounds_and_mutation_contract | 尚无对应执行证据 | [] | 未知；有限通过不覆盖完整合同 |
| org45-r3-s0-O3/member_002 | HB | {"object_id":"obj-520aa9e6ee8ece99dce73855","version_id":"v3"} | missing_versus_null | 尝试后未验证 | [] | 未知；有限通过不覆盖完整合同 |
| org45-r3-s0-O3/member_002 | HB | {"object_id":"obj-520aa9e6ee8ece99dce73855","version_id":"v3"} | nested_present_null | 尝试后未验证 | [] | 未知；有限通过不覆盖完整合同 |
| org45-r3-s0-O3/member_002 | HB | {"object_id":"obj-520aa9e6ee8ece99dce73855","version_id":"v3"} | not_and_semantics | 尝试后未验证 | [] | 未知；有限通过不覆盖完整合同 |
| org45-r3-s0-O3/member_002 | HB | {"object_id":"obj-520aa9e6ee8ece99dce73855","version_id":"v3"} | source_error_path | 尝试后未验证 | [] | 未知；有限通过不覆盖完整合同 |
| org45-r3-s0-O3/member_002 | HB | {"object_id":"obj-520aa9e6ee8ece99dce73855","version_id":"v3"} | direct_v2_validation | 尚无对应执行证据 | [] | 未知；有限通过不覆盖完整合同 |
| org45-r3-s0-O3/member_002 | HB | {"object_id":"obj-520aa9e6ee8ece99dce73855","version_id":"v3"} | complete_bounds_and_mutation_contract | 尚无对应执行证据 | [] | 未知；有限通过不覆盖完整合同 |
| org45-r3-s1-F2/member_001 | HB | {"object_id":"obj-c567f5b9c7d905481548e89b","version_id":"v4"} | missing_versus_null | 已有验证 | [{"test_id":"migration-missing-versus-null","passed":false}] | 已有当前用例反例 |
| org45-r3-s1-F2/member_001 | HB | {"object_id":"obj-c567f5b9c7d905481548e89b","version_id":"v4"} | nested_present_null | 已有验证 | [{"test_id":"migration-nested-present-null","passed":false}] | 已有当前用例反例 |
| org45-r3-s1-F2/member_001 | HB | {"object_id":"obj-c567f5b9c7d905481548e89b","version_id":"v4"} | not_and_semantics | 已有验证 | [{"test_id":"migration-not-and","passed":true}] | 未知；有限通过不覆盖完整合同 |
| org45-r3-s1-F2/member_001 | HB | {"object_id":"obj-c567f5b9c7d905481548e89b","version_id":"v4"} | source_error_path | 已有验证 | [{"test_id":"migration-error-source-path","passed":true}] | 未知；有限通过不覆盖完整合同 |
| org45-r3-s1-F2/member_001 | HB | {"object_id":"obj-c567f5b9c7d905481548e89b","version_id":"v4"} | direct_v2_validation | 尚无对应执行证据 | [] | 未知；有限通过不覆盖完整合同 |
| org45-r3-s1-F2/member_001 | HB | {"object_id":"obj-c567f5b9c7d905481548e89b","version_id":"v4"} | complete_bounds_and_mutation_contract | 尚无对应执行证据 | [] | 未知；有限通过不覆盖完整合同 |
| org45-r3-s1-F2/member_002 | HB | {"object_id":"obj-520aa9e6ee8ece99dce73855","version_id":"v9"} | missing_versus_null | 尝试后未验证 | [] | 未知；有限通过不覆盖完整合同 |
| org45-r3-s1-F2/member_002 | HB | {"object_id":"obj-520aa9e6ee8ece99dce73855","version_id":"v9"} | nested_present_null | 尝试后未验证 | [] | 未知；有限通过不覆盖完整合同 |
| org45-r3-s1-F2/member_002 | HB | {"object_id":"obj-520aa9e6ee8ece99dce73855","version_id":"v9"} | not_and_semantics | 尝试后未验证 | [] | 未知；有限通过不覆盖完整合同 |
| org45-r3-s1-F2/member_002 | HB | {"object_id":"obj-520aa9e6ee8ece99dce73855","version_id":"v9"} | source_error_path | 尝试后未验证 | [] | 未知；有限通过不覆盖完整合同 |
| org45-r3-s1-F2/member_002 | HB | {"object_id":"obj-520aa9e6ee8ece99dce73855","version_id":"v9"} | direct_v2_validation | 尚无对应执行证据 | [] | 未知；有限通过不覆盖完整合同 |
| org45-r3-s1-F2/member_002 | HB | {"object_id":"obj-520aa9e6ee8ece99dce73855","version_id":"v9"} | complete_bounds_and_mutation_contract | 尚无对应执行证据 | [] | 未知；有限通过不覆盖完整合同 |
| org45-r3-s1-O3/member_001 | HB | {"object_id":"obj-c567f5b9c7d905481548e89b","version_id":"v5"} | missing_versus_null | 尝试后未验证 | [] | 未知；有限通过不覆盖完整合同 |
| org45-r3-s1-O3/member_001 | HB | {"object_id":"obj-c567f5b9c7d905481548e89b","version_id":"v5"} | nested_present_null | 尝试后未验证 | [] | 未知；有限通过不覆盖完整合同 |
| org45-r3-s1-O3/member_001 | HB | {"object_id":"obj-c567f5b9c7d905481548e89b","version_id":"v5"} | not_and_semantics | 尝试后未验证 | [] | 未知；有限通过不覆盖完整合同 |
| org45-r3-s1-O3/member_001 | HB | {"object_id":"obj-c567f5b9c7d905481548e89b","version_id":"v5"} | source_error_path | 尝试后未验证 | [] | 未知；有限通过不覆盖完整合同 |
| org45-r3-s1-O3/member_001 | HB | {"object_id":"obj-c567f5b9c7d905481548e89b","version_id":"v5"} | direct_v2_validation | 尚无对应执行证据 | [] | 未知；有限通过不覆盖完整合同 |
| org45-r3-s1-O3/member_001 | HB | {"object_id":"obj-c567f5b9c7d905481548e89b","version_id":"v5"} | complete_bounds_and_mutation_contract | 尚无对应执行证据 | [] | 未知；有限通过不覆盖完整合同 |
| org45-r3-s1-O3/member_002 | HB | {"object_id":"obj-520aa9e6ee8ece99dce73855","version_id":"v8"} | missing_versus_null | 尝试后未验证 | [] | 未知；有限通过不覆盖完整合同 |
| org45-r3-s1-O3/member_002 | HB | {"object_id":"obj-520aa9e6ee8ece99dce73855","version_id":"v8"} | nested_present_null | 尝试后未验证 | [] | 未知；有限通过不覆盖完整合同 |
| org45-r3-s1-O3/member_002 | HB | {"object_id":"obj-520aa9e6ee8ece99dce73855","version_id":"v8"} | not_and_semantics | 尝试后未验证 | [] | 未知；有限通过不覆盖完整合同 |
| org45-r3-s1-O3/member_002 | HB | {"object_id":"obj-520aa9e6ee8ece99dce73855","version_id":"v8"} | source_error_path | 尝试后未验证 | [] | 未知；有限通过不覆盖完整合同 |
| org45-r3-s1-O3/member_002 | HB | {"object_id":"obj-520aa9e6ee8ece99dce73855","version_id":"v8"} | direct_v2_validation | 尚无对应执行证据 | [] | 未知；有限通过不覆盖完整合同 |
| org45-r3-s1-O3/member_002 | HB | {"object_id":"obj-520aa9e6ee8ece99dce73855","version_id":"v8"} | complete_bounds_and_mutation_contract | 尚无对应执行证据 | [] | 未知；有限通过不覆盖完整合同 |
| org45-r3-s1-S1/member_001 | HB | {"object_id":"obj-c567f5b9c7d905481548e89b","version_id":"v13"} | missing_versus_null | 已有验证 | [{"test_id":"migration-missing-versus-null","passed":false}] | 已有当前用例反例 |
| org45-r3-s1-S1/member_001 | HB | {"object_id":"obj-c567f5b9c7d905481548e89b","version_id":"v13"} | nested_present_null | 已有验证 | [{"test_id":"migration-nested-present-null","passed":false}] | 已有当前用例反例 |
| org45-r3-s1-S1/member_001 | HB | {"object_id":"obj-c567f5b9c7d905481548e89b","version_id":"v13"} | not_and_semantics | 已有验证 | [{"test_id":"migration-not-and","passed":false}] | 已有当前用例反例 |
| org45-r3-s1-S1/member_001 | HB | {"object_id":"obj-c567f5b9c7d905481548e89b","version_id":"v13"} | source_error_path | 已有验证 | [{"test_id":"migration-error-source-path","passed":true}] | 未知；有限通过不覆盖完整合同 |
| org45-r3-s1-S1/member_001 | HB | {"object_id":"obj-c567f5b9c7d905481548e89b","version_id":"v13"} | direct_v2_validation | 尚无对应执行证据 | [] | 未知；有限通过不覆盖完整合同 |
| org45-r3-s1-S1/member_001 | HB | {"object_id":"obj-c567f5b9c7d905481548e89b","version_id":"v13"} | complete_bounds_and_mutation_contract | 尚无对应执行证据 | [] | 未知；有限通过不覆盖完整合同 |

HA恢复后revision是否保留不能仅由“没有编辑recovery.py”下结论：静态置零循环、其它入口候选与公共客户端实际调用路径分别记录。HB的缺失/null、嵌套错误位置与语义迁移也只按已有精确版本观察分类，未覆盖边界保持未知。审计定位未注入剩余14槽提示。

| 槽/任务 | 发布者 | 发布事件 | 本人首次编辑 | 全队首次编辑 | 早于本人 | 早于全队 |
|---|---|---|---|---|---|---|
| org45-r0-s0-O3/fix_utc_date_key | member_001 | 8 | 3 | 3 | 否 | 否 |
| org45-r2-s0-F2/fix-between-operator | member_002 | 8 | 28 | 4 | 是 | 否 |
| org45-r2-s0-F2/fix-between-operator-boundary | member_002 | 10 | 28 | 4 | 是 | 否 |
| org45-r2-s0-S1/fix_rules | member_001 | 2 | 3 | 3 | 是 | 是 |
| org45-r2-s1-O3/fix_rules_between | member_002 | 3 | 7 | 6 | 是 | 是 |

在已执行24槽的保存轨迹中，任务发布事件5项；早于全队首次编辑2项，早于发布者本人首次编辑4项。无编辑时标null，不补成先任务后编辑。该顺序诊断不等同协作使用链，也不外推到未启动槽或全部历史。

### 任务与制度结果的可解释范围

原24库存已执行24槽，成功12槽，未提交或未通过12槽；其余0槽未作为R0补入。完整八块等权F2−S1=0.0，O3−F2=0.0。完整原面板已形成。



| 人工root | S1 | F2 | O3 | 成功数 | 已执行 |
| --- | --- | --- | --- | --- | --- |
| LA | 成功2/2；原分母2 | 成功2/2；原分母2 | 成功2/2；原分母2 | 6 | 6 |
| HA | 成功0/2；原分母2 | 成功0/2；原分母2 | 成功0/2；原分母2 | 0 | 6 |
| LB | 成功2/2；原分母2 | 成功2/2；原分母2 | 成功2/2；原分母2 | 6 | 6 |
| HB | 成功0/2；原分母2 | 成功0/2；原分母2 | 成功0/2；原分母2 | 0 | 6 |



四个root属于两个相关的人工事件／规则接口家族，不能当作四个独立真实产品来源。F2−S1包含多私有历史、协调机会与开销的制度组合差异；O3−F2衡量提供动态人数选择权后的结果，不等于实际增员的因果收益。

LA两个seed的三个制度都成功，token分别为S1 215,599、F2 327,828、O3 456,455；相邻制度增加52.05%和39.24%。这是一个root、两个seed的局部成本事实，不能推广为一般多智能体低效，也不能把没有出生的O3成本差归为实际招募成本。


### 成果使用链与实际伙伴机会

已执行中16槽有伙伴制度、8槽为真实S1。冻结跟踪符号口径中已证跨成员使用的有伙伴槽为0，实际新出生总数为0。原口径之外的源文件级有效应用另列，不能由原0覆盖该真实事件。S1无伙伴属于不适用，不能加入协作失败分母。

制度／程序与信息的五阶段完整计数见正文原测量表；这里保留其冻结跟踪范围，不另改变分母。

表中程序计数仅覆盖冻结声明的跟踪符号，不等于所有真实代码改动或固定补丁数。关系记录按版本／函数／接收者记录，多个关系可来自同一个episode和重复修改，不能当成独立实验，也不能假定每项产物都值得复用。可访问、输入含元数据、读取、具体使用、连至最终交付必须分开。产生阶段的结构unknown也不能直接当成未知协作链。

LB/452/S1提供实际分页消费实例：一次run_tests报告自动返回第0页后，模型主动读取第1、2页，两次返回均进入实际后续输入，三个正文页最终全部实际呈现；报告只执行一次测试。完整页读不是验收或继续运行的条件，这只是合法分页路径被实际使用的证据。

原HA/452/S1的三条snapshot结构unknown完整保留。仅补齐宿主预算前准备证据后，真实S1的三个使用聚合由旧null派生为false（无伙伴不适用）；历史null保留，不是发现了新使用证据，也没有修改原R。

公开后接收者的机会明细见正文世界事件表及源绑定机器记录。

原LA五条公开关系中，前四条的接收者随后有真实调用，首个实际输入也确含该补丁元数据；第五条LA/452/O3 patch-2发布时001已经提交并退役，没有后续机会。前四条均在接收者已有自己实现之后公开，其中三条在接收者自己的公开测试通过之后。没有取得不能被解释成普遍接口不可用，已有自己成果也不证明伙伴补丁无价值。

对每个新公开关系，表格只绑定公开时可达性、后续机会及接收者此前自己的工作；不由这些事实推断模型私有认知、缺动机或缺能力。HA未公开的关系先停在作者侧，不能直接归因于接收端取得摩擦。


### 冻结程序跟踪范围与真实代码公开的区别

工作测量按预先声明的顶层符号取结构指纹，不递归跟踪所有被调用的辅助函数。因而跟踪符号未变，不能等同于源文件没有产生工作；未进入程序关系表，也不等同于没有合法公开补丁。下面同时保留原测量和原世界事件，两者不合并改类。

各LB/HB槽的冻结符号、实际编辑和固定补丁、原跟踪计数已在正文并表，数值保持原件。

LB/451/O3给出了明确实例：冻结只跟踪rules.py的evaluate；两个成员实际修改的是validate_rule中的嵌套错误位置和_evaluate中的上端点<→<=。原evaluate指纹不变，所以冻结work记0程序产物，但既有版本字面差异与世界记录仍显示3次编辑、2次固定补丁。原R1、原stage计数和原证据均保留，没有扩展符号、重算指纹或追加验收。

LB/451/O3两次公开均仍有可达伙伴：patch-1的接收者随后有6次真实调用；patch-2的接收者随后有3次机会、2次真实调用，并且已经通过自己的测试。两个公开均未产生伙伴patch读取或集成。

这些世界公开事实补足描述范围，不自动升级为成果使用链。实际伙伴patch读取／集成候选在机器覆盖明细独立列出；没有这些行为的轨迹可支持未观察到该取得路径，不能用跟踪符号计数0代替这项核对。信息传播或语义使用另按其原输入和行为证据判断。


### HA失败路径与恢复义务

HA已执行6/6，成功0。原HA/451/S1第一次测试反馈被早期context截断；原HA/451/F2一名成员测试后被截断，伙伴继续但不测试；原HA/451/O3曾生成测试结果和早期分享机会，但没有当前成果公开；原HA/452/S1工作到498,562 token，v5后八次编辑没有复验，最后成员固定预算先拒绝。上述路径不能合并成单一16K解释。

本次补完的HA/452/O3和F2分别35次调用、498,914和492,735 token；两槽均未执行一次run_tests、未公开当前成果，最后按共享预算正常停止，均没有硬context拒绝。O3有16次落盘编辑，F2有8次，均只编辑event_store.py。它们提供“反复编辑而验证／交付未闭合”的实际证据；不能据此推定更长context必然解决问题。



| 槽 | 成员 | 最终可变版本 | 编辑数 | 既有测试版本 | 末测后编辑/从未测时全部编辑 | recovery归零语句仍在 |
| --- | --- | --- | --- | --- | --- | --- |
| org45-r1-s0-O3 | member_001 | v10 | 9 | v10 | 0 | True |
| org45-r1-s0-O3 | member_002 | v5 | 4 | v2,v3 | 2 | True |
| org45-r1-s0-S1 | member_001 | v2 | 1 | v2 | 0 | True |
| org45-r1-s0-F2 | member_001 | v13 | 12 | 未测试 | 12 | True |
| org45-r1-s0-F2 | member_002 | v2 | 1 | v2 | 0 | True |
| org45-r1-s1-S1 | member_001 | v13 | 12 | v5 | 8 | True |
| org45-r1-s1-O3 | member_001 | v10 | 9 | 未测试 | 9 | True |
| org45-r1-s1-O3 | member_002 | v8 | 7 | 未测试 | 7 | True |
| org45-r1-s1-F2 | member_001 | v6 | 5 | 未测试 | 5 | True |
| org45-r1-s1-F2 | member_002 | v4 | 3 | 未测试 | 3 | True |



旧六份实际HA报告的import-stale-after-restore均失败；三份报告未进入后续实际输入，另外三份只呈现第0页，恢复失败完整正文不在这些实际页内。目录和公共初始诊断另计，不能把完整存储报告等同于作者实际读完，也不能声称作者完全不知道恢复义务。

定向静态阅读发现既有最终候选的正式recovery恢复路径仍保留revision归零；部分成员在event_store中另写restore/replay，属于候选尝试，不能自动视为正式recovery入口已修复。新槽明细仅记录归零语句、同名函数和公开客户端调用的静态事实，不通过未编辑文件名断言整个最终程序必然错误。所有未测试最终版本保持未验证；原R仍以固定交付规则判断，未追加验收。


### HB语义迁移义务与验证范围

本阶段实际审阅HB 6/6槽。以下只汇总既有测试和对应精确版本；migration缺失／null、嵌套路径、not/all组合、源错误位置分别列入机器义务表，不以只读legacy检查通过冒充新v2行为通过。



| 槽 | 成员 | 实际编辑路径 | 最终可变版本 | 既有测试版本 | 末测后编辑/未测全部 | 当前有限检查 |
| --- | --- | --- | --- | --- | --- | --- |
| org45-r3-s0-S1 | member_001 | migration.py | v9 | v2,v8 | 1 | 当前版本暂无对应有限用例结果 |
| org45-r3-s0-F2 | member_001 | migration.py | v5 | 未测试 | 4 | 当前版本暂无对应有限用例结果 |
| org45-r3-s0-F2 | member_002 | migration.py | v6 | 未测试 | 5 | 当前版本暂无对应有限用例结果 |
| org45-r3-s0-O3 | member_001 | migration.py | v2 | 未测试 | 1 | 当前版本暂无对应有限用例结果 |
| org45-r3-s0-O3 | member_002 | migration.py,rule_v2.py | v3 | 未测试 | 2 | 当前版本暂无对应有限用例结果 |
| org45-r3-s1-F2 | member_001 | migration.py | v4 | v4 | 0 | missing_versus_null:migration-missing-versus-null=False; nested_present_null:migration-nested-present-null=False; not_and_semantics:migration-not-and=True; source_error_path:migration-error-source-path=True |
| org45-r3-s1-F2 | member_002 | migration.py,rule_v2.py | v9 | 未测试 | 8 | 当前版本暂无对应有限用例结果 |
| org45-r3-s1-O3 | member_001 | migration.py | v5 | v4 | 1 | 当前版本暂无对应有限用例结果 |
| org45-r3-s1-O3 | member_002 | migration.py,rule_v2.py | v8 | v7 | 1 | 当前版本暂无对应有限用例结果 |
| org45-r3-s1-S1 | member_001 | migration.py,rule_v2.py | v13 | v4,v13 | 0 | missing_versus_null:migration-missing-versus-null=False; nested_present_null:migration-nested-present-null=False; not_and_semantics:migration-not-and=False; source_error_path:migration-error-source-path=True |





| 槽 | 成员 | 原测试版本 | 通过/总例 | 未通过用例 | 实际正文页 | 既有执行错误/不匹配 |
| --- | --- | --- | --- | --- | --- | --- |
| org45-r3-s0-S1 | member_001 | v2 | 3/6 | migration-missing-versus-null,migration-not-and,migration-nested-present-null | 0 | builtins.KeyError:'kind' |
| org45-r3-s0-S1 | member_001 | v8 | 3/6 | migration-missing-versus-null,migration-not-and,migration-nested-present-null | 0 | builtins.NameError:name 'document' is not defined |
| org45-r3-s1-F2 | member_001 | v4 | 4/6 | migration-missing-versus-null,migration-nested-present-null |  | non-exception mismatch: |
| org45-r3-s1-O3 | member_001 | v4 | 4/6 | migration-missing-versus-null,migration-nested-present-null | 0 | non-exception mismatch: |
| org45-r3-s1-O3 | member_002 | v7 | 2/6 | migration-missing-versus-null,migration-not-and,migration-nested-present-null,migration-error-source-path | 0 | builtins.TypeError:validate_rule() takes 1 positional argument but 2 were given |
| org45-r3-s1-S1 | member_001 | v4 | 4/6 | migration-missing-versus-null,migration-nested-present-null | 0 | non-exception mismatch: |
| org45-r3-s1-S1 | member_001 | v13 | 3/6 | migration-missing-versus-null,migration-not-and,migration-nested-present-null |  | builtins.ValueError:$.rules[1].rule.value:scalar_required; builtins.ValueError:$.value:missing; non-exception mismatch: |



HB/451/S1的v2、v8分别在三个迁移用例上抛KeyError(kind)和NameError(document未定义)。这些既有失败不能直接解释成已经定位了missing/null或逻辑组合的返回值语义错误；执行先在异常处未完成。最终v9没有复验，不推断其运行结果。

HB/452/F2的001-v4则已经得到实际语义反例：missing/null期望[false,true]但返回[true,true]；嵌套exists期望[false,true]但返回[false,false]，其余四例通过。这份当前报告因下一请求仅超硬context 6 token而未呈现，当时余额236,731。伙伴随后继续编辑migration.py和rule_v2.py但没有测试，不能把该伙伴最后v9的结果由001-v4外推。

HB/452/O3提供另一种路径：001-v4同样仅missing/null和嵌套exists两例失败，002-v7的四个新迁移用例则均在validate_rule参数数目不符处抛TypeError，只有两个legacy检查通过。两份报告的第0页均实际呈现，missing/null失败完整正文进入各自下一实际输入；二人随后分别再编辑一次到v5和v8，却没有复验或固定提交，最后是共享预算停止，没有硬context拒绝。这里已有实际诊断取得，但最终改动是否解决问题仍未验证。

HB/452/S1最终v13已有当前版本测试，不能与未复验候选混为一谈：v4通过4/6，v13通过3/6。v13在missing/null和not/all用例分别抛ValueError（$.value:missing和$.rules[1].rule.value:scalar_required），嵌套exists仍返回[false,false]而非[false,true]；两个legacy和源错误位置用例通过。v4第0页实际呈现，最终v13报告已生成但没有后续呈现：下一请求实际准备为12942+2048 token，余额7695，成员固定model meter先拒绝；硬context尚余1394 token，无实际生成、收费或世界副作用。正式R0仍由无固定提交判定，不追加验收。

直接接受规范v2、畸形v2、全部深度／节点边界和完整不变性，不能只由几条迁移公开用例证明；若缺少对应既有证据，保留未知。成员脚本若实际执行则需按记录单独核对，不能把“未列入固定公开表”说成绝对没有做过。当前可变树也不替代已提交固定树，正式R引用原验收结果，不补验未提交树。


### 一条跨成员补丁的非同值实际应用

LB/452/O3的源文件层面出现一次可核验的跨成员有效应用。001先实际修复、测试，在世界序号23固定patch-1，序号25提交；002此前自己的v2只修好嵌套错误位置，between的上端比较仍为<。002在序号29自主调用integrate_patch，工具无冲突地把这处比较改为伙伴固定源中的<=；合并后所有文件与001固定源相同。它不是仅添加补丁ID的同值操作，也不是002早已独立完成同一上端实现。

原生工具输出、调用／成员身份、固定源、接收者before/after字节及成功回执已逐项绑定。导入成功回执进入002下一次真实生成；这次生成随后读取新的v3文件，但读回的完整代码正文因共享预算停止没有进入再下一实际输入。因此可确认模型选择并执行了文件应用、随后实际看到成功回执，不能声称它已阅读或理解完整导入代码。

作者001在序号27已经退役，固定补丁仍可供002合法导入。该事实区分了成员继续可调度与已公开固定成果持续可用。接收者导入后没有再测试、固定或提交；本槽R1来自更早的作者提交，不能将有效文件应用归为新增交付或因果收益。

冻结测量只跟踪rules.evaluate包装函数，实际迁移的修复位于_evaluate辅助函数；原程序阶段0/false保持。这里另存源文件层面的正面应用证据，不热改原指标，也不把单个实例升级为Contribution、训练资格或一般协作优势。


### 真实消息取得与未证实的工作使用

LB/451/F2出现一条真实完成状态／催办消息：001在完成自己的测试、固定补丁和提交后发给002，消息原文确实进入002的实际输入。这是已证实的通信和取得事实；原机械测量仍保留一条free-text semantic pending，不能把它与S1三个结构unknown混为同一种未知。

消息没有传递源代码或具体的新测试诊断。其“所有贡献者都必须提交”的说法不符合冻结合同，是模型生成文字，未改变运行规则。002之后读取自己的源文件、修改并通过公开测试，但没有读取／集成001补丁，也没有后续固定提交；单靠先后顺序不足以证明具体工作使用或消息的因果效果。最终有效交付在消息之前，未建立该消息使用连至固定交付的链。


### 任务发布顺序与研究边界



| 槽 | 首次task_created序号 | 发布者 | 首次编辑序号 | 编辑者 | 是否先发布再编辑 |
| --- | --- | --- | --- | --- | --- |
| org45-r0-s0-O3 | 8 | member_001 | 3 | member_001 | False |
| org45-r2-s0-F2 | 8 | member_002 | 4 | member_001 | False |
| org45-r2-s0-S1 | 2 | member_001 | 3 | member_001 | True |
| org45-r2-s1-O3 | 3 | member_002 | 6 | member_001 | True |



LB/451/S1提供完整episode层面的先发布后编辑实例：唯一成员先在世界序号1读取rules.py，序号2成功创建fix_rules任务，序号3首次编辑，之后测试、固定、提交并得到R1。这里明确是先发布再编辑，不把发布前的读取省略成完全未开展工作。

LB/451/F2另有成员层面的先发布后编辑实例：002在世界序号8、10创建两个任务，直到序号28才首次编辑自己的工作区；不过001早在序号4已经编辑。因此它证明该成员先发布任务，不证明全团队先发布再执行。

任务表按成功提交的世界事件排序，不能把被拒绝的工具请求当成已发布任务；这里的搜索范围只限原v0.45已执行库存。发布顺序可作为组织行为轨迹事实，不能代替成果的实际取得、具体使用与固定交付证据。

假说边界：多私有工作区中的重复修复与编辑后不复验，可能与局部成本和失败路径有关；本轮轨迹能定位这些现象，不能单独识别它们的因果贡献。冻结口径没有登记链不代表完整源文件层面没有应用；补充的一次有效应用也不能直接接入训练。

执行制度Γ与训练经验分配q保持分开；本轮冻结common3/3，没有新反向或参数更新，不能声称q/b重加权、Contribution或训练收益。可访问／已呈现／实际使用仍是不同证据层次。后继C/A触发的独立只读评估另列，任何探针均未自动启动。


## 6. 全量实际成本与服务器资源

| 指标 | 原首槽1 | 第一次接续9 | 本阶段原14实际 | 原24实际合计 |
|---|---|---|---|---|
| 决定 | 7 | 191 | 439 | 637 |
| 实际模型调用 | 7 | 184 | 421 | 612 |
| 输入token | 86263 | 2356681 | 5517542 | 7960486 |
| 输出token | 1627 | 118781 | 215662 | 336070 |
| 总token | 87890 | 2475462 | 5733204 | 8296556 |
| 成员公开run_tests | 2 | 17 | 23 | 42 |
| 成员脚本 | 0 | 0 | 0 | 0 |
| 初态公开driver | 2 | 8 | 10 | 20 |
| 初态缓存复用槽 | 0 | 5 | 9 | 14 |
| 最终私有验收driver | 1 | 5 | 6 | 12 |
| 最终公开验收driver | 1 | 5 | 6 | 12 |


| 阶段 | 分配worker秒 | 小时 | 各自supervisor墙钟秒 |
|---|---|---|---|
| 原首槽1 | 129.69554543495178 | 0.03602654039859772 | 195.72968697547913 |
| 第一次接续9 | 6008.9131689071655 | 1.6691425469186572 | 4880.686222791672 |
| 本阶段原14实际 | 11601.673152208328 | 3.222686986724536 | 11195.08640408516 |
| 失败解释器宿主（无模型） | 5.067300081253052 | 0.0014075833559036256 | 68.74323058128357 |

包含失败宿主的全部worker分配时间为17745.349166632秒（4.929263657小时）；实际加载模型的各阶段worker合计17740.281866550秒。原10模型worker的6138.608714342秒只计一次，失败加载器5.067300081秒另计。

native生成嵌套时间合计16498.799608秒，仅作分解；加载、恢复、CPU准备、测试、验收和轮询已包含在worker生命期中，不再相加。不同阶段墙钟不声称连续实验总墙钟，条件级GPU时间不任意分摊。

实际分配物理GPU：[4, 5]；保存采样内资源守卫全部通过：True。只读审阅未新增nvidia查询；采样通过不代表无间隙连续监测。

已加载模型worker来源/common/profile与逐槽费用/RNG守卫：`{"all_actual_workers_source_unchanged":true,"all_actual_workers_common_3_3_exact":true,"all_actual_workers_profile_identity_exact":true,"all_actual_slot_rng_restored_exactly":true,"all_actual_slot_guard_checks_pass":true,"all_actual_slot_usage_reconciliations_pass":true,"new_actor_steps":0,"new_critic_steps":0,"new_backward_calls":0,"failed_loader_common_guard":"not_applicable_not_reached","scope":"Phase-qualified model-loaded closed audited workers only; failed pre-model loader is separately N/A, never a common guard pass."}`。失败解释器尚未到达common，单列N/A，没有充当通过样本。

## 7. 研究解释与后续边界

S1/F2/O3比较的是调度与执行制度Γ；本轮没有比较训练经验分配q的后续效用增量。可访问、实际呈现、成果使用或一条工作链都不能自动升级为因果Contribution。集中完成、不增员与重复工作如实保留，API活跃度和消息量不作组织收益替代指标。

实际出生0，有出生槽0；冻结跟踪证据列于第4节，独立文件级确认的1次伙伴应用列于第5节。具体应用实例属于存在性证据，不能凭本批有限人工载体结果恢复学习队列或声称交付提升。

原24完整之后才可按预锁HA/HB×两seed的F2基准讨论C/A机制触发，C优先；不得把LA公开未取得事后替换预锁基准。此报告只记录候选机制事实，不冻结C+新长度、不增加模型资格调用、不自动启动四条探针。本轮C/A、训练、Contribution、正式更新、独立确认与梯度缓存生产新增调用/更新均0。

原26试训、3正式更新、48TextFSM独立确认及缓存生产继续暂停。没有为取得第一条链重跑原库存，没有自动后继；提出新研究问题须与本轮冻结范围、阶段差异和有限样本证据分开。


### 预锁C/A条件的只读触发审阅

预锁的 HA/HB × 两个 seed 共四条 F2 基准已全部核对，其中 2 条存在交付前、仍足以预约下一请求的真实硬 context 截断。符合该机制证据条件的槽为 org45-r1-s0-F2、org45-r3-s1-F2。因此按预锁优先级，容量模块 C 可列为后续条件化诊断提案。四条基准均无已记录的固定补丁/消息公开事件，跟踪关系也未证实合法公开；没有支持 A 模块的具体取得摩擦证据。本审阅不选择 C+ 长度，不启动资格调用或额外四槽；解除容量阻塞能否带来取得、使用或交付收益，尚未检验。

以下是封存原24结果后的机制条件核对，不是新增处理结果或模型资格。C与A存在优先顺序，最多仅形成一项后续提议；未调整context或采样任何处理槽。

| 预锁F2槽 | 已保存硬context事件数 | 原件引用 |
|---|---|---|
| org45-r1-s0-F2 | 1 | 触发审阅机器文件内该槽 sources |
| org45-r1-s1-F2 | 0 | 触发审阅机器文件内该槽 sources |
| org45-r3-s0-F2 | 0 | 触发审阅机器文件内该槽 sources |
| org45-r3-s1-F2 | 1 | 触发审阅机器文件内该槽 sources |


| 条件 | 触发资格 | 候选槽 |
|---|---|---|
| C：容量 | 是 | ["org45-r1-s0-F2","org45-r3-s1-F2"] |
| A：取得便利性 | 否 | [] |

终态只读分支判断：C。execution_permitted=false，C+具体context长度仍为null；本轮探针实际调用为0。候选机制证据不能保证处理有效，后续任何协议仍需另行冻结。

## 8. 来源与可复核性

本报告只组装封存的CPU/只读凭据、终态自动报告和增量审阅缓存；没有再扫描旧191条或重读新槽原始输入输出，没有新增分词、模型、业务测试或验收。机器明细保留逐槽指标与来源引用，不复制全量raw响应。原v045-final报告、旧unknown/停止、失败候选与失败加载记录均保持。

增量只读轨迹汇总曾把无固定交付的delivery=null按对象读取而失败；旧失败helper/回执保留，仅修宿主空值处理并定向补读该已闭合槽，未修改冻结测量、R或模型执行。该分析修复不计作实验样本。

C/A触发只读汇总的字段连接修复也保留在机器审阅analysis_corrections中；它不改变预锁基准、触发标准或任何模型结果，不属于新增资格调用。

| 证据 | SHA-256 |
|---|---|
| automatic_current_report | `9b463e86099cdc388e5133bab58b06c0ac4916cc69592007233e3c17379739cd` |
| cost_review | `3a604e9ed25a94766fdc50a4ce14832c1f267d4a1cd79a8f45a554c92d4f9f3d` |
| new14_cost_review | `9ea4399540d119fbab81746bf3e92eb0911392170ac05227d192f9be890343d4` |
| feedback_work_review | `013135d98cb0631b6aff703bd9a70c6a089f2a460f7dfef38409c5ba7830a791` |
| context_review | `4bdbb3568f679407c3299b8719925839fc648d5a5a7e7b5e5367c615179c02fd` |
| trajectory_facts | `535d56866b81dbb9b546bdb68e4a4ab04c044b75cf950a5b1bfd2743feb28a4c` |
| probe_trigger_review | `bcd9ef0a2856053afd4b76d96a3dd5c6404d8a43eeea66336cf62b2118be0305` |
| measurement_coverage_review | `8a61f91c94abfc67b4f54e6b530dd8fd1188df0fb38039c1460381d9c6c9e8a7` |
| semantic_review | `2c454c2efcad5b43e6bc62fc9b5f6d2b877ce8caa88f0d8015d193d33bba6098` |
| integration_review | `62a38ec541097846faedd843b7cf57571f75e466933eedd8b4e50851acd2120f` |
| retained_work | `c46e6eb7af22eea5e5a7e9257dc19c3d00ff55c92e045f029ab8d4d9ac47f3b4` |
| failed_loader_cost | `0d4c930a495fd2cbaa174cc563185b9eac1c18b28d215e138a9a52c58f7fa7aa` |
| prior10_final_report | `178aa6d7a08755551edd4d0a5524b37c938fadfa0752599a9a394337cf04c33e` |
| prior10_cost | `c7e4cb944115d8a63f6a324bbd2edac75f52f3f3079e7b2abf912697626e4ef5` |
| prior_context | `869ee07304c7193c87db750dd240bc93b3c1f00163b70b6ddff53180f23050b4` |
| original_plan | `37b56573b60172f7f88826c61265c3f5c62b7bc7f90ceb8b6d14874192d4dfea` |
| first_resume_plan | `0744de191a558f8de7a44c8bf40186a6f38ad8c9ad4727b0187b51406e571f62` |
| current_plan | `9a7a903057389fdad1adc583d6146dc63002c98f62cf984bae8e401d504ebf3a` |
| current_finish | `29d5f6b3001571097df573da97f6195448b6fb290b528a4b227dc7b9eda7ed14` |
| original_cpu_admission | `fa1ddf1c8a73ac336b57e624f61376df9012cc50f309967258cf754bc0f03155` |
| interface_repair | `80260c92a2b684b7edaedc836da397a355df6ea8baa08b093db9747c5beab702` |
| original_cpu_preparation | `b4bd3f53df40975b06b21b717d6785def2c369ae71f0bc173043e2401cb2b0f6` |
| first_resume_preparation | `8f6262b1944cac81814d1770763c0506e6ce24eb1a7f6c926b8c97d4d4198606` |
| audit | `2e76f31e4b605c8581810c62a9f4b9b8a4ed45e36a71c3b145c20819d25283f6` |
| current_preparation | `7c535ee95e4d2f38b99c182ca34511849f1b17fb224b0d9ff391d1f8fde8e9c8` |
| current_admission | `d60d9ebe7a06b0844c43cca338e9e555951455a6240cb31cda8855d33278b77b` |
| current_qualification | `efc009196464e7383833b82ae5490dcc52b9dab4a20922e338586eba0c33fa63` |
| measurement_controls | `3b8df5f1c1e9a69c4d15243250ee61e61a1f1d327c78e42735b0da29fc89bc77` |
| retained_revision | `de191468724f0b3b1609a6b90c3afd83e3034d2327354e03e7ffde5d2ccacbf7` |
| failed_python314_work | `863da5fc3b7966172a7ef321a3e0c0abf304ffa07d4340a61689c41de4e31def` |
| python_ast_diagnostic | `8d731c1791abdb8089fd73e29f8b1aed3eaebc90b5628ff690c8a4d96de76889` |
| first_materialization_log | `5ed78f2b93d3bdfbfddef20f552d2ad16b959ff7b8ef932898f15f358cb61ad2` |
| accepted_native312_materialization_log | `195ee2f6373a9ae6b5e7c0c84bbecf30a0b52f7b37f09fcd22199b4a0acb40a1` |
| initial_host_tests | `de32e54b6594c82d14980e45cff4b25f92262ffee0c60d21bc798afcf5bd0f95` |
| missing_cli_mode_log | `ed49b2aed79806b5241c78b8f639e4e0750a25484ce6280680258e922e718943` |
| corrected_cli_log | `eb23664be5642797b0f1e5b4c76b495bd9e6fdfb45887b71856727e270771a4a` |
| old10_business_publication | `d0221760438327ab91bf4c0edf03ea0f4652f406a6981842d14a030969e7b9f6` |
| prelaunch_static_review | `ad3ec0ef6a790bfbd55b15bc255a83ad1e6c34f9765ed0f0614442c244766d91` |
| prelaunch_static_addendum | `03e6c08ce1d9187522b1bbd9e56a0a8ae146db5d2f567e35f8af3419c106c621` |
| initial_source_root_plan_receipt | `1040ab85c2905e1ca72ec8c846af51478d238dbfbc85daf8a38ba631ceb1e29b` |
| failed_project_python_launch | `2cde97e0689453c6694df508fcec5c2bfb1672b95b4efebb9086e1b78cefbb0b` |
| corrected_sdk_launch | `cfdadf54e38aaa250c7b0a9742b17dd5b4a9d80b11b664640b210a566a0ae507` |
| failed_launcher_finish | `62c468dda6b881140ad4b47cb708b4c1a6781f02accd0a282615fd99ffcc6d43` |
| failed_launcher_supervisor | `f9ede8cdd4b784f08f63e90fa519e4bb0eb7356cd7e9759044e3cad1a1f0a6cd` |
| helper | `fd843b353b16bca1bc254e9766edf03658e23ee0ffb21e188d148941578d3a79` |
| trajectory_null_repair | `2f136fcc5dd960327393d5922d0d89af968c84bd3e6771527b04b4453d9a5953` |
| resource_attribution | `0f4a22bc30d0dc2947187576dc7071c85227f1d1f4aae403a9ef967202a3e9c4` |
| file_application_org45-r2-s1-O3 | `21927c27e9de0a2054ec40ca4027a4655388aac1d30a955396c43a3f222a16a1` |
| reviewed_interpretation | `6153c8c05315d1850a48ec72a7a77ceb2b96c0c71705699eab57c1b358b54354` |

[机器明细](software-organization-v045-completion-final.json) · [原10槽封存报告](software-organization-v045-final.md) · [原14协议](software-organization-v045-complete-protocol.md) · [准备](software-organization-v045-complete-preparation.md) · [启动及失败保留](software-organization-v045-complete-launch.md)
