# v0.13 critic 与在线策略窗口的有限合同

本次将已有联合经历接入逐窗口基础 RL 的必要边界，不以完整团队成功或多方法支持作为基础学习的前置条件。这里没有执行模型采样、梯度更新或 GPU 实验；也不改写旧 v0.12 准入结果。

## critic 状态编码修订

旧 `scripts/multiturn_ppo_v012.py::past_features` 的工作计数栏为 `open/active/pending/accepted/blocked`，但实际世界观察使用 `in_progress/in_review`。旧脚本保留原样，仅作为历史实现。旧 prepared、结果及旧门槛都未回填。

复现记录见 `docs/experiments/v013-critic-state-features.json`。`runs/critic-state-v013-before` 保存冻结 `f976224` 的完整训练脚本、实际 WorldCore 创建/修改/提交/批准返回、未经改写的观察与结束状态。旧完整模块编码真实的 `in_progress` 和 `in_review` 观察时发生碰撞，`open/accepted` 控制可区分。比较将各个真实观察分别放入相同的单观察前缀，以隔离状态通道；并不声称包含不同动作次数的完整历史也完全相同。

新增 `proworksim.critic_features`：

```python
features, provenance = past_features(
    events, before_sequence, member_id,
    member_ids=("provider", "implementer", "reviewer"),
)
```

版本为 `past-public-structure-v0.13`，保留 30 维：每成员 9 个结构计数，加 3 个 acting-member 指示。每成员的 5 个状态栏现在使用确切的 `open/in_progress/in_review/accepted/blocked`。另有可见工作数、工作区别名数、实际工具返回 ok/拒绝数。后两者是观察计数，不是正确性或奖励。

`member_ids` 始终是同一顺序的三个 critic 角色，哪怕某个 episode 只有一个活动模型成员。没有过去观察或动作的成员，计数为零。其他世界确实存在的 `revision_required/superseded/cancelled/waiting_dependencies` 保留在 `recognized_unbinned_work_status_counts`，此有限 30 维不为它们另加状态栏。未知状态报错，不悄悄按零或近义词处理。

前缀截点必须是原经历中匹配本成员/本 call 的 `model_call`、`stage=started` 事件序号。`MemberView.input_event_sequence` 指向结束的 HTTP attempt，不能代替决策开始截点。函数只读取截点之前各角色最近公共观察和工具 ok 字段；不读取内容数值、独立评分、未来观察或终局真值。provenance 记录版本、维度、特征名、角色顺序、观察序号及未观察成员。

该修订不证明旧状态编码是 Qwen 拒绝循环的原因；旧批并未进行 actor/critic 更新。它也不证明一个 30 维 critic 足以表达任意专业工作状态。

## 在线窗口绑定

`proworksim.online_support` 不创建新采样批、不选择成功案例、不执行优化。调用者在每个当前策略窗口开始前冻结声明：

```python
declaration = declare_window(
    window_id,
    actor_identity=owner.freeze_identity(),
    gamma_identity=frozen_execution_protocol,
    slot_specs=[{
        "slot_id": "declared-slot",
        "xi_id": "exact-situation",
        "xi_fingerprint": "registry-derived-fingerprint",
        "active_members": ["provider"],
        "policies": actual_runtime_policy_identities,
        "mapping_spec_id": "predeclared-method-equivalence",
    }],
    min_class_count=2,
)
```

有效 actor 身份严格包含 `version=shared-actor-identity-v0.13`、`policy_version`、实际 `adapter_sha256`、`base_manifest_sha256` 和 `inference_profile_sha256`。允许更新后的适配器；不要求第二个窗口仍是未训练 base。活动角色的 `ModelPolicy.config.weight_identity` 必须等于这一共同身份，`model_revision` 必须对应当前版本。角色任务文本和权限可以不同。

`expected_window(declaration, slot_id)` 直接产生 `export_team_rollout` 需要的五字段窗口。共同 actor 身份与 `team_policy_fingerprint` 分开：后者仍然是该情境真实 `manifest.policies` 的哈希。活动角色为 1/1/1/3 时，政策映射哈希自然不同，不能误判为共享权重不同；同时也不能因为同一 base 路径而忽略实际适配器已经变化。

`bind_rollout(declaration, slot_id, rollout, mapping=None)` 只核对已闭合的原始 TeamRollout，不修改事件、动作名或输入。它检查情境、Γ、实际政策映射、活动 target_model 集合，并核对所有实际响应的 `actor_identity`、`system_fingerprint` 与 `online_window_id`。孤儿响应也不能绕过策略身份检查。返回原 v0.12 `build_support` 可用的 slot 以及活动成员全部 `MemberView`。

非活动角色或准备前缀可保留为有来源的世界历史，但不能被补成目标成员的 actor 动作。角色没有本人的真实生成时，actor 掩码为零。缺 token 可保留语义经历；不能重新 tokenize 文本或伪造行为概率填成训练样本。

## 随在线交互产生支持诊断

```python
report = diagnose_window(declaration, [
    {"slot_id": "declared-slot", "status": "closed", "rollout": rollout},
])
```

显式记录支持 `closed/closed_unassessed/interrupted/not_started`；未传的预声明 slot 仍标为 `not_started`。没有完成的情境块分别报告计划、闭合、中断和未启动数量，不估计 b/v，不把未启动配额称为实际 rollout。完整块按照同一 ξ、Γ、当前策略与活动角色独立调用既有支持物化，返回 n、v、b、semantic support、base actor mask、Q=B 权重和原因。跨 ξ、布局、提示映射、窗口或实际 θ 的记录不能混入支持。

未提供映射时明确为 `unmapped`，不凭文字标签造方法类别。调用者提供映射时，其 rollout ID 与事前 `mapping_spec_id` 都必须匹配。不同样本不得复用同一联合 rollout 来增加计数。

**无支持或单类别只限制组合干预，不阻断基础 RL。**可可信评价的失败、完整本人成员 token 和已验证记录仍保留 base actor mask，Q=B 下权重为 1。评价未知或记录不可信仍单独隔离。优化器是否应更新、优势为零时如何处理、实际新旧概率是否一致，由版本化训练器负责；本诊断不会制造回报差异，也不会把随机 critic 初值差异当作工作学习信号。

不同长度的短工作片段有自己的责任范围。短段奖励通过不能冒充完整三成员链 V=true；旧 full-chain V 不应被当作所有基础短段 RL 的成功门槛。

## v0.13 读取操作的后验语义

世界新增的 `read_alias` 与 `read_version` 是实际 Core 操作，必须保留各自正式 receipt 和原始返回。旧 `read_object` 行为保持。`team_validity` 的 spec 可显式声明 `read_operations`，支持上述三种真实读；未声明时仍仅使用旧 v0.12 `read_object`。

`information_graph(rollout, read_operations=("read_alias", "read_version"))` 对声明的真实读结果建立 `observes_version` 边，并标记 `information-graph-v0.13` 与操作声明。默认调用仍是旧图语义。未知名称被拒绝；不能只改公共记录字符串来伪造实际读取。新 v0.13 full-chain spec 应固定该声明。短段自己的 validator 负责其局部工作范围；本模块不把未执行的复核义务自动判通过。

## 必要验证

```bash
.venv/bin/python -m pytest -q tests/test_critic_features_v013.py tests/test_online_support_v013.py
```

覆盖真实世界观察的状态通道、严格过去截点、未知枚举、固定三角色与 inactive 零填、可信失败保留、无动作、未知回报、实际适配器/profile/窗口混入、未启动分母与不同活动成员政策映射。测试中的合成 token/策略身份只用于接口反控制，不能报告为真实模型支持。


## 闭合 episode 的在线桥接

`export_online_rollout(episode, window=..., members=..., independent_capture=..., reward_spec=...)` 只读闭合历史，调用新的 scoped reward，保存原新奖励对象、原成员/政策/经历与 `online_scope`（奖励 spec 原文及哈希）。内部 `assess_online_validity` 复用记录/权限检查，再组合 scoped evaluator 从实际工作谓词独立产生的 basis/delivery；不比较 `reward == 1`，也不拿新奖励替换旧 RewardSpec 归档。

实际 CPU 规则控制已验证：仅承担 handoff 或 implement 的片段可以在没有全团队批准的情况下满足自己的 V；只读未交接的 handoff 获得局部奖励但 delivery=false。缺独立端口 capture 保持 record unknown。规则准备仍是 rule 来源，不变成当前模型支持。新的读操作还须匹配正式 commit receipt 的 contract 名称，不能把公共日志字段重命名当成新实际读取。

## 已知未发生生成的 direct 上下文预算停止

`MemberView` 更新为 `member-view-v0.13`。仅对 resident direct 的有限合同识别明确未抽样情况：唯一一次 finished `backend_context_limit` attempt、HTTP400、`transport_kind=resident_direct`、`generation_started=false`、当前完整 actor/window 身份、明确且确实超限的 token 长度，以及同 call 的实际 `model_boundary_error(status=model_budget_exhausted, backend_error.code=context_length_exceeded)`，同时没有 model_response。

这条记录保留实际请求和原 `non_generation_response`，标 `actor_required=false`，不增加生成数、不产生输出 token，并保留该成员此前完整实际动作。普通 HTTP 错误、重试、缺边界、错误 actor/window、未证明超限或生成已开始都不能走此分支。预算截断仍原样记录，不冒充自然任务终止。旧 HTTP 历史没有这个声明，不会被追溯认定为未抽样。


## 已闭合但后处理不可用

`closed_unassessed` 必须提供实际 episode 路径与 manifest SHA；检查其正式 `status=closed` 和冻结政策绑定。它保留在真实已闭合数量 `closed_joint_M` 中，不被改成未尝试、未闭合或 reward0。包含该类记录的 ξ 块不估 b/v，`support` 与 `Q_equals_B` 为 null；只保留基础分支的原始权重 1 与已知 actor mask，该未知 slot 的 mask 为 false。其他可信闭合样本仍由训练器独立判断，不因为组合支持未知而全被拒绝。

额外 CPU 假 transport 集成测试见 `tests/test_online_collection_v013.py`：提前 done 的 provider 不占用 implementer/reviewer 的各自预算；真实准备事件在 episode 外；工具参数拒绝不使角色提前退休；读取后处理故障保留闭合事实和未知评价。这里的假 completion/token 是显式测试夹具，不是模型工作能力或学习效果的证据。


## v0.13.1：record 检查传递真实窗口

O0 的真实 legacy 上下文 400 暴露了一个接缝：原 record helper 为 `member_view` 构造 `window={}`，因此无法验证明确未生成响应的 `online_window_id`。完整 TeamRollout 本身可以正确恢复此前两次生成，而旧 V.record 被保守置 unknown，进而使基础准入排除整条 slot 的活动角色。该错误没有伪造成功或奖励；O0 是评价模式，没有更新参数。

修订后 `export_online_rollout` 将已冻结的真实 window 显式传入 `assess_online_validity` 与 common record helper，并核对实际政策映射；测量标识升级为 `online-scoped-validity-v0.13.1`。没有绑定或绑定错误仍保持保守，不能从响应自己声称的 window 反推依据。

独立只读复核见 `docs/experiments/v013-context-window-binding.json`：保留旧完整源模块与原 R/V/support，在新测量下 legacy 个例的 record 从 unknown 变 true、此前真实动作恢复基础 mask；其 R0、basis/delivery 失败与无重配支持不变。新接口 R.25 与 R1 个例的原结论保持一致。没有覆盖原始归档，也没有重跑模型或世界动作。CPU 采集器回归同时覆盖了该真实闭合路径。

## v0.13.1 记录测量修订

`assess_online_validity` 将调用方已经冻结的 window 传给公共 record 检查，验证 manifest 的实际 policy-map SHA；不从模型返回体猜窗口。这样，本地可信服务在生成前因上下文预算拒绝，且绑定 actor/窗口和真实预算结束齐全时，不会误判成丢失了必需生成。缺失或错误窗口仍保守返回unknown。有效性 spec_id升至online-scoped-validity-v0.13.1，原v0.13结果留存；R及工作业务事实没有随该修订变化。

已闭合后评价失败仍单列closed_unassessed；其真实closed_joint_M保留，support及Q未知，不把它改成未尝试或0奖励。程序收到KeyboardInterrupt/SystemExit时保留当前真实计数并明确interrupted；未启动的下个窗口不得凑入经验分母。
