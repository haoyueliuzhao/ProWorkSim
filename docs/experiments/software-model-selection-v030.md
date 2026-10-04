# v0.30 O1与代码模型选型运行记录

本记录按本次抢占并接续实验要求进行一次加载故障恢复：9B 的原始 12 槽完整保留，未重跑；仅两新候选在加载证据序列化修复后重新进入资格与原定筛选。旧两次失败原件不改，完整引用见 JSON 的 recovery.prior。
9B 来源为 `c1c8a5e7d2386781cc1bd5233d3659d0a4328f87`；恢复来源为 `caf52da513aea0ba3b4fe27dddf8786ca56358e5`。GPU成本包含旧失败尝试及新尝试；预约占用单独留痕。

运行状态：`finite_batch_no_qualified_candidate`。执行源码：`caf52da513aea0ba3b4fe27dddf8786ca56358e5`。
原始记录：`/data1/zhuxinrui/projects/ProWorkSim/runs/software-model-selection-v030-recovery`。

本轮固定当前9B、SWE-Next-14B、Devstral-Small-2507。仅本项目新派生的Marshmallow六个开发合同参与模型选型；不是六个独立仓库。schema贡献开发和TextFSM独立确认没有参与选择。
最多36条筛选经历，另有每模型4次原生诊断、至多1次诊断参数更新与1个新身份单调用片段；技术控制不算工作成绩。

## 推理与训练资格

| 组合 | Worker状态 | 推理资格 | 更新接入 | 近16K容量 | 完整恢复 | 已记录筛选槽 |
|---|---|---|---|---|---|---:|
| qwen3.5-9b | complete | True | True | True | True | 12/12 |
| swe-next-14b | qualification_failed | False | False | False | True | 0/12 |
| devstral-small-2507 | qualification_failed | False | False | False | True | 0/12 |

`None`表示当前尚无该资格结果。必须通过原概率门、真实完整反传/一步更新、checkpoint重载、新身份回流和容量条件后，才进入冻结开发筛选。诊断正信号不称业务奖励；诊断后完整恢复原共同状态。

## 冻结开发逐槽结果

| 案例/seed | 当前9B | SWE-Next-14B | Devstral-Small-2507 |
|---|---|---|---|
| mm-nested-order-import / 202610040701 | 0 | not_started_or_not_closed | not_started_or_not_closed |
| mm-event-projection / 202610040701 | 1 | not_started_or_not_closed | not_started_or_not_closed |
| mm-envelope-hook-repair / 202610040701 | 1 | not_started_or_not_closed | not_started_or_not_closed |
| mm-nested-error-repair / 202610040701 | 1 | not_started_or_not_closed | not_started_or_not_closed |
| mm-ledger-rootgoal / 202610040701 | 0 | not_started_or_not_closed | not_started_or_not_closed |
| mm-settings-rootgoal / 202610040701 | 0 | not_started_or_not_closed | not_started_or_not_closed |
| mm-nested-order-import / 202610040702 | 0 | not_started_or_not_closed | not_started_or_not_closed |
| mm-event-projection / 202610040702 | 1 | not_started_or_not_closed | not_started_or_not_closed |
| mm-envelope-hook-repair / 202610040702 | 1 | not_started_or_not_closed | not_started_or_not_closed |
| mm-nested-error-repair / 202610040702 | 1 | not_started_or_not_closed | not_started_or_not_closed |
| mm-ledger-rootgoal / 202610040702 | 0 | not_started_or_not_closed | not_started_or_not_closed |
| mm-settings-rootgoal / 202610040702 | 0 | not_started_or_not_closed | not_started_or_not_closed |

R=1需完整独立交付验收；公开回归绿色、任务创建、发送消息或固定提交本身均不等于通过。单执行者API/修复与双成员O1分别评价，未启动不补零。

## 分类与选择

预定规则结果：`finite_batch_no_qualified_candidate`；选定组合：`None`。

| 组合 | API：成功/已知 | 修复：成功/已知 | O1：成功/已知 | 两seed均过案例 | 可选 |
|---|---:|---:|---:|---:|---|
| qwen3.5-9b | 2/4 | 4/4 | 0/4 | 3 | False |
| swe-next-14b | 0/0 | 0/0 | 0/0 | 0 | False |
| devstral-small-2507 | 0/0 | 0/0 | 0/0 | 0 | False |

每类别均预定4次，只有12槽全部已知且三个类别各至少2/4完整通过才可入选。排名依次采用O1、修复、API完整通过数、双seed一致性、格式错误、更低实际worker成本与固定候选顺序。技术失败不触发自动替换模型。

## 实际成本与边界

| 组合 | 结束worker GPU小时 | 诊断actor/critic步数 | 正式筛选优化器步数 |
|---|---:|---|---:|
| qwen3.5-9b | 1.952356 | 1/1 | 0 |
| swe-next-14b | 0.070145 | 0/0 | 0 |
| devstral-small-2507 | 0.068087 | 0/0 | 0 |

已结束worker累计GPU小时：2.090588；运行中worker已用：0.000000。下载/排队未分配GPU，不与worker GPU小时混算。
逐条真实输入输出长度、行为与梯度概率门、技术更新耗时/显存以及失败原因，见配套JSON中的qualification和原始目录。
本轮没有B/G-raw/I-P贡献试训、正式分配或锁定集确认；候选绝对工作变化不代表经验分配增量。一阶公式CPU控制也不代表已完成完整V1.3或跨窗口算法。
全部成功、失败、技术未知和未启动保留。报告只读取当前记录，不重试模型、改变门槛或补采。
