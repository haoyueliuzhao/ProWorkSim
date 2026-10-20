# v0.5.4：SWE-bench Verified 数据、镜像与官方评分依据

核对日期：2026-10-20（Asia/Shanghai）。

后续准备更新：用户已要求实际准备数据与环境。固定数据已通过ModelScope国内直连取得并按官方SHA核验，全部500-ID及1500预定槽已物化；评分器5.0.2已独立安装且500条规格CPU检查通过。见[数据准备](software-benchmark-v054-data-preparation.md)及[评分准备](software-benchmark-v054-scorer-preparation.md)。下文“本文形成时”的未完成记录为初次调查状态，保留其证据和判断范围，不代表后续准备的最新进度。模型运行授权仍为false。

本轮方案改用官方 SWE-bench Verified `test` 全部 500 题；REF、MATCH、PROJECT 三组共用同一任务身份、官方评分依据和原始 Qwen3.5-9B，无 LoRA，均为单 Agent。本文核实来源与评分接口，列出正式准备必须闭合的身份链；不构成新增模型运行授权。组间方法、预算和执行授权以 v0.5.4 主方案为准。

本文形成时只进行了官方网页、小元数据与源代码阅读。未启动容器、模型、GPU 或评分任务，未下载 500 个镜像。主代理通过现有国内下载入口尝试获取固定数据文件，但发生未批准的重定向，下载未完成；500 题身份清单和 1500 个具体运行槽均未物化。本轮只完成方案规格，运行授权和预算授权均为 false。v0.5.3 的 SWE-smith 镜像、任务资格和 200/40/280 库存均不等于本批 Verified 的准备结果。

## 1. 已核实的数据版本

| 字段 | 本次核实值 |
| --- | --- |
| 官方数据集 | `SWE-bench/SWE-bench_Verified` |
| 配置、分片 | `default`、`test` |
| 固定 revision | `78f471bf655a3137b2e8a75af1501690ec009ec3` |
| 官方声明题数 | 500 |
| 数据文件 | `data/test-00000-of-00001.parquet` |
| 文件大小 | 6,304,616 bytes |
| 官方 LFS SHA256 | `030cfd7f2a704c4c0226e7f104c725a3b41230b1d3517f9c915ad7ea5be3fa25` |
| 解压后数据量元数据 | 9,109,903 bytes；这不是下载文件大小 |

官方 `main` 文件页指向上述提交，提交差异直接提供文件大小和 LFS 内容哈希；数据卡声明 `test` 为 500 条。本次网页工具对 `main`/README 标记为“today”，提交页为“yesterday”，未提供精确抓取时刻。这里的“当前”限于本次官方网页核对，不把后续变化的 `main` 当成实验版本。[官方 main 文件页](https://huggingface.co/datasets/SWE-bench/SWE-bench_Verified/tree/main)、[固定提交及 LFS 元数据](https://huggingface.co/datasets/SWE-bench/SWE-bench_Verified/commit/78f471bf655a3137b2e8a75af1501690ec009ec3)、[官方数据卡](https://huggingface.co/datasets/SWE-bench/SWE-bench_Verified/blob/main/README.md)。

固定原站身份 URL：

```text
https://huggingface.co/datasets/SWE-bench/SWE-bench_Verified/resolve/78f471bf655a3137b2e8a75af1501690ec009ec3/data/test-00000-of-00001.parquet
```

该 URL 用于说明原始身份；宿主下载须使用项目批准的国内直连入口，保持 revision、文件大小及 SHA256 不变。镜像地址不可达、重定向域名未批准、内容身份不符时暂停，不自动回退原站或代理。国内镜像同步状态本身不能证明官方最新。

### 1.1 本轮国内获取状态

主代理使用现有国内直连工具访问固定 revision 的 `hf-mirror.com` 文件地址，收到 HTTP 302，目标为 `cas-bridge.xethub.hf.co`。该域名不在既有白名单，工具正确拒绝继续；数据 payload 为 0，未发生原站或代理 fallback。因此不能将这次请求记录为文件已下载、已验 SHA 或本地数据就绪。

补充的小量网页查询发现 [ModelScope 同名数据集](https://www.modelscope.cn/datasets/SWE-bench/SWE-bench_Verified)，页面显示 2.10MB、更新时间 2026-08-18，说明仍将 F2P/P2P 列为字符串。网页工具对其文件列表和仓库树元数据端点无法取得内容，也没有获得目标 SHA256 或固定 revision 的对应证明。页面抓取标记为 6 天前；仅凭名称或更新时间不能认定它与本轮 6,304,616-byte 文件相同，也不能断言实际仓库内容必然仍为旧版。

当前结论是：尚未确认能交付上述完整 SHA256 的国内替代来源。本轮不继续扩大搜索或尝试全文件下载，不切换到未核实的同名版本。500-ID 身份清单、1500 个实例化 slots/seeds 及镜像库存保持未准备状态。

### 1.2 500 题身份清单的形成

本次没有发现可直接下载、同时绑定上述 revision 的独立官方 500-ID 文件。当前可实施路径为：只获取这份固定小型 parquet，在可信 CPU 准备进程中以列投影读取 `instance_id`、`repo`、`base_commit`、`image`，输出身份清单；不要为了形成题单读取或打印 `patch`、`test_patch`、评分脚本或测试答案。

正式身份清单应包含：

1. 来源 revision、原文件相对路径、大小和 SHA256。
2. 全部 500 个不同 `instance_id`，每项绑定 `repo`、完整 `base_commit`、原始 `image` 字段。
3. 明确的规范排序、序列化规则及清单 SHA256；三组引用同一清单。
4. 完整性断言：行数为 500、ID 无重复、必需身份字段非空、集合来自完整 `test`，没有按仓库、难度、环境通过率或预期成绩抽取子集。

环境暂不可用的题仍保留在 500 题清单中并标注状态，不能用其他题替代。尚未生成并检查清单时，只能声称“官方数据声明 500 题”，不能声称“本地 500 题已准备完成”。

### 1.3 当前数据 schema 的实质变化

当前固定数据 schema 除身份、问题、补丁外，明确包含 `image`、`eval_script`、`log_parser`、`eval_type`。`FAIL_TO_PASS` 和 `PASS_TO_PASS` 为字符串列表，而不是必须再次 JSON 解码的字符串。数据卡正文中笼统描述“仅问题与 base_commit”的旧文案不能作为信息隔离依据，实际 schema 包含评分和答案字段。[固定提交的 schema 差异](https://huggingface.co/datasets/SWE-bench/SWE-bench_Verified/commit/78f471bf655a3137b2e8a75af1501690ec009ec3)。

实现必须显式区分 actor 输入投影与可信评分记录，不能把完整行通过提示、环境文件、日志查看工具或共享目录交给 Agent，也不能直接套用 SWE-smith 的 profile、mutation-family、bug/gold 生成流程。

## 2. 官方容器修复与本轮镜像身份

### 2.1 已确认的官方修复范围

2025-09-03 的官方仓库 issue #465 报告了未来 Git 历史可被 Agent 读取的问题。维护者于 2025-09-11 明确确认：Docker Hub 上全部 SWE-bench Verified 镜像已经更新，构建流程修复进入 PR #471 和 `swebench 4.1.0`；删除未来 Git 历史，保留历史提交及早于 `base_commit` 的标签。[官方 issue #465](https://github.com/SWE-bench/SWE-bench/issues/465)、[官方修复 PR #471](https://github.com/SWE-bench/SWE-bench/pull/471)。

这为本轮选择 Verified 官方镜像提供修复依据，但公告没有给出本次 500 个 `latest` 的完整 digest 清单。以下信息不能单独替代内容身份：`latest` 名称、镜像创建时间、下载日期、评分包版本，或 SWE-smith 镜像与官方当前 tag 相同。

### 2.2 镜像命名和 linux/amd64

Verified 的公开镜像实例采用类似以下名称：

```text
docker.io/swebench/sweb.eval.x86_64.pydata_1776_xarray-6992:latest
```

这里是按 `instance_id` 区分的评分镜像；`x86_64` 对应本轮所需的 `linux/amd64`。官方固定 digest 的公开问题报告提供了该命名的实证。[官方仓库 issue #640](https://github.com/SWE-bench/SWE-bench/issues/640)。

名称示例只是阅读辅助。正式下载表以固定数据每行 `image` 的实际值为起点，不仅凭字符串替换自行构造 500 个 tag。必须逐项确认 registry repository、tag/已有 digest 与平台；如果 metadata 是多架构 index，选择唯一 `linux/amd64` 子 manifest，同时保留顶层 index 和子 manifest 的 digest。单 manifest 的架构还需由 config 的 `os`/`architecture` 确认，不能因为名称含 `x86_64` 就省略平台证据。

### 2.3 “修复之后最新镜像”的可审计判定

正式准备时，为每题保留以下链条：

| 层级 | 必须记录的证据 |
| --- | --- |
| 数据身份 | 固定 revision、`instance_id`、`base_commit`、原 `image` |
| 官方当前 tag | 查询时间、原 registry/tag、响应 manifest 原始字节及内容 SHA256 |
| 平台身份 | 顶层 digest、选定 linux/amd64 digest、config digest、layer digest/size |
| 国内交付 | 使用的白名单 endpoint、重定向链、与官方内容 digest 的逐层对应 |
| 本地加载 | 实际 config/image ID 与平台；与已核验资产一致 |
| 最终 Agent 初态 | 实际工作树、可见 Git 状态、挂载与权限、已知泄露通道检查结果 |

宿主官方 registry 不可达时，可使用独立 CI 的官方 metadata 查询结果作为原站身份证据，宿主只从批准的国内服务获取相同内容。现有 `docker-image-manifests` 检查器及 v0.5.3 的 32-image inventory 属于 SWE-smith；需要为 Verified 新建输入和回执，不能将旧 32 项查询写成 Verified 500 项已核实。国内 registry 返回的相同内容可证明传输一致，不能独立证明官方 tag 目前仍指向该内容。

本轮尚未取得 Verified 全 500 项的上述镜像证据，也没有完成镜像环境检查，因此当前状态是“官方修复依据已核实；500 镜像身份及实际可用性待准备”。

### 2.4 Git 修复与全部可读文件隔离需要区分

2026-08-18 的 issue #640 报告另一通道：部分固定官方镜像的 Conda 缓存或 base 环境中有目标仓库较新源码副本。所查页面仍为 open，没有维护者已修复的回复。这是带固定 digest 的公开问题报告，不能扩写为全部镜像均受影响，也不能把 2025 年 Git 修复说成已经关闭该通道。[官方仓库 issue #640](https://github.com/SWE-bench/SWE-bench/issues/640)。

正式 actor 环境应针对可读的目标仓库副本、未来 Git 对象、答案和隐藏测试文件做必要核对；正常历史源码、已有普通测试和运行依赖仍保留。不能盲目删除全部 Conda、pip 或 uv 缓存，否则可能破坏评分环境。若确需权限隔离、定向屏蔽或派生镜像，三组使用同一预先冻结规则，记录与官方原镜像的差异及必要的兼容证据，不宣称这是未经修改的官方 actor 文件系统。

## 3. 官方 harness 版本及适配边界

### 3.1 可固定的软件分发版本

本次官方 PyPI 页面给出的最新稳定版是 `swebench==5.0.2`，发布于 2026-08-18。可固定的 wheel 为：

```text
swebench-5.0.2-py3-none-any.whl
sha256:b7f0416a1e686eca22c2f749b5f816685a202835032f6683080e2b53545bbb62
```

其 sdist SHA256 为 `faae7b1307b8188e842e78ef5826cf0d64fa78486adc41e3414f9533b9e0d7eb`。这是官方分发元数据核对，本文没有安装或执行该包。[官方 PyPI 5.0.2](https://pypi.org/project/swebench/5.0.2/)。

官方 GitHub 没有可供本次核对使用的 `v5.0.2` 路径，所试 raw URL 返回 404；因此不捏造该 wheel 对应的 Git commit。正式锁定应至少绑定 wheel SHA、实际安装文件哈希、依赖锁和解释器。若另外选择源码安装，需要单独确定完整 source commit，不能写 `main` 与 5.0.2 等价。

v0.5.3 为兼容 SWE-smith 曾使用 `swebench 4.1.0`，这项历史兼容选择不自动继承到新方案。4.1.0 是已核实的 Git 历史修复最低历史依据；5.0.2 是本次查到的最新稳定评分分发，两者用途不同。

### 3.2 必须闭合的读取与运行合同

官方当前 `main` 的 `make_test_spec` 按记录中的 `image`、`eval_script`、`log_parser`、`eval_type` 和 F2P/P2P 构造评分规格；这些字段与本次数据 schema 对应。本轮只将该源码作为适配风险证据，实际 5.0.2 wheel 的行为仍需在准备阶段做有限静态核对，不能将浮动 `main` 的所有功能归于该 wheel。[官方当前数据加载及 TestSpec 代码](https://github.com/SWE-bench/SWE-bench/blob/main/swebench/harness/utils.py)。

需要在正式执行前固定：

- 数据入口为已经核验的本地固定文件或其确定性可信评分导出；不把无 revision 参数的远端 dataset alias 当冻结输入。
- 缺失镜像时停止本题准备，不让评分器隐式拉取 Docker Hub 或重新构建漂移环境。
- parser、eval script、timeout、CPU/内存限制和候选补丁应用规则在三组间一致；不以项目自写测试判据替代官方 resolved。
- 官方评分进程及其完整数据、隐藏测试脚本、输出日志只能由可信后端访问。

这些边界有具体源码依据：官方当前数据加载器的远端分支调用 `load_dataset(name, split=split)`；运行器在本地镜像缺失时存在 `client.images.pull(image)` 路径。正式包装应阻断这两个漂移或绕过下载政策的入口，同时保持官方评分语义。[官方数据加载器](https://github.com/SWE-bench/SWE-bench/blob/main/swebench/harness/utils.py)、[官方运行器](https://github.com/SWE-bench/SWE-bench/blob/main/swebench/harness/run_evaluation.py)。

### 3.3 预测导出、缓存与评分记录

官方预测 JSON/JSONL 的核心字段是 `instance_id`、`model_name_or_path`、`model_patch`。每个 group/task 的最终候选只能按冻结规则导出一次，并保留原始补丁字节的 SHA256、候选来源、导出时间和对应模型成本记录。[官方 evaluation 指南](https://www.swebench.com/SWE-bench/guides/evaluation/)。

官方文档特别提示：重复使用相同 `run_id` 和实例可能直接复用旧评分，即使提交补丁已变更。当前源码也会在已有报告时直接返回；`model_name_or_path` 参与当前日志目录，但不能把仅更改模型名当成足够的缓存隔离规范。[官方 PyPI 缓存说明](https://pypi.org/project/swebench/5.0.2/)、[官方运行器](https://github.com/SWE-bench/SWE-bench/blob/main/swebench/harness/run_evaluation.py)。

三组应使用不同的 run_id；建议 run_id 同时关联本次冻结运行身份、group 和候选集合哈希。发生获准的评分修订时另建 run_id，保留旧报告及其错误原因。已有日志的重新解析不等于重新运行测试；镜像缓存复用也不等于评分结果可以跨组复用。

实际产物路径由锁定 wheel 确认并写入回执，不根据不同版本文档中的路径示例硬编码。至少保留候选补丁、官方原始报告、测试输出、实际 eval 脚本、运行日志、来源/镜像/评分软件身份；不能仅保留一个布尔值。

## 4. Actor 与可信评分侧的信息边界

| 内容 | Actor | 可信准备/评分侧 |
| --- | --- | --- |
| 冻结的问题文本、身份、历史工作树 | 按三组共同规则可见 | 可见 |
| 仓库内原有普通测试 | 可见并按工具规则运行 | 可见 |
| 官方 gold `patch` | 不可见 | 仅准备或评分所需的受控访问 |
| `test_patch`、隐藏 eval script、F2P/P2P 名单 | 不可见 | 按官方评分协议使用 |
| 其他组候选、隐藏评分反馈或历史答案轨迹 | 不可见 | 独立记录，不回流 Agent |
| 下载缓存、完整 parquet、评分日志、Docker socket | 不挂载给 Actor | 可信宿主控制 |

隐藏材料隔离覆盖提示、工具返回、文件挂载、可读路径、共享缓存和日志。只把 `patch` 从 prompt 删除不能保证隔离；完整 parquet 本身也不可放进 Agent 可读目录。模型已经停止并导出不可变候选后，才在独立评分初态中应用候选和官方隐藏测试。

按官方评分语义，完整 resolved 要求相应 F2P 与 P2P 均满足判据；不能以测试进程退出码、可解析输出存在或部分测试通过替代官方 resolved。[官方评分实现](https://github.com/SWE-bench/SWE-bench/blob/main/swebench/harness/grading.py)。

技术未知、未启动、缺预测和已确认模型失败分别记录。三组均保留完整 500 题库存；如果存在未闭合技术状态，报告完整分母及不确定范围，不能只对成功闭合子集给完成率。官方原始 resolved/error 分类保持原样保存，项目的技术归因另列，不覆盖官方输出，也不把“没有评分报告”直接当作可解释的模型失败。

## 5. 本次核实范围与后续必要准备

| 项目 | 本文完成时的状态 |
| --- | --- |
| 官方 Verified 数据 revision、test 数量、文件大小/SHA | 已通过官方小元数据核实 |
| 固定 parquet 国内下载 | 302 跳转域不在白名单，已拒绝；payload 0，未完成 |
| 仅身份列的本地 500-ID 清单 | 未物化，不能声称 local ready |
| REF/MATCH/PROJECT 的 3×500 slots/seeds | 仅有方案规格，1500 个具体运行槽尚未物化 |
| 500 个官方当前 tag / linux/amd64 digest | 待新 inventory 与官方 metadata 核对 |
| 500 镜像国内交付及本地加载 | 未在本次启动 |
| 2025-09 Verified Git 历史修复 | 官方维护者已确认 |
| 全部实际 actor 文件系统无已知泄露 | 尚未核验，不能以公告替代 |
| 5.0.2 官方包版本与分发 SHA | 已核实 |
| 锁定 wheel 的本地合同、依赖及评分准备 | 待实施 |
| 容器测试、正式模型运行、GPU | 本文工作均为 0；运行授权及预算授权均为 false |

必要准备应一次完成身份绑定、有限接口控制和对应环境检查；不为本文的文档修订运行重复测试。任一身份或公共系统故障未闭合时，保留全 500 题清单并标注未决，不能退回旧 SWE-smith 资产，也不能通过缩小题数制造“准备完成”。
