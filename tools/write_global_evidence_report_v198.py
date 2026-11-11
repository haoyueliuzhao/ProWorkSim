"""Render v198 development results without changing source labels or methods."""
import json,csv
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'artifacts/software-benchmark-v198'
def read(p):return json.loads(p.read_bytes())
def percent(x):return '—' if x is None else f'{x*100:.2f}%'
def main():
    result=read(BASE/'development-r1/summary.json');score=read(BASE/'development-score-r1/summary.json');mapping=read(BASE/'annotation-binding-r1/summary.json')
    fidelity=read(BASE/'engineering-review-r1/default-card-fidelity.json');groups={(g['condition'],g['budget']):g for g in score['groups']}
    rows=score['groups'];names=['condition','budget','old_essential_selected','old_essential_denominator','input_tokens_estimate_sum','cards','new_unlabelled_selected','precision_lower','precision_upper','coverage_infeasible_points']
    with (BASE/'development-score-r1/quality-cost.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=names,lineterminator='\n');w.writeheader();w.writerows({k:r[k] for k in names} for r in rows)
    gate={'version':'v198-development-admission-r1','user_amendment':'你自行审阅','review_mode':'primary-assistant AI engineering review',
        'human_gold_standard_claimed':False,'engineering_CPU_controls_passed':15,'old_necessary_events_reviewed':8,
        'useful_and_irrelevant_spot_reviews':24,'necessary_relations_processed':123,'unmapped_records_preserved':True,
        'open_world_source_sample_reviewed':12,'development_views_verified':720,'source_scope_or_version_errors':0,
        'scientific_graph_increment_supported':False,'default_card_fact_coverage_complete':False,
        'independent_task_evaluation':'not_started; r2 holdout identity reservation only',
        'tested_model_runtime':'not_started','new_API_cost_CNY':0,'new_Docker_objects':0,'new_GPU_use':0,'new_training':False,
        'completion_scope':'P0 AI engineering review and P1 offline development preparation complete under user amendment; no independent confirmation claim'}
    p=BASE/'p0-admission-r1/decision.json';p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(gate,ensure_ascii=False,indent=2)+'\n')
    text=['# 全局证据发现与实体绑定开发报告','',
        '**本轮缓解了路径筛选导致的事件漏选，但没有证明图关系带来增量收益，也没有解决默认卡片的全部内容遗漏。** 全局检索G2选中了旧参考集8/8项必要事件；直接检查卡片后，只有3项呈现了本次指定的关键事实探针，其余5项仍需回读原文。G3没有增加必要事件，也没有节省输入。',
        '', '本轮为v198的P0工程复核和P1离线开发。根据你“你自行审阅”的回复，由主助手完成AI工程复核，不冒充人工专家或新的独立盲审。旧48点、旧AI标签和旧结果均保留；没有启动新的被测API、容器、GPU、训练或真实修复任务。',
        '', '## 1 本轮具体修改','',
        '1. **全局候选发现。** 保留全部旧候选，并增加此前未建模的搜索、状态、笔记等已见观察。路径只加相关性分，不再决定候选资格。只读成员当时合法看到的材料，不读取完整隐藏仓库或未来反馈。',
        '2. **先保留明确的验证限制。** G2至G4先保护每个精确测试选择器最近一次未成功、且没有被后来同选择器成功替代的执行记录，再分配剩余预算。它是可核查的“验证状态提示”规则，不是对语义必要性的预测，也不表示当前代码仍有同一个缺陷。',
        '3. **取消8卡硬截断。** 五组共同受附加Token和单卡上限约束，G1至G4没有8卡硬上限；覆盖无法满足时显式记录未覆盖项。G1沿用K-v2的类型／时间排序，但候选和渲染采用本轮共同实现，不能冒充完全复跑旧K-v2。',
        '4. **稳定实体与来源链。** 区分Repository、Commit、私有Version、File、Symbol、TestDefinition、TestRun、Artifact、Observation和Task。ID包含真实基线commit与私有工作区版本，编辑后的版本不冒充Git commit。完整同版本片段可拼接解析；片段缺口、冲突或无法建立限定名时保留Reference。',
        '', '## 2 AI工程复核发现','',
        '8项必要旧事件的源事实均已逐项查看，并对照其近期窗口。原标签不修改，尤其不根据本轮算法选中了哪些项来修改标签。这里确认的是来源内容和解释边界，不是证明这些信息在所有修复路径上都不可替代。',
        '', '| 决策点 | 复核后的准确表述 |', '| --- | --- |',
        '| SymPy P007 | 原记录为185通过、2异常，堆栈显示弃用警告触发异常；不能写成两个代码断言失败，也不能当作v10的测试结果 |',
        '| Requests P018 | 旧源码确实区分非ASCII的IDNA路径与ASCII星号检查；它是定位参考，不是当前v3文件的完整重新读取 |',
        '| Sphinx P024 | 当前v7 full套件130失败的计数可信；头页没有给出全部原因，不能归因为本题新增130个缺陷 |',
        '| Scikit-learn P040 | 已见测试覆盖active estimators及KNN拒绝，片段没有None estimator组合；2项通过不证明目标组合覆盖 |',
        '| Astropy P041 | 递归与运算符表在已见代码中存在；这是静态分派证据，不是运行时调用或根因验证 |',
        '| Seaborn P046 | 实际刻度输出可信，但自写测试硬要求3个刻度、以字符长度判断大数显示均有局限 |',
        '| Seaborn P047 | 探针故意assert False；ScalarFormatter和1e6日志有价值，失败计数不是另一个软件缺陷 |',
        '| Seaborn P048 | 同版本full的6失败与较新子集2失败必须分开，子集不能替代full结论 |','',
        '另按固定种子抽查12项Useful和12项Irrelevant，保留原分类、记录来源与重复／版本限制。这是AI抽查，不升级为独立语义验收。一个系统性边界更加明确：**旧标签评价的是事件原文，而算法默认给出的是卡片；选中事件不能直接计作完整事实已经送达。**',
        '', '## 3 开放世界检查','',
        '48点原有617次候选出现扩为1835次，旧候选全部保留。新增1218次中，状态976、搜索224、其他工具9、笔记9；跨点去重后为522个新增事件。它们是历史观察和候选出现，不是新增任务数。',
        '', '随机抽查12个新来源，9个为状态记录、3个为搜索记录，保留字段均可回溯实际消息。搜索反馈确实是原候选建模的一处缺口，但大量状态记录也可能重复或过期；来源真实不等于应默认呈现。新候选没有被强行填成Useful或Irrelevant，仍单列未标注。',
        '', '这是开放来源类型检查，不能证明所有必要证据已被发现。反复出现的状态字段、长文本中的后段、未读页面和当前索引不能解析的关系，仍需要分别评价；未读材料不会被偷偷补入。',
        '', '## 4 实体与123条关系的处理结果','',
        '| 处理层次 | 结果 |','| --- | ---: |',
        '| 关系标注逐条登记 | 123/123 |',
        '| 246个端点成功绑定 | 54 |',
        '| 端点存在歧义 | 3 |',
        '| 当前解析器未绑定的端点 | 189 |',
        '| 两端及直接来源关系均可核对 | 8条，均为测试执行与版本关系 |',
        '| 仅两端绑定，关系未证实 | 1条 |',
        '| 关系仍未完成映射 | 114条 |','',
        '成功端点包括25个Version、19个TestRun、8个Symbol和2个File。未绑定记录有稳定的Reference编号和原因，但**Reference编号不计作解析成功**；未绑定也不证明原始材料里不存在该实体，可能是限定名、别名、片段、来源类型或当前解析器覆盖不足。当前完整定义解析主要支持read_file材料，不能声称已穷尽所有成功写入动作中的完整代码。',
        '', '跨48个快照去重后，6个文件版本取得完整可解析文本，产生57个限定名与签名明确的Symbol。60个TestRun与26个测试身份分开；后者不都意味着已见完整测试函数体。静态跨文件解析只得到1条Inferred候选，没有把名称匹配升级成Confirmed运行时调用。',
        '', '每条关系记录端点、原消息、范围、基线commit、私有版本、可见步骤、适用性和证明种类。测试通过只绑定其原版本和选定范围；历史记录仍可回读，但不继承为新版本通过。',
        '', '## 5 五组离线开发结果','',
        'G0为M1-5；G1为事件类型／时间排序；G2为全局词项检索加验证限制覆盖；G3在G2上加Confirmed实体／证据关系；G4再允许明确标记的Inferred扩展。五组用同一扩展候选池、原文权限、近期窗口、渲染和Token上限。',
        '', '主档为4096附加Token。下面“8项召回”只复用旧AI参考标签，衡量事件是否被选中，不是新的独立效果验证。新增候选没有标签，所以精确率给缺失标签上下界，不能把它们当作确定错误或确定正确。',
        '', '| 条件 | 旧必要事件选中 | 输入Token估计合计 | 卡片数 | 新候选未标注呈现 | 精确率范围 |','| --- | ---: | ---: | ---: | ---: | ---: |']
    for c in ['G0','G1','G2','G3','G4']:
        g=groups[c,4096];bounds='—' if g['precision_lower'] is None else percent(g['precision_lower'])+'–'+percent(g['precision_upper'])
        text.append(f'| {c} | {g["old_essential_selected"]}/8 | {g["input_tokens_estimate_sum"]:,} | {g["cards"]} | {g["new_unlabelled_selected"]} | {bounds} |')
    text += ['', 'G2相对本轮G1增加1项旧必要事件，输入仅多1162个本地估计Token。相对M1-5，G2输入多约7.89%；不能只报告8/8而忽略成本。由于候选、摘录与卡片数量规则都已变化，不能把这一总差直接归因为某一个检索模块。',
        '', 'G3相对G2只改变2/48份实际输入，没有增加旧必要事件，输入反而多12 Token，旧标签中的不相关卡多1项。内部排序列表在12点改变，但多数不改变最终输入，不能把12点都算作信息增益。G4与G3的实际输入完全相同。**当前仍没有证据支持图关系优于全局检索。**',
        '', '| 附加上限 | G1事件召回 | G2／G3／G4事件召回 | G2至G4覆盖未满足 |','| --- | ---: | ---: | --- |',
        '| 1024 | 5/8 | 7/8 | 各1点、1项验证提示未覆盖，已显式记录 |',
        '| 2048 | 7/8 | 8/8 | 0 |',
        '| 4096 | 7/8 | 8/8 | 0 |','',
        '完整[质量成本CSV](../../artifacts/software-benchmark-v198/development-score-r1/quality-cost.csv)同时保留新候选未标注比例。这里的Token是同一历史前缀的本地配方估计，不是新供应商usage或任务完整运行成本。',
        '', '## 6 8项事件被选中仍不等于8项关键内容被呈现','',
        '对G2主档卡片又做了明确标为探索性的字面事实检查：Sphinx全套130失败、Seaborn实际刻度输出与另一点全套6失败，共3项通过；其余5项缺少本次指定的关键片段。',
        '', '| 卡片 | 未直接呈现的关键内容 |','| --- | --- |',
        '| SymPy P007 | DeprecationWarning异常性质 |',
        '| Requests P018 | ASCII／非ASCII控制分支的具体代码 |',
        '| Scikit-learn P040 | 实际断言与KNN拒绝逻辑 |',
        '| Astropy P041 | _separable递归和_operators分派 |',
        '| Seaborn P047 | ScalarFormatter与1e6等诊断值 |','',
        '原因是代码默认摘录按首个词项命中取有限窗口，而旧测试卡也没有自动保留全部日志值。原文引用仍完整可用，但本轮没有真实Agent调用来证明它会主动回读。3/8是这组卡片的字面探针结果，不是整个输入的信息召回率，也不是任务成功率；近期窗口或保留动作可能另外包含同类信息。',
        '', '这说明下一步应优先对齐“必要事实的来源片段”和“实际呈现内容”，并处理状态重复，而不是为了提高事件召回数字继续加卡。此次未依据该检查修改权重再反复挑最优结果。',
        '', '## 7 留出材料与验证状态','',
        '已预留12道任务、覆盖10个仓库，与v175选定点、v181和v193的上下文开发任务隔离。只登记公开身份、仓库和基线commit，没有打开留出轨迹或评分。这些题来自更早的开发／校准池，不能称为整个研究历史都未暴露的独立确认集。',
        '', '原预留清单中Sphinx-8593的问题文本开头曾在检查源文件结构时打印，因此在任何留出评估前按固定哈希顺序替换为Sphinx-9698。原r1保留，规范清单为[留出r2](../../artifacts/software-benchmark-v198/holdout-reservation-r2/manifest.json)。没有因模型成绩换题。',
        '', f'15项CPU控制通过，覆盖片段拼接、版本隔离、限定名、未解析引用、测试身份、全局候选一致、超过8项失败提示、预算不足显式报告、来源范围、未执行报告不构成验证及快照不变。720份视图均通过来源、版本、权限和容量检查。开发计算约{result["wall_seconds"]:.2f}秒墙钟、{result["CPU_seconds"]:.2f}秒CPU，峰值RSS约{result["peak_RSS_KiB"]/1024:.1f}MiB；其中实体构建累计约{sum(x["registry_construction_CPU_seconds"] for x in result["inventories"]):.2f}秒。',
        '', '完成开发计算后增加了输入快照的外来／未来／篡改来源拒绝，以及未执行报告不得建立validates关系或进入实际失败保护集的控制。原历史60个可见TestRun均已有实际执行证据，所以该修订没有排除本轮记录。实验使用的原源码另行封存，新增控制通过CPU回归；没有重跑模型或改写已完成的视图。CPU与Token分别计量，不构造未经验证的统一费用。',
        '', '## 8 本轮结论','',
        '**完成了授权范围内的AI工程复核、实体索引、全局发现原型与离线开发比较；尚未通过信息有效性和图增量的科学准入。** 当前更明确的瓶颈是默认摘录没有保住部分关键事实、新增状态候选重复较多，以及引用到真实代码实体的解析覆盖不足。',
        '', '后续应先固定必要事实的源片段与输出级指标，验证默认呈现或真实回读是否传递了这些事实，再对任务级留出材料做一次冻结评估。若Confirmed扩展仍不能改善全局检索的质量成本关系，就停止增加图关系查询复杂度。真实单Agent、REVIEW2、组织与通信联合优化均未在本轮启动。',
        '', '## 9 复核文件','',
        '- [AI逐项复核](../../artifacts/software-benchmark-v198/engineering-review-r1/eight-review.json)、[原始证据包](../../artifacts/software-benchmark-v198/engineering-review-r1/eight-source-packet.json)、[卡片事实检查](../../artifacts/software-benchmark-v198/engineering-review-r1/default-card-fidelity.json)。',
        '- [123条关系映射](../../artifacts/software-benchmark-v198/annotation-binding-r1/summary.json)、[开放来源抽查](../../artifacts/software-benchmark-v198/open-world-review-r1/ai-source-review.json)。',
        '- [完整开发统计](../../artifacts/software-benchmark-v198/development-score-r1/summary.json)、[运行与成本](../../artifacts/software-benchmark-v198/development-r1/summary.json)、[准入记录](../../artifacts/software-benchmark-v198/p0-admission-r1/decision.json)。',
        '- [实现与复现实验说明](software-benchmark-v198-global-evidence-design.md)。','']
    (ROOT/'docs/experiments/software-benchmark-v198-global-evidence-report.md').write_text('\n'.join(text))
    print('v198 report written')
if __name__=='__main__':main()
