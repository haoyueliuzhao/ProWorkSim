# ProWorkSim

**面向智能体学习的专业工作世界模拟与任务流合成。** v0.6 实现了先于项目存在的 World Core：世界可以零项目启动，在同一身份、时间、对象注册表与历史中装载、运行和结束项目。工作人员能够创建新产物，项目之间通过明确的授权、共享和采用关系产生影响。

本轮按 [G0–G3 执行计划](docs/world-core-v06-plan.md) 完成 E2 测量修正、多项目承载与有限实验。没有调用模型 API、GPU 或开展训练；当前材料均为合成机制夹具，不代表真实金融工作质量。

## 安装与零项目世界

需要 Python 3.11+：

```bash
python -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'

# 世界先启动，再分别装载项目；两个项目共用人员，但权力分别配置
.venv/bin/proworksim world-create runs/world-demo --spec examples/world-core/world.json
.venv/bin/proworksim project-load runs/world-demo examples/world-core/project-a.json --actor operator
.venv/bin/proworksim project-load runs/world-demo examples/world-core/project-b.json --actor operator
.venv/bin/proworksim world-inspect runs/world-demo --actor alice --project A

# 产物并未在项目包中预建；工作人员通过工具创建
.venv/bin/proworksim world-act runs/world-demo create_object --actor alice --project A \
  --arguments '{"alias":"report","filename":"report.json","data":{"revenue":10,"margin":0.2},"deliverable_role":"analysis"}'
.venv/bin/proworksim world-act runs/world-demo submit --actor alice --project A \
  --request-key submit-A-1 --arguments '{"work_id":"work-1","artifacts":["report"]}'
.venv/bin/proworksim world-evaluate runs/world-demo --project A --work work-1 \
  --submission A::work-1-submission-1

.venv/bin/proworksim snapshot runs/world-demo runs/world-demo-snapshot
.venv/bin/proworksim restore runs/world-demo-snapshot runs/world-demo-restored
```

示例 A 使用 `delivery_only`：交付记录为责任者的完成决定。示例 B 则需要其项目审阅者批准。独立内容检查与制度结果分开；缺少字段的成果仍可留下正式提交和独立失败结果。当前内容检查仅验证 JSON 字段覆盖及冲突，不检查财务合理性。

## 世界与项目的共同规则

- 主体身份跨项目保持。可信会话绑定 actor/project，工具参数不能改绑；同一人的 A 执行职责不会自动变成 A 审阅权。
- 世界对象 ID、项目内别名和显示文件名分开。A/B 可同时使用 `work-1` 和 `report.json`，文件写到独立的受控位置。
- 共享精确版本与分享后续发布分开；采用成果不会获得上游私有材料。已经合法取得的人员阅读历史不会因切换项目而清除。
- 当前采用与固定快照可以对同一发布产生不同后果。环境更新关系和通知，工作人员显式编辑才产生新交付版本。
- 世界、项目、工作与 episode 生命周期分开。项目结束保留正式历史；世界空闲后可再装载；episode 结束不清空另一个项目。
- 同一 `WorldRunner` 执行阶段检查、命令／事件独立提交和有限恢复。World Core 身份覆盖 actor/project/request_key；同键异负载冲突，跨项目同文本键独立。

详细合同与 Python 用法见 [World Core 设计](docs/world-core-v06.md)、[核心语义](CORE_SEMANTICS.md)、[状态归属](STATE_OWNERSHIP.md)、[行动合同](ACTION_CONTRACTS.md)及[数据合同](docs/data-contracts.md)。

## 本轮实验

G0/E2 冻结于 `470d412`；最终 WorldCore 实验与完整回归冻结于 `b97e5c6`。**292 项测试通过**，Ruff 通过。

| 组别 | 正式结果 |
| --- | --- |
| G0 原 E2 检查点重投影 | 22/22；30 处合法确认由误报 false 修正为 true；原目录保持 |
| G0 测量真值／负对照 | 9/9 真值夹具，3/3 指定测量错误检出 |
| E2 四条真实适配器轨迹 | 4/4 世界；原 31 项关系＋22 项独立预期，53/53 |
| M1 世界与项目生命周期 | 13/13 |
| M2 名称、职责与访问隔离 | 14/14 |
| M3 不同采用政策与定向影响 | 10/10 |
| M3F 正式批准依据换版及隔离 | 8/8 |
| M4 动态产物与不同合法交付方式 | 14/14 |
| M5 多项目交错 | 8/8 |
| 新增恢复切点 | 两个真实 `os._exit(73)`，16/16 检查 |

**v0.5 的 E2 原 31/31 只保留为当时脚本输出。** 两种引用表示曾被直接比较，使两模板共同误报正式确认；原相等性通过不能证明这一维度测量正确。本轮使用精确引用规范化、签发关联及独立预期修正，原结果文件没有覆盖。其余旧实验仍保留各自证据范围。

[详细实验报告](docs/experiments/world-core-v06.md)记录审计逐项映射、开发期反例、夹具修订、原始材料与复现命令。各组计数不构成统计独立样本，也不合成为专业能力分数。

```bash
.venv/bin/python scripts/conformance_measurement_experiment.py --output runs/g0-new
.venv/bin/python scripts/adapter_conformance_experiment.py --output runs/e2-new --workers 4
.venv/bin/python scripts/world_core_experiment.py --output runs/m124-new --groups M1 M2 M4 --workers 3
.venv/bin/python scripts/world_core_relations_experiment.py --output runs/m35-new --groups M3 M5 --workers 2
.venv/bin/python scripts/world_core_basis_experiment.py --output runs/m3f-new
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check src tests scripts
```

输出目录须新建。G0 重投影需要本机保留的 `runs/adapter-conformance-v05` 原检查点；新克隆只有精简证据时，应明确缺少这部分原始输入，不能声称已重投影原检查点。其他实验可从合成包直接建立新世界。

## 范围与历史入口

新 World Core schema 为 `world-core-v0.6`；已有经营与文稿适配器保留 schema `0.5`。它们共用运行机制，但完整经营 XLSX 模板尚未自动迁移为项目包。当前多项目工具支持受控 JSON 文件及 Python/CLI 会话；既有模型运行器和训练导出仍属于单项目入口。

原经营模板保留 `short`、`file`、`continuous` 三种交付，以及十类有限机制情境：

```bash
.venv/bin/proworksim build runs/operating-demo --seed 17 --delivery continuous --information clarification
.venv/bin/proworksim run runs/operating-demo --provider baseline --inject-stale-memo
.venv/bin/proworksim evaluate runs/operating-demo
.venv/bin/proworksim export runs/operating-demo runs/operating-demo-export
```

单项目 DeepSeek 运行使用项目 `.env` 中的 `DEEPSEEK_API_KEY`，将 provider 改为 `deepseek`。原始世界、失败轨迹、导出包和历史 LoRA 检查点保留在本地 `runs/`；Git 保存代码、说明和精简证据。项目未使用 APEX 评测题、参考答案或受限数据训练模型。

本轮只支持单世界、单写者、明确共享关系及声明切点，不承诺任意并发、断电持久性或无限状态正确性。后续真实金融工作材料通过 provenance 区分直接支持、重建、合成与未知，用于领域校准；当前没有开展采集工程或编造未观察的工作过程。

- [本轮审计](docs/reference/multiproject-audit.md)
- [v0.5 一致性与恢复设计](docs/state-consistency-v05.md)及[含 E2 勘误的原报告](docs/experiments/state-consistency-v05.md)
- [v0.4 内核迁移](docs/semantics-kernel-v04.md)及[历史实验](docs/experiments/semantics-kernel-v04.md)
- [v0.3 生命周期](docs/world-semantics-v03.md)及[历史 API 实验](docs/experiments/world-semantics-v03.md)
- [v0.2 修订](docs/post-audit-implementation.md)及[历史训练接口](docs/experiments/post-audit-v02.md)
- [初版架构](docs/implementation-v0.1.md)、[初版实验](docs/experiments/v0.1.md)、[原始设计](docs/reference/design-v0.1.md)
