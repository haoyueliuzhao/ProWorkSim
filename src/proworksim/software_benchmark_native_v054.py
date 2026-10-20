"""The shared native OpenHands interface for v054 REF and MATCH.

This factory does not load a model, select a numerical backend, authorize model
execution, or provide a Docker workspace. A caller must separately supply those
admitted components before starting an episode.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

INTERFACE = {
    "version": "software-benchmark-v054-native-interface-v1",
    "sdk_tools_version": "1.49.6",
    "sdk_commit": "fcc102a697874d54a357e36004e02c95040dbdc0",
    "tools": ["TerminalTool", "FileEditorTool", "TaskTrackerTool"],
    "builtins": ["FinishTool", "ThinkTool"],
    "terminal": {"terminal_type": "subprocess", "shell_path": "/bin/bash"},
    "prompt": "unmodified_official_default_preset",
    "system_prompt_kwargs": {"cli_mode": False},
    "agent_context": None,
    "browser": False,
    "subagents": False,
    "mcp_config": {},
    "plugins": [],
    "tool_concurrency_limit": 1,
    "condenser": {
        "kind": "LLMSummarizingCondenser", "max_size": 80, "keep_first": 4,
        "max_tokens": None, "hard_context_reset_max_retries": 1,
    },
    "max_iteration_per_run": 128,
    "stuck_detection": True,
    "project_single_call_hint": False,
    "project_managed_tools": False,
}


def build_agent(llm):
    """Build the exact same native interface; arm-specific LLM is supplied."""
    from openhands.sdk import Agent
    from openhands.sdk.agent import base as official_base
    from openhands.sdk.context.condenser import LLMSummarizingCondenser
    from openhands.sdk.tool import Tool
    from openhands.tools.file_editor import FileEditorTool
    from openhands.tools.task_tracker import TaskTrackerTool
    from openhands.tools.terminal import TerminalTool

    if official_base._SOUL_PATH.exists():
        raise ValueError("A personal SOUL.md cannot enter the frozen native interface")
    condenser = LLMSummarizingCondenser(
        llm=llm.model_copy(update={"usage_id": "condenser"}),
        max_size=80, keep_first=4, max_tokens=None,
        hard_context_reset_max_retries=1,
    )
    return Agent(
        llm=llm,
        tools=[
            Tool(name=TerminalTool.name, params=dict(INTERFACE["terminal"])),
            Tool(name=FileEditorTool.name),
            Tool(name=TaskTrackerTool.name),
        ],
        include_default_tools=list(INTERFACE["builtins"]),
        system_prompt_kwargs=dict(INTERFACE["system_prompt_kwargs"]),
        condenser=condenser, mcp_config={}, agent_context=None,
        tool_concurrency_limit=1,
    )


def build_conversation(llm, *, workspace, persistence_dir):
    """Assemble only; does not call send_message(), run(), or any model."""
    from openhands.sdk import Conversation

    workspace = Path(workspace)
    if not workspace.is_dir():
        raise ValueError("An explicitly prepared native workspace is required")
    return Conversation(
        agent=build_agent(llm), workspace=workspace,
        persistence_dir=Path(persistence_dir), plugins=[],
        max_iteration_per_run=128, stuck_detection=True,
        visualizer=None, delete_on_close=False,
    )


def initialized_interface_manifest(agent):
    """Capture actual initialized tool schemas and prompt, without LLM settings."""
    if len(agent.tools_map) != 5:
        raise ValueError("Expected the three declared native tools and two builtins")
    tools = {
        name: tool.to_openai_tool(add_security_risk_prediction=True)
        for name, tool in sorted(agent.tools_map.items())
    }
    payload = {
        "contract": INTERFACE,
        "tool_schemas": tools,
        "static_system_prompt": agent.static_system_message,
        "condenser_configuration": agent.condenser.model_dump(
            mode="json", exclude={"llm"}),
        "tool_executor_classes": {
            name: f"{type(tool.executor).__module__}.{type(tool.executor).__name__}"
            for name, tool in sorted(agent.tools_map.items())
        },
    }
    serialized = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return {"interface_sha256": hashlib.sha256(serialized).hexdigest(), **payload}
