"""Render the v193 report from the frozen, independently recomputed tables."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'artifacts/software-benchmark-v195/context-report-r1'
DOC=ROOT/'docs/experiments'


def read(name):return json.loads((DATA/name).read_bytes())
def table(headers,rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |',
                      *['| '+' | '.join(map(str,row))+' |' for row in rows]])
def outcome(value):return '通过' if value else '未通过'


def main():
    s=read('summary.json');m=read('mechanism-audit.json');episodes=read('episodes.json');tasks=read('primary-tasks.json');repeats=read('repeat-pairs.json')
    g=s['primary'];groups=tuple(g);baseline=g['M0']['usage']['total_tokens']
    assert [g[x]['code_pass'] for x in groups]==[9,10,9,10]
    assert [g[x]['delivery_pass'] for x in groups]==[9,10,8,10]
    assert sum(r['usage']['total_tokens'] for r in episodes)==s['all_usage']['total_tokens']==131189824
    assert len(episodes)==60 and len(tasks)==12 and len(repeats)==12
    main_table=table(['条件','代码正确率','合法交付率','平均总Token','相对M0','主测费用上界'],[
        [x,f"{g[x]['code_pass']}/12（{g[x]['code_pass']/12:.1%}）",f"{g[x]['delivery_pass']}/12（{g[x]['delivery_pass']/12:.1%}）",
         f"{g[x]['mean_total_tokens']/10000:.2f}万",'—' if x=='M0' else f"{g[x]['usage']['total_tokens']/baseline-1:+.2%}",
         f"{g[x]['usage']['cost_nanoyuan']/1e9:.2f}元"] for x in groups])
    work_table=table(['条件','Agent请求数','平均每次Agent输入','记录的动作数','公开测试执行／同身份重复'],[
        [x,g[x]['usage_by_purpose']['agent']['requests'],f"{g[x]['mean_agent_input_per_request']/10000:.2f}万",
         sum(r['world_actions'] for r in episodes if r['primary_panel'] and r['group_id']==x),
         f"{g[x]['public_tests']['executed']}／{g[x]['public_tests']['exact_repeats']}"] for x in groups])
    repeat_table=table(['条件','预选6题首轮／重复通过','0/2成功','1/2成功','2/2成功','逐题结果翻转'],[
        [x,'4/6 → 4/6',*[s['repeat'][x]['two_run_code_distribution'].get(k,0) for k in ('0/2','1/2','2/2')],f"{s['repeat'][x]['code_flips']}/6"] for x in ('M0','M1-10')])
    report=f'''# 关键事件上下文管理实验报告

本轮为v191离线审计、v193正式运行及v194运行保障后的完整报告。四组均使用**项目S1受管OpenHands单Agent**，比较的是历史信息的保留方式。

**主要结论：本轮面板上，M1-5取得最好的成本与完成率组合；M1-5K的关键卡片确实运行，但尚未显示相对M1-5的额外收益。** M1-5与M1-5K均通过10/12题、合法交付10/12题，后者多消耗42.84%的Token，而且存在可复现的重复卡片与信息粒度不足问题。这个结论限于本轮12题，不是通用优越性或非劣效认证。

## 1. 实验设置

12题分别来自SWE-bench Verified的12个仓库。每题四条件各运行一次，共48个主回合；事前选定6题，在M0和M1-10下各额外运行一次，共12个重复回合。**60/60均完成生成和评分，技术未知、未启动、未结算API请求均为0。** 主测只统计第一次预定运行，重复结果单独报告。

| 条件 | 模型每次能看到怎样的历史 |
| --- | --- |
| M0 | 沿用原有OpenHands历史摘要机制；它不是无限保留全部原文 |
| M1-5 | 保留最近5轮完整观察；较早观察换成可回读引用，动作链保留 |
| M1-10 | 同上，但完整观察窗口为最近10轮 |
| M1-5K | 最近5轮加历史关键事件卡；以确定性规则保留版本、测试、错误等信息 |

共同配置为DeepSeek Flash非思考、temperature=1、top_p=1，每回合最多5M实际输入＋输出Token，总上下文131,072、输入上限98,304、输出上限32,768；工具、权限、同版本测试与正式提交规则相同。K不调用额外摘要模型。四组也共同使用修复后的测试短页头，完整公开报告仍可按页读取。

题单排除了上一轮v181的12题；Flask和Seaborn仍与离线原型材料重合，且整个Verified池更早已有开发曝光。因此本轮是**分层历史开发面板上的机制筛选**，不是完整500题成绩或独立确认集。题单与seed见[冻结方案](../../artifacts/software-benchmark-v191/full-task-design-r1/plan.json)。

## 2. 主测结果

平均总Token包括输入、输出和实际摘要调用；费用按冻结峰值费率及实际缓存usage计算，是计价上界而非供应商发票。

{main_table}

M1-5保留了M0全部9个成功任务，并新增通过Sphinx-8721。M1-5K也保留了M0全部9个成功任务，但新增通过的是SymPy-13091。**M1-5K与M1-5各有一题独有成功，净通过数相同。** M1-10新增通过Sphinx，却失去Pylint-6903，并有一题代码正确但未合法交付。

每题对应8.33个百分点。不能把一题差异当作已稳定验证的优势，也不能将本轮与v190直接相减：两轮题目不同，本轮还统一修改了公开测试反馈。

## 3. Token差异主要在哪里

{work_table}

M1-5相对M0，Agent请求数只减少6.19%，平均每次Agent输入却减少39.29%；总Token下降43.27%。其节省主要表现为每次请求携带的历史更短。M0另有25次摘要请求，直接消耗17.63万Token，仅占该组主测总量0.57%，所以差异不能主要解释为省掉了摘要器调用费。

M1-5K相对M1-5多消耗**746.76万Token**：Agent请求由500增至647，增加29.4%；平均每次输入由3.47万增至3.83万，增加10.44%。读取文件、回读测试报告及修改代码的选择次数也更多。它执行67次公开测试，比M1-5多6次，但同版本、同命令、同选择器及同环境的精确重复只有1次，少于M1-5的4次；不能把多出的工作统称为重复测试浪费。

关键卡片文本累计约94.17万本地估计Token，占K组实际输入约3.80%；相对原引用标记的净增加约84.93万。这个量只相当于两组实际总Token差的约11.37%，而且是局部Tokenizer估计，不能当作供应商账单的精确成本分解。**额外成本更多表现为工作轨迹和请求输入的变化，不能只用“多了几张卡”解释。** 是否由某种卡片导致这些行为变化，仍需单项消融。

## 4. 关键事件保护生效了，但还存在什么问题

实际485个请求携带了关键卡片，共2573次呈现、165个不同来源。所有呈现的保留字段均与模型此前实际见过的消息匹配；没有用参考补丁或评分向模型补充信息。

不过，以下问题仍然存在：

1. **同一测试报告重复入卡。** 169个请求同时保留了执行与回读形成的卡片，多出289次完全相同字段的呈现。原因是`run_tests`按测试选择器归类，而`read_test_result`退回使用报告ID，两条路径没有合并为同一测试证据。
2. **保护的主要是元数据。** 54张不同失败测试卡都保留了版本、哈希、通过状态、计数和报告ID，但没有失败测试名称、命令或错误片段；54张代码变化卡也没有路径／diff字段。相关信息仍可能在动作链和原文中，不能据此说整个上下文完全丢失了它们，但卡片本身未充分满足“保留可行动关键诊断”的目标。
3. **自然回读仍未发生。** 全60回合没有一次`context_read`选择。卡片附带引用、原文可以恢复，并不等于模型实际使用了恢复机制。另有1183次候选卡片因卡片数量／总预算约束回退，包含同一事件被重复考虑，不是1183条独立信息丢失。

因此，本轮验证了卡片的实际呈现与字段来源可信性，**没有验证其语义选择已足够有效，也没有证明理解或采用这些卡片提高了完成率**。详细证据见[机制审计](../../artifacts/software-benchmark-v195/context-report-r1/mechanism-audit.json)。

## 5. 重复波动、预算与失败原因

{repeat_table}

M1-10的SymPy从失败翻为成功，Requests从成功翻为失败，虽然两轮总体都是4/6。相同总体分数不代表逐题稳定；M0的6题没有翻转，也只是一轮有限诊断。M1-5和M1-5K未设置重复，不能据此宣称其波动更小。

主测中**7/48回合（14.58%）触及5M下一请求预约门**：5个最终代码失败；M0的Matplotlib仍有正确代码和合法交付；M1-10的Requests则代码正确、没有合法交付。其余5个代码失败在没有预算截止的情况下结束。预算边界有影响，但不能解释全部失败；本轮60回合均没有上下文容量终止。

主要差异可以定位到具体轨迹：

| 任务 | 实际观察 | 能支持的解释 |
| --- | --- | --- |
| SymPy-13091 | K首轮通过，另外三组首轮失败；K对比较分派的修改更完整，耗费499.33万Token。M1-10重复轮也通过 | 实现覆盖及生成波动都重要，不能认定K卡片是成功的必要原因 |
| Sphinx-8721 | M1-5／M1-10在页面生成入口增加判断后通过；K扩大改动范围、引入额外回归，最终预算截止 | 代码修复路径偏离和返工可直接观察，不能只归因于卡片长度 |
| Pylint-6903 | M1-10只修改最终fallback，遗漏CPU配额分支，14次请求即结束 | 属于不完整修复，不是5M不足的实例 |
| Seaborn-3187 | 四组都预算截止且未通过；M1-5修好一条图例路径，仍未通过relational路径测试 | 部分修复、复现／测试覆盖和预算共同存在，增额是否足以修好尚未验证 |

**Requests-5414还暴露了公共测试环境问题。** 四组共14次公开测试返回出现httpbin夹具递归；M1-10还遇到`trustme`、`mocker`缺失及隔离网络限制。这说明评分环境gold／empty合格，不代表求解侧所有公开测试依赖都准备完整。

M1-10在该题的具体闭合链是：v17自写回归4项通过→删除临时测试形成v18→v18公开测试25项通过但3项夹具错误→成功固定v18补丁→累计496.29万Token后无法预约下一请求，尚未调用正式提交。最终代码官方评分通过。因此，交付缺口与**环境绕行、版本闭合步骤和预算**都相关，不能仅写成“忘了提交”，也不能声称再给一次调用就必然成功。[详细轨迹与边界](software-benchmark-v195-critical-context-appendix.md)

## 6. 全批成本、执行与可信度

48个主回合累计100,095,498 Token、170.54元计费上界；12个重复累计31,094,326 Token、54.46元。合计**131,189,824输入＋输出Token，225.00235088元**，低于300元额度，剩约75元。累计Token中99.58%是输入；缓存命中是输入的子集，未重复相加。

2843次真实HTTP请求全部结算。逐条核对了实际payload哈希、原始响应、usage和缓存字段，均匹配账本；返回model与fingerprint一致，但API别名不能视为可固定的发布权重。来源清单仍报告约0.14%的未归因语义字节；这是字节口径，本报告未将它冒充供应商逐Token精确归因。

本批于11月11日04:36结束。v193部署总墙钟约9小时12分钟，包含环境准备、生成、评分和等待。账本最长无HTTP窗口为77.28分钟，期间确认发生磁盘等待；原队列在共享空间恢复后继续，没有重采。项目随后完成历史快照无损归档，净回收116.73 GiB，不能把共享盘全部空闲增量或最初恢复都归因于该归档。资源已经释放。

## 7. 后续建议

当前优先保留M1-5作为低成本基线；M1-5K先修机制，再判断是否值得扩大。建议依次处理：**统一测试卡片去重身份；从已经可见的公开反馈中保留可行动诊断；补齐Requests公开测试夹具并建立求解侧准入检查；再做小规模自然回读与闭合验证。** 每项单独留痕和对照，不同时扩窗、增额、改路由后把提升全部归给关键事件保护。

本报告仅读取已封存记录，未启动新的模型、容器或评分。完整逐题结果、重复对照和测量说明见[附录](software-benchmark-v195-critical-context-appendix.md)；复算数据见[统计汇总](../../artifacts/software-benchmark-v195/context-report-r1/summary.json)、[主测CSV](../../artifacts/software-benchmark-v195/context-report-r1/primary-tasks.csv)、[全部回合CSV](../../artifacts/software-benchmark-v195/context-report-r1/episodes.csv)。
'''
    (DOC/'software-benchmark-v195-critical-context-report.md').write_text(report)
    task_table=table(['任务','M0','M1-5','M1-10','M1-5K'],[
        [r['instance_id'],*[('✓' if r[x] else '×')+('（未交付）' if r[x] and not r[x+'_delivery'] else '') for x in groups]] for r in tasks])
    byrepeat={}
    for r in repeats:byrepeat.setdefault(r['instance_id'],{})[r['group_id']]=r
    repeat_detail=table(['任务','M0代码首轮→重复','M0 Token首轮→重复','M1-10代码首轮→重复','M1-10 Token首轮→重复'],[
        [task,*[cell for x in ('M0','M1-10') for cell in
        (outcome(v[x]['first_code'])+'→'+outcome(v[x]['repeat_code']),f"{v[x]['first_tokens']/10000:.2f}万→{v[x]['repeat_tokens']/10000:.2f}万")]]
        for task,v in byrepeat.items()])
    efficiency=table(['条件','主测累计输入','累计输出','摘要输入＋输出','公开测试墙钟合计','首末API跨度均值','每次合法交付总Token成本'],[
        [x,f"{g[x]['usage']['input_tokens']:,}",f"{g[x]['usage']['output_tokens']:,}",f"{g[x]['usage_by_purpose']['condenser']['total_tokens']:,}",
         f"{g[x]['public_tests']['wall_seconds']:.2f}秒",f"{g[x]['mean_API_span_seconds']/60:.2f}分钟",f"{g[x]['total_tokens_per_legal_delivery']/10000:.2f}万"] for x in groups])
    budget=[r for r in episodes if r['primary_panel'] and r['end_class']=='token_budget']
    budget_table=table(['回合','条件／任务','实际Token','代码／交付'],[
        [r['slot_index'],r['group_id']+' / '+r['instance_id'],f"{r['usage']['total_tokens']:,}",outcome(r['code'])+'／'+outcome(r['delivery'])] for r in budget])
    labels={'diagnostic_error':'工具错误','code_change':'代码／版本信息','test_result':'一般测试结果','delivery':'发布／交付','test_failure':'失败测试'}
    category=table(['卡片类别','不同来源数','累计呈现次数'],[[labels[k],m['unique_source_categories'][k],g['M1-5K']['critical_categories'][k]] for k in m['unique_source_categories']])
    append=f'''# 关键事件上下文管理实验：数据与技术附录

本页补充[主报告](software-benchmark-v195-critical-context-report.md)，保留逐题结果与统计边界。正式任务均为v193身份，19300–19359；v192四个失败诊断未调用模型，不属于正式模型回合，也没有修改其历史状态。

## A. 12题主面板

✓为官方代码评分通过；合法交付不同的唯一成功代码已另注。全部失败和成功均有明确评分。

{task_table}

12仓各1题。选择seed为20261110191，顺序seed为20261110192，重复seed为20261110193；框架seed已冻结，不声称DeepSeek API采样seed可固定。每题四条件共享任务和环境；重复采用独立初态。原60身份没有因成绩而替换，既有可信候选没有best-of重选。

## B. 六题重复诊断

{repeat_detail}

M0为2题0/2、0题1/2、4题2/2；M1-10为1题0/2、2题1/2、3题2/2。M1-10代码翻转2/6，合法交付翻转1/6：Requests首轮虽然代码正确，但两轮交付都未通过。翻转是有限运行波动证据，不将“至少一次成功”作为主正确率。

Requests的M0两次都通过，但Token从195.20万增至499.46万；Astropy的M0两次都通过，Token从418.32万降至140.63万。结果稳定和成本稳定是不同问题。

## C. 输入、工作量与时间

{efficiency}

“每次合法交付总Token成本”＝该组12题全部消耗／合法交付数，包含失败题成本，不是只对成功题取均值。首末API跨度包含两次请求之间的工具与本地处理，不含进入首次API之前的准备和最后请求之后的归档，不能当作纯模型推理时间。公开测试耗时是命令墙钟之和，不是CPU秒。测试执行次数指命令实际启动，零测试收集或夹具错误也可计入；不等于测试通过或完整套件覆盖。精确重复按回合、代码树哈希、命令、选择器、环境哈希联合去重。动作列沿用运行边界的`actions`计数；模型响应中的工具选择次数另计，不把每次选择都当成成功的代码状态变化。

M1-5K相对M1-5，SymPy增加226.53万Token、Sphinx增加220.06万，两题合计约占净增加量59.80%；Requests、Pylint、Xarray也增加，部分任务如Astropy和Matplotlib则减少。两组不是同一动作轨迹，不能把所有成本差解释成文本投影本身。

全批输入130,638,338、输出551,486；其中缓存命中20,758,272，未命中109,880,066。缓存二者相加等于输入，而非再加到总量。冻结计价为每百万未命中输入2元、命中输入0.04元、输出8元，得到225.00235088元上界；不作为当前公开价格说明或供应商发票。

## D. 5M边界与交付实例

{budget_table}

5M门检查下一次请求的输入与输出预约，因此停止时实际结算量可以小于5M。另有1个重复回合（19358，Seaborn M1-10）触及此门；主测与重复的比例分别为7/48、1/12。本轮没有上下文容量截止或现金强制中断。

19322的末尾实际世界事件依次为：v17自写回归4项通过；删除该临时测试形成v18；v18测试25通过、3项httpbin夹具错误；`fix_patch`成功产生patch-1；下一模型机会被预算门拒绝。没有`submit_integration`调用，交付证据中的`submitted=false`与空交付清单吻合。不得把它描述成“未测试”“未固定”或“旧合法提交不正确”；也不能由最终代码通过推断下一次提交必然成功。

## E. 关键卡片与公开测试反馈

{category}

以上类别沿用冻结规则，不是实际代码修改次数。165个不同来源、2573次卡片呈现的字段均与此前实际wire中的原消息匹配。该核验是**来源和字段一致性**，不是完整关键事实召回率、语义重要性金标准或模型理解率。

版本标签：与最新已见工作区同版本457次，历史版本1609次，版本未知507次。历史标签本身不是错误，也不能当成模型实际误用旧测试；全部卡片都声明其文字不是一次新的验证。需要真正的行为证据或后续消融才能量化过期信息负担。

169个请求含同报告、同代码哈希的重复测试卡，289张多余卡的保留字段完全一致，直接文本合计约12.40万本地估计Token。该数是94.17万全部卡片文本中的一部分，不能与其再次相加。即使全部去重，也不能据此预测总Token会减少相同数量，因为后续模型动作可能变化。

1183次候选回退中，没有一次因为单卡超过768 Token；它们触及卡片数量／总预算约束。回退保持原文引用。同一候选可以在多个请求中重复回退，不能把次数当作不同缺失信息数量。

实际54张失败测试卡只包含`source_reference`、`files_sha256`、`passed`、`validation_status`、`counts`、`report_id`六类字段；54张代码变化卡都有版本来源，37张还有文件集合哈希，但无路径／diff字段。这是对实际输出的统计，不是说工具原始反馈不含这些信息。原动作链和可回读材料仍可能保留更详细内容。

核对564个实际进入模型上下文的测试工具返回，短证据页头最大1263字节，低于4096字节设计上限；完整测试日志仍在原分页正文中。短页头机制在本批实际生效，但没有同题旧页头对照，不能单独量化其对正确率或容量终止率的影响；它也没有保证公开测试依赖完整。四组Requests返回都出现过httpbin递归依赖；M1-10两次还报告`trustme`缺失与`mocker`缺失，一次包含隔离网络不可达。对公开测试故障、模型自写测试错误、官方代码失败应分别记录。

## F. 失败轨迹的证据范围

- **SymPy-13091**：三份首轮失败候选均未通过`test_comparisons_with_unknown_type`。K候选覆盖Basic、Expr、Number及相关比较分派，官方通过；其他候选覆盖不完整或分派处理不同。未进行逐补丁成分消融，因此不将单行修改或某张卡片称为已证实原因。M1-10重复轮成功进一步限制了“只有K能解出”的解释。
- **Sphinx-8721**：M1-5与M1-10在`collect_pages`等页面生成入口补充builder限制。K最终大幅重写viewcode流程，除原目标测试外，还损坏`test_viewcode_epub_enabled`和`test_local_source_files`；公开测试记录也有回归扩散。它是观察到的返工实例，但未证明最初偏离由某张卡片引起。
- **Pylint-6903**：M1-10只把最终`return cpu_count`改成`return cpu_count or 1`，未处理前面的`min(cpu_share, cpu_count)`分支；官方CPU小数配额测试仍失败。该回合仅48.19万Token，不能解释为耗尽5M。
- **Seaborn-3187**：四组均未完整修复两条图例路径。M1-5只剩relational目标测试失败，另外三组两条目标测试都失败。公开轨迹包含误用内部API的自写复现及未覆盖目标行为的测试通过，说明测试“通过”不等于问题已解决；是否追加预算就能成功，当前没有证据。

## G. 完整性、部署和可复算材料

4个v193零模型诊断与12题24项gold／empty评分控制通过；正式60回合全部闭合、全部双端点评分明确。M0/M1-5/M1-10/M1-5K的模型、角色及工具权限保持冻结。v192前置配置字段遗漏发生在0API阶段，v193开始前已修正并保留原件；运行中没有热改策略。

2843个物理请求的payload哈希、原始响应、usage、缓存字段与账本逐条一致，全部为首次物理尝试、无费用未知。全部响应报告`model=deepseek-flash`、`system_fingerprint=bc19ba97cbe016479903222bb1578db6`，但这不等于可以锁定供应商发布权重。

来源清单累计471,699,002个语义payload字节，其中660,480字节未归因，约0.1400%，分布于28个请求。本报告读取原清单的来源覆盖统计，没有重新进行全部span的Tokenizer归因；不能将99.86%的字节覆盖说成供应商Token覆盖。卡片长度采用冻结本地Tokenizer估计，API usage才是总Token权威值。

v193从11月10日19:24:28至11月11日04:36:45，共约9小时12分钟。最长无HTTP窗口为11月10日22:07:02至23:24:19；期间观察到输出盘预约不足。归档启动晚于该窗口，因此最初恢复不能归功于归档。v194后来无损归档80个旧世界快照，核算净释放116.73 GiB；本批与归档服务均已退出，无活动资源租约。未修改共享服务器配置。

复算入口为[结果与usage审计](../../tools/analyze_critical_context_v195.py)、[机制与案例审计](../../tools/audit_critical_mechanisms_v195.py)、[文档生成](../../tools/write_critical_report_v195.py)。数据为[汇总JSON](../../artifacts/software-benchmark-v195/context-report-r1/summary.json)、[逐回合CSV](../../artifacts/software-benchmark-v195/context-report-r1/episodes.csv)、[重复配对CSV](../../artifacts/software-benchmark-v195/context-report-r1/repeat-pairs.csv)、[实际卡片](../../artifacts/software-benchmark-v195/context-report-r1/critical-cards.json)、[机制证据](../../artifacts/software-benchmark-v195/context-report-r1/mechanism-audit.json)。所有派生材料与运行原件分开，报告没有新增API调用、评分、容器、GPU或训练。
'''
    (DOC/'software-benchmark-v195-critical-context-appendix.md').write_text(append)
    print(json.dumps({'main_report':str(DOC/'software-benchmark-v195-critical-context-report.md'),
        'appendix':str(DOC/'software-benchmark-v195-critical-context-appendix.md'),
        'report_characters':len(report),'appendix_characters':len(append)},ensure_ascii=False))


if __name__=='__main__':main()
