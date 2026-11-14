"""Private low-peak world persistence with unchanged JSON values and digests.

Only new v141 worlds opt in. No historical module globals, host services or
existing world files are patched. Immutable strings may be shared in memory;
mutable JSON containers are always copied.
"""
from __future__ import annotations

import ast
import hashlib
import inspect
import json
import math
import os
import re
import textwrap
from dataclasses import asdict, is_dataclass
from functools import cache
from pathlib import Path
from tempfile import NamedTemporaryFile
from types import FunctionType, SimpleNamespace

from . import scenarios, storage, world_core
from .core import journal, runner, transitions
from .core import world as core_world
from .software_fixed_organization_clone_v131 import clone_namespace
from .software_benchmark_state_cache_v054 import CachedStateStore

VERSION = "v141-private-streamed-json-world-r1"
_ENCODER = json.JSONEncoder(ensure_ascii=False, indent=2, allow_nan=False)
_CANONICAL = json.JSONEncoder(
    sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
_SPECIAL = re.compile(r'["\\]')


def clone_json(value, _active=None):
    """Match a finite JSON dump/load normalization without a full JSON string."""
    active = set() if _active is None else _active
    kind = type(value)
    if value is None or kind in (str, bool, int):
        return value
    if isinstance(value, str):
        return str(value)
    if isinstance(value, bool):
        return bool(value)
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Out of range float values are not JSON compliant")
        return float(value)
    if not isinstance(value, (dict, list, tuple)):
        raise TypeError("Object is not JSON serializable: " + kind.__name__)
    identity = id(value)
    if identity in active:
        raise ValueError("Circular reference detected")
    active.add(identity)
    try:
        if not isinstance(value, dict):
            return [clone_json(item, active) for item in value]
        result = {}
        for key, item in value.items():
            if isinstance(key, str):
                normalized = str(key)
            elif key is None or isinstance(key, (bool, int, float)):
                normalized = json.dumps(key, allow_nan=False, separators=(",", ":"))
            else:
                raise TypeError("JSON object keys must be str, int, float, bool or None")
            result[normalized] = clone_json(item, active)
        return result
    finally:
        active.remove(identity)


def validate_finite_json(value):
    # No output is accumulated. Per-string escaping is bounded by the largest
    # individual value, instead of the whole package/scenario/state.
    for _ in _ENCODER.iterencode(value):
        pass


def streamed_digest(value, *, canonical=False):
    h = hashlib.sha256()
    for part in (_CANONICAL if canonical else _ENCODER).iterencode(value):
        h.update(part.encode("utf-8"))
    if not canonical:
        h.update(b"\n")
    return h.hexdigest()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with NamedTemporaryFile(dir=path.parent, prefix=".tmp-v141-", delete=False) as stream:
            temporary = Path(stream.name)
            for part in _ENCODER.iterencode(value):
                stream.write(part.encode("utf-8"))
            stream.write(b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


class _Reader:
    """Read containers incrementally; only an individual string is buffered."""

    def __init__(self, stream, chunk_size=65536):
        self.stream, self.chunk_size = stream, chunk_size
        self.buffer, self.position, self.offset = "", 0, 0
        # Deduplication is local to this one load, not a process-global cache.
        self.strings = {}

    def peek(self):
        if self.position == len(self.buffer):
            self.offset += self.position
            self.buffer, self.position = self.stream.read(self.chunk_size), 0
        return self.buffer[self.position:self.position + 1]

    def take(self):
        char = self.peek()
        self.position += bool(char)
        return char

    def whitespace(self):
        while self.peek() and self.peek() in " \r\n\t":
            self.take()

    def error(self, message):
        raise ValueError(f"{message} at character {self.offset + self.position}")

    def string(self):
        if self.take() != '"':
            self.error("Expected a string")
        parts = ['"']
        while self.peek():
            match = _SPECIAL.search(self.buffer, self.position)
            if match is None:
                parts.append(self.buffer[self.position:])
                self.position = len(self.buffer)
                continue
            parts.append(self.buffer[self.position:match.end()])
            self.position = match.end()
            if match.group() == '"':
                value = json.loads("".join(parts))
                if len(value) >= 1024:
                    key = (len(value), hashlib.sha256(value.encode("utf-8", "surrogatepass")).digest())
                    previous = self.strings.get(key)
                    if previous is not None and previous == value:
                        return previous
                    self.strings[key] = value
                return value
            escaped = self.take()
            if not escaped:
                self.error("Incomplete string escape")
            parts.append(escaped)
        self.error("Unterminated string")

    def value(self):
        self.whitespace()
        char = self.peek()
        if char == '"':
            return self.string()
        if char == "{":
            self.take()
            result = {}
            self.whitespace()
            if self.peek() == "}":
                self.take()
                return result
            while True:
                self.whitespace()
                if self.peek() != '"':
                    self.error("Object keys must be strings")
                key = self.string()
                self.whitespace()
                if self.take() != ":":
                    self.error("Missing object colon")
                result[key] = self.value()
                self.whitespace()
                delimiter = self.take()
                if delimiter == "}":
                    return result
                if delimiter != ",":
                    self.error("Missing object separator")
        if char == "[":
            self.take()
            result = []
            self.whitespace()
            if self.peek() == "]":
                self.take()
                return result
            while True:
                result.append(self.value())
                self.whitespace()
                delimiter = self.take()
                if delimiter == "]":
                    return result
                if delimiter != ",":
                    self.error("Missing array separator")
        if not char:
            self.error("Missing JSON value")
        parts = []
        while self.peek() and self.peek() not in " \r\n\t,]}":
            parts.append(self.take())
        if not parts:
            self.error("Unexpected JSON delimiter")
        # This decoder handles numeric precision, exponents and JSON literals.
        return json.loads("".join(parts))


def read_json(path, *, chunk_size=65536):
    if type(chunk_size) is not int or chunk_size <= 0:
        raise ValueError("A positive JSON read chunk size is required")
    with Path(path).open("r", encoding="utf-8") as stream:
        reader = _Reader(stream, chunk_size)
        result = reader.value()
        reader.whitespace()
        if reader.peek():
            reader.error("Extra JSON content")
    return result


class StreamStore(storage.Store):
    def load(self):
        return read_json(self.control / "state.json")

    def save(self, state):
        atomic_json(self.control / "state.json", state)


class StreamCachedStore(CachedStateStore, StreamStore):
    """Keep the original one-state cache with streamed cache misses and saves."""


def _private(function, namespace):
    result = FunctionType(function.__code__, namespace, function.__name__,
                          function.__defaults__, function.__closure__)
    result.__kwdefaults__ = function.__kwdefaults__
    return result


def _mapping(value, label):
    if is_dataclass(value):
        value = asdict(value)
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    try:
        return clone_json(value)
    except (ValueError, TypeError) as error:
        raise ValueError(f"{label} must contain finite JSON values") from error


_core = clone_namespace(core_world, _mapping=_mapping)
_journal = SimpleNamespace(**{
    **vars(journal), "canonical_digest": lambda value: streamed_digest(value, canonical=True)})
_transitions = clone_namespace(
    transitions, canonical_digest=lambda value: streamed_digest(value, canonical=True))
_runner = {
    **vars(runner), "Store": StreamStore, "read_json": read_json,
    "journal": _journal, "execute_transition": _transitions["execute_transition"],
    "validate_finite_json": validate_finite_json,
}
_world = {**vars(world_core), "Store": StreamStore,
          "new_world_state": _core["new_world_state"], "install_package": _core["install_package"]}


def _stream_runner_action():
    tree = ast.parse(textwrap.dedent(inspect.getsource(runner.WorldRunner.act)))
    changed = 0

    class ReplaceValidation(ast.NodeTransformer):
        def visit_Expr(self, node):
            nonlocal changed
            if (isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name)
                    and node.value.func.id == "json_bytes"):
                changed += 1
                node.value.func.id = "validate_finite_json"
            return self.generic_visit(node)

    tree = ReplaceValidation().visit(tree)
    if changed != 2:
        raise ValueError("The two original discarded JSON validation expressions changed")
    compiled = {}
    exec(compile(ast.fix_missing_locations(tree), __file__ + ":bounded-act", "exec"), _runner, compiled)
    return compiled["act"]


class LowMemoryWorldCore(world_core.WorldCore):
    """A new opt-in base with the same command/transition and byte semantics."""

    __init__ = _private(runner.WorldRunner.__init__, _runner)
    _operation_identity = _private(runner.WorldRunner._operation_identity, _runner)
    act = _stream_runner_action()
    create = classmethod(_private(world_core.WorldCore.create.__func__, _world))
    _action_install_project = _private(world_core.WorldCore._action_install_project, _world)


@cache
def bind_world_type(original):
    if not issubclass(original, world_core.WorldCore):
        raise TypeError("Only an explicitly selected WorldCore implementation may opt in")
    if issubclass(original, LowMemoryWorldCore):
        return original
    if original is world_core.WorldCore:
        return LowMemoryWorldCore

    def initialize(self, root):
        original.__init__(self, root)
        # v054 installs its ordinary CachedStateStore after its super call.
        # That constructor does not read; replace it before preparation uses it.
        old_store = self.store
        self.store = StreamCachedStore(old_store.root)
        self.store.fault_hook = old_store.fault_hook

    return type(original.__name__ + "StreamedV141", (original, LowMemoryWorldCore),
                {"__module__": __name__, "__init__": initialize, "memory_revision": VERSION})


def _scenario_validator():
    tree = ast.parse(textwrap.dedent(inspect.getsource(scenarios.validate_scenario)))
    changed = 0

    class ReplaceNormalization(ast.NodeTransformer):
        def visit_Call(self, node):
            nonlocal changed
            if ast.unparse(node) == "json.loads(json.dumps(spec, allow_nan=False))":
                changed += 1
                return ast.copy_location(ast.Call(func=ast.Name(id="clone_json", ctx=ast.Load()),
                                                 args=[ast.Name(id="spec", ctx=ast.Load())], keywords=[]), node)
            return self.generic_visit(node)

    tree = ReplaceNormalization().visit(tree)
    if changed != 1:
        raise ValueError("The original scenario normalization expression changed")
    compiled = {}
    exec(compile(ast.fix_missing_locations(tree), __file__ + ":bounded-scenario", "exec"),
         {**vars(scenarios), "clone_json": clone_json}, compiled)
    return compiled["validate_scenario"]


def save_deployment(deployment, root=None):
    if deployment.world is None:
        raise ValueError("No created world to persist")
    if root is not None and Path(root).resolve() != deployment.world.store.root.resolve():
        raise ValueError("Deployment manifest belongs to its created world")
    record = {
        "version": scenarios.SCENARIO_VERSION,
        "world_id": deployment.world.state["world_id"],
        "instance_id": deployment.world.state["instance_id"],
        "scenario_sha256": streamed_digest(deployment.spec),
        "spec": deployment.spec, "status": deployment.status,
        "diagnostics": deployment.diagnostics, "deployment_log": deployment.deployment_log,
        "prefix": deployment.prefix,
    }
    path = deployment.world.store.control / "scenario.json"
    atomic_json(path, record)
    return path


build_scenario = _private(scenarios.build_scenario, {
    **vars(scenarios), "WorldCore": LowMemoryWorldCore,
    "validate_scenario": _scenario_validator(), "save_deployment": save_deployment})
