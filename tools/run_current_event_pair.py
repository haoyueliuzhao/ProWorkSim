"""Run new naturally captured pairs with the current review handoff and their registered live OSA."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_event_pairs_v243 as event
from proworksim import software_review_handoff_v243_1 as handoff
from proworksim.software_fixed_organization_clone_v131 import clone_function


def main():
    branch = clone_function(event.branch, {**event.branch.__globals__, "orders": handoff})
    launcher = event.previous.main
    clone_function(
        launcher,
        {
            **launcher.__globals__,
            "PLAN": event.PLAN,
            "RUN": event.RUN,
            "NS": event.NS,
            "__file__": __file__,
            "run_branch": branch,
        },
    )()


if __name__ == "__main__":
    main()
