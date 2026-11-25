"""Use the passive v245.2 intake from a separately budgeted ordinary evaluation job.

Called by an existing ordinary scheduler after it reserves the job's own slot.
There is no model or container launch at import and no prospective-pair budget.
"""

from pathlib import Path
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_ordinary_successor_v243_2 as ordinary
from proworksim.software_benchmark_candidates_v054 import checked
from proworksim.software_fair_delivery_v245 import Execution
from proworksim.software_fair_intake_v245 import BANK, observe_ordinary
from proworksim.software_fixed_organization_clone_v131 import clone_function
from proworksim.software_prefix_resume_v243_2 import release_on_ordinary_entry
from proworksim.storage import read_json


def generate_registered(registration_file, case, slot):
    path = Path(registration_file).resolve()
    if path.parent != BANK / "ordinary-registrations":
        raise ValueError("Expected a prospective ordinary registration")
    reg = read_json(path)
    task = read_json(checked(reg["task"]))
    authority = checked(reg["authority"])
    if (
        task["instance_id"] != case["instance"]
        or reg["instance"] != case["instance"]
        or reg["source"] != "ordinary"
    ):
        raise ValueError("Registered task and ordinary continuation differ")
    out = Path(reg["job_root"])

    def fragment(prepared, rt, *, registration, **kwargs):
        release_on_ordinary_entry(rt, kwargs["folder"])
        return observe_ordinary(prepared, rt, registration_file=path, **kwargs)

    # Both ordinary jobs and the paired regression use the same managed world.
    launcher = SimpleNamespace(
        paired=SimpleNamespace(
            prior=SimpleNamespace(paired=SimpleNamespace(EvidenceFollowupExecution=Execution))
        )
    )
    fn = clone_function(
        ordinary.generate,
        {
            **ordinary.generate.__globals__,
            "AUTH": authority,
            "native": launcher,
            "run_worker_fragment": fragment,
        },
    )
    return fn(dict(case=case, slot=slot, task=task, limit=5_000_000), out)
