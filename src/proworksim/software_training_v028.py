"""Conservative net-delivery routes, with immutable v027 evidence/export contracts.

This mapper reads archived versions only. It never executes code, assigns causal
value, repairs failed work, or upgrades development assets to training sources.
The limited Python contract roots are explicit; unsupported new source families
require their own frozen mapper instead of silently inheriting these categories.
"""

import ast
import copy
from functools import lru_cache
from pathlib import Path

from .member_views import member_view
from .online_support import bind_rollout, expected_window
from .software_collaboration_v027 import software_collaboration_facts
from .software_training_v027 import _bundle, software_work_evidence as original_evidence
from .storage import Store, digest, json_bytes, read_json
from .team_rollout import export_team_rollout, work_validity
from .team_validity import assess_record_permission

VERSION = "software-token-projection-v0.28"
MAPPER = "software-work-methods-v0.28"
VALIDITY = "software-complete-work-v0.28"
CLASSES = ("concentrated_net_delivery", "net_work_before_import", "net_work_after_import")
CONTRACT_ROOTS = {
    "src/marshmallow/fields.py": {"class:String"},
    "consumer.py": {"class:InventorySchema", "function:load_inventory"},
}


class _WithoutDocstrings(ast.NodeTransformer):
    def generic_visit(self, node):
        node = super().generic_visit(node)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if (node.body and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                    and isinstance(node.body[0].value.value, str)):
                node.body = node.body[1:]
        return node


def _units(text, path):
    """Stable whole-definition AST units; comments/formatting/docstrings vanish.

    An edited definition is indivisible: a later rewrite owns the new definition.
    We deliberately do not infer partial-line authorship or semantic necessity.
    """
    try:
        tree = _WithoutDocstrings().visit(ast.parse(text))
    except (SyntaxError, ValueError):
        return None
    if path == "test_member.py":
        return {"module:member_test": ast.dump(tree, include_attributes=False)}
    result = {}
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            key = ("class:" if isinstance(node, ast.ClassDef) else "function:") + node.name
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            # Import changes alone do not establish delivered implementation.
            continue
        else:
            # Changes outside declared callable roots are retained as uncertain.
            key = "other:" + digest(ast.dump(node, include_attributes=False).encode())
        if key in result:
            return None  # Redefinitions need a richer binding analysis.
        result[key] = ast.dump(node, include_attributes=False)
    return result


def _project_assertion(text):
    """Recognize a bounded directly asserted project API call, not arbitrary tests.

    This is syntactic contract contact plus observed execution, not a proof of
    test coverage. Unsupported indirect/unittest tests remain uncertain.
    """
    tree = ast.parse(text)
    imported = set()
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module in {"marshmallow", "consumer"}:
            imported.update(alias.asname or alias.name for alias in node.names)
        if isinstance(node, ast.Import):
            imported.update(alias.asname or alias.name for alias in node.names
                            if alias.name in {"marshmallow", "consumer"})
    for node in tree.body:
        if not isinstance(node, ast.Assert):
            continue
        for call in ast.walk(node.test):
            if not isinstance(call, ast.Call):
                continue
            head = call.func
            while isinstance(head, (ast.Attribute, ast.Call)):
                head = head.value if isinstance(head, ast.Attribute) else head.func
            if isinstance(head, ast.Name) and head.id in imported:
                return True
    return False


def software_work_evidence(episode, assessment):
    """Bind net AST provenance to the independently checked fixed delivery.

    Trace back through actual immutable edit/integration inputs. Reverted edits,
    overwritten definitions, comments, and no-op imports cannot create support.
    A conflicting/partial merge is not silently interpreted as a collaboration
    method: uncertain provenance remains explicit and prevents classification.
    """
    evidence = original_evidence(episode, assessment)
    root = Path(episode)
    state = read_json(root / "end/control/state.json")
    start = read_json(root / "start/control/state.json")
    facts = software_collaboration_facts(state)
    raw_events = facts["events"][len(start.get("software_events", [])):]
    evidence.update(version=VERSION, original_event_inventory=raw_events,
                    net_delivery_units=[], relevant_net_edits=[],
                    relevant_cross_member_inputs=[], uncertain_net_units=[],
                    excluded_edit_sequences=[], contract_roots={
                        path: sorted(keys) for path, keys in CONTRACT_ROOTS.items()})
    delivery = evidence["delivery"]
    if delivery is None:
        evidence["scope"] = "No fixed delivery; preserve raw events without assigning a method."
        return evidence
    store = Store(root / "end")
    events = evidence["events"]  # v027 binder already cuts at this fixed submission.
    def key(reference):
        return reference["object_id"], reference["version_id"]

    # Reference dictionaries are not required to preserve insertion order.
    writes = {key(e["source_reference"]): e for e in events
              if e["kind"] in {"edit", "integrate"}}

    @lru_cache(maxsize=None)
    def bundle(reference):
        return _bundle(store, state, dict(zip(("object_id", "version_id"), reference)))

    @lru_cache(maxsize=None)
    def units(reference, path):
        return _units(bundle(reference)["files"].get(path, ""), path)

    @lru_cache(maxsize=None)
    def trace(reference, path, unit):
        event = writes.get(reference)
        current = units(reference, path)
        if current is None:
            return None
        if event is None:
            return {"author_edit_sequence": None, "actor_id": None, "inputs": []}
        previous = key(event["previous_reference"])
        before = units(previous, path)
        if before is None:
            return None
        if current.get(unit) == before.get(unit):
            return trace(previous, path, unit)
        if event["kind"] == "edit":
            return {"author_edit_sequence": event["sequence"],
                    "actor_id": event["actor_id"], "inputs": []}
        incoming = key(event["input_reference"])
        source = units(incoming, path)
        if source is None or source.get(unit) != current.get(unit):
            return None
        provenance = trace(incoming, path, unit)
        if provenance is None:
            return None
        patch = facts["patches"][event["patch_id"]]
        edge = {"sequence": event["sequence"], "patch_id": event["patch_id"],
                "sender": patch["author"], "recipient": event["actor_id"],
                "input_reference": copy.deepcopy(event["input_reference"]),
                "output_reference": copy.deepcopy(event["source_reference"]),
                "path": path, "unit": unit, "conflicts": copy.deepcopy(event["conflicts"])}
        return {**provenance, "inputs": provenance["inputs"] + [edge]}

    fixed = key(delivery["source_reference"])
    # Every fixed patch pins the same real source baseline; reject any disagreement.
    bases = {key(e["base_reference"]) for e in events if e["kind"] == "patch_fixed"}
    if len(bases) != 1:
        raise ValueError("A net-delivery route requires one immutable common source baseline")
    baseline = next(iter(bases))
    selected_edits, selected_edges = {}, {}
    for path in (*CONTRACT_ROOTS, "test_member.py"):
        final, original = units(fixed, path), units(baseline, path)
        if final is None or original is None:
            evidence["uncertain_net_units"].append({"path": path, "reason": "unparseable_definition"})
            continue
        changed = sorted(k for k in set(final) | set(original) if final.get(k) != original.get(k))
        for unit in changed:
            item = {"path": path, "unit": unit,
                    "semantic_sha256": digest(final.get(unit, "<deleted>").encode())}
            relevant = unit in CONTRACT_ROOTS.get(path, set())
            if path == "test_member.py":
                # Success of this fixed driver means its second run_path reached
                # and completed test_member.py after the frozen visible suite.
                executed = [e["sequence"] for e in events if e["kind"] == "test"
                            and e.get("executed") and e.get("driver_completed")
                            and e.get("returncode") == 0 and key(e["source_reference"]) == fixed]
                relevant = bool(executed and _project_assertion(bundle(fixed)["files"][path]))
                item["verification_sequences"] = executed
            provenance = trace(fixed, path, unit) if relevant else None
            if provenance is None or provenance["author_edit_sequence"] is None:
                evidence["uncertain_net_units"].append({**item, "reason": "no_conservative_contract_provenance"})
                continue
            item.update(provenance)
            evidence["net_delivery_units"].append(item)
            selected_edits[item["author_edit_sequence"]] = next(
                e for e in events if e["sequence"] == item["author_edit_sequence"])
            for edge in item["inputs"]:
                if edge["sender"] != edge["recipient"]:
                    selected_edges[(edge["sequence"], path, unit)] = edge
    evidence["relevant_net_edits"] = [selected_edits[k] for k in sorted(selected_edits)]
    evidence["relevant_cross_member_inputs"] = [selected_edges[k] for k in sorted(selected_edges)]
    evidence["excluded_edit_sequences"] = [e["sequence"] for e in evidence["actual_file_edits"]
                                          if e["sequence"] not in selected_edits]
    evidence["scope"] = (
        "Whole-definition net AST routes at fixed delivery, with retained directly asserted "
        "and executed project tests; no independence, semantic necessity, causal value, "
        "or coverage inference. Unsupported or partial provenance stays uncertain."
    )
    return evidence


def map_software_method(rollout, evidence):
    result = {"version": VERSION, "rollout_id": rollout["rollout_id"], "spec_id": MAPPER,
              "status": "unmapped", "class_id": None,
              "evidence_sha256": digest(json_bytes(evidence))}
    if rollout.get("manifest_sha256") != evidence["manifest_sha256"]:
        raise ValueError("Method evidence belongs to another original rollout")
    if rollout["work_validity"]["value"] is not True:
        return {**result, "reason": "Complete work false or unknown; no positive method support"}
    if not evidence["delivery"] or evidence["uncertain_net_units"]:
        return {**result, "reason": "No fixed delivery or conservative net provenance is uncertain"}
    integrator = evidence["delivery"]["actor_id"]
    own = [e for e in evidence["relevant_net_edits"] if e["actor_id"] == integrator]
    if not own:
        return {**result, "reason": "No current retained contract edit by the final integrator"}
    edges = [e for e in evidence["relevant_cross_member_inputs"] if e["recipient"] == integrator]
    if edges:
        if any(e["conflicts"] for e in edges):
            return {**result, "reason": "Conflicting merge requires richer provenance; no repair category inferred"}
        category = ("net_work_before_import" if min(e["sequence"] for e in own)
                    < min(e["sequence"] for e in edges) else "net_work_after_import")
    elif {e["actor_id"] for e in evidence["relevant_net_edits"]} == {integrator}:
        # An actual conflict/import discarded by a final rewrite does not prove
        # single-person production. Preserve that ambiguity rather than rename it.
        attempted = [e for e in evidence["cross_member_patch_transformations"]
                     if e["recipient"] == integrator]
        if attempted:
            return {**result, "reason": "Imported work was overwritten or partially rewritten; attribution uncertain"}
        category = "concentrated_net_delivery"
    else:
        return {**result, "reason": "No retained cross-member contract input establishes the route"}
    return {**result, "status": "mapped", "class_id": category,
            "reason": "Fixed valid delivery with retained contract edit/input/verification provenance",
            "scope": "Neutral observed net-work order; no independent-branch or causal-method claim"}


def export_software_episode(prepared, episode, assessment, *, declaration, slot_id, captured):
    """Reuse raw TeamRollout projection, with new evidence and exact protocol IDs."""
    root = Path(episode)
    manifest = read_json(root / "manifest.json")
    case = prepared.case
    variation = manifest["scenario"].get("variation", {})
    if variation.get("software_case") != case:
        raise ValueError("Actual software case must be fixed before the first opportunity")
    window = expected_window(declaration, slot_id)
    slot = next(s for s in declaration["slots"] if s["slot_id"] == slot_id)
    initial = {"case": case, "reward_spec": prepared.reward_spec,
               "initial_business_sha256": prepared.prefix["prepared_business_state_sha256"]}
    runtime = variation.get("software_runtime", {})
    protocol_fields = ("first_member", "role_decision_limits", "scheduling_protocol")
    if (case.get("first_member") not in prepared.active_roles
            or not case.get("scheduling_protocol")
            or runtime.get("version") != "software-runtime-v0.28"
            or window["xi_id"] != case["case_id"] + "::first=" + case["first_member"]
            or window["xi_fingerprint"] != digest(json_bytes(initial))
            or slot["mapping_spec_id"] != MAPPER
            or slot["active_members"] != list(prepared.active_roles)
            or any(runtime.get(k) != case.get(k) for k in protocol_fields)):
        raise ValueError("Exact software case, scheduling protocol, stable members and Mapper differ")
    members = {role["role_id"]: {"actor_id": role["actor"], "origin": "target_model"}
               for role in prepared.scenario["roles"]}
    common = assess_record_permission(root, members=members, independent_capture=captured,
                                      spec_id=VALIDITY, window=window)
    evidence = software_work_evidence(root, assessment)
    if evidence["case"] != case:
        raise ValueError("Archived software work uses another case")
    checks = [check for component in common["components"].values() for check in component["checks"]]
    ref = {"manifest_sha256": evidence["manifest_sha256"],
           "independent_assessment_sha256": evidence["assessment_sha256"]}
    checks.extend([
        {"dimension": "basis", "value": True,
         "reason": "Public case, immutable source and actual integration input identity bind", "evidence": ref},
        {"dimension": "delivery", "value": (None if assessment["status"] == "unknown" else
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
    rollout = export_team_rollout(root, window=window, members=members, validity=validity, reward=reward)
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
        "training_probability_qualified": False, "optimizer_update_allowed": False,
        "scope": "Software development projection; not current training support or learning benefit",
    }
