"""Current ProWorkSim organization harness for new policy studies and managed deployments."""

from .software_context_v232 import DEFAULT_CONTEXT
from .software_organization_v232 import OrganizationExecution


def run_worker_fragment(prepared, runtime, *, source="ordinary", **kwargs):
    """Run the existing Worker schedule with a zero-call observer on settled opportunities."""
    if source == "ordinary":
        from .software_event_intake_v243 import run_ordinary
        from .software_prefix_resume_v243_2 import release_on_ordinary_entry

        release_on_ordinary_entry(runtime, kwargs.get("folder"))

        return run_ordinary(prepared, runtime, **kwargs)
    from .software_event_harness_v243 import run_worker_fragment as observed

    return observed(prepared, runtime, source=source, **kwargs)


__all__ = ["DEFAULT_CONTEXT", "OrganizationExecution", "run_worker_fragment"]
