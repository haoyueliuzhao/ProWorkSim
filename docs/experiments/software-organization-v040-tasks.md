# v0.40 承接态开发任务与初始公开诊断

两个具名承接态变体已准备，8项有限CPU任务控制通过，Ruff通过。初始分支可运行且部分公开检查通过，两组公开诊断都记录了真实通过项与失败项；完整reference通过原质量要求。没有运行模型、GPU、反向或参数更新。

## 任务与来源

本轮保留v0.39两个已用共享产品任务的完整业务输入/输出要求、可编辑模块、公开及私有请求—预期对；新增名称和初态绑定。代码环境仍是已固定的pristine `schema@24a3045773eac497c659f24b32f24a281be9f286`。它具有SWE-smith来源谱系，但这两个任务是项目自建合同的承接态变体，**不是新来源、独立benchmark或独立确认材料**。

| 本轮ID | 继承root | 可编辑生产模块 | 初始兼容缺口（环境作者说明） |
|---|---|---|---|
| sc-record-views-handoff-v040 | sc-record-views-v039 | records.py、report.py、query.py | report组序错误；query筛选后重编号丢失原position |
| sc-record-catalog-handoff-v040 | sc-record-catalog-v039 | records.py、report.py、query.py | 重复key更新改变首出现顺序；query混淆存在假值与缺失 |

这些缺口通过对参考侧完整实现作小范围改动构造；它们是公开合同下的真实兼容错误。初态不是空函数集合，未受影响的行为继续成立。完整参考程序只留在资格/验收侧；`initial-provenance.json`中的作者缺口说明也不进入成员文件或观察。上表不作为模型修复提示发送。

公共合同继续规定根功能、API和质量，不创建任务卡或职责。成员具有相同文件与工具权限，仍可集中完成，也可自行交流、形成任务和职责。没有把诊断A规定成某人的岗位，也没有强迫两名成员分别修两个文件。允许空任务绑定固定交付，当前版本测试、固定patch和主动提交要求保持。

所有新variant仅用于`organization_development`，训练、Contribution和独立确认资格均为false。旧v0.39资产、成绩、技术未知及未启动槽不改写；没有读取TextFSM确认池。

## 两份诊断实际记录什么

准备阶段分别执行两组冻结公开driver。A覆盖共享产品/报告检查，B覆盖查询检查；分组只是技术事实的来源划分。初始代码、缺口和诊断都标为环境准备、`model_generated=false`，不是当前成员自主发现。

| 变体 | A：通过/失败 | A失败ID | B：通过/失败 | B失败ID |
|---|---:|---|---:|---|
| record-views handoff | 3/1 | report-group-order | 2/1 | query-original-positions |
| record-catalog handoff | 2/2 | catalog-first-last、catalog-table | 2/1 | catalog-query-repeats |

catalog有两项逻辑缺口，表现为三个失败检查，因为共享key顺序同时影响共享产品和报告。不能把失败检查数直接当作缺陷数。

两根各保留7个公开业务请求和9个私有同合同请求；完整公开执行还包含1个原始schema回归。初态views公开业务为5通过/2失败，catalog为4通过/3失败，原库回归均通过。当前这项准备资格没有给初态执行私有验收；它只验证真实公开缺口与有限正反程序控制，不将初态人为写成某个模型得分。

成员可见诊断包含稳定`diagnostic_id=<case_id>:diagnostic_a/b`、当前文件SHA、检查执行状态/计数和测试ID。失败项保留真实公开request、observed、expected；通过项紧凑摘要。不会加入修复补丁、分工方案、私有验收输入、详细`source_api_trace`或宿主路径。世界为每条episode另行绑定其baseline对象/版本；诊断分配由信息条件决定，源适配器不分配成员。

`prepare_initial_diagnostics(case_id, run_root)`返回两份事实、来源回执和实际准备成本。`run_public_tests`仍只调用一次完整公开sandbox，再从同一真实结果投影两组`public_diagnostics`，标记`origin=member_public_test_execution`和当前文件SHA。因此任何成员使用相同的`run_tests`都能重新得到两组事实，I-split不会永久隐藏信息。可选成员脚本最多再执行一次，每次`run_tests`仍最多两个隔离执行。

## 缓存、版本与成本

首次在一个worker进程内准备某个精确初始文件/manifest/driver组合时，实际执行两组检查，落`initial-diagnostic-receipt.json`，保留原执行输出、环境边界与elapsed秒。只有两组都完整得到真实通过和失败事实才进入缓存；异常准备先保留回执，再阻止无效准备继续。

同进程随后对相同组合的准备可复用该回执：`cache_reuse=true`，本次`actual_public_driver_executions=0`、sandbox新增秒数0；另外记录缓存读取/验证的函数耗时。首调用新增执行数为2。原始执行成本放在`source_recorded_preparation_cost`，不在每个复用槽重复声称又执行过。返回值深拷贝，调用方添加本world对象引用或修改返回对象不会污染其他条件的缓存事实。

宿主receipt路径、先前slot目录和计时只属于控制器provenance，不进入可见诊断。缓存只复用冻结技术事实，不复制成员历史或工作结果。不同worker进程拥有独立缓存；本轮四个root/seed worker不能被描述成“每个root全批只准备一次”。**真实全批准备次数和耗时应累计各worker原回执及复用记录**，不能从root数量推算或把复用次数当新执行。

环境准备不扣成员共享32次`run_tests`额度，也不产生模型调用、token、任务、编辑或自主发现信用。成员之后自行重测、分享、解释和基于事实修改，才是本轮真实工作过程；这种区分需要运行记录继续保留。

## 有限CPU控制结果

源组件资格为8通过、0失败、0跳过；Ruff通过。该次资格真实执行18个隔离程序：两root初始分组诊断共4次、完整公开重跑共2次、两root各3个完整reference/API绕过/product绕过程序的公开与私有检查共12次。没有重复v0.39的20变体资格，也没有新的模型接口诊断或tiny反向。

| 程序/控制 | record-views handoff | record-catalog handoff | 可支持的结论 |
|---|---|---|---|
| 初始分支公开检查 | 部分通过，A/B均有真实失败 | 部分通过，A/B均有真实失败 | 初始诊断来自实际执行，而非人工编写错误结论 |
| 同初态完整公开重跑 | 与两组诊断逐项一致 | 与两组诊断逐项一致 | 同权限`run_tests`可重新取得诊断事实 |
| 完整reference | 完整公开/私有通过 | 完整公开/私有通过 | 原业务合同仍有可执行完整实现 |
| library_bypass | 内容正确，规定API不合格 | 内容正确，规定API不合格 | 不能以手写等价逻辑替代真实schema API |
| product_bypass | 内容正确，共享产品调用不合格 | 内容正确，共享产品调用不合格 | 两消费者仍需实际调用规定共享产品；该控制仍真实调用schema |
| 缓存复用与调用方修改 | 新执行0，原事实不污染 | 新执行0，原事实不污染 | 信息布局不因先前world metadata获得额外内容 |

这些是有限输入上的调用与输出见证，不证明任意防绕过或唯一因果贡献，也不证明模型一定沟通或更有效。业务合同、可编辑路径与原请求—预期对逐项相同；私有数据、reference、缺口来源说明均未进入初始文件和诊断。

[机器记录](software-organization-v040-tasks.json)保存测量结果、来源、精确初态和driver绑定及成本。资产入口为[source manifest](../../examples/software-organization-v040/source-manifest.json)与[source partition](../../examples/software-organization-v040/source-partition.json)；manifest的`sha256`是排除自身字段后的规范payload摘要，实际文件摘要另存机器记录。

本记录仅完成任务及CPU准备。16条主比较的I-shared/I-split、G-base/G-team、先手/分配轮换与新seed由主协议事前冻结；这里不自动启动实验、不恢复旧训练、不补跑旧槽，也不把准备成本或CPU脚本行为当作模型协作证据。
