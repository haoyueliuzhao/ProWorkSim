# v030–v032 GPU 区间并集记账修订

生成时间：2026-10-05T10:36:43.589448+08:00（北京时间）。

本修订按每张 GPU 对已记录的 worker 与 reservation 时间区间重新求并集、交集；未调用模型、GPU 或重新评分。
输入为 `runs/v032-final-analysis/costs.json`，SHA-256 为 `61324dd1490f01387d6f67513ab37f8edd618f8453dcc01f2423facd832f64b5`。

共读入 11 个 worker 区间、7 个完整 reservation 区间；另有 1 个预约 child 因缺少完整边界单列为未知。
worker 边界采用 assigned→ended；预约边界采用 allocation_ready→ended。先在同一卡上合并相交、包含、相邻和重复区间，再计算交集与两类区间并集，最后跨卡相加。跨卡并行时间分别计入 GPU 小时，不作为全局墙钟时间。

| 口径 | GPU 秒 | GPU 小时 |
|---|---:|---:|
| worker 区间并集 | 21401.993382 | 5.944998162 |
| reservation 区间并集 | 5045.830958 | 1.401619711 |
| 两类区间交集 | 0.000000 | 0.000000000 |
| 总体已记录占卡区间并集 | 26447.824340 | 7.346617872 |
| 仅预约、无 worker 覆盖 | 5045.830958 | 1.401619711 |

| GPU | worker 并集秒 | reservation 并集秒 | 交集秒 | 总体并集秒 | 仅预约秒 |
|---|---:|---:|---:|---:|---:|
| 4 | 11346.010263 | 3510.554580 | 0.000000 | 14856.564843 | 3510.554580 |
| 5 | 497.634154 | 685.035450 | 0.000000 | 1182.669604 | 685.035450 |
| 6 | 9558.348965 | 850.240928 | 0.000000 | 10408.589893 | 850.240928 |

实算各卡两类区间的交集均为 0 秒。因此本次已记录总体区间并集在数值上等于两个并集之和；这一结论来自逐区间计算，并非直接将旧报告的两个四舍五入小时数相加。

历史 worker-only 成本仍独立保留：21401.993381739 秒（5.944998161594 GPU 小时）。区间时间戳复算与旧浮点时长的差为 0.000000261338 秒，属于记录精度差异；不改写旧 worker 成本，也不将预约成本混入模型筛选排名。

## 未纳入并集的未知预约

- GPU5，PID 2934162，`/data1/zhuxinrui/projects/ProWorkSim/runs/v030-recovery/gpu5-reservation`，状态 `failed`：没有完整 allocation_ready→ended 边界，实际分配持续时间未知。记录 child body 墙钟时间为 0.48435354232788086 秒；它不能替代 GPU 占用时间，也不能被解释为已证明占用 0 秒。

## 边界与解释

这份统计只覆盖日志已记录的区间。worker 生命周期包含加载、诊断、筛选、退出及失败，并不意味着全程高利用率；reservation ready→end 也不是精确 GPU 计算时间，更不能证明最后心跳后始终独占。尚未 ready 的分配过程、缺边界的失败预约和记录外活动没有被猜测填补。

已 ready 但失败的预约仍按完整已记录区间纳入。watcher 等待、handoff 元数据、同一 child 的重复 state/result 引用均不另加。原 36 槽结果、模型调用、参数更新和技术准入结果完全不由本项成本修订改变。

## 可复算方法

```bash
.venv/bin/python scripts/gpu_occupancy_accounting.py \
  --input runs/v032-final-analysis/costs.json \
  --json-output docs/experiments/gpu-occupancy-v030-v032.json \
  --markdown-output docs/experiments/gpu-occupancy-v030-v032.md
```

机器记录保存所有输入区间及源 JSON pointer、各卡合并后区间、交集和汇总。必要 CPU controls 覆盖相交、包含、相邻、重复、多卡独立与负值/无效边界拒绝；执行回执见 `runs/v033-controls/occupancy/checks.json`。
