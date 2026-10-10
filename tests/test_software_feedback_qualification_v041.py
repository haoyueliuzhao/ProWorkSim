"""Gate integrity controls only; real tokenizer/SDK routes run once as P0-B/C."""
import copy
import json

from scripts import software_feedback_qualification_v041 as qualification


def completed_control_rows():
    rows = []
    for spec in qualification.configuration_inventory() + qualification.representative_inventory():
        names = (qualification.CORE_REQUIRED_STAGES if spec["kind"] == "core"
                 else qualification.REPRESENTATIVE_REQUIRED_STAGES[spec["kind"]])
        rows.append({**spec, "passed": True, "stages": [{"stage": name,
            "fits": True, "context_limit": 16384, "reserved_output_tokens": 2048,
            "prompt_tokens": 13336, "headroom_tokens": 1000,
            "feedback_invariants": dict.fromkeys(qualification.INVARIANT_KEYS, True)} for name in sorted(names)]})
    return rows


def test_gate_requires_all_sixteen_shapes_and_each_full_feedback_route():
    rows = completed_control_rows()
    assert len(qualification.configuration_inventory()) == 16
    assert qualification.qualification_gate(rows)["passed"] is True
    missing = copy.deepcopy(rows)
    missing[0]["stages"] = [row for row in missing[0]["stages"] if row["stage"] != "after_failed_public_tests"]
    assert qualification.qualification_gate(missing)["passed"] is False
    assert qualification.qualification_gate(rows[:-1])["passed"] is False
    assert qualification.qualification_gate(rows + rows[:1])["passed"] is False
    rows[0]["member"] = "a_different_member"
    assert qualification.qualification_gate(rows)["passed"] is False


def test_gate_rejects_overflow_changed_feedback_and_incomplete_representatives():
    for mutation in ("overflow", "feedback", "empty_invariants", "missing_representative_stage"):
        rows = completed_control_rows()
        if mutation == "overflow":
            rows[0]["stages"][0].update(prompt_tokens=14337, headroom_tokens=-1)
        elif mutation == "feedback":
            rows[0]["stages"][0]["feedback_invariants"]["latest_complete_visible_round_exact"] = False
        elif mutation == "empty_invariants":
            rows[0]["stages"][0]["feedback_invariants"] = {}
        else:
            rows[-1]["stages"] = []
        assert qualification.qualification_gate(rows)["passed"] is False


def test_feedback_checks_cannot_replace_latest_fact_or_drop_real_tool_failure():
    observation = {"role_task": "full instruction", "observation": {"contract": "full contract",
        "root_goal": {"description": "full contract"}, "initial_diagnostics": [{"id": "owned-initial"}],
        "tasks": [{"revision": 2}]}}
    request = {"max_tokens": 2048, "tools": [{"actual": "tool schema"}], "messages": [
        {"role": "system", "content": "original system"},
        {"role": "assistant", "content": None, "tool_calls": [{"id": "actual", "function": {"name": "run_tests"}}]},
        {"role": "tool", "tool_call_id": "actual", "content": '{"passed": false, "visible": "entire failure"}'},
        {"role": "user", "content": json.dumps(observation)}]}
    selected = copy.deepcopy(request)
    del observation["observation"]["root_goal"]["description"]
    selected["messages"][-1]["content"] = json.dumps(observation)
    assert all(qualification.feedback_invariants(request, selected).values())
    selected["messages"][2]["content"] = '{"passed": false}'
    assert qualification.feedback_invariants(request, selected)["latest_complete_visible_round_exact"] is False
    selected = copy.deepcopy(request)
    observation["observation"]["initial_diagnostics"] = [{"sha256": "only-a-hash"}]
    selected["messages"][-1]["content"] = json.dumps(observation)
    assert qualification.feedback_invariants(request, selected)["full_latest_initial_diagnostics_retained"] is False
