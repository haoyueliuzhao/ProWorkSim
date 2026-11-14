"""Controller-side bindings to the unchanged native and managed numerical providers."""
from __future__ import annotations

from contextlib import contextmanager
import copy
import json
from pathlib import Path
import time

from .software_benchmark_exact_transport_v054 import MatchExactAdapter
from .software_benchmark_match_v054 import DispatchStopped
from .software_benchmark_normal_boundary_v054 import NormalEpisodeBoundary, known_boundary
from .storage import atomic_write, json_bytes


class HostDeadline:
    """The child only publishes deadlines; an independent host process enforces them."""
    def __init__(self, start):
        self.start = start
        self.path = Path(start["guard_path"])

    @contextmanager
    def request(self, arm):
        if time.monotonic() >= self.start["soft_at"]:
            raise NormalEpisodeBoundary("soft_deadline_before_new_dispatch")
        guard = json.loads(self.path.read_text())
        if guard["stop_requested"]:
            raise DispatchStopped("host_closed_dispatch")
        guard["request_deadline"] = min(
            self.start["hard_at"], time.monotonic() + (1860 if arm == "REF" else 660))
        atomic_write(self.path, json_bytes(guard))
        try:
            yield
        except NormalEpisodeBoundary:
            raise
        except BaseException:
            guard["stop_requested"] = True
            atomic_write(self.path, json_bytes(guard))
            raise
        finally:
            guard["stop_requested"] |= (time.monotonic() >= guard["request_deadline"]
                                        or json.loads(self.path.read_text())["stop_requested"])
            guard["request_deadline"] = None
            atomic_write(self.path, json_bytes(guard))


class RemoteLedger:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.value = {"attempts": 0, "decisions": 0, "known_actual_tokens": 0,
                      "complete_actual_tokens": 0, "per_usage_id": {}, "calls": []}

    def update(self, value):
        self.value = copy.deepcopy(value)
        atomic_write(self.directory / "ledger.json", json_bytes(self.value))

    def snapshot(self):
        return copy.deepcopy(self.value)


class RemoteMatchAdapter:
    maximum_input_tokens = MatchExactAdapter.maximum_input_tokens
    maximum_output_tokens = MatchExactAdapter.maximum_output_tokens
    temperature = MatchExactAdapter.temperature
    request_defaults = MatchExactAdapter.request_defaults

    def __init__(self, client, gate, directory):
        self.client, self.gate = client, gate
        self.ledger = RemoteLedger(directory)

    def count(self, request):
        with self.gate.request("MATCH"):
            return self.client.call("match_count", request=request)

    def complete(self, request, usage_id):
        with self.gate.request("MATCH"):
            try:
                result = self.client.call("match_complete", request=request, usage_id=usage_id)
            except BaseException:
                # The authoritative ledger remains in the model service's output,
                # including any unresolved full reservation. Do not invent usage.
                atomic_write(self.ledger.directory / "transport-unknown.json", json_bytes({
                    "actual_usage": None, "authoritative_ledger": "model-service/match-ledger/ledger.json",
                    "automatic_retry": False}))
                raise
            self.ledger.update(result["ledger"])
            if result.get("terminal_boundary"):
                boundary = result["terminal_boundary"]
                validated = known_boundary(DispatchStopped(boundary["reason"]), result["ledger"])
                if validated != boundary:
                    raise RuntimeError("Owner terminal boundary does not match its complete ledger")
                raise NormalEpisodeBoundary(boundary["reason"])
            return result["body"]


class GuardedRefAdapter:
    def __init__(self, adapter, gate, started):
        self.adapter, self.gate = adapter, gate
        self.adapter.started = started

    def __getattr__(self, name):
        return getattr(self.adapter, name)

    def count(self, request):
        with self.gate.request("REF"):
            return self.adapter.count(request)

    def complete(self, request, usage_id):
        with self.gate.request("REF"):
            try:
                return self.adapter.complete(request, usage_id)
            except DispatchStopped as error:
                if known_boundary(error, self.ledger.snapshot()) is None:
                    raise
                raise NormalEpisodeBoundary(str(error)) from error


class RemoteProjectOwner:
    """Public transport facade, never passed off as an actual CalibrationActor."""
    def __init__(self, client, tokenizer, gate, *, window_id):
        self.client, self.tokenizer, self.gate = client, tokenizer, gate
        self.identity = client.identity
        self.recipe = self.identity["recipe"]
        self.contract, self.path = self.identity["contract"], self.identity["path"]
        self.inference_profile = self.identity["inference_profile"]
        self.window_id, self.phase, self.actor_steps, self.critic_steps = window_id, "collecting", 0, 0
        self.transport = self

    def freeze_identity(self):
        return copy.deepcopy(self.identity["actor_identity"])

    def prepare_request(self, request):
        from .software_calibration_runtime_v051 import prepare_native_input
        native = prepare_native_input(self.tokenizer, request, self.contract)
        return native["rendered_prompt"], native["actual_prompt_messages"], native

    def complete(self, request, *, timeout_seconds):
        if timeout_seconds != 600:
            raise ValueError("PROJECT retains the original request timeout")
        with self.gate.request("PROJECT"):
            return self.client.call("project_complete", request=request)
