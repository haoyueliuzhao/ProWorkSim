# v0.51 校准与条件 HOLD 汇总报告

**CAL0、CAL1、CAL2及本次获准的HOLD库存均已收口，历史缺口仍保留。** HOLD宿主complete，原32行中16个合格槽全部闭合、16个来源阻断槽未进入模型；已执行槽5份固定交付完整成功、11槽未提交、0份提交未全过。CAL1仍有9个分析缺证，CAL2仍有6个严格代码未知；HOLD缺失四个固定任务，完整八题主结果为null。阶段收口不等于完整比较或全部历史费用可知。

本报告直接复用各阶段既有终态摘要和已签发准入，没有重新读取或重算原始模型调用，没有重评分、重建请求、重新分词、补跑资格或启动额外模型。[总体机器报告](software-calibration-v051-overall-final.json)由准备好的只读脚本在HOLD终态后唯一生成一次，SHA为`1024a6089d0e4621752b5a75afff5a6effe43a86a1682b1576aba0fdd8c7b379`；其四题描述复用既有bounded/paired函数，只增加摘要层计算。跨阶段费用由[校准小计 JSON](../../artifacts/software-calibration-v051/final-calibration-subtotals.json)绑定三个原报告的路径、SHA 和字节数。小计 SHA 为 `49291ebab62ca8d6f5a1e011d3dc7c32bbdd9d269add9e7b57ddb5a0560e51f7`。各阶段的原始失败、暂停、缺证和后续独立修订继续保留。

## 1. 本轮回答的问题与不适用的结论

v0.51依次检查旧开发结果的固定交付评分是否有可解释的接入问题、原始模型的两条代码生成入口在同一本地条件下如何表现、原生单人框架与 ProWorkSim 单人接口及已有 S_star 状态在仓库任务中的表现，再对四个已有状态开展原预锁 HOLD 任务评价。阶段之间的任务、端点和分母不同，不能把所有槽拼成一个总成功率。

| 阶段 | 固定范围 | 主要端点 | 最终状态与保留限制 |
|---|---|---|---|
| CAL0 | 原 v050 的32个开发终态，只读复核 | 原最后合法固定交付及原评分 | 18完整成功、4提交合同失败、10未提交；未新增业务验收 |
| CAL1 | 24题 × reference/project 两路，原48槽 | 官方单候选 pass@1，另保留原 grade | 46完整回包；严格39已知、9缺证；完整两路均值与配对差为 null |
| CAL2 | 6题 × R/P/U，原18槽 | 三条件末树 R_code/Q_terminal；P/U另列固定交付 R_joint | 严格12代码端点已知、6技术未知；完整六题均值与条件差为 null |
| HOLD | 原8题 × S_star/B/Q_plus/Q_minus，完整32行 | 严格O1最后合法固定提交 F；不验未提交末树 | 4题的16槽全部闭合；另4题的16槽 source blocked；完整八题主结果为null |

所有新模型阶段均不进行新反向或 actor/critic 参数更新。CAL0只是对已有 v050 结果的独立只读一致性审计，不是新模型样本。HOLD评价四个旧检查点在新仓库任务与本次执行条件下的表现，不能与 v050 旧八单位合并为同分布复测，不能称本轮新增学习收益。原训练、Contribution、独立确认、v046及缓存队列保持原暂停状态，没有自动追加库存。

整体协议及来源范围见[校准协议](software-calibration-v051-protocol.md)、[仓库协议](software-calibration-v051-repository-protocol.md)和[CAL→HOLD阶段判断](software-calibration-v051-cal-to-hold-decision.md)。阶段放行条件是关键接入问题得到解释、剩余限制可明确声明，并非达到某个成绩门槛。

## 2. CAL0：原32开发终态的只读评分核对

[CAL0报告](../../artifacts/software-calibration-v051/cal0/report.md)及其[JSON原件](../../artifacts/software-calibration-v051/cal0/report.json)覆盖原32槽。已有1,830项只读一致性判断全部通过；22份最后合法固定树均绑定原锁、世界版本、同树公开测试和最终评分；读取的292个原私验判定与已存观察一致。原报告中没有发现本审计范围内的评分转换或固定交付接入错误。

| 旧状态 | 原槽数 | 固定提交完整成功 | 固定提交未全过 | 未提交 | 原 F | 原平均 Q_task |
|---|---:|---:|---:|---:|---:|---:|
| S_star | 8 | 5 | 1 | 2 | 0.625 | 0.7395833333333334 |
| B | 8 | 4 | 1 | 3 | 0.5 | 0.6171875 |
| Q_plus | 8 | 4 | 2 | 2 | 0.5 | 0.734375 |
| Q_minus | 8 | 5 | 0 | 3 | 0.625 | 0.625 |

四份提交失败分别涉及余数分配、区间内部零长度插入冲突、预订ID校验、同坐标补丁顺序。原报告将其绑定到公开合同义务、固定生产代码及原观察，没有把它们改判为技术故障。有限公开测试通过仍不保证完整合同正确。

十个未提交槽没有追加验收。它们的原 R/Q=0表示没有形成合格固定交付，不能据此断言终态私有源码必然错误。其中九槽有历史公开测试，但测试可能早于后续编辑；另一槽没有成员测试。本文不把这些历史观察冒称为终态工作树评分。

CAL0新增模型调用、候选执行、业务重执行、反向和优化器更新均为0。旧v050生成和训练费用不转入本轮校准小计；这不表示旧32槽的历史生成费用为0。CAL0报告没有给出本次CPU审计耗时，本文不补为0。只读核对通过也不等于模型能力、所有系统接缝或全部历史实验均已验证。

## 3. CAL1：原始 grade 与严格39已知、9缺证并列

[CAL1最终报告](software-calibration-v051-cal1-final.md)唯一合并原48槽。首阶段已有15槽进入执行，其中13份完整回包、2份无完整回包；两次用户资源调整后，只接续原33个未开始槽，没有重跑原15槽。原停止记录和原阶段33个未开始的历史事实保留，合并后原库存未开始为0。

### 3.1 条件与外推范围

两路使用相同24题、事前seed、单候选、解码与官方提取/评分规则；reference采用官方支持入口下的共同数值桥接，project保留项目注意力路径。两路共用HF生成器、BF16主干和FP32输出头，因此不是两套独立推理引擎。相同seed和同卡不能保证输出逐token相同，也不能把有限差异唯一归因于某一组件。

24题为固定来源的难度分层面板，不是官方累计全集，也不是厂商完整recipe或榜单复现。没有使用厂商公布成绩作为停止或成功阈值，没有看到成绩后换题、修改提取器、追加候选或补验。

### 3.2 原始观测和严格结果

| 路径 | 原 grade=1 | 原 grade=0 | 无完整原 grade | 严格成功 | 严格已知失败 | 严格缺证 |
|---|---:|---:|---:|---:|---:|---:|
| reference | 16 | 8 | 0 | 12 | 8 | 4 |
| project | 14 | 8 | 2 | 11 | 8 | 5 |

七个已有完整输出和评分的槽缺少worker最终只读guard，另两个槽缺完整回包。前者不是已证实参数发生变化，后者也不能作为正常代码错误；两类都不能自动通过。原grade保留，严格分析值保持未知。两次用户资源取消与这些缺证的来源绑定见[独立阶段release](software-calibration-v051-cal1-to-cal2-release.json)。这不是为未知结果指定成功或失败归因。

后续33槽的来源、输入、评分和终态证据全部闭合，无新增完整性问题。这一事实与原9个缺证同时成立，不能用新阶段闭合替代旧guard或回包。

| 严格指标 | 固定分母 | 完整点估计 | 原报告的未决界限 |
|---|---:|---:|---|
| reference pass@1 | 24 | null | [0.5, 0.6666666666666666] |
| project pass@1 | 24 | null | [0.4583333333333333, 0.6666666666666666] |
| project−reference | 24个配对题 | null | [-0.20833333333333331, 0.16666666666666663] |

配对分类为10题两路通过、7题两路失败、1题仅project通过、1题仅reference通过、5题未决。界限表示未知在允许范围内的可能值，不是置信区间，不是用0或完整案例均值填补未知。该面板不足以给出完整路径优势判断或总体能力估计。

### 3.3 费用与历史资源

| 阶段 | 完整回包 | 已开始缺完整回包 | 已知实际token | 不确定预约token | 唯一worker秒 |
|---|---:|---:|---:|---:|---:|
| 原阶段 | 13 | 2 | 231,909 | 164,789 | 13,031.596915721893 |
| 原33槽接续 | 33 | 0 | 1,410,170 | 0 | 66,839.5831618309 |
| 原48唯一合并 | 46 | 2 | 1,642,079 | 164,789 | 79,871.1800775528 |

完整实际费用为null。1,806,868是已知实际加保守预约的账本量，不是已知实际收费。原阶段未用预算未转移给接续槽。

唯一8段worker驻留包含装载、预留、生成、CPU评分、收尾和失败，原生生成耗时已在其中，不再次相加。接续阶段历史采用GPU0/1/3/4/6/7、空闲稳定60秒及最多4驻留，实际使用6/7/4/7；之后解除GPU范围与空闲限制的授权不回写这段历史。

## 4. CAL2：原18槽、两类环境缺陷和6个代码未知

[CAL2最终报告](software-calibration-v051-cal2-final.md)及其[紧凑JSON](software-calibration-v051-cal2-final.json)保留原18逻辑槽、原历史尝试及全部raw值。R为原始权重的mini-SWE单agent；P为原始权重的ProWorkSim S1；U为S_star 4/4的同一S1。三者采用项目共同数值路径、fresh resident和原任务初态。

R_code比较各条件末树代码，Q_terminal描述完整原测试集合的观察分数；P/U另有固定交付R_joint。R没有项目固定交付端点，R_joint为N/A，不能填0。未收集或未运行的原测试节点明确保留not-run，不能伪造成已执行失败。

### 4.1 原失败与接续范围

初阶段四个尝试遇到两种实现问题。原R在模型循环前因初态来源映射的CRLF归一化误报而退出，没有任何已准备或开始的生成请求；原文件字节未被改动，原加载失败及驻留费用保留。其后唯一首次实际模型执行不是旧轨迹重采。原三个P/U已有真实模型轨迹，但测试child在pytest执行前因导入项目包牵入缺失的openpyxl而退出，业务测试观察为0；原R_code/Q未知不重评分、不补跑。

独立r2只接原14个未开始槽及唯一零生成R的首次真实样本。之后发现socket适配将socket类替换为函数，使原asyncio/ssl路径的测试环境失效。影响限定为boltons-1/R、boltons-2/R、boltons-2/U；独立环境有效性层将三条严格R_code/Q_terminal置为技术未知，原raw分数不改。boltons-2/U原无固定提交的R_joint=0仍保留，不能外推修好环境后它是否会提交。

r2按完整性门暂停，已开始槽依规则闭合；r3仅运行原七个未进入槽，七槽均闭合，没有新增未决公共故障。历史三条P/U代码未知加r2三条环境无效代码未知，共六条；这些限制没有因r3闭合被消除。原18逻辑槽与19段物理worker不是同一计数：多出的一段是保留的零生成R失败历史，不是新增逻辑样本。

### 4.2 raw与严格代码端点

| 条件 | raw代码已知/6 | raw完整R_code均值 | 严格代码已知/6 | 严格完整R_code均值 | 严格未决界限 |
|---|---:|---:|---:|---:|---|
| R | 6/6 | 0 | 4/6 | null | [0, 0.3333333333333333] |
| P | 4/6 | null | 4/6 | null | [0, 0.3333333333333333] |
| U | 5/6 | null | 4/6 | null | [0.3333333333333333, 0.6666666666666666] |

R的raw全零包含受环境故障影响的观察，不能当作六题严格业务失败。全六题等权严格P−R为null，界限为[-0.3333333333333333, 0.3333333333333333]；U−P也为null，界限为[0, 0.6666666666666666]。未知不填0，不按可运行库、成功或提交筛成一个“完整”面板。

| 严格Q_terminal | 已知/6 | 完整均值 | 未决界限 |
|---|---:|---:|---|
| R | 4/6 | null | [0.5196712018140589, 0.8530045351473922] |
| P | 4/6 | null | [0.5230725623582767, 0.85640589569161] |
| U | 4/6 | null | [0.5425170068027211, 0.8758503401360543] |

Q_terminal的P−R和U−P完整均值也均为null。上述上下界只反映未决值范围，不是将技术未知解释为真实测试失败，也不是统计显著性证据。

### 4.3 固定交付另表

| 条件 | raw R_joint均值 | 严格已知/固定分母 | 严格完整均值 | 严格未决界限 |
|---|---:|---:|---:|---|
| R | N/A | N/A | N/A | N/A |
| P | 0 | 4/6 | null | [0, 0.3333333333333333] |
| U | 0.3333333333333333 | 5/6 | null | [0.3333333333333333, 0.5] |

raw固定交付差U−P为0.3333333333333333，但严格完整差仍为null。该raw差不能替代严格代码比较，不能因为某个原assessment写有0就认定缺失的机械或评分证据已闭合。固定交付和末树正确性是不同端点。

### 4.4 费用与适用限制

CAL2共有430次开始且完整的真实回包，已知与完整实际费用均为4,661,175 token，不确定预约0；19段唯一worker驻留合6,212.898454666138秒。评分未知与费用未知分开：本阶段代码端点有六条未知，但回包账单完整闭合。初阶段原报告中保守的完整费用null原值仍保留；最终报告通过独立零生成R来源证据与完整native回包绑定说明费用闭合，没有回改旧报告。

最终费用已经包含初始+r2小计一次及r3一次，原零生成R的加载成本也已包含。CAL2报告中的CAL1费用只是附记，不能再次加进CAL2或全窗口。阶段内部generation、评分或phase耗时不再与worker驻留叠加。

六题来自三个公开仓库的合成缺陷，不能称原始真实issue或官方SWE-bench榜单复现。R最多128次bash机会，P/U最多32次公开测试，工具机会与固定交付要求有差异。共同数值路径、fresh resident和有限任务分布也限制外推。现有观察不足以给出完整接口优劣、S_star普遍收益或一般协作收益的结论。

## 5. HOLD：共同实现冻结、部分来源准入与独立输入身份修订

HOLD共同代码在内容访问前冻结为 `0770d02f11bae4b33018c94be809f416c5fb91a2`，见[common freeze](software-holdout-v051-common-freeze.json)。来源访问和模型准入由[独立source release](software-holdout-v051-source-access-release.json)及[model admission](software-holdout-v051-model-admission.json)分别绑定；本轮模型阶段按准入提交`36d4b62`启动。本文不修改原plan、状态、输入或终态。

### 5.1 来源资格保留原八题

来源资格保留八题的正确、缺陷、参考三态，共24个逻辑单元。按事前完整身份去重后执行13次物理runner，完整执行回执13、未决0；逻辑数与物理数分开记录。这些是CPU环境/来源资格，不是模型成绩或模型调用。[来源资格摘要](../../artifacts/software-calibration-v051/holdout-sources/qualification/summary.json)为固定四题合格、四题阻断。

| 固定任务 | 来源资格 | 输入资格处理 | 对原四状态库存的处理 |
|---|---|---|---|
| hold-funcy-1、hold-funcy-2 | blocked：冻结环境缺测试依赖`whatever` | not_run_source_blocked | 每题四槽保留source_or_input_blocked |
| hold-python-slugify-1、hold-python-slugify-2 | blocked：原native测试ID不满足冻结的一一映射要求 | not_run_source_blocked | 每题四槽保留source_or_input_blocked |
| hold-iniconfig-1、hold-iniconfig-2 | qualified | 原容量fit，独立r2身份等价修订后qualified | 原四状态可派发 |
| hold-dominate-1、hold-dominate-2 | qualified | 原容量fit，独立r2身份等价修订后qualified | 原四状态可派发 |

没有修复后重跑funcy/slugify资格，没有换题、删测试、重新解释测试ID或转移其预算。plan仍保留完整32行，其中16行可派发、16行source blocked；不是新建一个只有四题的完整面板。四题来源缺失意味着完整八题的主均值和状态差为null；另外16槽已经全部闭合，仍不能消除来源缺题。

### 5.2 branch_id修订是测量修订，实际输入保持

四个来源合格任务的两个角色、四个状态共32份实际SDK初态请求均通过原硬容量测量。原报告保存32个独立投影、64次实际tokenizer编码、160次精确编码缓存命中，以及64次native模板渲染。实际模型生成和程序响应均为0；这不是额外模型资格。

但原冻结`business_projection`比较门使四题全部input blocked，原资格`passed=false`保留。独立只读审计比较原32请求后确认，八个任务×角色组都只有三个叶路径差异：`observation.instance_id`、`observation.branch_id`和`observation.team_model_budget.state_sha256`。原身份mask已有instance与账本摘要，遗漏branch_id；除此之外的任务、工具和公共字段结构同值。

冻结初始化链为builder→scenarios→WorldCore→`core/world.py`。instance_id和branch_id均在创建新world时独立以`uuid.uuid4().hex`生成，HOLD observation将其原样公开。**branch_id是模型可见的随机命名空间字段，不是非输入宿主元数据。** 它不编码状态B/Q标签或任务业务差异，但不能据此证明模型对随机ID不敏感。

[独立r2摘要](software-holdout-v051-initial-input-identity-r2.json)采用新版本`v051-holdout-initial-input-identity-readonly-v2`，绑定原false摘要、全部32份请求/投影及[只读差异审计](../../artifacts/software-calibration-v051/hold-input-readonly-audit/report.json)。它只在分析等价比较中新增`/observation/branch_id`身份归一化，不修改任何真实请求、token、共同Γ或原资格字段；新增SDK请求、tokenizer、模型和测试执行均为0。

这项修订支持原四个来源合格任务的独立输入准入，不是把原冻结比较门写成已经通过。四状态的原输入并非逐字节同值；未来独立会话也可能得到新ID，原32实例fit不保证任意未来ID容量。正式运行仍执行逐请求硬容量门。

### 5.3 运行条件与业务端点

四个已有actor状态精确映射S_star/B/Q_plus/Q_minus；S_star历史4/4，其他历史5/5，但B与Q_plus即使步数相同也不得交换授权。模型只加载对应actor，不构造critic或优化器。固定O1的两个独立成员会话、空任务表、自主责任、真实伙伴事件唤醒、Γ1、18432上下文/2048输出、3072字符分页以及每槽500,000 token、128决定/attempt、32次公开测试保持。

每槽采用独立fresh resident；90分钟软边界和100分钟硬边界保持。当前资源范围为GPU0—7，最多4驻留，按容量共享，取消旧空闲60秒门；历史资源分配不改写。安全且证据充分的局部context或预算终止保留并继续独立槽，真正完整性问题暂停未开库存，不能按F高低筛选。

HOLD唯一主业务端点F绑定最后合法固定提交。无提交且机械、费用、guard均闭合时F=0，不执行未提交末树“救援”验收；机械未知不能由F0掩盖。CAL2末树R_code不进入HOLD。行政删失时joint与token口径分开，不把预算、context、真实故障和行政时间边界合成同一原因。详细方法见[HOLD接口协议](software-calibration-v051-hold-interface-protocol.md)及[测量/宿主方法](software-holdout-v051-host-measurement-method.md)。

## 6. HOLD实际终态：16闭合、16来源阻断

[HOLD唯一最终JSON](software-holdout-v051-final.json)的SHA为`1512dbc00aeeb97f7ae63c6db0842b237641275119f1e83edc4406a52c3b01d1`，9,804,540 bytes。宿主终态complete；运行窗口为北京时间2026-10-18 15:34:26.530673—16:17:13.922044，原时间戳1792308866.5306735—1792311433.9220443。实际GPU为0/4/5/6/7，16段worker驻留合9,046.376301288605秒；这与宿主墙钟窗口是不同口径。

原32行保留：16个合格槽全部closed，另外16行为source_or_input_blocked；可派发库存中没有未开始槽或正式技术未知。五份固定提交均完整通过，另外11槽没有合法固定提交，没有“提交但未全过”的槽。无提交F=0只表示固定交付缺失，不构成终态私有源码错误率；未提交工作树未被补验。

本阶段16槽的F、Q_joint、R_token、Q_token均已知。R_token/Q_token沿用原token预算下的端点定义，**不是得分除以token的归一化效率指标**；本次这些端点在逐槽数值上与F/Q_joint相同，不改变其定义。

### 6.1 完整八题分母保留null

| 状态 | 严格已知/原8题 | F=1 | F=0 | 来源blocked任务 | 完整8题F均值 | 未决界限 |
|---|---:|---:|---:|---:|---:|---|
| S_star | 4/8 | 0 | 4 | 4 | null | [0.0, 0.5] |
| B | 4/8 | 2 | 2 | 4 | null | [0.25, 0.75] |
| Q_plus | 4/8 | 2 | 2 | 4 | null | [0.25, 0.75] |
| Q_minus | 4/8 | 1 | 3 | 4 | null | [0.125, 0.625] |

Q_joint、R_token、Q_token的完整八题均值同样为null。本次其逐槽值同F，因此相应已知数与界限一致。四个完整八题配对效应B−S_star、Q_plus−B、Q_minus−B、Q_plus−Q_minus也均为null，F界限依次为[-0.25, 0.75]、[-0.5, 0.5]、[-0.625, 0.375]、[-0.375, 0.625]。这些是缺题结果的允许界限，不是置信区间。

### 6.2 原四个合格任务的等权描述

四题子集在模型启动前按来源/input资格确定，并非按模型成绩筛选。原任务为iniconfig两题、dominate两题；四状态的所需值均已知，故可以给出该子集每题等权的描述性均值与配对差。它不替代原八题主结果，也不是新增学习或一般协作收益的证明。

| 固定合格任务 | S_star F/Q_joint | B F/Q_joint | Q_plus F/Q_joint | Q_minus F/Q_joint |
|---|---:|---:|---:|---:|
| hold-iniconfig-1 | 0 / 0.0 | 0 / 0.0 | 1 / 1.0 | 0 / 0.0 |
| hold-iniconfig-2 | 0 / 0.0 | 0 / 0.0 | 0 / 0.0 | 0 / 0.0 |
| hold-dominate-1 | 0 / 0.0 | 1 / 1.0 | 0 / 0.0 | 0 / 0.0 |
| hold-dominate-2 | 0 / 0.0 | 1 / 1.0 | 1 / 1.0 | 1 / 1.0 |

| 状态 | 四题F均值 | 四题Q_joint均值 | 四题R_token均值 | 四题Q_token均值 |
|---|---:|---:|---:|---:|
| S_star | 0.0 | 0.0 | 0.0 | 0.0 |
| B | 0.5 | 0.5 | 0.5 | 0.5 |
| Q_plus | 0.5 | 0.5 | 0.5 | 0.5 |
| Q_minus | 0.25 | 0.25 | 0.25 | 0.25 |

| 四题等权配对差 | 已知配对/4 | F | Q_joint | R_token | Q_token |
|---|---:|---:|---:|---:|---:|
| B−S_star | 4/4 | 0.5 | 0.5 | 0.5 | 0.5 |
| Q_plus−B | 4/4 | 0.0 | 0.0 | 0.0 | 0.0 |
| Q_minus−B | 4/4 | -0.25 | -0.25 | -0.25 | -0.25 |
| Q_plus−Q_minus | 4/4 | 0.25 | 0.25 | 0.25 | 0.25 |

子集内B相对S_star的两个额外成功来自dominate两题。Q_plus与B的四题平均F差为0，但逐题并非全部同值：iniconfig-1为+1、dominate-1为−1，另外两题为0。Q_plus相对Q_minus的+0.25只来自iniconfig-1。四个任务、两个仓库和单次配对观察不足以外推总体状态优劣、方向最优或统计稳定性。

### 6.3 机械与过程证据

16个正式端点来自宿主closed回执、continue verdict和continue measurement；674次生成均有完整账单，费用完整性错误为空。正式结果与raw值在这些已闭合槽一致；16个来源blocked槽没有模型执行，不填F0。

[独立终态机制摘要](../../artifacts/software-calibration-v051/hold-final-mechanisms/report.json)SHA为`7738b74f1c76beeba7a394206319d13055c2caec387f463b57bd877dc11a03c7`，283,443 bytes。它只复用16份已有worker report，不扫描原轨迹、不重新运行measurement，没有新测试、分词或模型。

| 已闭合16槽的机制量 | 正式摘要结果 | 解释边界 |
|---|---:|---|
| 决定 / 完整调用 | 701 / 674 | 另外27次为有证据的执行前局部team_budget拒绝 |
| prompt / completion token | 7,711,434 / 129,357 | 相加为7,840,791实际token；不是另加费用 |
| 保存反馈 / 首次真实同成员后继呈现 | 674 / 642 | 32条没有后续实际生成，不当作已呈现或反馈丢失 |
| 无后继原因 | team_budget 27；工作结束且无可达事件4；等待无事件1 | 原未呈现与原因保持 |
| 局部停止分类 | 14 safe_local_resource_stop；2 ordinary_closed_stable_O1 | 16个宿主判断均continue；不按F筛选 |
| 公开run_tests / host最终验收 | 47 / 5 | 同一47次的反馈数、报告历史数、共享测试用量是同一事实，不相加 |
| 显式read_test_result决定 | 32 | 不是79次读页调用 |
| 验证通过的含页反馈条目 | 79 | 47次run_tests自动首页 + 32次显式读页；不是唯一页面数或独立模型回包数 |
| 至少有一页实际呈现的测试报告 / 全页呈现报告 | 44 / 0 | 不强制全读，也不据此推断模型理解或使用 |
| actor guard及四项episode guard | 16全部通过 | 四项分别为learning未变、RNG精确恢复、software binding未变、actor身份未变 |
| native回包多重集绑定 / 全部started已结算 / 固定端点验证 | 各16通过 | CPU fixture不替代正式native凭据 |
| 新更新 / 反向 / 成员请求出生 / 外部出生 | 全0 | 历史4/4与5/5步数不是本轮更新 |

页计数定义另见[page-count-definition.json](../../artifacts/software-calibration-v051/hold-final-mechanisms/page-count-definition.json)。79按已经验证的含页反馈条目计数，不因同一条反馈在多个后续输入出现而重复加；47次公开测试返回的自动第一页也在其中。

历史检查点身份与本次执行身份分开记录。历史`source_actor_identity.inference_profile_sha256`为`b7aebd3ce0119fa6e4067524c255cef29f1816adc361d2ed0a93f21f83844252`；本次`guard.actor_identity.inference_profile_sha256`为`20a2732be082bc3c144d5a3dcf3d9efe1caac05e2741c169472f130c59e20225`。前者是保留检查点的来源声明，后者绑定当前直接native路径、decoder、dtype、attention和无learning执行profile，不能把旧profile冒称为本次实际profile，也不称完整learner恢复。具体四状态授权与原件路径由HOLD准入和各worker来源引用保留。

`R_token`在非行政删失时沿原定义等于`R_joint`，行政删失时为null；本次16槽该端点均已知。它是原token-budget政策端点，既不是每token奖励，也不是按token归一化的分数。

伙伴语义使用在本次机制摘要中明确为`not_analyzed/null`。本次没有重新扫描消息与采用轨迹，因此不能把消息、页数、测试、唤醒或成功计数替代“伙伴贡献被实际使用”的证明，也不能据此宣称已有跨成员收益或断言没有伙伴使用。

## 7. 模型费用与唯一驻留：CAL小计加HOLD一次

以下数值只来自CAL既有小计和HOLD唯一final摘要，CAL0为该只读审计的新增量。准备下载、CPU资格、分词、只读审计和模型生成属于不同活动；没有完整耗时来源的CPU环节不虚填为0，也不混成GPU小时。

| 范围 | 已开始生成 | 完整回包 | 已知实际token | 不确定预约token | 完整实际token | 唯一GPU worker段 | GPU worker秒 |
|---|---:|---:|---:|---:|---:|---:|---:|
| CAL0新增只读审计 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| CAL1原48唯一合并 | 48 | 46 | 1,642,079 | 164,789 | null | 8 | 79,871.1800775528 |
| CAL2原18唯一合并 | 430 | 430 | 4,661,175 | 0 | 4,661,175 | 19 | 6,212.898454666138 |
| CAL小计，未含HOLD | 478 | 476 | 6,303,254 | 164,789 | null | 27 | 86,084.07853221893 |
| HOLD唯一阶段 | 674 | 674 | 7,840,791 | 0 | 7,840,791 | 16 | 9,046.376301288605 |
| v051 CAL+HOLD总计 | 1,152 | 1,150 | 14,144,045 | 164,789 | null | 43 | 95,130.45483350754 |

全窗口已知实际加不确定预约为14,308,834 token，它不是已知实际收费。HOLD本身账单完整，完整实际费用为7,840,791 token、预约0、integrity_errors为空；CAL1原两次缺完整回包仍在，故整个v051完整实际费用保持null，不能因为HOLD闭合而填成已知实际之和。

43段唯一GPU worker驻留共26.425126342640983小时，其中CAL为23.912244036727483小时，HOLD为2.5128823059135015小时。它们表示全驻留累计量，不是宿主墙钟经过时间、GPU kernel忙时或付费价格。worker包含装载、预留、生成、CPU评分、收尾及失败区间。

费用合并遵守以下范围：

- CAL1 final已包含original与idle continuation各一次，不再追加其阶段小计。
- CAL2 final已包含initial、r2和r3各一次；CAL2中的CAL1附记不再加入。
- 原零生成R加载失败驻留已经在CAL2的19段worker中，不删除，也不另加一次。
- generation、model、scoring及phase耗时嵌在worker内，不再与驻留累加。
- CAL0读取的原v05032槽及旧训练费用不转入v051；HOLD不继承CAL余额。
- 请求预约与实际回包费用分列；unknown不能变为0，评分未知也不能自动变为费用未知。
- HOLD final只加入一次；本报告没有重新遍历原调用账本或重算旧阶段。

本轮新增actor/critic更新、反向和优化器更新均为0；聚合过程没有新模型、SDK、分词、测试或评分执行。

## 8. 当前证据能支持与仍不能支持的判断

CAL0支持“在已核对的原固定交付与评分范围内，未发现评分转换或接入错误”，并将四个失败绑定到公开业务义务。它不证明所有系统问题均不存在，也不补验未提交源码。

CAL1支持“后续33个原未开始请求在本地共同条件下获得完整来源/输入/评分/终态闭合”，同时完整保留原9个分析缺口。它不能给出完整24题路径优劣或厂商能力复现结论。

CAL2支持“已定位两类环境问题并在独立后续库存中处理，r3原七槽完整闭合，实际native费用可知”，但六个代码端点技术未知使完整六题比较保持null。修复说明不等于重判历史成绩；raw观察不等于严格正式端点。

HOLD支持原四个合格任务全部四状态的有限描述：S_star/B/Q_plus/Q_minus的F为0/0.5/0.5/0.25，674次实际回包与16个端点闭合，新增费用已知。四个来源blocked任务仍从完整八题结果中缺失，不能冒称完整面板或普遍收益。条件子集的观察仍受任务分布改变、固定交付要求、资源停止和有限配对样本约束；HOLD的闭合不消除CAL1/CAL2历史未知。

## 9. 来源索引与收口范围

| 来源 | 用途 |
|---|---|
| [CAL小计JSON](../../artifacts/software-calibration-v051/final-calibration-subtotals.json) | 三阶段报告ref、严格/raw小计、成本边界及防重复规则 |
| [CAL0 JSON](../../artifacts/software-calibration-v051/cal0/report.json) / [说明](../../artifacts/software-calibration-v051/cal0/report.md) | 原32开发终态只读审计 |
| [CAL1 final JSON](software-calibration-v051-cal1-final.json) / [说明](software-calibration-v051-cal1-final.md) | 原48唯一库存、9缺证、原始评分与费用 |
| [CAL1→CAL2 release](software-calibration-v051-cal1-to-cal2-release.json) | 不按成绩阈值的阶段解释，原未知保留 |
| [CAL2 final JSON](software-calibration-v051-cal2-final.json) / [说明](software-calibration-v051-cal2-final.md) | 原18唯一库存、环境有效性、raw/strict及独立账单 |
| [CAL→HOLD判断](software-calibration-v051-cal-to-hold-decision.md) | 校准收口边界与后续资格条件 |
| [共同源码冻结](software-holdout-v051-common-freeze.json) | 内容访问前common0770d02与必要控制 |
| [来源资格](../../artifacts/software-calibration-v051/holdout-sources/qualification/summary.json) | 原八题24逻辑/13物理资格及4合格4阻断 |
| [原input false](../../artifacts/software-calibration-v051/holdout-initial-inputs/summary.json) | 原32请求、容量测量及原比较门阻断 |
| [只读差异审计](../../artifacts/software-calibration-v051/hold-input-readonly-audit/report.json) / [独立r2身份摘要](software-holdout-v051-initial-input-identity-r2.json) | 可见随机branch_id的限定测量修订，不修改实际输入 |
| [HOLD模型准入](software-holdout-v051-model-admission.json) | 原32行、16可派发/16blocked和精确四状态授权 |
| [HOLD唯一最终JSON](software-holdout-v051-final.json) / [说明](software-holdout-v051-final.md) | 原32库存、16闭合/16blocked、674回包及唯一worker来源 |
| [总体唯一JSON](software-calibration-v051-overall-final.json) | CAL一次加HOLD一次、完整八题结果与合格四题描述 |
| [HOLD机制摘要](../../artifacts/software-calibration-v051/hold-final-mechanisms/report.json) / [页计数定义](../../artifacts/software-calibration-v051/hold-final-mechanisms/page-count-definition.json) | 原worker测量字段只读汇总，伙伴语义使用未分析 |

HOLD plan SHA为`ef798d0758bfc4444c0da2f97eea20fc92406bb09d4b67a50cc9761da006f9c5`，宿主终态supervisor SHA为`7780982f6251d5f6a0595ab927cfed00aa7a7d4b7f8b6ab1a64296816084b5aa`；两者的路径、字节数和完整来源链由唯一HOLD final引用。本文不重复嵌入大段supervisor或原模型正文。总体JSON保留原阶段raw/严格结果、未知边界、引用与费用分层；本轮库存收口后无自动追加实验。
