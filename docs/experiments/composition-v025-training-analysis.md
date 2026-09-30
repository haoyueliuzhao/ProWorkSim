# v0.25 支持池与 R1 训练数值详析

本附件汇总 v0.25 原支持窗口与 R1 成功更新的已存证据。结论是：**16 条真实联合经历已经完成一次真实的基础参数更新；成员条件经验重配未触发；这些训练数值本身不能证明工作能力提升。**R2 的业务确认与后继交互结果另见主报告。

本文仅解析 JSON 记录并汇总计数，不加载模型或张量、不调用 API、不重跑环境或评分，不覆盖原始记录。精确字段、汇总值及所用文件 SHA-256 见 [结构化附件](composition-v025-training-analysis.json)。

## 1. 数据身份与重复消费口径

原 v0.25 生成了 16 条唯一新增的联合经历：A、B 两个精确情境各 8 次。它们属于同一冻结窗口 `v025-window-1` 和同一 actor-2 策略。原失败尝试与 R1 恢复各消费同一组 16 条，因而是 **16 条唯一经历、32 次尝试级 episode 消费**，不是 32 条独立训练样本，也不是两次成功参数更新。原始 rollout、成员、调用身份未重写。

| 项目 | 原 v0.25 尝试 | R1 恢复 |
|---|---:|---:|
| 使用原窗口经历 | 16 | 同一 16 |
| 新采集训练 episode | 16 | 0 |
| 已持久化反向完成决定 | 266 / 283 | 283 / 283 |
| 本尝试 actor / critic 优化器步 | 0 / 0 | 1 / 1 |
| 累计 actor / critic 步 | 保持 2 / 2 | 3 / 3 |

原失败由资源查询失败中止；恢复证明同时记录旧 supervisor 的 `task_time_budget` 标签，不能只引用这个旧标签推断是计算超时。原 updater 规定在任一 optimizer.step 之前必须写出的四类产物全部缺失，已结束进程身份也经过检查，由此形成 `optimizer_steps_this_attempt=0` 的记录证据。原进度 266/283 不构成一个已保存的部分更新。

R1 恢复的是原 `shared-before.pt` 中完整 actor、critic、两个优化器及 CPU/CUDA RNG 状态，状态张量摘要前后一致：`4d39266883472dd4ae550ef243b72cce24a65e4ee991cc5e0dcdf88c0062dcf7`。恢复没有复用部分梯度，没有重新生成训练轨迹，也没有再次调用 begin_window。重新构造的 admission 与原文件完全相同，SHA-256 为 `83bcd654eda2e22996ad9bb5d2d53a99892f506cb520737e5688e15eb2029ee3`。本附件引用已有恢复证明，未重新读取张量验证。

## 2. 原支持池的任务表现与方法准入

| 任务 | 原 episode | 全部成员请求 | 实际生成 / 纳入决定 | 自身输出 token | 完整职责 | 平均终局 R | 方法映射 |
|---|---:|---:|---:|---:|---:|---:|---:|
| joint_a | 8 | 159 | 156 | 42,200 | 1/8 | 0.3000 | 1/8 |
| joint_b | 8 | 143 | 127 | 49,810 | 0/8 | 0.0375 | 0/8 |

合计 302 次成员请求中，283 次实际生成形成 92,010 个可训练自身输出 token。余下 19 次请求因上下文限制未开始生成，仍留在原请求和停止记录中，不伪造输出训练目标；所有 16 个原始 slot 都留在冻结分母中。这里的“原 episode 完整”指业务合同完整职责，而不是运行状态 closed。

A 的 8 条经历都完成了适用依据交付（0.2 分），只有 `train-00-5` 将该交付用于正确构建并完成固定提交，R=1；其余 7 条各 R=0.2。B 仅 `train-01-6` 达成正确固定最终产物（0.3 分），未完成独立最终复核与有效复核修复路径，因此 8 条均未完整完成职责；其余 7 条 R=0。

| 成员条件块 | 原 M | 映射后、支持门前候选 | 过门 n_positive | v | 可配置自由度 |
|---|---:|---|---:|---:|---:|
| joint_a / provider | 8 | {"a_active_handoff": 1} | 0 | 0 | 0 |
| joint_a / implementer | 8 | {"a_active_handoff": 1} | 0 | 0 | 0 |
| joint_b / implementer | 8 | {} | 0 | 0 | 0 |
| joint_b / reviewer | 8 | {} | 0 | 0 | 0 |

`train-00-5` 的完整实际路径可映射为 `a_active_handoff`，但该类只有 1 个当前窗口样本，低于冻结的 `min_class_count=2`。因此 A 的两个成员块均为 `n_positive=0、v=0`，`eligible_slots/n_by_class/b` 均为空；不能把“1 个完整映射样本”表述为已经获得可用于重配置的方法支持，也不能把支持后的 v 写成 1/8。B 两个成员块连支持门前候选都没有。

此外，B 的证据反馈 CPU 路径在模型采样前未能于不变上下文预算内通过资格验证，本轮预先声明 B 不进入配置；这是本轮资格限制，不能推论该路径原则上不可行。最终 `selected_block=null`、`changed_blocks=[]`、`Q_equals_B=true`，283 个纳入 actor 目标的组合权重全部为 1。基础 RL 不要求方法类支持，因此仍执行一次基础更新；**本轮没有非平凡 Q/B 重配实验，也没有可报告的经验配比优化收益。**

逐条支持池明细：

| slot | 任务 | 请求 / 纳入决定 | token | R | 完整职责 | 方法映射 |
|---|---|---:|---:|---:|---|---|
| train-00-0 | joint_a | 18 / 17 | 4,445 | 0.2 | 否 | 未映射 |
| train-01-0 | joint_b | 17 / 15 | 5,615 | 0.0 | 否 | 未映射 |
| train-00-1 | joint_a | 19 / 19 | 4,532 | 0.2 | 否 | 未映射 |
| train-01-1 | joint_b | 14 / 12 | 6,668 | 0.0 | 否 | 未映射 |
| train-00-2 | joint_a | 17 / 17 | 3,638 | 0.2 | 否 | 未映射 |
| train-01-2 | joint_b | 16 / 14 | 7,879 | 0.0 | 否 | 未映射 |
| train-00-3 | joint_a | 21 / 20 | 7,423 | 0.2 | 否 | 未映射 |
| train-01-3 | joint_b | 18 / 16 | 4,908 | 0.0 | 否 | 未映射 |
| train-00-4 | joint_a | 22 / 22 | 6,916 | 0.2 | 否 | 未映射 |
| train-01-4 | joint_b | 15 / 13 | 5,680 | 0.0 | 否 | 未映射 |
| train-00-5 | joint_a | 18 / 17 | 4,803 | 1.0 | 是 | a_active_handoff |
| train-01-5 | joint_b | 27 / 25 | 6,516 | 0.0 | 否 | 未映射 |
| train-00-6 | joint_a | 22 / 22 | 4,189 | 0.2 | 否 | 未映射 |
| train-01-6 | joint_b | 19 / 17 | 5,388 | 0.3 | 否 | 未映射 |
| train-00-7 | joint_a | 22 / 22 | 6,254 | 0.2 | 否 | 未映射 |
| train-01-7 | joint_b | 17 / 15 | 7,156 | 0.0 | 否 | 未映射 |

## 3. 实际更新配方与预更新状态

本轮沿用 `terminal_mc`：将该 episode 的终局 R 分配到实际成员输出，减去冻结的预更新、已观察历史 critic 值，不做 advantage 标准化。归一化保留原定 slot × 活跃成员 × 该成员全部实际输出 token 的分母；排除项不会重定义分母。它是成员内 token 平均的 PPO surrogate，原记录明确不主张与未归一化的 episodic policy gradient 精确无偏等价。

| 配方字段 | 本轮值 |
|---|---|
| epoch / discount gamma | 1 / 1.0 |
| actor LR / critic LR | 1e-5 / 1e-3 |
| PPO clip / gradient clip | 0.2 / 1.0 |
| critic coefficient | 0.5 |
| entropy / KL coefficient | 0 / 0 |
| 采样 temperature | 0.7 |
| 最大上下文 / 最大输出 | 16,384 / 2,048 |
| LoRA | r=8，alpha=16，dropout=0，q_proj/v_proj |
| 概率门 max / mean atol | 0.02 / 0.002 |
| 分组梯度额外采集预算 | 0 |

原 update 报告有通用描述字符串 `zero-initialized observed-history critic`，不能据此说本轮 critic 为零。R1 恢复的累计 actor/critic 步已是 2/2，包含既有优化器状态；`critic_had_nonzero_reward_history=true`，283 个实际预更新 critic 值全部非零、均为正，范围为 **0.00750459591～0.0109255742**，平均 0.00955834614。本轮是从既有学习状态继续更新，不是重新初始化 actor、critic 或优化器。

critic 输入为 30 维、截至对应 model_call 开始前已经观察的公共结构与当前成员标记；来源记录列明不包含内容真值、未来观察和终局奖励。这个输入合同及实际来源标记不等于证明 critic 对工作质量已准确校准。

## 4. 概率一致性、损失与真实步进

| 检查 | 决定 / token | 通过 | 最大绝对差 | 全 token 平均绝对差 |
|---|---:|---:|---:|---:|
| behavior probability guard | 283 / 92,010 | 283/283 | 0.0 | 0.0 |
| gradient probability guard | 283 / 92,010 | 283/283 | 0.0 | 0.0 |

两道门分别记录行为概率与重演路径、行为概率与可微路径在实际纳入 token 上一致。这里的 0 是存证比较值，不是把未检查 token 视作相同。

| 更新量 | 已存数值 |
|---|---:|
| actor loss 各决定项之和 | -0.159571246 |
| critic loss 各决定项之和 | 0.0413130446 |
| optimizer step 前 PPO ratio 范围 | [1, 1] |
| clip 生效 / ratio 越界 token | 0 / 0（分母 92,010） |
| actor / critic 梯度范数 | 0.016328346 / 0.101453818 |
| 改变的 actor 元素 | 1,114,065 |
| 本轮 actor / critic optimizer step | 1 / 1 |
| 累计 actor / critic step | 2→3 / 2→3 |

损失按已保存逐决定值求和；本附件未重新计算网络输出或反向。一个 epoch 在同参数旧策略上累积后再执行 step，因而 step 前 ratio=1、clip=0 与非零梯度和真实更新相容，不能据此说没有学习，也不能仅凭损失为负说工作质量改善。actor 摘要从 `2896e50d1b66e915c19d7b13cbab82589976bf073b31152a6b5f29999e8394ed` 变为 `a86e2de651045373cf93242b1708f9f431d9a9388eb43c16e3376bf015fe443a`。

最终检查点记录 `serialized_reload_exact=true`，actor、critic、优化器及 RNG 已保存重载一致；状态张量摘要为 `769e667b3d3866eaa8652807163b893565d98109bc8cfa8a5824601a783dd187`。这证明一次已完成且可恢复的更新，不替代后续业务评价。R1 update 记录的 RSS 峰值为 17.50 GiB；这不是 GPU 显存占用。

## 5. 成员与时间阶段的实际信用信号

全体 283 个决定中 advantage 为正 173 个、为负 110 个、为零 0 个、未知 0 个；范围 -0.0102904197～0.992495404。由于 critic 已非零，B 的 R=0 轨迹产生负 advantage，而非零信号或被删除目标。

| 任务 / 成员 | 决定 | 自身 token | 正 / 负 / 零 advantage | actor loss 项之和 | critic loss 项之和 |
|---|---:|---:|---:|---:|---:|
| joint_a / provider | 39 | 10,367 | 39 / 0 / 0 | -0.0730789557 | 0.0194342725 |
| joint_a / implementer | 117 | 31,833 | 117 / 0 / 0 | -0.0723329427 | 0.0192167249 |
| joint_b / implementer | 62 | 18,108 | 11 / 51 / 0 | -0.00682188082 | 0.00132346695 |
| joint_b / reviewer | 65 | 31,702 | 6 / 59 / 0 | -0.00733746683 | 0.00133858026 |

A 的正 advantage 不仅出现在成功完整履职的一个 episode，也覆盖其他 7 个仅交付依据、最终未完成的 episode。终局 MC 的广播合同使这些 episode 中交付后的各实际输出也获得正信号。**这是存证的信用分配事实；“它可能强化了无效后续动作”只是待对照验证的机制假设，不能作为已证实的因果结论。**

阶段分组是当时公共工作状态与是否已有依据交付的描述；`blocked` 表示观察到的工作状态，并不自动表示每个动作都错。以下仅按原 14 组汇总，不重定义奖励：

| 任务 / 成员 | 阶段 | 决定 | token | 正 / 负 |
|---|---|---:|---:|---:|
| joint_a / provider | open/no_episode_basis_delivery | 11 | 1,940 | 11 / 0 |
| joint_a / provider | open/after_basis_delivery | 7 | 2,972 | 7 / 0 |
| joint_a / implementer | open/no_episode_basis_delivery | 8 | 1,559 | 8 / 0 |
| joint_a / implementer | open/after_basis_delivery | 25 | 9,400 | 25 / 0 |
| joint_a / implementer | in_progress/after_basis_delivery | 28 | 5,646 | 28 / 0 |
| joint_a / implementer | in_review/after_basis_delivery | 1 | 146 | 1 / 0 |
| joint_b / implementer | in_review/no_episode_basis_delivery | 53 | 15,446 | 8 / 45 |
| joint_b / implementer | in_progress/no_episode_basis_delivery | 9 | 2,662 | 3 / 6 |
| joint_b / reviewer | in_review/no_episode_basis_delivery | 60 | 24,344 | 6 / 54 |
| joint_b / reviewer | in_progress/no_episode_basis_delivery | 5 | 7,358 | 0 / 5 |
| joint_a / provider | blocked/no_episode_basis_delivery | 7 | 2,207 | 7 / 0 |
| joint_a / provider | blocked/after_basis_delivery | 14 | 3,248 | 14 / 0 |
| joint_a / implementer | blocked/no_episode_basis_delivery | 2 | 207 | 2 / 0 |
| joint_a / implementer | blocked/after_basis_delivery | 53 | 14,875 | 53 / 0 |

`diagnostic_max_groups=0`，因此本轮没有分组梯度范数、组间余弦或精确梯度贡献归因；14 个组都列在 omitted_groups 中。全局 actor 梯度范数可报告，不能把按任务或动作阶段分组的损失项、加权 advantage 当作该组独立梯度，更不能称为成员因果贡献。work-signal-diagnostics 的动作阶段关联同样是描述性分析，不是动作局部奖励。

## 6. 更新后的有限同上下文概率诊断

预先选择规则是固定 task/member 对的第一个纳入决定，缺失组合不按结果替换。配置上限为 6，**实际只有 4 条决定、504 个原行为 token**，分别对应 A/provider、A/implementer、B/implementer、B/reviewer，额外 actor forward 也是 4。它们是原上下文上的重算，不是 6 个或 4 个新的工作情境。

| 任务 / 成员 | token | 平均新−旧 logp | 平均绝对 logp 变化 | 采样 k3 量 | clip 区间外比例 |
|---|---:|---:|---:|---:|---:|
| joint_a / provider | 41 | -0.000860804616 | 0.00158237045 | 3.21389897e-05 | 0 |
| joint_a / implementer | 265 | 0.000261877624 | 0.0047042575 | 0.000100769868 | 0 |
| joint_b / implementer | 100 | -0.000258141756 | 0.00633058775 | 0.000338603699 | 0 |
| joint_b / reviewer | 98 | -0.00508374873 | 0.00775077936 | 0.000349076332 | 0 |

这些数值支持共享策略确实发生概率变化，且这批选定行为 token 上未见 ratio 超出 clip 区间。`same_parameter_probability_gate=false` 是更新前后参数已经不同的诊断标记，不是前述训练准入概率门失败。`full_distribution_kl_computed=false`，所以不能把采样 k3 量写成完整分布 KL、轨迹 KL 或广泛稳定性保证；采样 logratio 均值可以为负。

## 7. 本附件能支持与不能支持的判断

- **机制通过：**原始自身 token 和角色身份可追溯；原窗口准入与分母保持；同窗口恢复与两道实际概率门通过；检查点完整保存重载。
- **真实学习更新：**R1 完成 283/283 决定反向，actor/critic 各真实步进一次，参数及选定输出概率都改变。
- **经验配置效果尚未测试：**四个成员条件块都没有通过冻结方法支持门，Q=B、权重全为 1，本轮不能评价非平凡联合经验配比优化。
- **业务收益证据不能由训练数值推出：**梯度、损失、参数变化和抽样概率变化都不等于职责完成改善；须结合独立、可比的更新前后工作评价。原支持样本还参与了更新，不能直接把其完整职责比例作为独立对照。

## 8. 主要原始证据

下列为已读本地原始文件。结构化附件记录每个文件 SHA-256 与字节数，供后续审计定位：

- [支持准入与各成员方法支持](../../runs/domain-v025/support/actual/support.json)
- [冻结训练合同](../../runs/domain-v025/support/actual/admission.json)
- [原窗口声明](../../runs/domain-v025/support/actual/collection/declaration.json)
- [R1 恢复证明](../../runs/domain-v025-r1/train_base/actual/restoration-proof.json)
- [R1 准入决定](../../runs/domain-v025-r1/train_base/actual/update/admission.json)
- [R1 更新结果](../../runs/domain-v025-r1/train_base/actual/update-result.json)
- [行为概率检查](../../runs/domain-v025-r1/train_base/actual/update/behavior-probability-check.json)、[可微路径概率检查](../../runs/domain-v025-r1/train_base/actual/update/gradient-probability-check.json)
- [逐决定损失](../../runs/domain-v025-r1/train_base/actual/update/losses.json)、[分组信号](../../runs/domain-v025-r1/train_base/actual/update/signal-diagnostics.json)、[工作信用信号](../../runs/domain-v025-r1/train_base/actual/update/work-signal-diagnostics.json)
- [更新后同上下文诊断](../../runs/domain-v025-r1/train_base/actual/update/post-update-sampled-policy.json)
- [最终检查点元数据](../../runs/domain-v025-r1/train_base/actual/checkpoint-final/checkpoint.json)
