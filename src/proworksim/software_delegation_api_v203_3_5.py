"""Empirical start-only cash admission; unchanged token and provider accounting.

Old records and nominal 80 CNY authority stay intact. Active cost is counted
once, at max(actual+uncertain request exposure, estimated slot cost).
"""
from .software_delegation_api_v203_3_3 import Ledger as OriginalLedger,Backend,DirectHTTPS,AdmissionStopped,CAP
VERSION='v203.3.5-empirical-start-only-950-r1'
ESTIMATE=9_500_000_000

def exposure(connection):
 rows=connection.execute('SELECT s.id,s.status,s.hold,COALESCE(SUM(r.cost),0) FROM slots s LEFT JOIN requests r ON r.slot=s.id GROUP BY s.id').fetchall()
 return sum(cost if status=='closed' else max(hold,cost) for _,status,hold,cost in rows)

def fits(connection):return exposure(connection)+ESTIMATE<=CAP

class Ledger(OriginalLedger):
 def admit(self,slot,limit):
  if type(limit)!=int or not 0<limit<=5_000_000:raise ValueError('Bad slot token ceiling')
  with self.db() as c:
   if c.execute('SELECT 1 FROM slots WHERE id=?',(slot,)).fetchone():raise ValueError('Slot may not silently restart')
   if not fits(c):raise AdmissionStopped('Insufficient start-only empirical cash admission')
   c.execute('CREATE TABLE IF NOT EXISTS cash_admission_revisions (slot TEXT PRIMARY KEY,version TEXT,estimate INTEGER,nominal_cap INTEGER,started_not_cash_interrupted INTEGER)')
   c.execute('INSERT INTO cash_admission_revisions VALUES (?,?,?,?,1)',(slot,VERSION,ESTIMATE,CAP))
   c.execute('INSERT INTO slots VALUES (?,?,?,?)',(slot,limit,'active',ESTIMATE))
 def snapshot(self):
  result=super().snapshot()
  with self.db() as c:value=exposure(c)
  result.update(cash_policy_version=VERSION,cap_is_new_start_line=True,estimated_start_CNY=ESTIMATE/1e9,
   admission_exposure_CNY=value/1e9,over_nominal_CNY=max(0,result['peak_cost_upper_CNY']-80),
   estimate_is_cost_guarantee=False,started_slot_cash_cutoff=False)
  return result
