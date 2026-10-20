"""Exercise the actual CPU official-parser sidecar with synthetic token IDs."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import traceback


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-local", type=Path, required=True)
    parser.add_argument("--interface-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    receipt = {
        "version": "software-benchmark-v054-official-codec-control-v1",
        "started_at_utc": datetime.now(timezone.utc).isoformat(), "passed": False,
        "model_calls": 0, "tool_executions": 0, "network_attempts": 0,
        "weight_file_opens": 0, "gpu_device_opens": 0,
        "formal_execution_authorized": False, "cases": {},
    }

    def audit(event, values):
        if event == "socket.getaddrinfo" or (
                event in {"socket.connect", "socket.sendto"}
                and values[0].family != socket.AF_UNIX):
            receipt["network_attempts"] += 1
            raise RuntimeError("Only the local codec Unix socket may be used")
        if event == "open" and values and isinstance(values[0], (str, bytes)):
            path = os.fsdecode(values[0])
            if path.endswith((".safetensors", ".gguf")) or "pytorch_model" in path:
                receipt["weight_file_opens"] += 1
                raise RuntimeError("No weight access in codec control")
            if path.startswith(("/dev/nvidia", "/dev/dri/")):
                receipt["gpu_device_opens"] += 1
                raise RuntimeError("No GPU access in codec control")

    sys.addaudithook(audit)
    process = None
    socket_path = args.output / "codec.sock"
    identity_path = args.output / "identity.json"
    try:
        assert os.environ.get("CUDA_VISIBLE_DEVICES") == ""
        assert os.environ.get("NVIDIA_VISIBLE_DEVICES") == "void"
        from transformers import AutoTokenizer
        module_path = Path(__file__).resolve().parents[1] / "src/proworksim/software_benchmark_codec_v054.py"
        spec = importlib.util.spec_from_file_location("v054_standalone_codec", module_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        UnixSocketCodec = module.UnixSocketCodec
        tokenizer = AutoTokenizer.from_pretrained(
            str(args.model_local), local_files_only=True, trust_remote_code=False)
        interface = json.loads(args.interface_manifest.read_bytes())
        tools = list(interface["tool_schemas"].values())
        with (args.output / "sidecar.log").open("xb") as log:
            process = subprocess.Popen([
                sys.executable, "tools/serve_match_codec_v054.py",
                "--model-local", str(args.model_local),
                "--socket", str(socket_path), "--identity-output", str(identity_path),
                "--diagnostic-traceback-seconds", "20",
            ], stdout=log, stderr=subprocess.STDOUT)
            deadline = time.monotonic() + 60
            while not (socket_path.exists() and identity_path.exists()):
                if process.poll() is not None:
                    raise RuntimeError(f"Codec exited during startup: {process.returncode}")
                if time.monotonic() >= deadline:
                    raise TimeoutError("Codec CPU startup timeout")
                time.sleep(0.1)
            identity = json.loads(identity_path.read_bytes())
            client = UnixSocketCodec(socket_path, identity)
            fixtures = {
                "summary_eos": ("synthetic summary", False),
                "two_calls": (
                    "<tool_call>\n<function=terminal>\n"
                    "<parameter=command>printf synthetic</parameter>\n"
                    "<parameter=timeout>3</parameter>\n"
                    "<parameter=is_input>false</parameter>\n"
                    "<parameter=reset>false</parameter>\n"
                    "</function>\n</tool_call>\n"
                    "<tool_call>\n<function=task_tracker>\n"
                    "<parameter=command>plan</parameter>\n"
                    '<parameter=task_list>[{"title":"x","status":"todo","notes":""}]</parameter>\n'
                    "</function>\n</tool_call>", True),
                "nullable_array": (
                    "<tool_call>\n<function=file_editor>\n"
                    "<parameter=command>view</parameter>\n"
                    "<parameter=path>/testbed/a.py</parameter>\n"
                    "<parameter=view_range>[1,3]</parameter>\n"
                    "</function>\n</tool_call>", True),
                "finish": (
                    "<tool_call>\n<function=finish>\n"
                    "<parameter=message>synthetic finish</parameter>\n"
                    "</function>\n</tool_call>", True),
                "malformed": (
                    "<tool_call>\n<function=terminal>\n<parameter=command>unfinished", True),
            }
            for name, (text, use_tools) in fixtures.items():
                receipt["current_case"] = name
                (args.output / "progress.json").write_text(json.dumps(
                    receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
                ids = tokenizer.encode(text, add_special_tokens=False) + [248044]
                request = {
                    "model": "raw-qwen3.5-9b-v054-match",
                    "messages": [{"role": "user", "content": "Synthetic parser fixture."}],
                    "tools": tools if use_tools else [],
                }
                result = {"output_ids": ids, "finish_reason": "stop"}
                decoded = client.decode(request=request, result=result)
                receipt["cases"][name] = decoded
                assert decoded["generated_token_count"] == len(ids)
                assert decoded["presentation_token_count"] == len(ids) - 1
            cases = receipt["cases"]
            assert cases["summary_eos"]["message"]["content"] == "synthetic summary"
            calls = cases["two_calls"]["message"]["tool_calls"]
            assert [item["function"]["name"] for item in calls] == ["terminal", "task_tracker"]
            terminal = json.loads(calls[0]["function"]["arguments"])
            tracker = json.loads(calls[1]["function"]["arguments"])
            assert terminal["timeout"] == 3 and terminal["is_input"] is False
            assert tracker["task_list"][0]["status"] == "todo"
            editor = json.loads(cases["nullable_array"]["message"]["tool_calls"][0]["function"]["arguments"])
            assert editor["view_range"] == [1, 3]
            assert cases["finish"]["message"]["tool_calls"][0]["function"]["name"] == "finish"
            receipt.update({
                "passed": True, "codec_identity": identity,
                "sidecar_pid": process.pid,
                "native_interface_manifest_sha256": hashlib.sha256(
                    args.interface_manifest.read_bytes()).hexdigest(),
                "synthetic_cases": len(fixtures), "actual_task_runs": 0,
                "malformed_result_preserved_without_retry": True,
            })
    except Exception as error:
        receipt["error"] = {"type": type(error).__name__, "message": str(error)}
        receipt["traceback"] = traceback.format_exc()
    finally:
        (args.output / "receipt.json").write_text(json.dumps(
            receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
                receipt["sidecar_cleanup"] = "terminated_and_reaped"
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
                receipt["sidecar_cleanup"] = "killed_after_termination_timeout_and_reaped"
        socket_path.unlink(missing_ok=True)
    receipt["ended_at_utc"] = datetime.now(timezone.utc).isoformat()
    (args.output / "receipt.json").write_text(json.dumps(
        receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    print(json.dumps(
        {key: value for key, value in receipt.items() if key != "cases"},
        ensure_ascii=False, sort_keys=True))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
