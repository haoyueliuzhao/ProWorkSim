# v0.8 持续工作修订与实验报告

日期：2026-09-23。依据：[v0.7 审计](../reference/continuous-work-audit.md)、[两阶段计划](../continuous-work-v08-plan.md)；实现合同见[设计说明](../continuous-work-v08.md)。

本轮在有限、合成、单写者世界中接通了：来源真实发布→项目规则形成具体工作义务→公开工作人员发现新义务并显式采用、读取和交付。嵌套 JSON 冲突已按递归类型语义修复；采用与请求现在具有精确工作上下文。**这支持有限持续工作的机制结论，不等于专业工作质量、通用自主规划或训练数据准入已获证明。**

## 1. 冻结身份与执行范围

| 阶段 | 冻结提交 | 正式执行 |
| --- | --- | --- |
| 旧版反例 | `db7949b83a18a8c226790eeafb6bf1015b1ca191` | 完整旧源隔离展开后执行真实 WorldCore/Session，P0 与同别名新工作采用反例；不是仅摘录函数 |
| A：内容与绑定 | `28786f42022df0836cc36e60cc9b030a97e526c5` | P0/P1、相关 N1/N3，冻结上完整 pytest 379 项、53.63 秒 |
| B：集成持续工作 | `62f3a6a11dc2917e857734bc587447b41a2dc9fb` | P0/P1 回归、P2–P4、两个新恢复切点、资料重叠回复反例、N1/N3；pytest 421 项、62.20 秒，Ruff 通过 |

阶段 A 源树 SHA-256：`6005607d3b14a0ea58414143de3b2177148d8cc0a11f40796e3df4c0e7a91d20`。

阶段 B 源树 SHA-256：`6398c901f9adeaba1092cec92f042226cb6dbf50b799ed348827ce26409008e9`。

源树摘要按 `src/**/*.py` 的相对路径与字节计算；阶段 B 批次还逐一保存全部测试文件、运行脚本和 pyproject 的起止摘要。阶段 B 每个作业及整个成功批次的起止身份一致，`code_dirty=false`。成功批次在 UTC 06:06:19–06:07:26（北京时间14:06–14:07）执行。归档文档在全部作业结束之后写入，最终文档提交不替换上述实现身份。

阶段 A 的pytest身份由批次起止包围，未单独记录该测试进程起止身份；不把阶段 B 更细记录倒填给它。阶段 A 正式作业全部完成后才接入阶段 B 运行时。第一冻结中已包含并行准备的纯维护规则模块和检查，但当时未以此宣称 P2 运行时验收。A/B 同一协议的重复执行计为回归，不增加独立情境样本。

批次最多并行六个作业；矩阵的不同情境在不同目录运行，各世界仍只有一个写者。**本轮模型 API 调用、GPU 使用、参数训练、真实资料采集均为零。**没有占用另一个项目的本地模型或 GPU。

## 2. 正式结果及审计对应

| 审计要求 | 最终结果 | 证据支持的范围 |
| --- | --- | --- |
| P0 嵌套内容顺序无关 | 9 类、17 个真实会话分支，76/76 | 68 个分支命题及8个顺序诊断对照；同时核对明确真值，不只比较两顺序一致 |
| P1 精确工作采用与资料路线 | 5 组，27/27 | 同别名不同工作/版本、新要求仍允许旧版或要求新版、迟到旧回复、政策绕约与错范围拒绝 |
| P2 事件驱动义务 | 20/20 情境，180/180 | 五个事实阶段×四种关系；实际通知/替代/后继/忽略及重复事件保持 |
| P3 多源局部更新 | 4/4 世界，64/64；另2/2布局对照 | 变化外部来源＋固定本地输入；两种文件组织；质量、忠实性、总体目标分开 |
| P4 公开持续工作人员 | 7/7 协议组，67/67 | 多端口/多任务、阻塞期间切换、资料恢复、新要求、自动发布后继、四种退出区分 |
| 代表恢复切点 | 2/2，20/20 | 绑定命令提交后、后继事件提交后真实进程退出；同检查点控制组比较 |
| 资料恢复与旧回复重叠 | 一个匹配反例，4/4命题 | 旧条件 superseded、新条件 resolved、工作 open；原始回复及无关项目保持 |
| 原 N1/N3 相关内容回归 | 22/22、11/11 | 受限 XLSX/JSON 与原来源消费合同；不是重跑全部旧故障矩阵 |

上述“通过”指观察符合预先声明的期望，包括应该拒绝、等待或内容评价失败的情境。不同分母包含状态、字节、制度事实、拒绝及诊断检查；**不求和为员工能力分数，也不把 pytest 中重复运行的协议算作新增样本。**

## 3. P0：修复已确认的内容评价缺陷

旧 `_equal` 只在直接标量层区分 bool 与 number，容器比较仍接受 Python 的 `True == 1`。多文件合并随后覆盖值，造成文件枚举顺序影响结论。

本轮递归检查对象键、数组顺序和标量类型；任意深度的布尔值与数值不同。有限 int/float 等价沿用既有合同，没有增加浮点容差、深层合并或选取正确文件作为赢家。冲突字段不会由最后一个文件代替其他声明成为有效答案。内容评价版本从 v0.7 的版本提升为阶段 A `finite-products-v0.8`，阶段 B 新增多源合同后为 `finite-products-v0.8.1`。

旧完整版本更正测量后为 **62/76**；修复后阶段 A 和 B 均 **76/76**。旧版14个失败断言包含10个独立真值断言与4个顺序诊断，不代表14处缺陷。嵌套 true/1、false/0 在一顺序误通过，反顺序失败；数组 `[true]`/`[1]` 还出现两顺序共同误通过，说明仅要求两顺序相同是不够的。相同嵌套数值、不同数值、合法单文件、顶层字段拆分等对照按各自真值保留。

旧 P0 第一次驱动误把 `artifact_id` 和 `object_id` 两种引用表示的字面不同算成依赖不同，带来17个伪失败。保留首次目录，再更正驱动于旧冻结源独立重跑；62/76 来自更正后的实验，没有覆盖首次记录。详见 [before档案](v08-json-before.json)与[最终P0](v08-json-conflicts.json)。本缺陷不追溯否定原 N3 的顶层 `margin/source_ref` 固定情境；旧报告已加后续审计注记，原 JSON 保持。

## 4. P1：别名、工作采用、政策目标和提交快照

`workspaces[project][alias]` 继续指向一个对象；`adoptions[work_id::alias]` 保存一项确切工作/需求版本的实际采用；公开 adoption_view 描述政策目标；提交独立冻结该工作采用快照。新工作可以沿同一别名合法显式采用，新旧工作可使用不同版本。旧绑定不因替代而转给新工作。

完整旧世界反例确认：旧工作已采用 input 后，新需求创建了新工作，但同一别名再次 adopt 被拒绝，提示使用新别名。新版消除该绑定结构障碍。`adopt_version` 明确接收 work_id，省略只允许恰好一个当前绑定；不同工作/项目和不适用政策仍拒绝。

项目 requirements 事先声明 `input_policy` 或按别名 `input_policies`，可为单政策或允许集合；fixed 版本可明确限定。包准入、需求修订、执行及提交评价核对同一合同，不能通过把 current_published 自改为 fixed 绕过要求。允许政策选择的合同仍尊重选择。

路线定义绑定稳定工作节点；每次请求冻结具体工作、需求、证据和路线版本。新工作使用既有 route_id 发新请求，迟到旧回复仍保留，但不能满足新工作或给它授予旧请求对应的新增读取权限。

P1 的五组分别是仅发布、替代后 fixed、替代后 current、迟到资料、范围与政策拒绝，共27项。原采用、固定文件、答案、既有制度完成记录（P1为delivery_only）和提交采用快照保持。**正式修订可以为旧提交添加 `superseded_requirements` 等适用性注记**；不把这种变化误算为篡改不可变内容，也不声称整个旧提交字典必定不变。[P1证据](v08-work-bindings.json)保存精确比较范围。

## 5. P2：相同变化按阶段与合同产生不同后果

项目声明来源、稳定 work node、事实阶段、effect、授权 actor 及有限要求更新。发布时捕获实际阶段和具体工作，影响作为独立事件提交。环境不替员工改文件、不自动采用，也不按固定轮数生成 work-2。

| 关系 | before_read／after_read／output_ready／pending | accepted |
| --- | --- | --- |
| notice | 一次规则后果通知，不新建工作 | 同左 |
| explicit revise | 正式替代当前工作，保留旧历史 | 同样明确修订；不伪装为维护后继 |
| maintenance | 声明的 active 阶段规则执行 revise | 独立 successor，旧 accepted 工作保持 |
| fixed ignore | 记录忽略，不重开任务 | 同左 |

阶段从真实记录计算：责任者对精确工作/需求的来源读取；本人有工作上下文的实际编辑；有效待审提交；制度 accepted。`output_ready` 在内核中仅表示明确产物编辑发生，不证明内容已完整或员工的心理判断；本实验另外实际写入预声明内容以构造产物完成条件。五阶段不是把同一固定第二轮换标签。

后继 ID 由发布、项目、规则和节点产生，保留前项关系且递增需求版本；maintenance_heads 指向该谱系的新义务。继承节点范围和合同，清空新工作提交/编辑，不继承旧采用。来源 release、rule/node 去重阻止重复后果。已被外部修订替代的目标记录 stale_target，不默默将旧事件转投新工作。

20个情境均检查真实后果通知、工作数与谱系、B文件和采用、旧提交/审阅、A无关事实、实际旧观察及重复效果。重复交付由**可信实验控制器将真实已提交事件的 event_id/kind/at/payload 原样重新入队**，验证 journal 对同一事件身份去重；该路径不会再次进入 apply_impact。影响层按 release/project/rule/node 的独立去重另由局部单测覆盖。控制器重投不属于公开员工动作，也不伪造审批。

开发审阅发现，初版 P2 把空 `state.observations` 前缀当作旧观察保持；`WorldCore.observe()` 实际返回观察但不自动写该数组。修正后的 `actual-observations-v2` 在事件之前立刻保存真实返回与构造阶段的实际工具往返，检查非空工作/需求/状态及当时仅可见 v1，再核对保存字节与哈希。正式180项采用此修正协议；旧draft/draft2的同分母不能用于声明新观察覆盖。[P2证据](v08-maintenance.json)。

## 6. P3：多源局部更新和责任区分

新增 `json_linear_sources`：2至8个明确来源、有限系数及常数；逐项读取固定 JSON 字段或 XLSX 缓存单元格。正文引用、具体工作采用快照、政策目标、实际字节哈希和贡献文件的来源依赖都必须对应。评价按独立 Python 标量计算，不调用被测 Spreadsheet 引擎造期望；不把布尔值或字符串转换成数值。

本矩阵用 A 的接口和 B 的固定本地3：初始 A=10、B=13；随后只更新 A 并真实提交、批准和发布。B 的 accepted 工作经声明规则产生后继。发布和新采用之后 B 文件均保持，随后由真实读取与编辑产生新提交。固定本地对象、无关工作和所有旧版本字节保持。

| 更新条件 | A独立目标20 | B按接口合计 | B忠实性 | 总体目标23 |
| --- | --- | --- | --- | --- |
| 正确 A=20 | 通过 | 23 | 通过 | 满足 |
| 故意错误 A=40 且获正式批准 | 失败，批准事实保留 | 43 | 通过 | 不满足 |

错误条件只注入一个上游源错误；下游忠实传播不是新增独立能力缺口。B 通过不能解释为端到端正确。旧 B=13 的固定提交评价在新发布和后继完成后保持原结果。

四个世界为单文件/两文件×正确/错误来源。单文件同时给 total 和 sources；两文件分别给 total 与 sources，以原有顶层并集合并，两者各自声明所贡献内容的精确来源。64项检查与另2项布局对照均符合期望；这种布局对照证明存在多个合法组织，不证明程序工作人员会自动探索两种布局。[P3证据](v08-multisource.json)。

## 7. P4：公开界面的等待、切换和继续

新 `ContinuousWorker` 只接收不透明的 `tools/observe/call` 端口。按端口及精确工作轮转，每 step 最多一个真实工具调用；观察、工具定义、参数、身份键及返回在发生时记录，与独立端口捕获逐项核对。世界控制器安装项目、恢复提供者或操作上游，但不给工作人员后台状态、正确答案或替它制作产物。

| 协议组 | 实际过程与期望 |
| --- | --- |
| blocked_resume | A请求留下持久不可得条件；B继续交付7；合法provider改变可得性；checkpoint继续后A发新请求、取得资料并交付11 |
| revision_multiple | 同端口多工作先完成；真实需求修订后发现新工作/需求，显式新采用与读取并交付19；其他工作保持 |
| missing_route | A报告 worker_waiting/capability_gap，无虚构请求或内核条件；B仍可完成 |
| budget | 一次动作预算明确截断；同一工作人员继续，最终完成两项交付 |
| environment_error | 控制器在真实观察之后、首次动作之前执行有权 pause；真实工具拒绝被记录为环境错误，不算合理等待 |
| multiple_sources | 公开读取两份确切来源，绑定与贡献依赖齐全，独立字面合计15 |
| published_successor | B公开交付11并accepted；之后控制器仅A的真实write/publish；事件自动生成后继；checkpoint恢复后发现新ID/需求2，同别名新采用v2并公开交付19 |

最后一组是冻结前新增的独立12项，原六组55项保留，正式合计67项；不能从早期55/55推断自动后继已经覆盖。该组后半程没有控制器直接 revise、重新装包或改 B 状态。旧 accepted 工作、提交、审阅、采用、版本和原观察保持。

worker_waiting 是策略出口；world_blocked 要有公开可见的真实未满足条件；budget_exhausted 表示实验预算截断；environment_error 保留真实拒绝或异常。submitted/completed 仅代表制度进度，独立内容评价另做。本组交付按 delivery_only 合同获得完成状态，不捏造经理批准。

checkpoint 仅支持**完整 step 返回之后**的公共策略进度保存与恢复；不是任意进程中断的策略 exactly-once。CLI `world-continue` 支持同一世界多端口、额外动作预算、保存结果及checkpoint；真实 CLI 测试覆盖先执行再恢复和非法配置无文件副作用。[P4证据](v08-continuous-worker.json)。

另一个实际联调反例是提供者恢复发生在旧不可得回复之前：原实现新请求得到资料后，旧 pending 条件又变 unavailable，使同一工作仍 blocked。现在较新可得性修订的请求会撤除旧 pending/unavailable 条件的阻塞作用；原始两个回应继续保存。冻结源直接重放原六个公开调用，旧条件 superseded、新条件 resolved、工作 open；测试同时覆盖 B 无关工作保持。[重叠回复证据](v08-information-overlap.json)。这属于阶段B开发缺陷，不归因于旧v0.7或阶段A冻结版本。

## 8. 代表恢复边界

两个新切点分别为 `adopt_version / after_command_commit` 和 `maintenance_successor / after_event_commit`。子进程真实 `os._exit(73)`，不是抛异常模拟；同一字节检查点复制出控制组和故障组，命令身份保持。

比较完整状态，仅排除诊断性 `wall_seconds` 与 `state_digests`；所有工作、绑定、请求、条件、签发、提交/审阅、操作登记及事件历史继续比较。另比较全部不可变版本与镜像字节、原命令结果、新实际观察，以及再次重试无正式效果。

绑定切点含另一项 fixed v1 已接受工作和真实pending请求；后继切点要求一个命令和一个事件的已提交前缀、只生成一个新义务、旧 accepted 工作不变。在故障注入及检查点复制之前捕获三个真实公开观察并纳入检查点，保存非空上下文和字节哈希；不把空 `state.observations` 当证据。两情境20项均通过。[恢复证据](v08-recovery.json)。

这支持两个新增机制的代表提交边界，不扩展为所有工具/切点组合、并发写者、宿主断电或分布式一致性保证。

## 9. 开发失败与测量修订记录

完整索引见 [开发记录](v08-development.json)，正式启动与测试见 [validation](v08-validation.json)。没有删除失败目录或回填过去未记录的起始身份。

| 记录 | 分类与处理 |
| --- | --- |
| P0首次旧版依赖断言 | 测量把两种等价引用表示直接比较；保留首次结果，更正后旧源独立重跑 |
| P1首次开发24/27 | 两个断言忽略合法适用性注记，一个使用错误状态名satisfied；限定确切允许变化后27/27，非三处新内核缺陷 |
| P3首轮0/64，四个世界构造失败 | 按工作授权的CreateObject漏传node上下文；修复真实范围传递，不增加通配授权；原失败未执行项保留 |
| P4首轮 | fixture私有对象将无读取权的alice列为writer，另一fixture授权名写错；保留构造失败并修正规格 |
| P4第二轮54/55 | 旧submission整字典比较忽略合法适用性标注；修正精确比较后55/55，再独立增加自动后继12项 |
| 资料恢复重叠反例 | 阶段B运行时旧pending条件未被新路线请求取代；真实调用复现后修复，冻结源匹配重放 |
| P2/恢复旧观察检查 | 空state.observations不构成证据；改为真实捕获与非空上下文/字节检查，保留旧draft |
| 冻结后首批启动失败 | 批次启动器将venv解释器符号链接解析到基础Python，依赖导入失败，pytest未收集；只修正外部启动器路径，源码/协议不变，再运行完整成功批次 |

启动失败的原supervisor、移动后的原日志及哈希均进入validation档案；它没有创建实验世界或执行机制检查，不将其算成 P0–P4 的生产失败，也不隐去这次尝试。开发缺陷、规格错误、测量错误和有意注入的负条件分别说明。

## 10. 复跑与证据索引

以下目录均须尚不存在，命令在第二阶段冻结源码和已安装的项目虚拟环境执行。不同命令可在不同目录并行，但不能对同一世界并发写入。

```bash
.venv/bin/python scripts/json_conflict_experiment.py --output runs/p0-new --workers 4
.venv/bin/python scripts/work_binding_experiment.py --output runs/p1-new --workers 4
.venv/bin/python scripts/maintenance_experiment.py --output runs/p2-new --workers 4
.venv/bin/python scripts/multisource_experiment.py --output runs/p3-new --workers 4
.venv/bin/python scripts/continuous_worker_experiment.py --output runs/p4-new --workers 4
.venv/bin/python scripts/work_obligation_recovery_experiment.py --output runs/recovery-new --workers 2
.venv/bin/python scripts/work_capability_experiment.py --output runs/n1-new
.venv/bin/python scripts/publication_consumption_experiment.py --output runs/n3-new --groups N3 --workers 2
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check src tests scripts
```

| Git归档 | 原始服务器证据目录 |
| --- | --- |
| [阶段A](v08-stage1.json) | `runs/json-conflicts-v08-stage1`、`work-binding-v08-stage1`、`work-capability-v08-stage1`、`consumption-v08-stage1` |
| [旧P0](v08-json-before.json)、[开发记录](v08-development.json) | `runs/json-conflicts-v08-before*`、`work-binding-v08-before`及各dev/draft目录 |
| [P0](v08-json-conflicts.json)、[P1](v08-work-bindings.json) | `runs/json-conflicts-v08-final`、`runs/work-binding-v08-final` |
| [P2](v08-maintenance.json)、[P3](v08-multisource.json) | `runs/maintenance-v08`、`runs/multisource-v08` |
| [P4](v08-continuous-worker.json)、[恢复](v08-recovery.json) | `runs/continuous-worker-v08`、`runs/work-obligation-recovery-v08` |
| [资料重叠](v08-information-overlap.json)、[完整验证](v08-validation.json) | `runs/information-overlap-v08-before`、`-after`；N1/N3 final目录；原测试日志与批次清单引用见JSON |

Git保存完整协议、逐检查结果、重要制度/版本事实及原始文件摘要；大文件、完整会话、世界和检查点留在服务器目录。各精简归档明确列出省略项，不能把摘要引用当作远端已包含全部世界。

本轮仍限合成数据、一个世界两个项目、有限JSON/XLSX内容合同和透明程序策略。真实工作材料继续用于校准工具表达、领域定义和通用关系；未观察的历史不补造，合法轨迹也不限于本实验参考路线。没有据此启动扩大训练或宣布高质量训练数据自动准入。
