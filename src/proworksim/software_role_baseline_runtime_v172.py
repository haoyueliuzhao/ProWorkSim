"""Future controller binding: passive observer faults never block legal export.

The active v170 runtime remains frozen. No tool, prompt, organization, source
capture, provider accounting or generation policy changes are introduced here.
"""
from types import SimpleNamespace
from . import software_role_baseline_runtime_v167 as previous
from .software_collaboration_runtime_observer_v172 import RuntimeObservationBridge

VERSION = REPAIR_REVISION = 'v172-actual-controller-passive-observer-binding-r1'
prepare_case = previous.prepare_case
worker_config = previous.worker_config
worker_type = previous.worker_type
close_runtime = previous.close_runtime
lock_fixed_candidates = previous.lock_fixed_candidates
member_wire_tools = previous.member_wire_tools
build_runtime = previous.build_runtime
run_fragment = previous.run_fragment
prepare_schema_inventory = previous.prepare_schema_inventory

observed = SimpleNamespace(**vars(previous.observed))
observed.build_team_owner = previous._bind(previous._observed.build_team_owner,
    RuntimeObservationBridge=RuntimeObservationBridge)
build_team_owner = previous._bind(previous.build_team_owner, observed=observed)
