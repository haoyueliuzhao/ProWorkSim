# v051 CAL-1唯一48槽合并结案

本报告只读复用原阶段JSON，逐项绑定续阶段的新33槽。原15个已开始槽没有重跑、重评分或覆盖；原7个已评分但缺worker最终guard的结果及2个缺完整回包继续未决。原grade值与分析结果分别保存。

| 阶段 | 正式宿主状态 | 完整生成 | 已开始缺完整回包 | 本阶段未开始 | 已知实际token | 不确定预约 | worker秒 |
|---|---|---:|---:|---:|---:|---:|---:|
| original | paused | 13 | 2 | 33 | 231909 | 164789 | 13031.596916 |
| idle_continuation | complete | 33 | 0 | 0 | 1410170 | 0 | 66839.583162 |

原阶段33个未开始槽已由续阶段唯一补齐，因此合并库存未开始为0；阶段表保留原停止当时的33，不把它再次计入总库存。已知费用相加一次，不确定预约继续归原中断，不转为续阶段预算，也不声称是已知实际收费。

续阶段新来源/测量检查全部闭合：`True`。这与原未决同时成立；并不将原缺guard解释为已证实权重发生变化。

## 原评分与可归属结果

| 路径 | 原评分通过 | 原评分失败 | 无原评分 | 来源绑定通过 | 来源绑定失败 | 来源绑定未决 |
|---|---:|---:|---:|---:|---:|---:|
| reference | 16 | 8 | 0 | 12 | 8 | 4 |
| project | 14 | 8 | 2 | 11 | 8 | 5 |

原评分只描述已保存代码的官方评分，不替代缺失的最终只读guard。全24题分母下的两路点估计和配对差仍为null。以下完整表保留各槽与配对、原停止、费用与来源限制。

## 合并测量明细

正式宿主终态为`original_paused;continuation_complete`。固定48个单候选槽中，46个生成有完整费用，2个已开始但缺完整回包，0槽未启动。本报告只读汇总原始结果，没有新增生成、评分、分词或参数更新。

冻结执行提交：`19d848e26e25dc2e82ca0b0e748191348fa70d95`。来源绑定是否全部闭合：`False`；48槽来源绑定后的结果全部已知：`False`。原停止与未决记录均保留。

## 固定24题的结果

| 路径 | 成功 | 已知失败 | 技术未知 | 未启动 | 完整pass@1 | unresolved上下界 |
|---|---:|---:|---:|---:|---:|---|
| reference | 12/24 | 8 | 4 | 0 | null | [0.500000, 0.666667] |
| project | 11/24 | 8 | 5 | 0 | null | [0.458333, 0.666667] |

完整配对差project−reference为 **null**。存在未决时，该值保持null；区间是未决结果的显式界，不是把未知当失败。
配对分类：`{"both_fail": 7, "both_pass": 10, "project_only_pass": 1, "reference_only_pass": 1, "unresolved": 5}`。

| 题 | reference | project | project−reference | 输出IDs同值 | token差 |
|---|---:|---:|---:|---|---:|
| `atcoder-abc391_a` | 1 | 1 | 0 | False | -3544 |
| `atcoder-abc400_b` | 1 | 1 | 0 | False | 4476 |
| `atcoder-abc398_a` | 1 | 1 | 0 | False | 1794 |
| `leetcode-3817` | 1 | 1 | 0 | False | -395 |
| `leetcode-3832` | 0 | 0 | 0 | False | 0 |
| `leetcode-3799` | 1 | 1 | 0 | False | 583 |
| `leetcode-3811` | null | null | null | False | 747 |
| `atcoder-abc391_b` | null | null | null | False | 764 |
| `leetcode-3722` | null | null | null | null | null |
| `atcoder-abc397_b` | 0 | 1 | 1 | False | -59998 |
| `leetcode-3754` | 1 | 1 | 0 | False | 15540 |
| `leetcode-3794` | 0 | 0 | 0 | False | -52532 |
| `leetcode-3793` | null | null | null | False | 6167 |
| `leetcode-3791` | 1 | null | null | null | null |
| `leetcode-3748` | 1 | 1 | 0 | False | 4086 |
| `leetcode-3785` | 1 | 1 | 0 | False | 5568 |
| `atcoder-abc393_d` | 1 | 1 | 0 | False | 5112 |
| `atcoder-arc192_e` | 0 | 0 | 0 | False | -7129 |
| `atcoder-arc193_d` | 0 | 0 | 0 | False | 15187 |
| `atcoder-arc192_b` | 0 | 0 | 0 | False | 0 |
| `atcoder-abc398_g` | 0 | 0 | 0 | False | -3925 |
| `leetcode-3701` | 0 | 0 | 0 | False | -36270 |
| `atcoder-abc398_d` | 1 | 1 | 0 | False | -2183 |
| `atcoder-abc394_e` | 1 | 0 | -1 | False | 41847 |

这些读数只涉及事前固定的24题、每路单候选。[官方Qwen模型卡](https://huggingface.co/Qwen/Qwen3.5-9B)的LCB v6=65.6不作为门槛；本面板是[官方v6增量来源](https://huggingface.co/datasets/livecodebench/code_generation_lite/tree/0fe84c3912ea0c4d4a78037083943e8f0c4dd505)的难度分层样本，不是累计1,055题或厂商完整recipe复现。

## 停止、提取与费用

| 路径 | 完整生成 | 已知实际token | 原生终止计数 | 提取为空 | 官方错误码 |
|---|---:|---:|---|---:|---|
| reference | 24 | 879,647 | `{"length": 5, "stop": 19}` | 4 | `{"-2": 3, "-4": 5}` |
| project | 22 | 762,432 | `{"length": 4, "no_complete_generation": 2, "stop": 18}` | 3 | `{"-2": 2, "-4": 6}` |

已知实际生成量 **1,642,079 token**；无完整回包的保守预约 **164,789 token**；完整实际费用为`None`。预约不是已证实实际费用。原宿主账本与只读重算一致：`True`。

唯一8个worker区间共 **79871.180078秒（22.186439小时）**。包含装载、资源预留、生成、CPU评分、收尾和失败区间；原生生成耗时已经嵌套其中，不再次加总。这不是GPU kernel忙时。

| worker | attempt | GPU | 秒 | 退出码 | 原终态/停止原因 |
|---|---|---:|---:|---:|---|
| shard-0 | `attempt-001` | 7 | 2872.899143 | 0 | paused_before_next_slot / None |
| shard-1 | `attempt-001` | 5 | 2821.086993 | -15 | None / None |
| shard-2 | `attempt-001` | 6 | 3756.258420 | -15 | None / supervisor_interrupted_or_fault |
| shard-3 | `attempt-001` | 1 | 3581.352361 | 0 | paused_before_next_slot / None |
| shard-0 | `attempt-001` | 6 | 10126.474538 | 0 | complete / None |
| shard-1 | `attempt-001` | 7 | 11760.731278 | 0 | complete / None |
| shard-2 | `attempt-001` | 4 | 11874.513596 | 0 | complete / None |
| shard-3 | `attempt-001` | 7 | 33077.863750 | 0 | complete / None |

本轮另有用户明确要求让渡GPU5、撤销在途GPU实验并改为空闲调度的外部有意中断。该回执按GPU、PID绑定原worker，并保留宿主原停止名称与调用未知；不将它解释为算法失败或普通显存故障，也不据此重采。
外部干预：`[{"source": {"path": "/data1/zhuxinrui/projects/ProWorkSim/runs/software-calibration-v051-cal1/gpu5-relinquishment.json", "bytes": 853, "sha256": "e63158b16b130ba6f112901d35dd11c8df0c08b6aa921219147b19c59271f1a6"}, "kind": "explicit_user_gpu_relinquishment", "reason": "User instruction: 让渡GPU5", "requested_gpu": 5, "pid": 1609847, "at": 1792241353.659443, "worker_binding_known": true, "worker_attempt": "/data1/zhuxinrui/projects/ProWorkSim/runs/software-calibration-v051-cal1/shard-1/attempt-001", "classification": "explicit_user_resource_relinquishment", "restart_or_resample_authorized": false, "worker_released": true, "original_host_stop_and_unknown_records_preserved": true, "not_an_algorithm_or_ordinary_resource_failure": true}, {"source": {"path": "/data1/zhuxinrui/projects/ProWorkSim/runs/software-calibration-v051-cal1/gpu-idle-reschedule.json", "bytes": 2152, "sha256": "f8f1541ac7cb300f48f477de7299fa102a0603df135ceb45176ab141219aa5a5"}, "kind": "explicit_user_cancel_active_gpu_and_reschedule_when_idle", "instruction": "当前资源紧张，撤销本次GPU实验，安排调度器在显卡空闲时进行任务，并发上限设为4，除GPU2，5均可调度", "at": 1792242290.2763581, "worker_binding_known": true, "worker_attempts": ["/data1/zhuxinrui/projects/ProWorkSim/runs/software-calibration-v051-cal1/shard-2/attempt-001"], "classification": "explicit_user_idle_rescheduling", "allowed_gpu_indices": [0, 1, 3, 4, 6, 7], "max_residents": 4, "no_started_request_replay": true, "original_host_stop_and_unknown_records_preserved": true, "not_an_algorithm_or_ordinary_resource_failure": true}]`。

## 全48槽附表

| 槽 | seed | GPU | 终态 | pass@1 | finish | native错误码 | 实际token |
|---|---:|---:|---|---:|---|---|---:|
| `cal1-01-reference` | 202610170511 | 7 | passed | 1 | stop | None | 9043 |
| `cal1-01-project` | 202610170511 | 7 | passed | 1 | stop | None | 5499 |
| `cal1-02-project` | 202610170512 | 7 | passed | 1 | stop | None | 18978 |
| `cal1-02-reference` | 202610170512 | 7 | passed | 1 | stop | None | 14502 |
| `cal1-03-reference` | 202610170513 | 7 | passed | 1 | stop | None | 9254 |
| `cal1-03-project` | 202610170513 | 6 | passed | 1 | stop | None | 11048 |
| `cal1-04-project` | 202610170514 | 6 | passed | 1 | stop | None | 4492 |
| `cal1-04-reference` | 202610170514 | 6 | passed | 1 | stop | None | 4887 |
| `cal1-05-reference` | 202610170515 | 6 | official_incorrect | 0 | length | -4 | 82490 |
| `cal1-05-project` | 202610170515 | 6 | official_incorrect | 0 | length | -4 | 82490 |
| `cal1-06-project` | 202610170516 | 6 | passed | 1 | stop | None | 10603 |
| `cal1-06-reference` | 202610170516 | 6 | passed | 1 | stop | None | 10020 |
| `cal1-07-reference` | 202610170517 | 5 | technical_unknown | null | stop | None | 6140 |
| `cal1-07-project` | 202610170517 | 5 | technical_unknown | null | stop | None | 6887 |
| `cal1-08-project` | 202610170518 | 5 | technical_unknown | null | stop | None | 8390 |
| `cal1-08-reference` | 202610170518 | 5 | technical_unknown | null | stop | None | 7626 |
| `cal1-09-reference` | 202610170519 | 5 | technical_unknown | null | stop | None | 28212 |
| `cal1-09-project` | 202610170519 | 5 | technical_unknown | null | None | None | null |
| `cal1-10-project` | 202610170520 | 7 | passed | 1 | stop | None | 22380 |
| `cal1-10-reference` | 202610170520 | 7 | official_incorrect | 0 | length | -4 | 82378 |
| `cal1-11-reference` | 202610170521 | 7 | passed | 1 | stop | None | 20565 |
| `cal1-11-project` | 202610170521 | 7 | passed | 1 | stop | None | 36105 |
| `cal1-12-project` | 202610170522 | 7 | official_incorrect | 0 | stop | -4 | 30080 |
| `cal1-12-reference` | 202610170522 | 7 | official_incorrect | 0 | length | -4 | 82612 |
| `cal1-13-reference` | 202610170523 | 6 | technical_unknown | null | stop | None | 21722 |
| `cal1-13-project` | 202610170523 | 6 | technical_unknown | null | stop | None | 27889 |
| `cal1-14-project` | 202610170524 | 6 | technical_unknown | null | None | None | null |
| `cal1-14-reference` | 202610170524 | 4 | passed | 1 | stop | None | 24898 |
| `cal1-15-reference` | 202610170525 | 4 | passed | 1 | stop | None | 10315 |
| `cal1-15-project` | 202610170525 | 4 | passed | 1 | stop | None | 14401 |
| `cal1-16-project` | 202610170526 | 4 | passed | 1 | stop | None | 15477 |
| `cal1-16-reference` | 202610170526 | 4 | passed | 1 | stop | None | 9909 |
| `cal1-17-reference` | 202610170527 | 4 | passed | 1 | stop | None | 14529 |
| `cal1-17-project` | 202610170527 | 4 | passed | 1 | stop | None | 19641 |
| `cal1-18-project` | 202610170528 | 4 | official_incorrect | 0 | stop | -2 | 73404 |
| `cal1-18-reference` | 202610170528 | 4 | official_incorrect | 0 | stop | -2 | 80533 |
| `cal1-19-reference` | 202610170529 | 1 | official_incorrect | 0 | stop | -2 | 67767 |
| `cal1-19-project` | 202610170529 | 7 | official_incorrect | 0 | length | -4 | 82954 |
| `cal1-20-project` | 202610170530 | 7 | official_incorrect | 0 | length | -4 | 82705 |
| `cal1-20-reference` | 202610170530 | 7 | official_incorrect | 0 | length | -4 | 82705 |
| `cal1-21-reference` | 202610170531 | 7 | official_incorrect | 0 | stop | -2 | 57712 |
| `cal1-21-project` | 202610170531 | 7 | official_incorrect | 0 | stop | -2 | 53787 |
| `cal1-22-project` | 202610170532 | 7 | official_incorrect | 0 | stop | -4 | 46261 |
| `cal1-22-reference` | 202610170532 | 7 | official_incorrect | 0 | length | -4 | 82531 |
| `cal1-23-reference` | 202610170533 | 7 | passed | 1 | stop | None | 28364 |
| `cal1-23-project` | 202610170533 | 7 | passed | 1 | stop | None | 26181 |
| `cal1-24-project` | 202610170534 | 7 | official_incorrect | 0 | length | -4 | 82780 |
| `cal1-24-reference` | 202610170534 | 7 | passed | 1 | stop | None | 40933 |

## 原件与解释限制

报告JSON逐项列出generation、grade、原始task/worker/账本、native故障与来源SHA。评分严格复用同一完整公共+私有样本；未重新执行候选代码。官方空metadata故障、原生fatal退出或评分缺回包保留技术未知，未补为0。若worker的终态只读guard缺失，原grade分数仍单独保留，来源绑定后的分析值为null。

准备阶段的下载截断/ETag判断、tokenizer返回类型、宿主Path类型和测试收集错误均继续保留。双EOS修订、loading-info序列化增量控制，以及评分子进程继承worker进程组的静态修订各有独立回执；原控制汇总和原失败没有回写。报告生成不重复这些控制。

两路共享HF生成器、BF16主干与FP32输出头；reference为官方支持入口下的共同数值桥接，project保留v020注意力路径。相同题、seed、模式、解码和评分减少比较混杂，但不证明逐token等价，也不把有限差异唯一归因于某一组件。新增训练为0，结果不构成学习收益证据。

CAL-0是先前独立的只读核查；CAL-2/HOLD的任务资格与结果不由本报告推断。本报告不启动任何后继、旧训练或缓存生产。

来源/测量问题：`[{"kind": "slot_binding_issues", "slots": ["cal1-07-reference", "cal1-07-project", "cal1-08-project", "cal1-08-reference", "cal1-09-reference", "cal1-09-project", "cal1-13-reference", "cal1-13-project", "cal1-14-project"]}]`。
原pause记录：`{"kind": "execution_or_measurement_pause", "detail": {"worker": "shard-1", "attempt": {"started_at": 1792238534.330084, "pid": 1609847, "output": "/data1/zhuxinrui/projects/ProWorkSim/runs/software-calibration-v051-cal1/shard-1/attempt-001", "gpu": {"index": 5, "uuid": "GPU-f731a280-01e3-2359-ace9-aa2ad2112f55", "free_mib": 53467.0, "total_mib": 81920.0, "utilization_percent": 35.0, "shared": true}, "binding": {"version": "software-learning-resources-v0.50-r3", "gpu_index": 5, "gpu_uuid": "GPU-f731a280-01e3-2359-ace9-aa2ad2112f55", "sampled_free_mib": 53467.0, "target_mib": 52443}, "command": ["/data1/zhuxinrui/projects/ProWorkSim/runs/v016-sdk/resident-venv/bin/python", "-m", "scripts.software_calibration_v051", "worker", "--root", "/data1/zhuxinrui/projects/ProWorkSim/runs/software-calibration-v051-cal1", "--worker", "shard-1", "--attempt", "/data1/zhuxinrui/projects/ProWorkSim/runs/software-calibration-v051-cal1/shard-1/attempt-001"], "identity": {"pid": 1609847, "available": true, "alive": true, "start_ticks": 466292950, "state": "R"}, "ended_at": 1792241355.4170759, "seconds": 2821.0869925022125, "exit_code": -15, "reason": null, "report": {}}}, "at": 1792241355.4171844}`。

## 独立阶段判断所需证据

本次没有释放CAL2或HOLD，不依据通过率作下一阶段门槛。可供独立准入引用的是：原阶段报告和两个已闭合宿主的SHA、原9个未决的来源与范围、新阶段有无新增完整性问题、唯一库存和费用。这些字段位于JSON的stage_review_evidence；是否准入由后续独立协议决定。

续阶段执行时使用0/1/3/4/6/7空闲60秒且无compute进程、util为0的历史资源门，并发上限4；实际worker GPU按附表保留。之后用户解除GPU范围及空闲限制属于后续资源协议，不回写本阶段。

本报告只新增有限合并CPU控制，不重复先前11项控制；无新模型、评分、分词、训练或学习更新。
