# ProWorkSim

**面向智能体学习的专业工作世界模拟与任务流合成。** v0.1 将已有经营估值模型、披露材料、邮件口径和研究备忘录编译成可执行项目，让分析师通过工具完成实际工作，并导出可验证经历。

第一版已实现三个交付粒度：

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

## 实现范围与结果

v0.1 包含真实 XLSX 修改和受限公式重算、角色权限、私有材料隔离、离散事件、条件审阅、版本依赖、快照分支、DeepSeek 运行器、经历与 SFT/RL 适配包、谱系划分、课程采样。

已完成 12 个离线世界实例及 3 个 DeepSeek 实例的机制验证。三种真实交付粒度均通过修正后的独立验证，实际调用可编译出 37 条符合当前规则的 SFT 记录。连续项目首次评估曾暴露一处未公开的额外引用判据，修订过程保留在实验报告中。

这些结果仅说明小规模机制和数据管线可以运行；尚未执行参数训练，也未证明泛化、训练收益或连续过程优于静态任务。

- [架构与设计落实](docs/implementation-v0.1.md)
- [详细实验报告](docs/experiments/v0.1.md)
- [数据格式与扩展接口](docs/data-contracts.md)
- [用户提供的设计文档](docs/reference/design-v0.1.md)及[APEX 补充资料](docs/reference/apex-supplement.md)

工作簿计算支持的公式集合见架构文档。后台控制文件与导出包面向实验操作者；目标模型只能获得绑定身份的工具会话，不能访问宿主机 Shell 或后台目录。
