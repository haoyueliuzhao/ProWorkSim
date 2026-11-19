"""Generation and scoring have independent worker pools; no task-wide barrier."""
from concurrent.futures import ThreadPoolExecutor,Future
class SplitLanes:
 def __init__(self,generation=18,scoring=2):self.generate=ThreadPoolExecutor(max_workers=generation);self.score=ThreadPoolExecutor(max_workers=scoring)
 def submit(self,generate,score):
  final=Future();first=self.generate.submit(generate)
  def generated(f):
   try:value=f.result();second=self.score.submit(score,value)
   except BaseException as e:final.set_exception(e);return
   def scored(done):
    try:final.set_result(done.result())
    except BaseException as e:final.set_exception(e)
   second.add_done_callback(scored)
  first.add_done_callback(generated);return final
 def close(self):self.generate.shutdown(wait=True);self.score.shutdown(wait=True)
