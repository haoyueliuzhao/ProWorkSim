# ProWorkSim

**面向智能体学习的专业工作世界模拟与任务流合成。** v0.10 将现有财务资料核对与有限报告审阅接入统一工作人员运行、声明场景、实际经历与分项评价接口。“核对—发布—报告—审阅”链可以从同一规格构建并持续运行。

世界核心负责权限、版本、工作义务与问题处理关系；工作人员策略决定业务动作；场景控制器执行预声明的外部事件。机构接受、内容正确、来源忠实性、独立目标和未评项分别记录。

## 安装与运行

需要 Python 3.11+，使用新世界目录及新输出文件：

```bash
python -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'

.venv/bin/proworksim scenario-build runs/platform-demo --spec examples/scenarios-v10/chain-accepted.json
.venv/bin/proworksim staff-run runs/platform-demo --output runs/platform-demo-run.json
.venv/bin/proworksim episode-assess runs/platform-demo --experience runs/platform-demo-run.json --output runs/platform-demo-assessment.json
```

[八份场景规格](examples/scenarios-v10/README.md)包括独立核对、独立报告、三种更正时点的跨模板链、真实待审起点和显示名表面变体。场景只使用现有两个模板。缺资料、无效引用或不可达起点会返回明确诊断，实际已发生的构造与前缀保留。

运行输出包含实际经历及检查点。若要在完整行动之后截断、继续，可在首次staff-run指定`--max-opportunities 8`，再次运行时传`--checkpoint 上次输出文件`并指定新的`--output`。继续要求同实例、同分支、同规格及最新完整检查点；预算截断记录保留。输出文件放在世界目录外。

默认评价没有独立业务目标或过程要求时，相应项目为unassessed。可用`episode-assess --spec 文件.json`显式提供work_ids、independent_targets、process_requirements；接口不生成总体成功布尔值。

## 本版模块

- **StaffRuntime**：每个角色保留独立公开上下文、记忆和上次实际返回；透明轮转行动机会，每次最多调用一个工具。核对、写作、审阅与局部修复均由可替换策略决定。
- **Scenario**：声明项目、角色、共享、资料到达时点、实际执行前缀和运行边界；部署和事件通过真实工具执行。控制器不根据独立评分临时补料或改正文。
- **ExperienceRecorder**：保存实际观察、决定、动作和返回；背景部署、真实前缀、控制器干预与环境事件分别记录。
- **只读评价**：区分pass、structure_failure、content_failure、source_unavailable、unassessed、evaluator_error；episode另列制度进度、内容、独立目标、过程约束、不完备与运行问题。

声明范围到达可返回boundary_reached，其他项目保持开放；completed还要求制度接受、公开交付中的发布义务兑现且没有待处理环境事件。工作结束、机构批准和内容正确有不同判据。

[实现设计](docs/platform-modules-v010.md)、[两阶段计划](docs/platform-modules-v010-plan.md)、[核心语义](CORE_SEMANTICS.md)、[行动合同](ACTION_CONTRACTS.md)与[状态归属](STATE_OWNERSHIP.md)说明具体接口。既有模板业务与共同问题关系见[v0.9设计](docs/template-expansion-v09.md)及[旧公开端口示例](examples/templates-v09/README.md)。

## 正式实验

最终实现冻结`55277d59ce0a17eff9555478f6b9fb43bd921394`，**573项测试通过，Ruff通过**。阶段A冻结`0b53a24`的R0 98/98、R1 40/40及550项测试也独立保留。两阶段分母不相加，后续新增检查不倒填旧结果。

| 组别 | 最终结果 |
| --- | --- |
| R0 评价边界 | 14条件，98/98；真实合法提交的结构错、业务错、来源缺口及评价器故障分开 |
| R1/R2 工作人员协作 | 8案例，93/93；正确首交、逐项修复、反驳、等待、非法操作、私有性与晚到历史 |
| R3 声明场景 | 8场景，85/85；相同起点重复性、单维结构变化、真实前缀及表面变体 |
| R4 分项评价 | 4条件，69/69；上游错而下游忠实、metadata对而正文错、合理未知、评价器故障 |
| 实际CLI链 | 8/8；声明部署、截断、续行、保留经历与只读评价 |

通过表示符合预声明后果，也包括应拒绝、应未评或应内容失败的情况。R4四组均到达声明范围边界，无关项目仍开放。详细[实验报告](docs/experiments/platform-modules-v010.md)保留源码身份、原始反例、开发失败、测量修订与证据引用。

```bash
.venv/bin/python scripts/evaluation_boundary_experiment.py --output runs/r0-new
.venv/bin/python scripts/staff_runtime_experiment.py --output runs/r12-new
.venv/bin/python scripts/scenario_experiment.py --output runs/r3-new
.venv/bin/python scripts/episode_assessment_experiment.py --output runs/r4-new
.venv/bin/python scripts/platform_cli_experiment.py --output runs/cli-new
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check src tests scripts
```

Git保存协议和紧凑证据，完整世界、逐次轨迹和检查点保留在服务器runs目录。本轮未使用模型API/GPU或训练；规则策略结果不代表模型能力。后续固定模型角色实验应另行冻结预算，真实保留失败。

## 范围与历史

核对模板保留冲突、不可比、缺失和歧义；报告评价针对公开有限句式中的数字、期间、趋势及引用，开放论证与专业充分性未评。可信Python策略接口不是恶意代码沙箱。当前单写者、完整行动返回后的继续，不证明任意并发、断电或策略崩溃恢复。

软件版本0.10.0，核心世界格式仍为world-core-v0.9；不静默迁移旧v0.6–v0.8世界。最终工作人员检查点为staff-runtime-v0.10.1，以实例和分支身份阻止同名世界间误用记忆，不兼容阶段A旧检查点。

原经营单模板入口保留自身0.5格式：

```bash
.venv/bin/proworksim build runs/operating-demo --seed 17 --delivery continuous --information clarification
.venv/bin/proworksim run runs/operating-demo --provider baseline --inject-stale-memo
.venv/bin/proworksim evaluate runs/operating-demo
```

- [本轮依据审计](docs/reference/platform-modules-audit.md)
- [v0.9双模板实验](docs/experiments/template-expansion-v09.md)
- [v0.8持续工作](docs/continuous-work-v08.md)及[实验报告](docs/experiments/continuous-work-v08.md)
- [v0.7工作能力](docs/work-capabilities-v07.md)及[历史报告](docs/experiments/work-capabilities-v07.md)
- [v0.6多项目世界](docs/world-core-v06.md)、[v0.5状态一致性](docs/state-consistency-v05.md)
- [v0.4内核迁移](docs/semantics-kernel-v04.md)、[原始设计](docs/reference/design-v0.1.md)
