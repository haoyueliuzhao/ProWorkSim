"""Read-only JSON accounting; no tensor/model/GPU operations."""
from pathlib import Path
from datetime import datetime, timezone, timedelta
from collections import defaultdict
import hashlib
import json

ROOT=Path('/data1/zhuxinrui/projects/ProWorkSim')
OUT=ROOT/'artifacts/software-learning-v050/final-analysis'
TZ=timezone(timedelta(hours=8))
def read(p): return json.loads((ROOT/p).read_text())
def ref(p):
    q=ROOT/p
    return {'path':str(p),'sha256':hashlib.sha256(q.read_bytes()).hexdigest()}
def stamp(t): return datetime.fromtimestamp(t,TZ).isoformat() if t is not None else None
names=['software-learning-v050']+['software-learning-v050-resume-'+r for r in ['r1','r2','r3','r4','r5','r6','r6-restored']]
workers=[]
phases=[]
for name in names:
    p=Path('runs')/name/'supervisor.json'
    x=read(p)
    owned=[]
    for key,v in x['states'].items():
        if not v.get('attempted'): continue
        item={k:v.get(k) for k in ['status','pid','gpu','gpu_uuid','started_at','ended_at','elapsed_gpu_seconds','stop_reason','exit_code','planned_slots','process_started_at','resource_attempt_gpu_seconds']}
        item.update(root=name,worker=key,source=ref(p),process_start_ticks=v.get('process_identity',{}).get('start_ticks'))
        item['accounted_started_at']=v.get('process_started_at',v['started_at'])
        item['started_at_shanghai']=stamp(item['accounted_started_at'])
        item['ended_at_shanghai']=stamp(item['ended_at'])
        item['interval_matches_accounted_seconds']=abs(item['ended_at']-item['accounted_started_at']-item['elapsed_gpu_seconds'])<1e-6
        item['category']='generation' if key.startswith(('collect-','dev-')) else ('state_materialization' if key=='s_star' else 'training')
        if name.endswith('r4') and key=='update-Q_minus': item['category']='zero_model_resource_failure'
        if 'prelease_included_in_total' in v:
            item['reservation_preworker_seconds']=v['resource_prelease_seconds']
            item['formal_worker_gpu_seconds']=v['formal_worker_gpu_seconds']
            item['prelease_included_in_total']=v['prelease_included_in_total']
            item['bootstrap_terminal_at']=v['lease_terminal_observation']['lease_state']['ended_at']
            item['supervisor_exit_detection_lag_seconds']=item['ended_at']-item['bootstrap_terminal_at']
        workers.append(item); owned.append(item)
    phases.append({'root':name,'historical_supervisor_status':x['status'],'supervisor_started_at':x['started_at'],'supervisor_ended_at':x.get('ended_at'),'supervisor_started_at_shanghai':stamp(x['started_at']),'supervisor_ended_at_shanghai':stamp(x.get('ended_at')),'unique_owned_worker_count':len(owned),'owned_worker_seconds':sum(v['elapsed_gpu_seconds'] for v in owned),'reported_closed_worker_seconds':x['closed_worker_gpu_seconds'],'source':ref(p)})
identities=[(v['pid'],v['process_start_ticks']) for v in workers]
assert len(identities)==len(set(identities))
assert all(v['interval_matches_accounted_seconds'] for v in workers)
by_gpu=defaultdict(float);by_category=defaultdict(float)
for v in workers:by_gpu[str(v['gpu'])]+=v['elapsed_gpu_seconds'];by_category[v['category']]+=v['elapsed_gpu_seconds']
events=[]
for v in workers: events.extend([(v['accounted_started_at'],1,v['root']+'/'+v['worker']),(v['ended_at'],-1,v['root']+'/'+v['worker'])])
active=set();peak=0;first_peak=None
for when,delta,key in sorted(events):
    if delta==1:active.add(key)
    else:active.remove(key)
    if len(active)>peak:peak=len(active);first_peak={'at':when,'at_shanghai':stamp(when),'workers':sorted(active)}
cap_handoff=read('runs/software-learning-v050-concurrency-r6/administrative-handoff.json')
cap_at=cap_handoff['recorded_at']
active=set();after_peak=0
for when,delta,key in sorted(events):
    if delta==1:active.add(key)
    else:active.remove(key)
    if when>=cap_at:after_peak=max(after_peak,len(active))
plan=read('runs/software-learning-v050-resume-r4/plan.json')['q_compute_replay']
a=plan['allocation']
prior={}
for key,part in [('Q_plus',a['Q_plus_prior_attempt']),('Q_minus',a['Q_minus_prior_budget']['prior_attempts'])]:
    for v in (part if isinstance(part,list) else [part]):prior[(Path(v['root']).name,'update-'+key)]=v
training=[]
for v in workers:
    if v['category']!='training':continue
    p=Path('runs')/v['root']/v['worker']/'actual'
    c=read(p/'training-compute.json');r=read(p/'update/report.json')
    old=prior.get((v['root'],v['worker']))
    elapsed=c.get('elapsed_seconds') if c['ended_at'] is not None else old['elapsed_seconds_upper']
    lo=r['backward_decisions_completed']; hi=lo if c['ended_at'] is not None else old['backward_charged_upper']
    training.append({'root':v['root'],'worker':v['worker'],'gpu':v['gpu'],'status':r['status'],'compute_started_at':c['started_at'],'compute_ended_at':c['ended_at'],'compute_ended_at_upper':c['ended_at'] or old['training_ended_at_upper'],'compute_interval_seconds':c.get('elapsed_seconds'),'compute_interval_seconds_upper':elapsed,'compute_interval_exact':c['ended_at'] is not None,'maximum_seconds_this_attempt':c['maximum_seconds'],'admitted_rows':c['admitted_rows'],'admitted_output_tokens':r['admitted_output_tokens'],'native_forward_started':c['native_forward_started'],'native_forward_completed':c['native_forward_completed'],'native_gradient_forward_started':c['native_gradient_forward_started'],'native_no_grad_forward_started':c['native_no_grad_forward_started'],'actor_backward_completed_lower':lo,'actor_backward_charged_upper':hi,'critic_backward_completed_lower':lo,'critic_backward_charged_upper':hi,'actor_optimizer_steps':r['actor_optimizer_steps'],'critic_optimizer_steps':r['critic_optimizer_steps'],'abandoned_partial_gradients':c['ended_at'] is None,'sources':[ref(p/'training-compute.json'),ref(p/'update/report.json')],'nested_in_worker_interval_do_not_add':True})
training_sum={k:sum(x[k] for x in training) for k in ['native_forward_started','native_forward_completed','native_gradient_forward_started','native_no_grad_forward_started','actor_backward_completed_lower','actor_backward_charged_upper','critic_backward_completed_lower','critic_backward_charged_upper','actor_optimizer_steps','critic_optimizer_steps','compute_interval_seconds_upper']}
training_sum['compute_interval_hours_upper']=training_sum['compute_interval_seconds_upper']/3600
training_sum['exact_total_training_interval_seconds']=None
training_sum['actual_optimizer_committed_rows_per_side']=sum(t['actor_backward_completed_lower'] for t in training if t['actor_optimizer_steps'])
training_sum['abandoned_backward_rows_completed_lower_per_side']=sum(t['actor_backward_completed_lower'] for t in training if t['abandoned_partial_gradients'])
training_sum['abandoned_backward_rows_charged_upper_per_side']=sum(t['actor_backward_charged_upper'] for t in training if t['abandoned_partial_gradients'])
training_sum['native_forward_without_recorded_return']=training_sum['native_forward_started']-training_sum['native_forward_completed']
training_sum['no_grad_or_gradient_wrapper_counts_are_not_model_generation_tokens']=True
training_sum['optimizer_state_interpretation']='Three independent branches B/Q_plus/Q_minus each restored S_star 4/4 and committed 1 actor + 1 critic step to their own 5/5 state; not one serial 7/7 state.'
training_sum['interval_uncertainty']='Three interrupted old Q attempts have no exact training end; upper endpoints are their observed process exits. Their in-flight partial backward work is bounded, not declared zero.'
budget={k:a[k] for k in ['time_policy','aggregate_compute_seconds_cap','B_complete_interval_seconds','prior_Q_seconds_upper','prior_all_compute_seconds_upper','remaining_seconds_exact','branch_seconds','aggregate_seconds_upper','unallocated_seconds','original_branch_48h_enforced','r3_unstarted_reserved_seconds_charged','sha256']}
budget['actual_final_compute_seconds_upper']=training_sum['compute_interval_seconds_upper'];budget['remaining_seconds_after_actual_upper']=budget['aggregate_compute_seconds_cap']-budget['actual_final_compute_seconds_upper'];budget['passed']=budget['actual_final_compute_seconds_upper']<=budget['aggregate_compute_seconds_cap'];budget['source']=ref('runs/software-learning-v050-resume-r4/plan.json')
last=read('runs/software-learning-v050-resume-r6-restored/supervisor.json')
qplus=[w for w in workers if w['root'].endswith('r6-restored') and w['worker'].startswith('dev-Q_plus-')]
qminus=[w for w in workers if w['root'].endswith('r6-restored') and w['worker'].startswith('dev-Q_minus-')]
q_timing={}
for branch,items in [('Q_plus',qplus),('Q_minus',qminus)]:q_timing[branch]={'development_workers':len(items),'gpus':sorted({w['gpu'] for w in items}),'started_at_shanghai':stamp(min(w['accounted_started_at'] for w in items)),'ended_at_shanghai':stamp(max(w['ended_at'] for w in items)),'wall_seconds':max(w['ended_at'] for w in items)-min(w['accounted_started_at'] for w in items),'gpu_seconds':sum(w['elapsed_gpu_seconds'] for w in items)}
total=sum(w['elapsed_gpu_seconds'] for w in workers)
result={'version':'software-learning-v050-final-cost-accounting-v1','created_at_shanghai':datetime.now(TZ).isoformat(),'scope':'Original v050 unique inventory and all documented recovery resource costs, excluding previous v049 experiments and never counting adopted/external workers twice.','read_only_analysis':{'model_calls':0,'gpu_calls':0,'tensor_files_loaded':0,'experiments_started':0,'source_records_changed':False},'generation':None,'workers':workers,'phases':phases,'gpu_worker_accounting':{'unique_process_count':len(workers),'seconds':total,'hours':total/3600,'by_gpu_seconds':dict(sorted(by_gpu.items())),'by_category_seconds':dict(by_category),'time_definition':'Host-recorded process occupation from launch to observed exit, including model loading/final guards, lease prelude, interruptions and zero-model startup failure. Poll/exit detection overhead remains in historical receipts; not exact GPU kernel busy time.','prelease_already_included_seconds':next(w['reservation_preworker_seconds'] for w in workers if 'reservation_preworker_seconds' in w),'nested_training_intervals_added_again':False,'external_observation_added_again':False,'generation_token_usage_implies_no_training_token_equivalence':True},'concurrency':{'whole_window_peak_from_unique_intervals':peak,'first_peak':first_peak,'cap4_handoff_at_shanghai':stamp(cap_at),'peak_after_cap_handoff':after_peak,'maximum_after_cap_authorized':4,'passed':after_peak<=4,'historical_resource_policy_not_rewritten':True,'source':ref('runs/software-learning-v050-concurrency-r6/administrative-handoff.json')},'training_attempts':training,'training_aggregate':training_sum,'training_allocation':budget,'final_development_timing':q_timing,'completion':{'final_supervisor_status':last['status'],'final_completed_at':last['ended_at'],'final_completed_at_shanghai':stamp(last['ended_at']),'first_host_started_at_shanghai':stamp(phases[0]['supervisor_started_at']),'wall_seconds_from_first_host_to_completion':last['ended_at']-phases[0]['supervisor_started_at'],'final_unfinished_owned_workers':sum(s['status']!='complete' for s in last['states'].values()),'source':ref('runs/software-learning-v050-resume-r6-restored/supervisor.json')},'zero_work_and_administrative_history':[{'root':'software-learning-v050-resume-r3','owned_gpu_workers':0,'worker_seconds':0,'reason':'Waited without starting; original external Q_plus failure later retained. No r3 reserved compute used.'},{'root':'software-learning-v050-resume-r5','unstarted_development_workers_transferred_to_r6':16,'development_gpu_seconds':0,'reason':'Administrative concurrency-4 handoff; Q_minus remained active under original r5 host and is counted once.'},{'root':'software-learning-v050-resume-r6','owned_gpu_workers':0,'worker_seconds':0,'reason':'Administrative single-GPU change preparation; no development worker launched.'},{'root':'software-learning-v050-single-gpu-r7','formal_run_created':False,'gpu_or_model_workers':0,'worker_seconds':0,'reason':'User cancelled single-GPU2 change; undeployed draft has no new worker/compute. Original updates were not interrupted.','source':ref('runs/software-learning-v050-single-gpu-r7/cancellation-and-restore-proof.json')},{'root':'software-learning-v050-resume-r4','worker':'update-Q_minus','worker_seconds':12.528383493423462,'native_forward':0,'backward':0,'optimizer_steps':0,'reason':'CUDA resource query OOM before true model loader; spent worker time retained once; no training-interval allowance spent.','source':ref('artifacts/software-learning-v050/analysis/qminus-r5-startup-proof.json')}], 'limitations':['Generation and training compute are distinct costs; no currency price or total CPU core-hours were measured.','Three historical interrupted training intervals and partial backward rows retain upper/lower accounting; successful recovery does not make the old attempts successful.','Waiting supervisors with no launched GPU worker add wall-clock delay but zero worker GPU seconds.','All intervals use historical host process accounting; they are not hardware utilization integrals.']}
science_path=Path('artifacts/software-learning-v050/final-analysis/scientific-results.json')
science=read(science_path)
result['generation']={'totals':science['metrics']['generation'],'groups':{k:v['generation'] for k,v in science['groups'].items() if k!='all'},'source':ref(science_path),'unique_scientific_slots':56,'training_collection_slots':24,'paired_development_slots':32,'original_token_ceiling':28000000,'remaining_unspent_not_transferred':28000000-science['metrics']['generation']['complete_actual_tokens'],'all_generation_usage_known':True,'generation_worker_count':len(science['generation_workers'])}
assert result['generation']['generation_worker_count']==sum(w['category']=='generation' for w in workers)
(OUT/'costs.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
lines=['# v050 本轮费用与时间核算','',f"最终监督器于 **{result['completion']['final_completed_at_shanghai']}** 闭合。唯一 GPU worker 进程 {len(workers)} 个，合计 **{total:.9f} 秒 / {total/3600:.9f} GPU 小时**。这是原宿主的进程占用计时，包含装载、收尾、检测退出开销和失败工作，不等同于 GPU kernel 忙时。",'', '## 按阶段计算','', '| 运行根 | 唯一 worker | GPU worker 秒 |','|---|---:|---:|']
for p in phases:lines.append(f"| {p['root']} | {p['unique_owned_worker_count']} | {p['owned_worker_seconds']:.9f} |")
lines += ['', 'r4 Q+ 的 106010.5683760643 秒已经包含 GPU2 同进程预约前奏 2013.5438561439514 秒。不能再次加预约目录的全长。训练区间也嵌套在 worker 时间中，不与该表相加。r4 Q− 装载前资源 OOM 的 12.528383493423462 秒仍在表内；其模型前向/反向/optimizer 为 0。', '', '## 真实训练及遗留失败','', '| 执行 | 输入行 | 已完成/已开始 native forward | 已确认 backward 行/扣账上界（actor、critic各） | actor/critic step | 训练区间秒（旧中断为上界） |', '|---|---:|---:|---:|---:|---:|']
for t in training:lines.append(f"| {t['root']}/{t['worker']} | {t['admitted_rows']} | {t['native_forward_completed']}/{t['native_forward_started']} | {t['actor_backward_completed_lower']}/{t['actor_backward_charged_upper']} | {t['actor_optimizer_steps']}/{t['critic_optimizer_steps']} | {t['compute_interval_seconds_upper']:.9f} |")
lines += ['',f"合计 native forward {training_sum['native_forward_started']} 次开始、{training_sum['native_forward_completed']} 次有完整返回；旧 Q+ 有 1 次返回未确证。每侧 backward 已确认 {training_sum['actor_backward_completed_lower']} 行，扣账上界 {training_sum['actor_backward_charged_upper']} 行；不能把上界写成精确完成。三个完整分支实际使用 1929 行；旧失败部分已完成至少 581 行、上界 584 行，未应用任何 optimizer step，恢复均从相同 S_star 4/4 重新计算。B、Q+、Q− 各有 actor/critic 1/1 次真实提交，各自到 5/5，不是串行到 7/7。",'',f"累计训练区间保守上界 **{training_sum['compute_interval_seconds_upper']:.9f} 秒 / {training_sum['compute_interval_hours_upper']:.9f} 小时**。旧中断没有精确训练结束时间，按进程观察退出时刻扣账。最终 r4/r5 分配冻结为各 135481 秒，已用旧 B 和所有旧 Q 成本共 247437.88451504707 秒只计一次，总训练 518400 秒（144 小时）边界保持；实际保守上界剩余 {budget['remaining_seconds_after_actual_upper']:.9f} 秒。成功完成不抹除旧失败和舍弃的梯度工作。",'', '## 调度、结束与行政记录','',f"全窗口唯一进程区间重建的并发峰值为 {peak}；限制为 4 后峰值仍为 {after_peak}。峰值首次出现在 {first_peak['at_shanghai']}，对应四条 Q− 开发。Q+ 开发使用 GPU2/6，Q− 开发使用 GPU1/4/5/7；最终 Q+、Q− 训练分别使用 GPU2、GPU1。",'',f"Q+ 开发八槽 wall time {q_timing['Q_plus']['wall_seconds']:.3f} 秒，Q− 八槽 {q_timing['Q_minus']['wall_seconds']:.3f} 秒。这些并行 wall time 不可相加当作 GPU 时间。",'', 'r3 未启动 GPU worker；旧 r5 开发库存的停止标记是并发上限交接，Q− 没有中断；旧 r6 的十六条开发全部未启动，单卡 r7 仅为取消前草稿，没有正式运行根和 GPU/model worker。恢复的 r6-restored 只执行原十六槽。行政 `closed_with_unknowns` 不表示新增十六个业务技术未知。', '', '逐 worker 起止、源文件 SHA、训练上下界、GPU 分配和全部计算见同目录 `costs.json`；生成费用由唯一 56 槽结果核算补入，不从训练 native forward 推算生成 token。分析仅读取 JSON，不加载张量、不调用 GPU/模型、不改原实验记录。']
lines += ['', '## 唯一 56 槽生成费用', '', '| 组 | 决定 | 实际调用 | 输入 token | 输出 token | 合计 token | 成员测试 |', '|---|---:|---:|---:|---:|---:|---:|']
for group,g in result['generation']['groups'].items():
    lines.append(f"| {group} | {g['decisions']} | {g['complete_actual_calls']} | {g['prompt_tokens']} | {g['completion_tokens']} | {g['complete_actual_tokens']} | {g['public_member_tests']} |")
g=result['generation']['totals']
lines += [f"| 合计 | {g['decisions']} | {g['complete_actual_calls']} | {g['prompt_tokens']} | {g['completion_tokens']} | {g['complete_actual_tokens']} | {g['public_member_tests']} |", '', '所有 56 槽实际生成费用已知，1,527 次 attempt 均有完整输出回包，未知费用 0；39 次额外决定为执行前团队余额预约拒绝。22,078,253 实际 token 与账本扣账相同，原 28M 上限未用 5,921,747 token 不转移。训练重复读取这些本人输出不算新的生成调用或新增生成 token。']
(OUT/'costs.md').write_text('\n'.join(lines)+'\n')
print(json.dumps({'workers':len(workers),'gpu_seconds':total,'gpu_hours':total/3600,'training_upper_seconds':training_sum['compute_interval_seconds_upper'],'completed_at':result['completion']['final_completed_at_shanghai'],'categories':dict(by_category),'output':str(OUT/'costs.json')},ensure_ascii=False))
