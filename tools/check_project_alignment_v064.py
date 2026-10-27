"""CPU-only real-SDK fixture for the newly aligned managed PROJECT path.

Responses and their token counters are programmed, not model generations or
measured tokenizer counts. Network, Docker, GPU and official grading are unused.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import socket

from proworksim import software_benchmark_managed_v064 as managed
from proworksim.repository_sources_v054 import capture_repository, tree_manifest
from proworksim.software_benchmark_candidates_v054 import lock_episode_candidates, read_episode_candidates, write_new
from proworksim.software_calibration_collector_v051 import budget_snapshot, close_runtime, run_fragment
from proworksim.software_organization_runtime_v047 import DispatchDeadline
from proworksim.storage import digest, json_bytes


class ScriptedModel:
    limits = {"context_limit": 131072}
    maximum_input_tokens, maximum_output_tokens = 98304, 32768
    model, thinking = "programmed-cpu-fixture-v064", True

    def __init__(self):
        self.responses, self.requests = [], []
        self.script = [
            ("search_repository", {"text": "value"}),
            ("write_file", {"path": "sample.py", "text": "value = 1\n"}),
            ("run_tests", {}),
            ("fix_patch", {"task_ids": [], "message": "Explicit current fixed version"}),
            ("submit_integration", {"message": "Explicit tested delivery"}),
            ("staff_done", {"reason": "Scripted fixture is finished"}),
        ]

    def request(self, messages, tools):
        return {"model": self.model, "messages": copy.deepcopy(messages), "tools": copy.deepcopy(tools),
                "max_tokens": 32768, "stream": False}

    def count(self, wire):
        return {"prompt_tokens": 90000, "context_limit": 131072,
                "method": "programmed CPU fixture; not a real tokenizer measurement",
                "request_sha256": digest(json_bytes(wire)), "exact_provider_token_ids_available": False}

    def complete(self, wire, usage_id):
        assert usage_id == "agent" and len(self.responses) < len(self.script)
        self.requests.append(copy.deepcopy(wire))
        index = len(self.responses)
        name, arguments = self.script[index]
        body = {"id": f"fixture-v064-{index}", "created": 0, "model": self.model,
                "object": "chat.completion", "choices": [{"index": 0, "finish_reason": "tool_calls",
                "message": {"role": "assistant", "content": "", "reasoning": f"fixture reasoning {index}",
                            "tool_calls": [{"id": f"fixture-call-{index}", "type": "function",
                                            "function": {"name": name, "arguments": json.dumps(arguments)}}]}}],
                "usage": {"prompt_tokens": 90000, "completion_tokens": 17, "total_tokens": 90017}}
        self.responses.append(copy.deepcopy(body))
        return body


def run(output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    os.environ.update(LITELLM_LOCAL_MODEL_COST_MAP="True", CUDA_VISIBLE_DEVICES="",
                      NVIDIA_VISIBLE_DEVICES="void", OPENHANDS_SUPPRESS_BANNER="1",
                      OH_PERSISTENCE_DIR=str(output / "empty-user-config"))
    original_socket = socket.socket
    class ConfinedSocket(original_socket):
        def __init__(self, family=socket.AF_INET, *args, **kwargs):
            if family in (socket.AF_INET, socket.AF_INET6):
                raise RuntimeError("This programmed SDK fixture cannot use the network")
            super().__init__(family, *args, **kwargs)
    def no_dns(*args, **kwargs):
        raise RuntimeError("This programmed SDK fixture cannot resolve network names")
    socket.socket, socket.getaddrinfo = ConfinedSocket, no_dns
    source = output / "public"
    source.mkdir()
    (source / "sample.py").write_text("value = 0\n")
    manifest = capture_repository(source, output / "snapshot", task_id="fixture__sdk-064",
        problem_statement="Programmed public fixture: change value from 0 to 1.",
        source_identity={"instance_id": "fixture__sdk-064", "repo": "fixture/sdk",
                         "base_commit": "a" * 40, "dataset_revision": "b" * 40})
    public_calls = []
    def public_test(**payload):
        public_calls.append(copy.deepcopy(payload))
        passed = payload["files"]["sample.py"] == "value = 1\n"
        return {"passed": passed, "execution": {"executed": True,
                "input_tree_sha256": tree_manifest(payload["files"], payload["entry_metadata"])["tree_sha256"]},
                "groups": {"fixture": {"status": "passed" if passed else "failed", "executed": True,
                                       "passed": passed, "tests": [{"test_id": "fixture", "passed": passed}]}}}
    deadline = DispatchDeadline(soft_seconds=21600, hard_seconds=23400)
    prepared = managed.prepare_case(manifest, output / "world", max_total_tokens=5_000_000,
        public_test_callback=public_test, deadline=deadline)
    adapter = ScriptedModel()
    owner = managed.ProjectOwner(adapter, window_id="programmed-v064-sdk-fixture",
                                 identity={"policy_version": "programmed-fixture-not-a-model"})
    runtime = None
    try:
        runtime, _, _ = managed.build_runtime(owner, prepared, output / "runtime", deadline=deadline,
            public_initial_message="Programmed public fixture: change value from 0 to 1.\nPublic Python: fixture only.")
        boundary = run_fragment(prepared, runtime)
        counters = budget_snapshot(runtime, prepared)
        if boundary["execution_integrity_failure"] is not None:
            raise ValueError(boundary["execution_integrity_failure"])
        assert len(adapter.responses) == 6, boundary
        assert counters["model"]["charged_tokens"] == 540102
        assert counters["model"]["attempts"] == 6
        assert len(public_calls) == 1
        assert runtime.policies["member_001"].llm.max_input_tokens == 98304
        assert all(message.get("reasoning_content") == message.get("reasoning")
                   for request in adapter.requests for message in request["messages"]
                   if message.get("role") == "assistant")
    finally:
        if runtime is not None:
            close_runtime(runtime)
    locked = lock_episode_candidates(prepared, run_root=output / "candidates")
    candidates = read_episode_candidates(locked)
    assert candidates["terminal_code"]["files"]["sample.py"] == "value = 1\n"
    assert candidates["last_legal_delivery"]["files"]["sample.py"] == "value = 1\n"
    result = {"version": managed.VERSION, "passed": True, "programmed_sdk_responses": 6,
              "programmed_token_counters": 540102, "real_model_calls": 0, "real_model_tokens": 0,
              "network_calls": 0, "docker_operations": 0, "gpu_operations": 0, "official_scores": 0,
              "actual_single_agent_SDK_runtime": True, "public_fixture_calls": 1,
              "old_500k_and_18432_gates_crossed_in_programmed_fixture": True,
              "full_input_limit": 98304, "output_limit": 32768,
              "reasoning_preserved_in_following_input": True,
              "explicit_same_version_delivery": True, "candidate_lock": locked,
              "counters_are_programmed_not_tokenizer_or_model_measurements": True}
    write_new(output / "result.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    print(json.dumps(run(parser.parse_args().output), ensure_ascii=False))
