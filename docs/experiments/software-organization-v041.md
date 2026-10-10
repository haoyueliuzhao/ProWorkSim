# v0.41 详细报告：静态去重已修订，完整反馈容量准入未通过

**本轮完成两版呈现候选的CPU准入实验；新16槽模型比较全部未启动。** 代码机制的30项必要检查和全局Ruff均通过，但最终容量资格`passed=false`，因此没有加载9B权重、没有真实模型调用、没有GPU worker，也没有启动首个配对块。v0.40原16槽及其R=0不改写。

## 1. 范围与实际推进

用户要求依据[v0.40审计](../reference/audit-v040-next-v041.md)修订并开展后续实验。审计规定：先去除同成员的重复静态信息，以实际tokenizer验证完整行动—反馈—下一行动；P0-A/B/C通过后，才执行两个原承接态root×shared/split×base/team×两个新seed的16槽。详细事前条件见[协议](software-organization-v041-protocol.md)。

本轮先保留原合同去重并新增`role_task`、`initial_diagnostics`精确去重。首版不通过后，在任何模型采样前仅扩展到源码可证明固定的九类政策字段，重新完整测量同一组历史前缀及同一组程序路线。两版结果与各自源码快照都保存，没有覆盖首版失败，也没有只重测失败个案。第二版仍不通过，故在CPU门槛处结束本轮，不做第三候选或临时分页。

固定原9B tokenizer/native renderer，context=16384、输出预留2048，因此完整prompt≤14336。历史请求与程序请求均先原生渲染，再对整个请求实际编码；没有以Unicode字符数或片段token加和代替。此阶段不加载common/模型权重、不恢复参数，也不运行概率或反向计算。

## 2. 实现与信息边界

新增独立v041上下文与运行时，原v040及更早冻结源码保持。仅当同成员、world/instance/branch/project/接口身份、同语义字段、证据身份/版本及完整值相等时，移除较早静态快照；最新完整正文仍留在selected请求。原/selected请求、删除位置、保留位置、证据身份、原生prompt、实际input IDs及SHA都归档。

第二版声明的额外固定字段为`action_error_policy`、`acceptance_contract`、`scheduling`、`member_limits`、`shared_resource_limits`、`isolation`、`observation_projection`、`initial_diagnostic_provenance`和`editable_paths`。它们另绑定同root合同，初始诊断来源同时绑定原报告身份。调度中的`first_member`是事前冻结先手，不是当前调度游标。

`execution_condition`实时人数、`task_formation`计数、成员注册表、任务、消息、预算及其他动态字段不因当前相等就删除。工具调用及原v040规定可见的完整最新返回不改写；没有向其他成员或新生补诊断，没有以hash代正文，没有免费加入host stdout/API细迹，没有摘要或自动提交。已有较旧完整工具回合选择规则继续适用。

呈现位置与重复次数变化可能影响行为，这是新Γ；CPU容量改善不能证明行为等价，也不能计为参数学习或ID-VTDO分配收益。

## 3. P0-A：原32次拒绝前缀实际分词复核

| 候选 | 原记录完整复现 | 新请求fit | 最大新prompt | 最小余量 | 门槛 |
|---|---:|---:|---:|---:|---|
| 1 | 32/32 | 27/32 | 15001 | -665 | 未通过 |
| 2 | 32/32 | 31/32 | 14396 | -60 | 未通过 |

每条原SDK选中消息及完整请求SHA均匹配归档；旧selected请求、prompt token、渲染SHA及input-ID SHA也均复现。原记录拒绝范围为14360—16537 prompt token。首版关键ST例14365/14360→11910/11905，余量2426/2431，说明修复不只是腾出29 token；但完整分母仍有5条不fit。

| slot / 成员 | 旧prompt | 候选1prompt | 候选2prompt | 候选2余量 | 候选2fit |
|---|---:|---:|---:|---:|---|
| org40-r0-s0-SB / member_002 | 14572 | 12669 | 12064 | 2272 | 是 |
| org40-r0-s0-SB / member_001 | 16361 | 13992 | 14255 | 81 | 是 |
| org40-r0-s0-ST / member_001 | 14427 | 11972 | 11367 | 2969 | 是 |
| org40-r0-s0-ST / member_002 | 14369 | 11914 | 11309 | 3027 | 是 |
| org40-r0-s0-PB / member_002 | 15832 | 14444 | 13839 | 497 | 是 |
| org40-r0-s0-PB / member_001 | 15428 | 14017 | 13928 | 408 | 是 |
| org40-r0-s0-PT / member_001 | 15084 | 14012 | 13872 | 464 | 是 |
| org40-r0-s0-PT / member_002 | 16475 | 15001 | 14396 | -60 | 否 |
| org40-r0-s1-ST / member_002 | 14365 | 11910 | 11305 | 3031 | 是 |
| org40-r0-s1-ST / member_001 | 14360 | 11905 | 11300 | 3036 | 是 |
| org40-r0-s1-PB / member_001 | 14910 | 13499 | 14209 | 127 | 是 |
| org40-r0-s1-PB / member_002 | 14430 | 14081 | 14213 | 123 | 是 |
| org40-r0-s1-PT / member_002 | 15922 | 14448 | 13843 | 493 | 是 |
| org40-r0-s1-PT / member_001 | 15576 | 14079 | 13900 | 436 | 是 |
| org40-r0-s1-SB / member_002 | 14523 | 12154 | 11549 | 2787 | 是 |
| org40-r0-s1-SB / member_001 | 14667 | 12298 | 11693 | 2643 | 是 |
| org40-r1-s0-PB / member_002 | 15525 | 13944 | 13741 | 595 | 是 |
| org40-r1-s0-PB / member_001 | 15248 | 14138 | 13533 | 803 | 是 |
| org40-r1-s0-PT / member_001 | 15500 | 13947 | 14068 | 268 | 是 |
| org40-r1-s0-PT / member_002 | 15580 | 14307 | 14044 | 292 | 是 |
| org40-r1-s0-SB / member_002 | 14821 | 12203 | 11598 | 2738 | 是 |
| org40-r1-s0-SB / member_001 | 14858 | 12240 | 11635 | 2701 | 是 |
| org40-r1-s0-ST / member_002 | 14962 | 12258 | 11653 | 2683 | 是 |
| org40-r1-s0-ST / member_001 | 14866 | 12162 | 11557 | 2779 | 是 |
| org40-r1-s1-PT / member_001 | 15328 | 13775 | 14279 | 57 | 是 |
| org40-r1-s1-PT / member_002 | 16537 | 14870 | 14265 | 71 | 是 |
| org40-r1-s1-SB / member_001 | 14814 | 12196 | 11591 | 2745 | 是 |
| org40-r1-s1-SB / member_002 | 14975 | 12357 | 11752 | 2584 | 是 |
| org40-r1-s1-ST / member_001 | 15094 | 12390 | 11785 | 2551 | 是 |
| org40-r1-s1-ST / member_002 | 15087 | 12383 | 11778 | 2558 | 是 |
| org40-r1-s1-PB / member_001 | 15355 | 13888 | 13947 | 389 | 是 |
| org40-r1-s1-PB / member_002 | 15919 | 14338 | 14254 | 82 | 是 |

最后一条仍不fit的是`org40-r0-s0-PT/member_002`：14396+2048=16444，超出60 token。它保留了一次真实`run_tests`完整可见返回（9981字符）和一条真实格式反馈（1656字符），selected角色为system、user、user、assistant、tool、user。测试指向`obj-520aa9e6ee8ece99dce73855/v1`，files SHA为`90963997cd9f8ea92c4d8a0513e68a69392b6a658fd958d15a355c50143ac0a0`；公开业务7项5过2败、upstream1过、成员自测未执行。字符数仅用于描述体量，不代表独立token成本。

这只回答原历史前缀在新表示下能否容纳。没有重采原模型动作，不能说模型在新协议下仍会走到相同前缀或最终成功。14396也仅是当前允许删除规则下的剩余长度，不是信息论意义的最短表示。

## 4. P0-B/C：真实SDK程序路线与完整反馈往返

以CPU私有程序驱动真实SDK/世界工具，明确标记为`cpu_private_program`。它不是模型生成，也不进入模型提示或规定真实团队分工。每个root、四条件、两初始成员共16形状，从初始化与正常读文件，推进至公开失败反馈、合法修复、公开通过反馈、固定与提交后的机会；容量失败即停止该路线，其后的动作没有伪造为已执行。未运行独立私有验收。

| 候选 | 核心路线通过 | 代表路线通过 | 实测请求阶段 | 最大prompt | 最小选中余量 | 全阶段信息不变量 |
|---|---:|---:|---:|---:|---:|---|
| candidate1 | 4/16 | 11/12 | 112 | 15676 | -1340 | 全部通过 |
| candidate2 | 12/16 | 12/12 | 152 | 15064 | -728 | 全部通过 |

第一版12条核心路线在失败测试反馈后的请求停止，另有catalog最大实际文件读取页超限。第二版所有代表控制通过，核心剩余4条catalog shared仍未通过。

| 候选2核心形状 | 通过 | 测量阶段数 | 最大prompt | 最小选中余量 | 最后实际测量阶段 |
|---|---|---:|---:|---:|---|
| core-r0-SB-member_001 | 是 | 8 | 14247 | 89 | after_submit_integration |
| core-r0-SB-member_002 | 是 | 8 | 14206 | 130 | after_submit_integration |
| core-r0-ST-member_001 | 是 | 8 | 14332 | 4 | after_submit_integration |
| core-r0-ST-member_002 | 是 | 8 | 14293 | 43 | after_submit_integration |
| core-r0-PB-member_001 | 是 | 8 | 14284 | 52 | after_submit_integration |
| core-r0-PB-member_002 | 是 | 8 | 14326 | 10 | after_submit_integration |
| core-r0-PT-member_001 | 是 | 8 | 14118 | 218 | after_submit_integration |
| core-r0-PT-member_002 | 是 | 8 | 14331 | 5 | after_submit_integration |
| core-r1-SB-member_001 | 否 | 3 | 14978 | -642 | after_failed_public_tests |
| core-r1-SB-member_002 | 否 | 3 | 14962 | -626 | after_failed_public_tests |
| core-r1-ST-member_001 | 否 | 3 | 15064 | -728 | after_failed_public_tests |
| core-r1-ST-member_002 | 否 | 3 | 15043 | -707 | after_failed_public_tests |
| core-r1-PB-member_001 | 是 | 8 | 14324 | 12 | after_submit_integration |
| core-r1-PB-member_002 | 是 | 8 | 14240 | 96 | after_submit_integration |
| core-r1-PT-member_001 | 是 | 8 | 14234 | 102 | after_submit_integration |
| core-r1-PT-member_002 | 是 | 8 | 14311 | 25 | after_submit_integration |

剩余失败均为catalog的`after_failed_public_tests`：SB/member_001=14978（超642）、SB/member_002=14962（超626）、ST/member_001=15064（超728）、ST/member_002=15043（超707）。

## 5. 最差合法反馈的具体组成

候选2最差为catalog ST/member_001。原v040规定可见的`run_tests`返回完整保留，为11367字符/UTF-8字节；完整原生prompt52280字符，实际15064 token，加2048输出为17112，超728。请求保留system、首观察、最新assistant/tool往返、末观察；之前读文件的完整旧往返已经删除，再删就会破坏保护的最新失败反馈。

该可见结果包含两个公开诊断组、各组与成员测试事实、source_reference/files SHA、测试预算、不测项声明和原反馈呈现说明。其`public_diagnostics`序列化5552字符、`groups`3307字符等仅是字段体量；没有单独重新分词或将字段数相加当完整请求token，也不主张每个事实在各字段间绝无重叠。现有重复删除规则不能继续合法降低这个请求。

最新返回SHA：`b400f26e882e9e0e7b7e2a61c892a74a205aeb5c60f02c6a9652efcb10c29338`；完整input-ID SHA：`611ff6deb290ba2125a2def6f6128b2388fb630b46c3541a2cdbf7d115ba5e35`。完整证据路径及源版本见机器报告。初始报告仍对应初态，当前测试仍是独立事件，不能因某些文本相同而把两者合并。

候选2通过阶段也出现4/5/10 token选中余量：这是旧选择器保留尽可能多完整历史回合直到刚好fit后的值，不能据此断言独特必需正文只剩4 token空间。相反，失败阶段已去掉可删除旧回合后仍超限，构成明确门槛失败。不同新世界路线的ID/预算摘要会变化，两版最大值之差也不能全部归因静态字段；因果式节省应对同一原请求测量。

## 6. 已预声明的较大返回与其他代表控制

每个root覆盖六类代表路线：最大实际文件180行读取页、修复差异6000字符页、4000字符合法消息、普通未知工具名拒绝后的反馈与恢复、四项任务增长、新生非空briefing初始化与读文件。最大实际文件为`test_visible.py`的91行；所有请求保持完整工具schema和2048预留，没有临时换短页。

| 候选2代表路线 | 通过 | 最大prompt | 最小选中余量 |
|---|---|---:|---:|
| representative-r0-largest_legal_read | 是 | 13676 | 660 |
| representative-r0-repair_diff | 是 | 12556 | 1780 |
| representative-r0-message_4000 | 是 | 12480 | 1856 |
| representative-r0-format_rejection | 是 | 11709 | 2627 |
| representative-r0-task_growth_4 | 是 | 12429 | 1907 |
| representative-r0-newborn | 是 | 11994 | 2342 |
| representative-r1-largest_legal_read | 是 | 13933 | 403 |
| representative-r1-repair_diff | 是 | 12987 | 1349 |
| representative-r1-message_4000 | 是 | 12802 | 1534 |
| representative-r1-format_rejection | 是 | 12043 | 2293 |
| representative-r1-task_growth_4 | 是 | 12701 | 1635 |
| representative-r1-newborn | 是 | 12105 | 2231 |

它们是有限代表形状，不声称穷举任意代码、消息或无限任务增长。CPU程序能够完成某些固定提交仅证明这些路线在环境中存在，不是模型成功率、协作效果或隐藏验收成绩。

## 7. 检查、成本与本轮未执行范围

最终统一核验：30项必要CPU合同检查通过（含真实SDK的脚本化接入），全局`ruff check src tests scripts`通过；只有既有第三方Pydantic ReadOnly警告。源码/回执引用集成期间发现SHA字符串与引用对象的格式处理差异，已修复；保留中间检查日志，未重跑P0世界路线或改其资格数据。最终资格仍因P0容量失败为false，而非代码测试失败。另将真实失败资格送入prepare，确认在建立实验plan和加载模型前抛出拒绝，目标目录未创建；回执见机器报告。

新增反馈测量器已实现“保存→后续真实selected输入→相关行为候选→固定交付关联”的分层与无后续原因分母。实际呈现不等于理解或因果采用。首块门槛和直接worker入口均检查同一机制证据，不依赖R、消息或出生数；但本轮尚未调用这一模型阶段门槛，不能声称已通过。

| P0-B/C成本 | 候选1 | 候选2 | 说明 |
|---|---:|---:|---|
| CPU程序响应 | 99 | 148 | 脚本化SDK控制响应，不是模型生成 |
| 成员公开测试调用 | 20 | 28 | 实际CPU公开检查 |
| 初始环境诊断driver | 16 | 16 | 准备成本，不是成员发现 |
| 独立私有验收driver | 0 | 0 | 未对CPU提交补验 |
| 测量阶段 | 112 | 152 | 实际原生请求编码 |
| 路线阶段墙钟秒 | 26.735596895217896 | 33.20369100570679 | 并行CPU墙钟，不是累计CPU核秒或GPU时间 |

上述成本仅指P0-B/C两版路线；P0-A分词及必要pytest另有日志，不混算为真实模型成本。两候选路线合计247次CPU程序响应、48次成员公开测试调用、32次初始诊断driver，私有验收0。

**新模型经历0/16、真实模型调用0、权重加载0、GPU-worker时间0、反向0、actor/critic更新0。** GPU3/4/5/7只读检查时有空闲，但容量门槛失败与GPU空闲无关。本轮不使用v040额外卡许可，没有启动监督/接管队列，没有自动后继。原26次Contribution试训、3次正式更新、48条TextFSM独立确认及缓存生产验证继续暂停；原3/3 common与共同B 4/4及全部历史结果保留。

## 8. 原新16槽库存的状态

预登记seed为202610100401、202610100402；首块原计划ST/PB/PT/SB，随后三个块依门槛并行。所有槽均未启动，不赋R=0，不标成已执行的技术未知；信息主效应、说明主效应和交互均未测量。没有从12条能完成的CPU核心形状中挑样去运行模型。

| slot | root | seed | 状态 | R |
|---|---|---:|---|---|
| org41-r0-s0-ST | sc-record-views-handoff-v040 | 202610100401 | 未启动：CPU容量未通过 | 未测 |
| org41-r0-s0-PB | sc-record-views-handoff-v040 | 202610100401 | 未启动：CPU容量未通过 | 未测 |
| org41-r0-s0-PT | sc-record-views-handoff-v040 | 202610100401 | 未启动：CPU容量未通过 | 未测 |
| org41-r0-s0-SB | sc-record-views-handoff-v040 | 202610100401 | 未启动：CPU容量未通过 | 未测 |
| org41-r0-s1-PB | sc-record-views-handoff-v040 | 202610100402 | 未启动：CPU容量未通过 | 未测 |
| org41-r0-s1-PT | sc-record-views-handoff-v040 | 202610100402 | 未启动：CPU容量未通过 | 未测 |
| org41-r0-s1-SB | sc-record-views-handoff-v040 | 202610100402 | 未启动：CPU容量未通过 | 未测 |
| org41-r0-s1-ST | sc-record-views-handoff-v040 | 202610100402 | 未启动：CPU容量未通过 | 未测 |
| org41-r1-s0-PT | sc-record-catalog-handoff-v040 | 202610100401 | 未启动：CPU容量未通过 | 未测 |
| org41-r1-s0-SB | sc-record-catalog-handoff-v040 | 202610100401 | 未启动：CPU容量未通过 | 未测 |
| org41-r1-s0-ST | sc-record-catalog-handoff-v040 | 202610100401 | 未启动：CPU容量未通过 | 未测 |
| org41-r1-s0-PB | sc-record-catalog-handoff-v040 | 202610100401 | 未启动：CPU容量未通过 | 未测 |
| org41-r1-s1-SB | sc-record-catalog-handoff-v040 | 202610100402 | 未启动：CPU容量未通过 | 未测 |
| org41-r1-s1-ST | sc-record-catalog-handoff-v040 | 202610100402 | 未启动：CPU容量未通过 | 未测 |
| org41-r1-s1-PB | sc-record-catalog-handoff-v040 | 202610100402 | 未启动：CPU容量未通过 | 未测 |
| org41-r1-s1-PT | sc-record-catalog-handoff-v040 | 202610100402 | 未启动：CPU容量未通过 | 未测 |

## 9. 下一步需要明确的返回协议（未实现、未采样）

精确静态去重提供了有界改善证据，但不足以容纳完整工作循环。继续堆seed、增加团队累计token或空闲GPU不能改变当前单请求边界。下一步应先冻结返回范围或精确分页，再重新验证所有形状；本轮没有用新返回协议替换失败结果。

若采用精确分页，需要明确：

1. 仅分页原v040允许看到的信息集合；完整公开失败请求、观察/预期、各组事实、来源版本、不测项和完整性声明仍可恢复，不增加host-only stdout/API细迹。
2. 页绑定一次真实测试事件、成员权限、不可变源版本/files SHA、诊断组/test ID和稳定位置；初始诊断与后续测试不同事件，不合并。
3. 首页明确可见内容范围、剩余页和结束状态；后续页由成员主动合法读取，记录工具决定、模型调用和预算，不后台代读、不免费补输入、不只给hash声称正文已知。
4. 事先固定排序、页边界、超长单项精确分段和cursor规则；不是根据结果选择保留失败。此处尚未选择页大小或实施新工具。
5. 用固定16384/2048的完整原生请求重新测16形状的失败→修复→通过→固定/提交及已声明代表控制。分页改变信息时点和代价，是另一版Γ，不宣称行为等价或学习收益。

因此本轮可封存为“修订与CPU准入实验完成、容量门槛未通过、模型16槽未启动”。现有数据不支持协作收益、模型不愿交流、模型不会利用反馈或条件等价的判断。

## 10. 复核入口

- [机器报告](software-organization-v041.json)包含32前缀逐项、两版28条程序路线的阶段统计、完整来源引用/hash、最终代码资格和16槽未启动清单。
- P0-A：`runs/v041-controls/context-replay/`、`context-replay-candidate2/`，各自保留qualification、原/新请求、原生prompt、input IDs、projection、record及source-snapshot。
- P0-B/C：`runs/v041-controls/feedback-route/`、`feedback-route-candidate2/`，各自保留qualification、实际SDK世界、逐阶段原/selected请求/编码及source-snapshot。
- 最终门槛：`runs/v041-controls/organization-launch-closed/qualification.json`；两份check日志通过，但`capacity_controls_passed=false`。
- 只读容量汇总：`runs/v041-controls/capacity-summary.json`；生成本报告未重新分词、测试、验收或调用模型。
