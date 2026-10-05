# v0.33 同根目标单／双执行诊断：完整实验报告

本轮已完成。北京时间 **2026-10-05 21:23:20**，接续监督队列正常闭合，两模型均正常退出并恢复原common。原4条经历经离线记录修复后，与后续12条合为原定16个逻辑槽，全部记录可信、完整回报已知，没有未开始槽或技术未知。

**完整交付为0/16：9B的S/T各0/4，Devstral的S/T各0/4；八个同根目标配对全部两侧失败。** 六条已提交交付均通过公开7项检查，但独立内容验收均未通过；另十条未提交，内容／过程保持未知。按事前规则没有新训练来源的局部团队载体，尚未开展B/G/I配置或参数训练。

本报告只读整理已完成原件，未重跑模型、代码验收或测试，未修改旧结果。完整机器证据见[最终机器汇总](software-paired-o1-v033-final.json)；[接续自动报告](software-paired-o1-v033-recovery.md)及其[数据](software-paired-o1-v033-recovery.json)、[原停止报告](software-paired-o1-v033.md)继续保留。自动终态报告已推送为`96867f4`。

## 1. 问题、实验单位与固定条件

本轮补上同一O1根目标的单执行者S／双成员T比较。它用于观察完整交付受到领域合同、接口手续与组织过程的哪些限制。两个根目标是ledger导入／审计和settings部分更新，均沿用原公开业务合同、源代码及独立验收；它们属于已有开发池，不能称为新来源独立确认。

| 对象 | 固定设置 |
|---|---|
| 模型 | 当前Qwen3.5-9B端点；Devstral-Small-2507 |
| 规模 | 两模型 × 两根目标 × S/T × 两seed = 16条，一次有限诊断 |
| seed | s1=`202610050701`；s2=`202610050702` |
| 顺序与先手 | s1每root先S后T，T先A；s2先T后S，T先B；S均为A |
| 初始组织 | 空任务表；模型自行创建、领取和调整工作；没有预设库／consumer岗位或额外经理 |
| 信息与副本 | S一个实际工作副本，获得T合法初始信息并集；T两个私有副本、局部历史、显式发布／导入 |
| 参数 | 每模型唯一当前actor；T两个会话顺序使用相同参数，窗口内不更新 |
| 团队总额 | 每槽128决定、128模型attempt、500000实际调用token、32次run_tests；S/T相同 |
| 生成 | 上下文16384、单次最大输出2048、temperature=0.7、resident top_p=1.0／top_k=0 |
| 执行 | 单owner单张A100 80GB，最多两个模型owner并行；无新增模型下载 |

共同总额不按人数翻倍，也没有每成员64决定的硬拆分。token以实际选中prompt加最大输出做生成前预约，再按真实usage结算；测试按实际run_tests调用计数，内部公开／成员脚本及控制器独立验收的范围另有记录。单槽最高额度相同，不要求实际消耗相同。

实际SDK保留完整会话原件，生成上下文使用冻结的首个与最新观察及最后四轮工具往返投影。9B使用官方Qwen原生工具模板、关闭thinking；Devstral使用原官方Mistral tokenizer路径。两者保留BF16主干、FP32 LM head／LoRA及原数值配方。9B起点actor／critic累计3／3，Devstral为0／0；这些是此前学习状态，不是本轮更新。slot seed逐槽重置，不能将recipe中的初始seed误作实际slot seed。

完整规范及来源边界见[原协议](software-paired-o1-v033-protocol.md)、[用户审计](../reference/audit-v032-next-v033.md)和[修复接续协议](software-paired-o1-v033-recovery-protocol.md)。

## 2. 执行谱系与记录恢复

| 阶段 | 源码／记录 | 实际新经历 | 实际模型调用 | 说明 |
|---|---|---:|---:|---|
| 原v0.33 | `6325ddb`；原停止报告`74923c1` | 4 | 138 | 每模型执行ledger-s1的S/T后，被生成前预算拒绝的记录解释缺陷阻断 |
| CPU离线恢复 | 修复源`ab6cd08`所绑定的解释器 | 0 | 0 | 保留原归档、业务验收和token；两条T的record未知纠正为可信 |
| r1接续 | `ab6cd08`；终态报告`96867f4` | 12 | 437 | 仅运行原来未开始的六槽／模型；四条原经历不重采 |
| 本轮去重合计 | 原16个逻辑槽 | **16** | **575** | 没有把恢复导出算成新经历 |

原缺陷是新的`team_budget_exhausted`生成前拒绝没有旧`model_budget_stop`事件，成员视图误将真实未生成的调用当成缺失response。修复以原call／成员／身份／窗口、封印准备、边界及最终团队账、真实usage算术和零attempt／response／动作证据判定；原事件和模型输出均不改。其余生产源码中194个文件与原冻结版本字节一致，仅成员记录解释和跳过已执行前缀的采集代码变更。

原两S entry保持相同；两T只修正记录有效性，业务结果使用原独立验收，仍为R=0。旧约2.1GB归档前后全树SHA一致：`66c2684e249e6aa0a7b8db07887d45c0f875071c68488620f85175619736aa2a`。一次开发期CPU派生导出被中断且保留了未完成目录；正式恢复随后完整通过，此事没有产生额外模型、episode或业务验收。详情见[修复启动记录](software-paired-o1-v033-recovery-launch.md)。

本轮完成后，接续12槽中实际保存了9次严格共享token预算“未生成”证明，另有5次旧个人预算停止；原4槽对应4次共享证明和1次个人停止。合计19次未生成机会，加575次实际模型尝试，等于594次决定。真实context容量证明和个人／共享混合账本分支的触发数均为0；它们有CPU控制，不能写成此次真实模型已经触发。

## 3. 完整结果与分母

| 模型 | 条件 | 完整通过／可评 | 固定提交／槽 | 内容通过／已知 | 规定过程通过／已知 | 内容／过程未知 |
|---|---|---:|---:|---:|---:|---:|
| 9B | S | 0/4 | 1/4 | 0/1 | 0/1 | 3 |
| 9B | T | 0/4 | 2/4 | 0/2 | 0/2 | 2 |
| Devstral | S | 0/4 | 2/4 | 0/2 | 2/2 | 2 |
| Devstral | T | 0/4 | 1/4 | 0/1 | 0/1 | 3 |
| 合计 | S+T | **0/16** | **6/16** | **0/6** | **2/6** | **10** |

内容维度保留原期望值、异常、输入保持和公开／上游义务；规定过程维度沿用独立验收的`source_api_used`，检查指定load／dump路径。它不是完整工程过程的形式证明，完整R仍须固定交付和全部原义务同时满足。

“可评”指该episode的完整交付回报可以确定，不表示所有可变代码都接受了独立内容测试。未提交的十条按缺少固定交付记R=0，内容与过程保留未知；不能把0/6内容验收写成0/16已测内容。

规定过程2/6通过，另外4份判定为未通过。其中三份ledger有明确load=true、dump=false证据；一份Qwen settings交付的独立检查抛异常、没有输出source_api_used map。后一项不能解释为“模型未调用任何load/dump”，下文单列。

| 模型 | 根目标 | seed | S完整R | T完整R | T−S | 配对结果 |
|---|---|---|---:|---:|---:|---|
| 9B | ledger | s1 | 0 | 0 | 0 | 两侧未通过 |
| 9B | ledger | s2 | 0 | 0 | 0 | 两侧未通过 |
| 9B | settings | s1 | 0 | 0 | 0 | 两侧未通过 |
| 9B | settings | s2 | 0 | 0 | 0 | 两侧未通过 |
| Devstral | ledger | s1 | 0 | 0 | 0 | 两侧未通过 |
| Devstral | ledger | s2 | 0 | 0 | 0 | 两侧未通过 |
| Devstral | settings | s1 | 0 | 0 | 0 | 两侧未通过 |
| Devstral | settings | s2 | 0 | 0 | 0 | 两侧未通过 |

八对均失败，只有本轮端点回报差为0这一描述。单执行者也未完成同样根目标，因此不能将团队全零仅归因于协作负担；两边均未越过完整交付门槛，也不足以证明两条件能力相同或协作没有作用。两root、两seed和同一开发来源不构成总体稳定性或泛化估计。

## 4. 逐槽成绩、消耗与终止

所有行record=true、完整R=0。原来源“原”表示原4条经派生记录恢复，“续”表示新执行12条；s1/s2含义见第1节。内容／过程“—”表示没有固定交付可供独立验收。

| 模型 | root | seed | 条件 | 来源 | 提交 | 内容／过程 | 调用 | 实际token | 测试 | 最终终止 |
|---|---|---|---|---|---|---|---:|---:|---:|---|
| 9B | ledger | s1 | S | 原 | 无 | — | 38 | 487,601 | 7 | token预算 |
| 9B | ledger | s1 | T | 原 | 有 | 未通过／未通过 | 43 | 497,662 | 4 | token预算 |
| 9B | settings | s1 | S | 续 | 无 | — | 38 | 491,248 | 7 | token预算 |
| 9B | settings | s1 | T | 续 | 有 | 未通过／未通过 | 42 | 492,720 | 5 | token预算 |
| 9B | ledger | s2 | T | 续 | 无 | — | 40 | 491,375 | 5 | token预算 |
| 9B | ledger | s2 | S | 续 | 有 | 未通过／未通过 | 18 | 220,347 | 3 | 角色主动完成 |
| 9B | settings | s2 | T | 续 | 无 | — | 40 | 493,649 | 7 | token预算 |
| 9B | settings | s2 | S | 续 | 无 | — | 39 | 494,972 | 6 | token预算 |
| Devstral | ledger | s1 | S | 原 | 有 | 未通过／通过 | 15 | 184,511 | 2 | 角色主动完成 |
| Devstral | ledger | s1 | T | 原 | 无 | — | 42 | 495,884 | 2 | token预算 |
| Devstral | settings | s1 | S | 续 | 无 | — | 38 | 492,656 | 11 | token预算 |
| Devstral | settings | s1 | T | 续 | 无 | — | 39 | 493,957 | 10 | token预算 |
| Devstral | ledger | s2 | T | 续 | 有 | 未通过／未通过 | 27 | 310,946 | 2 | 角色主动完成 |
| Devstral | ledger | s2 | S | 续 | 无 | — | 37 | 494,152 | 11 | token预算 |
| Devstral | settings | s2 | T | 续 | 无 | — | 41 | 489,178 | 8 | token预算 |
| Devstral | settings | s2 | S | 续 | 有 | 未通过／通过 | 38 | 487,811 | 8 | token预算 |

13/16个episode至少一成员最终因token预约额度不足停止；按角色计为19/24个role-episode，另5个角色主动completed。两种分母不能混用。十个未提交episode全部落在这13个预算终止episode中；另三条预算终止经历已有固定提交但验收失败。三条全角色主动completed的episode也均未通过完整验收。

预算停止时仍有2338—12399 token，但不足以容纳下一次实际prompt加2048最大输出预约；这些未生成调用无模型输出和token收费。观察到预算边界不证明更大预算会完成工作，也不能将所有失败都解释为预算不足。未触发额外普通格式退休；最终完整16槽没有技术未知。

## 5. 六份固定交付的具体失败

六份最终交付全部通过当时公开7项检查，独立内容验收全部失败。下面列出的未知字段、金额语法／精度、Schema使用、默认值和完整加载状态都是事先公开合同中的义务，没有为解释结果新增隐藏要求。机器汇总的`submission_review.submissions`保留每条原assessment的JSON pointer、固定bundle／源码／合同引用与SHA、expected／observed。

### 1. 9B ledger s1 T

- 精度用例第一行 `{"id":"x","amount":"0.01","ignored":true}` 应忽略未知键并接受；实际将 index=0 判为 invalid，遗漏 x/0.01。
- 大金额 z 应输出 1000000000000000.02，实际为 1000000000000000.00；总额应为 1000000000000009.93，实际为 1000000000000009.88。
- 三个独立用例均记录 LedgerSchema.load=true、LedgerSchema.dump=false；合同要求consumer同时使用该schema的load与dump路径。

**基于封存代码的解释，非新执行验证：** 交付LedgerSchema未配置Meta.unknown或load的unknown选项；封存Marshmallow的默认未知字段策略为RAISE，且consumer直接load原row。此静态路径与该合法行被拒绝一致。 交付代码使用整数cents除以100或100.0后以浮点格式化金额/总额；此路径与封存大金额尾数丢失一致。未重新执行数值计算或修改交付。 consumer手工构造accepted金额和total，封存代码中没有调用schema.dump；此代码事实与测得dump=false一致。

原件：[assessment.json](/data1/zhuxinrui/projects/ProWorkSim/runs/software-paired-o1-v033/qwen3.5-9b/actual/diagnostics/slot-1/assessment.json)；SHA256 `0d457afc347ea92de572f1687ebdf406b050e7a4e4114f24c60cdd006af777d9`。

### 2. 9B settings s1 T

- secret-and-default用例应忽略base.irrelevant和patch.extra、更新host/token、将port载入为443并补retries=3；实际抛ValidationError：{'irrelevant': ['Unknown field.']}，没有返回约定结果。
- 该异常check的observed只有kind/type/text，没有source_api_used，因此原过程维度为false；其余三个独立settings用例明确load=true/dump=true。

**基于封存代码的解释，非新执行验证：** SettingsSchema未配置unknown=EXCLUDE；复制后的result保留base.irrelevant，最终load抛错后恢复分支再次load同一base，异常逸出。此路径来自固定代码，未重跑。

原件：[assessment.json](/data1/zhuxinrui/projects/ProWorkSim/runs/software-paired-o1-v033-recovery/qwen3.5-9b/actual/diagnostics/slot-3/assessment.json)；SHA256 `16b100187b73bb899898a427bec63c3d3f67ee6c4c97ad7a06645ce1fcee4028`。

### 3. 9B ledger s2 S

- 精度用例第一行 `{"id":"x","amount":"0.01","ignored":true}` 应忽略未知键并接受；实际将 index=0 判为 invalid，遗漏 x/0.01。
- 此份交付的大金额z为1000000000000000.02，与期望一致；总额为1000000000000009.92，较期望1000000000000009.93少0.01。不能将其他ledger交付的浮点精度缺陷套用于本槽。
- 三个独立用例均记录 LedgerSchema.load=true、LedgerSchema.dump=false；合同要求consumer同时使用该schema的load与dump路径。

**基于封存代码的解释，非新执行验证：** 交付LedgerSchema未配置Meta.unknown或load的unknown选项；封存Marshmallow的默认未知字段策略为RAISE，且consumer直接load原row。此静态路径与该合法行被拒绝一致。 consumer手工构造accepted金额和total，封存代码中没有调用schema.dump；此代码事实与测得dump=false一致。

原件：[assessment.json](/data1/zhuxinrui/projects/ProWorkSim/runs/software-paired-o1-v033-recovery/qwen3.5-9b/actual/diagnostics/slot-5/assessment.json)；SHA256 `331bb104252f9c08583eeea03c0cebf7f758e33217d18c2840db67e2b4e845f5`。

### 4. Devstral ledger s1 S

- 精度用例第一行 `{"id":"x","amount":"0.01","ignored":true}` 应忽略未知键并接受；实际将 index=0 判为 invalid，遗漏 x/0.01。
- 大金额 z 应输出 1000000000000000.02，实际为 1000000000000000.00；总额应为 1000000000000009.93，实际为 1000000000000009.88。

**基于封存代码的解释，非新执行验证：** 交付LedgerSchema未配置Meta.unknown或load的unknown选项；封存Marshmallow的默认未知字段策略为RAISE，且consumer直接load原row。此静态路径与该合法行被拒绝一致。 交付代码使用整数cents除以100或100.0后以浮点格式化金额/总额；此路径与封存大金额尾数丢失一致。未重新执行数值计算或修改交付。

三个独立用例的LedgerSchema.load/dump均为true；本槽是内容失败，不能归因为未使用指定API。

原件：[assessment.json](/data1/zhuxinrui/projects/ProWorkSim/runs/software-paired-o1-v033/devstral-small-2507/actual/diagnostics/slot-0/assessment.json)；SHA256 `1878f12f449408ed9eaa3f3f35c0a9abd47a185014538f3baa89e2491ee72cd1`。

### 5. Devstral ledger s2 T

- 大金额 z 应输出 1000000000000000.02，实际为 1000000000000000.00；总额应为 1000000000000009.93，实际为 1000000000000009.88。
- 非法格式用例 index=3 的 amount=".5" 应判invalid；实际接受 d/0.50，导致该用例总额由期望5.00变成5.50。
- 三个独立用例均记录 LedgerSchema.load=true、LedgerSchema.dump=false；合同要求consumer同时使用该schema的load与dump路径。

**基于封存代码的解释，非新执行验证：** 交付代码使用整数cents除以100或100.0后以浮点格式化金额/总额；此路径与封存大金额尾数丢失一致。未重新执行数值计算或修改交付。 replace删除小数点后只检查isdigit，随后拼接空整数部分与小数部分；没有要求小数点前至少一位数字，与误接受.5的记录一致。 consumer手工构造accepted金额和total，封存代码中没有调用schema.dump；此代码事实与测得dump=false一致。

原件：[assessment.json](/data1/zhuxinrui/projects/ProWorkSim/runs/software-paired-o1-v033-recovery/devstral-small-2507/actual/diagnostics/slot-4/assessment.json)；SHA256 `ba0a3f53e00a75d7aa781d0a4108c546115e471b7e774ac995c935f4e39292b3`。

### 6. Devstral settings s2 S

- secret-and-default合法patch应返回ok=true、host=backup.org、token=new；实际ok=false，host仍example.org、token仍old，并把原base.irrelevant保留在state。
- 该用例还要求返回完整加载状态：port应为整数443、retries应补3；实际state.port仍为字符串"443"且state/public都缺retries。

**基于封存代码的解释，非新执行验证：** 最终生效Meta使用default_unknown而非封存Marshmallow读取的unknown；patch含extra，schema.load(patch,partial=True)会落入未知字段拒绝路径。这是与已记录ok=false相符的静态解释，内部异常内容未单独记录。 Field未设load_default；Meta.default不是该字段的默认值配置。异常分支返回原base，且成功路径也未采用load(new_state)返回值。这里只报告封存失败用例观察到的字符串端口与默认值缺失，不外推未跑输入。

四个独立用例的SettingsSchema.load/dump均为true；本槽是内容失败，不能归因为未使用指定API。

原件：[assessment.json](/data1/zhuxinrui/projects/ProWorkSim/runs/software-paired-o1-v033-recovery/devstral-small-2507/actual/diagnostics/slot-7/assessment.json)；SHA256 `44b4ee1069e965baac404828c76d9e2b31c21cdaa8b6ac9c5aceea04552df353`。

由这些交付可确认：公开测试绿色、成功固定版本或调用了规定API，都不能替代完整内容正确性。将过程约束全部取消也不会让这六份交付的已测内容全部通过；本报告不改变原合同或分数。

## 6. 未提交经历与自主组织过程

十条未提交经历均没有成功submit_integration事件，也没有进入世界执行链的submit_integration工具调用；其内容未作隐藏补验。9/10没有成功固定patch，唯一例外是9B ledger-s2-T：B先因包含并非本人持有的任务而发布被拒，随后固定了本人任务patch，但没有导入或提交，最终团队token边界结束。9B settings-s2-S也有因任务责任不匹配而拒绝fix_patch的记录。

9B两个未提交settings-S的最后一次公开测试记录通过，但仍未完成固定提交；对其可变副本不追补独立分数。其他未提交经历可见的末次检查包括未过的公开或成员测试。所有结论都以记录过的版本／动作和终止边界为限，不能由这些局部迹象断言“只差一两步便能成功”。

| 模型／条件 | 创建任务 | 领取 | 编辑 | 固定patch | 显式导入 | run_tests | 提交 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 9B／S | 6 | 6 | 30 | 1 | 0 | 23 | 1 |
| 9B／T | 9 | 8 | 28 | 3 | 1 | 21 | 2 |
| Devstral／S | 3 | 3 | 41 | 2 | 0 | 32 | 2 |
| Devstral／T | 11 | 6 | 35 | 1 | 0 | 22 | 1 |
| 合计 | 29 | 23 | 134 | 7 | 1 | 98 | 6 |

这些是已提交世界事件次数，不是独立产物数、合理分工数或贡献权重。初始任务表为空，后续任务确由模型创建。全16槽没有记录到task_revised、delegate、task_returned、work_message、dependency_declared、dependency_removed或handoff事件；八个T槽共有一次显式integrate。该结果描述了所用组织行动的范围，不意味着规定必须发消息／强制协作，也不能以动作次数替代方法支持或协作收益。

T中还可见15次“任务已被领取”的claim拒绝（9B 12、Devstral 3）；Devstral T有23次精确旧文本／可编辑路径不匹配的replace_file拒绝。这些是合法执行链路给出的工作错误反馈，不能与关键记录失真混称；它们提供了责任协调和编辑恢复断点的线索，尚无消融证明哪一种断点对最终失败贡献最大。

## 7. 接口修订的实测与证据边界

**可选备注确实被真实模型使用。** Devstral三次最终成功提交的参数均为`{}`，占全部六次最终成功提交的3/6；其source reference／SHA与最终assessment绑定，原message缺失手续不再阻止这三次提交。另一次Devstral空参数提交因为尚未固定该工作版本被拒绝，未计为成功。这说明备注放宽与固定版本守卫同时生效；三次成功提交仍全部独立验收失败。

| 模型／条件 | 格式拒绝 | 涉及episode／4 | 后续实际调用且携带反馈 | 下一次世界动作成功 | 普通格式退休角色 |
|---|---:|---:|---:|---:|---:|
| 9B／S | 7 | 4/4 | 6 | 5 | 0 |
| 9B／T | 6 | 2/4 | 5 | 5 | 0 |
| Devstral／S | 2 | 1/4 | 1 | 0 | 0 |
| Devstral／T | 1 | 1/4 | 1 | 0 | 0 |

按episode／成员／call_id去重，普通native／schema格式拒绝共16次；13次之后确有下一次实际调用且原反馈出现在该请求中，10次的下一次世界动作成功。这些成功指工具动作执行成功，不是业务完整交付。

本次没有观察到“达到旧连续2／累计4门后仍额外实际生成”的事件；达到边界处后续仍可能被token准入阻断。因此不能将CPU中连续五次错误仍可继续的控制写成真实模型收益，也不能声称移除额外退休门已产生因果改善。本轮没有接口单因素消融。

修复后的九次新增共享预算拒绝均在完整原件下解释为未发生生成，十二个接续槽随后全部正常闭合。这是此次记录修复的直接运行证据。context容量和混合预算证明仍只有本轮CPU覆盖，未在接续模型工作中实际触发。

## 8. 用量、时间与GPU成本

| 模型／条件 | 决定 | 实际调用 | 实际token | run_tests |
|---|---:|---:|---:|---:|
| 9B／S | 136 | 133 | 1,694,168 | 23 |
| 9B／T | 172 | 165 | 1,975,406 | 21 |
| Devstral／S | 131 | 128 | 1,659,130 | 32 |
| Devstral／T | 155 | 149 | 1,789,965 | 22 |
| 合计 | **594** | **575** | **7,118,669** | **98** |

实际token包括 **7,003,000 prompt token** 与 **115,669 completion token**。prompt是每次真实请求的累计量，包含重复上下文，不能理解为同等数量的新项目信息；completion也不等于本轮用于优化的token，因为本轮没有训练。S累计3,353,298 token，T累计3,765,371 token；实际用量可不同，两者共同上限相同，这也不是同等成功工作量下的效率估计。

下表均为2026-10-05北京时间。等待从对应监督器启动计至worker实际分配；它包含容量稳定和调度等待，不计GPU占用，各候选等待区间重叠，不能相加为整轮墙钟。

| 阶段／模型 | GPU | 实际分配 | worker结束 | 等待小时 | worker GPU秒 |
|---|---:|---|---|---:|---:|
| 原／9B | 1 | 14:33:23 | 14:53:39 | 3.346318 | 1216.304375 |
| 原／Devstral | 0 | 14:38:26 | 14:56:34 | 3.430616 | 1087.423858 |
| 接续／9B | 6 | 19:46:22 | 20:46:11 | 4.140867 | 3588.593916 |
| 接续／Devstral | 5 | 20:26:02 | 21:23:19 | 4.801879 | 3437.889352 |

| 成本 | GPU秒 | GPU小时 |
|---|---:|---:|
| 原四槽两worker | 2303.728234 | 0.639925 |
| 接续十二槽两worker | 7026.483268 | 1.951801 |
| 原／新同卡交集 | 0 | 0 |
| 逐卡区间并集 | **9330.211501** | **2.591725** |

成本使用每张卡的worker分配至结束区间并集，包含该worker加载和边界工作，不代表GPU利用率或纯生成内核时间。本轮没有追加显存预约；CPU修订、离线恢复、报告整理和队列等待不计在上述GPU小时中，也未混入v0.30—v0.32历史7.3466小时。浮点worker时长之和与整数微秒并集约相差1.075微秒，仅为舍入，不是额外收费。

四个原／接续worker PID均已不存在，排除了仍运行或PID重用；接续两worker exit_code=0、stop_reason=null。自动报告已正常推送。

## 9. 四层证据与研究结论

| 层次 | 本轮已经取得的证据 | 尚未取得的结论 |
|---|---|---|
| 执行可信 | 十六槽完整已知；身份、记录、每槽与全局guard通过；生成前拒绝修复后接续正常 | 任意新任务／边界都不会出现执行缺陷的普遍保证 |
| 学习接入 | 继承原完整数值／近16K／更新恢复证据；本轮同common／profile，四个worker的结束common恢复通过，步骤计数9B3/3与Dev0/0保持 | 本轮重新完成了反向压力资格，或出现新的参数学习收益 |
| 工作行为 | 同根目标／同团队上限的S/T比较闭合；6提交、10未提交，0完整通过，具体合同缺口可定位 | 通用模型能力排名、协作有害／有效的总体因果结论 |
| 分配支持 | 本轮用途仍为开发诊断；没有T完整成功的局部候选 | 新训练来源的M、n、n+、v、b、可辨识梯度，或B/G/I效果 |

本轮没有新增actor、critic、诊断或正式优化步骤；没有进行贡献试训、独立确认或经验分配。规则／CPU控制、真实冻结模型工作和参数训练收益分别报告。训练可微接入已经存在，当前结果集中暴露的是这些工作条件下的完整合同保持与交付问题，不能把工程恢复本身写成软件学习收益。

观察支持的有限解释是：同样复杂根目标下，单人也失败，合作组织并非唯一可疑因素；公开测试覆盖不足以代表完整合同，部分固定提交存在明确内容和API路径缺口。预算和任务责任／编辑反馈问题提供可见断点，但增加预算、修改任务复杂度或改变组织方式会产生何种改善，仍须另行冻结实验验证。

## 10. 事前结束条件与后续范围

`next-stage-decision.json`已输出`no_local_team_carrier`，支持采集候选为None。两模型八槽均可信，但T各0/4，未达到“至少一条T完整交付”的事前局部可行性条件；本轮不会强行选择赢家，也不追认原v0.30候选入选。

按已冻结审计分支，下一步应另设领域规则较少、仍保留真实API—消费者依赖的新根目标，继续保持空任务表和自主组织。当前两复杂root及全部失败保留，可作为后续难度扩展；这16条不重复、不改作训练，也不继续搜索第四个模型或重做相同资格题。

新任务应先冻结合同、用途与过程约束的工程意义，然后采集新训练来源的当前经验并核验完整有效工作、方法区分、频数与可辨识梯度。B／G-raw／I-P须使用同模型、同完整学习起点、同原始材料与分母；贡献C来自实际更新后的开发工作，独立确认不回流选权。本报告仅记录这一后继方向，**没有启动新根目标、支持采集或B/G/I试训**。

## 11. 原件与本次必要核验

- 原执行：`runs/software-paired-o1-v033`；派生恢复：`runs/v033r1-record-recovery`；接续执行：`runs/software-paired-o1-v033-recovery`。
- 原／接续执行源码：`6325ddb07b79b8d7573c1592cd76da33a32ff17d`／`ab6cd083beb33b4ffbccf48546d9394a34175ed3`。
- 本次只读汇总：`runs/v033-final/summary-audit.json`、`submission-review.json`、`process-review.json`；其内容、来源引用和SHA一并归入最终机器报告。
- 核验限于终态、唯一逻辑库存、已记录用量算术、原验收与固定交付、guard／common、进程身份及逐卡区间成本。没有重新运行pytest、模型、GPU、独立验收或旧归档全树扫描。
- 原[CPU与启动记录](software-paired-o1-v033-launch.md)、[修复控制与启动记录](software-paired-o1-v033-recovery-launch.md)、[原协议](software-paired-o1-v033-protocol.md)和[接续协议](software-paired-o1-v033-recovery-protocol.md)保留当时状态。

机器报告包含逐槽证据来源、精确账目、全部六份提交的expected／observed及静态解释标签、全部未提交断点和分母定义。静态源码解释明确区分于已执行测量；未提交可变代码未被补判成功或失败内容。
