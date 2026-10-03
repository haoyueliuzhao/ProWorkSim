"""Recovery publication must select its own report pair."""

import json
from pathlib import Path
from types import SimpleNamespace

from scripts import finish_software_development_v028 as finisher


def test_recovery_finisher_passes_distinct_report_prefix(tmp_path, monkeypatch):
    calls = []
    root = tmp_path / "recovery"

    def execute(argv, **kwargs):
        calls.append(argv)
        if "supervise" in argv:
            destination = Path(argv[argv.index("--output") + 1])
            destination.mkdir()
            (destination / "plan.json").write_text("{}")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(finisher.subprocess, "run", execute)
    result = finisher.run(tmp_path / "plan.json", root, tmp_path,
                          report_prefix="software-development-v028-recovery")
    assert result["status"] == "reported"
    report_command = calls[1]
    assert report_command[report_command.index("--output-prefix") + 1] == "software-development-v028-recovery"
    saved = json.loads((tmp_path / "recovery-finish.json").read_text())
    assert saved["report_prefix"] == "software-development-v028-recovery"
