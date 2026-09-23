# ProWorkSim

**面向智能体学习的专业工作世界模拟与任务流合成。** v0.9 在同一 WorldCore 上实现两种不同工作结构：财务资料的集合核对，以及针对实际报告的审阅与局部修复；两者可以沿真实发布和声明的维护规则继续协作。

世界核心负责身份、作用域、版本、义务、审阅关系及提交恢复。领域合同判断有限内容；工作人员实际读取和修改文件。**机构接受、内容正确、来源忠实性和总体目标分别记录。**

## 安装和两个模板示例

需要 Python 3.11+：

```bash
python -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'

.venv/bin/proworksim world-create runs/templates-v09-demo/world --spec examples/templates-v09/world.json
.venv/bin/proworksim project-load runs/templates-v09-demo/world examples/templates-v09/reconciliation.json --actor operator
.venv/bin/proworksim project-load runs/templates-v09-demo/world examples/templates-v09/report.json --actor operator
.venv/bin/python examples/templates-v09/run_workers.py runs/templates-v09-demo/world \
  --output runs/templates-v09-demo/public-transcript.json
```

目录须新建。[示例说明](examples/templates-v09/README.md)提供独立模板运行、公开端口配置和Python调用。策略实现位于`proworksim.workers`，只接收`tools/observe/call`；实际观察和返回随运行保存。该示例演示两个独立项目，跨模板发布联动另由下面X3实验配置。

## 本版能力与边界

- **财务资料核对**：覆盖两表记录并集，检查单位、期间、定义和币种适用性；明确保留冲突、不可比、缺失及歧义。公开路线支持资料不可得后的继续。
- **报告审阅**：针对真实固定提交读取正文、提出有位置和证据的问题；责任者可局部修复或有据反驳。修错沿同一工作/需求重交，不必每次创建新需求。
- **共同问题关系**：`inspect_submission / raise_issue / respond_issue / decide_issue`复用同一版本与提交体系；文件变化不会自动关闭问题，一项决定不能关闭其他问题，晚到旧意见保留历史。
- **跨模板维护**：A更正一行并发布，A核对与B报告沿各自规则形成后继；B公开发现新义务、采用并继续审阅。固定历史工作及无关行/章节保持。
- **失败归因**：工具拒绝的实际返回与策略错误、业务约束、能力缺口、实现异常分别记录；未明确分类的错误保持未知。

新领域合同使用JSON；既有受限XLSX能力保留。报告正文只评价公开声明的有限数字、期间、趋势及引用句式，开放论证和专业充分性未评。合成核对不等于真实财务审计；程序策略不代表通用模型规划能力。

[设计说明](docs/template-expansion-v09.md)、[实施计划](docs/template-expansion-v09-plan.md)、[核心语义](CORE_SEMANTICS.md)、[行动合同](ACTION_CONTRACTS.md)与[状态归属](STATE_OWNERSHIP.md)说明具体分层和边界。

## 正式实验

最终冻结代码为`07bd9fd`，**498项测试通过，Ruff通过**。首个冻结`37a84ff`的494项及实验结果也保留；后来发现非dict参数错误报告回归，修复、补测试后重新冻结验证，没有覆盖原证据。

| 组别 | 最终结果 |
| --- | --- |
| X1/X2 财务核对 | 6场景，58/58；另1/1合法组织比较 |
| X1/X2 报告审阅 | 8分支，70/70；另1/1合法替代比较 |
| X3 同世界联动 | 3条件，72/72；区分上游质量、下游忠实性、正文表达和总体目标 |
| X4 共同问题关系 | 两模板28/28；一个真实进程中断切点10/10 |
| 拒绝归因 | 六类真实拒绝，24/24 |
| 相关旧机制回归 | P2 180/180；明确更新拒绝口径后的P4 67/67；P0/P1/P3等纳入完整测试 |

通过表示符合预声明期望，也包括应拒绝、应保持未知或应内容失败的情境。各分母不合并为专业能力分数。[详细报告](docs/experiments/template-expansion-v09.md)保留完整审计对应、失败、测量修订、冻结身份和证据索引。

```bash
.venv/bin/python scripts/reconciliation_experiment.py --output runs/reconcile-new --workers 3
.venv/bin/python scripts/research_review_experiment.py --output runs/report-new --workers 3
.venv/bin/python scripts/cross_template_experiment.py --output runs/cross-new --workers 3
.venv/bin/python scripts/issue_relations_experiment.py --output runs/issues-new
.venv/bin/python scripts/tool_rejection_experiment.py --output runs/rejections-new
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check src tests scripts examples/templates-v09
```

Git保存协议与精简证据，完整世界、轨迹和检查点保留在服务器`runs/`。本轮没有模型API调用、GPU使用、参数训练或真实数据采集；后续真实材料用于校准，未观察历史不补造。

## 范围与历史

当前新世界格式为`world-core-v0.9`，不静默迁移旧v0.6–v0.8世界。单写者及指定提交切点的通过不意味着任意并发、断电或分布式一致性已验证。

原经营单模板入口仍可运行，使用自身0.5格式：

```bash
.venv/bin/proworksim build runs/operating-demo --seed 17 --delivery continuous --information clarification
.venv/bin/proworksim run runs/operating-demo --provider baseline --inject-stale-memo
.venv/bin/proworksim evaluate runs/operating-demo
```

- [本轮审计](docs/reference/template-expansion-audit.md)
- [v0.8持续工作](docs/continuous-work-v08.md)及[实验报告](docs/experiments/continuous-work-v08.md)
- [v0.7工作能力](docs/work-capabilities-v07.md)及[历史报告](docs/experiments/work-capabilities-v07.md)
- [v0.6多项目世界](docs/world-core-v06.md)、[v0.5状态一致性](docs/state-consistency-v05.md)
- [v0.4内核迁移](docs/semantics-kernel-v04.md)、[原始设计](docs/reference/design-v0.1.md)
