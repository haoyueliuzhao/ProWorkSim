# v0.28：SWE-smith 实际任务导入与 CPU 资格记录

日期：2026-10-03（北京时间）。这是审计后续阶段 2 的小批来源结果。**已导入 3 个用途明确、能执行和评价的派生任务，来自 3 个整仓隔离的真实 SWE-smith 仓库；尚无这批来源的模型经历、方法支持、参数更新或 B/G/I 效果结果。** 旧 Marshmallow 资产仍只作接口开发，不在本清单中。

完整原始子进程输出、原始测试结果、API 返回及父进程比较保存在[机器报告](software-sources-v028.json)。原始来源和派生合同见[资产目录](../../examples/software-sources-v028/README.md)。没有用 CPU 程序解冒充当前策略经历。

## 1. 固定来源与用途先后

本次先读取官方元数据，只下载一个 6,006,895 字节的 Parquet 分片，从中取得 3 个轻量纯 Python 仓库各 12 条最短补丁候选记录（共 36 条），选阅其中的直接 API 回归，为每仓选择 1 个实例。筛选没有使用模型成绩。未全量下载数据集、未批量构建镜像、未导入教师轨迹。

固定数据集为 `SWE-bench/SWE-smith-py`，revision 为 `77cab9055d42ab4a5c25c89a8f937096db13558e`；分片为 `data/train-00002-of-00011.parquet`。这是 SWE-smith 主来源的 Python 分库，不是切换或并行建设另一套训练来源。官方旧总库说明已转向语言分库；本次实际保存了固定 Python 分库的原始 dataset card。[官方数据集说明](https://huggingface.co/datasets/SWE-bench/SWE-smith)、[固定 Python 分库](https://huggingface.co/datasets/SWE-bench/SWE-smith-py/tree/77cab9055d42ab4a5c25c89a8f937096db13558e)

[来源清单](../../examples/software-sources-v028/source-manifest.json)保存分片、源压缩包、原始 task 行、上游测试、许可证和环境的 SHA-256。重现下载已对 3 条完整原始行逐字段核对，确认补丁、问题描述、FAIL_TO_PASS、PASS_TO_PASS、仓库及 image_name 与该固定分片一致。官方 RepoProfile 的固定实现为 `9b74ac08118a85c39c356802f7961893af73e07f`，其中 3 个仓库的完整 commit 与实际下载源代码一致。[固定官方 Python profiles](https://github.com/SWE-bench/SWE-smith/blob/9b74ac08118a85c39c356802f7961893af73e07f/swesmith/profiles/python.py)

| 用途 | 仓库与完整 commit | 原始实例 | 项目派生任务 |
|---|---|---|---|
| 策略训练 | `andialbrecht/sqlparse`；`e57923b3aa823c524c807953cecc48cf6eec2cb2` | `andialbrecht__sqlparse.e57923b3.func_basic__gd5m1k59` | `sqlparse-comparison-records` |
| 贡献开发 | `keleshev/schema`；`24a3045773eac497c659f24b32f24a281be9f286` | `keleshev__schema.24a30457.func_basic__asdkjyun` | `schema-catalog` |
| 独立确认 | `google/textfsm`；`c31b600743895f018e7583f93405a3738a9f4d55` | `google__textfsm.c31b6007.func_basic__sbxjl844` | `textfsm-record-items` |

[用途划分](../../examples/software-sources-v028/source-partition.json)在北京时间 **10 月 3 日 00:28:13** 冻结，SHA-256 为 `9bf31612adac43e3d54d118e2494f12b1f7e44ee40d93482087230b87fcd30c7`。消费者需求及独立 API 输入在此之后才派生。采用已有 v0.27 整仓、commit、补丁、测试、来源簇和父谱系传递闭包规则，3 个仓库分别属于 3 个用途；不是把同仓不同 issue 当成独立材料。原始划分中的 `task_derivation_started=false` 是冻结时状态，后续任务绑定其摘要，不回写历史声明。

主训练路线只有 sqlparse 一个仓库。每个用途目前仅 1 个任务，这是来源资格样本，不能支持跨仓分布泛化或正式统计功效结论。独立确认仓库本次只执行固定程序解的可行性检查，未用任何候选策略在其上的成绩选权或调参。

数据集声明 MIT；另保留 SWE-smith toolkit 的 MIT 许可证。上游代码分别按 sqlparse 的 BSD-3-Clause、schema 的 MIT、TextFSM 的 Apache-2.0 许可保存；Python 源文件版权头及许可证原文未删改。数据集许可不替代上游代码许可。[许可与固定 card 证据](../../examples/software-sources-v028/provenance/sources.json)

## 2. 原始缺陷与新增共同交付

这些原始 SWE-smith 问题是单人软件修复问题。**不能因改用双成员运行器，就说原始任务天然具有协作要求。** 本次另派生一个消费真实库 API 的业务文件，保留原库修复目标，以两个可联合实现的交付项构成有界软件任务。

| 任务 | 原始实际缺陷 | 新增消费者交付 | 参考实现中的真实依赖 |
|---|---|---|---|
| sqlparse | `Comparison.right` 返回首项，右操作数退化为左操作数 | `comparison_records(expressions)` 按输入顺序输出左右操作数，保留引号和括号 | 消费 `sqlparse.parse` 产生的 `Comparison.left/right` |
| schema | `Schema.description` 对 `None` 调用 `.strip()`；也会错误去掉说明两侧空格 | `schema_catalog(specs)` 输出按名字组织的 JSON Schema 目录 | 用真实 `Schema(...).json_schema(...)`，保留库导出结果 |
| TextFSM | `List.OnSaveRecord` 反转已收集项目 | `record_items(text)` 将有 key、item、end 的记录转为有序对象列表 | 用真实 `TextFSM.ParseText`，保持项目顺序及重复项 |

两名成员身份稳定、权限相同，两项任务初始均无负责人。可以自主领取、协商、转交、交换固定补丁并集成；也允许一人集中完成两个交付。资格检查证明的是**两个产物共同可行且参考消费者依赖库修复**，不是证明两个成员都必须参与，更不是已经观察到模型协作或可靠方法类别。

只修库时消费者仍抛 `NotImplementedError`；只提供参考消费者时真实库缺陷传递到消费结果；联合参考解同时满足上游回归与父进程 API 检查。这种四态控制比“文件名看起来有上下游关系”更强，但仍只是该固定程序见证的依赖关系，不证明所有可能实现都无法绕过库 API。

## 3. 执行环境与评价边界

Docker 可执行文件存在，但本用户执行 `docker info` 返回访问 `/var/run/docker.sock` 的 permission denied。原始错误保存在机器报告 `docker_probe`；没有修改 Docker 权限、冒充已拉取镜像或把普通工作目录当隔离环境。

本次复用项目既有 `software-landlock-seccomp-v0.15` 执行边界，而不是另造容器运行器。固定环境为 `/usr/bin/python3` **3.12.3**，实际 Landlock ABI **4**；源文件只读白名单，seccomp 禁止网络、子进程和相关进程操作，环境变量清空。每次运行上限为 20 秒墙钟、10 秒 CPU、512 MiB 虚拟地址空间、256 KiB 输出和 64 个打开文件。所有实际执行都报告隔离已安装，没有 timeout。内存上限不是实测峰值。

官方镜像名按原始行保留，但未拉取，镜像 digest 未宣称固定；这套 Python 3.12.3 隔离适配**不等同于官方 Docker 环境**。它只支持本次纯 Python、无额外运行依赖的有限源代码和测试子集。源文件、原测试模块和许可由控制器取固定字节，仓库安装脚本、外部 shell 命令和 Dockerfile 均未执行。

上游可见回归采用两种方式：sqlparse/schema 只运行原测试文件中选定的无参数、无装饰器函数，函数体和断言保持原样，不提供假的 pytest；TextFSM 载入原始 `UnitTestFSM` 类，通过标准库 unittest 执行选定方法。完整原测试文件仍随来源保存。**这不是全套 pytest 或官方 SWE-smith harness 的成绩。**

独立 API 检查不采信 worker 自报的 pass，也不把可见测试绿色当最终验收。父进程只向隔离子进程发送 API 输入，期望值和比较逻辑留在父进程；返回结构需合法、唯一、完整，父进程逐项比较。冻结测试、公开合同等不可编辑文件被改动时，在运行前拒绝。该边界限制宿主机访问并独立作有限输出比较，但不是防任意对抗程序伪造有限输出的密码学证明；不能据此宣称不存在一切评分投机。

## 4. 实测资格结果

下表为最终 `qualification-02`，每仓执行 3 次上游测试和 4 次独立 API 评价，共 **21 次隔离执行**。

| 仓库 | 原始数据所列 FAIL_TO_PASS / PASS_TO_PASS | 本次选定 F / P | 原基线 | 加原缺陷后 | 逆补丁修复后 |
|---|---:|---:|---:|---:|---:|
| sqlparse | 16 / 315 | 3 / 2 | 5/5 通过 | 3 个 F 失败，2 个 P 通过 | 5/5 通过 |
| schema | 64 / 52 | 3 / 2 | 5/5 通过 | 3 个 F 失败，2 个 P 通过 | 5/5 通过 |
| TextFSM | 2 / 94 | 2 / 2 | 4/4 通过 | 2 个 F 失败，2 个 P 通过 | 4/4 通过 |

F/P 的选择在模型采集前冻结。此处共 14 个选定测试身份，三态共 42 次测试调用；不是 42 个问题，也不表示未选定的上游测试已通过。缺陷是原数据中的原始 diff，修复控制是对该 diff 的精确逆操作。必要机制测试另验证逆操作恢复全部原始字节，以及错误上下文会被拒绝。

独立 API 检查同时覆盖源 API 和消费结果；分子为通过的固定输入条目数，只有所有条目通过才完成任务：

| 任务 | 原缺陷＋消费桩 | 只修库 | 只给参考消费者 | 联合参考解 |
|---|---:|---:|---:|---:|
| sqlparse（6 项） | 1/6 | 3/6 | 2/6 | **6/6** |
| schema（5 项） | 0/5 | 3/5 | 1/5 | **5/5** |
| TextFSM（6 项） | 2/6 | 3/6 | 4/6 | **6/6** |

三仓均达到事前控制标准：原基线和修复态回归通过，原缺陷态实际产生所选预期失败并保留所选回归，只有联合解通过全部 API 条目，且只给消费者时至少一条消费检查也失败。TextFSM 的空输入和对称列表可能在错误反转下仍正确，非对称多记录输入确实暴露反转；没有把所有单条输入都宣称为有效的缺陷探针。

具体失败保留在原输出中：sqlparse 右项实际变成 `sensor`/`ratio` 等左项；schema 返回 `builtins.AttributeError`，提示 `NoneType` 无 `.strip`；TextFSM 多记录项目实际变为 `['a', 'z']`、`['b', 'c']`，与预期 encounter order 不同。联合解通过不依赖改测试、消除原始失败记录或放宽已有用途隔离。

## 5. 运行次数、失败记录与轨迹保存

首次 `qualification-01` 的 21 次执行已全通过。之后补上原始行的固定 Parquet 对照验证、参考解摘要检查和可见返回格式检查，再作 `qualification-02` 的完整 21 次复核。两轮都保存在机器报告，第一轮没有当作失败删除，也不把第二轮说成全部工作成本。

`qualification-02` 初次下载调用发生一个控制器路径记录错误：相对 `--run-root` 与绝对项目根调用 `relative_to` 不匹配。它发生在资格 worker 启动之前；修复为记录解析后的绝对路径，复用已保存分片并重新核对 SHA-256 后继续。该错误摘要与原因一并保留，没有任何模型结果被筛除。

两轮累计 **42 次隔离执行，42 次成功安装隔离，0 次 timeout**；子进程墙钟耗时合计 **5.064099 秒**，两轮资格阶段墙钟合计 **2.876855 秒**。后者因三仓并行而小于前者；二者都不是 CPU 活跃时间，不含下载、实现和人工审查。GPU 消耗、模型 episode、当前策略轨迹和参数更新均为 **0**。

保留内容包括：

- 提交的小资产：原 task JSON、补丁、源包 Python 文件、原测试、许可、用途分区、派生合同、消费桩、控制器参考消费者、独立固定 API fixture、依赖控制声明及各摘要。
- 机器报告：两轮所有原始测试/ API worker 输出、父进程逐项结果、原缺陷失败、环境信息、Docker 拒绝和下载重试记录。
- 本地完整下载及逐任务轨迹：`runs/software-sources-v028/`，包括固定分片、源压缩包、原始 API 元数据、36 个候选记录、`qualification-01/`、`qualification-02/` 和各 `traces/*.json`。大资产不纳入 git，提交的清单和下载脚本可验证重现。

## 6. 可复用入口与未完成项

[源任务适配器](../../src/proworksim/software_tasks_v028.py)提供：

- `build_case(task_id)`：返回初始缺陷源文件、消费桩、公开合同/回归、可编辑路径、两项无主任务及用途。不会把参考解、正确未破坏源码、原补丁和私有期望值送入成员副本。
- `run_public_tests(task_id, files, run_root=...)`：执行选定真实上游回归，供软件工具反馈使用。
- `assess(task_id, files, run_root=...)`：校验不可编辑文件，执行隔离 API 请求并在父进程评价。
- `reference_solution(task_id)`：只给来源资格控制器使用，不是模型路线、训练样本或在线经历。

[重现脚本](../../scripts/import_software_sources_v028.py)不启动模型、不安装包、不建镜像：

```bash
.venv/bin/python scripts/import_software_sources_v028.py --download --qualify
```

另外执行 **7 项**必要机制回归，覆盖用途隔离、缺陷逆操作、错误上下文、源字节篡改、参考解篡改和冻结测试篡改；Ruff 通过。这些检查不同于 14 个上游测试，也不是任何模型工作次数。

本交付把阶段 2 从空目录推进到 3 个固定可执行任务和独立评价接口。它仍是小规模适配，不是任意 SWE 仓库已接入，也不是正式 B/G/I 试验已可无条件启动。后续必须把同一接口绑定到当前策略采集与动态职责规则，冻结实际窗口/预算，保存成员原始经历并检验可靠方法支持；无配置自由度时应按审计停止，而不能把这些程序见证改成训练数据或用旧 Marshmallow 开发经历补支持。
