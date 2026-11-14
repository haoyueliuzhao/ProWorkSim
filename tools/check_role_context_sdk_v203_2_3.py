"""Real pinned SDK + scripted provider + retained v175 CPU tests, no API/network."""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import inspect
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

os.environ.update(LITELLM_LOCAL_MODEL_COST_MAP="True", OPENHANDS_SUPPRESS_BANNER="1",
                  HF_HUB_OFFLINE="1", HF_DATASETS_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
ROOT = Path(__file__).resolve().parents[1]


def run(output, conditions=("K0", "K1", "K2")):
    from proworksim import software_role_baseline_runtime_v203_2_1 as base
    from proworksim.software_role_context_runtime_v203_2_3 import install
    from proworksim.software_collaboration_observation_v141 import load_official_content_counter
    from proworksim.software_public_test_retention_v203_2_3 import retaining_executor
    from proworksim.storage import digest, json_bytes
    from proworksim.software_benchmark_managed_v064 import MAX_INPUT_TOKENS
    from proworksim.software_role_context_v203_2_3 import digest as context_digest, EVIDENCE_KEY
    output.mkdir(parents=True, exist_ok=False)
    os.environ["OH_PERSISTENCE_DIR"] = str(output / "sdk-settings")
    spec = importlib.util.spec_from_file_location("cpu_fixture_v141", ROOT / "tools/check_role_baseline_sdk_v141.py")
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    tokenizer = ROOT / "runs/software-benchmark-v055/tokenizer-r1/manifest.json"
    count, tokenizer_metadata = load_official_content_counter(tokenizer,
        manifest_sha256=hashlib.sha256(tokenizer.read_bytes()).hexdigest())
    from proworksim.software_benchmark_deepseek_tokenizer_v055 import OfficialDeepSeekCounter
    from proworksim.software_benchmark_deepseek_prefix_v055_r2 import count_incomplete_prefix
    wire_counter = OfficialDeepSeekCounter(tokenizer,
        manifest_sha256=hashlib.sha256(tokenizer.read_bytes()).hexdigest())
    original_fixture = fixture.fixture
    summaries = []
    for condition in conditions:
        folder = output / condition
        captures, holder = [], {}

        def make_case(where, group):
            prepared, deadline, public_calls = original_fixture(where, group)

            def public_test(*, files, entry_metadata, request):
                public_calls.append(copy.deepcopy(request))
                target = where / "actual-public-tests" / str(len(public_calls))
                target.mkdir(parents=True)
                for name in ("sample.py", "test_sample.py"):
                    (target / name).write_text(files[name])
                entry = {"argv": [str(ROOT / ".venv/bin/python"), "-m", "pytest", "-q", "test_sample.py"]}
                execute = retaining_executor(where / "framework-journals", binding={
                    "source_reference": request["source_reference"], "candidate_tree_sha256": request["tree_sha256"],
                    "member": request["actor_id"], "condition": condition})
                value = execute(entry, root=target, environment={"PATH": "/usr/bin:/bin", "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}, timeout_seconds=20)
                proof = {key: value[key] for key in ("validation_status", "counts", "test_evidence")}
                return {"passed": value["passed"], **proof,
                    "execution": {"executed": True, "command_executed": True,
                        "input_tree_sha256": request["tree_sha256"], "actor_id": request["actor_id"],
                        "organization_id": group, "managed_request_sha256": digest(json_bytes(request)),
                        "argv": entry["argv"], "public_test_selection": request["public_test_selection"],
                        "public_test_selection_revision": "v110-public-test-selection-r1", **proof},
                    "groups": {"public_repository_tests": {"passed": value["passed"], "executed": True,
                        "status": "passed" if value["passed"] else "failed", "output": value["output"],
                        "tests": [{"test_id": "test_sample.py::test_value", "passed": value["passed"]}], **proof}},
                    "repository_collection_errors": []}
            prepared.source_provider.runner.callback = public_test
            return prepared, deadline, public_calls

        def build_owner(post, **kwargs):
            def captured(route, payload):
                captures.append({"route": route, "payload": copy.deepcopy(payload)})
                if route == "/tokenize":
                    return wire_counter.measure(payload["wire"])
                if route == "/tokenize-prefix":
                    prefix_folder = folder / "prefix-counts"
                    prefix_folder.mkdir(exist_ok=True)
                    tokens = count_incomplete_prefix(SimpleNamespace(counter=wire_counter, folder=prefix_folder),
                        payload["wire"], tuple(payload["pending_ids"]))
                    return {"prompt_tokens": tokens, "request_sha256": digest(json_bytes(payload["wire"])),
                        "method": "official_original_member_incomplete_prefix", "count_only_not_dispatchable": True}
                value = post(route, payload)
                measured = wire_counter.measure(payload["wire"])
                if payload["prompt_upper_bound"] != measured["prompt_tokens"]:
                    raise AssertionError("Actual SDK dispatch reservation differs from the official local counter")
                value["usage"].update(prompt_tokens=measured["prompt_tokens"],
                    total_tokens=measured["prompt_tokens"] + 25,
                    prompt_cache_miss_tokens=measured["prompt_tokens"])
                return value
            return base.build_team_owner(captured, **kwargs)

        def build_runtime(*args, **kwargs):
            result = base.build_runtime(*args, **kwargs)
            runtime = result[0]
            holder["runtime"] = runtime
            holder["prepared"] = args[1]
            holder["condenser"] = {member: worker.agent.condenser.model_dump(exclude={"llm"})
                for member, worker in runtime.policies.items()}
            holder["installed"] = install(runtime, condition=condition, folder=folder / "role-projections",
                budget_tokens=4096, count=count, request_budget_tokens=MAX_INPUT_TOKENS)
            return result

        def finalize(prepared, destination, slot):
            from proworksim.software_benchmark_project_closure_v203_2_3 import export_managed_closure
            closure = export_managed_closure(prepared, destination, slot_id=slot, sdk_closed=True)
            if closure["group_id"] != condition or closure["organization_id"] != "REVIEW2":
                raise AssertionError("New K-arm closure lost its group or fixed organization identity")
            holder["closure"] = closure
            return closure["controller_candidate_lock"]

        namespace = {**fixture.__dict__, "fixture": make_case, "_condition": condition, "_finalize": finalize,
            "_runtime": SimpleNamespace(**{**base.__dict__, "build_team_owner": build_owner, "build_runtime": build_runtime})}
        source = inspect.getsource(fixture.run)
        source = source.replace("from proworksim import software_role_baseline_runtime_v141 as runtime_module", "runtime_module = _runtime")
        source = source.replace('slot = f"cpu-v141:fixture__sdk-141:{cfg[\'condition_id\']}:141"',
            'slot = f"v203.2.3:fixture__sdk-141:{_condition}:141"')
        source = source.replace("condition_id=cfg['condition_id']", "condition_id=_condition")
        source = source.replace("    if group == 'REVIEW2':\n        runtime.policies['member_002'].agent.condenser.max_size = 12\n", "")
        source = source.replace("assert summaries and summary['artifacts']['independent_review_events'] == 1", "assert summary['artifacts']['independent_review_events'] == 1")
        # v172 observer intentionally leaves total unknown without cash receipts;
        # the CPU provider has token receipts but never a real cash settlement.
        source = source.replace("summary['usage']['actual_total_tokens'] == owner.adapter.ledger.actual",
            "summary['usage']['known_actual_tokens']['total_tokens'] == owner.adapter.ledger.actual")
        source = source.replace("owner.adapter.ledger.actual == len(requests)*281 == runtime.team_budget.snapshot()['charged_tokens']",
            "owner.adapter.ledger.actual == runtime.team_budget.snapshot()['charged_tokens']")
        source = source.replace("lock = runtime_module.lock_fixed_candidates(prepared, folder/'closure', sdk_closed=True)",
            "lock = _finalize(prepared, folder/'new-group-closure', slot)")
        exec(compile(source, __file__ + ":scripted-real-SDK", "exec"), namespace)
        result = namespace["run"](folder, "REVIEW2")
        runtime = holder["runtime"]
        closure = holder["closure"]
        if holder["condenser"] != {member: worker.agent.condenser.model_dump(exclude={"llm"}) for member, worker in runtime.policies.items()}:
            raise AssertionError("The original SDK condenser parameters changed")
        receipts = [row for value in holder["installed"].values() for row in value["receipts"]]
        if condition == "K0" and any(row["baseline_request_sha256"] != row["selected_request_sha256"] for row in receipts):
            raise AssertionError("K0 changed the original v117 request")
        counts = {digest(json_bytes(row["payload"]["wire"])) for row in captures if row["route"] == "/tokenize"}
        dispatches = [row for row in captures if row["route"] == "/chat/completions" and row["payload"]["usage_id"] == "agent"]
        if not dispatches or any(digest(json_bytes(row["payload"]["wire"])) not in counts for row in dispatches):
            raise AssertionError("Actual SDK dispatch wire lacks its same-byte counting request")
        selected = [row for row in receipts if row["proof"].get("request_projection_applied")]
        if condition != "K0" and not selected:
            raise AssertionError(condition + " never applied an actual SDK role projection")
        role_nonzero = sum(any(rank["score"]["role"] for rank in row["proof"].get("ranking", [])) for row in receipts)
        if condition == "K2" and not role_nonzero:
            raise AssertionError("K2 degenerated to zero role ranking")
        verified_removed = 0
        for dispatched in dispatches:
            wire = dispatched["payload"]["wire"]
            matches = [row for row in selected if row["selected_request_sha256"] == context_digest(wire)]
            if not matches:
                continue
            projected = matches[-1]
            for removed in projected["proof"]["eligible_dynamic_fields_removed"]:
                body = json.loads(wire["messages"][removed["message_index"]]["content"])
                field = removed["pointer"].split("/")[-1]
                if field in body["observation"]:
                    raise AssertionError("An eligible historical field was duplicated in the actual model request")
                verified_removed += 1
            envelopes = [json.loads(m["content"]) for m in wire["messages"] if m.get("role") == "user"
                         and isinstance(m.get("content"), str) and EVIDENCE_KEY in m["content"]]
            if len([body for body in envelopes if EVIDENCE_KEY in body]) != 1:
                raise AssertionError("Selected historical field cards were not presented exactly once")
        if condition != "K0" and not verified_removed:
            raise AssertionError("No actual SDK dispatch demonstrated eligible-field omission")
        deltas = [row["proof"]["baseline_request_tokens_local_estimate"] - row["proof"]["request_tokens_local_estimate"]
                  for row in selected]
        record = {"condition": condition, "actual_sdk": True, "scripted_result": result,
            "selector_calls": len(receipts), "applied_selector_calls": len(selected), "role_sensitive_calls": role_nonzero,
            "dispatches_with_same_byte_count": len(dispatches), "original_condenser_parameters_unchanged": True,
            "billing": "synthetic usage set to official local count plus 25 output tokens; not provider billing", "tokenizer": tokenizer_metadata,
            "actual_dispatch_prompt_upper_bounds": [row["payload"]["prompt_upper_bound"] for row in dispatches],
            "all_dispatch_reservations_match_official_local_recipe": True,
            "eligible_field_omissions_checked_in_actual_dispatch": verified_removed,
            "serialized_content_token_savings_range": [min(deltas), max(deltas)] if deltas else [0, 0],
            "selected_field_sequences": [row["selected_fields"] for row in selected],
            "new_group_closure": closure}
        summaries.append(record)
        (folder / "transport-capture.json").write_text(json.dumps(captures, ensure_ascii=False) + "\n")
        (folder / "role-control.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    by_condition = {row["condition"]: row for row in summaries}
    difference = (by_condition["K1"]["selected_field_sequences"] != by_condition["K2"]["selected_field_sequences"]
                  if {"K1", "K2"} <= set(by_condition) else None)
    if difference is False:
        raise AssertionError("K1 and K2 did not produce different actual SDK field sequences")
    result = {"passed": True, "API_calls": 0, "Docker_operations": 0, "real_model_calls": 0,
        "actual_pinned_SDK": True, "conditions": summaries, "K1_K2_actual_field_sequences_differ": difference,
        "deployment_qualified": False, "task_interpreter_qualified": False}
    (output / "summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return {"passed": True, "summary": str(output / "summary.json"), "real_model_calls": 0}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--conditions", nargs="+", choices=("K0", "K1", "K2"), default=["K0", "K1", "K2"])
    args = parser.parse_args()
    def no_network(event, values):
        if event in {"socket.connect", "socket.bind", "socket.getaddrinfo", "socket.sendto"}:
            raise AssertionError("Network forbidden in this real SDK scripted control")
    sys.addaudithook(no_network)
    print(json.dumps(run(args.output.resolve(), args.conditions), ensure_ascii=False))
