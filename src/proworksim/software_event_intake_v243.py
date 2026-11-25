"""Ordinary harness entry: publish a registration sidecar for real settled observations."""

from pathlib import Path
import subprocess
from . import software_event_harness_v243 as observer
from .software_benchmark_candidates_v054 import reference
from .software_fixed_organization_clone_v131 import clone_function
from .storage import atomic_write, json_bytes, read_json


class NaturalCapture(observer.PassiveCapture):
    def observe(self, ordinal, outcome):
        found = super().observe(ordinal, outcome)
        actor = outcome.get("worker_id")
        if actor in self.views:
            # A5 is a team delivery condition and can legitimately have no scoped package.
            found.extend(
                n
                for n in self.views[actor].nodes.values()
                if n["anomaly_type"] == "A5"
                and not n["affected_work"]
                and n["status"] in ("OPEN", "ACTIVE", "REOPENED")
                and n["evidence_refs"][-1]["opportunity"] == ordinal
            )
        return found


def normal_registration(job):
    repo = Path(__file__).resolve().parents[2]
    manifest = job / "actor/source-manifest.json"
    if not manifest.is_file():
        return None
    (record,) = read_json(manifest)["tasks"]
    identity = record["source_identity"]
    for panel in ("v217", "v216"):
        path = repo / f"artifacts/software-benchmark-{panel}/protocol-r1/candidate-tasks.json"
        for row in read_json(path)["rows"]:
            if (row["instance_id"], row["repo"], row["base_commit"]) == (
                record["task_id"],
                identity["repo"],
                identity["base_commit"],
            ):
                authority = repo / "runs/software-benchmark-v243/event-pairs-r1/authority.json"
                return dict(
                    panel=panel,
                    index=row["index"],
                    instance=row["instance_id"],
                    job_root=str(job.resolve()),
                    ledger=read_json(authority)["ledger"],
                )
    return None


def run_ordinary(
    prepared,
    runtime,
    *,
    folder=None,
    history=(),
    on_opportunity=None,
    registration=None,
    native_run=None,
):
    root = (
        Path(folder)
        if folder is not None
        else Path(runtime.owner.folder).parent / "passive-captures"
    )
    status = []

    def register(o):
        idx = runtime.opportunities
        try:
            for p in sorted(root.glob(f"*-{idx}/capture.json")):
                site = read_json(p)
                if (
                    site["scope"] != "event"
                    or site["complementary_only"]
                    or not site["capacity"]["enough"]
                ):
                    continue
                enrollment = registration or normal_registration(root.parent)
                if enrollment is None:
                    continue
                tasks = site["node"]["affected_work"]
                cmd = (o.get("decision") or {}).get("model_tool_call_id")
                if not cmd:
                    continue
                context = dict(
                    registration=enrollment,
                    model_tool_call_id=cmd,
                    base_versions=site["menu"]["base_version"],
                    work_status={
                        t: dict(
                            completed=bool(
                                prepared.world.dynamic()["work"][t].get("completion_current")
                            ),
                            authors=prepared.world.dynamic()["work"][t].get("authors", []),
                        )
                        for t in tasks
                    },
                )
                sidecar = p.with_name("registration.json")
                atomic_write(sidecar, json_bytes(context))
                inbox = (
                    Path(__file__).resolve().parents[2]
                    / "runs/software-benchmark-v243/event-pairs-r1/inbox"
                )
                inbox.mkdir(parents=True, exist_ok=True)
                atomic_write(
                    inbox / (site["checkpoint"] + ".json"),
                    json_bytes(dict(registration=reference(sidecar), capture=reference(p))),
                )
                # Durable receipt first; one short-lived dispatcher serializes admitted pairs.
                repo = Path(__file__).resolve().parents[2]
                with (inbox.parent / "dispatcher.log").open("ab") as output:
                    subprocess.Popen(
                        [
                            str(repo / ".venv/bin/python"),
                            "-E",
                            str(repo / "tools/run_offline_scorer_v096.py"),
                            str(repo / "tools/drain_event_pairs_v243.py"),
                        ],
                        cwd=repo,
                        stdin=subprocess.DEVNULL,
                        stdout=output,
                        stderr=subprocess.STDOUT,
                        start_new_session=True,
                    )
        except Exception as exc:
            status.append(dict(ordinal=idx, error=repr(exc)))
        if on_opportunity:
            return on_opportunity(o)

    run = clone_function(
        observer.run_worker_fragment,
        {**observer.run_worker_fragment.__globals__, "PassiveCapture": NaturalCapture},
    )
    try:
        return run(
            prepared,
            runtime,
            folder=root,
            history=history,
            on_opportunity=register,
            source="ordinary",
            native_run=native_run,
        )
    finally:
        if status:
            atomic_write(root / "registration-errors.json", json_bytes(status))
