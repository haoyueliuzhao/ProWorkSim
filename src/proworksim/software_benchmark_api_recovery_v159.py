"""Read-only audit and admission of never-called original communication teams.

This module cannot create a cash ledger, call a model, alter a reservation, or
replay a consumed team. Cash and tokens remain in the original v157 account.
"""
from __future__ import annotations
from collections import Counter,defaultdict
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import sqlite3

VERSION='v159-original-cny500-uncalled-team-recovery-r1'


def audit(ledger_path,original_plan):
    path=Path(ledger_path).resolve()
    with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=30) as db:
        db.row_factory=sqlite3.Row;db.execute('PRAGMA query_only=ON');db.execute('BEGIN')
        policy_text=db.execute("SELECT value FROM metadata WHERE name='policy'").fetchone()[0]
        policy=json.loads(policy_text)
        rows=[dict(r) for r in db.execute('SELECT * FROM requests ORDER BY reserved_utc,request_id')]
        metadata={r['name']:r['value'] for r in db.execute("SELECT * FROM metadata WHERE name!='policy'")}
    if (policy.get('version')!='v157-communication-shared-cny500-r1'
        or policy.get('cap_nanoyuan')!=500_000_000_000 or policy.get('available_nanoyuan')!=500_000_000_000
        or policy.get('child_ledger_path')!=str(path)):
        raise ValueError('Only the original independent500-CNY pilot ledger may fund recovery')
    planned={r['slot_id']:r for r in original_plan['rows']}
    if len(planned)!=72:raise ValueError('Keep all72 original scheduled identities')
    totals=Counter();by_group=defaultdict(Counter);by_purpose=defaultdict(Counter)
    by_team={};requests=[]
    for row in rows:
        scheduled=planned.get(row['slot_id'])
        if (scheduled is None or row['condition']!=scheduled['condition_id']
            or row['member_id'] not in scheduled['fixed_members']
            or row['usage_id'] not in {'agent','condenser','compressor'}):
            raise ValueError('A physical usage identity left the original plan')
        group=scheduled['group_id'];purpose=row['usage_id'];status=row['status']
        if status not in {'settled','reserved','unknown','http_error_uncertain'}:
            raise ValueError('Unexpected physical accounting state')
        team=by_team.setdefault(row['slot_id'],{'slot_id':row['slot_id'],'slot_index':scheduled['slot_index'],
            'group_id':group,'condition_id':row['condition'],'instance_id':scheduled['instance_id'],
            'wave':scheduled['wave'],'physical_requests':0,'settled_requests':0,'inflight_requests':0,
            'uncertain_requests':0,'retry_requests':0,'known_actual_input_tokens':0,
            'known_actual_output_tokens':0,'known_actual_total_tokens':0,
            'settled_peak_upper_nanoyuan':0,'held_or_unknown_nanoyuan':0,'held_or_unknown_token_upper':0})
        metrics=Counter(physical_requests=1,retry_requests=int(row['attempt_index']>1))
        item={k:row[k] for k in ('request_id','logical_id','attempt_index','slot_id','member_id','condition','usage_id','status')}
        if status=='settled':
            usage=json.loads(row['usage_json']);prompt=usage['prompt_tokens'];output=usage['completion_tokens']
            if usage['total_tokens']!=prompt+output:raise ValueError('Authoritative usage partitions disagree')
            metrics.update(settled_requests=1,known_actual_input_tokens=prompt,
                known_actual_output_tokens=output,known_actual_total_tokens=prompt+output,
                settled_peak_upper_nanoyuan=row['settled_nanoyuan'])
            item.update(usage=usage,settled_peak_upper_nanoyuan=row['settled_nanoyuan'])
        else:
            metrics.update(inflight_requests=int(status=='reserved'),uncertain_requests=int(status!='reserved'),
                held_or_unknown_nanoyuan=row['reserved_nanoyuan'],held_or_unknown_token_upper=row['reserved_tokens'])
            item.update(reserved_nanoyuan=row['reserved_nanoyuan'],reserved_tokens=row['reserved_tokens'],
                reservation_is_actual_usage=False)
        for key,value in metrics.items():team[key]+=value
        totals.update(metrics);by_group[group].update(metrics);by_purpose[purpose].update(metrics);requests.append(item)
    used=set(by_team);unused=set(planned)-used
    total=dict(totals)
    for key in ('physical_requests','retry_requests','inflight_requests','uncertain_requests',
                'settled_peak_upper_nanoyuan','held_or_unknown_nanoyuan','held_or_unknown_token_upper'):
        total.setdefault(key,0)
    total['cap_nanoyuan']=500_000_000_000
    total['remaining_peak_upper_nanoyuan']=500_000_000_000-total['settled_peak_upper_nanoyuan']-total['held_or_unknown_nanoyuan']
    return {'version':VERSION,'snapshot_utc':datetime.now(timezone.utc).isoformat(),'ledger_path':str(path),
        'policy':policy,'policy_sha256':hashlib.sha256(policy_text.encode()).hexdigest(),
        'global_halt':metadata.get('halted'),'planned_teams':72,'used_teams':len(used),'unused_teams':len(unused),
        'used_original_slots':sorted(used),'admitted_original_slots':sorted(unused),
        'groups':{g:dict(v) for g,v in by_group.items()},'purposes':{p:dict(v) for p,v in by_purpose.items()},
        'teams':[by_team[k] for k in sorted(by_team)],'requests':requests,'totals':total,
        'new_cash_allowance_nanoyuan':0,'old_cash_policy_changed':False,'model_calls_during_audit':0,
        'consumed_teams_may_be_resampled':False,'source_attribution_not_readded_to_actual_tokens':True}


def validate_recovery_plan(plan,original_plan,snapshot,*,coexistence=None):
    original={r['slot_id']:r for r in original_plan['rows']}
    admitted=plan.get('admitted_original_slots');used=plan.get('used_original_slots')
    if (not isinstance(admitted,list) or not isinstance(used,list)
        or len(set(admitted))!=len(admitted) or len(set(used))!=len(used)
        or set(admitted)&set(used) or set(admitted)|set(used)!=set(original)
        or set(used)!=set(snapshot['used_original_slots'])
        or set(admitted)!=set(snapshot['admitted_original_slots'])):
        raise ValueError('Recovery may admit exactly the original teams with zero physical requests')
    rows=plan['rows']
    if len(rows)!=len(admitted) or {r['slot_id'] for r in rows}!=set(admitted):
        raise ValueError('Recovery rows must cover each never-called identity once')
    if any(row!=original[row['slot_id']] for row in rows):
        raise ValueError('Recovery must preserve every original task/seed/config/member field byte-for-byte')
    if snapshot['global_halt']:
        raise ValueError('An original global accounting halt cannot be bypassed')
    if snapshot['totals']['inflight_requests']:
        active=set((coexistence or {}).get('active_old_slots',[]))
        inflight={r['slot_id'] for r in snapshot['requests'] if r['status']=='reserved'}
        if (not isinstance(coexistence,dict) or coexistence.get('passed') is not True
            or coexistence.get('old_new_generation_admission_closed') is not True
            or not active or not active<=set(used) or not inflight<=active):
            raise ValueError('The old physical queue must drain or have exact approved isolated coexistence')
    return True
