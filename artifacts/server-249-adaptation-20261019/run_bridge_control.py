"""One synthetic repository node through the new server bridge identity."""
import hashlib
import json
from pathlib import Path

from proworksim.server_bridge_runtime_v052 import execution_protocol
from proworksim.software_bridge_sources_v052 import ref, run_repository_tests

root = Path(__file__).resolve().parent
manifest = root / "bridge-runtime.json"
runtime = json.loads(manifest.read_bytes())
files = {
    "migration_answer.py": "def answer():\n    return 42\n",
    "test_migration_answer.py": (
        "from migration_answer import answer\n"
        "def test_answer():\n    assert answer() == 42\n"
    ),
}
task = {
    "nodeids": ["test_migration_answer.py::test_answer"],
    "cpu_python": runtime["python_invocation"],
    "bridge_runtime_ref": ref(manifest),
    "bridge_execution_protocol": execution_protocol(runtime),
    "frozen_test_hashes": {
        "test_migration_answer.py": hashlib.sha256(files["test_migration_answer.py"].encode()).hexdigest()
    },
    "initial_production_hashes": {
        "migration_answer.py": hashlib.sha256(files["migration_answer.py"].encode()).hexdigest()
    },
}
result = run_repository_tests(files=files, task=task, run_root=root / "bridge-synthetic")
assert result["executed"] is True and result["passed"] is True, result
assert result["source_unchanged"] is True and len(result["tests"]) == 1, result
assert result["isolation"]["filesystem_backend"] == "user_mount_namespace", result
binding = json.loads(Path(result["bridge_binding"]["path"]).read_bytes())
assert binding["version"] == "server-249-v052-repository-test-binding-v1", binding
print(json.dumps({"passed": True, "synthetic_nodes": 1,
                  "evaluation_identity": result["evaluation_identity"],
                  "bridge_binding": result["bridge_binding"],
                  "isolation": result["isolation"], "model_calls": 0}, indent=2))
