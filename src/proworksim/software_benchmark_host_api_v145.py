"""New-deployment host binding for v145 recovery; unchanged managed tool schema.

The scope guard is injected by the new sealed runner. The frozen v142 host and
its ledger are never rebound. Retry waits occur inside the client, outside any
host HTTP permit, while each team still serializes its actual member actions.
"""

from __future__ import annotations

import copy
from pathlib import Path
import threading
from types import SimpleNamespace

from . import software_benchmark_host_api_v142 as old_host
from .software_benchmark_deepseek_api_v142 import _private
from .storage import digest, json_bytes


class HostTeamTransport:
    port, timeout_seconds = 18219, 1800

    def __init__(self, runtime, row, output):
        self.runtime, self.row = runtime, copy.deepcopy(row)
        self.slot_id, self.condition_id = row["slot_id"], row["condition_id"]
        self.group = row["organization_id"]
        self.client = runtime.clients[self.group].fork_for_episode()
        if self.client.http_slots is not runtime.http_slots:
            raise ValueError("All episode clients must share the actual runtime HTTP limit")
        self.folder = Path(output) / "host-api-counts"
        self.folder.mkdir(parents=True, exist_ok=True)
        self._lock, self.cancelled = threading.RLock(), threading.Event()
        self._counts_only = _private(
            old_host.HostTeamTransport.post, api_for=lambda group: runtime.apis[group]
        )

    validate_identity = old_host.HostTeamTransport.validate_identity
    abort = old_host.HostTeamTransport.abort

    def post(self, path, payload):
        if path in {"/tokenize", "/tokenize-prefix"}:
            # This reused branch returns before frozen scope/API dispatch checks.
            return self._counts_only(self, path, payload)
        if path != "/chat/completions":
            raise ValueError("No search, fetch, arbitrary URL or provider tool route")
        api = self.runtime.apis[self.group]
        member = payload.get("member_id")
        common = {
            "wire",
            "member_id",
            "team_slot_id",
            "request_id",
            "slot_id",
            "condition",
            "usage_id",
            "prompt_upper_bound",
        }
        if (
            set(payload) != common
            or payload["team_slot_id"] != self.slot_id
            or payload["slot_id"] != self.slot_id
            or payload["condition"] != self.condition_id
            or member not in self.row["fixed_members"]
            or payload["usage_id"] not in {"agent", "condenser"}
        ):
            raise ValueError("The frozen team/member/request identity changed")
        wire = payload["wire"]
        if wire.get("user_id") != api.slot_user_id(self.slot_id + ":" + member, self.condition_id):
            raise ValueError("Member cache identity changed")
        api.validate_payload(wire, self.client.allowed_tool_names)
        expected = {
            item["function"]["name"]: item for item in self.runtime.schemas[self.group][member]
        }
        supplied = {item["function"]["name"]: item for item in wire.get("tools", [])}
        if (
            payload["usage_id"] == "agent"
            and supplied != expected
            or payload["usage_id"] == "condenser"
            and supplied
        ):
            raise ValueError("Actual member schema or request purpose changed")
        with self._lock:
            if self.cancelled.is_set():
                raise api.PreDispatchBudgetStopped("owned_team_stopped_before_dispatch")
            self.runtime.authorize(
                "v145.api.request", slot_id=self.slot_id, instance_id=self.row["instance_id"]
            )
            measured = self.runtime.counter(wire)
            if (
                measured["request_sha256"] != digest(json_bytes(wire))
                or measured["prompt_tokens"] != payload["prompt_upper_bound"]
            ):
                raise ValueError("Host/controller original-member token reservations differ")
            return self.client.complete(
                wire,
                **{k: v for k, v in payload.items() if k not in {"wire", "team_slot_id"}},
                cancel_event=self.cancelled,
            )


def runtime_for(*, apis, schemas, counter, authorize, api_key, max_concurrency):
    """Construct a host runtime only; no listener, container or model request."""
    if not apis:
        raise ValueError("An explicit organization API inventory is required")
    policies = [api.POLICY for api in apis.values()]
    if any(policy != policies[0] for policy in policies[1:]):
        raise ValueError("All groups must share one exact ledger/cash authority/policy")
    if not policies[0].get("child_ledger_path") or not policies[0].get("cash_authority"):
        raise ValueError("A bound child ledger and frozen cash authority are required")
    if any(api.group_id != group for group, api in apis.items()):
        raise ValueError("API organization views must retain their declared identities")
    runtime = SimpleNamespace(
        apis=apis,
        schemas=schemas,
        counter=counter,
        authorize=authorize,
        http_slots=threading.BoundedSemaphore(max_concurrency),
        clients={},
    )
    for group, api in apis.items():
        if api.POLICY["max_concurrency"] != max_concurrency:
            raise ValueError("HTTP permit limit and immutable cash policy differ")
        names = {
            item["function"]["name"]
            for member_tools in schemas[group].values()
            for item in member_tools
        }
        runtime.clients[group] = api.DeepSeekClient(
            api_key=api_key, allowed_tool_names=names, http_slots=runtime.http_slots
        )
    return runtime
