# v052 原生OpenHands与受管S1桥接终态

宿主`paused`；原12行状态`{'closed': 5, 'technical_unknown': 4, 'not_started': 3}`。raw与正式结果分列，未知不填0。

## 六题等权主端点

| 端点/条件 | 已知/6 | 正式均值 | 未决界限 |
|---|---:|---:|---|
| R_code/OH_ref | 4/6 | null | [0.0, 0.3333333333333333] |
| R_code/PS1 | 1/6 | null | [0.0, 0.8333333333333334] |
| R_code/PS1−OH_ref | 1/6 pairs | null | [-0.3333333333333333, 0.8333333333333334] |
| Q_task_terminal/OH_ref | 4/6 | null | [0.2559936595997622, 0.5893269929330955] |
| Q_task_terminal/PS1 | 1/6 | null | [0.16585760517799353, 0.9991909385113269] |
| Q_task_terminal/PS1−OH_ref | 1/6 pairs | null | [-0.42346938775510207, 0.7431972789115647] |

## 逐槽原始与正式端点

| 槽 | 状态 | raw R_code | 正式R_code | raw Q_terminal | 正式Q_terminal | PS1 R_joint |
|---|---|---:|---:|---:|---:|---:|
| v052-cal2-boltons-1-OH_ref | closed | 0 | 0 | 0.9951456310679612 | 0.9951456310679612 | N/A |
| v052-cal2-boltons-1-PS1 | closed | 0 | 0 | 0.9951456310679612 | 0.9951456310679612 | 0 |
| v052-cal2-boltons-2-PS1 | technical_unknown | null | null | null | null | null |
| v052-cal2-boltons-2-OH_ref | closed | 0 | 0 | 0.0 | 0.0 | N/A |
| v052-cal2-parse-1-OH_ref | closed | 0 | 0 | 0.0 | 0.0 | N/A |
| v052-cal2-parse-1-PS1 | technical_unknown | null | null | null | null | null |
| v052-cal2-parse-2-PS1 | technical_unknown | null | null | null | null | null |
| v052-cal2-parse-2-OH_ref | closed | 0 | 0 | 0.5408163265306123 | 0.5408163265306123 | N/A |
| v052-cal2-xmltodict-1-OH_ref | technical_unknown | null | null | null | null | N/A |
| v052-cal2-xmltodict-1-PS1 | not_started | null | null | null | null | null |
| v052-cal2-xmltodict-2-PS1 | not_started | null | null | null | null | null |
| v052-cal2-xmltodict-2-OH_ref | not_started | null | null | null | null | N/A |

OH固定交付端点不适用；PS1 R_joint/Q_joint六题摘要及raw指标见JSON。测试未观察节点保持not-run/未知，不冒称已执行失败。

## 费用与限制

本轮账本：`{"known_actual_tokens": 1795219, "uncertain_reservation_tokens": 14512, "started_generations": 158, "complete_generations": 157, "ledger_tokens": 1809731, "complete_actual_tokens": null, "logical_inventory": 12, "new_actor_steps": 0, "new_critic_steps": 0, "new_backward_calls": 0, "source": {"source": {"path": "/data1/zhuxinrui/projects/ProWorkSim/runs/software-bridge-v052/supervisor.json", "bytes": 3565328, "sha256": "64830c228d60768807fab107a1a75da55f5a1a286340a6ff1af48fac5f497659"}, "json_pointer": "/ledger"}, "integrity_errors_count": 0, "integrity_errors_source": {"source": {"path": "/data1/zhuxinrui/projects/ProWorkSim/runs/software-bridge-v052/supervisor.json", "bytes": 3565328, "sha256": "64830c228d60768807fab107a1a75da55f5a1a286340a6ff1af48fac5f497659"}, "json_pointer": "/ledger/integrity_errors"}, "scope": "Only the current v052 supervisor actual-native ledger, used once; no v051 or nested cost added."}`。

唯一worker `12` 段，已知秒数 `2683.403012275696`，完整秒数 `2683.403012275696`；缺失时不填0。

- Six fixed development tasks from three repositories; not a new independent holdout or vendor benchmark reproduction.
- Same raw/no-adapter project numerical provider; native OH tools/history/finish differ from managed S1 Gamma and fixed submission.
- Each task is equally weighted. Any required unknown makes the full mean or paired difference null; bounds are not confidence intervals.
- R_code/Q_task_terminal compare sole terminal production trees. PS1 R_joint/Q_joint are additional fixed-delivery endpoints; OH is not applicable.
- Safe context or budget closure with all source/guard/test bindings can have known code zero. A fault, missing guard or unstarted slot is not imputed zero.
- No rescore, model retry, additional seed or reward threshold. Report construction performs no new experiment.

完整来源与紧凑guard/停止/测试/复用字段见JSON；大段原始调用和测试正文仅在原worker report保留。
