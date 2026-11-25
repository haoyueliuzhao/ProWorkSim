"""Consume ordinary-Worker captures in priority order, reserving a whole pair before dispatch."""

from pathlib import Path
import fcntl
import sqlite3
from contextlib import closing
import sys
import subprocess

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_event_pairs_v243 as panel
from proworksim.software_benchmark_candidates_v054 import checked, reference
from proworksim.software_three_graph_v240 import build
from proworksim.software_context_panel_v231 import PairedLedger
from prepare_osa_states_v236 import evidence
from run_offline_scorer_v096 import launch_spec
from proworksim.storage import read_json
from proworksim.software_organization_api_v204 import AdmissionStopped

PLAN, RUN, ROOT = panel.PLAN, panel.RUN, panel.ROOT


def enroll(entry):
    info = read_json(entry)
    src = checked(info["capture"]).parent
    if not src.is_relative_to(ROOT / "runs") or checked(info["registration"]).parent != src:
        raise ValueError("Foreign source")
    site = read_json(src / "capture.json")
    ctx = read_json(src / "registration.json")
    if (
        site["parent_condition"] != "ordinary"
        or site["complementary_only"]
        or site["scope"] != "event"
        or not site["capacity"]["enough"]
        or ctx["base_versions"] != 0
    ):
        raise ValueError("Not an independent admissible event")
    reg = ctx["registration"]
    # Use the same task and official scorer as the normal run; check against its registered panel.
    panels = {
        "v217": ("score_project_relations_v217_1.py", "candidate-tasks.json"),
        "v216": ("score_real_adaptation_v216.py", "candidate-tasks.json"),
    }
    script, filename = panels[reg["panel"]]
    registry = ROOT / f"artifacts/software-benchmark-{reg['panel']}/protocol-r1" / filename
    (task,) = [
        r
        for r in read_json(registry)["rows"]
        if r["index"] == reg["index"] and r["instance_id"] == reg["instance"]
    ]
    checked(task["configuration"])
    proof = read_json(src / "checkpoint/manifest.json")
    if (
        proof["identity"] != site["checkpoint"]
        or site["prefix_tokens"] != proof["prefix_tokens"]
        or site["capacity"]["remaining"] != 5000000 - proof["prefix_tokens"]
    ):
        raise ValueError("Historical usage or source differs")
    history = read_json(src / "observations.json")
    last = history[-1]
    if (
        last["ordinal"] != site["ordinal"]
        or (last["outcome"].get("decision") or {}).get("model_tool_call_id")
        != ctx["model_tool_call_id"]
    ):
        raise ValueError("Opportunity differs")
    job = Path(reg["job_root"]).resolve()
    if not job.is_relative_to(ROOT / "runs") or not src.is_relative_to(job):
        raise ValueError("Unrelated worker run")
    found = False
    ledger = Path(reg["ledger"]).resolve()
    if not ledger.is_relative_to(ROOT / "runs"):
        raise ValueError("Unregistered ledger location")
    with closing(sqlite3.connect(ledger.as_uri() + "?mode=ro", uri=True)) as db:
        for api in ("api", "physical-api"):
            for f in (job / api).glob("*/response.json"):
                body = read_json(f)
                if not any(
                    c.get("id") == ctx["model_tool_call_id"]
                    for c in body["choices"][0]["message"].get("tool_calls") or []
                ):
                    continue
                req = read_json(f.with_name("request.json"))["payload"]
                if req["member_id"] != site["observer"]:
                    continue
                found = db.execute(
                    "select 1 from requests where provider_id=? and status='settled' and slot=?",
                    (body["id"], req["team_slot_id"]),
                ).fetchone()
                if found:
                    break
            if found:
                break
    if not found:
        raise ValueError("No settled worker call backing capture")
    node = site["node"]
    menu = site["menu"]
    kind = node["anomaly_type"]
    by_cmd = {
        x["outcome"]["response"]["command_id"]: x["outcome"]
        for x in history
        if (x["outcome"].get("response") or {}).get("command_id")
        and x["outcome"].get("worker_id") == site["observer"]
    }
    commands = [e["command_id"] for e in node["evidence_refs"]]
    case = kind + "-" + task["instance_id"].split("__")[-1] + "-" + proof["identity"][:8]
    row = dict(
        id=case,
        instance=task["instance_id"],
        reference_type=kind,
        observer=site["observer"],
        graph=menu["graph"],
        options=menu["options"],
        targets=node["affected_work"],
        work_status=ctx["work_status"],
        available_tokens=site["capacity"]["remaining"],
        evidence={f"E{i}": evidence(by_cmd[k]) for i, k in enumerate(commands, 1)},
        provenance=dict(commands=commands, checkpoint=proof["identity"]),
    )
    project, obligations, routes = build(row)
    if not routes:
        raise ValueError("No executable route")
    labels = {
        "A1": "repair_target",
        "A2": "release_upstream",
        "A3": "resolve_conflict",
        "A4": "independent_review",
    }
    relevant = sorted(k for k, v in obligations.items() if v["label"] == labels[kind])
    row["probe_id"] = relevant[0] if relevant else sorted(obligations)[0]
    panel.previous.freeze(
        src / "three-graphs.json",
        dict(
            project=project,
            obligations=obligations,
            organization=menu["graph"],
            checkpoint=proof["identity"],
        ),
    )
    item = dict(
        case=case,
        instance=row["instance"],
        kind=kind,
        row=row,
        task=task,
        configuration=task["configuration"],
        initial_budget=row["available_tokens"],
        pair_hold_nanoyuan=2 * row["available_tokens"] * 8000,
        checkpoint=proof["identity"],
        score_script=script,
        score_index=task["index"],
        state=dict(
            case=case,
            source_prefix=str(src.relative_to(ROOT)),
            checkpoint=proof["identity"],
            shared_prefix_usage=proof["prefix_tokens"],
        ),
    )
    return item


def main():
    RUN.mkdir(parents=True, exist_ok=True)
    records = []
    with (RUN / "queue.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        active = {
            r["instance"]: r["kind"]
            for f in PLAN.glob("*/protocol.json")
            for r in read_json(f)["roster"]
        }
        candidates = []
        for entry in sorted((RUN / "inbox").glob("*.json")):
            try:
                candidates.append(enroll(entry))
            except Exception as exc:
                records.append(dict(entry=entry.stem, status="not_admitted", error=repr(exc)))
        for r in sorted(
            candidates, key=lambda r: (panel.capture.PRIORITY.index(r["kind"]), r["case"])
        ):
            kind, case = r["kind"], r["case"]
            specfile = PLAN / case / "protocol.json"
            if (RUN / case / "completed.json").is_file():
                continue
            if not specfile.exists() and (
                r["instance"] in active
                or list(active.values()).count(kind) >= panel.capture.GOALS[kind]
            ):
                records.append(dict(case=case, status="quota_or_same_task"))
                continue
            try:
                # Atomic full-price reservation; reuse only if identical to the existing block.
                panel.previous.prior.paired.reserve(
                    RUN / "authority.json",
                    dict(
                        case=case,
                        account_cap_nanoyuan=230000000000,
                        arm_limit=r["initial_budget"],
                        worst_pair_nanoyuan=r["pair_hold_nanoyuan"],
                    ),
                    namespace=panel.NS,
                    block=panel.NS + ":" + case,
                )
            except (AdmissionStopped, ValueError) as exc:
                if (
                    isinstance(exc, ValueError)
                    and str(exc) != "Insufficient funds for this complete pair"
                ):
                    raise
                records.append(dict(case=case, status="deferred_cash"))
                continue
            spec = panel.previous.spec_for(r)
            baseline = read_json(PLAN / panel.CASE / "protocol.json")
            spec.update(
                protocol=baseline["protocol"],
                files=baseline["files"] + [reference(Path(__file__))],
                resources=dict(remaining=r["initial_budget"]),
                orders=panel.orders.orders(r["row"]),
            )
            panel.previous.freeze(specfile, spec)
            active[r["instance"]] = kind
            command, env = launch_spec([str(Path(panel.__file__)), "--case", case])
            code = subprocess.run(command, env=env, cwd=ROOT).returncode
            records.append(
                dict(case=case, returncode=code, status="ran" if code == 0 else "execution_error")
            )
        panel.save(
            PLAN / "ordinary-intake.json",
            dict(
                entries=records,
                registered=active,
                reviewed_inputs=len(list((RUN / "inbox").glob("*.json"))),
            ),
        )


if __name__ == "__main__":
    main()
