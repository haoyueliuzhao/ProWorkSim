"""CPU-only controls for source-bound, non-authoritative team observations."""
import hashlib
import json

import pytest

from proworksim.software_collaboration_observation_v141 import ObservationError, ObservationLog


M1, M2, M3 = "member_001", "member_002", "member_003"


def evidence(name):
    return {"trusted_runtime_event": name}


def version(member, number):
    return {"object_id": "private-" + member, "version_id": "v" + str(number),
            "files_sha256": hashlib.sha256((member+str(number)).encode()).hexdigest()}


def read(obs, name, member, text, start, end, *, version_number=1, path="module.py"):
    obs.record_information_read(name, member, source_reference=version(member, version_number),
        path=path, full_text_sha256=hashlib.sha256(text.encode()).hexdigest(), start=start,
        end=end, total=len(text), text=text[start:end], authorized=True, evidence=evidence(name))


def usage(prompt=100, output=10):
    return {"prompt_tokens": prompt, "completion_tokens": output, "total_tokens": prompt+output,
            "prompt_cache_hit_tokens": prompt//2, "prompt_cache_miss_tokens": prompt-prompt//2}


def chain(obs):
    obs.record("publish", "artifact_published", M2, patch_id="patch-1",
        source_reference=version(M2, 3), content_identity={"files_sha256": "abc", "tasks": {"t": 1}},
        evidence=evidence("publish"))
    obs.record("opportunity", "artifact_opportunity", M1, publication="publish", eligible=True,
        evidence=evidence("allowed"))
    obs.record("adopt", "artifact_acquired", M1, opportunity="opportunity",
        adopted_reference=version(M1, 2), evidence=evidence("explicit integrate tool receipt"))
    obs.record("test", "artifact_validated", M1, acquisition="adopt", tested_reference=version(M1, 2),
        executed=True, passed=True, evidence=evidence("real public test receipt"))
    obs.record("review", "artifact_review", M1, validation="test", decision="accept",
        evidence=evidence("review"))
    obs.record("integrate", "artifact_integrated", M1, publication="publish", result_reference=version(M1, 2),
        explicit_agent_action=True, evidence=evidence("integrate"))


def test_actual_provider_usage_counts_once_and_never_grants_budget(tmp_path):
    with ObservationLog(tmp_path, "team", [M1, M2]) as obs:
        receipt = evidence("provider-request-1")
        args = ("u1", M1, "r1", "agent", "settled", usage())
        obs.record_usage(*args, cost_cny="0.012", receipt=receipt)
        assert obs.record_usage(*args, cost_cny="0.012", receipt=receipt)["duplicate"] is True
        obs.record_usage("u1-alias", M1, "r1", "agent", "settled", usage(), cost_cny="0.012", receipt=receipt)
        obs.record_usage("u2", M2, "r2", "condenser", "settled", usage(40, 5),
                         cost_cny="0.003", receipt=evidence("provider-request-2"))
        obs.record_action("a1", M1, "send_message", "r1", False, evidence=evidence("business rejection"))
        obs.record_coverage("coverage-u", "usage", True, evidence=evidence("broker finalized"))
        value = obs.summary()
        assert value["usage"]["unique_requests"] == 2
        assert value["usage"]["actual_total_tokens"] == 155
        assert value["usage"]["cache_hit_tokens"] == 70
        assert value["usage"]["cache_miss_tokens"] == 70
        assert value["usage"]["total_cost_CNY"] == "0.015"
        assert value["usage"]["by_member"][M2]["total_tokens"] == 45
        assert value["actions"]["whole_request_attribution"]["send_message"]["whole_request_tokens"] == 110
        assert value["actions"]["attribution_is_net_tool_cost"] is False
        assert value["changes_to_model_budget"] == 0
        with pytest.raises(ObservationError, match="two actions"):
            obs.record_action("second-action", M1, "read_file", "r1", True, evidence=evidence("a2"))
        with pytest.raises(ObservationError, match="cross member"):
            obs.record_usage("wrong-member", M2, "r1", "agent", "settled", usage(), receipt=receipt)


def test_uncertain_usage_and_missing_cost_are_not_zero(tmp_path):
    with ObservationLog(tmp_path, "team", [M1]) as obs:
        obs.record_usage("unknown", M1, "r1", "agent", "uncertain", None, receipt=evidence("unknown"))
        obs.record_coverage("coverage-u", "usage", True, evidence=evidence("broker stopped"))
        assert obs.summary()["usage"]["actual_total_tokens"] is None
        obs.record_usage("settled", M1, "r1", "agent", "settled", usage(), receipt=evidence("later receipt"))
        assert obs.summary()["usage"]["actual_total_tokens"] == 110
        assert obs.summary()["usage"]["total_cost_CNY"] is None
        with pytest.raises(ObservationError, match="settled accounting"):
            obs.record_usage("changed", M1, "r1", "agent", "settled", usage(200), receipt=evidence("changed"))
        with pytest.raises(ObservationError, match="unknown"):
            obs.record_usage("fake-zero", M1, "r2", "agent", "uncertain", usage(0, 0), receipt=evidence("x"))


def test_send_receipt_and_actual_model_exposure_are_separate(tmp_path):
    with ObservationLog(tmp_path, "team", [M1, M2, M3]) as obs:
        obs.record_message_sent("m", M1, [M2], "Inspect patch-1 at v3", evidence=evidence("sent"))
        initial = obs.summary()["messages"]
        assert initial["sent"] == 1 and initial["obtained_receipts"] == 0
        assert initial["actual_model_presentations"] is None
        assert initial["direct_content_tokens"] is None
        with pytest.raises(ObservationError, match="receipt"):
            obs.record_message_received("queued", M2, "m", actually_obtained=False, evidence=evidence("queue"))
        with pytest.raises(ObservationError, match="receipt"):
            obs.record_message_received("foreign", M3, "m", actually_obtained=True, evidence=evidence("wrong target"))
        obs.record_message_received("obtained", M2, "m", actually_obtained=True, evidence=evidence("visible receipt"))
        assert obs.summary()["messages"]["observed_model_presentations"] == 0
        obs.record_information_presented("input-1", M2, "r1", ["obtained"],
            actual_input={"sha256": "input-packet-1"}, evidence=evidence("actual submitted API input"))
        obs.record_coverage("coverage-input", "presentations", True, evidence=evidence("input hook complete"))
        assert obs.summary()["messages"]["actual_model_presentations"] == 1
        with pytest.raises(ObservationError, match="private acquisition"):
            obs.record_information_presented("illegal", M3, "r2", ["obtained"],
                actual_input=evidence("input"), evidence=evidence("not authorized"))
        with pytest.raises(PermissionError, match="evaluation-only"):
            obs.solver_view(M1)


def test_content_counter_is_identified_and_not_added_to_billed_usage(tmp_path):
    with ObservationLog(tmp_path, "team", [M1, M2], token_counter=len,
                        tokenizer_id="test-fixture-character-counter-not-provider") as obs:
        obs.record_message_sent("m1", M1, [M2], "abc", evidence=evidence("sent1"))
        obs.record_message_sent("m2", M1, [M2], "abc", evidence=evidence("sent2"))
        obs.record_coverage("messages", "messages", True, evidence=evidence("complete"))
        value = obs.summary()
        assert value["messages"]["direct_content_tokens"] == 6
        assert len(list((tmp_path / "content").iterdir())) == 1
        assert value["usage"]["known_actual_tokens"]["total_tokens"] == 0
        assert value["usage"]["actual_total_tokens"] is None
        assert value["messages"]["net_communication_token_cost"] is None


def test_duplicate_ranges_distinguish_reread_and_cross_member_acquisition(tmp_path):
    text = "abcdefghij"
    with ObservationLog(tmp_path, "team", [M1, M2]) as obs:
        read(obs, "a", M1, text, 0, 6)
        read(obs, "b", M1, text, 3, 8)
        read(obs, "c", M2, text, 4, 10)
        # Changed content has a different source identity even at the same path.
        read(obs, "d", M2, "ABCDEFGHIJ", 0, 10, version_number=2)
        obs.record_coverage("coverage-reads", "reads", True, evidence=evidence("complete read hook"))
        value = obs.summary()["information"]
        assert value["returned_read_characters"] == 27
        assert value["same_member_reread_characters"] == 3
        assert value["cross_member_first_acquisition_overlap_characters"] == 4
        assert value["source_bound_overlap_ratio"] == pytest.approx(7/27)
        assert value["waste_or_semantic_duplication_ratio"] is None
        assert value["actual_model_presentations"] is None
        obs.record_information_presented("input1", M2, "r1", ["c", "d"],
            actual_input=evidence("actual packet1"), evidence=evidence("dispatch1"))
        obs.record_information_presented("input2", M2, "r2", ["c"],
            actual_input=evidence("actual packet2"), evidence=evidence("dispatch2"))
        assert obs.summary()["information"]["observed_model_presentations"] == 3
        assert obs.summary()["information"]["read_events_presented_to_model"] == 2
        with pytest.raises(ObservationError, match="only be presented once"):
            obs.record_information_presented("input1again", M2, "r1", ["c"],
                actual_input=evidence("actual packet1"), evidence=evidence("dispatch1"))


def test_denied_read_and_wrong_range_do_not_establish_acquisition(tmp_path):
    with ObservationLog(tmp_path, "team", [M1, M2]) as obs:
        with pytest.raises(ObservationError, match="Denied reads"):
            obs.record_information_read("bad", M2, source_reference=version(M1, 1), path="secret.py",
                full_text_sha256="a"*64, start=0, end=3, total=3, text="abc",
                authorized=False, evidence=evidence("denied"))
        with pytest.raises(ObservationError, match="exact source range"):
            obs.record_information_read("wrong", M2, source_reference=version(M2, 1), path="module.py",
                full_text_sha256="a"*64, start=0, end=3, total=3, text="ab",
                authorized=True, evidence=evidence("wrong range"))
        assert obs.summary()["information"]["returned_read_characters"] == 0


def test_partner_use_requires_actual_adoption_validation_and_delivery_lineage(tmp_path):
    with ObservationLog(tmp_path, "team", [M1, M2]) as obs:
        chain(obs)
        obs.record_coverage("artifacts-complete", "artifacts", True, evidence=evidence("all artifact events"))
        before = obs.summary()["artifacts"]
        assert before["obtained"] == 1 and before["same_version_public_test_passed"] == 1
        assert before["R_use"] == 0
        obs.record("edit", "version_transition", M1, from_reference=version(M1, 2),
            to_reference=version(M1, 3), evidence=evidence("explicit later edit preserving provenance"))
        obs.record("lock", "candidate_locked", M1, reference=version(M1, 3), generation_closed=True,
            evidence=evidence("only final candidate"))
        delivery = dict(candidate_lock="lock", legal=True, submitted_reference=version(M1, 3),
            artifact_chain=[{"integration": "integrate", "validation": "test", "transitions": ["edit"]}],
            evidence=evidence("last legal delivery chain"))
        obs.record("delivery", "final_delivery", M1, **delivery)
        result = obs.summary()["artifacts"]
        assert result["known_eligible_partner_artifacts"] == 1
        assert result["entered_legal_delivery_chain"] == 1 and result["R_use"] == 1
        assert result["semantic_or_causal_contribution_proven"] is False
        with pytest.raises(ObservationError, match="last legal delivery"):
            obs.record("old-delivery-union", "final_delivery", M1, **delivery)


def test_stale_test_or_missing_lineage_cannot_prove_partner_use(tmp_path):
    with ObservationLog(tmp_path, "team", [M1, M2]) as obs:
        chain(obs)
        with pytest.raises(ObservationError, match="same-version"):
            obs.record("stale", "artifact_validated", M1, acquisition="adopt",
                tested_reference=version(M1, 1), executed=True, passed=True, evidence=evidence("old test"))
        obs.record("lock", "candidate_locked", M1, reference=version(M1, 3), generation_closed=True,
            evidence=evidence("lock"))
        with pytest.raises(ObservationError, match="does not reach"):
            obs.record("delivery", "final_delivery", M1, candidate_lock="lock", legal=True,
                submitted_reference=version(M1, 3), artifact_chain=[{"integration": "integrate", "validation": "test"}],
                evidence=evidence("missing transition"))
        assert obs.summary()["artifacts"]["entered_legal_delivery_chain"] == 0


def test_unknown_opportunity_and_empty_single_agent_denominator_stay_unknown(tmp_path):
    with ObservationLog(tmp_path / "two", "team2", [M1, M2]) as obs:
        obs.record("publish", "artifact_published", M2, patch_id="patch-1", source_reference=version(M2, 2),
            content_identity={"hash": "h"}, evidence=evidence("publish"))
        obs.record_coverage("artifacts", "artifacts", True, evidence=evidence("missing opportunity is still missing"))
        result = obs.summary()["artifacts"]
        assert result["opportunity_unknown_artifacts"] == 1
        assert result["R_use"] is None and not result["R_use_denominator_complete"]
        with pytest.raises(ObservationError, match="legal partner-artifact opportunity"):
            obs.record("auto", "artifact_integrated", M1, publication="publish",
                result_reference=version(M1, 2), explicit_agent_action=True, evidence=evidence("no visibility proof"))
    with ObservationLog(tmp_path / "one", "team1", [M1]) as obs:
        obs.record_coverage("artifacts", "artifacts", True, evidence=evidence("S1 has no peer"))
        assert obs.summary()["artifacts"]["R_use"] is None
        assert obs.summary()["artifacts"]["known_eligible_partner_artifacts"] == 0


def test_restart_replays_exact_log_without_doubling_usage_or_receipts(tmp_path):
    with ObservationLog(tmp_path, "team", [M1, M2]) as obs:
        read(obs, "read", M1, "abcdef", 0, 6)
        obs.record_message_sent("message", M1, [M2], "Please inspect patch", evidence=evidence("sent"))
        obs.record_usage("usage", M1, "r1", "agent", "settled", usage(), receipt=evidence("provider"))
        before = obs.summary()
        with pytest.raises(ObservationError, match="already has a writer"):
            ObservationLog(tmp_path, "team", [M1, M2])
    with ObservationLog(tmp_path, "team", [M1, M2]) as obs:
        assert obs.summary() == before
        with pytest.raises(ObservationError, match="cannot change its meaning"):
            obs.record_message_sent("message", M1, [M2], "Changed message", evidence=evidence("sent"))
    with pytest.raises(ObservationError, match="identity"):
        ObservationLog(tmp_path, "another-team", [M1, M2])


def test_tampered_or_partial_records_are_not_silently_repaired(tmp_path):
    with ObservationLog(tmp_path, "team", [M1]) as obs:
        obs.record("role", "role_state", M1, state_id="role1", state={"role": "self organized"}, evidence=evidence("declaration"))
    with (tmp_path / "events.jsonl").open("ab") as stream:
        stream.write(b'{"partial":')
    with pytest.raises(ObservationError, match="Incomplete"):
        ObservationLog(tmp_path, "team", [M1])


def test_mutating_input_does_not_change_recorded_role_and_whole_state_is_rejected(tmp_path):
    with ObservationLog(tmp_path, "team", [M1]) as obs:
        role = {"role": "developer", "source": "member declaration", "reason": "available task"}
        obs.record("role", "role_state", M1, state_id="r1", state=role, evidence=evidence("declaration"))
        role["role"] = "mutated"
        saved = json.loads((tmp_path / "events.jsonl").read_text().splitlines()[1])
        assert saved["data"]["state"]["role"] == "developer"
        with pytest.raises(ObservationError, match="full history/state"):
            obs.record("bad", "task_state", M1, state_id="task", state={"whole_tree": "x"*10000}, evidence=evidence("bad"))
        assert obs.summary()["role_state_events"] == 1


def test_unsettled_presented_request_keeps_usage_unknown_and_foreign_group_is_rejected(tmp_path):
    with ObservationLog(tmp_path, "team", [M1, M2]) as obs:
        read(obs, "read", M1, "text", 0, 4)
        obs.record_information_presented("input", M1, "r1", ["read"], actual_input=evidence("packet"), evidence=evidence("sent"))
        obs.record_coverage("coverage", "presentations", True, evidence=evidence("all presentations"))
        assert obs.summary()["information"]["actual_model_presentations"] == 1
        assert obs.summary()["usage"]["actual_total_tokens"] is None
        obs.record_coverage("usage-coverage", "usage", True, evidence=evidence("reported complete but receipt missing"))
        assert obs.summary()["usage"]["actual_total_tokens"] is None
        assert obs.summary()["usage"]["requests_without_usage"] == 1
        with pytest.raises(ObservationError, match="Foreign member"):
            obs.record_action("foreign", "member_999", "read_file", "r2", True, evidence=evidence("foreign"))


def test_failed_validation_cannot_be_upgraded_by_review(tmp_path):
    with ObservationLog(tmp_path, "team", [M1, M2]) as obs:
        chain(obs)
        obs.record("failed", "artifact_validated", M1, acquisition="adopt", tested_reference=version(M1, 2),
            executed=True, passed=False, evidence=evidence("actual failure"))
        with pytest.raises(ObservationError, match="Acceptance cannot"):
            obs.record("bad-accept", "artifact_review", M1, validation="failed", decision="accept", evidence=evidence("bad"))
        obs.record("return", "artifact_review", M1, validation="failed", decision="request_changes", evidence=evidence("rework"))


def test_expired_opportunity_blocks_late_adoption_but_does_not_erase_denominator(tmp_path):
    with ObservationLog(tmp_path, "team", [M1, M2]) as obs:
        obs.record("publish", "artifact_published", M2, patch_id="patch-1", source_reference=version(M2, 2),
            content_identity={"hash": "h"}, evidence=evidence("publish"))
        obs.record("eligible", "artifact_opportunity", M1, publication="publish", eligible=True,
            evidence=evidence("legal opportunity at time1"))
        obs.record("expired", "artifact_opportunity", M1, publication="publish", eligible=False,
            evidence=evidence("task revision changed at time2"))
        with pytest.raises(ObservationError, match="legal opportunity"):
            obs.record("late", "artifact_acquired", M1, opportunity="eligible",
                adopted_reference=version(M1, 2), evidence=evidence("stale adoption"))
        obs.record_coverage("complete", "artifacts", True, evidence=evidence("complete"))
        result = obs.summary()["artifacts"]
        assert result["known_eligible_partner_artifacts"] == 1
        assert result["R_use"] == 0
def test_runtime_explicit_message_reread_only_presented_on_later_actual_input(tmp_path):
    import json
    from types import SimpleNamespace
    from proworksim.software_collaboration_runtime_observer_v141 import RuntimeObservationBridge
    bridge = RuntimeObservationBridge(tmp_path, team_id='cpu-read', members=['member_001', 'member_002'])
    source = {'object_id': 'source-002', 'version_id': 'v1'}
    bridge.runtime = SimpleNamespace(prepared=SimpleNamespace(world=SimpleNamespace(
        org_current_identity=lambda _: {'source_reference': source})))
    bridge.log.record_message_sent('sent', 'member_001', ['member_002'], 'Please inspect', evidence={'event': 1})
    bridge.messages[1] = {'event': 'sent', 'recipient': 'member_002', 'body': 'Please inspect'}
    response = {'ok': True, 'result': {'kind': 'work_message', 'sequence': 1, 'body': 'Please inspect'}}
    bridge.executed('member_002', 'read_work_event', {'sequence': 1},
                    {'model_tool_call_id': 'read-call', 'model_call_id': 'model'}, response, source)
    assert bridge.log.summary()['messages']['observed_model_presentations'] == 0
    wire = {'messages': [{'role': 'tool', 'tool_call_id': 'read-call', 'content': json.dumps(response)}]}
    bridge.provider_returned('member_002', {'request_id': 'real-next', 'wire': wire, 'usage_id': 'agent'},
        {'usage': {'prompt_tokens': 2, 'completion_tokens': 1}, 'choices': []})
    assert bridge.log.summary()['messages']['observed_model_presentations'] == 1
    assert bridge.log.summary()['usage']['known_actual_tokens']['total_tokens'] == 3
    bridge.log.close()


def test_runtime_observation_error_log_failure_does_not_fail_provider_path(tmp_path, monkeypatch):
    from proworksim import software_collaboration_runtime_observer_v141 as bridge_module
    bridge = bridge_module.RuntimeObservationBridge(tmp_path, team_id='cpu-fault', members=['member_001'])
    def broken(*_args):
        raise OSError('synthetic observer-only storage failure')
    monkeypatch.setattr(bridge_module, 'atomic_write', broken)
    assert bridge.safely('provider', broken) is None
    assert len(bridge.errors) == 1 and 'observer_error_log_unwritable' in bridge.partial
    assert bridge.log.summary()['changes_to_model_budget'] == 0
    bridge.log.close()

