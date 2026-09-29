"""One formal 16-slot CPU collection; no 9B, no composition optimization run."""

import copy
import json

import pytest

from proworksim.collaboration_training_v025 import diagnose_support, records_from_entries
from proworksim.composition_training_v025 import materialize_composition, validate_composition
from proworksim.deterministic_work_v024 import DeterministicCandidateActor
from proworksim.online_training import SharedActor, prepare_window, tensor_tree_digest
from proworksim.storage import digest, json_bytes, read_json
from proworksim.work_composition_diagnostics_v025 import summarize_work_signals
from proworksim.templates import retail_collaboration_v025 as world
from scripts.composition_pilot_v025 import support_collection, train_branch
from scripts.credit_pilot_v024 import publish_checkpoint
from scripts.evaluate_work_v022 import checked, reference
from test_collaboration_training_v022 import ExplicitSyntheticTokenTransport
from test_online_training_v13 import _features, _owner, _sample_entry


def test_formal_support_original_state_branch_binding_and_known_no_generation(tmp_path):
    torch = pytest.importorskip("torch")
    if not (world.DEFAULT_ASSETS / "manifest.json").exists():
        pytest.skip("Pinned v025 source materials required; no substitute source")
    catalog = world.registry()
    contract = catalog["training_window"]
    prototype = _owner(
        tmp_path,
        torch,
        "tiny-prototype",
        base_identity={"manifest": {"sha256": digest(b"CPU integration fixture")}},
    )
    native = object.__new__(DeterministicCandidateActor)

    class Owner(SharedActor):
        fixture_collection = False

        def reseed(self, seed, *, label):
            super().reseed(seed, label=label)
            slot = next(s for s in contract["slots"] if s["slot_id"] == label)
            self.task, self.counters, self.current_slot = slot["task"], {}, label

        def complete(self, request, *, timeout_seconds):
            if not self.fixture_collection:
                return super().complete(request, timeout_seconds=timeout_seconds)
            names = {t["function"]["name"] for t in request["tools"]}
            member = (
                "implementer"
                if "write_object" in names
                else "reviewer"
                if "raise_issue" in names
                else "provider"
            )
            if self.current_slot == contract["slots"][0]["slot_id"] and member == "provider":
                body = {
                    "error": {
                        "code": "context_length_exceeded",
                        "prompt_tokens": 16384,
                        "requested_output": 2048,
                        "context_limit": 16384,
                    },
                    "transport_kind": "resident_direct",
                    "generation_started": False,
                    "actor_identity": self.freeze_identity(),
                    "online_window_id": self.window_id,
                    "fixture_provenance": "Explicit CPU pre-generation context-stop control",
                }
                return {
                    "http_status": 400,
                    "body": body,
                    "raw_body": json_bytes(body).decode(),
                    "response_headers": {},
                }
            result = ExplicitSyntheticTokenTransport.complete(
                self, request, timeout_seconds=timeout_seconds
            )
            body = result["body"]
            message = body["choices"][0]["message"]
            raw = message["content"]
            if message.get("tool_calls"):
                call = message["tool_calls"][0]["function"]
                params = "".join(
                    "<parameter="
                    + key
                    + ">\n"
                    + (value if isinstance(value, str) else json.dumps(value))
                    + "\n</parameter>\n"
                    for key, value in json.loads(call["arguments"]).items()
                )
                raw += (
                    "\n<tool_call><function="
                    + call["name"]
                    + ">\n"
                    + params
                    + "</function></tool_call>"
                )
            parsed, error = native.parse_response(raw, request)
            assert error is None
            body["choices"][0]["message"] = parsed
            body["native_cpu_fixture_raw"] = raw
            body["fixture_provenance"] += "; actual native XML parser"
            result["raw_body"] = json_bytes(body).decode()
            self.responses[-1]["body"] = copy.deepcopy(body)
            self.parsed_calls += 1
            return result

    def owner(name):
        result = Owner(
            type(prototype.model)(),
            prototype.tokenizer,
            output=tmp_path / name,
            device="cpu",
            torch_module=torch,
            base_identity=prototype.base_identity,
            inference_profile=prototype.inference_profile,
            recipe={"max_length": 16384, "max_output_tokens": 2048, "post_update_max_decisions": 6},
        )
        result.requests, result.responses, result.counters, result.task = [], [], {}, None
        result.current_slot, result.parsed_calls = None, 0
        return result

    warm = owner("warm")
    for i in range(2):
        warm.begin_window(f"explicit-CPU-warm-{i}")
        warm.update_window(
            [_sample_entry(warm, reward=1.0)],
            tmp_path / f"warm-update-{i}",
            feature_function=_features,
        )
    run_root = tmp_path / "run"
    prior = publish_checkpoint(warm, tmp_path / "prior-checkpoint", run_root, "mc")
    original_digest = prior["state_tensor_digest"]
    plan = {
        "prior_endpoint": reference(run_root / "checkpoints/mc.json"),
        "source_pin": reference(world.PIN_PATH),
        "assets_root": str(world.DEFAULT_ASSETS),
        "composition": {"epsilon": 0.1},
    }
    collector = owner("collector")
    collector.fixture_collection = True
    output = tmp_path / "support"
    output.mkdir()
    result = support_collection(collector, plan, catalog, output, run_root)
    assert result["status"] == "complete" and result["actual_new_episodes"] == 16
    assert result["collection_state_guard"]["learning_unchanged"]
    assert result["collection_state_guard"]["rng_restored_exactly"]
    marker = read_json(run_root / "support-complete.json")
    assert (
        marker["origin_precedes_collection"]
        and marker["origin_checkpoint"]["state_tensor_digest"] == original_digest
    )
    entries = read_json(checked(marker["entries"]))
    declaration = read_json(checked(marker["declaration"]))
    support = read_json(checked(marker["support"]))
    assert len(entries) == len(declaration["slots"]) == support["raw_slot_count"] == 16
    assert collector.parsed_calls > 0
    assert support["selected_block"] is None  # No fake route completion is invented.
    direct = diagnose_support(entries, declaration)
    assert direct["supports_by_xi"] == support["supports_by_xi"]
    assert all(b["M"] == 8 for s in direct["supports_by_xi"].values() for b in s["blocks"].values())
    first = entries[0]["slot_id"]
    projection = read_json(output / "collection" / first / "projection.json")
    assert projection["token_projection_members"]["provider"]["status"] == "known_no_generation"
    assert projection["has_complete_trainable_actual_members"]
    unit = materialize_composition(entries, declaration, records_from_entries(entries))
    assert unit["Q_equals_B"]
    raw = json_bytes(entries)
    observed = {}

    class StopBeforeOptimizer(Exception):
        pass

    branch = owner("base-branch")

    def inspect_update(actual_entries, update_output, *, composition, post_update_selector):
        # Exercise the real runner's origin/marker/q selection before any
        # optimizer. Native collection tokens above are explicitly synthetic.
        assert branch.actor_steps == branch.critic_steps == 2
        assert branch.window_id == declaration["window_id"] and branch.phase == "collecting"
        state = branch._state_bundle()
        state["last_window_id"] = warm.window_id
        state["used_window_ids"] = warm.used_window_ids
        assert tensor_tree_digest(state, torch) == original_digest
        assert json_bytes(actual_entries) == raw and composition == unit
        prepared = prepare_window(
            actual_entries, branch.freeze_identity(), branch.window_id, branch.recipe
        )
        weights, proof = validate_composition(actual_entries, prepared, composition)
        assert prepared["slot_count"] == 16 and all(w == 1 for w in weights)
        assert proof["original_normalization_preserved"]
        assert prepared["slots"][0]["members"]["provider"]["exclusions"] == [
            "no_own_sampled_actions"
        ]
        assert not any(
            r["slot_id"] == first and r["member_id"] == "provider" for r in prepared["decisions"]
        )
        for row in prepared["decisions"]:
            assert row["actor_denominator"] >= 16 * 2 * len(row["tokens"]["output_ids"])
        observed["decisions"] = len(prepared["decisions"])
        diagnostic = tmp_path / "explicit-CPU-diagnostic-arithmetic"
        diagnostic.mkdir()
        (diagnostic / "admission.json").write_bytes(json_bytes(prepared))
        # An explicit display/arithmetic fixture, not supported configuration
        # evidence or an optimizer result. Original collection is untouched.
        diagnostic_weights = copy.deepcopy(proof)
        diagnostic_weights["rows"][0]["weight"] = 1.2
        (diagnostic / "composition-admission.json").write_bytes(json_bytes(diagnostic_weights))
        (diagnostic / "report.json").write_bytes(
            json_bytes(
                {
                    "status": "explicit_CPU_diagnostic_weight_fixture",
                    "old_critic_values": [0.0] * len(prepared["decisions"]),
                    "advantages": [r["reward"] for r in prepared["decisions"]],
                    "actor_optimizer_steps": 0,
                    "critic_optimizer_steps": 0,
                }
            )
        )
        signals = summarize_work_signals(actual_entries, diagnostic)
        assert signals["scheduled_slots"] == len(signals["slots"]) == 16
        assert all(slot["nominal_slot_weight"] == 1 / 16 for slot in signals["slots"])
        assert signals["decisions"][0]["composition_weight"] == 1.2
        assert signals["decisions"][0]["configured_token_average_weight"] == (
            1.2 * signals["decisions"][0]["nominal_token_average_weight"]
        )
        assert all(row["composition_weight"] == 1 for row in signals["decisions"][1:])
        raise StopBeforeOptimizer

    branch.update_window = inspect_update
    branch_output = tmp_path / "base-output"
    branch_output.mkdir()
    with pytest.raises(StopBeforeOptimizer):
        train_branch(branch, plan, catalog, branch_output, run_root, "base")
    assert observed["decisions"] > 0
    consumption = read_json(branch_output / "consumption.json")
    assert (
        consumption["same_complete_origin"]
        and consumption["restored_state_tensor_digest"] == original_digest
    )
    assert checked(consumption["raw_entries"]) == checked(marker["entries"])
    assert not (run_root / "base-complete.json").exists()
    assert not (branch_output / "update").exists()
    assert json_bytes(entries) == raw
    assert (
        branch.actor_steps
        == branch.critic_steps
        == collector.actor_steps
        == collector.critic_steps
        == 2
    )
