# ProWorkSim

**面向智能体学习的专业工作世界模拟与任务流合成。** 当前 v0.2 将已有经营估值模型、披露材料、邮件口径和研究备忘录编译成可执行项目，让分析师通过工具完成实际工作，并导出可验证经历。

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

基线只用于验证任务可解，不是模型能力实验。存在历史失败提交时，`evaluate` 会完整展示失败记录；退出码按每项工作的最后提交判定。

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

## 审计后修订与实验

已修复公开引用与评分漂移、正文/元数据依赖不一致及百分号优先级错误。新版本支持链式、分叉、选择性更新和实时信息协调，通过规格定义节点和事件，支持标准/移动表格布局。

```bash
.venv/bin/proworksim build runs/fork --seed 211 --topology fork --layout shifted
.venv/bin/proworksim run runs/fork --provider deepseek
.venv/bin/proworksim evaluate runs/fork
```

验证结果：60 项整套测试及新增课程准入回归通过；原 12 配置和新增 16 配置机制矩阵通过；四种新结构的真实 DeepSeek 试跑全部通过。历史 43 次调用保持不变，37 条候选 SFT 经修订评价复核后保留。

匹配的第二阶段快照实验中，保留/清空历史上下文各通过 1/2，两次失败均沿用旧假设，尚无一致优势。本地 Qwen 已完成真实 LoRA 更新、保存、精确参数重载和工具环境回接，但未在 12 轮预算内完成后续任务；本轮没有证明训练收益。

- [审计后实现说明](docs/post-audit-implementation.md)
- [本轮详细实验与失败记录](docs/experiments/post-audit-v02.md)
- [初版架构记录](docs/implementation-v0.1.md)与[初版实验](docs/experiments/v0.1.md)
- [数据格式与扩展接口](docs/data-contracts.md)
- [原始设计](docs/reference/design-v0.1.md)、[补充资料](docs/reference/apex-supplement.md)、[审计结论](docs/reference/audit-v0.1.md)

目标模型仅通过绑定身份的工具会话访问资料。当前计算器为显式定义的 XLSX 子集，不提供宿主机 Shell。真实原始轨迹、导出包和 LoRA 检查点保存在本地 `runs/`，Git 保存代码、报告及精简结果。
