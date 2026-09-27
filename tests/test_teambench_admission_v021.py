from __future__ import annotations

import hashlib
import json

import pytest

from scripts.teambench_admission_v021 import (
    COMMIT,
    check_candidate_inputs,
    decompose_score,
    native_contract_conflicts,
    verify_assets,
)


def test_execution_rejects_resealed_but_unreviewed_bytes(tmp_path, monkeypatch):
    from scripts import teambench_admission_v021 as admission

    path = tmp_path / "files/generators/base.py"
    path.parent.mkdir(parents=True)
    reviewed = b"# reviewed\n"
    path.write_bytes(b"# different code\n")
    monkeypatch.setattr(admission, "REVIEWED", {
        "generators/base.py": hashlib.sha256(reviewed).hexdigest()})
    (tmp_path / "manifest.json").write_text(json.dumps({
        "commit": COMMIT,
        "files": [{"path": "generators/base.py", "sha256": admission.digest(path)}]}))
    with pytest.raises(ValueError, match="unreviewed bytes"):
        verify_assets(tmp_path)


def test_missing_expected_and_conflicting_expected_fail_closed(tmp_path):
    with pytest.raises(ValueError, match="missing native expected"):
        check_candidate_inputs(tmp_path)
    (tmp_path / "reports").mkdir()
    expected = {"dedup_id": "3", "dedup_category": "sales",
                "batch1_missing_category_ids": ["1", "2", "3"]}
    (tmp_path / "reports/expected.json").write_text(json.dumps(expected))
    assert native_contract_conflicts(expected)
    with pytest.raises(ValueError, match="contradictory"):
        check_candidate_inputs(tmp_path)


@pytest.mark.parametrize("attestation_ok,passed,failures", [
    (True, 15, ["missing_category_fill_fail"]),
    (False, 14, ["missing_category_fill_fail", "bad_attestation"]),
])
def test_product_score_is_separate_from_verifier_execution(attestation_ok, passed, failures):
    score = {"secondary": {"checks_total": 16, "checks_passed": passed},
             "failure_modes": failures, "pass": False}
    row = decompose_score(score)
    assert row["artifact_checks_total"] == 15
    assert row["artifact_checks_passed"] == 14
    assert row["attestation_verdict_check_passed"] is attestation_ok
    assert row["verifier_execution_or_independence_measured"] is False


def test_d2_fixed_expected_hash_and_structure_are_both_required(tmp_path):
    from scripts.teambench_admission_v021 import digest, validate_d2_expected

    path = tmp_path / "expected.json"
    expected = {
        "row_count": 1, "columns": ["id", "name", "score", "department"],
        "score_col": "score", "dept_col": "department", "dup_ids": ["3"],
        "dup_winner_scores": {"3": "40"}, "out_of_range_ids": [], "missing_ids": ["3"],
        "low_score_missing_dept_id": "3", "correct_fill": "MISSING", "review_needed_id": "3",
    }
    path.write_text(json.dumps(expected))
    frozen = digest(path)
    assert validate_d2_expected(path, frozen) == expected
    expected["row_count"] = 2
    path.write_text(json.dumps(expected))
    with pytest.raises(ValueError, match="frozen instance SHA256"):
        validate_d2_expected(path, frozen)
    del expected["dup_winner_scores"]
    path.write_text(json.dumps(expected))
    with pytest.raises(ValueError, match="expected schema"):
        validate_d2_expected(path, digest(path))
