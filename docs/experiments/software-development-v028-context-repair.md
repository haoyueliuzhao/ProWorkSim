# v0.28.1 软件上下文修复与GPU5恢复

日期：2026-10-03，北京时间。用户要求修复上下文问题并恢复实验，随后要求后续仅在GPU5排队、先占用GPU5。此前取消总GPU时长、每worker累计时长和统一墙钟截止的授权继续有效；等卡截止仍为2026-10-06 00:00。

## 16K的来源与实际故障

16K是本项目的冻结推理配置，不是模型文件声明的最大上下文。本地已绑定的`Qwen3.5-9B-c20223623576/config.json`中`text_config.max_position_embeddings=262144`，`tokenizer_config.json`中`model_max_length=262144`；本项目旧recipe的`max_length=16384`，输出预留2048。模型声明容量与本运行器已实测容量应分别表述；本次修复保留16K/2048及同一actor、critic、优化器和RNG起点，只修改工作接口及上下文选择。

旧槽`worker-1/dev-1-first-1-r0`中member_a把`fields.py`整体改写为43行的String片段，导致测试NameError。随后`diff_workspace({})`无界返回全部差异。原WorldCore回执的diff为78987字符；SDK把整个工具消息裁到50000字符，模型可见diff仅47922字符且含`<response clipped>`标记。下一次请求（call31、该成员第16次决策）真实输入19439 tokens，预留2048后超过16384，生成未开始，记录HTTP400 `context_length_exceeded`。旧运行将其记为`execution_unknown`并停止该worker，另两槽未启动。原始请求、完整WorldCore回执、SDK已裁视图及错误均保留，未重写旧判定。

这不是GPU累计时长触发。GPU5上的worker-0后来已自然完成全部四槽，退出码0；不能把其正常结束误报为同类故障。

## 修复范围

- `diff_workspace`提供版本绑定分页：默认4000、最多6000 Unicode字符；返回总长度、下一页offset、原diff SHA、源版本及基线引用。继续分页须固定同一source_reference；本人历史版本和已公开固定版本可回读，伙伴未公开版本仍不可读。拼接页可以恢复完整真实diff，原世界版本和原始证据不删改。
- 真实采样前使用相同actor renderer和本地tokenizer计数。只移除最旧的完整assistant/tool轮次；保留最新完整轮次、全部system/user原文、工具schema及采样参数，不生成摘要、不截文本、不隐式重试。SDK原请求、实际选取请求、逐步token计数、删除索引和原始响应分别落盘。
- 若保留必要反馈后仍超限，在生成前明确记录context_capacity边界。SDK原错误事件保留，软件运行边界另记录受控的上下文额度耗尽，不将其伪装成模型调用成功，也不按推理服务宕机停止整个worker。其他服务/环境故障仍为unknown。
- 经验声明登记新接口修订`software-collaboration-v0.28.1`和上下文策略`software-context-v0.28.1`。恢复轮结果与旧接口结果不能视为完全同条件重复。

## 必要资格与原失败复现

必要针对检查共50项通过：接口分页10项、上下文选择和独立恢复报告路径5项、真实SDK/runtime 15项、恢复与预留交接/报告20项。其中包括生成前上下文耗尽与其他技术故障的区分、保留R0、历史unknown尝试保留、GPU5串行和只向身份匹配的reservation发送信号。全体src/tests/scripts静态检查通过。原始SDK/runtime测试目录与JUnit位于`runs/v028-context-repair/runtime-checks/`及`runtime-checks.xml`。源码冻结后另做同源正式资格，不用开发期脏源码结果启动模型。

实际tokenizer开发回归文件为`runs/v028-context-repair/context-regression-development-r2/context-qualification.json`，14项门检查通过，模型调用0、未加载模型权重、未使用GPU：

| 程序控制 | 真实输入tokens | 结果 |
| --- | ---: | --- |
| 原call31原始请求 | 19439 | 复现超过16K；原文件不修改 |
| 同一错误写入、采用新WorldCore分页回执 | 7961 | 输出预留2048后余量6375 |
| 大diff成为较旧完整轮次 | 6280 | 完整移除旧轮后可容纳 |
| 大diff仍为最新完整轮次 | 17481 | 保留必要反馈，明确拒绝；不裁掉最新结果以伪造可容纳 |

新WorldCore根据原请求历史中实际write_file参数重建错误工作区，20页拼接出的78987字符diff及SHA与旧`public-capture/member_a.jsonl`中的完整原始回执一致。程序重建明确是CPU回归控制，不是模型重跑或对旧轨迹的修改。首轮`context-regression-development`误把SDK已裁文本当完整diff参考，唯一相关门检查失败，失败目录保留；第二轮改为对照原WorldCore完整回执。

## 原运行的真实闭合结果及逐条审阅

原运行`runs/domain-v028-software-dev-open-runtime/`自然终态为`closed_with_missing_or_interrupted`。5条closed中4条独立验收通过、1条未交付；另1条上下文技术异常未知、2条未启动。原报告已经自动归档推送。以下基于实际消息、文件编辑、补丁导入、测试及固定交付审阅，未重新评分。

| 原槽 | 事实链及独立验收 | Mapper与限定 |
| --- | --- | --- |
| dev-0-first-0-r0 | A实际实现API和consumer；B发消息、导入后未编辑业务文件便再发布补丁；最终A交付，R1。自写test_member.py使用未安装的pytest，6次运行在visible测试通过后仍因ModuleNotFoundError失败，不能照抄模型“全部测试通过”的自述。 | unmapped：自写测试缺少成功验证来源；业务代码集中由A实现，不能按补丁往返次数声称双方共同实现。 |
| dev-1-first-0-r0 | 双方领取不同任务，各自在fields.py引入构造参数错误或破坏性整文件覆盖，无消息、固定补丁、导入和提交；R0。终态A=model_budget_exhausted，B=model_format_error，93 opportunities/89 actions。 | unmapped：无完整交付。不是16K异常，恢复不得挑掉此R0或重新跑到成功为止。 |
| dev-0-first-0-r1 | A把consumer责任转交B；B实现两个文件、测试、固定包含两任务的补丁并提交，R1；A随后导入。 | concentrated_net_delivery：实际是转交后的单成员实现；A后续格式错误不否定先前已有有效交付。 |
| dev-1-first-0-r1 | A提出方案并实现两功能及consumer；B导入A补丁出现真实冲突，随后修改冲突区域、测试、固定两任务补丁并交付，R1。 | unmapped：有跨成员接入和冲突处理，但最终String净来源不能按保守规则确认；不擅自归类或声称独立双分支贡献。 |
| dev-0-first-1-r0 | B固定API补丁，A声明依赖、导入API后编辑consumer；双方后续有重复改动与导入，最终A固定交付通过，R1。 | net_work_after_import：可追踪B→A的API输入和A随后consumer修改；重复导入不重复计新增贡献。 |

这些是复用开发题上的真实冻结模型观察，不是参数训练收益、独立留出确认或因果方法效果。独立验收R1也不等于所有成员自写测试均通过。

## 恢复与GPU5占用

恢复只执行3槽：原技术异常槽`dev-1-first-1-r0`重新开始一次，以及尚未启动的`dev-0-first-1-r1`、`dev-1-first-1-r1`。保留全部5条已闭合结果，包括R0。旧未知attempt及修复后的新attempt分别记录；同slot/seed不能宣称轨迹逐字复现。每个新worker从原完整3/3 checkpoint严格恢复，逐槽重新设置原seed并核对学习状态和RNG，不接着改写旧世界。

用户要求立即占用GPU后，确认GPU5无其他compute进程、空闲容量符合要求，启动本项目reservation进程939191（start_ticks344950613），实际占用约76GiB。该进程只占用显存、模型调用0；状态及命令保存在`runs/v028-context-repair/gpu5-reservation/`。模型恢复前按PID/start_ticks/GPU UUID核对并交接，仅释放本项目reservation；若交接时出现其他作业则回到GPU5排队。显存保留时长与模型执行GPU时长分开记账。GPU7当前已有其他作业，不会触碰。

实际恢复冻结源码为`df37917d0a2b8555125d0bd57309a897be9dd2f5`，工作树`runs/frozen-v028-context-repair/`。同源SDK/tokenizer正式资格4/4程序控制、58次程序请求通过，最大输入7824、最大程序输出635、输出预留后的最小余量6512；同源专项回归14门全部通过，原19439、新分页7961、旧轮筛选后6280、不可舍弃最新轮17481的测量与开发回归一致。两套资格均模型调用0，源提交干净且资格过程中未变。

GPU5 reservation仅在身份核对后释放，实际预留占用 **870.536秒**，与模型运行时间分开记账。释放后首次采样显存已空闲81154MiB，但利用率仍报告99%，因此没有即时准入；后续满足原60秒空卡门后，于北京时间 **2026-10-03T19:14:11+08:00** 启动恢复worker。未更改准入门限或终止其他项目进程。

截至 **2026-10-03T19:17:35.224228+08:00**：归档驱动PID 951091、监督PID 951100、GPU5 worker PID 952068均核对存活、start_ticks和冻结cwd。worker-0状态retained，不再加载模型；worker-1执行恢复计划的3槽。完整原3/3状态恢复校验通过，actor、critic、两优化器及RNG的完整摘要与原checkpoint一致，原marker未变，optimizer更新0。已观察到20次真实响应，首响应HTTP200、原生解析无错误；这只证明已恢复实际采样，不提前声称当前任务成功。

当前有效入口：

- 恢复声明：`runs/v028-context-repair/recovery-plan.json`；同时绑定普通资格、专项资格、原运行闭合记录及reservation身份。
- 启动及核验：同目录`recovery-launch.json`、`recovery-verification.json`、`recovery-finish.log`。
- 当前模型轨迹与监督：`runs/domain-v028-software-dev-context-recovery/`。
- 归档驱动状态：`runs/domain-v028-software-dev-context-recovery-finish.json`。
- 同源资格：`runs/v028-context-repair/frozen-sdk-tokenizer-01/`、`frozen-context-regression-01/`。

[恢复运行报告](software-development-v028-recovery.md)与同名JSON为独立报告，逐槽保留attempt0/attempt1及各自源提交/接口修订，原未知尝试不会被覆盖；模型worker消耗含原运行与恢复运行，并与显存预留分别列示。恢复驱动结束时自动汇总、只提交推送这对新报告。旧[原运行报告](software-development-v028.md)保持原终态。完整计划、进程、交接、恢复和采样证明见[机器证据](software-development-v028-context-repair.json)。


## 恢复终态（2026-10-03 19:44，北京时间）

恢复监督于2026-10-03 19:44:45正常结束，worker退出码0，GPU5已释放。三条恢复任务均完成有限工作过程和独立验收，R均为0、均未固定提交集成交付。结合保留的旧5条，8槽全部有可评结果：4条通过、4条未完成交付；原技术异常attempt仍保留。这是跨原接口与修复接口的任务状态总账，不能当作同一协议的成功率对照或修复效果估计。

恢复轮共172次实际模型响应均HTTP200，最大实测输入11540 tokens，全部请求在16384/2048条件内。没有context_capacity耗尽，也没有再出现原HTTP400 context_length_exceeded；未触发按token数删除较旧工具轮次。本轮模型没有调用diff_workspace，因此本轮真实采样证明无上下文异常，分页大diff的精确回读与超过窗口时的整轮选择仍由专项CPU/真实tokenizer回归证明，不能混同为模型已走过这些工具路径。

三条新轨迹的学习状态均保持不变，RNG均恢复准确。实际模型worker占用：原运行3945.567秒、恢复运行1833.510秒，合计约1.6053 GPU小时；另有870.536秒（约0.2418小时）GPU5预留，占用分列。自动归档驱动已提交推送恢复终态报告，原始请求/响应、token、工具回执、世界版本和原失败attempt保留。

逐槽停止边界及token/HTTP核验见[终态审阅机器记录](software-development-v028-recovery-final-audit.json)。本次只读复核没有重跑模型、重评分或修改原始实验文件。


三条恢复轨迹的逐条内容审阅也已完成（e为software-evidence事件序号，x为experience事件序号）：

| 恢复槽 | 实际工作链 | 结束原因 |
| --- | --- | --- |
| dev-1-first-1-r0 | B领取whitespace并询问实现/交接方案（e2/e13），修改类型声明、基类及String但未发布。A领取casefold（e4），最后用38行String片段覆盖整个fields.py（e70/x1309），固定patch-1并导入自己的补丁（e71/e72）。没有跨成员导入、测试、consumer修改或提交。 | B第33次决策因schema格式失败退场，A达到48次决策（x1365/1366）。整文件覆盖删除导入和基类定义是编辑事实；没有测试，不虚构已观测运行异常。 |
| dev-0-first-1-r1 | A请求B实现API后交接（e16）并等待。B先保持默认False，测试因consumer未适配失败（e23）；随后将默认改True导致回归（e28/e31），再改consumer（e33）仍未通过，最后恢复默认False（e48），但未再测试或交付。全部实际编辑来自B，未发布可供A导入的补丁。 | B达到48次决策上限，A仍等待（x1178/1179）。最后改动未经测试，不能断言代码已修好。 |
| dev-1-first-1-r1 | A提出各自实现再合并（e12），自己未编辑。B只改_deserialize以从kwargs读strip_whitespace（e17），并未实际增加消息中声称的构造参数，随后询问consumer/交接方案（e19）。无测试、补丁、导入或提交。 | A等待B的whitespace补丁，B等待A的casefold/集成方案（x341/359/361），双方等待且无可达新事件。没有格式错误或工具拒绝。 |

此处48次是仍有效的每成员决策次数，不是已撤销的GPU累计时长上限。恢复轮3条未交付均没有触发新上下文容量边界。结合原5条，8个最终选用结果已全部完成内容审阅；原技术未知attempt的根因和原始证据另外保留。
