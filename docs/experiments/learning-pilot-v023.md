# v0.23 有限配对工作学习报告

状态：`closed_incomplete`。内部计划 72 例，外部另计 6 例；本报告只读取原始归档，不重新评分。

已完成训练窗口 4/4；可信完整配对 19/24，来自 12 个情境的各两次种子重复。
预定协议完整职责变化：未知/未完成；全部 24 对分母的不确定范围：[-0.25, 0.16666666666666666]。

| 工作结构 | 已知配对/计划 | 完整职责均值差 | 全分母范围 |
|---|---:|---:|---|
| joint_a | 8/8 | -0.125 | [-0.125, -0.125] |
| joint_b | 8/8 | 0.0 | [0.0, 0.0] |
| maintenance | 3/8 | 未知/未完成 | [-0.625, 0.625] |

三类结构等权；重复、初末端点和同源新材料均不能当作额外独立来源。已知失败保留为零，未知不填零。一个训练种子不支持稳定性或显著性结论。

初末配对固定的是情境、Torch 采样种子与业务初态，并不保证 wire 消息或输入 token 逐项相同。StaffRuntime 的 run_id 使用 UUID，经 request_key 派生的命令标识及 response_sha256 可能进入后续真实工具输入。这项未控制的 Γ 随机性，加上每情境仅两次重复和单训练种子，限制把观测差异确定性地全部归因于参数更新；不改变本报告预先固定的配对及主描述量定义。本轮没有改动世界标识机制。

| 训练窗 | 状态 | 最后保存的 actor/critic 步数 | 正优势所关联的已达成回报项 |
|---|---|---|---|
| 1 | closed | 1/1 | {"applicable_basis_delivered": ["train-1-0", "train-1-4"], "independent_final_review": ["train-1-5"], "correct_fixed_final_product": ["train-1-5"], "valid_review_and_repair_path": ["train-1-5"]} |
| 2 | closed | 1/1 | {"applicable_basis_delivered": ["train-2-0", "train-2-4"]} |
| 3 | closed | 1/1 | {"applicable_basis_delivered": ["train-3-0", "train-3-4"]} |
| 4 | closed | 1/1 | {"applicable_basis_delivered": ["train-4-0", "train-4-4"], "delivered_basis_used_in_build": ["train-4-0"]} |

未闭合更新窗的保存步数是进度，不能替代终态证明。JSON 保留逐槽回报来源、成员动作、正/负/零优势、固定上下文概率变化及原始 SHA 引用。终端回报与动作阶段的关联不等于逐动作因果信用。

终态 actor/critic 累计步数：4/4。
原五阶段及条件恢复已结算 GPU 秒下界：78804.456；完整总量：78804.45593190193。资源竞争 PID 按原监督采样保留，不推断它造成失败。

外部指定 D2 变体：已知 3/3 对；完整责任均值差 0.0，独立于内部 72 例。原修订 grader 与真实复核责任分别保存在外部归档。

内容、固定交付、复核缺席和错误/无据判断只使用已存 assessment 能直接支持的字段。未公开纯内容或错误原因拆分的字段明确为 null，不据 partial reward 推断完整工作提升。

实验目录：`/data1/zhuxinrui/projects/ProWorkSim/runs/domain-v023`。冻结源码、计划、catalog、checkpoint 和每项产物 SHA 见同名 JSON。
