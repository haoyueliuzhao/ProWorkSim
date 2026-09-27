# v0.20 SQLite 来源 CPU 准入实验

本实验完成了 **3 个 Six-Gym SQLite 开发样例的实际初始化、错误区分与合法修复程序见证**，共 33 项控制通过。它只证明这一有限接口具有可行路径和区分能力；没有模型调用、GPU 调用、训练样本或参数更新，不证明当前模型支持、成员协作能力或学习收益。其他并行实验的状态不由本报告推断。

机器可读归档：[sql-source-v020-p0.json](sql-source-v020-p0.json)。完整本地原始记录位于 `runs/sql-source-v020-p0/`，原始报告 SHA 和每例动作、原生执行、私有参考、独立计算结果的路径及 SHA 均收入归档。公开来源文件保存在忽略目录 `runs/assets/sql-v020/`，没有将约 14 MB 的任务文件或数据库提交进仓库。

## 1. 官方来源、版本与取得范围

| 来源 | 固定提交 | 公开记录 | 数据库数 | 公开字段边界 |
|---|---|---:|---:|---|
| Six-Gym-SQLite | `d603cc8af5294bb75415b8137d362080dab01bfd` | 5,000 | 13 | 包含 `sol_sql`、Python `test_cases` |
| BIRD-Critic-SQLite | `af2b1c3e2f8b3480e5569212198761c770df06d0` | 500 | 15 | 公开 JSONL 无 `sol_sql`、`test_cases` |

依据是 [Six 固定版本官方数据卡](https://huggingface.co/datasets/birdsql/six-gym-sqlite/blob/d603cc8af5294bb75415b8137d362080dab01bfd/README.md)、[Critic 固定版本官方数据卡](https://huggingface.co/datasets/birdsql/bird-critic-1.0-sqlite/blob/af2b1c3e2f8b3480e5569212198761c770df06d0/README.md) 和固定提交的实际任务文件、递归文件清单。两卡标记 CC BY-SA 4.0，本地保留数据卡及原始归属。本次列出的有限表投影属于改编，来源和变化均显式记录；不将它称为新独立来源。

两源共同公开 `instance_id / db_id / dialect / version / category / query / issue_sql / preprocess_sql / clean_up_sql`。本次实际计数：Six 为 Query 3,094、Management 1,087、Personalization 819；Critic 为 Query 284、Management 75、Personalization 141。HF 文件的技术 split 名 `train` 不等于本研究获准的政策训练用途。

[官方 BIRD-RL](https://github.com/bird-bench/BIRD-RL) 与 Six 数据卡将 Six 描述为 BIRD-Critic-SQLite 的训练分支。Critic 官方卡要求另行申请完整参考解和测试，本次没有发送申请邮件，也没有获得其完整官方评分资产。因此 **Critic 目前仅完成公开来源及谱系检查，不能报告官方成绩，不能说锁定外测已准入**。SQLite 外部控制也不能替代协作评价。

本次下载并验真的数据文件如下，均为固定提交 URL：

| 文件 | 字节 | SHA-256 |
|---|---:|---|
| [Six train.jsonl](https://huggingface.co/datasets/birdsql/six-gym-sqlite/resolve/d603cc8af5294bb75415b8137d362080dab01bfd/train.jsonl) | 13,393,232 | `7df6797d4b093fd9a34a24569a521f56d29b80dcfacdf567ee41b61dbd30e92c` |
| [Critic SQLite JSONL](https://huggingface.co/datasets/birdsql/bird-critic-1.0-sqlite/resolve/af2b1c3e2f8b3480e5569212198761c770df06d0/sqlite-00000-of-00001.jsonl) | 928,636 | `4abb18afbc7c1f8e9c566d04707ebbdc8508247924ced01b927ef716393fd468` |
| [Six book_publishing_company 原 SQLite](https://huggingface.co/datasets/birdsql/six-gym-sqlite/resolve/d603cc8af5294bb75415b8137d362080dab01bfd/database/book_publishing_company/book_publishing_company_template.sqlite) | 184,320 | `b493a54214d7b224a6f2b9b22b0f651c98f0c345a91cdec10b94825d4d897f4d` |

仅下载了一份数据库。其余数据库重合检查依据官方固定清单的 LFS SHA，不等于已逐个下载检查内容。没有执行远程 Python loader 或上游 Python 测试。

## 2. 谱系重合：按数据库名隔离仍不充分

两套数据的数据库 ID 和发布的 SQLite LFS SHA 均无交集，但题面存在实质精确重合。对 NFKC、大小写及空白规范化后的字段组合，跨来源共有 **22 个题面指纹、10 个错误 SQL 指纹、3 个题面与错误 SQL 联合指纹**。这些计数是不同指纹数，不是配对数；3 个联合指纹对应下面 5 个任务配对。

| Six 任务及 DB | Critic 任务及 DB |
|---|---|
| TRAIN_66 / olympics | SQLite_325 / european_football_2 |
| TRAIN_429 / books | SQLite_325 / european_football_2 |
| TRAIN_1250 / hockey | SQLite_466 / card_games |
| TRAIN_2953 / public_review_platform | SQLite_466 / card_games |
| TRAIN_340 / hockey | SQLite_482 / formula_1 |

原记录可以从固定 JSONL 按 ID 复查，联合指纹 SHA 已归档。部分问题直接在 CTE 中携带小数据或针对抽象表结构，因此不同 `db_id` 并不能保证任务内容独立。这是实际重复检查结果，不是仅根据共同命名推断。

当前检查不覆盖语义近重复、变形 SQL、原始用户问题 ID 或完整任务模板家族；两份公开数据未提供足以核验这些关系的原始问题标识。**无精确匹配不等于无污染。** 后续用途准入应按数据库、表、任务模板及派生关系做联合闭包，跨用途精确重复至少要整体隔离，且仍须审查近重复。

本轮冻结的用途仅是：`book_publishing_company` 及其本轮派生样例为接口开发；Six 其余部分未分配训练或锁定评价用途；Critic 为待谱系闭包和官方评分资产核验的独立 SQL 外测候选。已查看的公开题面属于来源审查材料，不把本轮开发材料重新包装成未接触锁定集。

## 3. 有限 P0 设计与执行边界

固定选择 `TRAIN_86 / TRAIN_210 / TRAIN_303`，均为同一 book 数据库的 Query 类，只有一条原问题 SQL、一条参考 SQL，且 `preprocess_sql / clean_up_sql` 均为空。选择依据是可检查合同与现有 SELECT 接口适配，未使用目标模型分数筛选。

预先语义审查保留两个不准入例子：`TRAIN_100` 的公共需求要求随后最早日期，参考却把日期 ASC 改成 DESC；`TRAIN_120` 要求每个出版商的书目数，参考内连接遗漏零书目出版商，实际库中有 5 个这样的出版商（1622、1756、9901、9952、9999）。前者为需求与参考方向矛盾，后者至少有零行覆盖歧义。本轮没有悄悄修正参考或按参考标签评分，两例均不进入 P0 执行集。原行另存 `runs/sql-source-v020-p0/private/semantic-exclusions.json`。

**原生路径：** 验证原 SQLite SHA，以只读 immutable 方式打开，复制到新的内存库。关闭扩展加载、关闭 trusted_schema，启用 query_only；authorizer 仅容许有限读取及聚合函数。子进程限制 wall 8 秒、CPU 4 秒、地址空间 512 MiB、SQL 20,000 字符、返回 5,000 行、VM 500,000 步。实际执行原问题、私有参考、host 修复程序和合法错误程序，并执行写入、ATTACH、加载扩展三个拒绝控制。这里是已审查公开 SQLite 查询的有界入口，不是任意外部代码执行沙箱。

**世界路径：** 复用已有 WorldCore 与 `managed-duckdb-v0.18`，没有新增世界引擎。公开材料包含原需求、原错误 SQL，以及以下列的全量原始行：authors 的 au_id/au_fname/au_lname 共 23 行，titleauthor 的 au_id/title_id 共 25 行，titles 的 title_id/type/price 共 18 行。共 66 行，无行筛选；只做显式列投影，不宣称完整 SQLite 数据库迁移。价格以原生 REAL 对应 DOUBLE，本次只做 `>15` 条件比较，不涉及金额精度核算。

工作人员通过实际工具读数据、固定采用 data v1、写代码并调用 `sql_build`，构建证据由内核写入不可由 JSON 内容伪造的版本元数据。每例 14 次受管调用，共 42 次。参考 SQL、上游 Python 测试和独立期望值均留在 host 私有文件；初始角色观察及 v1 文件检查不含它们。上游 Python 只经 AST 语法解析、记录函数名与 SHA，**未执行**。

独立 oracle 用 Python 对原始投影表做集合排除、连接筛选或分组计数，不调用参考 SQL，也不读取它的输出。原生参考和修复程序分别与该 oracle 对照。模型工具只见源事实与正常执行产物，不提供隐藏正确答案接口。P0 世界的 content_checks 为空且场景 `model_eligible=False`，没有把程序见证转换成正式训练奖励合同，也没有进行提交验收或团队协作评分。

## 4. 实测结果

| 任务 | 原 SQLite 问题结果 | 原生参考 / 修复 | Managed 原问题 | Managed 修复 | 合法但错误的对照 |
|---|---|---|---|---|---|
| TRAIN_86：未参与指定图书的作者 | 可运行，23 行，错误 | 均 21 行，正确 | 可运行，23 行，错误 | 21 行，正确 | 可运行，0 行，失败 |
| TRAIN_210：business 且 price > 15 的作者 | `FRM` 语法错误 | 均 3 行，正确 | 真实执行错误 | 3 行，正确 | 阈值改成 >1000，0 行，失败 |
| TRAIN_303：按类型计数 | 可运行，1 行，错误 | 均 6 行，正确 | 缺 GROUP BY 的 BinderException | 6 行，正确 | 每组计数 +1，6 行但值错，失败 |

SQLite 的宽松聚合语义与 DuckDB 不完全相同，303 的失败机制已经分别保存。不能把三个受支持见证推广为全数据方言等价、Management/Personalization 支持或官方测试兼容。

每例的三个原生危险操作均被真实拒绝。修复结果的准确 data v1 采用和实际代码版本均保留在执行谱系；之后写入错误版本，不改变旧正确版本的判定。把正确表及可编辑 `execution` 字段原样复制成新 JSON 版本，数值虽正确，却因缺少内核构建元数据而失败。这些是程序负例控制，不是模型失败率。

正式 CPU 实验耗时 **4.46 秒**，3 例共 33 项控制通过；该时长不含先前来源下载和静态审查。原数据库前后 SHA 不变。定向测试 **2 passed，4.49 秒**，三份新增 Python 文件 Ruff 通过，未运行全库测试。测试另行重复了同一固定 P0 控制，不能计作新的独立来源或追加实验样本。

## 5. 复现入口与尚未完成项

```bash
.venv/bin/python -m scripts.sql_source_experiment_v020 \
  --assets runs/assets/sql-v020 --output runs/sql-source-v020-p0-new
.venv/bin/python -m pytest -q tests/test_sql_source_v020.py
```

输出目录必须不存在。资产目录结构与下载 URL/SHA 见机器归档的 `source_declarations`、`lineage.sources` 和本报告文件表：各源的固定清单与数据卡分别保存为 `tree.json / card.md`，下载声明为 `source.json`；任务文件、源提交、声明所列文件 SHA 不符均拒绝。缺少本地公开数据时，测试明确 skip，不伪造真实来源运行。

本轮尚未完成：BIRD-Critic 完整官方评价资产和原生官方评分器接通；跨源语义/模板/原问题谱系闭包；Six 其余数据库的用途划分与训练准入；需要写操作的任务；同领域多成员信息不对称合同；单共享模型真实支持探针和后续训练。后续必须分别报告这些门槛，不能把本次三个 host 程序见证计为 SFT、模型完成、协作增益或 ID-VTDO 经验支持。
