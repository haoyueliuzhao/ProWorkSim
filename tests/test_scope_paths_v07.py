"""Real session regression for exact same-project sharing and narrow adoption."""

import pytest

from scripts.scope_paths_experiment import run_group


@pytest.mark.parametrize("group", ["share", "adopt_initial", "adopt_update"])
def test_authorized_scope_paths_and_negative_controls(tmp_path, group):
    report = run_group(group, tmp_path)
    assert report["construction_error"] is None, report["construction_error"]
    failed = [check for check in report["checks"] if not check["passed"]]
    assert failed == [], failed
