from types import SimpleNamespace
import pytest
from proworksim.software_score_fixture_recovery_v217_3 import apply_fixture_reset,FIXTURE,INSTANCE
class Spec:
 def __init__(self,s):self.eval_script_list=[s]
 @property
 def eval_script(self):return '\n'.join(self.eval_script_list)
def test_exact_official_added_fixture_only():
 s=f'diff --git a/{FIXTURE} b/{FIXTURE}\nnew file mode 100644\nindex 000..123\n--- /dev/null\n+++ b/{FIXTURE}\n@@ -0,0 +1 @@\n+x\n'
 spec=Spec(s);proof=apply_fixture_reset(spec,{'instance_id':INSTANCE})
 assert spec.eval_script_list[1:]==[s]
 assert spec.eval_script_list[0]=='cd /testbed && rm -f -- '+FIXTURE
 assert not proof['locked_candidate_modified']
@pytest.mark.parametrize('iid,script',[(INSTANCE,'unrelated'),('other','anything'),(INSTANCE,f'diff --git a/{FIXTURE} b/{FIXTURE}\n--- a/{FIXTURE}\n+++ b/{FIXTURE}\n')])
def test_reject_unbound_fixture(iid,script):
 with pytest.raises(ValueError):apply_fixture_reset(Spec(script),{'instance_id':iid})
