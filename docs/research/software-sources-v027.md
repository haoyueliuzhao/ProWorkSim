# v0.27 软件协作素材、用途划分与来源准入

日期：2026-10-02（北京时间）。本文件落实 [10 月 2 日审计对齐计划](../software-allocation-v027-plan.md)中的来源边界。

**当前完成的是来源入口核对、用途划分规则和 CPU 准入检查。没有取得或筛选真实 SWE 任务，没有构建环境、运行模型或更新参数。** [机器来源计划](../../examples/software-collaboration-v027/source-plan.json)中的 `partition=null`、`tasks=[]`，实际样本数和运行预算均待冻结。这些空值会被运行来源门拒绝；审计建议的 4 情境 × 2 重复仅保存在建议字段，不是已冻结的运行量。

## 1. 来源角色与核对范围

主训练素材来源收敛为 SWE-smith。复用仓库起点、环境与任务测试，不接入其教师经历或另建训练器。SWE-Gym只保留备选，不能与主来源同时成为新的训练流水线。

| 来源 | v0.27 用途 | 当前证据和边界 |
|---|---|---|
| SWE-smith | 主任务与环境来源 | 核对官方文档和固定提交中的指定入口文件；实际任务、dataset revision、镜像摘要未冻结 |
| SWE-Gym | 不启用的备选 | 核对官方 README；若主路线不适配或成本不合适，记录原因并另冻结来源协议 |
| CooperBench | 外部协作结果补充候选 | 保持原生逐 feature 评价含义；合并后集成测试须另列 |
| AsynCodeBench | 可选候选 | 官方站点本次正文读取不完整，未完成实现审计，不设为下一阶段必经门槛 |
| SWE-bench | 个体代码修复与回归控制候选 | 未选子集；不能独立承担协作结论 |
| 既有 Marshmallow v0.15 | 历史与接口开发 | 不重新当作训练新来源、贡献开发材料或独立确认 |

固定版本来自本次对官方 GitHub commit API 的读取；下表对应文件也实际读取并计算 SHA-256，摘要保存在机器计划中。**这是所列文件的来源核对，不是完整仓库下载、全实现审计或环境可运行性证明。**

| 官方仓库 | 本次核对提交 | 核对文件 |
|---|---|---|
| [SWE-smith](https://github.com/SWE-bench/SWE-smith/tree/9b74ac08118a85c39c356802f7961893af73e07f) | `9b74ac08118a85c39c356802f7961893af73e07f` | README、建镜像、程序任务生成、收集补丁、valid/gather/eval 共 7 个文件 |
| [CooperBench](https://github.com/cooperbench/CooperBench/blob/63b9d44d9f39a02fccf5bf0052db48a917a011fd/README.md) | `63b9d44d9f39a02fccf5bf0052db48a917a011fd` | README |
| [SWE-Gym](https://github.com/SWE-Gym/SWE-Gym/blob/b681068ca20628c6987b7416cc4cf03f06b77ba5/README.md) | `b681068ca20628c6987b7416cc4cf03f06b77ba5` | README |

## 2. SWE-smith 可复用入口

官方说明支持通过 RepoProfile 取得任务环境，也提供仓库环境创建、破坏既有测试的候选任务生成与验证入口。入口如下，参数占位符尚未绑定实际任务，**本次没有执行这些命令**。[官方固定 README](https://github.com/SWE-bench/SWE-smith/blob/9b74ac08118a85c39c356802f7961893af73e07f/README.md)

| 工作 | 固定版本的 Python 入口 | 本项目需另外冻结 |
|---|---|---|
| 创建选定仓库环境 | `python -m swesmith.build_repo.create_images -r <repository>` | 精确仓库、源 commit、构建脚本及镜像摘要、资源上限 |
| 获取已有任务容器 | `swesmith.profiles.registry.get_from_inst(task).get_container(task)` | dataset revision、原始 instance id、容器镜像摘要 |
| 生成候选程序缺陷 | `python -m swesmith.bug_gen.procedural.generate <repository> --max_bugs <limit>` | 候选上限、原始补丁、派生关系；不默认调用模型生成 |
| 收集候选补丁 | `python -m swesmith.bug_gen.collect_patches <candidate-dir>` | 输入目录内容摘要与全部候选清单 |
| 验证候选 | `python -m swesmith.harness.valid <patches.json>` | 原始测试、补丁、验证报告和日志 |
| 收集有效实例 | `python -m swesmith.harness.gather <validation-run-dir>` | 通过与未通过的原始分母 |
| 评价修复补丁 | `python -m swesmith.harness.eval --dataset_path <instances.json> --predictions_path <predictions.json> --run_id <id>` | 修复补丁、评价版本、测试命令和完整结果 |

环境指南说明该路线使用 Docker，并给出选定仓库创建镜像的入口。应显式指定仓库，不能把无选择参数的批量构建当作默认步骤。[环境文档](https://swesmith.com/guides/env_construction/)

候选生成产出原始 diff 与生成元数据；本项目要保留它们作为谱系，不用新需求文本替代原始任务身份。[任务生成文档](https://swesmith.com/guides/create_instances/)

官方验证先运行原始测试，再施加候选缺陷并重跑；收集器要求至少一个 FAIL_TO_PASS 和一个 PASS_TO_PASS。该事实不证明本项目派生的多人工作可共同实现，后者仍需独立联合见证。[验证与评价文档](https://swesmith.com/guides/harnesses/)

## 3. 先分用途，再派生协作需求

首版采用保守的整仓与谱系隔离。不是只按 benchmark 名字区分 train/test：同一源码可以出现在多个 benchmark、镜像或镜像仓库中。

四种用途分别是：

| 固定用途 | 允许的工作 | 不允许替代的证据 |
|---|---|---|
| `interface_development` | 工具开发、合同调试、程序见证、有限模型开发诊断 | 策略训练样本或独立效果确认 |
| `policy_training` | 当前策略、当前参数窗口产生的原始成员工作 | 外部教师、程序路线、旧窗口或其他方法的后继轨迹 |
| `contribution_development` | 配置探测、开发效用测量和选择配置 | 选权后的独立算法结论 |
| `independent_confirmation` | 预先留出的固定确认材料 | 候选或配置选择依据 |

`freeze_source_partition(assets, assignments)`要求每个原始候选记录完整的 `repository`、40 位 `commit`、原始或稳定合成 `issue_id`、`target_patch_sha256`、`test_sha256`、`environment_sha256`、`source_cluster`、父资产和派生根。它执行以下规则：

1. 规范仓库 URL 拼写；同仓库、同声明来源簇、同 commit、同仓库 issue、同目标补丁、同测试、同派生根或父子关系，均连成同一来源簇。
2. 取传递闭包后，一个来源簇只能有一个用途。即使来源标签改成 SWE-smith/CooperBench，也不能分开。
3. 父来源必须出现在清单中；不接纳未记录父资产。用途必须完整覆盖资产，禁止默认为训练。
4. 只有 `task_derivation_started=false` 的原始候选能创建初始划分；随后派生任务绑定该划分 SHA-256，不能改用途再用同一冻结记录。
5. 明确标记既往使用的资产和既有 Marshmallow 仓库限定为 `interface_development`。历史材料保留原用途记录，不宣称重新获得独立性。

这些检查依赖完整、真实的输入谱系。哈希能检查声明一致性，不能自行发现未声明的 fork、语义近重复、隐藏派生、预训练污染，也不能单凭一个布尔值证明历史发生顺序。实际素材准入还要保留原始下载记录、分区文件和随后生成需求的记录。

本版整仓隔离是首轮的保守选择，不声称同仓库永远不能做验证。同仓库新任务的诊断最多支持同源验证；若后续改用更细的来源簇，需先改协议并明确结论范围。主张新来源迁移应继续保留独立仓库或等价独立来源簇，不能事后看到结果再改划分。

## 4. 派生任务、成员与当前经历

仅接纳两类协作任务：`interface_producer_consumer`和`cross_feature_integration`。需求派生前已经定好来源用途，派生时记录来源资产列表、需求摘要、共同可行解见证摘要、真实依赖见证摘要和独立验证器摘要。两个无关 issue 并排运行，或两项互相矛盾的目标，都不是这两类任务的有效替代。

`validate_derived_tasks`检查上述绑定和证据字段是否齐全。**它不执行见证、不证明任务语义成立。**具体工作世界还必须实际执行程序见证与独立测试，记录共同目标可达、依赖有后果以及集成结果。通过来源门不能代替工作合同与学习器准入。

每条任务具有两个稳定成员身份，双方都具有读文件、编辑、测试、任务板、交换补丁、集成和提交能力；不把一人固定为只传消息的提供者。职责与时序由任务板动作决定；谁最终成功不能改变过去动作归属。来源门检查能力声明，权限执行仍由实际工作接口负责。

`validate_on_policy_record`要求 `origin=current_policy`、精确 actor 摘要、当前 `window_id`、原始任务与成员身份、原始成员动作摘要。外部教师轨迹、脚本见证、旧 actor 或旧窗口记录均不能冒充当前在线经历。该检查是来源声明校验，不替代运行器的原始 token、采样概率与参数绑定。真实训练仍沿用项目既有学习器，不导入来源项目的 SFT 配方。

## 5. 评价边界

CooperBench 官方固定 README 中，`team`使用共享任务列表、原子领取和共享 scratchpad；`coop`为成员预分配 feature。其默认评价对 solo 单个补丁或 coop/team 各成员补丁分别执行 feature 测试，**不自动给出合并后的整体正确性**。本项目若运行补充集成测试，须另报工作合同、合并规则、结果与失败，不能改写其原生 benchmark 分数。[CooperBench 固定协议说明](https://github.com/cooperbench/CooperBench/blob/63b9d44d9f39a02fccf5bf0052db48a917a011fd/README.md)

[AsynCodeBench 官方站点](https://asyncodebench.org/)本次页面正文读取不完整，未在本轮确认实现、任务谱系或评分器行为；仅保留候选状态。SWE-bench固定子集也尚未选定。内部独立软件协作测试是分配算法的主确认场所，外部 benchmark 名称不替代用途隔离和共同工作验收。

## 6. 运行预算与本次验证

`require_run_admission(plan)`检查本轮来源声明、冻结分区、非空真实任务与独立 v0.27 预算。预算必须明确 `gpu_seconds`、`wall_seconds`、`episode_count`、`max_decisions_per_member`、`context_tokens`和`output_tokens`，`protocol=software-collaboration-v027`、`inherited_from=null`。不得沿用 v0.26 的 8 小时扩展、等卡期限、80 GiB 阈值或旧逻辑槽数。它不启动任何工作进程；即使来源检查通过，返回值仍标明 `execution_performed=false`与`semantic_witness_validation=external_required`。

机器计划的当前状态是来源入口已核对、真实清单和预算未冻结，因而调用该函数会明确拒绝。这里没有向用户重新申请 GPU/API 授权；欠缺的是本轮可复现的任务、成本和执行合同，不能用历史资源授权伪装为已填写的实验协议。

本轮 `.venv/bin/python -m pytest -q tests/test_software_sources_v027.py` 为 **28 passed**，对应两文件的 Ruff 检查通过。CPU 控制使用合成资产：覆盖四用途冻结、不同 benchmark 下的跨用途泄漏、传递派生、历史资产、派生后分区、未知父来源、权限声明、教师与旧窗口记录，以及预算缺失和 v0.26 继承拒绝。它们不构成真实 SWE 任务可达性、真实模型工作、学习支持或分配效果证据。

实现：[software_sources_v027.py](../../src/proworksim/software_sources_v027.py)。检查：[test_software_sources_v027.py](../../tests/test_software_sources_v027.py)。本文件与机器计划共同保留尚未完成的实际素材接入边界。
