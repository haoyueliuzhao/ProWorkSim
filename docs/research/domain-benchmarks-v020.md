# v0.20 同领域来源与外部评价准入

日期：2026-09-27。机器清单为[benchmark-registry.json](../../examples/id-vtdo-v20/benchmark-registry.json)，本地固定官方源码/元数据清单保存在 `runs/assets/domain-v020/`。本次只读核查和静态解析，没有外部模型、模拟用户、评审API、Docker角色运行或benchmark得分。目录名与上游技术split不替代本项目用途划分。

| 对象 | 实际核查 | 本项目用途/状态 |
|---|---|---|
| TeamBench | 固定源码 `d185aef1916fd86a9ba554d581fd256319a973af`；预定领域规则识别12个候选家族，有限读取D1/D2/D3元数据和D1执行器 | 角色交接与独立复核候选；已检查的开发家族不能直接变成锁定任务，正式准入0 |
| Mini-Interact a-Interact | 源码 `451fe2c3518ee1cf908d8139e2913483bd519381`；数据 `088b3787303e69129e395a9f712902670339ef72`；实际300条公共任务、26个被引用数据库 | 信息澄清与依据使用候选；非空sol_sql和test_cases均0，尚无完整官方评价资产 |
| Co-Gym Tabular Analysis | 固定源码 `58972c0702412f293e303c3e49b6cc896db2467a`；AST静态解析为110个query项、4个数据家族 | 共享分析候选；尚未固定伙伴/语义评审和原生执行环境 |
| BIRD-Critic-SQLite | 固定公开500条；与Six联合谱系/重复核查已执行 | 个体SQL能力和退化控制；不是协作主指标，完整官方评分未准入 |

表中的候选家族、query项、任务行、种子和独立来源各是不同单位；没有把12个家族直接称为12个已冻结外测任务。前三个仓库的内容取得包含一次raw端点TLS失败及部分contents路径404；随后使用固定Git对象读取，未取得的D3 spec明确记unavailable，没有生成缺失内容或因此运行模型。

## TeamBench：领域筛选与来源风险

预定筛选限定实际数据工作对象：`D1–D9`（schema/data quality/pipeline/reconciliation）、`SQL1/SQL2`、`CROSS2_schema_evolution`，共12个家族。规则在目标模型评分前制定；没有为凑数加入其他软件或事件响应任务。已读取D1完整需求、简要需求、元数据及种子感知grader，D2需求与元数据，D3仅元数据。它们属于接口开发暴露；后续锁定子集应排除这些已用于接口修改的家族及其种子派生物。

官方入口是原生`harness.ablation`，支持自己的`ToolCallAdapter`或兼容接口；完整需求、工作空间修改和验证权限按角色隔离。D1实际grader检查ETL结果、列映射、去重和attestation，但仅存在grader并不证明当前系统已完成OS角色隔离或当前模型验证者职责。因此本轮没有运行mock来伪装模型成绩，也没有脱离原生隔离把host直接评分称为TeamBench协作评价。[官方入口及角色约束](https://github.com/ybkim95/TeamBench/tree/d185aef1916fd86a9ba554d581fd256319a973af)

官方数据目录明确包含UCI Online Retail，下载器还允许部分来源退回synthetic placeholder。故TeamBench不能按benchmark名称直接计为独立于本项目UCI的新来源；运行前须核定实际文件是原始数据还是合成替代，记录原数据库/表与模板派生关系。[官方数据目录](https://github.com/ybkim95/TeamBench/blob/d185aef1916fd86a9ba554d581fd256319a973af/datasets/README.md)

本轮把“现有UCI接口开发”与“TeamBench Online Retail派生锁定候选”作为一对真实来源声明送入谱系检查，返回跨用途冲突且后者谱系未完整。该负控只支持这个已知重合的隔离，不是所有TeamBench任务污染检查已完成。仓库MIT与数据上游许可分别保留；不能因代码MIT推断所有数据可无条件再许可。

## Mini-Interact：公共接口可查，隐藏评分仍缺失

实际取得300条公共记录，不仅查看数据卡计数。`sol_sql`、`test_cases`字段虽然存在，但均为空数组；不能把字段存在当作已拿到答案/测试。26是这些公共记录引用的数据库数量，不是本轮下载或执行了26库。数据卡为CC BY-SA 4.0，公共jsonl的上游split名为dev，本项目没有因此默认把它用于训练。[固定官方数据卡](https://huggingface.co/datasets/birdsql/mini-interact/blob/088b3787303e69129e395a9f712902670339ef72/README.md)

上游当前Mini设计仅覆盖SQLite SELECT、知识歧义与首阶段澄清，没有把后续查询或CRUD能力算入覆盖。它由BIRD-Interact/LiveSQLBench的上游任务派生，后续须追踪祖先任务，不能与相关训练材料按新ID简单划分。完整GT/测试应按官方取得流程处理；本轮未发送索取邮件，也没有调用模拟用户。[官方Mini范围](https://github.com/bird-bench/BIRD-Interact/blob/451fe2c3518ee1cf908d8139e2913483bd519381/mini_interact/README.md)

原生a-Interact位于`mini_interact/knowledge_based/mini_interact_agent`，原生入口使用用户模拟器；本研究后续须冻结其配置与交互预算，再仅替换目标工作模型。公开记录里的masked SQL知识、参考答案和测试需按原角色投影留在host/模拟用户侧，不能整行塞给目标模型。当前还缺完整评分资产、冻结伙伴配置/额度和原生目标模型适配，成绩保持null。[官方原生入口](https://github.com/bird-bench/BIRD-Interact/blob/451fe2c3518ee1cf908d8139e2913483bd519381/mini_interact/knowledge_based/mini_interact_agent/README.md)

## Co-Gym：共享分析和语义评价单列

固定代码的`DISCOVERY_BENCH_DATAPOINTS`经AST literal解析，110个query项来自4个家族：`introduction_pathways_non-native_plants`、`archaeology`、`meta_regression_raw`、`worldbank_education_gdp_indicators`。未import其运行模块，以免初始化Jupyter或评审模型。它们是DiscoveryBench-Real派生项，不能按110个query宣称110独立来源。[官方数据关系](https://github.com/SALT-NLP/collaborative-gym/blob/58972c0702412f293e303c3e49b6cc896db2467a/datasets/README.md)

原生`CoAnalysisEnv`共享Jupyter历史和分析文稿，额外领域知识与完整元数据供伙伴。实际代码含语言模型对假设的语义评价，不能描述成全由独立数值重算评分。固定伙伴、judge模型/版本/提示和API额度以及全部表/metadata/gold尚未完成，本轮不以DeepSeek静默替换官方评审，也不执行外部调用。[固定执行与评分代码](https://github.com/SALT-NLP/collaborative-gym/blob/58972c0702412f293e303c3e49b6cc896db2467a/collaborative_gym/envs/tabular_analysis.py)

## Six/Critic与四用途闭包

[SQLite P0报告](../experiments/sql-source-v020-p0.md)给出真实3例程序控制，以及Six 5000/Critic 500公开记录的精确重复核查。两源不同数据库ID与SQLite SHA仍存在3个联合题面指纹、5个跨源任务配对。所有精确重复至少随祖先整体隔离，仍需语义近重复和模板谱系检查。

四用途依次为接口开发、策略训练、贡献开发、锁定评价，先划原数据库/表/模板/祖先及其派生物，再做采样。共享检索、角色笔记、示例和准备资产随原用途。`source_partition_audit`检查给定谱系的传递冲突，未知不会自动准入；它不声称自动发现未知祖先。

本轮外部benchmark实际模型运行数与成绩均为0/未测。现有UCI只能作同源验证；CPU程序见证不是目标模型经历或SFT。最终子集、伙伴/评审、初末checkpoint和总预算尚需冻结，不能将四项候选组合当作已经完成的迁移结论。
