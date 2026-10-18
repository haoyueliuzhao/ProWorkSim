# v052 准备凭据第一部分：已闭合控制与原初态退出

本文件封存现有只读审计、来源资格及CPU/合成控制，作为后续准入的静态第一部分。它不签发模型准入，不宣称十二个初态已经通过。独立PS1来源绑定重物化和其余十个初态的完成情况由后续另一个JSON/Markdown补充；本文件不追更、不回改原退出或false。

这里的pending表示“本静态分册尚未纳入独立完成凭据”，不表示后续工作没有任何进展。截止范围固定为两个原初态退出及修复启动阶段；后续成果不能倒写成原尝试已经成功。

## 已闭合部分

| 证据组 | 固定范围与执行数 | 结论及限制 |
|---|---|---|
| 原HOLD只读过程审计 | 原全部16已执行槽：5成功、11未提交；另16来源blocked保持 | 首轮11解析成功/5解析错误，修复后只读重处理5、复用11，16全部闭合；不补验旧树、不改F |
| 来源资格 | 18逻辑三态单元、9实际runner、9完整执行、1,710原节点观察 | 六个开发任务全部qualified；三态预期闭合不等于1,710节点全部通过 |
| 来源/锁定纯控制 | 2个不同合同、3次累计执行 | 首fixture字段错误保留，只重跑受影响1项 |
| OH原生接口 | 4个不同合同、13个pytest节点结果：3pass/7fail/3setup error；另1次只读尾断言完成 | 3个实际合成Conversation，4份programmed响应，1次受限shell和1次共享synthetic测试；均非模型调用 |
| 受管关闭与宿主 | 4个不同合同、5次累计执行 | 初4项通过，来源引用闭合增量仅重跑受影响项；旧运行器不变 |
| 初态脚本纯控制 | 3项首次通过 | 证明捕获与计数脚手架，不等于实际12初态资格通过 |
| 终态报告器 | 1项首次通过（0.06秒） | 固定12/6分母、缺证null、OH joint N/A；尚未生成真实终态报告 |

这些数字属于不同活动，不能合成“若干次模型测试”。实际来源资格的9次CPU执行与OH接口的1次synthetic共享测试分别记账，不冒称零测试；本阶段真实模型、权重装载和GPU worker均为0。

## 原HOLD审计：全16覆盖，原件不改

详细结果见[只读过程审计](software-bridge-v052-hold-process-audit.md)及[JSON](software-bridge-v052-hold-process-audit.json)。首次解析器在合法Γ1 same_input_ref处误把对象当list，5槽分析未闭合；错误与首版源码保留，随后只解析同一请求中精确引用，重处理原5槽、复用另外11槽。累计21次槽解析不是21次新实验。

审计包括全部5个原成功和11个未提交结果，不据其成绩筛v052六题。未对旧11份未提交树追加私验，没有重放旧SDK、模型、测试或原测量，也没有改原guard、费用与报告。本准备分册仅引用审计顶层结果，不再遍历这些轨迹。

## 共同来源与测试入口

[来源资格摘要](../../artifacts/software-bridge-v052/source-qualification/summary.json)整体completed/passed均true，六个原CAL2开发任务全部合格。18逻辑单元按完整文件、测试、环境、命令、runner和参数身份，在结果出现前机械去重成9个物理执行。1,710是这9个执行的原测试节点观察次数，不是不同测试ID的去重数，也不是全部通过数；正确/参考态与缺陷态各自符合冻结资格条件。

正式解释器、依赖、沙箱和测试入口见[共享source/test协议](software-bridge-v052-source-test-protocol.md)。PS1 run_tests、OH明确的bridge_run_tests与最终代码评价共用该入口。原socket类保持，必要loopback受控，不开放外网。此处的新9次资格不改变旧CAL2的六个技术未知，也不修funcy/slugify或替换题目。

只引用原532KB来源摘要的path/SHA和必要计数，不复制其完整logical_cells/测试正文。计划、runtime和release引用在配套JSON中保留。

## OH及宿主控制的失败与实际执行

[OH方法](software-bridge-v052-openhands-reference.md)明确采用固定官方Agent/Conversation、官方TerminalAction/Observation/finish及隔离executor，非完整默认preset；每次fresh bash的实际限制在工具description和user前言均披露。原resident未装tools，因此新增同commit独立overlay与最小锁定依赖，没有升级SDK或数值库。

OH早期三个setup错误发生于pytest临时目录；其后缺工具包和固定SDK不接受普通factory注册的错误，均在创建Conversation前停止。修复后初态捕获和context控制通过，真实合成loop完成4程序响应和唯一共享测试。末尾断言误读status而实际字段为outcome，随后只从已保存result/request/command补完判断，没有重新跑该SDK场景、shell或测试。

[受管/宿主方法](software-bridge-v052-host-method.md)保留初4项控制与仅引用闭合相关的一次增量。来源控制的首fixture错把execution_identity写成evaluation_identity也单独保留。新版“通过”是有限修复后的新凭据，不抹掉原失败，也不把程序响应当真实native模型账单。

## 实际初态资格的两个原退出

### r1：在tokenizer文件集合门处停止

[原退出回执](../../artifacts/software-bridge-v052/input-controls/actual-initial-exit.json)记录exact tokenizer file-set gate不一致。停止发生于AutoTokenizer初始化前；实际SDK请求0、编码0、模板渲染0、模型0、业务测试0、权重和GPU均0。原declaration和退出保留，不把它解释为context容量不足或模型故障。

### r2：2个真实SDK捕获边界，只有OH原请求完整保存

[第二次原退出](../../artifacts/software-bridge-v052/input-controls/actual-initial-r2-exit.json)记录已到达2个真实SDK初态捕获边界。第一个OH_ref原请求、native输入、projection与capture均已保存，selected prompt 5,024 token，输出预约2,048，fits=true；该原件可直接复用，不重建或重编码来证明同一事实。

第二个PS1在capture后的计数断言、原request导出和Γ1/native容量测量之前停止。冻结harness的_completions是在LLM入口累加，不能当作已经返回模型响应的次数。这是资格测量计数错误，不是SDK/模型实际生成故障。

PS1原provider request文件没有落盘，原provider request SHA也没有保存；只有完整真实SystemPromptEvent、user MessageEvent、实际工具schema和冻结转换/config依赖可用。因此独立重物化只能称“来源绑定的确定性重物化”，不能称读取先前存在的raw request，更不能声称与不存在的原provider SHA作过独立同值比较。

r2实际模型、预约、工具、业务测试、权重和GPU均0。整个进程在最终编码/render/cache汇总快照落盘前退出，故r2累计tokenizer次数在本分册保持null；不能因PS1测量未进入就把整轮编码数填0。原OH容量凭据独立保留。

PS1实际harness/team决定bookkeeping保持原值，不加shim、回滚或转移到正式episode；它不等于模型生成。OH不具备同一个受管team meter，不强行套相同计数。

## 后续独立完成仍为pending

本静态第一部分将以下内容明确标为pending，交由另一个完成补充记录闭合：

- 原PS1形状依据完整实际事件和冻结转换依赖进行来源绑定重物化；保留原request未落盘、原SHA缺失事实，不再触发同一SDK捕获。
- 仅原其余十个从未捕获的初态形状，按独立修订和release处理；原OH直接复用，不重采。
- 最终12形状的来源、容量及完整计数摘要，以及root独立模型准入。纯控制通过和本文件封存均不代替这些条件。

本分册不改源码或release。详细初态方法见[初态资格说明](software-bridge-v052-input-qualification-method.md)；后继完成文档应引用本文件及两个原退出，而不是覆盖它们。

## 零新增模型与来源索引

本准备阶段真实模型调用0、权重装载0、GPU worker0、optimizer/actor/critic/backward更新0。programmed owner的4响应与404合成账单字段不是实际生成费用。原HOLD成本不转入v052，旧未用预算不转移。

- [配套静态JSON](software-bridge-v052-preparation.json)：所有顶层summary和详细文档的绝对path、SHA、bytes引用及分层计数。
- [来源控制](../../artifacts/software-bridge-v052/source-controls/summary.json)与[正式来源资格](../../artifacts/software-bridge-v052/source-qualification/summary.json)。
- [OH控制](../../artifacts/software-bridge-v052/openhands-controls/summary.json)与[只读尾断言完成](../../artifacts/software-bridge-v052/openhands-controls/readonly-completion.json)。
- [宿主引用闭合增量](../../artifacts/software-bridge-v052/host-managed-controls/summary-reference-closure.json)。
- [初态纯控制](../../artifacts/software-bridge-v052/input-controls/summary.json)与两个原退出回执。
- [报告器控制](../../artifacts/software-bridge-v052/report-controls/summary.json)和[报告方法](software-bridge-v052-report-method.md)。

本文件的编写只读现有摘要，没有新测试、分词、SDK、模型、资格执行或大轨迹重读；封存之后不在原文件中补写新“通过”状态。
