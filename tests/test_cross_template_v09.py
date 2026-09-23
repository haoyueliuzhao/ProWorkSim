"""One representative integration regression for the new application chain.

The larger formal experiment owns the other two error-attribution branches; this
regression exercises a real publication-created obligation and actual report
issue repair through public ports, including the fixed historical control.
"""

from scripts.cross_template_experiment import run_case


def test_release_chain_and_real_report_issue_repair(tmp_path):
    result = run_case("report_error", tmp_path / "cross-template")
    assert result["construction_error"] is None, result["construction_error"]
    assert result["passed"], [c for c in result["checks"] if not c["passed"]]
    assert result["outcome"]["before_review"] == {
        "A_quality": True,
        "B_interface_fidelity": True,
        "B_expression": False,
        "overall_goal": False,
    }
    assert result["outcome"]["final"] == {
        "A_quality": True,
        "B_interface_fidelity": True,
        "B_expression": True,
        "overall_goal": True,
    }
    assert result["outcome"]["injected_root_errors"] == 1
