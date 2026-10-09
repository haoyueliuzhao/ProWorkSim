# v0.36 实验中的任务与职责如何形成

日期：2026-10-09。案例范围：已结束的P2支持窗口。配套：[逐节汇报稿](software-organization-v036-speaking-notes.md)。

**当前实验中，任务由模型成员在合同范围内自行拆分，职责通过认领、转交等工具操作形成。** 这里的“合同”是实验预先规定的目标、模块/API和验收要求。模型可以决定怎样安排工作，但不能改变这些要求。

理解这个机制，需要依次看三件事：启动时给了什么、任务和负责人怎样产生、成员实际上做了什么。下面先说明规则，再用一条实际轨迹展示规则如何被使用。

## 1 实验开始时给定什么

本轮所有案例都要求完成同一个SQL脚本处理目标，包含两个模块：

- `reader.py`：实现 `statement_records(script)`，调用真实sqlparse API，按顺序生成语句记录。
- `report.py`：实现 `summarize(script)`，使用reader的结果，返回记录、三类语句计数和总数。

两个模型成员记为A和B。它们使用相同的模型参数和初始业务材料，各有独立会话和私有工作副本，共享团队预算。**初始任务表为空，没有预设“实现者”“测试者”等岗位，也没有预先指定谁负责哪个模块。** A固定先手，之后调度器轮流给可运行成员行动机会。[初始化代码](../../src/proworksim/software_collaboration_v036.py) · [P2先手设置](../../scripts/software_support_v036.py) · [成员会话与调度](../../src/proworksim/software_runtime_v036.py)

“私有副本”意味着，A修改文件后，B的文件不会自动变化。成员需要先发布一个固定版本的补丁，伙伴再显式整合，才能把这些改动引入自己的副本。

## 2 任务和负责人怎样形成

模型通过工具操作建立和调整任务记录。任务内容、操作对象等参数由模型生成，环境负责检查是否合法，并保存成功操作的结果。

| 环节 | 成员怎样操作 | 系统记录怎样变化 |
|---|---|---|
| 拆分任务 | 调用 `create_task`，填写任务描述、ID和父任务 | 新任务进入任务表，暂时没有负责人 |
| 确定负责人 | 调用 `claim_task`，认领尚未分配的任务 | `owner`（正式负责人）设为认领成员；创建者可以是另一个人 |
| 转移职责 | 当前负责人调用 `delegate_task` 转给可接收工作的伙伴；也可用 `return_task` 退回任务 | 转交后负责人变为伙伴；退回则清空负责人，恢复待认领状态 |
| 调整任务 | 有权限的成员修订描述、声明或移除依赖 | 环境按操作检查权限、版本和依赖关系，阻止依赖成环 |
| 沟通协商 | 通过消息讨论安排、说明进展 | 消息被记录，**消息本身不会修改正式负责人** |

实现位置：[创建、修订与消息](../../src/proworksim/software_collaboration_v030.py) · [认领](../../src/proworksim/software_collaboration_v027.py) · [转交与退回](../../src/proworksim/software_collaboration_v028.py)。

例如，A创建任务后，B可以自行认领。此时“创建者是A”和“负责人是B”同时成立。如果A只发消息说“请B负责”，任务的正式负责人不会因此自动改变。

**任务负责人也不等于文件的专属编辑者。** 成员仍可修改自己副本内的全部可编辑文件。任务归属影响部分任务操作和关联补丁发布的权限，但不会按照任务描述锁住相应文件。因此，即使B认领了实现任务，A也可能同时编写同样的模块。

编辑和测试可以先于任务登记。发布固定补丁则至少需要关联一个自己负责的任务；最终提交还要满足固定版本和测试等要求。机制允许成员自行安排任务形成的时机，但交付仍有明确条件。

## 3 第13号槽的实际过程

一个“槽”就是一次A、B共同完成根目标的运行，编号从0开始。P2第13号槽展示了一个重要现象：**实际行动未必遵循“先分工、再执行”。**

1. **A先写代码。** A修改了 `reader.py` 和 `report.py`，当时任务表里还没有任务。
2. **A建任务，B来认领。** A随后创建实现任务，B自行认领。任务的创建者是A，负责人是B。
3. **两份实现发生冲突。** B也修改两个模块并发布补丁；A把B的补丁整合进自己的副本时，两个模块都出现冲突。
4. **A另建任务并自行认领。** 新任务与B持有的任务描述相同，覆盖同一实现范围。这时任务表里有两条任务，分别由A和B负责。
5. **A发布并提交自己的版本。** 原验收结果为通过。但原有产物判定规则未确认最终版本有效保留了伙伴产物，不能仅凭整合记录就认定B的代码构成了最终贡献。

[第13号槽原始事件](/data1/zhuxinrui/projects/ProWorkSim/runs/software-support-v036/qwen3.5-9b/actual/collection/slot-13/world/control/state.json:21091) · [原验收结果](/data1/zhuxinrui/projects/ProWorkSim/runs/software-support-v036/qwen3.5-9b/actual/collection/slot-13/assessment.json)。

这个案例说明，任务登记可以发生在工作之后，同一范围也可以出现重复任务。**任务表描述的是正式责任关系，实际贡献还要沿着编辑、补丁整合和最终交付继续核对。**

## 4 其他运行展示的工作方式

相同的初始规则，还产生了以下路径。表中“最终交付者”指原评估采用的最后一次固定提交的成员。

| 案例 | 实际发生的过程 |
|---|---|
| 第00号槽 | A登记实现任务，B后来登记验证任务，最终由B交付。但双方在建任务前都已编辑两个模块，B的验证任务也晚于冲突修复和公开检查。 |
| 第05号槽 | A建实现任务、B认领。A再认领同一任务时被拒，随后另建并认领验证任务；接入B的补丁、处理冲突并测试后，由A最终交付。双方此前也都编辑过两个模块。 |
| 第14号槽 | A建任务、B认领。B发布覆盖两个模块的完整产物并通过验收，是本槽唯一提交者；A也编辑并整合过代码，之后继续修改自己的冲突副本。 |
| 第12号槽 | 全程没有建任务或认领，双方仍累计进行了13次编辑、6次测试，最后没有发布固定补丁，也没有提交。 |

对比第00和05号槽，A、B登记的“实现／验证”职责互换，最终交付者也从B变为A；原规则均确认了有限的伙伴产物保留关系。但这些职责标签不能说明双方从开始就按岗位分工，也不能证明伙伴产物对成功具有因果必要性。

第14号槽说明完整产物和最终交付可以集中在一人身上，不能据此说另一人没有工作。第12号槽说明编辑和测试不依赖事先登记任务；它的零分来自没有固定提交，未提交工作区没有接受隐藏内容验收，不能解释为已证实全部代码错误，也不能仅凭这一例将未交付归因于没有建任务。

各槽的事件编号、原结果与文件定位见附录。

## 5 这些记录能够说明什么

这不是第13号槽独有的现象。在全部16次运行中，A、B都编辑过两个模块；15次建立了任务，而且这15次都先发生生产文件编辑，后出现第一个任务。另一次始终没有登记任务。

本轮职责主要通过创建与认领形成。虽然系统提供转交、退回、任务修订和依赖调整，但这些操作在本窗口的成功事件数均为0。因此，可以说明机制支持这些能力，不能说本轮已经展示了它们的实际使用效果。

**本窗口实际呈现的主要模式是：先各自实现，随后登记任务、整合和交付。** 这表明机制允许自主组织，也容纳重复工作、交付集中或先执行后登记。是否形成了有效分工，需要结合编辑、消息、补丁整合和最终产物判断，不能只看任务名称、任务数量或负责人。

这些案例尚不足以证明分工高效、稳定或最优，也不构成参数训练收益或不同学习方法优劣的对照证据。

## 附录A 全部16次运行的统计

统计对象为同一根目标 `sp-script-inventory-v035`、不同采样种子的16条双成员轨迹。除特别注明的拒绝事件外，下表只统计成功保存的世界事件，不把模型自述当作实际完成。

| 观察项 | 结果 |
|---|---:|
| 初始任务表为空 | 16/16槽，两成员视图均为空 |
| A、B均编辑过reader和report | 16/16槽 |
| 创建过任务 | 15/16槽 |
| 首次生产编辑早于首次建任务 | 15/15个建过任务的槽 |
| 创建任务／认领任务／工作消息 | 21／20／2次 |
| 转交、退回、任务修订、依赖增删 | 成功事件均为0 |
| 发生补丁整合 | 14/16槽，各1次，均记录两个生产文件冲突 |
| 提交成员分布 | 9槽仅一人提交，5槽双方提交，2槽未提交 |
| 最终通过原完整验收 | 14/16槽；另2槽未提交 |

这些统计没有纯单人工作的样本。整合冲突反映了协调过程中发生的具体问题，但没有同条件的组织策略对照，不能据此量化效率损失或收益。

## 附录B 关键事件和原结果

A/B对应 `member_a/member_b`。下表保留审计所需的编号和标签：`W#n`为该槽的世界事件序号，不是模型轮次，不能跨槽比较；`R`为原完整验收结果；`Mapper`是原实验按产物来源证据进行分类的规则。`unmapped`表示未归入原有方法类别，不等于代码验收失败。

| 槽与seed | 关键事件顺序 | 原结果及解释 |
|---|---|---|
| 13 · `202610070114` | W#5/#6：A编辑两模块；#10/#11：A创建 `implement_sql_inventory`、B认领；#12/#13/#17：B编辑并发布patch-1；#18：A整合，两文件冲突；#25/#26：A创建同描述的 `my_sql_inventory_task` 并认领；#27/#28：A发布patch-2并提交delivery-2 | R=1；Mapper为unmapped。已解释的弃用导入不足以证明最终保留伙伴产物；`included_patch_ids`非空不能单独证明有效伙伴贡献。 |
| 00 · `202610070101` | W#4/#6和#9/#10：双方先编辑；#11/#13：A创建并认领实现任务；#15：A发布；#18：B整合并冲突；#21—#24：B修复并通过公开检查，成员自测未执行；#27/#28：B才创建并认领验证任务；#29/#30：B发布并最终提交 | R=1；有证据的同伴产物交付。双方均有提交，正文展开的是最后一次固定交付。 |
| 05 · `202610070106` | W#4/#8和#5/#10：双方先编辑；#14/#15：A建实现任务、B认领；action-25：A认领被拒；#17/#19：A另建并认领验证任务；#21/#22：B发布、A整合并冲突；#27—#29：A修改并测试；#30/#31：A发布覆盖实现与测试文件的patch-2并最终提交 | R=1；有证据的同伴产物交付。双方均有提交；认领拒绝后另建任务只是可观察顺序，不据此推定模型的内部动机。 |
| 14 · `202610070115` | W#6—#9：双方编辑；#12/#13：A创建仅描述reader的任务、B认领；#14：B发布两模块；#15：A整合并冲突；#16：B提交完整本地版本；#19/#20：A继续修改但没有第二份提交 | R=1；本地产物交付，未包含伙伴补丁。任务文字范围与实际操作文件范围并不相等，“本地”类别不代表过程里没有伙伴活动。 |
| 12 · `202610070113` | W#8/#10：B编辑两模块；#13/#15：A编辑两模块；#17/#18/#34：测试节选；终态0创建、0认领、0工作消息、0固定补丁、0提交，共13次编辑、6次测试 | R=0；未提交。未对可变工作区补做隐藏内容验收。 |

## 附录C 证据索引与引用口径

案例选择先依据完整16槽组织事件核对，再按说明目的选取5槽；成功案例与未提交案例均保留。省略读文件、重复测试、完整代码和模型对话，仅展示影响责任或协作路径的关键动作。

原件中的`software_events`记录成功落库的动作；槽05的认领拒绝来自`interactions[24]`，不混入成功认领统计。W序号保留原值，跳号表示省略事件。task标签、消息自述、提交与最终验收分别判断。中文事件描述是基于动作字段的概述，未改写原R和Mapper。

共同证据：[初始团队证明](/data1/zhuxinrui/projects/ProWorkSim/runs/software-support-v036/qwen3.5-9b/actual/collection/initial-team-proofs.json) · [P2原结果](software-support-v036.md) · [完整实验报告](software-support-v036-v037-report.md)。

| 证据 | 原事件文件与关键位置 | 原结果位置 |
|---|---|---|
| S00 | [槽00世界事件](/data1/zhuxinrui/projects/ProWorkSim/runs/software-support-v036/qwen3.5-9b/actual/collection/slot-0/world/control/state.json:24295)，W#11起；关键序号11、13、15、18、27、28、29、30 | [槽00 assessment](/data1/zhuxinrui/projects/ProWorkSim/runs/software-support-v036/qwen3.5-9b/actual/collection/slot-0/assessment.json) |
| S05 | [槽05世界事件](/data1/zhuxinrui/projects/ProWorkSim/runs/software-support-v036/qwen3.5-9b/actual/collection/slot-5/world/control/state.json:25956)，W#14起；另见`/interactions/24`拒绝 | [槽05 assessment](/data1/zhuxinrui/projects/ProWorkSim/runs/software-support-v036/qwen3.5-9b/actual/collection/slot-5/assessment.json) |
| S13 | [槽13世界事件](/data1/zhuxinrui/projects/ProWorkSim/runs/software-support-v036/qwen3.5-9b/actual/collection/slot-13/world/control/state.json:21091)，W#5起；同描述任务在W#10和#25 | [槽13 assessment](/data1/zhuxinrui/projects/ProWorkSim/runs/software-support-v036/qwen3.5-9b/actual/collection/slot-13/assessment.json) |
| S14 | [槽14世界事件](/data1/zhuxinrui/projects/ProWorkSim/runs/software-support-v036/qwen3.5-9b/actual/collection/slot-14/world/control/state.json:17731)，W#6起；最终提交W#16 | [槽14 assessment](/data1/zhuxinrui/projects/ProWorkSim/runs/software-support-v036/qwen3.5-9b/actual/collection/slot-14/assessment.json) |
| S12 | [槽12世界事件](/data1/zhuxinrui/projects/ProWorkSim/runs/software-support-v036/qwen3.5-9b/actual/collection/slot-12/world/control/state.json:24759)，W#8起；最终任务表为空 | [槽12 assessment](/data1/zhuxinrui/projects/ProWorkSim/runs/software-support-v036/qwen3.5-9b/actual/collection/slot-12/assessment.json) |

每份state中，`/software_events/(n−1)`对应W#n；它是JSON数组位置，不是文件行号。上述运行路径用于本地核对，正文已经保留理解案例所需的关键事实，无需阅读完整轨迹。

机制代码：[v036初始空任务板与相同成员指令](../../src/proworksim/software_collaboration_v036.py) · [任务创建、修订与依赖](../../src/proworksim/software_collaboration_v030.py) · [认领与责任快照](../../src/proworksim/software_collaboration_v027.py) · [委派与退回](../../src/proworksim/software_collaboration_v028.py)。

所选五份世界事件原件的SHA256（便于核对版本）：

```text
S00 23f538744461676867a7ececda3b10033620e6804b65ac4ec7f50b4be141c10e
S05 f20e4668c5098ca429da349692d00003771012281b99114f638872b21da3a5d1
S13 bcf023a9eee212fb9345b3e8802f47cc6ceaddc9eb8724acba920b5104f48998
S14 9e806b2ab808d31fe6bcd48edf708ca364db678416019c27b1c299fe3616589b
S12 c5a62e26878ea13295b691eec4b376317df0ea0177c7fdd8cb5b479964f18ca4
```
