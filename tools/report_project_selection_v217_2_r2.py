"""Read-only four-table report of all recorded panels, updates and confirmation."""
import json,collections,sqlite3,statistics
from pathlib import Path
from proworksim.software_organization_selector_v217 import policy_value
from proworksim.software_benchmark_candidates_v054 import reference
R=Path(__file__).resolve().parents[1];ROOT=R/'runs/software-benchmark-v217/streaming-r2';LEGACY=R/'runs/software-benchmark-v217/confirmation-resume-r1';HISTORY=R/'runs/software-benchmark-v217/selection28-r1';RECOVERY=R/'artifacts/software-benchmark-v217/resilience-r1';OUT=R/'artifacts/software-benchmark-v217/results-r3';OUT.mkdir(parents=True,exist_ok=True)
def read(p):return json.loads(p.read_text()) if p.exists() else None
def save(n,x):(OUT/n).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
records=read(HISTORY/'dev1-results.json')+read(RECOVERY/'dev2-results-canonical.json')+[read(p) for p in sorted(ROOT.glob('task-*/panel-result.json'))];confirm=[r for r in records if r['phase']=='confirm' and r['complete']]
values=[]
for r in confirm:
 results={z:{'correct_legal':v['legal_correct'],'tokens':v['logical_tokens']} for z,v in r['outcomes'].items()}
 v={q:policy_value(dist,results) for q,dist in r['decision']['probabilities'].items()}
 for q,dist in r['decision']['probabilities'].items():v[q]['code_quality']=sum(dist[z]*r['outcomes'][z]['code_correct'] for z in dist)
 values.append({'index':r['index'],'instance_id':r['instance_id'],'repo':r['repo'],'values':v,'delta':{ref:v['P_CN']['utility']-v[ref]['utility'] for ref in ('q0','L_CN','P_C','KEEP')},'candidate_outcomes':r['outcomes'],'probabilities':r['decision']['probabilities']})
comparisons={}
for ref in ('q0','L_CN','P_C','KEEP'):
 ds=[v['delta'][ref] for v in values]
 comparisons[ref]={'n_tasks':len(ds),'mean_delta':statistics.mean(ds) if ds else None,'by_task':ds,'leave_one_task_out':[(sum(ds)-d)/(len(ds)-1) for d in ds] if len(ds)>1 else [],'by_repo':{repo:statistics.mean(v['delta'][ref] for v in values if v['repo']==repo) for repo in sorted({v['repo'] for v in values})}}
relations=[];chains=[]
for task in sorted([*HISTORY.glob('task-*'),*LEGACY.glob('task-*'),*ROOT.glob('task-*')]):
 for ep in [task/'PREFIX',*[task/z for z in ('KEEP','C1','C2')]]:
  pg=read(ep/'project-relations.json')
  if pg:relations.append({'task':task.name,'episode':ep.name,'graph_id':pg['graph_id'],'relation_counts':dict(collections.Counter(r['kind'] for r in pg['relations'])),'fact_status':dict(collections.Counter(r['fact_status'] for r in pg['relations'])),'validity':dict(collections.Counter(r['validity'] for r in pg['relations'])),'source':reference(ep/'project-relations.json')})
 panel=next((r for r in records if r['index']==int(task.name.split('-')[-1])),None);bank=read(task/'GENERATOR/candidate-bank.json');dec=read(task/'decision.json')
 if bank and dec:
  for z,c in bank['candidates'].items():
   ep=Path(panel['outcomes'].get(z,{}).get('episode_path',str(task/z))) if panel else task/z;d=read(ep/'dynamic-final.json') or {};boundary=read(ep/'boundary.json') or {};actions=[]
   for o in boundary.get('outcomes',[]):
    a=o.get('decision',{});res=o.get('response',{})
    if a.get('action') in ('select_arrangement','offer_joint_arrangement','accept_joint_arrangement','change_dependency','integrate_patch','complete_work','complete_evidence','org_review_patch','submit_integration'):
     actions.append({'actor':o.get('worker_id'),'tool':a['action'],'ok':res.get('ok'),'arguments':a.get('arguments'),'error':res.get('error')})
   chains.append({'index':panel['index'] if panel else int(task.name.split('-')[-1]),'condition':z,'candidate':c,'selected_by_primary':dec['selected']==z,'choice':d.get('lifecycle',{}).get('choice'),'actions':actions,'outcome':panel['outcomes'].get(z) if panel else None})
updates=[read(LEGACY/f'policy-{i}.json') for i in (1,2)]
with sqlite3.connect('file:'+str(R/'runs/software-benchmark-v211/budget700-r1/ledger.sqlite')+'?mode=ro',uri=True) as conn:
 statuses=[dict(zip(('status','requests','tokens','cost_CNY_upper'),r)) for r in conn.execute("SELECT status,count(*),sum(tokens),sum(cost)/1e9 FROM requests WHERE slot LIKE 'v217:%' GROUP BY status")]
 settled=conn.execute("SELECT COALESCE(sum(cost),0)/1e9 FROM requests WHERE status='settled'").fetchone()[0]
 totals=collections.Counter()
 for (body,) in conn.execute("SELECT body FROM requests WHERE slot LIKE 'v217:%' AND status='settled'"):
  u=json.loads(body);totals.update({k:u.get(k,0) or 0 for k in ('input_tokens','output_tokens','total_tokens','cache_hit_tokens','cache_miss_tokens')})
summary={'version':'v217-full-panel-report-r1','finished':read(ROOT/'finished.json'),'planned_states':28,'planned_max_continuations':84,'states_with_panel_results':len(records),'complete_panels':sum(r['complete'] for r in records),'confirmation_tasks':len(confirm),'real_updates':sum(u is not None for u in updates),'comparisons':comparisons,'physical_requests':statuses,'physical_usage':dict(totals),'shared1100_settled_CNY_upper':settled,'remaining_CNY':1100-settled,'confirmation_not_used_for_fitting':True,'single_generation_per_candidate':True,'no_population_significance_claim':True}
save('project-relations.json',relations);save('organization-chains.json',chains);save('development-updates.json',updates);save('frozen-confirmation.json',values);save('summary.json',summary)
lines=['# 项目关系与C/N协作选择实验报告','',f"实际取得{len(records)}个任务候选面板，完整面板{sum(r['complete'] for r in records)}个；完成{summary['real_updates']}次真实反馈更新。确认任务数{len(confirm)}，计划28个状态、最多84条主续跑。",'', '项目关系选择器与工作台账选择器共用候选和实际结果；比较只识别同一候选支持下的选择增量。每候选一次生成，模型波动未消除，不能把各候选当成独立任务。','', '## 冻结确认比较','', '| 比较 P_CN减参照 | 完整任务数 | 平均效用差 |','| --- | ---: | ---: |']
for ref,c in comparisons.items():lines.append(f"| {ref} | {c['n_tasks']} | {c['mean_delta'] if c['mean_delta'] is not None else '未知'} |")
lines+=['','效用＝合法且正确交付−0.1×完整任务Token/500万。所有选择器按同题完整候选结果概率加权；KEEP也承担共同候选准备成本。缺失候选结果的题不填0，其面板和原计划分母保留。','', '## 实际范围和费用','',f"请求状态：{json.dumps(statuses,ensure_ascii=False)}。共享1100元账本累计{settled:.8f}元（峰值费率上界），余额{1100-settled:.8f}元。逻辑任务前缀不能再次加到物理账本。",'', '## 四张主表','', '- [项目关系与来源](../../artifacts/software-benchmark-v217/results-r3/project-relations.json)','- [候选选择、真实组织操作与后继结果](../../artifacts/software-benchmark-v217/results-r3/organization-chains.json)','- [两轮C/N、拟合参数与分布变化](../../artifacts/software-benchmark-v217/results-r3/development-updates.json)','- [逐题冻结确认、仓库和留一敏感度](../../artifacts/software-benchmark-v217/results-r3/frozen-confirmation.json)','- [完整统计及状态](../../artifacts/software-benchmark-v217/results-r3/summary.json)','', '仅完整面板用于当前可计算效用，未完成和技术未知需结合原计划规模解释。负收益、KEEP概率提高或无改善均保留；不据确认成绩追加样本。']
(R/'docs/experiments/software-benchmark-v217.2-streaming-full-report.md').write_text('\n'.join(lines)+'\n')
print(json.dumps(summary,ensure_ascii=False))
