# v052 两路宿主与 PS1 评分装配方法

本文件说明 [software_bridge_v052.py](/data1/zhuxinrui/projects/ProWorkSim/scripts/software_bridge_v052.py) 与 [software_bridge_managed_v052.py](/data1/zhuxinrui/projects/ProWorkSim/src/proworksim/software_bridge_managed_v052.py) 的实现边界及已有控制，不是模型放行凭据。**截至本文编写时，v052 全局真实 `model_calls=0`，独立模型准入尚未签发。** CPU来源资格、初态 SDK 请求捕获、程序化响应控制和只读分析分别记录，不能计为真实模型生成。

初态记录修复属于独立输入执行协议，见 [输入资格方法](software-bridge-v052-input-qualification-method.md)、[原输入 release](software-bridge-v052-input-execution-release.json) 与 [独立 r2 release](software-bridge-v052-input-execution-release-r2.json)。本文不覆盖原失败、未决或计数，不替代该协议的实际闭合摘要，也不因宿主控制通过而自动认可十二份输入已准入。

## 固定面板与共同数值路径

库存固定为原 CAL2 的 boltons、parse、xmltodict 各两题，共六题 × `OH_ref`／`PS1` 两条件 = 12槽。task、source row、seed `202610180521—526`、两条件先后顺序和预算见 [设计清单](software-bridge-v052-design.json) 与 [总协议](software-bridge-v052-protocol.md)。宿主逐项验证清单，不按成绩、工作量或错误类型换题或追加样本。

两条件每槽均重新加载同一原始 Qwen3.5-9B 发布权重，明确 `checkpoint=None`，不挂 S_star、B、Q± 或其它训练适配器。两路共用 `software_calibration_runtime_v051.load_actor`、同一 model manifest、tokenizer 和 `path="project"` 数值 provider；每槽独立 resident、独立采样 seed 和 readonly guard。共同合同为非思考／不保留 thinking，C18432、O2048、temperature0.7、top-p1、top-k0、repetition penalty1，原 EOS `[248044,248046]`／pad248044，HF 生成迭代时间上限600秒。

每槽原额度为500,000实际输入＋输出 token、128决定、128attempt、90分钟软截止＋10分钟收口。全12槽上限6M实际生成 token、1536决定、1536attempt。PS1保留32次项目公开测试额度；OH的原生 terminal 命令和明确的共享测试入口单独实报，不能把二者测试机会宣称为完全等同。新增 actor／critic／optimizer／backward均为0。

这是一项同数值 provider、不同工作框架装配的比较。两路 SDK 公共指令、工具、历史管理及输入可以不同；不要求输入逐字节相同，也不把 PS1 Γ1 强加给 OH。

## PS1 保留的路径与两处 AST 导入替换

PS1继续调用原 `software_calibration_world_v051` 构建真实单成员 `member_001` 世界。原模型可见问题、工具、观察、Γ1、分页、私有版本、公开测试、任务 ownership、fixed patch 与合法 submit 合同均不改。`fix_patch`／ownership／submit 的合法拒绝继续是业务合同结果，不因 [HOLD过程诊断](software-bridge-v052-hold-process-audit.md) 而跳过、自动补办或重试。

`software_bridge_managed_v052.collector_binding()`读取原 `software_calibration_collector_v051.collect_episode` 的函数源码并在**私有 namespace**编译副本。它只替换该函数内两处相对导入的模块名：

1. `assess_software_collaboration`／`assess_terminal_working_tree` 的评分钩子导入。
2. `validate_case` 的导入；新模块直接别名原 world 的 `validate_case`，验证算法不变。

实现要求恰好找到两处导入，否则拒绝装配。函数副本的 `run_fragment`、`build_runtime`、原 runtime VERSION 等仍来自旧模块；不替换生命周期、预算、模型循环或模型可见文本，也不改旧模块 globals。回执记录原函数源码 SHA、改写后 AST SHA、两处修改计数与不变边界。

外部条件名是 `PS1`，内部仍传 `calibration_condition="P"`，保留原 `calibration-v051:<v052-slot>` 窗口和原 S1 measurement 标识。这是新库存对原 P/raw 路径的明确复用，不通过修改标识伪造旧门通过。wrapper要求 slot以`v052-`开头且没有 checkpoint，原 collector再次检查 raw P条件；原 measurement继续核对0/0历史步数、单成员、实际 actor／window／recipe及完整输入证据。

## 唯一末树先锁，再评分

PS1收口时，原 collector先锁定最后合法 fixed submission并结束工作。新评分钩子在任何固定树或末树评分之前，读取 member_001当前唯一私有树，写入：

- `terminal-code/prelocked-source/`中的原 candidate、权威 grading tree、canonical receipt、task与lock。
- `terminal-code/terminal-candidate-lock.json`中的成员、原 source reference、bundle SHA、files SHA及上面 lock 的绝对 path／SHA／bytes引用。

然后才调用原 fixed-delivery assessment，保持其 `R_joint` 语义。之后的末树钩子要求目录与先前锁一致，重读当前树并对 source reference、bundle SHA、files SHA逐项核对；任何改变均拒绝，不能看过评分再选择另一个候选。

共享评分实现位于 [software_bridge_sources_v052.py](/data1/zhuxinrui/projects/ProWorkSim/src/proworksim/software_bridge_sources_v052.py)。`grade_locked_candidate` 用唯一 `entered.json` 和最终 assessment 文件防止同一锁被再次评分。权威 tree恢复原 readonly测试／配置／support；对 OH保留合法生产代码新增和真实删除，对 PS1则继续原文件集合和 readonly合同。该步骤不向已结束的模型追加反馈。

OH走官方 Agent／Conversation 的独立 collector。其唯一末态导出在结束工作后固定为`candidate_files`与`candidate_lock`，都是绝对 path／SHA／bytes引用；宿主随后对这一个导出调用同一 shared lock／grade入口。宿主不会从多个原生工作树或评分结果中挑候选。

### 固定与末树相同，只复用完整身份匹配的原评分

`evaluation_identity` 在看到结果之前生成，覆盖有序完整文件 map、原测试节点、目标 module、配置、CPU解释器、loopback fixture、source roots、原测试及生产初态 hash、initial file inventory、允许新增生产路径、冻结 runtime ref，以及runner／shell helper和固定资源规则。端点名称和分数不参与身份选择。

真实固定评分沿 `OriginalSources.assess_files → self._execute → self.runner_spec` 调用，因此使用的就是新 provider spec。其 spec已包含 `initial_file_paths=sorted(original_files)` 和 `accepted_new_production_paths=[]`；PS1只允许原文件集合，末树 canonical阶段再次设置这两个字段时同值。两条评分路径都按同一规则排序文件 map。

fixed assessment带回真实 `evaluation_identity`、`authoritative_runner_receipt`及`bridge_binding`。只有提交存在且完整 identity与末树锁一致，末树才读取该次原r3 result复用，同时核对result引用、bridge identity和runtime引用。只比文件名、某个文件SHA、同仓库或同一个成功分数均不够。

| PS1收口情况 | 固定评分 | 新末树评分 | 正常完整时的新增host执行数 |
|---|---:|---:|---:|
| 没有合法提交 | 0 | 唯一末树1次 | 1 |
| fixed与末树完整评分身份相同 | 1次 | 复用，0次 | 1 |
| fixed与末树不同 | 1次 | 唯一末树1次 | 2 |

表中两次分别服务事前定义的两个不同端点，不是看分数重试同一候选。实际 `new_evaluation_attempts` 与 `new_test_executions` 分开记录；基础设施失败可能有attempt但没有真正执行test，不能强填为表中正常数值。原末树测量仍检查same-tree复用、锁字段和host计数的一致性。

## 正式端点、raw记录与未知

PS1正式保留 `R_joint`／`R_token`／`Q_joint`／`Q_token` 的固定交付语义，另列唯一末树 `R_code` 与 `Q_task_terminal`。没有合法固定提交时，PS1的 `R_joint=0` 不代表末态代码错误；末树评分也不回填旧 fixed reward。OH没有项目 fixed-submit端点，明确 `R_joint=null`、`project_delivery_endpoint="not_applicable"`，不能写作0。

宿主可以保存评分返回的 `raw_outcomes`，但只有 report.status=`closed` 且 verdict=`continue` 才进入账本的正式端点。`R_code`必须为已知0或1；PS1的`R_joint`也必须已知。即使已有 `R_joint=0`，末树技术未知仍暂停，不会借0绕过门。OH的N/A仅限项目交付端点，不是免除代码结果、费用、身份、输入和guard检查。

PS1复用原 `software_calibration_measurement_v051.measure_slot`。新 terminal receipt保留它要求的原成员／source／files锁字段、`assessment.independent_acceptance.execution`、same-fixed-tree复用标志及新增attempt/test计数，故没有把新的端点格式交给不认识它的旧 marker检查。

OH的`collect_episode`接收host给出的owner、task_source、provider、slot、seed、worktree和episode目录。`measure_closed(result, row, owner_identity, accounting)`核对官方请求／原生响应、费用多重集、唯一导出和episode guard；它接受host追加的terminal指标，不按代码成败决定机械门。两条件的 `episode/evaluation-guard.json` 都必须存在并给出学习不变、RNG精确恢复、软件绑定不变、actor身份不变。host另调用实际owner guard，保留无梯度、无optimizer／critic和无新增更新事实。

## 宿主重绑定、准入和停止作用域

`supervisor_binding()`复制旧 CAL2宿主的 namespace，在副本中绑定v052的 VERSION、frozen-plan校验、ledger和classifier。`worker_completion`直接复用旧函数的code object；`supervise`的AST仅把一个worker模块字符串从 `scripts.software_calibration_v051_cal2` 改成 `scripts.software_bridge_v052`，并要求恰好替换一次。原资源监控、phase时限、进程身份、子组清理和调度算法没有复制后再改写，也不修改旧全局变量。

正式prepare之前，独立model admission必须已签发且所有必要check键齐全为true。来源与初态均须 `completed=true`、`passed=true`、`fixture_only=false`；原六题全部合格，实际十二份初态请求齐全，新增模型调用为0。新引用闭合检查还要求：

- source的`runtime_manifest`等于admission的`test_runtime`。
- inputs的`design`、`source_qualification`、`test_runtime`、`reference_runtime`逐项等于admission引用。
- 各ref本身完整，避免把分别完好的“A环境资格”和“B环境执行”拼在一起。

prepare要求主仓源码已提交且clean，复制实际 `src/`／`scripts/` 到新run snapshot，记录逐文件SHA并封存admission及相关回执。worker再次验证plan、源码、资产、来源及资源引用，使用固定native解释器。每槽先记录进入，再加载新resident；进入模型loader的槽没有科学重试或预算转移。

只有可证明在任何槽／loader／模型进入之前发生的startup容量不足，且原退出75、零模型回执和清理都匹配，才允许原资源等待路径再次尝试。原process helper只负责已注册且身份匹配的子组；不声称清理无关进程。

完整绑定的安全局部资源结束可以闭合当前槽并继续其它独立槽，不按 `R_code=0`、未提交或正常结束筛选。费用或副作用未决、缺失实际请求／响应、身份／guard不符、末树未知、measurement不是continue等均进入全局暂停。已在途任务按原收口规则完成，旧记录保留；不能自动重采或用另一个工作树补验。

## 资源政策

沿已授权的物理 GPU **0—7全部可调度、最多4个resident**；容量足够可共享，不要求整卡无进程、util=0或空闲稳定60秒。原r3/r5资源门保持：装载前至少46,080 MiB可用，cache target为`min(73,728, floor(free−1,024))` MiB，并须落在45,056—73,728 MiB；原allocation margin256 MiB和startup协调逻辑保留。它不控制其它用户进程，也不更改数值路径。

宿主继承的phase上限为reservation900秒、loading900秒、preparation600秒、generation900秒、整episode6000秒、scoring600秒、measurement600秒；每worker RSS上限64 GiB、artifact上限128 GiB、卷至少留20 GiB，每5秒轮询。HF600秒与宿主generation900秒属于不同层级，不能把其中一个冒称为另一层的硬预抢占。实际模型阶段尚未开始，这些是冻结执行门，不是已测资源使用结果。

## 已有有限控制及保留的失败

控制代码为 [test_software_bridge_host_managed_v052.py](/data1/zhuxinrui/projects/ProWorkSim/tests/test_software_bridge_host_managed_v052.py)。本组只有4个不同控制：固定12槽与来源／输入gate；代码0和OH N/A不绕过机械闭合；私有宿主／collector装配不改旧模块；末树必须先锁、不能改变或二次选择。

- [首轮摘要](/data1/zhuxinrui/projects/ProWorkSim/artifacts/software-bridge-v052/host-managed-controls/summary.json)：4项一次全通过，`4 passed in 0.16s`。其SHA为 `c40fdd22414533eb7ebcc40e6d75f4bcfd7e7580cdc514e88e5f9052a2d8a09e`。
- [首轮 Ruff 原件](/data1/zhuxinrui/projects/ProWorkSim/artifacts/software-bridge-v052/host-managed-controls/ruff-first.txt)：保留未使用 `proworksim.storage.json_bytes` import导致的F401失败。仅删除该unused import后，Ruff通过，没有重跑4项pytest；[修后回执](/data1/zhuxinrui/projects/ProWorkSim/artifacts/software-bridge-v052/host-managed-controls/ruff-after-unused-import.txt)保留。
- [引用闭合修订摘要](/data1/zhuxinrui/projects/ProWorkSim/artifacts/software-bridge-v052/host-managed-controls/summary-reference-closure.json)：窄只读审阅发现准入引用闭合遗漏后，只补跑受影响的gate控制，`1 passed, 3 deselected in 0.11s`，[该次原件](/data1/zhuxinrui/projects/ProWorkSim/artifacts/software-bridge-v052/host-managed-controls/pytest-reference-closure.txt)保留；相应Ruff通过。

因此是 **4 unique controls、5次累计pytest执行**，不能写成新增5项控制或把第一次Ruff失败抹去。后续源码绑定以引用闭合摘要为准：host SHA `bee539039b092c5aaaea83a1bcd17b02602bc9816fae90c3b208b115c94e4d4d`，managed评分装配SHA `9df94b8dfdddf60ef1a04494729ece215292c1b1f5f56a390b0e69893b5a452f`。

本次文档没有重复上述控制、旧runtime／loop／shell／SDK控制或来源资格。共享真实测试环境、OH官方工具接缝和初态捕获分别见 [来源测试协议](software-bridge-v052-source-test-protocol.md)、[OpenHands参照方法](software-bridge-v052-openhands-reference.md) 与前述输入资格方法。它们各自的有效回执及独立model admission必须继续完整绑定，本文本身不启动模型或后继队列。
