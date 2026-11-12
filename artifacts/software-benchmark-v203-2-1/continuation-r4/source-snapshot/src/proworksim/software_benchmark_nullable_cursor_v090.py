"""Opt-in PROJECT-only repair of SDK-dropped, explicitly nullable cursors.

The frozen SDK parser drops JSON null before constructing an Action.  The
managed gateway intentionally requires an exact match to the admitted original
arguments.  Restore only the four declared optional cursor fields, then run the
unchanged gateway comparison and execute the original arguments once.

This module does not patch SDK globals or install itself in existing workers.
"""
from __future__ import annotations

import copy
import hashlib
import json

from jsonschema import Draft202012Validator

VERSION = "v090-project-explicit-null-cursor-restoration-r1"
CURSOR_TOOLS = frozenset({"list_files", "read_file", "search_file", "diff_workspace"})


def _check_schema(name, schema):
    if name not in CURSOR_TOOLS:
        raise ValueError("Nullable restoration is limited to four PROJECT cursor tools")
    Draft202012Validator.check_schema(schema)
    cursor = schema.get("properties", {}).get("cursor", {})
    if (schema.get("type") != "object"
            or schema.get("additionalProperties") is not False
            or "cursor" in schema.get("required", [])
            or cursor.get("type") != ["string", "null"]
            or set(cursor) - {"type", "description"}):
        raise ValueError("Require the exact optional string/null cursor contract")


def needs_null_cursor_restoration(name, schema, original, projected):
    """Return true only for removal of an admitted optional cursor:null.

    Unknown arguments, missing required arguments, values of the wrong type,
    renamed or changed arguments, and missing non-null cursors are rejected.
    Omission, empty string, and a nonempty continuation cursor remain distinct.
    """
    _check_schema(name, schema)
    Draft202012Validator(schema).validate(original)
    if not isinstance(projected, dict):
        raise ValueError("Expected the SDK Action's JSON object projection")
    if projected == original:
        return False
    if ("cursor" not in original or original["cursor"] is not None
            or "cursor" in projected
            or projected != {key: value for key, value in original.items() if key != "cursor"}):
        raise ValueError("SDK changed arguments beyond the permitted explicit-null cursor")
    return True


class _NullableCursorExecutor:
    def __init__(self, delegate, *, worker, name, schema):
        _check_schema(name, schema)
        self.delegate, self.worker, self.name = delegate, worker, name
        self.schema = copy.deepcopy(schema)

    def __call__(self, action, conversation=None):
        pending = self.worker._pending
        if (pending is None or self.worker._executions != 0
                or pending["name"] != self.name):
            # Keep the original gateway's identity and single-execution guard.
            return self.delegate(action, conversation)
        original = pending["arguments"]
        projected = action.model_dump(mode="json", by_alias=True,
                                      exclude_unset=True, exclude_computed_fields=True)
        if needs_null_cursor_restoration(self.name, self.schema, original, projected):
            restored = type(action).model_validate(copy.deepcopy(original))
            exact = restored.model_dump(mode="json", by_alias=True,
                                        exclude_unset=True, exclude_computed_fields=True)
            if exact != original:
                raise RuntimeError("Restored Action did not preserve original arguments")
            self.worker._emit("sdk_explicit_null_cursor_restored", {
                "version": VERSION, "tool": self.name,
                "model_tool_call_id": pending["tool_call_id"],
                "restored_field": "cursor", "original_value": None,
                "other_arguments_changed": False, "world_action_executed": False,
                "original_gateway_comparison_still_required": True,
            })
            action = restored
        return self.delegate(action, conversation)


def install_project_nullable_cursors(worker):
    """Install on one fresh managed HarnessWorker, before its first step.

    Uses ToolDefinition.set_executor's immutable-copy API and replaces only the
    fresh worker's private map under its existing SDK lock.  The pinned SDK's
    public tools_map is a read-copy, and add_runtime_tools rejects replacement.
    Native REF workers are rejected; no class/module/global map is patched.
    """
    from .harness_sdk import HarnessWorker, _GatewayExecutor

    if not isinstance(worker, HarnessWorker):
        raise TypeError("This installer only accepts a managed PROJECT HarnessWorker")
    if (getattr(worker, "_nullable_cursor_v090", None) is not None
            or worker.meter["decisions"] != 0 or worker._pending is not None
            or worker._executions != 0):
        raise ValueError("Install exactly once, before any managed decision")
    definitions = {row["name"]: row["parameters"] for row in worker.definitions}
    if not CURSOR_TOOLS.issubset(definitions):
        raise ValueError("Require all four existing PROJECT cursor tools")
    # HarnessWorker construction is lazy in pinned SDK 1.49.6.  Resolve its
    # existing local tools once, without sending a message or requesting a
    # completion.  Later send_message/run reuse the same initialized instance.
    worker.conversation._ensure_agent_ready()
    agent = worker.conversation.agent
    tools = agent.tools_map
    replacements, schema_digests = {}, {}
    for name in sorted(CURSOR_TOOLS):
        if name not in definitions or name not in tools:
            raise ValueError("Require all four existing PROJECT cursor tools")
        schema, tool = definitions[name], tools[name]
        _check_schema(name, schema)
        if (not isinstance(tool.executor, _GatewayExecutor)
                or tool.executor.worker is not worker or tool.executor.name != name
                or tool.response_schema is not None):
            raise ValueError("Require the original bound managed gateway executor")
        replacements[name] = tool.set_executor(_NullableCursorExecutor(
            tool.executor, worker=worker, name=name, schema=schema))
        schema_digests[name] = hashlib.sha256(
            json.dumps(schema, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    receipt = {"version": VERSION, "tools": sorted(replacements),
               "original_schema_sha256": schema_digests,
               "SDK_globals_changed": False, "native_REF_changed": False,
               "tool_schema_changed": False, "raw_arguments_rewritten": False}
    # Match the pinned SDK's own copy-on-replacement pattern, rather than
    # mutating a read-copy returned by tools_map or a map shared by model_copy.
    # All checks succeed before changing this fresh, not-yet-stepped worker.
    with agent._tools_lock:
        current = agent._tools
        if set(current) != set(tools) or any(current[key] is not value
                                             for key, value in tools.items()):
            raise RuntimeError("Managed tool bindings changed during fresh-worker installation")
        object.__setattr__(agent, "_tools", {**current, **replacements})
    worker._nullable_cursor_v090 = copy.deepcopy(receipt)
    return receipt


def create_project_worker(*args, **kwargs):
    """Factory for a future, separately versioned PROJECT controller."""
    from .harness_sdk import HarnessWorker

    worker = HarnessWorker(*args, **kwargs)
    try:
        install_project_nullable_cursors(worker)
    except BaseException:
        worker.close()
        raise
    return worker
