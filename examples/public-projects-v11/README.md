# 公开可执行项目群：有限 DuckDB 原型

本例固定使用 [dbt-labs/jaffle_shop_duckdb 的 36bde6c 提交](https://github.com/dbt-labs/jaffle_shop_duckdb/tree/36bde6cba69d962b83be1d52fc65a0dce1cb4ebb)。原始 CSV、SQL、schema、README 和 Apache-2.0 许可证保存在 `upstream/`，每个文件的原始字节摘要见 `source-manifest.json`。数据为官方虚构电商样例：100 位客户、99 笔订单和 113 条支付。原仓库不提供完整企业 PR／CI 流程；本项目添加的四项目分工、任务合同、权限、沟通和需求变化均为研究设计。

运行基础是固定版本 DuckDB 1.5.5。这里执行真实 SQL、建立数据库、运行可编辑测试及查询；没有运行完整 dbt CLI，也没有宣称任意 dbt 宏、依赖包、生产数据库或任意命令行兼容性。

| 项目 | 公开工作合同 | 实际依赖 |
| --- | --- | --- |
| P0 数据准备 | 将全部客户、订单、支付行按声明列名整理，保留整数支付分 | 固定官方原始输入 |
| P1 经营指标 | 仅计 completed 订单；先按订单合并支付，避免多支付记录放大订单数；保留零收入客户 | P0 的发布表和 P2 的接口要求 |
| P2 客户分析 | 保留指标中的客户／期间键和收入，连接客户姓名并按有无已完成收入分组 | P0 客户表、P1 指标、P2 的接口要求 |
| P3 集成核验 | 两侧分别汇总再核对金额、差值和客户行数 | P1 指标、P2 分析及相同接口要求 |

初始接口要求是客户粒度，因此 P1 可以先发布、P2 再使用；没有相互等待对方最终完成的循环。动态场景在初始四项工作接受后，按预先声明的事件将 P2 的要求改成客户×自然月粒度。P1、P2 及 P3 分别承接新工作。月份集合是原始订单中出现的四个月；月度指标和客户分析分别应覆盖 100×4 个键。

P2 的同事策略以另一个绑定在 P1 的公开端口工作，实际读取旧指标的固定提交和新发布要求，再对缺少 period 的具体 columns 位置提出意见。这不是独立评价器生成的提示，也不关闭或否认旧接口在原需求下的历史接受。P1 根据新公开要求编辑 SQL、执行并发布；后续产物采用各自工作中固定的新来源版本。事件控制器仅写入和发布 P2 的要求文件，不修改 P1/P2 SQL、结果或评价。

## 受管 SQL 能力

每个项目的 `code` 别名是一份可版本化 JSON 文件，其内容直接包含可执行 SQL：

```json
{
  "models": [{"name": "example", "sql": "SELECT customer_id FROM customers"}],
  "tests": [{"name": "no_null_id", "sql": "SELECT * FROM example WHERE customer_id IS NULL"}],
  "config": {"exports": ["example"], "description": "公开用途说明"}
}
```

员工通过已有 `read_object`／`write_object` 阅读和修改 SQL、测试与配置，再调用：

- `sql_build(work_id, code_alias, output_alias, input_aliases)`：输入必须已经采用到该具体工作。宿主读取固定版本，将模型和测试投影为实际 `.sql` 文件，在新 DuckDB 中加载真实输入、建立模型并执行测试。测试以返回的失败行为依据；零行为通过。
- `sql_query(work_id, source_alias, sql, output_alias)`：从来源版本的实际逻辑表重建数据库，执行一次查询，将实际查询结果保存为新版本。

`sql_project` 公开要求分别限定代码、构建输出和查询输出别名。执行需本人工作及 `execute_sql` 权限；不会借构建动作覆盖另一份未经声明的对象。读取来源不会自动建立采用关系。提交必须使用 `code`、`result` 等工作区别名，并固定实际执行过的代码与结果版本。

构建错误也会形成实际结果版本。例如初始 P1 SQL 引用不存在的 missing_amount，真实 DuckDB 返回 BinderException；员工可以读取错误、修改 SQL 再构建。规则基线确实保留该失败后再修复。模型策略没有调用规则 SQL 生成器代写答案。

结果文件的 `test_results` 保存每项测试的实际通过值和失败行；`files` 保存实际执行文件文本；`tables` 保存实际数据库输出的列及行；`execution` 保存精确代码／输入引用。数据库是受控派生物：没有作为额外可变事实留在工作区；从已提交代码、输入版本和逻辑表可以重建。这里不承诺重建后 `.duckdb` 二进制字节完全相同。

执行版本另有由 WorldCore 写入的 `execution_provenance` 元数据。员工将结果 JSON 复制或改写到新版本不会获得该元数据。独立评价要求提交的代码与真实执行引用一致，并从采用的原始输入独立计算有限业务结果；可编辑测试的绿色状态不替代独立检查。等价 SQL 的行序和列序不作为评分目标。

## 执行边界

仅支持一条 SELECT／CTE、有限的未引用内置函数、标量列和显式类型表。函数名单由执行器公开常量约束；引用函数名被拒绝，正常引用列名可以使用。外部文件函数、ATTACH、COPY、INSTALL、LOAD、PRAGMA、可变 SQL 和多语句不属于能力。DuckDB 还独立关闭 external access 和扩展自动加载／安装。员工没有宿主 Shell、网络、控制区、API 密钥或隐藏评价器的查询入口。

每次子进程使用清理后的环境和新临时目录，固定为 1 个数据库线程、128 MB DuckDB 内存、4 秒 CPU、8 秒墙钟；每表最多 5,000 行、64 列，最多 8 个模型、12 个本地测试，每条 SQL 最多 20,000 字符。超界不静默截断为成功。以上是有限 SQL 接口及实际拒绝检查，不是允许任意恶意 Python／原生扩展的通用隔离保证。

## 运行与证据

`static.json`、`dynamic.json` 可由通用 `scenario-build` 和 `staff-run` 使用；`P1` 是可替换为模型的经营指标角色，其他角色可保持固定规则策略。公开任务要求完整列出了独立验证所用的期间、状态、键、金额、零值覆盖和输出字段规则，没有隐藏附加业务要求。

```bash
.venv/bin/proworksim scenario-build runs/public-project-demo --spec examples/public-projects-v11/dynamic.json
.venv/bin/proworksim staff-run runs/public-project-demo --output runs/public-project-demo-run.json
.venv/bin/python scripts/executable_project_experiment.py --output runs/public-project-repeat --workers 3
```

脚本分别保留静态／动态链、等价 SQL、非等价业务 SQL、实际篡改本地测试和伪造结果版本。它们是规则可行性和明确程序负对照，不是模型成绩；API pilot、批量模型运行与训练收益应另行报告。
