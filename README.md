# ProWorkSim

## v0.25 当前支持已采集，基础更新因监控查询超时中断

[最新停止核对](docs/experiments/composition-v025-stop-note.md)：9月30日01:21，单次GPU资源查询超时触发监控终止；支持16/16，最后反向266/283，本轮参数更新0步，确认及后继未启动。累计13.726393 GPU小时，当前模型进程已结束；不是新增18小时预算耗尽。原始失败与旧observer超时标签保留，实际首触发另据guard和资源记录说明。

[本轮方案](docs/domain-collaboration-v025-plan.md)固定v0.24 MC完整终态与terminal MC基础配方，在新A/B情境各采8条当前策略经历；首次将完整工作有效性、真实方法支持和成员条件化q/b接入actor更新。若A成员存在两类各至少两条的支持，按固定顺序选择一个块，做同起点基础/小扰动试训、独立开发选择和受约束正式配置；确认材料单独保留，后继只交互不增加更新。

[程序准入](docs/experiments/retail-work-v025-qualification.md)为分项通过：A两路线、B自检与其他14材料获资格；B反馈修复仍触及原上下文门，故本轮**只允许A成员配置，B保持基础权重**。没有继续放宽harness、角色或上下文。[完整工作与支持控制](docs/experiments/work-support-v025-controls.md)、[真实tiny梯度与16槽集成](docs/experiments/composition-training-v025-controls.md)、[条件执行及报告控制](docs/experiments/composition-v025-execution-controls.md)已完成，不能视为真实模型支持或算法收益。

原计划上限58 GPU小时、最多56新episode和三次独立16槽更新。实际16条支持采集后无可配置块，按规则仅基础更新、12确认与2后继，最多30新episode；不补采凑齐。9月29日用户授权[运行中预算延长](docs/experiments/composition-v025-budget-extension.md)：同一模型更新上限11→18小时、阶段12→20小时，全计划有效上限66 GPU小时、当前无支持分支31.5 GPU小时。预算接管曾保留同一模型持续计算，最终在资源查询失败门停止，原计划与数值门保持。北京时间9月29日11:38已在GPU2启动真实支持采集，执行提交`e374324`；[启动记录](docs/experiments/composition-pilot-v025-launch.md)保留当时状态。没有当前可配置双类支持或配置收益结论；[自动终态报告](docs/experiments/composition-pilot-v025.md)已归档，实验未完整完成。


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


**面向 ID-VTDO 研究的信息不对称专业工作世界。** ProWorkSim 提供持续世界、局部工具与可核验联合经历；当前研究目标是利用信息依赖结构配置各成员的经验，检验更新后团队的工作能力。世界运行、参数更新和学习收益分别验证。

[研究目标与理论设计 V1](docs/research/id-vtdo.md)是研究入口；[v0.19 吞吐计划](docs/throughput-v019-plan.md)的优化实现和单模型控制已保留，旧高资源后继已按用户要求暂停，本轮仅按v0.22有限方案恢复9B；原H1已在冻结协议下完成，同时保留[v0.15 原线](docs/learning-v015-plan.md)的独立终态。新主 pilot 明确为 Q=B 基础学习；另外规划同策略密度诊断，不自动启动贡献调权。不使用 SFT 主路线；基础 RL 不要求先取得完整成功或多类方法支持。

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
