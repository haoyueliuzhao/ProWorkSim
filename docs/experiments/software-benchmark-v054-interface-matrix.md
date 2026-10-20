# v054 接口能力矩阵：Verified 500／REF／MATCH／PROJECT

后续修订：用户已明确授权修复下列文件数量／大小及新增、删除、重命名缺陷。新v054实现与17项合成CPU控制见 [受管文件修复记录](software-benchmark-v054-file-repair.md)。下面按`b06c8f2`整理的“当前”列是修复前的审计事实；正式PROJECT将明确绑定修复后的新版本，不能把两者混称同一接口。未增加不受管bash、任意命令或跨文件搜索。

状态：方案修订与接口审计，未授权本轮模型运行。审计日期：2026-10-20；代码基点：`b06c8f2`。本文只阅读接口、运行器和导出代码，没有读取任何题目的 gold patch 或 `test_patch`，没有执行真实题目、环境资格或模型调用，没有修改旧冻结资产。

本轮目标按用户指定切换为 SWE-bench Verified 官方 test 全部 500 题，比较 REF、MATCH、PROJECT。现有 v052／v053 不能直接更换数据集名称后作为这三组运行。本轮测量当前 PROJECT，保持其既有能力与限制：当前受管文件接口没有通用仓库的创建、删除、重命名和命令能力；这些是需要冻结和报告的覆盖限制，不是本轮默认补齐的功能。必要适配限于 Verified 公开任务／基线接入、隐藏评分隔离，以及如实导出现有可表达状态；旧候选规范化不得额外丢弃这些状态。

## 三组身份与当前实现

| 组别 | 本轮含义 | 本地已有什么 | 当前不能声称什么 |
| --- | --- | --- | --- |
| REF | 外部原生 OpenHands 参考配置 | v052／v053 均实际使用官方 SDK 的 `Agent`／`Conversation`，但显式只注册 Terminal＋Finish，并替换终端执行器。见 [v052:95](../../src/proworksim/software_bridge_openhands_v052.py#L95)、[v053:508](../../src/proworksim/software_panel_native_v053.py#L508)。 | 这不是未经修改的完整默认 OpenHands preset，也没有已经绑定本轮外部 REF 配置。不能直接把旧 `OH_ref` 名称当作新 REF。 |
| MATCH | 保留与 REF 相同的原生接口，匹配项目推理预算 | 可复用原生 SDK 循环和精确 token 预约／结算框架。v053 [账本:105](../../src/proworksim/software_panel_native_v053.py#L105)、[请求与工具绑定:327](../../src/proworksim/software_panel_native_v053.py#L327)。 | 尚无 REF→MATCH 的新配置差异清单；必须明确只匹配哪些推理参数，不能顺便改工具、题面、历史策略或候选选择。 |
| PROJECT | 真实 S1 受管 OpenHands，保留 PS1＋Γ1 等项目机制 | v052 通过受控的两个 assessment import 替换继承 v051 真实 managed collector；不是另写简化 agent。见 [v052 binding:74](../../src/proworksim/software_bridge_managed_v052.py#L74)。 | 当前接口不具备一般仓库的全部合法操作，不能通过旁接未受管 bash 把缺口掩盖成已有能力。 |

PROJECT 实际调用链：

```text
software_bridge_managed_v052.collect_episode
  → software_calibration_collector_v051.collect_episode
  → context_transport / SoftwareContextTransport（Γ1）
  → build_runtime / HarnessPort / StableO1Worker
  → 官方 OpenHands Agent / Conversation
  → 项目注册的受管工具 → 带版本的项目工作树
```

证据：[collector 建立 Γ1 transport:411](../../src/proworksim/software_calibration_collector_v051.py#L411)、[受管端口及 worker:302](../../src/proworksim/software_calibration_collector_v051.py#L302)、[实际 SDK Agent:251](../../src/proworksim/harness_sdk.py#L251)。受管 Agent 的 `include_default_tools=[]`、`condenser=None`，工具经过 `_GatewayExecutor`；其控制和历史机制不能被原生 TerminalTool 悄悄替代。

## 逐能力矩阵

“原生”列指现有 v052／v053 的实际能力基础，不表示新的 REF／MATCH 已完成配置与验证。本轮不因表中限制扩展 PROJECT 工具或放宽容量。若未来选择受管扩展，必须另立版本并明确声明，不能仍称为本轮原 PROJECT。

| 能力 | PROJECT 当前实际支持／限制 | 原生 REF／MATCH 的可复用基础 | 本轮冻结／部署限制与适配边界 |
| --- | --- | --- | --- |
| 完整代码树浏览 | `list_files` 只列 `bundle["files"]` 中已索引文件；`read_file` 每次最多 180 行。原 source provider 初态硬限 200 文件、2 MB，且仅文本。见 [list_files:114](../../src/proworksim/software_collaboration_v029.py#L114)、[read_file schema:52](../../src/proworksim/software_collaboration_v027.py#L52)、[provider bounds:18](../../src/proworksim/repository_sources_v051.py#L18)。 | v053 terminal 在真实 Docker `/testbed` 执行命令，可用仓库内现有工具列目录、读取文件，不经过小型 JSON 初态文件表。见 [terminal:427](../../src/proworksim/software_panel_native_v053.py#L427)。 | 冻结现有 200 文件／2 MB／文本范围，依据公开基线和事前通用规则检查能否装载；不能按答案文件列表选取子集，也不能据此删掉 Verified 题目或静默扩大上限。超出能力的题保留部署限制记录及完整 500 题分母。未来完整仓库索引扩展须另版本。 |
| 搜索 | `search_file` 是单个已索引文件内字面量搜索，查询最多 200 字符，只返回前 30 行及总匹配数；没有递归搜索和续页 cursor。见 [实现:232](../../src/proworksim/software_collaboration_v027.py#L232)。 | 终端可调用环境中已有的 `grep`／`rg`／Python 等，是否安装具体工具由原镜像决定；当前 runner 不额外提供原生代码搜索工具。见 [普通命令分派:447](../../src/proworksim/software_panel_native_v053.py#L447)。 | 本轮冻结单文件字面量搜索及既有限额，如实报告缺少跨文件搜索／续页的限制。未来若新增受管跨文件搜索或分页，须另版本，不在本轮通过旁路提供。 |
| 多文件修改 | 可以连续调用 `write_file`／`replace_file` 修改多个已声明文件，每次产生新版本；没有一个动作内的多文件事务。`replace_file` 必须唯一精确匹配，整文件写入上限 300,000 字节。见 [写入:120](../../src/proworksim/software_collaboration_v029.py#L120)、[替换:132](../../src/proworksim/software_collaboration_v029.py#L132)。 | 一个合法终端命令可修改多个仓库文件，文件变化持续到下一命令；SDK 记录命令和真实返回。见 [终端记录:460](../../src/proworksim/software_panel_native_v053.py#L460)。 | 本轮保留逐操作版本和现有动作粒度；如实导出全部已产生修改，不能只接收某个主文件。不增加多文件事务工具；与原生接口的动作粒度差异单独披露。 |
| 新增文件 | **未支持**：`_write_file` 要求路径已在 `editable_paths`，并直接读取 `bundle["files"][path]` 的旧内容。见 [实现:120](../../src/proworksim/software_collaboration_v029.py#L120)。 | shell 能创建文件，但 v052 最终只接收三个旧模块规则内的新 `.py` 文件；v053 tar 可记录通用普通文件。见 [v052 过滤:29](../../src/proworksim/software_calibration_native_grade_v051.py#L29)、[v053 文件成员:689](../../src/proworksim/software_panel_docker_v053.py#L689)。 | PROJECT 当前不支持，冻结并报告这一能力限制；不依据 gold 认定某题必需 create，不因此跳过或替换题目。未来受管 create 扩展须另版本。原生组已产生的新增文件应按其候选合同如实导出。 |
| 删除文件 | **未支持**独立删除路径；写空字符串只是清空文件。当前工具表没有 delete。见 [文件工具表:49](../../src/proworksim/software_collaboration_v027.py#L49)。 | shell 可删；v052 仅保留声明生产文件的删除，其他删除会被恢复；v053 在独立 judge 中清除旧源码后导入候选，因此可表达普通源码的缺失。见 [v052:49](../../src/proworksim/software_calibration_native_grade_v051.py#L49)、[judge:1149](../../src/proworksim/software_panel_docker_v053.py#L1149)。 | PROJECT 当前不支持，冻结并报告，不能把写空文件称为删除。本轮不新增 delete；未来受管扩展须另版本。对原生组实际发生的删除，候选导出不得恢复该路径或改为空文件。 |
| 重命名／移动 | **未支持** rename；因 create/delete 都缺失，也不能完整等价组合。固定补丁 changed paths 只遍历原 editable 清单。见 [fix_patch:147](../../src/proworksim/software_collaboration_v029.py#L147)。 | shell `mv` 可执行；能否成为最终候选取决于旧导出过滤。 | PROJECT 当前不支持，冻结并报告，不在本轮新增 move/rename 或 create＋delete 组合。未来扩展须另版本；原生组的实际移动可用删除＋新增等价导出，不要求 Git 必须标记为 rename。 |
| 配置／构建文件 | 当前 PS1 明确把原测试与 supporting files 设为只读；`editable_paths` 来自旧 provider 的预声明生产范围。见 [世界契约:69](../../src/proworksim/software_calibration_world_v051.py#L69)、[提示:93](../../src/proworksim/software_calibration_world_v051.py#L93)、[source contract:115](../../src/proworksim/repository_sources_v051.py#L115)。 | terminal 能编辑，但 v052 canonical 恢复只读文件；v053 `protected_path` 统一保护 `pyproject.toml`、`setup.cfg`、`tox.ini` 等，judge 会恢复它们。见 [v053:89](../../src/proworksim/software_panel_docker_v053.py#L89)。 | PROJECT 本轮保留其配置／support 只读能力边界，不能把它宣称为 Verified 对全部组的官方限制，也不默认扩大 editable_paths。三组各自真实可表达的改动须如实导出；原生组合法配置不能被旧统一恢复规则静默覆盖。未来放宽 PROJECT 配置编辑须另版本。 |
| 合法命令 | **没有通用命令工具**。受管项目工具包含固定 `run_tests` 等动作，工具调用经 `HarnessPort` 和世界端口记账。见 [HarnessPort:79](../../src/proworksim/harness_port.py#L79)、[S1 工具继承:33](../../src/proworksim/software_calibration_world_v051.py#L33)。 | v053 使用真实容器 terminal；普通命令 timeout 夹在 1–60 秒，shell 状态和后台任务不跨命令，拒绝交互输入／reset／空轮询。见 [终端分派:435](../../src/proworksim/software_panel_native_v053.py#L435)。这是显式缩减的执行器，不是默认持久 terminal。 | 本轮保持 PROJECT 无通用命令的事实，只使用现有受管动作；禁止旁接未受管 bash，也不以新增受管命令作为放行条件。未来若扩展命令能力，必须另版本并保留网关、状态／历史／计量约束；不能仍称本轮原 PROJECT。 |
| 公开测试 | 当前 PS1 `run_tests` 固定执行完整旧原仓库测试，至多 32 次；同一集合用于终评。v052 native `bridge_run_tests` 还在独立树中恢复原 tests/config。见 [PS1:118](../../src/proworksim/software_calibration_world_v051.py#L118)、[旧预算:33](../../src/proworksim/software_collaboration_v033.py#L33)、[native public:263](../../src/proworksim/software_bridge_sources_v052.py#L263)。 | v053 已分离“actor 当前可见测试”和最终 judge，`run_public_tests` 在当前 actor 内执行。见 [backend:1093](../../src/proworksim/software_panel_docker_v053.py#L1093)。 | 将现有公开测试动作绑定到工作期允许看到的基线测试；各组只使用其既有工具能创建的自建测试或执行的命令，不能恢复或调用隐藏终评材料。旧“完整原测试全部公开”合同不复用，但不据此给 PROJECT 新增写测试／命令能力。本次没有读取 `test_patch` 内容决定公开工具或权限。 |
| 测试结果分页 | 真实支持：每个公开执行保存不可变报告，首页 3,072 Unicode 字符，`read_test_result(report_id,cursor)` 读取原报告后续页，不再执行测试、不重置预算。见 [协议:24](../../src/proworksim/software_organization_v042.py#L24)、[保存与读取:223](../../src/proworksim/software_organization_v042.py#L223)。 | v053 native 返回官方 TerminalObservation，没有项目式 `read_test_result` cursor；可通过命令将日志保存到工作树后按需读取，但这不是自动等价的分页工具。见 [返回:468](../../src/proworksim/software_panel_native_v053.py#L468)。 | PROJECT 可复用分页与身份机制，替换报告来源为允许的公开执行。REF／MATCH 维持相同原生反馈接口；不能为 MATCH 单独注入项目分页。 |
| 历史／记忆访问 | `work_history_search`／`work_history_read` 只访问本成员已见 observation／真实工具返回；搜索最多 5 条，整条 exact read 不等于通用分页。Γ1 保留最新反馈和页面、做有限同输入字段引用及上下文选轮。见 [历史工具:28](../../src/proworksim/harness_port.py#L28)、[搜索实现:130](../../src/proworksim/harness_port.py#L130)、[Γ1:233](../../src/proworksim/software_context_v048.py#L233)。 | 官方 Conversation 历史持久化在宿主 evidence 中；当前无项目 history-search 工具，`condenser=None`。见 [原生会话:520](../../src/proworksim/software_panel_native_v053.py#L520)。 | PROJECT 保留真实 Γ1 和成员私有历史，不把全部原始历史强行塞回上下文，也不将未见材料作为检索来源。REF 与 MATCH 的原生历史／condenser 设置须一致并单独冻结。 |
| 最后工作树 | v052 managed 在评分前锁定当时 `member_001` 的真实 bundle，再检查源引用与字节哈希未改变。见 [预锁:24](../../src/proworksim/software_bridge_managed_v052.py#L24)、[锁后检查:46](../../src/proworksim/software_bridge_managed_v052.py#L46)。 | v053 在 SDK 结束后调用后端唯一导出，不按评分选择候选。见 [收口:585](../../src/proworksim/software_panel_native_v053.py#L585)、[不可覆盖锁:1101](../../src/proworksim/software_panel_docker_v053.py#L1101)。 | 可复用“停止→唯一锁→终评”的顺序；Verified 导出需如实承接各组现有可表达状态，不沿用旧三仓库专属过滤，也不借此扩大 PROJECT 写权限。统一主候选选择规则，不以曾固定提交为由换一个更好树。 |
| 最后合法固定提交 | PROJECT 已有 `fix_patch`＋`submit_integration`，提交需当前版本曾真实执行测试且存在该版本固定补丁，不要求测试必须绿；终态取 `deliveries[-1]`，无提交记录时固定交付端点为 0。见 [提交条件:368](../../src/proworksim/software_collaboration_v027.py#L368)、[最后交付:316](../../src/proworksim/software_calibration_world_v051.py#L316)。 | native Finish 不等同项目固定提交；v052 prompt 明确无该合同。见 [native prompt:191](../../src/proworksim/software_bridge_openhands_v052.py#L191)。 | 保留 PROJECT 的过程交付为独立诊断，明确它与最后工作树是否相同；不从历次补丁择优，不将“无固定提交”替换为官方最后工作树能力分数 0。原生两组该项目端点记不适用。 |
| 候选无损导出 | 当前 bundle 仅 `str→str`，不能表达二进制、符号链接、模式；v052 canonical 会恢复只读文件并丢弃非旧生产域新增文件。见 [候选过滤:38](../../src/proworksim/software_calibration_native_grade_v051.py#L38)。 | v052 `read_worktree` 拒绝 symlink／非 UTF-8，上限 5,000 文件／32 MiB。v053 tar 保留普通文件字节、可执行位与安全相对 symlink，但排除固定目录、拒绝 hardlink／special，模式规范化为 0644／0755。见 [v052:108](../../src/proworksim/software_calibration_v051_mini.py#L108)、[v053:665](../../src/proworksim/software_panel_docker_v053.py#L665)。 | 以各组当前可表达状态为导出对象，验证官方应用方式能重建该状态；PROJECT 的文本／路径限制本轮不放宽，也不宣称支持全部 Verified 文件类型。公开基线无法由当前 PROJECT 承载时逐题记录部署限制，保留完整分母；导出不能无声裁剪，未来扩展字节／链接／模式能力须另版本。 |

## 预算匹配与身份不混同

现有项目推理事实为 18,432 上下文、2,048 输出、非 thinking、temperature 0.7、top-p 1、top-k 0、每次生成 600 秒上限；单成员池 128 decisions／128 attempts／500,000 实际输入＋输出 token，公开测试 32 次；episode 5,400 秒软边界与 6,000 秒硬边界。证据：[执行 contract:52](../../src/proworksim/software_calibration_collector_v051.py#L52)、[共享预算:33](../../src/proworksim/software_collaboration_v033.py#L33)、[episode 检查:394](../../src/proworksim/software_calibration_collector_v051.py#L394)。

这些是旧实现的审计事实，**不是本文已经冻结的 v054 参数**。MATCH 必须逐字段列出与 PROJECT 匹配的预算；模型版本、采样、上下文、输出上限、实际计费、生成时间、工具时间和测试次数不能笼统合并成“相同预算”。例如当前原生 runner 没有 PS1 的 32 次专用公开测试上限，普通 shell 中也可能执行 pytest；若要匹配测试机会，必须有明确定义，不能只匹配 magic command 计数。

PROJECT 的 Γ1、受管动作、历史检索和固定提交过程是该组的实际机制。MATCH 与 REF 使用同一原生工具／历史合同；不能给 MATCH 加 Γ1、给 PROJECT 加未受管 terminal，再把两组称为原定比较。

## 可复用的运行器部件

| 部件 | 可复用内容 | 不能直接沿用的绑定 |
| --- | --- | --- |
| `software_bridge_managed_v052.py`＋v051 collector | PS1 真实单成员调度、SDK worker、Γ1、受管事件、预算结算、终态／交付双端点的锁顺序。 | v052 slot 前缀、CAL2 六题 provider、公开完整原测试与数据集特有评分绑定需适配；原工具能力、容量及配置只读限制本轮保留并披露，不能当作可随接入默认放宽的项目。见 [binding:96](../../src/proworksim/software_bridge_managed_v052.py#L96)、[provider:145](../../src/proworksim/software_bridge_sources_v052.py#L145)。 |
| `software_panel_native_v053.py` | 官方 SDK 调用、terminal 接口分派、精确 token 账目、身份 guard、一次候选导出。 | SWE-smith prompt、单条件名称、固定数值常量、200＋40 repeat 行绑定，以及“Terminal＋Finish 即完整外部 OpenHands”的误称。 |
| `software_panel_docker_v053.py` | 专用 daemon、按 immutable image ID 独立容器、资源边界、后台进程清理、候选锁、字节快照基础。 | SWE-smith mirror main／U/C/T/B 初态、注入数据集 bug patch、删除 F2P 文件、反向补丁 gold、原 profile parser、统一恢复配置与自定义严格 R。见 [prepare_checkout:564](../../src/proworksim/software_panel_docker_v053.py#L564)、[strict R:759](../../src/proworksim/software_panel_docker_v053.py#L759)。 |
| `scripts/software_panel_run_v053.py`／host supervisor | 已进入 slot 不自动重跑、资源故障与模型尝试分开、后台进程记录和中断证据。 | 行数校验明确要求 280 episode／200 main／40 repeats，不能给 500×3 方案套旧计划。见 [plan validation:49](../../scripts/software_panel_run_v053.py#L49)。 |
| 报告与审计框架 | 保留技术未知、实际 token／时间、失败原因、每个候选的不可变引用。 | 旧六题、分层 SWE-smith 200 题、旧 `R_joint` 与 Verified 官方结果不是同一个分母或评分口径。 |

## 从 SWE-smith 迁移时必须分开的语义

1. **全 500 题是固定目标集合。**旧“二十仓库×十题全合格才选入、按后续仓库补齐”的规则不能复用，否则会把 Verified 全集改成新的筛选面板。环境失败要保留对应题的状态，不能悄悄替换题目。旧规则见 [selection rules:33](../../src/proworksim/software_panel_v053.py#L33)。
2. **初态不是人工注入缺陷树。**v053 的 `task["patch"]` 被当作 bug 注入，gold 则反向应用；此逻辑绑定 SWE-smith 任务含义，不能迁移到 Verified。v054 必须通过其官方基线／环境适配器建立工作树，禁止将答案补丁作为初始化材料。
3. **不能按 F2P 列表删除工作期测试文件。**这是 v053 对 SWE-smith 分支的重建，Verified 需要自己的官方工作期／终评边界；三个实验组看到的公开材料应相同。也不能沿用 v051“终评完整测试集合全部公开”的另一极端。
4. **不能把 gold 转移检查变成全集准入筛选。**旧 `admission_verdict` 要求 clean/gold 每项过、bug 每项 F2P 明确 FAILED／ERROR；节点缺失即排除。这是旧面板标准，不是 Verified 全集的默认资格规则。见 [实现:825](../../src/proworksim/software_panel_docker_v053.py#L825)。
5. **不能把旧主 R 当官方分数。**v053 另设所有必要状态必须 PASSED／XFAIL 的严格 R，并保留 `official_R`。v054 主结果应绑定用户指定的官方评分器与版本，不静默沿用旧规则；项目过程交付指标单列。
6. **如实导出当前能力产生的状态，不借导出扩展 PROJECT。**Verified 适配不能继续使用 boltons／parse／xmltodict 专属 canonical，额外丢弃各组真实候选改动。PROJECT 当前不可创建、不可编辑配置及文本容量等限制则保持不变，作为能力／部署限制报告；不能把取消这些限制当作导出修复。旧 raw candidate 与 grading tree 分开保存的审计设计可用，二者差异必须可解释，不能静默裁剪。

## 准备阶段的完成条件

这份矩阵不是运行准入。进入本轮真实评测前，需要绑定官方 500 题清单及官方环境／评分版本，固定 REF 与 MATCH 的同一原生接口和明确预算差异，并预先冻结当前 PROJECT 的工具、文件容量、可写范围和历史机制。本轮必要适配限于公开任务／基线接入、隐藏评分隔离及如实导出现有可表达状态；机械 fixture 只核验这些接缝，不以补齐 create/delete/rename/search/bash 或取消 200 文件限制作为放行前提。分别锁定最后工作树和 PROJECT 最后合法交付的端点规则。

若公开基线不能被当前 PROJECT 装载，或实际运行暴露能力限制，逐题保留原因与结果状态，维持完整 500 题分母；不能只统计已支持子集、替换题目或依据 gold 判断某题必须使用某工具。覆盖过低时如实报告当前系统的覆盖实况，不在看到结果后放宽接口。未来若决定扩展受管能力，必须另版本、另声明其比较含义。

本次没有执行上述适配、机械 fixture 或正式运行。本轮不为补齐矩阵而扩展 PROJECT，也不增加绕过管理器的 bash。
