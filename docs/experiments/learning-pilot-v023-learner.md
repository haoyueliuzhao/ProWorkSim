# v0.23 训练投影、行为信用诊断与原窗口恢复

本文记录新增接口及 CPU 控制，不是本轮真实模型实验结果。v0.22 已完成当前运行组合的学习接入；本轮保留该实现，研究重点转为实际工作在更新前后的变化。没有重新展开缓存、精度或反向候选筛选。

## 1. 固定学习接口

`collaboration_training_v023.py` 将新材料目录中的四个窗口分别绑定为六个预定槽，顺序为 A、B、实现、复核、A 重复、B 重复。每窗只有四个不同情境；A 的两次使用同一个精确 case，B 同理，两次各自形成真实 episode。四窗的训练情境互不替换。训练、评价材料按完整客户、发票、原始行检查不重叠；同一 UCI 来源内的划分不产生独立来源。

`training_admission(catalog, source_pin)` 检查模板目录、源清单字节、四窗结构和用途；`validate_window_declaration` 检查全部槽的顺序、情境、活跃成员、固定采样种子以及角色机会预算。实现 12，复核 12，A 为 6＋16，B 为 24＋28；context 16384、单次输出 2048、温度 0.7。四次决策的旧桥接限制不能通过新准入。业务 episode 仍由已有有限工作期限闭合；其停止与完整职责成功分别记账，更新的计算监督期限另外设置。

`export_training_episode` 读取本轮实际 WorldCore 记录、独立业务评价和角色原始 token，生成现有 `TeamRollout` / `MemberView`。引用准备状态、程序见证、评价经历或旧 E/W1 的产物不构成当前目标。输入 loss mask 为 0，本人实际输出为 1。已知零回报、拒绝动作和格式失败的实际输出继续保留；缺 token 记录或未知业务结果不能转成训练零值。

学习仍调用原 `prepare_window` 和单窗 PPO 更新器：每个成员的所有实际输出 token，除以 **6 个预定槽 × 该槽实际活跃成员数 × 该成员全部目标 token 数**。critic 分母同样保留全部预定槽和成员。缺失槽不会被移除后重新归一化。所有组成权重为 1，即 Q=B；完整 basis/delivery 重配置有效性尚未建立，不能把 reward、completed 或描述性动作类别升级为 ID-VTDO 支持。

初始化使用公共 9B 加 fresh LoRA、critic 和两个 optimizer。函数式 `functional_qwen_v022.py` 的字节保持不变；存储精度、`terminal_mc`、epochs=1、原 PPO 目标、学习率和概率门保持原配方。原更新状态若是概率失配或运行错误，不能作为“正常零更新”进入下一窗口。

## 2. 这一步强化了哪些实际行为

`work_learning_diagnostics_v023.summarize_work_signals(entries, update_output)` 在已有记录上工作，不调用模型，也不添加前向。它将每一项已保存优势与原 `slot_id/member_id/call_id` 对齐，并输出：

- 原终端回报、原分项是否实现及其分值、更新前 critic、优势值和正／负／零／未知类别；
- 本人的真实世界工具调用、成功／拒绝回执、动作序列号、提交／构建／证据读取／正式复核／修复等描述性阶段，以及决策前公共阶段；
- 原 token 分母、该决策的名义 token 平均权重和带优势的权重；六个槽、成员与缺失状态保持可见。

某次 `sql_build` 成功只证明工具执行成功；正确内容必须由独立业务回报分项证明。终端回报广播给整条本人经历，因此“某阶段获得正优势”是描述性关联，不是这个动作独立产生回报的因果证明。局部 actor 优势为零，也不表示共享参数更新不会改变该成员以后的行为。若原窗口没有生成完整优势记录，报告填未知，不能填零。

## 3. 更新后固定上下文概率变化

每窗最多六条，预声明顺序为：A/provider、A/implementer、B/implementer、B/reviewer、implement/implementer、review/reviewer。各对只取 admission 中第一条实际决策；该对缺失就保持缺失，不按得分、阶段或输出长度补位。对应索引在 admission 后、任何参数 step 前写入 `post-update-selection.json`。

`SharedActor.update_window` 仅增加可选 `post_update_selector` 注入点。原损失、准入、反向和 optimizer 不变；未传入时保留旧选择规则。v0.23 显式传入上述六对选择器。追加前向使用原上下文、原输出 token 和原温度，比较更新前已通过行为门的概率与更新后的概率；不重新采样，不将学习引起的差异送入同参数一致性门。

这是一组有限行为 token 的变化诊断，不是完整分布 KL、完整轨迹 KL 或工作提升。一次整窗起点梯度中 PPO clipping 为零，也不能作为更新后策略变化必然受 clip 区间约束的证据。六条额外前向计入本轮资源成本。

## 4. 一次有界原窗口恢复

`pilot_recovery_v023.admit_recovery(old_stage_dir, plan)` 只接受训练进程已退出、监督器明确记录更新阶段超时／中断的情形。旧源和计划必须与当前冻结源完全相同，原窗口是最后一个 `updating` 窗口，之前 0—3 个窗口已正常闭合。原窗口六槽全部记录、原始 declaration、准入和 `shared-before.pt` 必须齐全，原行为概率核查完整通过；更新只能停在 `preparing/backward`，本窗 actor/critic step 计数均为 0。

未 step 证明使用冻结更新器控制流：`gradient-probability-check.json`、`losses.json`、`signal-diagnostics.json`、`gradients-before-clip.pt` 都必须在任一 optimizer step 前写入，旧进程退出后它们必须全部不存在。任何必经文件存在、已经保存后继 checkpoint、数值失败、worker 仍存活或 step 状态不明，均拒绝恢复。这不是进程死亡后的内存张量读取证明。

`restore_window` 用 `weights_only=True` 载入原共享状态，恢复 actor、critic、两个 optimizer、CPU/CUDA RNG、已有 step 数、非零回报历史、窗口和策略身份；对完整 `_state_bundle()` 做张量树摘要相等检查。允许之前已经完成 0—3 步，不要求总 step 数为零。清除部分梯度，再从原六条经历重建 `prepare_window`，要求整个 admission 与原文件完全相同，才回到原 `collecting` 边界重算。本窗不重新采样，不替换材料，不跳过零优势行。

该助手不分配 GPU、不延长期限，也不管理任意故障恢复。监督器另行约束最多一次恢复、原窗口额度及全程累计额度；旧失败与重算成本都保留。参数 step 状态不明不自动重做。

## 5. 必要 CPU 控制

`test_collaboration_training_v023.py` 使用明确标注的合成 token transport，运行真实新材料 WorldCore 和实际 `learning_pilot_v023.collect_window`：验证六槽、A/B 精确重复但 episode 不同、调用种子顺序、本人分母、缺失槽保留、评价材料替换拒绝以及四次复核预算拒绝；检查分项→优势→真实动作关联，未知优势不填零。这些 token 和数值不进入实际 pilot。

`test_work_learning_diagnostics_v023.py` 验证选择器不受结果／阶段影响，缺失对不补位；小型 CPU actor 验证选择器在 step 前只执行一次。测试专用的大更新使更新后概率差超过旧同参数阈值，仍按学习变化记录，原行为核查保持通过。该控制不加载 9B，也不重新建立模型数值资格。

`test_pilot_recovery_v023.py` 验证必经文件存在、worker 存活、已知数值失败均禁止恢复；小型 CPU actor 在已有一次 actor/critic 更新后保存第二窗口状态，恢复两 optimizer、RNG、窗口历史并重建原六槽准入。首次测试复用了旧 fixture 的非 SHA256 基座标识而被身份校验拒绝，已将 fixture 改为明确 CPU 基座 digest；生产身份门未放宽。

本说明的测试范围不替代正式 72 例工作评价，也不把 CPU fixture 记为模型成功。

## 6. 成本依据及外推边界

逐决策长度和原始引用摘要见 [learning-pilot-v023-cost-inputs.json](learning-pilot-v023-cost-inputs.json)。这些是历史观测的只读整理，没有运行新模型。

| 历史观测 | 输入 token | 输出 token | 有图前向秒 | backward 秒 |
|---|---:|---:|---:|---:|
| N1 development | 8473 | 146 | 13.234 | 53.479 |
| N1 heldout-0 | 4251 | 308 | 25.109 | 82.977 |
| N1 heldout-1 | 13275 | 2048 | 160.717 | 578.223 |

R1 的 24 条决策合计输入 171735、输出 3134，平均每条约 7156／131。更新 heartbeat 到首个 post heartbeat 为 1478.275 秒，包含无梯度核查、有图前向、反向、step 和 checkpoint 边界，**不是纯反向时长**；原档案没有保存逐决策各计算阶段的完整计时，不能补造。B1 四片采集阶段合计约 188.695 秒，不能用这段采样时长代替更新成本。

完整六槽每窗的上限是 172 次生成机会。如果长度与负载完全复现 R1，机械外推更新约 **2.943 GPU 小时／窗、四窗 11.771 小时**，尚未加入新采样、每窗最多六条 post 前向和额外边界成本。作为另一种压力情景，如果 172 条都与 N1 最长例一样，单窗仅有图前向＋反向就约 35.305 小时。后者不是预计表现，前者也不是完成承诺；实际完整工作会改变长度分布和停止位置。额度应先固定，触限如实报告未完成，而不是看到业务结果后延长。

## 7. 初末配对的随机性边界

代码检查确认，固定情境、采样 seed 和初始业务状态摘要，不等于之后每个模型输入 token 完全一致。`StaffRuntime.run_id` 使用独立 `uuid4`，实际工具 `request_key` 包含它；WorldCore 的 `command_id` 又由该 key 派生。ModelPolicy 将真实返回完整写入 tool 消息，compact 保留相应返回，并把其摘要写入本人的动作索引。第一次工具返回后，这些标识可进入后续模型输入；固定 Torch RNG 并未固定这条 UUID 来源。此外原生生成解析也产生随机 tool call ID，其是否直接进入 token 取决于 chat template。

因此本轮配对控制情境、预定采样种子和业务初态，仍有未单独控制的运行标识随机项。不能把配对描述为更新前后全部输入序列逐 token 相同；行为本身的分叉也会改变后续输入。本轮没有为此改动世界 ID 机制，也没有据业务成绩筛掉受影响的配对。
