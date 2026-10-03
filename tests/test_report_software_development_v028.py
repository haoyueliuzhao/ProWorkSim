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
    (list(range(8)), 1791216000.0, "2026-10-06 00:00", None, None, None),
])
def test_report_uses_actual_plan_gpu_range_deadline_and_budgets(tmp_path, gpus, deadline, expected_date,
                                                              total, per_worker, wall):
    workers = dict.fromkeys(("worker-0", "worker-1"), per_worker)
    (tmp_path / "plan.json").write_text(json.dumps({
        "assignments": assignments(), "source": {"fixture": True},
        "gpu_preference": gpus, "queue_deadline_at": deadline,
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
    else:
        assert "累计GPU时长上限：6 GPU小时" in rendered
        assert "每worker GPU时长上限：worker-0=3小时、worker-1=3小时" in rendered
        assert "全局墙钟截止：北京时间2026-10-04 03:05" in rendered
