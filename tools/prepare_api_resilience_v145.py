"""Seal a read-only cash/source handoff for future API recovery; run nothing.

This does not create a ledger, client, HTTP request, service, or container.
It preserves historical unknown attempts and only freezes their remaining cash.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path

from proworksim import software_benchmark_deepseek_api_v145 as api
from proworksim.software_benchmark_candidates_v054 import reference

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "runs/software-benchmark-v142/role-pilot40-r1"
STATE = BASE / "deployment-v143"
OUTPUT = ROOT / "artifacts/software-benchmark-v145/api-deployment-preparation-r2"
CHILD_LEDGER = ROOT / "runs/software-benchmark-v145/api-recovery-prepared-r1/ledger.sqlite"


def read(path):
    return json.loads(Path(path).read_text())


def available_nanoyuan(value):
    number = Decimal(value)
    if (
        not number.is_finite()
        or number < 0
        or number > 400
        or number * 10**9 != int(number * 10**9)
    ):
        raise ValueError("Only an exact nonnegative remainder within the existing CNY400 cap")
    return int(number * 10**9)


def disk_identity(path):
    path = Path(path)
    value = {"path": str(path), "exists": path.exists()}
    if path.exists():
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for part in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(part)
        value.update(sha256=digest.hexdigest(), bytes=path.stat().st_size)
    return value


def prepare(*, output=OUTPUT, expected_available_cny="49.1863482"):
    expected = available_nanoyuan(expected_available_cny)
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError("Never overwrite an existing preparation record")
    if not output.is_relative_to(ROOT / "artifacts/software-benchmark-v145"):
        raise ValueError("Preparation output must remain inside its new v145 artifact directory")
    ledger = BASE / "ledgers/pilot.sqlite"
    before = [disk_identity(ledger), disk_identity(str(ledger) + "-wal")]
    progress_path = STATE / "api-coordinator/progress.json"
    progress = read(progress_path)
    if (
        progress.get("phase") != "closed"
        or any(
            progress.get(k) != 0
            for k in (
                "generation_active",
                "candidate_preparation_active_or_queued",
                "scoring_active",
                "scoring_pending",
            )
        )
        or any(progress.get("generation_pending", {}).values())
    ):
        raise ValueError("The prior pipeline must be closed and have no active/pending work")
    final_path = STATE / "api-coordinator/coordinator-finalization.json"
    final = read(final_path)
    release_path = Path(final["coordinator_release"]["path"])
    if final.get("cleanup_errors") != [] or read(release_path).get("released") is not True:
        raise ValueError("Prior coordinator cleanup/release is not proven")
    plan_path = STATE / "execution-plan.json"
    plan = read(plan_path)
    if len(plan["rows"]) != 120 or len({r["slot_index"] for r in plan["rows"]}) != 120:
        raise ValueError("The prior pilot identity must remain exactly its120 attempts")
    quiet_refs = []
    folders = [BASE / "episodes" / str(r["slot_index"]) for r in plan["rows"]]
    folders += [BASE / f"diagnostic-{r['index']}" for r in plan["diagnostics"]]
    for folder in folders:
        quiet_path = folder / "quiescence.json"
        quiet = read(quiet_path)
        if (
            quiet.get("quiescent") is not True
            or quiet.get("all_owned_objects_removed") is not True
            or quiet.get("cleanup_errors") != []
            or quiet.get("retained_objects") != []
        ):
            raise ValueError(
                "An original actor/controller or volume remains unproven: " + folder.name
            )
        quiet_refs.append(reference(quiet_path))
    authority = {
        **api.prior_cash_snapshot(ledger),
        "child_ledger_path": str(CHILD_LEDGER.resolve()),
    }
    if authority["available_nanoyuan"] != expected:
        raise ValueError("The requested frozen remainder differs from the read-only prior ledger")
    after = [disk_identity(ledger), disk_identity(str(ledger) + "-wal")]
    if before != after:
        raise ValueError("Historical SQLite database or WAL changed during preparation")
    # Do not open BudgetLedger/DeepSeekClient: preparation cannot consume money.
    output.mkdir(parents=True, exist_ok=False)
    authority_path = output / "cash-authority.json"
    with authority_path.open("x") as stream:
        json.dump(authority, stream, ensure_ascii=False, indent=2)
    module_paths = [
        ROOT / "src/proworksim/software_benchmark_deepseek_api_v145.py",
        ROOT / "src/proworksim/software_benchmark_host_api_v145.py",
        Path(__file__).resolve(),
        ROOT / "tests/test_deepseek_resilience_v145.py",
    ]
    manifest = {
        "version": "v145-api-recovery-deployment-preparation-r2",
        "prepared_utc": datetime.now(timezone.utc).isoformat(),
        "state": "prepared_not_started",
        "cash_authority": reference(authority_path),
        "unique_child_ledger_path": str(CHILD_LEDGER.resolve()),
        "supersedes_preparation_only": reference(
            ROOT / "artifacts/software-benchmark-v145/api-deployment-preparation-r1/manifest.json"
        ),
        "remaining_CNY": str(Decimal(expected) / 10**9),
        "original_total_cap_CNY": "400",
        "additional_budget_CNY": "0",
        "new_api_calls": 0,
        "new_model_episodes": 0,
        "new_containers": 0,
        "new_services": 0,
        "new_ledgers": 0,
        "old_ledger_mutated": False,
        "original_database_and_WAL_before": before,
        "original_database_and_WAL_after": after,
        "prior_progress": reference(progress_path),
        "prior_finalization": reference(final_path),
        "prior_capacity_release": reference(release_path),
        "prior_plan": reference(plan_path),
        "prior_frozen_sources": reference(STATE / "runtime-sources.json"),
        "prior_statuses": dict(Counter(progress["prepared_statuses"])),
        "quiescence_records": quiet_refs,
        "new_source_files": [reference(p) for p in module_paths],
        "transport_policy": {
            "max_http_attempts_per_logical_request": 3,
            "retry_http_statuses": sorted(api.RETRY_STATUSES),
            "unknown_timeout_disconnect_parse_retry": False,
            "failed_cash_and_token_upper_retained": True,
            "actual_usage_filled_from_reservations": False,
            "single_success_clears_breaker": False,
            "wait_holds_http_permit": False,
        },
        "validation": {
            "command": ".venv/bin/python -m pytest -q tests/test_deepseek_resilience_v145.py",
            "CPU_tests_passed": 23,
            "real_API_acceptance": False,
            "live_runtime_migrated": False,
        },
        "activation_requires": "A separate frozen deployment, approved attempt identities and scope guard; this manifest does not authorize replay or start a run.",
    }
    with (output / "manifest.json").open("x") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--expected-available-cny", default="49.1863482")
    args = parser.parse_args()
    result = prepare(output=args.output, expected_available_cny=args.expected_available_cny)
    print(
        json.dumps(
            {
                k: result[k]
                for k in (
                    "state",
                    "cash_authority",
                    "remaining_CNY",
                    "new_api_calls",
                    "old_ledger_mutated",
                )
            },
            ensure_ascii=False,
            indent=2,
        )
    )
