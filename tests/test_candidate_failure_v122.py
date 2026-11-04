"""Narrow measurement predicates; reuse the single completed real-patch proof."""
from __future__ import annotations

import copy
from pathlib import Path

import pytest

from proworksim import software_benchmark_candidate_failure_v122 as repair
from proworksim.software_benchmark_candidates_v054 import reference, write_new

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT/'runs/software-benchmark-v118/project-repaired-r1/grading-v120/score-8039'
PROOF = ROOT/'artifacts/software-benchmark-v122/pylint-patch-repair-r1/cpu-proof.json'


def test_exact_preserved_candidate_is_failure_without_rewriting_official_receipt():
    before = reference(FOLDER/'receipt.json')
    result = repair.derive_resolution(reference(FOLDER/'request.json'), reference(PROOF))
    assert result['status'] == 'adjudicated_candidate_code_failure'
    assert result['resolved'] is False and result['actual_patch_application_succeeded'] is True
    assert result['original_report']['patch_successfully_applied'] is False
    assert result['official_scoring_rerun'] is False and result['new_gold_empty_controls_needed'] is False
    assert reference(FOLDER/'receipt.json') == before


def test_missing_application_proof_cannot_change_unknown_to_failure(tmp_path):
    proof = repair.load(reference(PROOF))
    proof['exact_patch_application_verified'] = False
    ref = write_new(tmp_path/'unproven.json', proof)
    with pytest.raises(ValueError, match='completed CPU proof'):
        repair.derive_resolution(reference(FOLDER/'request.json'), ref)


def test_an_actual_environment_failure_is_not_adjudicated_as_candidate_failure(monkeypatch):
    original = repair.load
    receipt_path = str((FOLDER/'receipt.json').resolve())
    def changed(ref):
        value = original(ref)
        if ref['path'] == receipt_path:
            value = copy.deepcopy(value)
            value['official_result'][1][repair.TASK]['infra_failure'] = True
        return value
    monkeypatch.setattr(repair, 'load', changed)
    with pytest.raises(ValueError, match='non-infra'):
        repair.derive_resolution(reference(FOLDER/'request.json'), reference(PROOF))


def test_missing_symbol_claim_refused_when_candidate_retains_import():
    source = 'import re\nSPECIAL_OBJ = re.compile("literal")\n'
    with pytest.raises(ValueError, match='still defines'):
        repair.missing_binding_evidence(source, source)
