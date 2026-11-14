"""Focused source coordinates/fallback controls, complementary to real SDK tape replay."""
import copy
from types import SimpleNamespace

import pytest

from proworksim.software_benchmark_history_v117 import SummarizingManagedContextTransport, project_observation_history
from proworksim.software_role_context_runtime_v203_2_3_r3 import install, resolve_sources, SourceResolutionUnavailable
from proworksim.software_role_context_v203_2_3 import estimate_tokens
from test_history_compaction_v117 import request as original_request


def projected(*, condensed=False):
    request, observations = original_request()
    if condensed:
        request["messages"] = [request["messages"][0],
            {"role": "user", "content": "Summary replacing earlier complete rounds; original observations are absent."},
            {"role": "user", "content": observations[-2]}, {"role": "user", "content": observations[-1]}]
    feedback = {"role": "user", "content": "A previously presented, now historicalized format feedback"}
    request["messages"].insert(1, feedback)
    mapping = [i for i in range(len(request["messages"])) if i != 1]
    formatted = {**copy.deepcopy(request), "messages": [copy.deepcopy(request["messages"][i]) for i in mapping]}
    baseline, history = project_observation_history(formatted, member_id="member_001", registered_observations=observations)
    return request, baseline, {"selected_indices": mapping, "removed_indices": [1]}, history, observations


def test_removed_feedback_uses_projected_to_original_mapping_and_original_hash():
    req, base, feedback, history, observations = projected()
    sources = resolve_sources(req, base, feedback, history, set(observations))
    assert sources and all(original > index for index, original, *_ in sources)
    assert all(message == req["messages"][original] for _, original, message, _, _ in sources)
    assert any(req["messages"][index].get("content") not in observations for index, *_ in sources)


def test_after_condenser_only_current_literal_sources_are_used():
    req, base, feedback, history, observations = projected(condensed=True)
    sources = resolve_sources(req, base, feedback, history, set(observations))
    assert len(sources) == 1
    assert sources[0][2]["content"] == observations[-2]
    assert all(source[2]["content"] not in observations[:2] for source in sources)


@pytest.mark.parametrize("tamper", ["missing_registration", "wrong_index_map", "wrong_source_hash"])
def test_unprovable_source_is_not_reconstructed_from_private_archive(tamper):
    req, base, feedback, history, observations = projected()
    if tamper == "missing_registration":
        observations = observations[1:]
    elif tamper == "wrong_index_map":
        feedback["selected_indices"] = list(range(len(base["messages"])))
    else:
        history["rewritten_observations"][0]["original_content_sha256"] = "0" * 64
    with pytest.raises(SourceResolutionUnavailable):
        resolve_sources(req, base, feedback, history, set(observations))


@pytest.mark.parametrize("condition", ["K0", "K1", "K2"])
def test_candidate_source_failure_never_changes_baseline_or_aborts_sdk(condition, tmp_path):
    req, base, feedback, history, observations = projected()

    class CapturedTransport(SummarizingManagedContextTransport):
        def __init__(self):
            pass

        def select_for_member(self, request, member):
            return copy.deepcopy(base), copy.deepcopy(feedback), copy.deepcopy(history)

    workers = {member: SimpleNamespace(transport=CapturedTransport(), meter={"decisions": 0},
        _observation_texts=observations[1:]) for member in ("member_001", "member_002")}
    runtime = SimpleNamespace(policies=workers, owner=SimpleNamespace(window_id="unit-scope"))
    install(runtime, condition=condition, folder=tmp_path, budget_tokens=4096, count=estimate_tokens, request_budget_tokens=131072)
    selected, _, audited = workers["member_001"].transport.select_for_member(req, "member_001")
    assert selected == base
    receipt = audited["role_context_projection"]
    assert receipt["proof"]["request_projection_applied"] is False
    if condition == "K0":
        assert receipt["K0_candidate_extraction_bypassed"]
        assert receipt["proof"]["admitted"] is True
    else:
        assert receipt["proof"]["admitted"] is False
        assert receipt["proof"]["rejection"] == "original_registered_observation_unavailable"
        assert receipt["proof"]["safe_fallback"] == "original_v117_baseline"
