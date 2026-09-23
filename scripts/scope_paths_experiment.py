"""N0: actual ProjectSession scope paths with predeclared positive/negative controls.

Setup uses only WorldSpec and legal install_project/object/share session calls.
The measurement may inspect persisted facts after actions, never patch ACLs.
Historical v0.6/v0.7 runs retain their frozen scripts. The current regression uses
v0.8 work-scoped bindings and explicitly updates each authorized work edition.
"""

import argparse
import copy
import hashlib
import json
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from proworksim.core.adoption import binding_key
from proworksim.audit import code_identity
from proworksim.core.world import WorldSpec, object_identity
from proworksim.storage import atomic_write, digest, json_bytes
from proworksim.world_core import WorldCore

ACTORS = ("operator", "alice", "bob", "carol")
CHECKS = {
    "share": (
        "same_project_before_denied",
        "cross_project_before_denied",
        "same_project_share_recorded",
        "same_project_exact_version_readable",
        "cross_project_share_recorded",
        "cross_project_exact_version_readable",
        "unshared_v2_denied_both_projects",
        "unshared_actor_denied_both_projects",
        "base_acl_and_other_object_unchanged",
        "observation_exposes_only_shared_version",
    ),
    "adopt_initial": (
        "object_and_work_scoped_initial_adoption",
        "separate_grants_cover_all_target_works",
        "wrong_object_denied",
        "wrong_work_denied",
        "partial_multiwork_denied",
        "foreign_project_work_denied",
        "wrong_project_denied",
        "empty_work_list_does_not_bypass_narrow_grant",
        "failed_declarations_preserve_aliases_and_adoptions",
        "first_cross_project_adoption_with_broad_grant",
    ),
    "adopt_update": (
        "object_and_work_scoped_update",
        "separate_grants_cover_all_update_works",
        "wrong_object_update_denied",
        "wrong_project_update_denied",
        "fixed_policy_update_denied",
        "unshared_version_update_denied",
        "partially_authorized_update_denied",
        "failed_updates_preserve_adoptions",
        "successful_update_records_exact_history",
    ),
}


def package(pid, objects=(), grants=(), adoptions=()):
    return {
        "project_id": pid,
        "goal": "Finite exact sharing and adoption contract",
        "participants": list(ACTORS),
        "objects": list(objects),
        "works": [
            {
                "work_id": wid,
                "owner": "alice",
                "approval_policy": "delivery_only",
                "deliverable_contract": {"min_files": 1, "max_files": 2},
            }
            for wid in ("work-1", "work-2")
        ],
        "grants": list(grants),
        "adoptions": list(adoptions),
        "provenance": {"kind": "synthetic", "source_evidence_refs": []},
    }


def material(alias, readers=None):
    return {
        "alias": alias,
        "filename": alias + ".json",
        "owner": "alice",
        "readers": list(ACTORS) if readers is None else readers,
        "writers": ["alice"],
        "data": {"value": 1},
    }


def grant(actor, alias, work):
    return {
        "actor_id": actor,
        "power": "adopt",
        "subject": "artifact",
        "object_ids": [alias],
        "work_nodes": [work],
    }


class Evidence:
    def __init__(self, group, root):
        self.group, self.root = group, root
        self.checks, self.transcript = [], []
        self.world = WorldCore.create(
            root / "world",
            WorldSpec(
                "scope-paths",
                actors={actor: {} for actor in ACTORS},
                bootstrap_grants=[
                    {"actor_id": "operator", "scope": "world", "power": p}
                    for p in ("install_project", "create_object", "publish", "share")
                ],
            ),
        )

    def call(self, actor, project, action, **arguments):
        result = self.world.session(actor, project).call(action, **arguments)
        self.transcript.append(
            {
                "actor": actor,
                "project": project,
                "action": action,
                "arguments": copy.deepcopy(arguments),
                "result": result,
            }
        )
        return result

    def require(self, actor, project, action, **arguments):
        result = self.call(actor, project, action, **arguments)
        if not result["ok"]:
            raise AssertionError(f"Construction failed: {actor}/{project}/{action}: {result}")
        return result["result"]

    def install(self, pkg):
        self.require("operator", None, "install_project", package=pkg)

    def check(self, name, observed, expected=True):
        if name not in CHECKS[self.group] or any(c["name"] == name for c in self.checks):
            raise AssertionError("Undeclared or duplicate check: " + name)
        self.checks.append(
            {
                "name": name,
                "expected": expected,
                "observed": observed,
                "passed": observed == expected,
                "not_executed": False,
            }
        )

    def declarations(self):
        state = self.world.store.load()
        return copy.deepcopy({key: state[key] for key in ("workspaces", "adoptions")})


def share_group(ev):
    ev.install(
        package(
            "A",
            [material("private", ["alice"]), material("other", ["alice"])],
            [
                {
                    "actor_id": "alice",
                    "power": "share",
                    "subject": "artifact",
                    "object_ids": ["private"],
                }
            ],
        )
    )
    ev.install(package("B"))
    oid = object_identity("A", "private")
    ref = {"object_id": oid, "version_id": "v1"}
    ev.check("same_project_before_denied", not ev.call("bob", "A", "read_object", **ref)["ok"])
    ev.check("cross_project_before_denied", not ev.call("bob", "B", "read_object", **ref)["ok"])
    for pid, prefix in (("A", "same_project"), ("B", "cross_project")):
        share = ev.call("alice", "A", "share", **ref, target_project=pid, actor_ids=["bob"])
        ev.check(
            prefix + "_share_recorded",
            share["ok"]
            and any(
                s["object_id"] == oid
                and s["version_id"] == "v1"
                and s["project_id"] == pid
                and s["actor_ids"] == ["bob"]
                for s in ev.world.store.load()["shares"]
            ),
        )
        read = ev.call("bob", pid, "read_object", **ref)
        ev.check(
            prefix + "_exact_version_readable",
            read["ok"] and read["result"]["data"] == {"value": 1},
        )
    ev.require("alice", "A", "write_object", alias="private", data={"value": 2})
    ev.check(
        "unshared_v2_denied_both_projects",
        [
            ev.call("bob", pid, "read_object", object_id=oid, version_id="v2")["ok"]
            for pid in ("A", "B")
        ],
        [False, False],
    )
    ev.check(
        "unshared_actor_denied_both_projects",
        [ev.call("carol", pid, "read_object", **ref)["ok"] for pid in ("A", "B")],
        [False, False],
    )
    original = ev.call("alice", "A", "read_object", object_id=oid, version_id="v2")
    unrelated = ev.call("bob", "A", "read_object", alias="other")
    ev.check(
        "base_acl_and_other_object_unchanged",
        [original["ok"], unrelated["ok"], ev.world.store.load()["artifacts"][oid]["readers"]],
        [True, False, ["alice"]],
    )
    observed = ev.world.session("bob", "A").observe()
    ev.transcript.append({"actor": "bob", "project": "A", "action": "observe", "result": observed})
    ev.check(
        "observation_exposes_only_shared_version",
        observed["objects"].get(oid, {}).get("versions"),
        ["v1"],
    )


def initial_group(ev):
    grants = [
        grant("bob", "target", "work-1"),
        grant("carol", "target", "work-1"),
        grant("carol", "target", "work-2"),
    ]
    ev.install(package("A", [material("target"), material("other")], grants))
    ev.install(
        package(
            "B",
            [material("other")],
            [
                grant("bob", "other", "work-1"),
                {"actor_id": "operator", "power": "adopt", "subject": "artifact"},
            ],
        )
    )
    oid = object_identity("A", "target")
    ev.check(
        "object_and_work_scoped_initial_adoption",
        ev.call(
            "bob",
            "A",
            "adopt",
            alias="narrow",
            object_id=oid,
            version_id="v1",
            policy="current_applicable",
            work_ids=["work-1"],
        )["ok"],
    )
    ev.check(
        "separate_grants_cover_all_target_works",
        ev.call(
            "carol",
            "A",
            "adopt",
            alias="multi",
            object_id=oid,
            version_id="v1",
            policy="current_applicable",
            work_ids=["work-1", "work-2"],
        )["ok"],
    )
    before = ev.declarations()
    for check, alias, object_id, work_ids in (
        ("wrong_object_denied", "wrong-object", object_identity("A", "other"), ["work-1"]),
        ("wrong_work_denied", "wrong-work", oid, ["work-2"]),
        ("partial_multiwork_denied", "partial", oid, ["work-1", "work-2"]),
        ("foreign_project_work_denied", "foreign", oid, ["B::work-1"]),
        ("empty_work_list_does_not_bypass_narrow_grant", "empty", oid, []),
    ):
        ev.check(
            check,
            not ev.call(
                "bob",
                "A",
                "adopt",
                alias=alias,
                object_id=object_id,
                version_id="v1",
                policy="current_applicable",
                work_ids=work_ids,
            )["ok"],
        )
    # A local grant must not authorize even a same-named object in B.
    ev.check(
        "wrong_project_denied",
        not ev.call(
            "carol",
            "B",
            "adopt",
            alias="wrong-project",
            object_id=object_identity("B", "other"),
            version_id="v1",
            policy="current_applicable",
            work_ids=["work-1"],
        )["ok"],
    )
    ev.check("failed_declarations_preserve_aliases_and_adoptions", ev.declarations(), before)
    external = ev.require(
        "operator",
        None,
        "create_object",
        alias="external",
        filename="external.json",
        data={"value": 9},
    )
    ev.require(
        "operator",
        None,
        "share",
        object_id=external["object_id"],
        version_id="v1",
        target_project="B",
        actor_ids=["operator"],
    )
    ev.check(
        "first_cross_project_adoption_with_broad_grant",
        ev.call(
            "operator",
            "B",
            "adopt",
            alias="external",
            object_id=external["object_id"],
            version_id="v1",
            policy="fixed",
            work_ids=["work-1"],
        )["ok"],
    )


def update_group(ev):
    source = ev.require(
        "operator", None, "create_object", alias="source", filename="source.json", data={"value": 1}
    )
    other = ev.require(
        "operator", None, "create_object", alias="other", filename="other.json", data={"value": 1}
    )
    for obj in (source, other):
        for pid in ("A", "B"):
            ev.require(
                "operator",
                None,
                "share",
                object_id=obj["object_id"],
                version_id="v1",
                target_project=pid,
                actor_ids=list(ACTORS),
            )

    def adoption(alias, obj=source, policy="current_applicable", work_ids=None):
        return {
            "alias": alias,
            "object_id": obj["object_id"],
            "version_id": "v1",
            "policy": policy,
            "work_ids": work_ids or ["work-1"],
        }

    ev.install(
        package(
            "A",
            grants=[
                grant("bob", "input", "work-1"),
                grant("carol", "input", "work-1"),
                grant("carol", "input", "work-2"),
            ],
            adoptions=[
                adoption("input"),
                adoption("multi", work_ids=["work-1", "work-2"]),
                adoption("other", other),
                adoption("fixed", policy="fixed"),
            ],
        )
    )
    ev.install(
        package(
            "B",
            grants=[grant("bob", "other", "work-1")],
            adoptions=[adoption("input"), adoption("other", other)],
        )
    )
    for alias, obj in (("source", source), ("other", other)):
        ev.require("operator", None, "write_object", alias=alias, data={"value": 2})
        for pid in ("A", "B"):
            ev.require(
                "operator",
                None,
                "share",
                object_id=obj["object_id"],
                version_id="v2",
                target_project=pid,
                actor_ids=list(ACTORS),
            )
    ev.check(
        "object_and_work_scoped_update",
        ev.call("bob", "A", "adopt_version", alias="input", work_id="work-1", version_id="v2")["ok"],
    )
    first = ev.call("carol", "A", "adopt_version", alias="multi", work_id="work-1", version_id="v2")
    after_first = ev.world.store.load()["adoptions"]
    isolated = (
        after_first[binding_key("A::work-1", "multi")]["version_id"] == "v2"
        and after_first[binding_key("A::work-2", "multi")]["version_id"] == "v1"
    )
    second = ev.call("carol", "A", "adopt_version", alias="multi", work_id="work-2", version_id="v2")
    ev.check(
        "separate_grants_cover_all_update_works",
        first["ok"] and second["ok"] and isolated,
    )
    ev.require("operator", None, "write_object", alias="source", data={"value": 3})
    before = ev.declarations()
    for name, actor, project, alias, version in (
        ("wrong_object_update_denied", "bob", "A", "other", "v2"),
        ("wrong_project_update_denied", "bob", "B", "input", "v2"),
        ("fixed_policy_update_denied", "bob", "A", "fixed", "v2"),
        ("unshared_version_update_denied", "bob", "A", "input", "v3"),
        ("partially_authorized_update_denied", "bob", "A", "multi", "v1"),
    ):
        ev.check(
            name,
            not ev.call(
                actor, project, "adopt_version", alias=alias, version_id=version,
                work_id="work-2" if name == "partially_authorized_update_denied" else "work-1",
            )["ok"],
        )
    ev.check("failed_updates_preserve_adoptions", ev.declarations(), before)
    decl = ev.world.store.load()["adoptions"][binding_key("A::work-1", "input")]
    history = decl.get("history", [])
    ev.check(
        "successful_update_records_exact_history",
        [
            decl["version_id"],
            [(h["previous_version"], h["version_id"], h["actor_id"]) for h in history],
        ],
        ["v2", [("v1", "v2", "bob")]],
    )


GROUPS = {"share": share_group, "adopt_initial": initial_group, "adopt_update": update_group}


def run_group(group, output):
    root = output / group
    root.mkdir(parents=True)
    ev = Evidence(group, root)
    failure = None
    try:
        GROUPS[group](ev)
    except Exception:
        failure = traceback.format_exc()
    completed = {c["name"] for c in ev.checks}
    for name in CHECKS[group]:
        if name not in completed:
            ev.checks.append({"name": name, "passed": False, "not_executed": True})
    transcript = root / "transcript.json"
    atomic_write(transcript, json_bytes(ev.transcript))
    state_path = root / "world" / "control" / "state.json"
    return {
        "group": group,
        "construction_error": failure,
        "checks": ev.checks,
        "transcript": {"path": str(transcript), "sha256": digest(transcript.read_bytes())},
        "final_state": {"path": str(state_path), "sha256": digest(state_path.read_bytes())},
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument(
        "--source-commit", help="Archive source identity when .git is intentionally absent"
    )
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    source_before = code_identity()
    protocol = {
        "experiment": "N0-exact-share-and-work-scoped-adoption-v08",
        "checks": CHECKS,
        "expected": "Legal exact grants execute; unrelated versions/actors/objects/projects/works deny",
        "construction": "WorldSpec plus legal package and public ProjectSession actions only",
        "measurements": "Exact tool outputs, resulting declarations, unchanged base ACL, recorded observations",
        "boundary": "Finite synthetic authorization cases; no model, GPU, training or universal permission proof",
    }
    atomic_write(args.output / "protocol.json", json_bytes(protocol))
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        groups = list(pool.map(lambda group: run_group(group, args.output), GROUPS))
    checks = [check for group in groups for check in group["checks"]]
    result = {
        "protocol": protocol,
        "source_before": source_before,
        "source_after": code_identity(),
        "archive_source_commit": args.source_commit,
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "groups": groups,
        "total": len(checks),
        "passed": sum(c["passed"] for c in checks),
        "not_executed": sum(c["not_executed"] for c in checks),
    }
    atomic_write(args.output / "report.json", json_bytes(result))
    print(json.dumps({key: result[key] for key in ("total", "passed", "not_executed")}))
    return 0 if result["passed"] == result["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
