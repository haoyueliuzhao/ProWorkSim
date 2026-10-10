"""Gate contracts only; real tokenizer/SDK/page routes run once in P0-B/C."""
import copy
import json

from scripts import software_feedback_qualification_v042 as qualification


def completed_control_rows():
    rows = []
    inventory = (qualification.configuration_inventory() + qualification.representative_inventory()
                 + qualification.pagination_inventory())
    for spec in inventory:
        names = (qualification.CORE_REQUIRED_STAGES if spec["kind"] == "core" else
                 qualification.REPRESENTATIVE_REQUIRED_STAGES.get(spec["kind"],
                     qualification.PAGINATION_REQUIRED_STAGES.get(spec["kind"])))
        labels = ["failed", "passed"] if spec["kind"] == "core" else (
            ["counterexample"] if spec["kind"] in qualification.PAGINATION_COMBINATIONS else [])
        rows.append({**spec, "passed": True, "report_recovery": [
            {"label": label, "exact_recovery": True,
             "all_pages_presented_in_subsequent_fitting_requests": True} for label in labels],
            "stages": [{"stage": name, "fits": True, "context_limit": 16384, "reserved_output_tokens": 2048,
                "prompt_tokens": 14330, "headroom_tokens": 6,
                "protected_prompt_tokens": 13000, "protected_headroom_tokens": 1336,
                "protected_engineering_margin_tokens": 1024, "protected_headroom_after_margin_tokens": 312,
                "protected_margin_fits": True,
                "feedback_invariants": dict.fromkeys(qualification.INVARIANT_KEYS, True),
                "protected_feedback_invariants": dict.fromkeys(qualification.INVARIANT_KEYS, True)}
                for name in sorted(names)]})
    return rows


def test_gate_keeps_sixteen_core_twelve_representatives_and_four_paging_combinations():
    rows = completed_control_rows()
    assert len(qualification.configuration_inventory()) == 16
    assert len(qualification.representative_inventory()) == 12
    assert len(qualification.pagination_inventory()) == 4
    assert qualification.qualification_gate(rows)["passed"] is True
    missing = copy.deepcopy(rows)
    missing[0]["stages"] = [row for row in missing[0]["stages"] if row["stage"] != "after_failed_report_complete"]
    assert qualification.qualification_gate(missing)["passed"] is False
    assert qualification.qualification_gate(rows[:-1])["passed"] is False
    assert qualification.qualification_gate(rows + rows[:1])["passed"] is False
    rows[0]["member"] = "wrong_owner"
    assert qualification.qualification_gate(rows)["passed"] is False


def test_selected_hard_gate_and_protected_engineering_margin_are_independent():
    # Selected intentionally has only 6 tokens left; protected has the required
    # 1024 plus 312. Applying 1024 to selected would reject this valid fixture.
    rows = completed_control_rows()
    assert qualification.qualification_gate(rows)["passed"] is True
    too_large = copy.deepcopy(rows)
    too_large[0]["stages"][0].update(prompt_tokens=14337, headroom_tokens=-1, fits=False)
    assert qualification.qualification_gate(too_large)["passed"] is False
    protected_too_large = copy.deepcopy(rows)
    protected_too_large[0]["stages"][0].update(protected_prompt_tokens=13313,
        protected_headroom_tokens=1023, protected_headroom_after_margin_tokens=-1, protected_margin_fits=False)
    assert qualification.qualification_gate(protected_too_large)["passed"] is False


def test_exact_recovery_without_later_page_presentation_cannot_pass():
    for index in (0, -1):
        rows = completed_control_rows()
        rows[index]["report_recovery"][0]["all_pages_presented_in_subsequent_fitting_requests"] = False
        assert qualification.qualification_gate(rows)["passed"] is False
    rows = completed_control_rows()
    rows[0]["report_recovery"][0]["exact_recovery"] = False
    assert qualification.qualification_gate(rows)["passed"] is False
    rows = completed_control_rows()
    rows[0]["stages"][0]["protected_feedback_invariants"] = {}
    assert qualification.qualification_gate(rows)["passed"] is False


def test_latest_exact_page_cannot_be_replaced_by_a_digest_or_another_page():
    observation = {"role_task": "full instruction", "observation": {"contract": "full contract",
        "root_goal": {"description": "full contract"}, "initial_diagnostics": [{"id": "owned-initial"}],
        "tasks": [{"revision": 2}]}}
    request = {"max_tokens": 2048, "tools": [{"actual": "read_test_result schema"}], "messages": [
        {"role": "system", "content": "original system"},
        {"role": "assistant", "content": None, "tool_calls": [{"id": "actual", "function": {"name": "read_test_result"}}]},
        {"role": "tool", "tool_call_id": "actual", "content": '{"ok": true, "result": {"report_id": "owned", "page": {"text": "exact saved fragment"}}}'},
        {"role": "user", "content": json.dumps(observation)}]}
    selected = copy.deepcopy(request)
    del observation["observation"]["root_goal"]["description"]
    selected["messages"][-1]["content"] = json.dumps(observation)
    assert all(qualification.feedback_invariants(request, selected).values())
    selected["messages"][2]["content"] = '{"body_sha256": "hash-does-not-replace-body"}'
    assert qualification.feedback_invariants(request, selected)["latest_complete_visible_round_exact"] is False
