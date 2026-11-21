"""Batch-local actor: same isolation, explicit revised public selector upload."""
from pathlib import Path
from .software_organization_actor_v211 import Actor as Prior
from .software_fixed_organization_clone_v131 import clone_function
R=Path(__file__).resolve().parents[2]
FILES={**Prior.start.__globals__['PUBLIC_FILES'],'public_test_library_sha256':R/'tools/public_test_library_v223_1.py'}
class Actor(Prior):
 start=clone_function(Prior.start,{**Prior.start.__globals__,'PUBLIC_FILES':FILES})
