import importlib.util
import json
from pathlib import Path
import threading
import time

from proworksim.software_benchmark_candidates_v054 import reference, write_new

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("full_coordinator_cpu_fixture", ROOT / "tools/run_full_benchmark_v064.py")
coordinator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(coordinator)


class Runtime:
    def __init__(self):
        self.closed = 0

    def start_residents(self):
        return self.ready_residents()

    def ready_residents(self):
        return [{"root": f"model-{index}"} for index in range(6)]

    def stop_residents(self):
        self.closed += 1
        return [{"owned_unit_stopped": True}]


class API:
    def __init__(self, state="ready"):
        self.state = state

    def budget_status(self):
        return {"state": self.state, "can_start_generation": self.state == "ready"}

    def logical_resident(self):
        return {"endpoint": "http://127.0.0.1:18219", "api_key_file": None}

    def transport_factory(self, *_):
        raise AssertionError("No transport is called in this CPU scheduler fixture")


class Fixture:
    def __init__(self, path, *, unknown=None, unquiet=None, busy_once=None):
        self.path, self.unknown, self.unquiet, self.busy_once = path, unknown, unquiet, busy_once
        self.lock, self.entered, self.calls = threading.Lock(), set(), {}
        self.active_generation = self.active_grading = self.maximum_generation = self.maximum_grading = 0
        self.by_model, self.maximum_by_model = {}, 0
        self.grade_overlapped_generation = False

    def episode(self, row, resident, **kwargs):
        key = row["slot_id"]
        with self.lock:
            self.calls[key] = self.calls.get(key, 0) + 1
            if key == self.busy_once and self.calls[key] == 1:
                raise coordinator.policy.ResourceBusy("not entered")
            self.entered.add(key)
            self.active_generation += 1
            self.maximum_generation = max(self.maximum_generation, self.active_generation)
            if row["model_key"] == "QWEN":
                name = resident["root"]
                self.by_model[name] = self.by_model.get(name, 0) + 1
                self.maximum_by_model = max(self.maximum_by_model, self.by_model[name])
            else:
                assert kwargs.get("api_transport_factory") is not None
        time.sleep(.005 if row["slot_index"] % 5 == 0 else .04)
        unknown = key == self.unknown
        result = {"slot_id": key, "configuration": row["configuration"],
            "status": "technical_unknown" if unknown else "closed", "model_calls": 1,
            "quiescence": {"quiescent": key != self.unquiet, "cleanup_errors": [], "create_result_unknown": False},
            "ledger": {"known_actual_tokens": 10, "complete_actual_tokens": None if unknown else 10,
                       "inflight": {"reservation": 50} if unknown else None,
                       "uncertain_reserved_tokens": 50 if unknown else 0}}
        result_ref = write_new(self.path / f"result-{row['slot_index']}.json", result)
        with self.lock:
            self.active_generation -= 1
            if row["model_key"] == "QWEN":
                self.by_model[resident["root"]] -= 1
        return result_ref

    def prepare_score(self, result_ref, *, endpoint="code"):
        result = json.loads(Path(result_ref["path"]).read_bytes())
        index = int(result["slot_id"].split("-")[-1])
        return write_new(self.path / f"request-{index}-{endpoint}.json", {
            "slot_id": result["slot_id"], "instance_id": "task", "resource_key": f"score-{index}",
            "directory": str(self.path / f"grading-{index}")})

    def run_request(self, request_ref, stop_event=None):
        with self.lock:
            self.active_grading += 1
            self.maximum_grading = max(self.maximum_grading, self.active_grading)
            self.grade_overlapped_generation |= self.active_generation > 0
        time.sleep(.01)
        with self.lock:
            self.active_grading -= 1
        return {"status": "process_exited", "returncode": 0}

    def trustworthy_cleanup(self, _):
        return True

    def delivery_disposition(self, result_ref, code_request_ref):
        return {"status": "no_legal_delivery", "resolved": False, "scoring_request": None}


def rows(path, count=24):
    config = write_new(path / "configuration.json", {})
    return [{"slot_index": index, "slot_id": f"slot-{index}", "instance_id": "task",
        "configuration": config, "model_key": "QWEN" if index % 2 == 0 else "DEEPSEEK",
        "arm": "PROJECT" if index % 3 == 0 else "REF", "group_id": f"group-{index % 12}",
        "generation_token_upper_bound": 1000} for index in range(count)]


def execute(path, fixture, planned, api=None):
    runtime, progress, events = Runtime(), [], []

    def event(kind, **values):
        events.append((kind, values))

    result = coordinator.execute_queue(planned, controls=[],
        qualifications={"task": {"status": "qualified"}}, grading=fixture,
        runtime=runtime, run_episode=fixture.episode, api_runtime=api or API(),
        progress_sink=progress.append, event_sink=event,
        entered_probe=lambda row: row["slot_id"] in fixture.entered,
        model_exhausted=lambda _: False, generation_limit=lambda: 12)
    return result, runtime, progress, events


def test_generation_and_grading_overlap_with_both_hard_concurrency_limits(tmp_path):
    fixture = Fixture(tmp_path)
    result, runtime, progress, _ = execute(tmp_path, fixture, rows(tmp_path))
    assert result["failure"] is None and len(result["generation"]) == 24 and len(result["scores"]) == 24
    assert fixture.maximum_generation <= 12 and fixture.maximum_grading <= 4
    assert fixture.maximum_by_model <= 2
    assert fixture.grade_overlapped_generation is True and runtime.closed == 1
    assert all(count == 1 for count in fixture.calls.values())
    assert progress[-1]["finished_generation"] == 24


def test_api_cash_stop_keeps_unentered_denominator_and_qwen_continues(tmp_path):
    fixture = Fixture(tmp_path)
    result, runtime, _, _ = execute(tmp_path, fixture, rows(tmp_path), API("cash_exhausted"))
    assert result["failure"] is None and runtime.closed == 1
    assert len(result["scores"]) == 12
    unentered = [value for value in result["generation"].values() if value["entered"] is False]
    assert len(unentered) == 12
    assert all(value["not_started_reason"] == "api_monetary_budget_exhausted" for value in unentered)
    assert all(int(key.split("-")[-1]) % 2 == 0 for key in fixture.calls)


def test_isolated_unknown_usage_with_bound_does_not_stop_other_slots(tmp_path):
    fixture = Fixture(tmp_path, unknown="slot-0")
    result, runtime, _, events = execute(tmp_path, fixture, rows(tmp_path, 6))
    assert result["failure"] is None and len(result["generation"]) == 6 and len(result["scores"]) == 5
    assert result["generation"]["slot-0"]["status"] == "technical_unknown"
    assert any(kind == "isolated_exception" for kind, _ in events) and runtime.closed == 1


def test_resource_busy_before_entry_consumes_no_episode_and_requeues_original_slot(tmp_path):
    fixture = Fixture(tmp_path, busy_once="slot-0")
    result, _, _, _ = execute(tmp_path, fixture, rows(tmp_path, 4))
    assert result["failure"] is None and len(result["scores"]) == 4
    assert fixture.calls["slot-0"] == 2 and len(fixture.entered) == 4


def test_unproven_cleanup_stops_new_dispatch_but_always_closes_own_residents(tmp_path):
    fixture = Fixture(tmp_path, unquiet="slot-0")
    result, runtime, _, _ = execute(tmp_path, fixture, rows(tmp_path, 24))
    assert result["failure"]["kind"] == "unproven_generation_cleanup"
    assert result["unentered_generation"] and runtime.closed == 1
    assert all(count == 1 for count in fixture.calls.values())


def test_shared_money_failure_stops_before_model_work(tmp_path):
    fixture = Fixture(tmp_path)
    result, runtime, _, _ = execute(tmp_path, fixture, rows(tmp_path, 4), API("shared_halted"))
    assert result["failure"]["kind"] == "unbounded_or_invalid_api_money_authority"
    assert fixture.calls == {} and runtime.closed == 1


def test_administrative_stop_classifier_does_not_scan_issue_or_model_text():
    text = "global_cny_budget_reservation_insufficient"
    assert coordinator.administrative_truncation({"problem_statement": text, "model_text": text}) is False
    assert coordinator.administrative_truncation({"adapter_halted": text}) is True


def test_generation_ceiling_leaves_grading_capacity_with_six_models(tmp_path, monkeypatch):
    monkeypatch.setattr(coordinator, "BATCH_ROOT", tmp_path)
    directory = tmp_path / "resource-claims"
    directory.mkdir()
    for index in range(6):
        (directory / f"active-model-{index}.json").write_text("{}")
    assert coordinator.generation_lane_limit() == 10
    (directory / "active-model-5.json").unlink()
    assert coordinator.generation_lane_limit() == 12


def test_new_unit_launcher_only_targets_its_own_bounded_user_unit(tmp_path, monkeypatch):
    source = importlib.util.spec_from_file_location("launcher_v064_fixture", ROOT / "tools/launch_full_benchmark_v064.py")
    launcher = importlib.util.module_from_spec(source)
    source.loader.exec_module(launcher)
    monkeypatch.setattr(launcher.policy, "cpu_set", lambda *args: "0,1,2,3")
    value = {"unit": launcher.UNIT, "user_id": launcher.os.getuid(), "cpu_affinity": [0, 1, 2, 3],
        "source": reference(launcher.__file__), "ownership_token": "fixture"}
    command = launcher.command(value)
    assert command[:2] == ["systemd-run", "--user"]
    assert "--unit=proworksim-v064-full-verified.service" in command
    assert "--property=MemoryMax=16G" in command and "--property=CPUQuota=400%" in command
    assert "--property=Restart=no" in command
    assert not any(word in command for word in ("sudo", "mount", "umount", "unshare"))


def test_usage_sidecars_keep_only_counters_in_memory_and_administrative_scores_separate(tmp_path, monkeypatch):
    matrix = json.loads((ROOT / "artifacts/software-benchmark-v064/preparation-r1/plan.json").read_bytes())
    row = next(value for value in matrix["rows"] if value["model_key"] == "DEEPSEEK" and value["arm"] == "PROJECT")
    monkeypatch.setattr(coordinator, "RUN_ROOT", tmp_path)

    class UsageAPI(API):
        @staticmethod
        def usage_for_slot(_):
            return {"calls": [{"call_id": "request", "purpose": "agent", "prompt_tokens": 100,
                "completion_tokens": 20, "accounted_cost_cny": "0.01"}],
                "unresolved_calls": [], "usage_capture_complete": True}

        @staticmethod
        def preparation_usage():
            return {"calls": [], "unresolved_calls": []}

    folder = tmp_path / "score"
    folder.mkdir()
    request = write_new(folder / "request.json", {"directory": str(folder)})
    write_new(folder / "receipt.json", {"status": "official_report", "resolved": False})
    recorder = coordinator.UsageRecorder(matrix, UsageAPI())
    recorder(row, {"entered": True, "status": "closed", "administrative_truncation": True}, {},
             {"request": request}, {"resolved": False})
    compact = recorder.records[row["slot_id"]]
    assert "calls" not in compact and compact["prompt_tokens_known"] == 100
    saved = json.loads(Path(compact["record"]["path"]).read_bytes())
    assert saved["code_result"] is None and saved["diagnostic_official_code_result"] is False
    assert saved["delivery_result"] is None and saved["diagnostic_delivery_result"] is False
    recorder.flush(final=True)
    report = json.loads((tmp_path / "actual-usage-summary.json").read_bytes())
    group = report["groups"][row["group_id"]]
    assert group["code_outcomes"]["unresolved"] == 0
    assert group["all_planned"]["known_usage_all_entered_including_unknown_outcomes"]["input_plus_output_tokens"] == 120
    assert "record_files" in json.loads((tmp_path / "actual-usage-records.json").read_bytes())
