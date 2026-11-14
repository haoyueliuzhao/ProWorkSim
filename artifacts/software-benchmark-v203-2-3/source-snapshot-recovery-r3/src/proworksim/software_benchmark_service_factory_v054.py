"""Fixed model-service argv builders. Dynamic capacity evidence is never synthesized."""
from __future__ import annotations

import json
from pathlib import Path
import re
import secrets
import os

from .software_benchmark_candidates_v054 import checked, reference, write_new
from .software_benchmark_match_v054 import CONTRACT
from .software_benchmark_deployment_gpu_v054 import validate_card_identity
from .software_benchmark_resident_pool_v054 import declared_session_capacity, validate_registration
from .storage import digest, json_bytes

ROOT = Path(__file__).resolve().parents[2]
MODEL = ROOT / "runs/assets/models/Qwen3.5-9B-c20223623576"
VERSION = "v054-formal-service-factory-v1"
CAPACITY_ADMISSION = ROOT / "artifacts/software-benchmark-v054/native-environment/model-capacity-admission.json"


def capacity_admission(arm, capacity_reference):
    admission_ref = reference(CAPACITY_ADMISSION)
    admission = json.loads(checked(admission_ref).read_text())
    mode = "REF" if arm == "REF" else "MATCH"
    record = admission["admitted_modes"][mode]
    capacity = json.loads(checked(capacity_reference).read_text())
    if (admission.get("version") != "v054-model-capacity-admission-v1"
            or record["capacity_receipt"] != capacity_reference
            or capacity.get("status") != "capacity_and_synthetic_accounting_passed"
            or capacity.get("arm") != mode
            or capacity.get("source", {}).get("model_manifest") != reference(MODEL / "proworksim-manifest.json")
            or capacity.get("source_seal") != record["source_seal"]):
        raise ValueError("The independent actual per-mode capacity admission differs")
    sealed = json.loads(checked(record["source_seal"]).read_text())
    if sealed.get("match_contract") != CONTRACT:
        raise ValueError("Capacity evidence used a different original owner numerical contract")
    current_ref = json.loads((ROOT / "config/v054-ref-service.json").read_text())
    if sealed.get("ref_config") != current_ref:
        raise ValueError("Capacity evidence used a different REF service configuration")
    # Operational monitor revisions may differ; the numerical implementation and
    # actual runtime scripts imported by the solver must remain the qualified ones.
    relevant = {ROOT / name for name in (
        "src/proworksim/software_benchmark_owner_ipc_v054.py",
        "src/proworksim/software_benchmark_match_v054.py",
        "src/proworksim/software_calibration_runtime_v051.py",
        "src/proworksim/candidate_runtime_v020.py",
        "src/proworksim/software_panel_resources_v053.py",
        "tools/serve_benchmark_owner_v054.py", "tools/run_benchmark_runtime_v054.sh",
        "tools/enter_benchmark_runtime_v054.sh", "scripts/run_ne_v021.py")}
    if arm == "REF":
        relevant.update({ROOT / "tools/run_ref_preparation_v054.sh",
                         ROOT / "tools/start_ref_capacity_server_v054.py"})
    frozen = {Path(item["path"]): item for item in sealed["files"]}
    if not relevant <= set(frozen):
        raise ValueError("Capacity evidence lacks the actual solver numerical/runtime sources")
    for path in relevant:
        checked(frozen[path])
    runtime = record["runtime_environment"]
    expected = {"PYTHONPATH": str(ROOT / "src") + ":" + str(ROOT),
                "PYTORCH_CUDA_ALLOC_CONF": "backend:native"}
    if arm == "REF":
        expected["TRITON_LIBCUDA_PATH"] = "/opt/host-nvidia"
        expected["CUDA_HOME"] = "/usr/local/cuda-13.0"
    if any(runtime.get(key) != value for key, value in expected.items()):
        raise ValueError("Formal runtime differs from the capacity-qualified environment")
    return admission_ref


def validate_service(service, arm):
    if service.get("deployment_mode") == "resident-session-v1":
        return validate_resident_session_service(service, arm)
    if (service.get("factory_version") != VERSION or service.get("arm") != arm
            or service.get("condition") != condition_reference(arm)
            or service.get("factory_source") != reference(__file__)
            or service.get("admission_passed") is not True):
        raise ValueError("Only this fixed admitted service factory may supply an episode")
    spec_path = checked(service["service_spec"])
    spec = json.loads(spec_path.read_text())
    declaration = spec_path.parent / "model-service.json"
    if json.loads(declaration.read_text()) != service:
        raise ValueError("Caller service differs from the complete frozen declaration")
    capacity = json.loads(checked(service["capacity_receipt"]).read_text())
    if service.get("capacity_admission") != capacity_admission(arm, service["capacity_receipt"]):
        raise ValueError("The per-mode capacity admission changed")
    if (capacity.get("status") != "capacity_and_synthetic_accounting_passed"
            or capacity.get("arm") != ("REF" if arm == "REF" else "MATCH")
            or spec["condition"] != service["condition"]
            or spec["capacity_receipt"] != service["capacity_receipt"]
            or spec["card"]["uuid"] != service["gpu_uuid"]
            or service["command"][1:] != [str(ROOT / "tools/run_formal_model_service_v054.py"),
                "--spec", str(spec_path), "--spec-sha256", service["service_spec"]["sha256"]]):
        raise ValueError("Service capacity/condition/deployment identity differs")
    return reference(declaration)


def condition_reference(arm):
    if arm not in {"REF", "MATCH", "PROJECT"}:
        raise ValueError("Unknown frozen condition")
    return reference(ROOT / ("config/v054-condition-" + arm + ".json"))


def ref_arguments():
    return ["serve", str(MODEL), "--host", "127.0.0.1", "--port", "18054",
            "--served-model-name", "raw-qwen3.5-9b-v054-ref", "--tensor-parallel-size", "1",
            "--dtype", "bfloat16", "--gpu-memory-utilization", "0.8", "--max-model-len", "131072",
            "--max-num-seqs", "1", "--no-enable-prefix-caching", "--generation-config", "vllm",
            "--language-model-only", "--enable-auto-tool-choice", "--tool-call-parser", "qwen3_coder",
            "--reasoning-parser", "qwen3"]


def templates():
    return {"version": VERSION, "conditions": {arm: condition_reference(arm) for arm in
            ("REF", "MATCH", "PROJECT")}, "REF": {"argv": ref_arguments(),
            "endpoint": "http://127.0.0.1:18054", "maximum_REF_residents": 1,
            "singleton_lock": "runs/v054-gpu/locks/ref-port-18054.lock",
            "authentication": "new owner-only API key per service; authenticated exact transport",
            "occupied_port": "fail before loading; never attach to another service"},
            "MATCH_PROJECT": {"entrypoint": "tools/serve_formal_owner_v054.py",
                "contract": CONTRACT, "capacity_smoke_only": False,
                "MATCH_codec": "separate pinned CPU codec child in the same model service scope",
                "numerical_path": "original raw CalibrationActor plus shared r3/r5 cache protocol"},
            "dynamic_inputs_required": ["actual passed capacity receipt", "observed GPU card",
                "per-slot fresh output paths", "separate formal execution/budget permit"],
            "maximum_global_residents": 8, "model_loads": 0, "formal_execution_authorized": False}


def build_service(*, arm, capacity_reference, card, directory, resident_reference=None,
                  registration_reference=None, pool_policy_reference=None):
    if resident_reference is not None:
        return build_resident_session_service(arm=arm, capacity_reference=capacity_reference,
            card=card, directory=directory, resident_reference=resident_reference,
            registration_reference=registration_reference, pool_policy_reference=pool_policy_reference)
    if registration_reference is not None or pool_policy_reference is not None:
        raise ValueError('Dynamic pool execution requires an admitted persistent resident')
    admitted_capacity = capacity_admission(arm, capacity_reference)
    capacity = json.loads(checked(capacity_reference).read_text())
    mode = "REF" if arm == "REF" else "MATCH"
    if (capacity.get("status") != "capacity_and_synthetic_accounting_passed"
            or capacity.get("arm") != mode
            or capacity.get("source", {}).get("model_manifest") != reference(MODEL / "proworksim-manifest.json")):
        raise ValueError("A real passed capacity receipt for this unchanged numerical mode is required")
    if (not re.fullmatch(r"GPU-[0-9a-fA-F-]{36}", card["uuid"])
            or type(card["index"]) is not int or not 0 <= card["index"] < 8):
        raise ValueError("An observed physical GPU binding is required")
    if arm == 'REF' and card['index'] != 7:
        raise ValueError('REF retains its one fixed GPU7 deployment')
    root = Path(directory).resolve()
    if not root.is_relative_to(ROOT / "runs/software-benchmark-v054"):
        raise ValueError("Fresh model service output must be under this project's benchmark runs")
    root.mkdir(parents=True, exist_ok=False)
    condition = condition_reference(arm)
    owner_admission = write_new(root / "owner-admission.json", {
        "arm": arm, "capacity_receipt": capacity_reference, "condition": condition,
        "capacity_admission": admitted_capacity,
        "capacity_passed": True, "formal_execution_authorized": False,
        "model_manifest": reference(MODEL / "proworksim-manifest.json")})
    short = ROOT / "runs/v054-gpu" / secrets.token_hex(6)
    short.mkdir(mode=0o700, parents=True, exist_ok=False)
    contract = write_new(root / "contract.json", CONTRACT)
    permit = write_new(root / "load-admission.json", {
        "model_loading_authorized": True, "formal_execution_authorized": False,
        "model_manifest": reference(MODEL / "proworksim-manifest.json"),
        "contract_sha256": digest(json_bytes(CONTRACT)), "capacity_receipt": capacity_reference})
    key_path = None
    if arm == "REF":
        key_path = root / "ref-api-key.private"
        fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as stream:
            stream.write(secrets.token_urlsafe(48) + "\n")
    specification = write_new(root / "service-spec.json", {
        "version": VERSION, "arm": arm, "card": card, "capacity_receipt": capacity_reference,
        "capacity_admission": admitted_capacity,
        "condition": condition, "model_manifest": reference(MODEL / "proworksim-manifest.json"),
        "root": str(root), "short": str(short), "contract": contract, "load_admission": permit,
        "api_key_file": str(key_path) if key_path else None, "REF_argv": ref_arguments() if arm == "REF" else None,
        "factory_source": reference(__file__)})
    return write_new(root / "model-service.json", {
        "factory_version": VERSION, "factory_source": reference(__file__), "service_spec": specification,
        "condition": condition, "arm": arm, "admission_passed": True, "capacity_receipt": capacity_reference,
        "capacity_admission": admitted_capacity,
        "owner_admission": owner_admission, "gpu_uuid": card["uuid"], "startup_timeout_seconds": 1800,
        "ready_path": str(root / "ready.json"), "identity_path": str(root / "identity.json"),
        "socket_path": str(short / "owner.sock") if arm != "REF" else None,
        "endpoint": "http://127.0.0.1:18054" if arm == "REF" else None,
        "api_key_file": str(key_path) if key_path else None,
        "command": [os.sys.executable, str(ROOT / "tools/run_formal_model_service_v054.py"),
                    "--spec", specification["path"], "--spec-sha256", specification["sha256"]],
        "formal_execution_authorized": False, "model_loads_from_factory": 0})


def validate_resident_session_service(service, arm):
    spec_path = checked(service["service_spec"])
    spec = json.loads(spec_path.read_text())
    declaration = json.loads(checked(service["resident_reference"]).read_text())
    registration = validate_registration(
        json.loads(checked(service['resident_registration']).read_text()), service['resident_pool_policy'])
    if (registration['event_reference'] != service['resident_registration']
            or registration['declaration'] != service['resident_reference']
            or spec.get('resident_registration') != service['resident_registration']
            or spec.get('resident_pool_policy') != service['resident_pool_policy']):
        raise ValueError('Session escaped its current immutable resident registration')
    capacity = declared_session_capacity(declaration)
    session_contract = ({"session_protocol": "mp-interleave-v1", "maximum_sessions": 2}
                        if capacity == 2 else {})
    for key, value in session_contract.items():
        if service.get(key) != value or spec.get(key) != value:
            raise ValueError("Session service lost its frozen interleave protocol")
    if capacity == 1 and (service.get("maximum_sessions", 1) != 1
                          or spec.get("maximum_sessions", 1) != 1):
        raise ValueError("A single-session deployment cannot claim extra slots")
    expected_command = [str(ROOT / ".venv/bin/python"), str(ROOT / "tools/hold_resident_session_v054.py"),
                        "--session", str(Path(spec["root"]) / "session.json")]
    if (service["factory_source"] != reference(__file__) or service["arm"] != arm
            or service["condition"] != condition_reference(arm)
            or service["capacity_admission"] != capacity_admission(arm, service["capacity_receipt"])
            or service["command"] != expected_command
            or spec["resident_reference"] != service["resident_reference"]
            or declaration["mode"] != ("REF" if arm == "REF" else "MATCH_PROJECT")
            or declaration["gpu_uuid"] != service["gpu_uuid"]
            or declaration['gpu_index'] != service['gpu_index']
            or registration['resident_id'] != service['resident_id']
            or service["admission_passed"] is not True):
        raise ValueError("Resident session differs from its frozen service/condition")
    recorded = spec_path.parent / "model-service.json"
    if json.loads(recorded.read_text()) != service:
        raise ValueError("Resident service declaration changed")
    return reference(recorded)


def build_resident_session_service(*, arm, capacity_reference, card, directory, resident_reference,
                                   registration_reference, pool_policy_reference):
    admitted = capacity_admission(arm, capacity_reference)
    validate_card_identity(card)
    if registration_reference is None or pool_policy_reference is None:
        raise ValueError('Formal sessions require a separately admitted pool registration')
    registration = validate_registration(json.loads(checked(registration_reference).read_text()), pool_policy_reference)
    if (registration['event_reference'] != registration_reference
            or registration['declaration'] != resident_reference):
        raise ValueError('Resident declaration is not this active admitted registration')
    declaration = json.loads(checked(resident_reference).read_text())
    capacity = declared_session_capacity(declaration)
    session_contract = ({"session_protocol": "mp-interleave-v1", "maximum_sessions": 2}
                        if capacity == 2 else {})
    deployment = json.loads(checked(declaration["source_spec"]).read_text())
    if (declaration["mode"] != ("REF" if arm == "REF" else "MATCH_PROJECT")
            or (arm == 'REF' and declaration['gpu_index'] != 7)
            or card["index"] != declaration["gpu_index"] or card["uuid"] != declaration["gpu_uuid"]
            or deployment["capacity_receipt"] != capacity_reference):
        raise ValueError("Resident is outside the admitted physical/numerical mode")
    root = Path(directory).resolve()
    if not root.is_relative_to(ROOT / "runs/software-benchmark-v054"):
        raise ValueError("Session output must be an independent project episode directory")
    root.mkdir(mode=0o700, parents=True, exist_ok=False)
    condition = condition_reference(arm)
    owner_admission = write_new(root / "owner-admission.json", {
        **session_contract,
        "arm": arm, "capacity_receipt": capacity_reference, "capacity_admission": admitted,
        "condition": condition, "capacity_passed": True, "formal_execution_authorized": False,
        'resident_pool_policy': pool_policy_reference, 'resident_registration': registration_reference,
        "model_manifest": reference(MODEL / "proworksim-manifest.json"), "resident_reference": resident_reference})
    spec = write_new(root / "service-spec.json", {**session_contract, "root": str(root), "arm": arm,
        "condition": condition, "resident_reference": resident_reference,
        'resident_pool_policy': pool_policy_reference, 'resident_registration': registration_reference,
        "capacity_receipt": capacity_reference, "factory_source": reference(__file__)})
    return write_new(root / "model-service.json", {**session_contract, "factory_version": VERSION,
        "deployment_mode": "resident-session-v1", "factory_source": reference(__file__),
        "arm": arm, "condition": condition, "admission_passed": True, "capacity_receipt": capacity_reference,
        "capacity_admission": admitted, "model_manifest": reference(MODEL / "proworksim-manifest.json"),
        "owner_admission": owner_admission, "resident_reference": resident_reference,
        'resident_pool_policy': pool_policy_reference, 'resident_registration': registration_reference,
        'resident_id': registration['resident_id'], 'gpu_index': card['index'],
        "session_directory": str(root), "service_spec": spec, "gpu_uuid": card["uuid"],
        "startup_timeout_seconds": 30, "ready_path": str(root / "session-ready.json"),
        "identity_path": str(root / "session-identity.json"), "socket_path": None,
        "endpoint": declaration["admin"].get("endpoint"),
        "api_key_file": declaration["admin"].get("api_key_file"),
        "command": [str(ROOT / ".venv/bin/python"), str(ROOT / "tools/hold_resident_session_v054.py"),
                    "--session", str(root / "session.json")], "formal_execution_authorized": False,
        "model_loads_from_factory": 0, "weights_retained_by_independent_resident": True})
