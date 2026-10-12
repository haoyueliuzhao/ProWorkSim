# v049 训练方法、实际更新与完整状态证据

日期：2026-10-12。本文整合已保存的 v049/r1 证据，覆盖原八条采集、记录修订、真实 O1、完整 B 更新与无 I 方向的结论。开发收口、r2/r2g 宿主修订及本轮 GPU 范围扩大见[最终报告](software-learning-v049-final.md)，本文集中记录训练方法。本文没有重跑生成、tokenizer、测试、业务验收、导出、概率核对或张量比较，也没有读取 `.pt`；历史报告与其中的 unknown、false、待定字段保持原样。

原八槽已全部完成，正式 R_joint/Q_joint 均为 1；全部 16 条成员轨迹、206 次真实回包、51,328 个本人输出目标进入 B。B 实际完成原 H=1 全窗口更新，actor/critic 各一步，完整步数由 3/3 到 4/4。四个 root/member 支持块均只有一个可靠类别，I 组成自由度为 0，因此 Q± 未执行。这些是材料与更新事实，不能替代开发收益或因果 Contribution 证据。

## 1. 冻结任务、O1 与模型输入

原训练根是已披露的两个人工合同 LA（UTC 转换后的日期与边界）和 LB（inclusive between 规则边界与错误路径），各四个新重复。LA 种子为 202610120491—494，先手 member_001；LB 为 202610120495—498，先手 member_002。它们是八条新策略经历，不是八个独立业务题，也没有把 v047/v048 旧开发轨迹拼入训练。

两名稳定成员为 member_001/member_002，初始任务表为空，公开合同和事实相同，拥有独立工作副本与同等权能。任务、责任、交流、集中实现与采用都由模型行动产生，未规定最低消息数、多人编辑数或协作成功门。`staff_done` 仅结束当前工作并休眠：成员身份、责任、SDK 会话、历史与原计量保留。只有较晚真实可达的伙伴消息或已提交公共事件可以唤醒；context、成员 fixed meter 或团队预算已使会话不可运行时不恢复。不存在新增成员、替换成员或永久退休动作。

真实原件中可核对的 O1 行为包括：原五槽有三次任务创建与三次认领，均未形成已提交 work_message；r1 余三槽没有新任务或消息，但有 12 次 staff_done、6 次随后真实唤醒，来源恰为三次伙伴 patch_fixed 与三次伙伴 submit，唤醒后仍在本人原会话实际生成。三槽终态均保留原两名 live 身份，各自休眠；没有出生、永久退休或预算重置。任务表事件、实际唤醒和代码采用应分别记录，不能用其中一项替代其他项。

全程沿用唯一 Γ1 五字段严格同值引用、总容量 18,432、输出预约 2,048、测试正文页长 3,072 Unicode 字符及原数值路径。每槽上限 128 决定/128 attempt、500,000 token、32 次成员测试，90 分钟软截止与 100 分钟硬截止。训练使用实际模型收到的 Γ1 native input IDs 和本人原始 output IDs；归档 original/selected、实际响应、账单和来源绑定共同证明输入。没有把展开的原请求替换成实际条件上下文，没有按文本重新分词或截去真实生成后缀。

原输入 ID 的当前目标 ownership mask 全为 0，本人实际输出 ID 全为 1。伙伴内容、历史内容与工具反馈可以成为上下文，但不因此增加本人的输出目标。来源可信的业务拒绝或格式错误实际输出仍保留；执行前无生成拒绝没有伪造 output、mask 或训练目标。

证据：[原协议](/data1/zhuxinrui/projects/ProWorkSim/docs/experiments/software-learning-v049-protocol.md)、[O1 与测量控制](/data1/zhuxinrui/projects/ProWorkSim/docs/experiments/software-learning-v049-runtime-controls.md)、`software-learning-v049-r1-evidence/original-five-work-facts-r1.*`、`r1-new-collection-behavior.*`。证据目录均位于 `docs/experiments/`。

## 2. 原五槽停止与 r1 记录接缝修复

原执行源码为 `e2221fc5ad5d3cc9e32ba4c785f7b29e31c2706f`。原五槽在物理 GPU 3/4 完成，保留 122 次宿主决定、119 次真实回包、1,617,987 token 与 14 次成员测试；五槽正式 R 均为 1。发现记录归因未决后，原监督器写入停止凭据，并允许已经在途的 LA r3 自然闭合。原 `closed_with_unknowns` 是监督与记录状态，不表示五个已闭业务结果未知。原 S0 保存仍为 3/3，此阶段没有真实新反向或参数更新。

旧 reader 的共享预约停止判定要求终态预算包装中的 `world_instance_id` 等于 manifest 身份；本轮沿用的预算包装缺少该字段，但同源 manifest、世界 start/end 档案、原 ledger、准备请求与响应都保存了相应绑定。LA r2 末端一次、LB r1 两成员末端各一次均为充分绑定的执行前共享预算拒绝。旧完整记录门因这个字段接缝把 LA r2 的 38 条与 LB r1 的 34 条真实回包整槽排除，原 119 条只剩 47 条入场。

r1 仅替换这一个世界身份来源判定：在包装缺字段时，从同一已闭 episode 的 manifest/start/end/slot/终态/边界 ledger 建立替代证据；所有原请求、actor/window/hash、额度算术、无 attempt、无费用和无副作用条件继续成立。已有身份字段错误、账单改变、档案缺失或真实在途不获准。已知合法关闭后新增的 `deadline_receipt` 宿主注释仅在与原 deadline 文件一致时获准，其他终态字段仍逐值绑定。

修订没有覆盖原 manifest、event、训练导出或 unknown。三个无需修订槽的新旧 entry 完全同值；旧 47 条准入 decision 逐字段不变，另外恢复原有 72 条回包及其真实目标，共 119 条、31,747 输出 token。新 reader、TeamValidity、Mapper、support 与 prepare_window 以隔离绑定贯通；原 Mapper 规格哈希、本人 mask 语义、原 8×2 分母及 H=1 数值 code object 保持不变。

原修订留下 27 项不同 CPU 控制、累计 28 次执行（27 通过、1 次早期 fixture 缺项失败）以及 Ruff 回执；其中包含四项消费者控制。原失败与旧判定不抹去，不把它们并入一次不存在的总验证。原 961 个来源文件同字节凭据与原五槽只读重物化回执已保存。本文仅复用这些回执，不重做原件核验。

r1 随后只执行原未开 LA r4、LB r3/r4，保持原 seed、先手、S0 与逻辑窗口；旧五槽没有重采，旧未用额度不转移。正式材料由唯一 registry 的旧五加新三按原顺序合并，八个 slot 与八个实际 episode 目录各不重复。重物化与读取成本不是新增模型生成费用。

证据：`software-learning-v049-record-binding-r1-protocol.md`、`software-learning-v049-record-binding-r1-consumers.md`、对应 CPU/消费者 JSON，以及 `software-learning-v049-r1-evidence/original-five-work-facts-r1.*`。

## 3. 完整八槽与基础测度

| 原槽 | 来源 | 正式 R/Q | 真实回包 | 完整 token | 001：回包/输出 | 002：回包/输出 | 最终 Mapper |
|---|---|---:|---:|---:|---:|---:|---|
| LA r1 | 原五 | 1/1 | 14 | 182,504 | 7/1,856 | 7/1,795 | local |
| LA r2 | 原五 | 1/1 | 38 | 493,282 | 9/2,742 | 29/7,231 | local |
| LA r3 | 原五 | 1/1 | 15 | 196,209 | 8/2,196 | 7/1,510 | local |
| LA r4 | r1 余三 | 1/1 | 32 | 448,905 | 14/3,067 | 18/5,057 | peer |
| LB r1 | 原五 | 1/1 | 34 | 495,438 | 17/5,037 | 17/4,218 | local |
| LB r2 | 原五 | 1/1 | 18 | 250,554 | 9/2,750 | 9/2,412 | local |
| LB r3 | r1 余三 | 1/1 | 20 | 270,431 | 11/1,811 | 9/2,201 | peer |
| LB r4 | r1 余三 | 1/1 | 35 | 495,265 | 16/3,447 | 19/3,998 | local |
| 合计 | 唯一八槽 | 8/8 已知成功 | 206 | 2,832,588 | 91/22,906 | 115/28,422 | local 6、peer 2 |

总宿主决定为 209，真实回包为 206，三次执行前共享拒绝分列；输入 2,781,260，输出 51,328，合 2,832,588 token，26 次成员测试。原五仅计一次：119 回包/1,617,987 token/14 测试；r1 余三为 87/1,214,601/12。最长实际训练序列为 17,384，低于冻结总容量 18,432。

八个联合 episode 对应 16 条成员轨迹，不能称为 16 个独立 episode。所有基础 actor mask 为 true；全部 206 条真实回包和 51,328 个本人输出目标进入 B，没有基础入场排除。可信失败与 unmapped 原本也按协议保留单位基础材料，但本次八槽实际恰好全部 R=1；该政策事实不应改写成“本次观察到了失败样本”。

固定全局成员质量因子为 8×2=16。对槽 s、成员 m，令 T_sm 为该成员全部本人输出数，K_sm 为入场的真实生成决定数：actor 分母为 16T_sm，critic 分母为 16K_sm。M=4 是 root/member 支持块的重复数，不能替代损失分母 16。51,328 是全部输出目标总数，并非将所有 token 均权后只除一次 51,328；实现先在每条成员轨迹内平均，再给予每条轨迹 1/16 的基础质量。

| 原槽/成员 | K | T | actor 分母 16T | critic 分母 16K |
|---|---:|---:|---:|---:|
| LA r1/001 | 7 | 1,856 | 29,696 | 112 |
| LA r1/002 | 7 | 1,795 | 28,720 | 112 |
| LA r2/001 | 9 | 2,742 | 43,872 | 144 |
| LA r2/002 | 29 | 7,231 | 115,696 | 464 |
| LA r3/001 | 8 | 2,196 | 35,136 | 128 |
| LA r3/002 | 7 | 1,510 | 24,160 | 112 |
| LA r4/001 | 14 | 3,067 | 49,072 | 224 |
| LA r4/002 | 18 | 5,057 | 80,912 | 288 |
| LB r1/001 | 17 | 5,037 | 80,592 | 272 |
| LB r1/002 | 17 | 4,218 | 67,488 | 272 |
| LB r2/001 | 9 | 2,750 | 44,000 | 144 |
| LB r2/002 | 9 | 2,412 | 38,592 | 144 |
| LB r3/001 | 11 | 1,811 | 28,976 | 176 |
| LB r3/002 | 9 | 2,201 | 35,216 | 144 |
| LB r4/001 | 16 | 3,447 | 55,152 | 256 |
| LB r4/002 | 19 | 3,998 | 63,968 | 304 |

曾有只读摘要直接比较 `all_decisions` 与 `actual_completions`，在 LA r2/002（30 对 29）、LB r1/001 和 /002（各 18 对 17）返回 false；这是宿主决定与真实回包口径不同的分析比较误报，原 false 数值保留。B 实际 admission 的 `decisions` 共 206，critic K 分别取 29、17、17；三次无生成拒绝未进入分母，也没有因此修改原材料或学习器。

证据：`training-eight-work-support.*`、`h1-objective-and-cost-method.*`、`final-support-direction.json` 的 `decision_accounting`。

## 4. Mapper、采用事实与可靠支持

冻结类别为 `local_lineage_delivery`（local）和 `evidenced_peer_product_delivery`（peer），描述最后原固定成果的可追溯交付路线，再向实际有本人输出的两成员投射。它不是代码作者筛选、奖励拆分、因果贡献或已测正 Contribution。

LA r4 已证 001 的非同值 `event_time.py` 固定成果，经 002 真正采用、002 在同树测试、反馈实际呈现及最终固定交付。001 在采用前已提交自己的固定成果，故不能断言采用是回合成功的必要原因。LB r3 已证 002 的非同值 `rules.py` 固定成果，经 001 采用、本人同树测试与最终固定交付；001 没有本人生产编辑，但其 11 回包/1,811 输出仍全部入场。两条均有实际 input/receipt/版本来源证据，未将展开输入替代 native input，也未重验早期固定提交。

LB r4 确有 002 采用 001 固定成果，但采用前后文件表已同值。更关键的是最后被评估的交付为 001 自己的本地谱系，`included_patch_ids=[]`；002 的中间采用不在该最终链上。因此其最终 local 类别不否认真实采用动作或中间交付。

| root/member | 原 M/基础轨迹 | 门前 local/peer | 可靠类别/样本 | v | b(local) | B 决定 | I 自由度 | G-raw 类内自由度 |
|---|---:|---:|---|---:|---:|---:|---:|---:|
| LA/001 | 4/4 | 3/1 | local/3 | .75 | 1 | 38 | 0 | 2 |
| LA/002 | 4/4 | 3/1 | local/3 | .75 | 1 | 61 | 0 | 2 |
| LB/001 | 4/4 | 3/1 | local/3 | .75 | 1 | 53 | 0 | 2 |
| LB/002 | 4/4 | 3/1 | local/3 | .75 | 1 | 54 | 0 | 2 |

事前门要求同一 root/member 块的每类至少两条。每块 peer 仅一条，因此是有证据但 `below_frozen_class_support`，不是 unmapped。不能跨 LA/LB 合并 peer，也不能把同一联合回合向两成员的投射当成同块两次独立重复。

v=.75 描述可靠组成支持占原四重复的质量，不是训练目标保留率。LA r4、LB r3 的四条成员轨迹共 52 个决定、12,136 输出目标仍全部以基础权重 1 入场；B 全 16 条轨迹权重均 1。未将基础损失乘 .75，未删除 peer 或按 12 条可靠轨迹重归一，也没有把残余质量转移给 local。

## 5. 原 H=1 数值路径及实际优势

S0 恢复原完整 common 3/3，仅将原 member_a/member_b/software_inactive critic 坐标显式绑定为 member_001/member_002/software_inactive；容量元数据复用既有 18,432 绑定。迁移未改变数值状态，随后冻结 actor、critic、两个 Adam、RNG、recipe、步数与历史窗口。采集期间参数不动，B 从该同一完整 S0 更新。

原 `SharedActor.update_window` 的 code object、closure、defaults 相同。隔离扩展只绑定 v049 组成验证与可选梯度观察器，r1 再绑定使用新 record reader 的原 prepare_window；原模块 globals 与 owner method 未被改写。PPO、critic 目标、原累积顺序、梯度裁剪及 optimizer 语句保持原数值路径。冻结训练源码为 `fa392e24a7c656c83ccd992d4194f1ded700b892`，tree SHA 为 `91825baf3cdf24d421017b1c2cd43a6def5aff4365622c36e165451c9daee96d`。

actor 是共享 q/v LoRA（r8、alpha16、dropout0），critic 为原 30→32 tanh→1；第三 inactive 坐标没有伪造动作。critic 特征只用决定开始前实际可见公共结构、计数和成员编码，不读取未来状态或验收真值。原配方 epochs=1、无 minibatch/中途成员级 optimizer step，按原 admitted 决定顺序累积；actor/critic AdamW 学习率分别 1e-5/1e-3，weight_decay=0，保留已有动量与 step。两套累积梯度分别按 L2 阈值 1.0 裁剪；PPO clip=.2，entropy/KL 系数为 0。

定义每条原输出 token 的概率比 r 为当前原生 logprob 与行为 logprob 之差的指数，冻结温度 .7、top_p=1、top_k=0。B 的 w_sm=1：

\[
L_\pi=-\sum_{s,m}\frac{w_{sm}}{16T_{sm}}\sum_{j,t}\min\{r_{smjt}A_{smj},\operatorname{clip}(r_{smjt},.8,1.2)A_{smj}\}.
\]

概率比 r 与可选组成权重 w 是不同量。该目标是成员输出平均的 surrogate，不能称作未归一化整回合策略梯度的严格无偏等价。

\[
L_{V,\mathrm{backprop}}=.5\sum_{s,m}\frac{1}{16K_{sm}}\sum_j\frac12(V_\phi(f_{smj})-R_s)^2.
\]

内层 1/2 是原平方误差定义，外层 .5 是 critic coefficient；`losses.json` 的 critic_loss 未包含外层系数。terminal MC、γ=1，每个决定回报为该 episode 的 R_joint；没有 GAE、bootstrap 或新增成员回报。优势是更新前冻结的 A=R_joint−V_S0，不做标准化。

原报告关于 critic 的 `zero-initialized` 字面描述继承自构造器；当前 S0 已有原三个更新，不能说 critic 当前值为零。已存 206 个旧 critic 全部非零，范围 .0110197216272—.0158443208784，决定均值 .0135794559186；本次 R 均为 1，实际冻结优势因此全部为正，范围 .984155679122—.988980278373，决定均值 .986420544081，正/零/负=206/0/0。这里的均值是决定均权描述统计，不是最终 loss 的轨迹/token 加权值，也不预测开发收益。

首轮 no_grad replay 与每次原生梯度前向各核对原始输出 logprob，门为每决定最大绝对差≤.02 且平均绝对差≤.002。两轮已存结果均 206/206 通过；已存首轮最大与平均误差均为 0。本文仅读取已存结果，不重算概率。

## 6. B 真实更新、状态与成本

| 原生计量 | started | completed |
|---|---:|---:|
| actor wrapper forward 合计 | 414 | 414 |
| gradient actor forward | 206 | 206 |
| no_grad actor forward | 208 | 208 |

208 次 no_grad 前向由 206 次首轮核对与事前固定两行后更新测量组成；后两行索引为 0、7，不按更新或开发结果挑选。actor backward 与 critic backward 各 206，206 条行级完成计量为 exact，losses 也为 206 行。wrapper forward 不是 GPU kernel 数，内部非 reentrant gradient checkpointing 重算不额外计作该包装层 forward。H=1 是一次完整窗口，不能写成一次 backward。

actor/critic 各执行一次 optimizer step，步数由 3/3 到 4/4；更新状态为 updated/complete。裁剪前范数分别为 .050031084567308426/.627356112003326，均低于阈值 1。支持 hook 返回 None，只复制实际 B 已有 leaf 梯度到 CPU，覆盖 16 个 slot/member、每组 32 个 actor 张量；没有额外 forward、backward 或 optimizer step，但复制、汇总与保存仍有实际 CPU/内存/时间成本。

独立既有 CPU 状态比较已各读取一次 S0/B `.pt`，采用 map_location=cpu、weights_only=True、CUDA_VISIBLE_DEVICES 为空；完成 worker、冻结源码、S0 绑定、文件 SHA/字节数及全 tensor tree digest 均匹配。此处复用其 JSON，不重复读取张量。

| 保存状态 | 文件 SHA-256 | 字节数 |
|---|---|---:|
| S0 | 96c11a5ad48a330d4188d87b844a49a745b5cef6f13272a45804e08fe8671dc5 | 13,440,892 |
| B | 5d0886fa54c429a95ae2d62e0895e13a9afa287873aaebeaeab574e8c7f5d2c5 | 13,440,956 |

| 成分 | 张量叶数/变化叶数 | 变化元素/总元素 | 差值 L2 | 最大绝对差 |
|---|---:|---:|---:|---:|
| actor LoRA | 32/32 | 1,114,091/1,114,112 | .00481456405144 | 1.00643810583e-5 |
| critic | 4/4 | 833/1,025 | .0174211750891 | .000957966549322 |
| actor Adam（含 step） | 96/96 | 2,228,256/2,228,256 | 5.65685647702 | 1 |
| critic Adam（含 step） | 12/12 | 1,670/2,054 | 2.00086899526 | 1 |

两个 Adam 每个参数的 step 均 3→4，actor_steps、critic_steps 与 policy_revision 也均 3→4；Adam param_groups 等非张量配置保持。Adam 合并 L2 包含 step 标量，不能称参数更新范数。actor 一阶/二阶矩各全部 1,114,112 元素变化，critic 两种矩各 833 元素变化。完整 recipe、base_identity、inference_profile、critic_has_nonzero_reward_history 与 version 不变；CPU RNG 的 5,056 个 uint8 元素及已存 CUDA RNG 的 16 个 uint8 元素均同值。这里只比较既有 CUDA RNG 张量，独立分析没有调用 CUDA API。

原 reader/reporter 的 `complete_tensor_checkpoint_comparison_executed=false`、`full_comparison=false` 以及“未加载 checkpoint 张量”的 scope 原样保留：它们正确描述原 JSON-only 报告当时做过的事。后来独立一次 CPU 比较是单独证据补充，不能回写成原 reader 已经执行比较。静态 method、pre-update、八槽 support 快照中的待定语句也保留其时间范围，由本文并列引用完成后的证据。

学习 updater interval 为 29,529.8200297 秒（8.20272778603 小时），不含此前装载/原生输入证据重放与此后 checkpoint 保存；其已含在整段驻留 worker 成本中，不能再相加。区间峰值 GPU allocated 为 37,189,235,712 字节。训练 replay 的输入/输出材料量与前向/反向计算不算新增生成 token 账单。原阶段（含唯一 S0 及五条训练）GPU worker 2,162.429730653763 秒也只在最终总成本计一次；开发/r2g 及总 worker 成本由最终主报告唯一合并，本文不将中间旧总数冒充最终总数。

既有独立 CPU 状态比较耗时 1.44209687505 秒、CPU process time 1.593435759 秒、峰值 RSS 747,016 KiB，两个 checkpoint 合读 26,881,848 字节；其新模型、GPU API、forward/backward/optimizer 工作均为 0。原学习运行成本与该审计成本分别保存。

证据：`pre-update-probability-advantages.*`、`final-support-direction.*`、`S0-B-saved-state-comparison.*`。完整状态摘要、逐参数差异和绑定见后者 JSON，本文没有重新核验。

## 7. I=0、Q 未执行与解释边界

正式 direction 在任何开发之前封存：`selected=false`、`reliable_base_material=true`、`no_admissible_I_direction_B_only`、`frozen_before_any_development=true`。按原顺序 LA/001→LA/002→LB/001→LB/002 检查，四块都因 `single_qualified_category` 排除。可靠支持只含 local，单元素概率单纯形没有非零 I 组成方向，因此保持 q=b；ρ、ε、Q± 权重与有限差分保持 null。

这不是因优势为零、基础梯度为零、optimizer 未改变参数或开发成绩而排除。实际 16 组 B 支持梯度范数全部大于 0，actor/critic 确实完成更新；非零基础梯度不能替代 I 方向的支持与可行性。原 signal 诊断总范数 .05003108470413243 与原生 report .050031084567308426 按各自口径保留，不强改成同一数值。原 JSON 未给 root/member 向量和范数，不能把各轨迹范数相加或填为 0。

每块三条可靠 local 原始轨迹仍有两个 G-raw 类内自由度；本轮没有执行 G-raw。Q± 和其各四个开发槽均属条件不适用，没有 Q 新状态、更新或结果，不应写为 Q 失败、Q=B 或已测 Contribution=0。没有为凑两类追加训练轨迹、跨 root 拼支持、换门槛或换方向。

本轮也未运行未更新 S0 的相同开发面板，因此即便 B 开发存在成功，也不能得出 B 相对训练前有提升。LA/LB 两个人工根、各四重复与最低两例支持不构成独立确认或充分统计功效。已证伙伴采用、最终成功、基础更新和因果协作/学习收益属于不同证据层次。开发中旧 DA s2 的正式 R/Q 与完整费用未知继续保留；其未知不因 r2g 完成其他原槽而填 0，也不由本方法报告消除。

## 8. 证据使用与合并注意事项

- 本文唯一基础证据目录为 `docs/experiments/software-learning-v049-r1-evidence/`，另引用冻结协议与有限 CPU 控制。各 MD 的同名 JSON 含更细的来源引用、SHA、逐行数值与原件位置；不把报告间重复引用的同一数据加成多次实验。
- 原五槽的旧 unknown、原监督器停止、三次共享拒绝和旧导出保留；r1 新解释另列，不称策略改进。首次分析跨计数口径比较 false 也保留，不当作模型或更新失败。
- 原八槽 support 与概率分析是完成前快照；最终支持、B 完整状态比较提供完成后证据。不能回写快照或把当时的 null 改成“当时已知”。
- 最终主报告需单列生成成本、训练计算、驻留 GPU worker 成本、CPU 只读审计成本，并用唯一 slot/worker 身份合并。r2/r2g 宿主接续和扩大 GPU 范围只改变新授权宿主调度，不改历史物理卡记录。
- 本文由已保存的只读方法草稿整理成最终文档，数值与证据沿用原件；最终整理未执行模型、测试、验收或状态比较，也未读取 .pt。
