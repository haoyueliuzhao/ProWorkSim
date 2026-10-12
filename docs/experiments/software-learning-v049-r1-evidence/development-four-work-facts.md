# v049 原 B 开发四槽：只读终态事实

本文件是原 `runs/software-learning-v049-resume-r1/dev-B` 在监督器 `closed_with_unknowns` 时的独立证据摘要。只读取已保存 JSON、事件、SDK 和世界档案；没有重跑模型、使用 GPU、分词、测试、验收、导出或修改原件。用户后来授权的问题修复和接续应另记来源阶段，本文件不提前记作已经执行。

| 原冻结槽 | seed / 先手 | 正式状态 | R / Q | 完整回包 | 已知回包 token | 预约扣账 | 成员测试 |
|---|---|---|---:|---:|---:|---:|---:|
| DA-s1-B | 202610120591 / 001 | 闭合 | 1 / 1 | 33 | 491926 | 491926 | 7 |
| DA-s2-B | 202610120592 / 001 | 技术未知、中断 | null / null | 4 | 39347 | 52396 | 0 |
| DB-s1-B | 202610120593 / 002 | 未启动 | null / null | 0 | 0 | 0 | 0 |
| DB-s2-B | 202610120594 / 002 | 未启动 | null / null | 0 | 0 | 0 | 0 |

完整四槽 `F_B=null`、`Q_B=null`；不能把唯一已知 R1 写成四槽 F=1，不能把中断或未启动补为 R0。Q±因事前封存 `no_admissible_I_direction` 为 not_applicable，未执行。

原开发共40决定、38已派发 attempt，其中37完整回包；已知输入505154、输出26119、合531273 token。另1次不确定 attempt 按13049预约扣账，开发账本总544322 token，但完整实际 token 仍为 null。7成员测试、2执行前共享预算拒绝；没有已记录的 context 或成员 fixed 拒绝。开发 GPU3 worker 时长1338.457052230835秒，读取原监督器值，不与回合或模型嵌套时长重复相加。开发阶段新 actor/critic step 均0。

## B 状态绑定与 guard

`loaded-state.json` 指向真实 update-B checkpoint，完整状态重载标记 `serialized_reload_exact=true`，actor/critic=4/4，状态 digest `ff8c828bcc475132d6d6bbddad3a114da62ace9da9c905e560d7d7c5a3cefc39`，actor adapter `06f997903cd7d9bf8fb5dba403d5fe831619a1d871faec8e4699576a55154bcf`。共同3/3恢复记录是宿主初始来源，开发实际随后加载的是更新后的B。

DA-s1 的正式结果和 DA-s2 的原 `model-scenario.json` 均明确记录 branch B、同一 checkpoint digest、起始 actor4/critic4/policy_revision4；DA-s2 第5请求的预算准备和 runner-turn 也绑定同一 actor。这里是新增只读佐证，不回填原报告器因缺 `slot-result.json` 而保留的字段 null。

两槽的 `evaluation-guard.json` 实际都存在，learning_unchanged、rng_restored_exactly、software_binding_unchanged、actor_identity_unchanged 均true，两槽 actor/critic及optimizer hash一致。两槽 frozen-collection-close 均记录 evaluation_only_no_learning_computation、4/4、0学习计算。外层 `collection-guard.json` 缺失，worker `success_boundary=false`；不可把单槽 cleanup guard 写成整个四槽开发完成。

## DA-s1：固定成功、预算闭合，无本槽休眠唤醒或伙伴采用链

原 R_joint/R_token=1、Q_joint/Q_token=1，私有合同12/12；无行政删失。最后唯一固定交付为001的 `delivery-1`、v3，files SHA `e26cf48ba832a52f1ca01003aac52cb4536d4bff60d29f69046523049545379b`，绑定测试世界事件10，在事件19提交，included_patch_ids为空。之后仍有世界编辑20/21/29/34和伙伴后来的固定patch，原验收只绑定上述已固定交付；本分析没有补验后续未提交工作区。

001有17完整调用、256658 token；002有16完整调用、235268 token。共7次本人公开测试（001三次、002四次），3次普通格式拒绝、1次 submit_integration 工具业务拒绝；它们与2次无生成的团队预约拒绝分开。预算末余额8074，小于后续请求预约，原停止原因为两名成员各自 team_budget_exhausted，机械判定continue，无全局违规或未决。

初始任务表为空；001在世界事件12创建任务、14认领，终态该任务owner=001。终态仍是原001/002两个live身份、无新出生或永久退休。没有staff_done、休眠边界或唤醒事件，两人停止来自预算，不可套用训练槽的“休眠后唤醒”结果。

原动作没有 work_message、adopt_candidate、integrate 或带patch_id的读取；没有已证的具体伙伴固定成果使用链。伙伴公开信息是否被语义使用不作推断，不能把共享任务可见性直接当使用或因果贡献。

33反馈全部保留，31有同成员后续实际生成并首次呈现，2因团队预算无后继；33实际输入原机械测量通过。7测试报告目录/首段均实际呈现，0补读页、0历史全页呈现；这不是必须全读的要求。

## DA-s2：第5次生成中断，费用与正式结果保持未知

原第5请求为001、`model-35a28f9cc1265cb061b2c3c6`。experience 103开始调用，104只是prepared_not_dispatched，105真实派发，106记录actual_generation_started=true，107派发失败；不能只取104的false而说没有实际生成。请求准备 P11001+O2048=13049，fits18432=true，预约前余额460653，故不是容量或共享/成员预算拒绝。

`request-00005` 留有original/selected request、projection、budget-preparation、runner-turn和feedback lifecycle，但无response.json；无第五model_response、policy_decision或工具动作。实际输出长度、完成输入消费/部分生成程度与实际用量未知。账本attempt_started/dispatch_started均true，按 `uncertain_attempt_charged_reservation` 扣13049，reported_usage=null，末账本52396、余额447604。账本中的response_body_sha256不能替代缺失的完整模型回包。

四完整回包的已知39347 token来自38941输入+406输出；已执行动作只有list_files×2、read_file×2，世界档案仅2个read事件，0编辑/测试/固定/提交。原件没有第五世界动作；这不意味着第五生成计算或token耗用为0。

原interruption为KeyboardInterrupt/signal15、episode_closed_before_error=false；软硬截止均未触发，未锁提交、final_assessment_calls=0，正式slot-result和mechanical-measurement不存在。episode档案的manifest.status=closed只说明中断档案封口，其termination明确interrupted、business_result=null、continuation=false，不是业务正式闭合。本文件不推断信号来源。

## 精确恢复的证据边界

原World end快照、SDK持久化、运行时和共享账本都在，B参数身份也已证。但001 SDK base_state停在running和最后user leaf，002为paused；最终runtime保存5机会/4动作，而最后已完成机会checkpoint保存4/4。第5完整回包、实际费用以及逐请求生成RNG/部分生成状态未见保存。

源代码的evaluation guard在finally中把Torch CPU/CUDA RNG恢复到**槽前**内存快照，只将hash写入收条；它验证学习未变，并不保存可续算第5生成的RNG张量或原子SDK/World/账本状态。因此当前保留证据不足以认定DA2可安全精确恢复；不能凭guard=true重试第5attempt、重采该槽、抹除原不确定扣账，或虚构终态。

原两个DB目录不存在、从未开始。授权后以真实B checkpoint和原DB初态/seed/先手作首次执行，与恢复DA2中断生成是不同操作。原DA2应继续保留未知及全部原件；即使两个DB以后完成，若DA2仍未知，完整原四槽F_B也仍null。

机器JSON保留逐项源文件SHA、原动作、拒绝、账单、固定交付、起始绑定、两类guard和恢复边界。本摘要没有将单槽成功解释为学习收益、一般协作收益或Contribution。
