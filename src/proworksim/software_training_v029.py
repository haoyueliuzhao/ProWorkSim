"""Frozen, limited software work-process routes for the new v0.29 sources.

This is an episode category, not final-code authorship or causal credit. Actual
member actions stay in their original MemberViews, even when code is overwritten,
work fails, or this mapper abstains. The v0.28 net-AST mapper is unchanged.
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

VERSION = "software-token-projection-v0.29"
MAPPER = "software-work-process-v0.29"
VALIDITY = "software-complete-work-v0.29"
CLASSES = ("concentrated_delivery", "contract_work_before_import", "contract_work_after_import")
SCOPE = (
    "Observed contract-contact work and exact patch-import order at fixed valid delivery; "
    "not final-code ownership, retained-input necessity, independent branches, or causal credit. "
    "Named callable changes are bounded syntactic contract contact, not proof that each edit "
    "was necessary. Raw member actions are never selected by this category."
)


class _WithoutDocstrings(ast.NodeTransformer):
    def generic_visit(self, node):
        node = super().generic_visit(node)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if (node.body and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                    and isinstance(node.body[0].value.value, str)):
                node.body = node.body[1:]
        return node


def _contract_units(text, names):
    """Only frozen named definitions; ignore comments, imports and other code."""
    try:
        tree = _WithoutDocstrings().visit(ast.parse(text))
    except (SyntaxError, ValueError):
        return None
    result = {}
    for name in names:
        node = tree
        for part in name.split("."):
            matches = [child for child in getattr(node, "body", [])
                       if isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
                       and child.name == part]
            if len(matches) > 1:
                return None  # Binding through duplicate definitions is outside this mapper.
            if not matches:
                node = None
                break
            node = matches[0]
        result[name] = ast.dump(node, include_attributes=False) if node is not None else None
    return result


def _test_unit(text, modules):
    """A direct asserted project call is a bounded executable work artifact.

    Merely importing a package or asserting a constant is not contract contact.
    Execution is checked separately against the exact archived test contents.
    """
    try:
        tree = _WithoutDocstrings().visit(ast.parse(text))
    except (SyntaxError, ValueError):
        return None
    imported = set()
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module in modules:
            imported.update(alias.asname or alias.name for alias in node.names if alias.name != "*")
        elif isinstance(node, ast.Import):
            imported.update(alias.asname or alias.name.split(".")[0] for alias in node.names
                            if alias.name.split(".")[0] in modules)
    contact = False
    for assertion in (node for node in tree.body if isinstance(node, ast.Assert)):
        for call in (node for node in ast.walk(assertion.test) if isinstance(node, ast.Call)):
            head = call.func
            while isinstance(head, (ast.Attribute, ast.Call)):
                head = head.value if isinstance(head, ast.Attribute) else head.func
            if isinstance(head, ast.Name) and head.id in imported:
                contact = True
    return {"executed_contract_assertion": ast.dump(tree, include_attributes=False) if contact else None}


def source_training_admission(case, gamma):
    """Purpose and collection mode are separate gates; success changes neither."""
    from .software_collaboration_v029 import validate_case

    validate_case(case)
    if gamma.get("source_usage") != case["usage"]:
        raise ValueError("The frozen window cannot change the source purpose")
    mode = gamma.get("collection_mode")
    if mode not in {"current_policy_collection", "frozen_development", "frozen_evaluation", "successor_work"}:
        raise ValueError("The source window needs its frozen collection mode")
    allowed = bool(case["usage"] == "policy_training" and case["training_eligible"] is True
                   and mode == "current_policy_collection")
    return {"version": VERSION, "purpose": case["usage"], "collection_mode": mode,
            "optimizer_update_allowed": allowed, "source_training_admission": allowed,
            "composition_reconfiguration_eligible": allowed,
            "source_partition_sha256": case["source_contract"]["source_partition_sha256"],
            "mapping_controls_token_ownership": False,
            "unmapped_and_trusted_failures_remain_base_material": allowed}


def software_work_evidence(episode, assessment):
    """Read exact actor-bound versions and changes, never repair the trajectory.

    A pre-import work item must still differ from baseline at that import's
    frontier. An edit reverted before the frontier cannot manufacture an early
    route. Subsequent rewrites and conflict repairs are allowed: this records
    actual work at the frontier, not retained whole-definition provenance.
    """
    from .software_collaboration_v029 import validate_case

    root = Path(episode)
    evidence = original_evidence(root, assessment)
    case = validate_case(evidence["case"])
    roots = case["source_contract"]["contract_roots"]
    state = read_json(root / "end/control/state.json")
    start = read_json(root / "start/control/state.json")
    facts = software_collaboration_facts(state)
    raw_events = facts["events"][len(start.get("software_events", [])):]
    evidence.update(version=VERSION, mapper_spec_id=MAPPER,
                    original_event_inventory=copy.deepcopy(raw_events),
                    contract_roots=copy.deepcopy(roots), relevant_contract_edits=[],
                    contract_work_frontiers=[], relevant_cross_member_inputs=[],
                    excluded_edit_sequences=[], excluded_integrations=[],
                    net_delivery_diagnostic={"status": "not_applicable",
                        "mapper": "software-work-methods-v0.28",
                        "reason": "Frozen v0.28 roots concern Marshmallow; new-source net ownership is not inferred"},
                    scope=SCOPE)
    delivery = evidence["delivery"]
    if delivery is None:
        return evidence
    events = evidence["events"]  # Existing binder cuts exactly at the fixed submission.
    store = Store(root / "end")

    def key(reference):
        return reference["object_id"], reference["version_id"]

    writes = {key(e["source_reference"]): e for e in events if e["kind"] in {"edit", "integrate"}}
    fixed_patches = {e["patch_id"]: e for e in events if e["kind"] == "patch_fixed"}
    bases = {key(e["base_reference"]) for e in fixed_patches.values()}
    if len(bases) != 1:
        raise ValueError("A process route requires one immutable common source baseline")
    baseline = next(iter(bases))
    modules = {path.split("/")[0] for path in roots if "/" in path} | {"consumer"}
    paths = (*roots, "test_member.py")

    @lru_cache(maxsize=None)
    def bundle(reference):
        return _bundle(store, state, dict(zip(("object_id", "version_id"), reference)))

    @lru_cache(maxsize=None)
    def units(reference, path):
        text = bundle(reference)["files"].get(path, "")
        return _test_unit(text, modules) if path == "test_member.py" else _contract_units(text, roots[path])

    @lru_cache(maxsize=None)
    def last_author(reference, path, unit):
        """Find a real edit at this frontier, without claiming final authorship."""
        event = writes.get(reference)
        current = units(reference, path)
        if event is None or current is None:
            return None
        previous = key(event["previous_reference"])
        before = units(previous, path)
        if before is not None and current.get(unit) == before.get(unit):
            return last_author(previous, path, unit)
        if event["kind"] == "edit":
            return event["sequence"]
        incoming = key(event["input_reference"])
        source = units(incoming, path)
        return (last_author(incoming, path, unit) if source is not None
                and source.get(unit) == current.get(unit) else None)

    by_sequence = {e["sequence"]: e for e in events}
    substantive = {}
    for event in evidence["actual_file_edits"]:
        path = event["path"]
        if path not in paths:
            continue
        before, after = units(key(event["previous_reference"]), path), units(key(event["source_reference"]), path)
        original = units(baseline, path)
        if after is None or original is None:
            continue
        names = [name for name, value in after.items() if value is not None
                 and value != original.get(name) and (before is None or value != before.get(name))]
        if names:
            substantive[event["sequence"]] = {**copy.deepcopy(event), "contract_units": names,
                                               "repairs_unparseable_previous": before is None}
    evidence["relevant_contract_edits"] = [substantive[k] for k in sorted(substantive)]

    def test_executions(reference, path):
        if path != "test_member.py":
            return []
        return [e["sequence"] for e in events if e["kind"] == "test" and e.get("executed")
                and e.get("driver_completed") and e.get("returncode") == 0
                and units(key(e["source_reference"]), path) == units(reference, path)]

    def active_work(reference, actor):
        result = []
        for path in paths:
            current, original = units(reference, path), units(baseline, path)
            if current is None or original is None:
                continue
            for name, value in current.items():
                sequence = last_author(reference, path, name)
                if (value is None or value == original.get(name) or sequence not in substantive
                        or by_sequence[sequence]["actor_id"] != actor):
                    continue
                executions = test_executions(reference, path)
                if path == "test_member.py" and not executions:
                    continue
                result.append({"sequence": sequence, "actor_id": actor, "path": path,
                               "unit": name, "semantic_sha256": digest(value.encode()),
                               "test_execution_sequences": executions})
        return result

    selected_edits = set()
    for event in (e for e in events if e["kind"] == "integrate"):
        patch = facts["patches"][event["patch_id"]]
        if patch["author"] == event["actor_id"]:
            continue
        fixing = fixed_patches.get(event["patch_id"])
        previous, output, incoming = (key(event[name]) for name in (
            "previous_reference", "source_reference", "input_reference"))
        if fixing is None or patch["source_reference"] != event["input_reference"]:
            raise ValueError("Process input must name a current, exactly fixed partner patch")
        imported = []
        for work in active_work(incoming, patch["author"]):
            path, name = work["path"], work["unit"]
            if work["sequence"] >= fixing["sequence"]:
                continue
            before, after = units(previous, path), units(output, path)
            if bundle(previous)["files"].get(path) == bundle(output)["files"].get(path):
                continue
            source = units(incoming, path)
            if before is not None and source is not None and before.get(name) == source.get(name):
                continue
            if before is not None and after is not None and before.get(name) == after.get(name):
                continue
            # A conflict is still a real import of a fixed input, with the
            # unresolved syntax explicitly retained. Later work must close it.
            if after is None and path not in event["conflicts"]:
                continue
            imported.append(work)
        if not imported:
            evidence["excluded_integrations"].append({"sequence": event["sequence"],
                "patch_id": event["patch_id"],
                "reason": "No changed contract unit from a current partner-authored fixed input"})
            continue
        recipient = event["actor_id"]
        subsequent = [e["sequence"] for e in events if e["actor_id"] == recipient
                      and e["sequence"] > event["sequence"] and (
                          e["sequence"] in substantive or
                          (e["kind"] == "test" and e.get("executed") and e.get("driver_completed")) or
                          (e["kind"] == "submit" and e.get("delivery_id") == delivery["delivery_id"]))]
        if not subsequent:
            evidence["excluded_integrations"].append({"sequence": event["sequence"],
                "patch_id": event["patch_id"], "reason": "No related subsequent work or fixed delivery"})
            continue
        frontier = active_work(previous, recipient)
        selected_edits.update(work["sequence"] for work in frontier + imported)
        edge = {"sequence": event["sequence"], "patch_id": event["patch_id"],
                "sender": patch["author"], "recipient": recipient,
                "input_reference": copy.deepcopy(event["input_reference"]),
                "previous_reference": copy.deepcopy(event["previous_reference"]),
                "output_reference": copy.deepcopy(event["source_reference"]),
                "conflicts": copy.deepcopy(event["conflicts"]),
                "imported_contract_work": imported, "recipient_work_before_input": frontier,
                "subsequent_work_sequences": subsequent}
        evidence["relevant_cross_member_inputs"].append(edge)
        evidence["contract_work_frontiers"].append({"kind": "before_contract_import",
            "sequence": event["sequence"], "actor_id": recipient,
            "source_reference": copy.deepcopy(event["previous_reference"]), "work": frontier})
    final_work = active_work(key(delivery["source_reference"]), delivery["actor_id"])
    selected_edits.update(work["sequence"] for work in final_work)
    evidence["contract_work_frontiers"].append({"kind": "fixed_delivery",
        "sequence": next(e["sequence"] for e in events if e["kind"] == "submit"
                         and e["delivery_id"] == delivery["delivery_id"]),
        "actor_id": delivery["actor_id"], "source_reference": copy.deepcopy(delivery["source_reference"]),
        "work": final_work})
    evidence["excluded_edit_sequences"] = [e["sequence"] for e in evidence["actual_file_edits"]
                                          if e["sequence"] not in selected_edits]
    return evidence


def map_software_method(rollout, evidence):
    result = {"version": VERSION, "rollout_id": rollout["rollout_id"], "spec_id": MAPPER,
              "status": "unmapped", "class_id": None,
              "evidence_sha256": digest(json_bytes(evidence)), "scope": SCOPE}
    if rollout.get("manifest_sha256") != evidence["manifest_sha256"]:
        raise ValueError("Method evidence belongs to another original rollout")
    if evidence.get("mapper_spec_id") != MAPPER:
        raise ValueError("Process evidence must use the frozen v0.29 mapper")
    if (rollout["work_validity"]["value"] is not True
            or evidence["assessment_status"] != "evaluable"
            or evidence["parent_acceptance_passed"] is not True):
        return {**result, "reason": "Complete work false or unknown; preserve original base-learning material"}
    if not evidence["delivery"]:
        return {**result, "reason": "No fixed software delivery"}
    integrator = evidence["delivery"]["actor_id"]
    frontiers = [f for f in evidence["contract_work_frontiers"] if f["actor_id"] == integrator]
    own = [work for frontier in frontiers for work in frontier["work"]]
    if not own:
        return {**result, "reason": "No current integrator contract work at an import or delivery frontier"}
    inputs = [edge for edge in evidence["relevant_cross_member_inputs"] if edge["recipient"] == integrator]
    if inputs:
        first_input = min(edge["sequence"] for edge in inputs)
        category = ("contract_work_before_import" if any(work["sequence"] < first_input for work in own)
                    else "contract_work_after_import")
    else:
        category = "concentrated_delivery"
    return {**result, "status": "mapped", "class_id": category,
            "reason": "Independently valid fixed delivery with observed contract work and exact input order"}


def export_software_episode(prepared, episode, assessment, *, declaration, slot_id, captured):
    """Original-member projection plus source-scoped process categorization.

    Probability qualification is checked later against the actual collector's
    selected requests and owner ledger. This exporter cannot certify gradients.
    """
    root = Path(episode)
    manifest = read_json(root / "manifest.json")
    case = prepared.case
    variation = manifest["scenario"].get("variation", {})
    if variation.get("software_case") != case:
        raise ValueError("Actual software case must be frozen before the first opportunity")
    window = expected_window(declaration, slot_id)
    slot = next(s for s in declaration["slots"] if s["slot_id"] == slot_id)
    initial = {"case": case, "reward_spec": prepared.reward_spec,
               "initial_business_sha256": prepared.prefix["prepared_business_state_sha256"]}
    runtime = variation.get("software_runtime", {})
    if (case.get("first_member") not in prepared.active_roles
            or runtime.get("version") != "software-runtime-v0.29"
            or window["xi_id"] != case["case_id"] + "::first=" + case["first_member"]
            or window["xi_fingerprint"] != digest(json_bytes(initial))
            or slot["mapping_spec_id"] != MAPPER
            or slot["active_members"] != list(prepared.active_roles)
            or any(runtime.get(k) != case.get(k) for k in (
                "first_member", "role_decision_limits", "scheduling_protocol"))):
        raise ValueError("Exact source case, first member, scheduling protocol and Mapper differ")
    scope = source_training_admission(case, declaration["gamma_identity"])
    if (runtime.get("source_usage") != scope["purpose"]
            or runtime.get("collection_mode") != scope["collection_mode"]):
        raise ValueError("Archived runtime cannot change source purpose or collection mode")
    members = {role["role_id"]: {"actor_id": role["actor"], "origin": "target_model"}
               for role in prepared.scenario["roles"]}
    common = assess_record_permission(root, members=members, independent_capture=captured,
                                      spec_id=VALIDITY, window=window)
    evidence = software_work_evidence(root, assessment)
    if evidence["case"] != case:
        raise ValueError("Archived software work uses another frozen source case")
    checks = [check for component in common["components"].values() for check in component["checks"]]
    ref = {"manifest_sha256": evidence["manifest_sha256"],
           "independent_assessment_sha256": evidence["assessment_sha256"],
           "source_contract": copy.deepcopy(case["source_contract"])}
    checks.extend([
        {"dimension": "basis", "value": True,
         "reason": "Frozen source, public contract, exact patch inputs and case purpose bind", "evidence": ref},
        {"dimension": "delivery", "value": (None if assessment["status"] == "unknown" else
            bool(evidence["delivery"] and evidence["parent_acceptance_passed"])),
         "reason": "Independent fixed delivery checks API, consumer/library contact and selected regressions",
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
    rollout["online_scope"] = scope
    mapping = map_software_method(rollout, evidence)
    bound = bind_rollout(declaration, slot_id, rollout, mapping=mapping)
    views = {member: member_view(rollout, member) for member in members}
    return {"slot_id": slot_id, "rollout": rollout, "reward": reward,
            "active_members": list(prepared.active_roles), "mapping": mapping}, {
        "version": VERSION, "semantic_evidence": evidence, "work_validity": validity,
        "method_mapping": mapping, "member_views": views,
        "binding_matches_views": bound["member_views"] == views,
        "training_probability_qualified": False,
        "optimizer_update_allowed": scope["optimizer_update_allowed"],
        "scope": "Current original member actions; process classes never replace actual token ownership",
    }
