# v052 原十二槽唯一接续合并报告

宿主`complete`；原12行状态`{'closed': 8, 'technical_unknown': 4}`。raw与正式结果分列，未知不填0。

## 六题等权主端点

| 端点/条件 | 已知/6 | 正式均值 | 未决界限 |
|---|---:|---:|---|
| R_code/OH_ref | 5/6 | null | [0.0, 0.16666666666666666] |
| R_code/PS1 | 3/6 | null | [0.16666666666666666, 0.6666666666666666] |
| R_code/PS1−OH_ref | 2/6 pairs | null | [0.0, 0.6666666666666666] |
| Q_task_terminal/OH_ref | 5/6 | null | [0.41432699293309555, 0.5809936595997622] |
| Q_task_terminal/PS1 | 3/6 | null | [0.48807982740021577, 0.9880798274002158] |
| Q_task_terminal/PS1−OH_ref | 2/6 pairs | null | [-0.09291383219954648, 0.5737528344671201] |

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
| v052-cal2-xmltodict-1-PS1 | closed | 0 | 0 | 0.9333333333333333 | 0.9333333333333333 | 0 |
| v052-cal2-xmltodict-2-PS1 | closed | 1 | 1 | 1.0 | 1.0 | 1 |
| v052-cal2-xmltodict-2-OH_ref | closed | 0 | 0 | 0.95 | 0.95 | N/A |

OH固定交付端点不适用；PS1 R_joint/Q_joint六题摘要及raw指标见JSON。测试未观察节点保持not-run/未知，不冒称已执行失败。

## 费用与限制

本轮账本：`{"known_actual_tokens": 2683508, "uncertain_reservation_tokens": 14512, "started_generations": 238, "complete_generations": 237, "ledger_tokens": 2698020, "new_actor_steps": 0, "new_critic_steps": 0, "new_backward_calls": 0, "complete_actual_tokens": null, "logical_inventory": 12, "stage_logical_inventories": [12, 3], "scope": "First-stage sealed scalars once plus continuation-only ledger once; overlapping inventory is not15 slots."}`。

唯一worker `18` 段，已知秒数 `3776.746076107025`，完整秒数 `3776.746076107025`；缺失时不填0。

- Six fixed development tasks from three repositories; not a new independent holdout or vendor benchmark reproduction.
- Same raw/no-adapter project numerical provider; native OH tools/history/finish differ from managed S1 Gamma and fixed submission.
- Each task is equally weighted. Any required unknown makes the full mean or paired difference null; bounds are not confidence intervals.
- R_code/Q_task_terminal compare sole terminal production trees. PS1 R_joint/Q_joint are additional fixed-delivery endpoints; OH is not applicable.
- Safe context or budget closure with all source/guard/test bindings can have known code zero. A fault, missing guard or unstarted slot is not imputed zero.
- No rescore, model retry, additional seed or reward threshold. Report construction performs no new experiment.
- This is the unique original12 inventory, not15 samples. First nine rows remain verbatim; only original three unstarted identities are replaced.
- Four interrupted outcomes remain null. Complete call billing does not prove a terminal business score or exact recovery state.
- The original14512 uncertain reservation remains uncertain; complete actual generation cost stays null after continuation.
- The original file named final.json remains the immutable first-stage report; each stage binds its own plan and supervisor.
- The failed r1 bootstrap entered no slot/model/generation; it adds no scientific row or model fee, but its three worker lifetimes add15.057310104370117 seconds once.
- First-stage nine rows and r2 replacement three remain the same12. r1 is an operational stage, not three new samples.

完整来源与紧凑guard/停止/测试/复用字段见JSON；大段原始调用和测试正文仅在原worker report保留。

首阶段九行原样保留，仅替换原三个未开始槽；四中断评分与 14512 不确定预约保留。完整实际 token 成本仍为 null，分阶段标量与来源见 JSON；未重评分或恢复中断回合。

r1 零模型启动阶段没有新增科学行或模型账单；三个 worker 区间 15.057310104370117 秒单列且仅计一次。r2 仍仅替换原三个未开始槽。
