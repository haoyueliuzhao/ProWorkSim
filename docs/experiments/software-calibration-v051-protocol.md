# v051：零训练单人校准与既有状态保留评价协议

本轮承接v050的有限结论：**局部经验组成干预已经进入真实参数更新，但整体学习收益尚未建立。** 本轮先解释评分与推理接入，再在冻结条件下评价已有状态；不从v050八单位事后选Q−作为新训练起点，不扩大Q±重训。新增actor更新、critic更新和反向均为0。

用户在提供[本轮审计](../reference/audit-v050-next-v051-calibration.md)后明确要求“参照审计修订并开展后续实验”。本文件与[机器来源锁](software-calibration-v051-source-lock.json)冻结CAL-1的实际题单、共同推理条件和评分口径；后两阶段还须分别绑定真实任务、环境和放行凭据。只有审计粘贴文本实际可读；其中链接的A1.0原件、结构化提案JSON和ZIP没有随附件取得，不能冒称已读或已执行其隐藏材料。

本文的状态快照在CAL-1模型启动前形成。CAL-0只读核查和下面列出的有限CPU控制已完成；CAL-1实际48次生成、CAL-2与HOLD尚不因本文件存在而记为通过。启动时的冻结提交、宿主控制、资源准入和运行状态由正式plan与回执补充。已通过且未变的检查不重复执行。

## 1. 阶段、预算与进入条件

| 阶段 | 固定对象与问题 | 本阶段新增生成上限 | 当前证据状态 |
|---|---|---:|---|
| CAL-0 | v050全部32开发终态；固定交付与评分是否对齐 | 0 | 已完成只读核对；没有业务重执行 |
| CAL-1 | 24个官方LCB题×reference/project两路×单候选；原始发布模型的共同条件桥接 | 48次；3,959,768输入+输出token | 题单、实际输入、源码和CPU控制就绪；待正式宿主准入 |
| CAL-2 | 6个仓库任务、至少3个仓库×R/P/U；每条件真实单人 | 18episode×500,000＝9,000,000token | 任务和环境资格另行冻结，本文件不记准备完成 |
| HOLD | 8个新仓库修复任务×S*/B/Q+/Q−；严格O1固定2成员 | 32episode×500,000＝16,000,000token | 校准后条件阶段；静态任务来源与资格另行绑定 |

全部阶段生成token的预先上界为**28,959,768**，训练计算为0；旧未用预算不转移。CAL-1的次数是单次生成次数；CAL-2/HOLD是多决定episode，不能将三者直接写成98次模型调用。没有额外模型资格题、第二候选、输出预算扫描或按成绩追加题目。

校准结束依据是关键输入、评分、模型状态和账单接入得到解释，剩余限制可以明确声明。成绩低或没有达到厂商分数本身不构成工程失败；高分也不能替代身份与完整性凭据。发生真实输入、权限、状态、记录或费用完整性问题时停止相应未开库存，保存已执行结果及未知；不在原题输出之后热改配置并重采。

HOLD在CAL结束前只允许静态ID、revision、来源SHA和许可信息冻结，不执行其正确源、故障源、参考修复或验收CPU题检，不用HOLD题目修理CAL。CAL共同实现封存后，才执行一次事前规定的环境/评分资格；失败保留且停止相应库存，不换题。这样限制的是评价信息的使用，而不是依据模型通过率筛选任务。

## 2. CAL-0已经得到的证据

[CAL-0只读报告](../../artifacts/software-calibration-v051/cal0/report.md)覆盖原32槽与291个原文件，完成1,830项来源及数值一致性判断，失败0项。22份固定提交均绑定最后合法交付、版本SHA、本人同树公共测试和原评分；原私验输出中的292个判定按原fixture复算一致。所有来源文件读取前后SHA一致。**没有运行候选代码、增加私验或修改原R/Q。**

| 原状态 | 完整成功 | 提交未全过 | 未提交 | 原F | 原平均Q_task |
|---|---:|---:|---:|---:|---:|
| S* | 5/8 | 1 | 2 | 0.625 | 0.739583 |
| B | 4/8 | 1 | 3 | 0.500 | 0.617188 |
| Q+ | 4/8 | 2 | 2 | 0.500 | 0.734375 |
| Q− | 5/8 | 0 | 3 | 0.625 | 0.625000 |

四份提交失败均能绑定到公开合同和固定代码：S*/DA-s1将余数分配全部给首账户；B/DD-s2遗漏替换区间内部插入冲突；Q+/DC-s1遗漏reserve ID校验；Q+/DD-s2的端点插入与替换顺序不符合原坐标合同。这个范围内没有发现评分转换或交付接入错误的证据，结论仍是原件级核查，不是独立业务重执行。

10个未提交槽均无submit尝试，两个成员均最终因团队预算结束。9槽有历史公共测试且相关末次测试未过；Q−/DD-s2没有成员测试。历史测试可能早于后续编辑，不能推出最终未提交代码必然错误；本轮不补验这些工作区，也不回填原R。

有限检索中找到了旧DeepSeek内部任务校准、Qwen接口/数值检查、SDK与容量控制，但未获得与本轮CAL-1/CAL-2等价的官方单人能力校准完成凭据。应写“尚未取得本范围完成证据”，不能写“历史从未进行过任何校准”。

## 3. CAL-1官方来源与样本

原模型是[Qwen/Qwen3.5-9B后训练发布权重](https://huggingface.co/Qwen/Qwen3.5-9B/tree/c202236235762e1c871ad0ccb60c8ee5ba337b9a)，revision固定为`c202236235762e1c871ad0ccb60c8ee5ba337b9a`，复用已有完整原始权重清单和四分片身份。CAL-1两路均不加载项目训练适配器，不构造critic或optimizer。其模型配置原生最大位置长度262,144不修改，RoPE、量化与权重不作容量补丁。

[官方模型卡](https://huggingface.co/Qwen/Qwen3.5-9B)报告LiveCodeBench v6为65.6，并说明默认思考模式、较长上下文及竞赛代码任务的较大输出建议。这里没有取得该榜单的完整提示、题窗、抽样次数、执行器与精确解码recipe；**65.6只是来源参照，不是24题通过门槛，也不是待精确复现的目标。** 本轮采用的明确参数是本地桥接设计，不把现有18,432/2,048非思考研究条件等同于厂商默认条件。

[LiveCodeBench官方代码](https://github.com/LiveCodeBench/LiveCodeBench/tree/28fef95ea8c9f7a547c8329f2cd3d32b92c1fa24)固定revision为`28fef95ea8c9f7a547c8329f2cd3d32b92c1fa24`；[官方lite数据](https://huggingface.co/datasets/livecodebench/code_generation_lite/tree/0fe84c3912ea0c4d4a78037083943e8f0c4dd505)固定revision为`0fe84c3912ea0c4d4a78037083943e8f0c4dd505`。`release_v6`累计口径有1,055题，本轮只使用其中`test6.jsonl`增量，明确不是整个累计题集。该文件175条，实际日期2025-01-04至2025-04-06；按事前闭区间2025-02-01至2025-04-30过滤后131条，其中easy31、medium39、hard61。

各难度分别按`SHA256(UTF8("v051-cal1|" + platform + "|" + question_id))`升序取前8条，再按easy、medium、hard连接，共24题、12个AtCoder与12个LeetCode。筛选不读取模型输出、参考解或测试表现，不按提示长度、私测复杂度或最终分数换题。原始增量文件134,303,240字节，Git LFS SHA256为`bb4c364f71921c4495a6ad15abe1a927350b720009f4933e2e71f8af0f6fd1f5`。

代码仓库为MIT；数据卡标为未细分的`cc`，builder的info却标MIT，两个来源标签原样保留，没有将二者合成一项更强许可判断。原题与测试完整材料留在本地来源目录，版本锁只公开必要身份与摘要。

下表顺序是唯一配对清单。“测试”列为公共+私有个数；两路径使用同一个evaluation_sample，不减私测。输入token来自最终实际tokenizer结果，已经包含原生聊天模板。

| 序号 | 题ID | 难度 | 日期 | 配对seed | 输入token | 测试 | shard | 路径顺序 |
|---:|---|---|---|---:|---:|---:|---:|---|
| 1 | `atcoder-abc391_a` | easy | 2025-02-01 | 202610170511 | 337 | 2+40 | 0 | reference→project |
| 2 | `atcoder-abc400_b` | easy | 2025-04-05 | 202610170512 | 441 | 4+40 | 0 | project→reference |
| 3 | `atcoder-abc398_a` | easy | 2025-03-22 | 202610170513 | 273 | 2+40 | 0 | reference→project |
| 4 | `leetcode-3817` | easy | 2025-03-22 | 202610170514 | 369 | 2+31 | 0 | project→reference |
| 5 | `leetcode-3832` | easy | 2025-03-29 | 202610170515 | 570 | 2+31 | 0 | reference→project |
| 6 | `leetcode-3799` | easy | 2025-03-15 | 202610170516 | 455 | 4+31 | 0 | project→reference |
| 7 | `leetcode-3811` | easy | 2025-03-29 | 202610170517 | 424 | 2+31 | 1 | reference→project |
| 8 | `atcoder-abc391_b` | easy | 2025-02-01 | 202610170518 | 661 | 2+40 | 1 | project→reference |
| 9 | `leetcode-3722` | medium | 2025-03-01 | 202610170519 | 412 | 2+40 | 1 | reference→project |
| 10 | `atcoder-abc397_b` | medium | 2025-03-15 | 202610170520 | 458 | 3+40 | 1 | project→reference |
| 11 | `leetcode-3754` | medium | 2025-02-01 | 202610170521 | 609 | 2+40 | 1 | reference→project |
| 12 | `leetcode-3794` | medium | 2025-03-22 | 202610170522 | 692 | 3+40 | 1 | project→reference |
| 13 | `leetcode-3793` | medium | 2025-03-29 | 202610170523 | 412 | 4+40 | 2 | reference→project |
| 14 | `leetcode-3791` | medium | 2025-03-08 | 202610170524 | 537 | 2+40 | 2 | project→reference |
| 15 | `leetcode-3748` | medium | 2025-02-08 | 202610170525 | 490 | 3+40 | 2 | reference→project |
| 16 | `leetcode-3785` | medium | 2025-03-01 | 202610170526 | 536 | 3+40 | 2 | project→reference |
| 17 | `atcoder-abc393_d` | hard | 2025-02-15 | 202610170527 | 587 | 3+40 | 2 | reference→project |
| 18 | `atcoder-arc192_e` | hard | 2025-02-09 | 202610170528 | 647 | 3+40 | 2 | project→reference |
| 19 | `atcoder-arc193_d` | hard | 2025-02-23 | 202610170529 | 1034 | 1+1 | 3 | reference→project |
| 20 | `atcoder-arc192_b` | hard | 2025-02-09 | 202610170530 | 785 | 3+40 | 3 | project→reference |
| 21 | `atcoder-abc398_g` | hard | 2025-03-22 | 202610170531 | 715 | 3+40 | 3 | reference→project |
| 22 | `leetcode-3701` | hard | 2025-02-01 | 202610170532 | 611 | 3+40 | 3 | project→reference |
| 23 | `atcoder-abc398_d` | hard | 2025-03-22 | 202610170533 | 889 | 3+40 | 3 | reference→project |
| 24 | `atcoder-abc394_e` | hard | 2025-02-22 | 202610170534 | 860 | 2+40 | 3 | project→reference |

真实题干、starter code、已渲染文本、原始input IDs与evaluation_sample保存在[cal1-cases.json](../../artifacts/software-calibration-v051/sources/cal1-cases.json)，文件SHA为`7d1919afbb3b472242fb17f91067033440537d095f961df9413ce80a4f8f1c5d`。evaluation_sample含私有测试，只供评分器读取，绝不能整体作为模型输入。每个任务的messages、rendered text、IDs、原始题记录、evaluation_sample SHA均在来源锁逐项列出。

## 4. CAL-1两路的共同条件与真实差异

[Transformers官方文档](https://huggingface.co/docs/transformers/model_doc/qwen3_5)支持Qwen3_5ForCausalLM文本生成。本轮reference使用该类的官方支持入口与标准SDPA；project使用项目原v020的BF16显式KV注意力路径及原生成代码对象，另有只读存储校验。两路都使用同一已安装HF生成器、BF16文本主干、FP32未绑定lm_head、输出头前的FP32提升，以及相同FP32采样变换。因此应称**共有数值设置下的本地桥接**，不能称两个独立推理引擎，也不能称reference完全等于厂商原始评测数值路径。

| 项目 | 两路共同冻结值 |
|---|---|
| 模型/已训练适配器 | 原Qwen3.5-9B发布权重；无已训练适配器模块 |
| 输入 | 同一个官方generic system+user提示、同一完整原生input IDs；tools为空 |
| 模式 | enable_thinking=true；preserve_thinking=false |
| 上下文/输出 | 131,072 / 81,920 token |
| 采样 | do_sample=true；temperature0.6；top_p0.95；top_k20；min_p0；presence0；repetition1 |
| 停止 | 有序EOS `[248044,248046]`；pad248044；无额外停止字符串 |
| 单次时间 | HF max_time7,200秒；宿主生成硬界7,800秒，含600秒闭合余量 |
| 缓存/精度 | 无跨请求prefix cache；matmul highest；TF32关闭；无量化、RoPE改写或自动数值回退 |
| 候选/seed | 每题每路1个候选；同题同seed；无生成重试或结果选择 |
| 软件 | 原native Python，torch2.6.0+cu124，Transformers5.17.0；依赖路径另锁 |

temperature、TopK和TopP由新采样记录器按同版本HF实现各施加一次；生成器对应温度/TopK/TopP置中性，避免重复处理。记录概率来自实际过滤后分布。旧项目在top_p1/top_k0下的过滤前记录不能直接宣称是本轮受截断采样的行为概率；本轮不会把这些概率输入学习器。

原来源提案只建议模型config中的EOS248044。模型前核查发现，tokenizer的聊天终止为248046，而此固定仓库没有generation_config.json；仅停248044可能跨越助手回合。因而两路共同显式冻结`[248044,248046]`，pad248044，记录为[独立停止策略修订](../../artifacts/software-calibration-v051/sources/stop-policy-correction.json)。原提案保留，不回改其SHA；没有重新挑题、分词、评分或调用模型。这个修订是本地设计决定，不声称复原了未披露的厂商完整recipe。

最终24个输入的原生直接编码与渲染再编码逐一同值，长度273–1,034，每路合13,804；全部实际输入加81,920输出预约均小于131,072。两路总输入27,608，输出最大3,932,160，所以总token上限3,959,768。已冻结不变的输入不再为了形式重复分词，不在模型前另加资格请求。

四个worker分别承担连续六个配对题，每个worker只驻留一份原始模型。同题两路在同一物理GPU运行，按固定次序切换注意力实现并清除请求缓存；1-based奇数题reference→project，偶数题project→reference。每个arm重新绑定同一事前seed。相同seed与同卡减少运行条件差异，但不能保证不同数值路径逐token相同，也不能将全部成绩差异唯一归因于某一个组件。

时间、输出长度或EOS终止分别保留。7,200秒是HF迭代边界检查，不能保证中断任意卡住的单次forward；宿主以7,800秒独立监管当前生成，额外600秒用于有界闭合，不是第二候选或续写预算。截断输出仍存原件并只使用同一提取器评分，不续写、不修复、不追加候选。若已进入生成而无完整回包，实际费用和该候选结果可保持技术未知，不能以零费用或失败样本替代。

## 5. 官方代码提取、评分和隔离

提示使用固定上游generic code-generation system与user模板；不是为这24题手写解题提示。提取器精确复用`extract_code(..., LMStyle.OpenAIChat)`：按最后两行三反引号取代码，不足两条分隔行则返回空串。完整原始输出与思考内容另存；不在看到通过率后改提取位置、去掉困难题或另选代码块。

评分复用未改的官方`testing_util.run_test`，evaluation_sample按原规则连接全部公共与私有测试，function题使用原metadata.func_name，stdin题使用原标准输入比较。单测试6秒；完整外层公式为`(timeout+1)×测试数+5`，当前最大44测试对应313秒。官方native结果全部大于0才记单候选pass@1=1；Wrong Answer、官方语法/运行错误、明确native TLE为0。评分器自身异常、缺回包或记录不完整保持null，不能盲填模型错误。

上游`check_correctness`的空metadata分支会在`metadata_list[0]`抛IndexError。本轮用原函数AST的有限CPU反例实际复现了这个行为，没有热改官方判定。由于项目OS隔离禁止socket/fork，生产包装使用一个外层独立进程代替原Manager/子进程调度，保留原run_test和全局时间公式；必须如实注明此执行包装差异。

执行前清空环境、进入新的空cwd，并安装项目原Landlock/seccomp文件、网络、子进程限制；地址空间4GiB、stdout文件1MiB，CPU与墙钟有界。完整raw输出、提取代码、固定样本、隔离安装记录、原native结果/metadata、退出码、费用和未知原因分别存档。启动前仅将评分子进程设置为继承worker进程组，使宿主killpg覆盖在途评分；其自身超时仍直接kill该单子进程。此一处flag修订做静态AST确认，原19项CPU控制及9次合成执行原件不回改、不重跑，另存`scoring-process-group-correction.json`与新源码SHA。评分目录必须全新，避免覆盖后重评。这里是OS访问约束，不声称未改的同进程Python评分器能抵抗任意帧反射或自省攻击。

评分API为`score_cal1_candidate(raw_output, evaluation_sample, source_root=..., run_root=新目录, python_executable=...)`，默认per_test_seconds=6。CPU评分只需要已固定的NumPy2.5.3环境，不需要加载torch或模型。实际题private tests只进入评分进程，不进入模型请求。

## 6. 已完成的必要控制与原失败记录

| 证据组 | 已完成范围 | 不能据此声称 |
|---|---|---|
| CAL-0 | 1,830项原件判断、292个已保存私验判定、32终态全覆盖 | 独立重新业务验收或未提交代码正确率 |
| 官方来源 | 22个来源文件与官方Git blob逐字节身份一致；完整数据LFS SHA一致 | 已运行官方任务或精确复现厂商榜单 |
| 真实输入 | 最终24题tokenizer同值与容量检查 | 24次模型资格、模型能力已通过 |
| 推理接口 | 共25项不同CPU控制：先21项，再3项新EOS/pad、路径切换、SDK时间账单，最后仅1项Transformers5 loading-info集合序列化；各次未重跑已通过部分 | GPU生成已经通过 |
| 采样算术 | 两个小CPU张量上的8项同版HF过滤/记录判断 | 原9B模型行为或token等价 |
| 评分 | 19项CPU控制，其中9个合成候选隔离进程：stdin/function正反例、缺围栏、语法、TLE、fatal exit、OS拒绝 | 真实24题已评分或模型已生成 |
| 宿主 | 7项不同CPU控制：5项库存/来源/账单控制及2项调度模拟，最终均通过 | 实际GPU装载、生成或资源调度已经完成 |

推理与评分新增文件的Ruff已通过。上述计数属于不同种类，不能简单合成“若干模型测试”。控制明细见[runtime-controls-summary.json](../../artifacts/software-calibration-v051/runtime-controls-summary.json)、[scoring-control-summary.json](../../artifacts/software-calibration-v051/sources/scoring-control-summary.json)及各原件。宿主记录见`artifacts/software-calibration-v051/host-controls.json`：首组首次2通过、3因read_json路径类型失败，修正后仅重跑3失败项；新2项调度模拟首次因测试括号错误未能收集，修正后通过。没有重复已通过部分，也没有模型调用。

初始下载存在匿名网络TLS、archive截断与API限流；来源文件随后由相同固定revision的GitHub连接器取得。增量数据第一次短了最后一段，经HTTP206字节续取恢复后，以Git LFS指针核定完整SHA；先前误把Xet HEAD ETag当作LFS SHA的断言失败也保留。CPU准备脚本首次将Transformers5.17返回的BatchEncoding与list直接比较，类型断言失败；修正为显式return_dict与input_ids读取，随后完成最终24题核对。装载前静态阅读还发现Transformers5的loading-info可能含set，运行器改用项目已有的顶层集合序列化，保持原装载准入不变；仅新增1项CPU控制通过，旧24项与8项小张量控制未重跑，凭据独立存于`loading-info-incremental-control.json`。它们都是模型前来源/实现准备问题，没有产生题目成绩、换题或新模型候选。

## 7. 资源、结果口径与阶段限制

GPU范围继续为物理0—7，总模型驻留上限4，包含所有CAL路径与后继阶段；已取消的GPU2单卡约束不恢复。装载前空闲至少46,080MiB，稳定等待阈值0，目标预留`min(73,728, free−1,024)`且最低45,056MiB，分配余量256MiB；运行中最低free为0。这是继承后的实际资源门，不能改写成最初56GiB/60秒/6GiB余量规则。容量不足排队，未消费候选的纯资源装载失败可以有凭据地重排；生成开始后的异常不自动重试。宿主装载与预留各900秒，评分与边界各600秒，每worker RSS上限64GiB，实验根产物128GiB，卷空闲保留20GiB；生成宿主硬界7,800秒与HF7,200秒分别记录。

CAL-1主表保留每题两路的原始终止原因、提取状态、native结果、错误类型与token费用。完整24题每路均已知时才给固定分母pass@1和配对差。存在技术未知时，完整主均值/差保持null，另列已知成功、已知失败、未知和显式上下界，不删除困难配对、不默认为0。官方65.6不参与停止或成功阈值。

CAL-2的R为原始权重+固定[mini-SWE-agent2.4.6](https://github.com/SWE-agent/mini-swe-agent/tree/a83fcae82d2a08f0ee0c688f9d137b3566c097f8)，P为同原始权重+ProWorkSim S1，U为已存S*4/4+同S1；三者都是初始、活动和累计出生上限均1的真实单人。[mini-SWE-agent官方SWE-bench入口](https://mini-swe-agent.com/latest/usage/swebench/)提供单人执行与预测导出方法，但不是Qwen9B厂商SWE-bench成绩来源。实际任务、原revision、工具机会、采样、资源、评分和本地环境隔离须在模型前进一步冻结；原生代码正确性、项目固定交付要求和技术未知分别报告。

CAL-2/HOLD拟使用固定[SWE-smith-py来源](https://huggingface.co/datasets/SWE-bench/SWE-smith-py/tree/77cab9055d42ab4a5c25c89a8f937096db13558e)中的公开仓库故障任务；它们是合成缺陷，不冒称原始上游真实issue或官方SWE-bench榜单复现。本文件尚不宣称六题/八题环境已准备或资格已通过。后续实际任务表独立冻结，不因模型成绩或环境资格失败替换题目。

HOLD使用全部四个已有actor状态，保持严格O1固定两成员，不仅比较Q−与B。源完整checkpoint身份要绑定，推理只加载actor张量，不构造critic/Adam，也不称完整learner恢复。新增仓库修复任务与v050同属宽泛软件任务域，但不是原四个人工家族的相同分布，不能与v050旧八单位合并成独立同分布确认。若CAL改变共同Γ，HOLD明确报告为“旧检查点在新执行条件下的表现”。

本轮不执行B/G-raw/I-P/I-S学习规则、多窗口选择、梯度缓存生产或新的方向扩大。旧v049 DA-s2和v046未知、未开槽及26试训/3正式/48确认/缓存生产暂停状态保留。校准与本次条件评价结束后无自动新增学习或样本。

## 8. 来源文件与复用

[机器来源锁](software-calibration-v051-source-lock.json)包含24题全部身份/seed/顺序/输入和评分SHA、原发布模型身份、官方源码revision、停止修订及CPU回执引用。原[来源提案](../../artifacts/software-calibration-v051/sources/cal1-source-proposal.json)SHA仍为`4f11a5dcf42cbd3c85849edf55eb3a2314fd6d84faed7c6ebf4e5acfc965d7c0`；正式条件以本文件和独立停止修订为准，不回写原提案。

`prepare_cal1_sources.py`保存从已核定官方记录构建提示、实际IDs与样本的准备方法；它是可复建的方法凭据，不是要求再次编码的启动步骤。现有结果已通过时直接复用；只有实际依赖变化才做相应必要核查。原始大文件、下载失败、合成控制与全部输入留在`artifacts/software-calibration-v051/`，已被git忽略；说明、来源锁和新执行代码随项目提交。正式模型启动还要绑定宿主plan、源码冻结提交及最终准入回执，不把文档冻结本身当作模型运行证据。
