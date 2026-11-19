"""Score-side reset of the one verified hidden-test fixture collision.

Never alter the locked prediction or solver workspace. The official test patch
owns this newly introduced fixture; its content is installed by the official
script after this reset. No other candidate path is touched.
"""
import re
FIXTURE='tests/roots/test-ext-autodoc/target/empty_all.py'
INSTANCE='sphinx-doc__sphinx-8595'
def apply_fixture_reset(spec,instance):
 if instance['instance_id']!=INSTANCE:raise ValueError('Only the audited instance')
 script=spec.eval_script
 pattern=r'diff --git a/'+re.escape(FIXTURE)+r' b/'+re.escape(FIXTURE)+r'\nnew file mode [0-7]+\n(?:(?!diff --git)[\s\S])*?--- /dev/null\n\+\+\+ b/'+re.escape(FIXTURE)+r'\n'
 if not re.search(pattern,script):raise ValueError('Official newly added fixture not verified')
 # A fresh, network-isolated container with no host bindings owns this path.
 command='cd /testbed && rm -f -- '+FIXTURE
 spec.eval_script_list.insert(0,command)
 return {'revision':'v217.3-official-test-fixture-collision','path':FIXTURE,'operation':'remove exact fixture before unchanged official test patch','official_script_suffix_unchanged':spec.eval_script_list[1:],'locked_candidate_modified':False,'solver_feedback':False}
