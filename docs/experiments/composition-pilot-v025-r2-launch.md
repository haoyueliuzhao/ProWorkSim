# v0.25 R2 仅评价恢复：实际启动记录

北京时间 2026-09-30 13:45:31 CST 已启动，GPU 3，监督器 PID 4028355、worker PID 4028749。此页为启动快照，不是完整评价结果。

- 监督器执行提交：`9a1e3a71a5520203900580eec685c6239b0b1eae`，冻结目录 `runs/frozen-v025-r2`。
- 模型/世界/评分 worker 仍执行原提交：`eeffa716296af65d1c3ea545db9b0da36436841f`，冻结目录 `runs/frozen-v025-r1`，原 plan 不变。
- 实际进程 TMPDIR/TMP/TEMP 均为 `/data1/zhuxinrui/projects/ProWorkSim/runs/domain-v025-r2/tmp`，PYTHONPATH 明确指向原冻结 worker。生产 Python 环境的真实 DuckDB 构建通过，数据卷实际数据库创建成功。
- 原 R1 checkpoint marker 逐字匹配；首例 `confirm-00-0` 已以 `online-actor-3` 原 adapter 身份开始，初始业务状态 SHA 与原中断尝试完全相同。
- 首次采样时 telemetry 新鲜、无连续失败，自身显存约 22.02 GiB。之后运行资源以 supervisor 及 resources.jsonl 为准。
- 仅执行原12确认＋2后继，不重新训练；确认剩余额度约4小时26分47秒，后继1小时，旧费用91221.31274986267 GPU秒继续累计。

[恢复方案](../domain-collaboration-v025-r2-plan.md)说明失败原因、CPU控制、预算与解释边界；[启动机器记录](composition-pilot-v025-r2-launch.json)保留精确身份、环境及摘要。原R1首例未知记录保留，未填零、未重评分。首例重试不增加独特情境数。

运行目录为 `runs/domain-v025-r2`。终态将自动生成独立 `composition-pilot-v025-r2.md/.json` 并提交推送；现阶段不能据启动或恢复成功判断工作能力改善。
