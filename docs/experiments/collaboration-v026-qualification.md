# v0.26 协作载体 CPU 资格验证

这是公开端口上的显式程序可达性检验。没有模型推理、GPU 计算、参数更新、教师轨迹或有效方法支持；它只回答指定工具、调度和预算下是否存在完整路线。

资格结果：**通过**。GPU 启动资格：`True`。

每成员最多 24 次决定，实际官方 tokenizer 上下文 16,384，固定预留输出 2,048；程序工具正文也须不超过 2,048。没有为见证放宽预算。

程序仅从各成员实际 observation 与自己的工具返回选择动作。maintainer 的复核算术只用它已合法读取的 raw/demand/source_contract；generic witness SQL 不读取 case ID 或隐藏事实。正常条件保留需求先行、先合法查询两种可行执行顺序（不据此预认定两种可重配方法）；query_first消费者用实际样例返回中的取消/负量行形成随后需求解释；单转发条件全 episode 只有 consumer 发出一次精确 demand v1，仅附固定非业务头部 Original demand document.，其他业务工具保持同样权限与额度。

| case | 条件 | 程序路线 / 对照 | 决定次数 M/C | 峰值输入 token | 完整职责 | 资格 |
|---|---|---|---|---|---|---|
| reciprocal-v26-00 | normal | constraint_first | {'maintainer': 20, 'consumer': 16} | 14230 | True | True |
| reciprocal-v26-00 | normal | query_first | {'maintainer': 21, 'consumer': 17} | 14282 | True | True |
| reciprocal-v26-00 | single_pass | constraint_first | {'maintainer': 20, 'consumer': 16} | 14242 | True | True |
| reciprocal-v26-01 | normal | constraint_first | {'maintainer': 20, 'consumer': 16} | 14281 | True | True |
| reciprocal-v26-01 | normal | query_first | {'maintainer': 21, 'consumer': 17} | 14332 | True | True |
| reciprocal-v26-01 | single_pass | constraint_first | {'maintainer': 20, 'consumer': 16} | 14291 | True | True |
| reciprocal-v26-02 | normal | constraint_first | {'maintainer': 20, 'consumer': 16} | 14215 | True | True |
| reciprocal-v26-02 | normal | query_first | {'maintainer': 21, 'consumer': 17} | 14251 | True | True |
| reciprocal-v26-02 | single_pass | constraint_first | {'maintainer': 20, 'consumer': 16} | 14219 | True | True |
| reciprocal-v26-03 | normal | constraint_first | {'maintainer': 20, 'consumer': 16} | 14224 | True | True |
| reciprocal-v26-03 | normal | query_first | {'maintainer': 21, 'consumer': 17} | 14260 | True | True |
| reciprocal-v26-03 | single_pass | constraint_first | {'maintainer': 20, 'consumer': 16} | 14228 | True | True |
| reciprocal-v26-01 | normal | ignore_demand_distinction | {'maintainer': 19, 'consumer': 16} | 13546 | False | False |
| reciprocal-v26-02 | single_pass | ignore_unit_distinction | {'maintainer': 19, 'consumer': 16} | 13505 | False | False |

## 反事实与公平性

首个真实模型格式请求直接比较保存的完整 JSON 字节摘要；配对共用 seed namespace，不删去业务字段，也不把随机世界 ID 的删除当作检验。demand_pair 必须出现来源与最终指标变化；unit_pair 必须出现来源金额/单位变化，正确消费者换算后的最终指标可以相同。

- [0, 1] / normal / constraint_first：首请求相同=True；来源产物变化=True；最终指标变化=True；通过=True。
- [2, 3] / normal / constraint_first：首请求相同=True；来源产物变化=True；最终指标变化=False；通过=True。
- [0, 1] / normal / query_first：首请求相同=True；来源产物变化=True；最终指标变化=True；通过=True。
- [2, 3] / normal / query_first：首请求相同=True；来源产物变化=True；最终指标变化=False；通过=True。
- [0, 1] / single_pass / constraint_first：首请求相同=True；来源产物变化=True；最终指标变化=True；通过=True。
- [2, 3] / single_pass / constraint_first：首请求相同=True；来源产物变化=True；最终指标变化=False；通过=True。
- case 0：业务工具定义相同=True；单次合法转发=True；两条件均完整可达=True。
- case 1：业务工具定义相同=True；单次合法转发=True；两条件均完整可达=True。
- case 2：业务工具定义相同=True；单次合法转发=True；两条件均完整可达=True。
- case 3：业务工具定义相同=True；单次合法转发=True；两条件均完整可达=True。

错误逻辑对照只忽略已读取的需求/单位区别，不伪称模型从未见到它；原工具、源数据与执行路径保留。期待独立 checker 拒绝完整职责，不能将该 CPU 对照当成通信有效性或学习收益。未读、伪造产物等底层负例由 `tests/test_reciprocal_data_v026.py` 独立核验。

## 失败和限制

预定 12 条正向 CPU 路线均在原预算内闭合。这仍不证明当前模型能找到这些路线，也不证明单转发一定劣于自由合作。后续 C1 必须报告两条件真实行为和工作结果。

见证程序采用公开合法的节省步骤：固定提交查看显式 include_contract=False（完整合同仍在当前公开观察，必要时可显式取回）；consumer在等待上游时先采用自己已读的demand；maintainer不额外转交未用于消费者构建的source_contract，consumer也不额外读取它。消费侧真正使用的是固定m_result里的interface_meta。以上只改变CPU程序动作选择，没有修改模型策略、工具合同或预算。

中止开发批次：`/data1/zhuxinrui/projects/ProWorkSim/runs/v026-controls/qualification/native-complete-05/report.json`，已完成 4 条；中止原因：Source/checker changed during batch；不能作为最终资格。

中止开发批次：`/data1/zhuxinrui/projects/ProWorkSim/runs/v026-controls/qualification/native-complete-06/report.json`，已完成 6 条；中止原因：Business completed but terminal staff_done exceeded context; optional unused packet removed in next CPU witness；不能作为最终资格。

前置开发记录保留：`/data1/zhuxinrui/projects/ProWorkSim/runs/v026-controls/qualification/native-contract-omitted-check-02/control.json`，严格门=False，输入峰=14463。

前置开发记录保留：`/data1/zhuxinrui/projects/ProWorkSim/runs/v026-controls/qualification/native-first-check-01/control.json`，严格门=False，输入峰=14463。

前置开发记录保留：`/data1/zhuxinrui/projects/ProWorkSim/runs/v026-controls/qualification/native-useful-packet-check-07/control.json`，严格门=True，输入峰=14230。

前置开发记录保留：`/data1/zhuxinrui/projects/ProWorkSim/runs/v026-controls/qualification/native-v26-approval-receipt-check-04/control.json`，严格门=False，输入峰=14798。

前置开发记录保留：`/data1/zhuxinrui/projects/ProWorkSim/runs/v026-controls/qualification/native-v26-shared-contract-check-03/control.json`，严格门=False，输入峰=15579。

原始资格目录：`/data1/zhuxinrui/projects/ProWorkSim/runs/v026-controls/qualification/native-complete-07`。各子目录保留请求、公开端口记录、完整不可变 episode、逐调用 token 测量与评分。

[机器可核对结果](collaboration-v026-qualification.json)

## 实测余量与适用范围补注

本批 14 条 CPU 程序共形成 **510 次程序请求**（12 条正向 440 次，2 条错误逻辑对照 70 次）。最大实际输入 **14,332 token**，出现在 `reciprocal-v26-01 / normal / query_first / maintainer` 的第 21 次 `staff_done` 请求；在固定预留输出 2,048 和总上下文 16,384 下，**最小剩余量只有 4 token**。最大程序输出为 **402 token**。这些均从本批逐请求 tokenizer 记录直接计算。

CPU 配对 seed 只有 `202610040000` 与 `202610040100`，每对情境共用一个 seed namespace。通过结论仅覆盖这些具体程序、工具参数、实际输入字节与 seed，不表示真实模型的任意措辞、额外操作或两次正式重复都会走同一路径并在预算内结束。原上下文门与输出门保持不变，真实模型发生超限须如实保留。

两种程序标签只证明有限可行执行顺序，不能预认定两类可重配协作方法。单转发条件已经有完整程序路线，因此当前证据也不证明额外解释或更多轮次是业务完成所必需的；实际作用仍须由 C1 冻结参数对照检验。

本补注只读计算，没有修改原始资格运行报告、episode、评分或条件。原运行报告路径及 SHA256 已写入 JSON 的 `qualification_run_report_reference`。
