# v0.13 共享 actor 在线训练实现

本模块把真实交互和参数更新放入同一进程。它提供在线循环的实现，不以实现完成、CPU 测试通过或优化器执行过一次，替代真实工作成绩与学习收益证据。正式实验的协议、资源、实际结果另存于实验文档。

## 对象与边界

`src/proworksim/online_training.py` 的 `SharedActor` 常驻一份原始基座和一份 q_proj/v_proj LoRA（r=8，alpha=16，dropout=0），持有唯一 actor AdamW；所有 provider、implementer、reviewer 使用这一实例。小型中央 critic 与其 AdamW 独立持有，不给 actor 添加联合状态输入。actor 的输入仍是该成员实际公开请求及其真实可见历史。

`DirectModelTransport.complete(request, *, timeout_seconds)` 兼容 ModelPolicy 原返回结构，让原有请求、attempt、response、预算与成员轨迹记录继续工作。它实际是进程内调用，没有 HTTP。返回 `http_status` 是适配器字段，不是网络活动；owner、response.service_record、在线总报告明确记录 `transport_kind=resident_direct` 和 `actual_network_http_calls=0`。原 ModelPolicy 的兼容 attempt 名称与预算字段仍应单独解释为 transport 调用。直接调用是同步执行；记录的 timeout 参数不被解释为具有抢占取消能力的真实 HTTP 超时。

transport 不访问世界、奖励、参考答案或策略规划。它只投影真实公开请求、使用模型聊天模板和已冻结的单次调用语法提示，原样保留解析前输出及全部实际 token。语法错误、错误工具动作及真实拒绝继续由已有 ModelPolicy/StaffRuntime 路径记录，不会在适配器内重新采样或修复。正式配置应固定单次 transport attempt。

## 窗口和权重身份

`begin_window(window_id)` 在空闲边界核验真实参数未被外部改写，并冻结 `owner.freeze_identity()`：

```json
{
  "version": "shared-actor-identity-v0.13",
  "policy_version": "online-actor-N:<adapter tensor SHA256>",
  "adapter_sha256": "<all trainable actor tensor names, dtype, shape and bytes>",
  "base_manifest_sha256": "<verified base file manifest>",
  "inference_profile_sha256": "<actual numeric profile>"
}
```

所有当窗角色的 `ModelPolicy.config.weight_identity` 使用这一完整值，`model_revision` 使用其中的 policy_version。response 同时保留相同 `actor_identity`、`system_fingerprint` 和 `online_window_id`。活动成员不同造成的角色配置集合摘要不同，不代表 actor 权重不同。

每个 role transport 绑定创建时的窗口及身份。窗口完成后统一更新，旧窗口 transport 不能用于下一窗口；新窗口由 collector 创建新 ModelPolicy，重新绑定更新后的同一 actor。零步窗口可以保持相同权重身份，但旧 transport 仍因窗口不同被拒绝。每次 generate 前后和每次更新边界都清除可重用生成缓存；真实工作状态与公开历史如何传递由 collector 和场景合同决定，不缓存旧参数的 KV。

`run_online_windows` 按冻结顺序执行每个窗口的完整 slots。collector 回传顺序、数量或 slot_id 改变会报错，不能丢弃失败后补采样。下一窗口的模型生成发生在上一窗口更新之后。共同检查点包括全部 actor、critic、两个优化器、学习计数、真实身份以及 CPU/CUDA RNG；文件写出后重新读取比对完整张量摘要。`restore_checkpoint` 恢复到已有共享实例，不创建每角色 actor 或优化器。LoRA 另存标准 adapter 文件方便独立环境接入。

## 准入、信号与目标

准入来自完整 TeamRollout/MemberView：每个活动目标成员的全部实际采样决策都保留，包括格式错误、wait/done 和失败工具调用。仅明确未发出请求的预算结束没有 actor target。未知奖励、丢失真实输出、未知行为概率或不可信记录明确隔离；超过长度上限排除该成员完整轨迹，不截短 token 或选取前几轮。隔离不缩小固定归一化分母，也不替换该 slot。

没有旧 D0 成功、固定四槽、永远未更新基座或每窗口回报必须有差异等永久门槛。原始基座文件仍逐项验 SHA；后续权重身份还包含实际更新的 adapter，不能再用基座 revision 代表当前行为策略。

默认配方如下；正式运行使用协议中完整 recipe 冻结实际值：

- 一次完整窗口累积，一次 actor/critic 更新机会；PPO clip=0.2，gamma=1，MC advantage=终局可信环境回报−更新前 critic，优势不标准化。
- actor loss 是每条原始输出 token 的 clipped surrogate；各预定 slot 等权，slot 内活动成员等权，成员内全部实际输出 token 等权。critic 同样按固定 slot/活动成员归一化，成员内按其全部真实决策均分。全体 actor 基础组合权重为 1（Q=B），不按成功筛选。
- actor AdamW lr=1e-5，critic lr=1e-3，weight_decay=0，默认 beta=(0.9,0.999)、epsilon=1e-8；两者分别做梯度范数裁剪 1。critic value loss 是 0.5×平方误差，固定外系数 0.5；entropy/KL 系数固定为 0。
- critic 的 30 维输入由新的版本化 `critic_features.past_features` 从该决策 **model_call started 之前** 的真实联合观察/动作前缀生成，状态包括实际 `in_progress`、`in_review`。critic 为 Linear(30,32)→Tanh→Linear(32,1)，最后层全零初始化，首窗预测严格为零。
- 未学习过任何非零真实奖励且当窗全部可信奖励为零时，actor 明确零步；critic 也不会因初始随机噪声制造信号。同值正奖励允许真实更新。已有非零真实奖励学习历史后，零奖励相对已学习 baseline 的负优势仍是普通 MC 信号。恰好零优势/零梯度不执行 actor optimizer.step。
- 默认温度 0.7，每响应最多 512 token，完整 input+output 上限 8192，不截断。FP32、单 batch、显式 repeatKV + 强制 efficient attention、matmul precision=high；保留实际库版本和运行 flags。
- 行为 logp 来自真实 generate 采样 logits。更新前、实际梯度前向中分别用原完整 input/output ids 复算，容差固定 max=0.02 nat、mean=0.002 nat；越界整个窗口零步并停止在线 runner，不改原值、不放宽门槛。原始全序列 teacher forcing `use_cache=False`，仅物化输出预测位置 logits。
- 模型所有 dropout 必须为零。生成与无梯度门槛使用 eval；梯度前向使用 train 以启动 HF 非重入 gradient checkpointing。此模式变化不引入 dropout。默认 host RSS 上限 64 GiB，在前向/反向间检查；不是外部 cgroup 硬限制，不保证一次内核分配不会先超限。

报告分别记录实际 actor/critic step、前后 tensor SHA、改变的参数元素、真实 loss、行为概率检查及梯度。若 actor step 后发生异常，实际 step 计数不能回写成零或 completed。单次窗口只有一次 PPO 更新，概率比通常接近 1；它不是多 epoch 的效果证明。

## 集成和执行

collector ABI：

```python
collect_window(owner, window_spec, output_dir) -> [
    {"slot_id": "...", "active_members": ["provider"],
     "rollout": team_rollout, "reward": exact_attached_reward},
    # 所有预先固定的槽，包含失败/不可评价项
]
```

需要在创建实际角色 policy 前使用 `owner.transport` 和 `owner.freeze_identity()`；每项回传 reward 必须与历史 TeamRollout 上的 reward 完全相同，且绑定原 episode_id/manifest SHA。规则准备前缀与已存在成果不能作为目标模型本轮动作。完整 world 准入和 reward 检查由在线 collection 与 reward 模块负责，本 learner 再核对记录、角色、行为和 token 一致性。

示例命令（正式协议路径与输出由宿主冻结，不会自动运行）：

```bash
PYTHONPATH=src CUDA_VISIBLE_DEVICES=0 .train-venv/bin/python scripts/online_learning_v013.py \
  --protocol /absolute/frozen-online-protocol.json \
  --model /absolute/Qwen2.5-7B-Instruct \
  --weight-manifest /absolute/verified-base-manifest.json \
  --output /absolute/new-online-run \
  --collector proworksim.online_collection:collect_window
```

`protocol.windows` 是按顺序排列的 `{window_id, slots:[{slot_id,...},...]}`。所有输出目录要求不存在。`mode="evaluate"` 仅运行 collector 的真实交互，完全跳过训练概率复算和 actor/critic 学习前向、反向与更新，随后保存相同权重身份和共同检查点。`--restore-checkpoint <共享检查点目录>` 可在新窗口开始前恢复 θ₂ 的 actor、critic、两优化器、计数和 RNG；不带该参数的独立实例使用初始 actor。评测窗口 ID 必须与恢复状态中的历史窗口不同。片段开始前，collector 可调用 `owner.reseed(predeclared_seed, label=case_id)`；方法要求没有活动生成，记录真实前后 CPU/CUDA RNG 摘要，不改变参数或选择性重采样。新鲜环境回报与跨情境比较仍需独立报告，不由该开关产生收益结论。

## 局部验证的范围

新增 CPU 测试验证：失败/多轮完整保留与固定分母；错权重/丢失输出拒绝；长度不裁剪；两次真实 Torch 小模型采样→更新→新采样时使用同一 actor optimizer；零信号零步后继续下一窗口；概率不一致时两优化器都不更新；共同 actor/critic/optimizer/RNG 状态保存、重读与恢复；禁止 collector 丢弃失败槽。小模型没有专业工作能力，测试通过不能称为 Qwen 在线训练成功或跨工作迁移。
