# ProWorkSim

**面向智能体学习的专业工作世界模拟与任务流合成。** 当前 v0.3.1 将经营估值模型、披露材料、版本化批准依据和研究备忘录编译成可执行项目。当前重点是工作世界语义与生命周期：确认、阻塞、需求变化、审阅和交付须产生可核验的后果。

保留三个交付粒度，并新增可配置的工作结构与布局：

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

## 当前修订与实验

已修复工作—发布互相等待的规格准入漏洞和 scope 回复误解无关阻塞的问题。新增正式批准依据、按版本授权、多个独立 blocker、编辑／等待／待审期间的需求变更、撤回重交，以及不同受众的有限内容要求。

数据来源新鲜度、依据适用性和数值正确性分别记录。缺适用批准时允许合理阻塞；不能用隐藏生成规格替代业务确认进行数值打分。模型仅改成“新版依据”标签而沿用旧数值时，独立评价仍会拒绝。

```bash
# 在待审期间发生依据变更
.venv/bin/proworksim build runs/review-change --scenario during_review --information clarification
.venv/bin/proworksim run runs/review-change --provider baseline
.venv/bin/proworksim evaluate runs/review-change

# 程序机制验收；不调用模型
.venv/bin/python scripts/world_mechanism_suite.py --output runs/world-mechanisms --workers 4
.venv/bin/python scripts/basis_error_diagnosis.py runs/basis-diagnosis --workers 4

# 固定模型作为测试工作人员，无参数训练
.venv/bin/python scripts/world_staff_trials.py runs/world-staff --workers 3 --max-turns 45
```

本轮结果：**142 项回归通过；10/10 程序机制情境和 4/4 错误策略预期通过。**固定 DeepSeek 的 7 个情境中，6 个完成并通过独立评价；信息不可得的一例最终阻塞，但此前两次尝试提交无适用批准的成果，均被拒绝，因此仍记失败。共 118 次 API 调用，未启动本地模型或 GPU 训练。

该失败还暴露了依据状态标签与无批准数值诊断的缺口，已补修。对原 7 个世界的副本重评保持文件、调用、消息、审阅和业务终态不变，新增 API 调用为 0；不把事后重评称作新的模型成功。

配置维度为四种工作配置、三种工作图（chain/fork/selective），coordination 是 chain 配 clarification。shifted 布局提供对应指南，selective 明示只改 note；这些实验不证明任意布局理解或自主发现全部影响范围。

- [本轮详细实验、失败轨迹与补修复核](docs/experiments/world-semantics-v03.md)
- [工作世界语义与生命周期设计](docs/world-semantics-v03.md)
- [数据格式与扩展接口](docs/data-contracts.md)
- [本轮审计](docs/reference/world-semantics-audit.md)
- [v0.2 实现](docs/post-audit-implementation.md)与[历史实验／训练接口归档](docs/experiments/post-audit-v02.md)
- [初版架构](docs/implementation-v0.1.md)与[初版实验](docs/experiments/v0.1.md)
- [原始设计](docs/reference/design-v0.1.md)、[补充资料](docs/reference/apex-supplement.md)、[首轮审计](docs/reference/audit-v0.1.md)

旧上下文对照和本地 LoRA 冒烟保留为历史诊断与接口验证，本轮未扩大该分支，也未证明训练收益。

目标模型仅通过绑定身份的工具会话访问资料。当前计算器为显式定义的 XLSX 子集，不提供宿主机 Shell。真实原始轨迹、导出包和 LoRA 检查点保存在本地 `runs/`，Git 保存代码、报告及精简结果。
