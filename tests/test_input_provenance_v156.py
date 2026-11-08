"""CPU-only provenance, identity and double-ledger controls; no model/network."""

from __future__ import annotations

import copy
import json

import pytest

from proworksim import software_input_provenance_v156 as p


def identity(request="request-1", attempt="attempt-1"):
    return {
        "request_id": request,
        "episode_id": "episode-1",
        "member_id": "member_001",
        "decision_id": "decision-1",
        "attempt_id": attempt,
        "model_alias": "deepseek-flash",
        "request_time": "2026-11-08T00:00:00+00:00",
        "purpose": "agent",
    }


def source(category, number=1):
    return p.SourceFragment(
        category,
        f"source-{category}-{number}",
        f"event-{number}",
        "member_002" if category == "Peer-message" else "member_001",
        "summary" if category == "Summary" else "raw",
        artifact_sha256="a" * 64 if category == "Artifact" else None,
        version_sha256="b" * 64 if category in {"Artifact", "Retrieved"} else None,
    )


def request(request_id="request-1", attempt_id="attempt-1"):
    fragments = tuple(
        p.TextSegment('same "中文\n' + str(i), source(category, i))
        for i, category in enumerate(p.PRIMARY_CATEGORIES)
    )
    return p.build_request(
        {
            "model": "deepseek-flash",
            "messages": [
                {
                    "role": p.AnnotatedText((p.TextSegment("user", source("Base/Template")),)),
                    "content": p.AnnotatedText(fragments),
                }
            ],
            "max_tokens": 100,
            "temperature": 1.0,
        },
        identity(request_id, attempt_id),
        template_source=source("Base/Template", 99),
    )


def response(built, prompt=100, output=3, cache=20, **kwargs):
    body = {
        "id": "response-" + built.manifest["identity"]["request_id"],
        "model": "deepseek-flash",
        "system_fingerprint": "fp1",
        "usage": {
            "prompt_tokens": prompt,
            "completion_tokens": output,
            "total_tokens": prompt + output,
            "prompt_cache_hit_tokens": cache,
            "prompt_cache_miss_tokens": prompt - cache,
        },
        "choices": [
            {
                "finish_reason": "tool_calls",
                "message": {
                    "tool_calls": [
                        {"id": "tool-1", "function": {"name": "send_message", "arguments": "{}"}}
                    ]
                },
            }
        ],
    }
    body.update(kwargs)
    return p.capture_response(
        built, body, outcome="success", http_status=200, response_time="2026-11-08T00:00:01+00:00"
    )


def mapping(built, *, domain="synthetic_control"):
    spans = [
        s for s in built.manifest["spans"] if s["semantic_input"] and s["kind"] == "text_fragment"
    ]
    tokens = [
        {"index": i, "token_id": i, "payload_ranges": [[s["payload_start"], s["payload_end"]]]}
        for i, s in enumerate(spans)
    ]
    evidence = {
        "domain": domain,
        "payload_sha256": built.manifest["payload_sha256"],
        "token_ids_sha256": p.digest(p.canonical([t["token_id"] for t in tokens]).encode()),
        "tokenizer_id": "CPU-span-fixture",
    }
    return tokens, evidence


def test_eight_mutually_exclusive_sources_and_actual_json_escape_offsets():
    built = request()
    assert p.verify_request(built)
    raw = json.loads(built.payload_bytes)
    assert raw["messages"][0]["content"].startswith('same "中文\n0')
    spans = [
        s
        for s in built.manifest["spans"]
        if s["json_pointer"] == "/messages/0/content" and s["kind"] == "text_fragment"
    ]
    assert [s["source"]["category"] for s in spans] == list(p.PRIMARY_CATEGORIES)
    for i, span in enumerate(spans):
        piece = built.payload_bytes[span["payload_start"] : span["payload_end"]]
        assert json.loads('"' + piece.decode() + '"') == 'same "中文\n' + str(i)
        assert span["decoded_text_sha256"] == p.digest(('same "中文\n' + str(i)).encode())
    assert len({s["occurrence_id"] for s in spans}) == 8


def test_identical_text_sources_bind_tree_positions_not_text_search():
    own = p.TextSegment("identical", source("Self-history"))
    peer = p.TextSegment("identical", source("Peer-message"))
    built = p.build_request(
        {"messages": [{"content": p.AnnotatedText((own, peer, peer))}]}, identity()
    )
    a = [s for s in built.manifest["spans"] if s["kind"] == "text_fragment"]
    assert [x["source"]["category"] for x in a] == ["Self-history", "Peer-message", "Peer-message"]
    assert len({x["payload_start"] for x in a}) == 3
    assert a[1]["source"] == a[2]["source"] and a[1]["occurrence_id"] != a[2]["occurrence_id"]


def test_unregistered_text_stays_unattributed_despite_template_marker():
    built = p.build_request(
        {"model": "x", "messages": [{"role": "user", "content": "unknown"}]},
        identity(),
        template_source=source("Base/Template"),
    )
    body = [
        s
        for s in built.manifest["spans"]
        if s["json_pointer"] == "/messages/0/content" and s["kind"] == "unannotated_text"
    ][0]
    assert body["source"] is None
    result = p.estimate_fragment_tokens(built, len, tokenizer_id="CPU-character-fixture")
    assert result["unattributed_fragment_tokens_estimate"] >= len("unknown")
    assert not result["provider_exact_mapping_available"]


def test_wire_configuration_cannot_inflate_semantic_coverage():
    base = {"messages": [{"content": "unknown"}]}
    bloated = {**base, "model": "template-" * 10000, "max_tokens": 99999, "temperature": 0.2}
    a = p.build_request(base, identity(), template_source=source("Base/Template"))
    b = p.build_request(bloated, identity("r2", "a2"), template_source=source("Base/Template"))
    ea = p.estimate_fragment_tokens(a, len, tokenizer_id="CPU")
    eb = p.estimate_fragment_tokens(b, len, tokenizer_id="CPU")
    assert ea["estimated_by_primary_category"] == eb["estimated_by_primary_category"]
    assert (
        ea["payload_local_estimated_token_coverage"] == eb["payload_local_estimated_token_coverage"]
    )
    assert b.manifest["semantic_payload_bytes"] == a.manifest["semantic_payload_bytes"]


def test_retry_identity_independent_capture_and_payload_equal(tmp_path):
    first, second = request(), request("request-2", "attempt-2")
    assert first.payload_bytes == second.payload_bytes
    a = p.persist_request(tmp_path, first)
    b = p.persist_request(tmp_path, second)
    assert a["payload"]["path"] != b["payload"]["path"]
    assert p.load_persisted_request(a) == first
    with pytest.raises(FileExistsError):
        p.persist_request(tmp_path, first)


@pytest.mark.parametrize("mutation", ["payload", "overlap", "uncovered", "hash"])
def test_original_and_offsets_tamper_rejected(mutation):
    built = request()
    manifest = copy.deepcopy(built.manifest)
    raw = built.payload_bytes
    if mutation == "payload":
        raw += b" "
    elif mutation == "overlap":
        manifest["spans"][1]["payload_start"] = 0
    elif mutation == "uncovered":
        manifest["spans"].pop()
    else:
        manifest["spans"][0]["payload_slice_sha256"] = "0" * 64
    with pytest.raises(ValueError):
        p.verify_request(p.BuiltRequest(raw, manifest))


def test_peer_and_self_owner_and_artifact_version_constraints():
    with pytest.raises(ValueError):
        p.SourceFragment("other", "s", "e", "member_001")
    with pytest.raises(ValueError):
        p.SourceFragment("Artifact", "s", "e", "member_002")
    wrong = p.SourceFragment("Self-history", "s", "e", "member_002")
    with pytest.raises(ValueError):
        p.build_request({"messages": [p.AnnotatedText((p.TextSegment("x", wrong),))]}, identity())


def test_local_token_mapping_does_not_become_exact_when_count_matches_usage():
    built = request()
    tokens, evidence = mapping(built)
    measured = p.attribute_input_tokens(
        built, response(built, len(tokens), cache=0), tokens, evidence
    )
    assert measured["payload_local_estimated_token_coverage"] == 1
    assert measured["provider_unmatched_token_difference"] == 0
    assert (
        measured["provider_exact_source_coverage"] is None
        and not measured["provider_exact_mapping_available"]
    )
    assert set(measured["local_by_primary_category"]) == set(p.PRIMARY_CATEGORIES)
    assert sum(measured["local_by_primary_category"].values()) == len(tokens)


def test_cross_category_token_and_hidden_wrapper_unattributed_no_proration():
    built = p.build_request(
        {
            "messages": [
                p.AnnotatedText(
                    (p.TextSegment("a", source("Task")), p.TextSegment("b", source("Peer-message")))
                )
            ]
        },
        identity(),
    )
    parts = [s for s in built.manifest["spans"] if s["kind"] == "text_fragment"]
    tokens = [
        {
            "index": 0,
            "token_id": 17,
            "payload_ranges": [[parts[0]["payload_start"], parts[1]["payload_end"]]],
        },
        {"index": 1, "token_id": 18, "payload_ranges": []},
    ]
    evidence = {
        "domain": "rendered_chat_local",
        "payload_sha256": built.manifest["payload_sha256"],
        "token_ids_sha256": p.digest(p.canonical([17, 18]).encode()),
    }
    m = p.attribute_input_tokens(built, response(built, 100, cache=0), tokens, evidence)
    assert m["local_unattributed_tokens"] == 2 and sum(m["local_by_primary_category"].values()) == 0
    assert m["provider_unmatched_token_difference"] == 98 and m["no_proportional_usage_allocation"]


def test_wire_parameter_token_is_excluded_from_semantic_input_denominator():
    built = request()
    wire = next(
        s
        for s in built.manifest["spans"]
        if s["json_pointer"] == "/max_tokens" and s["kind"] == "json_scalar"
    )
    tokens = [
        {
            "index": 0,
            "token_id": 1,
            "payload_ranges": [[wire["payload_start"], wire["payload_end"]]],
        }
    ]
    evidence = {
        "domain": "canonical_payload_local",
        "payload_sha256": built.manifest["payload_sha256"],
        "token_ids_sha256": p.digest(b"[1]"),
    }
    m = p.attribute_input_tokens(built, response(built), tokens, evidence)
    assert m["local_token_count"] == 0 and m["excluded_transport_configuration_tokens"] == 1
    assert m["payload_local_estimated_token_coverage"] is None


def test_cache_subset_and_authoritative_team_total_with_retries():
    a, b = request(), request("r2", "a2")
    ra, rb = response(a, 100, 3, 20), response(b, 80, 4, 10)
    entries = [
        {
            "request_id": r["request_id"],
            "status": "settled",
            "usage": {
                "prompt_tokens": r["usage"]["input_tokens"],
                "completion_tokens": r["usage"]["output_tokens"],
                "prompt_cache_hit_tokens": r["usage"]["cached_input_tokens"],
                "prompt_cache_miss_tokens": r["usage"]["cache_miss_input_tokens"],
            },
        }
        for r in [ra, rb]
    ]
    result = p.reconcile_ledgers([ra, rb, ra], entries)
    assert result["passed"] and result["physical_request_count"] == 2
    assert result["known_actual_total_tokens"] == 187 and result["cached_input_tokens_known"] == 30
    assert not result["analysis_subledgers_added_to_team_total"]
    entries[1]["usage"]["prompt_tokens"] += 1
    entries[1]["usage"]["prompt_cache_miss_tokens"] += 1
    assert not p.reconcile_ledgers([ra, rb], entries)["passed"]


def test_usage_unknown_is_retained_not_zero_completed():
    built = request()
    resp = p.capture_response(built, None, outcome="transport_unknown", error={"kind": "timeout"})
    result = p.reconcile_ledgers(
        [resp], [{"request_id": "request-1", "status": "uncertain", "usage": None}]
    )
    assert result["passed"] and not result["usage_complete"]
    assert result["uncertain_request_ids"] == ["request-1"]
    assert (
        resp["provider_model"]["status"] == resp["provider_fingerprint"]["status"] == "unavailable"
    )


def test_malformed_cache_and_conflicting_duplicate_rejected():
    built = request()
    with pytest.raises(ValueError):
        response(built, 10, 3, 20)
    first = response(built)
    second = copy.deepcopy(first)
    second["usage"]["input_tokens"] += 1
    result = p.reconcile_ledgers([first, second], [])
    assert not result["passed"] and any(
        x["kind"] == "conflicting_duplicate_request" for x in result["issues"]
    )


def test_g0_separates_payload_local_pass_from_unavailable_provider_gate(tmp_path):
    built = request()
    tokens, evidence = mapping(built)
    resp = response(built, len(tokens), cache=0)
    attr = p.attribute_input_tokens(built, resp, tokens, evidence)
    capture = p.persist_request(tmp_path, built)
    ledger = p.reconcile_ledgers(
        [resp],
        [
            {
                "request_id": resp["request_id"],
                "status": "settled",
                "usage": {
                    "prompt_tokens": len(tokens),
                    "completion_tokens": 3,
                    "prompt_cache_hit_tokens": 0,
                    "prompt_cache_miss_tokens": len(tokens),
                },
            }
        ],
    )
    gate = p.evaluate_g0(
        [{"request": built, "response": resp, "capture": capture}],
        [attr],
        ledger,
        other_gates={"G0-4": True, "G0-5": True, "G0-6": True},
    )
    assert gate["gates"]["G0-1"] and gate["gates"]["G0-2-payload-local-estimate"]
    assert not gate["gates"]["G0-2-provider-exact"] and not gate["p1_ready"]
    assert gate["provider_exact_unattributed_fraction"] is None
    deduplicated = p.evaluate_g0(
        [{"request": built, "response": resp, "capture": capture}] * 2,
        [attr, attr],
        ledger,
    )
    assert deduplicated["gates"]["G0-8"] and deduplicated["gates"]["G0-2-payload-local-estimate"]
    assert deduplicated["duplicate_observations_not_recounted"] == [resp["request_id"]]
    missing_response_id = copy.deepcopy(resp)
    missing_response_id["response_id"] = {
        "status": "unavailable",
        "value": None,
        "reason": "not_returned",
    }
    assert not p.evaluate_g0(
        [{"request": built, "response": missing_response_id, "capture": capture}], [attr], ledger
    )["gates"]["G0-1"]


def test_exact_evidence_must_bind_request_response_and_verified_method():
    built = request()
    tokens, evidence = mapping(built, domain="provider_prompt_exact")
    resp = response(built, len(tokens), cache=0)
    evidence.update(tokenizer_and_rendering_verified=True, hidden_wrapper_accounted=True)
    proof = {
        "request_id": resp["request_id"],
        "response_id": resp["response_id"]["value"],
        "payload_sha256": built.manifest["payload_sha256"],
        "token_ids_sha256": evidence["token_ids_sha256"],
        "response_object_sha256": resp["response_canonical_object_sha256"],
        "provider_model": resp["provider_model"]["value"],
        "method": "official_recipe_compatibility",
        "validation_status": "estimated",
        "provider_wrapper_included": True,
        "renderer_sha256": "a" * 64,
        "tokenizer_sha256": "b" * 64,
        "validation_record_sha256": "c" * 64,
        "official_recipe_reference": "cpu-control:synthetic-proof-not-real-provider",
    }
    evidence["compatibility_evidence"] = proof
    assert not p.attribute_input_tokens(built, resp, tokens, evidence)[
        "provider_exact_mapping_available"
    ]
    proof["validation_status"] = "exact_verified"
    # A synthetic branch test only; this fixture is not a provider compatibility result.
    assert p.attribute_input_tokens(built, resp, tokens, evidence)[
        "provider_exact_mapping_available"
    ]
    proof["request_id"] = "a-different-request"
    assert not p.attribute_input_tokens(built, resp, tokens, evidence)[
        "provider_exact_mapping_available"
    ]
    proof["request_id"] = resp["request_id"]
    proof["method"] = "provider_returned_input_ids"
    assert not p.attribute_input_tokens(built, resp, tokens, evidence)[
        "provider_exact_mapping_available"
    ]


def test_shared_attempt_id_across_distinct_requests_fails_idempotence_gate(tmp_path):
    a, b = request(), request("request-2", "attempt-1")
    records = [
        {"request": x, "response": response(x), "capture": p.persist_request(tmp_path, x)}
        for x in [a, b]
    ]
    gate = p.evaluate_g0(records, [], {"passed": True, "request_ids": ["request-1", "request-2"]})
    assert not gate["gates"]["G0-8"]
    assert gate["request_or_attempt_identity_conflicts"] == ["request-2"]
