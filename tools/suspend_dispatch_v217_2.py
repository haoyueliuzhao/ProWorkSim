"""Suspend only the known coordinator while holding the project's ledger gate.

This prevents freezing a SQLite write transaction. Model/scorer child processes
receive no signals and continue; stdout already points directly to their logs.
"""
import sqlite3,json,time,os,signal
from pathlib import Path
from proworksim.software_process_handoff_v217_2 import suspend,process
R=Path(__file__).resolve().parents[1];out=R/'artifacts/software-benchmark-v217/streaming-optimization-r1/handoff.json'
if out.exists():raise ValueError('Existing handoff cannot be replayed')
pid=1307553
with sqlite3.connect(R/'runs/software-benchmark-v211/budget700-r1/ledger.sqlite',timeout=60,isolation_level=None) as c:
 c.execute('BEGIN IMMEDIATE')
 try:snapshot=suspend(pid,R/'tools/resume_project_selection_v217_1.py')
 finally:c.rollback()
# Check process identities after exec transitions settle, without blocking any child.
time.sleep(.2)
from proworksim.software_process_handoff_v217_2 import children
snapshot['children']=children(pid);snapshot['sqlite_transaction_not_frozen']=True
out.write_text(json.dumps(snapshot,indent=2)+'\n')
print(json.dumps({'main_pid':pid,'children':len(snapshot['children']),'main_state':process(pid)['state'],'child_signals':0}))
