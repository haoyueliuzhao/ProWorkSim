# v049 实现边界与采集前控制

本文件描述新学习窗口的实现和有限控制，不是模型实验结果。原始设计与种子先提交为 `a58b6fd`；本实现完成并提交后才允许加载新窗口 S0 和开始八条采集。实际模型执行、训练费用、分支差异与开发结果另行归档。

## 复用和新接缝

新文件隔离在 `software_*_v049.py` 与两个新宿主脚本。v048 Γ1、v042 精确分页、原 native 数值路径、完整 common3/3、原训练损失及优化器实现不改写。已有 18432 容量凭据直接复用，不发新模型资格请求。旧实验记录、旧符号 tracker、v046 未决库存和旧26/3/48队列不进入本轮。

`software_organization_v049.py` 提供严格 O1 两个稳定成员。SDK 的 `staff_done` 原有永久锁存不符合当前工作结束语义，因此新 worker 只在收到真实可达伙伴工作事件后解除当前会话的 done 锁存，保留全部历史、身份和计量。上下文或预算已耗尽的会话不会恢复。公共 schema 去除出生、永久退出；保留原生整候选树采用通道，不能以三方合并冒充整树采用。

公开 `task_formation.level` 显式标为O1，人数另标 `stable_two`，避免旧 `fixed` 人数标签落在任务形成字段而造成歧义；任务仍由成员自主建立。该模型前显示修订仅重验初态合同一项，未重复SDK工作路线。

`software_training_v049.py` 在生成前绑定真实新 worker 类、源用途、共同窗口和情境。旧声明器将 OpenHands 绑定为旧类名；新模块在私有 globals 中执行其原 code object，仅替换为严格真实新类的身份校验，旧模块全局不修改。情境指纹保留业务初态、公开诊断、工具身份和权限，剔除两项纯宿主准备 provenance/cost 的路径、缓存命中和秒数；不同随机世界 UUID 与准备目录不成为新的经验情境。改变公开诊断归属仍改变指纹。

`software_mapper_v049.py` 直接绑定世界提交回执、原 native 动作与实际后续输入、不可变版本及最终交付。整文件关系覆盖辅助函数。它要求最终精确版本测试回执在提交前实际呈现；伙伴采用的元信息和采用回执也须在相应动作/测试前实际可见。Γ1 同输入引用的第一观察仍在实际输入内，可作为元信息凭据，学习目标不展开引用。无法解释的集成、来源取得或版本链保留 unmapped。真实任务、责任和消息事件附入证据，不规定数量。

`software_organization_measurement_v049.py` 从新 manifest 的真实 actor/recipe/window 读取绑定，接受更新后状态；保留旧 Γ1 呈现算法中 `world_runtime_library=v047` 的库来源字面，另用新 case/runtime 标识核验当前世界。成员首次生成前就 context 拒绝时，不虚构首个实际输入模板。安全局部 context、共享预约、成员 fixed 预算结束分别记录；未知收费、身份、权限或完整性问题停止未开始库存。

## 学习和支持

完整 S0 包含 actor、critic、两个 Adam、RNG、recipe、步骤与窗口记录。旧 a/b critic 坐标显式改名为001/002，inactive不动；所有数值状态及原30维特征配方保留。新责任事实进入 Mapper；原 critic 特征读取器的 `work_items` / `workspaces` 等固定字段覆盖范围不扩大，不能据此声称新 O1 的所有任务字段都进入 critic。缺少该旧字段时按原实现取零。

实际训练使用生成的 Γ1 input IDs 与本人 output IDs。桥接器逐项绑定保存的 original/selected request、反馈生命周期、runner turn、response、预算 seal，并用实际 tokenizer/renderer复核原生序列。复核不会将展开的文本替代训练材料，也不是新增模型资格。

基础更新执行原 `SharedActor.update_window` code object，私有 globals 仅替换新组成校验器与B的只读梯度观察器。原 PPO、critic、累积顺序、截断和 optimizer 语句保持。单位组成与原更新的 CPU 完整状态同值控制支持接缝正确性；它不等于第二次9B B重放。观察器 hook 返回 None，以原顺序记录实际B leaf梯度，不新增反向。其分组和CPU float64方向诊断只用于选向，Q±仍从 S0 做原生加权反向。

每root/成员有原M=4，基础训练总分母仍为8×2；可信失败、未映射、缺席和mask各有原记录，不能重分配质量。四块顺序及两个类别顺序来自采集前设计。支持和实际梯度生成后封存单一方向核心与宿主 envelope，两者各有 seal。开发执行只在B完成且方向封存后开放。没有I方向时只运行有可靠基础材料的B四开发，不追加采集。

集成窄审发现 exporter 初版将行政删失额外排除出训练资格；这超出了原 `evaluable` 奖励资格。模型前已明确训练与F采用共同token＋时间制度的正式R_joint，因此已知且可信的行政R_joint0/1均保留基础材料；R_token/Q_token的null及行政标记照旧保留。该修订不读取模型结果，也不把未知奖励补成0。

## 监督和费用

固定依赖为 S0 → LA/LB 两个采集 worker → B → 条件Q±与B开发 → 各Q开发。后三者可以在资源允许时并行，最多3驻留，仅物理GPU3/4/5/7。每个worker先加载原数值实现并验证旧完整 common，再恢复指定完整新S0或更新后checkpoint；开发采样以最后恢复的新状态为准，逐回合冻结守卫核验。

保留原GPU稳定容量、live空闲量、RSS、磁盘和telemetry守卫。加载900秒、单生成episode6000秒、边界600秒；训练使用每次前向及其后反向/记账各900秒，不设整个完整窗口的episode总时限。没有失败重试、额外seed、第二方向、放大ε或增加H。

生成最多20槽/10M实际输入加输出；所有加载、保存、训练前向、反向、optimizer、只读梯度观察和GPU驻留时间单列。S0保存本身没有模型调用或更新。模型库存尚未执行的阶段不能用0成绩补齐；条件未启用和技术未执行也要分开。

## 有限控制与已发现实现缺口

各控制使用程序构造或CPU toy模型，不把预设输出计为真实9B生成或学习收益。完整回执保存在忽略提交的 `artifacts/software-learning-v049/`；源码、规格与摘要保留在仓库。

- [业务来源控制](software-learning-v049-task-sources.md)：新DA/DB参考解、错误候选、初态公开诊断及来源用途。
- [导出接口控制](software-learning-v049-export-interface.md)：真实SDK程序路线中的可信未提交和本地成功交付、成员目标及分母、情境指纹与用途隔离。
- Mapper 的四项纯CPU关系控制覆盖辅助函数变化、真实同树采用、缺少测试/采用回执、未知取得和变化的固定树，以及动态/冲突代码。
- 其余学习、生命周期、测量和监督器控制的最终不同项数、累计执行及失败原因见采集前总回执；不能把修复前失败从累计执行中删去。

已在模型采集前发现并修正的缺口包括旧 worker 类身份 gate、首请求context拒绝时缺少旧测量模板、O1初版漏接原生整树采用工具。开发时还有测试fixture漏字段、旧recipe构造器直接使用新坐标、主脚本字典语法错误等；这些都发生在真实模型调用0时，分别保存原控制结果，不表述为模型或数值训练失败。

最终[采集前总回执](software-learning-v049-cpu-controls.json)记录 **77个不同必要CPU控制均有通过证据**，累计91次检查：84通过、7次较早失败。累计包含一次仅对原失败断言的离线复核，不冒称又执行一遍SDK路线；最初4个可选SDK缺失skip另列，后来均在原SDK解释器中完成。全仓库 Ruff 通过。跨进程冷缓存初态指纹还做了一次零模型只读/环境准备检查，单独计录，不并入pytest项目数。

其中8次完整toy H1与3次toy Adam初始化累计actor/critic各11步、toy生成32次，均为CPU小模型控制；不能计为9B实验。导出三条程序SDK路线21个synthetic completion单列。模型前真实9B生成、反向、参数更新及GPU worker均为0。早期零生成context控制的pytest临时目录在尝试持久保存时已不存在，原故障及修复有文字回执，不能声称保存了该旧临时fixture的完整原件。

### 导出与 Mapper 最终窄控制补充

Exporter 的行政口径修订完成后，只运行三项纯函数 CPU 控制：已知安全行政 R_joint=0、R_joint=1 均保留 `eligible=true`，未知 `R=None` 保留 `eligible=false`；三者的 `R_token=None` 和行政标记都保留。没有重采此前未提交和本地成功 SDK 路线。

接回原生 `adopt_candidate` 后，只增加一条伙伴程序路线，共11个人工 synthetic completions：member_001 写完整参考文件并固定发布；member_002 通过原生动作非同值采用该候选，随后执行同树公开测试、fix、submit。实际 selected Γ1 输入中可定位采用前元信息、采用后且测试前的收条，以及最终提交前的同树测试反馈；最终整文件树保持一致，Mapper 为 `evidenced_peer_product_delivery`。两稳定成员均有原本人输出，成员支持字段与联合类别一致。这是执行通道和证据流的程序见证，不是新增真实模型协作成功或 Contribution 标签。

新 Mapper 开始严格消费 exporter 的 `evidence_sha256`、五个原件路径/哈希以及重新读档后的实际事件、责任、patch和delivery同值。修改payload而不更新seal、换到另一状态文件、重新seal但删掉真实事件三种反例均被拒绝。另一个纯CPU正反例确认，当最后观察的patches仅为 `$same_input_ref`，同一实际输入中保留的第一观察可提供确切元信息；错误版本、其他成员和未来呈现都不通过，不展开训练输入。上述新增3项控制通过，类别规则没有改变，Ruff通过。

同一伙伴原件还做了一次只读新机械读器测量，无新程序响应或验收。页协议违规/未决、首次实际后继缺反馈均为0，候选采用与测试页/最终版本关系可读；整个生产资格仍返回 `global_pause`，因为这些档案明确标为 `cpu_programmed_fixture`，与生产重构的 `actual_generation_settled` 身份不同，且无真实数值状态 guard 哈希。保留该结果，不放宽生产读器或将程序见证表述为9B资格通过。完整原件在 `artifacts/software-learning-v049/peer-export-controls-attempt1/`。

截至这些控制，导出端共三条程序 SDK 路线、21个人工 synthetic completions、真实模型调用与GPU调用均为0。前两路线完成后才补齐 O1 原生采用接口和证据seal消费；不能把它们追述为在最终源码全同字节条件下执行。不同接缝的已通过控制按实际版本和来源保留，未重复旧模型或新增容量资格。

另作一次跨进程冷缓存情境控制：新独立 `.venv` 进程只准备同一个已存伙伴CPU路线的 LA 初态，真实公开诊断 cache_reuse=false，两次诊断 driver 执行。公开 `initial_diagnostics` 与此前独立进程档案逐值一致，没有嵌套宿主路径/计时字段；新情况指纹与归档均为 `90ce6eeca6271d40929d4fce19bcbb7d899ce7610b523bce1262217ac978e3b1`。无需新增 strip 或扩大规范化范围。回执 `artifacts/software-learning-v049/fingerprint-cross-process-check/receipt.json`；模型、模型 tokenizer 和 GPU 均为0，未重跑 SDK 路线。

最后还在真实模型调用0时统一新来源资格字段：`contribution_eligible` 仅表示可供训练组成支持，新LA/LB窗口为true，新DA/DB为false但development_eligible保持true，旧v045不变。新训练 assessment overlay 一并同步。新增1项无SDK纯来源控制通过，全部业务assets哈希不变；新来源清单仅元数据seal从`19704f32…3159c59`更新为`e979a05c…673d1c2`。旧完整清单和各CPU case/hash保留，未重复SDK/跨进程路线；实际模型阶段的事前声明将绑定最终元数据。
