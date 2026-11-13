import os
import pytest
def test_collision(monkeypatch):
    if os.environ.get("PWS_SYNTHETIC_CHILD") == "1":
        assert False, "expected child failure"
    monkeypatch.setenv("PWS_SYNTHETIC_CHILD", "1")
    assert pytest.main(["-q", __file__]) == 1
