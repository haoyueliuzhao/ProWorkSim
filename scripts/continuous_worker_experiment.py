"""P4: public multi-work scheduling, persisted blocking and later continuation.

Controllers install declared packages or execute explicit provider/revision actions.
The worker receives only opaque ports; its recorded returns are compared with an
independent capture at the port boundary, never reconstructed from final state.
"""

import argparse
import copy
import json
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from proworksim.audit import code_identity
from proworksim.continuous_worker import ContinuousWorker
from proworksim.core.world import WorldSpec
from proworksim.storage import atomic_write, digest, json_bytes
from proworksim.world_core import WorldCore

GROUPS = ("blocked_resume", "revision_multiple", "missing_route", "budget", "environment_error", "multiple_sources", "published_successor")
COMMON = ("opaque_public_ports", "authentic_original_transcript", "advertised_tools_only",
          "at_most_one_call_per_step", "all_content_actions_have_exact_work_context")
CHECKS = {
    "blocked_resume": COMMON + ("A_has_real_unavailable_condition", "B_completes_while_A_blocked",
        "provider_availability_is_public_action", "checkpoint_preserves_prior_observations",
        "resumed_A_uses_new_request", "new_information_resolves_new_condition", "both_deliveries_pass"),
    "revision_multiple": COMMON + ("initial_multiwork_deliveries_pass", "revision_creates_exact_new_work",
        "new_work_has_new_binding_and_read", "unrelated_work_and_old_submissions_preserved",
        "original_observations_preserved", "new_delivery_passes_v2_contract"),
    "missing_route": COMMON + ("worker_waiting_is_distinct_from_world_condition",
        "no_fabricated_A_request_or_delivery", "B_can_finish_despite_A_missing_route"),
    "budget": COMMON + ("one_action_budget_is_explicit_truncation", "same_worker_continues_after_budget",
        "both_deliveries_pass"),
    "environment_error": COMMON + ("real_pause_between_observe_and_action", "actual_rejection_is_environment_error",
        "no_delivery_claim_after_error"),
    "multiple_sources": COMMON + ("both_exact_sources_read", "two_work_bindings_and_dependencies",
        "independent_total15_and_content_pass"),
    "published_successor": COMMON + ("original_public_delivery11_accepted",
        "publication_event_creates_one_successor", "new_obligation_has_release_and_requirement_context",
        "worker_discovers_new_work_and_exact_v2_binding", "new_public_delivery19_passes",
        "old_work_binding_files_and_observations_preserved", "controller_only_writes_and_publishes_after_acceptance"),
}
PROTOCOL = {
    "suite": "public-continuous-work-P4-v0.8", "groups": GROUPS, "checks": CHECKS,
    "scope": "Each group has one WorldCore and A/B projects, one writer, explicit interleaving; no model or trained policy",
    "worker_inputs": "Opaque ports expose only tools/observe/call; requirements, routes, exact work IDs, policy targets, expressions and bytes are discovered publicly",
    "actions": "Finite adopt/update, request/wait, exact read, JSON create/write and submit, with at most one action per scheduler step",
    "independent_literals": {"A_v1": 11, "B": 7, "A_v2": 19, "multiple_sources": 15},
    "alternative_paths": "Several currently owned works and several ports round-robin; worker builds one combined JSON, while P3 independently accepts two-file layout",
    "controller_events": "Availability changes after actual A blocked/B completed outcome; formal requirement revision after real initial completion; a deliberate authorized pause after observation before first adoption creates an actual rejected tool call",
    "exits": ["completed", "submitted", "worker_waiting", "world_blocked", "budget_exhausted", "environment_error"],
    "pre_freeze_supplement": "published_successor adds a separate release-to-obligation-to-public-worker closed loop after the original six-group 55-check development protocol; earlier development reports do not cover this supplement",
    "checkpoint_boundary": "Explicit completed step-result checkpoint, JSON roundtrip of public progress/transcript only; not arbitrary process crash or exactly-once policy recovery",
    "comparison": "Compare original captured definitions/observations/action args/returns to worker transcript; inspect exact work/submission/binding and immutable bytes separately after execution. Replacement updates the old submission's current_applicability projection to superseded_requirements; every other submission field, including approval/answer/versions/adoption snapshot, is compared unchanged. Unrelated works are compared in full.",
    "limitations": ["Transparent finite program; no general planning claim", "P4 arithmetic is a declared scalar sum, not finance-quality evaluation", "Paused-tool rejection is a deliberate environment failure probe, not a spontaneous production failure", "No API/GPU/training or new crash cuts in P4"],
}


def write(path, value):
    atomic_write(path, json_bytes(value))
    return {"path": str(path), "sha256": digest(path.read_bytes()), "bytes": path.stat().st_size}


def package(pid, *, mode="existing", multiple=False):
    owner = "alice" if pid == "A" else "bob"
    value = 11 if pid == "A" else 7
    private = mode == "unavailable"
    works = [{
        "work_id": wid, "owner": owner, "goal": "Consume the publicly specified exact source",
        "approval_policy": "delivery_only", "requirement_dimension": "requirements",
        "requirements": {"input_policy": "fixed", "input_version": "v1"},
        "deliverable_contract": {"min_files": 1, "max_files": 1, "allowed_roles": ["report"],
            "allowed_kinds": ["json"], "required_fields": ["result", "source_ref"],
            "content_checks": [{"kind": "json_matches_source_field", "path": ["result"],
                "adoption_alias": "input", "source_path": ["amount"], "reference_path": ["source_ref"]}]},
    } for wid in (["work-1", "work-2"] if multiple else ["work-1"])]
    result = {
        "project_id": pid, "goal": "Finite continuous public work", "participants": [owner, "manager"],
        "objects": [] if mode == "missing" else [{
            "alias": "input", "filename": "input.json", "kind": "json", "owner": "manager" if private else owner,
            "readers": ["manager"] if private else [owner, "manager"],
            "writers": ["manager"] if private else ["manager", owner], "data": {"amount": value},
        }], "works": works,
        "grants": [{"actor_id": owner, "power": power, "subject": "artifact"}
                   for power in ("create_object", "adopt", "share", "publish")]
                  + [{"actor_id": "manager", "power": "revise_requirement", "subject": "requirements"}],
        "provenance": {"kind": "synthetic", "source_evidence_refs": [],
                       "note": "Independent literal values; finite mechanism witness"},
    }
    if private:
        result["information_routes"] = [{"route_id": "facts", "work_id": "work-1", "provider": "manager",
            "object_alias": "input", "purpose": "evidence", "delay": 2, "availability": "unavailable",
            "version_policy": "work_requirement"}]
        result["grants"].append({"actor_id": "manager", "power": "provide", "subject": "evidence",
                                 "work_nodes": ["work-1"], "object_ids": ["input"]})
    return result


def public_port(session, label, captured, before_call=None):
    def record(kind, value):
        captured.append({"sequence": len(captured), "port": label, "kind": kind,
                         "value": copy.deepcopy(value)})

    class Port:
        __slots__ = ()

        def tools(self):
            result = session.tools()
            record("tools", result)
            return result

        def observe(self):
            result = session.observe()
            record("observation", result)
            return result

        def call(self, action, request_key=None, **arguments):
            if before_call is not None:
                before_call(action)
            entry = {"action": action, "arguments": copy.deepcopy(arguments), "request_key": request_key}
            try:
                result = session.call(action, request_key=request_key, **arguments)
            except Exception as exc:
                entry["exception"] = {"type": type(exc).__name__, "message": str(exc)}
                record("tool_call", entry)
                raise
            entry["response"] = copy.deepcopy(result)
            record("tool_call", entry)
            return result

    return Port()


class Evidence:
    def __init__(self, root, group):
        self.root, self.group = root, group
        self.checks, self.controller, self.captured, self.outcomes = [], [], [], []
        self.world = WorldCore.create(root / "world", WorldSpec(
            "continuous-worker-" + group, {actor: {} for actor in ("alice", "bob", "manager")},
            applications=["files", "spreadsheets"], publication_policy="explicit",
            bootstrap_grants=[{"actor_id": "manager", "scope": "world", "power": power}
                              for power in ("install_project", "pause_world")],
        ))
        self.worker = None
        self.step_calls = []

    def call(self, session, action, **arguments):
        response = session.call(action, **arguments)
        self.controller.append({"actor": session.actor_id, "project": session.project_id,
                                "action": action, "arguments": copy.deepcopy(arguments), "response": response})
        if not response.get("ok"):
            raise AssertionError(self.controller[-1])
        return response["result"]

    def check(self, name, actual, expected=True):
        if name not in CHECKS[self.group] or any(c["name"] == name for c in self.checks):
            raise AssertionError("Undeclared or duplicate check: " + name)
        self.checks.append({"name": name, "actual": actual, "expected": expected,
                            "passed": actual == expected, "not_executed": False})

    def install(self, a_mode="existing", multiple=False, custom_a=None):
        manager = self.world.session("manager")
        self.call(manager, "install_project", package=custom_a or package("A", mode=a_mode, multiple=multiple))
        self.call(manager, "install_project", package=package("B"))

    def ports(self, labels=("A", "B"), hook=None):
        return {label: public_port(self.world.session("alice" if label == "A" else "bob", label),
                                   label, self.captured, hook if label == "A" else None) for label in labels}

    def run(self, budget=40):
        previous = self.worker.actions
        outcome = self.worker.run(max_actions=budget)
        deltas = [int(step["action_performed"]) for step in outcome["steps"]]
        self.step_calls.append({"action_delta": self.worker.actions - previous,
                                "reported_calls": sum(deltas), "max_step_calls": max(deltas, default=0)})
        self.outcomes.append(copy.deepcopy(outcome))
        return outcome

    def evaluations(self):
        result = []
        for wid, item in self.world.store.load()["work_items"].items():
            for sub in item["submissions"]:
                result.append({"work_id": wid, "submission_id": sub["submission_id"],
                               "evaluation": self.world.evaluate_submission(item["project_id"], wid, sub["submission_id"])})
        return result

    def delivered_values(self):
        """Read fixed submitted JSON bytes for the separately declared scalar oracle."""
        state = self.world.store.load()
        result = {}
        for wid, item in state["work_items"].items():
            if not item["submissions"]:
                continue
            sub = item["submissions"][-1]
            aid, vid = next(iter(sub["artifact_versions"].items()))
            data = json.loads(self.world.store.version_path(state["artifacts"][aid], vid).read_bytes())
            result[wid] = data.get("result", data.get("total"))
        return result

    def common(self, ports):
        self.check("opaque_public_ports", all(not hasattr(port, "__dict__") and
                   {name for name in dir(port) if not name.startswith("_")} == {"tools", "observe", "call"}
                   for port in ports.values()))
        self.check("authentic_original_transcript", self.worker.transcript == self.captured)
        tools, all_advertised = {}, True
        calls = []
        for entry in self.captured:
            if entry["kind"] == "tools":
                tools[entry["port"]] = {d["name"] for d in entry["value"]}
            elif entry["kind"] == "tool_call":
                all_advertised &= entry["value"]["action"] in tools[entry["port"]]
                calls.append(entry)
        self.check("advertised_tools_only", all_advertised)
        self.check("at_most_one_call_per_step", all(v["max_step_calls"] <= 1 and
                   v["action_delta"] == v["reported_calls"] for v in self.step_calls))
        self.check("all_content_actions_have_exact_work_context", all(
            entry["value"]["arguments"].get("work_id", "").startswith(entry["port"] + "::")
            for entry in calls if entry["value"]["action"] in {"read_object", "sheet_read", "create_object", "write_object"}))


def blocked_resume(ev):
    ev.install(a_mode="unavailable")
    ports = ev.ports()
    ev.worker = ContinuousWorker(ports, run_id="P4-blocked")
    first = ev.run()
    state = ev.world.store.load()
    conditions = [c for c in state["condition_specs"].values() if c["work_item_id"] == "A::work-1"]
    ev.check("A_has_real_unavailable_condition", first["status"] == "world_blocked" and any(c["status"] == "unavailable" for c in conditions))
    ev.check("B_completes_while_A_blocked", state["work_items"]["B::work-1"]["status"] == "accepted" and not state["work_items"]["A::work-1"]["submissions"])
    prefix = copy.deepcopy(ev.worker.transcript)
    checkpoint = json.loads(json.dumps(ev.worker.snapshot()))
    write(ev.root / "worker-checkpoint.json", checkpoint)
    changed = ev.call(ev.world.session("manager", "A"), "set_information_availability",
                      route_id="facts", available=True, reason="Declared material is now available")
    ev.check("provider_availability_is_public_action", changed["changed"] and changed["availability"] == "available")
    ev.worker = ContinuousWorker(ports, checkpoint=checkpoint)
    second = ev.run()
    ev.check("checkpoint_preserves_prior_observations", ev.worker.transcript[:len(prefix)] == prefix)
    calls = [c["value"] for c in ev.captured if c["kind"] == "tool_call" and c["value"]["action"] == "request_information"]
    request_ids = [c["response"]["result"]["request_id"] for c in calls]
    ev.check("resumed_A_uses_new_request", len(request_ids) == 2 and len(set(request_ids)) == 2)
    after = ev.world.store.load()
    statuses = [c["status"] for c in after["condition_specs"].values() if c["work_item_id"] == "A::work-1"]
    ev.check("new_information_resolves_new_condition", "superseded" in statuses and "resolved" in statuses)
    evaluations = ev.evaluations()
    ev.check("both_deliveries_pass", second["status"] == "completed" and len(evaluations) == 2 and all(e["evaluation"]["passed"] for e in evaluations)
             and ev.delivered_values() == {"A::work-1": 11, "B::work-1": 7})
    ev.common(ports)


def revision_multiple(ev):
    ev.install(multiple=True)
    ports = ev.ports()
    ev.worker = ContinuousWorker(ports, run_id="P4-revision")
    first = ev.run()
    before = ev.world.store.load()
    prefix = copy.deepcopy(ev.worker.transcript)
    write(ev.root / "before-revision-state.json", before)
    evaluations = ev.evaluations()
    ev.check("initial_multiwork_deliveries_pass", first["status"] == "completed" and len(evaluations) == 3 and all(e["evaluation"]["passed"] for e in evaluations)
             and ev.delivered_values() == {"A::work-1": 11, "A::work-2": 11, "B::work-1": 7})
    hashes = {f"{aid}@{vid}": digest(ev.world.store.version_path(artifact, vid).read_bytes())
              for aid, artifact in before["artifacts"].items() for vid in artifact["versions"]}
    manager = ev.world.session("manager", "A")
    ev.call(manager, "write_object", alias="input", data={"amount": 19})
    revised = ev.call(manager, "revise", work_id="work-1", updates={"requirements": {"input_policy": "fixed", "input_version": "v2"}}, reason="New exact input required for replacement work")
    new_id = revised["replacements"]["A::work-1"]
    ev.check("revision_creates_exact_new_work", new_id != "A::work-1")
    second = ev.run()
    after = ev.world.store.load()
    new_binding = after["adoptions"].get(new_id + "::input")
    new_reads = [e for e in ev.captured if e["kind"] == "tool_call" and e["value"]["action"] == "read_object"
                 and e["value"]["arguments"].get("work_id") == new_id]
    ev.check("new_work_has_new_binding_and_read", bool(new_binding) and new_binding["version_id"] == "v2" and bool(new_reads)
             and after["adoptions"]["A::work-1::input"]["version_id"] == "v1")
    preserved = all(digest(ev.world.store.version_path(after["artifacts"][key.rsplit("@", 1)[0]], key.rsplit("@", 1)[1]).read_bytes()) == value for key, value in hashes.items())
    old_submissions = after["work_items"]["A::work-1"]["submissions"]
    def immutable_submission_facts(submissions):
        return [{key: value for key, value in sub.items() if key != "current_applicability"}
                for sub in submissions]
    ev.check("unrelated_work_and_old_submissions_preserved", preserved
             and immutable_submission_facts(old_submissions) == immutable_submission_facts(before["work_items"]["A::work-1"]["submissions"])
             and all(sub["current_applicability"] == "superseded_requirements" for sub in old_submissions)
             and after["work_items"]["A::work-2"] == before["work_items"]["A::work-2"]
             and after["work_items"]["B::work-1"] == before["work_items"]["B::work-1"])
    ev.check("original_observations_preserved", ev.worker.transcript[:len(prefix)] == prefix)
    ev.check("new_delivery_passes_v2_contract", second["status"] == "completed" and any(e["work_id"] == new_id and e["evaluation"]["passed"] for e in ev.evaluations())
             and ev.delivered_values()[new_id] == 19)
    ev.common(ports)


def missing_route(ev):
    ev.install(a_mode="missing")
    ports = ev.ports()
    ev.worker = ContinuousWorker(ports, run_id="P4-missing")
    outcome = ev.run()
    state = ev.world.store.load()
    ev.check("worker_waiting_is_distinct_from_world_condition", outcome["status"] == "worker_waiting" and not state["condition_specs"])
    ev.check("no_fabricated_A_request_or_delivery", not any(e["port"] == "A" and e["kind"] == "tool_call" for e in ev.captured)
             and not state["work_items"]["A::work-1"]["submissions"])
    ev.check("B_can_finish_despite_A_missing_route", state["work_items"]["B::work-1"]["status"] == "accepted")
    ev.common(ports)


def budget(ev):
    ev.install()
    ports = ev.ports()
    ev.worker = ContinuousWorker(ports, run_id="P4-budget")
    first = ev.run(1)
    ev.check("one_action_budget_is_explicit_truncation", first["status"] == "budget_exhausted" and first["actions"] == 1)
    second = ev.run()
    ev.check("same_worker_continues_after_budget", second["status"] == "completed" and second["actions"] > first["actions"])
    ev.check("both_deliveries_pass", len(ev.evaluations()) == 2 and all(e["evaluation"]["passed"] for e in ev.evaluations())
             and ev.delivered_values() == {"A::work-1": 11, "B::work-1": 7})
    ev.common(ports)


def environment_error(ev):
    ev.install()
    fired = []

    def pause_before_first_action(action):
        if not fired:
            fired.append(action)
            ev.call(ev.world.session("manager"), "pause")

    ports = ev.ports(hook=pause_before_first_action)
    ev.worker = ContinuousWorker(ports, run_id="P4-environment")
    outcome = ev.run()
    ev.check("real_pause_between_observe_and_action", fired == ["adopt"] and ev.world.store.load()["world_status"] == "paused")
    calls = [e for e in ev.captured if e["kind"] == "tool_call"]
    ev.check("actual_rejection_is_environment_error", outcome["status"] == "environment_error" and len(calls) == 1 and not calls[0]["value"]["response"]["ok"])
    ev.check("no_delivery_claim_after_error", not ev.evaluations())
    ev.common(ports)


def multiple_sources(ev):
    a = package("A")
    a["objects"][0].update(alias="local", filename="local.json", data={"offset": 3})
    work = a["works"][0]
    work["requirements"] = {"input_policies": {"external": "current_published", "local": "fixed"}, "input_versions": {"local": "v1"}}
    work["deliverable_contract"]["required_fields"] = ["total", "sources"]
    work["deliverable_contract"]["content_checks"] = [{"kind": "json_linear_sources", "path": ["total"], "constant": 0,
        "sources": [{"alias": "external", "kind": "json_field", "source_path": ["rate"], "reference_path": ["sources", "external"], "coefficient": 1},
                    {"alias": "local", "kind": "json_field", "source_path": ["offset"], "reference_path": ["sources", "local"], "coefficient": 1}]}]
    ev.install(custom_a=a)
    producer = ev.world.session("bob", "B")
    source = ev.call(producer, "create_object", alias="upstream", filename="upstream.json", data={"rate": 12})
    ref = {"object_id": source["object_id"], "version_id": source["version_id"]}
    ev.call(producer, "share", **ref, target_project="A", actor_ids=["alice", "manager"], follow_updates=True)
    ev.call(producer, "publish", **ref, target_projects=["A"])
    ev.call(ev.world.session("alice", "A"), "adopt", alias="external", **ref, policy="current_published", work_ids=["work-1"])
    ports = ev.ports()
    ev.worker = ContinuousWorker(ports, run_id="P4-multiple")
    outcome = ev.run()
    state = ev.world.store.load()
    reads = [entry["value"]["arguments"] for entry in ev.captured if entry["port"] == "A" and entry["kind"] == "tool_call" and entry["value"]["action"] == "read_object"]
    ev.check("both_exact_sources_read", len(reads) == 2 and {r["object_id"] for r in reads} == {source["object_id"], state["workspaces"]["A"]["local"]})
    sub = state["work_items"]["A::work-1"]["submissions"][-1]
    aid, vid = next(iter(sub["artifact_versions"].items()))
    deps = state["artifacts"][aid]["versions"][vid]["derived_from"]
    ev.check("two_work_bindings_and_dependencies", len(sub["adoption_snapshot"]) == 2 and len(deps) == 2 and all(a["work_id"] == "A::work-1" for a in sub["adoption_snapshot"].values()))
    actual = json.loads(ev.world.store.version_path(state["artifacts"][aid], vid).read_bytes())
    evaluations = ev.evaluations()
    ev.check("independent_total15_and_content_pass", actual["total"] == 15 and outcome["status"] == "completed" and all(e["evaluation"]["passed"] for e in evaluations))
    ev.common(ports)



def published_successor(ev):
    manager = ev.world.session("manager")
    ev.call(manager, "install_project", package=package("A"))
    producer = ev.world.session("alice", "A")
    created = ev.call(producer, "create_object", alias="released-source", filename="released-source.json",
                      data={"amount": 11})
    ref = {"object_id": created["object_id"], "version_id": created["version_id"]}
    b = package("B")
    b["objects"] = []
    b["works"][0]["requirements"] = {"input_policy": "current_published"}
    b["maintenance_rules"] = [{
        "rule_id": "maintain-after-acceptance", "source": {"object_id": ref["object_id"], "source_project": "A"},
        "work_nodes": ["work-1"], "when": ["accepted"], "effect": "successor", "actor": "manager",
        "updates": {"goal": "Maintain delivery against the newly published interface",
                    "requirements": {"input_policy": "current_published"}},
    }]
    ev.call(manager, "install_project", package=b)
    ev.call(producer, "share", **ref, target_project="B", actor_ids=["bob", "manager"], follow_updates=True)
    ev.call(producer, "publish", **ref, target_projects=["B"])
    ev.call(ev.world.session("bob", "B"), "adopt", alias="input", **ref,
            policy="current_published", work_ids=["work-1"])
    ports = ev.ports(labels=("B",))
    ev.worker = ContinuousWorker(ports, run_id="P4-successor")
    first = ev.run()
    before = ev.world.store.load()
    prefix = copy.deepcopy(ev.worker.transcript)
    prior_evaluations = ev.evaluations()
    ev.check("original_public_delivery11_accepted", first["status"] == "completed"
             and before["work_items"]["B::work-1"]["status"] == "accepted"
             and ev.delivered_values() == {"B::work-1": 11}
             and len(prior_evaluations) == 1 and prior_evaluations[0]["evaluation"]["passed"])
    write(ev.root / "before-successor-state.json", before)
    hashes = {f"{aid}@{vid}": digest(ev.world.store.version_path(artifact, vid).read_bytes())
              for aid, artifact in before["artifacts"].items() for vid in artifact["versions"]}
    checkpoint = json.loads(json.dumps(ev.worker.snapshot()))
    write(ev.root / "worker-checkpoint.json", checkpoint)
    controller_boundary = len(ev.controller)
    ev.call(producer, "write_object", alias="released-source", data={"amount": 19})
    published = ev.call(producer, "publish", alias="released-source", version_id="v2", target_projects=["B"])
    after_release = ev.world.store.load()
    new_ids = sorted(set(after_release["work_items"]) - set(before["work_items"]))
    impacts = list(after_release["maintenance_impacts"].values())
    ev.check("publication_event_creates_one_successor", len(new_ids) == 1 and len(impacts) == 1
             and impacts[0]["result"]["effect"] == "successor"
             and impacts[0]["result"]["outcome"] == "applied"
             and {aid: artifact for aid, artifact in after_release["artifacts"].items() if artifact.get("project_id") == "B"}
                 == {aid: artifact for aid, artifact in before["artifacts"].items() if artifact.get("project_id") == "B"})
    if len(new_ids) != 1:
        raise AssertionError({"successor_ids": new_ids, "publish": published})
    new_id = new_ids[0]
    work = after_release["work_items"][new_id]
    release = next(release for release in after_release["releases"]
                   if release["object_id"] == ref["object_id"] and release["version_id"] == "v2")
    ev.check("new_obligation_has_release_and_requirement_context",
             work["previous_obligation_id"] == "B::work-1" and work["requirement_version"] == 2
             and work["maintenance_trigger"]["release_id"] == release["release_id"]
             and work["maintenance_trigger"]["source"] == {"object_id": ref["object_id"], "version_id": "v2"}
             and work["requirements"]["input_policy"] == "current_published")
    ev.worker = ContinuousWorker(ports, checkpoint=checkpoint)
    second = ev.run()
    after = ev.world.store.load()
    binding = after["adoptions"].get(new_id + "::input")
    public_work_seen = any(entry["kind"] == "observation" and new_id in entry["value"]["work_items"]
                          for entry in ev.captured[len(prefix):])
    ev.check("worker_discovers_new_work_and_exact_v2_binding", public_work_seen and binding is not None
             and binding["work_id"] == new_id and binding["requirement_version"] == 2
             and binding["version_id"] == "v2" and binding["object_id"] == ref["object_id"])
    evaluations = ev.evaluations()
    ev.check("new_public_delivery19_passes", second["status"] == "completed"
             and ev.delivered_values() == {"B::work-1": 11, new_id: 19}
             and len(evaluations) == 2 and all(e["evaluation"]["passed"] for e in evaluations))
    files_preserved = all(digest(ev.world.store.version_path(
        after["artifacts"][key.rsplit("@", 1)[0]], key.rsplit("@", 1)[1]).read_bytes()) == sha
        for key, sha in hashes.items())
    ev.check("old_work_binding_files_and_observations_preserved", files_preserved
             and after["work_items"]["B::work-1"] == before["work_items"]["B::work-1"]
             and after["work_items"]["A::work-1"] == before["work_items"]["A::work-1"]
             and after["adoptions"]["B::work-1::input"] == before["adoptions"]["B::work-1::input"]
             and ev.worker.transcript[:len(prefix)] == prefix
             and [e for e in evaluations if e["work_id"] == "B::work-1"] == prior_evaluations)
    ev.check("controller_only_writes_and_publishes_after_acceptance",
             [call["action"] for call in ev.controller[controller_boundary:]] == ["write_object", "publish"])
    ev.common(ports)


def run_group(output, group):
    root = Path(output) / group
    root.mkdir(parents=True, exist_ok=False)
    ev, error = Evidence(root, group), None
    try:
        globals()[group](ev)
    except Exception as exc:
        error = {"error": type(exc).__name__ + ": " + str(exc), "traceback": traceback.format_exc()}
    present = {check["name"] for check in ev.checks}
    checks = ev.checks + [{"name": name, "passed": False, "not_executed": True}
                           for name in CHECKS[group] if name not in present]
    record = {"group": group, "checks": checks, "error": error,
              "controller_calls": ev.controller, "outcomes": ev.outcomes,
              "world_root": str(ev.world.store.root), "step_call_counts": ev.step_calls,
              "port_capture": write(root / "port-capture.json", ev.captured),
              "worker_checkpoint": write(root / "final-worker-checkpoint.json", ev.worker.snapshot()) if ev.worker else None,
              "passed": error is None and all(check["passed"] for check in checks)}
    write(root / "report.json", record)
    return record


def run_experiment(output, workers=4):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    before = code_identity()
    write(output / "protocol.json", PROTOCOL)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        groups = list(pool.map(lambda group: run_group(output, group), GROUPS))
    checks = [check for group in groups for check in group["checks"]]
    result = {"protocol": PROTOCOL, "source_before": before, "source_after": code_identity(),
              "script_sha256": digest(Path(__file__).read_bytes()), "groups": groups,
              "check_count": len(checks), "check_pass_count": sum(check["passed"] for check in checks),
              "not_executed_count": sum(check["not_executed"] for check in checks),
              "passed": all(group["passed"] for group in groups),
              "resources": {"model_calls": 0, "GPU": False, "training": False}}
    write(output / "report.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    result = run_experiment(args.output, args.workers)
    print(json.dumps({key: result[key] for key in ("passed", "check_count", "check_pass_count", "not_executed_count")}, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
