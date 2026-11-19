import threading
from proworksim.software_streaming_lanes_v217_2 import SplitLanes

def test_scoring_does_not_hold_generation_lane():
 lanes=SplitLanes(generation=1,scoring=1);blocked=threading.Event();release=threading.Event();next_generated=threading.Event()
 def score_first(x):blocked.set();assert release.wait(5);return x
 first=lanes.submit(lambda:1,score_first);assert blocked.wait(2)
 def next_gen():next_generated.set();return 2
 second=lanes.submit(next_gen,lambda x:x)
 try:assert next_generated.wait(2) and not first.done()
 finally:release.set();lanes.close()
 assert first.result()==1 and second.result()==2

def test_one_failed_generation_does_not_cancel_other_panel():
 lanes=SplitLanes(2,1)
 def failed():raise ValueError('isolated generation')
 first=lanes.submit(failed,lambda x:x);second=lanes.submit(lambda:'healthy',lambda x:x);lanes.close()
 assert isinstance(first.exception(),ValueError) and second.result()=='healthy'
