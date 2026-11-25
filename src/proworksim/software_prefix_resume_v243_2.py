"""Release only a scheduling stop proven to belong to a smaller, settled prefix allocation."""

from .software_graph_execution_v230 import CALL_BOUND


def resume_stage_limited_members(runtime, stage_events):
    now = runtime.team_budget.snapshot()
    repairs = []
    if (
        runtime.prepared.world.protocol()["terminal"]
        or now["held_tokens"]
        or now["available_tokens"] < CALL_BOUND
        or min(now["remaining_attempts"], now["remaining_decisions"]) < 1
        or runtime.owner.cash_boundaries
        or runtime.owner.pre_dispatch_boundaries
    ):
        return repairs
    for member, status in list(runtime.stopped.items()):
        detail = runtime.terminal_details.get(member, {})
        if (
            status != "team_budget_exhausted"
            or detail.get("limits") != ["team_max_total_tokens"]
            or member in runtime.work_ended
        ):
            continue
        sequences = {
            e["sequence"] for e in detail.get("evidence", []) if e["kind"] == "model_boundary_error"
        }
        matches = [
            e
            for e in stage_events
            if e["sequence"] in sequences
            and e["worker_id"] == member
            and e["kind"] == "model_boundary_error"
        ]
        if len(matches) != 1:
            continue
        (e,) = matches
        p = e["payload"]
        old = p["team_budget"]
        if (
            p["status"] != status
            or p.get("limits") != detail["limits"]
            or old["team_id"] != now["team_id"]
            or old["held_tokens"]
            or old["limits"] != now["limits"]
            or not 0 < old["native_allocation"] < now["native_allocation"]
            or old["available_tokens"] >= CALL_BOUND
            or runtime.policies[member]._done is not None
        ):
            continue
        runtime.stopped.pop(member)
        runtime.terminal_details.pop(member)
        runtime.waiting.pop(member, None)
        runtime.roles[member].update(
            status="ready",
            reason="The prefix allocation has ended; the continuation allocation is active.",
        )
        record = dict(
            member=member,
            source_event=e["sequence"],
            old_allocation=old["native_allocation"],
            old_available=old["available_tokens"],
            current_allocation=now["native_allocation"],
            current_available=now["available_tokens"],
            ledger_tokens=now["charged_tokens"],
        )
        runtime.recorder.record("prefix_allocation_stop_released", record, worker_id=member)
        repairs.append(record)
    return repairs


def release_on_ordinary_entry(runtime, folder):
    """Use the authenticated prefix identity in the existing restoration receipt, if present."""
    import json
    from pathlib import Path
    from .storage import read_json, atomic_write, json_bytes

    if not any(s == "team_budget_exhausted" for s in runtime.stopped.values()):
        return []
    job = Path(folder).parent if folder is not None else Path(runtime.owner.folder).parent
    receipt = job / "restore.json"
    if not receipt.is_file():
        return []
    proof = read_json(receipt)
    source_paths = {
        Path(v["source_request"]).resolve().parents[2]
        for v in proof.get("common_prefix_registration_upgrade", {}).values()
        if v.get("source_request")
    }
    if len(source_paths) != 1:
        return []
    (src,) = source_paths
    if not src.is_relative_to(Path(__file__).resolve().parents[2] / "runs") or src.name != "PREFIX":
        return []
    manifest = read_json(src / "checkpoint/manifest.json")
    if manifest["identity"] != proof.get("checkpoint_identity") or manifest[
        "prefix_tokens"
    ] != proof.get("prefix_tokens"):
        return []
    old = read_json(src / "result.json")
    if old.get("condition") != "PREFIX" and not old.get("slot", "").endswith(":PREFIX"):
        return []
    events = []
    with (src / "runtime/experience.jsonl").open("rb") as f:
        for line in f:
            if b'"model_boundary_error"' in line:
                e = json.loads(line)
                if (
                    e.get("kind") == "model_boundary_error"
                    and old.get("stage_token_limit") is not None
                    and e["payload"].get("team_budget", {}).get("native_allocation")
                    == old["stage_token_limit"]
                ):
                    events.append(e)
    records = resume_stage_limited_members(runtime, events)
    if records:
        atomic_write(
            job / "prefix-stop-repair.json",
            json_bytes(dict(checkpoint=manifest["identity"], repairs=records)),
        )
    return records
