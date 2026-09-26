# ProWorkSim

**面向 ID-VTDO 研究的信息不对称专业工作世界。** ProWorkSim 提供持续世界、局部工具与可核验联合经历；当前研究目标是利用信息依赖结构配置各成员的经验，检验更新后团队的工作能力。世界运行、参数更新和学习收益分别验证。

[研究目标与理论设计 V1](docs/research/id-vtdo.md)是研究入口；当前按[v0.14 计划](docs/learning-v014-plan.md)研究实际工作信号、固定预算在线学习与条件迁移，ID-VTDO 支持随在线窗口诊断。基础 RL 不要求先取得完整成功或多类方法支持，不使用 SFT 主路线；贡献调权与强基线比较另按实际支持条件开展。

WorldCore管理权限、版本、采用、工作义务和问题处理；工作人员决定业务动作；场景控制器执行预声明事件。机构接受、内容正确、未知、服务故障和训练奖励分别记录。

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

Git保存协议与紧凑证据，完整世界、实际模型请求/响应和检查点保留在服务器runs。仍是有限模板、单一来源家族、单写者及完整行动边界；历史144次主批及正式ID-VTDO学习收益对照尚未执行。当前在线结果以v0.13报告为准。

## 历史与语义

核心世界格式沿用world-core-v0.9，模块分别版本化；旧世界不静默迁移。原经营单模板仍保留自身0.5格式入口。以新版实现为准，旧冻结结果仅作各自范围的历史证据。

- [核心语义](CORE_SEMANTICS.md)、[行动合同](ACTION_CONTRACTS.md)、[状态归属](STATE_OWNERSHIP.md)
- [当前ID-VTDO审计](docs/reference/id-vtdo-audit-v011.md)、[v0.11依据审计](docs/reference/model-executable-audit.md)
- [v0.10模块实验](docs/experiments/platform-modules-v010.md)
- [v0.9双模板实验](docs/experiments/template-expansion-v09.md)
- [v0.8持续工作](docs/continuous-work-v08.md)、[v0.7工作能力](docs/work-capabilities-v07.md)
- [v0.6多项目世界](docs/world-core-v06.md)、[v0.5状态一致性](docs/state-consistency-v05.md)
- [原始设计](docs/reference/design-v0.1.md)
