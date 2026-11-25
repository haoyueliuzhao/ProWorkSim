"""Trace one dependency edge through native receipts, relative to an actual decision boundary."""


def dependency_chain(
    outcomes, *, boundary, start, upstream, downstream, producer, consumer, known_artifact=None
):
    artifacts = {}
    deliveries = {}
    trail = []
    if known_artifact:
        artifacts[known_artifact] = dict(origin="present_at_decision", version=None)
    for ordinal, outcome in enumerate(outcomes, start):
        action = outcome.get("decision") or {}
        tool = action.get("action")
        args = action.get("arguments") or {}
        response = outcome.get("response") or {}
        result = response.get("result") or {}
        ok = response.get("ok") is True
        who = outcome.get("worker_id")
        cmd = response.get("command_id")
        if not cmd:
            continue

        def note(kind, **fields):
            trail.append(
                dict(
                    kind=kind,
                    ordinal=ordinal,
                    postdecision=ordinal > boundary,
                    actor=who,
                    command=cmd,
                    **fields,
                )
            )

        if who == producer and ok:
            if tool == "reopen_work" and args.get("task_id") == upstream:
                artifacts.clear()
                deliveries.clear()
                note("upstream_reopened")
            if (
                tool == "fix_patch"
                and upstream in args.get("task_ids", [])
                and result.get("author") == producer
                and result.get("patch_id")
            ):
                aid = result["patch_id"]
                v = result.get("source_reference")
                artifacts[aid] = dict(
                    origin="newly_fixed" if ordinal > boundary else "present_at_decision", version=v
                )
                note("fixed", artifact=aid, version=v)
            if tool in ("complete_work", "complete_evidence") and args.get("task_id") == upstream:
                aid = result.get("patch_id") or result.get("evidence_id")
                if aid:
                    artifacts.setdefault(
                        aid,
                        dict(
                            origin="first_seen_at_completion",
                            version=(result.get("identity") or {}).get("source_reference"),
                        ),
                    )
                    note("upstream_completed", artifact=aid)
            if (
                tool == "handoff_patch"
                and args.get("to_member") == consumer
                and result.get("recipient") == consumer
            ):
                aid = args.get("patch_id")
                sequence = result.get("handoff_sequence")
                if aid in artifacts and result.get("patch_id") == aid and type(sequence) is int:
                    deliveries[sequence] = aid
                    note(
                        "addressed_handoff",
                        artifact=aid,
                        origin=artifacts[aid]["origin"],
                        sequence=sequence,
                    )
        if who != consumer:
            continue
        if (
            tool == "read_work_event"
            and ok
            and result.get("kind") == "handoff"
            and result.get("sequence") in deliveries
            and result.get("recipient") == consumer
            and result.get("patch_id") == deliveries[result["sequence"]]
        ):
            note("read_handoff", artifact=result["patch_id"], sequence=result["sequence"])
        if tool in ("integrate_patch", "adopt_evidence") and ok:
            aid = args.get("patch_id") or args.get("evidence_id")
            confirms = (
                (
                    result.get("patch_id") == aid
                    and result.get("conflicts") == []
                    and result.get("conflict_count") == 0
                )
                if tool == "integrate_patch"
                else (result.get("evidence_id") == aid)
            )
            if aid in artifacts and confirms:
                note(
                    "adopted",
                    artifact=aid,
                    origin=artifacts[aid]["origin"],
                    addressed=aid in deliveries.values(),
                )
        rejection = ((response.get("error") or {}).get("rejection") or {}).get("context") or {}
        rd = result if ok and tool == "work_readiness" else rejection.get("readiness") or {}
        if rd.get("task_id") == downstream:
            gaps = rd.get("gaps", [])
            edge = [g for g in gaps if g.get("task_id") == upstream]
            for g in edge:
                aid = g.get("patch_id") or g.get("evidence_id")
                if aid:
                    artifacts.setdefault(
                        aid,
                        dict(
                            origin="present_at_decision"
                            if ordinal <= boundary
                            else "first_seen_in_blocker",
                            version=None,
                        ),
                    )
            if edge:
                note("blocked", gaps=edge)
            elif rd.get("ready") is True and gaps == []:
                note("downstream_ready")
        if (
            ok
            and tool == "begin_work"
            and args.get("task_id") == downstream
            and result.get("task_id") == downstream
        ):
            note("downstream_began")
    post = [r for r in trail if r["postdecision"]]
    end = next(
        (
            r["kind"]
            for r in reversed(post)
            if r["kind"] in ("blocked", "downstream_ready", "downstream_began", "upstream_reopened")
        ),
        None,
    )
    return dict(
        events=trail,
        last_witness=end,
        executable_at_last_witness=True
        if end in ("downstream_ready", "downstream_began")
        else False
        if end == "blocked"
        else None,
    )
