# ProWorkSim

**面向智能体学习的专业工作世界模拟与任务流合成。** v0.7 把 JSON、受限 XLSX、精确发布和采用接入同一个多项目世界：工作人员实际创建、编辑和交付文件，后续项目可以消费明确发布的成果。

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
- 资料路线必须明确配置实际提供者和精确材料；缺少路线或本次不可得时合理等待，不编造隐藏对象 ID、金额或回复。

[实现说明](docs/work-capabilities-v07.md)、[两阶段计划](docs/work-capabilities-v07-plan.md)、[核心语义](CORE_SEMANTICS.md)、[状态归属](STATE_OWNERSHIP.md)、[行动合同](ACTION_CONTRACTS.md)和[数据合同](docs/data-contracts.md)给出完整边界。

## 本轮实验

按审计要求分两次冻结。阶段 A 为 `a30a5b9`；最终实现与正式实验为 `d2a407c`。最终完整回归 **326 项通过**，Ruff 通过。

| 组别 | 正式结果 |
| --- | --- |
| N0 合法作用域路径 | 29/29；旧完整版本回放 22/29，七个失败观测对应两处缺陷 |
| N1 同世界 XLSX／JSON 能力 | 22/22 |
| N2 草稿、发布、采用与内容 | 17/17 |
| N3 跨项目成果使用 | 11/11，明确比较六种策略条件 |
| N4 公开会话工作人员 | 4/4 情境、28/28；三次交付，一次缺资料路线等待 |
| N4 不可得补充 | 8/8；合理等待，未计交付成功 |
| 新能力恢复 | 两个真实进程中断切点、16/16 |
| 相关原机制回归 | M2 14/14、M3 10/10、M3F 8/8 |

[详细实验报告](docs/experiments/work-capabilities-v07.md)保留两阶段身份、逐项审计对应、真实反例、开发记录、独立期望和原始证据索引。各分母含义不同，不合成专业能力分数。

```bash
.venv/bin/python scripts/scope_paths_experiment.py --output runs/n0-new --workers 3
.venv/bin/python scripts/work_capability_experiment.py --output runs/n1-new
.venv/bin/python scripts/publication_consumption_experiment.py --output runs/n23-new --workers 2
.venv/bin/python scripts/public_worker_experiment.py --output runs/n4-new --workers 4
.venv/bin/python scripts/capabilities_recovery_experiment.py --output runs/recovery-new --workers 2
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check src tests scripts
```

实验目录必须新建。Git 保存代码、协议及精简证据；完整版本、轨迹、检查点和故障材料保留在服务器 `runs/`。

## 范围与历史

新世界格式为 `world-core-v0.7`。旧 v0.6 世界需使用对应冻结版本，不隐式迁移历史。旧“后续写入即发布”仍可作为新世界的 `implicit_write` 政策明确选择；不为历史补造发布记录。

本轮迁入受限 XLSX 能力，没有将完整经营估值模板、任意 Excel 功能、GUI 或宿主 Shell 迁入核心；多项目 DeepSeek 执行器和训练导出未在本轮新增。原单项目入口仍可运行：

```bash
.venv/bin/proworksim build runs/operating-demo --seed 17 --delivery continuous --information clarification
.venv/bin/proworksim run runs/operating-demo --provider baseline --inject-stale-memo
.venv/bin/proworksim evaluate runs/operating-demo
```

本轮没有模型 API 调用、GPU 使用或训练，也没有真实金融数据采集。后续已有合法工作材料用于校准工具、领域合同或通用关系；provenance 继续区分 observed/reconstructed/synthetic/unknown，不能从财报和最终文件编造审批历史。单写者与指定中断切点的通过不意味着任意并发、断电或专业真实性已验证。

- [本轮审计](docs/reference/work-capabilities-audit.md)
- [v0.6 世界与多项目设计](docs/world-core-v06.md)及[原实验报告](docs/experiments/world-core-v06.md)
- [v0.5 状态一致性](docs/state-consistency-v05.md)及[含 E2 勘误的报告](docs/experiments/state-consistency-v05.md)
- [v0.4 内核迁移](docs/semantics-kernel-v04.md)及[实验](docs/experiments/semantics-kernel-v04.md)
- [v0.3 生命周期](docs/world-semantics-v03.md)、[历史 API 实验](docs/experiments/world-semantics-v03.md)、[历史训练接口](docs/experiments/post-audit-v02.md)
- [原始设计](docs/reference/design-v0.1.md)
