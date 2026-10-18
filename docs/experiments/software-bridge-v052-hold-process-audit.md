# v052 阶段 A：v051 HOLD 全16轨迹只读工作过程诊断

## 范围、原结果和结论边界

本诊断覆盖原 HOLD **全部16条已执行轨迹**，包括5条原 F=1和11条未提交 F=0，按原清单顺序处理。原32行中的另16行来源阻断继续保留。没有只选成功或失败子集，没有替换任务，也不据本诊断为 v052 的六个 CAL2 任务／12槽选题。

本次没有模型、tokenizer、仓库测试、私验、终态验收或世界动作执行；没有补验11条未提交树，没有改原 F、费用、guard、报告或 runtime。工作过程证据独立保存，不能把分析器错误当成原实验技术未知。

完整机器报告：[software-bridge-v052-hold-process-audit.json](software-bridge-v052-hold-process-audit.json)，SHA256 `8b9bc5a3db4194eb03b3373fa591caa3fe60a87d73f462df19b904c23379f648`。原槽逐动作证据、输入与版本来源另保存在报告链接的 `artifacts/software-bridge-v052/hold-process-audit/slots/` 和 `r2/slots/`。

可证实的接缝是“受检候选、实际反馈、后续合法固定与提交”之间存在具体断点，而不是已证实的 context 缺陷：两条未提交轨迹已出现公开全套测试 `passed=true` 的候选，实际反馈也已进入成员后继输入，随后仍未完成合法固定提交。其余9条未提交轨迹中，2条没有公开测试，7条有公开测试但未观测到全过候选。后两类不能分别写成“最终树一定错误”或“从未正确定位过任何缺陷”。

## 事前口径与执行记录

方法在全库存遍历前保存为 [method-before-execution.json](/data1/zhuxinrui/projects/ProWorkSim/artifacts/software-bridge-v052/hold-process-audit/method-before-execution.json)。独立解析器是 [software_bridge_v052_hold_process_audit.py](/data1/zhuxinrui/projects/ProWorkSim/scripts/software_bridge_v052_hold_process_audit.py)，只使用标准库读取既有证据，最多4个并行 CPU 读取器。

证据链来自：

1. 原终态32行清单及各 worker 的原报告，固定16条实际运行身份和原 F。
2. 原 `experience.jsonl` 的 policy decision、工具原回包、model call ID和序列；同一调用只归一次费用。
3. 原 episode manifest、归档末态与全部不可变仓库版本。逐版本读取已存 JSON 文件集，核对归档 SHA，比较真实 UTF-8 文件内容；不运行代码。
4. 原测量已绑定的674个实际 `selected-request.json`，绑定 request SHA和原 input-ID SHA，读取真实可见问题、伙伴公开内容以及反馈呈现。没有重新分词或重新运行反馈测量。
5. 原每调用 ledger 的 `reported_usage`、原 native accounting 与 guard。费用是该动作对应的完整原生成费用，不是“移除动作就一定节省”的反事实估计。

初态可见问题、每次修改的前后精确 reference／文件集 SHA／文件差异、同版本测试、反馈第一次实际呈现、固定和提交动作及拒绝原文均落在逐槽 JSON。公开测试通过仅记为当时原公开测试的结果，不代替未发生的固定交付或独立终验。

准备阶段一个紧凑 schema 探针把 `public_tools` 的 list payload 当 dict，抛出 `AttributeError`；修正探针类型过滤后才开始全库存解析。首次完整遍历的16槽中，11槽分析成功，5槽在已有 fixed patch 的伙伴可见性环节遇到合法 Γ1 `same_input_ref` 对象，分析器误当 list。首轮摘要、错误堆栈和首版源码全部保留；分析器随后只解析同一实际请求第一 observation 中 `/observation/patches` 的精确引用，只重新处理原5个 parser-error槽，复用另11槽，不重跑旧测量、SDK或模型。

最终16条全部解析闭合；主遍历为16个唯一槽，累计21次槽解析尝试。首轮摘要 SHA为 `6e0af167d8635ca46e287a5684300d6ea52d52b0c020443489289c14038f4742`；合并后的 [r2/summary.json](/data1/zhuxinrui/projects/ProWorkSim/artifacts/software-bridge-v052/hold-process-audit/r2/summary.json) SHA为 `a48b6d62a87e3138ea2f2f9b9df005f48cac184d393c4e7a6329a59cd0a438e2`。变更前后仅做相应解析器 Ruff 检查，均通过。最后的综合 JSON只读取这些生成的审计文件和已有机制摘要，没有再次遍历原轨迹。

## 全16槽时序盘点

下表的“版本变更”包括显式采用／整合造成的新私有版本，并不全是手工代码编辑；“提交”是成功固定提交动作次数，终态 F仍只由原最后合法固定提交决定。同一槽可以多次提交。重复读取采用严格口径：同成员、同路径、同不可变版本、同参数范围／搜索条件、同返回内容，第二次及之后才计入。

| 原槽 | 原 F | 版本变更 | 原公开测试（通过） | 固定 patch | 成功提交 | 精确重复读取 | 对应原调用 token |
|---|---:|---:|---:|---:|---:|---:|---:|
| iniconfig-1 / S_star | 0 | 4 | 4（0） | 0 | 0 | 1 | 10,742 |
| iniconfig-1 / B | 0 | 5 | 4（1） | 0 | 0 | 0 | 0 |
| iniconfig-1 / Q_plus | 1 | 4 | 4（1） | 1 | 1 | 9 | 100,951 |
| iniconfig-1 / Q_minus | 0 | 5 | 5（1） | 0 | 0 | 1 | 11,161 |
| iniconfig-2 / B | 0 | 6 | 5（0） | 0 | 0 | 2 | 23,622 |
| iniconfig-2 / Q_plus | 0 | 5 | 4（0） | 0 | 0 | 6 | 74,342 |
| iniconfig-2 / Q_minus | 0 | 6 | 4（0） | 0 | 0 | 4 | 48,451 |
| iniconfig-2 / S_star | 0 | 5 | 0（0） | 0 | 0 | 15 | 176,938 |
| dominate-1 / Q_plus | 0 | 3 | 0（0） | 0 | 0 | 12 | 137,849 |
| dominate-1 / Q_minus | 0 | 3 | 2（0） | 0 | 0 | 6 | 63,747 |
| dominate-1 / S_star | 0 | 3 | 2（0） | 0 | 0 | 3 | 32,397 |
| dominate-1 / B | 1 | 3 | 2（2） | 2 | 2 | 1 | 9,850 |
| dominate-2 / Q_minus | 1 | 6 | 5（4） | 2 | 3 | 1 | 12,625 |
| dominate-2 / S_star | 0 | 3 | 1（0） | 0 | 0 | 17 | 183,354 |
| dominate-2 / B | 1 | 4 | 3（2） | 2 | 2 | 1 | 10,281 |
| dominate-2 / Q_plus | 1 | 3 | 2（2） | 2 | 2 | 1 | 9,929 |
| 合计 | 5成功 | 68 | 47（13） | 9 | 10 | 80 | 906,239 |

原674次完整生成对应623个已解析 policy action和51个原格式反馈单元；701决定与27次执行前共享预算拒绝的差异沿用原账本。总7,840,791实际 token、47次公开测试和5次最终 host 验收均不改变。68个私有版本变更中包含1次文件内容已同值的再次采用。

原可见问题分别是：iniconfig-1 的 SectionWrapper 参数／访问异常，iniconfig-2 的节与续行解析异常，dominate-1 的上下文 `get_current`／`attr`，dominate-2 的转义／反转义行为。每个角色第一真实输入均有原问题原文和 source pointer。问题描述、具体修改和原测试结果的对应关系可逐版本检查，但本报告不把模型后续任何编辑都自动判为“正确理解了反例”。

## 两条“已有公开通过候选但未固定提交”的具体链

### iniconfig-1 / B

member_002 的原私有 `obj-520aa9e6ee8ece99dce73855/v4`，文件集 SHA为 `844250e063d4968f28bddc5aeea8d2a664cfe76c20af2ebbe6204f72e3f3e990`。序列824修改得到该版本；870对该版本执行原公开测试，`passed=true`。反馈在序列912的实际成员输入首次呈现，之后该成员还有2次真实生成。

- 序列916先调用 `submit_integration`，原合法拒绝为 **“Publish a fixed patch of this exact working version before submitting”**。该次原调用13,866 token。
- 拒绝原文又在序列958实际呈现。序列962调用 `fix_patch`，指定 `task_ids=["fix_section_wrapper"]`，原合法拒绝为 **“Only the current task owner may perform this task operation”**。该次原调用13,226 token。这个任务在序列893由另一成员创建，本次没有该调用者的合法 ownership。

这是被原任务／固定提交合同拒绝的时序，不是接入 bug。两次生成合27,092 token，之后原共享预算停止。没有跳过固定、代替成员取得任务或补验旧树，原 F=0保留。[逐槽证据](/data1/zhuxinrui/projects/ProWorkSim/artifacts/software-bridge-v052/hold-process-audit/slots/v051-hold-iniconfig-1-B.json) 保存原输入、版本、调用来源及完整错误对象。

### iniconfig-1 / Q_minus

member_002 的原私有同一 object／`v4`，文件集 SHA为 `c8b3889d5e49ef0a3eeef6faaa3925f5d79e8502414d8de33a21d6edf3ab72d5`。序列779修改；825对该版本公开测试通过；反馈在序列867实际呈现，之后该成员还有2次真实生成。

这两次分别为序列871 `create_task`（13,911 token）和917 `claim_task`（12,771 token），均被合法接受。该成员没有后续 `fix_patch` 或 `submit_integration`，两次原生成共26,682 token；原共享预算停止与原 F=0保留。另一个成员随后继续自身私有编辑与测试，不能把其结果替代为该候选的固定提交。[逐槽证据](/data1/zhuxinrui/projects/ProWorkSim/artifacts/software-bridge-v052/hold-process-audit/slots/v051-hold-iniconfig-1-Q_minus.json) 给出了两个成员的分开时序。

这两条证明“通过反馈后仍有实际行动，但未完成合法交付”，不证明模型本应选择哪个动作，也不证明再给额度就一定成功。全库存另有2个“已通过测试却未以同一个 reference 提交”的测试事件位于成功的 dominate-2/Q_minus 槽；其后存在相同文件内容的新版本与交付，不能把这2个事件额外算成未交付失败槽。

## 伙伴成果：已证导入链与先前交付必须分开

全16槽有25个原 directed work-message／handoff 类事件，其中23个至少在接收成员的真实公开 observation 中出现；这只是实际呈现，不是语义使用证明。没有记录到通过 `read_file(patch_id=...)`／`search_file(patch_id=...)` 单独读取伙伴固定代码的动作。另有4槽共5次明确 `adopt_candidate`／`integrate_patch`：4次导入前后文件树不同，1次文件树已同值。受者随后确有原同版本测试、实际反馈和后续相同树提交。

| 原槽 | 作者已先提交相同树 | 伙伴导入 | 受者测试／反馈实际呈现 | 受者提交 | 最后合法端点 |
|---|---:|---:|---|---:|---|
| dominate-1 / B | 664 | 735，非同值采用 | 758／777 | 852，delivery-2 | 受者 delivery-2 |
| dominate-2 / B | 290 | 478，非同值采用 | 708／727 | 804，delivery-2 | 受者 delivery-2 |
| dominate-2 / Q_plus | 703 | 726，非同值整合 | 774／793 | 870，delivery-2 | 受者 delivery-2 |
| dominate-2 / Q_minus | 455 | 568非同值采用；710再次同值采用 | 616／660；733／752 | 804，delivery-2 | 作者898的 delivery-3 |

表中均为原 experience 序列。每条链绑定 patch ID、作者、输入来源版本、受者前后完整文件树 SHA、受者测试来源版本和实际呈现 input SHA。四槽的作者都已在伙伴导入前提交**相同文件树**。所以已证的是具体成果使用与后续交付谱系，不能将后来的采用归因为新增 episode 成功或一般协作收益。dominate-2/Q_minus 的受者提交甚至不是最后验收端点；最后回到作者已提交过的相同原版本。报告的 `partner_import_chronologies` 保存这一差别。

文字建议是否改变接收者的理解、没有显式导入的编辑是否受伙伴启发，仍为 `unknown/null`。当前并未为每条消息做完整语义归因，不能把未识别等同于未发生。

## 重复活动及费用

严格同成员同版本同返回内容的重复读共80次，对应原完整调用906,239 token，约占全槽原实际 token 的11.56%。它们同时出现在成功和未提交轨迹中，例如成功的 iniconfig-1/Q_plus 有9次，未提交的 iniconfig-2/S_star 有15次、dominate-2/S_star 有17次。报告保留每次重复相对于哪一个先前序列、文件路径／版本、返回内容 SHA、参数范围及费用，未用消息数或源码文件名相同就判断重复。

跨成员相同路径／范围／返回片段的内容重叠另有37次，对应372,473 token。它不要求两成员完整文件树相同，也不等于伙伴使用，与同成员重复类别可能重叠，不能相加成“浪费总量”。

文件树已同值的再次采用1次，对应14,513 token；返回曾出现过的成员文件树3次，对应42,546 token，其中包含上述同值采用。相同编辑参数对相同前态的再次尝试1次，对应12,058 token。原“File content did not change”等拒绝另按实际错误计数保存。回退、复读、确认和重试可能有工作目的；这些都是可观察的调用及成本，不是可移除成本的因果估计，更不能把全部输入 token 归为浪费。

## 对 v052 的有限用途

本诊断没有发现需要绕过原 fixed-patch、ownership 或 submit 合同才能继续的执行缺陷。先固定同版本、持有被绑定任务等均是合法合同条件。PS1继续原模型可见 Γ 和交付合同，本报告不建议自动补固定、自动转任务、代替提交或重采旧轨迹。

可行动的测量接缝是：在**新的、事前冻结**协议中，将末态代码结果 `R_code` 与合法固定交付 `R_joint` 分开记录，观察已有代码候选与工作过程交付是否分离。不能为回答这一问题回头私验旧11条未提交工作区。此做法也不意味着两条已公开通过候选的旧 F可以改为1。

其他结论仍受限：2条未测试树的正确性未知；7条只有失败公开测试的轨迹可能曾有局部正确修改；23条消息实际出现不证明语义利用；4条明确非同值伙伴导入不证明因果成功增益；额外预算／更长 context 的收益未在这里检验。v052的六个既定 CAL2开发任务与最多12个新槽不因本次结果而改变。
