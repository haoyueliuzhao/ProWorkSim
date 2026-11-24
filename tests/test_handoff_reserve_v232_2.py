from types import SimpleNamespace
from pathlib import Path
import sys
from proworksim.software_graph_execution_v230 import CALL_BOUND
from proworksim.software_handoff_v232_2 import ProtectedHandoffExecution


def test_last_real_sphinx_window_keeps_room_for_the_correction():
    agent = "member_002"
    e = ProtectedHandoffExecution.__new__(ProtectedHandoffExecution)
    e.pending_task = "work_root"
    e.diagnostician = agent
    e.hold = ("handoff_contingency", agent)
    e.grants = [e.hold]
    e.native_limit = 5_000_000 - 1910
    e.example_sent = True
    # The actual r1 release window, before ordinary opportunity 79.
    used = e.native_limit - 237240
    budget = SimpleNamespace(native_allocation=e.native_limit)
    budget.snapshot = lambda: {"available_tokens": budget.native_allocation - used}
    world = SimpleNamespace(
        protocol=lambda: {"graph_control": {"duties": {"work_root": {"status": "pending"}}}},
        organization_active_members=lambda: ["member_001", agent],
    )
    e.runtime = SimpleNamespace(
        prepared=SimpleNamespace(world=world),
        team_budget=budget,
        stopped={},
        waiting={},
        work_ended={},
        sync_members=lambda: None,
        schedule=SimpleNamespace(choose=lambda choices: {"member": next(iter(choices))}),
        labels=["member_001", agent],
    )
    assert e.select_next() == {"member": agent}
    assert budget.snapshot()["available_tokens"] == 237240 - CALL_BOUND and e.grants == [e.hold]
    e.normal_select = lambda: None
    e.runtime.waiting[agent] = True
    assert e.select_next() is None and e.grants == [e.hold]
    assert budget.snapshot()["available_tokens"] == 237240 - CALL_BOUND


def test_corrected_reserve_uses_real_sdk_for_success_repair_and_exhaustion(tmp_path, monkeypatch):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
    import check_handoff_v232_1 as control
    from proworksim.software_fixed_organization_clone_v131 import clone_function

    for name, val in {
        "LITELLM_LOCAL_MODEL_COST_MAP": "True",
        "OPENHANDS_SUPPRESS_BANNER": "1",
        "HF_HUB_OFFLINE": "1",
        "PYTHON_DOTENV_DISABLED": "1",
    }.items():
        monkeypatch.setenv(name, val)
    exercise = clone_function(
        control.exercise,
        {**control.exercise.__globals__, "HandoffExecution": ProtectedHandoffExecution},
    )
    for name, repair, accepted in [("clean", 0, 1), ("repair", 1, 1), ("twice", 1, 0)]:
        monkeypatch.setenv("OH_PERSISTENCE_DIR", str(tmp_path / name / "sdk-settings"))
        row = exercise(tmp_path / name, name)
        assert (row["repair_dispatches"], row["real_handoffs"]) == (repair, accepted)
