# ProWorkSim

**面向智能体学习的专业工作世界模拟与任务流合成。** 当前 v0.5 的主线是内核状态一致性与有界恢复：明确行动阶段差分，从基础事实重建条件与当前工作视图，并实现单世界、单写者下的命令／事件提交和重试。经营分析仍是主模板；一个极小文稿模板用于检验共同规则的复用边界。

支持三个交付粒度，以及可配置的工作结构与布局：

| 模式 | 业务委托 | 最终交付 |
| --- | --- | --- |
| `short` | 组合已有模型股价与指定披露 EPS | 带来源的 P/E 数值回复 |
| `file` | 更新假设、重算模型、构建 2×2 敏感性分析 | 实际修改后的 XLSX |
| `continuous` | 更新模型与备忘录、接受审阅、处理后续披露和假设变化 | 多个绑定版本的交付物及连续工作记录 |

所有业务材料均为独立合成数据。项目没有使用 APEX 评测题、参考答案或受限数据训练模型。

## 安装和运行

需要 Python 3.11+。推荐项目独立虚拟环境：

```bash
python -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'

# 编译一个需要实时澄清的连续项目
.venv/bin/proworksim build runs/demo --seed 17 --delivery continuous --information clarification

# 通过公开工具运行规则基线，故意漏改一次备忘录以验证真实审阅返工
.venv/bin/proworksim run runs/demo --provider baseline --inject-stale-memo
.venv/bin/proworksim evaluate runs/demo
.venv/bin/proworksim export runs/demo runs/demo-export
```

基线只用于验证任务可解，不是模型能力实验。存在历史失败提交时，`evaluate` 会完整展示失败记录；退出码按当前适用工作项的最后提交判定。`blocked_unavailable` 是合法停止且 `complete=false`，不计为业务完成。

真实模型运行先在项目 `.env` 配置 `DEEPSEEK_API_KEY`（可参考 `.env.example`，已有 `.env` 不要覆盖）：

```bash
.venv/bin/proworksim build runs/deepseek --seed 101 --delivery continuous --information clarification
.venv/bin/proworksim run runs/deepseek --provider deepseek --max-turns 80
.venv/bin/proworksim evaluate runs/deepseek
.venv/bin/proworksim export runs/deepseek runs/deepseek-export
```

默认模型为 `deepseek-flash`，可通过 `--model` 或 `DEEPSEEK_MODEL` 修改。支持 `--thinking`、`--env-file`。网络失败后可对同一路径重新运行；已记录的工具调用使用幂等键恢复。模型返回普通文字不会自动变成文件交付或批准。

## 快照、观察与实验

```bash
.venv/bin/proworksim inspect runs/demo
.venv/bin/proworksim act runs/demo list_files
.venv/bin/proworksim snapshot runs/demo runs/demo-snapshot
.venv/bin/proworksim restore runs/demo-snapshot runs/demo-branch
.venv/bin/proworksim replay runs/demo --output runs/demo-recording.json

.venv/bin/proworksim experiment runs/matrix --seeds 11 29 --workers 4
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check src tests
```

快照和导出目录必须新建，且位于被操作世界之外。`replay` 导出实际已记录的输入、输出与工具结果；恢复状态使用 `restore`，默认分配新分支身份。

课程模块只读取开发集的有效诊断，生成结构配额并可编译新的训练世界：

```bash
.venv/bin/proworksim curriculum runs/demo --total 12 --output runs/quotas.json \
  --generate runs/next-training-worlds --seed-start 1000 --workers 4
```

若输入世界不属于开发集，其结果会被明确排除，配额使用均衡先验。当前“压力池”是对既有结构的重点采样标签，不自动注入矛盾或沟通噪声。

## 工作世界语义内核

先定义 [基本语义](CORE_SEMANTICS.md)、[状态归属](STATE_OWNERSHIP.md) 与 [行动合同](ACTION_CONTRACTS.md)，再将共用规则提取到 `core/`，将经营假设、阶段规则与组织配置分别放入领域和制度层。已有文件工具继续使用。当前运行器仅接受 schema 0.5；历史世界使用对应的冻结版本，本轮未提供旧历史的隐式迁移。

- 正式确认由配置权力产生；角色名称本身没有批准权。
- 可访问、已观察、声明采用和验证支持分别记录。
- 适用性针对凭据版本和具体工作查询；同一产物对不同工作可能有不同结论。
- 回复送达不等于条件满足；重复送达、旧回复、当前不可得和后续恢复具有明确后果。
- 提交、撤回、批准及需求替代共用状态规则；有权角色可批准错误产物，独立评价仍可拒绝。
- 行动分别记录 Apply、Derive 和净变化；基础区域／投影区域分类另列，失败阶段不伪报为空差分。
- 条件和当前工作视图从事实重建；删除或破坏指定缓存后，不改变历史决定、原始回复和文件。
- 命令与环境事件各自原子提交；同一身份重试返回已提交结果，负载变化明确冲突，恢复隔离未提交文件。
- 历史文件、提交和批准保留，派生与恢复过程不替工作人员修正文档。

文稿微模板使用相同的 `World.act`、版本存储、授权、确认、条件和生命周期函数，两套作者／编辑 ID 无需改变核心代码。它只检查字段、精确来源和指定短语，不是第二个行业基准。

```bash
# 指定缓存的删除、破坏和重复重建
.venv/bin/python scripts/state_projection_experiment.py --output runs/state-projection --workers 4
# 两个真实模板的共同语义轨迹
.venv/bin/python scripts/adapter_conformance_experiment.py --output runs/adapter-conformance --workers 4
# 独立参考模型下的有界状态探索
.venv/bin/python scripts/bounded_state_experiment.py --output runs/bounded-state --depth 4
# 真实进程中断及提交后异常恢复
.venv/bin/python scripts/bounded_recovery_experiment.py --output runs/bounded-recovery --workers 4
# 七个指定语义错误的负对照
.venv/bin/python scripts/semantic_mutation_experiment.py --output runs/semantic-mutants --workers 4
# 保留的十类经营世界回归
.venv/bin/python scripts/world_mechanism_suite.py --output runs/world-regression --workers 4
```

本轮 **247 项代码回归通过**，正式实验使用冻结提交 `fe80b02`：

| 实验 | 结果 |
| --- | --- |
| E1 指定缓存重建 | 48/48 变体，288/288 检查 |
| E2 两模板符合性 | 4/4 世界，11/11 跨模板比较点；含局部检查共 31/31 |
| E3 有界参考状态机 | 长度 ≤4，446 个状态、5139 次转移尝试，未发现反例 |
| E4 单写者恢复 | 10/10 真实进程中断切点，60/60 检查；另列普通异常探针 4/4 |
| E5 语义负对照 | 7/7 正常对照通过，7/7 变异触发指定断言 |
| 原机制回归 | 10/10 情境，56/56 检查；8 完成、1 规格拒绝、1 合理阻塞 |

各组计数含义不同，不合成总分。报告保留构造失败、开发期反例及修复记录。当前证据支持声明范围内的一致性，不证明所有历史路径、断电持久性、任意并发或领域专业真实性。

本轮没有 API、GPU 或参数训练。原工作配置仍为四种配置、三种不同工作图；带指南布局与明示范围的选择性更新保持有限解释。

- [v0.5 详细实验、开发期失败与复现](docs/experiments/state-consistency-v05.md)
- [v0.5 状态一致性与有界恢复设计](docs/state-consistency-v05.md)
- [数据合同与扩展接口](docs/data-contracts.md)
- [本轮审计](docs/reference/state-consistency-audit.md)
- [v0.4 内核迁移设计](docs/semantics-kernel-v04.md)与[历史实验](docs/experiments/semantics-kernel-v04.md)
- [v0.3 生命周期设计](docs/world-semantics-v03.md)与[历史 API／补修实验](docs/experiments/world-semantics-v03.md)
- [v0.2 实现](docs/post-audit-implementation.md)与[历史训练接口归档](docs/experiments/post-audit-v02.md)
- [初版架构](docs/implementation-v0.1.md)、[初版实验](docs/experiments/v0.1.md)、[原始设计](docs/reference/design-v0.1.md)

旧上下文对照、7 个 API 世界和本地 LoRA 冒烟保留为历史记录，本轮没有为补齐模型成功而重新采样。

目标模型仅通过绑定身份的工具会话访问资料。当前计算器为显式定义的 XLSX 子集，不提供宿主机 Shell。真实原始轨迹、导出包和 LoRA 检查点保存在本地 `runs/`，Git 保存代码、报告及精简结果。
