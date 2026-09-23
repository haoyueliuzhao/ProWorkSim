"""Independent multi-source content, exact contribution dependencies and policies."""

import copy

import pytest

from proworksim.adapters.capabilities import encode
from proworksim.domains.work_product import evaluate_submission, validate_content_contract
from test_work_capabilities import ledger


def specification():
    return {
        "kind": "json_linear_sources",
        "path": ["total"],
        "constant": 5,
        "sources": [
            {"alias": "external", "kind": "json_field", "source_path": ["rate"],
             "reference_path": ["refs", "external"], "coefficient": 2},
            {"alias": "local", "kind": "xlsx_cell", "sheet": "Inputs", "cell": "A1",
             "reference_path": ["refs", "local"], "coefficient": -1},
        ],
    }


def fixture(tmp_path, split=False, value=22, external_value=10):
    external = {"object_id": "external", "version_id": "v1"}
    local = {"object_id": "local", "version_id": "v1"}
    refs = {"external": external, "local": local}
    docs = [("total", {"total": value}), ("refs", {"refs": refs})] if split else [
        ("report", {"total": value, "refs": refs})]
    values = [(aid, "json", [encode("json", data)]) for aid, data in docs]
    values.extend([
        ("note", "json", [encode("json", {"note": "Unrelated delivery note"})]),
        ("external", "json", [encode("json", {"rate": external_value})]),
        ("local", "xlsx", [encode("xlsx", {"Inputs!A1": 3})]),
    ])
    adoptions = {}
    for alias, ref in refs.items():
        adoptions["B::work::" + alias] = {
            **ref, "target_version": "v1", "policy": "fixed", "alias": alias,
            "project_id": "B", "work_id": "B::work", "work_ids": ["B::work"],
            "requirement_version": 1,
        }
    return ledger(
        tmp_path, values, {"content_checks": [specification()]},
        submitted={**{aid: "v1" for aid, _ in docs}, "note": "v1"}, adoptions=adoptions,
        dependencies={(aid, "v1"): [external, local] for aid, _ in docs},
    )


@pytest.mark.parametrize("split", [False, True])
def test_scalar_reference_is_independent_and_accepts_two_organizations(tmp_path, monkeypatch, split):
    from proworksim.spreadsheet import Spreadsheet

    args = fixture(tmp_path, split)
    monkeypatch.setattr(Spreadsheet, "value", lambda *_: pytest.fail("Used production calculator"))
    before = copy.deepcopy((args[1], args[3]))
    result = evaluate_submission(*args)
    assert result["passed"]
    check = result["checks"][0]
    assert check["actual"] == check["expected"] == 22
    assert [source["contribution"] for source in check["sources"]] == [20, -3]
    assert all("note" not in [ref["object_id"] for ref in source["binding_files"]]
               for source in check["sources"])
    assert (args[1], args[3]) == before


@pytest.mark.parametrize("contributor,source", [("total", "external"), ("total", "local"),
                                                ("refs", "external"), ("refs", "local")])
def test_every_actual_scalar_or_reference_contributor_declares_its_sources(tmp_path, contributor, source):
    args = fixture(tmp_path, split=True)
    metadata = args[1]["artifacts"][contributor]["versions"]["v1"]
    metadata["derived_from"] = [ref for ref in metadata["derived_from"] if ref["object_id"] != source]
    result = evaluate_submission(*args)
    assert not result["passed"]
    assert "exact source dependency" in result["checks"][0]["reason"]


@pytest.mark.parametrize("field,value", [("requirement_version", 2), ("work_id", "B::other"),
                                        ("project_id", "A"), ("target_version", "v2")])
def test_each_source_uses_its_own_exact_submission_work_context(tmp_path, field, value):
    args = fixture(tmp_path)
    binding = args[3]["adoption_snapshot"]["B::work::local"]
    binding["policy"] = "current_published"
    binding[field] = value
    assert not evaluate_submission(*args)["passed"]


def test_multisource_actual_boolean_and_wrong_scalar_are_rejected(tmp_path):
    for number in (True, 23):
        args = fixture(tmp_path / str(number), value=number)
        assert not evaluate_submission(*args)["passed"]


@pytest.mark.parametrize("patch", [
    {"constant": True}, {"constant": float("inf")}, {"sources": []},
    {"sources": [specification()["sources"][0]]},
    {"sources": [specification()["sources"][0]] * 2},
])
def test_invalid_linear_contracts_fail_at_registration(patch):
    with pytest.raises(ValueError):
        validate_content_contract({"content_checks": [{**specification(), **patch}]})


@pytest.mark.parametrize("field,value", [("coefficient", False), ("coefficient", float("nan")),
                                        ("source_path", []), ("python", "anything")])
def test_source_contract_is_finite_and_not_executable(field, value):
    spec = specification()
    spec["sources"][0][field] = value
    with pytest.raises(ValueError):
        validate_content_contract({"content_checks": [spec]})


@pytest.mark.parametrize("source_value", [True, False, "10", None])
def test_linear_source_values_must_be_numeric_not_coercible(tmp_path, source_value):
    result = evaluate_submission(*fixture(tmp_path, external_value=source_value))
    assert not result["passed"]
    assert "finite number" in result["checks"][0]["reason"]


def test_overflowed_float_combination_is_a_failed_check_not_an_exception(tmp_path):
    result = evaluate_submission(*fixture(tmp_path, external_value=1e308))
    assert not result["passed"]
    assert "remain finite" in result["checks"][0]["reason"]


@pytest.mark.parametrize(
    "case", ["combined_correct", "split_correct", "combined_wrong_upstream", "split_wrong_upstream"]
)
def test_public_sessions_continue_after_one_source_change(tmp_path, case):
    from scripts.multisource_experiment import run_case

    result = run_case(case, tmp_path)
    assert result["construction_error"] is None, result["construction_error"]
    assert result["passed"], [check for check in result["checks"] if not check["passed"]]
