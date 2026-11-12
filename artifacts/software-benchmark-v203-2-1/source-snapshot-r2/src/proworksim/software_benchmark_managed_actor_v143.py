"""Deployment-only identity; retain every frozen v141 managed operation and gate."""
from . import software_benchmark_managed_actor_v141 as frozen

globals().update({key: value for key, value in vars(frozen).items()
                  if not key.startswith('__') and key != 'previous'})
DEPLOYMENT_VERSION = 'v143-private-actor-v141-result-binding-r1'
