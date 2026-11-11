"""Render the final development report from frozen v199 result artifacts."""
import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from prepare_dependency_audit_v197 import ROOT,read
BASE=ROOT/'artifacts/software-benchmark-v199';DOC=ROOT/'docs/experiments'
def table(headers,rows):
    def clean(x):return str(x).replace('|','／').replace('\n',' ').replace('[',r'\[').replace(']',r'\]')
    return '| '+' | '.join(headers)+' |\n| '+' | '.join(['---']*len(headers))+' |\n'+''.join('| '+' | '.join(clean(x) for x in r)+' |\n' for r in rows)

def main():
    data=read(BASE/'development-r4/summary.json');metric=read(BASE/'development-score-r4/summary.json')
    gate=read(BASE/'final-audit-r2/summary.json');normal=read(BASE/'normalization-r4/summary.json');relation=read(BASE/'relation-review-r2/summary.json')
    groups=[g for g in metric['groups'] if g['budget']==4096];names={'E0':'仅保留最近观察（M1-5）','E1':'全局检索','E2':'仅保护验证状态','E3':'全局检索＋验证保护','E4':'E3＋有证据的图关系'}
    main_table=table(['条件','旧必要事件选中','参考事实直接呈现','可合法回读','48 个输入的本地 token 估计','比 E0'],[
        [g['condition']+'：'+names[g['condition']],f"{g['reference_events_selected']}/8",f"{g['direct_facts']}/19",f"{g['recoverable_facts']}/19",f"{g['input_tokens_estimate_sum']:,}",f"{100*gate['main_view_input_cost_vs_E0'][g['condition']]:+.2f}%"] for g in groups])
    sensitivity=table(['附加卡片总预算','E1 直达事实','E2 直达事实','E3／E4 直达事实','E3／E4 未满足保护组数'],[
        [b,*[f"{next(g['direct_facts'] for g in metric['groups'] if g['budget']==b and g['condition']==c)}/19" for c in ['E1','E2','E3']],next(g['unmet_protection_groups'] for g in metric['groups'] if g['budget']==b and g['condition']=='E3')] for b in [1024,2048,4096]])
    cause_labels={
        'partial_source_without_complete_qualified_definition':'引用范围含不完整文件片段，不能直接确定完整限定名',
        'no_complete_qualified_definition_in_cited_sources':'引用来源中未建立该名称的完整定义',
        'external_definition_or_dynamic_target_unobserved':'外部库或动态目标未取得定义／运行时绑定',
        'ambiguous_symbols_or_versions':'存在多个兼容实体／版本',
        'descriptive_endpoint_without_single_identity':'描述性端点，尚不是单一实体身份',
        'delta_edit_not_complete_definition_source':'引用含增量修改，当前完整定义构建器未重建文件',
        'composite_or_negative_version_annotation':'多对象或含排除版本的复合标注',
        'definition_exists_outside_cited_source_or_version':'同名定义存在，但不在引用来源／版本范围',
        'expression_or_dispatch_not_entity_identity':'表达式或动态分派，不能直接当实体',
        'import_alias_runtime_target_unresolved':'可见别名与端点相关，但运行时目标仍未证实',
        'unsupported_endpoint_form_or_missing_identity_evidence':'当前端点形式不支持或缺少身份依据'}
    report=f'''# v199：事实级证据呈现与全局检索分解实验

日期：2026-11-11。规范实现与结果为 **r4**；P0 工程修订和 P1 历史离线实验已完成。

## 1. 本轮结论

**先解决了三个可复现的实现问题：原文回读入口丢失、计数变化阻碍状态去重、没有关系证据的图加分。修复后，信息可以完整恢复，但默认呈现和图收益仍未达到下一阶段要求。**

- 全局检索与验证保护共同选中 8/8 条旧必要事件；19 条事前冻结的参考事实中，13 条直接呈现，19 条均可合法回读。
- E3 与 E4 在三个预算档、48 个决策点的 **144 对实际输入上完全一致**。本轮没有证实 Confirmed 图关系能增加事实覆盖或降低输入成本。
- 522 个新增事件归一为 237 组。原始来源、每次呈现及费用含义没有删除或合并；这些数字不是 token 节省率。
- 123 条旧必要关系已逐条登记来源与失败原因。端点绑定从 54/246 增至 56/246；直接关系证明仍只有 8 条。

按审计的停止规则，**暂不扩大 Confirmed 图传播，不打开留出轨迹，不进入新的真实模型回合**。本轮没有新的任务正确率或合法交付率。

## 2. 怎样做的对照

沿用 12 个旧任务的 48 个已见历史决策点，每点比较 E0–E4，并使用 1,024／2,048／4,096 三档附加卡片预算，共 720 个规范离线视图。每个任务贡献 4 点；48 点不是 48 个独立任务。

E0 只保留最近 5 个工具周期及原有行动链，旧观察留有回读引用。E1 在全部允许的历史材料中检索；E2 只保护每个精确测试选择器最近一次实际未成功的验证记录；E3 同时使用两者；E4 再允许经当前有效 Confirmed 边到达新实体的候选获得优先级。

五组共享来源、事实池、渲染器、权限、版本约束及预算。每卡最多 768 token，完整输入最多 98,304 token，没有固定卡片数量上限。没有修改模型、提示、公开测试或评分器，也没有启动模型或评分容器。

选择器不读取必要性标签或参考答案。但规则修订使用了已知开发材料和审计指出的问题，因此本轮是**开发验证**。19 条参考事实来自原 8 项必要事件，在首次视图运行前按原文冻结，由主助手 AI 审阅，不能称人工金标准或独立盲测。

## 3. 主结果：找到事件仍不等于呈现事实

以下使用 4,096 档。token 是本地官方分词器对假设输入的估计，**不是新 API 实耗，也不是完整任务累计 token**。

{main_table}
E0 的 0/19 表示这组特意选取的旧历史事实没有默认显示，不表示输入没有任务信息；它仍能通过合法引用恢复 19/19。其他近期观察与全部原行动链按共同规则保留。

本轮区分出的机制是：

1. **全局候选入口解决资格遗漏，检索排序本身仍会漏选。** 所有 19 条参考事实、15 条文本证据片段都进入了可定位的事实清单，但 E1 的默认输入只有 5/19。
2. **验证保护以较低开销补充另一部分信息。** E2 只增加约 0.53% 的输入，呈现 8/19；它不会主动保护所有历史代码分支。
3. **两者联合有补充作用。** E3 呈现 13/19，比 E1 多 8 条；全部 8 条旧必要事件被选中。代价是比 E0 多约 7.91% 输入，不能由此宣称团队净成本下降。
4. **图关系未增加收益。** 只有 P020 的一个候选满足有证据的非起点扩展条件，所用边是测试报告与测试身份的绑定；该候选原本已会被 E3 选中。它不是跨文件运行时依赖证明。

这些是该开发样本上的机制差异。没有完整任务运行，因此不能推断修复率、真实回读频率或最终总 token 改善。

## 4. 剩余六条事实为什么没有直接出现

所有六条都有准确原文并属于已选中的事件组；它们在**单卡 768 token 的事实取舍**阶段被排除：

| 决策点 | 未默认呈现的内容 | 已核实的原因 |
| --- | --- | --- |
| P018 Requests | 非 ASCII 分支、ASCII 星号分支，共 2 条 | 同一文件版本的多个片段归组后竞争单卡；函数块优先于这两段控制分支 |
| P041 Astropy | `&` 对应 `_cstack` 的分派项 | 递归代码已进入卡片，分派表被单卡上限排除 |
| P046 Seaborn | 自写测试断言要求的具体标签列表 | 实际输出列表已呈现，断言上下文未进入剩余空间 |
| P047 Seaborn | `ScalarFormatter`、`USE_OFFSET True` | 偏移量和故意 `assert False` 已呈现，同报告的其他诊断输出被排除 |

因此当前问题已从“找不到旧事件”转移到“同事件内如何分配事实预算”。不能把六条遗漏解释为模型不会使用信息，也不能用提高全局卡片预算掩盖单卡取舍。

{sensitivity}
2,048 到 4,096 档没有增加 E3 的参考事实直达数，却增加 60,182 个本地输入 token。扩大总预算并未解除 768 单卡约束。1,024／2,048 档分别还有 4／1 个验证保护组无法放入，均显式记录；4,096 档为 0。

事实含义也必须保留边界：P007 的异常涉及弃用警告；P047 是故意失败的诊断探针；P046 自写预言本身需要审查。原文出现这些内容不等于这些内容证明仓库修复错误。

## 5. 已修复的问题与实体覆盖

**回读入口。** 首轮用一张多来源代码卡替换原观察时，只留下被选事实的来源引用，丢失了被替换观察本身的引用。原始字节还在，却无法从当前输入合法定位。现在每张卡强制保留原位置引用，所有 720 个规范视图检查此约束；19/19 参考事实全档可回读。

**状态去重。** `personal_workbench.observed_history_entries` 每步增长，使没有实质工作变化的状态也被视为新状态。现在计数属于呈现记录，所有计数值、来源和原始消息继续保留；版本、测试、交付、笔记和 todo 的变化仍形成新状态。新增状态事件 428 个归为 143 组；另外 85 个搜索、6 个原始记录、3 个工作台事件保留，共 237 组。全来源的状态从 500 次事件变为 180 个状态段，保留 168 次真实状态转换，A→B→A 不合并成 A。

**图加分。** 首轮实现把起点实体也列入已达集合，主档 280 条加分记录中 272 条没有关系边。这是实现偏差，不能用作图关系效果的证据。r4 只允许有边证明的非起点扩展；无边、失效边和 Inferred 边均不能触发该加分。

**来源绑定。** 在原有完整同版本 `read_file` 拼接基础上，增加“完整 `write_file/create_file` 参数＋成功回执”的定义来源，识别导入别名，并保留 Artifact 回执别名。18 份不同成功完整写入提供了额外来源；没有伪造新的读取观察。最终有 135 个 Symbol、60 个实际 TestRun、59 个 TestDefinition；后者包含静态定义或报告中的测试身份，并非 59 次执行。148 条不同导入别名记录不等于运行时已解析；7 条静态解析候选仍标 Inferred。

关系复核保持严格：56 个端点绑定、187 个未解决、3 个歧义；8 条关系有来源证明，1 条仅双端绑定，114 条仍未映射。新增绑定只是 P007 与 P046 的两项测试函数。已逐条说明限制并核对 411 段诊断原文；描述性端点、复合版本标签、不完整定义和增量编辑支持不足仍占主要部分。**无法映射不证明原文不存在，也不把端点绑定当关系证明。** 完整失败分类和每条记录见附录与 JSON。

## 6. 成本、验证与准入

最终 r4：720/720 视图完成，0 执行异常；21 项 CPU 控制通过，6,229 次默认事实呈现逐项匹配原始来源；全部输入保持权限、来源、版本及预算约束。工程门通过，但它只说明实现和测量边界可信，不能代表图有效。

r4 四路低优先级 CPU 执行约 {data['wall_seconds']:.2f} 秒墙钟、{data['worker_CPU_seconds']:.2f} 秒累计 worker CPU；单 worker 峰值约 {data['max_worker_RSS_KiB']/1024:.1f} MiB。完整建图／事实构建包含在累计 CPU 中。分组执行顺序固定且有缓存复用，不能把 E4 较小的计时解释为图算法更快。

原文恢复做了 9 次有界 CPU reader 调用，用于验证引用和字节完整性；**Agent 实际回读 0 次，事实实际采用未测量**。没有将验证调用混入真实行为数据。新被测 API 调用及费用为 0，无 Docker、GPU、训练或共享服务器配置修改；Codex 工程与审阅平台成本无法单独取得，不能说所有模型劳动成本为 0。

r1–r3 与所有失败检查日志均保留。r2 只修复回读入口；r3 修正状态身份；r4 修正关系加分。它们是发现具体缺陷后的开发修订，不是独立重复试验，也不是挑选最优分数。主表仅用 r4，历史结果不混合。r1 的一次报告草稿把有效扩展写为 0；最终审计 r2 按数据更正为每档 1 个候选，所有输入无变化的结论不变。

## 7. 后续决策

当前保留 M1-5 为强基线，保留全局候选入口、验证保护和可恢复的事实表示。下一步应先改进**事实之间的预算分配**，例如按问题相关性安排同事件内片段，避免整个大文件只能竞争一张卡；必须先冻结规则，再在未用于改规则的材料上检查，不能针对这里六条文字硬编码。

不继续增加 Confirmed 图传播深度或边类型；123 条关系的语义规范化和部分定义绑定仍可作为基础工程，但不能先承诺图一定有效。未评估的必要性标签不能凭原文一致性补成高精度：本轮 Fact Precision 与完整 Path Recall 仍不可作独立统计结论。

v198 留出清单 r2 保留，未打开其轨迹或评分；这些任务较早仍有开发校准曝光，不能称全项目历史独立确认。先取得事实级增量证据，再考虑新的单 Agent 全任务评测，之后才进入 REVIEW2 的职责—通信—上下文联合对照。

## 8. 文件

- [实现与逐项证据附录](software-benchmark-v199-fact-context-appendix.md)
- [规范实验指标](../../artifacts/software-benchmark-v199/development-score-r4/summary.json)
- [最终准入审计](../../artifacts/software-benchmark-v199/final-audit-r2/summary.json)
- [123 条关系复核](../../artifacts/software-benchmark-v199/relation-review-r2/summary.json)
- [522 个事件归一映射](../../artifacts/software-benchmark-v199/normalization-r4/summary.json)
- [原协议](../../artifacts/software-benchmark-v199/protocol-r1/plan.json)、[r2](../../artifacts/software-benchmark-v199/protocol-amendment-r2/record.json)、[r3](../../artifacts/software-benchmark-v199/protocol-amendment-r3/record.json)、[r4 修订](../../artifacts/software-benchmark-v199/protocol-amendment-r4/record.json)
'''
    facts=read(BASE/'fact-reference-r1/facts.json')['facts'];status={f['reference']:f for r in metric['reference_details'] if r['condition']=='E3' and r['budget']==4096 for f in r['facts']}
    fact_table=table(['事实','原文／值','来源消息','E3 直接显示','合法回读'],[[r['id'],str(r['value']),r['message_index'],'是' if status[r['id']]['direct_in_card'] or status[r['id']]['direct_original'] else '否','是' if status[r['id']]['legal_visible_recovery_reference'] else '否'] for r in facts])
    causes=table(['失败／限制分类（可重叠）','端点数'],[[cause_labels[k],v] for k,v in relation['nonexclusive_endpoint_failure_categories'].items()])
    mapping_rows=[]
    for r in relation['rows']:
        d=r['original_annotation'];codes=[]
        for side in ['from_binding','to_binding']:
            b=r[side]
            if b['status']!='bound':codes+=b['failure_analysis']['categories']
        text='；'.join(cause_labels[x] for x in dict.fromkeys(codes)) or ('有逐条来源关系证明' if r['relation_proofs'] else '两端已绑定；缺少要求的关系语义证明')
        mapping_rows.append([r['point']+'-'+str(r['annotation_index']),d['from']+' → '+d['to'],r['from_binding']['status']+'／'+r['to_binding']['status'],text])
    gates=table(['门','结果','依据'],[[g['gate'],g['status'],g['evidence']] for g in gate['engineering_gates']])
    appendix=f'''# v199 实现与证据附录

本附录服务于 [主报告](software-benchmark-v199-fact-context-report.md)，规范版本 r4，2026-11-11。以下指标只描述历史开发视图。

## A. 三级数据与来源规则

```mermaid
flowchart LR
    S[此前实际可见的原消息与哈希] --> E[事件／版本／状态段]
    E --> F[原文字段或片段 Fact]
    F --> P[消息身份＋JSON 路径＋字符范围]
    E --> G[来源约束的实体与关系]
    G --> Q[候选排序]
    F --> Q
    Q --> C[状态卡／证据卡]
    C --> R[原始引用的有界回读]
```

Fact 字段为 id、event_id、kind、name、value、origins、version、semantic_location、status、presentation_role。每个 origin 包含 source_id、message_index、message_sha256、channel、pointer、可选字符 span／调用下标。相同值但不同含义（如 executed=False 与 passed=False）不合并。精确文件／报告位置可合并同一事实的来源；不靠相似文本认定身份。

状态身份按工作空间版本、测试覆盖、交付、任务、消息、交接及个人笔记／todo 建立。只有连续相同状态段归并；只增长的历史条目计数另列为 occurrence_counter，数值与原文保留。TestRun 按实际 report 身份合并页与回读；同选择器重跑、不同版本执行仍是不同 TestRun。代码按私有作用域、完整版本和路径归组，不把另一版本片段拼入当前定义。

成功完整写入必须同时有真实调用参数与成功回执、路径和 source_reference；只写在计划里或失败写入不能构成定义来源。修改后的工作空间版本不是新 Git commit。静态 ImportAlias 为 Reference；静态可解析候选仍不证明运行时调用。

两种卡使用共同硬限。历史状态可显示，但须带版本／superseded 状态；历史测试不证明当前代码正确。每张卡保留替换位置的原始引用以及实际选中事实的来源引用。没有使用生成摘要作为新事实来源。

## B. 冻结的选择算法

- 查询：原 issue 与最近 3 个实际动作。BM25 k1=1.2、b=0.75；当前路径匹配加 2、当前版本加 1；失败状态本身不额外加检索分。
- E2/E3/E4 的保护：同精确 selector 最近实际执行且未成功的记录。保护不足显式报告，不把更旧成功当覆盖新版本的成功。
- Fact 默认优先级：counts100、passed99、显式 assert False95、异常／警告90、诊断输出85、断言上下文80、完整可见函数75、控制链72、分派表70、失败测试名60、语句40；同类再按词法相关性及稳定身份排序。已完整引用的同来源子片段不重复引用。
- E4：从前 8 个检索起点沿一条当前有效 Confirmed 的 declares／references／reports_test 边寻找非起点实体，给其已在共同候选池内的事件加 1。它改变排序资格，不引入此前未见材料；不把全局 Version 节点当全仓桥梁，不用 Inferred 边。
- 最近 5 个工具周期、原始行动链、输入工具定义及权限不变。附加卡片总预算 1024／2048／4096，单卡 768，全输入 98304，无固定卡片数上限。

这些规则在各修订首次运行前冻结。r2/r3/r4 的具体工程原因和源码快照分别保留；最终不得复用 r1 图自奖励解释收益。

## C. 19 条事前冻结的事实参考

{fact_table}
4 条为结构化计数字段，15 条为字面文本片段。直接覆盖按来源身份和指针／区间校验，不能仅靠相同数字或文字在其他位置出现。原字段的父结构包含相同子值时可算覆盖；错误来源或截断片段不算。合法恢复还要求引用实际出现在该方法输入中，不能仅凭后台存储有原文。

所有参考事实在候选清单中均可定位，所有文本目标都有原文区间；这只是既知开发参考上的覆盖。事实是否普遍必要、遗漏其他必要事实与无关 Fact 比例没有独立全量标注，故不报告虚构的 Fact Precision。

9 次 CPU reader 调用均按 8192 字符上限回读并拼回原件，未发送给模型。Agent 使用率为未测量，不能写成 100% 恢复或 0% 使用成功。

## D. 123 条关系：覆盖与限制

56/246 端点唯一绑定；187 未解决、3 歧义。8 条直接关系均属于有执行来源的测试—版本关系；1 条仅两端绑定；114 条未映射。48 个最终实体注册表与用于关系复核的注册表哈希一致，复用该复核不会混用实现。

{causes}
分类可重叠，属于当前解析器与引用范围的诊断，不是已经证明的唯一根因。描述性／复合标注需先拆成可核查实体，不能随意从一句话挑出想要的部分。partial 或增量修改来源未被当前完整定义解析器覆盖，不代表原任务模型不知道该代码。4 条相关别名未解决不是所有别名失败；外部／动态对象不能仅由 AST 升为 Confirmed。

每条关系的完整原标注、两端实体或失败引用、逐跳边、版本、证据片段和确认状态均在 [relation-review-r2/summary.json](../../artifacts/software-benchmark-v199/relation-review-r2/summary.json)。411 段诊断引用已经逐段按原消息哈希、指针及字符范围复核。下面列全部 123 条，保留原标注索引：

{table(['条目','原标注端点','端点状态','关系证据／限制'],mapping_rows)}
## E. 工程准入、成本与复现

{gates}
21 项 CPU 控制涵盖：警告／stdout／故意失败区分、函数与控制链片段、连续状态与 A-B-A、版本隔离、测试分页与真实重跑、代码版本归一、同值不同字段、五条件共享事实、来源恢复、篡改拒绝、成功写入与失败写入、历史不可变、同下标不同来源、重复子片段、跨成员拒绝、预算不足、引用区间、结构化字段、原位置回读保留、呈现计数、图边证据与失效过滤。

最终 720 视图逐项检查 6,229 次来源值，0 权限／版本／预算错误；未满足保护的低预算记录单列，不能称硬限错误。首次开发控制中的失败为测试夹具短观察／首观察不应遮蔽、权限异常类型等断言修正，日志原样保留。

规范运行命令（已执行，完成目录禁止覆盖）：

```bash
LITELLM_LOCAL_MODEL_COST_MAP=True OPENHANDS_SUPPRESS_BANNER=1 .venv/bin/python tools/run_offline_scorer_v096.py tools/run_fact_context_v199.py --revision-r4
.venv/bin/python tools/score_fact_context_v199.py --revision-r4
.venv/bin/python tools/audit_fact_context_v199.py
.venv/bin/python -m pytest -q tests/test_fact_context_v199.py
```

不要为了复算而覆盖 r1–r4 或自动重跑模型。源码快照位于 `artifacts/software-benchmark-v199/development-source-r4/`，大体积原文／视图位于 `runs/software-benchmark-v199/development-r4/`，轻量指标含路径与哈希。

主实现：[事实模型与选择](../../src/proworksim/software_fact_context_v199.py)、[实体来源](../../src/proworksim/software_evidence_bindings_v199.py)、[独立事实覆盖判据](../../src/proworksim/software_fact_metrics_v199.py)、[执行器](../../tools/run_fact_context_v199.py)、[评分](../../tools/score_fact_context_v199.py)、[关系复核](../../tools/map_fact_relations_v199.py)、[最终审计](../../tools/audit_fact_context_v199.py)。

最终结果是工程通过、开发对照完成、科学增量门不通过。没有打开留出内容，没有新 API、Docker、GPU、训练或共享服务器修改；过去现金账本未动。审阅为主助手 AI，依用户此前明确指定；不冒称人工或独立专家审查。
'''
    (DOC/'software-benchmark-v199-fact-context-report.md').write_text(report)
    (DOC/'software-benchmark-v199-fact-context-appendix.md').write_text(appendix)
    print('report and appendix written')
if __name__=='__main__':main()
