"""Freeze one synthetic task and three independent CPU programmed slots on an actual public tree."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from proworksim.software_benchmark_candidates_v054 import reference, write_new
from proworksim.software_benchmark_match_v054 import CONTRACT

ROOT = Path(__file__).resolve().parents[1]


def xml(name, arguments):
    parameters = "".join("<parameter=" + key + ">" + (
        value if isinstance(value, str) else json.dumps(value)) + "</parameter>"
        for key, value in arguments.items())
    return "<tool_call>\n<function=" + name + ">\n" + parameters + "\n</function>\n</tool_call>"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rootfs-environment", type=Path, required=True)
    parser.add_argument("--environment", type=Path, required=True)
    parser.add_argument("--baseline-mapping", type=Path, required=True)
    parser.add_argument("--scorer-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    environment = json.loads(args.environment.read_text())
    task = {**environment["task"], "problem_statement": (
        "Synthetic preparation only, not a benchmark problem or capability result. "
        "Create pws_preparation_probe.py containing exactly VALUE = 1 without a trailing newline. "
        "Run the public Python check that imports astropy and verifies that exact content. "
        "For the managed interface, complete the same-version public test, fixed patch and legal submission, "
        "then finish. For native tools, finish after that public check. Do not change other files.")}
    interpreter = environment["public_python"]
    statement = "import astropy; from pathlib import Path; assert Path('pws_preparation_probe.py').read_text() == 'VALUE = 1'; print('synthetic-public-check-ok')"
    entry = {"source": "public_repository", "admitted": True, "cwd": "/testbed",
             "argv": [interpreter, "-c", statement], "synthetic_preparation_only": True,
             "hidden_material_used": False}
    import shlex
    native_actions = [
        ("file_editor", {"command": "create", "path": "/testbed/pws_preparation_probe.py", "file_text": "VALUE = 1"}),
        ("terminal", {"command": " ".join(shlex.quote(value) for value in entry["argv"]), "timeout": 30}),
        ("finish", {"message": "Synthetic public check completed."}),
    ]
    project_actions = [
        ("create_file", {"path": "pws_preparation_probe.py", "text": "VALUE = 1"}),
        ("run_tests", {}), ("fix_patch", {"task_ids": [], "message": "Synthetic tested version."}),
        ("submit_integration", {"message": "Synthetic preparation delivery."}),
        ("staff_done", {"reason": "Synthetic preparation completed."}),
    ]
    seed = 202610210054
    slots = write_new(output / "synthetic-slots.json", {"formal_execution_authorized": False, "slots": [
        {"slot_id": "synthetic-" + arm + "-" + output.name, "instance_id": task["instance_id"],
         "arm": arm, "seed": seed, "execution_authorized": False} for arm in ("REF", "MATCH", "PROJECT")]})
    contract = write_new(output / "contract.json", CONTRACT)
    model_path = ROOT / "runs/assets/models/Qwen3.5-9B-c20223623576"
    cpu = ["/data0/zhuxinrui/proworksim-runtime/run-cpu.sh", "--write-project", "/usr/bin/env",
           "CUDA_VISIBLE_DEVICES=", "NVIDIA_VISIBLE_DEVICES=void", "HF_HUB_OFFLINE=1",
           "TRANSFORMERS_OFFLINE=1", "LITELLM_LOCAL_MODEL_COST_MAP=True",
           "PYTHONPATH=" + str(ROOT / "src"),
           str(ROOT / "runs/v016-sdk/resident-venv/bin/python"), "-B"]
    official_inventory = json.loads((ROOT / "runs/software-benchmark-v054/images/preparation-r1/image-inventory.json").read_text())
    official_image = next(row for row in official_inventory["images"] if row["instance_id"] == task["instance_id"])
    base = {"docker_socket": str(ROOT / "runs/software-panel-v053/docker/docker.sock"),
            "docker_cli": reference(ROOT / "runs/software-benchmark-v054/scorer-venv/bin/docker"),
            "scorer_manifest": reference(args.scorer_manifest), "baseline_mapping": reference(args.baseline_mapping),
            "image": official_image,
            "dataset": {"path": str(ROOT / "artifacts/software-benchmark-v054/source/trusted-evaluation.json"),
                        "bytes": 9795256, "sha256": "bdd44ad7182b9cb9dd8d679fbdf119b4372e925f3c08c5a30178db818284cfbb"},
            "limits": {"network_mode": "none", "nano_cpus": 4000000000, "memory_bytes": 17179869184,
                       "pids_limit": 16384, "timeout_seconds": 1800},
            "trusted_output_root": str(output / "official-output")}
    configs = []
    for arm in ("REF", "MATCH", "PROJECT"):
        run = output / arm
        actions = project_actions if arm == "PROJECT" else native_actions
        responses = [{"role": "assistant", "content": "", "tool_calls": [{
            "id": "scripted-" + str(index), "type": "function", "function": {
                "name": name, "arguments": json.dumps(arguments)}}]}
            for index, (name, arguments) in enumerate(actions)] if arm == "REF" else [
                xml(name, arguments) for name, arguments in actions]
        response_ref = write_new(output / (arm + "-responses.json"), responses)
        owner_admission = write_new(output / (arm + "-owner-admission.json"), {
            "programmed_fixture_only": True, "model_calls": 0, "GPU_opens": 0,
            "formal_execution_authorized": False, "responses": response_ref})
        condition = write_new(output / (arm + "-condition.json"), {
            "arm": arm, "seed": seed, "preparation_only": True, "public_task": task,
            "responses": response_ref, "baseline_mapping": reference(args.baseline_mapping)})
        config = {"arm": arm, "seed": seed, "preparation_only": True,
                  "slot_id": "synthetic-" + arm + "-" + output.name, "slots": slots,
                  "configuration": condition, "environment": reference(args.environment),
                  "owner_admission": owner_admission, "public_task": task,
                  "rootfs_environment": str(args.rootfs_environment.resolve()),
                  "stdlib": str(ROOT / "runs/software-benchmark-v054/native-binding-control/r3/REF/control-stdlib"),
                  "sdk_runtime": str(ROOT / "runs/software-benchmark-v054/native-binding-control/r3/sdk-runtime"),
                  "dataset_revision": "78f471bf655a3137b2e8a75af1501690ec009ec3",
                  "model_local": str(model_path), "public_test_entry": entry, "scorer_request_base": base,
                  "model_identity": str(run / "model-identity.json"),
                  "model_ready": str(run / "model-service/service-ready.json"),
                  "model_socket": str(run / "owner.sock")}
        if arm == "REF":
            identity = write_new(output / "REF-identity.json", {"programmed_fixture": True})
            config.update(model_identity=identity["path"], model_ready=str(run / "ref-ready.json"),
                          ref_endpoint="http://127.0.0.1:18055", model_command=[*cpu,
                str(ROOT / "tools/serve_scripted_ref_v054.py"), "--port", "18055", "--model-local", str(model_path),
                "--responses", response_ref["path"], "--ready", str(run / "ref-ready.json")])
        else:
            config["model_command"] = [*cpu, str(ROOT / "tools/serve_benchmark_owner_v054.py"),
                "--socket", config["model_socket"], "--model-local", str(model_path),
                "--model-manifest", str(model_path / "proworksim-manifest.json"),
                "--contract", contract["path"], "--output", str(run / "model-service"),
                "--identity-output", config["model_identity"], "--scripted-responses", response_ref["path"]]
        configs.append(write_new(output / (arm + "-runner.json"), config))
    print(json.dumps({"configs": configs, "slots": slots, "actual_dataset_results": 0}))


if __name__ == "__main__":
    main()
