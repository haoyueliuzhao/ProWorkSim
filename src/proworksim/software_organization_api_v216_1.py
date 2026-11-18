"""Repair-stage allocation: A plus common preparation share their original 73 CNY.

Global700 and the later189/189 lines do not increase. All v216 initial failures
remain charged in this combined stage; prior attempts are never erased.
"""
from .software_organization_api_v216 import Ledger as Prior,Backend,DirectHTTPS,AdmissionStopped,CAP
CAPS={'A_and_prepare':73_000_000_000,'B':189_000_000_000,'C':189_000_000_000}
def estimate(slot,n):return min(n*8000,6_600_000_000 if ':PREFIX' in slot else 200_000_000 if ':GENERATOR' in slot else 10_500_000_000)
class Ledger(Prior):
 def phase_exposure(self,c,phase):
  phases=('A','prepare','A_and_prepare') if phase=='A_and_prepare' else (phase,)
  return sum(super(Ledger,self).phase_exposure(c,p) for p in phases)
 def reserve_block(self,block,slots,phase='A'):
  phase='A_and_prepare' if phase in ('A','prepare','A_and_prepare') else phase
  if phase not in CAPS or not slots or any(not s.startswith('v216:r2-') or type(n)!=int or not 0<n<=5_000_000 for s,n in slots.items()):raise ValueError('New repair identity/complete block required')
  with self.db() as c:
   if any(c.execute('SELECT 1 FROM block_slots WHERE slot=?',(s,)).fetchone() for s in slots):raise ValueError('Identity already consumed')
   if self.phase_exposure(c,phase)+sum(estimate(s,n) for s,n in slots.items())>CAPS[phase]:raise AdmissionStopped('Combined A+prepare line, no new complete block')
   if self.exposure(c)[1]+sum(n*8000 for n in slots.values())>CAP:raise AdmissionStopped('Global worst-price bound')
   c.executemany('INSERT INTO block_slots VALUES(?,?,?,?)',[(s,block,n,'pending') for s,n in slots.items()]);c.executemany('INSERT INTO v216_phase_slots VALUES(?,?,?)',[(s,phase,estimate(s,n)) for s,n in slots.items()])
 def admit(self,slot,limit):
  super().admit(slot,limit)
  with self.db() as c:c.execute('UPDATE slots SET hold=? WHERE id=?',(estimate(slot,limit),slot))
 def snapshot(self):
  v=super().snapshot()
  with self.db() as c:phases={p:{'estimated_start_line_CNY':n/1e9,'estimated_exposure_CNY':self.phase_exposure(c,p)/1e9} for p,n in CAPS.items()}
  return {**v,'version':'v216.1-same700-combined-A-preparation-r1','new_phase_estimates':phases,'cash_cap_increased':False}
