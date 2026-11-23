"""Atomic panel admission for explicitly authorized anomaly pilots, in nanoyuan."""
from pathlib import Path
from .software_organization_api_v204 import Ledger, AdmissionStopped

class AnomalyLedger(Ledger):
    def __init__(self,path,*,stage,stage_cny):
        if stage not in ('v227','v228') or not isinstance(stage_cny,int) or stage_cny<=0:raise ValueError('Explicit stage authority required')
        self.path=Path(path)
        if not self.path.is_file():raise ValueError('Existing shared ledger required')
        self.stage=stage
        self.stage_cap=stage_cny*10**9

    def reserve_panel(self,block,token_limits):
        if not token_limits or any(not s.startswith(self.stage+':') or type(n)!=int or not 0<n<=5_000_000 for s,n in token_limits.items()):
            raise ValueError('Each branch requires its frozen stage ID and remaining budget')
        def exposure(db,pattern):
            rows=db.execute('SELECT s.status,s.token_limit,COALESCE(sum(r.cost),0),COALESCE(sum(CASE WHEN r.status="settled" THEN r.tokens ELSE 0 END),0),COALESCE(sum(CASE WHEN r.status="settled" THEN r.cost ELSE 0 END),0) FROM slots s LEFT JOIN requests r ON r.slot=s.id WHERE s.id GLOB ? GROUP BY s.id',(pattern,))
            cost=sum(c if status=='closed' else max(c,paid+max(0,n-used)*8000) for status,n,c,used,paid in rows)
            pending=db.execute('SELECT coalesce(sum(token_limit),0) FROM block_slots WHERE slot GLOB ? AND status="pending"',(pattern,)).fetchone()[0]
            return cost+pending*8000
        with self.db() as db:
            if db.execute("SELECT value FROM meta WHERE key='cap'").fetchone()!=('1100000000000',):raise ValueError('Unexpected shared authority')
            if any(db.execute('SELECT 1 FROM block_slots WHERE slot=?',(s,)).fetchone() for s in token_limits):raise ValueError('Consumed run identity')
            additional=sum(token_limits.values())*8000
            if exposure(db,'*')+additional>1100*10**9 or exposure(db,self.stage+':*')+additional>self.stage_cap:
                raise AdmissionStopped('Full task block exceeds available stage or shared allowance')
            db.executemany("INSERT INTO block_slots VALUES(?,?,?,'pending')",[(s,block,n) for s,n in token_limits.items()])
