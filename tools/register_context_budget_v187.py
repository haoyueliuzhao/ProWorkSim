"""Register the user's50-CNY increase once; no model or container operation."""
import json
from datetime import datetime,timezone,timedelta
from proworksim.software_context_cash_v187 import ROOT,LEDGER,AUTHORITY,VERSION,AMENDMENT,BASE,ADDED,CAP,register
from proworksim.software_benchmark_candidates_v054 import write_new,reference

if __name__=='__main__':
    AUTHORITY.parent.mkdir(parents=True,exist_ok=True)
    if not AUTHORITY.exists():
        write_new(AUTHORITY,{'version':VERSION,'approved':True,'amendment_id':AMENDMENT,
            'user_instruction':'允许追加50元预算完成任务','ledger':str(LEDGER),
            'previous_cap_nanoyuan':BASE,'added_nanoyuan':ADDED,'effective_cap_nanoyuan':CAP,
            'recorded_at':datetime.now(timezone(timedelta(hours=8))).isoformat(),
            'cash_gate':'new_task_admission_only','already_started_tasks_finish':True,
            'same_original60_attempts':True,'automatic_extra_resampling':False})
    value=register()
    target=AUTHORITY.parent/'registration.json'
    if not target.exists():write_new(target,value)
    print(json.dumps(value,ensure_ascii=False))
