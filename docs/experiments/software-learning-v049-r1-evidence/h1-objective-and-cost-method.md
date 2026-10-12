# v049 原 H=1 的目标、材料与成本口径（静态准备）

本说明只读冻结实现、S0 JSON 清单和 B 已保存的来源/材料/支持记录。它不报告 B 已经完成训练，也不根据训练终值或开发结果调整口径。动态优势、梯度、原生概率核对结果、参数/Adam/RNG变化和实际更新次数留待完成边界；本次没有读取 `.pt`、加载模型、访问 GPU、运行 forward/backward/test 或读取开发结果。

## 原件与基础材料

原 v049 八槽按原顺序唯一合并：旧阶段五槽只读保留，r1 原未开三槽接续。一次材料化绑定八个不同 episode source，条目、来源注册、原声明及配方均保留 SHA。r1 只扩展充分同源绑定的安全零生成拒绝读取，并保留原损失代码；原记录、反馈和生成账单没有重写。

已保存 token-evidence 确认 8 个联合 episode、16 条成员轨迹、206 个决定：输入 2,781,260 token，本人原始输出 51,328 token，实际输入加输出 2,832,588 token，最长实际序列 17,384（容量 18,432）。member_001 为 91 决定/22,906 输出，member_002 为 115 决定/28,422 输出；基础入场排除为空。这是材料入场证据，尚不能替代后续概率核对和反向完成证据。

所有原始 input ID 的目标 ownership mask 为 0，所有本人实际生成 output ID 为 1。完整原生输入用于条件上下文，全部实际本人输出用作目标；工具反馈、伙伴输出及历史内容即使处于上下文，也不增加当前本人的输出目标。实际 raw 输出与 trace 输出须严格相同，不按文本重新分词、不裁去生成后缀，也不把执行前零生成拒绝补成目标。格式错误或业务拒绝的真实已生成输出，在来源与完整轨迹可信时仍可入场。

## 0.75 的支持口径与全部基础目标

LA/LB × member_001/member_002 四块，各有原始 M=4、基础 actor mask 4/4。类别门前都是 local 3、peer 1；事前固定每类最少 2 条，因此支持集合仅留下 local 3，v=3/4=0.75，b(local)=1。这个 v 不是输出 token 保留率，不会将基础损失乘 0.75，也不会把基础分母重归一化为 12 条轨迹。

LA-r4 与 LB-r3 的 peer 单例仍以权重 1 留在 B，四条成员轨迹共 12,136 个本人输出目标也全部保留；总数仍是 51,328。四块类别组成自由度均为 0；每块 local 类内有 2 个 G-raw 自由度，但本轮并未执行 G-raw。方向及 Q 是否适用仍以 B 完成后封存结果为准，不能把这份门前说明写成已完成 Q 结论。

## Actor 与 critic 的实际损失

记 s 为 8 个原始槽之一，m 为每槽两个活动成员之一，j 为该成员一次原始决定，t 为该次本人输出 token。T_sm 是该槽成员全部本人输出数，K_sm 是其全部入场决定数；全局成员因子固定为 8×2=16。M=4 仅描述一个 root/member 支持块，不替代损失的全局 16。

\[
L_\pi=-\sum_{s,m}\frac{w_{sm}}{16T_{sm}}\sum_{j,t}\min\{\rho_{smjt}A_{smj},\operatorname{clip}(\rho_{smjt},0.8,1.2)A_{smj}\},
\]

其中 B 的所有 w_sm=1；ρ 是当前原生 logprob 与原始 behavior logprob 之差的指数，使用原温度 0.7 分布。PPO 概率比 ρ 与可选的轨迹组成权重 w 是两件事。分母在各原始成员轨迹内平均本人输出，再给每条成员轨迹 1/16 基础质量；未入场或 residual 质量不转给其他成员。该目标是成员输出平均的 surrogate，不能宣称与未归一化整回合策略梯度严格无偏等价。

\[
L_{V,\mathrm{backprop}}=0.5\sum_{s,m}\frac{1}{16K_{sm}}\sum_j\frac12\bigl(V_\phi(f_{smj})-R_s\bigr)^2.
\]

内层 1/2 来自原平方误差定义，外层 0.5 是 `critic_coefficient`，在 `.backward()` 前乘入。`losses.json` 的 `critic_loss` 只记录内层项及其分母，不含外层系数。critic 按成员决定平均，actor 按成员输出 token 平均，二者分母不同。逐轨迹已存分母见下表和配套 JSON。

原 `terminal_mc`、γ=1：每个决定的回报都是该联合 episode 的终止 R_joint；没有 GAE、bootstrap 或新增成员回报。可评失败 R=0 与安全行政关闭按原资格保留，行政删失时 R_token 另置 null，不替代 R_joint。当前八个训练原件终止 R_joint 都为 1，这不意味着所有优势为正。

优势 A_smj=R_s−V_phi_S0(f_smj)，在任何 optimizer step 前冻结，无优势标准化。S0 是原共同 actor/critic 各 3 步后的完整状态；构造器的零输出初始化不是“当前 S0 critic 值为零”的证据。critic 仍为原 30→32→1、tanh 网络，特征仅取决定开始前已实际观察的公共结构、计数和行动成员编码。O1 明确绑定 member_001/member_002，第三 software_inactive 坐标无伪造动作；特征不读取终止奖励、未来状态或验收真值。

## 原生概率核对与 H=1 数值路径

行为分布固定 temperature=0.7、top_p=1、top_k=0。每个决定必须同时满足原始输出序列 logprob 最大绝对差 ≤0.02、平均绝对差 ≤0.002，且序列长度与有限性有效。先在 no_grad 下完成全部原始决定的 replay 核对与冻结 critic 值；actor 启用时，再在每个原生梯度前向中核对一次，之后才做该行 backward。核对失败不能记作成功训练。

一个共享 q/v LoRA actor（r8、alpha16、dropout0）保留原非 reentrant gradient checkpointing，无生成 cache；全窗口按原决定顺序累积，epoch=1，中途无成员级或小批次 optimizer step。actor、critic 各自使用从 S0 完整恢复的 AdamW，学习率分别 1e-5、1e-3，显式 weight_decay=0；其余 Adam 超参数和已有动量留待状态对比读取，不在此猜测。

两套累积梯度分别做 L2 norm 裁剪，阈值都是 1.0；actor 还须满足原 actor_enabled 且范数正，critic 须范数正，才分别至多执行一次 optimizer step。范数非有限则阻断。entropy 与 KL 系数均为 0。H=1 描述原完整更新窗口，不保证实际一定发生 actor/critic 两次 step；实际次数仍以最终报告和 checkpoint 为准。

## 真实计算与费用边界

`software-consumption.json` 记录 `learning_logprobs` 包装层 actor forward 的 started/completed，分 gradient/no_grad；它不是 GPU kernel 数，也不把 gradient checkpointing 的内部重算另计成包装层 forward。每条 actor/critic backward 共同完成后才递增 `backward_decisions_completed`；中途打断时已完成行数是下界，不能抹掉未完成行已发生的部分计算。

事前固定后更新抽样上限为 6，但本窗口已锁定的实际选择仅 2 行（索引 0、7），按遇到的诊断组第一决定选取，没有读取更新或开发结果。如果全部 206 行通过且 actor 启用、完成原全过程，代码路径应有 206 个最初 no_grad 前向、206 个梯度前向和 2 个后更新 no_grad 前向，即 414 个包装层 actor forward，以及 actor/critic 各 206 个 backward；这只是条件路径说明，不是当前实测完成计数。

B 的支持观察器只通过 hook 复制真实已有 leaf 梯度到 CPU，按原 slot/member 分组。额外 forward/backward/optimizer step 为 0，但 CPU 复制、梯度汇总及序列化仍消耗时间和内存；不能写成“没有开销”。原 `diagnostic_max_groups=0` 保持，观察不会替代 Q 的原生加权反向。

更新 interval 的时钟从原生输入证据验证之后、进入原 updater 之前开始，到 updater 退出结束；不含此前模型装载/输入证据投影和此后完整 checkpoint 保存。GPU 峰值在该验证之后重置，属于此更新区间口径。驻留 worker 的 GPU 时长包含装载、更新和保存等整段成本，与其中嵌套更新 interval 不重复相加。训练 replay 的输入/输出序列材料量和 forward/backward 计算单列，不充当新生成 token 账单；旧五加新三的原生成费用只各计一次。

## 实际逐成员分母

| 槽 | 成员 | 决定 K | 本人输出 T | actor 分母 16T | critic 分母 16K |
|---|---|---:|---:|---:|---:|
| org49-train-LA-r1 | member_001 | 7 | 1856 | 29696 | 112 |
| org49-train-LA-r1 | member_002 | 7 | 1795 | 28720 | 112 |
| org49-train-LA-r2 | member_001 | 9 | 2742 | 43872 | 144 |
| org49-train-LA-r2 | member_002 | 29 | 7231 | 115696 | 464 |
| org49-train-LA-r3 | member_001 | 8 | 2196 | 35136 | 128 |
| org49-train-LA-r3 | member_002 | 7 | 1510 | 24160 | 112 |
| org49-train-LA-r4 | member_001 | 14 | 3067 | 49072 | 224 |
| org49-train-LA-r4 | member_002 | 18 | 5057 | 80912 | 288 |
| org49-train-LB-r1 | member_001 | 17 | 5037 | 80592 | 272 |
| org49-train-LB-r1 | member_002 | 17 | 4218 | 67488 | 272 |
| org49-train-LB-r2 | member_001 | 9 | 2750 | 44000 | 144 |
| org49-train-LB-r2 | member_002 | 9 | 2412 | 38592 | 144 |
| org49-train-LB-r3 | member_001 | 11 | 1811 | 28976 | 176 |
| org49-train-LB-r3 | member_002 | 9 | 2201 | 35216 | 144 |
| org49-train-LB-r4 | member_001 | 16 | 3447 | 55152 | 256 |
| org49-train-LB-r4 | member_002 | 19 | 3998 | 63968 | 304 |

配套 JSON 保存冻结源码 SHA、原始 JSON 引用、完整配方、逐成员材料和所有待定字段。S0 张量完整性与 S0→B actor/critic/Adam/RNG 数值差异仍由另备的一次 CPU checkpoint 对比完成；本说明不将 JSON 恢复回执升级为新的状态张量检查。
