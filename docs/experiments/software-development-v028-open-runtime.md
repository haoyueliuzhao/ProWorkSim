# v0.28 取消统一墙钟与累计GPU时长上限

2026-10-03用户先要求延长等待48小时、八卡全部纳入候选，随后明确取消“最晚运行截止为当天03:05”，并进一步要求“总预算也一并撤销”。当前有效含义如下：

| 项目 | 有效配置 |
| --- | --- |
| 排队候选 | GPU0–7全部八卡，最多两实例并行 |
| 等卡截止 | 北京时间2026-10-06 00:00 |
| 统一墙钟结束时间 | 撤销，wall_deadline_at=null |
| 总累计GPU时长上限 | 撤销，total_gpu_seconds=null |
| 每worker累计GPU时长上限 | 两者均撤销，worker_gpu_seconds均为null；不保留隐含的2×3小时限制 |
| 任务与学习 | 原8槽、每成员48次决策、0参数更新；不自动重试或追加实验 |
| 单任务超时 | 加载15分钟、每episode40分钟、boundary10分钟 |
| 其他运行边界 | 空卡准入、内存/存储保留、telemetry宽限、原始轨迹落盘继续有效 |

累计GPU用量仍记录，但不再用于累计时长终止。完成原8槽后结束；单任务超时、资源故障或其他已声明终止原因仍如实记录，不用撤销累计上限掩盖失败或补造结果。

首次队列`runs/domain-v028-software-dev/`和八卡初次队列`runs/domain-v028-software-dev-wait-extension/`均已确认零worker启动、GPU秒0后停止。终止前核对PID/start_ticks；先冻结监督确认无worker目录，再停止归档驱动，最后让监督保存SIGTERM终态。两个原目录、声明、轮询记录和启动证据均原位保留，没有改写历史预算或消耗记录。第一次过渡见`runs/v028-wait-extension-20261003/transition.json`，第二次见`runs/v028-remove-wall-deadline-20261003/transition.json`。它们保留各自发生时的授权边界；最新时长取消授权另存`runs/v028-open-runtime-20261003/authorization.json`。

新冻结源、同源资格及实际启动身份在核验后补入。真实模型状态以[运行报告](software-development-v028.md)为准，未启动结果仍未知。
