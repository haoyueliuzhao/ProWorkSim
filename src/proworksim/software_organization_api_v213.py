"""Reuse authorized 700 CNY ledger; separate new-stage admission accounting.

Paid requests retain the global worst-price protection. Phase estimates decide only
new complete blocks; no cash interruption of already admitted slots.
"""
from .software_organization_api_v211 import Ledger as Previous,Backend,DirectHTTPS,AdmissionStopped,CAP,ESTIMATE
PHASE_CAPS={'A2':70_000_000_000}
class Ledger(Previous):
 def __init__(self,path):
  super().__init__(path)
  with self.db() as c:c.execute('CREATE TABLE IF NOT EXISTS v213_phase_slots(slot TEXT PRIMARY KEY, phase TEXT NOT NULL)')
 def phase_exposure(self,c,phase):
  rows=c.execute('SELECT s.status,s.hold,COALESCE(SUM(r.cost),0) FROM v213_phase_slots p JOIN slots s ON p.slot=s.id LEFT JOIN requests r ON r.slot=s.id WHERE p.phase=? GROUP BY s.id',(phase,)).fetchall()
  pending=c.execute('SELECT b.token_limit FROM block_slots b JOIN v213_phase_slots p ON p.slot=b.slot WHERE p.phase=? AND b.status="pending"',(phase,)).fetchall()
  return sum(cost if status=='closed' else max(hold,cost) for status,hold,cost in rows)+sum(min(ESTIMATE,n*8000) for (n,) in pending)
 def reserve_block(self,block,slots,phase='A2'):
  if phase not in PHASE_CAPS or not slots or any(not s.startswith('v213:') or type(n)!=int or not 0<n<=5_000_000 for s,n in slots.items()):raise ValueError('Explicit new-stage whole block required')
  with self.db() as c:
   if any(c.execute('SELECT 1 FROM block_slots WHERE slot=?',(s,)).fetchone() for s in slots):raise ValueError('Identity already consumed')
   if self.phase_exposure(c,phase)+sum(min(ESTIMATE,n*8000) for n in slots.values())>PHASE_CAPS[phase]:raise AdmissionStopped('New phase estimate exhausted; wait for complete block refunds')
   if self.exposure(c)[1]+sum(n*8000 for n in slots.values())>CAP:raise AdmissionStopped('Global worst-price protection: wait')
   c.executemany('INSERT INTO block_slots VALUES (?,?,?,?)',[(s,block,n,'pending') for s,n in slots.items()])
   c.executemany('INSERT INTO v213_phase_slots VALUES (?,?)',[(s,phase) for s in slots])
 def snapshot(self):
  v=super().snapshot()
  with self.db() as c:phases={p:{'estimated_start_line_CNY':cap/1e9,'estimated_exposure_CNY':self.phase_exposure(c,p)/1e9} for p,cap in PHASE_CAPS.items()}
  return {**v,'version':'v213-shared700-phased-r1','new_phase_estimates':phases,'phase_estimated_start_line_CNY':None,'v211_cost_retained':True}
