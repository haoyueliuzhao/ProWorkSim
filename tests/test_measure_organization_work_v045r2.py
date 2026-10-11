"""Only original opportunity receipts gain a new source; work semantics do not."""
import ast
from collections import defaultdict
import copy
import inspect

from scripts import measure_organization_work_v045 as previous
from scripts import measure_organization_work_v045r2 as revised
from tests.test_measure_organization_budget_v045 import fixture, mutate
from tests.test_measure_organization_work_v045 import Archive, program_fixture, ref


def opportunity_reader(original):
    data = revised.Evidence.__new__(revised.Evidence)
    data.result, data.budget, data.evidence = (original[k] for k in ("result", "budget", "evidence"))
    data.experience = original["events"]
    data.by_kind = defaultdict(list)
    # This fixture has one earlier charged call without its optional resource
    # rows. Keep only the target call in the completeness check after resolving.
    for row in data.experience:
        data.by_kind[row["kind"]].append(row)
    data.gaps, data.opportunities = [], []
    data.experience_source = {"path": "fixture", "sha256": "fixture"}
    return data


def test_work_resource_uses_original_pre_shared_preparation_without_changing_ledger():
    original, _ = fixture()
    frozen = copy.deepcopy(original)
    data = opportunity_reader(original)
    data._opportunities()
    assert len(data.opportunities) == 1
    assert data.gaps == [{"reason": "incomplete_original_opportunity_resource_receipts"}]
    resource = data.resource({"call_id": "new"})
    assert resource["status"] == "recorded"
    assert resource["prompt_tokens"] == 13278 and resource["hard_headroom_tokens"] == 1058
    assert resource["team_available_tokens_before_opportunity"] == 1438
    assert resource["preparation_source"] == "original_start_before_shared_admission"
    assert resource["actual_generation_started"] is False
    assert original == frozen


def test_work_does_not_invent_preparation_from_member_terminal():
    original, _ = fixture()
    mutate(original, "missing_prep")
    data = opportunity_reader(original)
    data._opportunities()
    assert data.opportunities == []
    assert data.resource({"call_id": "new"})["status"] == "measurement_pending"


def test_aggregation_is_exact_frozen_function_and_shared_source_preserves_use(tmp_path):
    assert ast.dump(ast.parse(inspect.getsource(previous.measure_episode))) == ast.dump(
        ast.parse(inspect.getsource(revised.measure_episode)))
    folder = program_fixture(tmp_path)
    before = {str(p): p.read_bytes() for p in folder.rglob("*") if p.is_file()}
    old, new = previous.measure_episode(folder), revised.measure_episode(folder)
    def strip(value):
        if isinstance(value, dict):
            return {k: strip(v) for k, v in value.items() if k not in {"version", "preparation_source"}}
        return [strip(v) for v in value] if isinstance(value, list) else value
    assert new["status"] == "measured", new["measurement_gaps"]
    assert strip(old) == strip(new)
    assert all(p.read_bytes() == before[str(p)] for p in folder.rglob("*") if p.is_file())


def test_three_structure_unknowns_remain_s1_not_applicable(tmp_path):
    archive = Archive(tmp_path, condition="S1", members=1)
    prior = ref("member_001", "v1")
    for index in range(2, 5):
        current = archive.version("member_001", "v" + str(index), "def bad(:\n")
        archive.edit("member_001", prior, current)
        prior = current
    folder = archive.finish()
    old, new = previous.measure_episode(folder), revised.measure_episode(folder)
    assert new["pending_program_relations"] == old["pending_program_relations"]
    assert len(new["pending_program_relations"]) == 3
    assert new["cross_member_applicability"] == "not_applicable_no_partner"
    assert new["has_evidenced_cross_member_use"] is False
