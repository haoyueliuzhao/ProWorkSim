"""Check the installed REF packages on CPU without loading weights or inference."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import traceback


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pip-python", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("An earlier control receipt must not be overwritten")
    record = {
        "version": "software-benchmark-v054-ref-cpu-import-v1",
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "passed": False, "model_loads": 0, "generation_calls": 0,
        "network_attempts": 0, "weight_file_opens": 0, "gpu_device_opens": 0,
        "formal_execution_authorized": False,
        "gpu_capacity_or_numerical_admission": False,
    }

    def audit(event, values):
        if event in ("socket.getaddrinfo", "socket.connect", "socket.sendto"):
            record["network_attempts"] += 1
            raise RuntimeError("No network access during REF CPU checks")
        if event == "open" and values and isinstance(values[0], (str, bytes)):
            path = os.fsdecode(values[0])
            if path.endswith((".safetensors", ".gguf")) or "pytorch_model" in path:
                record["weight_file_opens"] += 1
                raise RuntimeError("No model weight access during REF CPU checks")
            if path.startswith(("/dev/nvidia", "/dev/dri/")):
                record["gpu_device_opens"] += 1
                raise RuntimeError("No GPU access during REF CPU checks")

    sys.addaudithook(audit)
    try:
        assert os.environ.get("CUDA_VISIBLE_DEVICES") == ""
        assert os.environ.get("NVIDIA_VISIBLE_DEVICES") == "void"
        assert os.environ.get("HF_HUB_OFFLINE") == "1"
        assert not any(stat.S_ISCHR(p.stat().st_mode) for p in Path("/dev").glob("nvidia*"))
        checked = subprocess.run(
            [str(args.pip_python), "-m", "pip", "--python", sys.executable,
             "--isolated", "--disable-pip-version-check", "check"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False)
        record["pip_check"] = {"exit_code": checked.returncode, "output": checked.stdout}
        if checked.returncode:
            raise RuntimeError("The installed REF dependency set does not pass pip check")
        import torch
        import vllm

        assert version("vllm") == "0.32.0"
        assert not torch.cuda.is_initialized()
        package_root = Path(vllm.__file__).parent
        required = (
            "model_executor/models/qwen3_5.py",
            "model_executor/models/registry.py",
            "tool_parsers/qwen3_engine_tool_parser.py",
            "tool_parsers/__init__.py",
            "reasoning/qwen3_engine_reasoning_parser.py",
            "reasoning/__init__.py",
            "parser/qwen3.py",
        )
        sources = {}
        for relative in required:
            body = (package_root / relative).read_bytes()
            sources[relative] = {"bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}
        assert "qwen3_coder" in (package_root / "tool_parsers/__init__.py").read_text()
        assert '"qwen3"' in (package_root / "reasoning/__init__.py").read_text()
        assert "Qwen3_5ForConditionalGeneration" in (
            package_root / "model_executor/models/registry.py").read_text()
        record.update({
            "passed": True,
            "python": sys.executable, "python_version": sys.version,
            "torch_version": torch.__version__, "torch_cuda_build": torch.version.cuda,
            "torch_cuda_initialized": torch.cuda.is_initialized(),
            "vllm_version": version("vllm"), "vllm_path": str(package_root),
            "qwen35_and_parser_source_files": sources,
        })
    except Exception as error:
        record["error"] = {"type": type(error).__name__, "message": str(error)}
        record["traceback"] = traceback.format_exc()
    record["ended_at_utc"] = datetime.now(timezone.utc).isoformat()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(
        record, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    print(json.dumps(record, ensure_ascii=False, sort_keys=True))
    return 0 if record["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
