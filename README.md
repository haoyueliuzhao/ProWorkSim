# ProWorkSim

**面向智能体学习的专业工作世界模拟与任务流合成。** v0.8 在同一个多项目世界中接通持续工作：真实发布按项目规则产生通知、需求修订或后继义务；工作人员通过公开接口取得资料、按具体工作采用来源并继续制作与交付。

世界核心负责身份、作用域、版本、事件与提交恢复；适配器执行文件操作；领域合同和独立评价检查固定提交。**保存草稿、正式发布、采用声明、实际内容更新是不同动作。**

## 安装与工作示例

需要 Python 3.11+：

```bash
python -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'

.venv/bin/proworksim world-create runs/capability-demo --spec examples/work-capabilities/world.json
.venv/bin/proworksim project-load runs/capability-demo examples/work-capabilities/project-a.json --actor operator
.venv/bin/proworksim project-load runs/capability-demo examples/work-capabilities/project-b.json --actor operator
.venv/bin/proworksim world-tools runs/capability-demo --actor analyst --project A
```

下面通过公开会话读取 A 的材料、创建工作簿、提交并发布，再让 B 的程序工作人员继续使用成果。该示例只计算一个有限合成差值，不是金融专业模型：

```python
from proworksim.world_core import WorldCore
from proworksim.public_worker import run_public_worker

world = WorldCore("runs/capability-demo")
a = world.session("analyst", "A")
b = world.session("writer", "B")

def call(session, tool, **arguments):
    result = session.call(tool, **arguments)
    assert result["ok"], result
    return result["result"]

source = call(a, "read_object", alias="private-input")
model = call(a, "create_object", alias="model", filename="report.xlsx", kind="xlsx",
    deliverable_role="model", dependencies=[source["reference"]], data={
        "Report!B1": source["data"]["revenue"],
        "Report!B2": source["data"]["cost"],
        "Report!B3": "=B1-B2",
    })
submission = call(a, "submit", work_id="work-1", artifacts=["model"])
call(world.session("reviewer", "A"), "approve", work_id="work-1",
     submission_id=submission["submission_id"])
call(a, "publish", alias="model", version_id=model["version_id"], target_projects=["A", "B"])
call(a, "share", object_id=model["object_id"], version_id=model["version_id"],
     target_project="B", actor_ids=["writer"], follow_updates=True)
call(b, "adopt", alias="released_model", object_id=model["object_id"],
     version_id=model["version_id"], policy="current_published", work_ids=["work-1"])
call(a, "close_project", mode="completed", reason="Published reusable calculation")
result = run_public_worker(b)
assert result["status"] == "submitted", result
print(world.evaluate_submission("B", "work-1", result["submission_id"]))
```

B 读取 A 的发布接口，不获得 A 的私有上游。程序工作人员只使用 `tools/observe/call`，记录当时实际返回的观察和工具往返；它是有限机制验证策略，不是模型能力实验。

也可使用 CLI：

```bash
.venv/bin/proworksim world-inspect runs/capability-demo --actor writer --project B
# 对尚未完成、符合有限来源合同的工作运行程序工作人员；轨迹文件须新建且在世界外
.venv/bin/proworksim world-worker runs/capability-demo --actor writer --project B \
  --max-actions 24 --output runs/worker-transcript.json
.venv/bin/proworksim snapshot runs/capability-demo runs/capability-snapshot
.venv/bin/proworksim restore runs/capability-snapshot runs/capability-restored
```

## 实际工作与评价

- `create_object` 支持 JSON 和 XLSX；`sheet_read/update/recalculate` 复用现有受限公式引擎。公式错误可以真实落盘，不能由后台偷偷修正。
- 同项目或跨项目的精确分享只开放指定版本。窄对象／工作采用权限逐项传入检查，其他范围与 fixed 政策的拒绝保持。
- 新世界默认显式发布。草稿不会自动成为下游正式输入；发布事实绑定版本、主体、时间和范围，再沿明确订阅产生授权与通知。
- `current_published` 跟随项目范围内的正式发布；`fixed` 保留快照。两者均不自动证明领域适用性。
- 独立评价仅读取固定不可变版本，核对实际缓存值、来源正文、采用快照及贡献文件的声明依赖。所有标签都换成 v2，旧数值仍会失败。
- 正式批准和内容正确性分开；A 的错误成果获批准后，B 忠实消费该接口不等于 A 的计算已正确。
- 采用按工作和需求版本独立保存；新工作可以沿相同别名采用另一版本，旧提交快照保持，已声明政策不能自行绕过。
- 嵌套 JSON 比较递归区分布尔值与数值；多文件冲突不随文件顺序改变结果，不挑选一份正确文件覆盖冲突。
- 项目维护规则按真实读取、编辑、待审和接受阶段产生明确义务。后继工作保留已接受前项，后台不替工作人员改文件。
- 多源合同支持有限线性计算，逐项核对精确引用、采用、贡献依赖和实际内容；上游正确性、下游忠实性、总体目标分别评价。
- 资料路线可供后继或替代工作复用，每个请求独立绑定具体工作。缺路线时报告能力缺口；提供者恢复后可发新请求并继续。

[实现说明](docs/continuous-work-v08.md)、[两阶段计划](docs/continuous-work-v08-plan.md)、[核心语义](CORE_SEMANTICS.md)、[状态归属](STATE_OWNERSHIP.md)、[行动合同](ACTION_CONTRACTS.md)和[数据合同](docs/data-contracts.md)给出完整边界。

## 持续执行与本轮实验

新 `ContinuousWorker` 支持多个公开会话和多项工作，每步最多一个工具调用，记录实际观察和返回。策略等待、世界条件阻塞、预算耗尽和环境错误分别报告。它是有限程序策略，不是通用模型能力结果。

`ports.json` 指定同一世界中的会话，例如：

```json
{"A": {"actor": "analyst", "project": "A"}, "B": {"actor": "writer", "project": "B"}}
```

```bash
.venv/bin/proworksim world-continue runs/capability-demo --ports ports.json \
  --max-actions 40 --output runs/continue-1.json
# 外部合法事件或新义务发生后，从已完成步骤的checkpoint继续；输出须是新文件
.venv/bin/proworksim world-continue runs/capability-demo --ports ports.json \
  --checkpoint runs/continue-1.json --max-actions 40 --output runs/continue-2.json
```

checkpoint 只承诺已完成步骤之间的显式保存与恢复；不等同任意进程崩溃下的策略恢复。前面的基础示例未配置维护规则；自动后继的完整配置、真实公开操作和轨迹由 P4 `published_successor` 情境提供。

阶段 A 冻结 `28786f4`，阶段 B 冻结 `62f3a6a`。两阶段均在冻结后记录测试身份，最终完整回归 **421 项通过**，Ruff 通过。

| 组别 | 正式结果 |
| --- | --- |
| P0 JSON冲突与顺序 | 76/76；旧完整版本更正测量后62/76 |
| P1 工作采用及资料路线 | 27/27 |
| P2 事件形成义务 | 20个情境，180/180 |
| P3 多源局部更新 | 64/64，另2/2合法布局对照 |
| P4 公开等待、切换与继续 | 7组，67/67；含真实发布自动后继完整闭环 |
| 新机制恢复 | 两个真实进程中断切点，20/20 |
| 原N1/N3相关回归 | 22/22、11/11 |

[详细实验报告](docs/experiments/continuous-work-v08.md)保留逐项审计对应、两阶段身份、开发缺陷与测量修订、独立期望及证据索引。各分母含义不同，不合成专业能力分数。

```bash
.venv/bin/python scripts/json_conflict_experiment.py --output runs/p0-new --workers 4
.venv/bin/python scripts/work_binding_experiment.py --output runs/p1-new --workers 4
.venv/bin/python scripts/maintenance_experiment.py --output runs/p2-new --workers 4
.venv/bin/python scripts/multisource_experiment.py --output runs/p3-new --workers 4
.venv/bin/python scripts/continuous_worker_experiment.py --output runs/p4-new --workers 4
.venv/bin/python scripts/work_obligation_recovery_experiment.py --output runs/recovery-new --workers 2
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check src tests scripts
```

实验目录必须新建。Git 保存代码、协议及精简证据；完整版本、轨迹、检查点和故障材料保留在服务器 `runs/`。

## 范围与历史

新世界格式为 `world-core-v0.8`。旧 v0.6/v0.7 世界需使用对应冻结版本，不隐式迁移历史。旧“后续写入即发布”仍可作为新世界的 `implicit_write` 政策明确选择；不为历史补造发布记录。

本轮保留受限 XLSX 能力，没有将完整经营估值模板、任意 Excel 功能、GUI 或宿主 Shell 迁入核心；多项目 DeepSeek 执行器和训练导出未在本轮新增。原单项目入口仍可运行：

```bash
.venv/bin/proworksim build runs/operating-demo --seed 17 --delivery continuous --information clarification
.venv/bin/proworksim run runs/operating-demo --provider baseline --inject-stale-memo
.venv/bin/proworksim evaluate runs/operating-demo
```

本轮没有模型 API 调用、GPU 使用或训练，也没有真实金融数据采集。后续已有合法工作材料用于校准工具、领域合同或通用关系；provenance 继续区分 observed/reconstructed/synthetic/unknown，不能从财报和最终文件编造审批历史。单写者与指定中断切点的通过不意味着任意并发、断电或专业真实性已验证。

- [本轮审计](docs/reference/continuous-work-audit.md)
- [v0.7工作能力](docs/work-capabilities-v07.md)及[含后续审计注记的原报告](docs/experiments/work-capabilities-v07.md)
- [v0.6 世界与多项目设计](docs/world-core-v06.md)及[原实验报告](docs/experiments/world-core-v06.md)
- [v0.5 状态一致性](docs/state-consistency-v05.md)及[含 E2 勘误的报告](docs/experiments/state-consistency-v05.md)
- [v0.4 内核迁移](docs/semantics-kernel-v04.md)及[实验](docs/experiments/semantics-kernel-v04.md)
- [v0.3 生命周期](docs/world-semantics-v03.md)、[历史 API 实验](docs/experiments/world-semantics-v03.md)、[历史训练接口](docs/experiments/post-audit-v02.md)
- [原始设计](docs/reference/design-v0.1.md)
