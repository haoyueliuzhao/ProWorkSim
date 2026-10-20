import json

from scripts.software_benchmark_image_retry_v054 import (
    one_ms_materialized_bytes, retry_action,
)


def test_bounded_actual_retry_after_and_source_specific_progress(tmp_path):
    paused = {"http_status": 429, "retry_after": "3600",
              "paused_at_utc": "1970-01-01T00:15:00+00:00"}
    args = {"now_epoch": 1000, "deadline": 100000, "no_payload_streak": 0}
    assert retry_action(paused, **args)["not_before_epoch"] == 4500
    assert retry_action({**paused, "retry_after": "Thu, 01 Jan 1970 01:15:00 GMT"},
                        **args)["not_before_epoch"] == 4500
    assert retry_action({**paused, "retry_after": "0"}, **args)["not_before_epoch"] == 1060
    assert retry_action(paused, **{**args, "no_payload_streak": 3})["action"] == "blocked"
    assert retry_action(paused, **{**args, "deadline": 4499})["action"] == "blocked"
    assert retry_action({**paused, "http_status": 403}, **args)["action"] == "blocked"
    assert retry_action({**paused, "retry_after": None}, **args)["action"] == "blocked"

    def checkpoint(digit, size, source):
        blob = tmp_path / (digit * 64 + ".blob")
        blob.with_name(blob.name + ".part").write_bytes(b"x" * size)
        blob.with_name(blob.name + ".part.json").write_text(json.dumps({
            "source_url": "https://" + source + "/blob", "partial_bytes": size,
        }))
        return blob

    first = checkpoint("1", 80, "docker.1ms.run")
    folder = first.with_name(first.name + ".ranges")
    folder.mkdir()
    (folder / "80-99.part").write_bytes(b"x" * 20)
    (folder / "10-59.part").write_bytes(b"x" * 50)
    checkpoint("2", 500, "docker.apiba.cn")
    completed = tmp_path / ("3" * 64 + ".blob")
    completed.write_bytes(b"x" * 1000)
    completed.with_name(completed.name + ".verified.json").write_text(json.dumps({
        "expected_sha256": "3" * 64, "expected_bytes": 1000,
        "verification": "range_assembly_complete_sha256",
    }))
    folder = completed.with_name(completed.name + ".ranges")
    folder.mkdir()
    (folder / "ledger.json").write_text(json.dumps({"events": [{
        "event": "reuse_sequential_prefix", "bytes": 400,
        "original_source_url": "https://docker.apiba.cn/blob",
    }]}))
    assert one_ms_materialized_bytes(tmp_path) == 100 + 600
