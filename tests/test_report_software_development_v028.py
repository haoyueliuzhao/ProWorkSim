"""Read-only unknown preservation and trajectory indexing, no model execution."""

import json

import pytest

from scripts.report_software_development_v028 import markdown, report
from scripts.software_development_v028 import assignments


def test_waiting_and_interrupted_requests_are_not_business_zero(tmp_path):
    (tmp_path / "plan.json").write_text(json.dumps({
        "assignments": assignments(), "source": {"fixture": True},
        "gpu_preference": [0, 4, 5, 7], "queue_deadline_at": 1791043200.0}))
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


@pytest.mark.parametrize("gpus,deadline,expected_date", [
    ([0, 4, 5, 7], 1791043200.0, "2026-10-04 00:00"),
    (list(range(8)), 1791216000.0, "2026-10-06 00:00"),
])
def test_report_uses_actual_plan_gpu_range_and_deadline(tmp_path, gpus, deadline, expected_date):
    (tmp_path / "plan.json").write_text(json.dumps({
        "assignments": assignments(), "source": {"fixture": True},
        "gpu_preference": gpus, "queue_deadline_at": deadline}))
    data = report(tmp_path)
    rendered = markdown(data)
    assert data["gpu_preference"] == gpus and data["queue_deadline_at"] == deadline
    assert data["queue_deadline_beijing"] == expected_date.replace(" ", "T") + ":00+08:00"
    assert f"在GPU{'/'.join(map(str, gpus))}等待空卡" in rendered
    assert f"等卡截止北京时间{expected_date}；" in rendered
