"""Private actor binding: original isolation and repaired deadline, FREE2 substrate."""
import inspect,textwrap
from .software_organization_runtime_v204 import Actor as DeadlineActor
from .software_delegation_actor_v203_3_3_r2 import Actor as OriginalActor
source=textwrap.dedent(inspect.getsource(OriginalActor.start))
assert source.count("'REVIEW2'")==2
namespace=dict(OriginalActor.start.__globals__)
exec(compile(source.replace("'REVIEW2'","'FREE2'"),__file__+':dynamic-actor','exec'),namespace)
class Actor(DeadlineActor):
 start=namespace['start']
