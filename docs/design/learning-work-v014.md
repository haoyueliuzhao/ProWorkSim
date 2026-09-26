# v0.14 显式业务情境与有限工作后果

日期：2026-09-26。实现入口为 `templates/learning_work.py`；旧 `online_work.py` 的 v0.13 注册表和历史八例不改写。本设计继续使用同一个构造 SQL 家族，内部锁定池不构成独立来源。

## 情境声明

注册表有 40 个实例：train、development、locked_facts、locked_information、locked_rules 各两个事实配置，每个配置派生 handoff、implement、review、chain 四项责任。四任务份额仍各 1/4。是否重复同一精确情境、重复次数及窗口数由正式在线协议冻结，注册表不按成功补采。

每个配置显式给出期间、纳入状态、金额倍数、去重方式、订单下界（含）和上界（不含）、业务依据持有者、审计依据持有者、待复核提交正确性、金额列表和是否有旧版本。没有依据种子奇偶选择状态或倍数的规则。train/development 使用 distinct_orders；locked_rules 增加 transaction_rows 和倍数 3；locked_information 将业务依据交给 reviewer、审计依据交给 provider。所有这些都是同源条件变化，不能用来声称新来源泛化。

每份数据都有重复订单、恰好落在上下界的订单、界外订单、另一期间记录、不同状态及无合格交易的客户。`basis_meta` 和审计材料写明业务规则值；公开合同只描述字段语义，不提供正确 SQL、数值结果或私有规则答案。业务内容由已有 `decision_team_sql` 检查器独立用 Python 对确切来源计算，SQL 运行的自定义测试不充当真值。

`controlled_pair()` 另声明一对公共目标、期间、数据、布局相同而私有状态/倍数不同的开发反事实。它不进入 40 例默认注册表和正式训练混合。CPU 输入合同测试在两个隔离目录构造相同公开 UUID，比较未经修改的实际 ModelPolicy request；这只是排除身份噪声后的私有信息可见性对照，不是两个独立生产世界，也不是模型行为收益。

## 真准备与责任范围

implement 在目标 episode 之前通过实际读、交接、采用准备；review 继续实际修改、执行 SQL、固定提交，并在交换布局中实际送达审计材料。正确和错误提交由显式配置决定；错误控制是真实 SQL 计数加一，仍然经过实际执行和提交。前缀保存在 preparation.json，新目标 recorder 从空开始，不记作当前模型动作或奖励。

所有准备调用使用按 case、actor 和实际准备次序确定的 request_key。相同 case 重建后的业务状态摘要逐项一致，保留命令、逻辑时钟、版本和文件字节，沿用 `initial_business_state` 原有的诊断身份排除，不删除业务差异来合并支持池。

公开规则见证使用与模型同一个 StaffRuntime 和 `run_fragment`。每个机会最多一次动作；wait 和 done 同样计入决定预算。provider 结束不会截断 implementer/reviewer 的剩余责任。预先声明期限：handoff 的实际资料持有者 4；implementer 短实现 10；reviewer 短复核 8；chain provider/implementer/reviewer 分别 6/12/14。期限不是依据模型结果事后加长。

完整链中的主动交接和请求后交接都由同一情境内三成员真实决策完成。请求路径使用真实 request_information、read_messages、request_id 和 handoff；没有环境自动答复，也不把单 provider 短交接当成三成员方法支持。

## 奖励与联合时间线

v0.14 沿用四项责任的 v0.13 终局权重和准入事实。新的 basis_provider 字段把交接义务绑定到实际公开路由持有者。独立复核继续要求确切固定 code/result、数据和适用审计依据；错误批准、虚假定位和晚读补证不能获得决定分。

`reward.ledger` 仅为可信闭合 episode 产生，所有 sequence 都取自该 episode 的真实联合事件。中间结算仅限于当时即可独立确认的不可变适用依据读取（短交接 0.25）和实际 applied 交接送达（短交接 0.75、完整链 0.2）。送达结算用匹配 event_id 的 environment_event 位置，不用早于送达的发起位置；若没有对应记录，不伪造早期时间。

读取所采用输入、实际 build、固定提交和复核依赖终态选择或可撤销状态，因此本轮保守地在终点结算，不根据后来的成功反选早期动作。最后总有 `terminal_contract_reconciliation = R - 已结算金额`；必要时可以是负值，确保撤销/失效后的总额严格回到原终局合同。实现不把每次成功调用变成奖励，也不修改终局 R。

训练侧 terminal_mc 与 joint_reward_to_go 的比较属于基础信用分配。成员 token 平均的现有 surrogate 仍保留其归一化特点，本设计不据此声称严格无偏等价，也不将这一改动当成 ID-VTDO 创新。

## 必要验证及解释边界

`runs/learning-work-v014-dev1/report.json`：40 个实例的主动规则路径，加 10 个完整链请求路径，50/50 完成各自完整成果；6/6 负控得分符合预设。真实决定数（包含等待和 done）：handoff 3；implement 6；review 7；chain provider 3–4、implementer 8–9、reviewer 11–12。reviewer 的完整链等待为 2–5 次，均计入预算。

负控包括沿用旧 SQL 规则、错误计数、错误批准、无依据错误定位、无目标动作和只读未送达。前两者只得读取输入 0.2；错误批准/错误定位只得复核证据 0.25；无动作 0；只读 0.25。规则见证建立可核验路径与期限可操作性，不说明目标模型会走该路径，也不说明参数学习有效。该 CPU 开发运行开始后做了确定性准备键与公开回执投影接入的后续修订；定向测试覆盖了这些修订，未把旧运行改标为冻结模型实验。

`tests/test_learning_work_v014.py` 与受影响的旧在线奖励回归合计 16 项通过。受控信息对另有持久化记录 `runs/learning-information-v014-contract/test_receiver_actual_request_e0/`：保留两个实际请求数组及信息对报告。训练模块对 56 个可信闭合 reward ledger 的只读严格解析全部通过，验证每个位置、终点与总额，不重新采样模型。

## 脚本合理路径的输入容量（非模型结果）

随后仅对 development-f0 的 implement/review/chain 各一条主动合理路径比较 full_v14/compact_v14；未重复 50 例规则实验。`scripts/learning_capacity_v014.py` 使用公开规则策略选择动作，再由真实 ModelPolicy 构建请求、正式 `prepare_prompt(single_call)` 和本地固定 Qwen tokenizer 计算输入。没有加载模型参数、生成 token、行为 logp、参数更新或 TeamRollout 训练导出。程序传输中的 completion_tokens=1 是适配器假计数，不是实际采样输出。

完整路径在容量测量适配器中允许 32k，以观察后续步骤，另逐步计算 8192/12288 和 512 输出预留的超限；这个反事实允许值不改变真实模型对照的上下文限制。结果来自 `runs/learning-capacity-v014-dev3/`，每一步保留原 request、prompt 和 tokenizer input_ids，摘要归档为 `docs/experiments/learning-capacity-v014-cpu.json`。

| 任务 | full 最大输入+512 | compact 最大输入+512 | 8192 对业务动作的影响 |
|---|---:|---:|---|
| implement | 9035 | 8423 | 两者仅提交后的 done 超限；本脚本提交动作仍可执行 |
| review | 9869 | 9302 | 第 6 决定 raise_issue 分别为 8809 / 8239，均超限 |
| chain | 10536 | 9908 | reviewer 第 10 决定 approve 分别为 9094 / 8463，均超限 |

六条脚本路径均未超过 12288。compact 在相关必要复核决策减少约 570–630 token，但仍不足以使这三条路径的所有必要复核动作适配 8192。此结论只说明呈现与输入容量，不能说明 Qwen 会选择合理路径，也不能把增加上下文与压缩的联合效果归因于单一因素。

最初两次容量开发尝试遗漏程序传输零价格配置，正常预算器在请求前阻止运行；首次报告器又因无数据报错。两处都只修正脚本，失败目录保留，后续 dev3 才是有效容量测量。受控信息对的原请求数组和报告分别归档到 `docs/experiments/learning-information-v014-actual-requests.json` 与 `learning-information-v014-cpu.json`；原请求字节比较没有做身份或字段归一化。
