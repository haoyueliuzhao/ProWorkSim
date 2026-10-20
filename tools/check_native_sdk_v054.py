"""One synthetic CPU construction control for the shared REF/MATCH interface."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import inspect
import json
import os
from pathlib import Path
import sys
import traceback


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    folder = args.output.absolute()
    folder.mkdir(parents=True, exist_ok=False)
    record = {
        "version": "software-benchmark-v054-native-sdk-construction-v1",
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "passed": False, "model_calls": 0, "network_attempts": 0,
        "weight_files_opened": 0, "gpu_device_opens": 0, "task_tool_calls": 0,
        "actual_task_runs": 0, "official_grader_calls": 0,
        "formal_execution_authorized": False,
        "sdk_construction_only": True,
        "terminal_initialization_shell_allowed": True,
    }

    def audit(event, values):
        if event in ("socket.connect", "socket.getaddrinfo", "socket.sendto"):
            record["network_attempts"] += 1
            raise RuntimeError("Network access forbidden during SDK construction")
        if event == "open" and values and isinstance(values[0], (str, bytes)):
            path = os.fsdecode(values[0])
            if path.endswith((".safetensors", ".gguf")) or "pytorch_model" in path:
                record["weight_files_opened"] += 1
                raise RuntimeError("Model weights forbidden during SDK construction")
            if path.startswith(("/dev/nvidia", "/dev/dri/")):
                record["gpu_device_opens"] += 1
                raise RuntimeError("GPU access forbidden during SDK construction")

    sys.addaudithook(audit)
    conversations = []
    try:
        assert os.environ.get("LITELLM_LOCAL_MODEL_COST_MAP") == "True"
        assert os.environ.get("CUDA_VISIBLE_DEVICES") == ""
        assert os.environ.get("NVIDIA_VISIBLE_DEVICES") == "void"
        os.environ["OH_PERSISTENCE_DIR"] = str(folder / "empty-user-config")
        from openhands.sdk import LLM
        from openhands.tools.terminal.terminal.subprocess_terminal import SubprocessTerminal
        from proworksim import software_benchmark_native_v054 as native

        assert version("openhands-sdk") == "1.49.6"

        class NeverCallLLM(LLM):
            def completion(self, *args, **kwargs):
                record["model_calls"] += 1
                raise RuntimeError("Model completion is forbidden in this control")

            async def acompletion(self, *args, **kwargs):
                record["model_calls"] += 1
                raise RuntimeError("Model completion is forbidden in this control")

        workspace = folder / "synthetic-workspace"
        workspace.mkdir()
        (workspace / "fixture.txt").write_text("Synthetic CPU fixture only.\n")
        before = {p.name: p.read_bytes() for p in workspace.iterdir()}
        manifests = {}
        arms = {}
        for arm, input_tokens, output_tokens, temperature in (
            ("REF", 131072, 32768, 0.6), ("MATCH", 18432, 2048, 0.7),
        ):
            llm = NeverCallLLM(
                model="openai/Qwen3.5-9B", base_url="http://127.0.0.1:9/v1",
                api_key="construction-control-no-secret",
                usage_id="agent", num_retries=0, stream=False,
                caching_prompt=False, max_input_tokens=input_tokens,
                max_output_tokens=output_tokens, temperature=temperature,
            )
            conversation = native.build_conversation(
                llm, workspace=workspace, persistence_dir=folder / arm)
            conversations.append(conversation)
            # Initializes the real tools and system prompt; never run()/step().
            conversation.send_message("Synthetic interface construction only. Do not run.")
            agent = conversation.agent
            manifests[arm] = native.initialized_interface_manifest(agent)
            terminal = agent.tools_map["terminal"].executor
            assert isinstance(terminal._session.terminal, SubprocessTerminal)
            assert not terminal.is_pooled
            assert set(agent.tools_map) == {
                "terminal", "file_editor", "task_tracker", "finish", "think",
            }
            arms[arm] = {
                "interface_sha256": manifests[arm]["interface_sha256"],
                "agent_class": f"{type(agent).__module__}.{type(agent).__name__}",
                "conversation_class": (
                    f"{type(conversation).__module__}.{type(conversation).__name__}"),
                "terminal_backend": (
                    f"{type(terminal._session.terminal).__module__}."
                    f"{type(terminal._session.terminal).__name__}"),
                "tool_names": sorted(agent.tools_map),
                "context_tokens": input_tokens, "output_tokens": output_tokens,
                "temperature": temperature,
            }
        assert manifests["REF"] == manifests["MATCH"]
        assert before == {p.name: p.read_bytes() for p in workspace.iterdir()}
        manifest_path = folder / "native-interface.json"
        manifest_path.write_text(json.dumps(
            manifests["REF"], ensure_ascii=False, sort_keys=True, indent=2) + "\n")
        source_files = set()
        for conversation in conversations:
            agent = conversation.agent
            for target in (type(agent), type(conversation), type(agent.condenser)):
                source_files.add(Path(inspect.getfile(target)))
            for tool in agent.tools_map.values():
                source_files.add(Path(inspect.getfile(type(tool))))
                if tool.executor is not None:
                    source_files.add(Path(inspect.getfile(type(tool.executor))))
        source_files.add(Path(native.__file__))
        record.update({
            "passed": True, "arms": arms,
            "interfaces_byte_identical": True,
            "workspace_unchanged": True,
            "native_interface_manifest": str(manifest_path),
            "native_interface_manifest_file_sha256": hashlib.sha256(
                manifest_path.read_bytes()).hexdigest(),
            "shared_interface_sha256": manifests["REF"]["interface_sha256"],
            "sdk_version": version("openhands-sdk"),
            "overlay_versions": {name: version(name) for name in
                                 ("binaryornot", "chardet", "libtmux")},
            "python": sys.executable, "python_version": sys.version,
            "source_files": {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                             for p in sorted(source_files)},
        })
    except Exception as error:
        record["error"] = {"type": type(error).__name__, "message": str(error)}
        record["traceback"] = traceback.format_exc()
    finally:
        for conversation in conversations:
            conversation.close()
        record["ended_at_utc"] = datetime.now(timezone.utc).isoformat()
        (folder / "receipt.json").write_text(
            json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    print(json.dumps(record, ensure_ascii=False, sort_keys=True))
    return 0 if record["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
