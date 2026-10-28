"""Two small-roster real-OpenHands CPU controls, not an evaluation.

Run under the already installed private Python with --output in a new project
folder. Network is rejected in-process and no GPU/model/runtime is launched.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import socket


def run_programmed_sdk(output, organization):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    os.environ.update(LITELLM_LOCAL_MODEL_COST_MAP="True", CUDA_VISIBLE_DEVICES="",
        NVIDIA_VISIBLE_DEVICES="void", OPENHANDS_SUPPRESS_BANNER="1",
        OH_PERSISTENCE_DIR=str(output / "empty-user-config"))
    denied_network = []
    original_socket = socket.socket

    class ConfinedSocket(original_socket):
        def __init__(self, family=socket.AF_INET, *args, **kwargs):
            if family in (socket.AF_INET, socket.AF_INET6):
                denied_network.append(str(family))
                raise RuntimeError("The fixed-organization CPU fixture has no network")
            super().__init__(family, *args, **kwargs)

    def no_dns(*_args, **_kwargs):
        denied_network.append("DNS")
        raise RuntimeError("The fixed-organization CPU fixture cannot resolve external names")

    socket.socket, socket.getaddrinfo = ConfinedSocket, no_dns

    from proworksim import software_fixed_organization_runtime_v065 as runtime_module
    from proworksim.software_fixed_organization_v065 import get_organization
    from proworksim import software_benchmark_managed_v064 as aligned
    from proworksim.repository_sources_v054 import capture_repository, tree_manifest
    from proworksim.software_benchmark_candidates_v054 import write_new
    from proworksim.software_organization_runtime_v047 import DispatchDeadline
    from proworksim.storage import digest, json_bytes

    spec = get_organization(organization)
    members = tuple(spec["fixed_members"])
    if organization not in {"DIALOGUE", "COUNCIL"}:
        raise ValueError("Only the two newly changed roster sizes need this CPU SDK control")
    calls_per_member = 3 if len(members) == 2 else 2
    expected_calls = len(members) * calls_per_member
    scripts = {
        members[0]: [("work_note", {"key": "private", "text": "CPU_PRIVATE_ONLY_001"}),
                     ("send_message", {"recipient": members[1], "task_id": "root_goal", "body": "public hello"}),
                     ("work_history_search", {"query": "CPU_PRIVATE_ONLY_001", "limit": 5})],
        members[1]: [("work_history_search", {"query": "CPU_PRIVATE_ONLY", "limit": 5}),
                     ("write_file", {"path": "sample.py", "text": "value = 2\n"}),
                     ("run_tests", {})],
    }
    if len(members) == 3:
        scripts[members[2]] = [("write_file", {"path": "sample.py", "text": "value = 3\n"}), ("run_tests", {})]

    class ScriptedModel:
        limits = {"context_limit": 131072}
        maximum_input_tokens, maximum_output_tokens = 98304, 32768
        model, thinking = "programmed-fixed-organization-cpu-v065", True
        fixture_only, external_resources_enabled = True, False

        def __init__(self):
            self.runtime = None
            self.requests, self.responses = [], []
            self.member_counts = {member: 0 for member in members}

        def request(self, messages, tools):
            return {"model": self.model, "messages": copy.deepcopy(messages),
                    "tools": copy.deepcopy(tools), "max_tokens": 32768, "stream": False}

        def count(self, wire):
            return {"prompt_tokens": 1000, "context_limit": 131072,
                    "method": "programmed CPU counter; not measured tokenizer usage",
                    "request_sha256": digest(json_bytes(wire)), "exact_provider_token_ids_available": False}

        def complete(self, wire, usage_id):
            assert usage_id == "agent"
            member = self.runtime._active["label"]
            member_number = self.member_counts[member]
            assert member_number < calls_per_member, (member, member_number)
            name, arguments = scripts[member][member_number]
            self.member_counts[member] += 1
            index = len(self.responses)
            self.requests.append({"member": member, "wire": copy.deepcopy(wire)})
            body = {"id": f"programmed-v065-{index}", "created": 0, "model": self.model,
                "object": "chat.completion", "choices": [{"index": 0, "finish_reason": "tool_calls",
                "message": {"role": "assistant", "content": "", "reasoning": f"Programmed private reasoning for {member}",
                    "tool_calls": [{"id": f"programmed-call-{index}", "type": "function",
                        "function": {"name": name, "arguments": json.dumps(arguments)}}]}}],
                "usage": {"prompt_tokens": 1000, "completion_tokens": 17, "total_tokens": 1017}}
            self.responses.append(copy.deepcopy(body))
            return body

    source = output / "public"
    source.mkdir()
    (source / "sample.py").write_text("value = 0\n")
    manifest = capture_repository(source, output / "snapshot", task_id="fixture__fixed-sdk-065",
        problem_statement="Programmed public fixture only: inspect this source.",
        source_identity={"instance_id": "fixture__fixed-sdk-065", "repo": "fixture/sdk",
                         "base_commit": "a" * 40, "dataset_revision": "b" * 40})
    public_calls = []

    def public_test(**payload):
        public_calls.append(copy.deepcopy(payload))
        return {"passed": False, "execution": {"executed": True,
            "input_tree_sha256": tree_manifest(payload["files"], payload["entry_metadata"])["tree_sha256"]},
            "groups": {"fixture": {"status": "failed", "executed": True, "passed": False,
                                   "tests": [{"test_id": "programmed", "passed": False}]}}}

    deadline = DispatchDeadline(soft_seconds=21600, hard_seconds=23400)
    prepared = runtime_module.prepare_case(manifest, output / "world", organization_id=organization,
        max_total_tokens=5000000, public_test_callback=public_test, deadline=deadline, max_decisions=expected_calls)
    adapter = ScriptedModel()
    owner = aligned.ProjectOwner(adapter, window_id="programmed-fixed-team-v065-" + organization,
                                 identity={"policy_version": "programmed-cpu-not-real-model"})
    runtime = None
    try:
        runtime, _, _ = runtime_module.build_runtime(owner, prepared, output / "runtime", deadline=deadline,
            public_initial_message=prepared.case["root_goal"], offline_fixture=True)
        adapter.runtime = runtime
        boundary = runtime_module.run_fragment(prepared, runtime)
        budget = runtime.team_budget.snapshot()
        assert boundary["execution_integrity_failure"] is None, boundary
        assert boundary["closure_reason"] == "shared_team_pool_exhausted", boundary
        assert len(adapter.responses) == budget["decisions"] == budget["attempts"] == expected_calls
        assert budget["charged_tokens"] == expected_calls * 1017
        assert adapter.member_counts == dict.fromkeys(members, calls_per_member)
        assert [item["member"] for item in adapter.requests] == list(members) * calls_per_member
        assert len(public_calls) == 1 and public_calls[0]["request"]["actor_id"] == members[-1]
        assert public_calls[0]["files"]["sample.py"] == f"value = {len(members)}\n"
        assert all("CPU_PRIVATE_ONLY_001" not in json.dumps(item["wire"])
                   for item in adapter.requests if item["member"] != members[0])
        assert all("CPU_PRIVATE_ONLY_002" not in json.dumps(item["wire"])
                   for item in adapter.requests if item["member"] != members[1])
        assert all(worker.llm.max_input_tokens == 98304 for worker in runtime.policies.values())
        assert all(message.get("reasoning_content") == message.get("reasoning")
                   for item in adapter.requests for message in item["wire"]["messages"]
                   if message.get("role") == "assistant")
        for member in members:
            observation = runtime.ports[member].observe()
            assert set(observation["fixed_organization"]["role_directory"]) == set(members)
            for definition in runtime.ports[member].tools():
                for argument in ("recipient", "to_member"):
                    prop = definition["parameters"].get("properties", {}).get(argument)
                    if prop is not None:
                        assert prop["enum"] == list(members)
        assert len(runtime.policies) == len(members)
        assert denied_network == []
        result = {"version": "v065-variable-roster-programmed-real-sdk-r2", "passed": True,
            "organization_id": organization, "actual_openhands_private_conversations": len(members),
            "programmed_sdk_responses": expected_calls,
            "programmed_tokens_not_actual_model_usage": budget["charged_tokens"],
            "per_member_programmed_calls": adapter.member_counts,
            "real_model_calls": 0, "actual_model_tokens": 0, "external_network_calls": 0,
            "docker_operations": 0, "gpu_operations": 0, "official_scores": 0,
            "public_fixture_callbacks": 1, "fixed_order_verified": True,
            "one_shared_budget_for_configured_members": True,
            "private_histories_verified": True, "reasoning_preserved": True,
            "boundary": boundary}
        write_new(output / "result.json", result)
        return result
    finally:
        if runtime is not None:
            runtime_module.close_runtime(runtime)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    output = parser.parse_args().output
    output.mkdir(parents=True, exist_ok=False)
    outcomes = [run_programmed_sdk(output / name, name) for name in ("DIALOGUE", "COUNCIL")]
    summary = {"version": "v065-variable-roster-real-sdk-cpu-r2", "passed": all(x["passed"] for x in outcomes),
               "cases": [{key: value for key, value in item.items() if key != "boundary"} for item in outcomes],
               "actual_model_calls": 0, "API_calls": 0, "Docker_operations": 0, "GPU_operations": 0,
               "old_four_session_SDK_control_repeated": False}
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(summary, ensure_ascii=False))
