# v050 Q− r2 恢复边界只读凭据

本核查只读旧 JSON、源码和文件目录，未导入 torch、未读取 `.pt` 内容、未分词、未运行模型或测试。旧 runs 未改动。机器凭据见 [qminus-r2-boundary-proof.json](qminus-r2-boundary-proof.json)。

## 结论

未发现所提恢复方案的科学范围阻断：用户已授权一次新尝试，可在隔离工作树及新运行根从原完整 S_star4/4 重算唯一同一 Q−。必须保留旧停止和全部成本，不重 B，不修改 Q+；原方向、权重、643 行、24 槽与 48 成员分母不变。这不是从第 192 条精确接续，也不保证跨设备逐位结果相同。新运行的源码绑定、预算执行和 GPU 资格仍须由新监督器检查。

## 旧停止边界

旧 PID3124128 在 GPU3 因 `shared_device_free_memory_reserve` 被宿主停止，exit −9。最后样本 free=4698 MiB，低于原 6144 MiB 余量；旧停止时间 1792044614.6065538。

确证 191 条 actor/critic 反向完成；第 192 条原生前向已经返回，其 actor/critic 反向可能未开始、部分进行或已完成但未落盘，均保留未知，不填 0。已记录 835 次原生前向开始及完成，其中 643 次 no-grad、192 次 grad。第 192 条为 `org50-train-LA-r10 / member_001 / model-5f10106ee2f8a3d44c02d838`。

冻结 H1 源码与 plan 及原运行绑定哈希一致。`online_training.py:838–882` 的全部 643 条逐行循环完成后，才保存梯度、裁剪并于 899/907 行执行两个 optimizer.step；每条 actor-enabled 循环都先经过持久化原生计数。仅 192 次 grad 前向且任务仍为 `learning-backward-or-bookkeeping-000835`，因此可证明旧 actor/critic optimizer 调用均为 0，而非仅相信 report 的 0。外层 `status=loading` 是未更新的旧快照，不能用作终态。

旧 actual 目录仅有 `update/shared-before.pt` 非 JSON 状态文件，没有完整更新 checkpoint 或 `gradients-before-clip.pt`。源码在 no-grad 概率检查前保存 shared-before；state bundle 不含累积 `.grad` 或行游标，因此没有第 191/192 条精确梯度、RNG、游标恢复点。此判断基于源码与目录，不声称检查了 `.pt` 内部。

## 状态与材料绑定

旧 loaded-state 完整恢复原 S_star actor/critic 4/4，state digest 为 `ff8c828bcc475132d6d6bbddad3a114da62ace9da9c905e560d7d7c5a3cefc39`。原方向与两层 seal 有效，Q− 权重逐行完全绑定；实际 admission 与预准入删除仅元数据字段 `v050_measure` 后完全一致。643 个 composition 行的 call、成员、token 摘要、权重及 actor/critic 分母全部匹配。ε=0.1，critic 不重加权。

## 原分支预算继续扣账

| 项目 | 旧已耗／上界 | 新上界 | 合计或剩余 | 原上限 |
| --- | ---: | ---: | ---: | ---: |
| 更新区间秒 | 41889.92003273964 | 至多剩余 | 130910.07996726036 剩余 | 172800 |
| 原生前向 | 835 | 1292 | 2127 | 6150 |
| actor 反向 | 191 确证，192 保守上界 | 643 | 835 上界 | 3072 |
| critic 反向 | 191 确证，192 保守上界 | 643 | 835 上界 | 3072 |
| 各 optimizer | 0 | 1 | 1 | 1 |

旧训练区间从 1792002724.686521 保守计至终止完成 1792044614.6065538，包含停止排空，剩余 36.363911102017 小时。若新实现需要整秒上限，可向下取 130910 秒；不得重置 48 小时。旧 GPUworker 时间 42106.40163946152 秒完整保留，训练区间是其中子区间，不重复相加。旧第 192 条可能的部分反向按上界计入。

## GPU4 即时样本

`4, GPU-ae8978c8-5100-933e-78d1-46ed781a8a0e, 61419, 81920, 100`（index, UUID, free MiB, total MiB, utilization %）。这是即时只读样本，未做 60 秒稳定资格，不据此声称 GPU 已独占或已经可以装载；新监督器继续执行原装载前 57344 MiB、60 秒稳定及运行 6144 MiB 余量门。
