"""E1: real adapter checkpoints, frozen cache paths and side-effect-free rebuilding.

Program mechanism witnesses only. No model, API, GPU or parameter training.
The sibling E2 script imports the adapter helpers, which never patch world facts.
"""

import argparse
import copy
import json
import shutil
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from proworksim.audit import code_identity
from proworksim.baseline import run_baseline
from proworksim.compiler import compile_world
from proworksim.designer import design
from proworksim.domains.publication import SOURCE_REF, PublicationWorld, compile_publication
from proworksim.kernel import World
from proworksim.storage import atomic_write, digest, json_bytes

SEED = 907
TEMPLATES = ("operating", "publication")
CHECKPOINTS = ("initial", "pending_reply", "in_review", "withdrawn", "revised", "late_reply")
VARIANTS = ("normal", "deleted", "corrupted", "repeated")
CHECKS = (
    "pure_query_does_not_mutate",
    "same_derived_view",
    "base_facts_unchanged",
    "artifact_bytes_unchanged",
    "actual_observation_unchanged",
    "rebuild_idempotent",
)


def write_json(path, value):
    atomic_write(path, json_bytes(value))
    return {"path": str(path), "sha256": digest(path.read_bytes())}


def file_hashes(world):
    state = world.store.load()
    hashes = {}
    for aid, artifact in state["artifacts"].items():
        for version in artifact["versions"]:
            path = world.store.version_path(artifact, version)
            hashes[f"versions/{aid}/{version}/{artifact['filename']}"] = digest(path.read_bytes())
        path = world.store.current_path(artifact)
        hashes[f"materialized/{aid}/{artifact['filename']}"] = digest(path.read_bytes())
    return hashes


class BeforeSubmission(Exception):
    pass


class AdapterTrace:
    """Every business mutation goes through a real adapter action.

    The operating preparation policy also uses real worker tools; its full inputs,
    results, reads and writes remain in control/state.json interactions.
    """

    def __init__(self, template, root, information="mail"):
        self.template = template
        self.root = Path(root)
        self.actions = []
        self.initial_work = "work-1" if template == "operating" else "publish-note"
        self.work_id = self.initial_work
        self.worker = "analyst" if template == "operating" else "author"
        self.coordinator = "manager" if template == "operating" else "editor"
        self.reviewer = "reviewer" if template == "operating" else "editor"
        self.credential = "basis" if template == "operating" else "editorial_policy"
        if template == "operating":
            self.world = World(
                compile_world(design(SEED, delivery="file", information=information), root)
            )
        else:
            self.world = PublicationWorld(compile_publication(root))
        self.initial_reference = copy.deepcopy(
            self.world.store.load()["work_items"][self.work_id]["required_credentials"][0]
        )

    def act(self, actor, action, expect_ok=True, **arguments):
        output = self.world.act(actor, action, arguments)
        self.actions.append(
            {"actor": actor, "action": action, "arguments": arguments, "output": output}
        )
        if output["ok"] != expect_ok:
            raise AssertionError(f"{self.template}/{action}: {output}")
        return output["result"] if expect_ok else output

    def prepare(self):
        if self.template == "operating":
            trace = self

            class Worker:
                def observe(self):
                    return trace.world.session().observe()

                def call(self, action, **arguments):
                    if action == "submit":
                        raise BeforeSubmission
                    output = trace.world.session().call(action, **arguments)
                    trace.actions.append(
                        {
                            "actor": trace.worker,
                            "action": action,
                            "arguments": arguments,
                            "output": output,
                        }
                    )
                    return output

            try:
                run_baseline(Worker())
            except BeforeSubmission:
                return
            raise AssertionError("Rule policy did not reach submission")
        reference = self.world.store.load()["work_items"][self.work_id]["required_credentials"][0]
        self.act(self.worker, "read_file", artifact_id="source_note")
        policy = self.act(
            self.worker,
            "read_file",
            artifact_id=self.credential,
            version_id=reference["version_id"],
        )
        phrases = json.loads(policy["content"])["required_phrases"]
        self.act(
            self.worker,
            "write_file",
            artifact_id="draft",
            content=json.dumps(
                {
                    "title": "Projection witness",
                    "body": ". ".join(phrases),
                    "source_ref": SOURCE_REF,
                }
            ),
            dependencies=[SOURCE_REF, reference],
        )

    def request(self):
        if self.template == "publication":
            return self.act(self.worker, "request", work_item_id=self.work_id)["request_id"]
        item = self.world.store.load()["work_items"][self.work_id]
        blocker = self.act(
            self.worker,
            "block_work",
            work_item_id=self.work_id,
            kind="scope",
            requested_role=self.coordinator,
            required_scope_version=item["basis_requirement_version"],
            reason="Await this work's exact approved reference",
        )
        return self.act(
            self.worker,
            "mail_send",
            to=self.coordinator,
            topic="scope",
            work_item_id=self.work_id,
            blocker_id=blocker["blocker_id"],
            body="Supply the exact applicable approved reference",
        )["message_id"]

    def reply(self, request_id):
        if self.template == "publication":
            return self.act(self.coordinator, "reply", request_id=request_id)
        request = self.world.store.load()["requests"][request_id]
        if request["status"] == "pending":
            self.act(self.worker, "wait", ticks=2)
        return self.world.store.load()["requests"][request_id]

    def revise(self):
        old = self.work_id
        if self.template == "publication":
            revision = self.world.store.load()["work_items"][old]["requirement_version"] + 1
            reference = self.act(
                self.coordinator,
                "confirm",
                required_phrases=["READY", "Revised edition"],
                requirement_version=revision,
                public=False,
            )["policy_ref"]
            changes = self.act(
                self.coordinator,
                "revise",
                work_item_id=old,
                policy_version=reference["version_id"],
                reason="Revise the concrete publication requirement",
            )["replacements"]
        else:
            changes = self.act(
                self.coordinator,
                "revise_requirements",
                work_item_ids=[old],
                growth_delta=0.02,
                reason="Revise the concrete analytical requirement",
            )["replacements"]
        self.work_id = changes[old]
        return self.work_id

    def submit(self):
        return self.act(self.worker, "submit", work_item_id=self.work_id)

    def withdraw(self, submission):
        return self.act(
            self.worker,
            "withdraw",
            work_item_id=self.work_id,
            submission_id=submission["submission_id"],
            reason="Recheck the pinned deliverable",
        )

    def approve(self, submission):
        return self.act(
            self.reviewer,
            "approve",
            work_item_id=self.work_id,
            submission_id=submission["submission_id"],
        )

    def archive(self, destination):
        shutil.copytree(self.world.store.root, destination)
        return {
            "world": str(destination),
            "state": write_json(
                destination.parent / f"{destination.name}-raw-state.json", self.world.store.load()
            ),
            "files": file_hashes(self.world),
            "actions": copy.deepcopy(self.actions),
        }


def build_checkpoints(base, template):
    folder = base / template
    folder.mkdir()
    points = {}
    trail = AdapterTrace(template, folder / "delivery-trace")
    points["initial"] = trail.archive(folder / "checkpoint-initial")
    request = trail.request()
    points["pending_reply"] = trail.archive(folder / "checkpoint-pending_reply")
    trail.reply(request)
    trail.prepare()
    sub = trail.submit()
    points["in_review"] = trail.archive(folder / "checkpoint-in_review")
    trail.withdraw(sub)
    points["withdrawn"] = trail.archive(folder / "checkpoint-withdrawn")
    trail.revise()
    points["revised"] = trail.archive(folder / "checkpoint-revised")
    delayed = AdapterTrace(template, folder / "late-reply-trace", information="clarification")
    old_request = delayed.request()
    delayed.revise()
    delayed.reply(old_request)
    points["late_reply"] = delayed.archive(folder / "checkpoint-late_reply")
    write_json(folder / "checkpoints.json", points)
    return template, points


def build_entry(entry):
    output, template = entry
    try:
        _, points = build_checkpoints(output, template)
        return template, points, None
    except Exception as error:
        details = {"error": f"{type(error).__name__}: {error}", "traceback": traceback.format_exc()}
        write_json(output / template / "construction-error.json", details)
        return template, {}, details


def project(state):
    from proworksim.core.projections import derive_condition_view, derive_current_work_view

    return {"conditions": derive_condition_view(state), "work": derive_current_work_view(state)}


def remove_paths(state, paths):
    """Experiment-local removal of the declared paths; no inference from bad values."""
    for path in paths:
        parent = state
        for key in path[:-1]:
            if not isinstance(parent, dict) or key not in parent:
                parent = None
                break
            parent = parent[key]
        if isinstance(parent, dict):
            parent.pop(path[-1], None)


def base_facts(state, paths):
    result = copy.deepcopy(state)
    remove_paths(result, paths)
    return result


def corrupt_paths(state, paths):
    for index, path in enumerate(paths):
        parent = state
        for key in path[:-1]:
            parent = parent.setdefault(key, {})
        parent[path[-1]] = {"deliberately_inconsistent_cache": index}


def run_variant(entry):
    from proworksim.core.projections import rebuild_projections

    (
        template,
        checkpoint,
        variant,
        source,
        paths,
        expected_view,
        expected_observation,
        facts,
        expected_files,
        destination,
    ) = entry
    world_type = World if template == "operating" else PublicationWorld
    result = {
        "template": template,
        "checkpoint": checkpoint,
        "variant": variant,
        "checks": [],
        "cache_paths": paths,
    }
    shutil.copytree(source, destination)
    world = world_type(destination)
    state = world.store.load()
    try:
        if variant == "deleted":
            remove_paths(state, paths)
        elif variant == "corrupted":
            corrupt_paths(state, paths)
        elif variant == "repeated":
            rebuild_projections(state)
        result["before_state"] = write_json(
            destination.parent / f"{destination.name}-before.json", state
        )
        queried = copy.deepcopy(state)
        view = project(state)
        pure = state == queried
        rebuild_projections(state)
        first = copy.deepcopy(state)
        rebuild_projections(state)
        second_same = state == first
        world.store.save(state)
        observed = world.session().observe()
        values = (
            pure,
            view == expected_view and project(state) == expected_view,
            base_facts(state, paths) == facts,
            file_hashes(world) == expected_files,
            observed == expected_observation,
            second_same,
        )
        result["checks"] = [
            {"name": name, "passed": bool(value)} for name, value in zip(CHECKS, values)
        ]
        result["view"] = view
        result["observation"] = observed
        result["after_state"] = write_json(
            destination.parent / f"{destination.name}-after.json", state
        )
        result["base_sha256"] = digest(json_bytes(base_facts(state, paths)))
        result["files"] = expected_files
    except Exception as error:
        result["error"] = f"{type(error).__name__}: {error}"
        result["traceback"] = traceback.format_exc()
        done = {check["name"] for check in result["checks"]}
        result["checks"].extend(
            {"name": name, "passed": False, "not_completed": True}
            for name in CHECKS
            if name not in done
        )
    result["passed"] = all(row["passed"] for row in result["checks"])
    write_json(destination.parent / f"{destination.name}-result.json", result)
    return result


def main():
    from proworksim.core.projections import projection_paths

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if args.output.exists() or args.workers < 1:
        parser.error("Use a new output directory and positive worker count")
    args.output.mkdir(parents=True)
    before, script_before = code_identity(), digest(Path(__file__).read_bytes())
    started = datetime.now(timezone.utc).isoformat()
    protocol = {
        "version": "state-projection-e1-v1",
        "templates": TEMPLATES,
        "checkpoints": CHECKPOINTS,
        "variants": VARIANTS,
        "checks": CHECKS,
        "expected_variant_count": 48,
        "expected_check_count": 288,
        "cache_scope": "Exactly core.projections.projection_paths at each untouched checkpoint, saved before corruption; no primary fact removal.",
        "comparison": "Full pure views and full worker observations within each checkpoint; no value or identity normalization.",
        "world_construction": "Real adapter calls only; copying and declared cache replacement are the sole harness interventions.",
    }
    write_json(args.output / "protocol.json", protocol)
    with ThreadPoolExecutor(max_workers=min(args.workers, 2)) as executor:
        built = list(executor.map(build_entry, ((args.output, template) for template in TEMPLATES)))
    checkpoints = {template: points for template, points, _ in built}
    construction_errors = {template: error for template, _, error in built if error}
    entries = []
    unexecuted = []
    for template in TEMPLATES:
        for name in CHECKPOINTS:
            if name not in checkpoints[template]:
                for variant in VARIANTS:
                    unexecuted.append(
                        {
                            "template": template,
                            "checkpoint": name,
                            "variant": variant,
                            "passed": False,
                            "not_executed": True,
                            "construction_error": construction_errors.get(template),
                            "checks": [
                                {"name": check, "passed": False, "not_executed": True}
                                for check in CHECKS
                            ],
                        }
                    )
                continue
            point = checkpoints[template][name]
            world_type = World if template == "operating" else PublicationWorld
            world = world_type(point["world"])
            state = world.store.load()
            paths = projection_paths(state)
            expected_view = project(state)
            expected_observation = world.session().observe()
            facts = base_facts(state, paths)
            write_json(
                args.output / template / f"{name}-reference.json",
                {
                    "cache_paths": paths,
                    "view": expected_view,
                    "observation": expected_observation,
                    "base_sha256": digest(json_bytes(facts)),
                },
            )
            for variant in VARIANTS:
                entries.append(
                    (
                        template,
                        name,
                        variant,
                        point["world"],
                        paths,
                        expected_view,
                        expected_observation,
                        facts,
                        point["files"],
                        args.output / template / f"{name}-{variant}",
                    )
                )
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        results = unexecuted + list(executor.map(run_variant, entries))
    after = code_identity()
    report = {
        "suite": "state-projection-e1-v0.5",
        "protocol": protocol,
        "seed": SEED,
        "started_at": started,
        "ended_at": datetime.now(timezone.utc).isoformat(),
        "code_identity_before": before,
        "code_identity_after": after,
        "source_tree_unchanged_during_run": before["source_tree_sha256"]
        == after["source_tree_sha256"],
        "script_sha256_before": script_before,
        "script_sha256_after": digest(Path(__file__).read_bytes()),
        "workers": args.workers,
        "construction_errors": construction_errors,
        "variant_not_executed_count": len(unexecuted),
        "variant_count": len(results),
        "variant_pass_count": sum(r["passed"] for r in results),
        "check_count": sum(len(r["checks"]) for r in results),
        "check_pass_count": sum(c["passed"] for r in results for c in r["checks"]),
        "api_calls": 0,
        "gpu_used": False,
        "training_performed": False,
        "interpretation": "Finite cache-invariance witnesses at actual two-template checkpoints, not independent samples, event-log reconstruction, arbitrary-state recovery or model performance.",
        "checkpoints": checkpoints,
        "results": results,
    }
    write_json(args.output / "report.json", report)
    print(
        f"E1: {report['variant_pass_count']}/{report['variant_count']} variants; {report['check_pass_count']}/{report['check_count']} checks",
        flush=True,
    )
    return 0 if all(r["passed"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
