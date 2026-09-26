# v0.14 基础信用分配与学习信号诊断

此修订保留 v0.13 的单一共享 actor / optimizer 与独立 critic，不再把“完成一次更新”作为工作收益。基础配方默认仍为 `terminal_mc`；可在冻结协议的 `recipe.credit_assignment` 中选择 `joint_reward_to_go`。二者都是基础 actor–critic 配方，不是 ID‑VTDO 经验配置干预。

## 旧正式两窗的只读分解

原始目录为 `runs/online-learning-v013-r2`。复算脚本 `scripts/online_signal_report_v014.py` 读取原 admission、优势、loss、概率重算记录及真实 episode 公共事件，没有加载模型、重新前向、修改旧奖励或覆盖原记录。完整分组及每个输入文件的 SHA256 保存在 [v014-historical-signal.json](experiments/v014-historical-signal.json)。

| 窗口 | 任务 / 成员 | 决定数 / 输出 token | 优势范围 | actor loss 项之和 |
|---|---|---:|---:|---:|
| 0 | 交接 / provider | 3 / 201 | +1 | -0.2499998584 |
| 0 | 实现 / implementer | 7 / 522 | 0 | 0 |
| 0 | 复核 / reviewer | 3 / 136 | 0 | 0 |
| 0 | 整链 / provider | 4 / 205 | +0.2 | -0.0166666720 |
| 0 | 整链 / implementer | 8 / 557 | +0.2 | -0.0166666670 |
| 0 | 整链 / reviewer | 6 / 387 | +0.2 | -0.0166666658 |
| 1 | 交接 / provider | 4 / 214 | +0.99464548 至 +0.99465153 | -0.2486620080 |
| 1 | 实现 / implementer | 4 / 392 | -0.00400157 至 -0.00390653 | +0.0009817764 |
| 1 | 复核 / reviewer | 5 / 443 | -0.00440599 至 -0.00439979 | +0.0011009369 |
| 1 | 整链 / provider | 4 / 248 | -0.00541679 至 -0.00515883 | +0.0004348586 |
| 1 | 整链 / implementer | 8 / 374 | -0.00420083 至 -0.00391134 | +0.0003424068 |
| 1 | 整链 / reviewer | 6 / 286 | -0.00464646 至 -0.00436457 | +0.0003756975 |

首窗实现与复核的自身 actor 项严格为零；这些轨迹被保留，并不意味着它们自身产生纠错梯度。次窗的失败项已有小幅负优势，不能继续描述为全零信号。共享参数仍可被其他工作项更新，分组信号也不能直接解释为分组能力变化。

阶段标签只读取该决定之前最近的成员公共工作状态及已经实际应用的 `basis` 送达事件，不使用未来成功结果。首窗整链在实际送达之后仍有 14 个决定、912 个输出 token，全部使用 +0.2 优势：provider 为 2 / 62，implementer 为 7 / 527，reviewer 为 5 / 323。这是终局 MC 将过去成果同时用于后续行为的直接记录，不是对其必然有害的因果结论。

两个旧窗口记录的总 actor 梯度范数分别为 0.1352956891、0.1134966984。旧记录没有保存分组梯度，因此本次不按 loss、token 或总范数比例臆造分组梯度。零优势项在此配方下的自身梯度为零；其他分组的数值范数与方向未知。

旧反向概率记录的 token 比均未触发实际 clipping 分支。旧数据只有更新前的概率重算，不能将其作为更新后策略变化或 full KL；本分析相应字段保留为空。

## 时间信用合同

设每个实际决定开始的全局 episode 事件序号为 `d`。

- `terminal_mc`：所有准入决定以终局合同 `R` 为 critic 目标，优势为 `R - V_old(h_d)`。
- `joint_reward_to_go`：以 `G_d = sum(amount[k] for sequence[k] >= d)` 为目标，优势为 `G_d - V_old(h_d)`。时间线为真实联合 episode 时间线，包含其他成员引起的后续团队成果。

`reward.ledger` 至少包含：

```json
{
  "version": "...",
  "terminal_sequence": 99,
  "events": [
    {"term_id": "deliver_applicable_basis", "sequence": 20, "amount": 0.2, "settlement": "event"},
    {"term_id": "terminal_contract_reconciliation", "sequence": 99, "amount": 0.0, "settlement": "terminal"}
  ]
}
```

训练器验证每个结算位置存在于原始 episode，终点序号等于该 episode 最后事件，金额有限，终点结算位于真实终点，所有结算总额在 `1e-10` 容差内等于同一终局奖励合同。缺失、伪造位置或不守恒的 ledger 不会静默转换为 MC。

只允许已经可以独立判定的成果早结算。当前奖励模块对适用依据实际读取与实际送达提供此类时间位置；实现、固定提交和复核的复合义务仍保守地在终点结算。终点差额项允许为负，明确校正先前成果失效时的总额。成功工具调用、行动数与重复成果不自动产生奖励。完整奖励定义与实际 ledger 由奖励模块保存；训练器不根据工具名制造奖励。

准备前缀仍由真实操作建立状态，但不包含在本轮模型动作或奖励信用中。成员只有在生成该决定之后发生的联合成果才进入该决定的 RTG。某个成员后续的错误 build 不会仅因过去已经结算的交接获得同一正向回报；这也不等于人为给错误工具调用负分。

actor 仍使用每窗固定槽位数 × 活动成员数 × 该成员本轮全部输出 token 的平均 surrogate。RTG 删去过去成果项的动机不等于证明此成员 token 平均目标与未归一化标准策略梯度严格无偏等价。两种时间配方必须在相同任务、公开界面、预算、权重起点和终局奖励合同下比较，不能将同时改动的其他因素归因于 RTG。

## 有界实测诊断

每次准入保存 `terminal_reward`、实际学习目标 `reward`、纳入 ledger 项、已排除过去金额、task、member 和公共阶段。旧字段 `report.rewards` 在 RTG 下指逐决定学习目标；终局奖励仍在 admission 的 slot 奖励记录与逐决定 `terminal_reward` 中，不混用。

`signal-diagnostics.json` 按 task / member / 公共阶段保存优势正负零分布、critic 值范围、目标范围、输出 token、真实 actor / critic loss 项及 clipping。这里区分两个计数：

- `ratio_outside_interval_tokens`：概率比超出区间的 token 数。
- `clipped_objective_tokens`：在当前优势符号下，实际 PPO minimum 使用平坦 clipping 分支的 token 数；正优势对应比值大于上界，负优势对应小于下界，零优势不计入。

`diagnostic_max_groups` 默认 32，可在协议冻结时设为 0 关闭，或设其他非负上限。参数 hook 观察现有 backward 的实际叶梯度，不改变梯度，不增加 actor 前向。各组在 CPU 累加，记录实际梯度 L2、与实际总梯度的点积 / 余弦，以及所有组齐备时重构总梯度的浮点残差。超过上限的组明确记录为遗漏。范数不可相加，方向对齐也不是该组工作收益的因果估计。

`post_update_max_decisions` 默认 12。更新后按准入顺序选取每个新 task / member / 阶段的第一个实际决定，至多达到冻结上限；不以成功、奖励、优势或 loss 选择。仅对这些原始完整上下文额外前向一次，保存更新前 / 后同一采样输出 token 的实际 logp 差、概率比范围、比值超区间比例、平均旧至新 logratio 及 `exp(delta)-1-delta` 的非负采样估计。后者不是遍历全词表的 full KL，也不是新策略在新世界中的成功率。有限采样的平均 logratio 可以为负。额外前向数写入报告。

阶段信息只用于诊断，不增加 actor 可见事实，不改变 critic 输入。它基于本 episode 已发生的公开事件；实现或复核的准备前缀可能已建立工作状态，因此 `no_episode_basis_delivery` 仅表示本 episode 尚无送达事件，不表示世界从未送达资料。

## 回归与边界

本修订执行了 `tests/test_online_signals_v014.py` 与 `tests/test_online_training_v13.py` 的有限回归：常规环境合计 9 passed / 11 skipped，独立 `.train-venv` 实际 Torch CPU 环境 20 passed。训练虚拟环境没有安装 pytest；运行器复用已有纯 Python pytest / pluggy 路径，禁用第三方插件自动加载，没有重新安装训练依赖。这些测试包括实际共享 toy actor 的 RTG 更新、分组梯度取消例、hook 不改变总梯度、更新后实际 logp 改变、旧零信号及概率门限回归。toy 模型结果只证明合同，不算 Qwen 工作学习收益。相关四个源码 / 测试 / 脚本 Ruff 检查通过。

此处没有启动大模型，没有重跑旧 842 项完整回归，也没有以 CPU 数学样例替代后续实际工作比较。正式多窗口、独立训练种子及固定情境重复槽位由冻结协议安排；一个种子内始终只有一套共享 actor / optimizer，重复槽位必须有唯一 slot id，不能将同一历史 episode 重放冒充新交互。

## 预声明开发测量窗口

`run_online_windows` 允许每个窗口显式指定 `mode: "evaluate"` 或 `mode: "online"`，未指定时继承总协议 `mode`。所有窗口的模式在执行前校验；报告逐窗保存实际模式。这样可以在固定训练节点插入开发测量，而无需另开一个模型池，也无需把测量轨迹加入训练。

测量窗只进行真实新世界交互和 `finish_evaluation`，不执行 learner 概率重放、critic 前向或反向。进入测量前记录实际 actor、critic、两个 optimizer、policy revision、actor / critic 更新计数及 critic 非零回报历史的指纹，并保存 Torch CPU / CUDA RNG。测量结束或异常退出时只恢复 RNG，保留真实 window ID、交互、日志与缓存清理计数。任何学习张量或更新计数改变均构成运行错误，不通过回滚张量掩盖。每窗 `evaluation-guard.json` 保存进入 / 离开时的学习指纹，以及采样后和恢复后的 RNG 指纹。

新增定向实际 Torch CPU 检查共 4 项通过：online → evaluate → online 的 toy 运行确有三次新采样、两次 actor / critic 更新，测量窗零更新；第三窗开始时 actor、critic、optimizer 与 RNG 均与进入测量前逐字节相同，三个真实 window ID 全部保留。另覆盖非法逐窗模式、原有全 evaluate 无学习合同及丢失计划槽位拒绝。本 CPU 检查中的 CUDA RNG 列表为空；GPU RNG 恢复路径已实现，此处没有声称完成 GPU 验证。这批只验证受影响的运行器，不重复全部训练或旧完整回归。证据见 [v014-probe-cpu-controls.json](experiments/v014-probe-cpu-controls.json)。
