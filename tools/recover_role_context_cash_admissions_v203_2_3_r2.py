"""Explicitly reopen only proven zero-provider closed holds in the same CNY130 ledger."""
import json,sqlite3,time
from proworksim import software_benchmark_scope_v203_2_3_r2 as scope
from proworksim.software_benchmark_candidates_v054 import reference


def recover():
    scope.require_runtime_gate()
    proof=scope.load(reference(scope.ARTIFACT_ROOT/'zero-provider-redeployment-r2/evidence.json'))
    expected=proof['team_admissions']
    folder=scope.ARTIFACT_ROOT/'zero-provider-redeployment-r2'
    backup=folder/'ledger-before-admission-recovery.sqlite'
    receipt=folder/'cash-admission-recovery.json'
    if receipt.exists():raise PermissionError('Never replay admission recovery')
    with sqlite3.connect(scope.LEDGER_FILE) as db:
        if db.execute('SELECT COUNT(*) FROM requests').fetchone()[0]:raise PermissionError('A provider-consumed account cannot reopen')
        rows=[list(row) for row in db.execute('SELECT slot_id,state FROM team_admissions ORDER BY slot_id')]
        if rows!=expected or any(state!='closed' for _,state in rows):raise PermissionError('Closed hold evidence changed')
        if backup.exists():raise PermissionError('An admission backup already exists; inspect before repeating')
        with sqlite3.connect(backup) as dst:db.backup(dst)
        db.execute('BEGIN IMMEDIATE')
        if db.execute('SELECT COUNT(*) FROM requests').fetchone()[0]:raise PermissionError('Provider requests appeared during recovery')
        db.execute("INSERT INTO metadata(name,value) VALUES(?,?)",('zero_provider_redeployment_r2',json.dumps({'plan':reference(scope.PLAN_FILE),'prior_closed_admissions':rows,'unix':time.time(),'additional_cash_CNY':'0.00'})))
        db.execute("DELETE FROM team_admissions WHERE state='closed'")
        db.commit()
    result={'version':'v203.2.3-zero-provider-admission-recovery-r2','passed':True,'same_ledger':str(scope.LEDGER_FILE),
        'before':reference(backup),'prior_closed_admissions':expected,'provider_requests':0,'new_API_budget_CNY':'0.00',
        'same_existing_authority':reference(scope.BUDGET_BASELINE_FILE),'plan':reference(scope.PLAN_FILE)}
    return scope.retain(receipt,result)

if __name__=='__main__':print(json.dumps(recover()))
