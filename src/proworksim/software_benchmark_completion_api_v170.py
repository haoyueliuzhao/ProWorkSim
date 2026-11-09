"""Append-only550-CNY start admission; started teams keep their5M work budget.

The historical policy and request rows are not rewritten. Cash may exceed the
start threshold only for explicitly admitted, finite recovery identities.
"""
from __future__ import annotations

import copy
import json
import re
from types import SimpleNamespace

from . import software_benchmark_deepseek_api_v157 as base
from .software_benchmark_candidates_v054 import checked

VERSION = 'v170-start-cash-admission-complete-entered-teams-r1'
AUTH_VERSION = 'v170-completion-recovery-authority-r1'
THRESHOLD = 550_000_000_000
START_HOLD = 98_304*2000 + 32_768*8000


def read(ref):
    return json.loads(checked(ref).read_bytes())


def validate_authority(api, ref):
    value = read(ref)
    if (value.get('version') != AUTH_VERSION or value.get('approved') is not True
            or value.get('base_policy_sha256') != base.sha(api.POLICY)
            or value.get('ledger_path') != api.POLICY['child_ledger_path']
            or value.get('new_team_start_threshold_nanoyuan') != THRESHOLD
            or value.get('additional_nominal_nanoyuan') != 50_000_000_000
            or value.get('started_teams_finish_above_threshold') is not True
            or value.get('team_token_limit') != 5_000_000
            or value.get('maximum_new_attempts') != 13):
        raise ValueError('Exact user-authorized50-CNY addition and started-team completion policy required')
    grant = read(value['user_grant'])
    if (grant.get('approved') is not True or grant.get('additional_nominal_CNY') != '50.00'
            or grant.get('new_team_start_cash_threshold_CNY') != '550.00'
            or grant.get('started_team_may_finish_above_threshold') is not True):
        raise ValueError('Explicit user cash/stopping-rule amendment is missing')
    original = read(api.POLICY.get('execution_plan') or api.POLICY['panel'])
    old = {r['slot_id']: r for r in original['rows']}
    entries = value.get('attempts', [])
    if len(entries) != 13 or len({r['original_slot_id'] for r in entries}) != 13:
        raise ValueError('Only13 specified interrupted original teams may recover once')
    for item in entries:
        row = old.get(item['original_slot_id'])
        if (row is None or item['recovery_slot_id'] != row['slot_id']+':completion-recovery-v170'
                or any(item[k] != row[k] for k in ('instance_id','condition_id','group_id','seed','fixed_members'))
                or item['original_configuration'] != row['configuration']):
            raise ValueError('Recovery changed task, seed, condition or original identity')
        before = read(item['original_configuration']); after = read(item['configuration'])
        expected = copy.deepcopy(before); expected.update(slot_id=item['recovery_slot_id'], slot_index=item['slot_index'])
        if after != expected:
            raise ValueError('Only independent physical identity may change')
        failure = read(item['failure_evidence']['boundary']).get('execution_integrity_failure')
        quiet = read(item['failure_evidence']['quiescence'])
        valid = (item['classification']=='observer_execution_interruption' and failure=='measurement_capture_incomplete'
            or item['classification']=='cash_admission_interruption' and isinstance(failure,dict)
                and failure.get('reason')=='remaining_cash_reservation_insufficient'
                and failure.get('before_dispatch_proven') is True)
        if (not valid or quiet.get('quiescent') is not True
                or quiet.get('all_owned_objects_removed') is not True or quiet.get('cleanup_errors') != []):
            raise ValueError('Recovery requires an actual interrupted and cleaned original attempt')
    return value, entries


def totals(db):
    rows = list(db.execute('SELECT status,reserved_nanoyuan,settled_nanoyuan FROM requests'))
    paid = sum(r['settled_nanoyuan'] for r in rows if r['status']=='settled')
    held = sum(r['reserved_nanoyuan'] for r in rows if r['status']!='settled')
    start_holds = db.execute("SELECT COUNT(*) FROM team_start_grants_v170 g WHERE g.state='started' AND NOT EXISTS(SELECT 1 FROM requests r WHERE r.slot_id=g.slot_id)").fetchone()[0]*START_HOLD
    return paid, held, start_holds, sum(r['status']=='reserved' for r in rows)


def register(api, authority_ref):
    authority, entries = validate_authority(api, authority_ref)
    ledger = api.BudgetLedger()
    with ledger.transaction() as db:
        if db.execute("SELECT 1 FROM requests WHERE status='reserved' LIMIT 1").fetchone():
            raise ValueError('Prior requests must settle before this policy transition')
        db.execute('CREATE TABLE IF NOT EXISTS cash_amendments_v170(authority_sha256 TEXT PRIMARY KEY,authority_json TEXT NOT NULL,registered_utc TEXT NOT NULL)')
        known = list(db.execute('SELECT * FROM cash_amendments_v170'))
        if known and (len(known)!=1 or known[0]['authority_sha256']!=authority_ref['sha256'] or known[0]['authority_json']!=base.canonical(authority)):
            raise ValueError('The50-CNY addition cannot be stacked or changed')
        db.execute('INSERT OR IGNORE INTO cash_amendments_v170 VALUES(?,?,?)', (authority_ref['sha256'],base.canonical(authority),base.now()))
        db.execute('CREATE TABLE IF NOT EXISTS completion_attempts_v170(slot_id TEXT PRIMARY KEY,authority_sha256 TEXT NOT NULL,entry_json TEXT NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS team_start_grants_v170(slot_id TEXT PRIMARY KEY,state TEXT NOT NULL,authority_sha256 TEXT NOT NULL,started_utc TEXT NOT NULL,committed_at_start_nanoyuan INTEGER NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS team_start_events_v170(sequence INTEGER PRIMARY KEY,slot_id TEXT NOT NULL,kind TEXT NOT NULL,observed_utc TEXT NOT NULL)')
        for item in entries:
            slot = item['recovery_slot_id']
            if db.execute('SELECT 1 FROM requests WHERE slot_id=? LIMIT 1',(slot,)).fetchone():
                raise ValueError('A called recovery identity cannot register again')
            old = db.execute('SELECT * FROM completion_attempts_v170 WHERE slot_id=?',(slot,)).fetchone()
            if old and (old['authority_sha256']!=authority_ref['sha256'] or old['entry_json']!=base.canonical(item)):
                raise ValueError('An independent identity amendment changed')
            db.execute('INSERT OR IGNORE INTO completion_attempts_v170 VALUES(?,?,?)',(slot,authority_ref['sha256'],base.canonical(item)))
    return {'version':VERSION,'authority':authority_ref,'registered_attempts':13,
        'additional_nominal_CNY':'50.00','start_threshold_CNY':'550.00',
        'historical_policy_and_requests_changed':False,'model_calls':0}


def completion_api(group_id, api, authority_ref):
    authority, entries = validate_authority(api, authority_ref)
    allowed = {r['recovery_slot_id']:r for r in entries if r['group_id']==group_id}
    if group_id != api.group_id:
        raise ValueError('Condition identity changed')

    class Ledger(api.BudgetLedger):
        def _entry(self, db, slot_id):
            expected = allowed.get(slot_id)
            if expected is None:
                raise ValueError('Only the finite authorized recovery identities may dispatch')
            row = db.execute('SELECT * FROM completion_attempts_v170 WHERE slot_id=?',(slot_id,)).fetchone()
            if (row is None or row['authority_sha256']!=authority_ref['sha256']
                    or row['entry_json']!=base.canonical(expected)):
                raise ValueError('The completion identity is not registered exactly')
            return expected

        def admit_team(self, slot_id):
            with self.transaction() as db:
                self._entry(db,slot_id)
                row=db.execute('SELECT * FROM team_start_grants_v170 WHERE slot_id=?',(slot_id,)).fetchone()
                if row and row['state']=='started':
                    return dict(row)
                if db.execute('SELECT 1 FROM requests WHERE slot_id=? LIMIT 1',(slot_id,)).fetchone():
                    raise ValueError('A paid team cannot restart as newly admitted')
                paid,held,start_holds,_=totals(db)
                if paid+held+start_holds+START_HOLD>THRESHOLD:
                    raise base.PreDispatchBudgetStopped('new_team_start_cash_threshold')
                if db.execute("SELECT 1 FROM metadata WHERE name='halted'").fetchone():
                    raise base.PreDispatchBudgetStopped('accounting_integrity_halt')
                stamp=base.now()
                db.execute('INSERT OR REPLACE INTO team_start_grants_v170 VALUES(?,?,?,?,?)',
                    (slot_id,'started',authority_ref['sha256'],stamp,paid+held+start_holds))
                db.execute('INSERT INTO team_start_events_v170(slot_id,kind,observed_utc) VALUES(?,?,?)',(slot_id,'started',stamp))
                return {'slot_id':slot_id,'started_utc':stamp,'state':'started'}

        def release_unentered(self, slot_id):
            with self.transaction() as db:
                self._entry(db,slot_id)
                if db.execute('SELECT 1 FROM requests WHERE slot_id=? LIMIT 1',(slot_id,)).fetchone():
                    raise ValueError('Cannot return a physically attempted team to the unentered queue')
                db.execute("UPDATE team_start_grants_v170 SET state='returned_unentered' WHERE slot_id=?",(slot_id,))
                db.execute('INSERT INTO team_start_events_v170(slot_id,kind,observed_utc) VALUES(?,?,?)',(slot_id,'returned_unentered',base.now()))

        def snapshot(self):
            with self.transaction() as db:
                paid,held,starts,inflight=totals(db)
            return {'version':VERSION,'settled_nanoyuan':paid,'reserved_or_unknown_nanoyuan':held,
                'new_team_start_hold_nanoyuan':starts,'remaining_nanoyuan':THRESHOLD-paid-held-starts,
                'admission_threshold_nanoyuan':THRESHOLD,'inflight_count':inflight,
                'over_threshold_nanoyuan':max(0,paid+held-THRESHOLD),
                'started_teams_continue':True,'cash_threshold_is_absolute_ceiling':False}

    # Reservation/settlement and token accounting are bound below. Only the
    # global monetary pre-dispatch rejection changes; token/call guards remain.
    return build_client_view(group_id, api, authority_ref, allowed, Ledger)


def build_client_view(group_id,api,authority_ref,allowed,Ledger):
    class BoundLedger(Ledger):
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
                admitted=db.execute('SELECT state,authority_sha256 FROM team_start_grants_v170 WHERE slot_id=?',(slot_id,)).fetchone()
                if admitted is None or admitted['state']!='started' or admitted['authority_sha256']!=authority_ref['sha256']:
                    raise base.PreDispatchBudgetStopped('team_has_no_actual_start_admission')
                # The user explicitly permits this started team to complete
                # above the monetary threshold. Keep every other bound below.
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
            self.ledger=BoundLedger()

    return SimpleNamespace(**{**vars(api),'VERSION':VERSION,'BudgetLedger':BoundLedger,'DeepSeekClient':Client,
        'completion_authority':authority_ref,'effective_start_threshold_nanoyuan':THRESHOLD,
        'base_cash_POLICY_is_unchanged':True,'started_teams_finish_above_threshold':True})
