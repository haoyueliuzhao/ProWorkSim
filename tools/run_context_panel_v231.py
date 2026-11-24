"""Run complete T0/T1 pairs. Scoring uses locked candidates and separate processes."""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import fcntl
import sqlite3
from proworksim.software_graph_budget_v229 import WindowLedger
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_anomaly_development_v227 import invoke
from proworksim.software_benchmark_candidates_v054 import reference, checked
from proworksim.software_context_panel_v231 import PairedLedger, ROOT, DESIGN, RUN, panel_row
from proworksim.software_organization_api_v204 import AdmissionStopped
from proworksim.storage import atomic_write, json_bytes, read_json

PLAN = ROOT / "artifacts/software-benchmark-v231/paired-r1"


def save(path, obj):
    atomic_write(path, json_bytes(obj))


def stored_run(script, args, folder, name):
    receipt = folder / name
    if receipt.exists():
        return read_json(receipt)
    if folder.exists() or folder.with_suffix(".log").exists():
        return {
            "status": "technical_unknown",
            "error": "Existing attempt needs reconciliation",
            "path": str(folder),
        }
    return invoke(script, args, folder, name)


def score(row, branch, arm):
    result = read_json(branch / "result.json")
    if result["status"] != "closed":
        return
    for kind in ("code", "delivery"):
        folder = branch.with_name(arm + "-" + kind)
        stored_run(
            row["scorer_script"],
            ["--index", row["source_index"], "--kind", kind, "--episode", branch],
            folder,
            "receipt.json",
        )


def study():
    auth = read_json(RUN / "authority.json")
    if not auth["approved"]:
        raise ValueError("Funding decision missing")
    meter = PairedLedger.load(RUN / "authority.json")
    config = read_json(PLAN / "freeze.json")
    for f in config["files"]:
        checked(f)
    states = read_json(DESIGN)["states"]
    # Largest complete pair first, so actual low-cost closures can release the most cash.
    order = sorted(range(len(states)), key=lambda i: -states[i]["remaining_per_branch"])
    state_rows = []
    with ThreadPoolExecutor(max_workers=2) as workers, ThreadPoolExecutor(max_workers=2) as scorers:
        scores = []
        for index in order:
            state = states[index]
            case = state["case"]
            folder = RUN / case
            folder.mkdir(exist_ok=True)
            gate = folder / "pair-admission.json"
            try:
                meter.reserve_pair(state)
                if not gate.exists():
                    save(
                        gate,
                        {
                            "case": case,
                            "tokens_per_arm": state["remaining_per_branch"],
                            "time": time.time(),
                        },
                    )
            except AdmissionStopped as err:
                state_rows.append({"case": case, "status": "cash_not_admitted", "reason": str(err)})
                save(RUN / "progress.json", state_rows)
                continue
            futures = {
                arm: workers.submit(
                    stored_run,
                    "run_context_pair_v231.py",
                    ["--index", index, "--arm", arm],
                    folder / arm,
                    "result.json",
                )
                for arm in ("T0", "T1")
            }
            reverse = {f: arm for arm, f in futures.items()}
            for f in as_completed(reverse):
                arm = reverse[f]
                try:
                    result = f.result()
                    if result["status"] == "closed":
                        scores.append(scorers.submit(score, panel_row(state), folder / arm, arm))
                    state_rows.append(
                        {
                            "case": case,
                            "arm": arm,
                            "status": result["status"],
                            "error": result.get("error"),
                        }
                    )
                except Exception as exc:
                    state_rows.append(
                        {
                            "case": case,
                            "arm": arm,
                            "status": "technical_unknown",
                            "error": repr(exc),
                        }
                    )
                save(RUN / "progress.json", state_rows)
        score_errors = []
        for f in scores:
            try:
                f.result()
            except Exception as exc:
                score_errors.append(str(exc))
    save(
        RUN / "completed.json",
        {"branches": state_rows, "score_errors": score_errors, "finished": time.time()},
    )


def rehearsal_summary():
    from inspect import signature
    from proworksim.software_benchmark_deepseek_tokenizer_v055 import OfficialDeepSeekCounter

    margin = signature(OfficialDeepSeekCounter).parameters["reservation_margin_tokens"].default
    rows = []
    for index, state in enumerate(read_json(DESIGN)["states"]):
        pair = []
        for arm in ("T0", "T1"):
            folder = RUN.parent / "first-dispatch-r1" / f"{index}-{arm}"
            result = read_json(folder / "result.json")
            (manifest,) = (folder / "telemetry/worker").glob("*/manifest.json")
            evidence = read_json(manifest)
            if (
                result["status"] != "restore_verified"
                or result["provider_calls"] != 0
                or result["checkpoint"] != state["checkpoint"]
                or evidence["condition"] != arm
                or evidence["estimated_input_tokens"] != result["first_request"]["prompt_tokens"]
            ):
                raise ValueError("Incomplete first-dispatch preparation")
            pair.append(
                {
                    "case": state["case"],
                    "arm": arm,
                    "worker": result["first_member"],
                    "usage_id": result["first_request"]["usage_id"],
                    "available": result["available_at_start"],
                    "checkpoint": result["checkpoint"],
                    "graph": result["graph_sha256"],
                    "input_local": result["first_request"]["prompt_tokens"] - margin,
                    "allowed_output": result["first_request"]["max_output"],
                    "manifest": reference(manifest),
                    "result": reference(folder / "result.json"),
                }
            )
        for key in ("worker", "usage_id", "available", "checkpoint", "graph", "allowed_output"):
            if pair[0][key] != pair[1][key]:
                raise ValueError("First dispatch conditions differ: " + key)
        rows.extend(pair)
    save(
        PLAN / "first-dispatch.json",
        {"provider_calls": 0, "separate_reservation_margin": margin, "rows": rows},
    )


def funding(reuse, independent):
    """Record only the designated account; never combine, transfer, or expand balances."""
    auth_path = RUN / "authority.json"
    RUN.mkdir(parents=True, exist_ok=True)
    if auth_path.exists():
        raise ValueError("Panel already has a funding decision")
    if reuse:
        orig = read_json(
            ROOT / "artifacts/software-benchmark-v229/dev1-balance90-r1/authority.json"
        )
        db = Path(orig["ledger"])
        cap = orig["new_cap_nanoyuan"]
        with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as c:
            if c.execute("SELECT value FROM meta WHERE key='cap'").fetchone() != (str(cap),):
                raise ValueError("Existing account cap changed")
            paid = c.execute(
                "SELECT coalesce(sum(cost),0) FROM requests WHERE status='settled'"
            ).fetchone()[0]
    else:
        db = RUN / "ledger.sqlite"
        if type(independent) is not int or independent <= 0:
            raise ValueError("An independent account needs an explicit cash cap")
        cap = independent * 10**9
        WindowLedger.create_independent(
            {
                "scope": "independent",
                "ledger": str(db),
                "account_cap_CNY": independent,
                "stage_cap_CNY": independent,
            }
        )
        paid = 0
    decision = {
        "approved": True,
        "scope": "reuse-v229" if reuse else "independent",
        "cap_nanoyuan": cap,
        "ledger": str(db),
        "settled_at_registration_nanoyuan": paid,
        "available_at_registration_nanoyuan": cap - paid,
    }
    with auth_path.open("x") as f:
        f.write(json_bytes(decision).decode())


def freeze():
    files = [
        DESIGN,
        Path(__file__),
        ROOT / "tools/run_context_pair_v231.py",
        ROOT / "tools/report_context_pair_v231.py",
        PLAN / "first-dispatch.json",
        ROOT / "artifacts/software-benchmark-v228/diagnosis-supplement-launch-r2/panel.json",
        ROOT / "artifacts/software-benchmark-v229/dev1-balance90-r1/panel.json",
        ROOT / "src/proworksim/software_context_panel_v231.py",
        ROOT / "src/proworksim/software_graph_execution_v230.py",
        ROOT / "src/proworksim/software_context_builder_v230.py",
        ROOT / "src/proworksim/software_trajectory_v230.py",
    ]
    for state in read_json(DESIGN)["states"]:
        row = panel_row(state)
        g = ROOT / state["graph_receipt"]
        files.append(
            (g.parent if g.name == "assigned-graph.json" else g.parent.parent) / "common-state.json"
        )
        files.extend(
            [
                ROOT / state["graph_receipt"],
                ROOT / state["source_prefix"] / "checkpoint/manifest.json",
                ROOT / "tools" / row["scorer_script"],
                checked(row["configuration"]),
            ]
        )
    data = {
        "files": [reference(f) for f in sorted(set(files))],
        "two_generation_lanes": True,
        "max_score_workers": 2,
        "historical_controller_decision_shared": True,
        "paired_same_remaining_tokens": True,
        "cash_gate": "Before each complete pair, reserve both remaining token envelopes at the maximum output rate; release on close.",
    }
    path = PLAN / "freeze.json"
    if path.exists() and read_json(path) != data:
        raise ValueError("Registered source has changed")
    save(path, data)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--freeze", action="store_true")
    mode.add_argument("--fund-from-v229", action="store_true")
    mode.add_argument("--fund-independent-cny", type=int)
    a = p.parse_args()
    if a.freeze:
        rehearsal_summary()
        freeze()
    elif a.fund_from_v229 or a.fund_independent_cny is not None:
        RUN.mkdir(parents=True, exist_ok=True)
        with (RUN / "coordinator.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            funding(a.fund_from_v229, a.fund_independent_cny)
    else:
        with (RUN / "coordinator.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            study()
            from report_context_pair_v231 import report

            save(PLAN / "results.json", report())
