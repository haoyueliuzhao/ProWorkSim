"""Read-only unknown preservation and trajectory indexing, no model execution."""

import json

import pytest

from scripts.report_software_development_v028 import markdown, report
from scripts.software_development_v028 import assignments


def test_waiting_and_interrupted_requests_are_not_business_zero(tmp_path):
    (tmp_path / "plan.json").write_text(json.dumps({
        "assignments": assignments(), "source": {"fixture": True},
        "gpu_preference": [0, 4, 5, 7], "queue_deadline_at": 1791043200.0,
        "total_gpu_seconds": 21600, "worker_gpu_seconds": {"worker-0": 10800, "worker-1": 10800},
        "limits": {"max_parallel_model_instances": 2},
        "wall_deadline_at": 1791054300.0}))
    (tmp_path / "supervisor.json").write_text(json.dumps({"status": "waiting"}))
    data = report(tmp_path)
    assert data["overall"] == {"scheduled": 8, "started": 0, "known": 0, "unknown_started": 0,
                                "not_started": 8, "complete": 0, "complete_rate_all": None}
    assert data["trajectory_files"] == 0 and "未知" in markdown(data)
    slot = assignments()["worker-0"][0]
    actual = tmp_path / "worker-0/actual"
    folder = actual / slot["slot_id"]
    stream = folder / "slot-0/experience.jsonl"
    stream.parent.mkdir(parents=True)
    stream.write_text(json.dumps({"sequence": 0, "worker_id": "member_a", "kind": "model_call",
                                  "payload": {"stage": "started"}}) + "\n" + '{"sequence":1')
    raw = folder / "raw-transport"
    raw.mkdir()
    (raw / "call-00001.started.json").write_text(json.dumps({"request": {"messages": []}}))
    backend = actual / "resident/calls/model-call.json"
    backend.parent.mkdir(parents=True)
    backend.write_text(json.dumps({"rendered_prompt": "original backend prompt", "response": None}))
    (actual / "progress.json").write_text(json.dumps([{**slot, "status": "started"}]))
    data = report(tmp_path)
    assert data["overall"]["unknown_started"] == 1 and data["overall"]["known"] == 0
    assert data["overall"]["complete_rate_all"] is None
    first = data["episodes"][0]
    assert first["reward"] is None and first["stream_tail_problem"]["line"] == 2
    assert first["calls"]["durable_request_ledgers"] == 1
    assert first["calls"]["durable_return_ledgers"] == 0
    index = json.loads((tmp_path / "trajectory-index.json").read_text())
    assert {row["path"] for row in index["files"]} == {
        str(stream), str(raw / "call-00001.started.json"), str(backend)}


@pytest.mark.parametrize("gpus,deadline,expected_date,total,per_worker,wall", [
    ([0, 4, 5, 7], 1791043200.0, "2026-10-04 00:00", 21600, 10800, 1791054300.0),
    ([5], 1791216000.0, "2026-10-06 00:00", None, None, None),
])
def test_report_uses_actual_plan_gpu_range_deadline_and_budgets(tmp_path, gpus, deadline, expected_date,
                                                              total, per_worker, wall):
    workers = dict.fromkeys(("worker-0", "worker-1"), per_worker)
    (tmp_path / "plan.json").write_text(json.dumps({
        "assignments": assignments(), "source": {"fixture": True},
        "gpu_preference": gpus, "queue_deadline_at": deadline,
        "limits": {"max_parallel_model_instances": 1 if total is None else 2},
        "total_gpu_seconds": total, "worker_gpu_seconds": workers, "wall_deadline_at": wall}))
    data = report(tmp_path)
    rendered = markdown(data)
    assert data["gpu_preference"] == gpus and data["queue_deadline_at"] == deadline
    assert data["queue_deadline_beijing"] == expected_date.replace(" ", "T") + ":00+08:00"
    assert f"在GPU{'/'.join(map(str, gpus))}等待空卡" in rendered
    assert f"等卡截止北京时间{expected_date}；" in rendered
    assert data["total_gpu_seconds"] == total and data["worker_gpu_seconds"] == workers
    assert data["wall_deadline_at"] == wall
    if total is None:
        assert "累计GPU时长上限：不设；每worker GPU时长上限：不设；全局墙钟截止：不设。" in rendered
        assert "6 GPU小时" not in rendered and "3小时" not in rendered
        assert "最多1个模型实例" in rendered
    else:
        assert "累计GPU时长上限：6 GPU小时" in rendered
        assert "每worker GPU时长上限：worker-0=3小时、worker-1=3小时" in rendered
        assert "全局墙钟截止：北京时间2026-10-04 03:05" in rendered
        assert "最多2个模型实例" in rendered


def test_recovery_report_retains_failure_unknown_and_attempt_sources(tmp_path, monkeypatch):
    from test_software_development_runner_v028 import recovery_fixture
    from scripts import report_software_development_v028 as reporter
    from scripts import software_development_v028 as runner

    prior, spec = recovery_fixture(tmp_path, monkeypatch)
    root = tmp_path / "recovery"
    runner.write(root / "plan.json", spec)
    runner.write(root / "supervisor.json", {"status": "running", "running_gpu_seconds": 2})
    before = report(root)
    assert before["overall"] == {"scheduled": 8, "started": 6, "known": 5, "unknown_started": 1,
                                  "not_started": 2, "complete": 4, "complete_rate_all": None}
    slot = assignments()["worker-1"][1]
    old_unknown = next(row for row in before["episodes"] if row["slot_id"] == slot["slot_id"])
    assert old_unknown["status"] == "execution_unknown" and old_unknown["recovery_status"] == "not_started"
    assert [attempt["attempt_index"] for attempt in old_unknown["attempts"]] == [0, 1]
    assert old_unknown["attempts"][1]["started"] is False
    folder = root / "worker-1/actual" / slot["slot_id"]
    reward = {"eligible": True, "completed": True, "reward": 1}
    guard = {"learning_unchanged": True, "rng_restored_exactly": True}
    row = {**slot, "status": "closed", "reward": reward, "evaluation_guard": guard, "attempt_index": 1}
    runner.write(root / "worker-1/actual/progress.json", [row])
    runner.write(folder / "slot-0/entry.json", {"reward": reward})
    runner.write(folder / "slot-0/assessment.json", {"status": "complete", "R": 1})
    runner.write(folder / "evaluation-guard.json", guard)
    data = report(root)
    recovered = next(item for item in data["episodes"] if item["slot_id"] == slot["slot_id"])
    assert recovered["status"] == "closed" and recovered["reward"] == 1
    assert recovered["source"] == spec["source"] and recovered["attempt_index"] == 1
    old, new = recovered["attempts"]
    assert old["status"] == "execution_unknown" and old["reward"] is None
    assert old["source"] == spec["recovery"]["prior_source"]
    assert old["raw_assessment"]["execution_failure"]["reason"] == "CPU fixture context_length_exceeded"
    assert new["source"] == spec["source"] and new["interface_revision"] == runner.INTERFACE_REVISION
    failure = next(item for item in data["episodes"] if item["slot_id"] == assignments()["worker-0"][1]["slot_id"])
    assert failure["retained_closed"] is True and failure["reward"] == 0 and failure["known"] is True
    assert failure["source"] == spec["recovery"]["prior_source"] and len(failure["attempts"]) == 1
    assert failure["trajectory_directory"].startswith(str(prior))
    assert data["overall"]["known"] == 6 and data["gpu_seconds"] == 125
    assert data["same_protocol_statistics_allowed"] is False
    rendered = markdown(data)
    assert "不能混同为相同协议的效果统计" in rendered and "execution_unknown" in rendered
    assert "software-development-v028-recovery.json" in rendered
    files = json.loads((root / "trajectory-index.json").read_text())["files"]
    assert any(item["attempt_index"] == 0 and item["path"].startswith(old["trajectory_directory"]) for item in files)
    assert any(item["attempt_index"] == 1 and item["path"].startswith(str(folder)) for item in files)
    monkeypatch.setattr("sys.argv", ["report", "--run-root", str(root), "--output-dir", str(tmp_path / "reports")])
    reporter.main()
    assert (tmp_path / "reports/software-development-v028-recovery.json").exists()
    assert not (tmp_path / "reports/software-development-v028.json").exists()
