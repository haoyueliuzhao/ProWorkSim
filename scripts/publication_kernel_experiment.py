"""Cross-template kernel reuse with two actor configurations and erroneous work."""

import argparse
import copy
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from proworksim.audit import code_identity
from proworksim.domains.publication import (
    PublicationWorld,
    compile_publication,
    evaluate_publication,
    SOURCE_REF,
)
from proworksim.storage import atomic_write, json_bytes


ACTORS = [
    {"author": "author", "editor": "editor"},
    {"author": "researcher-61", "editor": "signatory-84"},
]


def run_case(root, names, mode):
    label = ("default" if names["author"] == "author" else "renamed") + "-" + mode
    world = PublicationWorld(compile_publication(root / label, names))
    author, editor = names["author"], names["editor"]
    checks = []

    def check(name, condition, observed=None):
        checks.append({"name": name, "passed": bool(condition), "observed": observed})
        if not condition:
            raise AssertionError(name)

    def act(actor, action, **args):
        result = world.act(actor, action, args)
        if not result["ok"]:
            raise AssertionError(f"{action}: {result}")
        return result["result"]

    def write(version, body, source=SOURCE_REF):
        return act(
            author,
            "write_file",
            artifact_id="draft",
            content=json.dumps({"title": "Synthetic release", "body": body, "source_ref": source}),
            dependencies=[SOURCE_REF, {"artifact_id": "editorial_policy", "version_id": version}],
        )

    try:
        act(author, "read_file", artifact_id="source_note")
        act(author, "read_file", artifact_id="editorial_policy")
        if mode == "erroneous":
            write(
                "v1",
                "Unsupported description",
                {"artifact_id": "unestablished_source", "version_id": "v9"},
            )
            sub = act(author, "submit", work_item_id="publish-note")
            act(editor, "approve", work_item_id="publish-note", submission_id=sub["submission_id"])
            evaluation = evaluate_publication(world)
            check("erroneous_work_is_writable_and_submittable", True)
            check(
                "authorized_review_does_not_imply_independent_correctness",
                evaluation["business_accepted"] and not evaluation["passed"],
                evaluation,
            )
        else:
            write("v1", "READY. Synthetic demonstration")
            act(author, "submit", work_item_id="publish-note")
            act(author, "wait", ticks=2)
            first = copy.deepcopy(
                world.store.load()["work_items"]["publish-note"]["submissions"][0]
            )
            check("first_delivery_passes", evaluate_publication(world)["passed"])
            draft_before = world.store.content(world.store.load()["artifacts"]["draft"])
            policy2 = act(
                editor, "confirm", required_phrases=["READY", "Edition two"], requirement_version=2
            )["policy_ref"]
            work2 = act(
                editor,
                "revise",
                work_item_id="publish-note",
                policy_version=policy2["version_id"],
                reason="New edition",
            )["replacements"]["publish-note"]
            old_request = act(author, "request", work_item_id=work2)
            policy3 = act(
                editor,
                "confirm",
                required_phrases=["READY", "Final edition"],
                requirement_version=3,
            )["policy_ref"]
            work3 = act(
                editor,
                "revise",
                work_item_id=work2,
                policy_version=policy3["version_id"],
                reason="Clarified edition",
            )["replacements"][work2]
            request3 = act(author, "request", work_item_id=work3)
            old_reply = act(editor, "reply", request_id=old_request["request_id"])
            state = world.store.load()
            check(
                "old_reply_does_not_satisfy_new_work",
                state["work_items"][work3]["status"] == "blocked"
                and not old_reply["satisfaction"]["resolved_conditions"],
            )
            check(
                "old_version_access_does_not_grant_new",
                not world.act(
                    author, "read_file", {"artifact_id": "editorial_policy", "version_id": "v3"}
                )["ok"],
            )
            before_duplicate = world.store.load()
            act(editor, "reply", request_id=old_request["request_id"])
            after_duplicate = world.store.load()
            check(
                "repeated_delivery_has_no_primary_effect",
                all(
                    before_duplicate[k] == after_duplicate[k]
                    for k in (
                        "messages",
                        "access_grants",
                        "condition_specs",
                        "work_items",
                        "requests",
                    )
                ),
            )
            check(
                "revision_and_reply_preserve_draft_bytes",
                world.store.content(after_duplicate["artifacts"]["draft"]) == draft_before,
            )
            check(
                "old_approval_is_unchanged",
                after_duplicate["work_items"]["publish-note"]["submissions"][0]["review"]
                == first["review"],
            )
            act(editor, "reply", request_id=request3["request_id"])
            check(
                "new_matching_reply_reopens_work",
                world.store.load()["work_items"][work3]["status"] == "open",
            )
            written = write("v3", "READY. Final edition")
            first_new = act(author, "submit", work_item_id=work3)
            act(
                author,
                "withdraw",
                work_item_id=work3,
                submission_id=first_new["submission_id"],
                reason="Check wording without changing bytes",
            )
            second_new = act(author, "submit", work_item_id=work3)
            act(author, "wait", ticks=2)
            check(
                "withdraw_does_not_force_rewriting",
                first_new["artifact_versions"]
                == second_new["artifact_versions"]
                == {"draft": written["version_id"]},
            )
            evaluation = evaluate_publication(world)
            check(
                "current_publication_valid",
                evaluation["passed"] and evaluation["business_accepted"],
                evaluation,
            )
            historical = evaluate_publication(world, "publish-note")
            check(
                "historical_validity_is_separate_from_current_applicability",
                historical["passed"] and not historical["currently_applicable"],
                historical,
            )
        error = None
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    state = world.store.load()
    hashes = {
        str(p.relative_to(world.store.root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted((world.store.control / "versions").rglob("*"))
        if p.is_file()
    }
    result = {
        "case": label,
        "actors": names,
        "mode": mode,
        "checks": checks,
        "error": error,
        "mechanism_pass": error is None and all(c["passed"] for c in checks),
        "business_complete": world.session().observe()["complete"],
        "current_evaluation": evaluate_publication(world),
        "file_sha256": hashes,
        "interactions": state["interactions"],
        "event_history": state["event_history"],
        "attestations": state["attestations"],
        "work_items": state["work_items"],
        "model_calls": 0,
        "world": str(world.store.root),
    }
    atomic_write(world.store.root / "result.json", json_bytes(result))
    return result


def run(output, workers=4):
    root = Path(output)
    if root.exists():
        raise ValueError("Experiment output must be new")
    before = code_identity()
    root.mkdir(parents=True)
    jobs = [(names, mode) for names in ACTORS for mode in ("correct", "erroneous")]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(lambda pair: run_case(root, *pair), jobs))
    report = {
        "experiment": "publication-kernel-reuse",
        "code_before": before,
        "code_after": code_identity(),
        "model_calls": 0,
        "training_performed": False,
        "local_gpu_used": False,
        "workers": workers,
        "sampling": "Two actor configurations crossed with two fixed action strategies; no model sample or professional validity claim.",
        "shared_implementation": [
            "World.act",
            "core.transitions.execute_transition",
            "Store.put",
            "core.visibility.grant_version",
            "core.rules.confirm_credential",
            "core.rules.registered_applicability",
            "core.conditions.apply_response",
            "core.work.submit_work",
            "core.work.withdraw_submission",
            "core.work.approve_submission",
            "core.work.revise_requirement",
        ],
        "case_count": len(results),
        "mechanism_pass_count": sum(r["mechanism_pass"] for r in results),
        "results": results,
    }
    atomic_write(root / "report.json", json_bytes(report))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    report = run(args.output, args.workers)
    print(json.dumps({"cases": report["case_count"], "passed": report["mechanism_pass_count"]}))
    raise SystemExit(0 if report["case_count"] == report["mechanism_pass_count"] else 1)
