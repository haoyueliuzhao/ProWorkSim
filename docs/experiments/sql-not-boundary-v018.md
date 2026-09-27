# E1：NOT括号表达式的窄修复与真实工具核验

本项将词法误分类推进到真实WorldCore和DuckDB证据。旧H1冻结源 `6763677` 保持原样，不改变任何运行中的SQL支持、输出、奖励或样本分母。新的执行器标识为 `managed-duckdb-v0.18`。

## 改动范围

旧 `FUNCTIONS` 混合了函数与AS/AND/OR等括号前的语法词。新代码将原有语法词单列为 `PARENTHESIZED_SYNTAX`，并只增加NOT；函数白名单没有新增函数。函数候选仍扫描整段去除字面值/注释后的SQL，NOT括号内的受限函数不会被跳过。

单SELECT/CTE检查、禁止写语句、禁止外部文件/扩展访问、固定子进程和全部资源上限未改。没有关白名单、使用通用SQL框架或让harness自动改写SQL。此修复改变允许通过的表达式集合，属于新阶段执行语义，不能当作对旧样本无影响的勘误。

DuckDB官方文档说明 `NOT LIKE` 与对LIKE结果应用NOT等价，并说明AND/OR/NOT采用包括NULL的三值逻辑；这里使用真实DuckDB 1.5.5核对，而非将文档或SQLite结果当成本项目执行结果。[模式匹配](https://duckdb.org/docs/current/sql/functions/pattern_matching)、[逻辑运算符](https://duckdb.org/docs/current/sql/expressions/logical_operators)。

## 原反例与修后公开路径

固定8行人工票号/数量/价格素材，包括普通和取消票号、大小写/空格、空字符串、NULL票号、NULL数量、NULL价格、0数量和0价格。两对表达式分别覆盖：

- `NOT (LOWER(TRIM(InvoiceNo)) LIKE 'c%')` 与 `LOWER(TRIM(InvoiceNo)) NOT LIKE 'c%'`。
- 带嵌套括号、OR/AND、数量条件和 `UnitPrice IS NULL` 的等价组合。

每个表达式都经过真正的 `WorldCore.session.call("sql_query")` 和 `sql_build`，得到实际子进程结果及不可变版本；查询与构建使用相同SQL文本。语句输出布尔列而非只做WHERE过滤，因此保留并比较NULL结果。

| 同一固定控制 | 冻结旧源 | 修后新源 |
|---|---|---|
| 两个NOT括号版本，各query/build | 4次均为 `execution_error / allowlist:not` | 4次均成功 |
| 两个等价NOT LIKE版本，各query/build | 4次均成功 | 4次均成功 |
| 两对表达式、两公开路径结果 | NOT一侧被拒，不能比较为相等 | 每对4个结果逐行完全相等，NULL保持 |

原失败是工具执行结果中的失败：世界命令记录 `ok:true` 不意味着SQL执行成功。原失败结果及新成功结果分别保存在新建的诊断world中，没有修改历史H1 world。原数据源、代码及查询/构建输出均有真实版本与WorldCore回执。

7项必要公开负对照仍为execution_error：外部CSV简写访问、read_csv函数、LOAD扩展、COPY外部写入、多条SELECT、未支持函数及SQL字符上限。外部哨兵文件未变，写入目标不存在。补充回归还确认 `NOT(read_csv(...))` 不能隐藏内部禁用调用，引用的 `"not"(...)` 不被当作允许函数。有限控制不等于穷尽的安全证明。

## 原H1完整SQL的独立诊断

从27B首个native窗口slot-0/slot-1原失败结果的 `execution.code_reference` 和 `source_references` 读取不可变代码与确切typed inputs。逐文件核对原SHA，原样传入修后隔离DuckDB执行器；不运行工作人员、不调用独立业务评价，也不产生替代H1成绩。

| 原H1片段 | 原保存结果 | 修后原完整SQL、原输入的独立重演 |
|---|---|---|
| slot-0 / f0实现 | allowlist:not | 词法检查后出现TIMESTAMP与VARCHAR比较的BinderException |
| slot-1 / f1实现 | allowlist:not | 执行success；**业务正确性未评价** |

这一区分保留其他实际问题：解除NOT误拒不保证完整SQL可执行；可执行也不保证符合业务合同，更不意味着模型当时构建或提交成功。原两片段的R=.2不变。输入与SQL没有改写，所有原H1文件SHA在诊断前后相同。

本诊断使用项目Python3.14.6和DuckDB1.5.5；原H1使用独立Python3.12 resident环境及同版本DuckDB。本结果是新的CPU局部诊断，不冒充原进程重演或模型实验。

## 核验、来源与限制

必要测试命令：`.venv/bin/python -m pytest -q tests/test_sql_boolean_v018.py tests/test_sql_query_adoption_v11.py`，4项通过（4.60秒）；相关Ruff通过。没有重跑全库、GPU或模型。

- 原反例与原source快照：`runs/sql-boolean-v018-before/`。
- 修后公开工具与两条原SQL诊断：`runs/sql-boolean-v018-after/`。
- 冻结旧执行器SHA256：`fc3d039c914af24882fb761fcffce500162a78baba02186f2a64ad41db53d4e3`。
- 修后执行器SHA256：`a459ada0301beffde2ff0838a3cc7538e4e308df699a113b2a04a1ba920928e6`。
- [结构化记录](sql-not-boundary-v018.json)保存原/新完整报告、每次工具调用、真实world state、原H1代码/输入、重演结果及测试日志的路径和SHA。

资源上限仍为8秒wall、4秒CPU、128MB、每表5,000行、64列、8模型、12测试和20,000字符SQL。该识别器仍是明确有限的词法策略，不是完整SQL语法兼容层；本次只为NOT这一已复现根因提供真实路径验证，不声称所有合法SQL变体都已支持。
