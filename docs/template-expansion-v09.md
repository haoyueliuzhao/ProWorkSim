# v0.9：由两种工作结构推动的模板扩展

本文记录实现合同和归属，不预先宣称正式实验结果。实测结果、冻结身份、开发失败与限制另存于本轮实验报告。v0.8 的多项目世界、不可变版本、精确采用、发布及维护义务继续作为基础；新模板增加集合核对和针对实际交付的定向审阅。

## 1. 实现归属与边界

| 需要表达的需求 | 实现位置 | 处理方式 |
|---|---|---|
| 两张资料表、角色、批准方式、信息路线 | `templates/reconciliation.py` | 公开项目配置；资料与人工真值明确为合成 |
| 行集合匹配、期间／定义／币种适用性、单位换算 | `domains/reconciliation.py` | 有限领域合同和只读内容评价，不写世界状态 |
| 报告章节、公开 claim 范围和初始背景 | `templates/research_review.py` | 公开项目配置，不制造已发生的审阅历史 |
| 正文数值、期间、趋势和引用关系 | `domains/research_review.py` | 对声明章节的实际正文和结构化元数据分别核验 |
| 实际 JSON 内容的位置、确切版本读取证据 | `adapters/locations.py` 与 WorldCore 适配入口 | 有界 JSON 键／数组索引定位；校验可读、已读和位置存在 |
| 问题定位、回应、制度处理决定 | `core/issues.py`、行动投影和转换约束 | 两模板共用的追加事实与批准约束，不含模板名称分支 |
| 何时请求资料、匹配记录、修复何处 | `workers/` | 程序策略，只接收公开端口；判断错误不由后台修答案 |
| 工具拒绝的事实与有限归因 | `tool_outcomes.py`、运行器的已知边界 | 保存真实返回；仅在有明确依据的边界声明原因 |

本轮文件能力仍为现有 JSON／受限 XLSX。两个新领域合同读取 JSON，没有新增 PDF、Word、OCR 或完整数据库能力。财务字段与报告句式留在领域层，未成为世界内核固定本体。

新的 WorldCore 状态／运行器使用 `world-core-v0.9`，语义版本为 `work-world-v0.9`，内容评价版本为 `finite-products-v0.9`。旧的经营／出版单项目运行时仍保持原 `v0.5` schema，不能把其运行结果记为新世界结果。旧世界数据不通过静默兼容重写进入新 schema；应使用对应冻结运行时或明确受信检查点流程。

## 2. 财务资料核对合同

公开项目提供两张有限表和一份公开口径。每个源记录具有：

```json
{
  "record_id": "L3", "entity": "Acme", "metric": "cost",
  "period": "2026H1", "definition": "net", "currency": "CNY",
  "unit": "ones", "value": 80, "location": "records/2"
}
```

口径声明匹配键 `entity / metric`、`reporting_period`、`base_unit` 与正有限的 `unit_factors`，例如 `{"ones": 1, "thousands": 1000}`。两表中每条记录 ID 在本表唯一；同一业务键存在多个候选记录时保留为歧义，不自行去重或挑选一条。

内容检查的公开结构为：

```json
{
  "kind": "reconciliation_table",
  "path": ["reconciliation"],
  "left_alias": "ledger", "right_alias": "statement", "policy_alias": "definitions",
  "sources": [
    {"alias": "ledger", "reference_path": ["sources", "ledger"], "data_path": []},
    {"alias": "statement", "reference_path": ["sources", "statement"], "data_path": []},
    {"alias": "definitions", "reference_path": ["sources", "definitions"], "data_path": []}
  ]
}
```

`data_path` 指明实际 JSON 内容位置，空数组表示根对象。变体把两表放入 `appendix`、口径放入 `basis`，策略和评价均从公开声明定位，而非依赖固定文件名。公共评价入口另外检查每个源的精确工作采用、提交时政策目标、不可变文件内容，以及实际贡献交付文件的源依赖。`data_path` 不替代这些版本与权属检查。

交付包含 `reconciliation` 和 `sources`。每个业务键恰有一行，覆盖两表记录的并集。下列行表示真实冲突，不表示某一侧是真值：

```json
{
  "key": ["Acme", "cost"], "period": "2026H1", "status": "conflict",
  "left_ids": ["L3"], "right_ids": ["R3"],
  "left_value": 80, "right_value": 90, "delta": -10,
  "evidence": [
    {"alias": "ledger", "record_id": "L3", "location": "records/2",
     "period": "2026H1", "definition": "net", "currency": "CNY", "unit": "ones", "value": 80},
    {"alias": "statement", "record_id": "R3", "location": "records/2",
     "period": "2026H1", "definition": "net", "currency": "CNY", "unit": "ones", "value": 90}
  ]
}
```

六种分类具有固定有限含义：

| 分类 | 规则 |
|---|---|
| `matched` | 唯一两侧记录，期间符合口径，定义／币种相同，单位相同，数值相等 |
| `converted` | 适用性相同，经明确单位因子换算后相等；保留原单位和数值 |
| `conflict` | 可以比较且换算后数值不同，保留两侧值及差值 |
| `incomparable` | 期间、定义、币种或公开单位规则不适用，标准化比较值和差值为 `null` |
| `missing` | 缺一侧记录或可比较记录的值为 `null`，不补零 |
| `ambiguous` | 任一侧同键超过一条记录，完整保留所有候选证据，不选择赢家 |

财务记录的 `location` 是来源声明字段：领域评价核对交付 evidence 与该源字段一致，但不会将任意字符串解析为 JSON 路径并证明它就是当前数组下标。记录定位的确定性来自精确对象版本、公开 `data_path`、源表中唯一的 `record_id` 及全记录覆盖。静态样例使用真实的 `records/下标` 或 `appendix/records/下标`；这不扩大评价器对任意来源位置声明的保证。共享 issue 动作中的 `locator` 则是另一项经过实际 JSON 位置检查的结构化路径。

交付同时给出 `summary` 计数、`unresolved` 键集合、`base_unit` 和 `period`。顶层 `period` 是公开核对范围；行内与 evidence 中仍保存实际期间，跨期行不得因为顶层标签而成为可比。`unresolved` 包含冲突、不可比、缺失和歧义，作为合同允许的不完备结果。两表整体不可得且无法取得时可以保留世界阻塞，不要求伪造交付。

行、候选 ID、证据和未解决项的展示顺序不构成隐藏标准答案；重复项仍保留计数，不能用集合去重掩盖重复匹配。合法交付可以是单份综合 JSON，或完整顶层字段分开的两份 JSON；不做深层拼接，不从冲突文件中选一份赢家。

评价器直接检验提交的集合划分、适用性、精确证据及算术，不调用工作人员 matcher。合成样例的业务期望另用有限手写真值，避免被测匹配算法生成自身答案。这不是通用财务审计、模糊实体匹配、汇率推断或专业充分性评分。

## 3. 研究报告合同与正文范围

报告以 `report.sections` 保存章节，每节有 `section_id`、读者实际看到的 `body` 和结构化 `claims`。公开合同为每个受检 claim 指定唯一章节、标签、来源别名、值路径、期间路径和可选比较基期路径。例如：

```json
{
  "claim_id": "revenue", "section_id": "revenue", "label": "Revenue",
  "source_alias": "dataset", "value_path": ["metrics", "revenue", "value"],
  "previous_path": ["metrics", "revenue", "previous"], "period_path": ["period"]
}
```

有限源值 120、基期 100、期间 `2026H1` 可以支持以下两种完整正文：

```text
Revenue in 2026H1: 120; trend up; source dataset:metrics.revenue.value.
2026H1: Revenue = 120 (up) [dataset:metrics.revenue.value].
```

评价器对受检章节使用完整句式匹配，读取真实正文中的数值、期间、趋势和引用，再分别检查 claim 元数据。元数据正确而正文写 999，或数值正确但正文期间／来源错误，均不能通过。两类句式是明确的有限接口，不能将其识别率解释成自由文稿理解能力。

源值为 `null` 时正文写 `unknown`，claim 状态为 `unresolved`；有值且来源受支持时状态为 `supported`。趋势在基期存在时按数值关系为 `up / down / flat`；缺基期数据为 `unknown`；合同未声明基期关系时为 `unassessed`。开放论证、专业完整性、文风、未受检章节的自由文字继续明确未评。背景章节可以原样保留，局部修复只改选择的 claim 章节。

报告公开工作人员与领域评价器独立：策略从来源构造有限论断，审阅策略读取实际固定交付并检查句子，评价器另解析完整正文。意见可以错误，不能因审阅者有权提出意见便自动将意见变成事实。

## 4. 两模板共享的问题处理关系

世界保存三个追加事实注册表：`issues`、`issue_responses`、`issue_decisions`。公开 `issue_views` 从这些事实派生状态与当前适用性。

| 动作 | 固定联系与前置要求 |
|---|---|
| `inspect_submission` | 返回实际指定工作的固定提交、文件版本和提交快照 |
| `raise_issue` | 绑定提交、确切对象版本和 JSON 位置；提出者有相应 review 权限，并实际读取目标及引用证据 |
| `respond_issue` | 责任工作 owner 回应明确 issue，指向同工作／需求版本的一次实际提交，并给出确切已读证据 |
| `decide_issue` | 有权审阅者读取回应关联的当前固定提交，对这一项回应作 `accept_fix / accept_rebuttal / keep_open` 决定 |

每个动作有明确幂等 key：同一 key、相同内容重试复用原事实；重用 key 改变内容会被拒绝。决定还要求回应确属该 issue，并限制于当前待审提交。跨问题、跨工作或跨需求版本的回应不能混用。

在当前 pending 提交上创建的 blocking issue，对该工作形成批准门槛。同一工作撤回并重新提交不会仅因文件版本变化而自动关闭问题；必须针对真实回应产生处理决定。修复原交付错误使用同一工作、同一需求版本，只有目标或范围本身改变才走需求修订。`accept_rebuttal` 允许依据资料反驳错误意见，意见无需一律转化为修改。

旧提交的意见后来才到达时，保留历史事实而不自动形成当前批准阻塞；旧工作／旧需求版本关系不迁移到新工作。已经解决的问题不能被另一问题的处理动作连带关闭；已解决项若有新缺陷，应形成新的定位问题。正式处理决定仍是制度事实，独立内容评价继续核对实际文件，避免“有权接受”被解释成“内容必然正确”。

公开 worker 使用的读取、编辑、提交与关系动作均经过 WorldCore；实验测量器可以读取后台核验历史，但不能替工作人员改状态或提供隐含正确答案。

## 5. 工具返回与失败归因

`ok=false` 只证明某次公开动作被拒绝。`tool-rejection-v0.9` 保留 `code`、`category`、上下文及原始错误事实。支持的有限类别为 `policy_error`、`business_constraint`、`capability_gap`、`environment_error` 和 `unknown`。

运行器只在拥有明确事实的边界赋予类别，例如实际签名参数绑定、未知能力、世界暂停、未解决审阅事项阻止批准，或者从公开端口逃逸的异常。未覆盖的旧 `ValueError` 不凭错误文字猜原因，保持 `unknown / unattributed_tool_rejection`。工作人员是否等待、世界是否存在持久阻塞、调用预算是否用尽与工具拒绝归因是不同记录。

因此，本轮没有声称为所有非法动作提供完备诊断，也没有将工作人员错误参数或正常业务拒绝一律记为环境实现错误。

## 6. 跨模板接口和可运行入口

核对成果可以作为报告的一个公开来源。例如报告 claim 从 `reconciliation.summary.conflict` 取值，并从 `reconciliation.period` 取核对范围。该接口表达冲突数量，不证明全部财务问题已解决；不可比与未知仍应保留。

跨模板变化通过显式分享、发布、每项工作的采用政策及声明维护规则传递。控制器正常更正和发布 A 的材料，规则产生相关义务，工作人员在公开观察中发现工作并继续交付；控制器不直接编辑 B 的报告或代造缺陷。固定历史工作另保留其源版本与原有成果。评价分别记录 A 核对质量、B 对接口的忠实性、B 正文表达正确性和总体业务目标；同一个上游错误的传播不是多个独立根因。

[静态示例与命令](../examples/templates-v09/README.md)提供同世界两个独立项目的最小运行入口。程序策略可从 `workers.reconciliation` 和 `workers.research_review` 导入，不只存在于实验驱动内。此示例不等于完整跨模板实验，也不替代冻结版本上的正式机制验证。
