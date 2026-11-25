"""Observe ordinary two-worker runs at settled boundaries, without dispatching a model."""

from pathlib import Path
from tempfile import TemporaryDirectory
from copy import deepcopy
from .software_passive_capture_v242_1 import PassiveCapture
from .software_graph_execution_v230 import CALL_BOUND
from .software_multitype_execution_v242 import envelope
from .software_graph_controller_v228 import menu
from .storage import atomic_write, json_bytes
from . import software_sdk_resume_v203_3_4 as resume

PRIORITY = ("A2", "A1", "A3", "A4")
GOALS = {"A2": 2, "A1": 2, "A3": 1, "A4": 1}


def artifact_state(gap):
    """Classify only explicit facts from the observing actor's readiness receipt."""
    kind = gap.get("kind")
    ident = gap.get("patch_id") or gap.get("evidence_id")
    if kind in ("upstream_patch_not_adopted", "upstream_evidence_version_not_adopted") and ident:
        return "published_not_adopted"
    # A bare missing/stale completion record is not proof about an artifact's existence.
    for field, state in (
        ("exists", "absent"),
        ("published", "unpublished"),
        ("current", "stale"),
        ("verified", "unverified"),
    ):
        if gap.get(field) is False and (field == "exists" or ident):
            return state
    return "unknown"


def work_budget(kind, remaining, attempts, decisions):
    phases = envelope("diagnosis" if kind == "A1" else "verify")
    controller = 8192
    required = sum(phases.values()) + controller
    return dict(
        osa_max=controller,
        phases=phases,
        required=required,
        remaining=remaining,
        enough=remaining >= required
        and min(attempts, decisions) >= sum(phases.values()) // CALL_BOUND,
    )


def run_worker_fragment(
    prepared,
    runtime,
    *,
    folder,
    history=(),
    on_opportunity=None,
    source="ordinary",
    native_run=None,
):
    """The ordinary job continues through its own termination after the observer window closes."""
    from . import software_natural_organization_runtime_v224_2 as native

    root = Path(folder)
    observer = PassiveCapture(root, history=history, kinds=(*PRIORITY, "A5"))
    start = runtime.opportunities
    window = 24
    recorded = set()
    last_progress = 0
    seen = []
    errors = []

    def save_site(tag, control):
        root.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(dir=root) as temp:
            dest = Path(temp) / "site"
            dest.mkdir()
            proof = resume.save(prepared, runtime, dest / "checkpoint", control_state=control)
            atomic_write(dest / "observations.json", json_bytes(observer.history))
            atomic_write(
                dest / "capture.json",
                json_bytes(
                    {
                        **control,
                        "checkpoint": proof["identity"],
                        "prefix_tokens": proof["prefix_tokens"],
                    }
                ),
            )
            dest.rename(root / tag)
        return tag

    def inspect(outcome):
        nonlocal window, last_progress
        idx = runtime.opportunities
        delta = idx - start
        response = outcome.get("response") or {}
        action = (outcome.get("decision") or {}).get("action")
        if response.get("ok") and action in {
            "replace_file",
            "write_file",
            "fix_patch",
            "integrate_patch",
            "run_tests",
            "run_patch_review_tests",
            "complete_work",
            "handoff_patch",
            "org_review_patch",
            "complete_evidence",
        }:
            last_progress = delta
        if delta > window:
            return
        budget = runtime.team_budget.snapshot()
        nodes = observer.observe(idx, outcome)
        if budget["held_tokens"] or prepared.world.protocol()["terminal"]:
            return
        common = dict(ordinal=idx, observer=outcome.get("worker_id"), parent_condition=source)
        for n in sorted(nodes, key=lambda n: (*PRIORITY, "A5").index(n["anomaly_type"])):
            kind = n["anomaly_type"]
            if kind in recorded:
                continue
            if kind == "A4" and n["subject"] not in (
                "independent_current_review",
                "evidence_version_differs_from_final_tree_revalidate",
            ):
                continue
            capacity = work_budget(
                kind,
                budget["available_tokens"],
                budget["remaining_attempts"],
                budget["remaining_decisions"],
            )
            frozen = menu(prepared.world, n, common["observer"])
            evidence = response.get("result") or {}
            if not response["ok"]:
                evidence = (
                    ((response.get("error") or {}).get("rejection") or {}).get("context") or {}
                ).get("readiness") or {}
            assets = (
                [
                    dict(gap=g, state=artifact_state(g))
                    for g in evidence.get("gaps", [])
                    if g.get("task_id") == n["subject"]
                ]
                if kind == "A2"
                else []
            )
            if kind == "A2" and not any(
                g["gap"].get("task_id") in frozen["graph"]["work"][t]["depends_on"]
                for t in n["affected_work"]
                for g in assets
            ):
                continue
            site = dict(
                **common,
                node=deepcopy(n),
                menu=frozen,
                capacity=capacity,
                artifact_states=assets,
                complementary_only=source != "ordinary" or kind == "A5",
                scope="event",
            )
            recorded.add(kind)
            tag = save_site(f"{kind}-{idx}", site)
            seen.append(
                dict(
                    kind=kind,
                    ordinal=idx,
                    site=tag,
                    capacity=capacity,
                    complementary_only=site["complementary_only"],
                )
            )
        if budget["available_tokens"] < 8 * CALL_BOUND:
            if not nodes:
                seen.append(
                    dict(
                        kind="budget_boundary",
                        site=save_site(
                            f"budget-{idx}",
                            dict(
                                **common,
                                scope="budget_boundary",
                                remaining=budget["available_tokens"],
                            ),
                        ),
                    )
                )
            window = delta
        elif delta == 24 and last_progress >= 17 and budget["available_tokens"] >= 9 * CALL_BOUND:
            window = 32

    def after(o):
        if not errors:
            try:
                inspect(o)
            except Exception as e:
                errors.append(dict(opportunity=runtime.opportunities, error=repr(e)))
        if on_opportunity:
            on_opportunity(o)

    try:
        return (native_run or native.run_fragment)(prepared, runtime, on_opportunity=after)
    finally:
        root.mkdir(parents=True, exist_ok=True)
        atomic_write(
            root / "capture-index.json",
            json_bytes(
                dict(
                    source=source,
                    start=start,
                    window=window,
                    events=seen,
                    errors=errors,
                    observer_api_calls=0,
                )
            ),
        )
