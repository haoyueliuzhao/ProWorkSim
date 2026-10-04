# ProWorkSim

## v0.30 模型与 O1 选型：9B已完成，两新模型修复加载记录后接续

最新进度：9B完成12槽，API2/4、修复4/4、O1 0/4；两个新模型均已下载完整，但旧尝试在零采样阶段写加载记录失败。现已修复set的JSON表示，8项定向恢复测试和Ruff通过，GPU5于20:27成功预约，SWE-Next于20:39从干净快照在GPU5进入真实资格，Devstral继续排队。原结果与失败成本保留，详见[恢复记录](docs/experiments/software-model-selection-v030-recovery.md)。以下首段为原启动阶段记录。

更新于2026-10-04。按[新审计](docs/reference/audit-v029-next-v030.md)实施[本轮协议](docs/experiments/software-model-selection-v030-protocol.md)：保留v0.29完整工作0/8、无有效支持、依约停止的结论，后续先验证共同模型载体的API使用、真实失败修复与可微更新能力。三个候选的监督队列已于北京时间2026-10-04 13:54启动：9B于13:59在GPU4开始运行，恢复原3/3状态后进入真实资格测试；14B与24B等待完整权重下载及校验。当前尚无正式开发筛选成绩或参数训练收益；后续按条件自动接续并在整批结束时更新[运行报告](docs/experiments/software-model-selection-v030.md)。[启动记录](docs/experiments/software-model-selection-v030-launch.md)保存冻结版本、计划和进程凭据。

新工作世界从共同根目标和空任务表开始，成员自行形成、修订任务、责任与依赖；公开反馈分别呈现上游回归、consumer正常路径、成员自测和未测部分。[六个新开发合同](examples/software-sources-v030/README.md)复用一个固定Marshmallow仓库，分为2个API正常路径、2个真实故障修复和2个双成员O1根目标案例。它们永远属于模型／接口开发池，不用于参数训练、贡献估计或独立确认；不是六个独立仓库，也不重复旧sqlparse同题窗口。

候选固定为当前9B端点、SWE-Next-14B和Devstral-Small-2507，最多6案例×2seed×3模型＝36条正式筛选经历，三类成绩分别报告。每臂先经过最多4次原生技术诊断、1次可逆诊断更新和1次更新后单调用回流；保持原概率门及全部实际token，训练就绪还要求真实近16K序列完整反传。诊断后完整恢复共同actor／critic／两个optimizer／RNG，筛选不更新参数；未通过资格或全部候选不合格均按协议结束，不因低分增加候选或补采。

源码参考解、坏控制、O1生命周期和一阶分配已做CPU核验，[最终集成控制](docs/experiments/software-model-selection-v030-cpu.md)71项通过且Ruff通过；[原生模板资格](docs/experiments/software-native-templates-v030.md)的18个模型／案例组合、72次脚本化SDK请求全部通过，真实模型调用为0。CPU小模型的真实反传与恢复控制、脚本化规则执行、候选真实模型资格和软件工作成绩分别记账。新[一阶数学修订](docs/design/experience-allocation-v030.md)采用对数N、显式历史／覆盖双锚，并分开G-raw、G-lift与I-P；本地未取得完整V1.3原文，只声明可见一阶条款的实现，本轮不执行分配效果实验。

[候选来源与模型研究](docs/research/software-model-candidates-v030.md)记录固定revision、许可和有限重合检查；[旧27B清理记录](docs/operations/model-27b-cleanup-2026-10-04.md)记录已删除的权重、专属缓存与探针，合计约51.75GiB分配块，9B及历史实验、检查点均保留。[当前研究入口](docs/research/id-vtdo.md)汇总现状与回到同模型B／G-raw／I-P比较的条件。

## v0.29 新来源首窗已结案：完整工作0/8，无配置更新

[详细结案报告](docs/experiments/software-allocation-v029-final.md)：同一sqlparse情境、固定A先手的8个预登记seed全部可评，7槽有固定交付但consumer失败、1槽无固定交付，完整工作0/8。七份固定成果的库API和所选上游回归均通过，consumer均把Statement当Comparison而提前异常。一次交付后的成员自测实际暴露该错误，但预算内未修复；不能把全部测试绿色或模型自述扩大为任务通过。

两成员各M=8、n+=0、v=0，无可配置支持，按[冻结协议](docs/experiments/software-allocation-v029-protocol.md)结束。没有B/G/I试训、正式更新、schema开发、TextFSM确认或后继工作；actor/critic累计仍为3/3，本轮未得到ID-VTDO效果结果。478次真实响应和全部失败原件保留，详见[结案机器账](docs/experiments/software-allocation-v029-summary.json)。

北京时间10月4日04:28全部结束，实际使用GPU2一个owner，worker占用1.783123 GPU小时，原进程已退出。新来源、过程Mapper、实际token学习桥接及[36项CPU检查](docs/experiments/software-allocation-v029-qualification.md)与真实模型结果分别记录；[启动快照](docs/experiments/software-allocation-v029-launch.md)和[自动终态报告](docs/experiments/software-allocation-v029.md)保留原状态，不把等待记录误作当前运行状态。

## v0.28 动态职责修订与后续软件实验

按[10月3日审计](docs/reference/audit-v027-next-v028.md)实施[新协议](docs/software-allocation-v028-plan.md)：补编辑前消息、转交通知与归还、等待唤醒及有界阻塞。稳定成员自主承担预定义子任务，不声称完整任务分解。新Mapper以固定交付净定义及实际输入/验证关系分类，撤销或无关注释不制造第二类。

阶段1为2情境×2先手×2seed共8条9B开发经历，冻结参数、零更新；生成前原请求、SDK流、版本、独立验收与中断全部保存。[原运行记录](docs/experiments/software-development-v028.md)给出实际等待/启动/终态，未启动不补零。该轮恢复按当时指令仅在GPU5排队、单实例运行，原等待截止为北京时间2026-10-06 00:00；这不是当前v0.30的GPU范围。原运行与[修复恢复轮](docs/experiments/software-development-v028-context-repair.md)已于10月3日19:44结束：8槽全部可评，4通过/4未交付，GPU5已释放；原异常attempt保留，新旧接口结果仅作状态总账，详见[恢复运行报告](docs/experiments/software-development-v028-recovery.md)。 完整协议、九次尝试、故障与成本汇总见[本轮实验报告](docs/experiments/software-development-v028-summary.md)。

[SWE-smith来源阶段](docs/experiments/software-sources-v028.md)已取得3个整仓分用途的可执行任务：sqlparse训练、schema贡献开发、TextFSM独立确认，已实跑缺陷/修复及联合依赖控制。程序结果、开发模型工作和B/G/I效果分开；现有配置器登记为单窗口线性N/基础锚变体，并区分坐标斜率与b中心化C。

## v0.27 转向软件协作中的在线经验分配

按[10月2日审计](docs/reference/audit-v026-next-software-v027.md)完成[协议修订](docs/software-allocation-v027-plan.md)：保留世界内核、受管OpenHands SDK和共享学习器，主线改为模型自行分工、代码工作与集成，再比较基础B、一般成员—轨迹重加权G和结构化成员配置I的独立更新后表现。零售SQL保留历史结果与迁移控制，不再优先扩建。

本次新增两成员私有代码副本、轻量任务板、固定补丁与真实三方集成；软件工作证据接入原始成员投影。[通用配置器](docs/design/experience-allocation-v027.md)支持多情境、多成员、多类别、完整配对有限差分C、支持覆盖N及双KL锚，试训和正式配置都进入原actor损失。原始分母、critic与可信失败残余保持独立；接口开发资产即使删掉附加标签也不能进入训练。

[实施与验证报告](docs/experiments/software-alignment-v027.md)区分真实CPU代码执行、受控SDK响应、小模型反向控制和研究效果。已有Marshmallow仅用于接口开发；[SWE-smith来源方案](docs/research/software-sources-v027.md)完成用途和谱系准入，实际任务、环境与新运行预算尚未冻结。尚未运行9B软件采集、B/G/I效果比较或新GPU队列，不继承v0.26资源上限。[当前理论入口](docs/research/id-vtdo.md)已重组，旧V1与历史阶段[原文归档](docs/research/id-vtdo-v1-through-v026.md)。

## v0.26 相互依赖载体验证已结案：完整职责0/16

[本轮详细报告](docs/experiments/collaboration-v026-final.md)：四情境×两通信条件×两次固定seed的16个逻辑槽经恢复全部可评分，normal与single_pass完整职责均0/8、均分均0。共17次实际业务尝试，含1次原中断；[原R2](docs/experiments/collaboration-v026-c1-r2.md)的完整主比较仍未知，[恢复描述性结果](docs/experiments/collaboration-v026-c1-recovered.md)不覆盖原缺失。未执行训练更新，完整状态从旧3/3恢复；没有学习或配置算法收益结论。

[业务附录](docs/experiments/collaboration-v026-work-analysis.md)区分局部成果与完整合同：恢复后16槽的源端6次SQL执行成功，其中2份固定提交的表内容与单位正确，但类型和显式元数据依赖仍不合格；消费端成功构建0次、提交0次，未形成双向闭环。[C0审计](docs/experiments/collaboration-v026-c0.md)和[CPU资格](docs/experiments/collaboration-v026-qualification.md)分别保留；12条程序正路径通过不等于真实模型成功，CPU最小上下文余量仅4 token。

北京时间10月1日21:47:36全部模型结束，含两次加载失败与一次显存保护中断累计 **2.468925 GPU小时**。用户授权的累计预算为8 GPU小时、显存保护为80GiB；本轮未触发时间预算停止。[资源附录](docs/experiments/collaboration-v026-resource-analysis.md)保留恢复、末态证明缺失及退出核验，[精简结案数据](docs/experiments/collaboration-v026-summary.json)提供分母与证据摘要。C2新支持、C3配置对照及额外Q=B更新均未启动。

## v0.25 当前支持与更新后工作已结案

[本轮详细报告](docs/experiments/composition-pilot-v025-final.md)覆盖原采集、R1整窗重算和R2评价恢复：16条当前策略联合经历中只有1条完整有效主动交接，未达到每类至少2条的配置支持门；因此实际保持Q=B，没有运行非单位权重贡献探测或正式配置。R1完成283/283决定和92010自身输出token的一次actor/critic更新，完整状态累计由2/2变为3/3。

R2独立确认12/12均可评分，完整职责2/12（16.7%）；成功分别为正确初稿核准和数值不变维护，不能称作新修复。2个新后继均可评分、完整职责0/2，没有额外更新。没有这些确认情境的更新前配对端点，所以参数学习收益和ID-VTDO配置增量均未估计，不能与v0.24另一批材料上的3/12直接相减。

原单次资源查询失败、R1确认的系统临时目录磁盘故障及其成本完整保留；R2把临时目录迁到数据卷，沿用原模型/世界/评分代码完成后续工作。北京时间9月30日14:56:38全部阶段结束，本轮含两次中断累计26.524491 GPU小时。[精简结案数据](docs/experiments/composition-pilot-v025-summary.json)、[工作详析](docs/experiments/composition-v025-work-analysis.md)、[训练与支持详析](docs/experiments/composition-v025-training-analysis.md)和[资源附录](docs/experiments/composition-v025-resource-analysis.md)给出逐项证据。

[原方案](docs/domain-collaboration-v025-plan.md)、[分项程序准入](docs/experiments/retail-work-v025-qualification.md)、[原停止记录](docs/experiments/composition-v025-stop-note.md)、[R1恢复](docs/domain-collaboration-v025-r1-plan.md)和[R2仅评价恢复](docs/domain-collaboration-v025-r2-plan.md)保留历史边界。三份自动终态报告均原样归档，不将原失败改写为正常完成。

原支持窗口16条经历可通过[含成员协作有向图的HTML审阅页](docs/reviews/v025-joint-experiences/index.html)、[中文导读](docs/reviews/v025-joint-experiences/reading-notes.md)与[离线ZIP](docs/reviews/v025-joint-experiences.zip)查看。报告工作仅只读整理已有证据，未新开模型实验。

## v0.24 MC／交接RTG对照已结案：MC出现有限工作改善

[本轮完整报告](docs/experiments/credit-pilot-v024-final.md)：54个新episode全部闭合，MC与Handoff-RTG各完成两次actor/critic更新，θ0/MC/RTG评价各12/12已知。完整职责分别为0/12、3/12、0/12；预定主比较RTG−MC为−0.25，MC相对θ0为+0.25。MC的三个成功包括一次新正确交付、同一正确初稿B情境的两次独立核准；不将后两者称为修复，也不将单训练seed结果推广为稳定总体优势。

共同D0来自本次θ0，两个分支的完整状态恢复与同轨迹消费证明通过；第二窗各自新采。[训练信用分析](docs/experiments/credit-pilot-v024-training-analysis.md)与[工作成果详表](docs/experiments/credit-pilot-v024-work-analysis.md)区分目标变化、局部成果和完整职责。两方法三端点维护完整职责均0/4；RTG有局部内容改正，但没有完整职责成功。

北京时间9月29日07:32全部模型阶段结束，累计19.408172 GPU小时、墙钟11.130216小时。RTG训练有同卡竞争，耗时差不能直接解释为方法效率差；原模型进程均已退出。[精简结案数据](docs/experiments/credit-pilot-v024-summary.json)及[自动原始汇总](docs/experiments/credit-pilot-v024.json)保留证据、56次本地上下文拒绝和全部成本。外部九例、144例后继与ID-VTDO干预未启动；[原计划](docs/domain-collaboration-v024-plan.md)、[启动快照](docs/experiments/credit-pilot-v024-launch.md)和旧v0.23结果保留。

## v0.23 四窗Q=B学习已结案：未见完整职责改善

[本轮完整报告](docs/experiments/learning-pilot-v023.md)：24个训练episode全部完成，actor/critic各更新4次；内部终评24/24、外部初末6/6完成。内部初评在原2.5小时门停止，仅19/24闭合，因此预定完整主点估计未知。19个已知配对完整职责1/19→0/19，全部24个终评均未完整完成职责；外部完整职责0/3→0/3，没有工作改善证据。

训练已出现一次对继承正确产物的独立核准，以及一次正确构建但未交付；没有成功修复正例。外部评分需区分产物检查、实际验证和最终声明，公开缺失数值规则仍有解释限制。资源累计21.890127GPU小时，所有模型进程已结束；原失败、缺失和评分保留。[精简结案数据](docs/experiments/learning-pilot-v023-summary.json)及[自动原始汇总](docs/experiments/learning-pilot-v023.json)可核对；新增报告分析未运行模型或评分。144例及ID-VTDO干预未启动。

## v0.22 可微路径与真实更新桥接

[本轮完整报告](docs/experiments/domain-v022.md)：函数式状态候选通过小模型梯度控制、三条9B实际反向及原概率门；公开复核合同已修正，6个新同源情境×两种呈现的完整职责均为0/6，没有呈现收益证据。原四片段B1在整窗时限停止；保留失败后，R1从原完整快照恢复同一24决策窗口，完成一次actor/critic更新，再由新策略执行两段新联合片段（0.2／0，均未完整完成职责）。这是新组合的工作—更新—再次工作接通，尚不能证明能力提升。

N1/W1准备后在GPU2/3并行，B1及R1使用GPU2；全部已结束，含失败与重算共1.602136 GPU小时，模型网络API调用0。指定TeamBench D2修订变体通过实际OS角色隔离和程序控制，外部模型成绩仍未产生。[阶段计划](docs/domain-collaboration-v022-plan.md)与[机器账](docs/experiments/domain-v022.json)分开保留数值资格、工作结果、更新和外部入口；144例pilot与ID-VTDO干预未启动。


## v0.21 数值／工作／任务三线修订

[本轮报告](docs/experiments/domain-v021.md)：N缓存重演与原采样概率逐项一致，完整有图／无图前向相同但仍未通过原训练数值门；独立E六例全部可评，分数1／0.4／0／0.25／0.2／0，仅一例完整完成职责，A/B尚未完整完成。新N/E共用GPU4约20.3分钟，0反向／更新／模型API，已结束释放。A/B合同及CPU正反控制已接通；TeamBench显式D2修复变体通过程序控制，角色隔离与外部模型入口仍未准入。[新方案](docs/domain-collaboration-v021-plan.md)保留四种资格分离，旧P1不回填，144例学习不自动启动。


## v0.20 同领域协作研究（P0完成，P1数值门未通过）

按[新审计方案](docs/domain-collaboration-v020-plan.md)，当前目标收敛到数据分析与数据工程协作；一个共享模型顺序服务独立角色会话。新增真实BF16基座/FP32 LoRA与概率归约配置，单常驻、无prefix或采样副本。用户仅恢复最多1 GPU小时的9B单卡P1，原27B双副本及144例后继不自动启动。来源/谱系和有限CPU准入与P1分别记录；[结构化后继方案](examples/id-vtdo-v20/study-proposal.json)明确不可执行，尚未产生基础学习或ID-VTDO增量结论。

[本轮实验报告](docs/experiments/domain-collaboration-v020.md)：真实来源3例33项CPU控制通过；两种9B单卡配置各在首条自身概率门停止，合计92.691 GPU秒，0业务/反向/更新，未启动144例后继。原数据、FP32 head的有限作用及资源竞争均分别归档。


**面向 ID-VTDO 的软件协作与在线经验分配研究环境。** ProWorkSim 提供持续世界、局部工具与可核验联合经历；模型选择分工、调度与执行，算法配置当前经历的训练权重，检验更新后团队相对基础分配和一般重加权的独立工作增量。世界运行、基础学习和分配收益分别验证。

[当前研究设计与实现状态](docs/research/id-vtdo.md)是研究入口；[v0.19 吞吐计划](docs/throughput-v019-plan.md)等历史实现和[v0.15 原线](docs/learning-v015-plan.md)独立终态继续保留。历史Q=B基础学习、旧H1和v0.26结论不重判。v0.27的新配置比较须使用相同完整学习状态、同批当前经历与独立确认；无可配置支持时停止本次有限研究，不自动追加无对照训练。

WorldCore管理权限、版本、采用、工作义务和问题处理；工作人员决定业务动作；场景控制器执行预声明事件。机构接受、内容正确、未知、服务故障和训练奖励分别记录。

## v0.19 执行吞吐优化（GPU 后续实验已暂停）

[本轮正式实验报告](docs/experiments/round-v019-final.md)汇总审计修订、原H1终态、两候选完整请求控制、失败与成本，并明确暂停后未完成事项；[机器记录](docs/experiments/round-v019-final.json)保留派生数值及原证据SHA。

[优化计划](docs/throughput-v019-plan.md)保留原业务预算、概率门和唯一共享学习器，新增显式 FP32/high 执行配置、精确 token 前缀缓存及独立世界双副本采集。副本只加载真实当前 actor 快照，不构造 critic/optimizer；整个窗口闭合并核验后才允许父进程更新。原 H1 不切换配置，尚未开始的 v0.18 后继等待进程已实际停止。

开发阶段9B两条真实请求的64输出诊断中，high使延迟约从10.8/17.1秒降到4.8/7.0秒；长请求进一步暴露旧Math-GQA的反向内存问题，新candidate已改用项目既有explicit-KV efficient-only路径。原数值门保留，真实长输出/反向与相应副本数的验收仍分别记录，不能将局部通过称为完整容量或学习收益。见[优化实验](docs/experiments/throughput-v019.md)。

原H1已在原冻结环境完成48/48已知评分，按预定完整责任优先规则选择 **Qwen3.8-27B＋OpenHands SDK**；这不是修复环境的完整四臂排名，也不是按均分最大化选择。[终态报告](docs/experiments/harness-v019-original-H1.md)保留5次NOT误拒、逐臂成本与缺失。正式学习初末均用同一新执行配置，118例主pilot仍为Q=B。

9B、27B均已完成原3条请求、2048输出上限下的两卡概率与真实反向控制。用户因资源需求于2026-09-27暂停后续路线，GPU等待配置已撤下，未启动新队列等待进程、27B双副本验证、迁移、主pilot或四项目评价。[暂停记录](docs/experiments/throughput-v019-withdrawal.json)保留未部署边界；已有代码、原H1与性能结果保留，不自动改跑其他模型。当前容量结论限于已测请求，尚无本轮学习收益结论。

## v0.18 执行器修订、交叉复核与基础学习（机制保留，未启动后继由v0.19接续）

[实验报告](docs/experiments/harness-v018.md)记录真实 WorldCore/DuckDB 对照与 SDK 控制。已窄修合法 `NOT (...)` 被当函数拒绝的问题；四项目将终止、记录可信性与独立可评分开，可信格式失败保留已知业务结果。同一来源/口径下实际准备正确、错票数、错金额三类固定提交，解除旧复核目录的确定性关联；18 个真实准备世界通过独立内容检查，没有将标签提供给模型。

原 H1 源和 48 个槽保持，旧后继在尚未启动模型时已实际停止。新阶段将原 H1 选择限定为旧环境下的候选，修复环境确认并入 8 例实际迁移；迁移通过后 fresh 开始 **64 训练＋27 初始评价＋27 最终评价＝118 例**，四任务主效用各占 1/4。四项目静态/变更各 2 例另行评价。这些预算不代表已完成模型样本；实际进程与终态见报告。

主 pilot 每情境当窗最多 2 条、每类支持门槛 2，最多只有 1 类达标，组成自由度为 0。独立的两联合情境各 8 次计划必须绑定完成后 pilot 的最终权重；它只测支持，不执行 ID-VTDO 配置干预。

## v0.17 组合比较与四项目评价（历史协议，原 H1 已收口）

[实验报告](docs/experiments/harness-v017.md)记录了来源选择指令与两级格式反馈修订。原S1已经全部结束；27B有14个OOM未知，旧选型及后继准确停止，未填零。该阶段新H1单独固定9B两卡/27B四卡，两条长请求容量通过后实际启动48例比较；当时尚无最终选择，其后终态见v0.19。

原后继的 112 例 pilot 尚未开始，已在 v0.18 明确替换为上述 118 例协议，不回写本阶段记录。四项目正式评价已能拒绝共同错误而差额为零等负例；其模型采集后汇总缺陷及修订见 v0.18。

## v0.16 SDK 工作人员与独立实验（历史阶段）

[实验报告](docs/experiments/harness-v016.md)记录了真实 OpenHands Software Agent SDK 1.49.6、角色私有工作支持、受管版本编辑与原始模型 token 的接入。独立六情境来自新 UCI 实体；四项目已通过两版合同与混合版本错误的 CPU 见证。

真实 9B H0 已完成3例、33次生成、0次参数更新：接口校准接通；实现任务正确构建但未提交（R=0.5）；双成员未完成交接（R=0）。该阶段尚无 harness 收益比较，H1 当时为不可直接执行的规划；其后实际启动见 v0.17，后继边界修订见 v0.18。完整失败、资源、SDK表示修订与协议描述勘误均保留。

## v0.15 真实来源与候选模型实验（已结案）

[实验报告](docs/experiments/learning-v015.md)区分真实来源准入、模型接口、开发筛选和未执行的学习阶段。UCI Online Retail已进入可实际编辑SQL、构建、固定提交和独立复核的世界；Marshmallow已具备隔离代码工作与父进程独立验收，原验收绕过反例保留。

旧7B完成36例、完整责任0例；修正EOS后的9B完成36例、完整责任3例。27B全部36次尝试结束，其中14例因CUDA OOM不可评，22个已知结果中完整责任11例；全批评分不完整，旧选择器及N0/N1后继准确停止。旧错误EOS运行仍排除比较。[结案证据](docs/experiments/v017-original-s1-closure.md)保留未知、成本和逐事实重复结果；不能宣称完整排名或学习收益。

## v0.14 工作学习与数值修订

[实验报告](docs/experiments/learning-v014.md)记录了新的显式事实/持有者/规则任务、工具返回与上下文对照、分组真梯度诊断，以及同终局合同的 MC/联合 RTG。E0 六例在12k下消除了当组上下文停点，业务回报仍未改变；局部返回压缩没有减少总体token消耗。

正式两条件各3seed原计划744例，实际闭合264例；六个运行均在预设概率门停止，actor/critic各完成3次更新，480例未启动。最终评价缺失，**尚不能判断工作学习收益或MC/RTG优劣**。旧失败不填零或补采，当前多方法支持与单岗位交接分别报告。

[数值修订](docs/learning-v014-numeric-repair.md)复现了六个失败点，并验证完整FP32显著减小这些缓存/整序列概率差。新入口默认 `matmul_precision=highest`；显式high旧协议及历史冻结结果保留。新精度四例容量已完成，行为/反向各41项核验通过；该结果与原正式失败对照分开，不将数值稳定性当作学习收益。当前仍只有一个构造SQL来源家族。

- [工作任务与显式因子](docs/design/learning-work-v014.md)
- [公开呈现与确切检索](docs/design/work-presentation-v014.md)
- [时间信用、实际梯度与评价保护](docs/online-credit-v014.md)
- [冻结协议](examples/learning-v14/)

新精度有限运行示例（输出目录必须不存在）：

```bash
PYTHONPATH=src CUDA_VISIBLE_DEVICES=0 .train-venv/bin/python scripts/online_learning_v013.py \
  --protocol examples/learning-v14/capacity-highest12.json \
  --model /absolute/Qwen2.5-7B-Instruct \
  --weight-manifest /absolute/qwen-weights.json \
  --output runs/learning-capacity-new
```

## v0.13 历史在线工作与训练

严格复现历史结果应使用报告中的冻结提交；当前入口对未指定精度的新协议默认使用highest，不能把当前重新运行视作原数值协议。

[实验报告](docs/experiments/online-v013.md)区分接口对照、开发故障、正式在线更新和冻结新事实评价，全部失败保留。本轮真实Qwen已完成两次共享actor/critic更新；初始与最终各8例评测的回报逐项相同（平均均0.3），尚无工作成果提升证据。[冻结协议](examples/online-work-v13/)包括四种等份额短任务、两轮基础RL、初始/最终模型的单岗位与团队评测。当前只有一个development来源家族，内部锁定事实不等于独立来源泛化。

- [公开工作接口](docs/work-interface-v013.md)：按别名/确切版本读取拆分，完整公开schema，角色工具集合与可追溯观察压缩；真实拒绝不修答案。
- [短任务及奖励](docs/online-work-v013.md)：交接、实现、复核、完整链，真实准备前缀排除于当前目标动作/奖励，按一次工作成果计分。
- [共享在线训练器](docs/online-learning-v013.md)：单actor/LoRA/optimizer、独立critic，真实token概率核验，全成员同步更新、清KV；无信号明确零步。
- [在线窗口合同](docs/online-window-contract-v013.md)：当前权重/情境/协议绑定，原始分母、未知与基础mask分开，无支持不阻断Q=B。

实际训练使用独立.train-venv（Torch/Transformers/PEFT及项目openpyxl、固定duckdb1.5.5均需安装）。完整基座文件manifest校验、单卡FP32与数值profile按协议执行；本轮使用A100 80GB，其他显存配置尚未验证；运行前选择有容量的GPU，代码不会终止其他任务。以下输出目录必须不存在：

```bash
PYTHONPATH=src CUDA_VISIBLE_DEVICES=3 .train-venv/bin/python scripts/online_learning_v013.py \
  --protocol examples/online-work-v13/o1-online.json \
  --model /absolute/Qwen2.5-7B-Instruct \
  --weight-manifest /absolute/qwen-weights.json \
  --output runs/online-new
```

冻结评测改用`o2-evaluate.json`；不带restore使用初始actor，带`--restore-checkpoint runs/online-new/online/window-1/checkpoint`恢复完整最终共同状态，使用新的output。evaluate完全跳过学习前向/反向/概率复算。resident_direct为进程内真实模型计算，网络HTTP=0，原attempt字段名不代表HTTP。

## v0.12 历史预检结果

新增三名真实模型工作人员的手动信息交接、联合经历与完整成员投影、三值工作有效性、支持统计和多轮PPO准入。详见[实验报告](docs/experiments/id-vtdo-v012.md)和[冻结配置目录](examples/id-vtdo-v12/README.md)。

- 规则见证13条、73/73项判据通过，证明有限工作链与两种交接方式可行。
- D0的16段接口比较中，两后端均未通过跨报告/SQL的预声明完整工作门槛。
- DeepSeek的16条三成员联合经历中，V=true有3条，分属不同情境；缺实际token IDs/行为概率，本批无可训练actor支持；也不跨后端补Qwen支持。
- 原Qwen队列中断后，另冻新数值路径与公开合同，完成16条本地联合经历、952次实际响应，全部为可评零奖励。两批不合并，原失败不回填。
- 完整多轮PPO配方与CPU的Q=B损失/梯度/优化器恒等核验已建立；本轮未执行真实模型更新，D4–D5贡献调权和学习收益未建立。

以下单角色API示例保留原入口配置；历史v0.12三角色采集、只读物化与训练准入方式见该目录及[模型接口](docs/model-interface-v012.md)、[联合经历合同](docs/team-rollouts-v012.md)、[多轮PPO合同](docs/multiturn-ppo-v012.md)。

## 安装与真实模型运行

需要 Python 3.11+；DeepSeek密钥放在`.env`的`DEEPSEEK_API_KEY`，密钥不进入检查点或提交。

```bash
python -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'

.venv/bin/proworksim scenario-build runs/model-report-demo --spec examples/model-v11/report-deepseek.json
.venv/bin/proworksim staff-run runs/model-report-demo --output runs/model-report-demo.json
.venv/bin/proworksim episode-assess runs/model-report-demo --experience runs/model-report-demo.json --output runs/model-report-grade.json
```

使用新世界目录及世界目录外的新输出文件。模型通过真实公开工具读写、采用、提交和回应，不由规则策略补答案。模板的有限输出语法与字段约束公开给角色。调用、失败、重试、usage和真实动作分开保存；单动作JSON不合规会保留并停止，不猜测修正。

[模型配置与本地服务](examples/model-v11/README.md)提供两个单角色API示例及冻结实验协议。每角色有决策、attempt、token、请求大小和金额上限，可能在名义120次决策之前停止。latest_observation仅从实际HTTP请求筛除旧观察，完整经历不删改，选择过程可核对。

## 可执行公开项目群

将上例spec替换为`examples/model-v11/sql-deepseek.json`，可让DeepSeek承担P1 SQL指标工作，其余角色固定。纯规则可行链使用：

```bash
.venv/bin/proworksim scenario-build runs/sql-rule-demo --spec examples/public-projects-v11/dynamic.json
.venv/bin/proworksim staff-run runs/sql-rule-demo --output runs/sql-rule-demo.json
```

P0准备数据，P1经营指标与P2客户分析协调客户／月份粒度，P3汇合核验。SQL、配置、构建结果及执行错误形成真实世界版本；SQL查询使用当前工作采用的确切共享版本。复制结果或篡改项目自测不能替代独立业务评价。

来源为固定版本的官方`jaffle_shop_duckdb`虚构数据；新增组织流程属于研究设计。当前使用受限DuckDB执行，不宣称完整dbt、生产CI或任意终端沙箱。[公开项目说明](examples/public-projects-v11/README.md)列出来源、权限、SQL范围与资源限制。

## 历史评价、继续与奖励

每次staff-run保存可读的起止快照、原经历区间、责任工作、确切提交/产物和终止原因。`episode-assess`只评价该段结束时刻；`world-assess`另查当前进度。后来完成的工作不能回填旧episode。

`staff-run --max-opportunities N`可在完整行动后截断；随后用`--checkpoint 上次输出`及新output继续，生成另一个有父子关系的episode。声明的真实准备前缀单列，不伪造历史。模型done、等待、场景边界、机构接受和内容通过是不同事实。

RewardSpec可通过`episode-assess --reward-spec 文件.json`显式启用。原分项评价保留；真实可评失败为0，未知依据、评价故障或服务重试耗尽等导致不可评的故障没有可训练奖励，不能混作0。重复批准、发布或消息数量没有正奖励。

## v0.11 历史实验结果与边界

v0.11阶段完成36个真实单模型开发episode，另单列原协议pilot、双模型协作、公开项目和接口校准；失败全部保留。

- **36个目标奖励均为0。**DeepSeek的2次制度completed仍未通过独立质量合同；其余为预算／格式失败。Qwen18次均在当前单JSON协议下格式失败。
- 公开项目模型试跑已实际改SQL、运行构建和查询，并根据SQL错误再次修改；完整交付及后继工作仍有失败，不能称可靠完成。
- 规则机制：条件范围7/7、历史边界14/14、四项目SQL58/58、奖励反例21/21。
- 第一冻结完整测试643项通过；第二冻结675项通过，Ruff通过。后续窄补修与数值诊断分别记录，不倒填旧结果。
- 首决策训练保留两次未更新的失败尝试；修订后用原3条零奖励轨迹完成1次LoRA更新、保存与重载。独立adapter接入试跑仍格式失败，未测得学习收益。

[详细实验报告](docs/experiments/model-executable-v011.md)区分规则结果、真实模型、接口修订及训练证据；[实施计划](docs/model-executable-v011-plan.md)、[模块设计](docs/model-executable-v011.md)、[模型协议](docs/model-policy-v011.md)和[首决策训练范围](docs/first-decision-rl-v011.md)给出具体合同。

```bash
.venv/bin/python scripts/condition_scope_experiment_v011.py --output runs/conditions-new
.venv/bin/python scripts/episode_boundary_experiment_v011.py --output runs/boundary-new
.venv/bin/python scripts/executable_project_experiment.py --output runs/sql-new --workers 3
.venv/bin/python scripts/reward_contract_experiment_v011.py --output runs/reward-new --executable-episode runs/sql-new/tests_tampered/episode
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check src tests scripts
```

Git保存协议与紧凑证据，完整世界、实际模型请求/响应和检查点保留在服务器runs。仍是有限模板、单一来源家族、单写者及完整行动边界；历史144次主批及正式ID-VTDO学习收益对照尚未执行。当前各阶段的已完成与进行中结果以对应版本报告为准。

## 历史与语义

核心世界格式沿用world-core-v0.9，模块分别版本化；旧世界不静默迁移。原经营单模板仍保留自身0.5格式入口。以新版实现为准，旧冻结结果仅作各自范围的历史证据。

- [核心语义](CORE_SEMANTICS.md)、[行动合同](ACTION_CONTRACTS.md)、[状态归属](STATE_OWNERSHIP.md)
- [当前ID-VTDO审计](docs/reference/id-vtdo-audit-v011.md)、[v0.11依据审计](docs/reference/model-executable-audit.md)
- [v0.10模块实验](docs/experiments/platform-modules-v010.md)
- [v0.9双模板实验](docs/experiments/template-expansion-v09.md)
- [v0.8持续工作](docs/continuous-work-v08.md)、[v0.7工作能力](docs/work-capabilities-v07.md)
- [v0.6多项目世界](docs/world-core-v06.md)、[v0.5状态一致性](docs/state-consistency-v05.md)
- [原始设计](docs/reference/design-v0.1.md)
