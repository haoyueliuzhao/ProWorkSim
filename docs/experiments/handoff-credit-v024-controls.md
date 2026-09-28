# v0.24：实际交接账本与共同起点消费的 CPU 控制

本记录仅对应生产适配层与训练消费接口的机制控制。它没有模型采样、GPU 计算、概率反向或参数更新，不是 v0.24 学习结果，也不是 ID-VTDO 干预。来源为用户提供的 v0.23 审计与 v0.24 时间信用方案；v0.23 原结果、原 trajectory 和原分数均未重写。

## 1. 唯一被比较的训练因素

`handoff_credit_v024.py` 在新 v0.24 原始 reward 中附加一份两臂共用的事实账本。MC 使用既有 `terminal_mc`；Handoff-RTG 使用既有 `joint_reward_to_go`。终局合同及总回报不变；在线 learner、PPO、critic、优化器、已选 token 概率门、函数式 Qwen 路径均未改变。

A 情境首次合格的当前 episode 依据送达记 0.2，终点记 `R - 0.2`。其他情境或没有合格送达的 A 仅在终点记 `R`。账本调用原 `online_signals.joint_return` 核验事件位置、真实终点和总和守恒。负终点补差保留；重复相同或不同 handoff key 不增加早付。

事件定位按实际 `environment_event.sequence` 顺序扫描。证据必须同时满足：

- 与实际 WorldCore `event_history` 中的应用回执逐项一致，kind 为 `manual_handoff`、outcome 为 `applied`。
- 发送者、接收者、路线、工作、需求版本、项目及 delivered 状态与冻结 A 合同相符。依据对象来自 episode 起点的 workspace；确切版本内容是 immutable captured document，必须具有适用 period 和 approved edition。
- 当前 episode 中存在实际成功且 `created=True` 的 handoff 命令，其事件 ID、handoff ID 和确切 reference 相符；起点已经存在的 handoff 排除。
- 该命令之前，provider 已实际读取相同版本。模型路径还沿用既有 `presented_to_consumer` 检查，要求读结果实际进入该命令所对应模型请求。

定位不读取终局 reward 的成功分项，不读取终局 handoff.status，不用终局需求或别名覆盖起点合同。终局信息只用于 `R - 已付`。每个模型决定仍使用其原始 `model_call started` 序号计算 `u >= s` 的回报和，因此产生交接的决定包含交接项，交接完成后的决定排除已经付出的 0.2。

在“所有计划槽 × 实际活跃成员 × 该成员整条经历的实际输出 token 数”归一化下，两者是不同的时间信用 surrogate。本文不声称梯度无偏等价或只有方差不同。`Q=B` 保持；目标减去各分支自己的 critic 值，目标为零不等于梯度必为零。

## 2. 新材料、原轨迹与分支消费

`collaboration_training_v024.py` 固定两窗材料，每窗仍为 A2+B2+实现1+复核1。新 source PIN、case 摘要、用途、角色、完整职责机会预算、采样 seed 和顺序均被绑定。共同窗 ID 为 `v024-window-1`；两条第二窗分别为 `v024-window-2-mc` 和 `v024-window-2-handoff_rtg`。第二窗情境与 seed 相同，运行和原始 trajectory 独立；各由更新后的本分支重新采集。

新增 `credit_consumption_v024.py`：

1. `save_common_origin(owner, origin_dir, raw_entries, declaration, admission)` 只接受完整新共同窗、未更新 actor/critic、MC recipe 和 collecting 边界。绑定原 entries、declaration、admission 的 SHA256，明确关闭共同采集后调用既有完整 checkpoint 保存，另写 `consumption-origin.json`。这不是 evaluation guard，也未声称共同采集是评价。
2. `prepare_common_consumption(owner, origin_dir, raw_entries, declaration, admission, arm)` 为每个 fresh MC owner 读同一个 checkpoint，使用既有恢复接口并逐项核验完整 `_state_bundle` 摘要。actor、critic、两个 optimizer、CPU/CUDA RNG 必须与共同 origin 完全相同。
3. 恢复后仅更换 recipe 中的 `credit_assignment`，再将状态置为原共同窗的 collecting，以执行既有 `update_window`。不调用新 `begin_window`，不改写原 episode、window、调用、policy 或 token 身份；不同消费使用单独的 `consumption_id`。
4. 两种 recipe 对同一 entries 各调用原 `prepare_window`。除每行 `reward` 和 `credit` 以外，整个 admission 必须完全一致。原 token trace、上下文、critic 前缀特征、槽、成员、call_id 与所有分母都保持。

`online_support.py` 仅添加一项新 harness 映射，指向 v0.24 确定标识 policy 的实际类名，既有映射未改变。新的 common-origin 接口不授予无限重放许可；总体运行器仍约束两方法、各两次更新和新实验预算。

## 3. 必要 CPU 控制及限制

测试文件：`tests/test_handoff_credit_v024.py`、`tests/test_credit_consumption_v024.py`。真实材料来自新增 v0.24 PIN；如材料缺失，测试跳过并明确说明，不以另一来源替代。

| 控制 | 实际执行及判断 |
|---|---|
| A 只有交接 | 真 WorldCore read、handoff、送达，原业务 grader 得 `R=0.2`；早付0.2、终点0，交接后目标0 |
| A 交接＋正确构建 | 真 read/adopt/write/SQL build，原 grader 得 `R=0.5`；早付0.2、终点0.3 |
| A 完整交付 | 在上述路径上实际 submit，原 grader 得 `R=1`；早付0.2、终点0.8 |
| 产生交接的决定 | 原 handoff 动作序号及送达序号仍包含0.2；送达后只含剩余项 |
| 重复、准备前缀 | 真重复相同 key 和另一 key 只记一次；一次完整送达发生在新 episode 开始之前时，新 episode 不记早付 |
| 后续真实需求替换 | 使用 operator 的真实 `revise` 完成晚于送达的需求替换，早事件保持原实际位置；另改内存中的终局 handoff 状态、需求版本，定位结果仍不变 |
| 负补差 | 在上述真实历史上**显式给定数学控制 `R=0`**，验证终点 `-0.2`、总和0、交接后目标 `-0.2`。这不是业务 grader 实际输出0：当前冻结零售 A 合同可能保留原义务的历史交接分，本控制不虚称发现可触发负补差的生产情境 |
| 共同起点 | 六个真 WorldCore 情境，使用明确标注的 CPU 合成 token transport；保存 tiny SharedActor 的全部状态，再对两个独立 owner 故意扰动 critic、optimizer LR、RNG 后恢复。两臂完整状态摘要均匹配 origin |
| 原消费与掩码 | 两臂使用完全相同原 entries，只有目标/credit 字段可变；input mask=0、own output mask=1，已拒或格式错误输出保留；每槽全部成员及 token 分母保持 |
| 缺失与篡改 | 缺失末槽仍保留六槽分母；评价 case 替换、篡改 origin entries、同 owner 重复消费被拒绝 |

这些合成 token 记录只存在 CPU 测试路径，显式标识 fixture；它们没有进入真实实验材料，也未测量模型能力、梯度或概率。tiny SharedActor 检查 CPU RNG 与两套 optimizer 状态；CUDA RNG 的恢复使用原生产 checkpoint API，在此 CPU 控制中列表为空。

首次四项账本测试因实现假定 event history 保存 `result.granted_reference` 而失败。实际 WorldCore 应用记录保存 `payload` 与 `transition`，不保存该 `result` 字段。实现据实际回执 schema 修正，保留与原 event_history 的精确相等检查、applied 状态、原成功创建命令、前缀读取和适用依据检查；修正发生在任何新模型训练之前。随后四项通过。共同起点控制首次通过，未通过更换数值配置修复。

最终定向执行命令为：

```text
runs/v016-sdk/resident-venv/bin/python -m pytest -q tests/test_handoff_credit_v024.py tests/test_credit_consumption_v024.py
.venv/bin/python -m ruff check src/proworksim/handoff_credit_v024.py src/proworksim/credit_consumption_v024.py src/proworksim/collaboration_training_v024.py src/proworksim/online_support.py tests/test_handoff_credit_v024.py tests/test_credit_consumption_v024.py
```

最终定向结果为 **5 passed in 19.87s**；上述限定范围 Ruff 检查通过。重复运行同一控制不增加独立实验样本数。

## 4. 正式运行器的追加窄集成

随后仅增加一项 `tests/test_credit_runner_v024.py`，不重复前述五项核心控制。调用正式 `scripts.credit_pilot_v024.collect_window`，使用六个新材料 WorldCore 情境、正式确定标识 runtime 与 `DeterministicCandidateActor.parse_response` 的真实 native XML 解析；生成 token 仍为明确的 CPU 合成 fixture，没有加载 9B 或执行更新。正式 runner 写出的 declaration/Gamma、entries 与 source admission 随后进入 `save_common_origin` 和两次 `prepare_common_consumption`，均通过，原 entries 字节保持。

同一控制向正式 `credit_signals` 提供标注的 CPU signal report，检验两种实际目标及符号。复用的 v0.23 helper 事实上检查 `admission.row.reward - old_critic`，并不强制使用 `terminal_reward`，因此 RTG 的交接后 `terminal_reward=0.2 / return_target=0 / advantage=0` 能被正确报告，输出 mode 被正式 v0.24 wrapper 标识为 `joint_reward_to_go`。`positive_signal_slots_by_achieved_reward_term` 仍是整个槽的已实现分项与正优势的关联，不能解释为每行剩余回报分项或因果贡献。

运行器第二窗在本分支 `update_window` 返回 idle 后重新调用 `collect_window`；新 `begin_window` 绑定本分支当前 actor，并使用独立方法窗口 ID。此项为代码核对；CPU 集成另外验证，给 D0 declaration 仅替换第二窗 ID 会被不同 slot/case 合同拒绝。没有用伪造更新冒称验证真实第二次 on-policy 模型采样。

追加命令及结果：

```text
runs/v016-sdk/resident-venv/bin/python -m pytest -q tests/test_credit_runner_v024.py
1 passed in 16.03s
```

因此信用层共计六项不同的 CPU 测试：前述五项加本次一项。它们不是六个真实模型实验，也不构成六次学习更新。
