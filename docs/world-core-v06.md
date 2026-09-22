# v0.6 World Core：持久世界、多项目与动态产物

本轮依据 [多项目审计](reference/multiproject-audit.md)，按 [执行计划与验收协议](world-core-v06-plan.md) 实现。本文说明实际对象合同、运行边界和使用方式；正式实验成绩另在 `docs/experiments/` 记录。v0.5 的状态一致性与恢复基线继续保留；E2 的正式确认测量缺陷另行勘误和复验。

## 1. 架构与版本边界

`proworksim.world_core.WorldCore` 是一个持续存在的世界运行器。新建世界只要求世界身份、主体和世界级授权，项目集合初始为空。项目包随后向同一状态注册工作、对象、局部权限和采用关系，使用同一逻辑时钟、文件服务、事件队列与历史。

```text
core.world.WorldSpec
  └─ WorldCore：世界身份、主体、对象、项目集合、共享与采用
       ├─ ProjectInstance A ─ Workspace A ─ A::work-1
       ├─ ProjectInstance B ─ Workspace B ─ B::work-1
       └─ ProjectInstance C（运行中装载）

WorldCore ─────────────┐
经营 World ───────────┼─ core.runner.WorldRunner ─ Store / journal / transitions
文稿 PublicationWorld ┘
```

`WorldRunner` 从原运行器抽取公共的单写者锁、阶段执行、命令与事件提交、幂等与恢复过程。World Core 和既有适配器复用这一运行机制；新世界没有继承经营世界的金融字段、`model`/`basis` 对象或单个 `project` 假设。多个项目也没有被各自编译成子世界再由一个目录索引拼接。

| 标识 | 本轮含义 |
| --- | --- |
| Python 包版本 | `0.6.0` |
| 新世界 schema | `world-core-v0.6` |
| 新世界语义版本 | `work-world-v0.6` |
| 既有经营／文稿适配器运行格式 | 继续使用 `0.5`，可独立复验 |
| 新世界规格 | `proworksim.core.world.WorldSpec`，也由 `proworksim.WorldSpec` 导出 |
| 旧领域设计规格 | `OperatingTemplateSpec`；不再与通用世界规格同名 |
| 阶段回执格式 | 复用 `phase-deltas-v0.5`；每条回执／日志的语义版本取所在世界 |

不同格式没有隐式历史迁移。`WorldCore` 只装载自身 schema，旧运行器也不会把新状态解释为经营项目。既有完整经营 XLSX 模板并未自动转成 `ProjectPackage`；保留其原运行入口不等于已经完成领域包迁移。

## 2. 四种生命周期

| 生命周期 | 状态与操作 | 不隐含的效果 |
| --- | --- | --- |
| 世界 | 稳定 `world_id`、实例和分支身份、时间、主体、注册表；创建、暂停／恢复运行、观察、快照、故障恢复 | 没有活动项目不要求删除或重编译世界 |
| 项目 | `active` → `completed` 或 `archived`；装载与 `close_project` | 项目结束不删除主体、历史提交或已共享对象 |
| 工作 | 工作定义、需求版本、等待条件、提交、审阅、替代与取消 | 一项工作完成不关闭其他项目 |
| Episode | 选择项目集合的起止时间／提交 revision 记录 | 结束 Episode 不清空对象、消息、另一项目或人员阅读历史 |

`completed` 要求该项目的当前义务均已接受。`archived` 可结束尚未完成的项目，但必须按包中的 `close_policy.pending_obligations` 处理：

- `retain`：保留未完成义务和已经安排的回复接收。归档项目不再接受新的工作人员写入／提交，但后续接收事实仍可以保存。
- `cancel`：记录尚未完成工作和条件的取消／替代关系；相关待到事件按取消结果收尾，而不是静默删除历史。

关闭项目不会取消别的项目的事件。对象是否仍可读取由已有共享和访问关系决定；项目关闭不是一次全量撤权。当前版本没有重新开启归档项目的工具；持续工作应由明确的新项目或后续合同承接。

世界可以由具有显式世界级 `pause_world` 权力的会话调用 `pause`／`resume`。暂停时拒绝新工作及 `wait`，不处理到期环境事件，工作观察中的使能动作清空；读取、观察和结束 Episode 仍可进行。`resume` 恢复准入并处理到期事件。这里暂停的是工作准入与环境处理，不是挂起进程或冻结所有审计时间：逻辑时钟按操作计数，读取和拒绝操作仍可能推进。

世界观察区分 `paused` 与运行时的 `active`／`idle`；后两者取决于是否存在活动项目。这与项目是否业务成功、Episode 是否结束是不同判断。

## 3. 新规格与项目包

`WorldSpec` 包含：

```text
world_id, actors, applications, bootstrap_grants, event_policy
```

主体在世界级注册。`bootstrap_grants` 必须指向已登记主体，并显式标记 `scope="world"`。世界配置可以授予 `install_project`、`create_object`、`publish` 和 `share` 等权限；领域项目包不能借装载新建管理员或自动取得这些权力。`applications`、`event_policy` 是当前有限服务的配置和记录入口，不代表已经支持任意应用插件或事件规则语言。

`ProjectPackage` 包含：

```text
project_id, goal, participants, objects, works, grants,
adoptions, provenance, close_policy
```

包允许零个预设产物。工作既可声明固定交付别名，也可使用动态 `deliverable_contract`，让工作人员在运行中组织交付文件。项目包中的 `objects` 是带明确归属、访问者、写入者、内容和来源标记的材料；它们不是可以导入任意过去批准、对话和工作人员轨迹的历史容器。

包先完整验证主体、局部名称、对象引用、工作依赖、采用权限、授权范围和来源标记，然后进行状态注册与初始文件版本写入。非法工作引用、依赖环、跨项目授权或世界权力扩张使整个包拒绝。拒绝可以留下调用结果和提交日志；“没有半个项目”指项目、工作、对象、授权及正式文件不发生部分部署，而不是声称全状态连逻辑时间也完全不变。

`WorkContext` 明确表达 `world_id`、`project_id`、工作引用、需求版本、用途、期间、需求维度和工作节点。正式查询不会仅凭一个可能在多个项目重名的 `work-1` 推断作用域。

## 4. 身份、别名与作用域

世界工作引用使用项目限定名称，例如 `A::work-1` 与 `B::work-1`。项目内 `work-1` 由可信会话解析；直接填写另一个项目的限定工作引用也不能越过会话范围。

对象 ID、项目别名和显示文件名是三种不同关系：

| 关系 | 例子 | 约束 |
| --- | --- | --- |
| 世界对象身份 | 工具返回的 `object_id` | 由明确的世界／项目命名空间与别名编码生成，调用方不能指定另一个对象身份 |
| 工作空间别名 | A 的 `report`、B 的 `report` | 分别登记在 `workspaces[project_id]` 中；除显式采用外不指向其他项目对象 |
| 显示文件名 | 两者都为 `report.json` | 允许同名，实际存储路径含对象身份 |
| 精确引用 | `{object_id, version_id}` | 指向登记的不可变版本，不仅比较名字 |

对象 ID 是内部生成的稳定标识，不应由调用方拼接 `project--alias`。实验和应用使用创建工具的返回值或可信注册表查询。

`ScopedGrant` 指定主体、项目、权力、主题、工作节点以及对象范围。同一个人可以在 A 执行、在 B 审阅；B 的 `approve` 权不能批准 A 的提交。世界授权也不自动降级为所有项目的制度授权。

宿主通过 `world.session(actor, project_id)` 绑定身份与项目。工具输入禁止再次注入 `actor`、`actor_id` 或 `project_id`。CLI 的 `--actor`／`--project` 是可信操作者选择会话的入口；提供给模型的是已绑定会话，而不是让模型选择任意人的宿主身份。

命令身份包含主体、可信项目命名空间和 `request_key`；摘要包含工具与实际参数。相同主体在同一项目重试相同命令返回原结果；相同身份换负载冲突；相同主体在两个项目使用相同文本键与负载形成两条独立命令。

## 5. 动态产物与有限内容合同

`create_object` 在受控工作空间创建原来未登记的 JSON 对象，并立即进入相同的版本与权限体系。`write_object` 生成下一不可变版本；提交固定真实版本引用。工具只支持有限 JSON 对象和简单 JSON 文件名，不开放任意宿主路径或代码执行。

依赖通过显式精确引用声明。创建或修改文件时检查调用主体在绑定项目下可以读取依赖，但不会因此把依赖正文复制给后续接收者。项目内动态产物默认对项目参与者可读、仅创建者可写；项目包内的初始材料则按其明确声明的读写名单登记。

动态交付合同目前支持：

```json
{
  "min_files": 1,
  "max_files": 2,
  "allowed_roles": ["report"],
  "required_fields": ["revenue", "cost"]
}
```

制度提交检查文件数量、产物角色、对象归属、版本存在、当前工作与必要凭据。`required_fields` 的内容检查独立执行：读取提交固定的版本，合并顶层字段，报告缺失字段和多文件间的同名不同值冲突。它允许一份聚合文件或两份分拆文件满足同一字段合同；额外未提交的中间草稿不自动判错。

`evaluate_submission()` 当前范围是 `finite_json_presence_contract`。它不验证金融定义、计算正确性、单位、经济含义、叙述质量或现实真实性。即使包中记录了更复杂的业务描述，也不能据此把字段存在检查称为完整领域评价。

工作有两种批准政策：

- `review`：提交后由有权审阅者明确批准。
- `delivery_only`：合法交付即形成接受结果，无需外部审阅动作。内部沿用提交的 `review` 记录容器，保存 `decision_basis="delivery_only"` 及提交者身份，不能把这条记录描述成经理批准。

内容不充分的文件可以合法创建和提交，并保留正式历史；独立评价仍可以失败。评价不会倒写审阅或删除提交。这是制度可执行性与内容正确性的分离。

## 6. 正式确认、必要凭据与读取

确认针对真实存在的精确对象版本，要求签发主体在对应项目、工作、主题及对象范围拥有 `confirm` 权。签发事实由版本上的 `credential` 与世界 `attestations` 登记关联；正文自称 `approved`、共享事实或读过文件不能代替正式签发。

工作可声明 `required_credentials`。World Core 在提交和批准前检查这些版本可读且 `registered_applicability` 为 `PASS`；观察中的提交／批准使能也使用同一检查。错误项目、工作、需求、用途或缺少签发关联不能凭“同一文件名”获得正式效果。

历史确认存在与当前适用是不同维度：一份合法签发的旧凭据可以继续作为历史事实存在，同时不适用于新需求或另一项目。E2 测量修订因此规范化目标、凭据、签发记录三方 `VersionRef`，并检查签发关联；还增加独立真值预期，避免两个适配器同时误报 false 却通过相等性检查。

## 7. 共享、采用与定向变化

`share` 授予指定目标项目、主体和精确版本的访问。`follow_updates=false` 只分享这一版；后续发布不会自动开放新版本。`follow_updates=true` 明确建立后续版本的发布关系。分享下游成果不递归授予上游私有材料。

世界操作者可以为尚未安装的项目 ID 预分享世界材料，但接收者必须已经是世界主体；安装含该材料的采用关系时，仍逐项验证项目参与者和精确版本的授权。普通项目不能借此创建任意目标项目或预授权不存在的人。

`adopt` 把已经可读的版本登记为项目输入，并绑定具体工作：

| 采用政策 | 发布新版本后的含义 |
| --- | --- |
| `fixed` | 维持明确采用的历史版本；较旧不自动等于错误 |
| `current_applicable` | 对照已发布的目标版本；未显式采用新版时显示 `update_required` |

版本发布、关系／义务变化、通知送达、工作人员修改是分开的步骤。环境可以更新采用视图和发送通知；不会自动替工作人员重写成果。局部需求或受众修订同样不应直接重写共同文件字节。

`adopt_version(alias, version_id)` 是对 `current_applicable` 采用关系的显式更新入口；检查项目 `adopt` 权及目标版本的精确读取权限，相同版本重复声明无变化。更新 `adoption.version_id` 时向 `adoption.history` 追加 `previous_version`、`version_id`、`actor_id` 和 `at`，避免为了清除 `update_required` 悄悄改变过去采用的版本。采用新版也不表示已经修改或重新提交产物；实际文件仍需由工作人员调用写入工具更新。固定快照政策不被这个入口静默转换成跟踪最新版本。

观察展示项目当前可访问对象和允许动作。人员的 `knowledge` 与真实工具返回历史持续保留；切换项目不会让已合法获知的信息消失。技术访问边界也不等于建模了人的记忆、保密承诺或所有组织制度。

## 8. 回复、提交和有限恢复

项目请求固定具体工作、需求版本、提供者、用途和精确证据引用。延迟回复作为世界事件交错执行，使用共享条件内核保存原始响应并判断满足关系。A 的旧回复不能解除 B 的条件；A 修订之后到达的旧回复仍被保存，但不能自动满足新义务。

`WorldRunner` 的提交顺序为：

1. 在单写者锁内恢复已提交状态、重建指定投影并检查操作身份。
2. 执行工具 Apply 与 Derive，保留真实阶段差分并检查允许写入区域及不可改写历史。
3. 原子保存命令状态与操作提交记录。
4. 每个到期环境事件单独执行、单独提交；命令已提交与事件送达异常分别报告。

恢复沿用已提交 revision 前缀、版本哈希、物化镜像恢复及未提交暂存版本隔离。同一已提交命令重试不重复正式效果；必要时继续排队事件。`world-recover` 无需重新执行工作人员策略即可恢复和继续到期事件。

本轮针对新增共享变化选择少量提交前／提交后未返回的进程切点，比较项目、授权、别名、采用、历史及版本文件。它不扩张为多写者、分布式提交、断电持久性或任意外部插件事务的保证。

## 9. 最小使用示例

以下示例运行一个全新的 JSON 世界；目录必须不存在。身份选择由本地可信程序完成。

```python
from proworksim.core.world import WorldSpec
from proworksim.world_core import WorldCore

world = WorldCore.create("runs/example-world-core", WorldSpec(
    world_id="example-office",
    actors={"operator": {}, "analyst": {}},
    bootstrap_grants=[{
        "actor_id": "operator", "scope": "world", "power": "install_project"
    }],
))
package = {
    "project_id": "A",
    "goal": "Prepare a small synthetic JSON report",
    "participants": ["operator", "analyst"],
    "objects": [],
    "works": [{
        "work_id": "work-1",
        "owner": "analyst",
        "approval_policy": "delivery_only",
        "deliverable_contract": {
            "min_files": 1, "max_files": 2,
            "allowed_roles": ["report"],
            "required_fields": ["revenue", "cost"]
        }
    }],
    "grants": [{
        "actor_id": "analyst", "power": "create_object", "subject": "artifact"
    }],
    "provenance": {"kind": "synthetic", "source_evidence_refs": []},
    "close_policy": {"pending_obligations": "retain"}
}
assert world.session("operator").call("install_project", package=package)["ok"]
worker = world.session("analyst", "A")
created = worker.call(
    "create_object", alias="report", filename="report.json",
    data={"revenue": 10, "cost": 4}, deliverable_role="report",
    request_key="create-report"
)
assert created["ok"]
submitted = worker.call("submit", work_id="work-1", artifacts=["report"])
assert submitted["ok"]
print(world.evaluate_submission(
    "A", "work-1", submitted["result"]["submission_id"]
))
```

CLI 接收对应的世界规格和项目包 JSON 文件：

```bash
.venv/bin/proworksim world-create runs/new-world --spec world-spec.json
.venv/bin/proworksim project-load runs/new-world project-A.json --actor operator
.venv/bin/proworksim world-inspect runs/new-world --actor analyst --project A
.venv/bin/proworksim world-act runs/new-world create_object --actor analyst --project A \
  --request-key create-report \
  --arguments '{"alias":"report","filename":"report.json","data":{"revenue":10,"cost":4},"deliverable_role":"report"}'
.venv/bin/proworksim world-act runs/new-world submit --actor analyst --project A \
  --arguments '{"work_id":"work-1","artifacts":["report"]}'
.venv/bin/proworksim world-evaluate runs/new-world --project A --work work-1 \
  --submission A::work-1-submission-1
.venv/bin/proworksim world-recover runs/new-world
```

复现机制实验时使用新输出目录。脚本固定检查协议并保存原始调用、状态与文件证据；这里的命令不是已经执行的成绩：

```bash
.venv/bin/python scripts/conformance_measurement_experiment.py \
  --output runs/e2-measurement-replay
.venv/bin/python scripts/adapter_conformance_experiment.py \
  --output runs/e2-corrected --workers 4
.venv/bin/python scripts/world_core_experiment.py \
  --groups M1 M2 M4 --output runs/world-core-checks --workers 3
```

M3/M5 的定向关系和恢复协议见 [执行计划](world-core-v06-plan.md) 与其独立脚本 `scripts/world_core_relations_experiment.py`。

## 10. 真实工作材料的后续接入

项目包的 `provenance.kind` 区分 `observed`、`reconstructed`、`synthetic` 与 `unknown`。直接观察材料须提供非空 `source_evidence_refs`；工程重建和模拟补充不能冒充直接观察的正式确认、返工或审阅历史。

真实金融材料未来通过对象、参与者、工作要求、用途／期间和评价合同映射为项目包。格式差异由工具和渲染适配；金融定义、单位与计算由领域评价负责；无法表达的共享、权限或工作交接关系再反馈到世界核心。有限 JSON 示例没有证明真实金融工作流的外部合理性，也没有把原经营合成数据重新命名为真实金融数据。
