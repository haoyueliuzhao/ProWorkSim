> **获授权预算修订**：用户指示“提高预算，继续实验”。同一基线更新的时限由 11 延至 18 小时，阶段由 12 延至 20 小时；原计划名义上限 58 GPU 小时，有效上限 66 GPU 小时（无支持路径由 23.5 延至 31.5 GPU 小时）。本轮采用运行中获授权延长，不能表述为在原时限内完成。冻结计划、业务结果及采样/更新次数保持原记录；原自动报告完整字节与 SHA 已另存。

# v0.25 当前经验支持与成员配置实验

状态：`closed_incomplete`；执行终止：True。
实际闭合新episode：16（支持/开发/确认/后继分别[16, 0, 0, 0]）；训练消费16，新actor/critic步骤0/0。

预定配置−基础主点估计：None；配置是否改变：False。
无支持或最终保持Q=B时，不制造相同配置的重复模型比较；未执行不是零效果，未知不是负贡献。

| 精确情境 / 成员 | M | n+ | v | 各类n | b | 自由度 |
|---|---:|---:|---:|---|---|---:|
| retail-v25-a4be1394fce60c40 / provider | 8 | 0 | 0.000 | {} | {} | 0 |
| retail-v25-a4be1394fce60c40 / implementer | 8 | 0 | 0.000 | {} | {} | 0 |
| retail-v25-4273bbfbaa657a8c / implementer | 8 | 0 | 0.000 | {} | {} | 0 |
| retail-v25-4273bbfbaa657a8c / reviewer | 8 | 0 | 0.000 | {} | {} | 0 |

预定顺序选中块：None。
配置决定：no_current_supported_member_block；开发差分贡献：None。

| 确认端点 | 已知 / 12 | 完整职责 |
|---|---:|---:|
| base | 0/12 | 0 |
| configured | 0/12 | 0 |

确认端点未执行时，上表完整职责计数不构成0/12成绩。JSON保留每个槽的未知、部分成果与复核有效性。

| 分支 | 更新状态 | 同完整起点 | 反向权重匹配 | 非单位权重决定 |
|---|---|---|---|---:|
| base | preparing | True | None | 0 |
| probe | None | None | None | 0 |
| configured | None | None | None | 0 |

只有合格成员分支actor项乘q/b；原奖励/优势/PPO比率/critic及槽、成员、本人token分母保持。共同原轨迹分别消费，不冒充新样本。

| 阶段 | 状态 | GPU小时 |
|---|---|---:|
| support | complete | 1.861355 |
| train_base | stopped | 11.865038 |
| train_probe | not_required | 0.000000 |
| dev_base | not_required | 0.000000 |
| dev_probe | not_required | 0.000000 |
| train_configured | not_required | 0.000000 |
| confirm_base | not_started_endpoint_unavailable | 0.000000 |
| confirm_configured | not_required | 0.000000 |
| next_base | not_started_endpoint_unavailable | 0.000000 |
| next_configured | not_required | 0.000000 |

已结算成本13.726393 GPU小时，原计划上限58 GPU小时／获授权有效上限66 GPU小时；外部模型/API为0。加载、试训、开发、失败和并行卡占用全部计入。
后继交互仅新策略rollout与支持诊断，无第二次优化。一般元调权强基线、独立训练seed、跨来源与图特征贡献均未在本轮检验。

原始证据、配置和逐成员权重、完整起点、端点配对、资源竞争及停止原因见同名JSON。此报告只读原记录，没有补采、重评分或改写旧实验。
