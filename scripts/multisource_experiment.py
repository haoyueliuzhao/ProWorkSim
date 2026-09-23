"""P3: two exact inputs, one changed source and an actual maintenance successor.

Four isolated two-project worlds vary file organization and one deliberate upstream
error. All business mutations use public project sessions. This informed driver is
not the P4 continuing worker. Independent literal expectations are 13, 23 and 43.
"""

import argparse
import copy
import json
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from proworksim.audit import code_identity
from proworksim.core.adoption import binding_key
from proworksim.core.world import WorldSpec
from proworksim.storage import digest
from proworksim.world_core import WorldCore

CASES = {
    "combined_correct": {"split": False, "new_source": 20, "a_correct": True, "b_faithful": True, "business_goal": True, "new_total": 23},
    "split_correct": {"split": True, "new_source": 20, "a_correct": True, "b_faithful": True, "business_goal": True, "new_total": 23},
    "combined_wrong_upstream": {"split": False, "new_source": 40, "a_correct": False, "b_faithful": True, "business_goal": False, "new_total": 43},
    "split_wrong_upstream": {"split": True, "new_source": 40, "a_correct": False, "b_faithful": True, "business_goal": False, "new_total": 43},
}
CHECKS = (
    "initial_two_input_delivery_matches_literal_13",
    "draft_changes_source_only_without_creating_obligation",
    "one_release_creates_exactly_one_declared_successor",
    "successor_has_explicit_predecessor_and_new_requirement_context",
    "publication_preserves_downstream_bytes_and_adoption_history",
    "new_work_does_not_inherit_old_adoption_bindings",
    "accepted_predecessor_and_original_observations_unchanged",
    "unrelated_work_in_both_projects_unchanged",
    "explicit_new_work_adoptions_do_not_edit_downstream_bytes",
    "actual_reads_use_new_external_and_fixed_local_versions",
    "updated_content_faithfully_combines_both_interfaces",
    "all_contributing_files_bind_both_exact_sources",
    "fixed_local_object_and_all_old_version_bytes_preserved",
    "historical_submission_evaluation_remains_13",
    "upstream_quality_downstream_faithfulness_business_goal_are_separate",
    "formal_upstream_approval_preserved_even_when_content_fails",
)
PROTOCOL = {
    "suite": "multisource-maintenance-P3-v0.8",
    "cases": CASES,
    "checks": CHECKS,
    "inputs": {"external": "A JSON rate v1=10, released v2=20 or deliberately wrong40", "local": "B JSON offset v1=3, fixed"},
    "calculation": "total = external.rate + local.offset; reference uses Python scalar addition and literal expectations 13/23/43, never Spreadsheet",
    "allowed_actions": "install_project, share, publish, adopt, read_object, create_object, write_object, submit, approve",
    "legal_layouts": "One JSON with total and sources; or two whole-field JSON objects {total} and {sources}. Each contributing file declares both exact dependencies. No deep merge.",
    "maintenance": "B predeclares source A selector, analysis lineage, accepted trigger, successor effect, manager revision authority, new goal; actual publication event creates successor without controller revision/install",
    "exits": "Every action/event error fails construction; missing checks are not-executed. A wrong source is an intentional content-negative condition, not a kernel failure.",
    "comparison_scope": "Per-world old submissions/adoptions/observations and all old version bytes; fixed local object; unrelated work records in A and B; actual immutable content and source dependencies",
    "error_attribution": "Wrong upstream40 causes the A content check and overall23 goal to fail; B reporting43 is faithful. This is one injected source error, not two independent worker capability failures.",
    "limits": ["One world with two projects and single writer per isolated branch", "Unrelated work within those projects is checked; no third unrelated project is introduced", "Finite linear scalar content with controlled JSON production; mixed XLSX source reading is additionally covered by unit tests", "No model/API/GPU/training; this informed driver is distinct from P4 public-only execution"],
}


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n")


def content_contract():
    return {
        "min_files": 1, "max_files": 2, "allowed_roles": ["report"], "allowed_kinds": ["json"],
        "required_fields": ["total", "sources"],
        "content_checks": [{
            "kind": "json_linear_sources", "path": ["total"], "constant": 0,
            "sources": [
                {"alias": "external", "kind": "json_field", "source_path": ["rate"], "reference_path": ["sources", "external"], "coefficient": 1},
                {"alias": "local", "kind": "json_field", "source_path": ["offset"], "reference_path": ["sources", "local"], "coefficient": 1},
            ],
        }],
    }


class Evidence:
    def __init__(self, name, output):
        self.name, self.output, self.spec = name, Path(output), CASES[name]
        self.calls, self.observations, self.checks, self.evaluations = [], [], [], []
        self.world = None

    def call(self, actor, project, action, **arguments):
        result = self.world.session(actor, project).call(action, **arguments)
        self.calls.append({"actor": actor, "project": project, "action": action, "arguments": copy.deepcopy(arguments), "return": copy.deepcopy(result)})
        if not result.get("ok") or result.get("pending_event_errors") or result.get("event_delivery_errors"):
            raise AssertionError({"action": action, "result": result})
        return result["result"]

    def observe(self, actor="bob", project="B"):
        result = self.world.session(actor, project).observe()
        self.observations.append(copy.deepcopy(result))
        return result

    def check(self, name, observed, expected=True):
        if name not in CHECKS or any(c["name"] == name for c in self.checks):
            raise AssertionError("Unknown or repeated check " + name)
        self.checks.append({"name": name, "observed": copy.deepcopy(observed), "expected": copy.deepcopy(expected), "passed": observed == expected, "not_executed": False})

    def state(self):
        return self.world.store.load()

    def evaluate(self, pid, wid, sub):
        result = self.world.evaluate_submission(pid, wid, sub["submission_id"])
        self.evaluations.append({"project": pid, "work": wid, "result": copy.deepcopy(result)})
        return result

    def hashes(self, project=None):
        return {oid + "/" + vid: digest(self.world.store.version_path(obj, vid).read_bytes())
                for oid, obj in self.state()["artifacts"].items() if project is None or obj["project_id"] == project
                for vid in obj["versions"]}


def setup(ev):
    ev.world = WorldCore.create(ev.output / "world", WorldSpec(
        world_id="multisource-" + ev.name, actors={a: {} for a in ("alice", "bob", "manager")},
        bootstrap_grants=[{"actor_id": "manager", "scope": "world", "power": "install_project"}],
    ))
    a = {
        "project_id": "A", "goal": "Produce an independently checked intermediate interface",
        "participants": ["alice", "manager"],
        "objects": [{"alias": "source", "filename": "source.json", "owner": "alice", "kind": "json", "data": {"rate": 10}, "deliverable_role": "interface"}],
        "works": [
            {"work_id": "production", "owner": "alice", "approval_policy": "review", "deliverables": ["source"],
             "deliverable_contract": {"min_files": 1, "max_files": 1, "allowed_kinds": ["json"], "allowed_roles": ["interface"],
                                      "content_checks": [{"kind": "json_field_equals", "path": ["rate"], "expected": 20}]}},
            {"work_id": "unrelated", "owner": "alice", "deliverable_contract": {"min_files": 1, "max_files": 1}},
        ],
        "grants": [{"actor_id": "alice", "power": p, "subject": "artifact"} for p in ("share", "publish")]
                  + [{"actor_id": "manager", "power": "approve", "subject": "deliverable", "work_nodes": ["production"]}],
    }
    ev.call("manager", None, "install_project", package=a)
    source = ev.observe("alice", "A")["workspaces"]["A"]["source"]
    b = {
        "project_id": "B", "goal": "Maintain a finite aggregate from two declared inputs", "participants": ["bob", "manager"],
        "objects": [{"alias": "local", "filename": "local.json", "owner": "bob", "kind": "json", "data": {"offset": 3}},
                    {"alias": "untouched", "filename": "untouched.json", "owner": "bob", "kind": "json", "data": {"unrelated": 99}}],
        "works": [
            {"work_id": "analysis", "owner": "bob", "goal": "Combine external and fixed local input", "approval_policy": "review", "deliverable_contract": content_contract(),
             "requirements": {"input_policies": {"external": "current_published", "local": "fixed"}, "input_versions": {"local": "v1"}}},
            {"work_id": "unrelated", "owner": "bob", "deliverables": ["untouched"]},
        ],
        "grants": [{"actor_id": "bob", "power": power, "subject": "artifact", "work_nodes": ["analysis"]} for power in ("adopt", "create_object")]
                  + [{"actor_id": "manager", "power": power, "subject": subject, "work_nodes": ["analysis"]}
                     for power, subject in (("approve", "deliverable"), ("revise_requirement", "requirements"))],
        "maintenance_rules": [{"rule_id": "refresh-aggregate", "source": {"object_id": source, "source_project": "A"}, "work_nodes": ["analysis"],
                               "when": ["accepted"], "effect": "successor", "actor": "manager", "updates": {"goal": "Combine the newly released external input and the unchanged fixed local input"}}],
    }
    ev.call("manager", None, "install_project", package=b)
    ev.call("alice", "A", "share", object_id=source, version_id="v1", target_project="B", actor_ids=["bob"], follow_updates=True)
    ev.call("alice", "A", "publish", alias="source", version_id="v1", target_projects=["B"])
    local = ev.observe()["workspaces"]["B"]["local"]
    return source, local


def bind(ev, wid, source, local, version):
    for alias, oid, vid, policy in (("external", source, version, "current_published"), ("local", local, "v1", "fixed")):
        ev.call("bob", "B", "adopt", alias=alias, object_id=oid, version_id=vid, policy=policy, work_ids=[wid])


def produce(ev, wid, *, create):
    observation = ev.observe()
    inputs = {}
    for alias in ("external", "local"):
        binding = observation["adoptions"][binding_key(wid, alias)]
        inputs[alias] = ev.call("bob", "B", "read_object", alias=alias, version_id=binding["adopted_version"], work_id=wid)
    refs = {alias: {"object_id": value["reference"]["artifact_id"], "version_id": value["reference"]["version_id"]} for alias, value in inputs.items()}
    # Reference arithmetic is deliberately outside the spreadsheet capability.
    total = inputs["external"]["data"]["rate"] + inputs["local"]["data"]["offset"]
    docs = {"total": {"total": total}, "references": {"sources": refs}} if ev.spec["split"] else {"aggregate": {"total": total, "sources": refs}}
    for alias, data in docs.items():
        arguments = {"alias": alias, "data": data, "dependencies": list(refs.values()), "work_id": wid}
        if create:
            arguments.update(filename=alias + ".json", kind="json", deliverable_role="report")
        ev.call("bob", "B", "create_object" if create else "write_object", **arguments)
    return list(docs), total, refs


def execute(ev):
    source, local = setup(ev)
    bind(ev, "B::analysis", source, local, "v1")
    artifacts, total, _ = produce(ev, "B::analysis", create=True)
    original = ev.call("bob", "B", "submit", work_id="B::analysis", artifacts=artifacts)
    ev.call("manager", "B", "approve", work_id="B::analysis", submission_id=original["submission_id"])
    original_eval = ev.evaluate("B", "B::analysis", original)
    ev.check("initial_two_input_delivery_matches_literal_13", [total, original_eval["passed"], original_eval["checks"][0]["expected"]], [13, True, 13])
    observation = ev.observe()
    observation_copy = copy.deepcopy(observation)
    before, old_files, downstream_files = ev.state(), ev.hashes(), ev.hashes("B")
    ev.call("alice", "A", "write_object", alias="source", data={"rate": ev.spec["new_source"]}, work_id="A::production")
    draft = ev.state()
    ev.check("draft_changes_source_only_without_creating_obligation", draft["work_items"].keys() == before["work_items"].keys()
             and not draft.get("maintenance_impacts") and ev.hashes("B") == downstream_files)
    a_sub = ev.call("alice", "A", "submit", work_id="A::production", artifacts=["source"])
    ev.call("manager", "A", "approve", work_id="A::production", submission_id=a_sub["submission_id"])
    a_eval = ev.evaluate("A", "A::production", a_sub)
    a_review = copy.deepcopy(ev.state()["work_items"]["A::production"]["submissions"][-1]["review"])
    ev.call("alice", "A", "publish", alias="source", version_id="v2", target_projects=["B"])
    changed = ev.state()
    additions = set(changed["work_items"]) - set(before["work_items"])
    impacts = list(changed.get("maintenance_impacts", {}).values())
    ev.check("one_release_creates_exactly_one_declared_successor", len(additions) == 1 and len(impacts) == 1 and impacts[0]["result"]["effect"] == "successor")
    if len(additions) != 1:
        raise AssertionError("Cannot continue without the actual configured successor")
    wid = next(iter(additions))
    new = changed["work_items"][wid]
    ev.check("successor_has_explicit_predecessor_and_new_requirement_context", [new["previous_obligation_id"], new["requirement_version"], new["project_id"]], ["B::analysis", 2, "B"])
    ev.check("publication_preserves_downstream_bytes_and_adoption_history", ev.hashes("B") == downstream_files and changed["adoptions"] == before["adoptions"])
    ev.check("new_work_does_not_inherit_old_adoption_bindings", all(binding_key(wid, alias) not in changed["adoptions"] for alias in ("external", "local")))
    ev.check("accepted_predecessor_and_original_observations_unchanged", changed["work_items"]["B::analysis"] == before["work_items"]["B::analysis"] and observation == observation_copy)
    ev.check("unrelated_work_in_both_projects_unchanged", all(changed["work_items"][pid + "::unrelated"] == before["work_items"][pid + "::unrelated"] for pid in ("A", "B")))
    bind(ev, wid, source, local, "v2")
    ev.check("explicit_new_work_adoptions_do_not_edit_downstream_bytes", ev.hashes("B"), downstream_files)
    artifacts, actual, refs = produce(ev, wid, create=False)
    ev.check("actual_reads_use_new_external_and_fixed_local_versions", refs, {"external": {"object_id": source, "version_id": "v2"}, "local": {"object_id": local, "version_id": "v1"}})
    submitted = ev.call("bob", "B", "submit", work_id=wid, artifacts=artifacts)
    ev.call("manager", "B", "approve", work_id=wid, submission_id=submitted["submission_id"])
    evaluation = ev.evaluate("B", wid, submitted)
    ev.check("updated_content_faithfully_combines_both_interfaces", [actual, evaluation["passed"], evaluation["checks"][0]["expected"]], [ev.spec["new_total"], True, ev.spec["new_total"]])
    expected_refs = set((ref["object_id"], ref["version_id"]) for ref in refs.values())
    state = ev.state()
    ev.check("all_contributing_files_bind_both_exact_sources", all(
        {(ref.get("object_id", ref.get("artifact_id")), ref["version_id"]) for ref in state["artifacts"][oid]["versions"][vid]["derived_from"]} == expected_refs
        for oid, vid in submitted["artifact_versions"].items()))
    ev.check("fixed_local_object_and_all_old_version_bytes_preserved", state["artifacts"][local] == before["artifacts"][local]
             and all(ev.hashes()[key] == value for key, value in old_files.items()))
    historical = ev.evaluate("B", "B::analysis", original)
    ev.check("historical_submission_evaluation_remains_13", historical == original_eval and historical["checks"][0]["expected"] == 13)
    responsibility = {"upstream_correct": a_eval["passed"], "downstream_faithful": evaluation["passed"], "overall_business_goal": actual == 23,
                      "injected_source_errors": 0 if ev.spec["a_correct"] else 1}
    ev.check("upstream_quality_downstream_faithfulness_business_goal_are_separate", responsibility,
             {"upstream_correct": ev.spec["a_correct"], "downstream_faithful": ev.spec["b_faithful"], "overall_business_goal": ev.spec["business_goal"],
              "injected_source_errors": 0 if ev.spec["a_correct"] else 1})
    ev.check("formal_upstream_approval_preserved_even_when_content_fails", a_review == ev.state()["work_items"]["A::production"]["submissions"][-1]["review"] and a_review["decision"] == "accepted")
    return {"responsibility": responsibility, "final_total": actual, "layout": "split" if ev.spec["split"] else "combined", "successor": wid}


def run_case(name, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    ev, error, outcome = Evidence(name, output), None, None
    try:
        outcome = execute(ev)
    except Exception:
        error = traceback.format_exc()
    for name_ in CHECKS:
        if not any(c["name"] == name_ for c in ev.checks):
            ev.checks.append({"name": name_, "passed": False, "not_executed": True})
    result = {"case": name, "specification": ev.spec, "construction_error": error, "checks": ev.checks,
              "passed": error is None and all(c["passed"] for c in ev.checks), "calls": ev.calls,
              "observations": ev.observations, "evaluations": ev.evaluations, "outcome": outcome}
    if ev.world:
        write_json(output / "final-state.json", ev.state())
        result["immutable_file_sha256"] = ev.hashes()
    write_json(output / "report.json", result)
    return result


def run(output, workers=4):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    before = code_identity()
    started = datetime.now(timezone.utc).isoformat()
    write_json(output / "protocol.json", PROTOCOL)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(lambda name: run_case(name, output / name), CASES))
    comparisons = []
    for condition in ("correct", "wrong_upstream"):
        pair = [next(case for case in results if case["case"] == layout + "_" + condition) for layout in ("combined", "split")]
        comparisons.append({"condition": condition, "passed": all(case["passed"] for case in pair)
                            and pair[0]["outcome"]["responsibility"] == pair[1]["outcome"]["responsibility"]
                            and pair[0]["outcome"]["final_total"] == pair[1]["outcome"]["final_total"]})
    result = {"source_before": before, "source_after": code_identity(), "protocol": PROTOCOL, "started_at": started,
              "ended_at": datetime.now(timezone.utc).isoformat(), "cases": results, "layout_comparisons": comparisons,
              "passed_cases": sum(case["passed"] for case in results), "passed_checks": sum(check["passed"] for case in results for check in case["checks"]),
              "total_checks": len(CHECKS) * len(CASES), "not_executed": sum(check["not_executed"] for case in results for check in case["checks"]),
              "passed": all(case["passed"] for case in results) and all(c["passed"] for c in comparisons)}
    write_json(output / "report.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    result = run(args.output, args.workers)
    print(json.dumps({key: result[key] for key in ("passed", "passed_cases", "passed_checks", "total_checks", "not_executed")}))
    raise SystemExit(0 if result["passed"] else 1)
