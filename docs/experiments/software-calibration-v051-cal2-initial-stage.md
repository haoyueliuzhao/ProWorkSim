# v051 CAL2：固定六题、三条件只读结案

宿主终态`paused`；槽状态`{'technical_unknown': 4, 'not_started': 14}`。固定18槽全部来源闭合：`False`。报告只读取原件，不新增模型、评分、分词或更新。

R为原始mini-SWE单agent，P为原始模型的ProWorkSim S1，U为S_star actor4/4的同一S1。三条件均用同一project数值路径、独立fresh resident和原任务初态；R_code比较各自最终工作树。P/U的R_joint只衡量固定交付，R对此不适用，不能填0。

## 末树代码正确性：来源绑定

| 条件/差 | 已知/固定题数 | 六题等权均值 | 未决界限 |
|---|---|---:|---|
| R | 0/6 | null | [0.0, 1.0] |
| P | 0/6 | null | [0.0, 1.0] |
| U | 0/6 | null | [0.0, 1.0] |
| P_minus_R | paired/6 | null | [-1.0, 1.0] |
| U_minus_P | paired/6 | null | [-1.0, 1.0] |

## 末树代码正确性：原记录

| 条件/差 | 已知/固定题数 | 六题等权均值 | 未决界限 |
|---|---|---:|---|
| R | 0/6 | null | [0.0, 1.0] |
| P | 0/6 | null | [0.0, 1.0] |
| U | 0/6 | null | [0.0, 1.0] |
| P_minus_R | paired/6 | null | [-1.0, 1.0] |
| U_minus_P | paired/6 | null | [-1.0, 1.0] |

## 完整原测试观察分数：来源绑定

| 条件/差 | 已知/固定题数 | 六题等权均值 | 未决界限 |
|---|---|---:|---|
| R | 0/6 | null | [0.0, 1.0] |
| P | 0/6 | null | [0.0, 1.0] |
| U | 0/6 | null | [0.0, 1.0] |
| P_minus_R | paired/6 | null | [-1.0, 1.0] |
| U_minus_P | paired/6 | null | [-1.0, 1.0] |

## 固定交付：仅P/U

| 条件/差 | 已知/固定题数 | 六题等权均值 | 未决界限 |
|---|---|---:|---|
| P | 0/6 | null | [0.0, 1.0] |
| U | 0/6 | null | [0.0, 1.0] |
| R | N/A | N/A | N/A |
| U_minus_P | paired/6 | null | [-1.0, 1.0] |

每题等权，不按原测试数量、成功、提交或提前终止筛选。任一相关未知使完整均值或配对差保持null；界限只是未知结果在[0,1]内的范围。原结果与来源绑定口径并列，原非空值不因缺证被删除。

## 完整18槽与原测试观察

| 槽 | 原R_code | 绑定R_code | 原Q_terminal | 绑定Q_terminal | R_joint | 行政删失 | 测试已观察/总数 | 未运行 | 状态 |
|---|---:|---:|---:|---:|---:|---|---|---:|---|
| v051-cal2-boltons-1-R | null | null | null | null | N/A | null | 0/0 | 0 | technical_unknown |
| v051-cal2-boltons-1-P | null | null | null | null | null | False | 0/412 | 412 | technical_unknown |
| v051-cal2-boltons-1-U | null | null | null | null | null | False | 0/412 | 412 | technical_unknown |
| v051-cal2-boltons-2-P | null | null | null | null | null | False | 0/412 | 412 | technical_unknown |
| v051-cal2-boltons-2-U | null | null | null | null | null | null | None/None | None | not_started |
| v051-cal2-boltons-2-R | null | null | null | null | N/A | null | None/None | None | not_started |
| v051-cal2-parse-1-U | null | null | null | null | null | null | None/None | None | not_started |
| v051-cal2-parse-1-R | null | null | null | null | N/A | null | None/None | None | not_started |
| v051-cal2-parse-1-P | null | null | null | null | null | null | None/None | None | not_started |
| v051-cal2-parse-2-R | null | null | null | null | N/A | null | None/None | None | not_started |
| v051-cal2-parse-2-P | null | null | null | null | null | null | None/None | None | not_started |
| v051-cal2-parse-2-U | null | null | null | null | null | null | None/None | None | not_started |
| v051-cal2-xmltodict-1-P | null | null | null | null | null | null | None/None | None | not_started |
| v051-cal2-xmltodict-1-U | null | null | null | null | null | null | None/None | None | not_started |
| v051-cal2-xmltodict-1-R | null | null | null | null | N/A | null | None/None | None | not_started |
| v051-cal2-xmltodict-2-U | null | null | null | null | null | null | None/None | None | not_started |
| v051-cal2-xmltodict-2-R | null | null | null | null | N/A | null | None/None | None | not_started |
| v051-cal2-xmltodict-2-P | null | null | null | null | null | null | None/None | None | not_started |

Q_terminal的分母固定为完整原测试集合。源码归因成立的collection失败可使R_code=0；未运行节点列为not-run，不能说这些节点执行后失败。此时已观察通过数/完整分母是保守观察分数，逐槽还列出缺节点及全节点结果界限。runner、权限或来源故障保留未知。

## 费用、停止与资源

CAL2实际已知 **227876 token**，不确定预约 **0 token**，预约金额本身未知的请求0个；完整实际费用`None`。实际开始22次、完整回包22次；已准备但未派发0次。预约不是已知收费。

worker唯一4个区间，共413.148039秒（0.114763小时）。装载、生成、测试与闭合已包含在内，不加嵌套时长。CAL1费用只在可选附列中给出，未加入CAL2费用。

逐槽JSON保留context与预算执行前拒绝原件、宿主测量判定、原停止和中断回执。安全预算/context终止不自动变成技术未知；真实fault、费用/副作用或worker绑定未决不能填0。行政soft截止保留joint-policy观察；P/U的R_token在实际删失时保持null，不冒称纯token估计。

## 解释范围

只有三个公开仓库的六个人工合成缺陷任务；不是外部真实自然issue总体。R允许最多128次原生bash行动，P/U至多32次项目公开测试，界面、可用动作和交付流程不同，P−R并非单一组件的因果分离。末树代码正确性与固定交付不能互换。U−P仅描述本固定面板上的保留actor差异；没有新训练，不从有限任务推广一般协作、通用能力或训练收益。没有读取HOLD任务，也不自动启动下一阶段。

来源/测量未决：`[{"slot_id": "v051-cal2-boltons-1-R", "problems": ["worker_closure_or_mechanical_measurement_unresolved", "actor_numeric_path_or_final_guard_unresolved", "episode_guard_record_missing_or_different", "terminal_code_record_missing_or_different", "shared_test_runner_evidence_missing", "native_episode_task_or_seed_mismatch", "native_raw_and_authoritative_tree_binding_unresolved", "terminal_code_unknown"]}, {"slot_id": "v051-cal2-boltons-1-P", "problems": ["worker_closure_or_mechanical_measurement_unresolved", "shared_test_runner_source_unresolved", "terminal_code_unknown"]}, {"slot_id": "v051-cal2-boltons-1-U", "problems": ["worker_closure_or_mechanical_measurement_unresolved", "shared_test_runner_source_unresolved", "terminal_code_unknown"]}, {"slot_id": "v051-cal2-boltons-2-P", "problems": ["worker_closure_or_mechanical_measurement_unresolved", "shared_test_runner_source_unresolved", "terminal_code_unknown"]}]`。
