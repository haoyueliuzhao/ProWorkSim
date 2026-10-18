# v051 CAL2：原18槽与r2历史层只读合并

本报告复用原首阶段JSON，只读取已闭合r2宿主及其新记录。原4条技术未知历史完整保留，其中原3条有真实P/U模型轨迹的末树评分仍未知。原R零生成失败和r2首次真实模型曝光是两个历史层，映射同一个逻辑题/条件，不能删除旧失败或创造第19个独立样本。

另叠加独立环境有效性审计：boltons-1/R、boltons-2/R、boltons-2/U的socket fixture破坏原asyncio/ssl导入，命中原P2P测试。保留原执行器raw结果，但严格R_code/Q_terminal为技术未知，不能把已证实的环境故障解释成业务失败。boltons-2/U的未提交事实及原R_joint=0保留，不推测修好环境后是否会提交。该暂停来自完整性门，不是通过率阈值。

| 阶段 | 状态 | 完整回包 | 已知token | 不确定预约 | 原报告完整费用 | 独立原生费用 | worker秒 |
|---|---|---:|---:|---:|---:|---:|---:|
| initial_stage | paused | 22 | 227876 | 0 | null | 227876 | 413.148039 |
| r2 | paused | 253 | 2676767 | 0 | 2676767 | 2676767 | 3429.439327 |

原227,876token及413.1480391025543秒只计一次；原complete_actual_tokens=null保留。独立账目通过已准入零生成R证明及完整native usage判断费用；评分环境未知不等于费用未知。环境审计只改变代码结果的严格有效性，不把已绑定实际回包费用改成0。原阶段14未开数不与r2未开数相加；当前未开始状态按18个逻辑槽列示，未开始/在途不称失败。报告拒绝仍有在途worker的宿主。

## 原R的两个历史层

| 层 | 含义 | 结果处理 |
|---|---|---|
| 原首阶段 | 已装载、初树读取拒绝，native prepared/started/complete/fault均0 | 原technical_unknown、禁重排标记和worker成本不改 |
| r2 | 独立新准入的一次首次模型曝光；不复用旧模型状态 | 新原结果单独保存，环境审计后的严格末树端点未知 |

原首阶段还包含CRLF保真与文件映射排序缺陷、测试child间接依赖导入故障；r2的已披露窄修不倒改旧3条真实轨迹的失败反馈。socket fixture缺陷是新的独立环境有效性问题。各版本及暂停分别保留。

## 固定面板和完整明细

### 合并逻辑面板

宿主终态`paused`；槽状态`{'technical_unknown': 6, 'closed': 5, 'not_started': 7}`。固定18槽全部来源闭合：`False`。报告只读取原件，不新增模型、评分、分词或更新。

R为原始mini-SWE单agent，P为原始模型的ProWorkSim S1，U为S_star actor4/4的同一S1。三条件均用同一project数值路径、独立fresh resident和原任务初态；R_code比较各自最终工作树。P/U的R_joint只衡量固定交付，R对此不适用，不能填0。

## 末树代码正确性：来源绑定

| 条件/差 | 已知/固定题数 | 六题等权均值 | 未决界限 |
|---|---|---:|---|
| R | 2/6 | null | [0.0, 0.6666666666666666] |
| P | 2/6 | null | [0.0, 0.6666666666666666] |
| U | 1/6 | null | [0.0, 0.8333333333333334] |
| P_minus_R | paired/6 | null | [-0.6666666666666666, 0.6666666666666666] |
| U_minus_P | paired/6 | null | [-0.6666666666666666, 0.8333333333333334] |

## 末树代码正确性：原记录

| 条件/差 | 已知/固定题数 | 六题等权均值 | 未决界限 |
|---|---|---:|---|
| R | 4/6 | null | [0.0, 0.3333333333333333] |
| P | 2/6 | null | [0.0, 0.6666666666666666] |
| U | 2/6 | null | [0.0, 0.6666666666666666] |
| P_minus_R | paired/6 | null | [-0.3333333333333333, 0.6666666666666666] |
| U_minus_P | paired/6 | null | [-0.6666666666666666, 0.6666666666666666] |

## 完整原测试观察分数：来源绑定

| 条件/差 | 已知/固定题数 | 六题等权均值 | 未决界限 |
|---|---|---:|---|
| R | 2/6 | null | [0.20578231292517005, 0.8724489795918368] |
| P | 2/6 | null | [0.20918367346938774, 0.8758503401360543] |
| U | 1/6 | null | [0.11054421768707483, 0.9438775510204082] |
| P_minus_R | paired/6 | null | [-0.663265306122449, 0.6700680272108843] |
| U_minus_P | paired/6 | null | [-0.7653061224489796, 0.7346938775510204] |

## 固定交付：仅P/U

| 条件/差 | 已知/固定题数 | 六题等权均值 | 未决界限 |
|---|---|---:|---|
| P | 2/6 | null | [0.0, 0.6666666666666666] |
| U | 2/6 | null | [0.0, 0.6666666666666666] |
| R | N/A | N/A | N/A |
| U_minus_P | paired/6 | null | [-0.6666666666666666, 0.6666666666666666] |

每题等权，不按原测试数量、成功、提交或提前终止筛选。任一相关未知使完整均值或配对差保持null；界限只是未知结果在[0,1]内的范围。原结果与来源绑定口径并列，原非空值不因缺证被删除。

## 完整18槽与原测试观察

| 槽 | 原R_code | 绑定R_code | 原Q_terminal | 绑定Q_terminal | R_joint | 行政删失 | 测试已观察/总数 | 未运行 | 状态 |
|---|---:|---:|---:|---:|---:|---|---|---:|---|
| v051-cal2-boltons-1-R | 0 | null | 0.992718 | null | N/A | False | 412/412 | 0 | technical_unknown |
| v051-cal2-boltons-1-P | null | null | null | null | null | False | 0/412 | 412 | technical_unknown |
| v051-cal2-boltons-1-U | null | null | null | null | null | False | 0/412 | 412 | technical_unknown |
| v051-cal2-boltons-2-P | null | null | null | null | null | False | 0/412 | 412 | technical_unknown |
| v051-cal2-boltons-2-U | 0 | null | 0.992718 | null | 0 | False | 412/412 | 0 | technical_unknown |
| v051-cal2-boltons-2-R | 0 | null | 0.992718 | null | N/A | False | 412/412 | 0 | technical_unknown |
| v051-cal2-parse-1-U | 0 | 0 | 0.663265 | 0.663265 | 0 | False | 98/98 | 0 | closed |
| v051-cal2-parse-1-R | 0 | 0 | 0.642857 | 0.642857 | N/A | False | 98/98 | 0 | closed |
| v051-cal2-parse-1-P | 0 | 0 | 0.663265 | 0.663265 | 0 | False | 98/98 | 0 | closed |
| v051-cal2-parse-2-R | 0 | 0 | 0.591837 | 0.591837 | N/A | False | 98/98 | 0 | closed |
| v051-cal2-parse-2-P | 0 | 0 | 0.591837 | 0.591837 | 0 | False | 98/98 | 0 | closed |
| v051-cal2-parse-2-U | null | null | null | null | null | null | None/None | None | not_started |
| v051-cal2-xmltodict-1-P | null | null | null | null | null | null | None/None | None | not_started |
| v051-cal2-xmltodict-1-U | null | null | null | null | null | null | None/None | None | not_started |
| v051-cal2-xmltodict-1-R | null | null | null | null | N/A | null | None/None | None | not_started |
| v051-cal2-xmltodict-2-U | null | null | null | null | null | null | None/None | None | not_started |
| v051-cal2-xmltodict-2-R | null | null | null | null | N/A | null | None/None | None | not_started |
| v051-cal2-xmltodict-2-P | null | null | null | null | null | null | None/None | None | not_started |

Q_terminal的分母固定为完整原测试集合。源码归因成立的collection失败可使R_code=0；未运行节点列为not-run，不能说这些节点执行后失败。此时已观察通过数/完整分母是保守观察分数，逐槽还列出缺节点及全节点结果界限。runner、权限或来源故障保留未知。

## 费用、停止与资源

CAL2实际已知 **2904643 token**，不确定预约 **0 token**，预约金额本身未知的请求0个；完整实际费用`2904643`。实际开始275次、完整回包275次；已准备但未派发0次。预约不是已知收费。

worker唯一12个区间，共3842.587366秒（1.067385小时）。装载、生成、测试与闭合已包含在内，不加嵌套时长。CAL1费用只在可选附列中给出，未加入CAL2费用。

逐槽JSON保留context与预算执行前拒绝原件、宿主测量判定、原停止和中断回执。安全预算/context终止不自动变成技术未知；真实fault、费用/副作用或worker绑定未决不能填0。行政soft截止保留joint-policy观察；P/U的R_token在实际删失时保持null，不冒称纯token估计。

## 解释范围

只有三个公开仓库的六个人工合成缺陷任务；不是外部真实自然issue总体。R允许最多128次原生bash行动，P/U至多32次项目公开测试，界面、可用动作和交付流程不同，P−R并非单一组件的因果分离。末树代码正确性与固定交付不能互换。U−P仅描述本固定面板上的保留actor差异；没有新训练，不从有限任务推广一般协作、通用能力或训练收益。没有读取HOLD任务，也不自动启动下一阶段。

来源/测量未决：`[{"slot_id": "v051-cal2-boltons-1-R", "problems": ["worker_closure_or_mechanical_measurement_unresolved", "actor_numeric_path_or_final_guard_unresolved", "episode_guard_record_missing_or_different", "terminal_code_record_missing_or_different", "shared_test_runner_evidence_missing", "native_episode_task_or_seed_mismatch", "native_raw_and_authoritative_tree_binding_unresolved", "terminal_code_unknown"]}, {"slot_id": "v051-cal2-boltons-1-P", "problems": ["worker_closure_or_mechanical_measurement_unresolved", "shared_test_runner_source_unresolved", "terminal_code_unknown"]}, {"slot_id": "v051-cal2-boltons-1-U", "problems": ["worker_closure_or_mechanical_measurement_unresolved", "shared_test_runner_source_unresolved", "terminal_code_unknown"]}, {"slot_id": "v051-cal2-boltons-2-P", "problems": ["worker_closure_or_mechanical_measurement_unresolved", "shared_test_runner_source_unresolved", "terminal_code_unknown"]}, {"kind": "independent_environment_invalidity", "source": {"path": "/data1/zhuxinrui/projects/ProWorkSim/artifacts/software-calibration-v051/cal2-r2-first-execution-audit/report.json", "bytes": 63920, "sha256": "81820c7b2e3fd9df70e282d5cd1f842eab42e5564f29fd573aff800d0b8d50c6"}, "effects": [{"slot_id": "v051-cal2-boltons-1-R", "report_source": {"path": "/data1/zhuxinrui/projects/ProWorkSim/runs/software-calibration-v051-cal2-r2/workers/v051-cal2-boltons-1-R/attempt-001/report.json", "sha256": "e633b7eea39a05f7f23c5eb0afefb0b5210e70be8a74b42e6ace9f2346a41f87", "bytes": 296559}, "terminal_runner_source": {"path": "/data1/zhuxinrui/projects/ProWorkSim/runs/software-calibration-v051-cal2-r2/workers/v051-cal2-boltons-1-R/attempt-001/terminal-code/execution/result.json", "sha256": "ffcf0298dfa17d4e08f5dc21079d36f58ec1db34d5ac4b1e0a5b22de18002f14", "bytes": 154644}, "strict_code_status": "technical_unknown", "strict_R_code": null, "strict_Q_task_terminal": null, "preserve_original_R_joint": true, "original_submitted": null, "original_R_joint": null, "reason": "Frozen runner globally replaces socket.socket with a function, breaking unchanged original async P2P test at ssl.SSLSocket class definition. Complete node execution does not establish valid authoritative environment.", "counterfactual_score_reconstructed": false}, {"slot_id": "v051-cal2-boltons-2-R", "report_source": {"path": "/data1/zhuxinrui/projects/ProWorkSim/runs/software-calibration-v051-cal2-r2/workers/v051-cal2-boltons-2-R/attempt-001/report.json", "sha256": "26408887d8d418b11e1f5dd6b9b7df6e26b868d066a0e80574b7352fcbc538e7", "bytes": 309446}, "terminal_runner_source": {"path": "/data1/zhuxinrui/projects/ProWorkSim/runs/software-calibration-v051-cal2-r2/workers/v051-cal2-boltons-2-R/attempt-001/terminal-code/execution/result.json", "sha256": "cc6becf61b0b99dfbd810d05590002e22c328bfb859fbcd21394ee03f2a63f22", "bytes": 156003}, "strict_code_status": "technical_unknown", "strict_R_code": null, "strict_Q_task_terminal": null, "preserve_original_R_joint": true, "original_submitted": null, "original_R_joint": null, "reason": "Frozen runner globally replaces socket.socket with a function, breaking unchanged original async P2P test at ssl.SSLSocket class definition. Complete node execution does not establish valid authoritative environment.", "counterfactual_score_reconstructed": false}, {"slot_id": "v051-cal2-boltons-2-U", "report_source": {"path": "/data1/zhuxinrui/projects/ProWorkSim/runs/software-calibration-v051-cal2-r2/workers/v051-cal2-boltons-2-U/attempt-001/report.json", "sha256": "7597dd03c3aa6f10a3d4fc34f493f7f8e7e55926fd768be6738dba8d0b37f7c7", "bytes": 1161563}, "terminal_runner_source": {"path": "/data1/zhuxinrui/projects/ProWorkSim/runs/software-calibration-v051-cal2-r2/workers/v051-cal2-boltons-2-U/attempt-001/episode/terminal-code/tests/execution-9667ba4a465941bdbece3fbedcb5d574/result.json", "sha256": "e55c0a51c19103d64a81258ad611817143fd4f979ba0b852b34a4fa3983ed3b5", "bytes": 159417}, "strict_code_status": "technical_unknown", "strict_R_code": null, "strict_Q_task_terminal": null, "preserve_original_R_joint": true, "original_submitted": false, "original_R_joint": 0, "reason": "Frozen runner globally replaces socket.socket with a function, breaking unchanged original async P2P test at ssl.SSLSocket class definition. Complete node execution does not establish valid authoritative environment.", "counterfactual_score_reconstructed": false}]}]`。

## 必须保留的比较限制

即使其他槽全部有结果，原3条真实P/U轨迹也不补评分、不重采。因此完整六题P−R与U−P点估计继续null；独立环境审计再使相应三条新末树端点未知。不能用raw固定交付0替代严格代码未知，不能删去未知后改分母。原执行器raw R_code表含环境无效观测，仅供原记录核对，不能作有效业务成绩。

JSON同时保留original_entered_history、r2_rows_before_environment_overlay、独立audit来源、environment_validity_effects和最终逻辑rows。没有写回任一旧行、run、源码快照、权重或评分。后续未开库存如获新的修复/准入须另root记录，本报告不自动释放或启动。
