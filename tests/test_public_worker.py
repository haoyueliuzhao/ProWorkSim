"""The procedural worker must progress or wait using the actual public interface."""

import pytest

from scripts.public_worker_experiment import run_case


@pytest.mark.parametrize("case", ["existing", "published", "requestable", "missing", "unavailable"])
def test_public_worker_finite_contracts(tmp_path, case):
    result = run_case(tmp_path, case)
    assert result["error"] is None, result["error"]
    assert result["passed"], result
