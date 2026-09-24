# v0.10 统一工作人员、声明场景与分项评价实验

日期：2026-09-24。依据：[v0.9审计](../reference/platform-modules-audit.md)、[两阶段计划](../platform-modules-v010-plan.md)。实现接口见[设计说明](../platform-modules-v010.md)。

本轮完成评价输入补修，并让现有“财务核对—发布—报告—审阅”通过统一工作人员与声明场景运行。世界、策略、事件控制器、实际经历和独立评价各有明确入口。没有增加第三个行业模板，没有调用模型API、使用GPU、训练参数或采集真实业务资料。

结果支持有限规则策略和声明情境的模块集成，不能据此推断通用模型规划、自由专业报告质量、广泛信息隔离或任意时点崩溃恢复。本轮没有将检查条数合并为职业能力分数。

## 1. 两阶段冻结与正式执行

起始归档为`7a622539b1d57612ddc56923cb8ca21a4344b246`，其v0.9最终实现为`07bd9fd9e8a9e40681149a3bc41f133937205eea`。旧实验JSON原样保留。

| 阶段 | 实现冻结 | src源码树SHA256 | 正式范围 |
| --- | --- | --- | --- |
| A | `0b53a242503e8630774b88efd0eb57a3a8323088` | `93c8d832a0d9ccbf44944f982ca1d579787d57d54cf3292e183494fb6bf5466b` | R0、R1、550项测试、Ruff |
| B | `55277d59ce0a17eff9555478f6b9fb43bd921394` | `7a8ac58e556bdc1ed1e3b4cc86e91b46f6ae336c0bbd91bf5901c42eacac7735` | R0回归、R1/R2、R3、R4、真实CLI、573项测试、Ruff |

两阶段均在提交后执行，批次及各作业起止提交、干净状态和源码摘要相同；脚本、测试和场景JSON的输入哈希起止相同。阶段B执行时间为UTC 10:49:31–10:51:12，即北京时间18:49:31–18:51:12。不同世界并行，单世界仍为单写者。详细作业日志、输入清单、原监督脚本及摘要保存在[v010-validation.json](v010-validation.json)。

| 组别 | A | B | 计数解释 |
| --- | --- | --- | --- |
| R0 评价边界 | 98/98 | 98/98 | 14条件，每条件7个判据；重复运行是回归 |
| R1 运行迁移与语义保持 | 4案例，40/40 | 纳入下行，R1子集48项 | B新增真实历史版本核验，不能倒填到A |
| R1/R2 独立协作 | 未作正式R2结论 | 8案例，93/93 | 含上述4个R1案例，不额外相加 |
| R3 声明场景 | 未正式验收 | 8场景，85/85 | 每场景另一次初始构建仅用于重复性核验 |
| R4 经历与分项评价 | 未正式验收 | 4条件，69/69 | 包含应失败、应未评、应评价故障的判据 |
| 真实CLI链 | 未正式验收 | 8/8 | 实际部署、截断、续行、评价入口集成 |
| 完整pytest | 550通过，80.22秒 | 573通过，90.99秒 | 两阶段回归不累计为独立样本 |
| Ruff | 通过 | 通过 | src、tests、scripts |

阶段A已有部分并行准备的场景代码和测试，不据此声称阶段B已经完成。最终软件版本为0.10.0，WorldCore仍使用world-core-v0.9/work-world-v0.9；本轮没有新增一套世界业务状态。最终工作人员checkpoint为staff-runtime-v0.10.1，区别于阶段A的v0.10。

## 2. R0：合法JSON中的结构错误得到明确结果

先从起始Git提交导出完整源码，用真实WorldCore/ProjectSession创建世界、安装项目、读取与采用合法来源、写入版本并提交。没有只摘取领域函数复现。正常核对通过，结构完整的业务错误不通过；目标对象为null、结果行元素为null均在旧实现抛出AttributeError。两个异常触发属于同一输入边界根因。

旧探针中按新接口检查所得21/28不能解读成七个旧缺陷：旧接口本来没有新的status和归因字段。可直接解释的事实是四个真实会话的上述结果。完整旧源归档SHA256为`bd837e778690328e30f949c6fa57f4cf8de76cc9eeb77c0aaf8e181731adb5ff`，参与源码树摘要为`b91758998c6b6ebed8e10daea4429640344d235f0c1d7ccff2d0bdbba3733673`。

修复先检查结果对象、rows、行对象、键、证据数组及元素、汇总和未解决项等结构，再检查业务值；不是将所有异常包装成员工算错。对外评价入口版本为finite-products-v0.10。

| 条件 | 最终应有结果 |
| --- | --- |
| 正常核对 | pass |
| 结构完整但实际业务值错误 | content_failure |
| target_null、rows_null、row_null、key_nested、evidence_null、evidence_entry_null、summary_null、unresolved_nested | structure_failure |
| 精确来源读取不可用 | source_unavailable |
| 没有声明内容评价目标 | unassessed |
| 注入内部RuntimeError或TypeError | evaluator_error |

来源不可用条件是受控地使确切来源读取路径不可用，不冒称自然生产事故。内部异常仅在评价期间注入，独立串行执行，避免污染其他并行条件。外层明确评价边界接住未处理Exception，保留已经读取的read_set、已完成检查、被中断检查、异常类型及制度状态；系统退出和取消不归入该边界。

阶段A和B均98/98。已有required_fields齐全、但没有content_checks的旧M4断言改为“结构齐全、内容未评”，协议显式注明口径修订，旧JSON未改。最终还覆盖超大JSON整数造成math.isfinite转换溢出的本地输入路径；这是新增局部防护与测试，不声称完成该路径的完整旧版本复现。

完整协议、旧反例、原始错误及两阶段结果见[v010-evaluation-boundary.json](v010-evaluation-boundary.json)。

## 3. R1/R2：调度机会与业务决策分离

StaffRuntime轮转角色，一次机会取得该角色真实tools/observation，再调用其decide；策略返回act、wait或done。一次act最多执行一个真实工具调用。运行器管理各角色memory、上次action/result和预算，不导入匹配、报告生成、审阅或评价算法。

核对员、报告作者和审阅者的业务算法保留在独立规则策略。作者从实际工作和问题决定读源、采用、提交、局部修复或反驳；审阅者自己读取固定提交及证据，产生问题和处理决定。控制器没有把findings、修正正文或独立真值传给角色。公开交付要求可声明接收方与发布义务，由责任策略实际share/publish完成。

| 案例 | 核验的后果 |
| --- | --- |
| correct | 正确首交，一次提交即可接受，不强制返工 |
| two_partial | 两个独立问题分次局部修复；第一项处理后第二项仍开放；无关章节保持 |
| rebuttal | 对错误意见依据原材料反驳，保留同一次交付及明确处理关系 |
| reconciliation | 核对完整九组，独立手写真值覆盖匹配、冲突、歧义、缺失、换算与不可比 |
| unavailable_parallel | 一个角色真实等待资料，另一个角色仍推进合法工作，原信息条件保持 |
| illegal_action | 作者故意执行无批准权的动作，保存真实拒绝，运行器不替换成成功动作 |
| private_visibility | 指定无权作者未见审阅私有材料；独立评价答案不进入策略输入 |
| late_history | 实际旧错误版、修复版、接受后晚到意见保持历史；同key重复只产生一份效果，无关阻塞工作和条件不变 |

R1语义比较采用原v0.9受控公开驱动在本轮实现上新建世界真实执行，比较源引用、提交、问题—回应—决定关系、结果与历史，不要求动作数或日志形状相同。这不是在旧冻结内核上重新运行全部R1。核对审阅策略复用了公开matcher，因此另以手写字面真值核验，不能仅靠两种驱动相等自证正确。

阶段A40项中的字节保持覆盖初始输入/背景版；阶段B增加本轮创建的不可变版本以及实际读取内容和最终版本字节的对照，R1子集成为48项，R1/R2总计93项。各角色独立端口捕获与运行器实际经历对应一致。原报告中的outcome是最后一次step结果，常为worker_waiting；它不是整个世界完成标签。制度接受由独立事实检查确认。

非法批准在世界侧仍是缺少明确分类的ValueError，实际运行归因为unattributed_tool_rejection。已知该动作来自实验故障策略，不代表可以事后将工具归类伪造成policy_error或环境故障。私有性只验证指定材料/角色反例与独立记忆测试，不证明全部信息流性质。可信Python策略接口也不是恶意Python沙箱。

完整记录见[v010-staff-runtime.json](v010-staff-runtime.json)。

### 完整行动之后的继续与实例隔离

本版只承诺完整step返回后保存和继续。恢复比对角色顺序、策略类/config及公开的world_id、instance_id、branch_id、actor_id、project_ids；实际经历和各角色记忆保留。没有增加任意指令点的策略崩溃恢复保证，也没有重跑旧版全部进程中断矩阵。

开发复核发现直接StaffRuntime接口曾只比对世界名、角色和项目：同名但不同实例可能接受旧checkpoint，将旧世界读到的1交给实际值为2的新世界策略。CLI先前已有实例检查，但通用接口存在缺口。最终将已有instance/branch身份公开给运行绑定并升级checkpoint到v0.10.1；身份不一致时在调用策略前记录binding_error，接收策略无输入。旧checkpoint不静默兼容。

原探针没有记录执行开始时的完整源码身份。后续核实保存的staff_runtime.py和world_core.py与阶段A Git blob字节一致，但这不等于当时整个工作树已冻结。归档通过真实日志保留当时读取值，原探针也未保存完整观察/checkpoint；这些缺失不倒填。修复前后资料见[v010-instance-binding.json](v010-instance-binding.json)。

## 4. R3：场景规格、实际前缀和外部事件

Scenario声明世界、项目、角色、共享、setup、events、start和boundary；构建器只通过真实安装/工具动作部署。事件控制器读取预声明触发条件需要的事实，按声明actor/project执行工具，记录真实返回，不以独立评分选择补料或修正文稿。现有两个模板和linked_report配置是有限集成负载，没有引入任意代码生成或新行业。

| 场景 | 变化及用途 |
| --- | --- |
| finance-direct | 核对资料直接可见 |
| finance-route | 相同核对任务，资料改为需经合法路线请求 |
| report-direct | 报告独立场景 |
| chain-before-submit | 跨模板链，更正在提交前到达 |
| chain-pending | 同链，更正在待审阶段到达 |
| chain-accepted | 同链，更正在原工作接受后到达 |
| report-pending-start | 真实工作人员执行前缀后从待审状态继续 |
| finance-display-name | 显示名表面变体，单列而非新增工作结构 |

每场景重复构建起点，规范化仅排除已声明的实例/分支/父标识及诊断耗时、状态摘要；业务ID、逻辑时钟、命令、权限、版本及历史参与比较。八次重复初始构建不是八种新工作流。三种更正时点的业务配置只改变event.when，其余差异为场景身份与变体说明元数据；direct/route对照用于信息获取结构变化，不强制轨迹相同。

executed_prefix由真实StaffRuntime机会产生，保存实际经历区间、摘要及checkpoint。它有独立start预算；部署失败、前缀不可达或前缀事件拒绝会保留unbuildable诊断和已发生事实，不补写虚构审批或阅读历史。正式运行期间的事件拒绝另返回controller_rejected。初始背景构造、实际前缀和正式运行分别标记。

正式85/85包含起点重复性、两个独立模板、跨模板维护、真实待审前缀及表面变化区分；不可构建配置、失败前缀与重载由单元集成测试和补验支持，不计入这85项。结果与规格见[v010-scenarios.json](v010-scenarios.json)、[示例说明](../../examples/scenarios-v10/README.md)。

### 运行边界修复

开发R4暴露：selected work已达到显式终点，但无关项目仍开放时，控制器曾继续等待。修复后在每个完整角色机会之后检查声明范围，返回boundary_reached并保留无关世界事实。completed另要求制度接受、应有精确发布已兑现、无待处理环境事件且没有遗漏的声明事件。历史accepted前项只需其历史发布事实，不要求为了“最新版本”重新发布旧产物。

缺省终点通过完整无行动轮次判断完成、阻塞或策略等待；显式终点按声明检查。预算是开始该次运行前声明的边界，不能看评分临时延长。CLI软预算不改变场景规格；继续执行属于另一段有记录的运行。

## 5. R4：真实经历和多维评价

ExperienceRecorder保留发生时的公开工具、观察、策略决定、动作参数、request_key、返回/异常；controller_action与environment_event分别保存。完整记忆在checkpoint，摘要不能替代原始公开返回。经历不从最终状态反推，评价报告不进入策略上下文。

assess_episode只读固定事实和交付，分别输出institutional_progress、content_quality、independent_targets、process_constraints、incompleteness、runtime_problems与external_events；不提供overall passed。独立目标必须显式声明；缺expected或availability=unknown保持unassessed，显式expected:null则可表示已知JSON空值。过程约束当前仅支持禁止指定成功动作、保持指定版本；未声明约束时未评，被拒绝的尝试不算已完成禁止动作。

| 条件 | 实际配置与分项结果 |
| --- | --- |
| 上游错、下游忠实 | 明示故障核对策略将summary.conflict的1改为2，明示错误批准策略在读过源和交付后批准；A内容失败；B忠实表达2的有限合同通过；独立手写字面目标1失败 |
| metadata对、正文错 | 作者metadata写120，真实正文写999；只有作者被调度并在预声明pending终点结束；metadata目标通过，正文合同失败，没有控制器代修 |
| 合理未知 | 真实cost.value为null，正确unknown交付可以满足有限合同；已知JSON-null目标通过，未观察的外部真实cost保持unassessed |
| 评价器故障 | 正常交付及正式接受后，仅评价期间注入RuntimeError；content_quality为evaluator_error，已读read_set保留；制度接受和可独立检查的字面目标分别保留 |

上游故障策略在任何角色行动之前，显式绑定到一个新的StaffRuntime并记录干预；没有通过运行中篡改checkpoint给角色灌入结果。上游内容错误与总体目标失败不被计成两个独立业务根因。

四组均为boundary_reached：本实验刻意保留UNRELATED开放项目。检查确认它未因episode结束被清空或更改，不能写成整个世界工作完成。实际公开捕获与经历对应、固定提交重复评价相同、评价前后世界状态和不可变文件字节不变，合计69/69。原分项报告、过程要求、目标和经历引用见[v010-episode-assessment.json](v010-episode-assessment.json)。

## 6. 实际CLI集成与使用

新增三个入口分别负责声明部署、统一运行、只读评价。运行过程使用通用StaffRuntime与场景控制器，不调用专用实验驱动替工作人员安排业务步骤。

```bash
.venv/bin/proworksim scenario-build runs/platform-demo --spec examples/scenarios-v10/chain-accepted.json
.venv/bin/proworksim staff-run runs/platform-demo --max-opportunities 8 --output runs/platform-cut.json
.venv/bin/proworksim staff-run runs/platform-demo --checkpoint runs/platform-cut.json --output runs/platform-continued.json
.venv/bin/proworksim episode-assess runs/platform-demo --experience runs/platform-continued.json --output runs/platform-assessment.json
```

路径均使用新目录/新输出文件，输出在世界目录外。staff-run记录world实例、branch、规格摘要、worker和controller checkpoint；后续运行必须提供最新一次完整checkpoint。新运行可继续保留已发生环境变化，不要求世界状态版本与先前完全相等。CLI在执行动作之前核查明显非法输出位置，避免执行完才发现不能保存。

正式CLI实验真实调用进程，先截断8次机会再继续chain-accepted，验证原经历前缀保持、固定身份、只读评价、未声明独立目标及过程要求保持未评，以及控制器和环境事件分层，8/8。单元集成另覆盖旧checkpoint/非法路径拒绝和不可构建规格。证据见[v010-cli.json](v010-cli.json)。

episode-assess的可选--spec可声明work_ids、independent_targets、process_requirements。默认报告不会猜一个总体业务目标，因此“制度完成”不能被读取为“全部目标成功”。

## 7. 开发失败、测量修订与未证实疑点

完整索引见[v010-development.json](v010-development.json)。正式通过没有覆盖这些原始记录。

| 项目 | 原始问题 | 处理及解释 |
| --- | --- | --- |
| R0旧异常 | 两种合法JSON形状引发同根因AttributeError | 明确结构检查和独立故障边界；完整旧源会话保留 |
| R1最初驱动 | 直接脚本执行时受控对照导入失败 | 修正测量导入；未执行判据不算通过，不归因员工/环境 |
| 分拆交付策略 | 第二输出文件出现后，策略重新选择别名产生歧义 | 在精确work memory中保留原来合法选定的输出别名；保留真实失败世界 |
| R3首轮82/85 | 三链检查把没有previous_path的趋势预期写成unknown | 正确口径为unassessed；同一测量误差，不是三个世界缺陷 |
| R4首轮 | 未知值检查引用不存在的profit章节，实际为cost | 修正测量路径，原缺失/未执行保留 |
| R4第二轮 | 范围内工作已达终点，无关工作使终止延迟 | 实际场景边界缺陷；修复为boundary_reached，不关闭无关工作 |
| 直接运行恢复 | 同名不同实例可能将旧记忆传给新策略 | 加公开instance/branch身份及恢复拒绝；执行时源码身份缺口单列 |
| CLI测试初版 | 使用不存在的Store.state_path及错误版本目录 | 更正为control/state.json、control/versions并要求非空版本清单；这是测试夹具错误 |
| 超大整数 | 数值有限性判断可能发生浮点转换溢出 | 增加结构/数值保护与局部输入测试，不扩大旧版复现结论 |
| 前缀持久化疑点 | 怀疑不可达前缀诊断未存盘 | 独立复核否证，原实现已保存；没有将疑点写成新缺陷或修复成果 |

多数开发运行处于脏工作树，保留当时可得的源码前后摘要，不与正式冻结混淆。阶段A/B协议分母不同、重复条件、同根因多触发、未执行项都不累加为能力或故障样本量。

## 8. 证据位置、复验和结论边界

Git保存说明、完整判据、紧凑业务事实、原评价分项、源码身份及原始文件SHA256/大小引用。完整世界、版本字节、逐次观察、checkpoint和旧源码归档在服务器runs中，未声称所有原始轨迹已嵌入Git JSON。

| 证据 | 完整产物根目录 |
| --- | --- |
| 旧R0完整源与真实会话 | runs/evaluation-boundary-v10-before |
| A的R0/R1 | runs/evaluation-boundary-v10-stage1；runs/staff-runtime-v10-stage1 |
| B的R0/R1/R2 | runs/evaluation-boundary-v10-final；runs/staff-runtime-v10-final |
| B的R3/R4 | runs/scenarios-v010-final；runs/episode-assessment-v10-final |
| B的CLI | runs/platform-cli-v10-final |
| 实例问题前后 | runs/staff-instance-v10-before；runs/staff-instance-v10-after |

使用新输出目录可重跑最终有限协议：

```bash
.venv/bin/python scripts/evaluation_boundary_experiment.py --output runs/r0-repeat
.venv/bin/python scripts/staff_runtime_experiment.py --output runs/r12-repeat
.venv/bin/python scripts/scenario_experiment.py --output runs/r3-repeat
.venv/bin/python scripts/episode_assessment_experiment.py --output runs/r4-repeat
.venv/bin/python scripts/platform_cli_experiment.py --output runs/cli-repeat
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check src tests scripts
```

报告中的通过表示有限预声明后果成立，包括正确拒绝、未知、不完备和评价故障。它支持现有两个模板在统一模块中运行；不证明开放金融审计、任意报告语义、模型泛化、训练收益、多写者并发或任意断电一致性。下一步如引入固定模型角色，应独立冻结策略、预算和评价，真实保留失败，不用规则策略代做后计为模型成功；本轮未启动该可选实验。
