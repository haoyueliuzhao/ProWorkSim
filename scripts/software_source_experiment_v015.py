"""CPU witness/negative controls for pinned software asset, never model evidence."""
import argparse
import copy
import json
from pathlib import Path

from proworksim.software_sandbox import LIMITS, run_isolated
from proworksim.storage import atomic_write, digest, json_bytes
from proworksim.templates.software_maintenance import (
    ASSETS, SoftwareMaintenancePort, WORK, assess_software_submission,
    build_software_case, manifest,
)


def main(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    rows = []
    reference = json.loads((ASSETS / "private/reference-patch.json").read_text())
    for name in ("unmodified", "reference", "visible_green_unicode_wrong", "stale_test_report", "post_submission_edit", "unittest_monkeypatch"):
        prepared = build_software_case("marshmallow-v15-strip-implement", output / name)
        port = SoftwareMaintenancePort(prepared.world.session("implementer", "SOFTWARE"), "implementer")
        actions = []

        def call(action, **arguments):
            response = port.call(action, request_key=name + "-" + str(len(actions)), **arguments)
            actions.append({"action": action, "arguments": arguments, "response": response})
            if not response["ok"]:
                raise ValueError(response)
            return response

        call("read_alias", alias="contract", work_id=WORK)
        call("search_source", path="src/marshmallow/fields.py", text="class String")
        call("read_source", path="src/marshmallow/fields.py", start_line=894, max_lines=40)
        call("read_source", path="consumer.py", start_line=1, max_lines=30)
        if name not in {"unmodified", "unittest_monkeypatch"}:
            patches = copy.deepcopy(reference)
            if name == "visible_green_unicode_wrong":
                patches[0]["new"] = patches[0]["new"].replace("text.strip()", "text.strip(' ')")
            for patch in patches:
                call("replace_source", **patch)
        if name == "unittest_monkeypatch":
            call("replace_source", path="src/marshmallow/fields.py", old="import abc\n",
                 new="import abc\nimport unittest as _ut\nfrom types import SimpleNamespace as _NS\n_ut.main = lambda *a, **k: _NS(result=_NS(wasSuccessful=lambda: True))\n")
        tests = call("run_tests")["result"]
        if name == "stale_test_report":
            call("replace_source", path="consumer.py", old='"""Simulated downstream', new='"""Updated simulated downstream')
        call("submit", work_id=WORK, artifacts=["source", "test_result"])
        if name == "post_submission_edit":
            call("replace_source", path="consumer.py", old="strip_whitespace=True", new="strip_whitespace=False")
        assessment = assess_software_submission(prepared, run_root=output / name / "private-assessment")
        expected = 1 if name in {"reference", "post_submission_edit"} else 0
        if assessment["R"] != expected:
            raise AssertionError((name, assessment))
        if name in {"visible_green_unicode_wrong", "unittest_monkeypatch"} and tests["returncode"] != 0:
            raise AssertionError("Negative control must pass the actual public suite")
        evidence = {"name": name, "kind": "rule_control_not_model", "expected_R": expected,
                    "visible_tests": tests, "assessment": assessment, "action_count": len(actions),
                    "last_world_revision": prepared.world.state["state_revision"]}
        atomic_write(output / name / "actions.json", json_bytes(actions))
        atomic_write(output / name / "assessment.json", json_bytes(assessment))
        rows.append(evidence)
    canary = output / "host-canary.txt"
    canary.write_text("Not exposed to the worker")
    probe = f'''import errno, json, os, socket, subprocess
checks = {{}}
operations = {{
    'host_read': lambda: open({str(canary.resolve())!r}).read(),
    'system_read': lambda: open('/etc/passwd').read(),
    'proc_read': lambda: open('/proc/self/environ').read(),
    'workspace_write': lambda: open('created.py', 'w'),
    'host_write': lambda: open({str(canary.resolve())!r}, 'w'),
    'symlink': lambda: os.symlink('/etc/passwd', 'escape'),
    'network': lambda: socket.socket(),
    'subprocess': lambda: subprocess.run(['/bin/true']),
}}
for label, operation in operations.items():
    try:
        operation()
        checks[label] = 'FAILED_OPEN'
    except OSError as error:
        checks[label] = error.errno
print(json.dumps(checks, sort_keys=True))
assert all(value in (errno.EPERM, errno.EACCES) for value in checks.values())
'''
    isolation = run_isolated({"safe.txt": "permitted source"}, probe, run_root=output / "isolation")
    if not isolation["executed"] or not isolation["driver_completed"] or isolation["returncode"] != 0:
        raise AssertionError(isolation)
    early_exit = run_isolated({}, "import os\nos._exit(0)", run_root=output / "early-exit")
    if early_exit["driver_completed"]:
        raise AssertionError("Premature zero exit is not completed test evidence")
    private_files = {str(p.relative_to(ASSETS)): digest(p.read_bytes()) for p in sorted((ASSETS / "private").glob('*'))}
    result = {"version": "software-source-cpu-v0.15", "source": manifest(), "private_assets_sha256": private_files,
              "scope": "CPU rule witnesses and negative controls only; real model performance must be reported separately.",
              "controls": rows, "isolation_probe": isolation, "early_exit_probe": early_exit, "limits": LIMITS,
              "upstream_test_files": "Archived unchanged; the full upstream pytest suite was not executed in this bounded v0.15 preflight.",
              "model_runs": 0, "all_controls_pass": True}
    atomic_write(output / "report.json", json_bytes(result))
    print(json.dumps({"output": str(output), "controls": len(rows), "all_controls_pass": True}))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    main(parser.parse_args().output)
