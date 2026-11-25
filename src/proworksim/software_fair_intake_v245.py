"""Passive capture for separately registered ordinary jobs under the fair contract."""

from pathlib import Path

from .software_event_harness_v243 import run_worker_fragment
from .software_fair_delivery_v245 import FairWorld
from .software_benchmark_candidates_v054 import reference
from .storage import atomic_write, json_bytes, read_json

QUOTAS = {"A1": 2, "A2": 2, "A3": 2, "A4": 2}
ROOT = Path(__file__).resolve().parents[2]
BANK = ROOT / "runs/software-benchmark-v245/prospective-r1"
EXPOSED = ROOT / "artifacts/software-benchmark-v244/midtask15-r1/roster.json"


def observe_ordinary(
    prepared,
    runtime,
    *,
    registration_file,
    folder,
    history=(),
    on_opportunity=None,
    native_run=None,
):
    """The ordinary evaluator owns scoring and cash. This hook only saves eligible sites."""
    registration_file = Path(registration_file).resolve()
    entry = read_json(registration_file)
    job = Path(runtime.owner.folder).parent.resolve()
    if (
        registration_file.parent != BANK / "ordinary-registrations"
        or entry["source"] != "ordinary"
        or Path(entry["job_root"]).resolve() != job
        or not job.is_relative_to(ROOT / "runs")
        or [entry["instance"]] != list(prepared.source_provider.case_ids)
        or entry["instance"] in {r["instance"] for r in read_json(EXPOSED)["roster"]}
        or not isinstance(prepared.world, FairWorld)
        or prepared.world.protocol().get("graph_control", {}).get("versions")
    ):
        raise ValueError(
            "Prospective intake requires a registered independent, pre-policy ordinary job"
        )
    root = Path(folder).resolve()
    if root.parent != job:
        raise ValueError("Capture belongs to another job")

    def record(outcome):
        if on_opportunity:
            on_opportunity(outcome)
        # The underlying observer captures the just-settled action before this callback.
        for path in root.glob(f"*-{runtime.opportunities}/capture.json"):
            site = read_json(path)
            if (
                site.get("scope") != "event"
                or site["node"]["anomaly_type"] not in QUOTAS
                or site["parent_condition"] != "ordinary"
                or site["complementary_only"]
                or not site["capacity"]["enough"]
            ):
                continue
            ticket = dict(
                registration=reference(registration_file),
                capture=reference(path),
                instance=entry["instance"],
                kind=site["node"]["anomaly_type"],
                command=(outcome.get("response") or {}).get("command_id"),
                model_call=(outcome.get("decision") or {}).get("model_tool_call_id"),
            )
            if ticket["command"] and ticket["model_call"]:
                inbox = BANK / "inbox"
                inbox.mkdir(parents=True, exist_ok=True)
                atomic_write(inbox / (site["checkpoint"] + ".json"), json_bytes(ticket))

    return run_worker_fragment(
        prepared,
        runtime,
        source="ordinary",
        folder=root,
        history=history,
        on_opportunity=record,
        native_run=native_run,
    )
