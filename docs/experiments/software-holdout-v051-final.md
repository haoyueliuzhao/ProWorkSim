# v0.51 HOLD：四个既有检查点的固定保留任务评价

> **本轮已终态 complete：允许派发的 16 槽全部已知闭合，5 次固定交付成功、11 次未提交，技术未知与行政删失均为 0；另 16 个来源阻断槽仍保留。** 正式 674 次生成全部闭合，实际费用与账本均为 7,840,791 token，无不确定预约。本文只引用唯一最终 JSON 及现成机制摘要，没有新增来源、SDK、tokenizer、业务测试或模型执行，也未修改共同源码或运行原件。

原库存为四个真实 Python 仓库各两题、每题四个既有状态，共八题 32 槽。唯一来源资格中，24 个逻辑三态单元按事前完整身份去重为 13 次实际执行；iniconfig 1/2、dominate 1/2 合格，funcy 1/2 和 python-slugify 1/2 阻断。来源合格的四题完成 32 个真实 SDK 初态身份请求及实际 tokenizer 检查，全部满足初始硬容量，但原测量遗漏了模型可见随机 `branch_id` 的分析归一化，因此原摘要 `passed=false`、`qualified_case_ids=[]` 保留。后续只读来源审计支持独立的身份比较修订，未改变任何真实请求或共同执行代码。

独立模型准入最终只放行原四题各四状态的 16 槽。其余 16 槽保留在完整库存中，`attempts=[]`，正式 F/Q 为 null，不当作模型失败、不换题、不转移预算。**完整八题主均值和条件差仍为 null，不能把已完成的四题子集当作完整八题或一般任务分布。** 四题子集的 S_star/B/Q_plus/Q_minus 等权 F 均值为 0/0.5/0.5/0.25；这些数值只描述本次固定合格子集。

## 1. 评价对象与阶段边界

本轮用途固定为 `held_out_checkpoint_evaluation`，`holdout_evaluation=true`；training、Contribution、independent-confirmation 资格均为 false。评价对象是已存在的 S_star、B、Q_plus、Q_minus 状态在本次新任务与明确执行条件下的表现。本轮没有新增学习步骤，不与 v050 旧八单位合并，不声称同条件复测或新增学习收益。

四状态沿原静态库存绑定，S_star 历史 actor/critic 步数为 4/4，其余三状态为 5/5。正式评价只装载 actor，构造 critic/optimizer、新反向、actor/critic 参数更新均为 0。历史步数不是状态身份的充分条件：宿主同时绑定完整 checkpoint 引用、actor adapter SHA、base manifest、推理 profile 和状态授权，不能把 B 与 Q_plus 等同为可互换的“5/5”。

| 条件 | 历史步数 | 已冻结 actor adapter SHA256 |
| --- | --- | --- |
| S_star | 4/4 | `06f997903cd7d9bf8fb5dba403d5fe831619a1d871faec8e4699576a55154bcf` |
| B | 5/5 | `18f5fd7d61330aef9210965909d42b33944131fa94abc27c8846ca057317d465` |
| Q_plus | 5/5 | `7a76e93826a90052c400505bc407a30f9ff067e99fd1d1537e5d551678e69207` |
| Q_minus | 5/5 | `52dc58b5419c101b66045a7030c81b8ea0db1842ab3330a00a45563aa13e4995` |

上述身份来自[原库存](software-calibration-v051-repository-inventory.json)，并非报告编写时重新加载权重得到。共同 base manifest 为 `030031b27513e399360f26a8db31746e719bb15a3d2f4d68874c1dba3ccc60a6`，来源状态记录的历史推理 profile 为 `b7aebd3ce0119fa6e4067524c255cef29f1816adc361d2ed0a93f21f83844252`；它不等于本轮 native 执行 profile `20a2732be082bc3c144d5a3dcf3d9efe1caac05e2741c169472f130c59e20225`。原状态身份和本轮实际数值路径分别绑定，不能据这张静态表代替每槽的实际装载和终态只读 guard。

HOLD 的进入条件是 CAL 关键接入问题已解释、限制可明确声明，不是 CAL 达到成绩阈值。[阶段判断](software-calibration-v051-cal-to-hold-decision.md)与独立来源放行保留 CAL1 的两次缺完整输出、七次缺终态 guard，以及 CAL2 六个代码端点技术未知；没有用 HOLD 修理旧结果。CAL1/CAL2 完整主均值和差仍为 null。旧阶段费用只作独立引用，不重复加入 HOLD 模型账本；旧训练、Contribution、独立确认、v046 和缓存生产库存均未恢复。

## 2. 原八题、配对身份与完整 32 行库存

任务、上游 revision、原数据行 SHA、seed、先手与条件顺序在内容访问前固定。每题四状态使用该题同一配对 seed 和原先手；各槽独立新世界与驻留，不恢复旧会话或传递旧槽余额。以下“可派发”表示原准入范围；这 16 槽现已全部完成，其结果另列第 8 节。

| 任务 | Seed | 原先手 | 原四条件顺序 | 最终资格范围 |
| --- | --- | --- | --- | --- |
| hold-funcy-1 | 202610170561 | 001 | S_star → B → Q_plus → Q_minus | 来源阻断，四槽保留 |
| hold-funcy-2 | 202610170562 | 002 | B → Q_plus → Q_minus → S_star | 来源阻断，四槽保留 |
| hold-python-slugify-1 | 202610170563 | 001 | Q_plus → Q_minus → S_star → B | 来源阻断，四槽保留 |
| hold-python-slugify-2 | 202610170564 | 002 | Q_minus → S_star → B → Q_plus | 来源阻断，四槽保留 |
| hold-iniconfig-1 | 202610170565 | 001 | S_star → B → Q_plus → Q_minus | 来源及只读输入修订合格，四槽可派发 |
| hold-iniconfig-2 | 202610170566 | 002 | B → Q_plus → Q_minus → S_star | 来源及只读输入修订合格，四槽可派发 |
| hold-dominate-1 | 202610170567 | 001 | Q_plus → Q_minus → S_star → B | 来源及只读输入修订合格，四槽可派发 |
| hold-dominate-2 | 202610170568 | 002 | Q_minus → S_star → B → Q_plus | 来源及只读输入修订合格，四槽可派发 |

固定来源为 SWE-smith 的合成缺陷任务：真实上游仓库不等于自然发生并独立确认的真实用户 bug。问题描述、缺陷补丁和 F2P/P2P 来源按原数据保留；模型只接收原问题、初始缺陷文件和公开原测试信息，不接收正确树、参考修复或私有 F2P/P2P 分类。

## 3. 内容访问之前的共同冻结与控制

共同代码在读取 HOLD 业务材料之前提交并封存，提交为 **`0770d02f11bae4b33018c94be809f416c5fb91a2`**。共同快照为 `runs/software-holdout-v051-common/source`，冻结清单精确为 **607 个源码文件**。这是源码文件数量，不是来源资格的测试报告数量；后者也恰为 607，见下一节，二者没有同一分母含义。

[共同冻结记录](software-holdout-v051-common-freeze.json)创建于北京时间 2026-10-18 15:18:15.853470，SHA `57cb0048f4703ae50ae520fe68145609d3d7a83c5c2f2c2961e69c9130f31f5f`。它绑定 provider、world、collector、measurement、executor、host、来源与输入资格脚本、传递源码、tokenizer 和 CPU 环境。实际来源脚本从该 snapshot 运行，显式传 project root；模型宿主从同一共同快照复制源码，不能将打开任务后修改的 main 悄悄用于模型。

[来源访问放行](software-holdout-v051-source-access-release.json) SHA `f391a3259eaccdc3db4228094de322bb84b1834eb7a10e72ec09690e844328e7`，单独授权确定性导出与唯一资格，当时不授权模型调用。其元数据提交为 `8e16553`。后续依赖和配置数据准备按照已冻结规则完成，不修改引擎、不安装正确目标源码、不按资格成绩修规则。

共同控制全部使用合成材料。不同控制数、累计执行数、真实 SDK 程序响应与真实模型调用分开报告：

| 控制组 | 不同控制 / 累计测试节点执行 | 原失败、修订与复用 |
| --- | --- | --- |
| 两成员 world/collector | 5 / 5 | 首次 4 pass、1 fail。真实 SDK 两会话与 6 个程序响应已完成，末尾断言把 `team_budget.model.limits` 误读成 `team_budget.limits`。保留原失败、源码及日志，只读原件补完断言；没有重放 SDK 或重跑该控制。 |
| 独立来源/executor/provider | 5 / 6 | 两个真实 Python3.10 隔离子进程各一次、各两个虚构节点，含预期 assertion failure。其余为纯 provider、机械去重和环境归因控制；仅未知实际执行次数语义修订后重跑受影响的去重控制一次，没有重跑真实子进程。 |
| measurement/host | 5 / 6 | 首次五项全部通过；增加缺原件应保持 measurement_pending 的反例后，仅重跑 F_zero 一项。首次 Ruff 未使用导入错误与后续修订保留；原 fixture 只读测量仍拒绝作为正式模型证据。 |
| 初态资格实施 | 3 / 3 | 三项纯控制一次通过。首次 Ruff 未使用导入及一次摘要组装路径错误保留；不重新执行已通过测试或两会话 SDK fixture。 |
| 报告算术 | 1 / 1 | 单个合成报告控制一次通过，无新评分或模型。 |

这些计数不能改写为“所有初次 pytest 均通过”。world/collector 的原失败只是其最终只读审计已解释，原失败回执仍为失败。真实 SDK 程序控制的 6 响应和 2817 个 synthetic token units 也不是模型生成费用。各控制的 Ruff 和原件由 common-freeze 的 `controls` refs 绑定。没有重复 CAL2 来源资格、旧 tokenizer、旧模型槽或已有 TCP 控制来增加通过数。

## 4. 独立 CPU 环境与唯一三态来源资格

CPU 测试采用上游 Python profile 的 3.10 系列，本次实际为 **Python 3.10.18**，build stamp 20250918，Clang 20.1.4，独立解释器与 venv 置于项目 runs 下。原 profile SHA 为 `eadf29551ca2e706950d3f2311b47a3d08c2ccee3c8dd217fa299014a08e4286`。模型 SDK/权重执行仍沿用原 Python3.12；CAL2 环境和记录不改。这不是原 Docker image 的完全重现，而是旧 checkpoint 在已明确记录的新 CPU 执行条件下评价。

[环境模板](../../artifacts/software-calibration-v051/hold-python310/environment-template.json) SHA 为 `f9fe027d5ee14dae8c8e36acf885bb4586228c368a0c8e715089c5aa85f86dce`，记录解释器、build、bootstrap、wheel、完整 engine 文件 SHA 和精确依赖版本。业务依赖在放行后按静态原 metadata 解析，安装到独立 additive 目录，并与最终各库 environment 绑定；冻结 pytest/解释器不被替换。来源和模型测试使用相同的正式隔离 executor、配置和每库依赖身份。

环境不安装四个 HOLD 目标库的正确源码。针对 pytest 与 iniconfig 同名依赖，宿主只持有预绑定只读配置路径及 SHA 的受限静态视图，不能接受任意业务字符串，也不加载正确 iniconfig 的业务解析对象。真正目标模块从当前候选树导入并记录实际来源。隔离复用已冻 r3 的 Landlock/seccomp、子组登记与清理；没有借用正确目标包帮助 faulty 候选通过。

来源资格保留每题 baseline、defect、reference 三个逻辑单元，合计 24。完整候选 map、原测试 ID/config、依赖环境、引擎、runner/helper 与执行参数在结果产生前形成 identity；严格同值才共享一次物理执行。共享失败回执也不会重新运行。reference 由原补丁逆向构造，并与已冻 upstream 全 map 字节一致。

| 仓库 | 逻辑三态单元 | 唯一物理执行 | 实际测试报告数 | 资格结果 |
| --- | ---: | ---: | ---: | --- |
| funcy 两题 | 6 | 3 | 0 | 两题阻断：collection 缺 `whatever` |
| python-slugify 两题 | 6 | 4 | 328（4 × 82） | 两题阻断：原生 ID 非一一映射 |
| iniconfig 两题 | 6 | 3 | 84（3 × 28） | 两题合格 |
| dominate 两题 | 6 | 3 | 195（3 × 65） | 两题合格 |
| 合计 | **24** | **13** | **607** | **4 合格 / 4 阻断** |

“测试报告数”保留实际报告，包括 slugify 重复 ID，不冒称 607 个不同原节点全部有效。13 次执行都有终态及清理原件；来源字节、测试完整性和目标导入绑定均完整。各 runner 回执 `elapsed_seconds` 之和为 5.955964076332748 秒，仅是这些回执定义的执行区间之和，不是包括环境准备在内的总墙钟或 CPU 费用。

funcy 的 baseline、两题 defect 共三个物理执行都因原测试导入 `whatever` 而 collection 失败。代表 baseline 回执 returncode=4、executed=false，203 个原节点全部 missing，`environment_errors` 明确记录 ModuleNotFoundError；不能当作缺陷候选的业务失败。未在观察结果后补装依赖或重跑。两题各四模型槽保持来源阻断。

python-slugify 使用原 `python test.py --verbose`，没有替换成 pytest。四次物理执行各产生 82 条报告、81 个唯一 profile ID；`The regex_pattern turns the power to the caller.` 这一描述出现两次，并有五处多行 verbose description 与完整 native case 描述不等。题 1 原 union 为 73，还出现八个额外 ID；题 2 原 union 为 81，仍有重复报告而非一一映射。原 F2P/P2P 状态模式虽符合预期，不能代替冻结的身份门。两题均保持 blocked，不修改解析、去重规则或原测试后重试。

iniconfig 两题的原 28 节点和 dominate 两题的原 65 节点，baseline/reference 全通过；各 defect 原 F2P 分别为 6、25、2、5 个失败，原 P2P 分别为 22、3、63、60 个通过。它们通过来源三态和正式环境门，仅证明这四题在本次冻结执行条件下有可用来源；不证明全部八题已合格。

资格摘要 `completed=true`、总体 `passed=false`，合格子集显式列四题。[原摘要](../../artifacts/software-calibration-v051/holdout-sources/qualification/summary.json) SHA `bc953d1c54f2c738cffc9064bfa68d50ccad4e30a168e70ac9340d877ae84ab8`；[只读归因回执](../../artifacts/software-calibration-v051/hold-source-execution/qualification-audit.json) SHA `6aa215bd56752b8ae46d5fb99ab5290f46ee7b4bb73eacf66ba9738e2942c47c`。这些原件未被后续准入改写。

## 5. 初态 SDK/tokenizer 测量及 branch_id 只读修订

内容访问前的协议先区分 16 个 task×role 逻辑形状与四状态各自的必要身份实例，最多 64 个真实初态请求；底层 Γ1 编码和模板渲染次数另计，不把 64 称为 tokenizer 总调用上限。原初版“16 次编码直接复用四状态”的设想保留在旧提交，已在共同冻结前修正。

来源阻断四题不构造 SDK 初态。实际四题 × 两角色 × 四状态共 **32 个真实 SDK 初始请求、32 份不同请求投影**；逻辑角色形状为 8。实际底层 tokenizer 编码 **64 次**，精确编码缓存命中 **160 次**，模板渲染 **64 次**，渲染缓存命中 0。32/32 的 selected 输入加 2048 输出均不超过 18432。该阶段未加载权重、没有模型生成、程序响应、GPU worker 或业务测试。

原输入资格摘要仍为 `completed=true`、`passed=false`、`qualified_case_ids=[]`、八题全部列入 blocked：四题来源阻断未测，另外四题因原跨状态业务输入同值检查失败而 input_blocked。[原摘要](../../artifacts/software-calibration-v051/holdout-initial-inputs/summary.json) SHA `27e80b9d857a8dd1a4001c1ec0e320b4490a1494643b8dd569ff3b6fe0c34db5`。硬容量通过不等于原完整准入通过，原 false 不回写。

随后的独立只读审计逐组比较已有请求：八个 task×role 组的四状态请求恰有三种叶差异：`observation.instance_id`、`observation.branch_id`、`team_model_budget.state_sha256`。原分析规则已处理 instance_id 和预算摘要，却遗漏 branch_id。封存世界源码为 instance_id 与 branch_id 分别调用 `uuid.uuid4().hex`，HOLD observation 又原样向模型公开这些值。

因此 **branch_id 是实际模型可见的随机命名空间标识，不是模型看不到的宿主字段**。它不是业务源码、状态标签或模型成绩的函数。只读修订只在分析比较中新增 `/observation/branch_id` 的归一化，并要求其余完整请求、工具和业务合同保持一致。32 份原请求、原长度、随机值与正式世界均不改；没有重新建立 SDK 会话或编码。

这项解释**不证明原始输入逐字节相同，也不证明模型对随机 UUID 不敏感**。未来独立世界仍可能有不同的公开标识与 token 长度，初态形状合格也不保证所有后续输入都 fit；正式每次请求继续执行原硬容量门。初态四状态这里只是身份元数据装配，不冒称权重装载或终态参数/RNG guard 已完成。

独立修订摘要为 `v051-holdout-initial-input-identity-readonly-v2`，明确标记 post_qualification_measurement_revision；其总体 `passed=false` 仍对应完整八题未全合格，但 `qualified_case_ids` 为来源合格的原四题。原 input false 和原空 qualified 列表另外保留。新增 SDK、tokenizer、模型、业务测试、参数更新均为 0。修订发生在资格之后、模型成绩出现之前，不伪装成原事前比较规则已经通过。

修订见[方法说明](software-holdout-v051-input-identity-readonly-r2.md)和[独立摘要](software-holdout-v051-initial-input-identity-r2.json)，后者 SHA `fb769bb5500ecbe7687c1afb7051f241c34b508816a5d525e6f51a9bf9b7a6b9`；其只读 audit SHA `7766b2c27958608fceccb76124414ea9ea80d359e1632c8925cde9946c188812`。不能将该修订描述为新的 tokenizer 资格或新的共同实现候选。

## 6. 模型准入、O1 接口、预算与资源

[独立模型准入](software-holdout-v051-model-admission.json)创建于北京时间 2026-10-18 15:32:40.382588，绑定共同冻结、原来源资格、原输入 false、独立只读输入 r2、资源规则和全部八题资格行。可派发名单是来源与修订后输入资格的交集，精确为原四题；不是按模型成绩选子集。`unresolved_blockers=[]` 表示允许范围和阻断原因已确定，不表示八题无缺失。

两名固定成员 `member_001/member_002` 各有真实独立 SDK 会话与私有工作树，共享同一只读 actor 和团队预算。初态为空任务表、无人工预分工、无强制初始测试或诊断、无附加 member test。责任可自主建立；协作不是成功的必要条件。`staff_done` 结束当前工作并休眠，只有真实可达的伙伴事件才唤醒原会话；不新增、替换成员，不重置身份、历史或余额。对方的私有树和私有测试结果仍受权限限制。

保持 Γ1、C=18432、O=2048、3072 Unicode 字符精确分页、非思考模式与原采样条件。每槽预算为 **500,000 token、128 决定、128 attempt、32 次团队公共测试**，90 分钟软边界与 100 分钟硬边界保持。HF 的 600 秒迭代停止声明不被写成可靠的 600 秒硬抢占；原外层时间和资源 guard 继续独立约束。

| 范围 | 逻辑槽 | 生成 token 上限 | 决定上限 | attempt 上限 | 团队公共测试上限 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 原完整库存 | 32 | 16,000,000 | 4096 | 4096 | 1024 |
| 允许派发的固定子集 | 16 | 8,000,000 | 2048 | 2048 | 512 |
| 来源阻断保留行 | 16 | 不派发、不转移 | 0 实际执行 | attempts=[] | 0 实际执行 |

上限不是实际费用。物理 GPU 允许 0—7、最多四驻留，沿原足够显存可共享容量门；没有整卡 idle/util0/60 秒条件。内存、磁盘、进程身份、装载、生成和评分边界保持。本次实际使用物理 GPU 0/4/5/6/7，驻留峰值 4；16 个唯一 worker 区间分别由最终报告绑定，费用见第 9 节。

充分绑定的安全局部 context/shared/member-fixed 资源终止保留，并可继续其他独立槽；输入、权限、身份、账单、评分或共同服务完整性故障暂停未开始库存，在途槽按冻结规则闭合。已有原始结果不靠后续热改重评，原余额不转移。最终 16 槽的机制门均已解析、宿主判断均为 continue，没有全局暂停；这没有消除 27 次实际团队预算拒绝。

## 7. 固定交付 F 与正式未知

HOLD 主业务端点是关闭时最后一次合法固定提交的 **F=R_joint**，按其精确文件树、原测试与过程要求评定。后续私有工作区编辑不能替换已锁定提交。没有合法提交且来源、运行、反馈、费用、身份和终态 guard 完整时，F 可为 0，宿主 final test 次数为 0；不验收未提交末树来“挽救”结果。

本轮不引入 CAL2 末树 `R_code` 作为 HOLD 主端点，也不把公开 run_tests 成功当作最终固定交付成功。固定提交、当前版本公共测试与关闭时权威验收分别保留来源。提交后验收未知、或即使无提交但机械证据不完整，严格结果仍为技术未知，不能以未提交为由填 0。行政删失时保留 joint 与原 token 预算端点的差异，不将 R_token/Q_token 宣称为已知；后者不是按 token 除算的归一化得分。

正式测量还要求实际 native prepared/started/complete、SDK 回包、输入/输出/usage、actor 身份和账本闭合；CPU programmed fixture 不能通过正式模型门。固定 tree lock、唯一验收原件、终态 guard 与证据缺席都由独立 measurement 绑定。本次 16 槽固定端点均 verified，674 次已启动生成全部 settled，严格 F/Q 均已知；没有技术未知或行政删失。

## 8. 正式模型终态与固定子集结果

唯一[最终机器报告](software-holdout-v051-final.json)版本为 `software-holdout-v051-final-v1`，生成于北京时间 2026-10-18 16:18:14.215104，SHA `1512dbc00aeeb97f7ae63c6db0842b237641275119f1e83edc4406a52c3b01d1`。运行根为 `runs/software-holdout-v051`；模型实际使用共同提交 `0770d02f11bae4b33018c94be809f416c5fb91a2` 的封存源码，独立模型准入 SHA 为 `20e88c0e92ac12fc74cc9b8aeca29db33eeb09ee943429a547c26781ed55351b`。

[plan](../../runs/software-holdout-v051/plan.json) SHA 为 `ef798d0758bfc4444c0da2f97eea20fc92406bb09d4b67a50cc9761da006f9c5`；[终态 supervisor](../../runs/software-holdout-v051/supervisor.json) SHA 为 `7780982f6251d5f6a0595ab927cfed00aa7a7d4b7f8b6ab1a64296816084b5aa`，状态 complete。宿主开始/结束 epoch 分别为 1792308866.5306735 和 1792311433.9220443，即北京时间 **2026-10-18 15:34:26.530673—16:17:13.922044**。各槽均一次进入，无重新采样、重复加载后的补跑或原结果重评。

以下每格给出 `F / Q_joint`；本次已执行各槽两个值均同为 0 或同为 1。阻断行的 null 是未执行资格阻断，不是模型失败。

| 原任务 | S_star F/Q | B F/Q | Q_plus F/Q | Q_minus F/Q | 终态口径 |
| --- | --- | --- | --- | --- | --- |
| hold-funcy-1 | null | null | null | null | 来源阻断，原四槽保留 |
| hold-funcy-2 | null | null | null | null | 来源阻断，原四槽保留 |
| hold-python-slugify-1 | null | null | null | null | 来源阻断，原四槽保留 |
| hold-python-slugify-2 | null | null | null | null | 来源阻断，原四槽保留 |
| hold-iniconfig-1 | 0/0 | 0/0 | 1/1 | 0/0 | 四槽已知闭合 |
| hold-iniconfig-2 | 0/0 | 0/0 | 0/0 | 0/0 | 四槽已知闭合 |
| hold-dominate-1 | 0/0 | 1/1 | 0/0 | 0/0 | 四槽已知闭合 |
| hold-dominate-2 | 0/0 | 1/1 | 1/1 | 1/1 | 四槽已知闭合 |

原 32 行唯一终态为 16 closed、16 source_or_input_blocked。合格 16 槽中，**5 槽最终固定提交成功、0 槽提交后未全通过、11 槽未提交、0 技术未知、0 行政删失、0 合格未开始**。来源阻断的 16 行均保持 attempts=[]。固定提交权威验收共 5 次，均通过；未提交 11 槽没有末树补验，其 F=0 由完整运行与机械证据支持。

| 条件 | 完整原八题已知数 / 分母 | 完整八题均值 F、Q | 固定合格四题均值 F、Q |
| --- | --- | --- | --- |
| S_star | 4/8 | null | 0 |
| B | 4/8 | null | 0.5 |
| Q_plus | 4/8 | null | 0.5 |
| Q_minus | 4/8 | null | 0.25 |

固定合格四题的配对差为 B−S_star=0.5、Q_plus−B=0、Q_minus−B=−0.25、Q_plus−Q_minus=0.25；每个差均使用相同四题、四个已知配对。完整原八题对应均值及所有条件差继续为 **null**，不把缺失四题补成 0，不用子集均值替代主面板。

四题只覆盖两个通过本次环境资格的仓库、每库两个相关合成缺陷；它们不是八题的随机子样本，更不是广泛软件工程分布。子集 B 与 Q_plus 的均值相同，其相对 S_star 的描述差不能直接归因于一般协作能力、整体模型能力或本轮新增学习。模型在不同世界收到的公开随机 UUID 也并非逐字节相同，输入只读修订的限制继续成立。

最终报告层只作了一项 `gpu_index` 字段提取的窄修，配套一个结构控制及 Ruff；它使既有 worker 的实际物理卡信息进入报告，没有改变 common 0770d02、模型快照、宿主调度、评分或任何原始结果，也没有新启动模型或测试树执行。

## 9. 正式费用、资源终止与反馈机制

以下数据直接引用最终 JSON 与[终态机制摘要](../../artifacts/software-calibration-v051/hold-final-mechanisms/report.json)，后者 SHA `7738b74f1c76beeba7a394206319d13055c2caec387f463b57bd877dc11a03c7`。机制汇总仅读取 16 份既有 worker 报告，没有打开原始 trajectory/native generation/test artifact 或重新运行测量；缺席的 16 个阻断槽没有被填成零活动模型槽。

| 正式模型项目 | 闭合结果 |
| --- | --- |
| 已消费决定 / 实际 attempt / 完整生成调用 | 701 / 674 / 674 |
| 已启动 native generation / 完整回包 | 674 / 674，全部 settled |
| 实际 prompt / output / total token | 7,711,434 / 129,357 / **7,840,791** |
| 已知实际 / 完整实际 / 账本扣账 token | 均为 **7,840,791** |
| 不确定预约 / 不确定 usage attempt | 0 / 0 |
| 成员公共 run_tests / 固定提交权威验收 | 47 / 5 |
| 物理 GPU / 最大实际驻留 | 0、4、5、6、7 / 4 |
| GPU worker 唯一区间 | 16 段，共 **9046.376301288605 秒 = 2.5128823059135015 小时** |
| 硬 context / 团队预约 / 成员 fixed 拒绝 | 0 / **27** / 0 |
| 停止分类 | 14 safe_local_resource_stop；2 ordinary_closed_stable_O1 |
| 宿主判断 / 全局暂停 / 行政删失 | 16 continue / 0 / 0 |
| 新 backward / actor 更新 / critic 更新 / 出生 | 0 / 0 / 0 / 0 |

701 个已消费决定与 674 次实际生成之间的 27 次差对应充分绑定的团队预算执行前拒绝；它们没有生成或不确定费用。这些是实际资源终止，不能因最终分数已知就抹去。16 槽关闭原因均为所有成员停止或无可达事件；14 槽分类为安全局部资源停止，依原宿主作用域继续其他独立槽。所有实际费用、native/SDK 响应多重集和固定端点均闭合。

47 个 run_tests 反馈、47 份报告历史以及共享测试预算消耗 47 是同一批公开测试的三个观测口径，不相加成 141 次；宿主另有 5 次固定提交终验。来源资格的 13 次 CPU 执行和 607 条报告不混入这两种正式模型测试次数。GPU 成本只按 16 个唯一物理 worker 区间相加，包含其实际装载和工作区间，不再次加嵌套模型时长；宿主墙钟与多卡区间和是不同量。

674 个模型调用关联的反馈全部保存。642 个存在同成员后续真实生成的反馈，均在第一次真实后继输入中呈现；其余 **32 个无后继**，原因为团队预算 27、当前工作结束且无可达事件 4、等待且无事件 1。这里报告的是冻结测量器已经保存的分母和归因，没有为追求完整呈现追加请求。

测试反馈分页方面，47 份报告全部保存且存储验证通过，44 份目录被实际呈现，44 份至少一页被实际呈现；历史上全部页均呈现的报告数为 0。共有 32 次真实 `read_test_result` 请求。冻结字段 `verified_page_feedback_returns=79` 统计已验证的含页反馈条目，包含 **47 次 run_tests 自动附带首页 + 32 次显式读页**；它不是 79 次独立读页调用、79 个唯一页面，也不是同一反馈在多个输入中重复呈现的次数。后续分页原因分别为未请求 41、团队预算 5、自主结束 1。该机械计数不证明模型已读完全部报告、理解内容或使用了页面。字段定义另存[只读口径说明](../../artifacts/software-calibration-v051/hold-final-mechanisms/page-count-definition.json)，原摘要不改写。

两名固定成员的学习状态未变、RNG 精确恢复、软件绑定未变、actor 身份未变及 actor guard 均为 **16 true、0 false、0 unknown**。16 槽的机制门、native 精确回包多重集绑定、全部 started settled 以及固定端点 verified 全部成立。历史 4/4 或 5/5 只是保留状态的既有步数；本轮新增更新计数和反向计数全部为 0。

**伙伴语义使用链为 not_analyzed/null。** 本次终态机制汇总没有扫描原始轨迹去证明具体伙伴内容被采用、由接收者在精确版本上验证并连接到固定交付；不能把未分析写成“没有发生”“没有使用链”，也不能从消息、页面或测试频次推断协作收益。此限制与已知固定交付 F/费用闭合分别保留。

准备与资格成本独立列示：来源 13 次实际 CPU 执行、607 条原测试报告；初态资格 32 个 SDK 请求形状、64 次底层编码、160 次精确缓存命中、64 次模板渲染、0 模型生成；branch_id 只读修订新增上述执行均为 0。前置合成控制次数另见第 3 节。它们不混入正式模型调用/生成 token，也不能用来补足旧 CAL 的未知费用。

[全窗口唯一合并报告](software-calibration-v051-overall-final.json) SHA `1024a6089d0e4621752b5a75afff5a6effe43a86a1682b1576aba0fdd8c7b379` 仅读各 CAL 现成小计一次及本 HOLD 最终报告一次：1152 次 started、1150 次 complete，已知实际 14,144,045 token、不确定预约 164,789、账本 14,308,834；**完整实际 token 仍为 null**，原因是 CAL1 原两次缺完整回包。43 个唯一 GPU 区间合计 95,130.45483350754 秒，即 26.425126342640983 小时。该跨阶段账本与本节已闭合的 HOLD 账本分开，未重算原 raw calls、没有重复加入旧成本，也没有将历史未知清零。

## 10. 证据索引与结案边界

本报告使用的核心凭据如下，原件优先于文字简述：

- [原库存](software-calibration-v051-repository-inventory.json)、[接口协议](software-calibration-v051-hold-interface-protocol.md)、[校准到 HOLD 的阶段解释](software-calibration-v051-cal-to-hold-decision.md)。
- [共同冻结](software-holdout-v051-common-freeze.json)、[来源访问放行](software-holdout-v051-source-access-release.json)、[模型准入](software-holdout-v051-model-admission.json)。
- [来源/引擎方法](software-holdout-v051-source-engine-protocol.md)、[来源资格摘要](../../artifacts/software-calibration-v051/holdout-sources/qualification/summary.json)、[来源故障只读归因](../../artifacts/software-calibration-v051/hold-source-execution/qualification-audit.json)。
- [原初态资格 false](../../artifacts/software-calibration-v051/holdout-initial-inputs/summary.json)、[branch_id 只读修订方法](software-holdout-v051-input-identity-readonly-r2.md)、[独立 r2 摘要](software-holdout-v051-initial-input-identity-r2.json)。
- [两成员控制](../../artifacts/software-calibration-v051/hold-interface-controls/summary.json)、[来源控制](../../artifacts/software-calibration-v051/hold-source-controls/summary.json)、[宿主测量控制](../../artifacts/software-calibration-v051/hold-measurement-controls/summary.json)、[输入实施控制](../../artifacts/software-calibration-v051/hold-input-controls/summary.json)、[报告控制](../../artifacts/software-calibration-v051/hold-report-controls/summary.json)。
- [宿主与测量方法](software-holdout-v051-host-measurement-method.md)、[HOLD 最终 JSON](software-holdout-v051-final.json)、[plan](../../runs/software-holdout-v051/plan.json)、[终态 supervisor](../../runs/software-holdout-v051/supervisor.json)，最终 JSON 的 rows 保留逐槽报告与原件引用。
- [终态机制摘要](../../artifacts/software-calibration-v051/hold-final-mechanisms/report.json)与[CAL0/CAL1/CAL2/HOLD 唯一窗口合并](software-calibration-v051-overall-final.json)。

本轮保留所有来源阻断、原 input false、事后只读测量修订、真实输入差异、控制首失败及旧阶段未知。HOLD 可派发的 16 槽已全部闭合，原 16 个来源阻断槽保持原分母，完整八题效应仍缺失。协议没有授权换题、追加 seed、按结果重采、扩大容量、恢复旧训练队列或自动后继；本轮终态没有触发这些后续行动。
