# v051 HOLD 两成员接口的独立前置实现

新增 `software_holdout_world_v051.py` 和 `software_holdout_collector_v051.py`，不修改既有CAL2/O1模块或r3运行快照。唯一purpose为`held_out_checkpoint_evaluation`；training、Contribution和旧independent-confirmation资格均为false，另以holdout_evaluation标记本轮评估。此实现只用合成fixture完成接口控制，尚未读取HOLD业务内容、执行来源资格或放行模型。

## 两个真实成员与同一资源池

world建立operator缺陷baseline，以及001/002两个同初态但相互私有的工作树。任务表为空、没有预分工或人工初诊断，不额外添加contract.md、member测试脚本或隐藏成员。原问题直接作为root goal/contract观察；测试、配置与support只读。公共测试通过注入的repository provider执行原完整测试集合，world不假定底层是pytest还是unittest。结果仍使用原3072字符页，只有原测试成员可读其报告。

两成员均可发布固定patch；伙伴只可读取/精确采用合法共享版本，adopt_candidate不自动合并、测试或提交。采用后的当前版本仍须通过原测试/固定patch/主动submit流程。未发布的私有树及对方私有测试页不可访问。

collector复用v050严格O1的预算、轮转、休眠/唤醒、真实机会计数、局部停止和90+10分钟算法，worker使用原v049真实SDK wake hook。001/002是两个独立conversation，但共享同一actor和唯一128决定/128attempt/500000 token池；测试也是全队唯一32次。staff_done只结束当前工作，真实后继伙伴事件才能唤醒原会话，不重置历史或计量、不退休身份、不制造事件。新增装配函数绑定本次world/provider与独立window；原算法AST和源码引用另存控制摘要，不重跑旧O1全套。

`collect_episode(owner, prepared, folder, sampling_seed=..., slot_id=..., heldout_condition=..., checkpoint_authorization=...)` 只允许独立只读窗口`holdout-v051:<slot_id>`，18432/2048、nonthinking、temperature0.7、原EOS/pad、HF600秒及5400/6000秒不变。完整contract均绑定，禁止共享训练窗口。S_star要求历史4/4，其余状态5/5；实际owner的checkpoint、source_actor_identity、adapter SHA和完整retained_state_authorization必须等于传入授权。B/Q±同为5/5，条件标签到静态库存中具体授权的对应关系由独立host/measurement再绑定，不能凭步数区分。原loader继续承担真实state字节/tensor digest核验与仅加载actor的约束，本次控制没有读取权重。

## 固定提交是唯一HOLD业务端点

关闭时锁定最后合法固定提交，验收该精确source_reference/files SHA一次，过程合同与原行政删失口径分列。无提交时F/R_joint=0、content_correct未评估、宿主验收次数0；后续mutable编辑不改变已固定的验收对象。新增world不提供CAL2的assess_terminal_working_tree，collector也不调用native R grader或生成R_code/terminal_code。已提交树评分未知保持null。结果保留原R_joint/R_token/Q等口径，并新增F别名、heldout_condition、完整checkpoint授权、实际native calls路径及宿主验收次数。

## 必要合成控制与完整记录

首轮只运行五项新控制，pytest原结果为4 passed / 1 failed，未覆盖或重写。前四项通过，覆盖两个私有树/无初始工作、只读生产范围与角色观察、伙伴固定采用及私有分页、无提交零验收/固定树唯一评分/评分未知保留，以及四类actor的逻辑元数据绑定反例。所有测试返回均为明确的CPU程序fixture，不代表真实仓库验收。

第五项在固定SDK环境实际建立两个不同conversation，完整执行六条程序化响应：001休眠，002私有笔记不唤醒伙伴，002真实消息唤醒原001会话，两人最后休眠闭合。原worker/conversation对象和共享budget对象的身份断言通过；后续测试错将既有预算包络`team_budget.model.limits`写为`team_budget.limits`，在完整收口后发生KeyError。该失败、首次测试源码和完整SDK原件均保留。

修订只更正测试的预算字段路径，实施源码保持首次执行字节。没有重放SDK或重跑另外四项；从原档只读补完其余断言：六个程序响应/六个settled attempt、唯一共同池、两个conversation、一次真实后继事件唤醒且无reset、两角色新接口/purpose与空诊断、共同adopt工具、两身份live、无submit零宿主验收且没有终态工作树救援，全部通过。原累计2817计量单位来自合成64字符分块函数，不是模型token或真实tokenizer结果。只读补完回执不能改称首轮五项pytest均通过。

SDK导入时已有依赖尝试获取公开模型价格表失败后使用本地备份；这是依赖元数据访问，不是模型生成。原日志保留。新增实际模型、GPU、权重加载、真实repository测试、真实tokenizer、反向及optimizer均0。旧runner、O1、数值、来源资格和真实模型控制没有重跑。

原件、源快照、只读补完与最终摘要位于`artifacts/software-calibration-v051/hold-interface-controls/`。新sourceprovider/executor、measurement、host和独立准入由相应模块另行绑定；共同代码全部封存且CAL2解释完成前，不读取HOLD任务内容。之后仅按事前固定题目完成一次环境及初始实际tokenizer准入，失败原题保留阻断，不据HOLD结果调整共同实现。
