"""Explicit one-off technical attempts in the original500-CNY SQLite account.

The immutable base policy is retained. A separately reviewed, append-only
identity amendment permits only independently named, proven technical failures.
Importing or constructing a view does not register attempts or call an API.
"""
from __future__ import annotations
from collections import defaultdict
import copy
import hashlib
import json
from pathlib import Path
import re
from types import SimpleNamespace

from . import software_benchmark_deepseek_api_v157 as base
from .software_benchmark_candidates_v054 import checked,reference

VERSION='v161-explicit-technical-attempts-same-original500-r1'
AUTH_VERSION='v161-independent-technical-recovery-authority-r1'
CAP=500_000_000_000


def _read(ref):
    return json.loads(checked(ref).read_bytes())


def _validate_authority(api,ref):
    value=_read(ref)
    if (value.get('version')!=AUTH_VERSION or value.get('status')!='approved'
        or value.get('base_policy_sha256')!=base.sha(api.POLICY)
        or value.get('ledger_path')!=api.POLICY['child_ledger_path']
        or value.get('cash_authority')!=api.POLICY['cash_authority']
        or value.get('cap_nanoyuan')!=CAP or value.get('additional_cash_allowance_nanoyuan')!=0
        or value.get('maximum_recoveries_per_original')!=1
        or value.get('team_token_limit')!=5_000_000 or value.get('team_http_attempt_limit')!=512
        or value.get('same_initial_state_seed_and_condition') is not True
        or value.get('normal_model_failures_may_retry') is not False
        or not isinstance(value.get('attempts'),list) or not value['attempts']):
        raise ValueError('A concrete same-account technical-recovery amendment is required')
    original=_read(api.POLICY['execution_plan'])
    rows={r['slot_id']:r for r in original['rows']}
    entries=[];seen_original=set();seen_new=set()
    for item in value['attempts']:
        old=rows.get(item.get('original_slot_id'));new=item.get('recovery_slot_id')
        if (old is None or not isinstance(new,str) or new!=old['slot_id']+':independent-technical-recovery-r1'
            or old['slot_id'] in seen_original or new in seen_new
            or item.get('classification')!='request_source_capture_failure'
            or any(item.get(k)!=old[k] for k in ('instance_id','condition_id','group_id','seed','fixed_members'))
            or item.get('original_configuration')!=old['configuration']):
            raise ValueError('A recovery changed identity/seed/config or duplicates an original team')
        before=_read(item['original_configuration']);after=_read(item['configuration'])
        expected=copy.deepcopy(before)
        expected['slot_id']=new
        if 'slot_index' in expected:
            if type(item.get('slot_index')) is not int or item['slot_index']<16100:
                raise ValueError('An independently owned physical slot index is required')
            expected['slot_index']=item['slot_index']
        if after!=expected:
            raise ValueError('Recovery may change only its independent slot identity, not the task/configuration')
        result=_read(item['failure_evidence']['result'])
        observer=_read(item['failure_evidence']['observer'])
        quiet=_read(item['failure_evidence']['quiescence'])
        stderr=checked(item['failure_evidence']['controller_stderr']).read_text(errors='replace')
        primary=any(row.get('scope')=='request_capture' and row.get('type')=='AccountingConflict'
            and row.get('message')=='Actual request source attribution is below the approved 98% gate'
            for row in observer.get('runtime_measurement_errors',[]))
        if (result.get('slot_id')!=old['slot_id'] or result.get('status')!='technical_unknown'
            or result.get('candidate_lock') is not None or observer.get('completion_status')!='partial'
            or not primary or quiet.get('quiescent') is not True or quiet.get('cleanup_errors')!=[]
            or quiet.get('create_result_unknown') is not False
            or 'result["ledger"] = owner.save()' not in stderr
            or 'argument must be an int, or have a fileno() method.' not in stderr):
            raise ValueError('Only the independently verified source/finalization fault can recover')
        folder=Path(item['failure_evidence']['result']['path']).parent
        if (folder/'controller-output/project-candidates/terminal-code/lock.json').exists():
            raise ValueError('An existing uniquely locked candidate must be recovered without model replay')
        seen_original.add(old['slot_id']);seen_new.add(new)
        entries.append(copy.deepcopy(item))
    return value,entries


def register_authorized_attempts(api,authority_ref,authorize):
    """Explicit administrative step; no model request and no new cash allowance."""
    authorize('v161.register_attempts',authority=authority_ref)
    authority,entries=_validate_authority(api,authority_ref)
    ledger=api.BudgetLedger()
    with ledger.transaction() as db:
        policy=db.execute("SELECT value FROM metadata WHERE name='policy'").fetchone()[0]
        if policy!=base.canonical(api.POLICY):raise ValueError('The original cash policy changed')
        db.execute('CREATE TABLE IF NOT EXISTS technical_recovery_authorities ('
            'authority_sha256 TEXT PRIMARY KEY, authority_json TEXT NOT NULL, '
            'registered_utc TEXT NOT NULL, additional_cash_nanoyuan INTEGER NOT NULL CHECK(additional_cash_nanoyuan=0))')
        db.execute('CREATE TABLE IF NOT EXISTS technical_recovery_attempts ('
            'recovery_slot_id TEXT PRIMARY KEY, original_slot_id TEXT NOT NULL UNIQUE, '
            'group_id TEXT NOT NULL, authority_sha256 TEXT NOT NULL, entry_json TEXT NOT NULL)')
        old_authority=db.execute('SELECT authority_json FROM technical_recovery_authorities WHERE authority_sha256=?',
            (authority_ref['sha256'],)).fetchone()
        if old_authority is not None and old_authority[0]!=base.canonical(authority):
            raise ValueError('Recovery authority identity collision')
        for entry in entries:
            old=list(db.execute('SELECT status FROM requests WHERE slot_id=?',(entry['original_slot_id'],)))
            if not old or any(row['status']=='reserved' for row in old):
                raise ValueError('The original used team must have drained physical requests')
            if db.execute('SELECT 1 FROM requests WHERE slot_id=?',(entry['recovery_slot_id'],)).fetchone():
                raise ValueError('Registration cannot replay or rewrite a consumed independent attempt')
            previous=db.execute('SELECT * FROM technical_recovery_attempts WHERE original_slot_id=? OR recovery_slot_id=?',
                (entry['original_slot_id'],entry['recovery_slot_id'])).fetchone()
            if previous is not None:
                if (previous['authority_sha256']!=authority_ref['sha256'] or previous['entry_json']!=base.canonical(entry)):
                    raise ValueError('An original team has already received its one recovery authorization')
                continue
            db.execute('INSERT INTO technical_recovery_attempts VALUES(?,?,?,?,?)',
                (entry['recovery_slot_id'],entry['original_slot_id'],entry['group_id'],authority_ref['sha256'],base.canonical(entry)))
        if old_authority is None:
            db.execute('INSERT INTO technical_recovery_authorities VALUES(?,?,?,0)',
                (authority_ref['sha256'],base.canonical(authority),base.now()))
    return {'version':VERSION,'registered_attempts':len(entries),'authority':authority_ref,
        'same_ledger_path':str(ledger.path),'base_policy_sha256':base.sha(api.POLICY),
        'additional_cash_allowance_nanoyuan':0,'model_calls':0,'requests_created':0}


def recovery_api(group_id,api,authority_ref):
    """Build an identity-amended client view only; registration remains explicit."""
    authority,entries=_validate_authority(api,authority_ref)
    if group_id!=api.group_id:raise ValueError('The recovery view retains its communication group')
    allowed={entry['recovery_slot_id']:entry for entry in entries if entry['group_id']==group_id}

    class Ledger(api.BudgetLedger):
        def _entry(self,db,slot_id):
            expected=allowed.get(slot_id)
            if expected is None:raise ValueError('A technical-recovery view cannot dispatch another identity')
            try:row=db.execute('SELECT * FROM technical_recovery_attempts WHERE recovery_slot_id=?',(slot_id,)).fetchone()
            except Exception as error:raise ValueError('The explicit recovery identity is not registered') from error
            if (row is None or row['authority_sha256']!=authority_ref['sha256']
                or row['entry_json']!=base.canonical(expected)):
                raise ValueError('The immutable recovery identity amendment changed')
            return expected

        def reserve(self,*,logical_id,attempt_index,slot_id,member_id,condition,usage_id,
                    request_sha256,prompt_upper_bound,max_output_tokens):
            if (usage_id not in base.PURPOSES or group_id=='C0' and usage_id=='compressor'
                or not re.fullmatch('[0-9a-f]{64}',request_sha256)):
                raise ValueError('Unknown recovery request purpose/hash')
            prefix=slot_id+':'+member_id+(':compressor:' if usage_id=='compressor' else ':')
            index=logical_id[len(prefix):] if logical_id.startswith(prefix) else ''
            if not re.fullmatch(r'[0-9]{4}',index) or not 1<=int(index)<=512 or not 1<=attempt_index<=3:
                raise ValueError('Malformed or unbounded independent logical request')
            base.old.contract._integer(prompt_upper_bound,'prompt_upper_bound',maximum=98304)
            base.old.contract._integer(max_output_tokens,'max_output_tokens',maximum=32768)
            if not max_output_tokens or usage_id=='compressor' and max_output_tokens!=512:
                raise ValueError('Frozen output reservation changed')
            amount=prompt_upper_bound*2000+max_output_tokens*8000;tokens=prompt_upper_bound+max_output_tokens
            request_id=logical_id+f':http-{attempt_index}'
            with self.transaction() as db:
                entry=self._entry(db,slot_id)
                if condition!=entry['condition_id'] or member_id not in entry['fixed_members']:
                    raise ValueError('Independent request crossed condition or member identity')
                if db.execute("SELECT 1 FROM metadata WHERE name='halted'").fetchone():
                    raise base.PreDispatchBudgetStopped('accounting_integrity_halt')
                prior=list(db.execute('SELECT * FROM requests WHERE logical_id=? ORDER BY attempt_index',(logical_id,)))
                if attempt_index!=len(prior)+1 or any(r['status']!='http_error_uncertain' for r in prior):
                    raise base.PreDispatchBudgetStopped('logical_request_already_attempted_or_not_retryable')
                if any(r['request_sha256']!=request_sha256 or r['usage_id']!=usage_id for r in prior):
                    raise ValueError('A retry must retain its exact independent logical request')
                total=db.execute("SELECT COALESCE(SUM(CASE WHEN status='settled' THEN settled_nanoyuan ELSE reserved_nanoyuan END),0),SUM(status='reserved') FROM requests").fetchone()
                if total[0]+amount>CAP:raise base.PreDispatchBudgetStopped('remaining_cash_reservation_insufficient')
                if (total[1] or 0)>=api.POLICY['max_concurrency']:
                    raise base.PreDispatchConcurrencyBusy('original_shared_HTTP_limit')
                rows=list(db.execute('SELECT * FROM requests WHERE slot_id=?',(slot_id,)))
                if any(r['status']=='reserved' or r['status']=='unknown' and r['usage_id']!='compressor' for r in rows):
                    raise base.PreDispatchBudgetStopped('team_has_unrecoverable_or_inflight_attempt')
                accounted=sum(json.loads(r['usage_json'])['total_tokens'] if r['status']=='settled' else r['reserved_tokens'] for r in rows)
                if len(rows)>=512 or accounted+tokens>5_000_000:
                    raise base.PreDispatchBudgetStopped('shared_team_actual_plus_unknown_upper_limit')
                db.execute('INSERT INTO requests(request_id,logical_id,attempt_index,slot_id,member_id,condition,usage_id,request_sha256,status,reserved_nanoyuan,reserved_tokens,prompt_upper_bound,max_output_tokens,reserved_utc) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (request_id,logical_id,attempt_index,slot_id,member_id,condition,usage_id,request_sha256,
                     'reserved',amount,tokens,prompt_upper_bound,max_output_tokens,base.now()))
            return request_id

        def team_snapshot(self,slot_id):
            with self.transaction() as db:
                entry=self._entry(db,slot_id)
                rows=[dict(r) for r in db.execute('SELECT * FROM requests WHERE slot_id=? ORDER BY reserved_utc,request_id',(slot_id,))]
            actual=held=0;purposes={};members={}
            for row in rows:
                p=purposes.setdefault(row['usage_id'],{'prompt_tokens':0,'completion_tokens':0,'known_actual_tokens':0,
                    'uncertain_reserved_tokens':0,'physical_attempts':0})
                m=members.setdefault(row['member_id'],{'known_actual_tokens':0,'physical_attempts':0})
                p['physical_attempts']+=1;m['physical_attempts']+=1
                if row['status']=='settled':
                    u=json.loads(row['usage_json']);actual+=u['total_tokens'];p['known_actual_tokens']+=u['total_tokens'];m['known_actual_tokens']+=u['total_tokens']
                    for key in ('prompt_tokens','completion_tokens'):p[key]+=u[key]
                else:held+=row['reserved_tokens'];p['uncertain_reserved_tokens']+=row['reserved_tokens']
            return {'version':VERSION,'team_id':slot_id,'original_slot_id':entry['original_slot_id'],
                'group_id':group_id,'token_limit':5_000_000,'attempt_limit':512,'known_actual_tokens':actual,
                'uncertain_reserved_tokens':held,'accounted_tokens':actual+held,'available_tokens':max(0,5_000_000-actual-held),
                'attempts':len(rows),'decisions':len({r['logical_id'] for r in rows if r['usage_id']=='agent'}),
                'remaining_attempts':512-len(rows),'actual_usage_complete':not held,'per_usage_id':purposes,'per_member':members,
                'inflight_count':sum(r['status']=='reserved' for r in rows),
                'live_reserved_tokens':sum(r['reserved_tokens'] for r in rows if r['status']=='reserved'),
                'source':'one_shared_physical_provider_sqlite','recovery_authority':authority_ref}

    class Client(api.DeepSeekClient):
        def __init__(self,**kwargs):
            super().__init__(**kwargs)
            self.ledger=Ledger()

    return SimpleNamespace(**{**vars(api),'VERSION':VERSION,'BudgetLedger':Ledger,'DeepSeekClient':Client,
        'recovery_authority':authority_ref,'additional_cash_allowance_nanoyuan':0,
        'base_cash_POLICY_is_unchanged':True})
