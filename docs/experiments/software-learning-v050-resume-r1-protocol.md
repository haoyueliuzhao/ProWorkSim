# v050-r1：导出版本校验窄修与原23训练槽接续

用户在检查显卡并确认v050导出失败后明确要求“修复问题”。本次完成原已授权v050，不新增科学候选、seed或样本。原冻结`fae3a5314852ab0b9c905dcb19c1150d434af0a3`、原设计/协议、原运行根`runs/software-learning-v050`和停止记录均保持；另建`runs/software-learning-v050-resume-r1`，先完成必要CPU控制和原件只读凭据，再提交冻结后接续。

## 问题与原边界

原S_star恢复及声明在物理GPU2正常完成，随后collect-0执行首槽`org50-train-LA-r01`。该槽已经正常业务关闭：R_joint/R_token=0，Q_joint/Q_token=10/12；14决定、14attempt、14完整回包，输入183551、输出3944、合187495token，账本同值，3次成员测试。全部已发请求settled/returned，held_tokens=0，没有在途生成或费用未知。

原槽有3次提交动作，其中2次合法固定提交、1次业务拒绝；最终锁定delivery-2并仅执行一次正式关闭验收。不能补验早先提交或可变工作区，也不能将通用manifest的空fixed_deliveries字面误当软件世界没有合法交付。原14条反馈全部保存，12条在首次同成员实际后继呈现，2条staff_done后无可达事件。逐槽evaluation guard通过。

错误发生在已闭合、机械测量continue之后的训练材料导出：v050 exporter实际生成`software-training-export-v0.50`凭据，但v050 Mapper只适配了record reader，仍继承v049校验器对`software-training-export-v0.49`的硬编码要求，抛出`ValueError: Original v049 export evidence seal differs`。原worker退出1、宿主closed_with_unknowns是导出/collector边界失败，**不是首槽正式R未知，也不是显存不足**。外层collection guard和entries未到达，仍保留缺失，不补写成通过。

原S_star worker 51.6819634437561秒、原collect-0 worker 384.6467568874359秒，合436.328720331192秒。原完整S_star及首槽起始/worker最终状态均4/4，新actor/critic/反向更新0。其余23条训练、三个更新和32个条件开发单位从未启动。原loader中间common3/3是既有构造步骤，真实采集发生在随后完整S_star4/4恢复之后。

## 唯一修订

新增隔离v050r1消费者，将原Mapper导出版本谓词严格绑定为v0.50。原seal摘要、episode路径、manifest/start/end/assessment/runtime文件引用、世界事件、成果与实际输入来源等其余校验继续执行；不将v0.49/v0.50混为宽松白名单，不伪造旧版本标签。

原Mapper spec、两类规则与顺序、每类两例门、原record reader、Γ1/O1、世界行为、奖励、原数值H=1及源材料均不改变。新export仅指向该修订Mapper；新学习来源桥只增加原首槽与新23槽的严格有序source registry，不改本人mask、48T/48K分母、支持计算或optimizer。所有原1021个冻结文件必须同字节，新增文件有独立source commit。

有限CPU控制覆盖真实SDK/世界归档的R0、本地和伙伴路线完整export→Mapper→prepare_window/support消费，以及错版本、篡改、错episode/来源等反例。此前v050的控制通过记录保留，说明当时没有覆盖实际导出seal的这处版本接缝；本次补测不冒称原控制已捕获该问题。所有新fixture失败及修正另记，不修改生产协议去迎合fixture。

原首槽只做一次只读重物化，输出到`runs/software-learning-v050-resume-r1-controls/original-first-rematerialized`，保存新entry/export及来源回执。新正式根只引用或复制这些同字节产物，不再次导出。过程中不模型生成、不分词、不执行业务测试/验收、不读取模型张量。必须确认首槽可信R0仍按原单位基础权重入场，保留其全部14次回包及3944本人输出；Mapper不能证明可配置路线时unmapped不删除基础材料。

## 唯一库存与预算

复用原S_star、declaration、design、六root材料及全部原seed/先手。s_star在新宿主中标为复用、零新增GPU初始化成本，而不冒称重新执行过。

- 原collect-0剩余7条：LA-r04/r07/r10，LB-r01/r04/r07/r10。
- 原collect-1的8条：LA-r02/r05/r08/r11，LB-r02/r05/r08/r11。
- 原collect-2的8条：LA-r03/r06/r09/r12，LB-r03/r06/r09/r12。
- 原首槽LA-r01只计一次，不重采、不恢复原已结束成员、不转移其未用312505token。

每新槽仍128决定/attempt、500000token、32成员测试和原90+10分钟制度。剩余训练最多23槽/11.5Mtoken；条件开发最多32槽/16Mtoken。新阶段最多55生成槽、27.5Mtoken、7040决定/attempt、1760成员测试；加原已发生部分，整个唯一v050实际上界为27687495token、7054决定/attempt、1763成员测试。这个较紧上界不替代或放宽原56/28M全局限制。

原24槽、每root12、全局48的基础质量保持。只有24原来源全部闭合并通过记录/Mapper/CPU训练准入后才做一次支持门；无可靠多类支持则供给结案、不B不开发。有支持才B50，B后方向退化仅S_star/B各八单位；可行则三个匹配更新和四状态各八单位。所有权重、比例/TV界、步幅、单方向以及开发前封存要求保持，失败样本和低支持残余不筛除。

更新均从同一原完整S_star4/4独立恢复，原H=1、最多5/5、每branch48小时更新区间及原前向/反向/optimizer上限不变。原首槽实际14回包加新23各最多128，实际材料行上界更紧为2958，但原3072保护上界不因此成为可转移配额。新旧费用只合一次，不把CPU重物化或重复引用算作新采样。

## 资源、停止与报告

沿用GPU0—7、最多三resident、原57344MiB准入与自身上限、60秒稳定、6144MiB实时余量及所有主机/磁盘/telemetry保护。检查显卡时GPU2/3/4曾满足门槛；实际启动必须重新经过原资源门，不将历史单次读数当持续容量保证。高GPU利用率不等于显存不足，但可能影响运行速度，既有时间预算不按成绩延长。

新源绑定和CPU门通过后，只接续剩余库存，不重启原监督器或覆盖旧停止。执行前充分绑定的局部context/预算终止保留结果并允许独立授权槽继续；新的输入/权限/来源/账目/副作用/共同服务或测量完整性问题仍封存并暂停必要未开库存，不自动重试。

最终按原首槽加新23训练形成唯一24，原S_star/collector成本只一次；另列真实更新、条件开发、已知生成费用/不确定预约、CPU分析与GPUworker时间。原导出失败、外层guard未完成与旧停止记录均并列保留。修复本身不是策略改进；不从首槽R0推断v049 B使能力下降。旧DA-s2、v046及26/3/48/缓存生产继续暂停，本窗口结束无自动后继。

## 启动前实际控制回执

[CPU总门](software-learning-v050-resume-r1-cpu-controls.json)记录46项不同控制最终通过：export/registry 26项、宿主20项。export/registry历次合计51次通过、3次断言失败、13次共享fixture配置错误、13次默认环境缺SDK跳过；宿主累计37次执行均通过。不能将这些累计数当不同案例数。失败包括CPU fixture缺少terminal_mc元数据、测试使用不存在的usage字段、篡改输入被更早的来源校验正确拒绝；修正限于fixture或断言。只读消费命令的Path类型错误、首导出无旧entry的宿主绑定遗漏及Ruff首次未使用import也完整披露。最终全src/tests/scripts Ruff通过。

原首槽一次重物化后，真实14决定/3944本人输出均准入、Mapper仍unmapped；成员001的T=2090/K=7，actor分母100320、critic分母336；002的T=1854/K=7，actor分母88992、critic分母336。其余23条缺失保持，临时CPU支持门明确拒绝将不完整供给解释为无支持。原首槽重物化之后的检查命令失败没有触发第二次导出。

[证据目录](software-learning-v050-resume-r1-evidence/manifest.json)保存可核查的小型原件副本及大文件的SHA引用。宿主控制和联通检查没有单独保存原始stdout，其JSON明确为已观察工具输出的事后转录，不冒称原始终端日志。真实原件准入确认1021个冻结源码文件和286个原运行文件保持；只读报告联通为56库存、原首槽closed/R0、55未启动，187495token与436.328720331192 GPU秒只计一次。独立只读代码审阅未发现剩余阻断。所有修复控制的新真实模型调用、GPUworker、实际分词、原业务验收、参数与反向更新均为0；显式synthetic SDK/世界fixture运行另列，不能当真实9B实验。
