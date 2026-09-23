# v0.8 工作上下文与持续推进合同

依据：[审计](reference/continuous-work-audit.md)及[两阶段计划](continuous-work-v08-plan.md)。阶段 A 规定内容评价与工作绑定；阶段 B 将发布、义务、资料恢复与公开调度连接起来。本说明只记录实现合同，正式结果、冻结身份与覆盖范围见独立实验报告。

## 阶段 A：内容与工作绑定

新 schema 为 world-core-v0.8、语义 work-world-v0.8，阶段 A 内容评价版本为 finite-products-v0.8；阶段 B 增加有限多源合同，版本为 finite-products-v0.8.1。旧世界用其冻结版本；新运行时不把旧项目别名采用表当成新版工作绑定。

JSON 内容比较递归检查对象、数组和标量。布尔值不等于数值；有限 int/float 的既有等价保持，无浮点容差。顶层合并仍拒绝同键不同内容，不新增深层合并语义。冲突不以某个文件的值覆盖解决，不挑“正确”文件；正反提交顺序都按明确预期判断。

| 记录 | 语义 |
| --- | --- |
| workspaces[project][alias] | 项目发现入口，仅指一个世界对象 |
| adoptions[work_id::alias] | 一项具体工作/需求版本的采用事实；同alias可被另一工作独立采用另一版 |
| adoption_view | 该工作绑定的fixed/current_published/current_applicable政策目标 |
| submission.adoption_snapshot | 提交时该work的绑定/目标/政策范围，历史保持 |

adopt 需要明确非空work_ids，为各工作创建独立绑定；逐work校验真实对象权限。adopt_version 面向一个具体work_id更新；省略时仅允许一个无歧义当前绑定，新工作人员始终传work_id。旧工作的绑定不因修订而转给新工作；别名继续存在，新工作显式采用，既有上下文字段及历史前缀受转换保持保护。

requirements.input_policy 声明共同政策；input_policies[alias] 可逐输入覆盖；值为一个政策或明确允许列表。input_version/input_versions 可限定fixed精确版本。未声明允许选择，不由评价器事后强制；声明current_published时不能自行改为fixed绕过。current政策采用旧版可以留下可执行错误，但其提交时目标/内容检查仍会失败。

项目包和需求修订都验证政策合同，提交快照与评价再次核对同一声明，不能依赖被测对象自行填一个更宽政策。

## 可重复使用的资料路线

信息路线定义关联稳定work_node，具体请求记录真实work_item_id、requirement_version、证据版本及主体。公开观察按当前义务展开可用路线，工作被修订后可以同route_id发新请求，不复用旧请求或重装项目包。

version_policy 可为fixed、current_published或work_requirement。fixed使用路线声明版；current_published要求存在面向本项目的正式发布版。work_requirement先取该工作input_version(s)中对应object_alias的声明，再在允许current_published时查询正式目标；两者均未给出目标时回到路线声明版。这个后备路径不会把一个尚未发布的版本判作满足current_published合同；实际采用与提交仍受相应政策约束。路线不接受工作人员提供隐藏正确金额。请求时仍验证真实版本与提供者范围。迟到旧请求保存原始回应，但不满足新条件，也不为替代工作授予新的精确版本权限。

需求修订可给旧提交增加superseded_requirements等适用性注记；其固定文件、答案、采用快照与已有正式审阅保持。不能把保持固定历史误写成“所有状态字段完全不变”。


## 阶段 B：发布产生明确工作义务

项目包可安装 `maintenance_rules`。每条规则包含唯一 `rule_id`、来源选择器 `source`、稳定根工作 `work_nodes`、阶段集合 `when`、效果 `effect`、执行主体 `actor` 与有限要求更新 `updates`。来源选择一个对象 ID 或本项目已登记别名，可另核对 `source_project`；不接受自然语言影响分析或回调代码。创建义务的主体必须是该项目参与者，并在每个目标节点持有 `revise_requirement / requirements` 权力。安装阶段还校验更新后的输入政策合同。

下面是在 B 安装时配置的维护示例。`source_object_id` 应替换为当时已经存在的 A 对象身份，不能填一个未来对象占位符。

```json
{
  "rule_id": "refresh-aggregate",
  "source": {"object_id": "source_object_id", "source_project": "A"},
  "work_nodes": ["analysis"],
  "when": ["accepted"],
  "effect": "successor",
  "actor": "manager",
  "updates": {"goal": "使用新发布来源和原固定本地输入重新计算"}
}
```

阶段根据真实状态计算，判定优先级为 accepted、pending、output_ready、after_read、before_read：

| 阶段 | 精确含义 |
| --- | --- |
| before_read | 没有命中以下任何较高优先级事实 |
| after_read | 当前责任者已真实读取该来源，读取记录明确绑定本项目、此 work ID、此 requirement_version，且不早于该义务激活 |
| output_ready | 该工作存在明确绑定同一 work ID／requirement_version 的产物编辑记录；此名称不证明产物完整或正确 |
| pending | 存在真实有效的待审提交 |
| accepted | 制度工作状态为 accepted |

`read_object`、`sheet_read` 以及产物创建／写入／表格修改可显式传 `work_id`。运行时先解析真实项目和工作，按该节点检查需要的权限；编辑上下文要求当前责任者；可读主体可以将读取标记到本项目已存在的工作，但阶段判断只采纳该工作责任者的精确当前版本读取。没有 work 上下文的读写仍可按原对象权限执行，但不能被推断成某项工作的进展证据。

| effect | 合同效果 |
| --- | --- |
| notice | 登记发布影响并向责任者发送声明后果消息；不产生新工作 |
| ignore | 登记 ignored 后果；不产生义务，也不自动改内容 |
| revise | 调用共同需求修订机制，建立替代工作和 work_replacements；旧提交固定内容与审阅保留 |
| successor | 仅允许 when 为 accepted；创建独立后继义务，原工作继续保持 accepted，而非被改成第二轮开放状态 |

`updates` 只允许 `goal`、`visible_requirements`、`requirements`。这些字段采用顶层替换：若只更新 goal，其余合同继承；若声明 requirements，则替换整个要求映射，配置者必须保留仍需要的政策。规则不能增加权限、凭据或任意文件副作用。

发布记录形成时，内核捕获匹配规则、当前工作、阶段和来源版本，然后安排独立的 `maintenance_impact` 事件。规则只检查该 release 声明的目标项目；未匹配的来源／阶段不会自动创建工作。影响身份由 release ID、项目、规则 ID 和稳定目标节点决定，保存在 `maintenance_impacts`。重复发布同一精确发布事实不再次安排后果；重复事件交付复用已有登记。若目标已被需求替代，事件记录 stale_target；若项目已不活动，记录 project_inactive，不默默改投另一工作。

后继工作 ID 由发布与规则身份确定，保存 `previous_obligation_id` 和 `maintenance_trigger`。它继承原工作责任者、稳定 node、输入／交付合同、前驱和制度政策，并清空提交、编辑及条件缓存；需求版本在同一节点下递增。项目 `maintenance_heads` 让后续发布找到该谱系的最新维护义务。采用绑定没有继承或转绑，后继责任者必须针对新 work ID 显式采用；新产物也由工作人员实际制作。原批准不追溯改判。

命令提交与影响事件提交沿用共同单写者运行器。事件的固定 payload 不依赖重跑工作人员策略，失败事件保留独立错误与可恢复队列；这仍是单世界目录的有限提交协议。

## 阶段 B：有限多源内容合同

`finite-products-v0.8.1` 增加 `json_linear_sources`。以下是一项外部来源加固定本地量的完整内容检查，可置于 `deliverable_contract.content_checks`：

```json
{
  "kind": "json_linear_sources",
  "path": ["total"],
  "constant": 0,
  "sources": [
    {
      "alias": "external",
      "kind": "json_field",
      "source_path": ["rate"],
      "reference_path": ["sources", "external"],
      "coefficient": 1
    },
    {
      "alias": "local",
      "kind": "json_field",
      "source_path": ["offset"],
      "reference_path": ["sources", "local"],
      "coefficient": 1
    }
  ]
}
```

对应公开要求可声明：

```json
{
  "input_policies": {"external": "current_published", "local": "fixed"},
  "input_versions": {"local": "v1"}
}
```

sources 必须有 2 至 8 个不同 alias；每项读取 JSON `source_path` 或 XLSX `sheet/cell`。coefficient 默认 1，constant 默认 0，均须是有限数值且不接受布尔值。来源值和实际 total 同样不做字符串／布尔数值转换。期望值按声明顺序用 Python 标量计算 `constant + Σ(coefficient × source_value)`，没有表达式执行或浮点容差；计算溢出是失败检查。XLSX 只读固定版本中已持久化的值缓存，评价器不调用被测表格计算引擎。

每个来源分别校验提交快照中的 work ID、requirement_version、项目、alias、采用版、政策及提交时目标。正文来源引用须匹配采用的精确版本，实际来源字节须匹配已提交哈希。贡献 total 的文件必须声明每个来源依赖；仅贡献某个来源引用的文件必须声明该来源依赖；与本检查无关的交付文件不被强迫增加无关依赖。

单文件 `{total, sources}` 与两文件 `{total}`／`{sources}` 都是合法组织；后者按原有顶层字段并集组合，不增加嵌套深层合并。类型冲突仍使用阶段 A 的递归 JSON 比较处理。同样正确的文件布局不是唯一实现路径。

上游独立质量、下游对已发布接口的忠实性和总体业务目标分别记录。例如外部目标为 20、本地固定 3，而上游错误发布 40 时，下游如实计算 43 可以满足接口合同，但不满足总体目标 23。多个派生结果受同一错误来源影响，不能自动算成多个独立能力缺口。

## 阶段 B：资料可用性与实际继续

合法提供者可调用 `set_information_availability(route_id, available, reason)`。运行时要求调用者是路线声明的 provider，并持有该工作节点／对象／purpose 的 provide 权力；变化增加 `availability_revision`、追加 `information_updates` 并发送公开消息。相同可用性重申不制造新版本。此行动只改变路线状态，不直接创建内容、授予读取、解决阻塞或修改既有回应。

责任者从公开观察发现路线可用性版本改变后，对确切当前工作重新 `request_information`。请求保存 route revision、work ID、需求版本与所选对象版。可用路线的新请求会将同一工作、同一路线较旧 availability revision 的未满足条件标为 superseded，并建立新的条件；实际可用回复按路线与版本权限授予相应读取；条件是否满足仍由独立回应检查决定。单纯改变 availability 不算已取得资料或条件已解决。旧 unavailable 或迟到回应留在原请求历史中。

## 阶段 B：公开持续工作人员

`ContinuousWorker` 接收一个或多个不透明公开 port；每个 port 仅暴露 `tools()`、`observe()`、`call()`。调用方负责将 port 绑定到正确主体与项目。工作人员按端口和工作轮转，每次 step 至多进行一个真实工具调用，进度以 port label 与精确 work ID 为键。它从观察识别责任工作、当前替代、后继工作、正式目标、路线、条件和可提交性，不读取 WorldCore、Store 或隐藏规格。

有限策略支持一项来源对应检查或一项 `json_linear_sources` 检查；它通过公开信息显式采用、读取、计算并制作一个组合 JSON。支持的合法两文件组织由 P3 机制驱动另行覆盖，不等于此策略会自行选择多种布局。批准仍由有权主体执行；工作人员看到待审提交时报告 submitted，不自行制造审批。旧 `PublicWorker` 保留其单工作阶段边界，不能用它的 waiting 含义替代新持续策略的结果枚举。

| 结果 | 含义 |
| --- | --- |
| worker_waiting | 策略暂不能继续，例如缺路线、缺工具、目标不明确或合同不在其支持范围；单独记录 capability_gap |
| world_blocked | 公开世界确实存在该工作未满足／不可用条件；与仅由策略选择等待分开 |
| budget_exhausted | 本次额外工具调用预算用完；并非世界不可完成，之后可继续 |
| environment_error | 公开接口异常或真实工具拒绝，保留异常／返回；不能归为合理等待 |
| submitted / completed | 已提交待制度审阅，或公开状态已接受；不是独立内容质量标签 |

等待某项资料不会阻止调度其他端口或工作。工作人员记录当时真实 tools、观察、调用参数、request_key 与原始返回，后来的状态不能回填早先观察。路线可用性变更、正式需求修订或新维护义务可使后续观察发现新的可执行工作。

`ContinuousWorker.snapshot()` 深拷贝公开进度、精确来源缓存、任务、轮转位置、调用序号和 transcript。恢复仅限显式完成的 step 返回之后的 JSON checkpoint，并要求供应端口 label／顺序一致。它不是世界快照，不承诺任意进程终止后的策略 exactly-once，也不验证另一个世界上的同名端口可替换原端口；运行器自己的 command/event 恢复是另一层协议。

## 本版实现边界

本阶段按一个世界、两个项目、单写者交错执行组织实验；不声称并发写者、任意行业、自然语言事件推断或无限任务调度。受限 JSON/XLSX 能力、专业领域合同和工作世界关系仍分层。内容评价没有改为一般专业正确性判断，程序工作人员也不是模型能力或参数训练收益证据。有限恢复只沿用并扩展必要的提交边界，正式切点和结果应以实验报告为准。
