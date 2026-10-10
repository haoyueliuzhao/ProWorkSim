"""Small policy controls only; no world route, tokenizer, model or API."""
import copy

import pytest

from proworksim.software_organization_v042 import build_test_report
from proworksim.storage import digest, json_bytes
from scripts.software_organization_admission_v043 import (
    EvidenceReader, SELF, _validate_current_sources, margin_record, reference, verify_encoding, verify_report,
)
from test_software_organization_v042 import identity, visible_fixture


def test_exact_source_bindings_allow_another_checkout_and_reject_changed_runtime(tmp_path):
    creator, frozen = tmp_path / "creator", tmp_path / "frozen"
    name = "src/proworksim/software_organization_v042.py"
    for root in (creator, frozen):
        (root / SELF).parent.mkdir(parents=True)
        (root / SELF).write_text("Explicit source-binding CPU fixture, not executable admission evidence")
        (root / name).parent.mkdir(parents=True)
        (root / name).write_text("Same frozen world bytes")
    value = {"source_files": {name: digest((creator / name).read_bytes())},
             "admission_implementation": reference(creator / SELF)}
    _validate_current_sources(value, EvidenceReader(), frozen)
    (frozen / name).write_text("Changed page/runtime behavior")
    with pytest.raises(ValueError, match="source/evidence SHA"):
        _validate_current_sources(value, EvidenceReader(), frozen)


def encoding_fixture(tokens):
    request = {"messages": [{"role": "user", "content": "Explicit stored encoding fixture"}], "max_tokens": 2048}
    prompt, ids = "Explicit saved native prompt fixture; no tokenizer called", [1] * tokens
    encoding = {"rendered_prompt": prompt, "input_ids": ids, "prompt_tokens": tokens,
        "input_ids_sha256": digest(json_bytes(ids)), "rendered_prompt_sha256": digest(prompt.encode()),
        "context_limit": 16384, "reserved_output_tokens": 2048, "headroom_tokens": 14336 - tokens,
        "fits": tokens <= 14336, "native_projection": {"request_sha256": digest(json_bytes(request))}}
    return request, encoding


def test_actual_selected_hard_capacity_is_mandatory_even_with_trustworthy_encoding():
    request, encoding = encoding_fixture(14336)
    assert verify_encoding(request, encoding) == 14336
    request, encoding = encoding_fixture(14337)
    with pytest.raises(ValueError, match="actual selected hard context capacity exceeded"):
        verify_encoding(request, encoding)


def test_untrusted_body_or_actor_identity_cannot_receive_admission():
    report = build_test_report(visible_fixture(), actor_id="member_001", event_identity=identity())
    assert verify_report(report) == report
    changed = copy.deepcopy(report)
    changed["pages"][0]["text"] += "Unarchived extra body"
    with pytest.raises(ValueError, match="untrusted report"):
        verify_report(changed)
    changed = copy.deepcopy(report)
    changed["actor_id"] = "member_002"
    with pytest.raises(ValueError, match="actor.*identity"):
        verify_report(changed)


def test_original_margin_deficits_are_kept_as_nonblocking_diagnostics():
    locations = [margin_record({"route_id": "original-route", "stage": str(tokens)}, tokens)
                 for tokens in (13312, 13382, 14284)]
    assert [row["headroom_after_margin_tokens"] for row in locations] == [0, -70, -972]
    assert [row["margin_satisfied"] for row in locations] == [True, False, False]
    assert all(row["original_margin_tokens"] == 1024 and row["blocks_v043_first_block"] is False for row in locations)


def test_changed_evidence_file_cannot_be_reused_under_its_old_reference(tmp_path):
    path = tmp_path / "original-qualification.json"
    path.write_bytes(json_bytes({"passed": False, "fits": True}))
    original = reference(path)
    path.write_bytes(json_bytes({"passed": True, "fits": False}))
    with pytest.raises(ValueError, match="source/evidence SHA"):
        EvidenceReader().json(original)
