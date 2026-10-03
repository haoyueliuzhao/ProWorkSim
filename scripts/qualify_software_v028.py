"""CPU tokenizer + actual SDK software success controls, never model sampling.

Only the local tokenizer is loaded. Known-code scripts exercise the real world,
SDK, native XML parser and independent acceptance; their fictitious probability
traces must never be used as current-model or learning evidence.
"""

import argparse
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

# Bind both implementation and explicit CPU test fixtures to this checkout.
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests")]

from proworksim.audit import code_identity  # noqa: E402
from proworksim.deterministic_work_v024 import DeterministicCandidateActor  # noqa: E402
from proworksim.software_collaboration_v028 import CASE_IDS, MEMBERS, case_spec  # noqa: E402
from proworksim.software_context_v028 import VERSION as CONTEXT_POLICY, project_software_request  # noqa: E402
from proworksim.software_runtime_v028 import collect_software_window  # noqa: E402
from proworksim.storage import atomic_write, digest, json_bytes, read_json  # noqa: E402
from test_software_runtime_v028 import ScriptedSoftwareOwner, successful_cpu_actions  # noqa: E402

VERSION = "software-sdk-tokenizer-qualification-v0.28.1"
CONTEXT = 16384
OUTPUT = 2048
MINIMUM_MARGIN = 1024


def file_reference(path):
    path = Path(path).resolve()
    return {"path": str(path), "sha256": digest(path.read_bytes())}


def native_xml(name, arguments):
    """Use the same native string/nonstring representation as the frozen parser."""
    parameters = "\n".join(
        "<parameter=" + key + ">\n" + (value if isinstance(value, str)
                                      else json.dumps(value, ensure_ascii=False)) + "\n</parameter>"
        for key, value in arguments.items())
    return "<tool_call>\n<function=" + name + ">\n" + parameters + "\n</function>\n</tool_call><|im_end|>"


class QualifiedProgramOwner(ScriptedSoftwareOwner):
    """Follows explicit test actions; request rendering never invokes a network."""

    def __init__(self, actions, *, tokenizer, profile, output, window_id):
        super().__init__(actions, window_id=window_id)
        self.recipe.update(max_length=CONTEXT, max_output_tokens=OUTPUT)
        self.output = Path(output)
        self.output.mkdir(parents=True, exist_ok=False)
        # Do not call any actor constructor/from_candidate or create a network.
        self.renderer = object.__new__(DeterministicCandidateActor)
        self.renderer.tokenizer = tokenizer
        self.renderer.inference_profile = copy.deepcopy(profile)
        self.software_context_policy = CONTEXT_POLICY
        self.measurements = []

    def complete(self, request, **kwargs):
        response = super().complete(request, **kwargs)
        body = response["body"]
        function = body["choices"][0]["message"]["tool_calls"][0]["function"]
        arguments = json.loads(function["arguments"])
        selected, context_projection = project_software_request(
            request, render=self.renderer.prepare_request, tokenizer=self.renderer.tokenizer,
            context_limit=CONTEXT)
        if not context_projection["fits"]:
            raise ValueError("Qualification program exceeds the declared context capacity")
        rendered, messages, projection = self.renderer.prepare_request(selected)
        wire = native_xml(function["name"], arguments)
        number = len(self.measurements) + 1
        folder = self.output / f"request-{number:03d}"
        folder.mkdir()
        # Archive the proposed program output before parsing, so even a failed
        # future codec check retains the exact attempted bytes and real input.
        for name, data in (("request.json", request), ("selected-request.json", selected),
                           ("context-projection.json", context_projection), ("normalized-messages.json", messages),
                           ("projection.json", projection)):
            atomic_write(folder / name, json_bytes(data))
        atomic_write(folder / "rendered-prompt.txt", rendered.encode())
        atomic_write(folder / "program-output.xml", wire.encode())
        parsed, error = self.renderer.parse_response(wire, selected)
        atomic_write(folder / "native-parsed.json", json_bytes({"message": parsed, "error": error}))
        if error is not None:
            raise ValueError({"program_native_parse_error": error})
        parsed_call = parsed["tool_calls"][0]["function"]
        if (parsed_call["name"] != function["name"]
                or json.loads(parsed_call["arguments"]) != arguments):
            raise ValueError("Native program parsing changed the scripted action")
        tokenizer = self.renderer.tokenizer
        prompt_ids = tokenizer(rendered, add_special_tokens=False)["input_ids"]
        output_ids = tokenizer(wire, add_special_tokens=False)["input_ids"]
        member = body["id"].rsplit("-", 1)[0]
        for name, data in (("prompt-input-ids.json", prompt_ids), ("program-output-ids.json", output_ids)):
            atomic_write(folder / name, json_bytes(data))
        measurement = {
            "request_index": number, "member": member, "member_decision": self.calls[member],
            "action": function["name"], "prompt_tokens": len(prompt_ids),
            "program_output_tokens": len(output_ids),
            "reserved_output_tokens": OUTPUT, "context_limit": CONTEXT,
            "remaining_context_after_output_reservation": CONTEXT - OUTPUT - len(prompt_ids),
            "fits_context": len(prompt_ids) + OUTPUT <= CONTEXT,
            "program_output_within_limit": len(output_ids) <= OUTPUT,
            "request": file_reference(folder / "request.json"),
            "rendered_prompt": file_reference(folder / "rendered-prompt.txt"),
            "program_output": file_reference(folder / "program-output.xml"),
            "projection": projection, "native_parser_roundtrip": True,
            "context_projection": context_projection,
            "source": "actual SDK request and official local tokenizer; scripted output, zero model calls",
        }
        atomic_write(folder / "measurement.json", json_bytes(measurement))
        self.measurements.append(measurement)
        # Feed the SDK the actual native parser result, including real structural
        # tool-call IDs. These placeholders remain visibly synthetic; separate
        # files above contain measured prompt/program tokenization, not logits.
        body["choices"][0]["message"] = parsed
        body["usage"] = {"prompt_tokens": len(prompt_ids), "completion_tokens": len(output_ids),
                         "total_tokens": len(prompt_ids) + len(output_ids)}
        body["token_trace"].update(
            fixture_only=True, source="synthetic CPU fixture token/probability placeholders; never model sampling",
            tokenizer_measurements_separate=True)
        body["qualification_provenance"] = "scripted_CPU_action_with_native_parser_not_target_model"
        response["raw_body"] = json.dumps(body, ensure_ascii=False)
        atomic_write(folder / "scripted-response.json", json_bytes(response))
        return response


def qualify(output, prior_model_plan):
    """Four complete finite controls with durable raw traces and explicit gates."""
    from transformers import AutoTokenizer

    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    source = code_identity()
    prior_model_plan = Path(prior_model_plan).resolve()
    prior = read_json(prior_model_plan)
    profile = prior["runtime_profile"]
    if (profile["max_context_tokens"] != CONTEXT or profile["max_output_tokens"] != OUTPUT
            or profile["chat_template_kwargs"].get("enable_thinking") is not False):
        raise ValueError("Qualification fixes the prior 16K / 2048 non-thinking model profile")
    model_path = Path(prior["model"])
    tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
    sources = {name: file_reference(model_path / name)
               for name in ("tokenizer.json", "tokenizer_config.json", "chat_template.jinja")
               if (model_path / name).is_file()}
    implementation = {str(path.relative_to(ROOT)): file_reference(path) for path in (
        Path(__file__).resolve(), ROOT / "tests/test_software_runtime_v028.py",
        ROOT / "tests/test_online_collection_v013.py", ROOT / "tests/test_software_collaboration_v027.py",
        ROOT / "src/proworksim/software_context_v028.py")}
    report = {
        "version": VERSION, "passed": False, "source": source, "model_calls": 0,
        "optimizer_updates": 0, "model_weights_loaded": False, "gpu_used": False,
        "max_context_tokens": CONTEXT, "max_output_tokens": OUTPUT,
        "minimum_required_margin_tokens": MINIMUM_MARGIN,
        "prior_model_plan": file_reference(prior_model_plan), "runtime_profile": copy.deepcopy(profile),
        "tokenizer_files": sources, "controls": [],
        "qualification_implementation": implementation,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "fixture_token_trace": "synthetic placeholder IDs/probabilities; measured tokenization saved separately",
        "scope": "Four known-code CPU/SDK reachability and tokenizer-margin controls; no model success, sampling, training support or learning-effect evidence.",
    }
    atomic_write(output / "qualification.json", json_bytes(report))
    for index, (case_id, first) in enumerate((case, member) for case in CASE_IDS for member in MEMBERS):
        folder = output / f"control-{index}"
        folder.mkdir()
        case = case_spec(case_id, first_member=first, role_decision_limits=dict.fromkeys(MEMBERS, 48))
        actions = successful_cpu_actions(case_id, first)
        atomic_write(folder / "scripted-actions.json", json_bytes(actions))
        window_id = f"v028-cpu-qualification-{index}"
        owner = QualifiedProgramOwner(actions, tokenizer=tokenizer, profile=profile,
                                       output=folder / "requests", window_id=window_id)
        spec = {"window_id": window_id, "harness": "openhands_v16", "usage": "interface_dev",
                "mode": "frozen_development", "min_class_count": 2,
                "budget": {"max_slots": 1, "max_model_calls": sum(case["role_decision_limits"].values())},
                "slots": [{"slot_id": f"control-{index}", "case_id": case_id,
                           "sampling_seed": 202610030000 + index, "first_member": first,
                           "role_decision_limits": case["role_decision_limits"]}]}
        entry = collect_software_window(owner, spec, folder / "window")[0]
        atomic_write(folder / "raw-sdk-requests.json", json_bytes(owner.requests))
        slot = folder / "window/slot-0"
        assessment = read_json(slot / "assessment.json")
        boundary = read_json(slot / "episode/manifest.json")["termination"]
        margin = min(row["remaining_context_after_output_reservation"] for row in owner.measurements)
        control = {
            "control_id": f"control-{index}", "case_id": case_id, "first_member": first,
            "case": case, "R": assessment["R"], "work_validity": entry["rollout"]["work_validity"]["value"],
            "role_call_counts": dict(owner.calls), "scripted_request_count": len(owner.requests),
            "native_measured_request_count": len(owner.measurements),
            "all_requests_measured": len(owner.requests) == len(owner.measurements),
            "max_prompt_tokens": max(row["prompt_tokens"] for row in owner.measurements),
            "max_program_output_tokens": max(row["program_output_tokens"] for row in owner.measurements),
            "minimum_remaining_margin_tokens": margin,
            "all_contexts_fit": all(row["fits_context"] for row in owner.measurements),
            "all_outputs_fit": all(row["program_output_within_limit"] for row in owner.measurements),
            "role_budgets_satisfied": all(owner.calls[m] <= case["role_decision_limits"][m] for m in MEMBERS),
            "boundary_status": boundary["status"], "actual_first_member": boundary["outcomes"][0]["worker_id"],
            "assessment": file_reference(slot / "assessment.json"),
            "episode_manifest": file_reference(slot / "episode/manifest.json"),
            "raw_experience": file_reference(slot / "experience.jsonl"),
            "raw_sdk_requests": file_reference(folder / "raw-sdk-requests.json"),
            "requests": copy.deepcopy(owner.measurements), "model_calls": 0,
        }
        control["passed"] = (control["R"] == 1 and control["work_validity"] is True
            and control["all_contexts_fit"] and control["all_outputs_fit"]
            and control["all_requests_measured"]
            and control["role_budgets_satisfied"] and margin >= MINIMUM_MARGIN
            and control["boundary_status"] == "workers_done" and control["actual_first_member"] == first)
        report["controls"].append(control)
        atomic_write(folder / "summary.json", json_bytes(control))
        atomic_write(output / "qualification.json", json_bytes(report))
    report.update(
        passed=all(row["passed"] for row in report["controls"]),
        scripted_request_count=sum(row["scripted_request_count"] for row in report["controls"]),
        max_prompt_tokens=max(row["max_prompt_tokens"] for row in report["controls"]),
        max_program_output_tokens=max(row["max_program_output_tokens"] for row in report["controls"]),
        minimum_remaining_margin_tokens=min(row["minimum_remaining_margin_tokens"] for row in report["controls"]),
        ended_at=datetime.now(timezone.utc).isoformat(), source_after=code_identity())
    report["source_unchanged_during_controls"] = (
        report["source_after"] == report["source"] and
        all(file_reference(ref["path"]) == ref for ref in implementation.values()))
    report["passed"] = report["passed"] and report["source_unchanged_during_controls"]
    atomic_write(output / "qualification.json", json_bytes(report))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--prior-model-plan", default="runs/domain-v0201-p1-9b/plan.json")
    args = parser.parse_args()
    report = qualify(args.output, args.prior_model_plan)
    print(json.dumps({key: report[key] for key in (
        "passed", "scripted_request_count", "model_calls", "max_prompt_tokens",
        "max_program_output_tokens", "minimum_remaining_margin_tokens",
        "source_unchanged_during_controls")}, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
