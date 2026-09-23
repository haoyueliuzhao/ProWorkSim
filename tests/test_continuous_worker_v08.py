"""Public-only continuation must preserve real observations and exact work contexts."""

import pytest

from proworksim.continuous_worker import ContinuousWorker
from scripts.continuous_worker_experiment import GROUPS, run_group


@pytest.mark.parametrize("group", GROUPS)
def test_continuous_worker_real_session_protocol(tmp_path, group):
    result = run_group(tmp_path, group)
    assert result["error"] is None, result["error"]
    assert result["passed"], [check for check in result["checks"] if not check["passed"]]
    assert all(not check["not_executed"] for check in result["checks"])


def test_zero_budget_performs_no_port_access_and_is_not_waiting():
    class NoAccess:
        def tools(self):
            pytest.fail("Zero action budget accessed the port")

        observe = tools
        call = tools

    worker = ContinuousWorker({"A": NoAccess()}, run_id="zero")
    outcome = worker.run(max_actions=0)
    assert outcome["status"] == "budget_exhausted"
    assert outcome["actions"] == 0
    assert outcome["transcript"] == []
    with pytest.raises(ValueError, match="port labels"):
        ContinuousWorker({"B": NoAccess()}, checkpoint=worker.snapshot())


def test_negative_or_boolean_budgets_are_not_accepted():
    worker = ContinuousWorker({"A": object()})
    for budget in (-1, True, 1.5):
        with pytest.raises(ValueError, match="nonnegative integer"):
            worker.run(max_actions=budget)
