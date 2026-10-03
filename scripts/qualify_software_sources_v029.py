"""CPU qualification of new-source SDK requests and one exact eight-slot context.

Loads only the pinned local tokenizer. Explicit scripted responses exercise real
SDK tools; no model weights, logits, generation, training targets or GPU are used.
Token lengths cover initial requests, a largest-character 180-line source read,
and a bounded diff after deliberately overwriting a large module. They are
finite controls, not a guarantee for all possible future actor inputs.
"""
import argparse
from collections import Counter
import copy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
os.environ["CUDA_VISIBLE_DEVICES"] = ""
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
os.environ.setdefault("OPENHANDS_SUPPRESS_BANNER", "1")

from proworksim.audit import code_identity  # noqa: E402
from proworksim.deterministic_work_v024 import DeterministicCandidateActor  # noqa: E402
from proworksim.online_support import declare_window  # noqa: E402
from proworksim.software_collaboration_v029 import (  # noqa: E402
    CASE_IDS, MEMBERS, build_software_collaboration_case, case_spec,
)
from proworksim.software_context_v028 import (  # noqa: E402
    VERSION as CONTEXT_POLICY, project_software_request,
)
from proworksim.software_runtime_v029 import (  # noqa: E402
    MAPPER, build_runtime, close_runtime, run_fragment, situation_id,
)
from proworksim.storage import atomic_write, digest, json_bytes, read_json  # noqa: E402

VERSION = "software-source-sdk-tokenizer-qualification-v0.29"
CONTEXT = 16384
OUTPUT = 2048
MINIMUM_MARGIN = 1024


def reference(path):
    path = Path(path).resolve()
    return {"path": str(path), "sha256": digest(path.read_bytes())}


def _identity():
    return {"version": "shared-actor-identity-v0.13", "policy_version": "explicit-v029-CPU-qualification",
            "adapter_sha256": digest(b"CPU-no-adapter"), "base_manifest_sha256": digest(b"CPU-no-weights"),
            "inference_profile_sha256": digest(b"CPU-sdk-contract-only")}


class ConstructionOwner:
    recipe = {"temperature": 0.7, "max_output_tokens": OUTPUT, "max_length": CONTEXT}
    software_context_policy = CONTEXT_POLICY

    @property
    def transport(self):
        return self

    def freeze_identity(self):
        return _identity()

    def complete(self, *_, **__):
        raise RuntimeError("No transport request allowed during construction")


def preconstruction_control(output):
    """Build eight independent worlds and sixteen SDK conversations, no actions."""
    owner, runtimes, slots, rows = ConstructionOwner(), [], [], []
    output.mkdir(parents=True, exist_ok=False)
    try:
        for index in range(8):
            folder = output / f"slot-{index}"
            prepared = build_software_collaboration_case(case_spec(CASE_IDS[0]), folder)
            runtime, captures, _ = build_runtime(owner, prepared, folder)
            runtimes.append(runtime)
            initial = {"case": prepared.case, "reward_spec": prepared.reward_spec,
                       "initial_business_sha256": prepared.prefix["prepared_business_state_sha256"]}
            slots.append({"slot_id": f"support-{index}", "xi_id": situation_id(prepared.case),
                          "xi_fingerprint": digest(json_bytes(initial)), "active_members": list(MEMBERS),
                          "policies": runtime.policy_identities, "mapping_spec_id": MAPPER})
            rows.append({"folder": str(folder), "instance_id": prepared.world.state["instance_id"],
                         "business_sha256": prepared.prefix["prepared_business_state_sha256"],
                         "event_count": len(runtime.recorder.events),
                         "capture_count": sum(map(len, captures.values()))})
        declaration = declare_window("CPU-eight-context-control", actor_identity=owner.freeze_identity(),
            gamma_identity={"harness": "openhands_v16", "cpu_qualification": True}, slot_specs=slots)
        report = {"kind": "CPU_real_SDK_preconstruction_only", "model_calls": 0, "slot_count": len(slots),
                  "unique_xi_fingerprints": len({row["xi_fingerprint"] for row in slots}),
                  "unique_team_policy_fingerprints": len({row["window"]["team_policy_fingerprint"]
                                                          for row in declaration["slots"]}),
                  "unique_instance_ids": len({row["instance_id"] for row in rows}), "roots": rows}
        report["passed"] = (report["unique_xi_fingerprints"] == report["unique_team_policy_fingerprints"] == 1
                            and report["unique_instance_ids"] == 8
                            and all(row["event_count"] == row["capture_count"] == 0 for row in rows))
        atomic_write(output / "declaration.json", json_bytes(declaration))
        atomic_write(output / "summary.json", json_bytes(report))
        return report
    finally:
        for runtime in runtimes:
            close_runtime(runtime)


def native_xml(name, arguments):
    parameters = "\n".join("<parameter=" + key + ">\n" + (
        value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)) + "\n</parameter>"
        for key, value in arguments.items())
    return "<tool_call>\n<function=" + name + ">\n" + parameters + "\n</function>\n</tool_call><|im_end|>"


class MeasurementOwner(ConstructionOwner):
    """Explicit CPU response program; omits token_trace so it cannot train."""
    def __init__(self, renderer, scripts, output, window_id):
        self.renderer, self.scripts, self.output = renderer, scripts, output
        self.window_id, self.calls, self.measurements = window_id, Counter(), []
        output.mkdir(parents=True, exist_ok=False)

    def complete(self, request, **_):
        observations = [json.loads(message["content"])["observation"] for message in request["messages"]
                        if message["role"] == "user" and "observation" in json.loads(message["content"])]
        member = observations[-1]["actor_id"]
        phase, name, arguments = self.scripts[member][self.calls[member]]
        self.calls[member] += 1
        folder = self.output / f"request-{len(self.measurements):03d}"
        folder.mkdir()
        selected, projection = project_software_request(request, render=self.renderer.prepare_request,
            tokenizer=self.renderer.tokenizer, context_limit=CONTEXT)
        rendered, normalized, native_projection = self.renderer.prepare_request(selected)
        token_ids = self.renderer.tokenizer(rendered, add_special_tokens=False)["input_ids"]
        wire = native_xml(name, arguments)
        output_ids = self.renderer.tokenizer(wire, add_special_tokens=False)["input_ids"]
        parsed, error = self.renderer.parse_response(wire, selected)
        if error or (parsed["tool_calls"][0]["function"]["name"] != name
                     or json.loads(parsed["tool_calls"][0]["function"]["arguments"]) != arguments):
            raise ValueError("CPU action native-codec roundtrip changed its scripted arguments")
        for filename, value in (("original-request.json", request), ("selected-request.json", selected),
                                ("projection.json", projection), ("normalized-messages.json", normalized),
                                ("native-projection.json", native_projection), ("input-ids.json", token_ids),
                                ("scripted-output-ids.json", output_ids)):
            atomic_write(folder / filename, json_bytes(value))
        atomic_write(folder / "rendered-prompt.txt", rendered.encode())
        atomic_write(folder / "scripted-output.xml", wire.encode())
        margin = CONTEXT - OUTPUT - len(token_ids)
        measurement = {"member": member, "phase": phase, "scripted_action": name,
                       "prompt_tokens": len(token_ids), "reserved_output_tokens": OUTPUT,
                       "remaining_context_after_output_reservation": margin,
                       "fits_context": projection["fits"], "removed_indices": projection["removed_indices"],
                       "original_prompt_tokens": projection["original_prompt_tokens"],
                       "scripted_output_tokens": len(output_ids), "native_codec_roundtrip": True,
                       "request": reference(folder / "original-request.json"),
                       "projection": reference(folder / "projection.json"),
                       "measured_input_ids": reference(folder / "input-ids.json"),
                       "scope": "Actual SDK request; local tokenizer only; scripted response not model output"}
        self.measurements.append(measurement)
        atomic_write(folder / "measurement.json", json_bytes(measurement))
        if not projection["fits"]:
            raise ValueError("Finite new-source control exceeded the declared context; inspect preserved request")
        body = {"id": self.window_id + "-" + member + "-" + str(self.calls[member]),
                "model": "explicit-CPU-response-program", "system_fingerprint": self.freeze_identity()["policy_version"],
                "actor_identity": self.freeze_identity(), "online_window_id": self.window_id,
                "choices": [{"message": parsed, "finish_reason": "tool_calls"}],
                "usage": {"prompt_tokens": len(token_ids), "completion_tokens": len(output_ids),
                          "total_tokens": len(token_ids) + len(output_ids)},
                "qualification_provenance": "CPU_scripted_response_no_model_no_logits_no_training_token_trace"}
        envelope = {"http_status": 200, "body": body, "raw_body": json_bytes(body).decode()}
        atomic_write(folder / "scripted-response.json", json_bytes(envelope))
        return envelope


def largest_read(files, paths):
    """Freeze largest character count among every legal 180-line library page."""
    candidates = []
    for path in paths:
        if path in {"consumer.py", "test_member.py"}:
            continue
        lines = files[path].splitlines()
        for start in range(len(lines)):
            candidates.append((len("\n".join(lines[start:start + 180])), path, start + 1))
    size, path, start = max(candidates)
    return {"path": path, "start_line": start, "max_lines": 180}, size


def source_request_control(output, task_id, renderer):
    prepared = build_software_collaboration_case(case_spec(task_id), output / "case")
    files = prepared.world._bundle(MEMBERS[0])[2]["files"]
    read, chars = largest_read(files, prepared.case["editable_paths"])
    # A deliberate short overwrite produces a large cumulative diff through the
    # real managed edit tool. It is a stress fixture, never an attempted repair.
    library_path = max((path for path in prepared.case["editable_paths"] if "/" in path),
                       key=lambda path: len(files[path]))
    scripts = {
        MEMBERS[0]: [("initial", "read_file", read),
                     ("after_largest_180_line_read", "write_file", {"path": library_path,
                        "text": "# Explicit CPU-only large-diff stress overwrite; not a solution.\n"}),
                     ("after_short_overwrite", "diff_workspace", {"max_chars": 6000}),
                     ("after_bounded_6000_char_diff", "staff_done", {"reason": "CPU tokenizer control complete"})],
        MEMBERS[1]: [("initial_other_member", "staff_done", {"reason": "CPU tokenizer control only"})],
    }
    owner = MeasurementOwner(renderer, scripts, output / "requests", "CPU-" + task_id)
    runtime, captured, _ = build_runtime(owner, prepared, output / "case")
    try:
        boundary = run_fragment(prepared, runtime)
        atomic_write(output / "scripted-actions.json", json_bytes(scripts))
        atomic_write(output / "boundary.json", json_bytes(boundary))
        atomic_write(output / "captures.json", json_bytes(captured))
        atomic_write(output / "experience.json", json_bytes(runtime.recorder.snapshot()))
        diffs = [event["payload"]["response"]["result"] for event in captured[MEMBERS[0]]
                 if event["kind"] == "tool_call" and event["payload"]["action"] == "diff_workspace"
                 and event["payload"]["response"].get("ok")]
        reads = [event["payload"]["response"] for event in captured[MEMBERS[0]]
                 if event["kind"] == "tool_call" and event["payload"]["action"] == "read_file"]
        report = {"task_id": task_id, "kind": "CPU_source_read_and_paged_diff_stress",
                  "model_calls": 0, "scripted_sdk_transport_calls": len(owner.measurements),
                  "read_arguments": read, "largest_selected_read_characters": chars,
                  "stress_overwrite_path": library_path, "measurements": owner.measurements,
                  "minimum_remaining_margin_tokens": min(row["remaining_context_after_output_reservation"]
                                                         for row in owner.measurements),
                  "boundary_status": boundary["status"],
                  "diff_total_chars": diffs[0]["total_chars"] if diffs else None,
                  "diff_page_chars": len(diffs[0]["diff"]) if diffs else None,
                  "read_executed": len(reads) == 1 and reads[0].get("ok") is True,
                  "scope": "Finite read/overwrite/page sequences, not maximum future-context proof or business success"}
        report["passed"] = (len(owner.measurements) == 5 and boundary["status"] == "workers_done"
            and report["read_executed"] and len(diffs) == 1 and len(diffs[0]["diff"]) == 6000
            and diffs[0]["has_more"] and report["minimum_remaining_margin_tokens"] >= MINIMUM_MARGIN
            and all(row["fits_context"] and row["scripted_output_tokens"] <= OUTPUT for row in owner.measurements))
        atomic_write(output / "summary.json", json_bytes(report))
        return report
    finally:
        close_runtime(runtime)


def qualify(output, prior_model_plan):
    from transformers import AutoTokenizer

    output, prior_path = Path(output).resolve(), Path(prior_model_plan).resolve()
    output.mkdir(parents=True, exist_ok=False)
    prior = read_json(prior_path)
    profile = prior["runtime_profile"]
    if (profile["max_context_tokens"] != CONTEXT or profile["max_output_tokens"] != OUTPUT
            or profile["chat_template_kwargs"].get("enable_thinking") is not False):
        raise ValueError("Qualification fixes the 16384/2048 non-thinking model profile")
    tokenizer_root = Path(prior["model"])
    renderer = object.__new__(DeterministicCandidateActor)
    renderer.tokenizer = AutoTokenizer.from_pretrained(tokenizer_root, local_files_only=True)
    renderer.inference_profile = copy.deepcopy(profile)
    report = {"version": VERSION, "source": code_identity(), "passed": False,
              "model_calls": 0, "model_weights_loaded": False, "gpu_used": False, "optimizer_updates": 0,
              "started_at": datetime.now(timezone.utc).isoformat(),
              "context_policy": CONTEXT_POLICY, "max_context_tokens": CONTEXT, "max_output_tokens": OUTPUT,
              "minimum_required_margin_tokens": MINIMUM_MARGIN, "prior_model_plan": reference(prior_path),
              "runtime_profile": copy.deepcopy(profile), "controls": [],
              "tokenizer_files": {name: reference(tokenizer_root / name) for name in (
                  "tokenizer.json", "tokenizer_config.json", "chat_template.jinja")},
              "qualification_implementation": {str(path.relative_to(ROOT)): reference(path) for path in (
                  Path(__file__).resolve(), ROOT / "src/proworksim/software_runtime_v029.py",
                  ROOT / "src/proworksim/software_collaboration_v029.py",
                  ROOT / "src/proworksim/software_context_v028.py")},
              "scope": "Finite CPU SDK/tokenizer controls only; no current-policy support, model ability or training-effect claim"}
    atomic_write(output / "qualification.json", json_bytes(report))
    try:
        report["preconstruction"] = preconstruction_control(output / "preconstruction")
        for task_id in CASE_IDS:
            report["controls"].append(source_request_control(output / task_id, task_id, renderer))
            atomic_write(output / "qualification.json", json_bytes(report))
        report["source_after"] = code_identity()
        report["passed"] = (report["source_after"] == report["source"] and report["preconstruction"]["passed"]
                            and all(row["passed"] for row in report["controls"]))
    except BaseException as error:
        report["error"] = {"type": type(error).__name__, "message": str(error)}
        raise
    finally:
        report["ended_at"] = datetime.now(timezone.utc).isoformat()
        atomic_write(output / "qualification.json", json_bytes(report))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--prior-model-plan", required=True, type=Path)
    args = parser.parse_args()
    report = qualify(args.output, args.prior_model_plan)
    print(json.dumps({"passed": report["passed"], "model_calls": 0,
                      "controls": [{"task_id": row["task_id"], "passed": row["passed"],
                                    "minimum_remaining_margin_tokens": row["minimum_remaining_margin_tokens"]}
                                   for row in report["controls"]]}, ensure_ascii=False))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
