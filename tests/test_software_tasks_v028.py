"""Source lineage, patch fidelity and acceptance-boundary regression guards."""
import copy
import json
import shutil

import pytest

from proworksim import software_tasks_v028 as source
from proworksim.software_sources_v027 import validate_derived_tasks


def test_frozen_sources_are_whole_repository_disjoint():
    partition = json.loads((source.ASSETS / "source-partition.json").read_text())
    tasks = [json.loads(p.read_text()) for p in source.ASSETS.glob("*/derived-task.json")]
    assert validate_derived_tasks(partition, tasks)["tasks"] == 3
    cases = [source.build_case(task) for task in source.TASK_IDS]
    assert {case["purpose"] for case in cases} == {
        "policy_training", "contribution_development", "independent_confirmation"}
    assert [case["task_id"] for case in cases if case["training_eligible"]] == [source.TASK_IDS[0]]
    for case in cases:
        assert all(owner is None for owner in case["initial_owners"].values())
        assert not any("reference" in name or "acceptance" in name or "defect.patch" in name
                       for name in case["files"])
        assert "NotImplementedError" in case["files"]["consumer.py"]


@pytest.mark.parametrize("task_id", source.TASK_IDS)
def test_original_swe_mutation_reverses_exactly_without_touching_other_files(task_id):
    files = source.original_files(task_id)
    mutation = source._mutation(task_id)
    broken = source.apply_mutation(files, mutation)
    assert broken != files
    assert source.apply_mutation(broken, mutation, reverse=True) == files
    with pytest.raises(ValueError, match="context"):
        source.apply_mutation(broken, mutation)


def test_tampered_upstream_source_is_rejected_before_execution(tmp_path, monkeypatch):
    destination = tmp_path / "assets"
    shutil.copytree(source.ASSETS, destination)
    monkeypatch.setattr(source, "ASSETS", destination)
    path = destination / "sqlparse/upstream/sqlparse/sql.py"
    path.write_text(path.read_text() + "\n# unpinned edit\n")
    with pytest.raises(ValueError, match="Pinned upstream source changed"):
        source.build_case(source.TASK_IDS[0])


def test_joint_witness_hash_is_enforced(tmp_path, monkeypatch):
    destination = tmp_path / "assets"
    shutil.copytree(source.ASSETS, destination)
    monkeypatch.setattr(source, "ASSETS", destination)
    path = destination / "sqlparse/consumer-reference.py"
    path.write_text(path.read_text() + "\n# witness changed\n")
    with pytest.raises(ValueError, match="joint solution witness changed"):
        source.reference_solution(source.TASK_IDS[0])


def test_acceptance_rejects_actor_changes_to_frozen_tests_without_execution(tmp_path, monkeypatch):
    case = source.build_case(source.TASK_IDS[0])
    files = copy.deepcopy(case["files"])
    files["test_visible.py"] = "print('all pass')\n"
    monkeypatch.setattr(source, "run_isolated", lambda *a, **k: pytest.fail("must reject before execution"))
    with pytest.raises(ValueError, match="Only public editable paths"):
        source.assess(case["task_id"], files, run_root=tmp_path)
