"""Read-only software work evidence and existing TeamRollout/MemberView binding.

No model, SQL, test runner or optimizer is invoked. The independent evaluator is
called by the collector after dialogue closure, and its fixed delivery is bound
here to the archived world. Interface-development assets remain non-training.
"""

import copy
import json
from pathlib import Path

from .member_views import member_view
from .online_support import bind_rollout, expected_window
from .software_collaboration_v027 import software_collaboration_facts
from .storage import Store, digest, json_bytes, read_json
from .team_rollout import export_team_rollout, work_validity
from .team_validity import assess_record_permission

VERSION = "software-token-projection-v0.27"
MAPPER = "software-work-methods-v0.27"
VALIDITY = "software-complete-work-v0.27"
CLASSES = (
    "concentrated_delivery",
    "split_sequential",
    "split_independent_branches",
    "split_conflict_resolution",
)


def _bundle(store, state, reference):
    artifact = state["artifacts"][reference["object_id"]]
    version = reference["version_id"]
    content = store.version_path(artifact, version).read_bytes()
    if digest(content) != artifact["versions"][version]["sha256"]:
        raise ValueError("Archived software source bytes differ from their committed version")
    return json.loads(content)


def software_work_evidence(episode, assessment):
    """Recover observed responsibility and patch transformations, not mental use.

    Included patch IDs alone cannot establish consumption. A cross-member edge
    requires a fixed input with an actual author edit and a committed integration
    that changed file bytes. This is execution provenance, not a causal claim
    that every imported line survived or was necessary for final correctness.
    """
    root = Path(episode)
    manifest = read_json(root / "manifest.json")
    if manifest["status"] != "closed":
        raise ValueError("Software evidence requires a closed original episode")
    state = read_json(root / "end/control/state.json")
    start = read_json(root / "start/control/state.json")
    facts = software_collaboration_facts(state)
    old_events = start.get("software_events", [])
    if facts["events"][:len(old_events)] != old_events:
        raise ValueError("Historical software responsibility attribution changed")
    events = facts["events"][len(old_events):]
    for event in events:
        commit = state["operation_commits"].get(event["operation_id"])
        if (commit is None or commit["bound_actor"] != event["actor_id"]
                or commit["public_result"]["action_id"] != event["action_id"]):
            raise ValueError("Software event lacks its actual actor-bound WorldCore receipt")
    if assessment.get("status") not in {"evaluable", "unknown"}:
        raise ValueError("Independent assessment must retain evaluable or unknown status")
    if assessment["status"] == "evaluable" and (
        type(assessment.get("R")) is not int or assessment["R"] not in (0, 1)
    ):
        raise ValueError("Known software responsibility must be a finite Boolean result")
    if assessment["status"] == "unknown" and assessment.get("R") is not None:
        raise ValueError("An unknown independent result cannot be filled with zero")
    submitted = bool(facts["deliveries"])
    if assessment.get("submitted") is not submitted:
        raise ValueError("Independent assessment does not match archived delivery availability")
    store = Store(root / "end")
    delivery = facts["deliveries"][-1] if submitted else None
    if submitted:
        if assessment.get("delivery") != delivery:
            raise ValueError("Assessment must bind the latest fixed archived delivery")
        submitted_bundle = _bundle(store, state, delivery["source_reference"])
        if (digest(json_bytes(submitted_bundle)) != delivery["source_sha256"]
                or digest(json_bytes(submitted_bundle["files"])) != delivery["files_sha256"]):
            raise ValueError("Delivery content or source identity changed")
        acceptance = assessment.get("independent_acceptance", {})
        if assessment["status"] == "evaluable" and (
            acceptance.get("executed") is not True
            or type(acceptance.get("passed")) is not bool
            or assessment["R"] != int(acceptance["passed"])
        ):
            raise ValueError("Known delivery needs independently executed parent acceptance")
        endings = [e for e in events if e["kind"] == "submit"
                   and e.get("delivery_id") == delivery["delivery_id"]]
        if len(endings) != 1:
            raise ValueError("Fixed delivery must originate in this episode")
        # Later edits never change the method or quality of this fixed submission.
        events = [e for e in events if e["sequence"] <= endings[0]["sequence"]]
    elif assessment.get("R") == 1:
        raise ValueError("No fixed delivery cannot receive complete responsibility")

    edits = [e for e in events if e["kind"] == "edit"]
    fixed = {e["patch_id"]: e for e in events if e["kind"] == "patch_fixed"}
    edges, no_effect = [], []
    for event in events:
        if event["kind"] != "integrate":
            continue
        patch = facts["patches"].get(event["patch_id"])
        if patch is None or patch["source_reference"] != event["input_reference"]:
            raise ValueError("Integration input does not match its immutable patch")
        if patch["author"] == event["actor_id"]:
            continue
        before = _bundle(store, state, event["previous_reference"])
        after = _bundle(store, state, event["source_reference"])
        changed = sorted(path for path in after["files"]
                         if after["files"][path] != before["files"].get(path))
        incoming = _bundle(store, state, patch["source_reference"])
        fixing = fixed.get(patch["patch_id"])
        authored = [] if fixing is None else [e for e in edits
            if e["actor_id"] == patch["author"] and e["sequence"] < fixing["sequence"]
            and e["path"] in patch["changed_paths"]
            and e["after_sha256"] == digest(incoming["files"][e["path"]].encode())]
        authored_changed = sorted(set(changed) & {e["path"] for e in authored})
        edge = {"sequence": event["sequence"], "sender": patch["author"],
                "recipient": event["actor_id"], "patch_id": patch["patch_id"],
                "input_reference": copy.deepcopy(event["input_reference"]),
                "output_reference": copy.deepcopy(event["source_reference"]),
                "changed_paths": changed, "authored_changed_paths": authored_changed,
                "conflicts": copy.deepcopy(event["conflicts"]),
                "author_edit_sequences": [e["sequence"] for e in authored
                                          if e["path"] in authored_changed]}
        (edges if authored_changed else no_effect).append(edge)
    return {
        "version": VERSION, "manifest_sha256": digest((root / "manifest.json").read_bytes()),
        "case": copy.deepcopy(facts["case"]), "delivery": copy.deepcopy(delivery),
        "assessment_sha256": digest(json_bytes(assessment)),
        "assessment_status": assessment["status"],
        "parent_acceptance_passed": (assessment.get("independent_acceptance") or {}).get("passed"),
        "events": copy.deepcopy(events), "actual_file_edits": copy.deepcopy(edits),
        "cross_member_patch_transformations": edges,
        "integrations_without_current_authored_byte_change": no_effect,
        "responsibility_history": [copy.deepcopy(e) for e in events
                                   if e["kind"] in {"claim", "delegate"}],
        "declared_dependencies": [copy.deepcopy(e) for e in events
                                  if e["kind"] == "dependency_declared"],
        "scope": "Observed task, file and patch execution; no message-ID category, causal contribution or claim that all imported content survives.",
    }


def map_software_method(rollout, evidence):
    """Map actual organization routes only after independently valid work."""
    result = {"version": VERSION, "rollout_id": rollout["rollout_id"], "spec_id": MAPPER,
              "status": "unmapped", "class_id": None,
              "evidence_sha256": digest(json_bytes(evidence))}
    if rollout.get("manifest_sha256") != evidence["manifest_sha256"]:
        raise ValueError("Method evidence belongs to another original rollout")
    if rollout["work_validity"]["value"] is not True:
        return {**result, "reason": "Complete work false or unknown; trusted failure remains base RL"}
    delivery = evidence["delivery"]
    if not delivery:
        return {**result, "reason": "No fixed software delivery"}
    integrator = delivery["actor_id"]
    edits = evidence["actual_file_edits"]
    edges = [e for e in evidence["cross_member_patch_transformations"]
             if e["recipient"] == integrator]
    own_edits = [e for e in edits if e["actor_id"] == integrator]
    if not own_edits:
        return {**result, "reason": "Integrator has no current authored edit; forwarding is not a production route"}
    if edges:
        if any(edge["conflicts"] for edge in edges):
            category = "split_conflict_resolution"
        elif min(e["sequence"] for e in own_edits) > min(e["sequence"] for e in edges):
            category = "split_sequential"
        else:
            category = "split_independent_branches"
    elif len({e["actor_id"] for e in edits}) == 1:
        category = "concentrated_delivery"
    else:
        return {**result, "reason": "Multiple editors without a verified cross-workspace transform; do not infer consumption from declarations"}
    return {**result, "status": "mapped", "class_id": category,
            "reason": "Fixed valid delivery with actor-bound task/file/integration route",
            "scope": "Structural execution route; neither method quality ordering nor causal value"}


def export_software_episode(prepared, episode, assessment, *, declaration, slot_id, captured):
    """Connect software evidence to existing raw member projection and support.

    The current builder deliberately supplies development assets only. Even a
    complete positive trajectory from it is not admitted as software training.
    A future source-qualified training builder must declare its own frozen scope.
    """
    root = Path(episode)
    manifest = read_json(root / "manifest.json")
    case = prepared.case
    if manifest["scenario"].get("variation", {}).get("software_case") != case:
        raise ValueError("Actual software case must be fixed before the first opportunity")
    window = expected_window(declaration, slot_id)
    slot = next(s for s in declaration["slots"] if s["slot_id"] == slot_id)
    if (window["xi_id"] != case["case_id"] or slot["mapping_spec_id"] != MAPPER
            or slot["active_members"] != list(prepared.active_roles)):
        raise ValueError("Exact software situation, stable members and Mapper differ")
    members = {role["role_id"]: {"actor_id": role["actor"], "origin": "target_model"}
               for role in prepared.scenario["roles"]}
    common = assess_record_permission(root, members=members, independent_capture=captured,
                                      spec_id=VALIDITY, window=window)
    evidence = software_work_evidence(root, assessment)
    if evidence["case"] != case:
        raise ValueError("Archived software work uses another case")
    checks = [check for component in common["components"].values()
              for check in component["checks"]]
    ref = {"manifest_sha256": evidence["manifest_sha256"],
           "independent_assessment_sha256": evidence["assessment_sha256"]}
    checks.extend([
        {"dimension": "basis", "value": True,
         "reason": "Public case, immutable source and actual integration inputs bind; no manual adoption ceremony",
         "evidence": ref},
        {"dimension": "delivery", "value": (
            None if assessment["status"] == "unknown" else
            bool(evidence["delivery"] and evidence["parent_acceptance_passed"])),
         "reason": "Fixed combined delivery independently satisfies the declared API and regression contract",
         "evidence": ref},
    ])
    validity = work_validity(checks, spec_id=VALIDITY)
    reward = {"version": VERSION, "episode_id": manifest["episode_id"],
              "manifest_sha256": evidence["manifest_sha256"],
              "eligible": assessment["status"] == "evaluable", "reward": assessment["R"],
              "completed": assessment["R"] == 1, "scope": case["task_type"],
              "source_assessment_sha256": evidence["assessment_sha256"],
              "spec": copy.deepcopy(prepared.reward_spec)}
    rollout = export_team_rollout(root, window=window, members=members,
                                  validity=validity, reward=reward)
    # This scope is enforced again at the updater entry. Development successes
    # do not become on-policy training merely because a token trace is present.
    rollout["online_scope"] = {"version": VERSION, "purpose": "interface_development",
                               "optimizer_update_allowed": False,
                               "composition_reconfiguration_eligible": False,
                               "source_training_admission": False}
    mapping = map_software_method(rollout, evidence)
    bound = bind_rollout(declaration, slot_id, rollout, mapping=mapping)
    views = {member: member_view(rollout, member) for member in members}
    return {"slot_id": slot_id, "rollout": rollout, "reward": reward,
            "active_members": list(prepared.active_roles), "mapping": mapping}, {
        "version": VERSION, "semantic_evidence": evidence, "work_validity": validity,
        "method_mapping": mapping, "member_views": views,
        "binding_matches_views": bound["member_views"] == views,
        "training_probability_qualified": False,
        "optimizer_update_allowed": False,
        "scope": "Software development projection; not current training support or learning benefit",
    }
