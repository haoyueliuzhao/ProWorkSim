# v0.29 新来源经验分配实验记录

- 运行状态：`waiting`；当前阶段：`support`。
- 固定源码：`6b90e9bf71455e904e6b1d2b56e2ef59dabbb7be`；原始目录：`/data1/zhuxinrui/projects/ProWorkSim/runs/software-allocation-v029`。
- 三个来源用途固定：sqlparse训练、schema贡献开发、TextFSM独立确认。
- 首窗8槽同一精确情境、同一参数版本、member_a先手、最低类频数2。保留所有失败、未映射与技术未知。
- 没有可配置支持时停止，不补采、不改分母、不追加无对照基础更新。

## 当前策略原始窗口

| 槽位 | 状态 | R | 路线 |
|---|---|---:|---|
| support-0 | not_started | None | — |
| support-1 | not_started | None | — |
| support-2 | not_started | None | — |
| support-3 | not_started | None | — |
| support-4 | not_started | None | — |
| support-5 | not_started | None | — |
| support-6 | not_started | None | — |
| support-7 | not_started | None | — |

## 实际更新与工作执行

| Worker | 状态 | GPU小时 | actor/critic新步数 |
|---|---|---:|---|
| support | not_started | 0.000000 | 0/0 |

已结束worker累计GPU小时：0.000000；尚在运行worker已用GPU小时：0.000000。
该账含模型装载、训练、冻结执行与worker边界；没有另建显存预留进程。单次训练耗时与峰值见JSON中training_consumption。

## 独立确认与结论边界

TextFSM各方法均值：`{}`；I−B：`None`；I−G：`None`。
缺少完整4次已知验收时不计算该方法均值。每方法4个seed仍为同一个任务，不能解释为12个独立项目或广泛软件泛化。
完整交付、独立API、选定回归和consumer实际调用观察，以及后继sqlparse原件，逐槽保存在配套JSON。
配置权重变化或候选试训完成本身不证明分配有效；若所有schema结果相同，应归因于零可辨识贡献方向及覆盖/基础锚项，不能称为发现高价值经验。
CPU机制资格、真实模型工作结果、真实参数训练收益分别记录；队列状态不是实验效果。
