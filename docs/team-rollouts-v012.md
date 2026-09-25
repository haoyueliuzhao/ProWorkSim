# v0.12 团队轨迹、工作有效性与组合权重合同

本文说明 D2 的有限实现边界。它不修改 v0.11 `RewardSpec`，也不证明策略已经学习或当前模型已经拥有多种可靠合作方法。规则见证、离线算术夹具、真实模型采样与参数训练必须分别报告。

## 保存单位与三层门槛

`TeamRollout` 是一个已闭合历史 episode 的联合记录。读取既有 `EpisodeManifest` 的开始、结束快照、固定工作责任与原始 `[start,end)` 经历区间。`export_team_rollout` 调用历史只读评价，核对不可变文件、episode 身份、策略指纹和奖励所属 manifest。损坏到无法读取的 episode 不能导出有效轨迹，但采集窗口的原始 slot 必须保留，不能只从成功导出的行重建分母。

窗口明确固定以下五个身份：`window_id`、`xi_id`、`xi_fingerprint`、`gamma_fingerprint`、`team_policy_fingerprint`。ξ 包含实例、初始信息持有和权限；Γ 包含工具、提示、上下文选择、调度、预算和外生事件等执行规则。场景注册表负责 ξ 与数据来源/划分身份，D2 不通过场景名称猜测等价。不同信息布局即使业务表相同也不能合并补充支持。策略指纹必须与 episode 记录的实际 policy 配置一致。

三层判定分别保存：

| 层 | 回答的问题 | 未知/失败的处理 |
| --- | --- | --- |
| `reward_eligibility` | 固定目标的回报是否可可信评价？ | 沿用旧合同：可评真实失败可以为 0；外部未知、服务或评价故障为 `eligible=false,reward=null`。 |
| `work_validity` | 记录、权限、依据、交付是否符合本工作合同？ | 四维三值合取；任何已证伪分量使 V 为 false，全 true 才为 true，其余 unknown。回报高低不替代 V。 |
| 成员重配资格 | V=true 的联合轨迹是否映射可靠、本人动作可恢复、来源为当前目标策略且达到预声明支持门槛？ | 不满足时不进入重配正池；有可信奖励和可恢复本人动作的普通失败仍保留基础 actor 分支，权重 1。 |

V 的未知是 JSON `null`，不能转换为数值 0 再报告成工作失败。已证实记录完整性不足的轨迹不进入基础 actor 更新；slot 及其失败原因继续保留。基础 actor 掩码还要求可信回报、当前目标成员来源、完整动作轨迹、至少一次实际生成。V 的权限/依据/交付不通过不自动删除基础失败样本。

## 真实工作有效性的有限检查

`team_validity.assess_team_validity(episode, members=..., independent_capture=..., spec=..., assessment_spec=...)` 只读已闭合 episode。`spec` 来自开始前场景 `variation.validity_spec`，不是模型输出或运行后人工填充的四个 true。

当前 `decision_team` 合同检查：

1. 独立公共端口 capture 与经历中的全部工具清单、观察和实际调用逐项对照；模型关联元数据单独保留，不伪装为端口原返回。缺独立 capture 为 unknown，已观察到不一致为 false。
2. 调用与世界正式 command receipt 的绑定 actor、原返回一致；预声明允许的工具拒绝必须没有 apply 阶段业务变更。时钟推进或同轮环境事件与被拒操作本身的业务作用分开。合法拒绝不自动判 V=false。
3. 必需手工路由存在实际成员 `handoff_information`，发送者之前实际读取了选中的确切版本，且对应环境事件真实送达当前责任 work。自动服务回复、只排队未送达和旧版历史回复不能代替手工成员选择。
4. 末时固定提交，以及本 episode 中曾正式批准过的提交，使用真实 read 与固定 adoption_snapshot 对应的资料。允许修复时，已撤回且从未批准的早期准备草稿不永久污染最终 V；已经发生的无依据批准不能被事后读资料或重写文件洗掉。
5. 每次批准前，指定 reviewer 实际 inspect 固定提交、读取每个确切交付版本、读取适用当期的 approved audit_basis。退休版本或错误期间不能因为最终数值正确而通过。版本选择来自实际过去读取，不能拿结束时新版本替代过去审阅证据。
6. 交付维度要求当前固定责任的真实批准与独立内容评价通过。制度批准与内容正确性仍分别保留；单独批准、仅正确但未完成审阅、正确但缺依据都不能构成完整 V=true。

对于真实模型，依据必须能连到后续动作所对应的实际 HTTP request：先前确切 `model_tool_result.message` 存在于该请求的 messages，才算实际呈现。完整保存的 memory 不代表模型实际收到它。未能恢复该请求是 unknown；可观察请求中不存在对应资料是 false。这只能证明证据被真实呈现与引用的工作链，不能证明模型内部认知或因果必要性。

当前 `blocked_outcome="unknown"` 明确表示尚未建立通用合法受阻结局的充分判定合同。真实请求、成员 unavailable 回复、未伪造资料与未交付可以被记录和控制测试验证；它们不会被包装为已完成正类，也不会进入重配支持。允许运行在受阻边界停止与允许 V=true 是两个不同合同。不能把任意 `world_blocked` 自动标有效。

## MemberView 与实际 token 所有权

`member_views.member_view(rollout, member_id)` 对该成员所有 `model_call started` 逐一保留实际 HTTP request、原响应、上下文选择、policy 身份、effective generation、attempt/decision/opportunity 链接和实际世界动作。包含格式失败、等待或结束等实际生成，不只取首轮、最后一轮或成功工具调用。

服务实际产生并返回的 `token_trace` 才可提供训练位置。模块核对原 input/output IDs、输入掩码 0、本人生成掩码 1、有限 behavior log probabilities、usage 长度和原始生成来源标记。它不会重新 tokenize 文本、重构遗漏 completion 或伪造概率。工具返回和同事消息都在输入侧，不因文本相似成为本人 target；模型实际再次生成的引文则仍是它自己的输出位置。

任一应有实际生成的轮次缺唯一响应、孤儿记录、重复 call id、请求/响应关联不符、重试后可能遗漏行为抽样，均使本窗口该成员完整 actor 轨迹不成立。一个已开始编制请求但在真正发出 attempt 前被预算阻止的 call，在有对应明确 budget-stop 证据时标记 `actor_required=false`；它不能造出动作或 token。没有本人成员动作的块保留但 actor 梯度贡献为 0。

商业 API 缺实际 token IDs/概率时仍保留完整语义轨迹。`semantic_work_support` 单列 V=true、映射可靠、当前目标成员实际生成存在且 `complete_semantic_trajectory=true` 的语义支持计数；缺任一实际轮次的请求/响应、关联不符或重试后未明行为不会进入该语义计数；仅缺 token 的完整 API 对话仍可进入。它不代表可训练支持。`n_positive/b/v` 还要求该成员完整可恢复动作。provider 没有自己拥有的业务 work 不影响其真实 handoff 与生成属于本人；责任节点所有权不是 token 所有权。

`origin` 明确区分 `target_model`、`rule`、`teacher`、`historical_model`、`offline_fixture`。规则见证、老师轨迹或旧模型记录不能转成当前目标策略的支持。离线测试为了检验代码会构造带 token 字段的 fixture；这些夹具不是模型采样证据。

## 观察关系图与有限 Mapper

`information_mapper.information_graph` 保存实际动作、精确资料版本、请求、成员 handoff、环境送达、真实 actor 输入和公共 tool result 节点。边区分真实 read、选择、采用、声明依赖、request→reply、实际送达、送达后相同版本访问、tool result→实际选中输入和输入→动作。声明 dependencies 只标“声明”，时间先后只标“观察”，不称为已识别因果图。

`map_joint_method(graph, route_id="basis", spec_id=...)` 当前只支持预声明同一路由的两个结构类别：

- `proactive_handoff`：实际成员主动选择并送达确切资料，没有被伪造的 request。
- `requested_handoff`：实际送达与之前真实 request 身份相连。

随机 ID、文字措辞、等待时长不定义类别。保持真实角色/方向、资料版本与回复关联；不同布局在窗口合同层分开。幂等重发不增加方法。多个不同 handoff 需要更丰富的事先 Mapper，此版返回 ambiguous；缺实际送达/确切版本/被请求身份返回 unmapped。V 与方法映射是独立门槛，不能用某类标签保证工作有效。

## b、q、v 和原始分母

`support_weights.build_support(slots, window=..., member_ids=..., min_class_count=...)` 接收开始前固定的原始联合 slot 清单。M 是所有这些 slot 的数目，含采集失败、未知、无动作和不可训练记录。同一联合 rollout 不能按成员投影复制为多个样本；重复 ID、跨布局/协议/策略窗口、混用 Mapper/Validity 合同都被拒绝。

对每个成员，E 为可训练且 V=true、可靠映射并达到预声明频数门槛的 slot；`n_by_class`、`n_positive`、`v=n_positive/M`、`b=n_by_class/n_positive` 都被物化。另存门槛前候选数、逐 slot 排除原因、基础 actor mask 和语义支持。没有正支持时 b 为空，单类时组合自由度为 0；仍保留基础分支，不能靠跨布局或老师数据补类。

`materialize_weights(support,q,lower=...,upper=...)` 要求每个成员都有目标 q，支持集合与 b 精确相同、有限非负、归一化且 q/b 在固定边界内。超界拒绝，不偷偷截断或重新归一化。E 内权重为 q/b，其余原始 slot 为 1；没有实际动作仍通过 actor mask 给出 0 actor 贡献。固定基线分母不会被每个 minibatch 的 sum(weights) 替代。

Q=B 时此层应给每个原始 slot 精确权重 1，包括可评失败。离线 10-slot 算术控制含 6 个可重配样本，类别计数 3/2/1：v=0.6，b=(1/2,1/3,1/6)。均匀 q 的正分支权重为 (2/3,1,2)，其他四个失败保持 1，正分支质量仍为 6。

这些只证明表示和权重算术。完整 Q=B 等价还必须由 D3 核对相同样本、token/轮次归一化、优势、完整基础 loss、梯度和优化器更新；不能仅凭所有权重为 1 宣称训练实现正确。q/b 是组合权重，PPO `exp(new_logp-old_logp)` 是策略概率比，两者不同。组合权重只乘 actor 分支，不能改变 critic、entropy、KL 或重新按 q 计算优势。

## 必要局部验证

运行：

```bash
.venv/bin/python -m pytest -q tests/test_team_rollout_v012.py tests/test_team_validity_v012.py
```

前者是显式离线表示/算术反控制，包括跨窗口、重复 rollout、unknown、缺 token、无动作、Q=B、支持不足和实际请求选中关系。后者运行真实本地世界、独立端口 capture 与可读 episode，执行手工传递/采用/SQL/正式审阅；覆盖两种信息布局、主动/请求路径、无依据批准、退休 audit、合法拒绝与修复、缺 capture 和真实 unavailable。规则执行的 SQL 是机制见证，不能报告为目标模型发现方法或训练收益。正式实验的源身份、原始运行目录与模型采样结果需在对应实验报告中单独固定。


## 冻结 inventory 的只读物化入口

```bash
.venv/bin/python scripts/team_rollout_experiment.py --inventory frozen-inventory.json --output runs/new-team-materialization
```

输入版本为 `team-materialization-inventory-v0.12`，`windows` 中每项包括五字段 `window`、`members`、`mapper`、`min_class_count`、`reward_spec`、`assessment_spec`、`protocol_ref` 和完整 `slots`。`protocol_ref` 固定实际协议的 path/字节 SHA256。每个 slot 声明 `slot_id`、episode 目录、`scenario_ref`、`capture_ref`，可附 `record_ref`；所有 ref 为 path/字节 SHA256，相对路径以输入 inventory 所在目录为基准。场景内容必须与 episode 开始时冻结的 scenario（或其 `spec`）一致。

采集前固定 slot 名单、场景、成员政策、RewardSpec、评价与 Mapper 合同；采集后只能机械补录这些 slot 的真实文件路径/哈希，不能按成功结果删行。脚本不读取 runner 的“成功”标签来造奖励，而重新读取历史边界并运行独立评价。缺失/损坏 episode 或哈希不符产生 `read_only_materialization` 边界问题，保留 null 而不冒充员工 reward=0/V=false，并继续保留原始 slot 分母。

输出新目录中保存逐 slot 的 TeamRollout、MemberView、关系图、V、历史评价、奖励、映射及各自 SHA256；每窗口保存 support 和 Q=B 权重。紧凑 summary 按原始 M 报告可评失败、V 三值、映射失败、当前目标联合有效产出率以及每成员语义/可训练支持。跨窗口可合计原始计数，但不合并 b/q/支持。输出必须为新目录，且不得放在被读取的 episode 内。

API 的模型别名和响应指纹是观察到的身份，不证明供应商权重永久不变。商业 API 的语义统计与本地可核验权重/profile 的可训练支持需分别说明；不可将 API token 缺失解释为工作不可能，也不可将语义可行解释为已有 PPO 样本。
