"""Finite v049 reader/stop controls; CPU fixtures are never generated model data."""
import copy
from types import SimpleNamespace

import pytest

from proworksim import software_organization_measurement_v049 as measured
from proworksim import software_organization_runtime_v049 as runtime
from proworksim.software_context_v048 import SoftwareContextTransport
from proworksim.software_organization_v049 import CASE_IDS, build_software_collaboration_case, case_spec
from proworksim.storage import digest, json_bytes
from test_software_organization_runtime_v038 import action
from test_software_organization_runtime_v049 import sdk_owner
from tests.test_measure_organization_budget_v046 import fixture as old_fixed_fixture, seal
from tests.test_software_organization_stop_policy_v047 import fixture as old_stop_fixture
from tests.test_software_organization_stop_policy_v046 import fixture as old_context_fixture


def seal_guard(owner):
    original = owner.finish_evaluation_guard
    def finish(before):
        return {**original(before), "learning_before_sha256": digest(json_bytes(before)),
            "learning_after_sha256": digest(json_bytes(owner.learning)),
            "rng_before_sha256": digest(b"explicit-cpu-no-rng"),
            "rng_after_restore_sha256": digest(b"explicit-cpu-no-rng")}
    owner.finish_evaluation_guard = finish


def new_binding(row, ledger):
    return {"version": "v049-original-loaded-state-capacity-binding", "slot_id": row["slot_id"],
        **copy.deepcopy(ledger["binding"]), "context_limit": 18432, "reserved_output_tokens": 2048}


def stop_fixture(**kwargs):
    data = old_stop_fixture(**kwargs)
    row, ledger = data["row"], data["team_budget"]["model"]
    row.update(version=runtime.VERSION, condition="O1", team_token_budget=500000,
               online_window_id="v049-o1-learning-window-01")
    ledger.update(team_id=row["online_window_id"], members=measured.MEMBERS,
                  limits={"max_decisions": 128, "max_attempts": 128, "max_total_tokens": 500000},
                  available_tokens=499800)
    ledger["binding"]["window_id"] = row["online_window_id"]
    ledger["records"]["call-1"].pop("stage_id")
    seal(ledger, "state_sha256")
    data["feedback"].update(version=measured.VERSION, local_resource_rejections={}, capacity_binding=new_binding(row, ledger))
    data["feedback"]["mechanism_gate_inputs"]["requests_verified_under_v049"] = 1
    data["evidence"]["version"] = runtime.VERSION
    row["member_lifecycle"] = {"stable_member_ids": measured.MEMBERS, "cumulative_births": 2,
        "live_at_end": 2, "events": [], "registry": {member: {"status": "live"} for member in measured.MEMBERS}}
    data.pop("capacity_binding")
    return data


@pytest.mark.parametrize("R,submitted,censored", [(0, False, False), (1, True, False), (0, False, True)])
def test_new_window_o1_closure_uses_no_result_or_old_common_filter(R, submitted, censored):
    data = stop_fixture(R=R, submitted=submitted, censored=censored)
    before = copy.deepcopy(data)
    result = measured.assess_records(**data)
    assert result["decision"] == "continue", result
    assert result["R_used_for_scope"] is False and data == before


@pytest.mark.parametrize("mutation", ["window", "old_version", "unknown_usage", "projection", "guard", "side_effect"])
def test_binding_and_execution_faults_never_release_new_stock(mutation):
    data = stop_fixture()
    if mutation == "window":
        data["team_budget"]["model"]["binding"]["window_id"] = "organization-v047:fixture"
        seal(data["team_budget"]["model"], "state_sha256")
    elif mutation == "old_version":
        data["evidence"]["version"] = "software-organization-runtime-v0.47"
    elif mutation == "unknown_usage":
        data["row"]["usage"]["uncertain_usage_attempts"] = 1
    elif mutation == "projection":
        data["feedback"]["mechanism_gate_inputs"]["projection_violations"] = ["call-1"]
    elif mutation == "guard":
        data["guard"]["learning_unchanged"] = False
    else:
        data["events"].append({"sequence": 999, "kind": "world_integrity_error", "payload": {}})
    assert measured.assess_records(**data)["decision"] == "global_pause"


def test_missing_inputs_or_unknown_result_stay_pending_not_zero():
    data = stop_fixture()
    data["row"].update(status="technical_unknown", R=None, R_joint=None)
    data["feedback"]["mechanism_gate_inputs"].update(resolved=False, requests_verified_under_v049=0)
    result = measured.assess_records(**data)
    assert result["decision"] == "measurement_pending"
    assert result["formal_result"]["R"] is None


def rewrite_window(value):
    if isinstance(value, dict):
        for key, item in list(value.items()):
            if key == "window_id":
                value[key] = "v049-o1-learning-window-01"
            elif key == "kind" and item == "organization_work_opportunity_v045":
                value[key] = "organization_work_opportunity_v049"
            else:
                rewrite_window(item)
        for field in ("preparation_sha256", "state_sha256"):
            if field in value:
                seal(value, field)
    elif isinstance(value, list):
        for item in value:
            rewrite_window(item)


def test_fixed_member_pre_refusal_binds_same_shared_window_and_no_stage():
    data, _ = old_fixed_fixture()
    rewrite_window(data)
    row, budget = data["result"], data["budget"]
    row.update(version=runtime.VERSION, condition="O1", team_token_budget=500000,
               online_window_id="v049-o1-learning-window-01")
    budget.update(team_id=row["online_window_id"], limits={"max_decisions": 128, "max_attempts": 128, "max_total_tokens": 500000})
    seal(budget, "state_sha256")
    data["capacity_binding"] = new_binding(row, budget)
    before = copy.deepcopy(data)
    proof = measured.bind_member_fixed_budget("new", **data)
    assert proof["reason"] == "member_fixed_budget" and proof["attempt_started"] is False
    assert proof["member_available_tokens"] == 1438 and proof["charged_tokens"] == 0
    assert data == before
    data["events"][3]["payload"]["reservation"]["preparation"]["window_id"] = "wrong"
    with pytest.raises(ValueError):
        measured.bind_member_fixed_budget("new", **data)


def test_shared_reservation_refusal_requires_real_shortage_and_no_effects():
    data = old_context_fixture(R=0, submitted=False)
    row, budget = data["row"], data["team_budget"]["model"]
    row["online_window_id"] = "v049-o1-learning-window-01"
    budget["binding"]["window_id"] = row["online_window_id"]
    record = budget["records"]["model-rejected"]
    record.pop("budget_kind")
    record["admission_limits"] = ["team_max_total_tokens"]
    reservation = record["rejected_reservation"]
    reservation.update(input_token_reservation=15000, token_reservation=17048)
    prep = reservation["preparation"]
    prep.update(window_id=row["online_window_id"], prompt_tokens=15000, fits=True)
    seal(prep, "preparation_sha256")
    budget.update(available_tokens=1000, charged_tokens=499000)
    seal(budget, "state_sha256")
    data["events"][1]["payload"]["reservation"] = copy.deepcopy(reservation)
    data["events"][2]["payload"].update(status="team_budget_exhausted", limits=["team_max_total_tokens"], team_budget=copy.deepcopy(budget))
    data["events"][2]["payload"].pop("budget_kind")
    row["boundary"]["role_stops"]["member_001"] = "team_budget_exhausted"
    row["boundary"]["terminal_details"]["member_001"]["status"] = "team_budget_exhausted"
    args = dict(row=row, budget=budget, evidence=data["evidence"], events=data["events"], binding=new_binding(row, budget))
    proof = measured.bind_shared_budget("model-rejected", record, **args)
    assert proof["reason"] == "team_budget" and proof["charged_tokens"] == 0
    data["events"].append({"sequence": 6, "kind": "tool_call", "worker_id": "member_001", "payload": {"model_call_id": "model-rejected"}})
    with pytest.raises(ValueError, match="actual_effect"):
        measured.bind_shared_budget("model-rejected", record, **args)


@pytest.mark.parametrize("first_context_rejection", [False, True])
def test_real_sdk_new_o1_interface_sharedwindow_and_dormant_feedback_are_measured(tmp_path, monkeypatch, first_context_rejection):
    pytest.importorskip("openhands.sdk")
    owner = sdk_owner({
        "member_001": [action("staff_done", reason="Present work done"), action("run_tests")],
        "member_002": [action("send_message", recipient="member_001", task_id="root_goal", body="New actual request")],
    })
    seal_guard(owner)
    if first_context_rejection:
        owner.tokenizer = lambda *args, **kwargs: {"input_ids": [17] * 17000}
    monkeypatch.setattr(runtime, "_capture_slot_guard", lambda current: copy.deepcopy(current.learning))
    owner.begin_window("v049-o1-learning-window-01")
    prepared = build_software_collaboration_case(case_spec(CASE_IDS[0]), tmp_path / "prepared")
    folder = tmp_path / "collection"
    row = runtime.collect_episode(owner, prepared, folder, sampling_seed=49, slot_id="v049-cpu-measure",
        manage_owner_window=False, transport_factory=SoftwareContextTransport)
    before = (json_bytes(row), (folder / "slot-result.json").read_bytes())
    report = measured.measure_slot(row, tmp_path / "measurement.json")
    assert report["decision"] == "continue", report
    feedback = report["feedback"]
    assert feedback["mechanism_gate_inputs"]["resolved"] is True, feedback
    assert feedback["capacity_binding"]["actual_world_runtime_version"] == runtime.VERSION
    assert feedback["capacity_binding"]["inherited_projection_library_provenance"]["world_runtime_library"] == "v047"
    assert before == (json_bytes(row), (folder / "slot-result.json").read_bytes())
    if first_context_rejection:
        assert row["usage"]["attempts"] == 0 and row["team_budget"]["model"]["binding"] is None
        assert len(report["stop_assessment"]["local_context_events"]) == 2
    else:
        assert feedback["mechanism_gate_inputs"]["requests_verified_under_v049"] == 5
        assert feedback["denominators"]["no_followup_reasons"] == {"current_work_ended_no_reachable_event": 2}
        assert feedback["page_denominators"]["reports_saved"] == 1
        changed = copy.deepcopy(row)
        changed["R"] = 1
        assert measured.measure_slot(changed)["decision"] == "global_pause"
        with pytest.raises(FileExistsError):
            measured.measure_slot(row, tmp_path / "measurement.json")


def test_feedback_requires_its_original_error_source(tmp_path):
    event = {"sequence": 0, "kind": "model_format_feedback", "worker_id": "member_001",
             "payload": {"call_id": "fixture"}}
    with pytest.raises(ValueError, match="prior_runner_error"):
        measured.lifecycle_history(tmp_path, {"original_attempts": []}, {"records": {}},
                                   [event], SimpleNamespace(calls={}))
