# v050 最终报告来源与方法独立审查

本件为最终报告的只读支持分析。依据冻结协议和已有 JSON 原件，核对唯一库存、更新起点、方向封存、终态来源与状态守卫；未加载 `.pt`、未执行模型/分词/训练/业务验收/测试，未更改任何正式运行原件。机器凭据见同目录 `provenance.json`，抽取命令见 `extract-provenance.py`。其中 503 条为 JSON 字段、集合及小型文件摘要比较，不是 503 项新实验控制。

## 本轮回答的问题和可回答的范围

本轮是一次固定 Γ1、严格 O1、同一完整起点 S*4/4 下的局部 E2 经验组成敏感性窗口。先从 S* 新采集 LA/LB 各 12 条当前策略经历，再按照原本人目标、完整 H=1 学习配方进行 B；只有支持和实际 B 梯度成立时，才对事前排序选出的一个 root/member/class 方向形成 Q±，从同一 S* 分别独立更新。四个状态在事前冻结的同八单位开发面板评估。

它不是新的组织架构比较，也不是完整 I-P/I-S、Novelty 或 G-raw 算法实验。真实参数更新、实际开发差值、规则基线结果和一般组织协作收益必须分开陈述。S* 是 v049 的完整 B4/4，不是旧 common3/3；继承它不证明 v049 B 优于更早 S0。B−S* 是本轮固定面板上的一次实际更新差值；Q±−B 是本轮单个事前方向的有限差值。若差值为零，不能据此宣称精确 Contribution=0、参数完全不变或所有方向无效；若正/负，也不能推广为总体学习或合作效应。

## 训练来源与 Mapper

24 条唯一训练身份严格等于原冻结清单：LA seed202610130501—512、LB seed202610130513—524；LA 先手001、LB先手002。原首槽 LA-r01 来源仍是 `runs/software-learning-v050/collect-0/actual/episodes/org50-train-LA-r01/`，其余23来自 r1 三个 collector。首槽只读重物化的新 entry 只修导出消费者，不重跑世界、生成或原验收。原首槽正式 R/Q 已知，而原 collector 外层导出失败和未到达 collection guard 仍保留，不能把它叙述成原外层 worker 成功。

全24条、48条成员轨迹的本人输出进入基础训练，累计643个已准入真实决定、175532个本人目标token；三个最终更新各引用同一 entries、declaration、recipe和真实 native 输入来源。context 不作为本人输出目标，Γ1同输入严格引用不解压成新输入。全局基础质量为1/48，actor内部按该成员全部本人输出T、critic内部按实际生成决定K平均，分别保持48T/48K；可信 R0/unmapped 残余保单位权，缺失质量不转移。原v049旧8条不进入新材料。

Mapper 仍为 `local_lineage_delivery` / `evidenced_peer_product_delivery` 两类，每类至少2例。伙伴类别要求原生非同值采用、完整最终文件树谱系、本人精确同树测试、实际反馈可见和最终固定交付链；类别是观察到的共同交付路线，不是某成员的因果贡献或作者归属。同一共同路线投影到两名成员，不能把两份投影计成两次独立伙伴使用事件。

CPU供给门四块均可靠多类：LA/001和LA/002各local4、peer3，M=12、v=7/12；LB/001和LB/002各local4、peer6，M=12、v=10/12。所有块的I自由度为1，但实际只执行第一个合格非零方向。

## 唯一方向和权重

原排序 LA→LB、001→002、local→peer 中第一个候选即合格：LA/member_001/local_lineage_delivery。b(local,peer)=(4/7,3/7)，d=(3/7,−3/7)，rho=0.4666666666666667，epsilon=0.1，B实际混合梯度L2=0.007746008657106765。

Q+ local/peer组成=(0.6142857142857142,0.3857142857142857)，Q−=(0.5285714285714286,0.4714285714285714)。对应选中成员四条local权重分别1.075/0.925，三条peer分别0.9/1.1，其余41条成员轨迹仍1。Q+的含义是这一个LA/001块增加local组成，不应将其简称“增加合作”或“伙伴强化分支”。B和Q±所有critic目标、冻结优势、奖励和原顺序保持；critic不重加权。

方向封存时间1792002441.0071604，最早开发实际开始1792002562.2620924，提前121.2549319267秒。方向原件声明未读取开发结果；最终三个 composition-before-update 的权重均严格等于封存的 baseline/plus/minus 权重。没有按后续开发成绩挑方向、调epsilon或增加第二个方向。

## 更新终态、完整状态与源码

| 状态 | 最终执行来源 | 实际起点 | 最终步数 | 源提交 |
|---|---|---|---|---|
| S*参照 | v049 r1 `update-B/actual/checkpoint/checkpoint.json` | 原完整B4/4 | 4/4 | 原v049凭据 |
| B50 | v050 r1 `update-B/actual` | 同S*4/4 | 5/5 | abc30f7e060d3261f2a9ef6db132bbb57bdbfd1e |
| Q+ | v050 r4 `update-Q_plus/actual` | 同S*4/4 | 5/5 | 621219af2483f955c59d9df36b62ad46ba9eeb6d |
| Q− | v050 r5 `update-Q_minus/actual` | 同S*4/4 | 5/5 | 83d50e26824f55cab779a8dd91fffaffe7902bcc |

三路 `loaded-state.json` 均绑定同一个v049 checkpoint JSON SHA `b7e69820d705377804e4fc9afc329b8206e9cda532518d74ee99b686291d851f`，完整state tensor digest `ff8c828bcc475132d6d6bbddad3a114da62ace9da9c905e560d7d7c5a3cefc39`，恢复actor/critic/两个Adam/RNG并记录serialized_reload_exact=true。各自完整终态均success_boundary=true、source_before=source_after且clean、actor/critic各一次optimizer、643完整逐决定反向、完整checkpoint保存重载true。Q±不是从B继续更新，也没有拼接旧中断部分梯度。

原H1源码文件SHA三路相同 `c9264e59054831ed80a82cb02b6a5c1e9ef3b42a0adf072ba511e6b95d6d8c07`。每路原函数私有绑定凭据的code_object_identical/closure/defaults均true，未修改原module globals/owner方法。不同工作树的序列化函数code hash不同，不应把该字段跨工作树的字面差异当算法变更，亦不应称其字面完全相同；本审查依据原源码字节和各自本地绑定凭据。

三个最终actor摘要分别 `18f5fd7d…`、`7a76e938…`、`52dc58b5…`，actor Adam也各异。现成开发collection-guard证明B/Q±最终critic摘要均为 `6c8798957f3a6a06fc46cf1354bda01e585763d46c6377fbdc6d54a1fbcdc80a`，critic Adam均为 `845bac005760936b72e849639a6fd728e6ecde94db6f9f41c1e40fe41e0b5fa4`。这提供了只改变actor经验权重、critic处理保持一致的实际终态证据，无需额外载入权重重验。

原 `common-restore.json` 的3/3是构造阶段历史common恢复；实际采集/学习起点以随后 `loaded-state.json` 的4/4为准。`update/report.json` 的advantage说明仍带“zero-initialized”旧模板词，但实际 old_critic_values 全部非零、critic_had_nonzero_reward_history=true。最终方法说明应采用继承4/4的冻结非零critic，不修改旧原件、不照抄该模板误写成零critic。

## 唯一56槽与开发完整性

独立来源清单与原冻结身份严格匹配：24训练 + S*/B/Q+/Q−各8开发 = 56唯一槽，无缺漏、重复或新增seed。56槽正式R/Q都已知且无行政删失；56份逐槽evaluation guard均确认学习状态不变、actor身份/软件绑定保持、Torch CPU/CUDA RNG精确恢复。开发20个worker外层collection guard及source前后身份通过，实际完整加载状态与该分支的checkpoint digest相符。

S*/B各两worker（每worker四槽）来自r1；Q±各八个单槽worker来自 `runs/software-learning-v050-resume-r6-restored`，源码固定 `artifacts/software-learning-v050/resume-r6-source`，提交384e0a5c26f87dcd3207fe969447482fe0be4661。最终r6-restored的16个worker全部complete。各槽身份与来源已逐项写入provenance.json；该报告只统计唯一逻辑槽，不将多层父计划、观察凭据或行政移交重复计数。

## 必须披露的历史失败与协议变更

1. 原首槽结束后发生v050导出凭据与继承v049验证器的版本接缝失败；r1严格修绑定并只读重物化原件，然后接续23未开槽。原失败/外层guard缺失保留，首槽R0已知不改。
2. r1 Q−和r2 Q−两次因旧共享显存6144MiB余量门停止；r1 Q+也被同一旧宿主门停止。三次均未到optimizer，旧未完成行/在途前向边界仍有不确定，且没有能恢复累积梯度+RNG+游标的逐行断点。授权后从同S*完整重算，旧计算和费用保持。不能称三次原尝试也成功，不能把旧反向行加为新尝试进度。
3. r3拟议新任务尚未启动即因旧Q+失败停止，GPUworker0。r3取消固定并发3、60秒稳定、共享6144余量强停和自身56GiB上限，但当时未覆盖旧r1 Q+；r4统一修覆盖，并同PID接管事先预占GPU2。
4. r3/r4明确改变了原Q分支累计48小时限制：仍守三个分支合计144单卡训练区间小时，但重新分配未消费时间。最终r4新Q±各135481秒份额。不应写“所有原资源和时间限制不变”。成本代理另核原始实际及保守边界，本件不重复计算。
5. r4 Q−遇模型加载前首次cudaMemGetInfo OOM，12.528秒资源尝试后停止，模型/训练区间均0。r5新增充分绑定的零模型资源失败归档、退避重排；真正模型开始后仍不能自动重试。原r4故障和未开库存stopped仍保留。
6. r6按用户要求恢复总并发4，计入外部更新和资源取得。拟议GPU2单卡r7未部署，用户取消后使用原r6冻结源码另建r6-restored；旧r6/r5因行政移交的closed_with_unknowns汇总保留，但不能据此虚构16个开发技术未知。两路在途更新从未因这次行政交接重算。

最终资源政策为GPU0—7、总驻留4、每卡一个本项目resident、装载前至少46080MiB实际空闲、缓存目标min(73728,free−1024)MiB且至少45056MiB。显存预占是同进程allocator缓存，不是独占GPU租约。原56/28M生成库存与每槽500k/128决定/128attempt/32test、90+10分钟、18432/2048/page3072不变。旧生成余额不转移。

Q开发拆为单槽进程和资源政策变更，会改变装载成本、并发竞争和截止暴露；虽然本次无行政删失且数值源码一致，仍未证明跨GPU逐token一致，不能把GPUworker时间差直接归因于学习。应称为“含已披露宿主资源修订的原固定面板比较”，不要称所有过程完全同协议。科学方向、材料和种子均在相应输出前冻结，资源修订并不代表新增科学候选。

## 报告限定与非阻断发现

- 四个开发root都是人工业务合同；DA/DB复用v049家族，DC/DD本轮事前新写，但不是四个独立外部仓库，也不是独立确认。四状态都用同两个seed/root，F的八单位分辨率为0.125。
- 本轮完整56已知不抹除旧v049 DA-s2、v046技术未知、旧Q中断不确定或原停止记录；那些不属于本轮最终56唯一生成槽的缺失值。
- r2/r3历史文字将训练5个R0概称“5未提交”不准确：原LA-r01有合法固定提交，Q10/12。最终报告应采用原逐槽submitted/complete_delivery字段，而不复制该历史概称。
- 原更新advantage模板“zero-initialized”与实际继承critic不符，采用原实际数值和状态来源说明，并保留原模板记录。
- 本次JSON来源复核无阻断发现。没有恢复旧26/3/48、v046或缓存生产队列，没有自动第二窗口、追加seed或确认。

## 已读主要来源

- `docs/experiments/software-learning-v050-protocol.md` 与 `software-learning-v050-design.json`。
- `docs/experiments/software-learning-v050-resume-r1-protocol.md`。
- `artifacts/software-learning-v050/resume-r6-source/docs/experiments/software-learning-v050-resume-r{2,3,4,5,6}-protocol.md`。
- `docs/experiments/software-learning-v050-r7-cancelled-r6-restored.md`。
- 原plan/source-registry/support-gate/direction，三路最终update/loaded-state/checkpoint/learning-binding/原函数绑定JSON，56逐槽结果及guard、20开发外层guard、最终r6-restored外部完成回执与supervisor。
