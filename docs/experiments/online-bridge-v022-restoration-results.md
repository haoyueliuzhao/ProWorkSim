# v0.22 R1：原窗口精确恢复、完整更新与后续工作

日期：2026-09-27。本记录单独覆盖 `runs/domain-v022/R1`。数据来自已闭合的原始文件，只做读取、统计与保存张量的 CPU 检查；没有重跑模型、概率、评分或反向。原 B1 的时限停止与成本保留在 [B1 专项记录](online-bridge-v022-results.md)，不被本次成功覆盖。

## 1. 结论及边界

R1 以原 B1 更新前快照精确恢复同一个 `v022-b1-train` 窗口，从头重算原有 24 条行为，完成 24/24 次反向，并实际执行 **actor 1 step、critic 1 step**。行为复算与有梯度前向两套检查均覆盖原 3134 个目标 token，全部通过，逐条 max/mean 误差均为 0。保存的全部 actor/critic 梯度有限，actor 实际改变 589824 个元素，身份从 `online-actor-0` 刷新为 `online-actor-1`。

同一进程随后以更新后的参数运行了原先未开始的两个保留工作片段，两例均闭合且评价记录可信，奖励分别为 0.2、0，完整职责完成数为 0/2。两例各自的学习状态不变、Torch CPU/CUDA RNG 恢复守卫均通过。整线退出码为 0，前后源码相同。

这支持“真实成员行为投影 → 同一共享模型完整 PPO 更新 → 更新后身份继续实际工作”的工程闭环。它不是学习收益对照，不证明一次更新改善了工作；也没有形成多窗口学习、MC/R比较或 ID-VTDO 分布干预结论。

## 2. 为什么它是恢复，而不是新增训练样本

原 B1 在 12/24 条反向进度处触发原单任务时限。其 actor/critic step 均为 0，post 两例均未开始。已审计的原 updater 必须在 optimizer step 之前写出完整概率检查、losses、signal diagnostics 和梯度文件；这些文件当时全部不存在，原模型及 observer PID 已消失。该证据结合已保存进度支持“尚未到 step”，但不冒称取得了原 B1 被终止瞬间的 live 参数哈希。

R1 使用独立冻结源和输出目录，恢复原 `shared-before.pt` 中 actor、critic、两个 optimizer、CPU/CUDA RNG、window 与 policy identity。运行时恢复守卫记录：

- `exact_state_restored=true`，完整状态 digest 为 `1107fac7b2e52995f17ef115b494bf282b063d0c2482cf79e37ec754bdc31c9f`。
- 恢复前重建、恢复后重建的 admission 均与原 admission 精确相等：4 个槽位、24 条决策、3134 个目标 token，固定分母未变。
- 原 B1 已完成的 12 条反向及未知数量的在途计算全部丢弃，没有复用部分梯度。
- `new_training_model_calls=0`，没有再次采集 train，也没有把旧轨迹变为教师/SFT 样本。
- 仅执行原窗口所允许的一次共享更新；随后两例 post 是原先尚未开始的新工作片段，不进入本次训练。

原 B1 的失败与 R1 的恢复分别记账；R1 的 24 条不是新增加的 24 条独立训练样本。

## 3. 保持的学习路径与实际概率证据

执行源为 `c106fe3f34a65de76a235f857ca2323d29046b74`，tree SHA256 为 `1679ca5baafb4a028cc53f9d7e5039f92a57c8f64d9e1301b4eec386b97c89f8`。终态 `source_unchanged=true`，前后 `code_dirty=false`。

N1 功能式状态模块与原 PPO updater 的文件 SHA 均与原 B1 相同。仍保留完整 prefill、全部已保存输出、过去状态的 LoRA 依赖，使用非重入 checkpoint、8 token 解码块；未 detach 过去状态，未截断上下文或目标，未改变 dtype。原报告沿用的“full-sequence recomputation”表示以功能式递归完整重算原上下文，不能理解为旧的无 cache 一次性 full forward。

训练仍为 terminal MC、Q=B、composition weight=1、1 epoch，actor LR=1e-5、critic LR=0.001、PPO clip=0.2、gradient clip=1，温度 0.7。固定 token/成员/槽位归一化保持不变。原门槛仍是 max≤0.02、mean≤0.002，未因恢复放宽。

| 实际检查 | 决策数 | 目标 token | max absolute delta | 最大逐条 mean absolute delta | 通过 |
|---|---:|---:|---:|---:|---:|
| 原行为 vs no-grad 功能式复算 | 24 | 3134 | 0 | 0 | 24/24 |
| 原行为 vs grad-enabled 功能式前向 | 24 | 3134 | 0 | 0 | 24/24 |

两份检查原件的 SHA 相同，说明保存的相应数组与标量也一致。这里验证的是实际采样目标 token 的条件概率，不是全词表分布 KL；并未计算完整分布距离。

原 critic values 全为 0，24 条中 8 条优势为 +0.2、16 条为 0，没有负优势。非零信号来自原 joint A 中“适用依据已实际交付”的奖励项；该奖励不代表依据已经用于正确 build。窗口因此不是 zero signal。固定配方也没有跳过零优势行的 actor 重算。

## 4. 实际梯度、步进和身份

`gradients-before-clip.pt` 与 `checkpoint/shared-state.pt` 另以 `CUDA_VISIBLE_DEVICES=''`、`torch.load(weights_only=True,map_location='cpu')` 读取；该核验没有构造模型或访问 GPU。

| 项目 | actor | critic |
|---|---:|---:|
| 保存的梯度张量数 | 32 | 4 |
| 梯度 dtype | FP32 | FP32 |
| 梯度元素数 | 1114112 | 1025 |
| 非零梯度元素数 | 589824 | 33 |
| 全部有限 | 是 | 是 |
| clip 前整体梯度范数 | 0.0271881353110075 | 0.031824417412281036 |
| optimizer step | 1 | 1 |

actor 真正改变 589824 个参数元素。保存的 actor loss 总和为 `-0.05000000004656613`，critic loss 总和为 `0.005000000353902578`。3134 个被计量 token 中 PPO ratio 超出区间数与 clipped-objective token 数均为 0；这是本次同策略、首个 epoch 的测量，不能推出裁剪机制在其他窗口无作用。

具体身份：

- 更新前 adapter SHA：`4e82a9439a4ea533a327313426684874b1eec32eb45433fd24f8e7d9ce2241fa`。
- 更新后及最终 adapter SHA：`898326d64622c05c92c3823a913c911919cfdb56d8ac0b2bf5e807fb29d461fb`。
- base manifest SHA 仍为 `030031b27513e399360f26a8db31746e719bb15a3d2f4d68874c1dba3ccc60a6`；inference profile SHA 仍为 `c640cad53145a1df8ee7cc81932be81d931d58c1182aa872530460a030a694a6`。
- 保存检查点实际 actor tensor hash 与上述更新后 SHA 相等；policy_revision=1，actor/critic steps=1/1，两 optimizer state 条目数为 32/4，window 仍是原 `v022-b1-train`。
- 检查点完整 state tensor digest 为 `5a801886062d3e65b8a4c52acf1501fc3064f631f3a9df998f17d3a8aac21fdb`，运行时保存/重载精确一致的守卫通过，CPU 独立读取再核对也一致。

组别梯度抓取上限仍为 0，不能从这份整体梯度给各角色作因果贡献分解。原更新后固定上下文概率诊断上限亦为 0：`post_update_additional_actor_forwards=0`，不声称测过更新前后完整分布变化。

## 5. 更新后两次实际工作

两例仍采用桥接协议每个活跃角色 4 次实际模型决策的短片段预算。每例记录的 10 个机会包含最后两个无生成的预算边界事件；实际模型生成均为 8 次，不能把停止事件算成新增调用。该预算不是 W1 的完整工作预算。

| post | 保留 case | 实际角色 | 模型调用 | 输入/输出 token | 奖励 | 完整职责 |
|---|---|---|---:|---:|---:|---|
| 0 | `retail-v22-9d2fdf12fe8643d3` | provider、implementer | 8 | 41741 / 1180 | 0.2 | 未完成 |
| 1 | `retail-v22-4f858cb764fb94d3` | implementer、reviewer | 8 | 67964 / 1265 | 0 | 未完成 |

post-0 中，provider 首次未读依据即 handoff 被拒，随后实际 read_version，再 handoff 成功；implementer 有请求信息以及读取未共享/未知对象的拒绝记录。最终“适用依据已交付”成立，依据用于 build 与正确固定交付均不成立。这里描述原动作顺序，不把后续动作变化归因于一次参数更新。

post-1 中，两角色各执行 inspect_submission 后的实际版本读取；在预算内没有完成独立最终审查、正确最终产品或有效审查修复链。已有准备状态不计作当前角色工作。两例均以 `finite_task_deadline` 闭合，未完整完成业务，但 eligible=true、independent_assessability=known，失败没有排除出结果。

16 次实际调用均为本地 resident、状态 200、格式解析失败 0；输入总计 109705 token，输出总计 2445 token。保存响应的 output IDs/raw IDs、behavior/raw probabilities 对应一致，所有响应与 post 声明均绑定更新后 `online-actor-1:898326d6…`，不是只更新标签而继续记录旧身份。

两次评价前后 actor、critic、optimizer、step、policy revision 的 fingerprint 相同，`learning_unchanged=true`；各自 Torch CPU/CUDA RNG 回到评价前状态，`rng_restored_exactly=true`。最终仍为 1/1 step，post 没有额外训练。没有同 case 同初始化的更新前配对对照，因此 0.2/0 不能当作收益估计，也不能与原 train 的同数值直接相减解释。

## 6. 时间、资源与成本

R1 使用物理 GPU2，模型 PID291634、observer PID291554。北京时间 21:10:22.494094 开始，21:37:52.804876 结束，退出码 0，无资源停止原因。

- R1 单独成本：**1650.310781955719 设备秒**，27.505179699262 分钟，0.4584196616543664 GPUh，覆盖加载、精确恢复、完整概率复算/反向/step、检查点、两次 post 和退出。
- 此前各线（含失败 B1）已计 4117.379427433014 设备秒，累计为 **5767.690209388733 设备秒 / 1.602136169274648 GPUh**，低于本轮 7200 秒总限。
- R1 冻结总限 2400 秒、update task 2100 秒、其他 task 900 秒，各保留 30 秒停止余量；实际 update heartbeat 到 post-0 heartbeat 间隔约 1478.28 秒，含更新及随后的检查点等边界工作，不能冒称纯 GPU backward 时间。
- 冻结进程采样上限为 own GPU 73728 MiB、host RSS 64 GiB，v0.22 运行根产物上限 8 GiB。本记录按实际冻结监督器写这些值，不沿用更早版本的 5 GiB 上限。

| 观测 | 数值 | 范围 |
|---|---:|---|
| 资源样本数 | 715 | 真正 JSONL；查询失败 0 |
| own NVML 显存峰 | 31486 MiB | 定期进程采样，不保证捕捉瞬时极值 |
| own RSS 采样峰 | 14271066112 bytes | R1 进程 |
| update report RSS high-water | 18818482176 bytes | 包括此前加载阶段的进程历史峰 |
| post 生成 Torch allocated 最大值 | 23644782592 bytes | 生成阶段，不代表整个更新反向峰 |
| v0.22 运行根产物采样最大值 | 765967734 bytes | 监督器全根口径，不只是 R1 |
| R1 目录闭合后大小 | 87770416 bytes | 派生时文件统计 |

715 次样本未观察到 GPU2 上其他计算 PID。这个结论限定在采样点，不证明采样间隔内绝对独占，也不抹掉原 B1 曾经观测到同卡竞争的事实。GPU 设备秒是单卡占用期间的时间账本，不是 kernel active time；本 CPU 只读报告生成不计作 GPU 实验。

## 7. 原件与可核查性

[同名 JSON](online-bridge-v022-restoration-results.json) 保存完整原件路径、SHA、24 项概率检查标量、两个 post 的实际动作摘要/评价守卫及 16 个 resident 调用引用。大输入、概率数组和世界材料保留原处，不在文档重复展开。以下为核心原件指纹：

| 原件 | SHA256 |
|---|---|
| `supervisor` | `2a2cc088c14e2f4d7b81436e8b734e1c610a9d00acb0d04a79b8822168b51063` |
| `resources` | `3f4aa34e5043b502b840519f4e75993370d39254c31d54bc4fe13b921af758ca` |
| `report.json` | `407b317cf299451804cbd2492f975e09ff0cc2c621a245583cca77a58f4780ce` |
| `update/report.json` | `7a634f5120c6402c20788af58c84866472a720ed8ffbd5d68851520f502b7b44` |
| `update/admission.json` | `8e587278fc96f9462eb54690ac12784cee750acf97debc4a693fa8e7e3349eac` |
| `update/behavior-probability-check.json` | `cce4202b19f95f02c28e5b64638626734f48a38e7b718a88ebe0687c24c9d6a8` |
| `update/gradient-probability-check.json` | `cce4202b19f95f02c28e5b64638626734f48a38e7b718a88ebe0687c24c9d6a8` |
| `update/gradients-before-clip.pt` | `214168e956bd5544820296d1c3064c6571364fbd07e02510667c9d042c94c78d` |
| `checkpoint/shared-state.pt` | `c3099dfe0be4d56b68b77b139bcbf2625f8a0d577c91c10b22a8bd3c6cfadace` |
| `source/src/proworksim/online_training.py` | `a4ebf812ca28154002cc1d798b035ec41e3879f8b57f5f56797ea5de022f41c8` |
| `source/src/proworksim/functional_qwen_v022.py` | `8c759c43108c3caef3fbcff8c906720471e0f3e9a957d23e65b5ae4d1e0699c8` |

本次只完成已声明的 R1 恢复与两个 post，未追加训练窗口、调整数值容差、换候选、补样或启动下一轮。原 B1 失败、R1 新增成本和未完成的工作结果均保留。
