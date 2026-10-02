# v0.27：有限第一阶经验分配器

2026-10-02。本实现响应软件协作审计，保留现有在线学习器、成员动作投影和 `support_weights.py`。它实现可执行的选择规则和原始训练动作绑定；没有执行9B软件候选试训、正式训练或独立确认，不能作为 ID-VTDO 效果证据。旧 v0.25 两类别微实验保持原样；小模型CPU反向接线另作机械控制。

## 1. 输入与允许重配的范围

实现：[experience_allocation_v027.py](../../src/proworksim/experience_allocation_v027.py)。必要控制：[test_experience_allocation_v027.py](../../tests/test_experience_allocation_v027.py)。

一个计划接收同一当前参数采集窗口内的多个精确情境 `supports_by_xi`。每个情境保留固定原始槽清单、稳定成员身份、原始有效性和 Mapper 标签；不同初态、错误类型、执行协议、采集窗口或参数窗口不拼池。成员可承担不同工作职责，动作仍归属实际生成该动作的稳定成员。

每个成员块沿用 `build_support` 的统计：

\[
M,\quad n_z,\quad n^+=\sum_z n_z,\quad v=n^+/M,\quad b_z=n_z/n^+.
\]

`eligible_blocks` 是显式冻结的 `[xi_id, member_id]` 列表，必须具有至少两个达到支持频数门的类别。B、G、I 的原始采集材料、可重配分支、比例与 TV 界相同。其他情境/成员、可信失败、低频类别、无法映射但仍可用于基础 RL 的动作保持单位权重；缺失或不可信动作继续使用原来的 actor mask，不补造目标。

- **B**：基础 `Q=B`，所有已准入 actor 项权重为 1。
- **G**：一般成员—原始轨迹重加权。同一合格块中的每条原始成员轨迹是一个配置坐标，不按方法类别绑定 C 或权重。
- **I**：结构化成员—类别配置。同一精确情境、稳定成员、可靠工作类别内共享权重；类别应来自软件工作中的分工、依赖处理、集成路线等实际证据。

当前 I 的结构机制是类别分组和成员条件化的有限差分，没有大图网络、跨窗口校准预测器或自动发现结构标签。软件 Mapper 的有效性需要另行验收；分配器不通过成功分数反推标签。

所有块均无自由度时，计划返回 `status=no_configurable_support`，必要探测数为零，绑定试训/正式更新接口拒绝执行该有限配置试验。选择结果中的 `Q=B` 只是回退表示，不会自动发起昂贵基础训练；一般在线基础 RL 的原有准入规则未被改变。

## 2. C：有限完整方向配对探测

每个合格块在基础配置处建立完整、确定性的 Helmert 正交单纯形基。I 的维数为 `K-1`，G 的维数为 `n_positive-1`；没有硬编码 `joint_a`、两个类别、第一类别或六个布尔开发结果。

对方向 \(d_j\) 生成一对候选：

\[
q_j^- = b-h_jd_j,\qquad q_j^+=b+h_jd_j.
\]

\(h_j\) 同时满足共同的正负比例界和冻结的探测 TV 半径。每次只扰动一个成员块，其他块保持基础分配；这是第一阶局部规则，没有估计跨块交互。

所有试训从同一完整 actor、critic、两个 optimizer 和规定随机状态开始，使用同一当前模型训练经历。开发回执必须具有相同清单、种子、权重、用途、来源和初始状态/RNG 摘要。每个开发项的效用为有限数值或 `None`，数量不固定为六，未知不计为失败或零。

令冻结开发权重为 \(w_u>0\)，共同 B 试训为参考，有限配对方向效应为：

\[
\widehat c_j=
\frac{\sum_u w_u[(J_u(q_j^+)-J_u(B))-(J_u(q_j^-)-J_u(B))]}
{2h_j\sum_u w_u},\qquad
\widehat C=\sum_j\widehat c_j d_j.
\]

B 在中心差分的数值表达式中消去，但其回执仍必须完整、可对照。估计的 C 在单纯形切空间中取零均值代表；添加常数不改变配置。这里是有限半径、有噪声的开发反馈，不是精确微分，也没有声称 C 已校准成真实长期贡献。

一个方法所需任意 B/正负回执缺失或包含未知时，该方法完整回退到 B；不会仅凭 N 对未知 C 作替代估值。全部观测已知且 C 恰为零时，N 和覆盖锚仍可产生覆盖倾向，必须报告为覆盖规则产生的配置，不能写成已观测开发收益。

## 3. N、共同覆盖锚与精确约束求解

对一个 I 成员块，支持类别数为 \(K\)：

\[
r_z=1/K,\qquad N_z=\max(0,1-Kb_z).
\]

N 只表示**当前真实支持相对均匀支持类别目标的覆盖不足**，不读取开发/独立评价结果，不是贡献、不确定性或成功概率。它不对未观测类别分配质量，也不修补低频支持门。

为使 G 与 I 的先验压力可比，G 中原始成员轨迹 \(s\) 属于 \(z\) 时采用：

\[
b_s=1/n^+,\qquad r_s=1/(Kn_z),\qquad N_s=N_z.
\]

所以两者的覆盖目标按原始槽展开完全相同。G 仅为共同支持范围和覆盖约束使用类别信息；C 的所有原始轨迹坐标独立探测，不受类别绑定。任何 I 配置都可展开成 G 的合法配置 `q_s=q_z/n_z`，并具有相同逐槽权重、TV、两项 KL 和 N 项。两者差别包括结构维度和有限探测成本，不是把 G 的可行范围缩小。

每块求解以下严格凹目标：

\[
\max_q\ \langle q,\widehat C\rangle+\beta\langle q,N\rangle
-\lambda_B D_{KL}(q\Vert b)-\lambda_R D_{KL}(q\Vert r),
\]

\[
\sum_a q_a=1,\quad
\ell\le q_a/b_a\le u,\quad
\tfrac12\|q-b\|_1\le\rho.
\]

默认机制控制参数为 `lower=0.5, upper=2.0, tv_limit=0.2, probe_tv=0.05, lambda_b=1, lambda_coverage=1, beta=0.25`。调用方可以在反馈前冻结其他合法参数；两项 KL 系数须正，beta 可取预声明非负值，不再固定为旧原型的零。默认值只是可执行规则，不是经过软件模型开发校准的最优值。

求解器使用归一化乘子和 TV 非负乘子的嵌套二分，处理全部坐标的比例箱和 TV 边界，不是先剪裁再随意归一化。测试用三类别可行网格独立核对目标值。数值结果向 B 收缩约 `1e-12`，保证 `support_weights` 的严格浮点比例检查。

选择器只根据这个冻结的一阶代理目标生成最终配置，并不声称该配置的真实开发效用已经高于试训候选，也不保证组合多个局部改动后效用线性相加。正式更新后的独立工作才负责确认结果。

## 4. 预算：完整 G，不作随机弱化

非空合格块集合 \(E\) 的必要试训数：

\[
T_G=1+2\sum_{(\xi,m)\in E}(n^+_{\xi m}-1),\qquad
T_I=1+2\sum_{(\xi,m)\in E}(K_{\xi m}-1).
\]

前面的 1 是共同 B 参考。每种方法单独报告包含 B 的必要试训数和 `T * 开发项数` 次开发评价。B 回执可以物理共享，统计总成本时按唯一候选计数，不把同一个 B 执行重复记成本。

计划显式接收同一 `max_trial_updates_per_method`、`max_development_evaluations_per_method` 和 `formal_updates_per_method=1`。上限不足以完成 G 的全部原始方向时，冻结计划直接报错；不会随机截断 G，再与完整 I 宣称公平比较。I 省下的预算不作无意义填充执行。这个首版完整有限差分 G 随轨迹数线性增长，尚无大窗口低秩/梯度元优化版本；真实规模必须用软件任务成本决定，不能先冻结庞大 GPU 运行量。

纯选择器不包含实际时钟/GPU资源执行或成本测量。运行器必须分别登记：当前经历采集、候选试训、开发工作、选择器 CPU、正式更新、独立确认、后继在线工作。共同正式更新次数不代表相同总计算量，也不能据此宣称学习效率。

## 5. 开发输入与独立确认隔离

`development` 必须包含：

- `purpose=contribution_development`、数据清单 ID 和用途划分清单 SHA256；
- 同一起点完整状态 SHA256 和试训 RNG SHA256；
- 按固定顺序列出的 `unit_id/seed/weight`；
- 独立确认 ID 清单，与开发 ID 不相交；
- `provenance=current_model_development` 或 `synthetic_cpu_control`。

`development_receipt` 只是格式化接口，**不会运行或认证试训**。回执绑定候选逐槽权重 SHA256、共同开发清单和上述身份；选择器拒绝额外 `test_score`、独立测试用途、改动的开发 ID/种子/权重和不一致起点。它不能仅凭调用方提供的字符串证明仓库、commit、issue、补丁和测试派生关系没有泄漏；这些来源关系仍由上游冻结用途清单和执行审计保证。

`selection.effectiveness_evidence` 始终为 false：该对象只描述如何选权，不携带独立测试结果。CPU 控制的合成效用不允许包装成当前模型收益。独立确认必须在选权固定后进行，并单独保存 B/G/I 正式更新后的结果。后继经历由各自更新后的策略重新生成，不能交叉复用。

## 6. API 与现有更新器接线

```python
gate = inspect_allocation_window(declaration, records)
# 若 status != ready，保留原始槽和 diagnostic，结束本次有限配置试验。
supports, _ = supports_from_entries(entries, declaration, records)
plan = freeze_allocation_plan(
    supports,
    eligible_blocks=[[xi_id, stable_member_id]],
    development=development_manifest,
    budget=frozen_budget,
)
# 为每个唯一试训候选恢复共同完整状态和 RNG，验证摘要，再调用原更新器。
trial = bind_candidate(entries, declaration, records, plan, candidate_id)
owner.update_window(entries, trial_output, composition=trial)
# 使用更新后的候选模型在冻结开发项上工作；不要拿独立确认结果填写 utilities。
receipt = development_receipt(
    plan, candidate_id, utilities, provenance="current_model_development"
)
selection = select_allocation(plan, receipts)
# 再次恢复共同完整状态和 RNG；各方法正式更新一次。
formal = bind_allocation(entries, declaration, records, plan, selection, method="I")
owner.update_window(entries, formal_output, composition=formal)
```

以上是集成接口示意，既不是自动运行脚本，也不构成新的 GPU 或 API 实验执行授权。每个独立候选、B/G/I 正式分支都必须实际验证完整状态恢复；元数据指纹不替代检查 optimizer 或 RNG。

`candidate_materialization(plan, candidate_id)` 和 `materialize_allocation(plan, selection, method)` 都复用原 `support_weights.materialize_weights`。G 将同一原始成员轨迹作为数学上的单点配置坐标，不增加原始槽或伪造新的语义方法统计；I 使用原类别 q/b。基础任务/成员质量与失败残余因此保持不变。

`validate_allocation(entries, prepared, composition)` 接入现有更新器的版本分发，输出原决策顺序上的 actor 权重及报告，逐一核验：

- 原始 closed rollout、当前 actor、窗口、固定声明、Mapper 与支持一致；
- 试训配置来自已冻结候选，正式配置由冻结选择器和原回执重建；
- 决策属于实际稳定成员，没有重复计数或转移生成目标；
- 原始 input/output token、response SHA256 和 loss mask 未改；
- actor 与 critic 分母都仍是原基础规范；没有按当前权重总和重新归一化；
- 不能将原 mask 排除的目标通过分配重新准入。

`inspect_allocation_window(declaration, records)` 复用原 `diagnose_window`，在未启动、中断或闭合但未完成评估时返回 `status=incomplete_keep_original_inventory`、`supports_by_xi=None`，保留每个原始槽的状态、各情境原始 planned M 和已有诊断，不把 unknown 当作 `V=false`，也不估计不完整窗口的 b/v。它应在选权前调用。

当前绑定 API 要求声明中的原始槽全部有 closed rollout。中断/未启动采集不能删槽后冒充完整支持；按上述结构化状态和冻结协议结束或处理。可信的业务失败可以是 closed，继续保留基础权重。

更新器仍只在原 actor loss 处乘权重，critic、PPO 比率、优势、熵/KL配方和 checkpoint 内容不由本模块改写。`composition` 是绑定消费元数据，不是新模型结构或第二套学习框架。

## 7. 当前核验与未完成证据

必要 CPU 测试覆盖两个精确情境、两个稳定成员、每块三个支持类别、可信失败和缺失 token；验证 G 完整方向的线性真值恢复、I 类内共享、共同覆盖锚、比例/TV/预算约束、未知回退、用途/随机状态污染拒绝、原动作与分母绑定以及三类别求解器可行网格。开发时进行了对应文件的定向静态检查，结案另通过全体 `src tests scripts` 的 Ruff 检查。

上述纯选择器控制没有调用模型、GPU、外部 API 或独立软件测试，没有做参数更新，也不证明生成的软件经历已产生可配置支持。另有[小模型CPU接线控制](../../tests/test_allocation_update_v027.py)，实际恢复共同actor/critic/两个优化器/RNG，执行9个唯一候选试训与无配置/B/G/I四个更新对照，核验非单位配置只改变actor目标，显式B与无配置完全相同；其语义标签与开发效用仍为合成输入，不构成软件学习或分配效果。

后续须分别取得软件载体真实工作、当前训练窗口支持、B/G/I 同条件正式更新与独立确认四层证据。不得用本模块的合成开发分数替代其中任何一层。整合验证结果及环境见[本次实施报告](../experiments/software-alignment-v027.md)。
