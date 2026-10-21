"""Two full host lifecycle controls with programmed responses, never real API.

Both actual SDK paths use an already qualified public repository and original
isolated Actor. Only this subprocess substitutes the client/counter/controller
entry and a separate claim root. Formal sources, slots and ledger stay intact.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import copy
import importlib.util
import json
from pathlib import Path
import socket
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def controller_fixture(config_path):
    config = json.loads(config_path.read_bytes())
    folder = Path(config["output"])
    import proworksim.software_benchmark_deepseek_api_v055 as api
    import proworksim.software_benchmark_deepseek_tokenizer_v055 as tokenizer
    from proworksim.software_benchmark_candidates_v054 import write_new
    from proworksim.storage import digest, json_bytes

    network_attempts = []

    def deny_network(event, arguments):
        if event == "socket.getaddrinfo" or (event == "socket.connect"
                and arguments[0].family in {socket.AF_INET, socket.AF_INET6}):
            network_attempts.append(event)
            raise RuntimeError("Host lifecycle fixture forbids every Internet request")

    sys.addaudithook(deny_network)
    fixture_calls = []
    if config["arm"] == "PROJECT":
        public_readme = "README.rst" if Path("/testbed/README.rst").is_file() else "README.md"
        steps = [("read_file", {"path": public_readme}), ("staff_done", {"reason": "Programmed host lifecycle complete"})]
    else:
        steps = [("think", {"thought": "Programmed host lifecycle check"}),
                 ("finish", {"message": "Programmed host lifecycle complete"})]

    class FixtureTransport:
        def request(self, method, path, payload):
            index = len(fixture_calls)
            if (method, path) != ("POST", "/chat/completions") or index >= 2:
                raise ValueError("Exactly two local programmed responses are permitted")
            fixture_calls.append(copy.deepcopy(payload))
            name, arguments = steps[index]
            identity = config["slot_id"] + "-" + str(index)
            return {"id": identity, "model": "deepseek-flash",
                "choices": [{"index": 0, "finish_reason": "tool_calls", "message": {
                    "role": "assistant", "content": "", "reasoning_content": "",
                    "tool_calls": [{"id": identity + "-call", "type": "function",
                        "function": {"name": name, "arguments": json.dumps(arguments)}}]}}],
                "usage": {"prompt_tokens": 1000, "completion_tokens": 30, "total_tokens": 1030,
                          "prompt_cache_hit_tokens": 500, "prompt_cache_miss_tokens": 500}}

    original_client = api.DeepSeekClient

    def fake_client(**kwargs):
        if Path(kwargs["ledger_path"]).resolve() != (folder.parent / "programmed-only.sqlite3").resolve():
            raise ValueError("Fixture may not write into the shared monetary ledger")
        return original_client(**kwargs, transport=FixtureTransport())

    def counter(request):
        return {"prompt_tokens": 1000, "method": "programmed_host_lifecycle_only_not_provider_count",
                "request_sha256": digest(json_bytes(request))}

    api.DeepSeekClient = fake_client
    api.load_api_key = lambda _: "programmed-fixture-no-real-secret"
    tokenizer.build_counter = lambda _: counter
    source = ROOT / "tools/run_deepseek_controller_v055.py"
    spec = importlib.util.spec_from_file_location("v055_actual_controller_for_host_fixture", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.argv = [str(source), "--config", str(config_path)]
    try:
        return module.main()
    finally:
        write_new(folder / "programmed-model-control.json", {"programmed_responses": len(fixture_calls),
            "network_attempts": network_attempts, "real_model_calls": 0, "official_grader_calls": 0,
            "shared_monetary_ledger_used": False, "local_fixture_accounting_is_not_spend": True})


def host_control(source_config, output):
    from proworksim import software_benchmark_runner_v055 as runner
    from proworksim.software_benchmark_candidates_v054 import checked, reference, write_new
    from proworksim.software_benchmark_scorer_v055 import check_candidate
    out = output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    original = json.loads(source_config.read_bytes())
    task_id = original["public_task"]["instance_id"]
    slots = [{"slot_id": "v055-host-lifecycle-" + arm + "-" + task_id,
              "arm": arm, "condition_id": arm + "-nonthinking", "thinking": False,
              "instance_id": task_id, "seed": original["seed"]} for arm in ("MATCH", "PROJECT")]
    slots_ref = write_new(out / "programmed-only-slots.json", {"slots": slots,
        "programmed_host_control_only": True, "formal_task_count": 0})
    permit = write_new(out / "programmed-only-authorization.json", {
        "execution_authorized": True, "slots_sha256": slots_ref["sha256"],
        "slot_ids": [row["slot_id"] for row in slots], "real_API_authorized": False,
        "programmed_host_control_only": True, "formal_3000_slots_claimed": False})
    original_environment = runner.direct_environment_command

    def fixture_command(command):
        command = list(command)
        index = command.index(str(ROOT / "tools/run_deepseek_controller_v055.py"))
        command[index:index + 1] = [str(Path(__file__).resolve()), "--controller-fixture"]
        return original_environment(command)

    runner.RUN_ROOT = out
    runner.direct_environment_command = fixture_command
    sources = [reference(path) for directory in (ROOT / "src/proworksim", ROOT / "tools")
               for path in sorted(directory.glob("*v055*")) if path.suffix in {".py", ".sh"}]
    scorer_manifest = reference(ROOT / "runs/software-benchmark-v055/scorer-preflight-r1/installation-manifest.json")

    def one(slot):
        arm = slot["arm"]
        folder = out / arm
        folder.mkdir()
        condition_ref = reference(ROOT / ("config/v055-condition-" + slot["condition_id"] + ".json"))
        config = {key: original[key] for key in ("public_tasks", "public_task", "public_test_registry",
            "public_test_entry", "stdlib", "sdk_runtime", "lazy_native_preparation", "dataset_revision")}
        config.update(version="v055-deepseek-slot-config-r1", **slot, slots=slots_ref,
            authorization=permit, configuration=condition_ref, frozen_sources=sources,
            preparation_only=False, all_solver_admissions_passed=True, programmed_host_control_only=True,
            model="deepseek-flash", ledger_path=str(folder / "programmed-only.sqlite3"),
            api_key_file="unused-programmed-no-key", max_api_concurrency=64,
            context_counter={"module": "proworksim.software_benchmark_deepseek_tokenizer_v055",
                             "programmed_host_control_only": True},
            scorer_request_base={**original["scorer_request_base"], "scorer_manifest": scorer_manifest,
                "trusted_output_root": str(out / "never-executed-official-output")})
        write_new(folder / "config.json", config)
        result = runner.run(config, folder / "episode")
        if result["status"] != "closed":
            return {"arm": arm, "passed": False, "result": reference(folder / "episode/result.json")}
        programmed = json.loads((folder / "episode/programmed-model-control.json").read_bytes())
        if (programmed["programmed_responses"] != 2 or programmed["network_attempts"]
                or programmed["real_model_calls"] != 0 or not result["temporary_rootfs_cleanup"]):
            raise ValueError("Programmed model/cleanup evidence is incomplete")
        for request_ref in result["scoring_requests"]:
            check_candidate(json.loads(checked(request_ref).read_bytes()))
        return {"arm": arm, "passed": True, "result": reference(folder / "episode/result.json"),
            "programmed_model": reference(folder / "episode/programmed-model-control.json"),
            "candidate_export_and_request_validation": True, "official_grader_calls": 0,
            "real_model_calls": 0, "formal_3000_slot_claims": 0}

    with ThreadPoolExecutor(max_workers=2) as executor:
        cases = list(executor.map(one, slots))
    receipt = {"version": "v055-programmed-full-host-lifecycle-r1", "passed": all(row["passed"] for row in cases),
        "cases": cases, "real_model_calls": 0, "official_grader_calls": 0,
        "formal_3000_slot_claims": 0, "GPU_loads": 0, "programmed_responses_are_not_model_results": True,
        "source_config": reference(source_config), "sources": sources,
        "separate_claim_root": str(out / "episode-claims"), "shared_monetary_ledger_used": False}
    write_new(out / "receipt.json", receipt)
    print(json.dumps({key: receipt[key] for key in ("passed", "real_model_calls", "official_grader_calls", "formal_3000_slot_claims")}))
    return 0 if receipt["passed"] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--controller-fixture", action="store_true")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--source-config", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.controller_fixture:
        return controller_fixture(args.config)
    return host_control(args.source_config, args.output)


if __name__ == "__main__":
    raise SystemExit(main())
