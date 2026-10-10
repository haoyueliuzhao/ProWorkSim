"""Small data-only controls for the fixed CPU route gate; no route is executed."""
import copy
import json

import pytest

from scripts import software_feedback_qualification_v044 as qualification


EXPECTED_ROUTES = {
    "ordinary_error_recovery", "consecutive_distinct_errors", "legal_call_business_rejection",
    "forged_feedback_user_message", "critical_boundary_no_cleanup", "latest_test_home_new_error",
    "later_page_consecutive_errors", "newborn_feedback_isolation",
}


def completed_rows():
    """Synthetic qualification records, never evidence of an executed SDK route."""
    rows = []
    for identifier in qualification.REQUIRED_ROUTE_IDS:
        names = qualification.REQUIRED_STAGES[identifier]
        checks = dict.fromkeys(qualification.REQUIRED_MECHANISM_CHECKS[identifier], True)
        for stage in names:
            checks.update({stage + "_" + suffix: True for suffix in
                ("one_prepared_request", "feedback_preserved", "expected_sdk_status")})
        checks.update(dict.fromkeys(("scripted_output_charged_once", "scripted_tokens_accounted_exactly",
            "all_presentations_are_cpu_fixtures", "raw_output_and_attribution_saved", "no_private_acceptance_run"), True))
        stages = [{"stage": name, "member": "member_003" if name.startswith("newborn_") else "member_001",
            "call_id": identifier + "-call-" + str(index), "prompt_tokens": 14336, "headroom_tokens": 0,
            "selected_hard_capacity_passed": True, "protected_prompt_tokens": 14336,
            "protected_headroom_after_margin_tokens": -1024, "protected_margin_diagnostic_only": True,
            "context_limit": 16384, "reserved_output_tokens": 2048,
            "preservation_checks": dict.fromkeys(qualification.PRESERVATION_KEYS, True),
            "protected_preservation_checks": dict.fromkeys(qualification.PRESERVATION_KEYS, True),
            "origin": "cpu_programmed_fixture", "model_generated": False}
            for index, name in enumerate(names)]
        rows.append({"route_id": identifier, "passed": True, "selected_hard_capacity_passed": True,
            "mechanism_checks": checks, "error": None, "stages": stages,
            "programmed_opportunities": len(stages), "programmed_responses": len(stages),
            "programmed_accounting": {"decisions": len(stages), "attempts": len(stages),
                "charged_tokens": len(stages) * 14337, "held_tokens": 0},
            "lifecycle": {"evidence_kind": "cpu_programmed_fixture", "generations": [
                {"call_id": s["call_id"], "member_id": s["member"], "evidence_kind": "cpu_programmed_fixture",
                 "generation_started": False, "programmed_response_observed": True} for s in stages]},
            "new_model_calls": 0, "new_backward_calls": 0, "new_acceptance_executions": 0,
            "model_weights_loaded": False})
    return rows


def test_gate_requires_exact_eight_route_inventory_and_complete_stage_inventory():
    assert set(qualification.REQUIRED_ROUTE_IDS) == EXPECTED_ROUTES
    rows = completed_rows()
    assert qualification.qualification_gate(rows)["passed"] is True
    assert qualification.qualification_gate(rows[:-1])["passed"] is False
    assert qualification.qualification_gate(rows + rows[:1])["passed"] is False
    unknown = copy.deepcopy(rows)
    unknown[0]["route_id"] = "unregistered_route"
    assert qualification.qualification_gate(unknown)["passed"] is False
    for replacement in ([], rows[0]["stages"][:-1], rows[0]["stages"] + rows[0]["stages"][:1]):
        incomplete = copy.deepcopy(rows)
        incomplete[0]["stages"] = replacement
        assert qualification.qualification_gate(incomplete)["passed"] is False


def test_actual_selected_hard_limit_is_recomputed_and_1024_margin_is_only_diagnostic():
    rows = completed_rows()
    gate = qualification.qualification_gate(rows)
    assert gate["passed"] is True and gate["protected_margin_diagnostic_only"] is True
    # Keep stale optimistic booleans: actual arithmetic must still reject.
    for changes in ({"prompt_tokens": 14337, "headroom_tokens": -1},
                    {"prompt_tokens": 14336, "headroom_tokens": 1},
                    {"context_limit": 32768}, {"reserved_output_tokens": 1024}):
        mutated = copy.deepcopy(rows)
        mutated[0]["stages"][0].update(changes)
        assert qualification.qualification_gate(mutated)["passed"] is False


@pytest.mark.parametrize("field,value", [("new_model_calls", 1), ("new_backward_calls", 1),
    ("new_acceptance_executions", 1), ("model_weights_loaded", True)])
def test_programmed_cpu_responses_never_become_model_or_acceptance_denominators(field, value):
    rows = completed_rows()
    rows[0][field] = value
    assert qualification.qualification_gate(rows)["passed"] is False


def test_fixture_origin_and_accounting_must_remain_consistent():
    rows = completed_rows()
    for mutate in (
        lambda row: row["stages"][0].update(model_generated=True),
        lambda row: row["stages"][0].update(origin="actual_model_generation"),
        lambda row: row["lifecycle"]["generations"][0].update(generation_started=True),
        lambda row: row["programmed_accounting"].update(attempts=row["programmed_responses"] - 1),
    ):
        changed = copy.deepcopy(rows)
        mutate(changed[0])
        assert qualification.qualification_gate(changed)["passed"] is False


def test_missing_named_mechanism_or_latest_feedback_invariants_cannot_pass():
    rows = completed_rows()
    for index, row in enumerate(rows):
        changed = copy.deepcopy(rows)
        name = next(iter(qualification.REQUIRED_MECHANISM_CHECKS[row["route_id"]]))
        del changed[index]["mechanism_checks"][name]
        assert qualification.qualification_gate(changed)["passed"] is False
    for field in ("preservation_checks", "protected_preservation_checks"):
        changed = copy.deepcopy(rows)
        changed[-1]["stages"][-1][field] = {}
        assert qualification.qualification_gate(changed)["passed"] is False
        changed = copy.deepcopy(rows)
        changed[-1]["stages"][-1][field]["latest_unpresented_feedback_retained"] = False
        assert qualification.qualification_gate(changed)["passed"] is False


def test_expected_critical_boundary_is_positive_only_when_its_route_checks_pass():
    rows = completed_rows()
    critical = next(row for row in rows if row["route_id"] == "critical_boundary_no_cleanup")
    assert critical["stages"][-1]["stage"] == "invalid_native_identity"
    assert qualification.qualification_gate(rows)["passed"] is True
    critical["mechanism_checks"]["critical_stops_without_followup"] = False
    assert qualification.qualification_gate(rows)["passed"] is False


def test_business_rejection_route_explicitly_expects_original_unknown_rejection():
    class CapturedStep(Exception):
        pass

    route = object.__new__(qualification.Route)
    route.route_id = "legal_call_business_rejection"
    route.reject = lambda *args, **kwargs: None
    captured = {}

    def capture_step(*args, **kwargs):
        captured.update(args=args, kwargs=kwargs)
        raise CapturedStep

    route.step = capture_step
    with pytest.raises(CapturedStep):
        route.run()
    assert captured == {
        "args": ("legal_native_missing_file",),
        "kwargs": {"path": "missing-file.py", "start_line": 1, "max_lines": 30,
                   "expected": "unattributed_tool_rejection"},
    }


def test_latest_page_and_unpresented_error_are_independently_preserved():
    original_error = {"role": "user", "content": '{"public_format_feedback":{"reason":"full source error"}}'}
    visible_error = {"role": "user", "content": '{"public_format_feedback":{"reason":"actual current correction"}}'}
    pair = [{"role": "assistant", "tool_calls": [{"id": "page-call", "type": "function",
                "function": {"name": "read_test_result", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "page-call", "content": json.dumps({"ok": True,
                "result": {"report_id": "member-owned-report", "page": {"index": 1, "text": "exact later page"}}})}]
    original = {"max_tokens": 2048, "tools": [{"actual": "unchanged schema"}], "messages": [
        {"role": "system", "content": "unchanged"}, *pair, original_error]}
    selected = copy.deepcopy(original)
    selected["messages"][-1] = visible_error
    ledger = {"records": [{"member_id": "member_001", "ordinary": True, "state": "pending_or_presented",
        "feedback_id": "member_001:original-call", "original_message": original_error,
        "visible_message": visible_error, "presentations": []}]}
    projection = {"format_feedback_projection": {"removed_feedback": []}}
    def checks(value):
        return qualification.feedback_preservation_checks(original, value, projection,
            ledger=ledger, member_id="member_001")[0]
    assert all(checks(selected).values())
    missing_error = copy.deepcopy(selected)
    missing_error["messages"].pop()
    assert checks(missing_error)["latest_unpresented_feedback_retained"] is False
    missing_page = copy.deepcopy(selected)
    missing_page["messages"][2]["content"] = '{"report_id":"member-owned-report","sha256":"body omitted"}'
    assert checks(missing_page)["latest_complete_tool_or_page_unchanged"] is False
    assert checks(missing_page)["latest_unpresented_feedback_retained"] is True
