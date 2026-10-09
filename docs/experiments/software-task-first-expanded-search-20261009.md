# 扩大历史搜索：先创建任务、再编辑代码的真实轨迹

2026-10-09，针对“此前汇报例子都先编辑再发布任务，扩大搜索是否有先发布任务的轨迹”进行只读历史核查。

**有。新检查的v0.30—v0.34共60条真实模型业务轨迹中，27条先成功创建任务、再发生团队首次生产代码编辑；其中15条为双成员运行。** 原汇报使用的v0.36 P2共16条确实没有此类轨迹，不能将该窗口的结果推广到整个项目历史。

## 口径与覆盖

“发布任务”指模型实际生成`create_task`调用，工具成功执行并产生`task_created`世界事件。初始预置任务、认领已有任务、创建失败或只有自然语言计划都不计。团队口径比较首次成功任务创建与首次生产文件编辑，要求后面确有编辑；成员口径另比较创建者自身的首次生产编辑。W表示世界事件序号，不是模型轮次；测试脚本编辑不算生产编辑。

先按episode目录选择终态world或end状态，排除start/snapshot重复，再按世界实例/分支标识去重，并检查真实模型输出。排除了16个未发生模型输出的预建槽，以及6份资格探针/控制的world/end副本。v0.33原始运行与恢复运行合并成原16槽；不把恢复报告对旧路径的引用再计一次。不改变各原实验的分母或结果。

| 新检查窗口 | 真实业务轨迹 | 创建过任务 | 团队先任务后编辑 |
|---|---:|---:|---:|
| v0.30，Qwen3.5-9B | 12 | 12 | 7 |
| v0.31，Devstral Small 2507 | 12 | 10 | 6 |
| v0.31r2，SWE-next-14B | 12 | 2 | 2 |
| v0.33，原运行及接续 | 16 | 14 | 12 |
| v0.34 | 8 | 6 | 0 |
| **合计** | **60** | **44** | **27** |

| 工作类型 | 检查数 | 团队先任务后编辑 |
|---|---:|---:|
| 双成员O1根任务 | 28 | **15** |
| 单成员O1根任务 | 8 | 5 |
| 单成员API正常任务 | 12 | 4 |
| 单成员修复任务 | 12 | 3 |

v0.33目录名中的`diagnostics`属于该轮真实S/T业务诊断库存，并非要求模型演示创建工具的接口探针。以上是历史行为存在性搜索，不是统一条件下的策略效果比较。

## 例一：同一9B模型先创建两项任务，双方认领后才开始编辑

来源：v0.30 `qwen3.5-9b/actual/screen-0-4/slot-0`，`mm-ledger-rootgoal`。这是双成员账本导入任务，模型身份为原`online-actor-3:a86e2de…`，与后续9B原3/3 common的actor身份一致；任务和当时执行协议不同，不能作仅任务顺序不同的对照。

| 顺序 | 成员 | 实际动作 |
|---|---|---|
| 初始 | 环境 | 任务板为空 |
| W4 | A | 创建`task_cents_field`：金额字符串解析与标准格式输出 |
| W6 | A | 创建`task_ledger_schema`：账本记录字段验证 |
| W7 | B | 认领`task_cents_field` |
| W8 | A | 认领`task_ledger_schema` |
| W9 | B | 首次生产编辑，修改自己的`models.py` |
| W10 | A | 开始修改自己的`models.py` |

两个任务均在任何成员编辑生产代码之前创建，认领也早于首次编辑。原模型输出明确写道：“Let me create tasks to organize this work, then implement the solution.” 随后真实输出两个`create_task`，并有成功回执；不是依据最终任务表倒推顺序。

证据：[初始空任务板](/data1/zhuxinrui/projects/ProWorkSim/runs/software-model-selection-v030/qwen3.5-9b/actual/screen-0-4/slot-0/episode/start/control/state.json:2035)、[创建—认领—编辑事件链](/data1/zhuxinrui/projects/ProWorkSim/runs/software-model-selection-v030/qwen3.5-9b/actual/screen-0-4/slot-0/world/control/state.json:38210)、[第一项真实模型输出](/data1/zhuxinrui/projects/ProWorkSim/runs/software-model-selection-v030/qwen3.5-9b/actual/screen-0-4/slot-0/experience.jsonl:110)、[第二项真实模型输出](/data1/zhuxinrui/projects/ProWorkSim/runs/software-model-selection-v030/qwen3.5-9b/actual/screen-0-4/slot-0/experience.jsonl:144)。两个工具成功回执分别位于同文件114、148行。

**边界：** 最终未提交，原R=0。两人后来仍编辑各自副本中的相同文件，并都编辑过消费者模块；事前任务责任没有形成排他编辑权。该例证明实际出现了“先建立任务和责任、后开始编码”，不证明分工高效或交付成功。

## 例二：Devstral先建立并认领任务，再实现

来源：v0.31 `devstral-small-2507/actual/screen-1-5/slot-0`，双成员`mm-settings-rootgoal`。

B在W1创建`implement_settings_schema`，W3认领，W5才出现首次生产编辑`models.py`。其后W7创建消费者任务；A在W9另建同范围schema任务。初始任务板与两成员起始观测均为空，模型原输出、成功工具回执和世界事件已对应核查。

证据：[事件链](/data1/zhuxinrui/projects/ProWorkSim/runs/software-model-selection-v031/devstral-small-2507/actual/screen-1-5/slot-0/world/control/state.json:48364)、[真实模型创建输出](/data1/zhuxinrui/projects/ProWorkSim/runs/software-model-selection-v031/devstral-small-2507/actual/screen-1-5/slot-0/experience.jsonl:28)。最后未提交，R=0；先建立任务也可能伴随后续重复任务。

## 例三：先创建任务且最后通过，但属于单成员修复

来源：v0.30 `qwen3.5-9b/actual/screen-0-3/slot-0`，单成员`mm-nested-error-repair`。

W3创建嵌套验证错误路径修复任务，W4认领，W5编辑，W7固定补丁，W8提交，原独立验收R=1。这个任务有环境准备的初始公开失败反馈，属于单成员修复诊断；不把它当成双成员分工成功。

证据：[短动作链](/data1/zhuxinrui/projects/ProWorkSim/runs/software-model-selection-v030/qwen3.5-9b/actual/screen-0-3/slot-0/world/control/state.json:9635)、[真实模型创建输出](/data1/zhuxinrui/projects/ProWorkSim/runs/software-model-selection-v030/qwen3.5-9b/actual/screen-0-3/slot-0/experience.jsonl:44)。

## 更早与较新窗口的边界

v0.28—v0.29另核对17条去重真实9B软件经历：v0.28原运行6条、上下文恢复新增3条、v0.29支持8条。17条均初始预置两个执行任务，实际首个模型接口也没有`create_task`。有“先认领后编辑”的例子，但不属于成员自行发布任务，因此不并入上面60条自主任务形成统计。旧写文件操作也不强制先认领。

v0.15软件维护预设工作和实现者，没有自主建任务工具；相关devcase、参考补丁与验收目录是CPU控制。v0.27任务同样预置，软件对齐报告明确尚未采集真实9B软件经历，SDK示例是合成响应控制。这部分只做载体/协议排除核查，没有逐条遍历所有早期通用模型记录，不报告“早期全部模型从不先建任务”。

此前已经核查的v0.35 P2、v0.36 P2、v0.36 B开发、v0.38共72条中，37条创建过任务，全部首次编辑早于首次任务创建；这一有限结论保留。v0.39在本次搜索起点没有闭合slot-result，其有提示接口诊断及并行恢复验证不并入历史自主任务样本。

机制源码确认：[自主任务由调用参数创建](/data1/zhuxinrui/projects/ProWorkSim/src/proworksim/software_collaboration_v030.py:188)，[公开成员说明](/data1/zhuxinrui/projects/ProWorkSim/src/proworksim/software_collaboration_v030.py:351)允许自行形成任务，没有要求必须先建任务才能编辑；[文件编辑](/data1/zhuxinrui/projects/ProWorkSim/src/proworksim/software_collaboration_v027.py:241)检查合法工作副本与路径，不以任务认领为前置条件。旧固定补丁存在任务/所有权要求，但那不强制任务一定先于编码。

## 能支持的结论

历史上确实出现过自主创建任务并在编辑前形成责任安排，例一可用于补充说明这种机制的实际使用。原v0.36汇报仍限定其本批16条，不能把历史正例混入该批成绩。

27个顺序正例中，15条双成员轨迹的完整R均为0；12条单成员轨迹中5条R=1。这里R=0可能是未提交或固定交付未通过，具体保留各原记录。顺序证据不等于有效协作证据。不同版本的任务、提示、模型和预算不同，本次没有识别造成顺序变化的原因，也没有估计先建任务的因果收益。

全部逐槽顺序、去重/排除信息、代表案例原输出和实际回执索引见[机器明细](software-task-first-expanded-search-20261009.json)。本搜索未调用模型、未运行测试或重新验收，也未改写旧结果；并行开展的新实验另行记录。
