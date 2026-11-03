import os
os.environ.update(LITELLM_LOCAL_MODEL_COST_MAP="True", OPENHANDS_SUPPRESS_BANNER="1",
                  HF_HUB_OFFLINE="1", HF_DATASETS_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
import sys, socket, json, importlib.util, importlib.metadata
from pathlib import Path
runtime = Path(sys.argv[1]).resolve()
counts = {"network": 0, "process": 0}
def deny(event, args):
    if event in {"socket.connect", "socket.getaddrinfo", "socket.sendto"}:
        if event == "socket.getaddrinfo" or getattr(args[0], "family", None) in (socket.AF_INET, socket.AF_INET6):
            counts["network"] += 1
            raise RuntimeError("Offline bundle control refuses external networking")
    if event in {"subprocess.Popen", "os.system", "os.fork", "os.posix_spawn"}:
        counts["process"] += 1
        raise RuntimeError("Import/preload cannot create another process")
sys.addaudithook(deny)
from proworksim.software_benchmark_native_worker_v054 import preload
classes = preload()
from proworksim.software_benchmark_alignment_contract_v110 import condition, validate_condition
from proworksim.software_benchmark_managed_v110 import worker_type
from proworksim.software_benchmark_history_v110 import condenser_type
from proworksim.software_benchmark_public_tests_v110 import normalize_selection
for arm in ("REF", "PROJECT"):
    validate_condition(condition(arm))
assert condition("REF")["execution_strategy"] == condition("PROJECT")["execution_strategy"]
assert normalize_selection()["kind"] == "full"
worker = worker_type()
condenser = condenser_type()
entrypoints = []
for name in ("worker.py", "managed-worker.py", "controller.py", "project-controller.py", "public-test.py"):
    spec = importlib.util.spec_from_file_location("aligned_bundle_"+name.replace(".", "_").replace("-", "_"), runtime/name)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    entrypoints.append(name)
loaded = []
for name, module in sys.modules.items():
    if name == "proworksim" or name.startswith("proworksim."):
        source = Path(module.__file__).resolve()
        loaded.append(str(source.relative_to(runtime/"project/src/proworksim")))
assert not any("software_benchmark_scorer" in item or "software_benchmark_deepseek_api" in item for item in loaded)
assert not any(counts.values())
print(json.dumps({"sdk_version": importlib.metadata.version("openhands-sdk"),
    "tools": sorted(classes), "model_calls": 0, "tool_calls": 0, "Docker_operations": 0,
    "forbidden_operation_counts": counts, "actual_worker_preload": True,
    "all_controller_and_worker_entrypoints_imported": True, "entrypoints": entrypoints,
    "managed_worker_class": worker.__name__, "shared_condenser_class": condenser.__name__,
    "loaded_project_modules": sorted(loaded), "factory_runtime_exercised_in_this_probe": False,
    "real_SDK_scripted_factory_controls_are_separate": True}))
