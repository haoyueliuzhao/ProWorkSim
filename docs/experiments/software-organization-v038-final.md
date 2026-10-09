# v0.38 冻结模型自主组织开发：最终实验报告

**本轮24条预登记经历已于北京时间2026年10月9日10:44:55闭合：24条结果已知、0条技术未知，7条形成合格最终固定交付，17条未提交。** O1为3/8，O2为1/8，O3为3/8。O3八条均没有发起增员，初始人数、累计出生数和峰值人数均为2，期间有成员自退；因此本轮没有取得真实动态招募或替换行为的模型证据。

本轮使用原Qwen3.5-9B的3/3完整common作为统一起点。24份既有冻结护栏均通过，四个worker均以actor/critic步数3/3结束；本轮没有新增反向、actor更新、critic更新或Contribution试训。新增结果是冻结模型在不同组织制度下的开发经历，不能作为ID-VTDO经验分配或参数训练收益。

本报告以完整24槽为总体，保留所有未提交、重复编辑、格式拒绝、资源准入终止与无增员结果。报告编制只读取既有JSON、调用与世界事件定位，没有重新调用模型、诊断GPU、补验未提交工作区或重新加载张量。

对应的[最终机器汇总](software-organization-v038-final.json)汇集下文表格和证据；此前自动生成的[原运行报告](software-organization-v038.md)及[原机器结果](software-organization-v038.json)保留。设计、资格和启动过程分别见[冻结协议](software-organization-v038-protocol.md)、[准备记录](software-organization-v038-preparation.md)、[启动记录](software-organization-v038-launch.md)。

## 1. 完成范围与评价对象

四个worker均正常退出，原始24个槽、root、condition、seed和先手元数据与冻结库存完全一致，没有删槽、补槽或自动重试。第一条经历于09:51:41开始；最后一条结果于10:44:42落盘，最后worker报告于10:44:46闭合，监督器于10:44:55确认全部完成。原自动报告于10:45:03推送，提交为`888502a`；运行实现固定在clean提交`955681e`。

评价对象是**终态最后一次固定提交**。公开测试反馈、固定patch和主动提交是三个不同环节；早先提交不会自动终止其他成员。七条已提交经历的最终固定版本，原独立验收均记录内容、所要求的API过程及过程观测完整性通过。其余17条按未交付规则记R=0，其可变工作区没有被独立验收。

因此“17条未提交”不等于“17份代码已被证明错误”。同样，某成员公开测试通过，也不自动成为团队固定交付或私有验收通过。下文将交付、测试状态和停止原因分别报告。

## 2. 任务来源与冻结设计

本轮四个任务是基于SWE-smith来源的固定`schema`库环境构造的业务根目标，使用真实`schema.Schema.validate`及相应应用模块。它们是此前已使用的开发根目标的组织开发变体，**不是新增的独立确认任务，也不是四个原封不动的上游issue**。原公共API、只读库文件、公开驱动和私有同合同质量检查保持不变；仅组织与用途文字形成新的variant、manifest和partition绑定。

具体来源链为`SWE-bench/SWE-smith-py`中固定的`keleshev/schema`环境，仓库版本为`24a30457`；本轮保留未施加旧缺陷补丁的上游代码，业务合同、起始模块及验收属于项目自建任务。来源见[原数据集清单](../../examples/software-sources-v028/source-manifest.json)、[自建任务说明](../../examples/software-sources-v035/README.md)与[四根开发面板说明](../../examples/software-sources-v036/README.md)。

| 索引 | 原业务根目标 | 本轮业务要求概要 |
| --- | --- | --- |
| r0 | `sc-job-policy-v035` | 验证作业的队列和优先级策略，按输入顺序报告接受记录与拒绝索引 |
| r1 | `sc-command-set-v035` | 先验证完整命令批，再按顺序改变活动名称集合；无效批不得部分应用 |
| r2 | `sc-room-bookings-v036` | 验证房间预约并按合同处理非重叠排期 |
| r3 | `sc-order-totals-v036` | 验证完整嵌套订单，返回精确整数行金额、小计、折扣与应付值 |

四个本轮ID均为原ID追加`-orgdev-v038`，用途统一为`organization_development`；训练、Contribution和独立确认资格均为false。先前order-totals的低开发成绩没有成为排除理由，本轮完整保留它的六条经历。

此前“任务与职责如何产生”的轨迹汇报主要引用P2中`sqlparse`脚本库存任务的历史经历；本报告讨论的是四个`schema`开发根，不应把那份SQL任务材料与本轮结果混为同一任务。旧P2、共同B更新及开发评价继续保留各自的模型状态、用途和执行协议，不与新O1/O2/O3直接拼成受控收益比较。

三组均从空任务板、无预设负责人和私有工作副本开始。模型可以先工作再登记、集中完成或重叠探索；任务责任不构成文件专属编辑权。

| 条件 | 初始成员 | 出生与退出制度 | 实际发生 |
| --- | --- | --- | --- |
| O1 | 2名中性成员 | 固定出生集合，不增员；允许自愿永久退出，无自动补位 | 8条均累计2名成员 |
| O2 | 4名中性成员 | 固定出生集合，不增员；允许自愿永久退出，无自动补位 | 8条均累计4名成员 |
| O3 | 2名中性成员 | 同时存活≤4、累计出生≤6，包含初始成员；等待占存活位；允许显式增员/退出/替换 | 8条均累计2名成员；增员与替换均未触发 |

成员能力来自同一冻结actor，没有额外专家权重或永久经理。新身份上限为`member_001`至`member_006`，每条经历内出生ID不复用。转交须由`offer_transfer`提出并由接收者显式接受；退出不删除原责任，也不由后台派给其他成员。新成员只能从公共基线或明确指定的已发布固定patch开始，不继承其他人的私有会话。

三组统一允许`fix_patch(task_ids=[])`固定直接完成的工作；若填写非空任务列表，则仍需具备当前所有权并满足所声明的依赖版本。这个修改来源于旧32槽审计中“通过公开测试后补办任务手续、最终未能提交”的实际断点。它没有取消当前版本测试、固定版本或主动提交要求。

每条经历共享128次决定、128次attempt、500,000个实际输入输出token及32次`run_tests`。预算不按人数翻倍、不按个人拆份额，也不随出生或退出重置；上下文上限16,384、单次输出最多2,048，沿用原采样配置。每个worker只有一份常驻模型，各成员会话顺序调用；不同root的四个worker可以并行。

库存为四root×三条件×两个新seed，共24条。s0=`202610090101`，s1=`202610090102`。O1/O3对同一root-seed使用同一先手，两个seed轮换初始两人；O2按预登记表覆盖四名先手，每人两次。各条件仍可能因输入与行动序列不同而使用不同的随机序列片段，配对seed不表示相同模型输出。

## 3. 工作质量：完整条件、root与配对结果

三组均闭合8/8条，没有技术未知。下表分母包含全部未提交经历；成功率描述本轮完整合格交付，不代表所有成员工作副本的正确率。

| 条件 | 已闭合/计划 | 合格最终交付 | 未提交 | 技术未知 | R均值 |
| --- | --- | --- | --- | --- | --- |
| O1 | 8/8 | 3/8 | 5 | 0 | 0.375 |
| O2 | 8/8 | 1/8 | 7 | 0 | 0.125 |
| O3 | 8/8 | 3/8 | 5 | 0 | 0.375 |
| 全部 | 24/24 | 7/24 | 17 | 0 | 0.292 |

四个root表现不同。command-set在全部六条经历中均未提交；其余三root至少有一个条件形成合格交付。下表不把同一root的两个seed当作两个独立业务问题。

| root | O1成功/2 | O2成功/2 | O3成功/2 | 合计成功/6 |
| --- | --- | --- | --- | --- |
| sc-job-policy-v035 | 2/2 | 0/2 | 1/2 | 3/6 |
| sc-command-set-v035 | 0/2 | 0/2 | 0/2 | 0/6 |
| sc-room-bookings-v036 | 1/2 | 1/2 | 1/2 | 3/6 |
| sc-order-totals-v036 | 0/2 | 0/2 | 1/2 | 1/6 |

八个root-seed配对单元全部保留。表中差值是同单元二元结果的算术差，未作统计显著性或普遍优劣声明。

| root | seed | O1 | O2 | O3 | O3−O1 | O3−O2 |
| --- | --- | --- | --- | --- | --- | --- |
| sc-job-policy-v035 | s0 | 1 | 0 | 0 | -1 | 0 |
| sc-job-policy-v035 | s1 | 1 | 0 | 1 | 0 | 1 |
| sc-command-set-v035 | s0 | 0 | 0 | 0 | 0 | 0 |
| sc-command-set-v035 | s1 | 0 | 0 | 0 | 0 | 0 |
| sc-room-bookings-v036 | s0 | 1 | 0 | 1 | 0 | 1 |
| sc-room-bookings-v036 | s1 | 0 | 1 | 0 | 0 | -1 |
| sc-order-totals-v036 | s0 | 0 | 0 | 0 | 0 | 0 |
| sc-order-totals-v036 | s1 | 0 | 0 | 1 | 1 | 1 |

O3相对O1为**1胜、1负、6平，平均差0.00**；相对O2为**3胜、1负、4平，平均差+0.25**。O2相对O1的平均差为−0.25。这些差异局限于四个已用开发root的八个配对单元。

O3没有增员，所以不能把O3−O2的+0.25解释成“动态招募带来提升”。O2与O3初始人数不同；O1与O3即使实际人数相同，其允许的组织操作、条件说明和后续输入也不必相同。本轮同样不足以断言固定四人通常更差。

## 4. 全部24槽明细

全部槽状态均为`closed`。以下“调用”指已经开始的真实attempt，本轮每次均有原始输出；token为实际输入与输出合计，测试为成员主动触发的`run_tests`次数，耗时为episode记录的秒数。每行链接其原始结果。

停止记号按成员统计：D=实际`staff_done`后永久退出；T=下一次生成受团队token准入限制；C=下一次生成受上下文容量限制。`all_members_stopped`是三类停止的共同终态标签，不能读作全员主动完成。R=0行的“否”均表示未提交，而非补验失败。

| 槽 | R | 提交 | 实际调用 | 实际token | 测试 | episode秒 | 成员停止 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| [org-r0-O1-s0](/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v038/root-0/actual/episodes/org-r0-O1-s0/slot-result.json) | 1 | 是 | 41 | 493,385 | 5 | 403.16 | D1+T1 |
| [org-r0-O2-s0](/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v038/root-0/actual/episodes/org-r0-O2-s0/slot-result.json) | 0 | 否 | 42 | 491,151 | 5 | 542.58 | T3+C1 |
| [org-r0-O3-s0](/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v038/root-0/actual/episodes/org-r0-O3-s0/slot-result.json) | 0 | 否 | 39 | 485,534 | 3 | 331.81 | T2 |
| [org-r0-O2-s1](/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v038/root-0/actual/episodes/org-r0-O2-s1/slot-result.json) | 0 | 否 | 43 | 497,554 | 1 | 365.94 | T4 |
| [org-r0-O3-s1](/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v038/root-0/actual/episodes/org-r0-O3-s1/slot-result.json) | 1 | 是 | 29 | 347,510 | 5 | 439.85 | D1+C1 |
| [org-r0-O1-s1](/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v038/root-0/actual/episodes/org-r0-O1-s1/slot-result.json) | 1 | 是 | 39 | 471,674 | 5 | 385.22 | D2 |
| [org-r1-O3-s0](/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v038/root-1/actual/episodes/org-r1-O3-s0/slot-result.json) | 0 | 否 | 40 | 490,864 | 4 | 484.29 | T2 |
| [org-r1-O1-s0](/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v038/root-1/actual/episodes/org-r1-O1-s0/slot-result.json) | 0 | 否 | 41 | 493,964 | 7 | 514.93 | T2 |
| [org-r1-O2-s0](/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v038/root-1/actual/episodes/org-r1-O2-s0/slot-result.json) | 0 | 否 | 42 | 488,894 | 1 | 482.02 | T3+C1 |
| [org-r1-O1-s1](/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v038/root-1/actual/episodes/org-r1-O1-s1/slot-result.json) | 0 | 否 | 40 | 489,676 | 7 | 516.77 | T2 |
| [org-r1-O2-s1](/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v038/root-1/actual/episodes/org-r1-O2-s1/slot-result.json) | 0 | 否 | 42 | 494,296 | 1 | 673.86 | T4 |
| [org-r1-O3-s1](/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v038/root-1/actual/episodes/org-r1-O3-s1/slot-result.json) | 0 | 否 | 42 | 495,544 | 5 | 487.96 | T2 |
| [org-r2-O2-s0](/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v038/root-2/actual/episodes/org-r2-O2-s0/slot-result.json) | 0 | 否 | 42 | 489,364 | 3 | 630.32 | T4 |
| [org-r2-O3-s0](/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v038/root-2/actual/episodes/org-r2-O3-s0/slot-result.json) | 1 | 是 | 41 | 487,718 | 4 | 467.04 | D1+T1 |
| [org-r2-O1-s0](/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v038/root-2/actual/episodes/org-r2-O1-s0/slot-result.json) | 1 | 是 | 40 | 491,803 | 3 | 382.12 | D1+T1 |
| [org-r2-O3-s1](/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v038/root-2/actual/episodes/org-r2-O3-s1/slot-result.json) | 0 | 否 | 41 | 493,919 | 4 | 581.04 | T2 |
| [org-r2-O1-s1](/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v038/root-2/actual/episodes/org-r2-O1-s1/slot-result.json) | 0 | 否 | 40 | 488,504 | 5 | 360.79 | T2 |
| [org-r2-O2-s1](/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v038/root-2/actual/episodes/org-r2-O2-s1/slot-result.json) | 1 | 是 | 41 | 490,522 | 4 | 478.81 | D2+T2 |
| [org-r3-O1-s0](/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v038/root-3/actual/episodes/org-r3-O1-s0/slot-result.json) | 0 | 否 | 41 | 497,018 | 4 | 374.62 | T2 |
| [org-r3-O2-s0](/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v038/root-3/actual/episodes/org-r3-O2-s0/slot-result.json) | 0 | 否 | 42 | 495,607 | 1 | 424.56 | T4 |
| [org-r3-O3-s0](/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v038/root-3/actual/episodes/org-r3-O3-s0/slot-result.json) | 0 | 否 | 42 | 492,891 | 6 | 413.56 | T2 |
| [org-r3-O2-s1](/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v038/root-3/actual/episodes/org-r3-O2-s1/slot-result.json) | 0 | 否 | 42 | 493,508 | 2 | 323.61 | T4 |
| [org-r3-O3-s1](/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v038/root-3/actual/episodes/org-r3-O3-s1/slot-result.json) | 1 | 是 | 40 | 498,093 | 6 | 464.29 | D1+T1 |
| [org-r3-O1-s1](/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v038/root-3/actual/episodes/org-r3-O1-s1/slot-result.json) | 0 | 否 | 40 | 484,570 | 4 | 353.17 | T2 |

## 5. 模型实际使用了哪些组织能力

模型主要直接阅读、修改和测试私有副本，本轮很少使用正式任务组织。全24条仅有一次`create_task`和一次`claim_task`，出现在同一条经历；没有执行工作消息、责任转交、任务修订、依赖调整或增员。这是本批模型行为的覆盖边界，不能由CPU正控制通过来补足。

下表“尝试”只计实际进入运行器工具回执的调用；工具前被语法/格式拦下的输出另外统计，不伪装成已执行世界动作。“成功”表示工具接受并产生规定后果，不表示产物正确。

| 操作 | 实际工具尝试 | 成功 | 拒绝 | 观察含义 |
| --- | --- | --- | --- | --- |
| create_task | 1 | 1 | 0 | 仅1条形成任务 |
| claim_task | 1 | 1 | 0 | 同一成员接受自己刚创建的任务 |
| revise_task、依赖声明/删除 | 0 | 0 | 0 | 未覆盖任务范围或依赖调整 |
| offer/accept/decline/return | 0 | 0 | 0 | 未覆盖协商转交与退回 |
| send_message、handoff_patch | 0 | 0 | 0 | 未发生工具级工作消息或定向patch交接 |
| spawn_member | 0 | 0 | 0 | 未发生真实招募或替换 |
| retire_member（模型直接调用） | 0 | 0 | 0 | 另有9次staff_done触发宿主机械退役 |
| fix_patch | 10 | 9 | 1 | 9个成功patch全部task_ids=[] |
| integrate_patch | 3 | 3 | 0 | 3次真实版本整合，仍需分别审视冲突与最终交付 |
| submit_integration | 11 | 9 | 2 | 9个提交事件分布于7条经历 |
| run_tests | 95 | 95 | 0 | 工具接受不等于测试通过 |

| 观察 | O1 | O2 | O3 | 全部 |
| --- | --- | --- | --- | --- |
| 任务创建/认领 | 0/0 | 0/0 | 1/1 | 1/1 |
| 成功固定patch | 4 | 1 | 4 | 9 |
| 成功提交事件 | 4 | 1 | 4 | 9 |
| 实际整合事件 | 1 | 1 | 1 | 3 |
| 出现生产路径重叠编辑的槽 | 8 | 7 | 8 | 23 |
| 有输出参与成员数（按episode累计） | 16 | 32 | 16 | 64 |
| staff_done退役事件 | 4 | 2 | 3 | 9 |
| 模型格式拒绝输出 | 36 | 47 | 33 | 116 |
| 世界工具拒绝调用 | 11 | 10 | 9 | 30 |

9个成功patch均采用空任务绑定，七条提交经历均没有创建执行任务。这说明合法集中交付路径在真实运行中被使用；不能据此推论任务板本身无价值。唯一创建任务的经历在测试和编辑之后才登记责任，但最终没有固定或提交。

23条出现至少两个成员修改同一生产路径。这个“重叠”不要求内容相同，也不证明代码被覆盖或工作被浪费；私有副本可以形成不同探索结果。三次整合是可恢复的具体产物关系；仅有`included_patch_ids`也不能证明伙伴代码最终保留、不可替代或带来因果收益。

全24槽共有64条“成员×episode”记录产生过实际输出；同一中性ID在不同episode分别计数，这不是64个独立模型。输出可以只是控制动作，也不表示64条记录都有实质代码贡献。例如`org-r2-O2-s1`的member_003在首个机会就`staff_done`，但仍应算有输出参与者。该槽最后由member_001提交合格版本，member_002另行整合曾产生冲突。[该退出事件](/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v038/root-2/actual/episodes/org-r2-O2-s1/prepared/world/control/state.json:26245)与[整合事件](/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v038/root-2/actual/episodes/org-r2-O2-s1/prepared/world/control/state.json:33142)保留。

三组共有9次世界退役事件，均来自9次真实`staff_done`，没有模型直接调用`retire_member`。O3其中3次；这些是自退，不是新增成员、招募、替换或复杂人员调整。O3八条的累计出生数、峰值存活数和有输出参与数均为2。

原始`live_at_end`合计55，表示注册表中尚未自退的身份；它包含被预算或上下文永久停止调度的成员。四个worker已退出，不存在55个还在运行的成员。成员最终停止为9次自退、52次团队token准入停止、3次上下文准入停止。

## 6. 17条未提交经历停在哪里

17条未提交经历中，16条没有调用`fix_patch`，另1条调用被所有权检查拒绝；17条均没有实际`submit_integration`尝试，也没有成功固定patch。本节只描述终态原件，不对未提交副本补做私有验收。

这17条包含48个成员副本。按最后执行测试是否绑定**当前版本**分类如下；类别互斥，统计单位是成员副本，不是episode。

| 终态可观察阶段 | 成员副本数 | 可以说明什么 |
| --- | --- | --- |
| 从未执行测试 | 17 | 没有该成员的真实测试执行记录；不表示未编辑 |
| 最近测试后又编辑，当前版本未测 | 11 | 旧测试结论不能套用于当前工作区 |
| 当前版本已测，公开两组未全部通过 | 18 | 公开反馈仍有未通过项；不等于已进行私有验收 |
| 当前版本公开两组全部通过 | 2 | 仍缺固定patch与主动提交，私有验收未知 |
| 合计 | 48 | O1 10个、O2 28个、O3 10个成员副本 |

下面逐条列出断点。“未测”表示从未执行测试；“改后未测”表示最后一次测试之后又改动；“公开未全过/公开全过”均要求测试与终态当前版本一致。数字001等是该槽成员ID后缀。除标出的两条含C外，未提交槽的所有成员均因T停止；表中没有把终止原因自动当作业务失败的唯一原因。

| 未提交槽 | 各成员终态测试阶段 | 固定/提交断点 | 成员停止 |
| --- | --- | --- | --- |
| [org-r0-O2-s0](/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v038/root-0/actual/episodes/org-r0-O2-s0/prepared/world/control/state.json) | 001 改后未测；002 公开未全过；003 公开未全过；004 改后未测 | 无固定/提交尝试 | T3+C1 |
| [org-r0-O3-s0](/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v038/root-0/actual/episodes/org-r0-O3-s0/prepared/world/control/state.json) | 001 公开未全过；002 改后未测 | 无固定/提交尝试 | T2 |
| [org-r0-O2-s1](/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v038/root-0/actual/episodes/org-r0-O2-s1/prepared/world/control/state.json) | 001 公开未全过；002 未测；003 未测；004 未测 | 无固定/提交尝试 | T4 |
| [org-r1-O3-s0](/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v038/root-1/actual/episodes/org-r1-O3-s0/prepared/world/control/state.json) | 001 公开全过；002 公开未全过 | 所有权拒绝1次；后认领仍未固定 | T2 |
| [org-r1-O1-s0](/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v038/root-1/actual/episodes/org-r1-O1-s0/prepared/world/control/state.json) | 001 公开未全过；002 公开未全过 | 无固定/提交尝试 | T2 |
| [org-r1-O2-s0](/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v038/root-1/actual/episodes/org-r1-O2-s0/prepared/world/control/state.json) | 001 未测；002 未测；003 未测；004 公开未全过 | 无固定/提交尝试 | T3+C1 |
| [org-r1-O1-s1](/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v038/root-1/actual/episodes/org-r1-O1-s1/prepared/world/control/state.json) | 001 公开未全过；002 公开全过 | 无固定/提交尝试 | T2 |
| [org-r1-O2-s1](/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v038/root-1/actual/episodes/org-r1-O2-s1/prepared/world/control/state.json) | 001 改后未测；002 未测；003 未测；004 未测 | 无固定/提交尝试 | T4 |
| [org-r1-O3-s1](/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v038/root-1/actual/episodes/org-r1-O3-s1/prepared/world/control/state.json) | 001 公开未全过；002 公开未全过 | 无固定/提交尝试 | T2 |
| [org-r2-O2-s0](/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v038/root-2/actual/episodes/org-r2-O2-s0/prepared/world/control/state.json) | 001 未测；002 未测；003 公开未全过；004 公开未全过 | 无固定/提交尝试 | T4 |
| [org-r2-O3-s1](/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v038/root-2/actual/episodes/org-r2-O3-s1/prepared/world/control/state.json) | 001 改后未测；002 改后未测 | 无固定/提交尝试 | T2 |
| [org-r2-O1-s1](/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v038/root-2/actual/episodes/org-r2-O1-s1/prepared/world/control/state.json) | 001 公开未全过；002 公开未全过 | 无固定/提交尝试 | T2 |
| [org-r3-O1-s0](/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v038/root-3/actual/episodes/org-r3-O1-s0/prepared/world/control/state.json) | 001 公开未全过；002 改后未测 | 无固定/提交尝试 | T2 |
| [org-r3-O2-s0](/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v038/root-3/actual/episodes/org-r3-O2-s0/prepared/world/control/state.json) | 001 未测；002 未测；003 改后未测；004 未测 | 无固定/提交尝试 | T4 |
| [org-r3-O3-s0](/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v038/root-3/actual/episodes/org-r3-O3-s0/prepared/world/control/state.json) | 001 改后未测；002 公开未全过 | 无固定/提交尝试 | T2 |
| [org-r3-O2-s1](/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v038/root-3/actual/episodes/org-r3-O2-s1/prepared/world/control/state.json) | 001 未测；002 未测；003 改后未测；004 未测 | 无固定/提交尝试 | T4 |
| [org-r3-O1-s1](/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v038/root-3/actual/episodes/org-r3-O1-s1/prepared/world/control/state.json) | 001 公开未全过；002 改后未测 | 无固定/提交尝试 | T2 |

两个“当前公开全过”副本分别是`org-r1-O3-s0/member_001`与`org-r1-O1-s1/member_002`。这两个例子能够定位从公开反馈到固定交付之间的实际断点；不能把它们补算成合格交付，也不能假设再给一次或两次调用就一定会通过私有验收。

全24条中有22条出现团队token准入边界，3条出现上下文边界，二者可在同槽不同成员上并存。55次没有开始生成的决定分为52次token准入拒绝和3次上下文拒绝。后者发生于`org-r0-O2-s0/member_002`、`org-r0-O3-s1/member_002`、`org-r1-O2-s0/member_004`；其中`org-r0-O3-s1`最终已经有合格交付。成员遇到边界、团队未提交和代码错误不能互相替代。

**解释范围：**接近50万token以及终止时的准入拒绝是测量事实。重复阅读、格式拒绝、独立修改、测试位置与交付动作安排也都可能影响形成该终态的过程；本轮没有预算消融或反事实续跑，不能确认预算是唯一原因。

## 7. 四段代表性原始轨迹

以下按说明目的选择，不是随机样本，也不用于挑选成功子集计算效果。仅抽取必要事件；`E`为世界`software_events.sequence`，与工具`action_id`或experience序号不同。完整事件定位保存在[组织行为审计JSON](../../runs/v038-report-controls/organization-audit.json)。

### 7.1 集中完成可直接固定交付：org-r0-O1-s0

**该片段体现无执行任务的直接交付，以及当前版本测试门实际生效。** member_001直接完成应用代码，用空任务列表固定patch；第一次提交因缺少当前版本测试被拒，之后实际测试并重新提交。终态最后固定交付通过验收，R=1。它证明该合法路径在本次真实模型运行中发生，不证明伙伴贡献或分工优势。

| 顺序 | 真实后果 | 原件 |
| --- | --- | --- |
| E21 | member_001固定patch-1，task_ids=[]，绑定自己的v5 | [固定事件](/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v038/root-0/actual/episodes/org-r0-O1-s0/prepared/world/control/state.json:22668) |
| action-27 | 首次submit被拒：需要同一当前工作版本的真实测试 | [拒绝回执](/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v038/root-0/actual/episodes/org-r0-O1-s0/experience.jsonl:484) |
| E23 | member_001对v5执行公开测试，两组均通过 | [测试事件](/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v038/root-0/actual/episodes/org-r0-O1-s0/prepared/world/control/state.json:22715) |
| E25 | 主动提交delivery-1，绑定v5与E23 | [提交事件](/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v038/root-0/actual/episodes/org-r0-O1-s0/prepared/world/control/state.json:24381) |
| E27 | 实际staff_done引发永久自退；伙伴后续仍有机会 | [退役事件](/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v038/root-0/actual/episodes/org-r0-O1-s0/prepared/world/control/state.json:24842) |

### 7.2 公开测试通过后仍未交付：org-r1-O3-s0

**该片段体现本轮唯一一次任务创建/认领，以及公开测试通过后仍可能没有固定交付。** member_001先编辑并测试，E23公开两组通过；此后才建任务。创建不等于认领，带该任务固定patch时被所有权检查拒绝；随后认领成功，下一次生成受到团队token准入限制。没有成功patch或提交，R=0。新接口本来允许空任务绑定，模型仍主动选择了非空任务路径。

| 顺序 | 真实后果 | 原件 |
| --- | --- | --- |
| E23 | 当前私有版本公开两组通过 | [测试事件](/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v038/root-1/actual/episodes/org-r1-O3-s0/prepared/world/control/state.json:20788) |
| E25 | 创建complete_root_contract，owner仍为null | [创建事件](/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v038/root-1/actual/episodes/org-r1-O3-s0/prepared/world/control/state.json:23519) |
| action-30 | 带该task_id固定patch，被“只有当前所有者”检查拒绝 | [固定拒绝](/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v038/root-1/actual/episodes/org-r1-O3-s0/experience.jsonl:619) |
| E27 | 同一成员显式claim成功，owner变为member_001 | [认领事件](/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v038/root-1/actual/episodes/org-r1-O3-s0/prepared/world/control/state.json:24064) |
| 终态 | 两成员均受T限制；0个固定patch、0次提交 | [终态原结果](/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v038/root-1/actual/episodes/org-r1-O3-s0/slot-result.json) |

创建和认领记录说明责任可以后形成；它们不追溯改变先前编辑的作者，也不表明形成了多人职责分工。这里有明确的过程断点，尚无私有验收结论。

### 7.3 最后一次公开测试通过，仍未固定或提交：org-r1-O1-s1

**该片段体现“测试完成”和“交付完成”之间的差别，且没有补建任务这个中间环节。** member_002的最后一次实际工具调用为`run_tests`：E35绑定自己的v8，上游回归、公开业务组以及成员脚本均通过。此后下一次生成被团队token准入阻止；没有固定patch或提交尝试。另一成员当前公开组未全通过，团队最终未提交，R=0。

| 记录 | 可恢复事实 | 原件 |
| --- | --- | --- |
| E35 / action-38 | 真实测试绑定member_002的v8，当前版本未再编辑 | [测试事件](/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v038/root-1/actual/episodes/org-r1-O1-s1/prepared/world/control/state.json:27799) |
| experience 670 | 最后实际接受工具为run_tests | [工具回执](/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v038/root-1/actual/episodes/org-r1-O1-s1/experience.jsonl:671) |
| 终态 | 没有fix或submit；member_002因team_max_total_tokens停止 | [终态原结果](/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v038/root-1/actual/episodes/org-r1-O1-s1/slot-result.json) |

该副本没有被补验，也没有改判成功。公开测试有限，不能据此断言只缺手续就必然有合格最终交付。

### 7.4 首次提交后继续协作，整合冲突后再提交：org-r2-O3-s0

**该片段体现固定产物共享、接收者主动整合和后续修复；同时说明首次提交没有强制终止团队。** member_001先提交并自退；member_002继续工作，导入该公开patch时两个文件出现冲突，随后修改、测试并形成第二次固定提交。评价使用最后的delivery-2，R=1。本槽没有增员。

| 顺序 | 真实后果 | 原件 |
| --- | --- | --- |
| E19→E21 | member_001固定patch-1后提交delivery-1，绑定自己的v3 | [首次提交](/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v038/root-2/actual/episodes/org-r2-O3-s0/prepared/world/control/state.json:29548) |
| E23 | member_001实际staff_done并永久退出 | [退出事件](/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v038/root-2/actual/episodes/org-r2-O3-s0/prepared/world/control/state.json:29587) |
| E26 | member_002主动integrate_patch；consumer.py、rules.py写入冲突标记，产生v8 | [真实整合与冲突](/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v038/root-2/actual/episodes/org-r2-O3-s0/prepared/world/control/state.json:29637) |
| E33 | member_002后续v10执行公开测试，两组通过 | [后继版本测试](/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v038/root-2/actual/episodes/org-r2-O3-s0/prepared/world/control/state.json:29777) |
| E34→E35 | 固定patch-2并提交delivery-2，绑定v10；最后固定交付通过 | [最终提交](/data1/zhuxinrui/projects/ProWorkSim/runs/software-organization-v038/root-2/actual/episodes/org-r2-O3-s0/prepared/world/control/state.json:33743) |

`included_patch_ids=[patch-1]`保留的是整合来源关系。要证明伙伴代码对最终行为的必要贡献，还需要具体内容或反事实分析；本报告没有运行这种分析，不能仅靠该ID或最终成功作出贡献归因。首次delivery-1也没有单独补验，不能用终态验收倒推它此前已独立合格。

## 8. 调用、token与资源成本

所有成本按完整条件组与全部24槽累计，包含17条未提交经历；不按成功子集计算效率。实际972次调用全部有原始输出，输入11,450,667 token、输出192,896 token，总计11,643,563 token；预算记账量与实际报告量相等，不确定usage次数为0。输入占总token的98.3433%，是每次真实输入重复计入调用成本的结果，不是唯一内容字节或KV缓存命中统计；实际总token为24槽计划上界12,000,000的97.0297%。成员`run_tests`合计95次，控制器对固定最终交付的验收不混入该95次。

| 条件 | 决定 | 实际attempt / 有原输出 | 无生成决定 | 输入token | 输出token | 总/charged token | run_tests |
| --- | --- | --- | --- | --- | --- | --- | --- |
| O1 | 334 | 322 / 322 | 12 | 3,854,344 | 56,250 | 3,910,594 | 40 |
| O2 | 366 | 336 / 336 | 30 | 3,869,897 | 70,999 | 3,940,896 | 18 |
| O3 | 327 | 314 / 314 | 13 | 3,726,426 | 65,647 | 3,792,073 | 37 |
| 全部 | 1027 | 972 / 972 | 55 | 11,450,667 | 192,896 | 11,643,563 | 95 |

决定合计1,027次，其中55次在准入阶段没有启动模型生成。运行器机会数也为1,027，因此本轮没有额外的“未消费决定的控制机会”。972次真实attempt、972次有输出调用与55次无生成决定分别对齐预算账和紧凑原输出证据；没有把控制拒绝补造为模型输出。

| 条件 | 每槽调用均值 / 中位 | 每槽token均值 / 中位 | 每槽测试均值 / 中位 | episode总秒 | episode均值 / 中位秒 |
| --- | --- | --- | --- | --- | --- |
| O1 | 40.25 / 40.00 | 488,824.25 / 490,739.50 | 5.00 / 5.00 | 3290.78 | 411.35 / 383.67 |
| O2 | 42.00 / 42.00 | 492,612.00 / 492,329.50 | 2.25 / 1.50 | 3921.69 | 490.21 / 480.41 |
| O3 | 39.25 / 40.50 | 474,009.12 / 491,877.50 | 4.62 / 4.50 | 3669.85 | 458.73 / 465.67 |
| 全部 | 40.50 / 41.00 | 485,148.46 / 491,477.00 | 3.96 / 4.00 | 10882.32 | 453.43 / 452.07 |

episode记录耗时为收集入口开始到结果构造，部分结束护栏、关闭、case准备和加载位于该区间之外。O1/O2/O3的这些耗时不是同一条件的真实团队内并行耗时；每个worker中的成员始终顺序调用。不同root在不同物理卡上并行，也不能当作组织制度带来的加速。

四个worker只使用物理GPU 3、4、5、7，全部正常结束。以下时间区间来自监督器已有进程记录，累计11,215.475秒，即**3.11541 worker-GPU小时**。同一物理卡的worker区间并集在本轮与该和相等，因为每张卡只有一个本轮worker。

| worker / root | 物理GPU | 开始（北京） | 监督确认结束（北京） | 绑定worker秒 | GPU小时 | 启动至首episode秒 |
| --- | --- | --- | --- | --- | --- | --- |
| root-0 | 3 | 09:50:50.282 | 10:33:20.986 | 2550.704 | 0.70853 | 50.84 |
| root-1 | 4 | 09:50:50.284 | 10:44:55.166 | 3244.882 | 0.90136 | 50.87 |
| root-2 | 5 | 09:50:50.286 | 10:40:35.668 | 2985.382 | 0.82927 | 50.86 |
| root-3 | 7 | 09:50:50.287 | 10:31:24.794 | 2434.507 | 0.67625 | 51.13 |

监督器从09:49:46.979到10:44:55.168，共**55分8.189秒**；首worker前63.303秒包含协议要求的60秒容量稳定观察及轮询，不能全部归为外部排队。四worker同时段的墙钟包络为54分4.884秒，不能再将四卡时间和或episode时间叠加到这个墙钟值上。

启动至首episode约50.84—51.13秒，包括模型加载、恢复common与初始case准备。资源采样没有捕获短暂的独立restore起点，故不把这些时间写成纯模型加载时间。worker区间还包含CPU工作、等待、结束护栏和监督器退出检测，**不是GPU kernel活跃时间或利用率积分**。

1,943份原始资源采样均无guard异常，未触发停止。下表是采样观测峰值/最低值，不保证覆盖两次采样之间的瞬时极值；自己的GPU占用与设备总空闲分别报告。

| worker / GPU | 样本数 | 自身显存峰MiB | 单进程RSS峰GiB | 设备空闲最低MiB | guard异常 |
| --- | --- | --- | --- | --- | --- |
| root-0 / 3 | 442 | 29,954 | 3.546 | 51,191 | 0 |
| root-1 / 4 | 562 | 33,584 | 3.331 | 47,561 | 0 |
| root-2 / 5 | 517 | 29,914 | 3.329 | 51,231 | 0 |
| root-3 / 7 | 422 | 31,380 | 3.885 | 49,765 | 0 |

自身显存观测峰为33,584 MiB，单worker RSS观测峰为3.885 GiB，设备空闲最低47,561 MiB，均位于原资源合同内。统计仅解析旧`resources.jsonl`，没有为编写报告再次执行GPU查询。[成本与资源复算](../../runs/v038-report-controls/cost-review.json)提供各槽、各成员、每卡区间并集及口径。

## 9. 冻结状态、记录完整性与测试资格

24份既有`evaluation-guard.json`均通过，四个worker的common恢复和终态检查一致；actor、critic、两优化器、策略修订、actor/critic计数和critic已有奖励历史字段的记录指纹在24条中保持相同。训练计数始终为3/3。冻结关闭记录说明没有进行概率重算、学习前向或更新；原B的4/4检查点没有混入。

“新反向=0”来自本轮禁止学习的执行路径及既有报告字段，并由保护学习状态不变的记录互相印证；此次整理没有重新安装反向hook或执行张量复核。环境内修改任务、记笔记或编写业务代码都是工作过程，不是actor/critic参数训练。完整只读复核见[运行完整性审计](../../runs/v038-report-controls/integrity-review.json)。

启动前必要CPU合同资格为53通过、0失败、0跳过，Ruff通过。全量回归与环境复核的历史如下，保留默认环境的原失败，不改写成一次全量零失败。

| 检查 | 实际历史结果 | 范围与解释 |
| --- | --- | --- |
| 世界/源合同控制 | 17通过 | 出生/退役、权限、义务、转交、固定版本与直接交付门、四schema参考正控制 |
| 运行器控制 | 11通过 | 含真实SDK的CPU动态会话，共享transport/预算、唤醒与公平、提交后继续、冻结和技术未知 |
| 库存/入口控制 | 25通过 | 24槽配对、失败成本、未知保留、GPU白名单、含bytes的checkpoint引用正反例 |
| 最终源码绑定CPU资格 | 53通过，0失败，0跳过 | 不加载9B、不采样、不做tiny反向；一个Pydantic ReadOnly支持说明警告 |
| Ruff | 通过 | src、tests、scripts |
| 默认全量pytest | 1816通过、12失败、121跳过；602.70秒 | 按项目默认命令执行一次 |
| 仅上述12个失败节点定向复核 | 12通过；17.40秒 | 使用既有resident解释器/JSON Schema依赖及数据盘临时目录，CUDA禁用 |

12个默认环境失败节点与v037上一轮相同：轻量`.venv`缺Torch/JSON Schema，以及旧监督器测试因`/tmp`可用空间低于20GiB触发原保护。没有为通过检查放宽生产保护、修改旧数值实现或重复整套回归。准备期间实际只读prepare还发现合法checkpoint引用带`bytes`被旧式字典比较误拒，已在模型启动前修复并加入正反控制；另修复加载失败时负新增步数的显示。最终资格包含这些修订，旧失败日志和未启动旧计划均保留。[详细准备与命令记录](software-organization-v038-preparation.md)。

CPU控制证明有限接口可以正确执行，并不证明真实模型会调用它们。这个区分在本轮很直接：CPU出生、转交和唤醒控制通过，但24条模型经历没有发生真实招募、责任转交或工作消息。

本报告的表格读取已有结果和紧凑证据；未再次运行pytest、模型、验收或大产物哈希扫描。本次必要检查为新增只读提取脚本的Ruff、文档链接，以及24条结果、17条未提交记录和48个成员副本分类与机器账的一致性，均通过。原事件作者、版本、调用与用途没有因这次汇总改写。

## 10. 有限结论与尚未执行范围

本轮已完成授权的24条冻结模型组织开发，能恢复任务、私有版本、固定提交、实际整合、成员退出和真实调用成本；七个最终固定交付通过原质量合同。原3/3 common及全部保护学习状态保持不变，旧训练队列没有接续。

本批主要行为是直接工作与私有副本重叠探索。允许空任务绑定的集中交付路径实际发生，唯一一次任务登记出现在工作之后；消息、职责修订、转交和人员招募均未记录到调用。因此“更自由的接口已可运行”与“模型已经形成丰富自主组织”需要分别判断。本轮尤其不能声称O3产生了动态增员优势。

四个已用开发root的结果具有明显任务差异；O3相对O1平均差为0，相对O2为+0.25，都只是这八个配对单元的描述结果。更多成员、更多消息、更少用人或更低花费都不是独立的成功标准。未提交时的测试与交付断点值得继续研究，但未进行追加预算、提示诱导或反事实续跑，不能将任何单一因素认作已证明的失败原因。

原26次Contribution试训、3次正式更新、48条旧TextFSM独立确认、v037梯度缓存生产验证继续暂停；没有新反向或参数更新。审计中“12个新root×4条件×3seed=144次执行”仍只是规划示例，未形成冻结库存，也未启动。旧13条可靠双类支持的频数、b或缓存没有复制到新组织制度。

后续若进一步实验，可优先区分两类问题：一是从当前版本公开反馈走到固定交付的闭合过程；二是哪些任务依赖能为协商、分工或增员提供实际作用空间。这只是基于本轮记录的研究建议，不能自动恢复训练或追加“必须增员”的提示条件。任何新任务、预算或引导条件都应另行明确用途和比较范围；TextFSM确认池继续保留原独立用途。

机器证据入口：[最终机器汇总](software-organization-v038-final.json)、[原自动结果](software-organization-v038.json)、[24槽组织行为审计](../../runs/v038-report-controls/organization-audit.json)、[成本复算](../../runs/v038-report-controls/cost-review.json)、[记录完整性复核](../../runs/v038-report-controls/integrity-review.json)。原始运行目录为`runs/software-organization-v038`。
