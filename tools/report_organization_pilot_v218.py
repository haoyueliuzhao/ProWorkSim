"""Read-only pilot report: account for unqualified states and shared prefix cost."""
import json,statistics,collections
from pathlib import Path
from proworksim.software_organization_selector_v217 import policy_value
R=Path(__file__).resolve().parents[1];ROOT=R/'runs/software-benchmark-v218/pilot8-r1';OUT=R/'artifacts/software-benchmark-v218/results-r1';OUT.mkdir(parents=True,exist_ok=True)
def read(p):return json.loads(p.read_text()) if p.exists() else None
def save(n,v):(OUT/n).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
records=[read(p) for p in sorted(ROOT.glob('task-*/panel-result.json'))];confirmation=[]
for r in records:
 if r['phase']!='confirm' or not r['complete']:continue
 results={z:{'correct_legal':o['legal_correct'],'tokens':o['logical_tokens']} for z,o in r['outcomes'].items()};values={q:policy_value(dist,results) for q,dist in r['decision']['probabilities'].items()}
 for q,dist in r['decision']['probabilities'].items():values[q]['code_quality']=sum(dist[z]*r['outcomes'][z]['code_correct'] for z in dist)
 confirmation.append({'index':r['index'],'instance_id':r['instance_id'],'repo':r['repo'],'values':values,'outcomes':r['outcomes'],'probabilities':r['decision']['probabilities']})
complete=[r for r in records if r['complete']];arms=[o for r in complete for o in r['outcomes'].values()];finished=read(ROOT/'finished.json')
summary={'planned_states':8,'planned_max_arms':24,'panels':len(records),'complete_panels':len(complete),'complete_confirmation':len(confirmation),'scored_arms_in_complete_panels':len(arms),'code_correct':sum(o['code_correct'] for o in arms),'legal_correct':sum(o['legal_correct'] for o in arms),'stage_wait_notice_count':sum(len(o.get('stage_wait_corrections',[])) for o in arms),'quiescent_without_delivery':sum(o.get('termination_class')=='quiescent_without_delivery' for o in arms),'mean_logical_tokens':statistics.mean(o['logical_tokens'] for o in arms) if arms else None,'finished':finished,'initial_policy_updates':2,'additional_policy_updates':finished['policy_update']-2 if finished else None,'old_results_unchanged':True,'all_tasks_historically_exposed':True,'causal_stage_repair_claim':False,'single_candidate_not_forced':True,'policies':{q:{k:statistics.mean(x['values'][q][k] for x in confirmation) for k in ('code_quality','quality','tokens','utility')} for q in ('KEEP','q0','L_CN','P_C','P_CN')} if confirmation else {}}
save('summary.json',summary);save('panels.json',records);save('confirmation.json',confirmation);save('progress-at-report.json',read(ROOT/'progress.json'))
lines=['# v218 阶段与组织选择机会试跑报告','',f"计划8题、最多24续跑；实际取得{len(records)}个面板，完整{len(complete)}个，完整确认{len(confirmation)}个。",'', '本批固定两Agent、DeepSeek Flash非思考、每完整任务5M。统一修订前缀/续跑提示，最多两次有界全员等待提醒；只接纳有真实结构差异的候选面板。全部候选独立续跑，评分不反馈给求解器。', '', '当前策略由v217最终参数开始，再进行最多两轮新开发更新，最后冻结确认。不能与旧不同任务直接相减宣称阶段修复因果收益；本批是机制筛选，不作显著性结论。', '',f"完整面板内代码通过{summary['code_correct']}/{len(arms)}，合法交付{summary['legal_correct']}/{len(arms)}；实际有界等待提醒{summary['stage_wait_notice_count']}次，未交付静止{summary['quiescent_without_delivery']}条。",'', '| 条件 | 加权代码正确率 | 加权合法交付率 | 平均完整任务Token | 效用 |','|---|---:|---:|---:|---:|']
for q,v in summary['policies'].items():lines.append(f"| {q} | {v['code_quality']:.4%} | {v['quality']:.4%} | {v['tokens']:.1f} | {v['utility']:.6f} |")
lines+=['','平均值逐题等权、题内按冻结概率加权；不把候选重复当独立任务。共同前缀与候选生成计入各逻辑任务，物理总账只支付一次。', '',f"现金与实际使用：{json.dumps(finished['cash'] if finished else {},ensure_ascii=False)}",'', '[完整状态及分母](../../artifacts/software-benchmark-v218/results-r1/summary.json)；[逐题候选](../../artifacts/software-benchmark-v218/results-r1/panels.json)；[冻结确认](../../artifacts/software-benchmark-v218/results-r1/confirmation.json)。']
(R/'docs/experiments/software-benchmark-v218-pilot-report.md').write_text('\n'.join(lines)+'\n');print(json.dumps(summary,ensure_ascii=False))
