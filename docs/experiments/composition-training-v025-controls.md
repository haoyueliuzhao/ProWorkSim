# v0.25 成员条件化组成接线与双 KL 配置控制

本记录说明新接入的 actor 组成权重与有限二类配置函数，并报告必要 CPU 控制。它没有运行9B、GPU、业务采样或开发评价，不是当前策略已产生多方法支持的证据，也不是 ID-VTDO 工作收益结果。真实支持与 Mapper 由 v0.25 工作投影负责；新训练运行器负责共同起点、开发与独立确认。

## 1. 原学习器的最小接线

`SharedActor.update_window(..., composition=None)` 新增一个可选的消费参数。默认 `None` 保持原 `Q=B`；`recipe`、checkpoint schema、模型与 critic 结构、学习率、PPO clip、概率门和函数式 Qwen 学习路径未改。因此旧 MC final 的完整 actor/critic/两个 optimizer/RNG 状态仍由原恢复接口读取，不通过改 recipe 规避恢复约束。

`composition_training_v025.materialize_composition(entries, declaration, records, q_by_xi=None, selected_block=None)` 生成消费绑定：

1. 要求原 entries 顺序、计划槽、每槽活跃成员与 declaration 一致，所有 support record 绑定同一原闭合 rollout；mapping 必须与原工作投影一致。
2. 使用既有 `bind_rollout` 派生实际 MemberView，然后按精确 `xi` 调用既有 `support_weights.build_support(..., min_class_count=2)`，不跨情境、当前策略或窗口合池。
3. 使用既有 `materialize_weights(..., lower=0.5, upper=2)`。当前预模型资格门只允许 A 的选定真实二类成员块偏离 B；B 继续输出完整有效性、Mapper 和支持统计，但始终采用 Q=B。接线同时核对 selected.task 和原 entries 的真实任务，不能把 B 改名成 A。其余成员、低频、未映射及可信失败都保留权重1。未知行为证据仍由原准入控制，不为缺失动作制造目标。
4. 保存原 entries/declaration 摘要、Mapper、support 和既有物化结果。实际 update 重新核对这些绑定和 MemberView 的自有 token、原 response 摘要、输入0／本人输出1掩码及两个原分母，拒绝重复同一成员决定或成员串位。

actor 只在原来的 `ppo_sum / actor_denominator` 后乘对应 slot/member 的 `q/b`。当权重等于1时不增加乘法操作，因此显式 `Q=B` 不因额外浮点运算改变原路径。奖励、优势、PPO策略概率比率与其裁剪判定、critic loss、critic optimizer，以及原 slot/member/token 归一化均保持。权重不是 PPO ratio；也不按权重和重新归一化。

每个新 update 额外写出 `composition.json`、`composition-admission.json`；`losses.json` 每行的 `composition_weight` 为实际值。整个配置作为更新消费元数据，不进入 worker 输入，也不写进 checkpoint recipe。

## 2. 固定的有限差分与二类解

纯函数接口：

```text
baseline_configuration(supports_by_xi)
probe_configuration(supports_by_xi, selected_block, epsilon=0.1)
configure_from_development(supports_by_xi, selected_block, baseline_y, probe_y)
solve_two_class(b, contribution, class_order=...)
```

`selected_block` 至少含 `xi_id`、`member_id`、`class_order`，允许投影附带 `task` 和 `perturb_class_id`；后者必须等于 canonical 类列表第一项。不得用字典排序代替事前 canonical 顺序。块选择由工作投影的冻结顺序负责，不按开发成绩另挑。

探测固定 `epsilon=0.1`，方向 `d=δ_z−b`。开发输入为两臂各6个固定槽的完整职责 Boolean／unknown，若任一未知或两臂均值差为0，返回原 `Q=B`、`changed=False` 并给明确原因。此时不因覆盖 KL 单独漂移配置，也不把未知收益当负收益。

存在开发差异时，`C_hat=(mean(probe_y)−mean(baseline_y))/0.1`。只测过一个方向，故设置 `C_z=C_hat/(1−b_z)`、另一类贡献0，使 `⟨d,C⟩=C_hat`；没有声称识别了完整贡献向量或精确导数。

最终配置固定 `q0=B`、覆盖参考均匀、`lambda_h=lambda_r=1`、`beta=0`，最大化：

\[
\langle q,C\rangle-D_{KL}(q\|b)-D_{KL}(q\|[1/2,1/2]).
\]

令第一类概率为 x，则无约束最大值为：

\[
x_* = \operatorname{sigmoid}\left[\frac{C_z-C_{other}+\log(b_z/b_{other})}{2}\right].
\]

完整可行区间同时包含两个类的 `q/b∈[0.5,2]` 与 `TV(q,B)≤0.1`：

\[
\max(0.5b_z,1-2b_{other},b_z-0.1)\le x\le
\min(2b_z,1-0.5b_{other},b_z+0.1).
\]

将严格凹目标的唯一无约束最大值投影到该一维闭区间，即为完整约束解。浮点补数如越过既有严格比例边界，仅向 B 移动到相邻可表示值；不放宽比例门。最终再次调用原 `materialize_weights` 验证。

共同起点恢复与最多一步更新由运行器负责：F0、F_epsilon、F_configured 都从同一采样前 S* 的完整状态出发，消费相同新 D0；不能累计探测参数。该模块不启动任何分支或后继队列。continuation-purpose declaration 不能通过本接线成为额外配置更新。

## 3. 必要 CPU 控制

`tests/test_composition_training_v025.py` 包含3项不同控制。token 来自一个 tiny CPU 模型真实采样，loss 使用原 `SharedActor.update_window` 真正执行 autograd；完整工作有效性与方法标签是明确的构造控制，不是目标9B产生的业务支持。

| 控制 | 直接证据 |
|---|---|
| 单位组成严格恢复 | tiny learner 先真实更新两次，保存含持久 optimizer 的共同 checkpoint。三个分支分别恢复相同完整状态，原 `None` 与显式 `Q=B` 在全部逐行 loss、完整 actor/critic 梯度及最终 `_state_bundle` 摘要上相等；均仅2→3步 |
| 非均匀组成真正入梯度 | 同一批原 token，将仅 implementer 的两类 B=(0.5,0.5) 改为 Q=(0.6,0.4)。actor 原实际梯度及最终 actor tensor 改变；critic tensor、optimizer、梯度与每行 critic loss 完全相同。admission、优势及原 PPO ratio 相同 |
| 残余、原成员与原分母 | 8槽中合格两类各2条，另有低频1条、未映射1条及可信失败2条。合格总权重仍4，原8槽总权重仍8；残余与另一成员均为1。支持外类别、改另一成员权重、伪造物化结果、错 window、换本人 token mask、改actor/critic分母及重复本人决定均被拒绝 |
| 二类配置与停止出口 | epsilon只能0.1；正与负的6槽开发差异分别按已测方向配置；无差或unknown严格保持B。检查 `⟨d,C⟩=C_hat`、两类比例界、TV界，并在内部解及正负边界案例上与完整目标的101点可行网格比较 |

这里的表按机制拆开描述，实际 pytest 仍是3项，不把参数断言、网格点或 repeated run 计成新增独立实验。

定向命令：

```text
runs/v016-sdk/resident-venv/bin/python -m pytest -q tests/test_composition_training_v025.py
```

结果 **3 passed in 2.95s**。随后在同一原成员控制中增加重复本人 call 的负控，仅重跑这一项，**1 passed in 2.69s**；它不是第四项独立测试。新增模块、最小旧学习器修改和测试的 Ruff 检查通过。

CPU 控制支持接线正确性与固定数学解，不证明本次16条真实采样会形成多方法支持，不替代真实开发执行，更不能提前声称独立确认收益。若真实窗口无自由度，应按协议保持基础处理，停止无意义的重复探测。


## 4. 正式运行器追加窄集成

`tests/test_composition_runner_v025.py` 只采集一套16个实际 WorldCore CPU情境，使用正式 `scripts.composition_pilot_v025.support_collection`、`collect_window`、完整 v0.25 投影和真实 native XML parser。业务工具确实执行，但模型 token 由明确的 CPU transport fixture 给出；不把这些记录当作9B支持或训练材料。

先用 tiny CPU 模型真实做两次旧配方更新，保存包含 optimizer 历史与 RNG 的模拟先前 MC endpoint。正式 support 入口恢复该完整状态，在任何新采集前保存新的 origin，并验证完整 state 摘要不变。16槽采集结束后，学习状态保持、RNG恢复，原件与 marker 引用完整；再次通过正式 `train_branch(base)` 恢复 origin，并验证恢复证明、原 window、实际16槽、同原 entries 和单位组成传递到 update 边界。测试在优化前明确截停，没有声称用合成 token 执行了新的真实模型优化；原 actor/critic 步数仍为2。

同一套16槽中，第一个 A 的 provider 使用明确 `resident_direct`、`generation_started=False` 的 context stop。正式投影将其识别为 `known_no_generation`，保留16槽及该活跃成员位置；原 `prepare_window` 不制造该成员的输出目标，其他原成员分母没有缩减。每个精确情境的 `M=8`。这些 fixture 没有完整合法业务路线，支持结果正确保持无可重配块，没有通过伪造路线启动探测。

同一批记录还检验新增的16槽 `work_composition_diagnostics_v025.summarize_work_signals`：用明确的 CPU 算术 report/admission，并在单独诊断副本中设一个1.2权重，确认每槽名义权重1/16、原决定数和每行 `composition_weight`／`configured_token_average_weight` 保存正确。该1.2只是显示算术控制，不是经业务支持准入的配置，更不是一次参数更新；原 entries、实际单位组成与运行 marker 未改。

本次窄审在GPU开始前发现并由根代理修复三个接线问题：

1. `records_from_entries` 是单参数接口，原调用误传 declaration。
2. 旧 v0.23 诊断固定要求6槽，不能直接用于16槽；新版本独立保留16槽并读取实际组成权重，旧文件不重写。
3. checkpoint state reference 含 `bytes`，旧脚本 reference helper 只接受 path/sha 两字段，曾在任何 support episode 采集前拒绝模拟旧 endpoint。新 evidence helper 严格支持这两种既有 reference 形状，同时核验 SHA 及可选文件大小，没有省略身份检查。

修正后唯一一套16槽集成通过：

```text
runs/v016-sdk/resident-venv/bin/python -m pytest -q tests/test_composition_runner_v025.py
1 passed in 48.53s
```

没有重复执行前三项梯度／数学控制，没有第二套16槽采集。新增测试及相关代码 Ruff 检查通过。本项覆盖正式入口到优化调用前的接口和状态，不代表新生产模型已经完成配置学习。
