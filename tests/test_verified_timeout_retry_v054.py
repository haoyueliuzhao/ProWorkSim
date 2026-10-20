from scripts.software_benchmark_image_retry_v054 import retry_action


def test_saved_read_timeout_has_three_bounded_resumptions_only():
    fault = {"http_status": None, "error_type": "TimeoutError",
             "error": "The read operation timed out"}
    args = {"now_epoch": 1000, "deadline": 200000, "no_payload_streak": 0}
    for used, delay in enumerate((60, 300, 900)):
        action = retry_action(fault, **args, timeout_retries_used=used)
        assert action["kind"] == "read_timeout"
        assert action["not_before_epoch"] == 1000 + delay
        assert action["backoff_seconds"] == delay
    assert retry_action(fault, **args, timeout_retries_used=3)["action"] == "blocked"
    assert retry_action(fault, **{**args, "no_payload_streak": 3})["action"] == "blocked"
    assert retry_action(fault, **{**args, "deadline": 1059})["action"] == "blocked"
    assert retry_action({**fault, "http_status": 403}, **args)["action"] == "blocked"
    assert retry_action({"http_status": None, "error_type": "DownloadPaused",
                         "error": "Complete SHA256 mismatch"}, **args)["action"] == "blocked"
    assert retry_action({"http_status": None, "error_type": "DownloadPaused",
                         "error": "Range Content-Range mismatch"}, **args)["action"] == "blocked"
    assert retry_action({**fault, "http_status": 429, "retry_after": None},
                        **args)["action"] == "blocked"
