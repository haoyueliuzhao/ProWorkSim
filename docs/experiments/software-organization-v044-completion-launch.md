# v0.44 原九槽启动记录

北京时间 `2026-10-10T17:55:26.674564+08:00`，finisher/supervisor从 `runs/v044-completion-frozen-source` 启动，PID `1949357`，执行冻结提交 `519a18c4e9397b008a16bf1f40b12726feb34804`。80项必要CPU控制及Ruff通过；原7槽保留，启动前唯一16槽中7已知、新9未开，旧实际3369138 token与4941.221907 GPU worker秒各计一次。

本快照block-r0-s0已分配物理GPU5，完成原60秒资源稳定门后加载原common。另两块尚未启动，等待GPU3/4/5/7范围内资源，满足原门槛后自动并行，最多3resident。加载/分配不算模型输出或正式结果。GPU分配与后续变化以supervisor原记录为准，不借其它卡或下调显存门。

新根 `runs/software-organization-v044-completion`，plan文件SHA `5e7cd76be0a1aa42b52123d819f8c139e65f96cd8d3206aa41fe8c022b8af5e0`，日志 `runs/software-organization-v044-completion-finish.log`。批次政策 `v044-batch-stop-scope-revision-r2`：完整、安全、可核对的局部context终止保留且允许其它独立槽继续，R0/R1与提交前后相同；真实完整性/权限/服务问题或测量待决仍暂停未开槽。模型可见Γ和单成员/episode处理不变。

原9槽不重种子、不重跑原7、不改变初态或任务职责；新上限4500000 token、1152决定/attempt、288测试，旧130862余额不转移。原模型3/3参数冻结、新增actor/critic/反向0；旧训练/Contribution/正式更新/确认/缓存生产仍暂停。只有原9，不自动启动后继24条研究或更长context候选。

终态自动发布报告与推送。报告发布提交不替代实际执行源身份。[协议](software-organization-v044-completion-protocol.md) · [准备记录](software-organization-v044-completion-preparation.md) · [机器启动快照](software-organization-v044-completion-launch.json)。
