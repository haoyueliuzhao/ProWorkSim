# v053：200 题面板的来源、抽样与重复诊断

日期：2026-10-20。用途为原始 Qwen3.5-9B、原生 OpenHands 单 Agent 的能力评测／校准。本批材料不能再充当后续算法的独立确认集；不开展训练或架构对照。

## 实际来源

本轮使用官方维护的 Python 语言任务集
[SWE-bench/SWE-smith-py，revision 77cab9055d42ab4a5c25c89a8f937096db13558e](https://huggingface.co/datasets/SWE-bench/SWE-smith-py/tree/77cab9055d42ab4a5c25c89a8f937096db13558e)，
环境定义采用
[官方代码 revision 9b74ac08118a85c39c356802f7961893af73e07f](https://github.com/SWE-bench/SWE-smith/tree/9b74ac08118a85c39c356802f7961893af73e07f)。
这两项与项目此前记录的 pin 相同，但本轮读取全 11 个 Parquet 分片，不能把旧单分片或旧六题当作新面板。

全量实际统计为 **50,908 条任务、50,908 个唯一 instance_id、131 个 repository 标识**。官方资产页面的“128 仓库、50k+”是历史资产说明，本轮以固定版本实际清点结果为准。未下载专家轨迹、其他模型或训练材料。

原始字段只有 `instance_id`、`patch`、`FAIL_TO_PASS`、`PASS_TO_PASS`、`image_name`、`repo`、`problem_statement`。其中 `patch` 是从原始仓库生成缺陷的变更，用于宿主准备初态；它和参考恢复材料不进入模型提示。

官方数据没有单独的人类核验缺陷类型字段。本轮从 `instance_id` 提取 `mutation_family`，例如 `func_basic`、`func_pm_op_swap`、`combine_file`；`pr_<number>` 来源统一标记为 `pr_mined`。该字段只是**任务生成／变异来源代理标签**，不能宣称是真实缺陷语义的人工分类。

11 个分片逐一核对官方 HF LFS SHA-256。首次下载中 4 个分片流提前结束，长度／SHA 校验拒绝这些不完整文件；仅按 HTTP Range 续传原文件，未替换版本、未改题池。补齐后才建立候选题单。分片、官方代码归档与数据卡总计 228,897,812 bytes，原始资产保存在被 Git 忽略的 `artifacts/software-panel-v053/sources/`。

首次全量预检发现任务 ID 解析器漏认 2,481 条 `pr_<number>` 记录；原预检清单保存在 `candidate-inventory-precheck-r1.json`。在任何环境或模型成绩被使用之前，修正解析器以显式接纳 `pr_mined` 类，并重新生成正式候选库存。此修订是源 schema 适配，不是按模型表现改变题目。

最终候选库存 SHA-256 为 `09f30d93a0faaee285e750407e2dafed5cfdc5b12cfb3c6d93f8592d90995ada`。实际排除 11,437 条缺少题面的记录（缺少 image 的记录为 0），排除原六题及 4 条近重复变体。131 个仓库中 129 个能按规则提供 10 个候选；`datamade/usaddress` 和 `pwaller/pyfiglet` 分别只能保留 7 和 9 个候选。完整库存引用 1,306 个候选任务，选择过程中共记录 53 次候选近重复／精确重复拒绝。

尚未做环境替补的前 20 个仓库对应 200 个候选，覆盖 18 种代理标签与 131 个仓库内不同修改文件。这只是环境准备输入的覆盖情况，不能当作已经准入或运行的正式 200 题。完整预定顺序和每仓库题目 ID 见 [机器摘要](software-panel-v053-source-inventory.json)；全部候选的详细位置、失败测试集合和排除记录保留在本地、由上述 SHA 绑定。

## 模型成绩之前固定的选择规则

1. 从原始任务元数据中去除旧六题，以及符合下述机械近重复规则的旧六题变体。排除缺少题面、环境 image、非空 FAIL_TO_PASS，测试集合不唯一／交叉，或不能解析为安全文本源码变异的记录。记录排除原因。
2. 按 repository 分组。对每个仓库按 mutation family 轮转取题；family 顺序由 `SHA256(selection_seed, repository, family)` 确定。每一层内优先覆盖尚未使用的函数和文件，剩余顺序由固定 SHA-256 排名决定。没有使用成绩、难度估计、补丁长度或成功轨迹。
3. 规范化 patch 去掉 diff 元数据、行号和未修改上下文，对修改的路径、删除行和添加行作空白归一化。同仓库规范化结果相同的记录只保留一个。
4. 同仓库内，FAIL_TO_PASS 集合 Jaccard 相似度至少 0.8，并且修改同一函数上下文，或修改旧行位置与较小集合的重叠比例至少 0.8，则视为近重复。候选按固定顺序接受或排除，排除记录指出已经保留的代表题。
5. 只有去重后能取出 10 题、并且存在固定官方 profile 和 image 声明的仓库进入环境核验候选。候选仓库按 `SHA256(selection_seed, repository)` 排序，保留完整顺序。
6. 环境核验依候选仓库顺序进行。在**任何模型回合启动之前**，允许将明确无法准入的仓库及原因写入拒绝表，随后检查预定顺序中的下一仓库。最终使用前 20 个通过完整十题来源核验的仓库，每仓库恰好 10 题。前位仓库尚未检查时，不允许直接跳过。
7. 从最终每仓库 10 题中按固定重复抽样 seed 取 2 题，优先覆盖不同 mutation family。因此重复子集恰为 40 个不同任务，并覆盖全部 20 个仓库。
8. 一次性固定 200 个第一次运行和 40 题各两次额外运行，共 280 个唯一 slot 及独立生成 seed。正式模型运行后不能改题、换 seed 或按结果补跑。

固定种子字符串：

| 用途 | 值 |
| --- | --- |
| 主面板和仓库排名 | `20261020-v053-main-panel` |
| 40 题重复子集 | `20261020-v053-repeat-panel` |
| 每回合独立生成 seed | `20261020-v053-independent-generations` |

近重复排除是明确可复现的机械启发式。它能排除同一修改及相似位置／失败测试的变体，**不能认证所有剩余任务语义独立**。函数名只取原始 diff hunk 中明确出现的 `def` 上下文；没有该上下文时使用修改行位置，不猜测函数身份。不同仓库和不同文件／函数覆盖属于设计目标，具体达到的分布以机器清单为准。

## 机器文件与正式启动条件

- `artifacts/software-panel-v053/sources/download-manifest.json`：固定原始来源、文件大小和 SHA。
- `artifacts/software-panel-v053/candidate-inventory.json`：完整候选顺序、每仓库十题、去重与不合格原因。生成后禁止原位改写。
- `artifacts/software-panel-v053/tasks/<instance_id>.json`：官方七字段任务行。模型侧仅取得题面及受限初始工作树；完整原始行供宿主准备和评分使用。
- 环境 admission 文件：必须绑定 candidate inventory SHA，明确 `model_runs_started=0`，每个通过仓库必须绑定全部十题的 `qualified_task_ids`；拒绝必须有原因。
- `docs/experiments/software-panel-v053-panel.json`：只在 20 个仓库、200 题均完成环境准入之后输出正式 200／40／280 冻结清单。

`source_row_sha256` 是任务文件原始 bytes 的 SHA-256。序列化固定为 UTF-8、JSON 键排序、缩进 2、保留非 ASCII 字符并以一个换行结束。它不是忽略空白后的弱身份，也不依赖输入字段顺序。

候选库存不等于模型准入。正式清单存在、200 题环境资格齐全、固定原生 OpenHands 路径和全部推理配置完成来源绑定之前，不启动正式回合；不将“列出了 200 题”写成“200 题已运行”或“200 题环境均可用”。

## 预算和报告口径

200 个不同任务的第一次预定运行构成主结果，分母固定为 200。40 题重复子集另报三轮完成率和 0/3、1/3、2/3、3/3 成功的任务数量。技术未知单独保留；不能只统计成功闭合子集，不能把三次至少一次成功改称单次完成率，也不能把 280 回合简单混合平均为主结果。

每回合输入加输出 token 上限 500,000，总生成预算上限为 **140,000,000**。环境准备、CPU 测试和 GPU 驻留另计；上限不代表预计实际消耗。重复回合使用独立初态、会话、随机 seed 和候选文件树，不共享之前的补丁或测试反馈。

最终结论限定为“这一仓库分层任务面板上的单次完成率”。它不是整个 SWE-smith 自然分布的无条件均值，也不是 SWE-bench Verified 分数。三次重复只能诊断有限生成波动，不能认证稳定性。

## 实现入口

```bash
.venv/bin/python scripts/software_panel_v053.py fetch \
  --source-root artifacts/software-panel-v053/sources

.venv/bin/python scripts/software_panel_v053.py inventory \
  --source-root artifacts/software-panel-v053/sources \
  --code-root artifacts/software-panel-v053/sources/SWE-smith-9b74ac08118a85c39c356802f7961893af73e07f \
  --tasks-root artifacts/software-panel-v053/tasks \
  --output artifacts/software-panel-v053/candidate-inventory.json

.venv/bin/python scripts/software_panel_v053.py freeze \
  --inventory artifacts/software-panel-v053/candidate-inventory.json \
  --admission <完整环境准入文件> \
  --output docs/experiments/software-panel-v053-panel.json
```

`fetch` 下载官方代码归档；执行 `inventory` 前须将该固定归档安全解包到上述目录。已完成的同字节文件可以复用，已有不同字节的机器清单会被拒绝覆盖。必要控制覆盖输入顺序不变性、200／40／280 分母、独立 seed、来源拒绝顺序、模型前冻结门和近重复变体；不重跑旧模型实验。
