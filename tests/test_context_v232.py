import json
import pytest
from proworksim.software_context_builder_v230 import compact, recover_observations
from proworksim.software_context_v232 import checked_context, restore_delta, source_estimates
from proworksim.software_organization_v232 import visibility


def wire():
    obs = [
        {"actor_id": "member_001", "n": 0, "remove": True},
        {"actor_id": "member_001", "n": 1},
        {"actor_id": "member_001", "n": 2},
    ]
    return {
        "tools": [],
        "messages": [{"role": "system", "content": "worker"}]
        + [{"role": "user", "content": compact({"observation": d})} for d in obs],
    }


def test_checkpoint_delete_periodic_digest_and_graph():
    raw = wire()
    shown, meta = checked_context(raw, "member_001", "worker", 2, interval=2)
    assert recover_observations(raw) == recover_observations(shown)
    a, b, c = meta["snapshots"]
    assert a["full"] == "new_history" and b["base"] == 1 and c["full"] == "periodic"
    d = json.loads(shown["messages"][2]["content"])["observation_delta"]
    assert (
        d["removed"] == ["remove"]
        and json.loads(shown["messages"][3]["content"])["active_organization_version"] == 2
    )
    with pytest.raises(ValueError, match="Wrong snapshot"):
        restore_delta({}, d, "member_001", 1, a["version"], {})
    with pytest.raises(ValueError, match="private"):
        checked_context(raw, "member_002", "worker", 2)


def test_drift_recovers_full_and_summary_reanchors():
    r = wire()
    r["messages"][2]["content"] = compact(
        {"observation": {"actor_id": "member_001", "n": False, "remove": True}}
    )
    r["messages"].insert(3, {"role": "user", "content": "[Derived private history summary]"})
    out, m = checked_context(r, "member_001", "worker", 1)
    assert [v["full"] for v in m["snapshots"]] == ["new_history", "recovery_full", "new_history"]
    assert type(json.loads(out["messages"][2]["content"])["observation"]["n"]) is bool


def test_reference_read_requires_success_and_a_real_receipt():
    tool = {"id": "a", "function": {"name": "read_work_event", "arguments": '{"sequence":3}'}}
    r = {
        "messages": [
            {"role": "assistant", "tool_calls": [tool]},
            {"role": "tool", "tool_call_id": "a", "content": '{"ok":false}'},
            {"role": "user", "content": 'Work observation: {"evidence":{"E1":{"command_id":"c"}}}'},
        ]
    }
    idx = visibility(r, [{"sequence": 3, "operation_id": "c"}, {"sequence": 4}])
    assert (
        idx["operation_linked_sequences"] == [3]
        and idx["without_direct_identifier"] == [4]
        and not idx["successful_readbacks_present"]
    )
    assert source_estimates(r, "worker", len)["anomaly"] > 0
