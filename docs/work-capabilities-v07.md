# v0.7 工作能力与成果使用：实现说明

依据：[审计](reference/work-capabilities-audit.md)和[两阶段计划](work-capabilities-v07-plan.md)。本文件随两个阶段分别收口；正式结果独立归档，不将开发试跑与冻结实验混计。

## 阶段 A：权限路径与共享文件能力

WorldCore 新状态格式为 `world-core-v0.7`，工作语义为 `work-world-v0.7`，阶段回执继续沿用 `phase-deltas-v0.5`。不隐式重写旧 v0.6 世界；其历史格式和发布政策使用对应冻结版本解读。

同项目的基础 ACL 与精确分享共同决定读取。分享一个版本不会将接收者加入全版本 readers；其他版本、其他人仍独立检查。初次采用及采用更新都从可信项目上下文解析对象和工作集合，逐工作传递真实 object_id。初次跨项目采用在确认实际精确可读后，以仅含候选别名的只读权限上下文核对既有授权，不增加权力。fixed 政策、错误项目/对象/工作与不可读版本继续拒绝。

`adapters.capabilities` 是有限能力注册表，目前只支持：

| kind / application | 工具与数据 | 边界 |
| --- | --- | --- |
| json / files | create_object、read_object、write_object；data 为 JSON object | 受控别名与相对文件名 |
| xlsx / spreadsheets | create_object(kind=xlsx)、sheet_read、sheet_update、sheet_recalculate | 复用现有 Spreadsheet 的有限公式、范围与规模限制 |

WorldSpec.applications 明确启用能力。工具发现和实际准入使用同一能力选择；`ProjectSession.tools()` 返回参数定义，scope 和身份仍由会话绑定，不进入工具参数。未启用表格能力时不会展示或执行 sheet 工具。

项目包初始对象与工作人员动态创建使用相同编码、Store 与世界级对象身份。XLSX 在受控空间内保存真实字节，编辑和重算生成不可变版本。ZIP 时间戳与文档创建/修改时间规范化，使同一输入重试有稳定序列化；单元格、公式及错误缓存不在比较时删去。`=1/0` 等错误是可以落盘的工作错误，不被当成不合法文件操作。

### 固定提交的独立评价

工作合同可声明 `allowed_kinds`、`allowed_roles`、文件数量及 `required_fields`，再选择有限 `content_checks`：

- json_field_equals：实际 JSON 字段与明确标量比较。
- xlsx_cell_equals：不可变工作簿中指定单元格缓存与明确标量比较。
- xlsx_no_formula_errors：实际公式缓存不可缺失或为错误值。
- json_matches_source_cell / json_matches_source_field：JSON 的正文来源引用、实际数值与提交时采用的精确输入接口一致。

评价通过 version_path 读取固定提交版本并核对 sha256，不从当前镜像或隐藏正确模型读答案，也不调用被测公式引擎生成期望。内容评价不反向写入 review 或修复产物。来源接口核对只说明 B 与所消费成果一致；A 的计算是否正确需要自己的独立合同。

提交另保存 adoption_snapshot，包括明确采用版本与提交时政策目标，受历史保持检查保护。后续采用或发布不能改变旧提交的判据。当前字段齐全或 adoption_view=current 不能替代正文和输入关系检查。

## 使用示例

```python
from proworksim import WorldSpec
from proworksim.world_core import WorldCore

world = WorldCore.create("runs/capability-demo", WorldSpec(
    world_id="capability-demo", actors={"operator": {}, "worker": {}},
    applications=["files", "spreadsheets"],
    bootstrap_grants=[{"actor_id": "operator", "power": "*", "scope": "world"}],
))
# 项目包通过operator的install_project装载；工作人员使用绑定项目会话。
# create_object(kind="xlsx", alias="analysis", filename="analysis.xlsx",
#   data={"Report!A1":10,"Report!A2":4,"Report!A3":"=A1-A2"},
#   deliverable_role="model")
# sheet_update(alias="analysis", cells={"Report!A1":12})
# sheet_read(alias="analysis", version_id="v2")
```

本阶段不接入 GUI、宿主 Shell、任意插件或全部 Excel 函数。金融期间、单位、允许假设及指标定义仍由领域合同描述，不能成为通用世界分支。真实材料来源的四种标记与不得捏造过程历史的要求继续保持。
