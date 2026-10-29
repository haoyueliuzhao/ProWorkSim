# v087：旧 API 自然预算退出的行政交接

本工具只弥补 v086 已冻结交接器的自然退出路径；不修改 v085／v086 运行源码、不发送退出信号、不追加模型或评分、不修改账本、不创建或停止父资源组。实现完成时未执行实际核查、发布或 watcher，运行由主协调者审阅决定。

## 已确认的静态缺口

v086 原交接器要求旧主进程仍等于已记录的 PID，确认静止后才使用 pidfd 结束它。v085 若因原1500元账本达到 `cash_exhausted` 正常收口，会自行写入官方 `run-summary.json` 和最终 progress；随后原 PID 已不存在，不能再满足上述活进程前提。最终 progress 也没有正常循环中的全部 configured／effective／actual 字段，因此原静止判据不会自动采用它。

v085 的正常 finally 还会尝试 `parent.stop_empty()`。存在新 API actor 或父组子 cgroup 时会拒绝；若当时确实为空，旧端可以依法释放共同父组。这会使要求“父组仍合格存活”的旧交接授权入口失效，尽管纯历史记账本身已无需该父组。新评分若因此发生单独故障，本工具只记录它，不把它当成已修复或已完成。

## 发布条件和范围

`tools/complete_natural_api_handoff_v087.py` 只接受：

- 精确旧 v085 unit 已 inactive，原 PID 已消失或 start time 已变化，旧服务 cgroup 不含进程；无既存 signal-intent。
- 原官方 summary 的版本正确、共享 failure 为 null，明确记录 `cash_exhausted`／`api_monetary_budget_exhausted`，并且结束时间晚于本次 gate。
- summary 与 final cursor 的生成、代码评分、交付记录完全一致；原 old-owned 身份齐全；生成、评分、准备／交付 descriptor、待评分及 retained objects 全部清空。
- 新闭合原生成结果的任务／配置／状态与原记录一致，清理回执可信；旧异步评分每项都有精确 outcome 和 request/completion 身份，已消费评分具备真实清理证据。
- 全部旧身份活跃 claim 和 reserved 请求为零；原管理租约已经释放并有同一 claim 的回执。unknown／uncertain 记录不改为零。

先写真实 `natural-exit-v087/proof.json`，再向现有 v086 reader 发布 `historical-results.json` 和 `stopped.json`。仅导入 frozen old-owned 集合，过滤旧预算收口中可能同时标记了后继身份的 not_started 行。记录 `kind=natural_budget_exit`、`signal=null`、`signals_sent=0`，不伪造 SIGKILL。原子顺序保证 stopped 出现时历史文件已完整写好；已有不同历史或 signal 路径不得覆盖。

若父组已经由旧端自然 finally 释放，证明中保留其原释放回执；helper 的 parent operations 始终为 0。没有调用 `require_live_parent`。v086 自身进度及 failure 单独保留观察，不回改它的结果，也不为评分故障扩大执行权限。

## 使用与验证

```bash
# 只读条件核验；尚未自然结束时会拒绝。
.venv/bin/python tools/run_offline_scorer_v058.py tools/complete_natural_api_handoff_v087.py --inspect

# 主协调者决定后明确发布证明与历史。
.venv/bin/python tools/run_offline_scorer_v058.py tools/complete_natural_api_handoff_v087.py --execute

# 可由独立普通用户低资源服务运行；每15秒检查，最长4小时。
.venv/bin/python tools/run_offline_scorer_v058.py tools/complete_natural_api_handoff_v087.py --watch --interval-seconds 15 --maximum-seconds 14400
```

watch 首先只检查 stopped marker 或旧 run-summary 是否出现；旧端正常运行且尚无 summary 时，不遍历源码哈希、结果或评分记录。全部证明条件成立后才发布；否则记录等待理由，超时或收到本 watcher 的停止请求就结束，不代替任务发出停止信号。可变进度写入 `runs/software-benchmark-v087/natural-exit-watch-r1/progress.json`，artifact 只保留封存的验证证据。

初始 6 项有限 CPU fixture 通过：自然预算终态过滤后继身份、拒绝未清理工作及非预算失败、拒绝游标冲突或缺失身份、无信号发布及已有父组释放保留、拒绝既存 signal、watch 时长限制。随后针对 watcher 预检与截止行为的两项窄复测通过，包括确认旧 summary 未出现时不执行完整验证。Ruff 通过。这些控制没有运行真实 unit、Docker、模型、评分或账本操作。

## 部署状态

已启动独立普通用户服务 `proworksim-v087-natural-handoff-watch.service`，仅本服务配置 CPUQuota 10%、affinity 175、Nice 19、MemoryMax 512 MiB、swap 0、16 个任务和 512 个文件描述符；watch 自身最长四小时，服务另有 14500 秒总寿命限制且不自动重启。它不改变旧 API、新 API 或 Qwen 的服务配置。

初次实际进度为 `waiting_for_predecessor_summary`，明确未执行完整证据扫描、未发信号。此时尚未发布自然退出历史，不把 watcher 成功启动当成交接已经完成。启动命令、源码 SHA 及结果保存在 `artifacts/software-benchmark-v087/natural-exit-watch-launch-r1/`；运行中的进度与日志只写 runs 目录。
