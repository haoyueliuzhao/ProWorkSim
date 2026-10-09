# 任务与职责如何由模型形成

汇报范围：已完成的 **v0.36 P2支持窗口**，同一根任务的16次双成员运行。下文“当前实验”均指这一窗口。日期：2026-10-09。配套：[对应讲稿](software-organization-v036-speaking-notes.md)。

**当前实验中，任务由模型成员在合同范围内自行拆分，职责通过认领、转交等工具操作形成。**

初始状态只有根目标、规定的模块/API和验收要求。A、B使用相同模型参数和业务材料，各有私有工作副本，**任务表为空，没有预设“实现者”“测试者”等岗位**。A固定先手，之后调度器轮流给可运行成员行动机会。[初始化代码](/data1/zhuxinrui/projects/ProWorkSim/src/proworksim/software_collaboration_v036.py:150)

具体机制是：

| 环节 | 如何产生 |
|---|---|
| 拆分任务 | 模型调用 `create_task`，自己填写任务描述、ID和父任务；新任务暂时没有负责人 |
| 确定负责人 | 任一成员调用 `claim_task` 认领未分配任务，系统将 `owner` 设为该成员 |
| 转移职责 | 当前负责人调用 `delegate_task` 转给伙伴；伙伴可以用 `return_task` 退回待认领状态 |
| 调整分工 | 有权限的成员修订任务、声明或移除依赖，系统检查版本与依赖环 |
| 沟通协商 | 成员通过消息协商；**消息本身不会修改正式负责人** |

这些操作的参数由模型生成，环境负责校验和落库。[任务操作实现](/data1/zhuxinrui/projects/ProWorkSim/src/proworksim/software_collaboration_v030.py:188)

**机制允许自主组织，也允许重复工作、集中完成或先执行后登记。** 下面用五段真实轨迹分别说明这些工作方式如何出现。每个例子先说明体现的现象，再呈现关键动作和对应机制。

任务归属记录正式责任，不等于文件专属编辑权，也不能直接当作实际贡献。阅读轨迹时，要把任务登记与编辑、消息、补丁整合和最终交付联系起来。

## 共同任务：完成语句提取与汇总两个模块

后面五个案例都来自同一个任务：**将一段SQL脚本整理成语句记录和分类汇总。** 一个“槽”就是A、B共同完成这个目标的一次运行，编号从0开始；各槽使用不同采样种子。

| 必须完成的模块 | 合同要求 |
|---|---|
| `reader.py` | 实现 `statement_records(script)`，调用真实sqlparse API，按原顺序返回每条语句的文本和类型 |
| `report.py` | 实现 `summarize(script)`，使用reader的结果，返回语句记录、SELECT/UPDATE/DELETE计数和总数 |

原公开合同给出的例子是：

```sql
SELECT label FROM bins;
UPDATE bins SET flag = 1;
```

正确交付应保留这两条语句记录，得到 **SELECT＝1、UPDATE＝1、DELETE＝0、总数＝2**。此外还要遵守合同中的顺序、重复语句、空输入等要求。[原公开合同](/data1/zhuxinrui/projects/ProWorkSim/examples/software-sources-v035/sp-script-inventory-v035/contract.md:14)

**规定两个模块，并不等于给两个人各分一个模块。** A、B都能修改自己副本内的两个文件。谁创建任务、谁认领、谁整合和提交，要在运行中形成。

两份副本不会自动同步。伙伴的代码要先发布成固定补丁，再由接收者调用 `integrate_patch` 显式整合。后面的“冲突”，就发生在已有本地修改与伙伴补丁相遇时。

## 第13号槽：先执行后登记，也允许重复工作

**这段轨迹主要体现：成员可以先执行后登记，也可以重复实现相同范围的工作。**

1. **A先改代码。** A修改了reader和report，此时任务表还是空的。
2. **A建任务，B来认领。** A创建实现任务 `implement_sql_inventory`，B通过 `claim_task` 成为负责人。
3. **B也修改两个模块并发布补丁。** A将B的补丁整合进自己的副本，两个文件都发生冲突。
4. **A另建同范围任务并认领。** 新任务叫 `my_sql_inventory_task`，描述与第一项任务完全相同。
5. **A形成最后交付。** B此前也曾提交；A随后发布并提交自己的固定版本，原验收通过。

两项任务的原描述都是：

> Implement reader.statement_records and report.summarize to build SQL inventory from sqlparse

**对应机制：** 编辑不以任务登记为前提，任务所有权也不会锁住伙伴的文件副本。因此，同一实现范围可以同时存在两份代码和两条责任记录。[同描述任务原件](/data1/zhuxinrui/projects/ProWorkSim/runs/software-support-v036/qwen3.5-9b/actual/collection/slot-13/world/control/state.json:24264)

这段轨迹还说明消息与责任记录的关系。A曾发消息请求B认领并发布，但当时B已完成认领；消息没有再次改变负责人。正式责任来自已经执行的 `claim_task`。[消息原件](/data1/zhuxinrui/projects/ProWorkSim/runs/software-support-v036/qwen3.5-9b/actual/collection/slot-13/world/control/state.json:22173)

## 第00号槽：验证职责可以在工作之后登记

**这段轨迹主要体现：成员自行建立和认领职责，验证工作可以先做、后登记。**

1. **双方先编辑。** A、B在第一项任务出现前，都已经修改了两个模块。
2. **A登记实现职责。** A创建并认领实现任务，随后发布补丁。
3. **B接入并检查。** B整合A的补丁，处理冲突，修改代码并通过公开检查。
4. **B再登记验证职责。** 完成上述工作后，B才创建并认领验证任务，随后形成最后交付，原验收通过。

B创建的任务原文是：

> Member_b verification task. Confirming patch-1 implementation and test results.

**对应机制：** `create_task` 和 `claim_task` 建立正式责任记录，编辑和测试可以在这些记录形成之前发生。这里的“验证者”是B在运行中自行登记的职责，初始并没有这个岗位。[验证任务原件](/data1/zhuxinrui/projects/ProWorkSim/runs/software-support-v036/qwen3.5-9b/actual/collection/slot-0/world/control/state.json:28217)

## 第05号槽：创建者与负责人可以不同

**这段轨迹主要体现：任务由成员自主创建和认领，创建者不必成为负责人；成员也可以另建任务并承担责任。**

1. **双方先编辑。** A、B都已修改两个模块。
2. **A建任务，B认领。** A创建实现任务，B成为负责人。
3. **A认领同一任务被拒。** 系统返回 `Task has already been claimed`。
4. **A建立自己的验证任务。** A另建并认领验证任务，之后接入B的补丁、处理冲突并测试。
5. **A形成最后交付。** 原验收通过。

**对应机制：** 新任务最初没有负责人，任一成员均可认领；已有负责人的任务不能被另一次认领覆盖。成员仍可通过 `create_task` 建立其他任务，再自行认领。[认领拒绝原件](/data1/zhuxinrui/projects/ProWorkSim/runs/software-support-v036/qwen3.5-9b/actual/collection/slot-5/world/control/state.json:18705)

与第00号槽相比，这里是B负责实现、A负责验证。两种责任安排都在运行中形成，没有预设固定岗位；也没有发生 `delegate_task` 转交。两槽都曾由双方提交，本文比较的是最后交付者。

## 第14号槽：一名成员可以集中完成并交付

**这段轨迹主要体现：一名成员可以完成覆盖全部模块的可交付版本，并集中承担最终提交。**

1. **双方分别编辑。** A、B都修改了reader和report。
2. **A建任务，B认领。** 任务文字只描述reader实现。
3. **B发布完整产物。** B的补丁同时覆盖reader和report；A尝试整合，遇到两个文件的冲突。
4. **B提交，A继续自己的修改。** B形成了本槽唯一固定提交，原验收通过；A后续继续修改，但没有另一份提交。

**对应机制：** 每个成员都可以修改全部可编辑模块，任务描述不会把文件权限切成岗位。根目标可以由一名成员集中完成并交付，同时仍允许伙伴编辑、整合和继续工作。[任务、补丁与交付原件](/data1/zhuxinrui/projects/ProWorkSim/runs/software-support-v036/qwen3.5-9b/actual/collection/slot-14/world/control/state.json:19672)

这里的“集中完成”指B形成完整可交付版本，不表示A没有做过工作。

## 第12号槽：没有登记任务也可以编辑和测试

**这段轨迹主要体现：任务登记不是开始编辑和测试的前提，系统也不会自动替成员补齐任务或提交。**

1. **B先编辑两个模块。** 当时没有登记任务。
2. **A也编辑，双方继续测试。** 全槽累计13次编辑、6次测试。
3. **任务表一直为空。** 最终没有创建任务、发布固定补丁或提交。

**对应机制：** 编辑和测试可以直接进行；建任务、认领和提交则需要成员主动调用相应工具。这一槽展示了“允许先执行”，但没有继续走到登记和交付。[编辑与测试原件](/data1/zhuxinrui/projects/ProWorkSim/runs/software-support-v036/qwen3.5-9b/actual/collection/slot-12/world/control/state.json:24759)

v0.36发布固定补丁需要关联至少一项自己负责的任务，最终交付还要满足固定版本和测试条件。本槽没有提交，未对可变工作区补做隐藏验收；公开测试也曾失败，不能只凭任务表为空解释未交付的原因。

## 这些轨迹体现了怎样的机制

**机制允许自主组织，也允许重复工作、集中完成或先执行后登记。** 这些工作方式来自同一组执行规则：

| 工作环节 | 机制如何运行 | 轨迹中的表现 |
|---|---|---|
| 形成任务与职责 | 成员生成任务内容，再通过创建、认领等操作记录责任 | 第00、05号槽形成不同的实现与验证责任安排 |
| 编辑与测试 | 成员可以直接操作自己的合法文件，不必先登记任务 | 第13、00号槽先执行后登记；第12号槽一直没有登记 |
| 重复工作 | 双方都能修改全部可编辑模块，任务所有权不排除伙伴编辑 | 第13号槽出现相同范围的实现和任务，整合时发生冲突 |
| 集中完成 | 每个成员都有完成整个根目标所需的操作权限，不要求按人拆开模块 | 第14号槽由B形成完整版本并提交 |
| 沟通与交接 | 消息传递请求；负责人由任务工具改变，代码通过固定补丁显式整合 | 第13号槽的消息没有改写既有负责人，整合也不会自动消除冲突 |

本窗口实际出现的责任操作主要是创建与认领。转交、退回、修订和依赖调整虽然可用，但成功事件数均为0，不能把工具具备的能力写成本轮已经发生的行为。

这些例子用于说明机制如何容纳不同的工作过程。是否形成高效分工、伙伴成果是否进入最终版本，仍需结合编辑和产物证据判断；任务标签和验收通过率不能直接代表协作效率或参数训练收益。

## 证据索引

正文已保留理解案例所需的关键事实。以下用于会后核对：A/B对应`member_a/member_b`；W是各槽的世界事件序号，跳号表示省略中间动作，不是模型轮次。英文引用为原任务描述或消息；中文动作说明是依据记录整理的概述。

| 案例 | 关键原始事件 | 原验收记录 |
|---|---|---|
| 13：先执行、后登记 | [W5/6编辑，W10/11创建认领，W14消息，W17/18发布与冲突，W25/26同描述新任务，W28最后提交](/data1/zhuxinrui/projects/ProWorkSim/runs/software-support-v036/qwen3.5-9b/actual/collection/slot-13/world/control/state.json:21091) | [通过；原分类unmapped不等于验收失败](/data1/zhuxinrui/projects/ProWorkSim/runs/software-support-v036/qwen3.5-9b/actual/collection/slot-13/assessment.json) |
| 00：B后置登记验证 | [W11/13 A建任务与认领，W18 B整合，W21—24修复与检查，W27/28 B建验证任务与认领，W30最后提交](/data1/zhuxinrui/projects/ProWorkSim/runs/software-support-v036/qwen3.5-9b/actual/collection/slot-0/world/control/state.json:24295) | [通过](/data1/zhuxinrui/projects/ProWorkSim/runs/software-support-v036/qwen3.5-9b/actual/collection/slot-0/assessment.json) |
| 05：A负责验证与最后交付 | [W14/15 A建任务、B认领；action-25 A认领被拒；W17/19 A建验证任务与认领；W22整合；W31最后提交](/data1/zhuxinrui/projects/ProWorkSim/runs/software-support-v036/qwen3.5-9b/actual/collection/slot-5/world/control/state.json:25956) | [通过](/data1/zhuxinrui/projects/ProWorkSim/runs/software-support-v036/qwen3.5-9b/actual/collection/slot-5/assessment.json) |
| 14：B集中交付 | [W6—9双方编辑，W12/13任务与认领，W14/15发布与冲突，W16 B唯一提交，W19/20 A继续编辑](/data1/zhuxinrui/projects/ProWorkSim/runs/software-support-v036/qwen3.5-9b/actual/collection/slot-14/world/control/state.json:17731) | [通过](/data1/zhuxinrui/projects/ProWorkSim/runs/software-support-v036/qwen3.5-9b/actual/collection/slot-14/assessment.json) |
| 12：有行动、无提交 | [W8/10 B编辑，W13/15 A编辑，W17/18及W34测试；终态空任务表、无补丁和提交](/data1/zhuxinrui/projects/ProWorkSim/runs/software-support-v036/qwen3.5-9b/actual/collection/slot-12/world/control/state.json:24759) | [未提交，未补验可变工作区](/data1/zhuxinrui/projects/ProWorkSim/runs/software-support-v036/qwen3.5-9b/actual/collection/slot-12/assessment.json) |

全窗口统计来自[组织行为审计](software-organization-v038-prior-audit.md)的P2部分与[对应机器明细](software-organization-v038-prior-audit.json)；该审计文档同时覆盖B开发，本汇报只使用其中的16条P2。原实验整体结果见[完整报告](software-support-v036-v037-report.md)。本次仅重组文档并只读核对关键原件，没有重新执行模型、测试或验收。

统计补充：16/16槽中双方都编辑过两个模块；15槽建立任务，且均为首次编辑早于首次建任务。全窗口有21次创建、20次认领和2次工作消息；14次补丁整合都记录了两个生产文件冲突。最终14槽完整验收通过，2槽未提交。“首次编辑早于首次建任务”不表示每槽双方都在建任务前完成了实现。

机制补充定位：[认领](/data1/zhuxinrui/projects/ProWorkSim/src/proworksim/software_collaboration_v027.py:268)、[转交与退回](/data1/zhuxinrui/projects/ProWorkSim/src/proworksim/software_collaboration_v028.py:170)、[旧版固定补丁任务条件](/data1/zhuxinrui/projects/ProWorkSim/src/proworksim/software_collaboration_v030.py:256)。`return_task`使任务回到未分配状态，不自动把owner改回原委派者。
