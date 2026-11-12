"""Explicit future bundle selection; never starts or resumes an experiment."""
from __future__ import annotations

import json

from . import software_benchmark_sdk_bundle_v066 as original
from .software_benchmark_expansion_episode_v069 import clone_namespace

VERSION = 'v105-flash-nonthinking-paired-interface-bundle-r1'
OUTPUT = original.ROOT / 'runs/software-benchmark-v105/sdk-bundle-r1'
NEW_MODULES = (
    'software_benchmark_deepseek_contract_v105.py',
    'software_benchmark_deepseek_adapter_v105.py', 'software_benchmark_managed_v105.py',
    'software_benchmark_managed_actor_v103.py', 'software_benchmark_managed_v103.py',
    'software_benchmark_managed_v096.py', 'software_benchmark_managed_sync_v095.py',
    'software_benchmark_nullable_cursor_v090.py', 'software_benchmark_budget_closure_v103.py',
)
NEW_TOOLS = ('run_ref_controller_v105.py', 'run_project_controller_v105.py', 'run_managed_worker_docker_v103.py')
_namespace = clone_namespace(original, VERSION=VERSION, OUTPUT=OUTPUT, __file__=__file__,
    PROJECT_MODULES=tuple(sorted(set(original.PROJECT_MODULES) | set(NEW_MODULES))),
    TOOLS=original.TOOLS + NEW_TOOLS,
    ENTRYPOINT_ALIASES={**original.ENTRYPOINT_ALIASES,
        'managed-worker.py': 'run_managed_worker_docker_v103.py',
        'controller.py': 'run_ref_controller_v105.py',
        'project-controller.py': 'run_project_controller_v105.py'})


def probe_source():
    value = original.probe_source()
    for before, after in (
        ('tool_module("run_ref_controller_v066")', 'tool_module("run_ref_controller_v105")'),
        ('tool_module("run_project_controller_v066")', 'tool_module("run_project_controller_v105")'),
        ('tool_module("run_managed_worker_docker_v066")', 'tool_module("run_managed_worker_docker_v103")'),
        ('from proworksim.software_benchmark_managed_v064 import worker_type',
         'from proworksim.software_benchmark_managed_v105 import worker_type'),
        ('from proworksim.software_benchmark_managed_actor_v064 import validate_public_entry',
         'from proworksim.software_benchmark_managed_actor_v103 import validate_public_entry'),
    ):
        if before not in value:
            raise ValueError('Original bundle probe boundary changed: ' + before)
        value = value.replace(before, after)
    return value


_namespace['probe_source'] = probe_source
prepare_bundle = _namespace['prepare_bundle']
runtime_environment = _namespace['runtime_environment']
python_argv = _namespace['python_argv']



checked, digest, json_bytes = original.checked, original.digest, original.json_bytes


def controller_inputs(host_config, row, ready, model_identity, endpoint, *, diagnostic=False,
                      public_context=None, public_environment=None, public_test_entry=None,
                      file_policy=None, gitlinks=None):
    """Project public task/runtime fields; evaluator references and keys stay host-side."""
    condition_raw = checked(host_config["configuration"]).read_bytes()
    from .software_benchmark_deepseek_contract_v105 import validate_condition
    validate_condition(json.loads(condition_raw))
    if diagnostic:
        if model_identity:
            raise ValueError("Zero-model diagnostics cannot acquire a model service identity")
    elif model_identity.get("thinking") is not False:
        raise ValueError("Only the qualified non-thinking model route is allowed")
    arm = row.get("arm", row.get("execution_arm"))
    if (not row["slot_id"].startswith("v105:") or arm not in {"REF", "PROJECT"}
            or row.get("execution_arm", arm) != arm or row.get("model_key") != "DEEPSEEK"
            or any(host_config.get(key) != row[key] for key in
                   ("slot_id", "seed", "source_slot_id", "condition_id"))):
        raise ValueError("Controller inputs require one exact v105 non-thinking paired slot")
    public = host_config["public_task"]
    safe_identity = {key: model_identity[key] for key in (
        "model", "model_key", "model_revision", "documented_model_version", "vllm_version", "raw_release",
        "adapter_sha256", "model_manifest_sha256", "context_limit", "max_output_tokens",
        "service_admission_complete", "port", "deployment_version", "thinking",
        "provider_model_alias", "provider_weight_revision_pinnable") if key in model_identity}
    config = {"version": "v064-private-native-controller-r1" if arm == "REF" else "v064-private-project-controller-r1",
        "slot_id": row["slot_id"], "source_slot_id": row["source_slot_id"], "seed": row["seed"],
        "condition_id": row["condition_id"], "execution_arm": arm, "model_key": row["model_key"],
        "configuration": {"path": "/pws/control/condition.json", "sha256": digest(condition_raw), "bytes": len(condition_raw)},
        "public_task": {key: public[key] for key in ("instance_id", "repo", "base_commit", "problem_statement")},
        "ref_endpoint": endpoint, "model_identity_value": safe_identity, "output": "/pws/output",
        "start": "/pws/control/start.json", "ready": "/pws/control/actor-ready.json",
        "diagnostic": bool(diagnostic),
        "measurement_kind": "zero_model_diagnostic" if diagnostic else "full_verified_comparison"}
    from .software_benchmark_public_context_v062 import VERSION as CONTEXT_VERSION, terminal_initialization_action
    if (not isinstance(public_context, dict) or public_context.get("version") != CONTEXT_VERSION
            or public_context.get("instance_id") != row["instance_id"]):
        raise ValueError("Both conditions require the admitted public execution context")
    terminal_initialization_action(public_environment)
    config["public_context"] = {key: public_context[key] for key in ("version", "visible_text", "visible_facts")}
    config["public_environment"] = {key: public_environment[key] for key in
                                   ("kind", "image_id", "source_config_sha256", "public_python")}
    config["public_environment"]["environment"] = {key: public_environment["environment"][key]
        for key in ("PATH", "CONDA_PREFIX", "CONDA_DEFAULT_ENV") if key in public_environment["environment"]}
    if arm == "PROJECT":
        from .repository_sources_v054 import normalize_policy
        entry = public_test_entry if public_test_entry is not None else host_config["public_test_entry"]
        if (entry.get("instance_id") != row["instance_id"] or entry.get("hidden_material_used") is not False
                or entry.get("cwd") != "/testbed" or type(entry.get("timeout_seconds")) is not int
                or not 1 <= entry["timeout_seconds"] <= 1800
                or not isinstance(entry.get("argv"), list) or not entry["argv"]
                or entry["argv"][0] != public_environment["public_python"]):
            raise ValueError("PROJECT requires an explicit public-only fixed test command and timeout")
        config["public_test_entry"] = {
            "version": "v064-repository-public-test-entry-r1", "instance_id": row["instance_id"],
            "argv": entry["argv"], "cwd": "/testbed", "timeout_seconds": entry["timeout_seconds"],
            "hidden_material_used": False}
        config["file_policy"] = normalize_policy(file_policy if file_policy is not None else host_config.get("file_policy"))
        config["dataset_revision"] = host_config["dataset_revision"]
        config["gitlinks"] = gitlinks if gitlinks is not None else host_config.get("gitlinks", [])
    return {"condition.json": condition_raw, "actor-ready.json": json_bytes(ready),
            "controller-config.json": json_bytes(config)}

