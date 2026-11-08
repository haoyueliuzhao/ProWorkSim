"""The same locked candidate/delivery contract for unused original v157 slots.

No candidate selector, review rule, model-visible text or old identity is changed
by the host/controller lifecycle repair. Imported functions retain the exact
original implementations; only this new deployment references the contract.
"""
from .software_benchmark_project_closure_v157 import (
    VERSION,validate_slot_identity,validate_delivery_evidence,export_managed_closure,
)
DEPLOYMENT_VERSION='v159-same-candidate-and-delivery-contract-r1'
