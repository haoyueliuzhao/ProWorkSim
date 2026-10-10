# v0.44 批次停止政策修订与原16槽完整报告

**原九个剩余槽已全部闭合，原七槽保留，唯一16槽库存结果完整。新增九槽6次完整成功、3槽未提交；合并原16槽9次完整成功、7槽未提交，技术未知和未启动均为0。模型可见工作条件保持，批次停止政策作了明确披露的修订；不能称原研究协议毫无改动，也不能称容量问题已修复。**

完整四块等权比较：信息效应 DI=0.125，工作说明效应 DG=0.125，交互 DIG=0.25。这是原两个开发root、两seed在固定16K与团队预算下的有限综合结果，不是总体稳定效应或排除容量影响后的纯协作能力。

## 1. 改变范围与必要准入

用户随新审计明确要求修订并开展实验。本轮只针对原九槽修改宿主批次停止作用域：记录完整、执行前安全拒绝且业务结果可评的局部context终止，保留原成员停止和反馈未呈现，但不再自动取消其它独立episode。R0/R1、提交前后适用同一规则。

原单成员/episode行为、16K/2048、3072字符精确分页、普通格式反馈生命周期、工具schema、任务/初始信息、原9B完整common3/3、原seed和固定验收均不改。不补生成、不缩输出、不增预算、不恢复成员，不将旧正确patch或审计说明带入模型初态。两成员仍中性起步、空任务表，自主形成职责；没有临时指定经理、测试者或最终提交者。

真实输入遗漏、权限/来源/身份/费用/世界执行或共同服务不可信仍全局暂停；证据不足为measurement_pending。显式禁止controller_add_neutral_member请求在本次宿主策略中也保守列为控制权限暂停项；其原规则是执行前阻断，不能写成已经发生越权副作用。普通未知工具、参数和格式错误不在该标记范围。

独立审阅修正了政策初稿的一项过窄条件：context超限时若团队余额也不足，不能仅因此升级为全局故障。r2将可信非负余额和并发预约不足分别记录，后者只作描述。两版只读窄回执均保留，未改模型Γ或重新分词。

80项必要CPU控制通过（停止政策33、准入25、入口及三阶段合并22），全局Ruff通过。1292份旧执行/任务/控制文件逐字节同67a，新增6份声明的宿主源及测试；旧112形状、分页及近16K资格按原引用复用，没有重跑。pytest命令墙钟0.704066秒、Ruff0.052308秒；分模块开发控制不当作独立模型样本累计。

| 阶段 | 实际执行源 | 结果处理 |
|---|---|---|
| 原首块4槽 | e8aa60bd1a427944d8503fb02b30f6379ebd5889 | 原R、原false与停止记录保持；退休原因只读修订另存 |
| 首次接续3槽 | 67a4da1194cdad7de66d7621bf568261338f4f01 | 原R1/1/0、真实ST硬context及后9未启动事实保持 |
| 本次原9槽 | 519a18c4e9397b008a16bf1f40b12726feb34804 | 同模型工作条件，明确修改批次停止政策 |

三阶段src树均为 `47eb019ff4cc6170111cec16ab4c538c57719ad23d8774a5fd0c82dbc3caba30`。原gate=false、退休修订gate=true和前次真实context停机均保留；新host回执没有改写任何旧门。

## 2. 唯一库存与正式结果

原4＋前接续3＋本次9=唯一16。原七槽没有重跑，三个原块各自剩余三槽由新worker按原顺序执行，每个worker恢复一次冻结common，每槽按原规则重置。没有恢复旧成员或整块从头启动。旧七槽未消费130862 token不转移。

| slot | 阶段 | R | 固定提交 | 决定/实际调用 | 输入/输出token | 实际总token | run_tests |
|---|---|---:|---|---|---|---:|---:|
| org44-r0-s0-ST | retained_first_continuation_three | 1 | True | 39/37 | 486654/8330 | 494984 | 3 |
| org44-r0-s0-PB | new_original_remaining_nine | 1 | True | 41/39 | 485129/8476 | 493605 | 4 |
| org44-r0-s0-PT | new_original_remaining_nine | 0 | False | 41/39 | 485373/11498 | 496871 | 5 |
| org44-r0-s0-SB | new_original_remaining_nine | 1 | True | 38/37 | 477308/7661 | 484969 | 2 |
| org44-r0-s1-PB | retained_first_continuation_three | 1 | True | 39/38 | 478073/10339 | 488412 | 6 |
| org44-r0-s1-PT | new_original_remaining_nine | 1 | True | 40/38 | 479144/8525 | 487669 | 7 |
| org44-r0-s1-SB | new_original_remaining_nine | 1 | True | 19/17 | 208096/3065 | 211161 | 4 |
| org44-r0-s1-ST | new_original_remaining_nine | 0 | False | 39/37 | 484569/12601 | 497170 | 5 |
| org44-r1-s0-PT | retained_original_four | 1 | True | 34/34 | 420138/7292 | 427430 | 3 |
| org44-r1-s0-SB | retained_original_four | 0 | False | 38/36 | 474975/13677 | 488652 | 3 |
| org44-r1-s0-ST | retained_original_four | 0 | False | 38/36 | 472077/17311 | 489388 | 3 |
| org44-r1-s0-PB | retained_original_four | 0 | False | 40/38 | 473729/13647 | 487376 | 5 |
| org44-r1-s1-SB | retained_first_continuation_three | 0 | False | 39/37 | 478307/14589 | 492896 | 3 |
| org44-r1-s1-ST | new_original_remaining_nine | 1 | True | 40/38 | 486633/8436 | 495069 | 3 |
| org44-r1-s1-PB | new_original_remaining_nine | 0 | False | 40/38 | 473404/12506 | 485910 | 5 |
| org44-r1-s1-PT | new_original_remaining_nine | 1 | True | 40/38 | 480442/10257 | 490699 | 8 |

R只按原最终固定内容验收与运行合同确定。公开测试通过、可变副本、固定提交和后验独立验收分开；没有补验未提交工作区，也不将多次同版本提交计为多个成功样本。

## 3. 完整四块比较

SB/ST为shared初始诊断，PB/PT为split初始诊断；B为基础说明，T为共同交付说明。所有条件初始2成员、活动≤4、累计出生≤6，任务板为空，无预定职责或经理。信息布局与工作说明为原四条件的两个比较维度。

| 块 | SB | ST | PB | PT | DI | DG | DIG |
|---|---:|---:|---:|---:|---:|---:|---:|
| block-r0-s0 | 1 | 1 | 1 | 0 | -0.5 | -0.5 | -1 |
| block-r0-s1 | 1 | 0 | 1 | 1 | 0.5 | -0.5 | 1 |
| block-r1-s0 | 0 | 0 | 0 | 1 | 0.5 | 0.5 | 1 |
| block-r1-s1 | 0 | 1 | 0 | 1 | 0.0 | 1.0 | 0 |

DI=(PB+PT−SB−ST)/2；DG=(ST+PT−SB−PB)/2；DIG=PT−PB−ST+SB。先每个root/seed块内计算，再对原4块等权平均。

| 条件 | 成功/4 | 均值R |
|---|---:|---:|
| SB | 2/4 | 0.5 |
| ST | 2/4 | 0.5 |
| PB | 2/4 | 0.5 |
| PT | 3/4 | 0.75 |

四块主效应均值：DI=0.125、DG=0.125、DIG=0.25。所有槽都进入原估计量，包括context终止、正常预算终止及未提交；没有比较context-free子集来替代原面板。

只有两个开发root、四个配对块。这些数值描述信息布局、取得成本、输入历史容量、模型行为与交付流程的共同结果；不能解释为排除了资源边界的纯协作收益，不能直接推出总体稳定性，更不支持参数训练增益。

## 4. 局部context真实保留，放行作用域真实改变

本次3次硬context拒绝、14次团队预约拒绝分别记录。硬context的后续库存继续，不意味着受阻成员恢复或反馈已呈现。

| 槽/成员 | R | 原拒绝种类 | P | 预约输出 | P+预约 | 硬余量 | 当时池余额 | 最终池余额 | 相对首次成功提交 |
|---|---:|---|---:|---:|---:|---:|---:|---:|---|
| org44-r0-s0-PB/member_001 | 1 | team_reservation | 12963 | 2048 | 15011 | 1373 | 6395 | 6395 | 不适用 |
| org44-r0-s0-PB/member_002 | 1 | team_reservation | 12900 | 2048 | 14948 | 1436 | 6395 | 6395 | 不适用 |
| org44-r0-s0-PT/member_001 | 0 | team_reservation | 11145 | 2048 | 13193 | 3191 | 3129 | 3129 | 不适用 |
| org44-r0-s0-PT/member_002 | 0 | team_reservation | 14086 | 2048 | 16134 | 250 | 3129 | 3129 | 不适用 |
| org44-r0-s0-SB/member_002 | 1 | team_reservation | 14317 | 2048 | 16365 | 19 | 15031 | 15031 | 不适用 |
| org44-r0-s1-PT/member_001 | 1 | team_reservation | 14109 | 2048 | 16157 | 227 | 12331 | 12331 | 不适用 |
| org44-r0-s1-PT/member_002 | 1 | team_reservation | 11794 | 2048 | 13842 | 2542 | 12331 | 12331 | 不适用 |
| org44-r0-s1-SB/member_001 | 1 | hard_context | 14363 | 2048 | 16411 | -27 | 301443 | 288839 | after_first_successful_world_submission |
| org44-r0-s1-SB/member_002 | 1 | hard_context | 14350 | 2048 | 16398 | -14 | 288839 | 288839 | after_first_successful_world_submission |
| org44-r0-s1-ST/member_001 | 0 | hard_context | 15579 | 2048 | 17627 | -1243 | 186909 | 2830 | no_successful_world_submission_in_episode |
| org44-r0-s1-ST/member_002 | 0 | team_reservation | 13841 | 2048 | 15889 | 495 | 2830 | 2830 | 不适用 |
| org44-r1-s1-ST/member_002 | 1 | team_reservation | 13287 | 2048 | 15335 | 1049 | 4931 | 4931 | 不适用 |
| org44-r1-s1-ST/member_001 | 1 | team_reservation | 13859 | 2048 | 15907 | 477 | 4931 | 4931 | 不适用 |
| org44-r1-s1-PB/member_002 | 0 | team_reservation | 13173 | 2048 | 15221 | 1163 | 14090 | 14090 | 不适用 |
| org44-r1-s1-PB/member_001 | 0 | team_reservation | 12558 | 2048 | 14606 | 1778 | 14090 | 14090 | 不适用 |
| org44-r1-s1-PT/member_002 | 1 | team_reservation | 14016 | 2048 | 16064 | 320 | 9301 | 9301 | 不适用 |
| org44-r1-s1-PT/member_001 | 1 | team_reservation | 13646 | 2048 | 15694 | 690 | 9301 | 9301 | 不适用 |

views/seed442/SB的两次context请求分别为14363+2048、14350+2048，超限27/14；当时余额301443/288839，无并发预算短缺。两次都发生在首次成功世界提交之后；m001停止后只有伙伴多生成一次，不能把其拒绝余额替换成终态余额。feedback271/316是两份run_tests首页，均保存但未进入后续实际生成。该槽R1对应已有固定v3及闭合后的原私有/公开验收，模型当时只知道pending independent acceptance。

views/seed442/ST的R0也同样放行：m001请求15579+2048=17627，超限1243，当时余额186909。该episode没有任何提交请求；另一成员随后继续13次实际生成，最终余额2830只用于后面的正常预算拒绝。feedback415仍未呈现，停止成员未恢复。公开测试通过的可变v4没有固定交付或独立验收，不能推断若无context就必然成功。

上述三个拒绝调用在原经验记录中仅有生成前model_call:started，没有attempt、输出、收费、工具执行或action_link；全部实际费用精确对应其它已生成调用。原sealed preparation、actor/window/recipe、同机会边界与账本一致，未呈现反馈ID保留。证明消费原件，不新增tokenizer、渲染候选或模型资格。

提交时序通过同一experience中的实际调用→已提交工具事件→action_link→世界返回唯一关联。失败submit的命令也可能有committed留痕，但ok=false不算成功提交；不比较世界seq和experience seq数值，不用私有R决定提交时点。时序只作描述，不用于scope或筛样。

本次实际已生成请求最小selected硬余量0 token；protected扣1024工程余量不足15次，最低-803。工程余量仅诊断；等于硬界的合法请求不因余量不足停止。拒绝前缀不混入实际生成分母。

原七槽已有的那次ST硬拒绝（超229、当时余额231277）仍保留。完整面板含所有容量中断，不能写成容量已修复或所有反馈都能继续消费。

## 5. 反馈生命周期、页覆盖与实际使用

| 指标 | 原7保留 | 新9 | 唯一16 |
|---|---:|---:|---:|
| 全部反馈 | 256 | 321 | 577 |
| 首次后续实际呈现 | 242 | 303 | 545 |
| 无后续实际生成 | 14 | 18 | 32 |
| 普通格式反馈登记 | 20 | 25 | 45 |
| 普通格式反馈实际呈现 | 20 | 24 | 44 |
| 有后续实际移除的不同ID（按槽限定） | 17 | 23 | 40 |
| ID×后续输入移除出现 | 175 | 313 | 488 |
| 报告保存 | 26 | 43 | 69 |
| 报告至少一页实际可见 | 25 | 40 | 65 |
| 额外实际读页 | 5 | 11 | 16 |
| 报告历史完整覆盖 | 0 | 0 | 0 |

合并无后续原因：`{'voluntary_end': 3, 'voluntary_self_retirement': 1, 'team_budget': 24, 'context_capacity': 4}`。普通格式最终状态：`{'superseded': 11, 'historicalized_after_legal_native_schema': 33, 'pending_or_presented': 1}`。保留全部反馈分母，正常预算/退役没有未来生成也不补造呈现。

catalog/seed442/PB末次Incomplete native tool block反馈因为团队预算终止没有后续生成，仍保持待呈现；这不等于正文被错误删除。历史化、被新错误替代、真正下一输入移除分别计数，被替代不冒称已经修好。未全读不判失败，页覆盖并集不等于同时可见、理解或采用。

## 6. 正式交付与协作事实

| 新槽 | R | 最终固定交付 | world成功submit次数 | 已证实跨成员链 | 自主出生 | context事件 |
|---|---:|---|---:|---|---:|---:|
| org44-r0-s0-PB | 1 | member_002/v3/delivery-1 | 1 | False | 0 | 0 |
| org44-r0-s0-PT | 0 | 无固定交付 | 0 | False | 0 | 0 |
| org44-r0-s0-SB | 1 | member_001/v3/delivery-1 | 1 | False | 0 | 0 |
| org44-r0-s1-PT | 1 | member_002/v3/delivery-3 | 3 | False | 0 | 0 |
| org44-r0-s1-SB | 1 | member_002/v3/delivery-1 | 1 | False | 0 | 2 |
| org44-r0-s1-ST | 0 | 无固定交付 | 0 | False | 0 | 1 |
| org44-r1-s1-ST | 1 | member_002/v3/delivery-1 | 1 | False | 0 | 0 |
| org44-r1-s1-PB | 0 | 无固定交付 | 0 | False | 0 | 0 |
| org44-r1-s1-PT | 1 | member_002/v4/delivery-1 | 1 | False | 0 | 0 |

views/seed441/PT两名成员最后各有公开测试通过，但没有fix_patch或submit，正式R0。catalog/seed442/PB亦没有固定交付；其中member002末次公开/upstream组仍通过，失败的是后来自己写的test_member.py，不能误称公开业务回归，也不能补验工作副本抬高R。

views/seed442/PT的member002对同一v3三次成功world submit，只计一个槽的最终交付与原最后固定树验收。catalog/seed442/ST先有五次未发布fixed patch的提交拒绝，最终才固定并成功提交；拒绝保持原样呈现，不因最后成功改写中间行为。

新九槽工作链测量：`{'true': 0, 'false': 9, 'unknown': 0}`；程序链0、连至交付的程序链0、待决关系0、信息候选0。原七槽均未证实跨成员使用链。初始代码和环境诊断不算当前模型产生的成果，多个成员分别工作或代码相似不等于相互使用。

新世界事件统计：`{'read': 159, 'edit': 42, 'test': 43, 'test_report_saved': 43, 'test_report_page_read': 11, 'patch_fixed': 8, 'submit': 8, 'member_retired': 1}`。消息、任务发布、伙伴patch导入和新增成员均为0。没有用消息数、任务ID或出生数替代成果使用；集中完成、不增员本身并不作为失败。

## 7. 三阶段成本与资源

| 指标 | 原4 | 前接续3 | 本次9 | 原16合计 |
|---|---:|---:|---:|---:|
| 决定 | 150 | 117 | 338 | 605 |
| 实际调用 | 144 | 112 | 321 | 577 |
| 输入token | 1840919 | 1443034 | 4060098 | 7344051 |
| 输出token | 51927 | 33258 | 83025 | 168210 |
| 实际总token | 1892846 | 1476292 | 4143123 | 7512261 |
| run_tests/实际公开driver | 14 | 12 | 43 | 69 |
| 成员脚本执行 | 1 | 0 | 1 | 2 |
| 初态公开driver | 2 | 6 | 6 | 14 |
| 初态缓存复用槽 | 3 | 0 | 6 | 9 |
| 最终私有验收driver | 1 | 2 | 6 | 9 |
| 最终公开验收driver | 1 | 2 | 6 | 9 |

三阶段均无不明费用或无法归属调用。新338决定−321调用=17次执行前拒绝（3 context＋14团队预约）；全605决定−577调用=28次拒绝（4 context＋24团队预约）。这类预约不足不要求余额恰好为0，不能统称字面token耗尽。

| 阶段 | GPU worker秒 | GPU小时 | supervisor墙钟秒 |
|---|---:|---:|---:|
| 原4 | 2806.305519 | 0.779529 | 2875.421549 |
| 前接续3 | 2134.916388 | 0.593032 | 940.109572 |
| 本次9 | 4912.431448 | 1.364564 | 5118.702847 |
| 合计 | 9853.653355 | 2.737126 | 不作为连续墙钟相加 |

本次supervisor自北京时间2026-10-10 17:55:28.253运行至19:20:46.955。三个新resident均在物理GPU5按等待规则依次运行；原允许范围3/4/5/7、最大3驻留与56GiB空闲稳定60秒保持。本阶段没有三卡并行。相同worker名称跨阶段单独编号，原七费用只引用一次，不在复用时重复累加。worker横跨多个条件，GPU生命周期未按条件分摊；本详细JSON条件级GPU字段为null，真实费用以三阶段计时为准。旧自动报告中的0占位保留为原件，不解释为零GPU成本。

GPU worker占用包括加载、common恢复、CPU准备、模型生成、原验收和边界/轮询，不是纯kernel时间。resident/环境/测试/验收CPU子时间均嵌套，不再加到worker GPU时间。遥测仅审核原样本，不增加GPU诊断；artifact守卫包括历史roots，不冒称全是本轮增量。

新阶段的9槽合同与费用核对、3个worker的完整common3/3与源码冻结检查均通过，新增actor/critic/反向均0。761份运行资源样本均新鲜且通过，513次等待资源观测均明确限定物理3/4/5/7，无资源停止。样本中本进程GPU显存最高29700 MiB，GPU空闲最低51445 MiB，worker RSS最高4715667456字节；累计artifact最高68097374860字节（含历史），所在卷空闲最低388789915648字节。上述为保存样本范围内的检查，不声称无间断监测。

本次嵌套resident调用4336.186442秒；环境初态6次公开driver耗时0.688455秒，准备墙钟0.895659秒；43次run_tests公开driver为4.931103秒，1次成员自写脚本为0.114825秒；12次最终固定内容私有/公开验收合计1.375176秒。这些均包含在对应worker时间中。

新增九槽上限1152决定/attempt、4500000 token、288 tests；加旧七实际上界1419决定、1408attempt、7869138 token、314tests。所有单槽仍128决定/attempt、500000实际token、32tests；旧未用130862 token及本次各槽剩余均不转移，不按未花额度追加研究。CPU80控制和两次窄政策回执不计9B调用或GPU实验，旧资格程序响应不混入实际token。

## 8. 结论边界、原件与终态

本轮取得的是：在相同模型可见工作条件下，经过披露的批次停止政策修订，完成原预登记开发库存。局部context事件仍真实存在，R0和R1都按同一宿主规则处理；没有靠缩页、换提示、放大context或重采成功样本完成面板。

完整条件均值支持本批有限工作表现的描述，不证明模型普遍协作有效，不证明容量普遍可靠，也不是因果贡献信用或参数训练收益。新scope只是允许其它独立任务被观察，不能逆推出受阻成员若继续一定会提交或成功。

原首块测量修复、旧false、新true、前次真实停机均保留。原7成本与工作审阅复用保存证据，新9按闭合槽增量核对原输入/输出/计费/反馈；未重跑模型、tokenizer、业务测试或验收。审核helper及缓存永久留档，保留实际依赖和增量方法，不冒称无环境依赖的从零重建包。

| 证据 | SHA-256 |
|---|---|
| cost-review | `1ac9d021db05ebf3150277d41df58b71c62634aeda87d3b0a52b1b79317167a6` |
| new-nine-cost-review | `56a0c04a3b13b87f99132e2464ec97a4fe3180aee4e1af32ad1c2938fa12ea97` |
| context-review | `2015fbf1e4dddc6e85598945c06c0c9768bc8b6d89a421327923d22088ccb770` |
| provenance-review | `3c36e89461b90cd40b727ab03643365701e559dab95440df5c41fff565749b5a` |
| feedback-review | `3882ff3933eb5818d5fc185e2af2f9db5b58f5a9faf526eacfedd9a78e100465` |
| work-trace-review | `10e5c3f8bc45ab8b09614c9ce082be2e68810a16f1983d8d3f3d0808d4dbb6b6` |
| final_report_builder | `dae8c119824a16ddd2782e43a679767b0e55c4a7e91c75c828b9da7095eeaf2f` |
| hard-prefix-org44-r0-s1-SB | `e2983f78bb1c064a0b5585147766b2ca23ef397fe2f085f040e052f9260ed7bd` |
| hard-prefix-org44-r0-s1-ST | `afbb933bba750e3871a65372efb795095610ba900a5b11bc13c57f3d7b84f973` |
| original_four_plan | `fd34c20ee244a2031110a723f065e098461fa836298c50f0d211932faac09fb9` |
| first_continuation_plan | `3a5825cfae7f061a94457b5542772cd7b21e4e69b00e8a3278a69bbae0abb275` |
| completion_plan | `5e7cd76be0a1aa42b52123d819f8c139e65f96cd8d3206aa41fe8c022b8af5e0` |
| prior_seven_cost | `83a978a2d1f043a317fd97a84cd4cdbd9c9c5909435c5f421f290f1aad3b8c4e` |
| prior_seven_report | `28186942766a1a3d86e982bbfa7181ac4d085a10f6f610e48de51acd8355a518` |
| old_failed_gate | `79a4a02e0fec5694c42dd37c4c8deefd2b21c8b5963c85808c5e2926e5020431` |
| corrected_gate | `268862fd5b59bd705f00ce7b9f0a0d39007e80364210cffcd58608f0777bd68f` |
| prior_local_context_r2 | `78c66ad3d1800d2c888acade88f537e2febc47f8d569a1a2d40a85ea81f67ce6` |
| qualification | `bf8a2e64ce6bd8a8d760a5cfcabb297424bd4c864607c478f166cd5015c1552a` |
| admission | `cd0d8c51f7b232bc92a42c7ad8fee42825b0923b4424a84c7311e44393aa8708` |
| automatic_results | `7ec061554b07ce37df1addf7240cb08301e50568999aadd225ae9024a35adfc7` |
| finish | `7d39aac21bc1c7f776cd8f7d544a4520db90ea0951e1aec2ccb40dd87286f008` |
| audit | `12fa20b1a90bce0a6a1bfe32c1dc19df10525e7a60f59e470ef949423566ed1a` |

本次模型阶段已结束，无自动后继。审计中的S/F2/O3新24条、长context候选、原26次Contribution试训、3次正式更新、48条TextFSM确认及梯度缓存生产均未启动，旧暂停继续保持。

[机器详细记录](software-organization-v044-completion-final.json) · [自动原16槽结果](software-organization-v044-completion.json) · [冻结协议](software-organization-v044-completion-protocol.md) · [准备记录](software-organization-v044-completion-preparation.md) · [启动记录](software-organization-v044-completion-launch.md) · [此前7槽报告](software-organization-v044-resume-final.md) · [本轮审计](../reference/audit-v044-resume-next-completion.md)
