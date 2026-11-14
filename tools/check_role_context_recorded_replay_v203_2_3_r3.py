"""Reproduce the paid-response SDK failure, then test the new source mapping; zero API."""
from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import sys
from types import MethodType

os.environ.update(LITELLM_LOCAL_MODEL_COST_MAP="True", OPENHANDS_SUPPRESS_BANNER="1",
                  HF_HUB_OFFLINE="1", HF_DATASETS_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
ROOT = Path(__file__).resolve().parents[1]


def run(output):
    from proworksim import software_role_baseline_runtime_v203_2_1 as managed
    from proworksim import software_role_context_runtime_v203_2_3 as old
    from proworksim import software_role_context_runtime_v203_2_3_r3 as fixed
    from proworksim.software_role_context_recorded_replay_v203_2_3_r3 import RecordedProviderReplay, run_sdk_replay
    from proworksim.software_collaboration_observation_v141 import load_official_content_counter
    from proworksim.software_benchmark_deepseek_tokenizer_v055 import OfficialDeepSeekCounter
    from proworksim.software_benchmark_managed_v064 import MAX_INPUT_TOKENS
    from proworksim.software_benchmark_candidates_v054 import reference
    from proworksim.repository_sources_v054 import capture_repository
    from proworksim.software_organization_runtime_v047 import DispatchDeadline
    output.mkdir(parents=True, exist_ok=False)
    os.environ["OH_PERSISTENCE_DIR"] = str(output / "sdk-settings")
    tokenizer = ROOT / "runs/software-benchmark-v055/tokenizer-r1/manifest.json"
    token_ref = reference(tokenizer)
    counter = OfficialDeepSeekCounter(tokenizer, manifest_sha256=token_ref["sha256"])
    count, token_metadata = load_official_content_counter(tokenizer, manifest_sha256=token_ref["sha256"])
    origin = ROOT / "runs/software-benchmark-v203-2-3/role-context-pilot12-r2/episodes/2032300/controller-output/source-snapshot/initial-tree.json"
    public = json.loads(origin.read_bytes())["files"]
    chosen = {name: text for name, text in public.items() if name.startswith("astropy/timeseries/")}
    reports = []
    for label, condition, module in (("old-K0", "K0", old), ("fixed-K0", "K0", fixed),
                                     ("fixed-K1", "K1", fixed), ("fixed-K2", "K2", fixed)):
        folder = output / label
        source = folder / "public-subset"
        source.mkdir(parents=True)
        for name, text in chosen.items():
            path = source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        case_id = "fixture__recorded-20323"
        manifest = capture_repository(source, folder / "source-snapshot", task_id=case_id,
            problem_statement="Diagnostic public subset: inspect TimeSeries required-columns handling; this is a recorded-response replay, not benchmark evaluation.",
            source_identity={"instance_id": case_id, "repo": "fixture/recorded-provider-output", "base_commit": "a" * 40, "dataset_revision": "b" * 40})
        deadline = DispatchDeadline(soft_seconds=600, hard_seconds=660)
        def no_tests(**kwargs):
            raise AssertionError("The original response tape did not request public tests")
        entry = {"version": "v064-repository-public-test-entry-r1", "instance_id": case_id,
            "argv": [str(ROOT / ".venv/bin/python"), "-m", "pytest"], "cwd": "/testbed",
            "timeout_seconds": 20, "hidden_material_used": False}
        prepared = managed.prepare_case(manifest, folder / "world", organization_id="REVIEW2",
            public_test_callback=no_tests, deadline=deadline, public_test_entry=entry)
        replay = RecordedProviderReplay(counter, folder / "recorded-provider")
        owner = managed.build_team_owner(replay.post, organization_id="REVIEW2",
            slot_id="cpu-recorded-format:" + label, condition_id=condition, folder=folder / "model-ledger",
            deadline=deadline, identity={"policy_version": "recorded-provider-output-zero-network-diagnostic"},
            observation_token_counter=count, observation_tokenizer_id=token_metadata["tokenizer_id"])
        runtime, _, _ = managed.build_runtime(owner, prepared, folder / "runtime", deadline=deadline,
            public_initial_message="Use only this diagnostic public subset. Provider responses are replayed unchanged; no new model exists.")
        module.install(runtime, condition=condition, folder=folder / "context-projections", budget_tokens=4096,
            count=count, request_budget_tokens=MAX_INPUT_TOKENS)
        captured = []
        if label == "old-K0":
            for member, worker in runtime.policies.items():
                hook = worker.transport.select_for_member
                def trace(self, request, actor, *, hook=hook, worker=worker):
                    try:
                        return hook(request, actor)
                    except ValueError as error:
                        if "Candidate lacks the actual worker presentation registration" not in str(error):
                            raise
                        baseline, feedback, history = type(self).select_for_member(self, request, actor)
                        value = {"error": str(error), "actor": actor, "request": copy.deepcopy(request),
                            "baseline": baseline, "feedback": feedback, "history": history,
                            "registered_observations": list(worker._observation_texts)}
                        captured.append(value)
                        (folder / "actual-failing-SDK-input.json").write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
                        raise
                worker.transport.select_for_member = MethodType(trace, worker.transport)
        try:
            result = run_sdk_replay(runtime, replay)
            (folder / "observed-replay-result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
            if label == "old-K0":
                if result["passed"] or not captured or result["recorded_two_tool_response_rejected"] is not True:
                    raise AssertionError("Original runtime did not reproduce the real paid-response failure")
                result["expected_old_failure_reproduced"] = True
            elif result["passed"] is not True or result["recorded_two_tool_response_rejected"] is not True:
                raise AssertionError("New SDK source mapping did not survive the recorded real format rejection")
        finally:
            managed.close_runtime(runtime)
        (folder / "summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        reports.append({"case": label, "passed": result["passed"],
            "expected_old_failure_reproduced": result.get("expected_old_failure_reproduced", False),
            "recovery_projection_calls": result["recovery_projection_calls"],
            "remapped_projection_calls": result["remapped_projection_calls"], "report": reference(folder / "summary.json")})
    result = {"passed": True, "cases": reports, "actual_fixed_SDK": True,
        "historical_provider_tape": reference(ROOT / "config/v203-2-3-recorded-format-replay.json"),
        "public_subset_origin": reference(origin), "public_subset_files": len(chosen),
        "new_model_calls": 0, "Docker_operations": 0, "new_provider_billing": 0,
        "scope": "Recorded real output recovery edge plus declared diagnostic stop; not a fresh model or official benchmark score"}
    (output / "summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return {"passed": True, "summary": str(output / "summary.json")}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    def deny_network(event, values):
        if event in {"socket.connect", "socket.bind", "socket.getaddrinfo", "socket.sendto"}:
            raise AssertionError("No network or new provider call in recorded-response SDK replay")
    sys.addaudithook(deny_network)
    print(json.dumps(run(args.output.resolve()), ensure_ascii=False))
