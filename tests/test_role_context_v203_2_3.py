"""CPU-only contract controls: no provider, filesystem history, or World reads."""
import copy
from dataclasses import replace
import json

import pytest

from proworksim.software_context_compression_v175 import EvidenceStore
from proworksim.software_role_context_v203_2_3 import (
    Candidate, PresentedSource, SourceRejected, canonical, estimate_tokens,
    project_request, select_context,
)


def fixture():
    store = EvidenceStore("point", "episode", "alice")
    sources = []
    candidates = []
    for index, (kind, version, paths, text) in enumerate([
        ("code", {"commit": "current", "patch": "a"}, ["a.py"], "repair target target implementation"),
        ("test", {"commit": "current", "patch": "a"}, ["a.py"], "target public test passed"),
        ("test", {"commit": "current", "patch": "old"}, ["a.py"], "target public test passed"),
        ("risk", {"commit": "current", "patch": "a"}, ["b.py"], "unresolved hazard"),
    ]):
        message = {"role": "tool", "tool_call_id": f"call{index}", "content": json.dumps({
            "kind": kind, "version": version, "paths": paths, "text": text,
        })}
        reference = store.put(message, index + 2)
        sources.append(PresentedSource(f"s{index}", "episode", "alice", index + 2,
                                       1, message, reference))
        candidates.append(Candidate(f"s{index}", metadata_pointers={
            "kind": "/kind", "version": "/version", "paths": "/paths"}))
    return sources, candidates, store


def select(sources=None, candidates=None, **kwargs):
    if sources is None:
        sources, candidates, _ = fixture()
    options = dict(condition="K2", episode="episode", member="alice", decision_step=2,
                   task="target", role="reviewer", responsibilities=["a.py"],
                   current_version={"commit": "current", "patch": "a"}, budget_tokens=8192)
    options.update(kwargs)
    return select_context(sources, candidates, **options)


def baseline(sources):
    messages = [{"role": "system", "content": "rules"}, {"role": "user", "content": "task"}]
    for source in sources:
        messages.append({"role": "tool", "tool_call_id": source.message["tool_call_id"],
                         "content": "Earlier observation " + source.reference})
    messages += [{"role": "assistant", "content": "current action"},
                 {"role": "tool", "tool_call_id": "latest", "content": "latest observation"}]
    return {"messages": messages, "tools": [{"type": "function", "function": {"name": "context_read"}}],
            "max_tokens": 2000, "temperature": 0.3}


def test_k0_returns_existing_harness_request_exactly_without_reading_candidates():
    sources, candidates, _ = fixture()
    request = baseline(sources)
    out, proof = project_request(request, select([], candidates, condition="K0"),
                                 slots={}, request_budget_tokens=9999)
    assert out == request and out is not request
    assert proof["baseline_unchanged"] and not proof["request_projection_applied"]


def test_equal_pool_budget_rendering_only_ranking_differs():
    k1 = select(condition="K1")
    k2 = select(condition="K2")
    assert k1["proof"]["candidate_pool_sha256"] == k2["proof"]["candidate_pool_sha256"]
    assert k1["proof"]["budget_tokens_local_estimate"] == k2["proof"]["budget_tokens_local_estimate"]
    assert {c["candidate_id"]: c for c in k1["selected"]} == {c["candidate_id"]: c for c in k2["selected"]}
    assert k2["selected"][0]["source_id"] == "s1"
    scores = {row["candidate_id"]: row["score"] for row in k2["proof"]["ranking"]}
    cards = {card["source_id"]: card for card in k2["selected"]}
    assert scores[cards["s1"]["candidate_id"]]["exact_version"] == 8
    assert scores[cards["s2"]["candidate_id"]]["exact_version"] == 0
    assert scores[cards["s1"]["candidate_id"]]["version_bound_validation"] == 8
    assert scores[cards["s2"]["candidate_id"]]["version_bound_validation"] == 0


def test_k1_ignores_role_responsibility_and_version():
    a = select(condition="K1")
    b = select(condition="K1", role="developer", responsibilities=[], current_version="other")
    assert a == b


@pytest.mark.parametrize("mutation", [
    {"episode": "different"}, {"member": "bob"}, {"presented_step": 3},
    {"presented_step": -1}, {"origin_domain": "evaluator"}, {"origin_domain": "hidden"},
    {"owner_member": "bob", "published": False}, {"reference": "file:secret"},
    {"message": {"role": "assistant", "content": "private thought"}},
    {"message": {"role": "user", "content": "ordinary task instruction"}},
])
def test_rejects_sources_outside_actual_private_presented_prefix(mutation):
    sources, candidates, _ = fixture()
    sources[0] = replace(sources[0], **mutation)
    with pytest.raises(SourceRejected):
        select(sources, candidates)


def test_published_partner_evidence_still_requires_actual_presentation():
    sources, candidates, _ = fixture()
    sources[0] = replace(sources[0], owner_member="bob", published=True)
    assert select(sources, candidates)["proof"]["admitted"]
    with pytest.raises(SourceRejected):
        select(sources[1:], candidates)


@pytest.mark.parametrize("candidate", [
    Candidate("s0", start=-1), Candidate("s0", end=10**9),
    Candidate("s0", metadata_pointers={"kind": "/missing"}),
    Candidate("s0", metadata_pointers={"hidden_score": "/kind"}),
])
def test_rejects_fabricated_span_and_ungrounded_metadata(candidate):
    sources, _, _ = fixture()
    with pytest.raises(SourceRejected):
        select(sources, [candidate])


def test_protected_evidence_never_silently_truncated_and_intervention_rejected():
    sources, candidates, _ = fixture()
    candidates[0] = replace(candidates[0], protected=True)
    result = select(sources, candidates, budget_tokens=1)
    assert not result["selected"] and result["proof"]["unmet_protected"]
    assert not result["proof"]["admitted"]
    request = baseline(sources)
    out, proof = project_request(request, result, slots={}, request_budget_tokens=9999)
    assert out == request and not proof["request_projection_applied"]


def test_selected_text_provenance_full_reader_and_inputs_are_unchanged():
    sources, candidates, store = fixture()
    before = copy.deepcopy((sources, candidates, store.entries))
    result = select(sources, candidates)
    for card in result["selected"]:
        page = store.read({"reference": card["source_reference"]},
                          point_id="point", slot_id="episode", member_id="alice")
        assert card["text"] == page["text"]
        assert card["historical_evidence_not_current_validation"]
        with pytest.raises(PermissionError):
            store.read({"reference": card["source_reference"]}, point_id="point", slot_id="episode", member_id="bob")
    assert (sources, candidates, store.entries) == before
    assert result["proof"]["token_accounting"] == "local_estimate_only"
    assert not result["proof"]["provider_exact_tokens_claimed"]


def test_adapter_preserves_tool_wiring_options_and_recent_messages():
    sources, candidates, _ = fixture()
    request = baseline(sources)
    before = copy.deepcopy(request)
    out, proof = project_request(request, select(sources, candidates),
        slots={s.source_id: s.message_index for s in sources}, request_budget_tokens=9999)
    assert proof["request_projection_applied"]
    assert request == before and out["messages"][-2:] == request["messages"][-2:]
    assert {k: v for k, v in out.items() if k != "messages"} == {k: v for k, v in request.items() if k != "messages"}
    for i, message in enumerate(out["messages"]):
        assert {k: v for k, v in message.items() if k != "content"} == {k: v for k, v in request["messages"][i].items() if k != "content"}
    for source in sources:
        assert source.reference in out["messages"][source.message_index]["content"]


def test_adapter_rejects_missing_placeholder_and_full_request_overflow():
    sources, candidates, _ = fixture()
    selected = select(sources, candidates)
    request = baseline(sources)
    with pytest.raises(SourceRejected):
        project_request(request, selected, slots={s.source_id: 0 for s in sources}, request_budget_tokens=9999)
    out, proof = project_request(request, selected, slots={s.source_id: s.message_index for s in sources},
                                 request_budget_tokens=estimate_tokens(canonical(request)))
    assert out == request and not proof["admitted"] and proof["rejection"] == "whole_request_budget"


def test_full_card_budget_and_determinism():
    sources, candidates, _ = fixture()
    for budget in (0, 100, 500, 1000, 8192):
        a = select(sources, candidates, budget_tokens=budget)
        b = select(list(reversed(sources)), list(reversed(candidates)), budget_tokens=budget)
        assert a == b
        assert a["proof"]["selected_tokens_local_estimate"] <= budget
        assert estimate_tokens(a["rendered"]) <= budget


def v117_fixture():
    from test_history_compaction_v117 import request
    from proworksim.software_benchmark_history_v117 import project_observation_history, REFERENCE_KEY
    original, observations = request()
    base, evidence = project_observation_history(original, member_id="member_001", registered_observations=observations)
    sources, candidates = [], []
    for row in evidence["rewritten_observations"]:
        i = row["message_index"]
        marker = json.loads(base["messages"][i]["content"])[REFERENCE_KEY]
        reference = f'v117:{marker["original_content_sha256"]}:{marker["anchor_message_index"]}:{marker["anchor_content_sha256"]}'
        source = PresentedSource(f"v117-{i}", "episode", "alice", i, 1,
                                 original["messages"][i], reference)
        sources.append(source)
        start = source.message["content"].index(':', source.message["content"].index('"workspace_reference"')) + 1
        while source.message["content"][start].isspace():
            start += 1
        _, end = json.JSONDecoder().raw_decode(source.message["content"], start)
        candidates.append(Candidate(source.source_id, start, end,
                                   {"version": "/observation/workspace_reference"},
                                   field_pointer="/observation/workspace_reference"))
    return base, sources, candidates


def test_actual_v117_projection_preserves_anchor_dynamic_fields_and_tools():
    from proworksim.software_role_context_v203_2_3 import EVIDENCE_KEY, NOTICE_KEY
    base, sources, candidates = v117_fixture()
    selected = select(sources, candidates)
    out, proof = project_request(base, selected, slots={s.source_id:s.message_index for s in sources},
                                 request_budget_tokens=32768)
    assert proof["request_projection_applied"]
    assert out["messages"][-1] == base["messages"][-1]
    assert out["tools"] == base["tools"]
    for source in sources:
        body = json.loads(out["messages"][source.message_index]["content"])
        if source.message_index == min(s.message_index for s in sources):
            assert body.pop(EVIDENCE_KEY) == selected["selected"]
            assert body.pop(NOTICE_KEY)["lossless_full_history_reconstruction_claimed"] is False
        previous = json.loads(base["messages"][source.message_index]["content"])
        del previous["observation"]["workspace_reference"]
        assert body == previous
    assert [m for m in out["messages"] if m["role"] in ("assistant", "tool")] == [m for m in base["messages"] if m["role"] in ("assistant", "tool")]


@pytest.mark.parametrize("tamper", ["anchor", "marker", "old_dynamic"])
def test_actual_v117_adapter_rejects_corrupted_source_binding(tamper):
    from proworksim.software_role_context_v203_2_3 import V117_MARKER
    base, sources, candidates = v117_fixture()
    selected = select(sources, candidates)
    if tamper == "anchor":
        base["messages"][-1]["content"] += " "
    else:
        body = json.loads(base["messages"][sources[0].message_index]["content"])
        if tamper == "marker":
            body[V117_MARKER]["original_content_sha256"] = "a" * 64
        else:
            body["observation"]["current_version_test_coverage"]["passed"] = True
        base["messages"][sources[0].message_index]["content"] = json.dumps(body)
    with pytest.raises(SourceRejected):
        project_request(base, selected, slots={s.source_id:s.message_index for s in sources}, request_budget_tokens=32768)


def test_next_explicit_run_tests_is_role_relevance_not_completed_validation():
    sources, candidates, _ = fixture()
    data = json.loads(sources[0].message["content"])
    data["kind"] = "run_tests"
    sources[0] = replace(sources[0], message={**sources[0].message, "content":json.dumps(data)})
    result = select(sources[:1], candidates[:1])
    score = result["proof"]["ranking"][0]["score"]
    assert score["role"] == 12 and score["version_bound_validation"] == 0


def test_whole_structural_field_cards_create_real_role_ranking_difference():
    base, sources, _ = v117_fixture()
    source = sources[0]
    text = source.message["content"]
    candidates = []
    decoder = json.JSONDecoder()
    for name in ("messages", "current_version_test_coverage", "delivery_status"):
        start = text.index(':', text.index(json.dumps(name))) + 1
        while text[start].isspace():
            start += 1
        _, end = decoder.raw_decode(text, start)
        candidates.append(Candidate(source.source_id, start, end,
            {"version":"/observation/workspace_reference"}, field_pointer="/observation/" + name))
    developer = select([source], candidates, task="", role="developer")
    reviewer = select([source], candidates, task="", role="reviewer")
    assert developer["selected"][0]["metadata"]["kind"] == "message"
    assert reviewer["selected"][0]["metadata"]["kind"] == "test"
    assert developer["proof"]["candidate_pool_sha256"] == reviewer["proof"]["candidate_pool_sha256"]
    kwargs = dict(slots={source.source_id:source.message_index}, request_budget_tokens=32768)
    a, _ = project_request(base, developer, **kwargs)
    b, _ = project_request(base, reviewer, **kwargs)
    assert a != b
    assert all(row["score"]["version_bound_validation"] == 0 for row in reviewer["proof"]["ranking"])
    broken = replace(candidates[0], end=candidates[0].end-1)
    with pytest.raises(SourceRejected):
        select([source], [broken])


def test_unselected_v117_fields_are_removed_not_left_visible_under_original_keys():
    from proworksim.software_role_context_v203_2_3 import EVIDENCE_KEY, NOTICE_KEY
    base, sources, candidates = v117_fixture()
    # Enough for one complete card plus notice, not the entire pool.
    one = select(sources[:1], candidates[:1])
    budget = one["proof"]["selected_tokens_local_estimate"] + 10
    selection = select(sources, candidates, budget_tokens=budget)
    assert 0 < len(selection["selected"]) < len(candidates)
    out, proof = project_request(base, selection, slots={s.source_id:s.message_index for s in sources},
                                 request_budget_tokens=32768)
    assert proof["request_projection_applied"] and proof["selection_not_only_duplicate_salience"]
    assert len(proof["eligible_dynamic_fields_removed"]) == len(candidates)
    selected_cards = []
    for source in sources:
        body = json.loads(out["messages"][source.message_index]["content"])
        assert "workspace_reference" not in body["observation"]
        selected_cards.extend(body.get(EVIDENCE_KEY, []))
    assert selected_cards == selection["selected"]
    assert all(c["reference_semantics"] == "audit_locator_no_model_reader_after_dynamic_selection" for c in selected_cards)
    assert out["messages"][-1] == base["messages"][-1]
    assert NOTICE_KEY in json.loads(out["messages"][min(s.message_index for s in sources)]["content"])


@pytest.mark.parametrize("budget, applies", [(0, False), (100, True)])
def test_empty_v117_selection_has_notice_or_explicit_budget_rejection(budget, applies):
    from proworksim.software_role_context_v203_2_3 import EVIDENCE_KEY, NOTICE_KEY
    base, sources, candidates = v117_fixture()
    selected = select(sources, candidates, budget_tokens=budget)
    assert selected["selected"] == []
    out, proof = project_request(base, selected, slots={s.source_id:s.message_index for s in sources},
                                 request_budget_tokens=32768)
    assert proof["request_projection_applied"] is applies
    if applies:
        body = json.loads(out["messages"][min(s.message_index for s in sources)]["content"])
        assert body[EVIDENCE_KEY] == [] and NOTICE_KEY in body
        assert proof["eligible_dynamic_fields_removed"]
    else:
        assert not proof["admitted"] and out == base
