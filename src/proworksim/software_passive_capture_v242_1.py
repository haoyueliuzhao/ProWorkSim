"""Opt-in snapshot at a natural, settled Worker opportunity; takes no organization action."""

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory

from .software_anomaly_graph_v226 import AnomalyGraph
from .software_graph_execution_v230 import CALL_BOUND
from .storage import atomic_write, json_bytes


class PassiveCapture:
    def __init__(self, folder, *, history=(), kinds=("A1", "A2", "A3")):
        self.folder = Path(folder)
        self.kinds = frozenset(kinds)
        self.views = {m: AnomalyGraph(m) for m in ("member_001", "member_002")}
        self.history = []
        self.events = []
        self.attempted = set()
        self.disabled = False
        for item in history:
            self.observe(item["ordinal"], item["outcome"])

    def observe(self, ordinal, outcome):
        self.history.append(dict(ordinal=ordinal, outcome=outcome))
        actor = outcome.get("worker_id")
        if actor not in self.views:
            return []
        view = self.views[actor]
        view.observe(ordinal, outcome)
        return [
            node
            for node in view.nodes.values()
            if node["anomaly_type"] in self.kinds
            and node["affected_work"]
            and node["status"] in ("OPEN", "ACTIVE", "REOPENED")
            and node["evidence_refs"][-1]["opportunity"] == ordinal
        ]

    def after(self, prepared, runtime, outcome):
        from . import software_sdk_resume_v203_3_4 as resume

        ordinal = runtime.opportunities
        for node in self.observe(ordinal, outcome):
            kind = node["anomaly_type"]
            if kind in self.attempted or prepared.world.protocol()["terminal"]:
                continue
            budget = runtime.team_budget.snapshot()
            if budget["available_tokens"] < 8 * CALL_BOUND or budget["held_tokens"]:
                continue
            self.attempted.add(kind)
            tag = f"{kind}-{ordinal}"
            # Publish the SDK state and both unmodified members' histories together.
            # The observer has no path into either member's prompt or scheduling queue.
            try:
                self.folder.mkdir(parents=True, exist_ok=True)
                with TemporaryDirectory(dir=self.folder) as temp:
                    staged = Path(temp) / "snapshot"
                    staged.mkdir()
                    control = dict(
                        node=deepcopy(node), ordinal=ordinal, observer=outcome["worker_id"]
                    )
                    proof = resume.save(
                        prepared, runtime, staged / "checkpoint", control_state=control
                    )
                    atomic_write(staged / "observations.json", json_bytes(self.history))
                    staged.rename(self.folder / tag)
                self.events.append(
                    dict(
                        kind=kind,
                        ordinal=ordinal,
                        status="saved",
                        checkpoint=proof["identity"],
                        path=tag,
                    )
                )
            except Exception as exc:
                self.events.append(
                    dict(kind=kind, ordinal=ordinal, status="capture_error", error=repr(exc))
                )

    def callback(self, prepared, runtime, downstream=None):
        def settled(outcome):
            if not self.disabled:
                try:
                    self.after(prepared, runtime, outcome)
                except Exception as exc:
                    self.disabled = True
                    self.events.append(
                        dict(
                            status="observer_error", ordinal=runtime.opportunities, error=repr(exc)
                        )
                    )
            if downstream is not None:
                return downstream(outcome)

        return settled
