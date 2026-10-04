# v0.31 原生接口与数值路径修订后的有限选型

状态：`running`；新批执行源码：`3baa4783b7a76d3513a4e2a0d07a0eccb3a81475`。
原始记录：`/data1/zhuxinrui/projects/ProWorkSim/runs/software-model-selection-v031`。

本批仅改变SWE-Next与Devstral的原生接口／密集学习路径；公共世界、六开发合同、SDK、9B路径、两seed及所有选择门均保持。9B的原12槽和旧source只读保留，未重跑或挑选其成功子集。
v0.30原加载失败及r1技术资格失败均保留独立引用与成本；这不是logging-only恢复，也不是把新运行改写为v0.30成功。六案例仍是已见开发材料，不能用于训练支持、贡献估计或独立确认。

## 旧trace数值证明与新鲜资格

| 组合 | 来源 | 旧trace GPU门 | 当前状态 | 新鲜推理资格 | 更新接入 | 近16K | 完整恢复 |
|---|---|---|---|---|---|---|---|
| qwen3.5-9b | 原9B保留 | 不适用 | complete | True | True | True | True |
| swe-next-14b | 新v031组合 | passed | running | False | False | False | False |
| devstral-small-2507 | 新v031组合 | passed | running | True | False | False | False |

旧trace GPU控制只消费原失败的完整token，零新生成／零optimizer step，不证明16K容量。失败臂在numeric_preflight_failed终结，0新资格调用、0正式筛选；另一已准入臂可继续。新鲜资格仍需4条完整trace、原概率门、最多1次真实技术更新、1次新身份回流及完整common恢复。`None`表示未执行或无该项证据，不填成0分。

## 正式筛选逐槽结果

| 案例／seed | 9B原结果 | SWE-Next新组合 | Devstral新组合 |
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

公开测试绿色、任务数、消息数和固定提交都不等于完整验收。每臂须12槽全已知且API／修复／O1各至少2/4完整通过才可入选；三类成绩分开，未知或未启动不补零。

## 分类与选择

两新组合尚未全部终态，未执行最终选择。

## 成本与解释范围

| 组合 | 原v030 GPU秒 | r1 GPU秒 | 旧trace GPU证明秒 | v031新worker秒 | 累计GPU小时 |
|---|---:|---:|---:|---:|---:|
| qwen3.5-9b | 7028.481027 | 0.000000 | 0.000000 | 0.000000 | 1.952356 |
| swe-next-14b | 15.887841 | 236.632682 | 28.811610 | 0.000000 | 0.078148 |
| devstral-small-2507 | 20.620105 | 224.493526 | 40.724319 | 0.000000 | 0.079399 |

成本排名使用上表实际分阶段总成本；原失败不丢弃、r1累计字段中的原失败不重复加。worker成本是单张GPU分配期间墙钟，不是按利用率积分；下载／排队与预约占用另留原始记录。

本批不修改9B模型或原成绩，不根据已知隐藏失败补公开案例，不降低概率／完整交付／分类门。新旧差异只能作为已见开发集上的运行组合选型；没有B/G-raw/I-P配置试训、独立确认或算法收益结论。完整来源身份、实际trace长度、失败原因、数值回执和逐槽证据引用见配套JSON。
