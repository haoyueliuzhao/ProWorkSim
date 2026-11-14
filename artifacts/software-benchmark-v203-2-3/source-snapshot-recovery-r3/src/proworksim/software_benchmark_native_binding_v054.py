"""Shared REF/MATCH SDK factory binding to the isolated official tool worker."""
from __future__ import annotations

import json
import math
import os
import selectors
import threading
import time
import uuid
from typing import Any

from openhands.sdk.tool import Observation, Tool, ToolAnnotations, ToolExecutor, register_tool

from .software_benchmark_native_v054 import build_agent as build_native_agent


class NativeRPCObservation(Observation):
    """Keep native wire evidence and exactly its worker-rendered LLM content."""
    native_tool: str
    native_observation: dict[str, Any]

    @property
    def to_llm_content(self):
        # Native formatting (including output-file persistence) was executed in
        # the actor root. Never re-run it against a same-named path on the host.
        return self.content


class NativeToolRPC:
    def __init__(self, *, ready, reader, writer, response_timeout_seconds=6000):
        if ready.get("type") != "ready" or ready.get("version") != "software-benchmark-native-worker-v054":
            raise ValueError("An actually initialized native worker is required")
        isolation = ready["isolation"]
        if (isolation["pid"] != 1 or isolation["capabilities_all_zero"] is not True
                or isolation["dumpable"] is not False or isolation["no_new_privileges"] is not True):
            raise ValueError("Native worker isolation did not pass")
        self.ready, self.reader, self.writer = ready, reader, writer
        self.session_id = uuid.uuid4().hex
        self._lock = threading.Lock()
        self._sequence = 0
        self._closed = False
        self.transcript = []
        self._bound = False
        if response_timeout_seconds <= 0 or not math.isfinite(response_timeout_seconds):
            raise ValueError("A positive finite response timeout is required")
        self.response_timeout_seconds = response_timeout_seconds
        self._read_buffer = bytearray()
        self._failed = False

    def _receive(self, timeout_seconds=None):
        timeout = self.response_timeout_seconds if timeout_seconds is None else timeout_seconds
        if timeout <= 0 or not math.isfinite(timeout):
            raise TimeoutError("Native worker response deadline expired")
        deadline = time.monotonic() + timeout
        with selectors.DefaultSelector() as selector:
            selector.register(self.reader.fileno(), selectors.EVENT_READ)
            while True:
                separator = self._read_buffer.find(b"\n")
                if separator >= 0:
                    line = bytes(self._read_buffer[:separator])
                    del self._read_buffer[:separator + 1]
                    return json.loads(line)
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not selector.select(remaining):
                    self._failed = True
                    raise TimeoutError("Native worker RPC response timed out; supervisor must stop the episode")
                chunk = os.read(self.reader.fileno(), 65536)
                if not chunk:
                    self._failed = True
                    raise RuntimeError("Native worker RPC closed without a complete result")
                self._read_buffer.extend(chunk)

    def request(self, tool, action, *, timeout_seconds=None):
        with self._lock:
            if self._closed or self._failed:
                raise RuntimeError("Native worker was closed or its transport failed")
            self._sequence += 1
            request = {"id": self._sequence, "tool": tool, "action": action}
            self.writer.write(json.dumps(request, ensure_ascii=False) + "\n")
            self.writer.flush()
            result = self._receive(timeout_seconds)
            self.transcript.append({"request": request, "response": result})
            if result.get("id") != request["id"] or result.get("type") != "observation":
                raise RuntimeError("Native worker tool failed: " + str(result))
            return result

    def close(self, *, timeout_seconds=None):
        with self._lock:
            if self._closed:
                return
            if self._failed:
                raise RuntimeError("Failed RPC cannot establish quiescence; use the external supervisor")
            self._sequence += 1
            self.writer.write(json.dumps({"id": self._sequence, "op": "close"}) + "\n")
            self.writer.flush()
            result = self._receive(timeout_seconds)
            if result.get("type") != "closed" or result.get("id") != self._sequence:
                raise RuntimeError("Native worker did not acknowledge close")
            if result.get("official_terminal_close_returned") is not True:
                raise RuntimeError("Official terminal cleanup did not return")
            self._closed = True
            self.transcript.append(result)


class NativeProxyExecutor(ToolExecutor):
    def __init__(self, rpc, tool_name):
        self.rpc, self.tool_name = rpc, tool_name

    def __call__(self, action, conversation=None):
        result = self.rpc.request(self.tool_name, action.model_dump(mode="json"))
        return NativeRPCObservation(
            content=result["llm_content"], is_error=result["observation"]["is_error"],
            native_tool=self.tool_name, native_observation=result["observation"])

    def close(self):
        # Three executors share one worker. Its owning episode closes RPC once
        # after the SDK conversation has closed its tools.
        return None


def build_isolated_agent(llm, *, rpc):
    """Use the unmodified native Agent factory; replace only tool transport."""
    from openhands.tools.file_editor import FileEditorTool
    from openhands.tools.file_editor.definition import FileEditorAction
    from openhands.tools.task_tracker import TaskTrackerTool
    from openhands.tools.task_tracker.definition import TaskTrackerAction
    from openhands.tools.terminal import TerminalTool
    from openhands.tools.terminal.definition import TerminalAction

    if rpc._bound:
        raise ValueError("Each actual Agent requires a fresh independent worker")
    if rpc.ready["vision_enabled"] != llm.vision_is_active():
        raise ValueError("Native image-view description differs from the LLM configuration")
    agent = build_native_agent(llm)
    classes = {
        "terminal": (TerminalTool, TerminalAction),
        "file_editor": (FileEditorTool, FileEditorAction),
        "task_tracker": (TaskTrackerTool, TaskTrackerAction),
    }
    declarations = []
    for name, (definition, action) in classes.items():
        wire = rpc.ready["tool_definitions"][name]
        tool = definition(
            description=wire["description"], action_type=action,
            observation_type=NativeRPCObservation,
            annotations=ToolAnnotations.model_validate(wire["annotations"]),
            meta=wire["meta"], executor=NativeProxyExecutor(rpc, name))
        if tool.to_openai_tool(add_security_risk_prediction=True) != wire["openai_schema"]:
            raise ValueError("Native LLM-facing tool schema changed across transport")
        alias = "pws_v054_" + rpc.session_id + "_" + name
        register_tool(alias, tool)
        declarations.append(Tool(name=alias))
    rpc._bound = True
    return agent.model_copy(update={"tools": declarations})


def build_isolated_conversation(llm, *, rpc, persistence_dir):
    """Caller must mount this worker's public checkout at /testbed for SDK metadata."""
    from pathlib import Path
    from openhands.sdk import Conversation

    if not Path("/testbed").is_dir():
        raise ValueError("Trusted SDK metadata view must bind the same public checkout at /testbed")
    return Conversation(
        agent=build_isolated_agent(llm, rpc=rpc), workspace="/testbed",
        persistence_dir=persistence_dir, plugins=[], max_iteration_per_run=128,
        stuck_detection=True, visualizer=None, delete_on_close=False)
