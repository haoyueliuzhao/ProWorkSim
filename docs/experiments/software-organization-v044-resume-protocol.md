# v0.44 原十二槽接续协议

用户在提交 v0.44 审计后明确要求“参照审计修订并开展后续实验”，构成本次修订与原库存续跑授权。审计自身不是授权；本次用户指令是授权来源。本轮是原 Γ 下的接续，不新建 org45，不重跑首块，不续开已经退休的成员会话。

## 原结果保留与修订对象

原执行源为 `e8aa60bd1a427944d8503fb02b30f6379ebd5889`，原目录 `runs/software-organization-v044`。保留该目录全部原件、`gate=false`、停止事实及 PT/SB/ST/PB 的 R=1/0/0/0。原四槽已闭合，共150决定、144实际调用、1892846实际token、14次run_tests。六次未生成是团队余额无法覆盖输入加最大输出预约，不能写成context硬拒绝或字面花尽500000。

仅新增只读 `measure_organization_feedback_v044r1.py`，对完整原四槽重新物化，而不是手改旧JSON。直接自退役须由同一成员、episode/window、真实输出与计费调用，唯一 proposal→policy→committed→action_link→feedback，以及世界action/event/registry、退役终态与无后继生成共同证明。native `retire_member` 只有 `reason` 参数，目标由实际actor确定，不发明target参数。experience和world序号分别在各自日志内部使用，不跨日志比较大小。

证明成功归为 `voluntary_self_retirement`，只说明不存在应有的下一次生成机会。它不表示呈现、理解、任务完成或提交成功。反馈分母仍144，实际首次后续呈现仍136，原8条无实际后续仍保留。R0且未完成任务的真实自退役适用同一规则；管理员/外部、未提交、错身份/窗口、退休后生成或记录矛盾不能吸收为正常结束。

新回执在 `runs/v044-resume-controls/first-block-review`，旧feedback-loop与旧gate均不覆盖。新门消费四份新测量，不按R、消息、招募、页数、是否全读选择。若原件完备而新测量仍不能归因，状态为测量未决，暂停未开槽；不改称模型失败。

## 来源与准入

原源码、旧96项资格源清单、原112历史形状及有限路线的已存资格按原引用和实际依赖逐字节复用，不重做tokenizer、分页路线、资格模型题、业务测试或固定树验收。原执行提交与新测量/宿主入口提交分别绑定；新`src`树必须仍为 `47eb019ff4cc6170111cec16ab4c538c57719ad23d8774a5fd0c82dbc3caba30`。原src/scripts/tests/examples与pyproject均与旧执行提交比较，新代码只允许明确登记的6个测量/准入/入口及测试文件。

准入对照不可变发布提交 `6f37d0c23820e08a3ed2ce7ae40df0b6bba4b761` 的旧报告、监督状态和旧门，核原4槽唯一闭合、common/actor/源码守卫及其原成本，核另3块原目录完全不存在、supervisor无attempt/PID/命令/启动字段、progress和episodes只有首4槽。不能以“缺summary”推断未开始。

新入口只可写新目录 `runs/software-organization-v044-resume`，每块只准唯一 `block/actual` 输出目录且已存在即拒绝。旧根目录不得容纳新计划或新输出。冻结工作树运行，报告提交不改变实际执行源身份。新控制只做退休证据、准入、库存/合并和必要边界测试及全局Ruff，不重跑旧容量资格。

## 原库存、运行与预算

| 块 | 任务 | seed | 顺序 | 先手 | 诊断A归属 |
|---|---|---:|---|---|---|
| 保留 block-r1-s0 | catalog | 202610100441 | PT→SB→ST→PB | member_001 | member_001 |
| 接续 block-r0-s0 | views | 202610100441 | ST→PB→PT→SB | member_002 | member_002 |
| 接续 block-r0-s1 | views | 202610100442 | PB→PT→SB→ST | member_001 | member_002 |
| 接续 block-r1-s1 | catalog | 202610100442 | SB→ST→PB→PT | member_002 | member_001 |

保持原`org44-r*-s*-条件`身份、原9B完整common3/3、工具/提示/分页/反馈生命周期、初始2人、活动≤4/累计≤6、16K/2048、每槽128决定/attempt、500000实际token、32次run_tests与原固定内容验收。每槽只恢复原共同模型状态和原seed，不复用已完成模型轨迹。新审计、版本说明或修订文字不加入模型输入。

新增最多12槽、1536决定、1536attempt、6000000实际token、384次run_tests。旧未用107154token不转移，原四槽实际量加新增上限为1686决定、1680attempt、7892846token、398测试。预算是单槽独立原限额，上述合计不是扩大单槽上限。

最多3个新resident worker并行，仅物理GPU3/4/5/7，块内四槽依原顺序，成员调用仍串行。每卡启动需56GiB空闲稳定60秒，保留每worker显存/RSS、卷余量、单加载/episode/边界时间与遥测守卫。不恢复已取消的累积GPU小时或总wall cap，容量不足等待。其它GPU不启动本项目任务。

新四槽首块门不再重复。每新槽闭合后做相同只读机械检查；正常R0、自退役、正常预算耗止不阻断。若发现真实context/权限/来源/记录问题，或测量未决，记独立原因并暂停所有尚未开始的槽；已在途episode允许结束当前槽后停，不再开下一槽。资源/关键执行故障仍按原守卫停止。无热改、重采、成功后追加或自动后继。

## 合并与解释

只合并原4+原12=唯一16，不生成20槽。原4成本计一次，另列新增12、总16和本轮CPU修订成本；环境与测试CPU时间属于嵌套成本，不加到GPU worker占用。模型token只来自实际调用账单，程序响应、预约或未调用预算不计实际token。

SB/shared-base、ST/shared-team、PB/split-base、PT/split-team每条件原4槽。按root/seed四条件块计算：信息效应=[(PB+PT)−(SB+ST)]/2，说明效应=[(ST+PT)−(SB+PB)]/2，交互=PT−PB−ST+SB；再按原4块等权平均。任一必需R未知则对应主比较null，不补零、不以部分成功块替代。完整块描述可另列。

正式R、提交与固定验收、反馈呈现、工作链分别报告。没有证实跨成员使用链不能用消息/任务ID/相似代码代替。四块差异只是这两开发root与两seed的有限比较，不是总体协作收益或学习增益。旧26试训、3正式更新、48确认、缓存生产继续暂停；新增actor/critic/反向为0。

[审计原文](../reference/audit-v044-resume.md)；[原首块报告](software-organization-v044-final.md)。
