# v0.31 两个新模型运行组合修订：有限选型协议

本批响应继续修复并实验的要求，只修改两个新密集模型的原生工具接口与学习概率重算路径。
当前9B、公共工作世界、六个开发合同、公开／隐藏检查、共享SDK、原两seed和选型门均保持。
这是新的v0.31运行组合选型，**不是v0.30结果重判，也不再称logging-only恢复**。
实际GPU数值证明、资格和筛选是否完成，以各自真实运行回执为准；协议文本不代表已经通过。

## 1. 保留的事实与可比范围

[v0.30原协议](software-model-selection-v030-protocol.md)及原运行、加载故障恢复原件继续有效。
9B已完成的12槽全部保留，API正常路径2/4、真实失败修复4/4、O1根目标0/4；
没有删除失败、重跑失败槽或用新结果覆盖旧提交。其共同actor／critic为历史3/3端点，
原生和数值运行组合不变，结果必须标明原执行源码。

SWE-Next和Devstral原先均为正式筛选0槽。原加载证据JSON失败及r1原生／概率门失败分别归档，
费用逐次累计；本批不将其改判为通过。SWE原先生成XML而不符合当时冻结的JSON格式；
Devstral出现了未提供的staff_done调用。两者还各有原概率门失败，格式修订不能替代数值验证。

保留9B参照的前提是其工作世界和运行路径不变。计划逐文件核对原冻结源码中的公共world、
SDK、9B路径、六案例资产及固定Marshmallow原件。新增两模型模块不要求与旧全源码摘要相同，
但任何受保护旧路径变化都会拒绝引用旧9B作为该批参照。
原密集模型v0.30加载模块只豁免此前已单列的证据序列化修订；它不是9B后端。

六案例仍来自一个已参与过开发的Marshmallow仓库。这是已见开发材料上的运行组合选择，
不是新的独立泛化集，也不能解释为纯参数量、后训练方法或ID-VTDO分配增量的因果比较。
本批不针对已知隐藏失败新增公开例，不泄露隐藏输入、参考实现或正确解法。

## 2. 固定组合与唯一允许改变的路径

| 对象 | 本批执行 | 起点／接口 |
|---|---|---|
| Qwen3.5-9B | 仅引用原12槽；不加载、不新采样 | 原完整3/3端点、原XML与函数式学习路径 |
| SWE-Next-14B | 最多一次新资格及12槽筛选 | 固定官方权重、新项目0/0起点；作者公开XML函数／参数内容协议 |
| Devstral-Small-2507 | 最多一次新资格及12槽筛选 | 固定官方BF16权重、新项目0/0起点；v13原生格式与按实际schema生成的提示 |

候选名单和权重revision沿用v0.30，不添加Small 2、普通Coder或低分后的回退候选。
新入口为[CandidateActor](../../src/proworksim/candidate_runtime_v031.py)，原生协议位于
[native_codecs_v031.py](../../src/proworksim/native_codecs_v031.py)。
SWE的XML是事前声明的新接口，不作为旧JSON失败的事后猜测修复；不同时尝试多种parser挑成功。
Devstral继续直接使用官方native输入token IDs，只提示当前请求实际提供的工具。
未提供staff_done／staff_wait时不推荐它们，也不为资格增加逃避目标的停止工具。

两个密集模型保留原权重加载、存储精度、温度、EOS、cached采样及FP32采样分数路径。
新[完整可微状态重算](../../src/proworksim/functional_dense_v031.py)对齐原prefill／逐token计算形状，
保留全部前缀KV状态和梯度依赖，不detach、不截断、不删错误token、不覆写原行为概率。
新声明profile在owner初始身份形成前绑定；新架构不继承9B或旧技术诊断后的优化器状态。

## 3. 正式新采样之前的真实GPU数值门

先完成两个候选各自的一次原失败trace诊断：SWE使用r1原native-call-1，Devstral使用原native-call-3。
它们分别对应原零起始index 0与2。直接读取原response文件，固定路径和SHA，消费全部原input／output IDs及行为logprobs。
本阶段不生成新token、不开业务episode、不做optimizer step，也不借短trace宣称近16K训练容量。

GPU控制由独立的[probe_dense_replay_v031.py](../../scripts/probe_dense_replay_v031.py)执行；
队列不自行实现另一套重算或改写其证明。控制包括原完整序列失败复现、原native cache重演、
新函数式无梯度重算及新函数式有梯度完整反传。原失败路径继续报告真实差值；
新的声明路径必须满足未变的max absolute error≤0.02、mean absolute error≤0.002。
必须核验原actor身份、完整common恢复和零新采样／零优化器步数。

计划冻结每个proof的profile摘要、实际测试文件摘要、原trace引用、终态、真实GPU耗时和资源／异常原因。
实际数值／native代码不得在proof之后改变；仅后续pipeline或文档提交变化不要求重复GPU证明，
因此记录probe当时source，同时逐文件检查其测试实现，而非强求全部提交ID相同。

两个proof均闭合后，按臂独立处理：

- `passed=true`且身份、完整token、原概率门、完整反传和恢复证明全部满足的臂，才可新采样。
- 真实`failed`终态的臂，记`numeric_preflight_failed`，0新原生调用、0正式筛选；另一合格臂继续。
- 未完成、缺失身份／源码／trace绑定、非零新采样或optimizer计数的证明不能伪装成已闭合失败或通过。

数值失败不自动重试、加profile或扩大搜索。真实中断由总driver保存已测内容和退出／资源原因后闭合；
未知不能填成0分，失败proof不能通过删除困难token取得准入。

## 4. 新鲜原生、更新与容量资格

每个通过前述数值门的新组合，仍完整执行原[技术资格](../../src/proworksim/model_qualification_v030.py)：
最多4次原生诊断生成、最多1次aggregate技术更新、最多1次更新后单调用SDK回流。
先保存完整共同状态；诊断数据仅来自独立技术fixture，不取自六个开发案例。
前三call必须正确完成公开工具目标；第四call的自然length或格式失败不删token，
全部真实trace必须通过原行为和有梯度概率门。

技术更新使用原PPO、两个原optimizer与clip，明确恒定正诊断信号不是软件业务reward。
验证真实参数变化、保存重载及新身份回流后，完整恢复诊断前actor／critic／optimizer／recipe／RNG。
筛选只能消费该共同状态，不能让诊断更新改善候选比较。

推理、训练接入、近16K容量分别报告。总training_ready仍要求真实压力序列输入加输出≥15,360，
完整反传与更新／重载／回流均通过；自然短输出记`capacity_not_demonstrated`，不强制minimum generation或补调用。
任何概率失败均零步，任何不完整common恢复禁止筛选。旧短trace GPU通过不能替代这一新鲜资格。

## 5. 原正式12槽与选择规则

每个通过完整新鲜资格的臂恰好执行原6案例×原2seed：`202610040701/202610040702`，
seed外层、case固定顺序。前4案例单执行者每槽64次机会，后2个O1案例A／B各64次机会。
每新模型最多1024次正式工作调用，两模型最多24个新筛选episode；加原9B12槽共36个声明结果位置。
未启动槽保留未启动，不计作失败0分。新鲜技术资格另最多8次native与2次回流；旧trace数值控制新增采样为0。

所有原验收、分类和排名保持：12槽全部已知，API／修复／O1各至少2/4完整通过才可选。
依次比较O1成功数、修复成功数、API成功数、两seed均过案例数、格式错误、实际总GPU成本，
最后用原固定候选顺序处理完全平局。消息数、任务数、方法类别数或合作描述不计收益。
无合格组合则本批结束；不换模型、增加seed、重跑9B失败或自动启动后继配置实验。

全部6案例继续`model_interface_development`，训练、贡献估计及独立确认资格均false。
没有B/G-raw/I-P更新、schema贡献开发或TextFSM确认；本轮不拼开发经历作为有效支持。

## 6. 资源、成本与归档

按用户最新“先抢占空闲GPU4、6”的指令，优先级冻结为`[4,6,5,0,1,2,3,7]`，GPU0–7仍全部可用；
仅两个新组合可启动、每组合一个单卡owner，最多两个并行。
空闲A100需≥78000MiB free、利用率≤5%、无其他compute进程且稳定60秒。
已授权预约仅按实际pid／start_ticks／UUID核验后释放，不终止其他任务。现有可选GPU5预约接口保持其原范围，
不能把GPU4／6预约交给仅支持GPU5的旧helper；GPU4／6的probe占位由总driver管理，普通正式队列仍执行上述空闲门。

保留原单worker RSS≤64GiB、GPU80GiB范围、实验原件上限128GiB、卷预留20GiB；
loading900秒、单episode2400秒、boundary600秒、单资格inference900秒。
qualification update没有统一时间帽，但持续资源监控；累计GPU／worker时长、全局墙钟和队列截止保持None。
旧traceGPU诊断由总driver按独立任务记录资源和终态，不能与正式筛选次数混淆。

128GiB原件门同时覆盖原v0.30、r1、整个本次数值probe ledger（含controller／queue证据）和新正式run。
admission proof显式绑定其candidate目录和probe ledger根目录；所有目录resolve后按相同或嵌套关系去重，
声明时保存大小，运行时实时重测完整并集，以包含后续控制记录增长。模型资产根目录及其包含关系拒绝纳入该原件清单，
不通过漏计数值probe原件扩大原有预算。

成本按候选分别记录并累加：原v0.30worker、r1实际新增worker、v0.31旧traceGPU证明、v0.31新worker。
r1的累计字段已含原加载失败，不能再次重复加。保留9B原实际成本；
下载／排队不作为GPU计算时间，预约占用单独留痕。排名使用实际总成本，且说明这是GPU分配期间墙钟，
不是利用率加权的算力积分。实际profile不同、旧尝试成本和加载时间均不隐藏。

队列与报告入口为[software_model_selection_v031.py](../../scripts/software_model_selection_v031.py)。
新机器计划、每步task边界、原始请求／响应、private assessment、异常和成本分别保存。
终态只生成v0.31报告文件；v0.30及r1原目录、旧报告和9B交付不改写。
代码与文档修订、CPU控制、真实GPU数值证明、新鲜技术更新、冻结软件成绩分别表述。
