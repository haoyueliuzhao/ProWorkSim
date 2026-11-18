"""Same 700 CNY account, audit phases 63/189/189 plus 10 common preparation.

Complete state blocks only; remaining-token worst-price protection is global.
Started requests are not cash-interrupted. Prefix/generator costs stay physical
once and are included in every counterfactual's logical 5M task budget.
"""
from .software_organization_api_v211 import Ledger as Previous,Backend,DirectHTTPS,AdmissionStopped,CAP
PHASE_CAPS={'A':63_000_000_000,'B':189_000_000_000,'C':189_000_000_000,'prepare':10_000_000_000}
def estimate(slot,n):
 return min(n*8000,500_000_000 if ':GENERATOR' in slot else 2_000_000_000 if ':PREFIX' in slot else 10_500_000_000)
class Ledger(Previous):
 def __init__(self,path):
  super().__init__(path)
  with self.db() as c:c.execute('CREATE TABLE IF NOT EXISTS v216_phase_slots(slot TEXT PRIMARY KEY, phase TEXT NOT NULL, estimate INTEGER NOT NULL)')
 def phase_exposure(self,c,phase):
  rows=c.execute('SELECT s.status,p.estimate,COALESCE(SUM(r.cost),0) FROM v216_phase_slots p JOIN slots s ON p.slot=s.id LEFT JOIN requests r ON r.slot=s.id WHERE p.phase=? GROUP BY s.id',(phase,)).fetchall()
  pending=c.execute('SELECT p.estimate FROM block_slots b JOIN v216_phase_slots p ON p.slot=b.slot WHERE p.phase=? AND b.status="pending"',(phase,)).fetchall()
  return sum(cost if status=='closed' else max(held,cost) for status,held,cost in rows)+sum(x[0] for x in pending)
 def reserve_block(self,block,slots,phase='A'):
  if phase not in PHASE_CAPS or not slots or any(not s.startswith('v216:') or type(n)!=int or not 0<n<=5_000_000 for s,n in slots.items()):raise ValueError('New complete state block required')
  with self.db() as c:
   if any(c.execute('SELECT 1 FROM block_slots WHERE slot=?',(s,)).fetchone() for s in slots):raise ValueError('Identity already consumed')
   if self.phase_exposure(c,phase)+sum(estimate(s,n) for s,n in slots.items())>PHASE_CAPS[phase]:raise AdmissionStopped('Phase estimate: stop next complete block or wait for settlement')
   if self.exposure(c)[1]+sum(n*8000 for n in slots.values())>CAP:raise AdmissionStopped('Global remaining-token worst-price bound')
   c.executemany('INSERT INTO block_slots VALUES (?,?,?,?)',[(s,block,n,'pending') for s,n in slots.items()]);c.executemany('INSERT INTO v216_phase_slots VALUES (?,?,?)',[(s,phase,estimate(s,n)) for s,n in slots.items()])
 def admit(self,slot,limit):
  super().admit(slot,limit)
  with self.db() as c:c.execute('UPDATE slots SET hold=? WHERE id=?',(estimate(slot,limit),slot))
 def snapshot(self):
  v=super().snapshot()
  with self.db() as c:phases={p:{'estimated_start_line_CNY':cap/1e9,'estimated_exposure_CNY':self.phase_exposure(c,p)/1e9} for p,cap in PHASE_CAPS.items()}
  return {**v,'version':'v216-shared700-audit-phases-r1','new_phase_estimates':phases,'phase_estimated_start_line_CNY':None,'old_cost_retained':True}
