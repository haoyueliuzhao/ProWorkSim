# v0.30 软件工作载体候选与有限训练来源核查

2026-10-04（北京时间）查阅官方模型卡、固定 revision 的配置、SWE-Next 作者论文及公开数据集小元数据。结论是：**可以冻结当前 9B、SWE-Next-14B、Devstral-Small-2507 三个运行组合进入技术资格与开发筛选；本次资料审查没有测出它们在本项目上的能力排序。**未增加 Small 2 或其他候选臂。本记录不替代权重完整性、实际推理、学习概率、反向、保存重载和新策略回流资格。

机器可读记录见 [software-model-candidates-v030.json](software-model-candidates-v030.json)，保留固定来源、311 个公开仓库的频次和本次检查边界。原始小文件保存在 `runs/v030-model-research/`；此审查没有下载完整模型权重或完整训练轨迹；附录另记录了有界的首块传输探针。

## 候选身份

| 组合 | 官方 checkpoint revision | 许可证字段 | 固定配置架构 / 精度字段 |
|---|---|---|---|
| 当前 Qwen3.5-9B 参照 | `c202236235762e1c871ad0ccb60c8ee5ba337b9a` | Apache-2.0 | `Qwen3_5ForConditionalGeneration`；本项目只使用既有文本路径 |
| TIGER-Lab/SWE-Next-14B | `5d9484d6b0e20786629fccf6de9f190f5fb5ebc7` | MIT | `Qwen2ForCausalLM`，`dtype=bfloat16` |
| mistralai/Devstral-Small-2507 | `bd165ab26cebbcc2eea2c4ecbfc07f3ac42b3c39` | Apache-2.0 | `MistralForCausalLM`，`torch_dtype=bfloat16` |

来源为 [Qwen3.5-9B 固定模型卡](https://huggingface.co/Qwen/Qwen3.5-9B/blob/c202236235762e1c871ad0ccb60c8ee5ba337b9a/README.md)、[SWE-Next-14B 固定模型卡](https://huggingface.co/TIGER-Lab/SWE-Next-14B/blob/5d9484d6b0e20786629fccf6de9f190f5fb5ebc7/README.md)、[Devstral-Small-2507 固定模型卡](https://huggingface.co/mistralai/Devstral-Small-2507/blob/bd165ab26cebbcc2eea2c4ecbfc07f3ac42b3c39/README.md)及各 revision 的 `config.json`。许可证是发布者声明字段。本表只绑定基座来源；当前 9B 的项目 LoRA、优化器与运行数值配方另由实验协议和 checkpoint 身份绑定，不能把它写成从零加载原始 9B 的纯规模对照。

SWE-Next-14B 从 Qwen2.5-Coder-14B-Instruct 做全参数 SFT，发布者称使用 3,693 条执行轨迹，涵盖直接成功与看到失败后的修复。Devstral-Small-2507 的上游为 Mistral-Small-3.1-24B-Instruct-2503，官方说明去掉视觉编码器、面向工具与多文件工作，采用自己的 Tekken / Mistral 格式。两者有成为软件工作载体的资料依据，但仍须分别验证原生输入输出格式、停止、工具解析和实际 token 学习路径。不能把 Qwen 的接口假设直接套给 Mistral。

[SWE-Next 论文 Table 2](https://arxiv.org/html/2603.20691v1)报告其 14B 在 OpenHands 设置下 SWE-bench Verified pass@1 为 30.0%；[Devstral 官方发布](https://mistral.ai/news/devstral-2507/)报告 53.6%。这些是各自发布协议的结果，不能相减得到本项目预计收益，也不能据此宣布 24B 已在本项目获胜。BF16 参数可装入单卡与本项目长度分布下的可微更新是两项不同资格，实际成本应由资格运行测量。

## 用途分隔

本轮模型与接口开发使用固定 **Marshmallow 4.3.1** 派生的六个新合同：两个单执行者 API 正常路径、两个单执行者错误后修复、两个 O1 团队工作。它们属于一个公共库的六个开发案例，不是六个独立仓库。单执行者诊断与团队成功应分开报告。

下表后三项保持既有来源用途，不能通过其工作评分选择候选模型或接口。来源身份参见 [v0.28 source manifest](../../examples/software-sources-v028/source-manifest.json)。检查训练来源仓库身份是资料审查，不是执行这些锁定任务评分。

| 仓库 | 本项目用途 | 固定版本 / 提交 |
|---|---|---|
| `marshmallow-code/marshmallow` | 模型与接口开发池；六个新合同 | 4.3.1，沿用项目已冻结资产 |
| `andialbrecht/sqlparse` | 后续当前策略工作 / policy training | `e57923b3aa823c524c807953cecc48cf6eec2cb2` |
| `keleshev/schema` | 后续贡献开发 / 选权 | `24a3045773eac497c659f24b32f24a281be9f286` |
| `google/textfsm` | 后续独立确认 | `c31b600743895f018e7583f93405a3738a9f4d55` |

## SWE-Next 公开来源重合：查到的范围

作者 [论文 v1 附录 D、Table 7](https://arxiv.org/html/2603.20691v1)给出保留任务的完整仓库表。本次读取 HTML，排除跨列类别标题，得到 **311 个唯一仓库**。同时读取 [Hugging Face 官方数据统计](https://datasets-server.huggingface.co/statistics?dataset=TIGER-Lab/SWE-Next&config=default&split=train)，其 `repo` 频次表也有 311 项，两个仓库集合完全一致。没有根据首页少量预览推断全量仓库分布。

| 本项目仓库 | 论文 311 仓库表命中 | HF `repo` 频次命中 |
|---|---:|---:|
| `marshmallow-code/marshmallow` | 0 | 0 |
| `andialbrecht/sqlparse` | 0 | 0 |
| `keleshev/schema` | 0 | 0 |
| `google/textfsm` | 0 | 0 |

因此，**在已检查的 SWE-Next 公开保留任务来源清单中，未见这四个仓库。**这支持一项有限的来源分隔记录，不支持“训练无污染”或“模型从未见过这些库”的结论。

保留以下限制与原始差异：

- 数据卡和论文写 2,308 个任务；本次 HF statistics 返回 `num_examples=2306`、`partial=false`，311 个仓库频次和也为 2,306。两者差 2 未解决，不把网页声明与实时统计混写成已经核实的同一任务全集。仓库集合一致是实际比较结果。
- 同时观察到任务数据集 revision `9af83fbfb3db47baa5ec0b15268c1b68acdec963`，SFT 数据集 revision `e378a60ddd7050fe9519a31a4d41d4872eeec6ac`。HF viewer 的统计接口是可变服务，本次没有证明其快照与前述固定 revision 的逐字节绑定。
- [SFT 数据卡](https://huggingface.co/datasets/TIGER-Lab/SWE-Next-SFT-Trajectories/blob/e378a60ddd7050fe9519a31a4d41d4872eeec6ac/README.md)把数据描述为来源任务生成的 3,693 条 `messages` 轨迹；发布字段没有可直接用于本次审查的逐行 repo / instance 映射。未下载 215,812,925 字节轨迹做内容扫描；也未下载 1,099,116,615 字节完整任务 JSONL。因此没有完成逐轨迹、逐提交或精确题目去重。
- 尝试首个 Marshmallow 精确仓库 filter 时服务请求在 40 秒后超时，未据此报告零匹配，也未追加反复请求。表中结果来自论文完整清单与 statistics。
- Qwen2.5-Coder 基座预训练、它原有的后训练，以及公开轨迹中对依赖库的间接提及均未被这一仓库级审查覆盖。六个本项目新合同也不意味着底层公共 API 对基座从未可见。

## Devstral 与当前 9B 的未知范围

在检查的 Devstral 模型卡、固定配置和官方发布中，没有找到可以逐项核对的完整预训练 / 后训练仓库清单。在检查的 Qwen3.5-9B 模型卡与配置中，也没有取得这四个仓库的完整训练暴露清单。两者针对四个仓库的历史训练暴露均记录为 **unknown**；缺少披露不能改写成不重合。本轮不凭这种未知扩大候选名单，也不以官方成绩代替同协议开发筛选。

## 与审计及后续理论比较的衔接

当前可用的是用户本轮审计和仓库既有理论资料；主任务检索未取得 V1.3 全文，不能声称已逐式核对完整 V1.3。按明确审计要求，后续主理论比较需恢复对数 N、历史锚和覆盖锚，并区分不读取专用语义类别 / 工作图的 G-raw 与共享类别先验的辅助 G-lift。此处记录对齐要求，不猜测缺失公式、参数或实现细节。

模型资格与开发筛选通过后，应冻结一个共同运行组合，再开展同模型、同完整学习起点、同批当前经历的分配比较。跨架构模型不得复用旧 9B 的 LoRA 或优化器。O1 的任务形成、公开正常路径覆盖、新载体的工作能力以及理论分配公式是不同改动，均需对应证据；本轮来源审查本身没有产生算法收益、模型收益或更新资格结论。


## 附：固定身份下载源的有界探针

原下载器继续运行期间，只对两个已冻结候选核查官方 ModelScope 同名仓库元数据，并做共 **5 MiB** 的严格 Range 速度探针；没有停止下载、修改模型文件或启动另一份大权重下载。

ModelScope.cn 中 SWE-Next 的 **6/6** 分片、Devstral 的 **10/10** 分片，其声明 SHA-256 与大小全部匹配冻结 HF 元数据。对应 ModelScope revision 为 `9a2331e309eba573dace3c20f6bc80c05067563b` 和 `fd677dc8b6f1abd36f93342a552529b686439b66`。元数据入口分别为 [SWE-Next 官方同名仓库](https://www.modelscope.cn/api/v1/models/TIGER-Lab/SWE-Next-14B/repo/files?Revision=9a2331e309eba573dace3c20f6bc80c05067563b&Recursive=true)与 [Devstral 官方同名仓库](https://www.modelscope.cn/api/v1/models/mistralai/Devstral-Small-2507/repo/files?Revision=fd677dc8b6f1abd36f93342a552529b686439b66&Recursive=true)。这证明所查远端声明身份一致，实际大文件下载完成仍须校验完整字节。

| 候选第一分片首 1 MiB | 官方 HF | ModelScope.cn | ModelScope.ai |
|---|---:|---:|---:|
| SWE-Next-14B | 4.086 秒 | 1.343 秒 | 4.870 秒 |
| Devstral-Small-2507 | 4.873 秒 | 1.207 秒 | 未做；元数据请求超时 |

五份成功探针均返回准确 `206` 和 `Content-Range`。同一候选在成功来源的首块 SHA 完全相同。该小块观察支持尝试 ModelScope.cn 传输，但不是持续吞吐、64 连接扩展收益或完成时间的证据。

可选实施方案是同一目标保持一个写入者，按固定 revision 使用带 durable journal 的并发范围下载，最终仍按 HF 的完整 LFS SHA 验证；Devstral 继续只取十份 HF 兼容分片，不下载重复的 consolidated 文件。若接续现有 HF 前缀，应先建立可核查的块记录，不能把预分配逻辑长度当成有效数据。该探针阶段未切换原下载进程；后续受控接续的实际情况见下一节。原始探针与元数据保存在 `runs/v030-model-research/transport-probes/`，结构化摘要已写入对应研究 JSON。


## 下载接续实现与启动观测

按主任务授权落实 `scripts/download_models_v030.py` 的范围下载。旧 PID `2220558` 的命令、同用户身份、工作目录、启动标识 `351253785` 与 `PID=PGID=SID` 均核对一致；通过系统 Python 的 pidfd 发送 SIGTERM，并观察到同一进程退出后，才启动新写入者。旧日志、启动参数、原 manifest、42 个缓存项的清单保存在 `runs/v030-models/transition-to-modelscope-range/`。旧 HF 缓存当时逻辑大小 **10,297,029,211 字节**，全部原位保留为未验证 fallback；没有按其长度导入已完成范围。

实际下载保持两个固定候选及原 CLI 的 metadata / asset / report roots，每模型最多四个分片、每分片八个范围，合计最多 64 个范围连接；分块为 32 MiB，未增加模型、consolidated 副本、量化或 GPU 运行。下载器取得 asset-root 文件锁，减少误启动第二个受管写入者的风险。每个 HTTP 范围必须返回准确 `206`、`Content-Range` 和字节数量；短响应、越界响应或错位范围均拒绝。范围数据 fsync 后写入带 hash 的 journal；完整分片只有通过冻结 HF 的整文件 SHA 后才原子提升为正式文件。

所有 tokenizer/config 小文件先行。LFS 小文件用冻结 HF SHA，其他小文件用固定 HF `blobId` 对实际 Git blob 字节校验，而不是只检查大小。SWE 的完整 tokenizer / chat template 以及 Devstral 的 19,399,650 字节 `tekken.json` 均已验证落盘；两模型所有小文件通过后才放行权重分片。每个正式 `files` 记录都包含 `bytes`、`sha256`、`mtime_ns`，`status=complete` 仍要求全部冻结文件通过，metadata_ready 不代表模型可加载。

新后台 PID **2249361** 于北京时间 **12:51:35** 启动，日志为 `runs/v030-models/range-download.log`，启动与精确源码 SHA 见 `range-download-launch.json`。必要验证为 **9 项控制通过**及下载器/对应测试的 Ruff 通过；包括固定源身份、非 LFS blob 身份、精确范围、长短响应拒绝、整文件 SHA 门和复用 journal 的损坏恢复。没有做与资产下载无关的 GPU 或模型能力测试。

北京时间 **12:52:36—12:54:36** 的 120 秒观测中，两模型均为 downloading_weights，进程存活；当时尚无完整 32 MiB 范围封口，durable_range_bytes 为 0。另一对实际进程 I/O 读数相隔 **119.389706 秒**，`write_bytes` 从 **628,350,976** 增至 **1,226,039,296** 字节，对应 **4.774281 MiB/s**。进程 I/O 包含少量日志/元数据，是在途写入证据，不是已经完成或完整 SHA 认可的模型数据。该窗口不能证明已较旧下载持续提速，也不支持完成时间保证。原始观测在 `runs/v030-models/range-startup-throughput.json`；后续下载结果应另以最终完整 manifest 为准。
