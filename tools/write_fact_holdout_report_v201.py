"""Render the frozen historical task-holdout report and annotation protocol."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from prepare_dependency_audit_v197 import ROOT,read
BASE=ROOT/'artifacts/software-benchmark-v201';DOC=ROOT/'docs/experiments'
def table(headers,rows):
    def clean(v):return str(v).replace('\n',' ').replace('|','／').replace('[',r'\[').replace(']',r'\]')
    return '| '+' | '.join(headers)+' |\n| '+' | '.join(['---']*len(headers))+' |\n'+''.join('| '+' | '.join(clean(v) for v in row)+' |\n' for row in rows)
def main():
    metrics=read(BASE/'metrics-r1/summary.json');data=read(BASE/'offline-r1/summary.json');source=read(BASE/'source-admission-r1/summary.json');gate=read(BASE/'admission-r1/decision.json')
    lookup={(g['condition'],g['budget']):g for g in metrics['groups']};names={'A':'事件单卡（v199 E3）','B':'事实多卡（冻结 v200 F1）','C':'M1-5'}
    main_table=table(['条件','必要参考直接呈现','有用参考直接呈现','必要参考可恢复','输入 token 估计合计','相对 C'],[
        [c+'：'+names[c],f"{lookup[c,2048]['necessary_direct']}/34",f"{lookup[c,2048]['useful_direct']}/12",f"{lookup[c,2048]['necessary_recoverable']}/34",f"{lookup[c,2048]['input_tokens_estimate']:,}",f"{(lookup[c,2048]['input_tokens_estimate']/lookup['C',2048]['input_tokens_estimate']-1)*100:+.2f}%"] for c in names])
    sensitivity=table(['附加预算','A 必要覆盖','B 必要覆盖','C 必要覆盖','A 输入','B 输入','C 输入'],[[b,*[f"{lookup[c,b]['necessary_direct']}/34" for c in names],*[f"{lookup[c,b]['input_tokens_estimate']:,}" for c in names]] for b in [1024,2048,4096]])
    report=f'''# v201：冻结 F1 的任务隔离历史留出验证

日期：2026-11-12。已完成候选冻结、事实标注规范、来源准入和 A/B/C 离线对照。**本轮是历史开发留出验证，不是全研究历史未见的独立确认。**

## 1. 结论

**主档 2,048 token 下，多卡 F1 没有比单卡增加必要参考覆盖。** 两组均为33/34；F1多呈现3条有用参考，但完整输入估计多4,283 token，约0.49%。相对M1-5，两种事实管理方式均增加4条必要参考；F1增加约4.92%的输入。

这次没有复现v200中“多卡补齐全部六项必要遗漏”的主档优势。它也不证明F1没有任何价值：1,024敏感性档在一个任务上有增益，有用参考的覆盖也提高；但这些不足以替代事前规定的主档判断。

按审计准入条件，**暂不启动F1-T／F1-G、真实模型配对、REVIEW2、训练或新预算调用**。保留冻结F1与负向结果。共同遗漏已定位到多行赋值的右侧未被事实提取器捕获，而不是单卡装不下。

## 2. 先冻结，再打开材料

读取新轨迹前封存8个候选实现文件及其哈希，主预算固定为2,048，敏感性档为1,024、4,096；单卡768、完整输入98,304、近期5个工具周期、原动作链与来源约束不变。F1仍使用v200原有事件与事实顺序，没有针对本轮事实修改权重、拆分或装填规则。

实际使用v198预留r2的12题、10个仓库。它们与近期上下文调参题单任务级分离，但来自更早的开发／校准池；10个仓库也都在近期开发中出现过。**不能称仓库级隔离或全项目从未曝光。**

每题事前规定两个决策点：至少12个先前工具观察且Agent决策序号不小于12的首点，以及第24个Agent请求。Requests-1766没有第二个满足规则的点，保留一个，因此实际为23点，三条件×三预算＝**207个视图**。未根据结果换题或补造第二点。12题不是23个独立任务，更不是207个独立样本。

A原样使用v199 r4 E3单卡；B使用冻结F1多卡；C为M1-5。A↔B只比较表示机制，B↔C比较整个附加事实管理方案的成本与信息增量，两种差值不混用。

## 3. 来源怎样核实

材料来自原v142 S1实际输入。每份客户端request文件的字节哈希与成员账本一致，内部payload的规范哈希与供应商账本中settled请求一致。来源准入总共检查281个Agent输入；真正进入所选前缀的279个不同请求另核对任务／member_001作用域。没有读取随后模型回答、最终补丁或官方评分作为标注／选择依据。

旧SDK会摘要历史，导致数组位置重新编号；还会将旧观察中的静态字段变成同输入内的引用。本轮用实际tool call ID和此前完整呈现过的观察哈希建立稳定索引，逐条核对静态引用的锚点和原结构。这些是**派生来源索引，不冒称SDK原历史下标**；原wire文本和各次变体均保留，不能按当前位置猜测版本。

旧payload没有context_read。本轮在三组共同输入上加入同一只读历史恢复schema，以便比较统一的可恢复视图；只允许恢复本成员此前实际见过的原文，没有新增仓库或命令权限。这是明确的离线求解接口适配，不宣称原历史Agent当时已拥有这个工具。

另外发现6条不同的旧工具消息是被截断的不完整JSON，跨所选点出现7次。它们是合法API payload中的原始字符串，原请求哈希仍可信；但不能据此补造结构化测试状态。本轮保留原文，未修改旧反馈或冻结F1来重新解释这些结果。

## 4. 标注与主档结果

先按当前可见任务和实际harness状态定义决策问题，再封存标注，最后生成A/B/C视图。同题第二点在第一点标注封存后才审阅，第一点不因后来信息改写。

沿用此前你要求的“自行审阅”：共62条主助手AI参考，其中34条被判为当前明确定义决策所需、12条有用、16条重复结构元数据对照。它们不是人工金标准，也不是穷尽全部必要事实。每项记录真实性、来源、版本、相关性、必要性、互补／版本对照、冗余与恢复边界；标注值不进入选择器。

以下是23个决策输入的合计，token为本地官方分词器估计，**不是本轮实际API usage或完整任务成本**。

{main_table}
34条必要参考中，29条已在共同近期原文中直接可见。A、B各额外提供4条旧历史证据，因此总计33；不能把卡片的4条当成完整上下文只有4条，也不能把M1-5写成0覆盖。动作链及其他未改原文单列核对，此组参考没有新增严格同源计分；关键词碰巧再现不升级为同版本事实。

按任务保留层级后，A、B的任务均衡必要参考覆盖均为97.92%，C为88.19%。主档B对A：12题全部持平；B对C：4题更高、8题持平，没有更低。由于标注为AI开发参考，且题目与仓库有历史曝光，不据此做总体显著性或正式非劣效结论。

16条无关对照在三组均未被额外呈现，但它们主要是固定工作台协议版本等窄类别。其余事实没有全量独立相关性标签，因此**总体Fact Precision及“没有显著增加无关信息”均尚不能成立**。

## 5. 唯一共同遗漏的具体原因

Pylint-4604第一点中，判断type comment是否真正抑制unused-import，需要核对以下旧代码的名称消费条件：

```python
imported_name in self._type_annotation_names
or as_name in self._type_annotation_names
```

原文存在、引用可恢复，但事实提取器只提取了赋值开头：

```python
is_type_annotation_import = (
```

右侧跨行表达式没有被提取；包住它的长代码块又超过既有块提取边界。因此它没有进入单卡或多卡的候选事实目录，增加卡片数量与总预算都无法补救。这是**事实提取完整性限制**，不能说模型已经看到却不会用。

本轮只定位并记录，不在看过留出后修改F1再重测并冒充独立验证。若后续修复多行语句提取，应另立开发修订、通用CPU控制及新的冻结验证材料；当前留出已被打开，不再作为该修订的独立确认。

## 6. 预算、互补和恢复

{sensitivity}
1,024档B比A多1条必要参考，影响1题；主档及4,096档没有必要覆盖差异。B的有用参考覆盖随预算为6/12、8/12、10/12，A始终5/12。不能根据辅助档改换事前主结论。

标注了6组事实互补或版本对照，主档A、B完整呈现5组，C为3组。它们包括Quantity两个dtype分支、类型注释收集与消费、失败计数与网络错误，以及旧版失败与新版未执行状态。**组合完整不证明模型采用，也不证明超加性的效用性质。**

全部62条参考在所有条件与预算下均可从保留原文或可见引用合法恢复。新增52次有界CPU reader调用验证真实页与原文一致；它们不是Agent发起的回读。新Agent回读为0，理解、采用、返工及任务成功均未测量。

## 7. 工程与阶段准入

207/207视图通过来源、版本、权限、单卡和总预算核验，0运行异常。新来源适配器的3项CPU控制覆盖摘要后索引稳定、静态引用真实性及客户端／供应商／任务成员边界。准备后补充显式作用域拒绝检查，所有实际使用的279个请求通过，不需要重跑候选算法。

本次四路低优先级CPU视图运行约{data['wall_seconds']:.2f}秒墙钟、{data['worker_CPU_seconds']:.2f}秒累计worker CPU，单worker峰值约{data['max_worker_RSS_KiB']/1024:.1f}MiB。时长包含读取与本地分词，不能据缓存顺序比较各组速度。没有新被测API、Docker、GPU、训练或共享主机配置修改；旧现金账本未动。AI工程审阅平台成本无法单独取得，不报告为全部模型劳动成本为0。

工程准入通过，但事前“B在新任务上优于A，并能控制额外无关信息”的推进门**未通过**：主档必要覆盖相同，整体无关信息指标仍缺独立全量标签。当前不进入F1-T／F1-G，也不启动真实M1-5↔F1配对。

## 8. 下一批材料与研究路线

另按固定哈希顺序预留12题、10仓库，排除登记的近期调参清单及本轮12题；只保留instance_id、repo、base_commit，未打开其轨迹或评分。这只是**题目身份预留，不是可运行材料准备完成**。

本地Verified池有500题、12仓库，而这12个仓库都出现在当前方法开发中。因此在该池内无法建立仓库级隔离；真正新仓库的合格历史前缀目前为0。需要引入另一个明确来源或新采集前缀才能满足这一更强边界，不能把重新抽题当成新仓库确认。

未来重点是修复源事实提取、扩充任务条件下的标注，再验证信息如何影响决策，而不是继续调F2权重或扩大图传播。图继续承担身份、来源、版本及权限维护；任务阶段、角色职责、真实handoff／adoption和信息视图的联动仍是后续目标，本轮没有宣称实现协同进化。

## 9. 文件

- [标注规范与逐项结果](software-benchmark-v201-annotation-and-evidence.md)
- [完整指标与逐题比较](../../artifacts/software-benchmark-v201/metrics-r1/summary.json)
- [冻结协议](../../artifacts/software-benchmark-v201/protocol-r1/plan.json)、[来源准入](../../artifacts/software-benchmark-v201/source-admission-r1/summary.json)
- [推进门决定](../../artifacts/software-benchmark-v201/admission-r1/decision.json)、[多行赋值遗漏](../../artifacts/software-benchmark-v201/omission-analysis-r1/summary.json)
- [隔离审计](../../artifacts/software-benchmark-v201/isolation-audit-r1/summary.json)、[后续身份预留](../../artifacts/software-benchmark-v201/prospective-identities-r1/manifest.json)
'''
    items=[]
    details={(r['point'],r['condition']):{f['reference']:f for f in r['facts']} for r in metrics['details'] if r['budget']==2048}
    for p in source['points']:
        ann=read(BASE/'annotations-r1'/f"{p['point']}.json")
        for f in ann['reference_facts']:
            items.append([f['id'],f['relevance'],f['version_validity'],str(f['value'])[:230],*[('是' if details[p['point'],c][f['id']]['direct_union'] else '否') for c in names],f['rationale']])
    taskrows=[]
    for task in source['tasks']:
        stats={c:next(t for t in lookup[c,2048]['per_task'] if t['instance_id']==task['instance_id']) for c in names}
        taskrows.append([task['instance_id'],len(task['points']),*[f"{stats[c]['necessary_direct']}/{stats[c]['necessary_total']}" for c in names],*[stats[c]['input_tokens_estimate'] for c in names]])
    annotation=f'''# v201：事实标注规范与逐项证据

对应[实验报告](software-benchmark-v201-frozen-f1-holdout-report.md)，2026-11-12。适用于单个真实输入边界，禁止使用该请求之后的模型回答、未来测试或终局评分反推必要性。

## 1. 八个维度

| 维度 | 核验内容 | 不允许的替代判断 |
| --- | --- | --- |
| Factuality | 值或片段确实存在于当时真实输入 | 模型摘要自我证明、未读源码补全 |
| Provenance | request身份、消息哈希、作用域、JSON路径和字符区间 | 仅文件名相同或关键词出现 |
| Version Validity | 原执行／文件版本，以及当前、历史、未知边界 | 旧通过继承为新版本通过 |
| Task Relevance | 对明确定义的当前决策是否有帮助 | 所在事件Useful就给所有Fact同标签 |
| Necessity | 当前决策所需、可由替代证据满足或未知 | 把有用背景全部升级为必要 |
| Complementarity | 哪些事实应同时考虑，关系证据和范围是什么 | 共现就当因果或效用超加性已成立 |
| Redundancy | 是否被当前窗口／动作／等价同版本证据提供 | 不同执行或不同版本相似文本直接合并 |
| Recoverability | 当前视图有合法引用且可按页恢复原文 | 后台磁盘有记录就认为Agent可取得 |

本轮`necessary`是主AI对所声明决策的开发判断，非全任务所有正确路径的数学必要性。不能以事实匹配程序代替相关性和必要性审阅。`useful`表示相关但未认定不可替代；`irrelevant`对照主要为重复工作台协议版本，不覆盖全部噪声类别。未标注事实保持未知。

后续人工审阅应由两位审阅者分别冻结标注，隐藏方法输出、历史分数与另一人的判断，再由第三方处理分歧。保留初稿与理由，报告一致性和不确定性；没有做到时只能称AI开发参考。既有“自行审阅”安排不等于已经完成人工步骤。

## 2. 本轮逐题结果（主档2048）

{table(['任务','点数','A必要','B必要','C必要','A输入估计','B输入估计','C输入估计'],taskrows)}
先按任务聚合事实再算宏平均；23个点没有作为23个独立任务。输入合计因Requests只有1点，不能未经加权作为任务平均成本。

## 3. 62项参考及默认呈现

{table(['编号','标签','版本','原值／片段（显示截短）','A','B','C','判断理由'],items)}
表中长文字为了阅读截短，完整值、source_id、消息哈希、派生索引、pointer和span在`artifacts/software-benchmark-v201/annotations-r1/Hxx-x.json`。这些标签在207个视图生成前已封存，运行器只读取其文件哈希，不读取标注值。

## 4. 可复现来源与运行

来源映射使用真实tool call ID及原已见观察的内容哈希。对`_v117_same_input_static_fields`只从同次真实输入锚点复核，再与此前完整输入的严格JSON结构比对；未将重建内容伪装成新的模型观察。派生索引可跨SDK摘要保持身份，实际source_id仍包含每次真实消息哈希。

```bash
LITELLM_LOCAL_MODEL_COST_MAP=True OPENHANDS_SUPPRESS_BANNER=1 .venv/bin/python tools/run_offline_scorer_v096.py tools/prepare_fact_holdout_v201.py
LITELLM_LOCAL_MODEL_COST_MAP=True OPENHANDS_SUPPRESS_BANNER=1 .venv/bin/python tools/run_offline_scorer_v096.py tools/run_fact_holdout_v201.py
.venv/bin/python tools/score_fact_holdout_v201.py
.venv/bin/python -m pytest -q tests/test_history_source_v201.py
```

完成目录拒绝覆盖；不应为刷新分数重新运行或改标签。实际raw wire、common frame、source witness与静态锚点链在`runs/software-benchmark-v201/source-prefix-r1/`，counterfactual视图与reader entries在`runs/software-benchmark-v201/offline-r1/`。同题两个决策点不是两次独立运行；全部来自封存历史。

首批人工录入配方中H10-1的来源索引10没有result字段，写入前被拒绝，改为实际代码来源11后才封存；已封存的其他前缀未重写。原配方与后续补齐配方均保留，这不是模型失败或重采。

源适配器：[software_history_source_v201.py](../../src/proworksim/software_history_source_v201.py)；准备／标注／对照／统计：[准备](../../tools/prepare_fact_holdout_v201.py)、[标注封存](../../tools/annotate_fact_holdout_v201.py)、[运行](../../tools/run_fact_holdout_v201.py)、[统计](../../tools/score_fact_holdout_v201.py)。

## 5. 尚未启动的阶段

F1-T需要由真实harness状态与动作确定工作阶段，不能把模型一句“已修好”当验证状态。F1-G只能使用已确认依赖，不为获益提升Inferred。两者的启动条件仍是本轮主档推进门通过，本轮未满足。

真实单Agent比较应保留M1-5与冻结F1-2048，同题、独立工作区和相同总预算；统计模型实际读回、版本／片段正确性、工具行动与事实的可核查关联、代码与交付双端点和完整费用。关键词提及或时间先后都不能单独证明事实因果作用。

24题×两条件、每回合5M以及重复诊断仅为后续设计上限，没有本轮模型调用或预算授权。本轮不自动申请旧余额、不启动训练或REVIEW2。组织—通信—上下文协同仍需经真实成员、职责、交接、采用和测试回执逐层验证。
'''
    (DOC/'software-benchmark-v201-frozen-f1-holdout-report.md').write_text(report)
    (DOC/'software-benchmark-v201-annotation-and-evidence.md').write_text(annotation)
    print('v201 report and annotation protocol written')
if __name__=='__main__':main()
