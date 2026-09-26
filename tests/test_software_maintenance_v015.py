"""Meaningful new boundary controls; CPU witnesses are not model outcomes."""
import json
import sys
from pathlib import Path

import pytest

from proworksim.software_sandbox import run_isolated
from proworksim.templates.software_maintenance import (
    ASSETS, SoftwareMaintenancePort, WORK, assess_software_submission, build_software_case,
)

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Frozen sandbox requires Linux")


def test_fixed_source_submission_and_partial_read_receipt(tmp_path):
    prepared = build_software_case("marshmallow-v15-strip-implement", tmp_path / "case")
    port = SoftwareMaintenancePort(prepared.world.session("implementer", "SOFTWARE"), "implementer")
    read = port.call("read_source", path="src/marshmallow/fields.py", start_line=894, max_lines=40)
    assert read["ok"]
    assert prepared.world.state["knowledge"]["implementer"]["source_ranges"][-1]["start_line"] == 894
    assert not prepared.world.state["knowledge"]["implementer"]["read_artifacts"]
    receipt = prepared.world.state["operation_commits"][read["command_id"]]
    assert receipt["public_result"] == read
    for patch in json.loads((ASSETS / "private/reference-patch.json").read_text()):
        assert port.call("replace_source", **patch)["ok"]
    tests = port.call("run_tests")["result"]
    assert tests["executed"] and tests["driver_completed"] and tests["returncode"] == 0
    assert port.call("submit", work_id=WORK, artifacts=["source", "test_result"])["ok"]
    assert port.call("replace_source", path="consumer.py", old="strip_whitespace=True", new="strip_whitespace=False")["ok"]
    result = assess_software_submission(prepared, run_root=tmp_path / "review")
    assert result["R"] == 1 and result["source_reference"]["version_id"] == "v3"
    assert len(result["independent_acceptance"]["groups"]) == 12
    assert result["independent_acceptance"]["passed_case_count"] == 29
    assert port.call("withdraw", work_id=WORK, submission_id=result["submission_id"], reason="Withdraw this delivery")["ok"]
    withdrawn = assess_software_submission(prepared, run_root=tmp_path / "withdrawn-review")
    assert withdrawn["R"] == 0 and "withdrawn" in withdrawn["reason"]


def test_hidden_assets_paths_and_edit_scope_are_not_actor_tools(tmp_path):
    prepared = build_software_case("marshmallow-v15-strip-implement", tmp_path / "case")
    port = SoftwareMaintenancePort(prepared.world.session("implementer", "SOFTWARE"), "implementer")
    paths = {item["path"] for item in port.observe()["software_workspace"]["file_index"]}
    assert not any("private" in p or "acceptance" in p or "reference-patch" in p for p in paths)
    for path in ("../../.env", "/etc/passwd", "private/test_acceptance.py"):
        assert not port.call("read_source", path=path, start_line=1, max_lines=40)["ok"]
    assert not port.call("replace_source", path="test_visible.py", old="unittest.main", new="print")["ok"]
    assert not port.call("write_object", alias="test_result", data={"executed": True})["ok"]
    assert not port.call("run_tests", command="echo yes")["ok"]
    with pytest.raises(ValueError):
        run_isolated({"../escape": "x"}, "pass", run_root=tmp_path / "outside")


def test_real_os_denies_host_network_and_new_process(tmp_path):
    canary = tmp_path / "canary"
    canary.write_text("private")
    code = f'''import socket, subprocess
for operation in (lambda: open({str(canary)!r}).read(), lambda: open('new', 'w'), lambda: socket.socket(), lambda: subprocess.run(['/bin/true'])):
    try:
        operation()
    except PermissionError:
        pass
    else:
        raise AssertionError('isolation failed')
'''
    result = run_isolated({"allowed.txt": "x"}, code, run_root=tmp_path / "sandbox")
    assert result["executed"] and result["driver_completed"] and result["returncode"] == 0
    premature = run_isolated({}, "import os\nos._exit(0)", run_root=tmp_path / "premature")
    assert premature["returncode"] == 0 and not premature["driver_completed"]
    assert Path(canary).read_text() == "private"


def test_collection_closes_without_controller_completing_worker_task(tmp_path):
    from proworksim.software_collection import collect_software_episode

    class DoneTransport:
        def complete(self, request, *, timeout_seconds):
            assert timeout_seconds > 0
            assert not any("reference-patch" in message.get("content", "") for message in request["messages"])
            body = {"id": "fixture-done", "model": "explicit-cpu-fixture",
                    "choices": [{"message": {"role": "assistant", "content": '{"kind":"done","reason":"CPU closure fixture"}'}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3}}
            return {"http_status": 200, "body": body, "raw_body": json.dumps(body)}

    result = collect_software_episode({"model": "explicit-cpu-fixture", "api_key_env": None, "base_url": "http://127.0.0.1:1"}, tmp_path / "collection", transport=DoneTransport())
    assert result["termination"]["status"] == "completed"
    assert result["actions"] == 0 and result["assessment"]["R"] == 0
    assert not result["assessment"]["submitted"]
    manifest = json.loads(Path(result["episode_manifest"]).read_text())
    assert manifest["status"] == "closed"


def test_monkeypatching_unittest_cannot_supply_parent_correctness(tmp_path):
    from proworksim.software_acceptance import API_DRIVER
    prepared = build_software_case("marshmallow-v15-strip-implement", tmp_path / "case")
    port = SoftwareMaintenancePort(prepared.world.session("implementer", "SOFTWARE"), "implementer")
    payload = "import abc\nimport unittest as _ut\nfrom types import SimpleNamespace as _NS\n_ut.main = lambda *a, **k: _NS(result=_NS(wasSuccessful=lambda: True))\n"
    assert port.call("replace_source", path="src/marshmallow/fields.py", old="import abc\n", new=payload)["ok"]
    visible = port.call("run_tests")["result"]
    assert visible["returncode"] == 0 and visible["driver_completed"] and visible["output"] == ""
    assert port.call("submit", work_id=WORK, artifacts=["source", "test_result"])["ok"]
    result = assess_software_submission(prepared, run_root=tmp_path / "review")
    assert result["R"] == 0
    assert result["submitted_visible_driver_claims_pass"]
    checks = result["independent_acceptance"]
    assert checks["executed"] and not checks["passed"]
    assert checks["expected_values_sent_to_worker"] is False
    assert checks["passed_case_count"] < checks["case_count"]
    assert "unittest" not in API_DRIVER and "expected" not in API_DRIVER
    assert any(row["group"] == "consumer" and not row["passed"] for row in checks["checks"])
