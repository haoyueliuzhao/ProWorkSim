# v0.33 r1 记录修复、离线恢复与接续启动记录

**修复已完成，原四条记录恢复可信，剩余十二条已交给监督队列。** 队列于北京时间 **2026-10-05 15:37:52** 启动。此快照时GPU均未满足原空闲条件，两模型均为`not_started`，没有新增模型调用；监督与自动发布进程正常。实际后续状态以[接续运行报告](software-paired-o1-v033-recovery.md)及其[机器汇总](software-paired-o1-v033-recovery.json)为准。本启动快照不回改。

冻结执行提交：`ab6cd083beb33b4ffbccf48546d9394a34175ed3`，已推送用户账户下的本仓库。完整修订范围与约束见[接续协议](software-paired-o1-v033-recovery-protocol.md)。

## 1. 修复的是记录解释

原v0.33在两个团队槽结束时正常拒绝了超出剩余团队token预算的下一次调用。四个拒绝都发生在模型生成前，但导出器只识别旧`model_budget_stop`，未识别新的`model_boundary_error/team_budget_exhausted`，将本来不存在的response误判为记录缺失。因此原队列在两模型各执行两槽后停止，并没有执行完十六槽。

新增严格证明同时核对实际call/member/opportunity/window/actor/config、封印准备记录、边界账和最终账、原始收费响应与预算算术，以及没有任何阶段的attempt、response、世界／harness动作、收费或占用。仅对可证的未生成调用取消“必须有模型输出”的要求；不制造token，不修正模型输出，也不绕过真实记录、权限或身份错误。

收尾审查还发现同类可达情况：个人预算检查早于团队预约，个人拒绝会留下`decision_consumed`，随后另一成员可能收到团队拒绝。已补上严格的混合账本识别，只允许有原唯一预算停止、身份绑定、真实个人收费总额和精确超限算术的未生成行。原9B S实际证据为487601已用token，加13931预约超过500000；任意未完成或已开始调用仍不能获得豁免。

## 2. 原四条经历恢复结果

| 模型 | 条件 | 原最终记录状态 | 派生record | 完整R | 内容正确 | 规定过程 | 固定提交 |
|---|---|---|---|---:|---|---|---|
| 9B | ledger-S／seed1 | closed | true | 0 | 未知 | 未知 | 无 |
| 9B | ledger-T／seed1 | execution_unknown | true | 0 | false | false | 有 |
| Devstral | ledger-S／seed1 | closed | true | 0 | false | true | 有 |
| Devstral | ledger-T／seed1 | execution_unknown | true | 0 | 未知 | 未知 | 无 |

四个R来自原来已经执行过的独立验收。此次只重新解释记录，不重新运行验收或修改交付代码。两份S entry的数据完全相同；两份T entry只允许工作有效性中的record解释变化，原事件、token、reward及permission／basis／delivery维度保持。原异常progress、worker状态和[原停止报告](software-paired-o1-v033.md)均未覆盖。记录分类确实得到修正，业务验收没有重判。

原四槽共138次真实attempt、1665658个实际调用token，零参数更新。离线恢复新增模型调用、episode、验收执行、optimizer步骤均为0。原约2.1GB归档的前后全树hash一致：`66c2684e249e6aa0a7b8db07887d45c0f875071c68488620f85175619736aa2a`。派生恢复summary：`/data1/zhuxinrui/projects/ProWorkSim/runs/v033r1-record-recovery/summary.json`，SHA256 `ce7b161806dec3e0d1717ab314ce9985ac0285fb443e106707443db39d25e153`。

这两个ledger配对现在都可描述为S/T均未完整通过；其余十二条尚未开始，不能将局部结果扩大成全部团队失败或模型排名。当前仍未形成可训练配置支持或分配收益证据。

## 3. 必要控制及范围

| 检查 | 结果 | 实际证明范围 |
|---|---|---|
| 生成前拒绝解释 | 初始24项通过；混合账本补修后新增3项通过 | 完整边界／最终账证明、真实上下文溢出、错误身份／封印／使用量／已有尝试和响应等反控制；真实四个未生成调用及其他动作内容对照 |
| 接续采集与恢复限制 | 4项通过，19.27秒 | 真实SDK在CPU使用9条明确合成响应执行后六槽，前两槽无episode和采样；四对初始信息证明保留；非法前缀拒绝 |
| 监督与报告 | 12项通过 | 同common恢复、只采六槽、两worker失败隔离、技术未知分支、原验收不可替换、固定两报告发布路径 |
| 原件离线恢复 | 四槽全部通过 | 原世界／调用／验收／guard／common和最终账绑定，旧树未变；模型与验收执行均0 |
| 实际接续绑定 | 通过 | 原四个派生已知结果及十二个仅预建槽全部接受，未开始槽目录清单和hash冻结 |
| 静态检查 | 全项目Ruff通过 | `.venv/bin/python -m ruff check src tests scripts`；未重复全仓pytest |

分阶段检查和局部追加不合并成一个独立测试总数。完整命令、returncode、stdout、文件hash及引用见[启动机器记录](software-paired-o1-v033-recovery-launch.json)和`runs/v033r1-controls/`。

一次早期CPU派生导出在收尾修订协调中被中断，退出码130，未形成summary或通过结论。未完成文件保留在`runs/v033r1-record-recovery-interrupted`，中断记录也保留；其开始前记录的旧树hash与最终正式恢复的旧树hash相同。最终解释器冻结后完成了正式导出。该中断没有增加模型调用、业务验收或新episode，不能冒充成功控制，也没有删除其历史。

冻结资格不仅绑定通过回执，也将原冻结版本全部生产Python文件逐一比较：仅`member_views.py`和`software_runtime_v033.py`改变，其他 **194** 个文件字节一致。后者只允许精确跳过已执行前缀及声明实际六槽。世界、工具、提示、native处理、上下文选择、预算、采样及数值学习路径保持。继承原数值／16K／更新／恢复证据，不新增三题资格或模型诊断更新。

冻结资格SHA256：`d5c42b1b36dace770de0474a01974692eeaf09a462abc5658be2ff2789e0b926`。离线导出诚实记录其执行时的主工作树身份和解释器文件hash；后续提交只将同样的已核验文件冻结，不声称重新做过模型实验。

## 4. 实际接续部署

- 源码工作树：`/data1/zhuxinrui/projects/ProWorkSim/runs/v033r1-frozen-source`。
- 计划：`/data1/zhuxinrui/projects/ProWorkSim/runs/v033r1-plan.json`，SHA256 `471b8054064373f33657f0a12bd5cfff5e785a352d72a9eb6f6ad5c22ba2ea2d`。
- 新原件目录：`/data1/zhuxinrui/projects/ProWorkSim/runs/software-paired-o1-v033-recovery`。
- finish PID `2430`，启动ticks `361026736`；supervisor PID `2500`。启动日志：`/data1/zhuxinrui/projects/ProWorkSim/runs/software-paired-o1-v033-recovery-finish.log`。
- 实际入口：`python -m scripts.continue_paired_o1_v033r1 finish --plan runs/v033r1-plan.json --run-root runs/software-paired-o1-v033-recovery --report-repo <主仓库> --publish`；实际完整绝对路径与环境身份见机器记录。

每模型跳过原ledger seed1的S/T，只按原顺序执行余下六槽。两个owner最多并行，分别恢复9B原3／3、Devstral原0／0 common，不更新参数。每槽仍为团队128决定、128 attempt、500000 token和32次实际测试；不按人数翻倍，也不为修复扩大额度。

启动时所有GPU均忙，尚未分配任何新worker或预约显存。队列保持原空闲容量稳定60秒门、单加载／单episode／边界及内存／存储保护，累计期限继续为None。监督已确认存活且状态新鲜；本次没有终止其他作业。

## 5. 汇总、成本与下一阶段

新报告将四条派生旧记录与十二条新经历合并为原16个逻辑槽，每行保留来源引用。各侧已知S/T值独立显示，只有双方均可信才计算T-S；未开始和技术未知不补零。报告不把完整模型请求和账本重复嵌入Git，原件仍可按hash追溯。

原worker成本为2303.728234 GPU秒，接续在本快照为0；队列等待不算GPU占用。报告逐卡对原、新worker实际区间取并集，分别列原成本、新成本、交叠与正在运行时间。

接续结束后自动生成新报告、提交并推送。若有模型全部八槽可信、完整恢复common且T至少一槽完整通过，按原事前规则确定新训练来源的局部支持采集候选；若仍有技术未知，不套用“全T业务为零”的任务调整分支。完整全T已知为零时才转向领域负担更小的新根目标。旧选型与36条历史开发结果不改，当前开发记录不进入训练，B/G/I仍需新的实际支持和公平试训冻结。
