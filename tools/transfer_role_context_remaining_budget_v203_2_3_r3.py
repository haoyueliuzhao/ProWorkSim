"""Retire the spent parent account and transfer only its unspent authorization."""
from __future__ import annotations
from decimal import Decimal
import fcntl,json,sqlite3,time
from pathlib import Path
from proworksim import software_benchmark_scope_v203_2_3_r2 as previous
from proworksim.software_benchmark_candidates_v054 import reference,write_new

ROOT=previous.ROOT
OUT=previous.ARTIFACT_ROOT/'cash-handoff-r3'
CHILD=ROOT/'runs/software-benchmark-v203-2-3/role-context-recovery12-r3/ledgers/recovery.sqlite'
VERSION='v203.2.3-single-remaining-allowance-transfer-r3'


def transfer():
    if (OUT/'handoff.json').exists():raise PermissionError('Budget transfer already completed; no duplicate allowance')
    if CHILD.exists():raise PermissionError('Child account must not exist before the parent is retired')
    final=previous.load(reference(previous.API_ROOT/'coordinator-finalization.json'))
    if final['cleanup_errors'] or not previous.load(final['coordinator_release'])['released']:
        raise PermissionError('Parent coordinator cleanup is not complete')
    if list((previous.BATCH_ROOT/'resource-claims').glob('active-*.json')):
        raise PermissionError('Parent owned resources remain active')
    OUT.mkdir(parents=True,exist_ok=True)
    with (OUT/'transfer.lock').open('a+b') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        with sqlite3.connect(previous.LEDGER_FILE) as db:
            db.row_factory=sqlite3.Row
            rows=[dict(r) for r in db.execute('SELECT request_id,slot_id,status,reserved_nanoyuan,settled_nanoyuan,usage_json FROM requests ORDER BY request_id')]
            admissions=[dict(r) for r in db.execute('SELECT slot_id,state FROM team_admissions ORDER BY slot_id')]
            policy=json.loads(db.execute("SELECT value FROM metadata WHERE name='policy'").fetchone()[0])
            if db.execute("SELECT 1 FROM metadata WHERE name IN ('halted','superseded_by_recovery_r3')").fetchone():
                raise PermissionError('Existing halt/transfer requires explicit inspection, never an implicit second grant')
            if len(rows)!=48 or any(r['status']!='settled' for r in rows) or any(r['state']!='closed' for r in admissions):
                raise PermissionError('The known 48 fully settled calls and closed teams changed')
            if policy['cap_nanoyuan']!=130_000_000_000:raise PermissionError('Original authorization differs from CNY130')
            settled=sum(r['settled_nanoyuan'] for r in rows if r['status']=='settled')
            uncertain=sum(r['reserved_nanoyuan'] for r in rows if r['status']!='settled')
            remaining=policy['cap_nanoyuan']-settled-uncertain
            if remaining<=0:raise PermissionError('No remaining authorized allowance')
            backup=OUT/'parent-ledger-before-halt.sqlite'
            if backup.exists():raise PermissionError('Existing backup means this transfer needs recovery inspection')
            with sqlite3.connect(backup) as snapshot:db.backup(snapshot)
            quote={'version':VERSION,'parent_ledger':str(previous.LEDGER_FILE),'child_ledger':str(CHILD),
                'original_cap_nanoyuan':policy['cap_nanoyuan'],'parent_settled_nanoyuan':settled,
                'parent_uncertain_reserved_nanoyuan':uncertain,'child_cap_nanoyuan':remaining,
                'child_cap_CNY':str(Decimal(remaining)/10**9),'additional_budget_CNY':'0.00',
                'parent_calls_preserved':len(rows),'parent_tokens_preserved':sum(json.loads(r['usage_json'])['total_tokens'] for r in rows),
                'parent_requests':rows,'parent_admissions':admissions,'parent_backup':reference(backup),
                'parent_finalization':reference(previous.API_ROOT/'coordinator-finalization.json'),
                'authority_source':'User authorized recovery/retesting for system errors under the same total CNY130. This retires the old spending route and creates only the remaining allowance.',
                'handoff_not_budget_reset':True,'observed_unix':time.time()}
            intent=write_new(OUT/'intent.json',quote)
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT COUNT(*) FROM requests').fetchone()[0]!=len(rows):raise PermissionError('Parent requests changed during transfer')
            halted=json.dumps({'reason':'parent_retired_for_independent_recovery_r3','handoff_intent':intent,'child_ledger':str(CHILD)},sort_keys=True)
            db.execute("INSERT INTO metadata(name,value) VALUES('halted',?)",(halted,))
            db.execute("INSERT INTO metadata(name,value) VALUES('superseded_by_recovery_r3',?)",(json.dumps(quote,sort_keys=True),))
            db.commit()
            confirmed=db.execute("SELECT value FROM metadata WHERE name='halted'").fetchone()[0]
            if confirmed!=halted:raise RuntimeError('Parent spending halt did not persist')
        result={**quote,'intent':intent,'parent_halted':True,'parent_request_rows_deleted':0,
            'parent_closed_admissions_deleted':0,'child_created':False,'conservation_verified':True}
        return write_new(OUT/'handoff.json',result)


if __name__=='__main__':print(json.dumps(transfer()))
