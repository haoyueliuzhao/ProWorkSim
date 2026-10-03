# v0.28 取消统一墙钟与累计GPU时长上限

> 本文保留该次启动配置。该队列已自然结束；后续按用户要求仅GPU5恢复上下文异常及未启动槽，最新入口见[修复恢复记录](software-development-v028-context-repair.md)。时长上限撤销继续有效。

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

新冻结提交为`24dbc01eb0d3295a7844b1c8e08fb5c19168fd75`，工作树`runs/frozen-v028-open-runtime/`。仅排队/时长控制及只读报告修改，模型和工作接口源码摘要保持不变。新提交的同源CPU/SDK/tokenizer资格4/4通过，58次程序请求、模型调用0，最大prompt7658、程序输出635、最小余量6678；原请求、XML、token IDs、SDK/世界轨迹分别落盘。该结果是资格程序测量，不是模型成功。

针对runner与reporter的10项检查通过，四个修改代码/测试文件ruff通过。监督CPU模拟覆盖：worker累计10801秒仍可继续并完成；同样累计时长下单次loading已901秒，仍按single_task_budget终止。模拟结果不记入真实GPU占用或模型经历。

截至北京时间 **2026-10-03T14:56:37.382096+08:00**，新队列状态`waiting`，8槽均未启动、GPU占用0秒。归档驱动PID **738565** 与监督PID **738574** 均核对存活、启动身份和冻结cwd，监督心跳距核验约3.0秒。实际载入计划与新声明SHA一致，累计GPU、两worker累计时长及全局墙钟截止均为null。

当前有效路径：

- 新声明与授权：`runs/v028-open-runtime-20261003/plan.json`、`authorization.json`。
- 启动、核验、日志：同目录`launch.json`、`verification.json`、`finish.log`、`qualification.log`。
- 模型队列与原始轨迹：`runs/domain-v028-software-dev-open-runtime/`。
- 归档驱动状态：`runs/domain-v028-software-dev-open-runtime-finish.json`。
- 新同源资格：`runs/v028-controls/frozen-sdk-tokenizer-open-runtime-20261003/`。

归档驱动仍在队列结束后自动只读汇总并提交推送两份运行报告；报告按实际计划显示时长上限，不再写死6 GPU小时或某一墙钟截止。实际模型状态以[运行报告](software-development-v028.md)为准，未启动结果仍未知。完整声明、进程身份、最后一次过渡及校验摘要见[机器证据](software-development-v028-open-runtime.json)。
