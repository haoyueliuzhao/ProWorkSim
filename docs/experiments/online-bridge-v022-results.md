# v0.22 原 B1 桥接结果：真实训练投影与概率准入成立，整窗更新因时限未完成

日期：2026-09-27。本文专门记录原 `runs/domain-v022/B1`，不覆盖或合并后续 R1。原 B1 文件保持原样；本报告及同名 JSON 来自只读提取，未重跑模型、评分或反向。另对 `shared-before.pt` 做了明确限定的 CPU 安全快照读取。

**原 B1 完成了四个新工作片段、六份成员局部投影和 24 次真实行为的概率准入；随后在 24 个决策的梯度积累中完成 12 个，触发冻结的单任务时间门，被监督以 SIGTERM 停止。actor、critic 均未进入优化器 step，两段后续 development 未开始。**

本窗有真实非零奖励与优势，因此不能把这次零步写成“无学习信号”。也不能把未完成的更新称为“测得零学习收益”。它是一次有可信训练材料与数值准入、但未完成整窗更新的资源停止结果。

## 1. 原实验合同与终态

计划为四个新训练片段（实现、复核、联合 A、联合 B），至多一次共享 actor/critic 更新，再执行两个新的 development 联合片段。每个活跃角色最多四次模型决策，使用 `native_v22_compact_work`，与 W1 的完整 episode 行动预算不同。预算检查所产生的停止事件不另计真实生成。

执行源 commit：`04b9a1725e3eed09110860cec5bd91d59272173d`；source tree SHA256：`832c21e072368b0cca074431cd82dbf646299babf4754590174bcb89f27e0832`。监督记录启动源 clean。实际 learner 调用已通过 N1 的同一 `functional-qwen-state-v0.22` 实现，模块字节受准入引用约束；原 PPO、terminal MC、成员/窗口分母、原概率门和一个共享优化器不变。

物理 GPU2，模型 PID `225715`、监督 PID `225602`。北京时间开始 `2026-09-27 20:38:04.837653`，结束 `20:56:17.804425`。

| 记录层 | 实际终态 |
|---|---|
| 监督 `state.json` | `stopped`，exit `-15`，`stop_reason=task_time_budget` |
| 子 `actual/report.json` | 保留最后写入的 `updating` |
| `actual/update/report.json` | `status=preparing`、`stage=backward`，完成 12/24 个决策 |
| actor / critic optimizer steps | 0 / 0 |
| 后续 development | 0/2 开始；没有分数 |

子进程的 `updating` 是被终止前的持久状态，不表示它仍在运行。独立只读检查时两个 PID 均已消失。没有将原子报告改写为完成，也没有补写未发生的末态身份重哈希或 `source_after`。

## 2. 四个真实工作片段与训练投影

四个片段全部正常闭合，`record_validity=True`、业务回报已知、完整可训练实际成员证据均成立。它们均未完成完整职责。

| slot | case ID | 活跃成员及本人输出 token | 真实生成数 | 回报 | 已存业务依据 |
|---|---|---|---:|---:|---|
| train-0 | `retail-v22-71afefb98d91a236` | implementer：560 | 4 | 0.0 | 未取得正确构建或正确固定交付 |
| train-1 | `retail-v22-0cc431cce6d1255b` | reviewer：545 | 4 | 0.0 | 未形成有据正式复核判断 |
| train-2 | `retail-v22-be48487045bb921a` | provider：521；implementer：630 | 8 | 0.2 | `applicable_basis_delivered` 达成；用于构建与正确固定交付两项未达成 |
| train-3 | `retail-v22-97e6223f6c957930` | implementer：392；reviewer：486 | 8 | 0.0 | 最终独立复核、正确固定产品与有效复核修复路径未达成 |

A 的 0.2 具有该片段明确的“适用依据实际送达”含义，不能误报为已经正确使用并构建，或与其他版本同数值分数混作相同语义。准备阶段不计目标模型功劳。

实际 resident ledger 共 24 条 status 200，0 个 protocol parse error，0 次网络模型 API 调用。生成 token 账为输入 **171,735**、输出 **3,134**、合计 **174,869**；输入包含重复呈现的历史，不能当作独立信息量。没有把 N1、旧 E/W1 或 CPU 见证转为本窗示范数据。

对六份真实 `MemberView` 中的 24 个决策做了只读交叉核对：

- `origin=target_model`，成员轨迹及语义轨迹完整；每成员四次真实完成。
- 每个 decision 的 input IDs、output IDs 与关联 resident 原调用一致。
- 行为概率与原 `raw_behavior_logprobs` 逐项一致，actor identity 与本窗初态相同。
- `loss_mask` 精确为原输入全 0、本人原输出全 1。工具结果、同事消息及 prompt 没有被添加为生成目标。

全部 24 项关联检查通过，引用保存于派生 JSON；没有重新 tokenization 或重跑模型确认这些值。

## 3. 原 PPO 准入、分母与真实信号

`update/admission.json` 保留全部 4 个 scheduled slot、24 个决策和 3,134 个本人输出目标。组成条件为 `Q=B`、权重均为 1，没有 ID‑VTDO 重配置或根据成绩删除困难片段。

成员分母按原规则固定：

\[
\text{actor denominator}=4\times\text{该slot活跃成员数}\times\text{该成员全部输出token数}.
\]

| 成员块 | actor denominator | critic denominator |
|---|---:|---:|
| train-0 implementer | 2240 | 16 |
| train-1 reviewer | 2180 | 16 |
| train-2 provider | 4168 | 32 |
| train-2 implementer | 5040 | 32 |
| train-3 implementer | 3136 | 32 |
| train-3 reviewer | 3888 | 32 |

24/24 更新前行为概率检查通过，**每个 call 的最大与平均 logprob 差都为 0.0**，3,134 个目标全部与原行为概率逐项一致。仍是已选 token 的检查，没有全词表 KL 结论。

预更新 critic 对 24 个决策的值均为 0；8 个联合 A 决策的 terminal-MC 回报/优势为 0.2，其余 16 个为 0。故持久报告中 `zero_signal_window=False`、`actor_update_enabled=True`。这是真实部分成果提供的非零信号，不是用随机 critic 或人工奖励制造更新。

后续按原顺序积累梯度，最后持久计数为 **12/24**：实现 4 个、复核 4 个、A-provider 4 个完成；A-implementer 与 B 的剩余 12 个没有完整完成的持久记录。该计数指决策的 actor/critic backward 流程完成，不是优化器步数，也不能排除停止前下一决策已进行部分计算。

冻结控制流要求每个已完成决策先通过梯度前向概率检查。因此前 12 项的“检查通过”可由其完成顺序支持；但全窗 `gradient-probability-check.json` 尚未写出，不能将所有 24 项 grad-enabled 检查宣称完成，也不能补录未持久化的逐项 max/mean 值。

`gradient_norms`、`changed_actor_elements`、完整梯度汇总和最终更新结果均未形成。更新前概率门通过不等于整窗梯度积累与 step 已完成。

## 4. 未发生优化器 step 的证据与可恢复边界

对冻结的 `runs/frozen-v022-b1/src/proworksim/online_training.py` 只读核对，SHA256 为：

`a4ebf812ca28154002cc1d798b035ec41e3879f8b57f5f56797ea5de022f41c8`。

控制流是：每条决策完成后保存进度；全部 24 条完成后，依次写出梯度概率检查、losses、signal diagnostics 和 `gradients-before-clip.pt`，随后才能计算/裁剪总梯度并调用 optimizer step。

以下必经文件在原 B1 中均不存在：

- `update/gradient-probability-check.json`
- `update/losses.json`
- `update/signal-diagnostics.json`
- `update/gradients-before-clip.pt`

最后逐行持久进度停在 12/24、optimizer steps 为 0；监督已终止两个进程。**在原归档未被外部删除或改写的前提下，控制流和文件证据支持尚未进入任何 optimizer step。**这不依赖把初始 hash 冒充退出后的 tensor hash。

更新前快照 `actual/update/shared-before.pt` 已单独使用 `CUDA_VISIBLE_DEVICES=''`、`torch.load(weights_only=True, map_location='cpu')` 安全读取，没有构造模型或分配 CUDA tensor：

| 快照检查 | 实际值 |
|---|---|
| actor / critic steps、policy revision | 0 / 0 / 0 |
| last window | `v022-b1-train` |
| used window IDs | `['v022-b1-train']` |
| actor tensor | 32 个 FP32，共 1,114,112 元素，全部加载在 CPU |
| actor / critic optimizer state entries | 0 / 0 |
| actor / critic learning rate | `1e-5` / `0.001` |
| critic 最终层 | 全零；nonzero-reward-history 标记 false |
| 实际 actor tensor hash | 与原采样、初态及更新前 identity 一致 |

实际快照 actor hash 为 `4e82a9439a4ea533a327313426684874b1eec32eb45433fd24f8e7d9ce2241fa`；critic 与两优化器快照 hash 一并写入派生 JSON。快照文件 4,488,672 bytes，SHA256：

`10f4238d5016174a4b4c5f2106e337d58f355f3b275b7080b270c986ea1335cb`。

这些是**更新前快照**的实测 hash。没有退出后活模型 tensor 重哈希，没有已刷新的参数身份，没有最终 RNG 守卫记录。`checkpoint`、`post-progress.json`、`post-0`、`post-1` 均不存在。

该证据可供单独授权的 R1 从完整当前 θ0 状态与原 24 条 on-policy 行为重算，并重新检查全部概率与完整窗口；它不是 R1 的执行结果，也不把原 B1 改成成功。任何恢复的源码、预算、成本与两段 post 都须另列；不得把本次前 12 条部分梯度当成已提交更新或在恢复中额外累积一次 step。

## 5. 时间、资源与竞争

监督实际分配时间 **1092.9667720794678 秒**，即 **18.21611286799113 GPU 分钟 / 0.3036018811331855 GPU 小时**。从 `B1-single-shared-update` 心跳到监督结束为 **872.0080351829529 秒**，对应原 900 秒单任务额度扣除 30 秒停止预留后的 870 秒触发阈值，加监督与退出延迟。

停止原因明确为时间门，不是 OOM、已记录概率失配或已经证实的非有限总梯度。全窗末态梯度资格未完成，不能反向推断其一定有限或一定失败。

原 updater 的 `actor_enabled` 是窗口级：一旦本窗 A 提供非零优势，它也对零优势决策执行 actor 前向/反向。这是本次真实消耗的一部分；数学上的零贡献没有被执行器自动跳过。该事实可以解释成本结构，不能用来改写本次预算或假定某个优化版本已经运行。

| 资源指标 | 观测值 | 口径 |
|---|---:|---|
| 监督样本 | 479 | 查询失败 0 |
| 本模型 NVML 峰 | 31404 MiB | 离散进程占用，包含保留/上下文等 |
| 本线 RSS 采样峰 | 15797063680 bytes | B1 进程 |
| 所有实验线 RSS 采样峰 | 17566507008 bytes | 包含并行 W1，不全部归给 B1 |
| 生成期 Torch allocated 峰 | 23276963328 bytes | 仅真实生成期，不是完整更新峰 |
| 更新报告的 RSS high-water | 18794225664 bytes | 进程历史高水位，含加载等阶段 |
| B1 目录当前体积 | 140424589 bytes | 本目录全部原产物，未代表整轮总量 |

启动时 GPU2 通过空闲准入，但不能称运行全程独占：**479 个样本中有 1 个在 epoch `1790513577.5058072` 观察到同卡其他项目 PID `253714`（memalpha），占 `33694 MiB`。**这条原始竞争记录已保留。不能据一条观测证明超时由该竞争造成，也不能因大部分样本无其他 PID 而删除它。

本成本只覆盖原 B1，从加载、四片段生成、概率复算到部分反向和停止；不包含 N1、W1、X1、R1或未来学习。`resources.jsonl` 是真正的 JSONL：479 个非空物理行各自包含一个完整 JSON 对象。本次提取使用的 `JSONDecoder.raw_decode` 顺序解析同样适用于该格式；没有重写或压平原件。此前“多行对象流”的描述已按原件勘误，不改变样本数、SHA 或资源统计。

## 6. 原件索引与结论限制

| 原件 | SHA256 |
|---|---|
| `runs/domain-v022/B1/state.json` | `dd682ae3cf742d885c0d9c3361f5c6d8ef16feed1a8b58273c0434c529701cfd` |
| `runs/domain-v022/B1/resources.jsonl` | `cad2260ca82ef12b7ebcdfb6bac2ecfd947d8952927b0521e98e24476ccd8add` |
| `runs/domain-v022/B1/actual/report.json` | `7671eb42706f053faec4de97249835249544b792ea56e9210c532359636fd7e5` |
| `runs/domain-v022/B1/actual/update/report.json` | `da4c376783c7f61a619e4e7ae20cb0dda2d4bd0190af863770afbcb296a55e26` |
| `runs/domain-v022/B1/actual/update/admission.json` | `8e587278fc96f9462eb54690ac12784cee750acf97debc4a693fa8e7e3349eac` |
| `runs/domain-v022/B1/actual/update/behavior-probability-check.json` | `cce4202b19f95f02c28e5b64638626734f48a38e7b718a88ebe0687c24c9d6a8` |
| `runs/domain-v022/B1/actual/update/shared-before.pt` | `10f4238d5016174a4b4c5f2106e337d58f355f3b275b7080b270c986ea1335cb` |

[同名派生 JSON](online-bridge-v022-results.json)另保存四套 TeamRollout/projection/episode manifest/experience 的 SHA，以及 24 个实际模型调用的逐项关联引用。它保留原子报告状态、明确未知项与恢复证据范围，不替代原件。

本次可以保留的结论是：新工作情境的真实 token 投影、固定分母、原行为概率和函数式 learner 的窗口入口已经接通，并出现了真实非零优势。没有完成的部分是：整窗 actor/critic 梯度积累、优化器步进、参数身份刷新和两段后续工作。因此本文件不报告学习增益、参数不变的效果比较或 ID‑VTDO 增量。
