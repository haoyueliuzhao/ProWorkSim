"""Trusted SDK-side CPU control; stdin/stdout are the worker's JSON RPC pipes."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import traceback


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ready", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--outside-marker", required=True)
    parser.add_argument("--arm", required=True, choices=["REF", "MATCH"])
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    os.environ["OH_PERSISTENCE_DIR"] = str(output / "empty-user-config")
    counters = {"model_calls": 0, "network_attempts": 0, "gpu_device_opens": 0,
                "weight_files_opened": 0, "host_executor_constructions": 0}

    def audit(event, values):
        if event in {"socket.connect", "socket.getaddrinfo", "socket.sendto"}:
            counters["network_attempts"] += 1
            raise RuntimeError("No network in the SDK proxy construction control")
        if event == "open" and values and isinstance(values[0], (str, bytes)):
            path = os.fsdecode(values[0])
            if path.endswith((".safetensors", ".gguf")):
                counters["weight_files_opened"] += 1
                raise RuntimeError("No weights in the SDK proxy control")
            if path.startswith(("/dev/nvidia", "/dev/dri/")):
                counters["gpu_device_opens"] += 1
                raise RuntimeError("No GPU in the SDK proxy control")

    sys.addaudithook(audit)
    receipt = {"version": "v054-native-proxy-control-v1", "arm": args.arm, "passed": False,
               "started_utc": datetime.now(timezone.utc).isoformat()}
    rpc = conversation = None
    try:
        from openhands.sdk import LLM
        from openhands.tools.file_editor.impl import FileEditorExecutor
        from openhands.tools.task_tracker.definition import TaskTrackerExecutor
        from openhands.tools.terminal.impl import TerminalExecutor
        from proworksim.software_benchmark_native_binding_v054 import (
            NativeToolRPC, NativeProxyExecutor, build_isolated_conversation,
        )

        def forbidden(*args, **kwargs):
            counters["host_executor_constructions"] += 1
            raise RuntimeError("The SDK host must not construct native filesystem/shell executors")

        # Instrument this disposable host process only; worker files/classes are
        # untouched and have already been loaded in its independent process.
        for cls in (FileEditorExecutor, TerminalExecutor, TaskTrackerExecutor):
            cls.__init__ = forbidden

        class NeverCallLLM(LLM):
            def completion(self, *args, **kwargs):
                counters["model_calls"] += 1
                raise RuntimeError("LLM calls are forbidden in this CPU control")

            async def acompletion(self, *args, **kwargs):
                counters["model_calls"] += 1
                raise RuntimeError("LLM calls are forbidden in this CPU control")

        ref = args.arm == "REF"
        llm = NeverCallLLM(
            model="openai/Qwen3.5-9B", base_url="http://127.0.0.1:9/v1",
            api_key="synthetic-no-key", usage_id="agent", num_retries=0,
            stream=False, caching_prompt=False,
            max_input_tokens=131072 if ref else 18432,
            max_output_tokens=32768 if ref else 2048, temperature=0.6 if ref else 0.7)
        rpc = NativeToolRPC(ready=json.loads(args.ready.read_bytes()),
                            reader=sys.stdin, writer=sys.stdout)
        conversation = build_isolated_conversation(
            llm, rpc=rpc, persistence_dir=output / "conversation")
        conversation.send_message("Synthetic CPU proxy control only. No model generation.")
        agent = conversation.agent
        assert set(agent.tools_map) == {"terminal", "file_editor", "task_tracker", "finish", "think"}
        for name in ("terminal", "file_editor", "task_tracker"):
            assert isinstance(agent.tools_map[name].executor, NativeProxyExecutor)
            assert (agent.tools_map[name].to_openai_tool(add_security_risk_prediction=True)
                    == rpc.ready["tool_definitions"][name]["openai_schema"])
        interface = {
            "tools": {name: tool.to_openai_tool(add_security_risk_prediction=True)
                      for name, tool in sorted(agent.tools_map.items())},
            "static_system_prompt": agent.static_system_message,
            "condenser": agent.condenser.model_dump(mode="json", exclude={"llm"}),
            "worker_executor_classes": rpc.ready["executors"],
            "worker_terminal_backend": rpc.ready["terminal_backend"],
        }
        (output / "interface.json").write_text(
            json.dumps(interface, ensure_ascii=False, sort_keys=True, indent=2) + "\n")

        def call(name, **action):
            tool = agent.tools_map[name]
            observed = tool(tool.action_type.model_validate(action), conversation)
            assert ([item.model_dump(mode="json") for item in observed.to_llm_content]
                    == rpc.transcript[-1]["response"]["llm_content"])
            return observed.native_observation

        observed = call(
            "terminal", command="cd /testbed/sub; export RPC_STATE=kept; printf saved > rpc-state.txt",
            timeout=10)
        assert observed["exit_code"] == 0
        observed = call(
            "terminal", command='printf "%s|%s|" "$PWD" "$RPC_STATE"; cat rpc-state.txt', timeout=10)
        text = "".join(item.get("text", "") for item in observed["content"])
        assert "/testbed/sub|kept|saved" in text
        assert observed["metadata"]["working_dir"] == "/testbed/sub"
        assert observed["metadata"]["py_interpreter_path"] == rpc.ready["public_python"]
        observed = call("terminal", command=(
            "python - <<'PY'\n"
            "import socket\n"
            "server=socket.socket(); server.bind(('127.0.0.1',0)); server.listen(1)\n"
            "client=socket.socket(); client.settimeout(2); client.connect(server.getsockname())\n"
            "accepted,_=server.accept(); client.sendall(b'private-loopback')\n"
            "assert accepted.recv(64)==b'private-loopback'\n"
            "accepted.close(); client.close(); server.close(); print('loopback-ok')\n"
            "PY"), timeout=10)
        assert observed["exit_code"] == 0
        assert "loopback-ok" in "".join(item.get("text", "") for item in observed["content"])
        for path, content in (("/testbed/one.py", "VALUE = 1\n"),
                              ("/testbed/sub/two.py", "OTHER = 2\n")):
            assert not call("file_editor", command="create", path=path, file_text=content)["is_error"]
        assert not call(
            "file_editor", command="str_replace", path="/testbed/sub/two.py",
            old_str="OTHER = 2", new_str="OTHER = 3")["is_error"]
        assert not call("file_editor", command="view", path="/public/note.txt")["is_error"]
        for path in (args.outside_marker, next(iter(rpc.ready["official_sources"]))):
            assert call("file_editor", command="view", path=path)["is_error"]
        assert not call(
            "task_tracker", command="plan",
            task_list=[{"title": "RPC public step", "status": "todo"}])["is_error"]
        assert call("task_tracker", command="view")["task_list"][0]["title"] == "RPC public step"
        receipt.update({
            "passed": True, "tool_calls": len(rpc.transcript),
            "agent_class": type(agent).__module__ + "." + type(agent).__name__,
            "conversation_class": type(conversation).__module__ + "." + type(conversation).__name__,
            "same_official_visible_schemas_as_worker": True,
            "native_llm_content_preserved": True, "persistent_pty_state": True,
            "outside_host_and_sdk_files_denied": True,
            "public_interpreter_matches_environment": True,
            "private_loopback_available": True,
        })
    except BaseException as error:
        receipt["error"] = {"type": type(error).__name__, "message": str(error)}
        receipt["traceback"] = traceback.format_exc()
    finally:
        if conversation is not None:
            conversation.close()
        if rpc is not None:
            try:
                rpc.close()
            except Exception as error:
                receipt["passed"] = False
                receipt["close_error"] = str(error)
            (output / "rpc-transcript.json").write_text(
                json.dumps(rpc.transcript, ensure_ascii=False, indent=2) + "\n")
        receipt.update(counters)
        receipt["ended_utc"] = datetime.now(timezone.utc).isoformat()
        (output / "receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
